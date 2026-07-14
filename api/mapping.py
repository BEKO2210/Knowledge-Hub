"""Nacht-Mapping: Zeitplan, Läufe, Projektverwaltung und Reparatur."""

from __future__ import annotations

import getpass
import json
import os
import re
import shutil
import subprocess
import threading
from pathlib import Path

from starlette.requests import Request
from starlette.responses import JSONResponse

import config
import vault
from api.common import DATA_DIR, GRAPHIFY_BIN, KNOWLEDGE_ROOT
from api.i18n import T

# ---------------------------------------------------------------------------
TIMER_FILE = Path.home() / ".config" / "systemd" / "user" / "nightly-map.timer"
NIGHTLY_LOG_DIR = DATA_DIR / "build-logs"

# Empfohlene Standard-Ausschlüsse: minifizierte, vendored und generierte Dateien
# machen sonst die dichtesten Hub-Knoten des Graphen aus ($(), t(), *.min.js).
# graphify liest .gitignore ohnehin mit — hier steht nur, was dort typisch fehlt.
DEFAULT_IGNORE = """\
*.min.js
*.min.css
*.min.mjs
*.map
*.bundle.js
*.chunk.js
vendor/
third_party/
"""

TIMER_TEMPLATE = """[Unit]
Description=Startet das nächtliche Deep-Mapping um {time}

[Timer]
OnCalendar=*-*-* {time}:00
Persistent=true
RandomizedDelaySec=600

[Install]
WantedBy=timers.target
"""


def _sysctl(*args: str) -> tuple[int, str]:
    proc = subprocess.run(  # noqa: S603 - fixed binary, fixed unit names
        ["systemctl", "--user", *args], capture_output=True, text=True, timeout=15
    )
    return proc.returncode, (proc.stdout or proc.stderr).strip()


def _timer_time() -> str:
    if TIMER_FILE.exists():
        m = re.search(r"OnCalendar=\*-\*-\* (\d\d:\d\d)", TIMER_FILE.read_text())
        if m:
            return m.group(1)
    return "03:30"


def _parse_run(text: str) -> dict:
    """Kosten/Tokens/Projekte eines einzelnen Lauf-Abschnitts."""
    costs = [float(c) for c in re.findall(r"est\. cost [^:]*: \$([0-9.]+)", text)]
    toks = re.findall(r"tokens: ([\d,]+) in / ([\d,]+) out", text)
    return {
        "cost": round(sum(costs), 4),
        "tokens_in": sum(int(a.replace(",", "")) for a, _ in toks),
        "tokens_out": sum(int(b.replace(",", "")) for _, b in toks),
        "projects": len(re.findall(r"^--- /", text, re.M)),
        "failed": len(re.findall(r"FEHLGESCHLAGEN", text)),
        "done": "nightly-map done" in text,
    }


def _log_costs() -> dict:
    """Kosten-Statistik aus den Lauf-Logs.

    Wichtig: alles hier ist graphifys *Schätzung* (Tokens × Modellpreis), nicht die
    echte Anbieter-Rechnung — Prompt-Caching macht die reale Rechnung meist günstiger.
    """
    total_cost, total_in, total_out, runs = 0.0, 0, 0, 0
    last = None
    for f in sorted(NIGHTLY_LOG_DIR.glob("nightly-*.log")):
        text = f.read_text()
        # Jede Log-Datei kann mehrere Läufe enthalten (Nacht-Lauf + manuelle Starts)
        sections = text.split("=== nightly-map start")[1:]
        for sec in sections:
            r = _parse_run(sec)
            total_cost += r["cost"]
            total_in += r["tokens_in"]
            total_out += r["tokens_out"]
            runs += 1
            last = {**r, "date": f.stem.removeprefix("nightly-")}
    return {
        "total_cost": round(total_cost, 4),
        "total_in": total_in,
        "total_out": total_out,
        "runs": runs,
        "last": last,
    }


