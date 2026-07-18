"""Nacht-Mapping: Zeitplan, Läufe, Projektverwaltung und Reparatur."""

from __future__ import annotations

import getpass
import json
import os
import re
import shutil
import subprocess
import threading
import time
from contextvars import copy_context
from pathlib import Path

from starlette.requests import Request
from starlette.responses import JSONResponse

import config
import vault
from api.common import DATA_DIR, GRAPHIFY_BIN, KNOWLEDGE_ROOT, json_object
from api.i18n import T

# ---------------------------------------------------------------------------
# Instanz-bewusster Nachtlauf-Unit: mehrere Hub-Instanzen (Haupt-Hub + hub2)
# teilen sich denselben Code, dürfen aber NICHT denselben systemd-Unit starten,
# sonst mappt eine Instanz die Projekte der anderen und überschreibt deren Timer.
# Der Unit-Basisname kommt aus der Umgebung; ohne Env bleibt es „nightly-map"
# (Haupt-Hub unverändert, rückwärtskompatibel). hub2 setzt KMCP_MAP_UNIT im
# Service auf „nightly-map-hub2".
_MAP_UNIT = os.environ.get("KMCP_MAP_UNIT", "nightly-map")
_MAP_SERVICE = f"{_MAP_UNIT}.service"
_MAP_TIMER = f"{_MAP_UNIT}.timer"
TIMER_FILE = Path.home() / ".config" / "systemd" / "user" / _MAP_TIMER
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
# Secrets gehören nie in den Graphen (zusätzlich zur harten Sperre in extraction.py)
.env
.env.*
*.env
*.key
*.pem
id_rsa*
*secret*
*credential*
!*.example
!*.sample
!*.template
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
    try:
        proc = subprocess.run(  # noqa: S603 - fixed binary, fixed unit names
            ["systemctl", "--user", *args], capture_output=True, text=True, timeout=15
        )
    except (FileNotFoundError, subprocess.TimeoutExpired):
        # Docker-Image ohne systemd: sauber degradieren statt als 500 zu sterben —
        # status zeigt dann „ausgeschaltet", toggle/run melden den Grund als Text.
        return 1, T("systemd nicht verfügbar (Container ohne systemctl)")
    return proc.returncode, (proc.stdout or proc.stderr).strip()


def _timer_time() -> str:
    if TIMER_FILE.exists():
        m = re.search(
            r"OnCalendar=\*-\*-\* (\d\d:\d\d)",
            TIMER_FILE.read_text(encoding="utf-8", errors="replace"),
        )
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
        # errors="replace": Tool-/LLM-Ausgaben mit Nicht-UTF-8-Bytes dürfen die
        # Kostenanzeige nicht dauerhaft als 500 lahmlegen (BE-07).
        text = f.read_text(encoding="utf-8", errors="replace")
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
# Seit dem Pipeline-Umbau (Run 7/8) steht die abgenommene Generation so im Log —
# ohne dieses Muster zeigten die letzten Läufe keine Knotenzahlen mehr (Bug 1):
_GEN_RE = re.compile(
    r"Generation abgenommen: (g-\S+) \(\{'nodes': (\d+), 'edges': (\d+), 'communities': (\d+)\}"
)
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
    # Die Oberfläche zeigt ohnehin nur die letzten 60 Läufe, und neue Läufe stehen
    # verbindlich in den run-*.json — die Textlogs (Alt-Bestand) werden deshalb
    # gedeckelt gelesen, statt über Jahre unbegrenzt mitzuwachsen (SEC-06).
    # errors="replace" wie bei _log_costs: kein 500 durch Nicht-UTF-8-Bytes.
    for f in sorted(NIGHTLY_LOG_DIR.glob("nightly-*.log"))[-120:]:
        lines = f.read_text(encoding="utf-8", errors="replace").splitlines()
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
            m = _GEN_RE.search(line)
            if m and cur["projects"]:
                cur["projects"][-1].update(
                    build_id=m.group(1),
                    nodes=int(m.group(2)),
                    edges=int(m.group(3)),
                    communities=int(m.group(4)),
                )
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


