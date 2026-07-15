"""Run-032: öffentlicher Datenvertrag — Schema, Leak-Scanner, sicherer Abbruch.

Der Generator darf NUR aggregierte, freigegebene Zahlen ausgeben. Diese Tests sichern die
Sicherheitsgrenze (PUBLIC_DATA_POLICY): kein Pfad/Projektname/Secret in der Ausgabe, kaputte
Quelle bricht sauber ab, Schema-Verstoß wird abgelehnt.
"""

from __future__ import annotations

import json

import pytest

import public_data as pd

GOOD_TESTS = {"total": 323, "passed": 323, "failed": 0}
GOOD_GRAPH = {"projects": 13, "nodes": 5734, "edges": 8207, "communities": 852}
GOOD_BENCH = {
    "measured_at": "2026-07-15",
    "questions": 41,
    "projects": 11,
    "budgets": [400, 1200],
    "engines": {
        "hybrid": {"hit_rate_400": 0.683, "hit_rate_1200": 0.854},
        "graphify": {"hit_rate_400": 0.561, "hit_rate_1200": 0.585},
    },
}
GOOD_AUDIT = {"runs_passed": 31, "open_critical": 0, "open_high": 1}


def test_build_valides_dokument():
    doc = pd.build(GOOD_TESTS, GOOD_GRAPH, GOOD_BENCH, GOOD_AUDIT, commit="4f462cd", now=1784000000)
    assert doc["schema_version"] == "1.0"
    assert doc["build_id"].startswith("pd-")
    assert doc["tests"]["passed"] == 323
    assert doc["benchmark"]["engines"]["hybrid"]["hit_rate_1200"] == 0.854
    assert doc["release"]["commit"] == "4f462cd"
    assert doc["stale_after_days"] >= 1


def test_ausgabe_enthaelt_keine_verbotenen_felder():
    doc = pd.build(GOOD_TESTS, GOOD_GRAPH, GOOD_BENCH, GOOD_AUDIT, now=1784000000)
    erlaubt = {
        "schema_version",
        "generated_at",
        "build_id",
        "stale_after_days",
        "tests",
        "graph",
        "benchmark",
        "audit",
        "release",
    }
    assert set(doc) <= erlaubt


@pytest.mark.parametrize(
    "gift",
    [
        "/home/belkis/knowledge-mcp/vault.enc",
        "tolga",  # nicht freigegebener Projektname
        "hub2",
        "VAULT_KEY=abc",
        "kmcp_supersecret_token",
        "192.168.0.1",
        "belkis.aslani@gmail.com",
        "a" * 40,  # voller Hash
        "recovery-code 4f2a",
    ],
)
def test_leak_scanner_faengt_verbotene_muster(gift):
    with pytest.raises(pd.PublicDataLeak):
        pd._leak_scan(f'{{"irgendwas": "{gift}"}}')


def test_leak_scanner_laesst_saubere_ausgabe_durch():
    doc = pd.build(GOOD_TESTS, GOOD_GRAPH, GOOD_BENCH, GOOD_AUDIT, commit="4f462cd", now=1784000000)
    pd._leak_scan(json.dumps(doc, ensure_ascii=False))  # darf NICHT werfen


def test_schema_lehnt_ungueltige_trefferquote_ab():
    bad = json.loads(json.dumps(GOOD_BENCH))
    bad["engines"]["hybrid"]["hit_rate_1200"] = 1.7  # > 1
    with pytest.raises(pd.PublicDataInvalid):
        pd.build(GOOD_TESTS, GOOD_GRAPH, bad, GOOD_AUDIT, now=1784000000)


def test_schema_lehnt_fremdes_feld_ab():
    bad = dict(GOOD_TESTS, geheim="intern")  # additionalProperties: false
    with pytest.raises(pd.PublicDataInvalid):
        pd.build(bad, GOOD_GRAPH, GOOD_BENCH, GOOD_AUDIT, now=1784000000)


def test_fehlende_quelle_bricht_sicher_ab(tmp_path):
    # kein einziger Graph -> PublicSourceError statt Nullwerte
    (tmp_path / "leer").mkdir()
    with pytest.raises(pd.PublicSourceError):
        pd.gather_graph(knowledge_root=tmp_path, projekte=["gibtsnicht"])
    with pytest.raises(pd.PublicSourceError):
        pd.gather_benchmark(bench_dir=tmp_path)  # keine results/


def test_write_erzeugt_json_und_manifest(tmp_path):
    doc = pd.build(GOOD_TESTS, GOOD_GRAPH, GOOD_BENCH, GOOD_AUDIT, commit="4f462cd", now=1784000000)
    out = pd.write(doc, tmp_path)
    assert out.is_file()
    geladen = json.loads(out.read_text())
    assert geladen == doc
    manifest = json.loads((tmp_path / "public-data.manifest.json").read_text())
    import hashlib

    assert manifest["sha256"] == hashlib.sha256(out.read_text().encode()).hexdigest()
    assert manifest["build_id"] == doc["build_id"]
