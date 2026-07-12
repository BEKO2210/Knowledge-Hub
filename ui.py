"""Web-Schicht des Knowledge-MCP-Hub — liefert die Oberfläche unter /ui aus.

Die eigentlichen Endpunkte liegen thematisch gebündelt in api/; hier bleiben nur
Asset-Auslieferung, Schutz-Header, die Seite selbst und die Routentabelle.
Markup, Stylesheet und Skript liegen als echte Dateien in web/.
"""

from __future__ import annotations

import hashlib
import json
import secrets as _rnd
import time
import traceback
from pathlib import Path

from starlette.applications import Starlette
from starlette.middleware import Middleware
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import HTMLResponse, JSONResponse
from starlette.routing import Route

import config
import vault
from api import auth, i18n, knowledge, mapping, secrets, system
from api.common import CFG, DATA_DIR
from api.i18n import T

# ---------------------------------------------------------------------------
# Fehler-Robustheit
# ---------------------------------------------------------------------------
# Grundsatz: Der Nutzer bekommt einen verständlichen Satz und eine Referenznummer.
# Die Ursache (Traceback) landet ausschließlich hier auf der Platte — niemals in
# der Antwort, sonst verrät ein Fehler die Interna des Hubs nach außen.
ERROR_LOG = DATA_DIR / "errors.log"
_ERROR_LOG_MAX = 2_000_000  # ~2 MB, dann wird rotiert


def _log_error(ref: str, request: Request, exc: BaseException) -> None:
    try:
        if ERROR_LOG.exists() and ERROR_LOG.stat().st_size > _ERROR_LOG_MAX:
            ERROR_LOG.replace(ERROR_LOG.with_suffix(".log.alt"))
        eintrag = {
            "zeit": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
            "ref": ref,
            "methode": request.method,
            "pfad": request.url.path,
            "fehler": f"{type(exc).__name__}: {exc}",
            "spur": traceback.format_exc(limit=12),
        }
        with ERROR_LOG.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(eintrag, ensure_ascii=False) + "\n")
    except Exception:  # noqa: BLE001 - ein kaputtes Fehlerlog darf nichts umbringen
        pass


async def _on_unerwartet(request: Request, exc: Exception) -> JSONResponse:
    """Alles, womit niemand gerechnet hat — mit Referenznummer, ohne Interna."""
    ref = _rnd.token_hex(4)
    _log_error(ref, request, exc)
    return JSONResponse(
        {
            "error": T("Im Hub ist etwas schiefgelaufen. Der Vorfall wurde protokolliert."),
            "ref": ref,
        },
        status_code=500,
    )


async def _on_kaputte_eingabe(request: Request, exc: Exception) -> JSONResponse:
    """Unlesbares JSON ist ein Fehler des Aufrufers, kein Serverabsturz."""
    return JSONResponse({"error": T("Die Anfrage war kein gültiges JSON.")}, status_code=400)


async def _on_gesperrt(request: Request, exc: Exception) -> JSONResponse:
    return JSONResponse({"error": T("Der Vault ist gesperrt — bitte neu anmelden.")}, status_code=423)


async def _on_nicht_gefunden(request: Request, exc: Exception) -> JSONResponse:
    if request.url.path.startswith("/ui/api/"):
        return JSONResponse({"error": T("Diesen Endpunkt gibt es nicht.")}, status_code=404)
    return JSONResponse({"error": T("Nicht gefunden.")}, status_code=404)


WEB_DIR = Path(__file__).parent / "web"
_WEB_TYPES = {".css": "text/css; charset=utf-8", ".js": "application/javascript; charset=utf-8"}


def asset_version() -> str:
    """Inhalts-Hash über CSS+JS. Hängt als ?v= an den Asset-URLs und sorgt dafür,
    dass ein Update sofort ankommt, obwohl die Dateien langlebig gecacht werden."""
    h = hashlib.sha256()
    for n in ("app.css", "app.js"):
        h.update((WEB_DIR / n).read_bytes())
    return h.hexdigest()[:10]


