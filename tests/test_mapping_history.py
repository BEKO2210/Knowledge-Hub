"""Post-Run-40 Bug 1: Mapping-Verlauf — maschinenlesbare Läufe + robuster Alt-Parser.

Abgedeckt (Auftrags-Testkategorien 1-3): vollständige Läufe, Teilfehler, abgebrochene
und beschädigte Läufe/Logs — für die neue runlog-Quelle UND das Alt-Log-Parsing in
beiden Formaten (vor/nach dem Pipeline-Umbau aus Run 7/8).
"""

from __future__ import annotations

import json

from conftest import TMP

import runlog
from api import mapping

LOGDIR = TMP / "build-logs"
RUNSDIR = LOGDIR / "runs"


import pytest


@pytest.fixture(autouse=True)
def _saubere_laufdaten():
    def _clean():
        if RUNSDIR.exists():
            for f in RUNSDIR.glob("*.json"):
                f.unlink()
        LOGDIR.mkdir(exist_ok=True)
        for f in LOGDIR.glob("nightly-*.log"):
            f.unlink()

    _clean()
    yield
    _clean()  # nachfolgende Testdateien erben keinen Zustand


def _projekt(name: str, nodes: int = 10, edges: int = 20, comms: int = 3) -> str:
    p = TMP / "src" / name
    out = p / "graphify-out"
    out.mkdir(parents=True, exist_ok=True)
    (out / "build-manifest.json").write_text(
        json.dumps(
            {"build_id": f"g-test-{name}", "counts": {"nodes": nodes, "edges": edges, "communities": comms}}
        )
    )
    return str(p)


def test_erfolgreicher_lauf_zeigt_alle_projektdaten():
    rid = runlog.start("nightly", "openai", "gpt-4.1")
    runlog.project(rid, _projekt("alpha", 11, 22, 3), "success")
    runlog.project(rid, _projekt("beta", 44, 55, 6), "success")
    runlog.finish(rid)

    runs = mapping._load_run_files()
    assert len(runs) == 1
    r = runs[0]
    assert r["status"] == "success" and not r["aborted"]
    assert r["project_count"] == 2 and r["failed"] == 0
    assert r["duration_s"] is not None
    a = next(p for p in r["projects"] if p["name"] == "alpha")
    assert (a["nodes"], a["edges"], a["communities"], a["build_id"]) == (11, 22, 3, "g-test-alpha")


def test_teilfehler_zerstoert_die_anderen_projekte_nicht():
    rid = runlog.start("nightly")
    runlog.project(rid, _projekt("gut", 7, 8, 1), "success")
    runlog.project(rid, str(TMP / "src" / "kaputt"), "failed", "extract fehlgeschlagen")
    runlog.finish(rid)

    r = mapping._load_run_files()[0]
    assert r["status"] == "partial" and r["failed"] == 1
    gut = next(p for p in r["projects"] if p["name"] == "gut")
    assert gut["nodes"] == 7, "erfolgreiches Projekt muss seine Zahlen behalten"
    kaputt = next(p for p in r["projects"] if p["name"] == "kaputt")
    assert kaputt["status"] == "failed" and "fehlgeschlagen" in kaputt["error"]


def test_abgebrochener_lauf_ist_sichtbar_und_kippt_nichts():
    rid = runlog.start("mcp")
    runlog.project(rid, _projekt("halb", 5, 5, 1), "success")
    # kein finish -> abgebrochen
    r = mapping._load_run_files()[0]
    assert r["aborted"] is True and r["status"] == "running"
    assert r["projects"][0]["nodes"] == 5


def test_kaputte_run_datei_kippt_die_historie_nicht():
    rid = runlog.start("nightly")
    runlog.project(rid, _projekt("ok", 3, 3, 1), "success")
    runlog.finish(rid)
    RUNSDIR.mkdir(parents=True, exist_ok=True)
    (RUNSDIR / "run-19990101T000000Z.json").write_text('{"halb": ')  # beschädigt
    runs = mapping._load_run_files()
    assert len(runs) == 1 and runs[0]["projects"][0]["name"] == "ok"


