"""Systemzustand: Diagnose, Sicherung, Zwei-Faktor und Vault-Einstellungen."""

from __future__ import annotations

import asyncio
import json
import os
import platform
import re
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path

from starlette.requests import Request
from starlette.responses import JSONResponse

import config
import ratelimit
import totp
import vault
from api.common import (
    AUDIT_PATH,
    DATA_DIR,
    GRAPHIFY_BIN,
    KNOWLEDGE_ROOT,
    _check,
    _dir_size,
    _human,
    json_object,
)
from api.i18n import T
from api.mapping import NIGHTLY_LOG_DIR, _sysctl


def _backup_state(cfg: dict) -> dict:
    """Wo liegen die Sicherungen, wie alt ist die letzte, ist eine Passphrase gesetzt?"""
    targets = (cfg.get("backup") or {}).get("targets") or []
    files: list[Path] = []
    for t in targets:
        if t.get("type") == "local":
            d = Path(str(t["path"])).expanduser()
        elif t.get("type") == "git":
            # Zwei Varianten: vorhandener Klon (`repo`) oder Adresse (`url`, Klon im Cache)
            if t.get("repo"):
                base = Path(str(t["repo"])).expanduser()
            else:
                import backup as _backup

                base = _backup.CACHE_DIR / "backup-repo"
            d = base / str(t.get("subdir", "hub-backups"))
        else:
            continue
        if d.is_dir():
            files += list(d.glob("hub-*.khub"))
    last = None
    if files:
        newest = max(files, key=lambda f: f.stat().st_mtime)
        last = {
            "name": newest.name,
            "ts": newest.stat().st_mtime,
            "size": newest.stat().st_size,
            "path": str(newest),
        }
    return {
        "passphrase": bool(os.environ.get("BACKUP_PASSPHRASE")),
        "targets": [
            {
                "type": t.get("type"),
                "where": str(t.get("url") or t.get("path") or t.get("repo")),
                "url": t.get("url"),
                "subdir": t.get("subdir"),
                "branch": t.get("branch"),
                "secret": t.get("secret"),  # welches Vault-Secret liefert den Token
            }
            for t in targets
        ],
        "last": last,
        "count": len({f.name for f in files}),
    }


_backup_run: dict = {"status": "idle", "log": ""}


def _backup_worker(cfg: dict, passphrase: str) -> None:
    import backup as _backup

    try:
        rep = _backup.run(cfg, passphrase)
        lines = [("✓ " if r["ok"] else "✗ ") + r["detail"] for r in rep["results"]]
        if rep["ok"]:
            lines.append(
                T("Sicherung {file} ({size} Bytes) abgeschlossen.", file=rep["file"], size=f"{rep['size']:,}")
            )
        _backup_run.update(status="done" if rep["ok"] else "failed", log="\n".join(lines))
    except Exception as e:  # noqa: BLE001
        _backup_run.update(status="failed", log=T("Fehler: {msg}", msg=e))


async def twofa_status(request: Request) -> JSONResponse:

    return JSONResponse(totp.status())


async def twofa_setup(request: Request) -> JSONResponse:
    """Neues Geheimnis + QR erzeugen (noch nicht aktiv)."""
    import totp

    account = "hub"
    issuer = config.load()["branding"]["name"]
    data = await asyncio.to_thread(totp.begin_setup, account, issuer)
    return JSONResponse(data)


async def twofa_enable(request: Request) -> JSONResponse:
    import totp

    body = await json_object(request)
    # Schon aktiv? Dann nicht noch einmal aktivieren — ein zweites Absenden
    # (Doppelklick, zweites Gerät) würde sonst die gezeigten Recovery-Codes
    # entwerten. Klare Meldung statt des irreführenden „Code stimmt nicht" (R17-1).
    if await asyncio.to_thread(totp.is_enabled):
        return JSONResponse({"error": T("Zwei-Faktor ist bereits aktiv.")}, status_code=409)
    codes = await asyncio.to_thread(totp.enable, str(body.get("code", "")))
    if codes is None:
        return JSONResponse(
            {"error": T("Code stimmt nicht — bitte den aktuellen aus der App.")}, status_code=400
        )
    return JSONResponse({"ok": True, "recovery": codes})


async def twofa_disable(request: Request) -> JSONResponse:
    """2FA abschalten — verlangt einen gültigen Code (Bestätigung, dass es der
    Besitzer ist, nicht ein übernommener Browser)."""
    import totp

    body = await json_object(request)
    if totp.is_enabled() and not totp.check(str(body.get("code", ""))):
        return JSONResponse({"error": T("Zum Abschalten den aktuellen Code eingeben.")}, status_code=400)
    await asyncio.to_thread(totp.disable)
    return JSONResponse({"ok": True})


