"""Notizen aus dem Chat: speichern, auflisten, Projekt anlegen — und nichts bricht aus."""

from __future__ import annotations

import pytest
from conftest import TMP

import config
import server


@pytest.fixture(autouse=True)
def konfiguration_aufraeumen():
    """Notiz-Tests registrieren Projekte in der geteilten Test-Konfiguration.

    Ohne Aufräumen sieht jeder spätere Test diese Projekte — der Sprach-Wachhund
    fand so „über-belkis" im Mapping-Tab und schlug Alarm. Tests dürfen einander
    nicht beeinflussen.
    """
    vorher = config.project_entries()
    yield
    config.save_projects(vorher)


def test_notiz_wird_gespeichert_und_projekt_registriert(fresh_vault):
    f, neu = server._write_note("Über Belkis", "Wer ich bin", "Ich baue einen Hub.", ["profil"])
    assert f.exists()
    assert f.parent.name == "über-belkis"  # umlautfest verschlagwortet
    inhalt = f.read_text()
    assert "# Wer ich bin" in inhalt
    assert "Ich baue einen Hub." in inhalt
    assert "profil" in inhalt
    assert neu is True, "Das Projekt muss fürs Nacht-Mapping registriert werden"
    pfade = [e["path"] for e in config.project_entries()]
    assert any("über-belkis" in p for p in pfade)


def test_zweite_notiz_registriert_nicht_doppelt(fresh_vault):
    server._write_note("thema", "Eins", "a", None)
    _, neu = server._write_note("thema", "Zwei", "b", None)
    assert neu is False
    pfade = [e["path"] for e in config.project_entries()]
    assert sum("thema" in p for p in pfade) == 1


def test_gleicher_titel_am_selben_tag_ueberschreibt_nicht(fresh_vault):
    f1, _ = server._write_note("thema", "Idee", "erste Fassung", None)
    f2, _ = server._write_note("thema", "Idee", "zweite Fassung", None)
    assert f1 != f2, "Eine Notiz darf eine andere niemals stillschweigend überschreiben"
    assert "erste Fassung" in f1.read_text()
    assert "zweite Fassung" in f2.read_text()


def test_projektname_kann_nicht_ausbrechen(fresh_vault):
    """'../' im Namen darf nicht aus dem Notiz-Ordner herausführen."""
    f, _ = server._write_note("../../etc", "x", "y", None)
    assert f.resolve().is_relative_to(server.NOTES_ROOT)


def test_notiz_liste(fresh_vault):
    server._write_note("liste", "Alpha", "a", None)
    server._write_note("liste", "Beta", "b", None)
    namen = server.note_list("liste")
    assert len(namen) == 2
    assert all(n.endswith(".md") for n in namen)


def test_leerer_projektname_wird_abgelehnt(fresh_vault):
    with pytest.raises(ValueError):
        server.project_create("###", "")


def test_notizen_landen_im_wegwerf_verzeichnis(fresh_vault):
    """Die Suite darf niemals in das echte ~/knowledge-notes schreiben."""
    assert str(server.NOTES_ROOT).startswith(str(TMP))