_RUN_START_RE = re.compile(r"=== nightly-map start (\S+)(?: backend=(\S+))? model=(\S+) ===")
_RUN_DONE_RE = re.compile(r"=== nightly-map done (\S+) ===")
_PROJ_LINE_RE = re.compile(r"^--- (\S+) \(")
_WROTE_RE = re.compile(r"wrote \S*?/graph\.json: (\d+) nodes, (\d+) edges")
_COST_RE = re.compile(r"est\. cost [^:]*: \$([0-9.]+)")
_TOK_RE = re.compile(r"tokens: ([\d,]+) in / ([\d,]+) out")
_FAIL_RE = re.compile(r"FEHLGESCHLAGEN:?\s*(\S+)?")


def _iso_secs(a: str, b: str) -> int | None:
    """Sekunden zwischen zwei ISO-Zeitstempeln (Dauer eines Laufs)."""
    from datetime import datetime

    try:
        return max(0, int((datetime.fromisoformat(b) - datetime.fromisoformat(a)).total_seconds()))
    except (ValueError, TypeError):
        return None


def _parse_runs() -> list[dict]:
    """Alle Nacht-Läufe aus den Logs als strukturierte Liste (chronologisch).

    Ein Lauf = ein Abschnitt zwischen `start` und `done`. Pro Projekt werden Knoten/
    Kanten aus der `wrote …graph.json`-Zeile gezogen, Kosten/Tokens summiert, Fehler
    gezählt. Die Knoten-Differenz je Projekt entsteht im Vergleich zum vorigen Lauf.
    """
    runs: list[dict] = []
    for f in sorted(NIGHTLY_LOG_DIR.glob("nightly-*.log")):
        lines = f.read_text().splitlines()
        cur: dict | None = None
        cur_proj: str | None = None
        for line in lines:
            m = _RUN_START_RE.search(line)
            if m:
                cur = {
                    "start": m.group(1),
                    "backend": m.group(2) or "",
                    "model": m.group(3),
                    "projects": [],
                    "failed_names": [],
                    "failures": [],
                    "backup_failed": False,
                    "cost": 0.0,
                    "tokens_in": 0,
                    "tokens_out": 0,
                    "duration_s": None,
                }
                cur_proj = None
                runs.append(cur)
                continue
            if cur is None:
                continue
            m = _RUN_DONE_RE.search(line)
            if m:
                cur["duration_s"] = _iso_secs(cur["start"], m.group(1))
                cur = None
                continue
            m = _PROJ_LINE_RE.match(line)
            if m:
                cur_proj = m.group(1).rstrip("/").rsplit("/", 1)[-1]
                cur["projects"].append({"name": cur_proj, "nodes": None, "edges": None})
                continue
            m = _WROTE_RE.search(line)
            if m and cur["projects"]:
                cur["projects"][-1]["nodes"] = int(m.group(1))
                cur["projects"][-1]["edges"] = int(m.group(2))
                continue
            m = _COST_RE.search(line)
            if m:
                cur["cost"] += float(m.group(1))
                continue
            m = _TOK_RE.search(line)
            if m:
                cur["tokens_in"] += int(m.group(1).replace(",", ""))
                cur["tokens_out"] += int(m.group(2).replace(",", ""))
                continue
            # Fehler sind nicht gleich Fehler: Ein gescheitertes Projekt repariert man
            # anders als eine gescheiterte Sicherung. Vorher landete beides im selben
            # Topf — und die Sicherung, die keinen Projektnamen trägt, erschien in der
            # Oberfläche als namenloser Fehler „?".
            low = line.lower()
            if "sicherung fehlgeschlagen" in low:
                cur["backup_failed"] = True
                continue
            if "fehlgeschlagen" in low:
                fm = _FAIL_RE.search(line)
                name = (fm.group(1) or "").rstrip("/").rsplit("/", 1)[-1] if fm else ""
                if not name:
                    continue  # ohne Projektnamen ist es kein Projektfehler
                art = "sync" if low.startswith("sync") else "extract"
                cur["failed_names"].append(name)
                cur["failures"].append({"project": name, "kind": art})

    # Knoten-Differenz je Projekt gegenüber dem jeweils letzten bekannten Stand
    last_nodes: dict[str, int] = {}
    for r in runs:
        node_total, delta = 0, 0
        for p in r["projects"]:
            if p["nodes"] is None:
                continue
            node_total += p["nodes"]
            prev = last_nodes.get(p["name"])
            p["delta"] = None if prev is None else p["nodes"] - prev
            if prev is not None:
                delta += p["nodes"] - prev
            last_nodes[p["name"]] = p["nodes"]
        r["cost"] = round(r["cost"], 4)
        r["nodes_total"] = node_total
        r["node_delta"] = delta
        r["project_count"] = len(r["projects"])
        r["failed"] = len(r["failed_names"])
    return runs


