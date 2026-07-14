"""Tests für extraction.py — inkrementeller Standard-Extraktor des Hubs.

Das LLM wird durch einen zählenden Fake ersetzt: geprüft wird vor allem die
Inkrementalität (unveränderte Dateien kosten keinen Aufruf), der Umgang mit
gelöschten/kaputten Dateien und die Schema-Kompatibilität der graph.json.
"""

from __future__ import annotations

import json

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


def test_dateiknoten_kollidieren_nicht_mit_gleichnamigen_entitaeten():
    """graphifys Fuzzy-Dedup verschmolz Datei-Knoten (engine_py) mit ähnlichen Entitäten
    und VERWEIGERTE dann das Schreiben der geclusterten graph.json — Ergebnis waren
    Graphen ohne Communities neben Reports einer anderen Generation (asto-finance,
    hub-audit Run 10). Datei-Knoten tragen deshalb einen eigenen ID-Namensraum."""
    cache = {
        "engine.py": {
            "hash": "x",
            "entities": [{"label": "engine", "rationale": "Rechenkern", "type": "module"}],
            "relations": [{"source": "engine", "target": "engine.py"}],
        }
    }
    g = extraction.build_graph(cache)
    ids = {n["id"] for n in g["nodes"]}
    datei = [n for n in g["nodes"] if n["file_type"] == "file"]
    assert len(g["nodes"]) == 2, ids
    assert len(datei) == 1
    assert datei[0]["id"].startswith("file__"), datei[0]["id"]
    assert datei[0]["label"] == "engine.py"  # Label bleibt der reine Pfad
    # Kanten müssen den neuen Datei-Namensraum benutzen
    kanten = {(e["source"], e["target"]) for e in g["links"]}
    assert ("engine", datei[0]["id"]) in kanten, kanten


def test_vendor_und_testartefakte_werden_nicht_extrahiert(tmp_path, monkeypatch):
    """Elementa wurde von test-results/-JSONs und Minified-Code gemappt (hub-audit Run 11).
    Die eingebaute Skip-Liste muss die Auftrag-Kapitel-3.4-Muster abdecken."""
    projekt = tmp_path / "p"
    for rel in (
        "test-results/e2e.json",
        "playwright-report/index.html",
        "third_party/lib.py",
        "public/vendor/babel.min.js",
        "app/bundle.map",
        "echt/code.py",
    ):
        f = projekt / rel
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_text("x = 1\n")
    gefunden = {str(f.relative_to(projekt)) for f in extraction.iter_files(projekt)}
    assert gefunden == {"echt/code.py"}, gefunden


def test_graphifyignore_wirkt_auch_auf_die_eigene_extraktion(tmp_path):
    """Die UI schreibt .graphifyignore — bisher las nur graphify sie, extraction.py nicht.
    Ein in der UI ignoriertes Muster darf NICHT mehr extrahiert werden."""
    projekt = tmp_path / "p"
    (projekt / "geheim").mkdir(parents=True)
    (projekt / "geheim" / "notizen.md").write_text("privat")
    (projekt / "app.py").write_text("x = 1")
    (projekt / "gen.g.ts").write_text("// generiert")
    (projekt / ".graphifyignore").write_text("geheim/\n*.g.ts\n")
    gefunden = {str(f.relative_to(projekt)) for f in extraction.iter_files(projekt)}
    assert gefunden == {"app.py"}, gefunden


def test_ignorierte_datei_hinterlaesst_keinen_geisterknoten(projekt):
    """Eine Datei, die nachträglich ignoriert wird, verschwindet beim nächsten Lauf
    aus Cache UND Graph (Invariante aus GESAMTAUFTRAG Kap. 7)."""
    fake = ZaehlenderFake()
    extraction.extract_project(projekt, ask=fake)
    g = json.loads((projekt / "graphify-out" / "graph.json").read_text())
    assert any("app.py" in str(n.get("source_file")) for n in g["nodes"])
    (projekt / ".graphifyignore").write_text("app.py\n")
    extraction.extract_project(projekt, ask=fake)
    g = json.loads((projekt / "graphify-out" / "graph.json").read_text())
    assert not any("app.py" in str(n.get("source_file")) for n in g["nodes"]), (
        "ignorierte Datei darf keinen Geisterknoten hinterlassen"
    )


def test_laufzeitzustand_wird_nicht_als_architektur_gemappt(tmp_path):
    """Der Hub-Graph enthielt 28% Laufzeitdaten: answers/-Antwortcache anderer Projekte,
    oauth_state.json (Session-/Client-Zustand!), ratelimit.json (hub-audit Run 12).
    Veränderlicher Zustand ist kein Architekturwissen — und gehört schon gar nicht
    in das synchronisierte Wissens-Repo."""
    projekt = tmp_path / "hub"
    for rel in (
        "answers/foldpage/query-abc.json",
        "chunk-index/elementa.npz.json",
        "oauth_state.json",
        "ratelimit.json",
        "mapping_dismissed.json",
        "audit.log",
        "errors.log",
        "server.py",
        "config.example.yaml",
    ):
        f = projekt / rel
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_text("{}")
    gefunden = {str(f.relative_to(projekt)) for f in extraction.iter_files(projekt)}
    assert gefunden == {"server.py", "config.example.yaml"}, gefunden
