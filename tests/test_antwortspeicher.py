"""Antwort-Speicher: dieselbe Frage darf nicht zweimal Geld kosten — aber auch nie veralten."""

from __future__ import annotations

import json

import pytest

import api.knowledge as k
import llm


@pytest.fixture
def projekt(tmp_path, monkeypatch):
    """Ein Wegwerf-Projekt mit Graph, plus ein gefälschtes graphify."""
    wurzel = tmp_path / "wissen"
    (wurzel / "demo" / "graphify-out").mkdir(parents=True)
    (wurzel / "demo" / "graphify-out" / "graph.json").write_text(
        json.dumps({"nodes": [{"id": "a", "label": "vault.py", "community": 0}], "links": []})
    )
    monkeypatch.setattr(k, "KNOWLEDGE_ROOT", wurzel)
    monkeypatch.setattr(k, "ANTWORT_DIR", tmp_path / "answers")
    monkeypatch.setattr(k, "_ins_graph_gedaechtnis", lambda *a: None)   # kein echtes graphify
    return wurzel / "demo"


def test_zweite_erklaerung_kommt_aus_dem_speicher(projekt, monkeypatch):
    """Der Kern: Der KI-Aufruf darf beim zweiten Mal NICHT noch einmal passieren."""
    aufrufe = []

    def gefaelscht(*a, **kw):
        aufrufe.append(1)
        return "Das ist der Vault."

    monkeypatch.setattr(llm, "ask", gefaelscht)

    k._antwort_schreiben("demo", "explain", "vault.py", "gpt-5-mini",
                         {"text": "Das ist der Vault.", "source": "llm", "model": "gpt-5-mini"})
    treffer = k._antwort_lesen("demo", "explain", "vault.py", "gpt-5-mini")
    assert treffer is not None
    assert treffer["text"] == "Das ist der Vault."
    assert treffer["gespeichert"] > 0
    assert not aufrufe, "Ein Treffer im Speicher darf die KI gar nicht erst fragen"


def test_anderes_modell_ist_ein_anderer_eintrag(projekt):
    """Eine Antwort von gpt-5-mini gilt nicht als Antwort von gpt-4.1 — sonst wäre sie gelogen."""
    k._antwort_schreiben("demo", "explain", "vault.py", "gpt-5-mini", {"text": "A"})
    assert k._antwort_lesen("demo", "explain", "vault.py", "gpt-4.1-mini") is None


def test_neu_gemappter_graph_entwertet_alte_antworten(projekt):
    """Eine veraltete Erklärung ist schlimmer als gar keine.

    Der Speicher-Schlüssel enthält den Stand des Graphen. Wird neu gemappt, ist der
    alte Eintrag unerreichbar — er kann nicht mehr fälschlich ausgeliefert werden.
    """
    import os
    import time

    k._antwort_schreiben("demo", "explain", "vault.py", "m", {"text": "alt"})
    assert k._antwort_lesen("demo", "explain", "vault.py", "m")["text"] == "alt"

    # Neu mappen simulieren: graph.json bekommt einen neuen Zeitstempel
    g = projekt / "graphify-out" / "graph.json"
    neu = int(time.time()) + 500
    os.utime(g, (neu, neu))

    assert k._antwort_lesen("demo", "explain", "vault.py", "m") is None, \
        "Nach einem Neu-Mapping darf die alte Antwort nicht mehr ausgeliefert werden"


def test_kaputter_speicher_kostet_keine_antwort(projekt):
    """Ein unlesbarer Eintrag darf nicht die ganze Erklärung verhindern."""
    f = k._speicher_pfad("demo", "explain", "vault.py", "m")
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_text("{kaputt")
    assert k._antwort_lesen("demo", "explain", "vault.py", "m") is None   # kein Absturz


def test_gpt5_bekommt_den_richtigen_parameter():
    """Der Bug, der 'Erklären lassen' und den Fragen-Tab getötet hat.

    Die gpt-5-Familie lehnt `max_tokens` mit HTTP 400 ab und verlangt
    `max_completion_tokens`. Solange der Hub den alten Namen schickte, kam bei jeder
    Erklärung nur die Rohdaten-Notlösung zurück.
    """
    assert llm._NEUES_LIMIT.match("gpt-5-mini")
    assert llm._NEUES_LIMIT.match("gpt-5")
    assert llm._NEUES_LIMIT.match("o3-mini")
    assert not llm._NEUES_LIMIT.match("gpt-4.1-mini")

    koerper = json.loads(llm._openai_body("gpt-5-mini", "s", "u", "max_completion_tokens"))
    assert "max_completion_tokens" in koerper
    assert "max_tokens" not in koerper


def test_graph_stand_nutzt_nanosekunden():
    """Regression (#4): der Cache-Schlüssel nutzte int(st_mtime) (Sekunden) — zwei Graph-
    Generationen in derselben Sekunde bekamen denselben Schlüssel und lieferten eine alte
    Antwort. Jetzt st_mtime_ns (ganzzahlig, keine Sekunden-Trunkierung)."""
    import shutil

    from api import knowledge

    d = knowledge.KNOWLEDGE_ROOT / "nsproj" / "graphify-out"
    d.mkdir(parents=True, exist_ok=True)
    g = d / "graph.json"
    g.write_text('{"nodes": [], "links": []}')
    try:
        stand = knowledge._graph_stand("nsproj")
        assert stand == str(g.stat().st_mtime_ns)
        assert len(stand) >= 16, "Nanosekunden-Stempel, nicht auf Sekunden gekürzt"
    finally:
        shutil.rmtree(knowledge.KNOWLEDGE_ROOT / "nsproj", ignore_errors=True)
