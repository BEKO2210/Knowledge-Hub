"""knowledge-mcp — private MCP hub: graphify knowledge + encrypted secrets vault.

Transport: streamable HTTP (FastMCP) behind a static bearer token. Meant to sit
on 127.0.0.1 behind the Cloudflare tunnel; the token is the only thing between
the internet and the vault, so it is long, random, and checked constant-time.

Extending: drop more @mcp.tool functions here (or import service modules) —
every AI client that knows the URL + token gets them immediately.
"""

from __future__ import annotations

import hmac
import json
import os
import shlex
import subprocess
import threading
import time
from pathlib import Path

from fastmcp import FastMCP
from mcp.types import Icon
from starlette.requests import Request
from starlette.responses import JSONResponse

import config
import graph_context
import health
import oauth
import ratelimit
import semantic
import ui
import vault


def _on_block(action: str, ip: str, fails: int) -> None:
    """Wird ausgelöst, sobald eine IP gesperrt wird — deutlich ins Audit-Log,
    damit die Diagnose es als Angriffsversuch anzeigen kann."""
    vault.audit("SECURITY-ALERT", f"{ip} gesperrt nach {fails} Fehlversuchen ({action})", client="system")


ratelimit.set_alert(_on_block)

CFG = config.load()
KNOWLEDGE_ROOT = config.path(os.environ.get("KNOWLEDGE_ROOT", CFG["paths"]["knowledge_root"]))
GRAPHIFY_BIN = os.environ.get("GRAPHIFY_BIN", str(config.path(CFG["paths"]["graphify_bin"])))
MCP_TOKEN = os.environ.get("MCP_TOKEN", "")

# Icons für die Connector-Liste in Claude/ChatGPT. Ohne sie zeigt der Client nur einen
# Platzhalter. Die URLs MÜSSEN ohne Anmeldung erreichbar sein — /ui/static/ ist genau
# dafür in der BearerGate freigegeben; alles andere liefert 401 und der Client bekommt
# nie ein Bild zu sehen.
_PUBLIC = str(CFG["server"]["public_url"]).rstrip("/")
_ICONS = [
    Icon(src=f"{_PUBLIC}/ui/static/icon-192.png", mimeType="image/png", sizes=["192x192"]),
    Icon(src=f"{_PUBLIC}/ui/static/icon-512.png", mimeType="image/png", sizes=["512x512"]),
]

mcp = FastMCP(
    "knowledge",
    version=(Path(__file__).parent / "VERSION").read_text().strip(),
    website_url=f"{_PUBLIC}/ui",
    icons=_ICONS,
    instructions=(
        "Self-hosted knowledge hub. Knowledge graphs of your projects "
        "(query/explain/report) plus an encrypted secrets vault. Secrets are sensitive: "
        "fetch them only when a task genuinely needs a credential, never echo them back "
        "into chat unless the user explicitly asks. "
        "When the user shares knowledge worth keeping (facts about themselves, decisions, "
        "research, ideas), offer to save it with note_save — notes become part of the "
        "knowledge graph on the next mapping run."
    ),
)


def _projects() -> list[str]:
    return sorted(
        d.name
        for d in KNOWLEDGE_ROOT.iterdir()
        if d.is_dir() and (d / "graphify-out" / "graph.json").exists()
    )


@mcp.tool
def projects_list() -> list[dict]:
    """List all projects that have a knowledge graph, with basic stats."""
    out = []
    for name in _projects():
        g = json.loads((KNOWLEDGE_ROOT / name / "graphify-out" / "graph.json").read_text())
        nodes = g.get("nodes", [])
        out.append(
            {
                "project": name,
                "nodes": len(nodes),
                "edges": len(g.get("links", g.get("edges", []))),
                "communities": len({n.get("community") for n in nodes if n.get("community") is not None}),
            }
        )
    return out


def _run_graphify(project: str, args: list[str]) -> str:
    if project not in _projects():
        raise ValueError(f"unknown project {project!r}; known: {_projects()}")
    proc = subprocess.run(  # noqa: S603 - fixed binary, validated project, list args
        [GRAPHIFY_BIN, *args],
        cwd=KNOWLEDGE_ROOT / project,
        capture_output=True,
        text=True,
        timeout=120,
    )
    if proc.returncode != 0:
        raise RuntimeError(proc.stderr.strip()[:2000] or "graphify failed")
    return proc.stdout.strip()


