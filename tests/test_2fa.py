"""Zwei-Faktor-Aktivierung ist idempotent (Audit-Run 17, R17-1).

Ein Doppel-Absenden von „Aktivieren" (Doppelklick, Enter+Klick, zweites Gerät) darf die
gerade EINMALIG angezeigten Wiederherstellungscodes nicht durch einen neuen, nie gezeigten
Satz ersetzen. Vorher regenerierte jeder zweite enable()-Aufruf die Codes still — der Nutzer
hätte Codes gesichert, die schon nicht mehr galten, und sich bei Handyverlust ausgesperrt.
"""

from __future__ import annotations

import time

import totp


def _aktueller_code(secret: str) -> str:
    return totp._code_at(secret, int(time.time()) // totp.PERIOD)


def test_enable_regeneriert_recovery_nicht_beim_zweiten_aufruf(fresh_vault):
    d = totp.begin_setup("hub", "Test Hub")
    code = _aktueller_code(d["secret"])

    erst = totp.enable(code)
    assert erst and len(erst) == 8
    hashes_nach_erst = totp._load()["recovery"]

    # Zweiter Aufruf mit demselben, noch gültigen Code darf NICHTS neu erzeugen.
    noch = totp.enable(code)
    assert noch is None, "Ein zweites enable() darf keine neuen Codes liefern"
    assert totp._load()["recovery"] == hashes_nach_erst, "Die Recovery-Codes dürfen sich nicht ändern"


def test_twofa_enable_endpunkt_ist_bei_aktivem_2fa_409(client, auth, fresh_vault):
    d = totp.begin_setup("hub", "Test Hub")
    code = _aktueller_code(d["secret"])

    r1 = client.post("/ui/api/2fa/enable", headers=auth, json={"code": code})
    assert r1.status_code == 200
    assert len(r1.json()["recovery"]) == 8
    hashes1 = totp._load()["recovery"]

    # Sofortiges zweites Absenden (Doppelklick-Äquivalent) → 409, keine neuen Codes.
    r2 = client.post("/ui/api/2fa/enable", headers=auth, json={"code": code})
    assert r2.status_code == 409, r2.status_code
    assert "recovery" not in r2.json()
    assert totp._load()["recovery"] == hashes1, "Recovery-Codes müssen unverändert bleiben"
    assert totp.is_enabled()


def test_falscher_code_aktiviert_nicht(fresh_vault):
    totp.begin_setup("hub", "Test Hub")
    assert totp.enable("000000") is None
    assert not totp.is_enabled()