ASSET_V = asset_version()
UI_HTML = (WEB_DIR / "index.html").read_text(encoding="utf-8")


async def web_asset(request: Request):
    """Liefert web/app.css und web/app.js aus. Die URL trägt den Inhalts-Hash,
    darum darf hier aggressiv (unveränderlich) gecacht werden."""
    name = request.path_params["name"]
    path = (WEB_DIR / name).resolve()
    if not path.is_relative_to(WEB_DIR) or not path.is_file() or path.suffix not in _WEB_TYPES:
        return JSONResponse({"error": "not found"}, status_code=404)
    from starlette.responses import Response

    return Response(
        path.read_bytes(),
        media_type=_WEB_TYPES[path.suffix],
        headers={"Cache-Control": "public, max-age=31536000, immutable"},
    )


STATIC_DIR = Path(__file__).parent / "static"
_STATIC_TYPES = {
    ".png": "image/png",
    ".js": "application/javascript",
    ".webmanifest": "application/manifest+json",
    ".woff2": "font/woff2",
}


async def static_file(request: Request):
    name = request.path_params["name"]
    path = (STATIC_DIR / name).resolve()
    if not path.is_relative_to(STATIC_DIR) or not path.is_file():
        return JSONResponse({"error": "not found"}, status_code=404)
    from starlette.responses import Response

    return Response(
        path.read_bytes(),
        media_type=_STATIC_TYPES.get(path.suffix, "application/octet-stream"),
        headers={"Cache-Control": "public, max-age=86400"},
    )


async def root_icon(request: Request):
    """Favicon an der Domain-Wurzel — für Browser-Tabs und die Connector-Liste der KI-Clients.

    Die großen Icons sind PNG; .ico wird von allen aktuellen Clients als PNG akzeptiert.
    """
    from starlette.responses import Response

    gross = request.url.path.startswith("/apple-touch-icon")
    datei = STATIC_DIR / ("icon-192.png" if gross else "favicon.png")
    if not datei.is_file():
        return JSONResponse({"error": "not found"}, status_code=404)
    return Response(
        datei.read_bytes(),
        media_type="image/png",
        headers={"Cache-Control": "public, max-age=86400"},
    )


async def manifest(request: Request) -> JSONResponse:
    return JSONResponse(
        {
            "name": "Knowledge Hub",
            "short_name": "Knowledge",
            "start_url": "/ui",
            "display": "standalone",
            "background_color": "#0e1526",
            "theme_color": "#0e1526",
            "icons": [
                {"src": "/ui/static/icon-192.png", "sizes": "192x192", "type": "image/png"},
                {"src": "/ui/static/icon-512.png", "sizes": "512x512", "type": "image/png"},
            ],
        },
        headers={"Cache-Control": "public, max-age=86400"},
    )


def brand_html(name: str) -> str:
    """„Knowledge Hub" -> „Knowledge <em>Hub</em>" (letztes Wort als Akzent)."""
    import html as _html

    words = [_html.escape(w) for w in name.split()]
    if len(words) < 2:
        return f"<em>{words[0]}</em>" if words else "<em>Hub</em>"
    return " ".join(words[:-1]) + f" <em>{words[-1]}</em>"


def render(template: str) -> str:
    """Branding und Asset-Version zur Laufzeit einsetzen (Namensänderung wirkt ohne Neustart)."""
    name = config.load()["branding"]["name"]
    return (
        template.replace("__BRAND_HTML__", brand_html(name))
        .replace("__BRAND__", name)
        .replace("__V__", ASSET_V)
    )