async def vault_status(request: Request) -> JSONResponse:
    st = vault.status()
    st["env_key"] = bool(os.environ.get("VAULT_KEY"))
    return JSONResponse(st)


async def vault_autounlock(request: Request) -> JSONResponse:
    """Auto-Entsperrung an/aus. Aus = maximale Sicherheit (Vault bleibt nach jedem
    Neustart gesperrt), aber das Nacht-Mapping kann dann keine API-Keys mehr lesen,
    bis sich jemand angemeldet hat."""
    body = await json_object(request)
    enabled = bool(body.get("enabled"))
    try:
        if not await asyncio.to_thread(vault.set_auto_unlock, enabled):
            return JSONResponse({"error": T("Kein VAULT_KEY in der Umgebung.")}, status_code=400)
    except vault.VaultLocked:
        return JSONResponse({"error": T("Vault ist gesperrt — bitte neu anmelden.")}, status_code=423)
    return JSONResponse({"ok": True, "auto_unlock": enabled})


async def vault_password(request: Request) -> JSONResponse:
    body = await json_object(request)
    old, new = str(body.get("old", "")), str(body.get("new", ""))
    try:
        ok = await asyncio.to_thread(vault.change_password, old, new)
    except ValueError as e:
        return JSONResponse({"error": str(e)}, status_code=400)
    except vault.VaultLocked:
        return JSONResponse({"error": T("Vault ist gesperrt — bitte neu anmelden.")}, status_code=423)
    if not ok:
        # 403, NICHT 401. Der Aufrufer IST angemeldet — nur diese eine Aktion wird
        # abgelehnt. Bei 401 hält die Oberfläche das Sitzungs-Token für ungültig und
        # meldet sofort ab: Wer sich beim Passwortwechsel vertippte, flog raus, statt
        # „Aktuelles Passwort stimmt nicht." zu lesen.
        return JSONResponse({"error": T("Aktuelles Passwort stimmt nicht.")}, status_code=403)
    return JSONResponse({"ok": True})


async def backup_status(request: Request) -> JSONResponse:
    state = _backup_state(config.load())
    return JSONResponse({**state, "run": _backup_run})


GIT_URL_RE = re.compile(r"^(https://[\w.\-]+/[\w.\-/]+?(\.git)?|git@[\w.\-]+:[\w.\-/]+?(\.git)?)$")
BACKUP_TOKEN_SECRET = "backup_git_token"


async def backup_target(request: Request) -> JSONResponse:
    """Git-Ziel einrichten: Repo-Adresse + Zugriffstoken.

    Der Token kann neu eingegeben werden (landet dann im Vault) oder aus einem
    bereits im Vault liegenden Secret gewählt werden.
    """
    body = await json_object(request)
    url = str(body.get("url", "")).strip()
    token = str(body.get("token", "")).strip()
    secret_name = str(body.get("secret", "")).strip()
    subdir = str(body.get("subdir", "hub-backups")).strip() or "hub-backups"
    branch = str(body.get("branch", "main")).strip() or "main"

    # Vorhandenes Vault-Secret als Token-Quelle gewählt?
    if secret_name and not token:
        if secret_name not in vault.secret_list(client="web-ui"):
            return JSONResponse(
                {"error": T("Kein Secret namens „{name}“ im Vault.", name=secret_name)}, status_code=400
            )
        token = "vault"  # Platzhalter: Token wird zur Laufzeit aus dem Vault geholt

    if not url:
        return JSONResponse({"error": T("Repo-Adresse fehlt.")}, status_code=400)
    if not GIT_URL_RE.match(url):
        return JSONResponse(
            {"error": T("Ungültige Repo-Adresse. Beispiel: https://github.com/name/repo.git")},
            status_code=400,
        )
    if not re.fullmatch(r"[\w.\-/]{1,60}", subdir) or not re.fullmatch(r"[\w.\-/]{1,60}", branch):
        return JSONResponse({"error": T("Ungültiger Ordner- oder Branch-Name.")}, status_code=400)
    if url.startswith("https://") and not token and not secret_name:
        return JSONResponse(
            {
                "error": T(
                    "Für HTTPS-Repos wird ein Zugriffstoken gebraucht — entweder neu eingeben "
                    "oder ein vorhandenes Secret aus dem Vault wählen. "
                    "(GitHub: Settings → Developer settings → Personal access tokens, "
                    "Rechte: Contents read/write auf dieses Repo.)"
                )
            },
            status_code=400,
        )
    # Neu eingegebener Token wird im Vault abgelegt; ein gewähltes Secret bleibt, wie es ist.
    use_secret = secret_name or (BACKUP_TOKEN_SECRET if token else None)
    if token and token != "vault":
        vault.secret_set(use_secret or BACKUP_TOKEN_SECRET, token, client="web-ui")
        use_secret = use_secret or BACKUP_TOKEN_SECRET

    cfg = config.load()
    targets = [t for t in (cfg.get("backup") or {}).get("targets") or [] if t.get("type") != "git"]
    targets.append(
        {
            "type": "git",
            "url": url,
            "subdir": subdir,
            "branch": branch,
            "keep": 14,
            "secret": use_secret,
        }
    )
    config.save_backup(targets)
    vault.audit("BACKUP-TARGET", url, client="web-ui")
    return JSONResponse({"ok": True})