def _source_dir(project: str) -> Path | None:
    """Quellverzeichnis eines Projekts aus der Mapping-Config (für den Hybrid-Modus)."""
    try:
        for e in config.project_entries():
            p = Path(e["path"]).expanduser()
            if p.name.lower() == project.lower():
                return p if p.is_dir() else None
    except Exception:  # noqa: BLE001 - Hybrid ist Zugabe, Config-Probleme dürfen nichts kippen
        pass
    return None


@mcp.tool
def graph_query(project: str, question: str, budget_tokens: int = 1200) -> str:
    """Answer a question about a project's codebase (hybrid: knowledge graph + relevant file excerpts)."""
    if project not in _projects():
        raise ValueError(f"unknown project {project!r}; known: {_projects()}")
    # Dreistufige Kette: Hybrid → semantischer Graph → graphify-CLI.
    # graph_query darf nie an einem fehlenden Index oder Modell scheitern.
    try:
        raw = semantic.hybrid_query(
            KNOWLEDGE_ROOT / project, question, budget=budget_tokens, source_dir=_source_dir(project)
        )
    except Exception:
        try:
            raw = semantic.query(KNOWLEDGE_ROOT / project, question, budget=budget_tokens)
        except Exception:
            raw = _run_graphify(project, ["query", question, "--budget", str(budget_tokens)])
    return graph_context.anreichern(KNOWLEDGE_ROOT / project, raw)


@mcp.tool
def graph_explain(project: str, node: str) -> str:
    """Plain-language explanation of a graph node (function, concept, module)."""
    raw = _run_graphify(project, ["explain", node])
    return graph_context.anreichern(KNOWLEDGE_ROOT / project, raw)


@mcp.tool
def graph_path(project: str, source: str, target: str) -> str:
    """Shortest path between two concepts in a project's knowledge graph."""
    return _run_graphify(project, ["path", source, target])


@mcp.tool
def report_get(project: str) -> str:
    """The full GRAPH_REPORT.md of a project (god nodes, communities, surprises)."""
    if project not in _projects():
        raise ValueError(f"unknown project {project!r}; known: {_projects()}")
    return (KNOWLEDGE_ROOT / project / "graphify-out" / "GRAPH_REPORT.md").read_text()


GRAPHIFY_SYNC = os.environ.get("GRAPHIFY_SYNC", str(Path.home() / ".local" / "bin" / "graphify-sync"))
BUILD_LOG_DIR = Path(os.environ.get("KMCP_DATA_DIR", str(Path(__file__).parent))) / "build-logs"
_builds: dict[str, dict] = {}  # project name -> {status, started, finished, log}
_builds_lock = threading.Lock()


def _resolve_project_dir(project: str) -> Path:
    """Map a name or absolute path to a directory under $HOME (nothing outside is buildable)."""
    path = (Path(project) if project.startswith("/") else Path.home() / project).resolve()
    if not path.is_dir():
        raise ValueError(f"{str(path)!r} is not a directory")
    if not path.is_relative_to(Path.home()) or path == Path.home():
        raise ValueError("only project directories inside the home directory can be mapped")
    return path


def _build_worker(name: str, path: Path) -> None:
    """Ein Mapping-Lauf im Hintergrund.

    Der ganze Rumpf steht unter try/except/finally, und das ist der Punkt: Vorher fiel
    dieser Thread bei jedem unerwarteten Fehler still um — ein fehlendes graphify-sync,
    eine Zeitüberschreitung, eine volle Platte. Der Status blieb dann für immer auf
    „running“, und graph_build weigerte sich ab da, dieses Projekt je wieder zu bauen
    („build is already running“). Nur ein Serverneustart holte es zurück.

    Jetzt endet JEDER Weg aus dieser Funktion in einem Endzustand (done/failed), und der
    Grund steht im Log, das der Nutzer über graph_build_status sieht.
    """
    ende, grund = "failed", ""
    try:
        BUILD_LOG_DIR.mkdir(exist_ok=True)
        log_file = BUILD_LOG_DIR / f"{name}.log"
        steps = [[GRAPHIFY_BIN, "update", str(path)], [GRAPHIFY_SYNC, str(path)]]
        with log_file.open("w") as log:
            for cmd in steps:
                log.write(f"$ {shlex.join(cmd)}\n")
                log.flush()
                try:
                    proc = subprocess.run(  # noqa: S603 - fixed binaries, validated path
                        cmd,
                        stdout=log,
                        stderr=subprocess.STDOUT,
                        text=True,
                        timeout=1800,
                    )
                except subprocess.TimeoutExpired:
                    grund = f"Zeitüberschreitung nach 30 Minuten: {shlex.join(cmd)}"
                    log.write(f"\n!! {grund}\n")
                    return
                except OSError as e:  # Binary fehlt, keine Rechte, Platte voll
                    grund = f"{cmd[0]} konnte nicht ausgeführt werden: {e}"
                    log.write(f"\n!! {grund}\n")
                    return
                if proc.returncode != 0:
                    grund = f"{shlex.join(cmd)} endete mit Code {proc.returncode}"
                    return
        ende = "done"
    except Exception as e:  # noqa: BLE001 - ein toter Thread darf den Status nicht einfrieren
        grund = f"Unerwarteter Fehler: {type(e).__name__}: {e}"
    finally:
        with _builds_lock:
            _builds[name].update(status=ende, finished=int(time.time()), error=grund or None)