# ---------------------------------------------------------------------------
# Quittierte Läufe
# ---------------------------------------------------------------------------
# Ein Fehler im Verlauf ist eine Tatsache — man kann ihn nicht wegzaubern. Aber man
# kann ihn erledigt haben. Wer die Ursache behoben hat, hakt den Lauf ab; die Warnung
# verschwindet aus der Zusammenfassung, der Eintrag selbst bleibt ehrlich stehen.
# Die Liste liegt in einer Datei, nicht im Code.
DISMISSED_FILE = DATA_DIR / "mapping_dismissed.json"


def _dismissed() -> set[str]:
    try:
        return set(json.loads(DISMISSED_FILE.read_text()))
    except Exception:  # noqa: BLE001 - fehlende oder kaputte Datei = nichts quittiert
        return set()


def _set_dismissed(starts: set[str]) -> None:
    tmp = DISMISSED_FILE.with_suffix(".tmp")
    tmp.write_text(json.dumps(sorted(starts)))
    tmp.replace(DISMISSED_FILE)


async def mapping_history(request: Request) -> JSONResponse:
    """Verlauf aller Nacht-Läufe (neueste zuerst) — für Tabelle + Kosten-Sparkline."""
    runs = _parse_runs()
    quittiert = _dismissed()
    for r in runs:
        r["dismissed"] = r["start"] in quittiert
    return JSONResponse({"runs": list(reversed(runs))[:60]})


async def mapping_dismiss(request: Request) -> JSONResponse:
    """Einen Lauf als erledigt abhaken (oder das Häkchen wieder entfernen)."""
    body = await request.json()
    start = str(body.get("start", "")).strip()
    if not start:
        return JSONResponse({"error": T("Kein Lauf angegeben.")}, status_code=400)
    quittiert = _dismissed()
    if body.get("dismissed", True):
        quittiert.add(start)
    else:
        quittiert.discard(start)
    _set_dismissed(quittiert)
    return JSONResponse({"ok": True, "dismissed": start in quittiert})


async def mapping_status(request: Request) -> JSONResponse:
    cfg = config.load()  # frisch laden: Backend/Modell sind zur Laufzeit änderbar
    _, enabled = _sysctl("is-enabled", "nightly-map.timer")
    _, active = _sysctl("is-active", "nightly-map.service")
    _, next_run = _sysctl("show", "nightly-map.timer", "--property=NextElapseUSecRealtime", "--value")
    backend_name, backend = config.active_backend(cfg)
    stored = set(vault.secret_list(client="web-ui"))

    out_backends = []
    for name, b in config.backends(cfg).items():
        secret = b.get("secret")
        out_backends.append(
            {
                "id": name,
                "label": b.get("label", name),
                "models": b.get("models", []),
                "key_url": b.get("key_url"),
                "key_hint": b.get("key_hint"),
                "local": bool(b.get("local")),
                "secret": secret,
                # lokale Backends brauchen keinen Key -> gelten als "bereit"
                "has_key": bool(b.get("local")) or (secret in stored if secret else False),
            }
        )

    return JSONResponse(
        {
            "enabled": enabled == "enabled",
            # Type=oneshot meldet "activating", solange das Skript läuft
            "running": active in ("active", "activating"),
            "next_run": next_run if next_run not in ("", "n/a") else None,
            "time": _timer_time(),
            "backend": backend_name,
            "model": cfg["mapping"].get("model", ""),
            "backends": out_backends,
            "has_key": bool(backend.get("local"))
            or (backend.get("secret") in stored if backend.get("secret") else False),
            "projects": [str(p) for p in config.projects(cfg)],
            "costs": _log_costs(),
        }
    )