RECOVERY_HTML = """<!doctype html><html lang="de"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>Wiederherstellung nötig</title>
<style>body{margin:0;min-height:100dvh;display:flex;align-items:center;justify-content:center;padding:20px;
font-family:system-ui,sans-serif;background:#0f172a;color:#f8fafc}
.c{background:#1e293b;border:1px solid #f87171;border-radius:16px;max-width:36rem;padding:2rem;line-height:1.65}
h1{margin:0 0 .6rem;font-size:1.25rem;color:#f87171}p{color:#94a3b8;margin:.6rem 0}
pre{background:#0f172a;border:1px solid #334155;border-radius:8px;padding:12px;overflow-x:auto;
font-size:.82rem;color:#e2e8f0}b{color:#f8fafc}</style></head><body><div class="c">
<h1>Achtung: Konfiguration fehlt, aber es gibt einen Vault</h1>
<p>Die Datei mit deinen Schlüsseln (<b>env</b>) fehlt oder ist unvollständig — der verschlüsselte
Vault mit deinen Secrets ist aber vorhanden.</p>
<p><b>Richte NICHT neu ein.</b> Das würde deine Secrets unerreichbar machen. Spiele stattdessen
deine Sicherung zurück:</p>
<pre>cd ~/knowledge-mcp
python backup.py restore ~/backups/knowledge-hub/hub-*.khub --to /tmp/wiederherstellung
cp /tmp/wiederherstellung/env ~/.config/knowledge-mcp/env
systemctl --user restart knowledge-mcp</pre>
<p>Die Backup-Passphrase steht in deinem Passwort-Manager. Danach ist alles wieder da.</p>
</div></body></html>"""


async def page(request: Request) -> HTMLResponse:
    import setup_wizard  # lokal: der Wizard importiert seinerseits config

    if not setup_wizard.is_configured():
        # Vault vorhanden, aber env kaputt/fehlt -> NICHT den Wizard zeigen (er würde
        # zum Überschreiben verleiten), sondern zur Wiederherstellung anleiten.
        if vault.VAULT_PATH.exists():
            return HTMLResponse(RECOVERY_HTML, status_code=409)
        # Der Wizard trägt seinen einzigen Skriptblock inline — seine CSP erlaubt genau
        # diesen Block per Hash (SecurityHeaders lässt eine gesetzte CSP unangetastet).
        return HTMLResponse(
            render(setup_wizard.WIZARD_HTML),
            headers={"Content-Security-Policy": setup_wizard.WIZARD_CSP},
        )
    return HTMLResponse(render(UI_HTML))


class VaultGate(BaseHTTPMiddleware):
    """Ist der Vault gesperrt, antworten die APIs mit 423 statt mit einem Absturz.
    Die Oberfläche schickt den Nutzer dann zur Anmeldung."""

    async def dispatch(self, request, call_next):
        try:
            return await call_next(request)
        except vault.VaultLocked:
            return JSONResponse(
                {"error": "Vault ist gesperrt — bitte anmelden.", "locked": True},
                status_code=423,
            )


class Sprache(BaseHTTPMiddleware):
    """Sprache der Anfrage bestimmen — die Oberfläche schickt sie als X-Lang mit.

    Fällt sie weg (curl, KI-Client), entscheidet Accept-Language. So bekommt jeder
    Aufrufer die Diagnose in seiner Sprache, ohne dass der Server einen globalen
    Zustand mit sich herumträgt.
    """

    async def dispatch(self, request, call_next):
        gewuenscht = request.headers.get("x-lang") or request.headers.get("accept-language", "")
        i18n.set_lang("en" if not gewuenscht.lower().startswith("de") else "de")
        return await call_next(request)


class SchreibBremse(BaseHTTPMiddleware):
    """Drossel auf alle schreibenden UI-Endpunkte (POST/PUT/PATCH/DELETE unter /ui/api/).

    Die Anmeldung hat ihre eigene, viel strengere Bremse (5 Fehlversuche/15 min) —
    diese hier fängt den Rest ab: ein Skript, das mit einem gestohlenen Sitzungs-Token
    Secrets abräumt, Geräte-Tokens am Fließband erzeugt oder das Audit-Log über
    abgelehnte Schreibversuche vollmüllt. 120 Aufrufe/min bremsen keinen Menschen.
    """

    async def dispatch(self, request, call_next):
        from api.common import _client_ip

        if request.method in ("POST", "PUT", "PATCH", "DELETE") and request.url.path.startswith("/ui/api/"):
            import ratelimit

            ip = _client_ip(request)
            erlaubt, gerade_gesperrt = ratelimit.throttle("write", ip)
            if not erlaubt:
                if gerade_gesperrt:
                    vault.audit("WRITE-THROTTLED", f"{request.method} {request.url.path}", client=ip)
                return JSONResponse(
                    {"error": T("Zu viele Änderungen in kurzer Zeit — bitte einen Moment warten.")},
                    status_code=429,
                    headers={"Retry-After": "60"},
                )
        return await call_next(request)