# Bewusst KEINE eingefrorene Konstante: der Pfad folgt NIGHTLY_LOG_DIR zur Laufzeit
# (Tests patchen das Verzeichnis; eine Import-Zeit-Kopie würde am Patch vorbeilesen).


def _epoch(iso: str) -> float:
    from datetime import datetime

    try:
        return datetime.fromisoformat(iso).timestamp()
    except (ValueError, TypeError):
        return 0.0


def _load_run_files() -> list[dict]:
    """Maschinenlesbare Lauf-Artefakte (runlog.py) im Format des Verlaufs.

    Das ist seit Post-Run-40 die verbindliche Quelle; das Log-Parsing bleibt nur für
    Läufe aus der Zeit davor. Kaputte oder halbe Dateien werden übersprungen — sie
    dürfen die Historie nie zerstören.
    """
    runs: list[dict] = []
    try:
        dateien = sorted((NIGHTLY_LOG_DIR / "runs").glob("run-*.json"))
    except OSError:
        return runs
    for f in dateien:
        try:
            doc = json.loads(f.read_text(encoding="utf-8"))
            projekte = [
                {
                    "name": p.get("name", "?"),
                    "nodes": p.get("nodes"),
                    "edges": p.get("edges"),
                    "communities": p.get("communities"),
                    "delta": p.get("delta_nodes"),
                    "build_id": p.get("build_id"),
                    "status": p.get("status", "success"),
                    "error": p.get("error", ""),
                }
                for p in doc.get("projects", [])
            ]
            fehl = [p for p in projekte if p["status"] == "failed"]
            nodes = [p["nodes"] for p in projekte if p["nodes"] is not None]
            deltas = [p["delta"] for p in projekte if p["delta"] is not None]
            runs.append(
                {
                    "start": doc.get("started_at", f.stem.removeprefix("run-")),
                    "backend": doc.get("backend", ""),
                    "model": doc.get("model", ""),
                    "kind": doc.get("kind", "nightly"),
                    "status": doc.get("status", "running"),
                    "aborted": doc.get("finished_at") is None,
                    "projects": projekte,
                    "failed_names": [p["name"] for p in fehl],
                    "failures": [{"project": p["name"], "kind": "extract"} for p in fehl],
                    "backup_failed": False,
                    "cost": 0.0,
                    "tokens_in": 0,
                    "tokens_out": 0,
                    "duration_s": doc.get("duration_seconds"),
                    "nodes_total": sum(nodes),
                    "node_delta": sum(deltas),
                    "project_count": len(projekte),
                    "failed": len(fehl),
                }
            )
        except Exception:  # noqa: BLE001 - eine kaputte Datei kippt die Historie nicht
            continue
    return runs


def _merge_runs() -> list[dict]:
    """Log-Läufe + Datei-Läufe chronologisch, ohne Doppelte.

    Neue Läufe stehen in BEIDEN Quellen (Textlog fürs Lesen, JSON als Vertrag).
    Ein Log-Lauf, dessen Start näher als 3 Minuten an einem Datei-Lauf liegt, ist
    derselbe Lauf — die Datei gewinnt (validierte Zahlen, Projektstatus). Kosten/
    Tokens kennt nur das Textlog; sie werden in den Datei-Lauf übernommen.
    """
    datei_runs = _load_run_files()
    log_runs = _parse_runs()
    datei_zeiten = [(_epoch(r["start"]), r) for r in datei_runs]
    ergebnis = list(datei_runs)
    for lr in log_runs:
        t = _epoch(lr["start"])
        partner = next((dr for dt, dr in datei_zeiten if abs(dt - t) < 180), None)
        if partner is None:
            ergebnis.append(lr)
        else:
            for feld in ("cost", "tokens_in", "tokens_out"):
                partner[feld] = lr.get(feld, 0) or partner.get(feld, 0)
            if lr.get("backup_failed"):
                partner["backup_failed"] = True
    ergebnis.sort(key=lambda r: _epoch(r["start"]))
    return ergebnis


