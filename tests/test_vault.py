"""Vault: Verschlüsselung, Passwort-Verpackung, Secrets, Audit-Log."""

from __future__ import annotations

import pytest
from conftest import TEST_PASSWORD, TMP

import vault


def test_secret_roundtrip(fresh_vault):
    vault.secret_set("api_key", "geheim-42", client="test")
    assert vault.secret_get("api_key", client="test") == "geheim-42"
    assert "api_key" in vault.secret_list(client="test")
    assert vault.secret_delete("api_key", client="test") is True
    assert vault.secret_get("api_key", client="test") is None
    assert vault.secret_delete("api_key", client="test") is False


def test_nichts_liegt_im_klartext_auf_der_platte(fresh_vault):
    """Der entscheidende Test: Der Wert darf in der Datei nirgends lesbar auftauchen."""
    vault.secret_set("api_key", "streng-geheimer-wert", client="test")
    blob = (TMP / "vault.enc").read_bytes()
    assert b"streng-geheimer-wert" not in blob
    assert b"api_key" not in blob   # auch die Namen sind verschlüsselt


def test_falsches_passwort_entsperrt_nicht(fresh_vault):
    vault.secret_set("k", "v", client="test")
    vault.lock()
    assert vault.unlock("das-ist-falsch") is False
    assert vault.is_unlocked() is False


def test_gesperrter_vault_ohne_auto_entsperren_verweigert_zugriff(fresh_vault):
    """Ist das Auto-Entsperren aus, ist der gesperrte Vault wirklich zu — auch für den Prozess selbst.

    (Mit Auto-Entsperren geht er per VAULT_KEY absichtlich von allein auf; das ist die
    Voraussetzung für den unbeaufsichtigten Nacht-Job und wird separat geprüft.)
    """
    vault.set_auto_unlock(False)
    vault.secret_set("k", "v", client="test")
    vault.lock()
    with pytest.raises(vault.VaultLocked):
        vault.secret_get("k", client="test")


def test_richtiges_passwort_entsperrt(fresh_vault):
    vault.secret_set("k", "v", client="test")
    vault.lock()
    assert vault.unlock(TEST_PASSWORD) is True
    assert vault.secret_get("k", client="test") == "v"


def test_passwortwechsel_erhaelt_secrets(fresh_vault):
    """Der Hauptschlüssel wird nur neu verpackt — die Secrets dürfen NICHT verloren gehen."""
    vault.secret_set("k", "bleibt-erhalten", client="test")
    assert vault.change_password(TEST_PASSWORD, "neues-passwort-99") is True
    vault.lock()
    assert vault.unlock(TEST_PASSWORD) is False       # altes Passwort gilt nicht mehr
    assert vault.unlock("neues-passwort-99") is True
    assert vault.secret_get("k", client="test") == "bleibt-erhalten"


def test_passwortwechsel_mit_falschem_alten_passwort_scheitert(fresh_vault):
    assert vault.change_password("falsch", "neues-passwort-99") is False


def test_zu_kurzes_passwort_wird_abgelehnt(fresh_vault):
    with pytest.raises(ValueError):
        vault.change_password(TEST_PASSWORD, "kurz")


def test_env_schluessel_entsperrt_ohne_mensch(fresh_vault):
    """Auto-Entsperren nach Neustart: zweite Verpackung über VAULT_KEY."""
    vault.set_auto_unlock(True)
    vault.secret_set("k", "v", client="test")
    vault.lock()
    assert vault.unlock_env() is True
    assert vault.secret_get("k", client="test") == "v"


def test_auto_entsperren_abschaltbar(fresh_vault):
    vault.set_auto_unlock(True)
    vault.set_auto_unlock(False)
    vault.lock()
    assert vault.unlock_env() is False


def test_init_ueberschreibt_vorhandenen_vault_nicht(fresh_vault):
    """Ein zweites init() würde alle Secrets vernichten — muss sich weigern."""
    with pytest.raises(FileExistsError):
        vault.init("anderes-passwort")


def test_audit_log_schreibt_zugriffe_mit(fresh_vault):
    vault.secret_set("k", "v", client="test-client")
    vault.secret_get("k", client="test-client")
    log = (TMP / "audit.log").read_text()
    assert "SET" in log and "GET" in log
    assert "test-client" in log
    assert "v" not in log.split("SET")[1][:20]   # der WERT steht nie im Log