async def mapping_toggle(request: Request) -> JSONResponse:
    body = await request.json()
    on = bool(body.get("enabled"))
    code, out = _sysctl("enable" if on else "disable", "--now", "nightly-map.timer")
    vault.audit("MAPPING-ON" if on else "MAPPING-OFF", "nightly-map.timer", client="web-ui")
    if code != 0:
        return JSONResponse({"error": out[:300]}, status_code=500)
    return JSONResponse({"ok": True, "enabled": on})


async def mapping_config(request: Request) -> JSONResponse:
    body = await request.json()
    cfg = config.load()
    t = str(body.get("time", "")).strip()
    backend = str(body.get("backend", "")).strip()
    model = str(body.get("model", "")).strip()

    if not re.fullmatch(r"([01]\d|2[0-3]):[0-5]\d", t):
        return JSONResponse({"error": T("Ungültige Uhrzeit (Format HH:MM)")}, status_code=400)
    defs = config.backends(cfg)
    if backend not in defs:
        return JSONResponse({"error": T("Unbekanntes Backend")}, status_code=400)
    # Modell: aus der Liste ODER frei eingegeben (neue Modelle sollen ohne Update nutzbar sein)
    if not re.fullmatch(r"[\w.:\-/]{2,60}", model):
        return JSONResponse({"error": T("Ungültiger Modellname")}, status_code=400)

    TIMER_FILE.write_text(TIMER_TEMPLATE.format(time=t))
    config.save_mapping(backend, model)
    _sysctl("daemon-reload")
    _, enabled = _sysctl("is-enabled", "nightly-map.timer")
    if enabled == "enabled":
        _sysctl("restart", "nightly-map.timer")
    vault.audit("MAPPING-CONFIG", f"{t} {backend}/{model}", client="web-ui")
    return JSONResponse({"ok": True})


async def mapping_run(request: Request) -> JSONResponse:
    _, active = _sysctl("is-active", "nightly-map.service")
    if active in ("active", "activating"):
        return JSONResponse({"error": T("Läuft bereits")}, status_code=409)
    code, out = _sysctl("start", "--no-block", "nightly-map.service")
    vault.audit("MAPPING-RUN", "manuell gestartet", client="web-ui")
    if code != 0:
        return JSONResponse({"error": out[:300]}, status_code=500)
    return JSONResponse({"ok": True})


# --- Projekt-Verwaltung (Run 2) -------------------------------------------
# Verzeichnisse dürfen nur innerhalb dieser Wurzeln liegen — verhindert, dass
# über die UI beliebige Systempfade gescannt oder beschrieben werden.
BROWSE_ROOTS = [Path.home(), Path("/opt")]


def _safe_dir(raw: str) -> Path | None:
    try:
        p = Path(raw).expanduser().resolve()
    except (OSError, RuntimeError):
        return None
    if not p.is_dir():
        return None
    if not any(p.is_relative_to(root) for root in BROWSE_ROOTS):
        return None
    return p


def _project_paths() -> dict[str, dict]:
    """Konfigurierte Projekte, Schlüssel = aufgelöster absoluter Pfad."""
    out = {}
    for e in config.project_entries():
        p = Path(e["path"]).expanduser()
        out[str(p)] = e
    return out


async def mapping_projects(request: Request) -> JSONResponse:
    items = []
    for e in config.project_entries():
        p = Path(e["path"]).expanduser()
        graph = p / "graphify-out" / "graph.json"
        nodes = None
        if graph.exists():
            try:
                nodes = len(json.loads(graph.read_text()).get("nodes", []))
            except Exception:
                nodes = None
        issues = _diagnose_project(p)
        items.append(
            {
                "path": e["path"],
                "abs": str(p),
                "name": p.name,
                "enabled": e["enabled"],
                "exists": p.is_dir(),
                "nodes": nodes,
                "has_ignore": (p / ".graphifyignore").is_file(),
                # Was steht einem Mapping im Weg — und lässt es sich per Knopf beheben?
                "issues": issues,
                "repairable": bool(issues) and all(i["fixable"] for i in issues),
            }
        )
    return JSONResponse(items)