async def mapping_history(request: Request) -> JSONResponse:
    """Verlauf aller Läufe (neueste zuerst) — für Tabelle + Kosten-Sparkline."""
    runs = _merge_runs()
    quittiert = _dismissed()
    for r in runs:
        r["dismissed"] = r["start"] in quittiert
    return JSONResponse({"runs": list(reversed(runs))[:60]})


async def mapping_dismiss(request: Request) -> JSONResponse:
    """Einen Lauf als erledigt abhaken (oder das Häkchen wieder entfernen)."""
    body = await json_object(request)
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
    _, enabled = _sysctl("is-enabled", _MAP_TIMER)
    _, active = _sysctl("is-active", _MAP_SERVICE)
    _, next_run = _sysctl("show", _MAP_TIMER, "--property=NextElapseUSecRealtime", "--value")
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
    body = await json_object(request)
    on = bool(body.get("enabled"))
    code, out = _sysctl("enable" if on else "disable", "--now", _MAP_TIMER)
    vault.audit("MAPPING-ON" if on else "MAPPING-OFF", _MAP_TIMER, client="web-ui")
    if code != 0:
        return JSONResponse({"error": out[:300]}, status_code=500)
    return JSONResponse({"ok": True, "enabled": on})


async def mapping_config(request: Request) -> JSONResponse:
    body = await json_object(request)
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
    _, enabled = _sysctl("is-enabled", _MAP_TIMER)
    if enabled == "enabled":
        _sysctl("restart", _MAP_TIMER)
    vault.audit("MAPPING-CONFIG", f"{t} {backend}/{model}", client="web-ui")
    return JSONResponse({"ok": True})


async def mapping_run(request: Request) -> JSONResponse:
    _, active = _sysctl("is-active", _MAP_SERVICE)
    if active in ("active", "activating"):
        return JSONResponse({"error": T("Läuft bereits")}, status_code=409)
    # Startzeit hinterlegen, damit der Fortschritt diesen Lauf als „manuell" erkennt.
    try:
        NIGHTLY_LOG_DIR.mkdir(parents=True, exist_ok=True)
        _MANUAL_MARKER.write_text(str(time.time()), encoding="utf-8")
    except Exception:  # noqa: BLE001 - Marker ist nur Komfort, nie den Start blockieren
        pass
    code, out = _sysctl("start", "--no-block", _MAP_SERVICE)
    vault.audit("MAPPING-RUN", "manuell gestartet", client="web-ui")
    if code != 0:
        return JSONResponse({"error": out[:300]}, status_code=500)
    return JSONResponse({"ok": True})


# --- Projekt-Verwaltung (Run 2) -------------------------------------------
# Verzeichnisse dürfen nur innerhalb dieser Wurzeln liegen — verhindert, dass
# über die UI beliebige Systempfade gescannt oder beschrieben werden.
BROWSE_ROOTS = [Path.home(), Path("/opt")]


