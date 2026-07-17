"""OAuth 2.1 authorization server for knowledge-mcp.

Implements exactly what claude.ai custom connectors need to talk to a remote
MCP server:

  * RFC 8414  authorization-server metadata  (/.well-known/oauth-authorization-server)
  * RFC 9728  protected-resource metadata    (/.well-known/oauth-protected-resource)
  * RFC 7591  dynamic client registration    (/oauth/register)
  * Authorization-code flow with mandatory PKCE (S256) and refresh tokens

The "login" is a single password (OAUTH_PASSWORD) typed once per device on a
small HTML consent page — this is a single-user server, not a multi-tenant IdP.
Issued tokens are stored as SHA-256 hashes in oauth_state.json (mode 0600), so
a leaked state file does not leak usable tokens.
"""

from __future__ import annotations

import asyncio
import base64
import hashlib
import hmac
import html
import json
import os
import secrets
import tempfile
import time
from pathlib import Path
from urllib.parse import urlencode, urlparse

from starlette.applications import Starlette
from starlette.middleware import Middleware
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import HTMLResponse, JSONResponse, RedirectResponse
from starlette.routing import Route

import config as _config

ISSUER = os.environ.get("OAUTH_ISSUER", _config.load()["server"]["public_url"])
OAUTH_PASSWORD = os.environ.get("OAUTH_PASSWORD", "")
# Veränderliche Daten liegen im Datenverzeichnis (im Container ein Volume);
# ohne KMCP_DATA_DIR bleibt es wie bisher der Programmordner.
DATA_DIR = Path(os.environ.get("KMCP_DATA_DIR", str(Path(__file__).parent)))
STATE_FILE = DATA_DIR / "oauth_state.json"

CODE_TTL = 300  # 5 min
ACCESS_TTL = 30 * 86400
REFRESH_TTL = 180 * 86400