async def mapping_project_add(request: Request) -> JSONResponse:
    body = await request.json()
    p = _safe_dir(str(body.get("path", "")))
    if p is None:
        return JSONResponse(
            {"error": T("Kein gültiges Verzeichnis (erlaubt: Home und /opt)")}, status_code=400
        )
    entries = config.project_entries()
    if str(p) in {str(Path(e["path"]).expanduser()) for e in entries}:
        return JSONResponse({"error": T("Projekt ist bereits eingetragen")}, status_code=409)
    # Home-Pfade lesbar mit ~ abspeichern
    home = str(Path.home())
    stored = "~" + str(p)[len(home) :] if str(p).startswith(home) else str(p)
    entries.append({"path": stored, "enabled": True})
    config.save_projects(entries)
    vault.audit("PROJECT-ADD", stored, client="web-ui")
    return JSONResponse({"ok": True})


# Ordner im Wissens-Repo, die nie einem Projekt gehören — dürfen beim Purge nicht fallen
RESERVED_GRAPH_DIRS = {"hub-backups", "_claude"}


def _git_purge_commit(name: str) -> None:
    """Löschung im Wissens-Repo festhalten und pushen — best effort wie graphify-sync."""
    try:

        def git(*args: str) -> subprocess.CompletedProcess:
            return subprocess.run(  # noqa: S603 - fixed binary, list args
                ["git", *args], cwd=KNOWLEDGE_ROOT, capture_output=True, text=True, timeout=60
            )

        git("add", "-A")
        if git("diff", "--cached", "--quiet").returncode != 0:
            git("commit", "-q", "-m", f"graph purge: {name}")
            git("push", "-q", "origin", "main")
    except Exception:
        pass  # Repo-Sync darf das Entfernen nie blockieren


def _purge_graph_data(project_dir: Path) -> list[str]:
    """Löscht ALLE Graph-Artefakte eines Projekts: Hub-Kopie, lokales graphify-out, Antworten.

    Der Projektordner selbst (Quellcode, Notizen) bleibt unangetastet.
    """
    removed: list[str] = []
    name = project_dir.name.lower()
    if not name or name in RESERVED_GRAPH_DIRS:
        return removed

    # 1) Hub-Kopie im Wissens-Repo — das, was MCP-Tools und der Graphen-Tab servieren
    hub_copy = KNOWLEDGE_ROOT / name
    if hub_copy.is_dir() and hub_copy.resolve().parent == KNOWLEDGE_ROOT.resolve():
        shutil.rmtree(hub_copy)
        removed.append(str(hub_copy))
        _git_purge_commit(name)

    # 2) Lokale Graph-Daten im Projektordner
    local_out = project_dir / "graphify-out"
    if local_out.is_dir() and not local_out.is_symlink():
        shutil.rmtree(local_out)
        removed.append(str(local_out))

    # 3) Gespeicherte Antworten zu diesem Projekt
    answers = DATA_DIR / "answers" / name
    if answers.is_dir():
        shutil.rmtree(answers)
        removed.append(str(answers))

    return removed


async def mapping_project_update(request: Request) -> JSONResponse:
    """Toggle enabled oder Projekt entfernen (entfernen = Graph-Daten komplett löschen)."""
    body = await request.json()
    target = str(body.get("path", ""))
    action = str(body.get("action", ""))
    entries = config.project_entries()
    resolved = str(Path(target).expanduser())
    kept, found, purged = [], False, []
    for e in entries:
        if str(Path(e["path"]).expanduser()) == resolved:
            found = True
            if action == "remove":
                purged = _purge_graph_data(Path(e["path"]).expanduser())
                continue
            if action == "toggle":
                e["enabled"] = not e["enabled"]
        kept.append(e)
    if not found:
        return JSONResponse({"error": T("Projekt nicht gefunden")}, status_code=404)
    config.save_projects(kept)
    vault.audit(f"PROJECT-{action.upper()}", target, client="web-ui")
    if action == "remove":
        vault.audit("GRAPH-PURGE", "; ".join(purged) or "keine Graph-Daten vorhanden", client="web-ui")
    return JSONResponse({"ok": True, "purged": purged})