@mcp.tool
def graph_build(project: str) -> str:
    """Map (or re-map) a local project into the knowledge hub.

    Runs `graphify update` + sync in the background; the graph appears in
    projects_list when done. `project` is a directory name under the home
    directory (e.g. "bookit") or an absolute path. Check progress with
    graph_build_status.
    """
    path = _resolve_project_dir(project)
    name = path.name.lower()
    with _builds_lock:
        if _builds.get(name, {}).get("status") == "running":
            return f"build for {name!r} is already running"
        _builds[name] = {"status": "running", "started": int(time.time()), "finished": None}
    threading.Thread(target=_build_worker, args=(name, path), daemon=True).start()
    return f"started mapping {name!r} ({path}) — poll graph_build_status({name!r})"


@mcp.tool
def graph_build_status(project: str = "") -> dict | list[dict]:
    """Status of graph builds started via graph_build (all builds if project is empty)."""

    def _entry(name: str, b: dict) -> dict:
        log_file = BUILD_LOG_DIR / f"{name}.log"
        tail = log_file.read_text()[-1500:] if log_file.exists() else ""
        return {"project": name, **b, "log_tail": tail}

    with _builds_lock:
        if project:
            name = project.lower().rstrip("/").split("/")[-1]
            if name not in _builds:
                raise ValueError(f"no build known for {name!r}")
            return _entry(name, dict(_builds[name]))
        return [_entry(n, dict(b)) for n, b in _builds.items()]


def _kein_internes(name: str) -> None:
    """Interne Secrets (2FA-Seed) sind für verbundene Clients unsichtbar.

    Sie gehören der Anwendung, nicht dem Nutzer. Ein Client, der sie lesen darf,
    umgeht die Zwei-Faktor-Anmeldung; einer, der sie löschen darf, schaltet sie ab.
    Die Fehlermeldung ist bewusst dieselbe wie für ein nicht vorhandenes Secret —
    sie soll nicht einmal verraten, dass es den Eintrag gibt.
    """
    if name in vault.HIDDEN_SECRETS:
        raise ValueError(f"no secret named {name!r}")


@mcp.tool
def secret_list() -> list[str]:
    """Names of stored secrets (values are never listed)."""
    return [s for s in vault.secret_list(client="mcp") if s not in vault.HIDDEN_SECRETS]


@mcp.tool
def secret_get(name: str) -> str:
    """Fetch one secret value from the encrypted vault. Access is audit-logged."""
    _kein_internes(name)
    value = vault.secret_get(name, client="mcp")
    if value is None:
        raise ValueError(f"no secret named {name!r}")
    return value


@mcp.tool
def secret_set(name: str, value: str) -> str:
    """Store or overwrite a secret in the encrypted vault."""
    _kein_internes(name)
    vault.secret_set(name, value, client="mcp")
    return f"stored {name!r}"


# ---------------------------------------------------------------------------
# Notizen: Wissen aus dem Chat in den Hub schreiben
# ---------------------------------------------------------------------------
# Jede Notiz ist eine Markdown-Datei unter ~/knowledge-notes/<projekt>/. Das ist
# bewusst kein eigenes Datenbankformat: graphify liest Markdown ohnehin semantisch,
# die Dateien bleiben mit jedem Editor lesbar, und ein Projekt ist einfach ein Ordner.
NOTES_ROOT = Path(os.environ.get("KMCP_NOTES_ROOT", str(Path.home() / "knowledge-notes")))
_SLUG_RE = __import__("re").compile(r"[^a-z0-9äöüß]+")


def _slug(text: str, fallback: str) -> str:
    s = _SLUG_RE.sub("-", text.lower()).strip("-")[:60]
    return s or fallback


_projekt_lock = threading.Lock()