def _safe_dir(raw: str) -> Path | None:
    if not raw.strip():
        # Leerer/blanker Pfad: Path("").resolve() ergäbe das Arbeitsverzeichnis des
        # Servers (das Release-Verzeichnis) und würde es so als „Projekt" registrieren.
        # Blank hier abfangen, damit ALLE Aufrufer geschützt sind (BE-safe-dir-blank).
        return None
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
    body = await json_object(request)
    p = _safe_dir(str(body.get("path", "")))
    if p is None:
        return JSONResponse(
            {"error": T("Kein gültiges Verzeichnis (erlaubt: Home und /opt)")}, status_code=400
        )
    entries = config.project_entries()
    if str(p) in {str(Path(e["path"]).expanduser()) for e in entries}:
        return JSONResponse({"error": T("Projekt ist bereits eingetragen")}, status_code=409)
    # Basenamen-Kollision: ~/a/tool und ~/b/tool werden per rsync --delete auf
    # denselben Hub-Ordner „tool" gemappt — stiller Datenverlust (BE-07).
    namenskonflikt = next(
        (e for e in entries if Path(e["path"]).expanduser().name.lower() == p.name.lower()),
        None,
    )
    if namenskonflikt is not None:
        return JSONResponse(
            {
                "error": T(
                    "Der Ordnername „{name}“ ist bereits für {path} eingetragen — gleiche Namen "
                    "würden sich im Hub gegenseitig überschreiben.",
                    name=p.name,
                    path=namenskonflikt["path"],
                )
            },
            status_code=409,
        )
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
    import locks

    try:
        # graphify-sync betritt das Wissens-Repo nur unter sync-repo.lock — der
        # Purge-Commit muss sich genauso anstellen, sonst verzahnen sich rsync
        # und git mitten im Lauf (CE-08). Scheitert die Sperre, wird der Commit
        # wie bisher still übersprungen (best effort, s. except unten).
        with locks.sync_lock(timeout=60):

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


def _purge_graph_data(project_dir: Path) -> tuple[list[str], list[str]]:
    """Löscht ALLE Graph-Artefakte eines Projekts: Hub-Kopie, lokales graphify-out,
    Antworten, Chunk-Index. Der Projektordner selbst (Quellcode, Notizen) bleibt.

    Jede Löschung ist best-effort: Was sich nicht entfernen lässt — etwa
    /opt/lumo/graphify-out, dessen Elternordner root gehört (belkis hat dort kein
    Schreibrecht) — landet in ``skipped`` und blockiert die restliche Bereinigung
    NICHT. So bleibt kein Projekt jemals „halb gelöscht" in der Mapping-Liste
    hängen, nur weil ein einzelner Ordner nicht entfernbar war.

    Rückgabe: (removed, skipped).
    """
    removed: list[str] = []
    skipped: list[str] = []
    name = project_dir.name.lower()
    if not name or name in RESERVED_GRAPH_DIRS:
        return removed, skipped

    def purge(path: Path, *, on_success=None) -> None:
        if path.is_symlink() or not path.is_dir():
            return
        try:
            shutil.rmtree(path)
        except OSError as exc:  # PermissionError, Verzeichnis in Benutzung, …
            skipped.append(f"{path}: {exc.strerror or exc}")
            return
        removed.append(str(path))
        if on_success is not None:
            on_success()

    # 1) Hub-Kopie im Wissens-Repo — das, was MCP-Tools und der Graphen-Tab servieren
    hub_copy = KNOWLEDGE_ROOT / name
    if hub_copy.is_dir() and hub_copy.resolve().parent == KNOWLEDGE_ROOT.resolve():
        purge(hub_copy, on_success=lambda: _git_purge_commit(name))

    # 2) Lokale Graph-Daten im Projektordner
    purge(project_dir / "graphify-out")

    # 3) Gespeicherte Antworten zu diesem Projekt
    purge(DATA_DIR / "answers" / name)

    # 4) Chunk-Index (semantische Datei-Auszüge) — lag bisher außerhalb der Kaskade
    import semantic

    purge(semantic.CHUNK_DIR / name)

    return removed, skipped


# --- Graph-Bestand: Registrierung ist die Quelle der Wahrheit (Post-Run-40, Bug 2) ----
# Jeder sichtbare Graph gehört zu genau einem registrierten Projekt (aktiv ODER
# archiviert). Was übrig bleibt, ist ein Waisen-Graph: Er wird nicht still angezeigt,
# sondern als zu klärender Bestand geführt — mit den Aktionen registrieren/archivieren/
# entfernen. Der Quellordner eines Projekts wird hier grundsätzlich NIE angefasst.