def _diagnose_project(p: Path) -> list[dict]:
    """Warum lässt sich dieses Projekt nicht mappen? Liefert Befunde + Reparierbarkeit."""
    out: list[dict] = []
    if not p.is_dir():
        out.append(
            {
                "problem": T("Der Ordner {path} existiert nicht.", path=p),
                "fixable": False,
                "fix": T("Projekt entfernen oder Pfad korrigieren."),
            }
        )
        return out
    if not (os.access(p, os.R_OK) and os.access(p, os.X_OK)):
        out.append(
            {
                "problem": T("Keine Leserechte auf {path}.", path=p),
                "fixable": False,
                "fix": T(
                    "Auf dem Server ausführen:  sudo setfacl -m u:{user}:rx {path}",
                    user=getpass.getuser(),
                    path=p,
                ),
            }
        )
        return out
    graph_out = p / "graphify-out"
    if not graph_out.exists():
        out.append(
            {
                "problem": T("Der Ausgabeordner graphify-out fehlt."),
                "fixable": True,
                "fix": T("Wird beim Reparieren angelegt."),
            }
        )
    elif not os.access(graph_out, os.W_OK):
        out.append(
            {
                "problem": T("{path} ist nicht beschreibbar (gehört einem anderen Nutzer).", path=graph_out),
                "fixable": False,
                "fix": T(
                    "Auf dem Server ausführen:  sudo chown -R {user} {path}",
                    user=getpass.getuser(),
                    path=graph_out,
                ),
            }
        )
    return out


async def project_check(request: Request) -> JSONResponse:
    """Prüft ein Projekt und meldet, was einem Mapping im Weg steht."""
    target = str(request.query_params.get("path", ""))
    p = Path(target).expanduser()
    if str(p) not in _project_paths():
        return JSONResponse({"error": T("Projekt nicht konfiguriert")}, status_code=404)
    issues = _diagnose_project(p)
    return JSONResponse(
        {
            "ok": not issues,
            "issues": issues,
            "repairable": all(i["fixable"] for i in issues) if issues else True,
        }
    )


_repairs: dict[str, dict] = {}


def _repair_worker(name: str, p: Path, cfg: dict) -> None:
    """Repariert, was reparierbar ist, und mappt das Projekt danach neu."""
    lines: list[str] = []
    try:
        graph_out = p / "graphify-out"
        if not graph_out.exists():
            graph_out.mkdir(parents=True, exist_ok=True)
            lines.append(T("Ausgabeordner angelegt: {path}", path=graph_out))

        rest = [i for i in _diagnose_project(p) if not i["fixable"]]
        if rest:
            lines.append(T("Nicht automatisch behebbar:"))
            lines += [f"  • {i['problem']}\n    {i['fix']}" for i in rest]
            _repairs[name] = {"status": "failed", "log": "\n".join(lines)}
            return

        backend_name, backend = config.active_backend(cfg)
        model = cfg["mapping"].get("model", "")
        secret = backend.get("secret")
        key = vault.secret_get(secret, client="web-ui") if secret else ""
        env = dict(os.environ)
        args = [
            GRAPHIFY_BIN,
            "extract",
            str(p),
            "--backend",
            backend_name,
            "--model",
            model,
            "--api-timeout",
            str(cfg["mapping"].get("api_timeout", 300)),
        ]
        if secret and key:
            env[backend["env"]] = key
        elif secret:
            args.append("--code-only")
            lines.append(T("Kein API-Key hinterlegt — es wird nur Code gemappt (ohne Dokumente)."))

        lines.append(
            T(
                "Mappe {name} neu ({backend} · {model})…",
                name=p.name,
                backend=backend.get("label", backend_name),
                model=model,
            )
        )
        proc = subprocess.run(  # noqa: S603 - feste Binary, geprüfter Pfad, Listenargumente
            args,
            capture_output=True,
            text=True,
            timeout=1800,
            env=env,
        )
        tail = (proc.stdout or proc.stderr).strip().splitlines()[-12:]
        lines += tail
        if proc.returncode != 0:
            _repairs[name] = {"status": "failed", "log": "\n".join(lines)}
            return
        subprocess.run(
            [config.path(cfg["paths"]["graphify_sync"]), str(p)],  # noqa: S603
            capture_output=True,
            text=True,
            timeout=300,
        )
        lines.append(T("✓ Reparatur erfolgreich — Projekt ist wieder gemappt."))
        _repairs[name] = {"status": "done", "log": "\n".join(lines)}
    except Exception as e:  # noqa: BLE001
        lines.append(T("Fehler bei der Reparatur: {msg}", msg=e))
        _repairs[name] = {"status": "failed", "log": "\n".join(lines)}