async def backup_target_delete(request: Request) -> JSONResponse:
    cfg = config.load()
    targets = [t for t in (cfg.get("backup") or {}).get("targets") or [] if t.get("type") != "git"]
    config.save_backup(targets)
    vault.audit("BACKUP-TARGET", "git-Ziel entfernt", client="web-ui")
    return JSONResponse({"ok": True})


async def backup_now(request: Request) -> JSONResponse:
    pp = os.environ.get("BACKUP_PASSPHRASE", "")
    if not pp:
        return JSONResponse({"error": T("Keine Backup-Passphrase eingerichtet.")}, status_code=400)
    if _backup_run["status"] == "running":
        return JSONResponse({"error": T("Sicherung läuft bereits")}, status_code=409)
    _backup_run.update(status="running", log=T("Sicherung läuft…"))
    vault.audit("BACKUP-RUN", "manuell", client="web-ui")
    threading.Thread(target=_backup_worker, args=(config.load(), pp), daemon=True).start()
    return JSONResponse({"ok": True})


async def backup_setup(request: Request) -> JSONResponse:
    """Backup-Passphrase erzeugen (nur wenn noch keine existiert). Wird einmalig
    angezeigt — der Nutzer MUSS sie offline sichern, sonst ist das Backup wertlos."""
    import secrets as _secrets

    import setup_wizard

    if os.environ.get("BACKUP_PASSPHRASE"):
        return JSONResponse({"error": T("Es ist bereits eine Passphrase eingerichtet.")}, status_code=409)
    pp = "-".join(_secrets.token_urlsafe(6) for _ in range(4))
    setup_wizard._write_env({"BACKUP_PASSPHRASE": pp})
    os.environ["BACKUP_PASSPHRASE"] = pp
    vault.audit("BACKUP-SETUP", "Passphrase erzeugt", client="web-ui")
    return JSONResponse({"ok": True, "passphrase": pp})


def _probe_public(public: str) -> tuple[str, str]:
    """Prüft, ob der Hub von außen erreichbar ist (blockierend — im Thread aufrufen)."""
    # User-Agent ist Pflicht: Cloudflare & Co. blocken anonyme Clients mit 403.
    req = urllib.request.Request(
        public.rstrip("/") + "/ui/setup/status",
        headers={"User-Agent": "KnowledgeHub-Healthcheck"},
    )
    try:
        with urllib.request.urlopen(req, timeout=6) as r:  # noqa: S310 - eigene, konfigurierte URL
            return (
                ("ok", T("{url} antwortet", url=public))
                if r.status == 200
                else ("warn", T("{url} antwortet mit HTTP {code}", url=public, code=r.status))
            )
    except urllib.error.HTTPError as e:
        # Antwort kommt an -> Tunnel steht; nur der Statuscode passt nicht.
        return "warn", T("{url} antwortet mit HTTP {code}", url=public, code=e.code)
    except Exception as e:  # noqa: BLE001
        return "err", T("{url} nicht erreichbar ({error})", url=public, error=type(e).__name__)


