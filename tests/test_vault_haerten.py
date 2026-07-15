"""Run-020: Vault-Härtung — totp-Transaktions-Atomarität + kaputte Vault-Datei.

Belege in ~/hub-audit/EVIDENCE/run-020/vault_probe.py (vor dem Fix: 60/60 verlorene
Recovery-Sets, 60/60 doppelt akzeptierte Einmal-Codes, Absturz bei kaputter Datei).
"""

from __future__ import annotations

import hashlib
import threading
import time

import pytest

import totp
import vault


def _valid_code(secret: str) -> str:
    return totp._code_at(secret, int(time.time()) // totp.PERIOD)


def _parallel(fn, n=2):
    """fn() in n Threads gleichzeitig starten (Barrier), Ergebnisse einsammeln."""
    out: list = []
    barrier = threading.Barrier(n)

    def worker():
        barrier.wait()
        out.append(fn())

    ts = [threading.Thread(target=worker) for _ in range(n)]
    for t in ts:
        t.start()
    for t in ts:
        t.join()
    return out


# --- R20-1: totp-Transaktions-Atomarität -------------------------------------
def test_paralleles_enable_verliert_keine_recovery_codes(fresh_vault):
    """Zwei gleichzeitige 2FA-Aktivierungen (Doppelklick → zwei to_thread-Aufrufe)
    dürfen nicht zwei verschiedene Recovery-Sets erzeugen, von denen eines still
    verworfen wird. Genau ein Aufruf gewinnt; die dem Nutzer gezeigten Codes gelten."""
    setup = totp.begin_setup("kunde", "hub")
    code = _valid_code(setup["secret"])

    returned = [r for r in _parallel(lambda: totp.enable(code)) if r]
    persisted = set(totp._load().get("recovery", []))

    # Höchstens ein Aufruf darf Recovery-Codes zurückgeben (der andere sieht
    # enabled=True und liefert None) …
    assert len(returned) == 1, f"{len(returned)} Recovery-Sets vergeben — Lost-Update"
    # … und die zurückgegebenen Codes müssen die tatsächlich gespeicherten sein.
    hashes = {hashlib.sha256(c.encode()).hexdigest() for c in returned[0]}
    assert hashes == persisted, "gezeigte Recovery-Codes stehen nicht im Vault"


def test_paralleler_recovery_code_wird_nur_einmal_akzeptiert(fresh_vault):
    """Ein Einmal-Recovery-Code darf bei zwei gleichzeitigen Logins nur EINEN
    durchlassen — sonst ist der Einmal-Charakter (und die Sperre) ausgehebelt."""
    setup = totp.begin_setup("kunde", "hub")
    recovery = totp.enable(_valid_code(setup["secret"]))
    one = recovery[0]

    oks = _parallel(lambda: totp.check(one))
    assert oks.count(True) == 1, f"Einmal-Code {oks.count(True)}× akzeptiert"
    # Danach ist der Code verbraucht.
    assert totp.check(one) is False


# --- R20-3: Datei-Rechte des Audit-Logs --------------------------------------
def test_audit_log_ist_nur_fuer_den_eigentuemer_lesbar(fresh_vault):
    """Das Audit-Log listet Secret-NAMEN und Zugriffszeiten (Metadaten) — es darf
    nicht gruppen-/weltlesbar sein, sondern 0600 wie die vault.enc selbst."""
    vault.secret_set("api", "geheim", client="test")  # erzeugt/schreibt audit.log
    mode = vault.AUDIT_PATH.stat().st_mode & 0o777
    assert mode == 0o600, f"audit.log hat Rechte {oct(mode)}, erwartet 0o600"


# --- R20-2: kaputte Vault-Datei ----------------------------------------------
def test_halbe_vault_datei_meldet_sauber_statt_absturz(fresh_vault):
    vault.secret_set("api", "geheim", client="test")
    good = vault.VAULT_PATH.read_bytes()
    vault.VAULT_PATH.write_bytes(good[: len(good) // 2])  # Torn-Write simulieren
    vault.lock()

    # status() darf NICHT abstürzen …
    st = vault.status()
    assert isinstance(st, dict)
    # … und ein Secret-Zugriff meldet sauber VaultCorrupt (Unterklasse von VaultLocked),
    # kein nackter JSONDecodeError.
    with pytest.raises(vault.VaultLocked):
        vault.secret_get("api", client="test")


def test_muell_vault_datei_meldet_sauber_statt_absturz(fresh_vault):
    vault.secret_set("api", "geheim", client="test")
    vault.VAULT_PATH.write_bytes(b"\x00\x01voelliger-muell")
    vault.lock()

    assert isinstance(vault.status(), dict)
    with pytest.raises(vault.VaultLocked):
        vault.secret_get("api", client="test")


def test_kaputte_vault_datei_gibt_keinen_400_und_keinen_traceback(client, auth, fresh_vault):
    """An der HTTP-Schicht darf eine beschädigte Vault-Datei nicht als
    ‚kein gültiges JSON' (400, Schuld des Aufrufers) oder als 500-Traceback
    ankommen, sondern als sauberer, eindeutiger Serverfehler."""
    vault.secret_set("api", "geheim", client="test")
    good = vault.VAULT_PATH.read_bytes()
    vault.VAULT_PATH.write_bytes(good[: len(good) // 2])
    vault.lock()

    r = client.get("/ui/api/secrets", headers=auth)
    assert r.status_code in (423, 500)
    body = r.json()
    assert "error" in body
    # Nicht die irreführende Eingabe-Fehlermeldung:
    assert "JSON" not in body["error"] or "beschädigt" in body["error"].lower()