def _graph_dirs() -> list[str]:
    try:
        return sorted(
            d.name
            for d in KNOWLEDGE_ROOT.iterdir()
            if d.is_dir()
            and d.name not in RESERVED_GRAPH_DIRS
            and (d / "graphify-out" / "graph.json").exists()
        )
    except OSError:
        return []


def _graph_counts(name: str) -> dict:
    try:
        g = json.loads((KNOWLEDGE_ROOT / name / "graphify-out" / "graph.json").read_text(encoding="utf-8"))
        nodes = g.get("nodes", [])
        return {
            "nodes": len(nodes),
            "edges": len(g.get("links", g.get("edges", []))),
            "communities": len({n.get("community") for n in nodes if n.get("community") is not None}),
        }
    except (OSError, ValueError):
        return {"nodes": None, "edges": None, "communities": None}


def graph_inventory() -> dict:
    """Alle Hub-Graphen, eingeteilt in registriert / archiviert / unregistriert (Waisen)."""
    registriert = {Path(e["path"]).expanduser().name.lower() for e in config.project_entries()}
    archiviert = {a["name"]: a for a in config.archived_graphs()}
    inventar = {"registered": [], "archived": [], "unregistered": []}
    for name in _graph_dirs():
        info = {"name": name, **_graph_counts(name)}
        if name in registriert:
            inventar["registered"].append(info)
        elif name in archiviert:
            a = archiviert[name]
            inventar["archived"].append({**info, "origin": a["origin"], "archived_at": a["archived_at"]})
        else:
            mf = KNOWLEDGE_ROOT / name / "graphify-out" / "build-manifest.json"
            try:
                m = json.loads(mf.read_text(encoding="utf-8"))
                info["build_id"] = m.get("build_id")
                info["last_mapped"] = m.get("created_at")
            except (OSError, ValueError):
                info["build_id"] = info["last_mapped"] = None
            inventar["unregistered"].append(info)
    return inventar


async def mapping_graphs(request: Request) -> JSONResponse:
    return JSONResponse(graph_inventory())


def _purge_hub_graph(name: str) -> list[str]:
    """Hub-seitige Artefakte eines Graphen entfernen — niemals den Quellordner."""
    import semantic

    removed: list[str] = []
    if not name or name in RESERVED_GRAPH_DIRS:
        return removed
    hub_copy = KNOWLEDGE_ROOT / name
    if hub_copy.is_dir() and hub_copy.resolve().parent == KNOWLEDGE_ROOT.resolve():
        shutil.rmtree(hub_copy)
        removed.append(str(hub_copy))
        _git_purge_commit(name)
    for extra in (DATA_DIR / "answers" / name, semantic.CHUNK_DIR / name):
        if extra.is_dir():
            shutil.rmtree(extra)
            removed.append(str(extra))
    return removed