def _register_project(path: Path) -> bool:
    """Ordner ins Nacht-Mapping eintragen (idempotent). True = war neu.

    Unter der Sperre, weil Lesen–Anhängen–Schreiben sonst Einträge verliert: Legen zwei
    Clients gleichzeitig eine Notiz in je einem neuen Projekt an, lesen beide dieselbe
    Liste und der Zweite schreibt den Ersten wieder weg — sein Projekt würde nachts
    nie gemappt.
    """
    home = str(Path.home())
    stored = "~" + str(path)[len(home) :] if str(path).startswith(home) else str(path)
    with _projekt_lock:
        entries = config.project_entries()
        if any(str(Path(e["path"]).expanduser()) == str(path) for e in entries):
            return False
        entries.append({"path": stored, "enabled": True})
        config.save_projects(entries)
    return True


def _write_note(project: str, title: str, content: str, tags: list[str] | None) -> tuple[Path, bool]:
    pslug = _slug(project, "notizen")
    folder = (NOTES_ROOT / pslug).resolve()
    if not folder.is_relative_to(NOTES_ROOT):
        raise ValueError("invalid project name")
    folder.mkdir(parents=True, exist_ok=True)
    neu = _register_project(folder)
    stamp = time.strftime("%Y-%m-%d")
    basis = _slug(title, "notiz")
    kopf = [f"# {title.strip()}", ""]
    meta = [f"*Gespeichert am {time.strftime('%Y-%m-%d %H:%M')} aus einem Claude-Chat.*"]
    if tags:
        meta.append("Tags: " + ", ".join(str(t).strip() for t in tags if str(t).strip()))
    text = "\n".join(kopf + meta + ["", content.strip(), ""])

    # Gleicher Titel am selben Tag -> durchnummerieren. Das Anlegen MUSS exklusiv sein
    # (O_EXCL): Ein `while f.exists()` davor ist ein Prüfen-dann-Schreiben — speichern
    # zwei Clients gleichzeitig eine Notiz mit demselben Titel, sehen beide dieselbe
    # freie Nummer, und die zweite überschreibt die erste spurlos.
    for n in range(1, 1000):
        f = folder / (f"{stamp}-{basis}.md" if n == 1 else f"{stamp}-{basis}-{n}.md")
        try:
            fd = os.open(f, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        except FileExistsError:
            continue
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(text)
        break
    else:
        raise RuntimeError(f"zu viele Notizen mit dem Titel {title!r} an einem Tag")
    vault.audit("NOTE-SAVE", f"{pslug}/{f.name}", client="mcp")
    return f, neu


@mcp.tool
def note_save(project: str, title: str, content: str, tags: list[str] | None = None) -> str:
    """Save knowledge from this conversation into the hub as a markdown note.

    Use when the user shares something worth keeping: facts about themselves,
    decisions, research findings, ideas. `project` groups related notes (e.g.
    "ueber-belkis", "geschaeftsideen") — it is created and registered for the
    nightly mapping automatically. The note becomes part of the knowledge graph
    on the next mapping run and is then answerable via graph_query.
    """
    f, neu = _write_note(project, title, content, tags)
    hinweis = " New project registered for nightly mapping (03:30)." if neu else ""
    return (
        f"saved {f.name} in project {f.parent.name!r}.{hinweis} "
        f"It enters the knowledge graph on the next mapping run."
    )


@mcp.tool
def note_list(project: str) -> list[str]:
    """List the notes stored in a notes project (filenames, newest first)."""
    folder = (NOTES_ROOT / _slug(project, "notizen")).resolve()
    if not folder.is_relative_to(NOTES_ROOT) or not folder.is_dir():
        return []
    return sorted((f.name for f in folder.glob("*.md")), reverse=True)


@mcp.tool
def project_create(name: str, description: str = "") -> str:
    """Create a new (empty) notes project in the hub and register it for mapping.

    Use when the user wants a fresh knowledge area without saving a note yet.
    For code repositories use graph_build instead.
    """
    pslug = _slug(name, "")
    if not pslug:
        raise ValueError("project name must contain letters or digits")
    folder = (NOTES_ROOT / pslug).resolve()
    folder.mkdir(parents=True, exist_ok=True)
    readme = folder / "README.md"
    if not readme.exists():
        readme.write_text(f"# {name.strip()}\n\n{description.strip()}\n", encoding="utf-8")
    neu = _register_project(folder)
    vault.audit("PROJECT-CREATE", pslug, client="mcp")
    return (
        f"project {pslug!r} {'created and registered' if neu else 'already existed'} "
        f"at {folder}. Save knowledge into it with note_save."
    )


@mcp.tool
def secret_delete(name: str) -> str:
    """Delete a secret from the vault."""
    _kein_internes(name)
    return f"deleted {name!r}" if vault.secret_delete(name, client="mcp") else f"{name!r} did not exist"


app = mcp.http_app()


class BearerGate:
    """Reject requests that carry neither the static token nor a valid OAuth token.

    OAuth discovery + flow endpoints (/.well-known/*, /oauth/*) must stay open —
    they are how claude.ai obtains a token in the first place. The 401 carries a
    WWW-Authenticate pointer to the protected-resource metadata (RFC 9728) so
    OAuth-capable clients discover the flow automatically.
    """

    def __init__(self, inner):
        self._inner = inner

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self._inner(scope, receive, send)
            return
        path = scope.get("path", "")
        if path.startswith("/.well-known/") or path.startswith("/oauth/"):
            await oauth.oauth_app(scope, receive, send)
            return
        # Das Favicon an der Wurzel: Connector-Listen (ChatGPT, Browser-Tabs) fragen es
        # zuerst ab. Hinter der Schranke lieferte es 401 — der Client bekam nie ein Bild
        # und zeigte einen Platzhalter. Ein Icon ist kein Geheimnis.
        if path in (
            "/favicon.ico",
            "/favicon.png",
            "/apple-touch-icon.png",
            "/apple-touch-icon-precomposed.png",
        ):
            await ui.ui_app(scope, receive, send)
            return
        headers = dict(scope.get("headers") or [])
        auth = headers.get(b"authorization", b"").decode()
        token = auth.removeprefix("Bearer ").strip() if auth.startswith("Bearer ") else ""
        static_ok = bool(MCP_TOKEN) and hmac.compare_digest(token, MCP_TOKEN)
        ua = headers.get(b"user-agent", b"").decode(errors="replace")
        authorized = static_ok or oauth.validate_access_token(token, ua)
        # Gesundheitsebenen für Blue-Green: live/ready sind offen, aber bewusst nur ein
        # Statuswort (kein Befund nach außen — der Hostname hängt am Tunnel). Die
        # Detailsicht verlangt denselben Bearer wie MCP; ohne ihn fällt der Aufruf in
        # den allgemeinen 401-Zweig weiter unten.
        if path == "/healthz/live":
            await JSONResponse({"status": "ok"})(scope, receive, send)
            return
        if path == "/healthz/ready":
            ok, _checks = await health.ready(mcp)
            await JSONResponse({"status": "ready" if ok else "unready"}, status_code=200 if ok else 503)(
                scope, receive, send
            )
            return
        if path == "/healthz/deep" and authorized:
            ok, checks = await health.ready(mcp)
            await JSONResponse({"status": "ready" if ok else "unready", "checks": checks})(
                scope, receive, send
            )
            return
        if path == "/ui" or path.startswith("/ui/"):
            # Die Seite selbst und der Login sind offen; alle Daten-Endpunkte nicht.
            # /ui/asset/ = Stylesheet und Skript der Oberfläche — reiner Programmcode,
            # keine Daten. Muss offen sein, sonst lädt schon der Login-Bildschirm nicht.
            open_ui = (
                path in ("/ui", "/ui/", "/ui/api/login", "/ui/manifest.json")
                or path.startswith("/ui/static/")
                or path.startswith("/ui/asset/")
            )
            # Setup-Endpunkte sind nur offen, SOLANGE das System nicht eingerichtet ist —
            # danach sperren sie sich selbst (kein Übernehmen eines laufenden Hubs).
            if path.startswith("/ui/setup"):
                import setup_wizard

                if setup_wizard.is_configured() and path != "/ui/setup/status":
                    await JSONResponse({"error": "System ist bereits eingerichtet"}, status_code=409)(
                        scope, receive, send
                    )
                    return
                open_ui = True
            if open_ui or authorized:
                await ui.ui_app(scope, receive, send)
                return
            await JSONResponse({"error": "unauthorized"}, status_code=401)(scope, receive, send)
            return
        if not authorized:
            request = Request(scope, receive)  # noqa: F841 - consume for well-formed response
            response = JSONResponse(
                {"error": "unauthorized"},
                status_code=401,
                headers={
                    "WWW-Authenticate": (
                        'Bearer realm="knowledge-mcp", '
                        f'resource_metadata="{oauth.ISSUER}/.well-known/oauth-protected-resource"'
                    )
                },
            )
            await response(scope, receive, send)
            return
        await self._inner(scope, receive, send)


application = BearerGate(app)

if __name__ == "__main__":
    import uvicorn

    # Im Container muss auf 0.0.0.0 gelauscht werden -> Env sticht die Konfiguration.
    host = os.environ.get("KNOWLEDGE_HOST", CFG["server"]["host"])
    port = int(os.environ.get("KNOWLEDGE_PORT", CFG["server"]["port"]))
    uvicorn.run(application, host=host, port=port)
