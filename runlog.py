"""Maschinenlesbares Lauf-Protokoll für alle Mapping-Wege (Post-Run-40, Bug 1).

Der Mapping-Verlauf hing an Regexen über freie Logtexte — als die Pipeline in Run 7/8
ihr Ausgabeformat änderte, verschwanden Knotenzahlen und Projektdaten aus der Ansicht.
Dieses Modul beendet die Abhängigkeit: Jeder Lauf (Nachtlauf, UI-Start, MCP-graph_build)
schreibt eine JSON-Datei `build-logs/runs/run-<start>.json` mit dem verbindlichen Schema:

    {
      "run_id": "run-20260716T033851Z", "kind": "nightly", "backend": "openai",
      "model": "gpt-4.1", "started_at": "...", "finished_at": "...",
      "duration_seconds": 0, "status": "success|partial|failed|running",
      "projects": [ {"name": ..., "status": "success|failed|skipped",
                     "nodes": 0, "edges": 0, "communities": 0,
                     "delta_nodes": null, "build_id": "g-...", "error": ""} ]
    }

Die Zahlen stammen aus dem validierten build-manifest.json der abgenommenen Generation
(buildmeta, Run 7) — nicht aus Logtext. Ein fehlgeschlagenes Projekt hält nur seinen
eigenen Eintrag auf `failed`; alle anderen bleiben vollständig. Ein Lauf ohne
`finished_at` gilt als abgebrochen und zerstört die Historie nicht.

Die Datei wird bei jedem Schritt atomar (tmp+rename) fortgeschrieben, damit auch ein
hart abgebrochener Lauf einen lesbaren Stand hinterlässt.

CLI (für nightly-map.sh):
    runlog.py start <kind> [backend] [model]        -> druckt run_id
    runlog.py project <run_id> <projektpfad> <status> [fehlertext]
    runlog.py finish <run_id>
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
import time
from pathlib import Path

DATA_DIR = Path(os.environ.get("KMCP_DATA_DIR", str(Path(__file__).resolve().parent)))
RUNS_DIR = DATA_DIR / "build-logs" / "runs"

# Log-Rotation / Lesedeckel (CE-10): Eine Datei je Nachtlauf + je UI-/MCP-Build wuchse
# unbegrenzt, und jede Verlaufsauswertung las irgendwann ALLE Dateien. Es bleiben die
# jüngsten MAX_RUN_DATEIEN Dateien liegen (älteste werden gelöscht); der Verlauf liest
# höchstens die neuesten VERLAUF_LESE_LIMIT — beides deckelt Platte und Leseaufwand.
MAX_RUN_DATEIEN = 200
VERLAUF_LESE_LIMIT = 100


def _now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%S+00:00", time.gmtime())


def _pfad(run_id: str) -> Path:
    return RUNS_DIR / f"{run_id}.json"


def _lade(run_id: str) -> dict | None:
    try:
        return json.loads(_pfad(run_id).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def _schreibe(doc: dict) -> None:
    RUNS_DIR.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=RUNS_DIR)
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        json.dump(doc, f, indent=1, ensure_ascii=False)
    os.replace(tmp, _pfad(doc["run_id"]))
    _rotiere()


def _rotiere() -> None:
    """Älteste Lauf-Dateien entfernen, sobald mehr als MAX_RUN_DATEIEN liegen.

    run-<zeitstempel>.json sortiert lexikalisch = chronologisch (Kollisions-Suffixe
    stehen direkt hinter ihrem Lauf — für die Rotation gleichwertig). Fehler beim
    Löschen einzelner Dateien dürfen den Lauf selbst nie kippen.
    """
    try:
        dateien = sorted(RUNS_DIR.glob("run-*.json"))
    except OSError:
        return
    ueberzaehlig = len(dateien) - MAX_RUN_DATEIEN
    if ueberzaehlig <= 0:
        return
    for alt in dateien[:ueberzaehlig]:
        try:
            alt.unlink()
        except OSError:
            pass


def start(kind: str, backend: str = "", model: str = "") -> str:
    stamp = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())
    run_id = f"run-{stamp}"
    # Kollision (zwei Starts in derselben Sekunde): eindeutig machen statt überschreiben.
    n = 1
    while _pfad(run_id).exists():
        n += 1
        run_id = f"run-{stamp}-{n}"
    _schreibe(
        {
            "schema_version": "1.0",
            "run_id": run_id,
            "kind": kind,
            "backend": backend,
            "model": model,
            "started_at": _now(),
            "finished_at": None,
            "duration_seconds": None,
            "status": "running",
            "projects": [],
        }
    )
    return run_id


def project(run_id: str, project_path: str, status: str, error: str = "") -> None:
    """Projekt-Ergebnis anhängen. Bei success kommen die Zahlen aus dem Build-Manifest."""
    doc = _lade(run_id)
    if doc is None:
        return
    name = Path(project_path).name
    eintrag: dict = {
        "name": name,
        "status": status,
        "nodes": None,
        "edges": None,
        "communities": None,
        "delta_nodes": None,
        "build_id": None,
        "error": error[:300],
    }
    if status == "success":
        try:
            mf = json.loads(
                (Path(project_path) / "graphify-out" / "build-manifest.json").read_text(encoding="utf-8")
            )
            counts = mf.get("counts", {})
            eintrag.update(
                nodes=counts.get("nodes"),
                edges=counts.get("edges"),
                communities=counts.get("communities"),
                build_id=mf.get("build_id"),
            )
        except (OSError, ValueError):
            eintrag["error"] = "Manifest nicht lesbar — Zahlen fehlen"
    # delta_nodes gegenüber dem letzten bekannten Stand desselben Projekts
    prev = _letzter_stand(name, ausser=run_id)
    if prev is not None and eintrag["nodes"] is not None:
        eintrag["delta_nodes"] = eintrag["nodes"] - prev
    doc["projects"] = [p for p in doc["projects"] if p.get("name") != name] + [eintrag]
    _schreibe(doc)


def _letzter_stand(name: str, ausser: str) -> int | None:
    """Knotenzahl des Projekts aus dem jüngsten früheren Lauf (für delta_nodes)."""
    try:
        dateien = sorted(RUNS_DIR.glob("run-*.json"), reverse=True)
    except OSError:
        return None
    for f in dateien[:VERLAUF_LESE_LIMIT]:  # gedeckelt: nie ALLE Dateien lesen (Rotation s. _rotiere)
        if f.stem == ausser:
            continue
        try:
            doc = json.loads(f.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        for p in doc.get("projects", []):
            if p.get("name") == name and p.get("nodes") is not None:
                return p["nodes"]
    return None


def finish(run_id: str) -> None:
    doc = _lade(run_id)
    if doc is None:
        return
    doc["finished_at"] = _now()
    try:
        t0 = time.mktime(time.strptime(doc["started_at"][:19], "%Y-%m-%dT%H:%M:%S"))
        t1 = time.mktime(time.strptime(doc["finished_at"][:19], "%Y-%m-%dT%H:%M:%S"))
        doc["duration_seconds"] = max(0, int(t1 - t0))
    except (ValueError, KeyError):
        doc["duration_seconds"] = None
    stati = [p["status"] for p in doc["projects"]]
    if not stati or all(s == "success" for s in stati):
        doc["status"] = "success"
    elif any(s == "success" for s in stati):
        doc["status"] = "partial"
    else:
        doc["status"] = "failed"
    _schreibe(doc)


def main(argv: list[str]) -> int:
    if len(argv) >= 2 and argv[0] == "start":
        print(start(argv[1], argv[2] if len(argv) > 2 else "", argv[3] if len(argv) > 3 else ""))
        return 0
    if len(argv) >= 4 and argv[0] == "project":
        project(argv[1], argv[2], argv[3], argv[4] if len(argv) > 4 else "")
        return 0
    if len(argv) >= 2 and argv[0] == "finish":
        finish(argv[1])
        return 0
    print(
        "Aufruf: runlog.py start <kind> [backend] [model] | project <run_id> <pfad> <status> [fehler] | finish <run_id>",
        file=sys.stderr,
    )
    return 64


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