async def mapping_graph_action(request: Request) -> JSONResponse:
    """Waisen-/Archiv-Graphen verwalten: archivieren oder vollständig entfernen."""
    body = await json_object(request)
    name = str(body.get("name", "")).strip().lower()
    action = str(body.get("action", "")).strip()
    inventar = graph_inventory()
    unreg = {g["name"] for g in inventar["unregistered"]}
    arch = {g["name"] for g in inventar["archived"]}

    if action == "archive":
        if name not in unreg:
            return JSONResponse({"error": T("Kein unregistrierter Graph mit diesem Namen")}, status_code=404)
        origin = str(body.get("origin", "")).strip()[:300]
        if not origin:
            return JSONResponse(
                {"error": T("Herkunft (origin) ist Pflicht beim Archivieren")}, status_code=400
            )
        entries = config.archived_graphs()
        entries.append(
            {
                "name": name,
                "origin": origin,
                "archived_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            }
        )
        config.save_archived_graphs(entries)
        vault.audit("GRAPH-ARCHIVE", f"{name} ({origin[:80]})", client="web-ui")
        return JSONResponse({"ok": True})

    if action == "remove":
        if name not in unreg and name not in arch:
            return JSONResponse(
                {"error": T("Nur unregistrierte oder archivierte Graphen sind hier entfernbar")},
                status_code=404,
            )
        import locks

        try:
            with locks.project_lock(name, timeout=5):
                removed = _purge_hub_graph(name)
        except locks.LockedError:
            return JSONResponse(
                {"error": T("Graph wird gerade gebaut — bitte später erneut")}, status_code=409
            )
        config.save_archived_graphs([a for a in config.archived_graphs() if a["name"] != name])
        vault.audit("GRAPH-PURGE", name, client="web-ui")
        return JSONResponse({"ok": True, "removed": removed})

    return JSONResponse({"error": T("Unbekannte Aktion (archive|remove)")}, status_code=400)


async def mapping_project_update(request: Request) -> JSONResponse:
    """Toggle enabled oder Projekt entfernen (entfernen = Graph-Daten komplett löschen)."""
    body = await json_object(request)
    target = str(body.get("path", ""))
    action = str(body.get("action", ""))
    entries = config.project_entries()
    resolved = str(Path(target).expanduser())
    kept, found, purged, skipped = [], False, [], []
    for e in entries:
        if str(Path(e["path"]).expanduser()) == resolved:
            found = True
            if action == "remove":
                # Purge nimmt die Projekt-Sperre (Run 9): Löschen während ein Build läuft
                # würde halbe Artefakte hinterlassen bzw. der Build schriebe ins Nichts.
                import locks

                try:
                    with locks.project_lock(Path(e["path"]).name, timeout=5):
                        purged, skipped = _purge_graph_data(Path(e["path"]).expanduser())
                except locks.LockedError:
                    return JSONResponse(
                        {"error": T("Projekt wird gerade gebaut — bitte warten und erneut entfernen")},
                        status_code=409,
                    )
                continue
            if action == "toggle":
                e["enabled"] = not e["enabled"]
        kept.append(e)
    if not found:
        return JSONResponse({"error": T("Projekt nicht gefunden")}, status_code=404)
    config.save_projects(kept)
    vault.audit(f"PROJECT-{action.upper()}", target, client="web-ui")
    if action == "remove":
        detail = "; ".join(purged) or "keine Graph-Daten vorhanden"
        if skipped:
            detail += " | nicht löschbar: " + "; ".join(skipped)
        vault.audit("GRAPH-PURGE", detail, client="web-ui")
    return JSONResponse({"ok": True, "purged": purged, "skipped": skipped})


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


# Grobe Inhalts-Klassifikation (angelehnt an graphify/detect.py) — nur für
# verständliche Meldungen, nicht für die eigentliche Extraktion.
_CODE_SUFFIXES = {
    ".py",
    ".ts",
    ".tsx",
    ".js",
    ".jsx",
    ".mjs",
    ".go",
    ".rs",
    ".java",
    ".cpp",
    ".cc",
    ".c",
    ".h",
    ".hpp",
    ".rb",
    ".swift",
    ".kt",
    ".cs",
    ".scala",
    ".php",
    ".lua",
    ".ex",
    ".exs",
    ".jl",
    ".vue",
    ".svelte",
    ".astro",
    ".dart",
    ".sql",
    ".r",
    ".sh",
    ".bash",
    ".json",
    ".tf",
    ".zig",
}
_DOC_SUFFIXES = {".md", ".mdx", ".qmd", ".txt", ".rst", ".html", ".yaml", ".yml", ".pdf"}
_SKIP_DIRS = {
    ".git",
    "node_modules",
    "__pycache__",
    ".venv",
    "venv",
    ".next",
    "dist",
    "build",
    "graphify-out",
}


def _content_counts(p: Path) -> tuple[int, int]:
    """Zählt grob Code- und Dokumentdateien eines Projekts (code, docs)."""
    code = docs = 0
    for f in p.rglob("*"):
        if not f.is_file() or f.name.startswith("."):
            continue
        rel = f.relative_to(p).parts
        if any(part in _SKIP_DIRS or part.startswith(".") for part in rel[:-1]):
            continue
        s = f.suffix.lower()
        if s in _CODE_SUFFIXES:
            code += 1
        elif s in _DOC_SUFFIXES:
            docs += 1
    return code, docs


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
            label = backend.get("label", backend_name)
            code_n, doc_n = _content_counts(p)
            if code_n == 0:
                # Nur Dokumente/Notizen: Ohne Key würde ein Leerlauf folgen, der mit
                # „0 gefunden" endet und wie ein Defekt aussieht. Stattdessen ein
                # klarer Stopp mit Anleitung (kind=action → UI zeigt Hinweis statt Fehler).
                lines.append(T("Kein Fehler — es fehlt nur der KI-Schlüssel."))
                lines.append("")
                lines.append(
                    T(
                        "Dieses Projekt besteht aus Dokumenten und Notizen ({docs} Datei(en), kein Code). Ohne KI-Schlüssel kann der Hub daraus keinen Graphen bauen.",
                        docs=doc_n,
                    )
                )
                lines.append("")
                lines.append(T("So geht es weiter:"))
                lines.append(T("1. Tab „Mapping“ öffnen — dort steht die Karte „{label}-Key“.", label=label))
                lines.append(
                    T(
                        "2. Key einfügen und „Key speichern“ drücken. {hint}",
                        hint=backend.get("key_hint", ""),
                    ).rstrip()
                )
                lines.append(T("3. Danach hier „Erneut versuchen“ drücken — dann wird das Projekt gemappt."))
                _repairs[name] = {"status": "failed", "kind": "action", "log": "\n".join(lines)}
                return
            args.append("--code-only")
            lines.append(
                T(
                    "Hinweis: Kein {label}-Key hinterlegt — nur der Code wird gemappt, {docs} Dokument(e) bleiben außen vor. Key im Tab „Mapping“ speichern, dann fließen auch Dokumente ein.",
                    label=label,
                    docs=doc_n,
                )
            )

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
        proc2 = subprocess.run(
            [config.path(cfg["paths"]["graphify_sync"]), str(p)],  # noqa: S603
            capture_output=True,
            text=True,
            timeout=300,
        )
        if proc2.returncode != 0:
            # Ohne rc-Prüfung stand hier „erfolgreich", obwohl der Hub den Graphen
            # nie bekam (z. B. rc=75 Lock-Timeout beim Sync) — BE-07.
            lines += (proc2.stdout or proc2.stderr or "").strip().splitlines()[-8:]
            lines.append(T("Fehler bei der Reparatur: {msg}", msg=f"graphify-sync rc={proc2.returncode}"))
            _repairs[name] = {"status": "failed", "log": "\n".join(lines)}
            return
        lines.append(T("✓ Reparatur erfolgreich — Projekt ist wieder gemappt."))
        _repairs[name] = {"status": "done", "log": "\n".join(lines)}
    except Exception as e:  # noqa: BLE001
        lines.append(T("Fehler bei der Reparatur: {msg}", msg=e))
        _repairs[name] = {"status": "failed", "log": "\n".join(lines)}


async def project_repair(request: Request) -> JSONResponse:
    body = await json_object(request)
    target = str(body.get("path", ""))
    p = Path(target).expanduser()
    if str(p) not in _project_paths():
        return JSONResponse({"error": T("Projekt nicht konfiguriert")}, status_code=404)
    name = p.name
    if _repairs.get(name, {}).get("status") == "running":
        return JSONResponse({"error": T("Reparatur läuft bereits")}, status_code=409)
    _repairs[name] = {"status": "running", "log": T("Reparatur gestartet…")}
    vault.audit("PROJECT-REPAIR", target, client="web-ui")
    # Rohe Threads erben contextvars nicht von selbst — ohne copy_context wären
    # alle T()-Texte im Worker deutsch, auch wenn der Request englisch war (BE-05).
    threading.Thread(
        target=copy_context().run, args=(_repair_worker, name, p, config.load()), daemon=True
    ).start()
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
    body = await json_object(request)
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


def _read_tail(f: Path, max_bytes: int = 256 * 1024) -> str:
    """Nur das Dateiende lesen: Tages-Logs wachsen unbegrenzt — ein Voll-Read für
    die letzten 120 Zeilen blockiert die Event-Loop zunehmend (SEC-06)."""
    try:
        with f.open("rb") as fh:
            fh.seek(0, os.SEEK_END)
            fh.seek(max(0, fh.tell() - max_bytes))
            data = fh.read()
    except OSError:
        return ""
    return data.decode("utf-8", errors="replace")


# Manuell gestartete Läufe hinterlassen hier ihre Startzeit (epoch) — so kann der
# Fortschritt „manuell vs. automatisch (Timer)" unterscheiden, ohne das Nachtlauf-
# Skript anzufassen.
_MANUAL_MARKER = NIGHTLY_LOG_DIR / ".manual-trigger"


def _run_progress(log_path: Path) -> dict:
    """Fortschritt des jüngsten Nachtlaufs aus dem Log ableiten (Projekt X/Y + Schritt +
    Trigger). Rein lesend — verändert den laufenden Nachtlauf nicht."""
    prog = {"total": 0, "done": 0, "index": 0, "current": "", "step": "", "trigger": "", "backend": ""}
    try:
        lines = _read_tail(log_path).splitlines()
    except Exception:  # noqa: BLE001
        return prog
    start = None
    for i in range(len(lines) - 1, -1, -1):
        mt = _RUN_START_RE.search(lines[i])
        if mt:
            start, prog["backend"] = i, (mt.group(2) or "")
            started_iso = mt.group(1)
            break
    if start is None:
        return prog
    run = lines[start:]
    ended = any(_RUN_DONE_RE.search(x) for x in run)
    projekte = [m.group(1) for x in run if (m := _PROJ_LINE_RE.match(x)) and m.group(1).startswith("/")]
    synced = sum(1 for x in run if x.startswith("SYNC project="))
    try:
        total = len([p for p in config.load()["mapping"].get("projects", []) if p.get("enabled", True)])
    except Exception:  # noqa: BLE001
        total = 0
    prog["total"] = max(total, len(projekte))
    prog["index"] = len(projekte)
    prog["done"] = prog["total"] if ended else synced
    prog["current"] = projekte[-1].rstrip("/").split("/")[-1] if projekte else ""
    tail = " ".join(run[-8:]).lower()
    if ended:
        prog["step"] = "fertig"
    elif "sync project=" in tail:
        prog["step"] = "Synchronisieren"
    elif "cluster" in tail or "labeling" in tail:
        prog["step"] = "Clustering & Labeling"
    elif "hub-extract" in tail or "extrah" in tail:
        prog["step"] = "Extraktion (Claude Code)"
    else:
        prog["step"] = "läuft…"
    try:
        from datetime import datetime

        run_epoch = datetime.fromisoformat(started_iso).timestamp()
        if _MANUAL_MARKER.exists():
            mk = float(_MANUAL_MARKER.read_text().strip() or 0)
            prog["trigger"] = "manuell" if abs(mk - run_epoch) < 180 else "automatisch"
        else:
            prog["trigger"] = "automatisch"
    except Exception:  # noqa: BLE001
        prog["trigger"] = ""
    return prog


async def mapping_log(request: Request) -> JSONResponse:
    logs = sorted(NIGHTLY_LOG_DIR.glob("nightly-*.log"))
    if not logs:
        return JSONResponse({"lines": [], "file": None, "progress": {}})
    lines = _read_tail(logs[-1]).splitlines()[-120:]
    return JSONResponse({"lines": lines, "file": logs[-1].name, "progress": _run_progress(logs[-1])})