class SecurityHeaders(BaseHTTPMiddleware):
    """Schutz-Header für alle UI-Antworten."""

    async def dispatch(self, request, call_next):
        resp = await call_next(request)
        # script-src OHNE 'unsafe-inline': Selbst wenn es ein Angreifer schafft, Markup in
        # die Seite zu bekommen (XSS), führt der Browser daraus keinen Code aus. Der Preis
        # dafür war, jeden Inline-Handler (onclick="…") auf das Aktions-Register in app.js
        # umzustellen. style-src bleibt bei 'unsafe-inline' — Inline-STYLE kann keinen Code
        # ausführen; das Risiko ist eine andere Klasse als Inline-SKRIPT.
        # setdefault statt Zuweisung: Der Setup-Wizard bringt seine eigene CSP mit
        # (Hash auf seinen einzigen Skriptblock) — die darf hier nicht überschrieben werden.
        resp.headers.setdefault(
            "Content-Security-Policy",
            "default-src 'self'; script-src 'self'; "
            "style-src 'self' 'unsafe-inline'; img-src 'self' data:; "
            "connect-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'",
        )
        resp.headers["X-Content-Type-Options"] = "nosniff"
        resp.headers["X-Frame-Options"] = "DENY"
        resp.headers["Referrer-Policy"] = "no-referrer"
        resp.headers["Permissions-Policy"] = "geolocation=(), microphone=(), camera=()"
        # API-Antworten können Secrets enthalten -> nirgends zwischenspeichern
        # (Browser-Cache, Proxy, Blättern im Verlauf).
        if request.url.path.startswith("/ui/api/"):
            resp.headers["Cache-Control"] = "no-store, private"
            resp.headers["Pragma"] = "no-cache"
        # Die App-Seite selbst darf NICHT gecacht werden: Nach einem Update würde der
        # Browser sonst wochenlang die alte Oberfläche zeigen (genau das ist passiert).
        elif not request.url.path.startswith(("/ui/static/", "/ui/asset/")):
            resp.headers["Cache-Control"] = "no-cache, must-revalidate"
        # HSTS nur, wenn der Hub tatsächlich über HTTPS erreichbar ist
        if str(CFG["server"]["public_url"]).startswith("https://"):
            resp.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
        return resp


import setup_wizard  # noqa: E402 - nach config/vault, vermeidet Zirkelimport