def _sha(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def _now() -> int:
    return int(time.time())


def _write_atomic(state: dict) -> None:
    """Zustand atomar und von Anfang an mit Modus 0600 schreiben.

    write_text()+chmod() hatte zwei Lücken: ein Crash mitten im Schreiben hinterließ
    eine halbe Datei (die danach JEDE Anfrage mit 500 beantwortete), und bei der
    Erstanlage war die Datei bis zum chmod kurz für andere lesbar. mkstemp legt mit
    0600 an, os.replace macht den Tausch untrennbar (Muster wie vault._write_file).
    """
    fd, tmp = tempfile.mkstemp(dir=STATE_FILE.parent, prefix=".oauth-", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(json.dumps(state, indent=2))
        os.replace(tmp, STATE_FILE)
    except OSError:
        Path(tmp).unlink(missing_ok=True)
        raise


def _load() -> dict:
    state: dict = {}
    if STATE_FILE.exists():
        try:
            geladen = json.loads(STATE_FILE.read_text())
            if not isinstance(geladen, dict):
                raise ValueError("oauth_state.json ist kein JSON-Objekt")
            buckets = ("clients", "codes", "tokens", "refresh")
            if any(k in geladen and not isinstance(geladen[k], dict) for k in buckets):
                raise ValueError("oauth_state.json hat falsch typisierte Abschnitte")
            state = geladen
        except (OSError, ValueError):
            # Kaputte bzw. halb geschriebene Datei (Crash mitten im Schreiben) darf
            # nicht die komplette Anmeldung lahmlegen: quarantänisieren und mit
            # leerem Zustand weiter — Clients melden sich dann einfach neu an.
            try:
                STATE_FILE.replace(STATE_FILE.with_name(STATE_FILE.name + ".korrupt"))
            except OSError:
                pass
    state.setdefault("clients", {})
    state.setdefault("codes", {})
    state.setdefault("tokens", {})
    state.setdefault("refresh", {})
    _migrate(state)
    return state


def _migrate(state: dict) -> None:
    """Alt-Tokens (vor der Geräte-Verwaltung) haben keine Sitzungs-ID — ohne die
    ließen sie sich weder anzeigen noch einzeln abmelden. Hier nachgerüstet."""
    changed = False
    for bucket in ("tokens", "refresh"):
        for h, entry in state[bucket].items():
            if not entry.get("sid"):
                entry["sid"] = h[:12]
                entry.setdefault("created", entry.get("exp", _now()) - ACCESS_TTL)
                changed = True
    if changed:
        _write_atomic(state)


def _save(state: dict) -> None:
    now = _now()
    state["codes"] = {k: v for k, v in state["codes"].items() if v["exp"] > now}
    state["tokens"] = {k: v for k, v in state["tokens"].items() if v["exp"] > now}
    state["refresh"] = {k: v for k, v in state["refresh"].items() if v["exp"] > now}
    _write_atomic(state)


SEEN_THROTTLE = 300  # "zuletzt gesehen" höchstens alle 5 Minuten schreiben


def validate_access_token(token: str, user_agent: str = "") -> bool:
    """Wird vom Bearer-Gate für jede Anfrage aufgerufen.

    Nebenbei wird der Zeitpunkt des letzten Zugriffs festgehalten — damit man in der
    UI sieht, welches Gerät noch aktiv ist. Geschrieben wird höchstens alle 5 Minuten,
    sonst wäre jede Anfrage ein Dateizugriff.
    """
    if not token.startswith("kmcp_"):
        return False
    state = _load()
    entry = state["tokens"].get(_sha(token))
    if not entry or entry["exp"] <= _now():
        return False
    now = _now()
    if now - entry.get("last_seen", 0) > SEEN_THROTTLE:
        entry["last_seen"] = now
        if user_agent and not entry.get("ua"):
            entry["ua"] = user_agent[:120]
        _save(state)
    return True


def _device_label(entry: dict, clients: dict) -> str:
    """Sprechender Name für ein Gerät/Programm.

    Wird bei jedem Abruf neu gebildet (nicht gespeichert) — darum darf und muss er
    in der Sprache des Aufrufers erscheinen.
    """
    from api.i18n import T

    cid = entry.get("client_id", "")
    if cid == "web-ui":
        return T("Weboberfläche")
    name = clients.get(cid, {}).get("name") or ""
    return name or T("Unbekannter Client ({cid})", cid=cid[:8])


def list_sessions() -> list[dict]:
    """Alle gültigen Zugänge — je Sitzung ein Eintrag (Access + Refresh gehören zusammen)."""
    state = _load()
    now = _now()
    out: dict[str, dict] = {}
    for h, t in state["tokens"].items():
        if t["exp"] <= now:
            continue
        sid = t.get("sid", h[:12])
        out[sid] = {
            "id": sid,
            "label": _device_label(t, state["clients"]),
            "kind": "web" if t.get("client_id") == "web-ui" else "mcp",
            "created": t.get("created"),
            "last_seen": t.get("last_seen"),
            "expires": t["exp"],
            "ua": t.get("ua", ""),
        }
    return sorted(out.values(), key=lambda s: s.get("last_seen") or s.get("created") or 0, reverse=True)


def revoke_session(sid: str) -> bool:
    """Ein Gerät abmelden — Access- UND Refresh-Token verfallen sofort."""
    state = _load()
    before = len(state["tokens"]) + len(state["refresh"])
    state["tokens"] = {h: t for h, t in state["tokens"].items() if t.get("sid") != sid}
    state["refresh"] = {h: t for h, t in state["refresh"].items() if t.get("sid") != sid}
    removed = before - (len(state["tokens"]) + len(state["refresh"]))
    if removed:
        _save(state)
    return bool(removed)


def revoke_all(except_sid: str = "") -> int:
    """Alle Geräte abmelden (die aktuelle Sitzung bleibt bestehen)."""
    state = _load()
    now = _now()
    sids = {
        t["sid"]
        for t in state["tokens"].values()
        if t.get("sid") and t["sid"] != except_sid and t["exp"] > now
    }
    state["tokens"] = {h: t for h, t in state["tokens"].items() if t.get("sid") == except_sid}
    state["refresh"] = {h: t for h, t in state["refresh"].items() if t.get("sid") == except_sid}
    _save(state)
    return len(sids)


def session_of(token: str) -> str:
    """Zu welcher Sitzung gehört dieses Token? (damit man sich nicht selbst aussperrt)"""
    entry = _load()["tokens"].get(_sha(token), {})
    return entry.get("sid", "")


# --------------------------------------------------------------------------
# discovery metadata
# --------------------------------------------------------------------------


def _as_metadata(request: Request) -> JSONResponse:
    return JSONResponse(
        {
            "issuer": ISSUER,
            "authorization_endpoint": f"{ISSUER}/oauth/authorize",
            "token_endpoint": f"{ISSUER}/oauth/token",
            "registration_endpoint": f"{ISSUER}/oauth/register",
            "response_types_supported": ["code"],
            "grant_types_supported": ["authorization_code", "refresh_token"],
            "code_challenge_methods_supported": ["S256"],
            "token_endpoint_auth_methods_supported": ["none", "client_secret_post"],
            "scopes_supported": ["mcp"],
        }
    )


def _pr_metadata(request: Request) -> JSONResponse:
    return JSONResponse(
        {
            "resource": f"{ISSUER}/mcp",
            "authorization_servers": [ISSUER],
            "bearer_methods_supported": ["header"],
            "scopes_supported": ["mcp"],
        }
    )


# --------------------------------------------------------------------------
# dynamic client registration (RFC 7591)
# --------------------------------------------------------------------------

# Dynamische Client-Registrierung ist per RFC 7591 offen (claude.ai holt sich hier
# ohne Anmeldung eine client_id). Offen heißt nicht schrankenlos: eine Drossel pro IP
# und eine harte Obergrenze halten die Zustandsdatei klein. Bei Erreichen der Grenze
# werden verwaiste Clients (ohne gültige Tokens) verworfen — der jüngste zuerst behalten.
MAX_CLIENTS = 500


def _prune_clients(state: dict) -> None:
    if len(state["clients"]) <= MAX_CLIENTS:
        return
    referenced = {t.get("client_id") for bucket in ("tokens", "refresh") for t in state[bucket].values()}
    orphans = sorted(
        (cid for cid in state["clients"] if cid not in referenced),
        key=lambda cid: state["clients"][cid].get("created", 0),
    )
    while len(state["clients"]) > MAX_CLIENTS and orphans:
        del state["clients"][orphans.pop(0)]


def _redirect_uri_ok(uri: str) -> bool:
    """https überall erlaubt, http nur auf echtem Loopback (localhost/127.0.0.1).

    Der frühere Präfix-Check ließ sich austricksen: http://localhost@evil.com
    (Host ist evil.com), http://localhost.evil.com und http://127.0.0.1.evil.com
    begannen alle mit dem harmlosen Präfix. Deshalb strikt per urlparse prüfen —
    hostname ignoriert Userinfo, Suffixe und Groß-/Kleinschreibung.
    """
    try:
        p = urlparse(uri)
        host = p.hostname
    except ValueError:
        return False
    if p.scheme == "https":
        return bool(host)
    return p.scheme == "http" and host in ("localhost", "127.0.0.1")


async def _register(request: Request) -> JSONResponse:
    import ratelimit

    ip = request.headers.get("cf-connecting-ip") or (request.client.host if request.client else "?")
    erlaubt, _ = ratelimit.throttle("register", ip)
    if not erlaubt:
        return JSONResponse(
            {"error": "temporarily_unavailable", "error_description": "too many registrations"},
            status_code=429,
        )
    try:
        body = await request.json()
    except Exception:
        return JSONResponse({"error": "invalid_client_metadata"}, status_code=400)
    if not isinstance(body, dict):
        return JSONResponse({"error": "invalid_client_metadata"}, status_code=400)
    redirect_uris = body.get("redirect_uris") or []
    if (
        not isinstance(redirect_uris, list)
        or not redirect_uris
        or len(redirect_uris) > 10
        or not all(isinstance(u, str) and len(u) <= 2048 and _redirect_uri_ok(u) for u in redirect_uris)
    ):
        return JSONResponse({"error": "invalid_redirect_uri"}, status_code=400)
    state = _load()
    client_id = secrets.token_urlsafe(16)
    state["clients"][client_id] = {
        "redirect_uris": redirect_uris,
        "name": str(body.get("client_name", ""))[:100],
        "created": _now(),
    }
    _prune_clients(state)
    _save(state)
    return JSONResponse(
        {
            "client_id": client_id,
            "redirect_uris": redirect_uris,
            "client_name": state["clients"][client_id]["name"],
            "token_endpoint_auth_method": "none",
            "grant_types": ["authorization_code", "refresh_token"],
            "response_types": ["code"],
        },
        status_code=201,
    )


# --------------------------------------------------------------------------
# authorization endpoint: password-protected consent page
# --------------------------------------------------------------------------

_PAGE = """<!doctype html><html lang="de"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="robots" content="noindex"><title>Knowledge MCP — Anmeldung</title>
<style>
 body{{font-family:system-ui,sans-serif;background:#0f1420;color:#e8ecf3;display:flex;
      min-height:100vh;align-items:center;justify-content:center;margin:0}}
 form{{background:#1a2233;padding:2rem;border-radius:12px;max-width:22rem;width:90%}}
 h1{{font-size:1.1rem;margin:0 0 .4rem}} p{{color:#9aa7bd;font-size:.85rem;margin:.2rem 0 1rem}}
 input[type=password],input[type=text]{{width:100%;padding:.6rem;border-radius:8px;
      border:1px solid #3a4660;background:#0f1420;color:#e8ecf3;font-size:1rem;
      box-sizing:border-box;margin-top:.5rem}}
 button{{width:100%;margin-top:1rem;padding:.65rem;border:0;border-radius:8px;
      background:#4f7cff;color:#fff;font-size:1rem;cursor:pointer}}
 .err{{color:#ff7a7a;font-size:.85rem}}
 .ziel{{background:#0f1420;border:1px solid #3a4660;border-radius:8px;padding:.55rem .7rem;
      font-size:.85rem;margin:.6rem 0;word-break:break-all}}
 .ziel b{{color:#8fb0ff}}
 .cid{{color:#9aa7bd;font-size:.75rem;word-break:break-all}}
</style></head><body><form method="post" action="/oauth/authorize">
<h1>Knowledge MCP Hub</h1>
<p><b>{client}</b> möchte auf deinen Knowledge-Server zugreifen (Graphify-Graphen&nbsp;+ Secrets-Vault).</p>
<div class="ziel">Der Anmeldecode geht nach der Anmeldung an:<br><b>{host}</b></div>
<p class="cid">Anfragende Client-ID: {client_id}<br>Gib dein Passwort nur ein, wenn Ziel und Client
genau dem Dienst entsprechen, den du gerade selbst verbinden willst.</p>
{error}
<input type="password" name="password" placeholder="Zugangspasswort" autofocus required>
{totp}
{hidden}
<button type="submit">Zugriff erlauben</button></form></body></html>"""

# Zweiter Faktor auf der Consent-Seite: nur sichtbar, wenn 2FA aktiviert ist.
# Akzeptiert wird der 6-stellige TOTP-Code oder ein Wiederherstellungscode.
_TOTP_FELD = (
    '<input type="text" name="code" inputmode="numeric" autocomplete="one-time-code" '
    'placeholder="2FA-Code (6-stellig oder Wiederherstellungscode)" required>'
)


def _password_ok(password: str) -> bool:
    """Passwort gegen den Vault prüfen (dort ist es nicht gespeichert, sondern
    nur als Verpackung des Hauptschlüssels hinterlegt). Fällt auf das alte
    Klartext-Passwort zurück, wenn der Vault noch keine Passwort-Verpackung hat."""
    if not password:
        return False
    import vault as _vault

    if _vault.status().get("has_password"):
        return _vault.unlock(password)
    # Byteweise vergleichen: compare_digest wirft auf str mit Nicht-ASCII-Zeichen
    # (Umlaute im eingegebenen Passwort) einen TypeError — das wurde ein 500 statt
    # „falsches Passwort", und der Fehlversuch wäre nie gezählt worden.
    try:
        return bool(OAUTH_PASSWORD) and hmac.compare_digest(
            password.encode("utf-8"), OAUTH_PASSWORD.encode("utf-8")
        )
    except UnicodeError:
        return False


def _authorize_checks(state: dict, params) -> tuple[dict | None, str | None]:
    client = state["clients"].get(params.get("client_id", ""))
    if client is None:
        return None, "unknown client_id"
    if params.get("redirect_uri") not in client["redirect_uris"]:
        return None, "redirect_uri not registered for this client"
    if params.get("response_type") != "code":
        return None, "only response_type=code is supported"
    if not params.get("code_challenge") or params.get("code_challenge_method") != "S256":
        return None, "PKCE with S256 is required"
    return client, None


async def _zweiter_faktor_aktiv() -> bool:
    """Ist 2FA eingeschaltet? (Vault-Zugriff, deshalb im Thread.)

    VaultLocked → False: Dann ist der 2FA-Zustand schlicht unlesbar. Auf dem
    Consent-POST passiert das nur, wenn die Passwortprüfung über den alten
    Klartext-Fallback lief (Vault ohne Passwort-Verpackung) — und auf so einem
    Hub kann 2FA nie eingerichtet worden sein (das Setup braucht den entsperrten
    Vault). Auf dem GET ist der Vault vor der ersten Anmeldung typischerweise
    gesperrt; dann zeigt das Formular das Code-Feld eben erst nach dem ersten
    Absenden — geprüft wird auf dem POST in jedem Fall verbindlich.
    """
    import totp
    import vault as _v

    try:
        return await asyncio.to_thread(totp.is_enabled)
    except _v.VaultLocked:
        return False


async def _authorize(request: Request):
    params = request.query_params if request.method == "GET" else (await request.form())
    state = _load()
    client, problem = _authorize_checks(state, params)
    if problem:
        return HTMLResponse(f"<h3>OAuth-Fehler</h3><p>{html.escape(problem)}</p>", status_code=400)

    error_html = ""
    if request.method == "POST":
        import ratelimit

        ip = request.headers.get("cf-connecting-ip") or (request.client.host if request.client else "?")
        if not ratelimit.check("login", ip):
            import vault as _v

            _v.audit("LOGIN-BLOCKED", ip, client="oauth")
            return HTMLResponse(
                "<h3>Zu viele Fehlversuche</h3><p>Bitte 15 Minuten warten.</p>", status_code=429
            )
        password = str(params.get("password", ""))
        # scrypt (Vault-Entpackung) ist absichtlich langsam — im Thread rechnen,
        # sonst friert jeder Consent-POST die ganze Event-Loop ein.
        ok = await asyncio.to_thread(_password_ok, password)
        fehlertext = "Falsches Passwort."
        fehlversuch = True  # für die 5/15-min-Sperre zählen?
        if ok and await _zweiter_faktor_aktiv():
            # Bei aktivem 2FA reicht das Passwort allein NIE — ohne gültigen
            # TOTP-/Wiederherstellungscode wird kein Anmeldecode ausgestellt.
            import totp

            code = str(params.get("code", "")).strip()
            if not code:
                # Passwort stimmt schon, es fehlt nur der zweite Faktor — das ist
                # (wie beim UI-Login) kein Fehlversuch und wird nicht gezählt.
                ok, fehlertext, fehlversuch = False, "Bitte auch den 2FA-Code eingeben.", False
            elif not await asyncio.to_thread(totp.check, code):
                ok, fehlertext = False, "2FA-Code stimmt nicht."
        if ok:
            code = secrets.token_urlsafe(32)
            state["codes"][_sha(code)] = {
                "client_id": params["client_id"],
                "redirect_uri": params["redirect_uri"],
                "code_challenge": params["code_challenge"],
                "exp": _now() + CODE_TTL,
            }
            _save(state)
            ratelimit.record_success("login", ip)
            sep = "&" if "?" in params["redirect_uri"] else "?"
            qs = urlencode({"code": code, **({"state": params["state"]} if params.get("state") else {})})
            return RedirectResponse(f"{params['redirect_uri']}{sep}{qs}", status_code=302)
        if fehlversuch:
            import vault as _v

            ratelimit.record_failure("login", ip)
            _v.audit("LOGIN-FAIL", f"{ip} (oauth)", client="oauth")
        error_html = f'<p class="err">{fehlertext}</p>'

    hidden = "".join(
        f'<input type="hidden" name="{k}" value="{html.escape(str(params.get(k, "")), quote=True)}">'
        for k in (
            "response_type",
            "client_id",
            "redirect_uri",
            "state",
            "code_challenge",
            "code_challenge_method",
            "scope",
            "resource",
        )
        if params.get(k)
    )
    try:
        ziel_host = urlparse(str(params.get("redirect_uri", ""))).netloc
    except ValueError:
        ziel_host = ""
    return HTMLResponse(
        _PAGE.format(
            client=html.escape(client["name"] or "Ein MCP-Client"),
            host=html.escape(ziel_host or str(params.get("redirect_uri", "")), quote=True),
            client_id=html.escape(str(params.get("client_id", "")), quote=True),
            error=error_html,
            totp=_TOTP_FELD if await _zweiter_faktor_aktiv() else "",
            hidden=hidden,
        )
    )


# --------------------------------------------------------------------------
# token endpoint
# --------------------------------------------------------------------------


def _issue(state: dict, client_id: str, sid: str = "", user_agent: str = "") -> dict:
    """Access- + Refresh-Token ausstellen. `sid` klammert beide zu einer Sitzung —
    so lässt sich ein Gerät später mit einem Klick vollständig abmelden."""
    access = "kmcp_" + secrets.token_urlsafe(32)
    refresh = "kmcpr_" + secrets.token_urlsafe(32)
    sid = sid or secrets.token_urlsafe(9)
    now = _now()
    meta = {"client_id": client_id, "sid": sid, "created": now}
    state["tokens"][_sha(access)] = {
        **meta,
        "exp": now + ACCESS_TTL,
        "last_seen": now,
        "ua": user_agent[:120],
    }
    state["refresh"][_sha(refresh)] = {**meta, "exp": now + REFRESH_TTL}
    return {
        "access_token": access,
        "token_type": "Bearer",
        "expires_in": ACCESS_TTL,
        "refresh_token": refresh,
        "scope": "mcp",
    }


def _token_json(payload: dict, status_code: int = 200) -> JSONResponse:
    """Antwort des Token-Endpunkts: darf nirgends zwischengespeichert werden
    (RFC 6749 §5.1) — weder im Browser noch auf einem Proxy dazwischen."""
    return JSONResponse(
        payload,
        status_code=status_code,
        headers={"Cache-Control": "no-store", "Pragma": "no-cache"},
    )


async def _token(request: Request) -> JSONResponse:
    import ratelimit

    # Drossel gegen Code-/Refresh-Raten (abgemildert durch PKCE + Einmalnutzung,
    # aber RFC 6819 empfiehlt Throttling trotzdem) — wie bei /oauth/register.
    ip = request.headers.get("cf-connecting-ip") or (request.client.host if request.client else "?")
    erlaubt, _ = ratelimit.throttle("token", ip)
    if not erlaubt:
        return _token_json(
            {"error": "temporarily_unavailable", "error_description": "too many requests"},
            status_code=429,
        )
    form = await request.form()
    grant = form.get("grant_type")
    state = _load()

    if grant == "authorization_code":
        entry = state["codes"].pop(_sha(str(form.get("code", ""))), None)
        if entry is not None:
            # Der Code ist mit DIESEM Versuch verbraucht — auch wenn der Tausch
            # danach noch scheitert (falscher Verifier, client_id-/redirect-Mismatch).
            # Sonst ließe sich der PKCE-Verifier innerhalb der 5-min-TTL unbegrenzt
            # raten (RFC 6749 §4.1.2: Codes sind einmalig).
            _save(state)
        if entry is None or entry["exp"] < _now():
            return _token_json({"error": "invalid_grant"}, status_code=400)
        if form.get("client_id") != entry["client_id"] or form.get("redirect_uri") != entry["redirect_uri"]:
            return _token_json({"error": "invalid_grant"}, status_code=400)
        verifier = str(form.get("code_verifier", ""))
        expected = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode()
        if not hmac.compare_digest(expected, entry["code_challenge"]):
            return _token_json(
                {"error": "invalid_grant", "error_description": "PKCE failed"}, status_code=400
            )
        ua = request.headers.get("user-agent", "")
        payload = _issue(state, entry["client_id"], user_agent=ua)
        _save(state)
        return _token_json(payload)

    if grant == "refresh_token":
        key = _sha(str(form.get("refresh_token", "")))
        entry = state["refresh"].pop(key, None)  # Rotation: altes Refresh-Token stirbt
        if entry is None or entry["exp"] < _now():
            return _token_json({"error": "invalid_grant"}, status_code=400)
        # Sitzung bleibt dieselbe -> das Gerät behält seinen Eintrag in der Liste
        payload = _issue(
            state,
            entry["client_id"],
            sid=entry.get("sid", ""),
            user_agent=request.headers.get("user-agent", ""),
        )
        _save(state)
        return _token_json(payload)

    return _token_json({"error": "unsupported_grant_type"}, status_code=400)


class _SecurityHeaders(BaseHTTPMiddleware):
    """Schutz-Header für ALLE /oauth-Antworten (Consent, Token, Discovery, Fehler).

    Die Consent-Seite nimmt das Zugangspasswort entgegen und ist sessionlos per
    Form-POST erreichbar — ohne frame-ancestors/X-Frame-Options wäre sie per
    Iframe clickjacking-bar. Die Seite kommt ohne ein einziges Skript aus (nur
    Inline-Style), darum darf die CSP hier noch strenger sein als die der UI.
    """

    async def dispatch(self, request, call_next):
        resp = await call_next(request)
        # KEIN form-action: Die Consent-Seite MUSS nach dem Absenden per 302 an die
        # (serverseitig geprüfte) redirect_uri des Clients weiterleiten — meist eine
        # Fremd-Origin wie chatgpt.com. `form-action 'self'` verbietet dem Browser
        # genau diese Weiterleitung (CSP prüft auch Redirect-Ziele) und bricht damit
        # JEDEN OAuth-Login. Clickjacking-Schutz kommt aus frame-ancestors + X-Frame.
        resp.headers.setdefault(
            "Content-Security-Policy",
            "default-src 'none'; style-src 'unsafe-inline'; frame-ancestors 'none'; base-uri 'none'",
        )
        resp.headers["X-Content-Type-Options"] = "nosniff"
        resp.headers["X-Frame-Options"] = "DENY"
        resp.headers["Referrer-Policy"] = "no-referrer"
        resp.headers["Permissions-Policy"] = "geolocation=(), microphone=(), camera=()"
        return resp


oauth_app = Starlette(
    middleware=[Middleware(_SecurityHeaders)],
    routes=[
        Route("/.well-known/oauth-authorization-server", _as_metadata),
        Route("/.well-known/oauth-authorization-server/{path:path}", _as_metadata),
        Route("/.well-known/oauth-protected-resource", _pr_metadata),
        Route("/.well-known/oauth-protected-resource/{path:path}", _pr_metadata),
        Route("/oauth/register", _register, methods=["POST"]),
        Route("/oauth/authorize", _authorize, methods=["GET", "POST"]),
        Route("/oauth/token", _token, methods=["POST"]),
    ],
)