def test_delta_nodes_gegen_vorherigen_lauf():
    r1 = runlog.start("nightly")
    runlog.project(r1, _projekt("delta", 100, 1, 1), "success")
    runlog.finish(r1)
    r2 = runlog.start("nightly")
    runlog.project(r2, _projekt("delta", 130, 1, 1), "success")
    runlog.finish(r2)
    # r1 und r2 können in derselben Sekunde starten — der zweite Lauf ist der mit Delta.
    deltas = [p["delta"] for r in mapping._load_run_files() for p in r["projects"]]
    assert 30 in deltas


def test_altlog_neues_pipelineformat_liefert_zahlen():
    """Repro Bug 1: Läufe nach dem Umbau haben nur noch die Abnahme-Zeile."""
    (LOGDIR / "nightly-2026-01-01.log").write_text(
        "=== nightly-map start 2026-01-01T03:00:00+00:00 backend=openai model=gpt-4.1 ===\n"
        "--- /home/x/alpha (2026-01-01T03:00:01+00:00)\n"
        "[hub-extract] alpha: 5 Dateien, 0 neu extrahiert\n"
        "Generation abgenommen: g-20260101T030002Z-abc12345 ({'nodes': 620, 'edges': 1041, 'communities': 100})\n"
        "SYNC project=alpha local=succeeded remote=succeeded detail=pushed\n"
        "=== nightly-map done 2026-01-01T03:05:00+00:00 ===\n"
    )
    r = mapping._parse_runs()[-1]
    p = r["projects"][0]
    assert (p["nodes"], p["edges"], p.get("communities"), p.get("build_id")) == (
        620,
        1041,
        100,
        "g-20260101T030002Z-abc12345",
    )
    assert r["nodes_total"] == 620 and r["duration_s"] == 300


def test_altlog_altes_format_bleibt_lesbar():
    (LOGDIR / "nightly-2025-12-01.log").write_text(
        "=== nightly-map start 2025-12-01T03:00:00+00:00 model=gpt-4.1 ===\n"
        "--- /home/x/beta (2025-12-01T03:00:01+00:00)\n"
        "wrote /x/graphify-out/graph.json: 42 nodes, 77 edges\n"
        "=== nightly-map done 2025-12-01T03:04:00+00:00 ===\n"
    )
    r = mapping._parse_runs()[-1]
    assert r["projects"][0]["nodes"] == 42 and r["projects"][0]["edges"] == 77


def test_abgeschnittenes_log_ohne_done_zerstoert_nichts():
    (LOGDIR / "nightly-2026-01-02.log").write_text(
        "=== nightly-map start 2026-01-02T03:00:00+00:00 model=m ===\n--- /home/x/gamma (2026-01-02T03:00:01+00:00)\nGeneration abgen"  # hart abgeschnitten
    )
    runs = mapping._parse_runs()
    assert runs[-1]["projects"][0]["name"] == "gamma"
    assert runs[-1]["duration_s"] is None


def test_merge_dedupliziert_log_und_datei_und_uebernimmt_kosten():
    rid = runlog.start("nightly", "openai", "gpt-4.1")
    start_iso = json.loads((RUNSDIR / f"{rid}.json").read_text())["started_at"]
    runlog.project(rid, _projekt("merge", 9, 9, 1), "success")
    runlog.finish(rid)
    (LOGDIR / "nightly-2026-01-03.log").write_text(
        f"=== nightly-map start {start_iso} backend=openai model=gpt-4.1 ===\n"
        f"--- /home/x/merge ({start_iso})\n"
        "est. cost so far: $0.42\n"
        "tokens: 1,000 in / 2,000 out\n"
        f"=== nightly-map done {start_iso} ===\n"
    )
    merged = mapping._merge_runs()
    treffer = [r for r in merged if any(p["name"] == "merge" for p in r["projects"])]
    assert len(treffer) == 1, "Log- und Datei-Lauf müssen zu EINEM Lauf verschmelzen"
    assert treffer[0]["projects"][0]["nodes"] == 9, "Datei (validierte Zahlen) gewinnt"
    assert treffer[0]["cost"] == 0.42 and treffer[0]["tokens_out"] == 2000, "Kosten kommen aus dem Log"