async def project_repair(request: Request) -> JSONResponse:
    body = await request.json()
    target = str(body.get("path", ""))
    p = Path(target).expanduser()
    if str(p) not in _project_paths():
        return JSONResponse({"error": T("Projekt nicht konfiguriert")}, status_code=404)
    name = p.name
    if _repairs.get(name, {}).get("status") == "running":
        return JSONResponse({"error": T("Reparatur läuft bereits")}, status_code=409)
    _repairs[name] = {"status": "running", "log": T("Reparatur gestartet…")}
    vault.audit("PROJECT-REPAIR", target, client="web-ui")
    threading.Thread(target=_repair_worker, args=(name, p, config.load()), daemon=True).start()
    return JSONResponse({"ok": True})


async def project_repair_status(request: Request) -> JSONResponse:
    name = Path(str(request.query_params.get("path", ""))).expanduser().name
    return JSONResponse(_repairs.get(name, {"status": "idle", "log": ""}))


async def browse_dirs(request: Request) -> JSONResponse:
    raw = request.query_params.get("path", "")
    p = _safe_dir(raw) if raw else None
    if p is None:
        p = Path.home()
    dirs = []
    try:
        for child in sorted(p.iterdir()):
            if child.name.startswith(".") or not child.is_dir():
                continue
            dirs.append(child.name)
    except PermissionError:
        pass
    parent = str(p.parent) if any(p != root and p.is_relative_to(root) for root in BROWSE_ROOTS) else None
    roots = [str(r) for r in BROWSE_ROOTS]
    return JSONResponse({"path": str(p), "parent": parent, "dirs": dirs[:200], "roots": roots})


async def ignore_get(request: Request) -> JSONResponse:
    p = _project_paths().get(str(Path(request.query_params.get("path", "")).expanduser()))
    if p is None:
        return JSONResponse({"error": T("Projekt nicht gefunden")}, status_code=404)
    f = Path(p["path"]).expanduser() / ".graphifyignore"
    return JSONResponse(
        {
            "content": f.read_text() if f.is_file() else "",
            "default": DEFAULT_IGNORE,
        }
    )


async def ignore_put(request: Request) -> JSONResponse:
    body = await request.json()
    p = _project_paths().get(str(Path(str(body.get("path", ""))).expanduser()))
    if p is None:
        return JSONResponse({"error": T("Projekt nicht gefunden")}, status_code=404)
    content = str(body.get("content", ""))[:20000]
    f = Path(p["path"]).expanduser() / ".graphifyignore"
    try:
        f.write_text(content)
    except PermissionError:
        return JSONResponse({"error": T("Keine Schreibrechte in diesem Projekt")}, status_code=403)
    vault.audit("IGNORE-EDIT", p["path"], client="web-ui")
    return JSONResponse({"ok": True})


async def mapping_log(request: Request) -> JSONResponse:
    logs = sorted(NIGHTLY_LOG_DIR.glob("nightly-*.log"))
    if not logs:
        return JSONResponse({"lines": [], "file": None})
    lines = logs[-1].read_text().splitlines()[-120:]
    return JSONResponse({"lines": lines, "file": logs[-1].name})
