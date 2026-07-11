"""Fehler-Robustheit: sauber antworten, nichts verraten, alles protokollieren."""

from __future__ import annotations

import json

import pytest

import ui
from api import system


def test_kaputtes_json_ist_ein_400_kein_absturz(client, auth, fresh_vault):
    """Vorher: nacktes „Internal Server Error" (500). Das ist ein Aufruferfehler."""
    r = client.post("/ui/api/secrets",
                    headers={**auth, "Content-Type": "application/json"},
                    content=b"kein-json")
    assert r.status_code == 400
    assert "JSON" in r.json()["error"]


def test_unbekannter_endpunkt_antwortet_als_json(client, auth, fresh_vault):
    r = client.get("/ui/api/gibtesnicht", headers=auth)
    assert r.status_code == 404
    assert "error" in r.json()


def test_unerwarteter_fehler_verraet_keine_interna(client, auth, fresh_vault, monkeypatch):
    """Der Traceback darf NIE beim Aufrufer landen — nur eine Referenznummer."""
    def kaputt(*a, **kw):
        raise RuntimeError("geheimer interner pfad /srv/private/secret")

    monkeypatch.setattr(system, "_backup_state", kaputt)
    r = client.get("/ui/api/backup", headers=auth)

    assert r.status_code == 500
    body = r.json()
    assert "ref" in body and len(body["ref"]) >= 4
    text = r.text
    assert "Traceback" not in text
    assert "geheimer interner pfad" not in text
    assert "/srv/private" not in text


def test_unerwarteter_fehler_landet_im_fehlerlog(client, auth, fresh_vault, monkeypatch):
    """Die Ursache muss auffindbar sein — sonst kann man sie nicht beheben."""
    ui.ERROR_LOG.unlink(missing_ok=True)

    def kaputt(*a, **kw):
        raise RuntimeError("testfehler-xyz")

    monkeypatch.setattr(system, "_backup_state", kaputt)
    ref = client.get("/ui/api/backup", headers=auth).json()["ref"]

    assert ui.ERROR_LOG.exists(), "Es muss ein Fehlerlog geben"
    eintraege = [json.loads(z) for z in ui.ERROR_LOG.read_text().splitlines() if z.strip()]
    treffer = [e for e in eintraege if e["ref"] == ref]
    assert treffer, "Der Vorfall muss unter seiner Referenznummer auffindbar sein"

    e = treffer[0]
    assert "testfehler-xyz" in e["fehler"]
    assert e["pfad"] == "/ui/api/backup"
    assert e["methode"] == "GET"
    assert "Traceback" in e["spur"]   # die Spur gehört ins Log — nur dorthin


def test_gesperrter_vault_gibt_423_statt_500(client, auth, monkeypatch):
    """Ein gesperrter Vault ist ein erwarteter Zustand, kein Serverfehler.

    423 ist das Signal, auf das die Oberfläche mit „bitte neu anmelden" reagiert.
    """
    import vault

    monkeypatch.setattr(vault, "secret_list",
                        lambda *a, **kw: (_ for _ in ()).throw(vault.VaultLocked("zu")))
    r = client.get("/ui/api/secrets", headers=auth)
    assert r.status_code == 423


@pytest.mark.parametrize("pfad", ["/ui/api/secrets", "/ui/api/mapping/config"])
def test_leerer_body_stuerzt_nicht_ab(client, auth, fresh_vault, pfad):
    r = client.post(pfad, headers={**auth, "Content-Type": "application/json"}, content=b"")
    assert r.status_code in (400, 422), f"{pfad} -> {r.status_code}"