async def health(request: Request) -> JSONResponse:
    import shutil as _shutil

    cfg = config.load()
    checks: list[dict] = []

    # --- Dienste ---
    _, srv = _sysctl("is-active", "knowledge-mcp")
    checks.append(
        _check(
            T("Server"),
            "ok" if srv == "active" else "warn",
            T("läuft") if srv == "active" else T("systemd meldet: {status}", status=srv),
            "" if srv == "active" else "systemctl --user restart knowledge-mcp",
        )
    )
    _, timer = _sysctl("is-enabled", "nightly-map.timer")
    _, nxt = _sysctl("show", "nightly-map.timer", "--property=NextElapseUSecRealtime", "--value")
    checks.append(
        _check(
            T("Nacht-Mapping"),
            "ok" if timer == "enabled" else "warn",
            T("aktiv · nächster Lauf: {t}", t=nxt) if timer == "enabled" else T("ausgeschaltet"),
            "" if timer == "enabled" else T("Im Mapping-Tab einschalten."),
        )
    )

    # --- graphify ---
    gpath = Path(GRAPHIFY_BIN)
    have_graphify = gpath.is_file() or bool(_shutil.which("graphify"))
    checks.append(
        _check(
            "graphify",
            "ok" if have_graphify else "err",
            str(gpath) if have_graphify else T("nicht gefunden"),
            "" if have_graphify else T("pipx install graphifyy — ohne graphify ist kein Mapping möglich."),
        )
    )

    # --- KI-Anbieter + Key ---
    bname, backend = config.active_backend(cfg)
    model = cfg["mapping"].get("model", "")
    secret = backend.get("secret")
    stored = set(vault.secret_list(client="web-ui"))
    has_key = bool(backend.get("local")) or (secret in stored if secret else False)
    checks.append(
        _check(
            T("KI-Anbieter"),
            "ok" if has_key else "warn",
            f"{backend.get('label', bname)} · {model}"
            + ("" if has_key else " · " + T("kein Key hinterlegt")),
            "" if has_key else T("Key im Mapping-Tab eintragen — sonst werden Dokumente nicht analysiert."),
        )
    )

    # --- Vault + Backup ---
    vpath = Path(os.environ.get("VAULT_PATH", str(Path.home() / "knowledge-mcp" / "vault.enc")))
    vsize = _human(vpath.stat().st_size) if vpath.exists() else T("leer")
    checks.append(
        _check(T("Secrets-Vault"), "ok", T("{n} Secrets · verschlüsselt ({size})", n=len(stored), size=vsize))
    )
    b = _backup_state(cfg)
    if not b["passphrase"]:
        checks.append(
            _check(
                T("Sicherung"),
                "err",
                T("keine Backup-Passphrase gesetzt — es wird NICHT gesichert"),
                T(
                    "Unten auf dieser Seite einrichten. Ohne Sicherung sind die Secrets "
                    "bei einem Plattenausfall unwiederbringlich verloren."
                ),
            )
        )
    elif not b["last"]:
        checks.append(
            _check(
                T("Sicherung"),
                "warn",
                T("eingerichtet, aber noch nie ausgeführt"),
                T("Unten „Jetzt sichern“ drücken."),
            )
        )
    else:
        age_h = (time.time() - b["last"]["ts"]) / 3600
        offsite = any(t["type"] == "git" for t in b["targets"])
        st = "ok" if age_h < 36 else "warn"
        checks.append(
            _check(
                T("Sicherung"),
                st,
                T("letzte: {name} · vor {h} Std.", name=b["last"]["name"], h=int(age_h))
                + " · "
                + (T("auch offsite (Git)") if offsite else T("nur lokal!")),
                "" if age_h < 36 else T("Letzte Sicherung ist älter als 36 Stunden."),
            )
        )

    # --- Erreichbarkeit von außen ---
    public = cfg["server"]["public_url"]
    if public.startswith("https://"):
        # Der Aufruf geht über den Tunnel zurück auf diesen Server. Er MUSS in einem
        # eigenen Thread laufen — sonst blockiert er die Event-Loop, die genau diese
        # eingehende Anfrage beantworten müsste (Selbst-Deadlock → Timeout).
        reach, reach_detail = await asyncio.to_thread(_probe_public, public)
    else:
        reach, reach_detail = "warn", T("nur lokal erreichbar ({url})", url=public)
    checks.append(
        _check(
            T("Von außen erreichbar"),
            reach,
            reach_detail,
            "" if reach == "ok" else T("Tunnel/Proxy prüfen — ohne das erreichen dich KI-Clients nicht."),
        )
    )

    # --- Projekte ---
    entries = config.project_entries(cfg)
    missing = [e["path"] for e in entries if not Path(e["path"]).expanduser().is_dir()]
    unmapped = [
        e["path"]
        for e in entries
        if Path(e["path"]).expanduser().is_dir()
        and not (Path(e["path"]).expanduser() / "graphify-out" / "graph.json").exists()
    ]
    if missing:
        pstatus = "err"
        pdetail = T("{n} Ordner fehlen: {paths}", n=len(missing), paths=", ".join(missing[:3]))
    elif unmapped:
        pstatus, pdetail = "warn", T("{n} noch nicht gemappt", n=len(unmapped))
    else:
        pstatus, pdetail = "ok", T("{n} Projekte, alle gemappt", n=len(entries))
    checks.append(
        _check(T("Projekte"), pstatus, pdetail, T("Im Mapping-Tab prüfen.") if pstatus != "ok" else "")
    )

    # --- Speicherplatz ---
    du = _shutil.disk_usage(str(Path.home()))
    free_pct = du.free / du.total * 100
    checks.append(
        _check(
            T("Speicherplatz"),
            "ok" if free_pct > 10 else "warn",
            T(
                "{free} frei von {total} ({pct} %)",
                free=_human(du.free),
                total=_human(du.total),
                pct=f"{free_pct:.0f}",
            ),
            "" if free_pct > 10 else T("Platte wird knapp."),
        )
    )

    # --- Fehler NUR aus dem letzten Lauf ---
    # (früher: aus allen Läufen — dadurch standen längst behobene Fehler ewig da)
    errs: list[str] = []
    logs = sorted(NIGHTLY_LOG_DIR.glob("nightly-*.log"))
    if logs:
        last_run = logs[-1].read_text().split("=== nightly-map start")[-1]
        date = logs[-1].stem.removeprefix("nightly-")
        for line in last_run.splitlines():
            if "FEHLGESCHLAGEN" in line or "fehlgeschlagen" in line:
                errs.append(f"{date}: {line.strip()[:110]}")
    audit_lines = AUDIT_PATH.read_text().splitlines()[-300:] if AUDIT_PATH.exists() else []
    fails = [z for z in audit_lines if "LOGIN-FAIL" in z or "LOGIN-BLOCKED" in z]
    alerts = [z for z in audit_lines if "SECURITY-ALERT" in z]
    blocked = ratelimit.blocked_ips()
    if blocked:
        ips = ", ".join(b["ip"] for b in blocked[:3])
        checks.append(
            _check(
                T("Angriffsschutz"),
                "err",
                T("{n} IP(s) gerade gesperrt: {ips}", n=len(blocked), ips=ips),
                T("Jemand rät aktiv dein Passwort — die Bremse hält ihn auf."),
            )
        )
    elif alerts:
        checks.append(
            _check(
                T("Angriffsschutz"),
                "warn",
                T("{n} Sperre(n) in letzter Zeit — aktuell keine aktiv", n=len(alerts)),
                T("Audit-Log prüfen."),
            )
        )
    else:
        checks.append(
            _check(
                T("Angriffsschutz"),
                "ok",
                T("keine aktiven Sperren")
                + (" · " + T("{n} Fehlversuche protokolliert", n=len(fails)) if fails else ""),
            )
        )

    # Unerwartete Fehler: Das Log ist nur dann etwas wert, wenn man merkt, dass es
    # etwas enthält. Darum steht der Befund hier — sonst verstaubt es unbemerkt.
    fehler_log = DATA_DIR / "errors.log"
    if fehler_log.exists() and fehler_log.stat().st_size > 0:
        letzte = fehler_log.read_text(errors="replace").splitlines()[-50:]
        seit_24h = []
        grenze = time.time() - 86400
        for zeile in letzte:
            try:
                e = json.loads(zeile)
                t = time.mktime(time.strptime(e["zeit"][:19], "%Y-%m-%dT%H:%M:%S"))
                if t >= grenze:
                    seit_24h.append(e)
            except Exception:  # noqa: BLE001 - eine kaputte Zeile darf die Diagnose nicht kippen
                continue
        if seit_24h:
            letzter = seit_24h[-1]
            checks.append(
                _check(
                    T("Unerwartete Fehler"),
                    "warn",
                    T(
                        "{n} in den letzten 24 Std. · zuletzt {path} (Ref. {ref})",
                        n=len(seit_24h),
                        path=letzter["pfad"],
                        ref=letzter["ref"],
                    ),
                    T("Details stehen in {file} — dort steht auch, woran es lag.", file=fehler_log),
                )
            )
        else:
            checks.append(_check(T("Unerwartete Fehler"), "ok", T("keine in den letzten 24 Std.")))
    else:
        checks.append(_check(T("Unerwartete Fehler"), "ok", T("keine protokolliert")))

    graphs_size = _dir_size(KNOWLEDGE_ROOT)
    return JSONResponse(
        {
            "checks": checks,
            "errors": errs[-6:],
            "info": {
                "hub": cfg["branding"]["name"],
                "public_url": public,
                "mcp_url": public.rstrip("/") + "/mcp",
                "backend": f"{backend.get('label', bname)} · {model}",
                "projects": len(entries),
                "secrets": len(stored),
                "graphs_size": _human(graphs_size),
                "python": platform.python_version(),
            },
        }
    )
