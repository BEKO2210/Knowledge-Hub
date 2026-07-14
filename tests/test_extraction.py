"""Tests für extraction.py — inkrementeller Standard-Extraktor des Hubs.

Das LLM wird durch einen zählenden Fake ersetzt: geprüft wird vor allem die
Inkrementalität (unveränderte Dateien kosten keinen Aufruf), der Umgang mit
gelöschten/kaputten Dateien und die Schema-Kompatibilität der graph.json.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

import extraction


class ZaehlenderFake:
    """Gibt pro Datei eine Entity zurück und zählt die Aufrufe."""

    def __init__(self):
        self.calls = 0

    def __call__(self, backend, model, key, system, user, limit=900):
        self.calls += 1
        rel = user.split("\n", 1)[0].replace("Datei: ", "")
        return json.dumps(
            {
                "entities": [
                    {"label": f"Konzept {rel}", "type": "concept", "rationale": f"fakt aus {rel}: port 4242"}
                ],
                "relations": [],
            }
        )


@pytest.fixture()
def projekt(tmp_path):
    (tmp_path / "app.py").write_text("print('hallo')")
    (tmp_path / "docker-compose.yml").write_text("services:\n  web:\n    ports: ['4242:80']\n")
    return tmp_path


def test_erste_extraktion_ruft_llm_pro_datei(projekt):
    fake = ZaehlenderFake()
    stats = extraction.extract_project(projekt, ask=fake)
    assert fake.calls == 2
    assert stats["changed"] == 2
    g = json.loads((projekt / "graphify-out" / "graph.json").read_text())
    assert any("4242" in (n.get("rationale") or "") for n in g["nodes"])
    # Schema-Kompatibilität: Felder, auf die Hub/Viewer/anreichern bauen
    n = next(x for x in g["nodes"] if x.get("rationale"))
    for feld in ("id", "label", "norm_label", "source_file"):
        assert feld in n
    assert "links" in g and "nodes" in g


def test_zweiter_lauf_ohne_aenderung_kostet_nichts(projekt):
    fake = ZaehlenderFake()
    extraction.extract_project(projekt, ask=fake)
    vorher = fake.calls
    stats = extraction.extract_project(projekt, ask=fake)
    assert fake.calls == vorher  # kein einziger neuer LLM-Aufruf
    assert stats["changed"] == 0


def test_nur_geaenderte_datei_wird_neu_extrahiert(projekt):
    fake = ZaehlenderFake()
    extraction.extract_project(projekt, ask=fake)
    (projekt / "app.py").write_text("print('neu')")
    stats = extraction.extract_project(projekt, ask=fake)
    assert stats["changed"] == 1
    assert fake.calls == 3  # 2 initial + 1 für die Änderung


def test_geloeschte_datei_verschwindet_aus_dem_graphen(projekt):
    fake = ZaehlenderFake()
    extraction.extract_project(projekt, ask=fake)
    (projekt / "app.py").unlink()
    extraction.extract_project(projekt, ask=fake)
    g = json.loads((projekt / "graphify-out" / "graph.json").read_text())
    assert not any("app.py" in str(n.get("source_file")) for n in g["nodes"])


def test_kaputte_llm_antwort_verliert_kein_altes_wissen(projekt):
    fake = ZaehlenderFake()
    extraction.extract_project(projekt, ask=fake)

    def kaputt(*a):
        raise RuntimeError("API down")

    (projekt / "app.py").write_text("print('geaendert')")
    stats = extraction.extract_project(projekt, ask=kaputt)
    assert stats["changed"] == 0
    g = json.loads((projekt / "graphify-out" / "graph.json").read_text())
    # der alte app.py-Stand ist noch da
    assert any("app.py" in str(n.get("source_file")) for n in g["nodes"])


def test_kaputter_cache_fuehrt_zu_vollaufbau(projekt):
    fake = ZaehlenderFake()
    extraction.extract_project(projekt, ask=fake)
    (projekt / "graphify-out" / extraction.CACHE_NAME).write_text("kein json")
    stats = extraction.extract_project(projekt, ask=fake)
    assert stats["changed"] == 2  # alles neu, aber ohne Absturz
