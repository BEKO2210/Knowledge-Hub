"""Anmeldung, Sitzungen und Geräte-Kopplung (Verbinden-Tab)."""

from __future__ import annotations

import asyncio
import os
import re

from starlette.requests import Request
from starlette.responses import JSONResponse

import config
import oauth
import ratelimit
import vault
from api.common import _bearer, _check_password, _client_ip
from api.i18n import T


async def login(request: Request) -> JSONResponse:
    try:
        body = await request.json()
    except Exception:
        return JSONResponse({"error": "bad request"}, status_code=400)
    ip = _client_ip(request)
    if not ratelimit.check("login", ip):
        vault.audit("LOGIN-BLOCKED", ip, client="web-ui")
        return JSONResponse(
            {"error": T("Zu viele Fehlversuche — bitte 15 Minuten warten.")}, status_code=429
        )
    password = str(body.get("password", ""))
    code = str(body.get("code", "")).strip()
    # Passwortprüfung läuft über den Vault: Wenn sich damit der Hauptschlüssel
    # entpacken lässt, war das Passwort richtig — es ist nirgends gespeichert.
    # scrypt ist absichtlich langsam, deshalb im Thread.
    ok = await asyncio.to_thread(_check_password, password)
    if not ok:
        ratelimit.record_failure("login", ip)
        vault.audit("LOGIN-FAIL", ip, client="web-ui")
        await asyncio.sleep(1)  # Bremse gegen Rateversuche, ohne die Event-Loop zu blockieren
        return JSONResponse({"error": T("Falsches Passwort")}, status_code=401)

    # Zweiter Faktor, falls aktiviert. Passwort war hier bereits korrekt.
    import totp

    if totp.is_enabled():
        if not code:
            # Passwort stimmt — jetzt fehlt nur der Code. Kein Fehlversuch.
            return JSONResponse({"need_2fa": True}, status_code=401)
        if not totp.check(code):
            ratelimit.record_failure("login", ip)
            vault.audit("LOGIN-FAIL", f"{ip} (2FA-Code falsch)", client="web-ui")
            await asyncio.sleep(1)
            return JSONResponse({"need_2fa": True, "error": T("Code stimmt nicht")}, status_code=401)

    ratelimit.record_success("login", ip)
    vault.audit("LOGIN", ip, client="web-ui")
    state = oauth._load()
    payload = oauth._issue(state, "web-ui", user_agent=request.headers.get("user-agent", ""))
    oauth._save(state)
    return JSONResponse({"token": payload["access_token"], "expires_in": payload["expires_in"]})


async def unblock_ips(request: Request) -> JSONResponse:
    """Alle IP-Sperren aufheben (falls man sich selbst ausgesperrt hat)."""
    n = ratelimit.unblock()
    vault.audit("UNBLOCK", f"{n} Sperren aufgehoben", client="web-ui")
    return JSONResponse({"ok": True, "cleared": n})


async def sessions_list(request: Request) -> JSONResponse:
    """Alle angemeldeten Geräte/Clients — die eigene Sitzung ist markiert."""
    me = oauth.session_of(_bearer(request))
    items = oauth.list_sessions()
    for s in items:
        s["current"] = bool(me) and s["id"] == me

    # Das statische MCP-Token aus der env-Datei ist ein Dauer-Zugang, der sonst
    # unsichtbar bliebe. Es lässt sich nicht per Klick widerrufen (dafür muss der
    # Wert in der env-Datei getauscht werden) — aber man muss wissen, dass es existiert.
    if os.environ.get("MCP_TOKEN"):
        items.append({
            "id": "static",
            "label": T("Statisches Token (env-Datei)"),
            "kind": "static",
            "created": None,
            "last_seen": None,
            "expires": None,
            "ua": "",
            "current": _bearer(request) == os.environ["MCP_TOKEN"],
            "revocable": False,
            "note": T("Läuft nie ab. Zum Widerrufen den Wert MCP_TOKEN in "
                      "~/.config/knowledge-mcp/env ersetzen und den Dienst neu starten."),
        })
    return JSONResponse({"sessions": items, "current": me})


async def session_revoke(request: Request) -> JSONResponse:
    sid = request.path_params["sid"]
    me = oauth.session_of(_bearer(request))
    if sid == me:
        return JSONResponse(
            {"error": T("Das ist deine aktuelle Sitzung — nutze „Abmelden“.")}, status_code=400
        )
    if not oauth.revoke_session(sid):
        return JSONResponse({"error": T("Sitzung nicht gefunden")}, status_code=404)
    vault.audit("TOKEN-REVOKE", sid, client="web-ui")
    return JSONResponse({"ok": True})


async def sessions_revoke_all(request: Request) -> JSONResponse:
    """Alle anderen Geräte abmelden — die eigene Sitzung bleibt bestehen."""
    me = oauth.session_of(_bearer(request))
    n = oauth.revoke_all(except_sid=me)
    vault.audit("TOKEN-REVOKE-ALL", f"{n} Sitzungen", client="web-ui")
    return JSONResponse({"ok": True, "revoked": n})


async def connect_info(request: Request) -> JSONResponse:
    """Adresse + QR-Code für die Verbindungsseite."""
    import totp

    cfg = config.load()
    public = str(cfg["server"]["public_url"]).rstrip("/")
    mcp_url = public + "/mcp"
    try:
        qr = totp.qr_svg(mcp_url)
    except Exception:  # noqa: BLE001 - QR ist Beiwerk, darf die Seite nicht kippen
        qr = ""
    return JSONResponse({
        "public_url": public,
        "mcp_url": mcp_url,
        "qr": qr,
        "hub": cfg["branding"]["name"],
        "https": public.startswith("https://"),
    })


CONNECT_LABEL_RE = re.compile(r"^[\w.\- ()]{1,60}$")
DEVICE_TOKEN_TTL = 365 * 86400  # Geräte-Token: 1 Jahr, jederzeit widerrufbar


async def connect_token(request: Request) -> JSONResponse:
    """Ein eigenes, langlebiges Geräte-Token ausstellen (widerrufbar in „Geräte").

    Anders als der OAuth-Fluss von claude.ai braucht ein Terminal-/Desktop-Client
    ein Bearer-Token zum Einfügen. Es bekommt einen sprechenden Namen und taucht
    sofort in der Geräteliste auf, wo es einzeln abgemeldet werden kann.
    """
    import secrets as _secrets

    body = await request.json()
    label = str(body.get("label", "")).strip()[:60] or "MCP-Client"
    if not CONNECT_LABEL_RE.match(label):
        return JSONResponse({"error": T("Name enthält ungültige Zeichen.")}, status_code=400)
    state = oauth._load()
    cid = "dev_" + _secrets.token_urlsafe(8)
    state["clients"][cid] = {"redirect_uris": [], "name": label, "created": oauth._now()}
    payload = oauth._issue(state, cid, user_agent=T("Geräte-Token · {label}", label=label))
    # Langlebig machen: das Access-Token bekommt ein Jahr statt der üblichen 30 Tage.
    state["tokens"][oauth._sha(payload["access_token"])]["exp"] = oauth._now() + DEVICE_TOKEN_TTL
    oauth._save(state)
    vault.audit("CONNECT-TOKEN", label, client="web-ui")
    return JSONResponse({"token": payload["access_token"], "label": label, "ttl_days": DEVICE_TOKEN_TTL // 86400})