ui_app = Starlette(
    middleware=[
        Middleware(Sprache),
        Middleware(SchreibBremse),
        Middleware(SecurityHeaders),
        Middleware(VaultGate),
    ],
    exception_handlers={
        json.JSONDecodeError: _on_kaputte_eingabe,
        vault.VaultLocked: _on_gesperrt,
        404: _on_nicht_gefunden,
        Exception: _on_unerwartet,
    },
    routes=[
        Route("/ui", page),
        Route("/ui/", page),
        Route("/ui/setup", setup_wizard.wizard_page),
        Route("/ui/setup/status", setup_wizard.setup_status),
        Route("/ui/setup/submit", setup_wizard.setup_submit, methods=["POST"]),
        Route("/ui/setup/restart", setup_wizard.setup_restart, methods=["POST"]),
        # Wurzel-Icons: Clients fragen sie ohne /ui-Präfix ab (Browser-Tab, Connector-Liste).
        Route("/favicon.ico", root_icon),
        Route("/favicon.png", root_icon),
        Route("/apple-touch-icon.png", root_icon),
        Route("/apple-touch-icon-precomposed.png", root_icon),
        Route("/ui/static/{name}", static_file),
        Route("/ui/asset/{name}", web_asset),
        Route("/ui/manifest.json", manifest),
        Route("/ui/api/login", auth.login, methods=["POST"]),
        Route("/ui/api/projects", knowledge.projects),
        Route("/ui/api/graph/{project}", knowledge.graph),
        Route("/ui/api/ask/{project}", knowledge.graph_ask, methods=["POST"]),
        Route("/ui/api/report/{project}", knowledge.report),
        Route("/ui/api/explain/{project}", knowledge.explain),
        Route("/ui/api/answers/{project}", knowledge.antworten_liste),
        Route("/ui/api/secrets", secrets.secrets_list),
        Route("/ui/api/secrets", secrets.secrets_set, methods=["POST"]),
        Route("/ui/api/secrets/{name}", secrets.secrets_get),
        Route("/ui/api/secrets/{name}", secrets.secrets_delete, methods=["DELETE"]),
        Route("/ui/api/audit", secrets.audit),
        Route("/ui/api/health", system.health),
        Route("/ui/api/unblock", auth.unblock_ips, methods=["POST"]),
        Route("/ui/api/2fa", system.twofa_status),
        Route("/ui/api/2fa/setup", system.twofa_setup, methods=["POST"]),
        Route("/ui/api/2fa/enable", system.twofa_enable, methods=["POST"]),
        Route("/ui/api/2fa/disable", system.twofa_disable, methods=["POST"]),
        Route("/ui/api/vault", system.vault_status),
        Route("/ui/api/vault/autounlock", system.vault_autounlock, methods=["POST"]),
        Route("/ui/api/vault/password", system.vault_password, methods=["POST"]),
        Route("/ui/api/backup", system.backup_status),
        Route("/ui/api/backup/run", system.backup_now, methods=["POST"]),
        Route("/ui/api/backup/target", system.backup_target, methods=["POST"]),
        Route("/ui/api/backup/target", system.backup_target_delete, methods=["DELETE"]),
        Route("/ui/api/backup/setup", system.backup_setup, methods=["POST"]),
        Route("/ui/api/connect/info", auth.connect_info),
        Route("/ui/api/connect/token", auth.connect_token, methods=["POST"]),
        Route("/ui/api/sessions", auth.sessions_list),
        Route("/ui/api/sessions", auth.sessions_revoke_all, methods=["DELETE"]),
        Route("/ui/api/sessions/{sid}", auth.session_revoke, methods=["DELETE"]),
        Route("/ui/api/mapping/status", mapping.mapping_status),
        Route("/ui/api/mapping/toggle", mapping.mapping_toggle, methods=["POST"]),
        Route("/ui/api/mapping/config", mapping.mapping_config, methods=["POST"]),
        Route("/ui/api/mapping/run", mapping.mapping_run, methods=["POST"]),
        Route("/ui/api/mapping/log", mapping.mapping_log),
        Route("/ui/api/mapping/history", mapping.mapping_history),
        Route("/ui/api/mapping/history/dismiss", mapping.mapping_dismiss, methods=["POST"]),
        Route("/ui/api/mapping/projects", mapping.mapping_projects),
        Route("/ui/api/mapping/projects", mapping.mapping_project_add, methods=["POST"]),
        Route("/ui/api/mapping/projects", mapping.mapping_project_update, methods=["PATCH"]),
        Route("/ui/api/mapping/check", mapping.project_check),
        Route("/ui/api/mapping/repair", mapping.project_repair, methods=["POST"]),
        Route("/ui/api/mapping/repair", mapping.project_repair_status),
        Route("/ui/api/browse", mapping.browse_dirs),
        Route("/ui/api/mapping/ignore", mapping.ignore_get),
        Route("/ui/api/mapping/ignore", mapping.ignore_put, methods=["PUT"]),
    ],
)
