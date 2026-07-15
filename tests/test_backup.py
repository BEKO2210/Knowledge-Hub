"""Run-021: Backup/Restore — Roundtrip, Fehlerfälle, atomarer Write, Restore-E2E.

Beleg: ~/hub-audit/EVIDENCE/run-021/backup_probe.py (E: halbe .khub blieb liegen →
nach Fix atomar; A–D sauber, F 0/40 inkonsistent, G Restore intakt).
"""

from __future__ import annotations

import time

import pytest

import backup
import totp
import vault

PP = "backup-passphrase-1234"  # >= 12 Zeichen
# Muss zum Passwort des fresh_vault-Fixtures passen (conftest.TEST_PASSWORD).
# NICHT aus tests.conftest importieren: das führt conftest ein zweites Mal aus,
# legt ein neues Temp-Verzeichnis an und biegt VAULT_PATH um → vault.init und
# backup._paths zeigen dann auf verschiedene Verzeichnisse.
TEST_PASSWORD = "test-passwort-123"


def _seed():
    vault.secret_set("STRIPE_API_KEY", "sk_live_ABC", client="t")
    vault.secret_set("OPENAI_API_KEY", "sk-openai-XYZ", client="t")
    setup = totp.begin_setup("belkis", "hub")
    totp.enable(totp._code_at(setup["secret"], int(time.time()) // totp.PERIOD))


# --- Roundtrip + Fehlerfälle -------------------------------------------------
def test_create_verify_roundtrip(fresh_vault):
    _seed()
    blob = backup.create(PP)
    assert set(backup.contents(blob, PP)) == {"env", "vault.enc", "config.yaml", "BACKUP-INFO.txt"}


def test_passphrase_zu_kurz_wird_abgelehnt(fresh_vault):
    with pytest.raises(ValueError):
        backup.create("kurz")


def test_falsche_passphrase_meldet_sauber(fresh_vault):
    blob = backup.create(PP)
    with pytest.raises(ValueError):
        backup.open_archive(blob, "voellig-falsch-99")


def test_beschaedigtes_archiv_meldet_sauber(fresh_vault):
    blob = bytearray(backup.create(PP))
    blob[len(blob) // 2] ^= 0xFF
    with pytest.raises(ValueError):
        backup.open_archive(bytes(blob), PP)


@pytest.mark.parametrize("cut", ["half", "tiny", "empty", "nomagic"])
def test_abgeschnittenes_oder_fremdes_archiv_meldet_sauber(fresh_vault, cut):
    blob = backup.create(PP)
    data = {
        "half": blob[: len(blob) // 2],
        "tiny": blob[:5],
        "empty": b"",
        "nomagic": b"NICHTKHUB" + blob[9:],
    }[cut]
    with pytest.raises(ValueError):
        backup.open_archive(data, PP)


# --- R21-1: atomarer Write (volles Medium) -----------------------------------
def test_write_atomar_bei_schreibfehler_erhaelt_altdatei(tmp_path, monkeypatch, fresh_vault):
    """Ein abgebrochener Write (ENOSPC) darf weder eine halbe Datei hinterlassen
    noch ein bereits vorhandenes gutes Backup zerstören."""
    good = backup.create(PP)
    target = tmp_path / "hub-2026-07-15_0930.khub"
    target.write_bytes(good)  # vorhandenes GUTES Backup

    real_write = backup.os.write

    def enospc(fd, data):
        real_write(fd, data[: max(1, len(data) // 2)])  # halb schreiben …
        raise OSError(28, "No space left on device")  # … dann volles Medium

    monkeypatch.setattr(backup.os, "write", enospc)
    with pytest.raises(OSError):
        backup._write_atomar(target, good + b"neuerinhalt")
    monkeypatch.undo()

    assert target.read_bytes() == good, "vorhandenes gutes Backup wurde beschädigt"
    assert not list(tmp_path.glob(".khub-*.tmp")), "Zwischendatei blieb liegen"


def test_target_local_bei_vollem_medium_kein_kaputtes_neuestes(tmp_path, monkeypatch, fresh_vault):
    """_target_local: schlägt der Write fehl, liegt KEINE unlesbare .khub als
    neuestes Backup im Zielordner (das ältere gute überlebt)."""
    older = backup.create(PP)
    (tmp_path / "hub-2020-01-01_0000.khub").write_bytes(older)
    blob = backup.create(PP)

    real_write = backup.os.write

    def enospc(fd, data):
        real_write(fd, data[: max(1, len(data) // 2)])
        raise OSError(28, "No space left on device")

    monkeypatch.setattr(backup.os, "write", enospc)
    with pytest.raises(OSError):
        backup._target_local(blob, "hub-2026-07-15_0930.khub", {"path": str(tmp_path), "keep": 14})
    monkeypatch.undo()

    khubs = sorted(p.name for p in tmp_path.glob("hub-*.khub"))
    assert khubs == ["hub-2020-01-01_0000.khub"], f"unerwartete Dateien: {khubs}"
    # das übrig gebliebene Backup ist lesbar
    backup.open_archive((tmp_path / khubs[0]).read_bytes(), PP)


def test_cli_create_faengt_oserror_sauber(tmp_path, monkeypatch, fresh_vault, capsys):
    """CLI `create` bei vollem Medium: sauberer Fehler (Exit 1), kein Traceback."""
    monkeypatch.setenv("BACKUP_PASSPHRASE", PP)
    monkeypatch.setattr(
        backup, "_write_atomar", lambda *a, **k: (_ for _ in ()).throw(OSError(28, "No space left on device"))
    )
    monkeypatch.setattr(backup.sys, "argv", ["backup.py", "create", str(tmp_path / "x.khub")])
    rc = backup.main()
    assert rc == 1
    assert "✗" in capsys.readouterr().err


# --- R21-G: Restore End-to-End -----------------------------------------------
def test_restore_e2e_secrets_und_2fa_intakt(tmp_path, monkeypatch, fresh_vault):
    _seed()
    blob = backup.create(PP)
    fresh = tmp_path / "fresh"
    names = backup.restore(blob, PP, fresh)
    assert set(names) == {"env", "vault.enc", "config.yaml", "BACKUP-INFO.txt"}
    for n in names:
        assert (fresh / n).stat().st_mode & 0o777 == 0o600

    # frische Instanz simulieren: Vault-Modul auf die restaurierte Datei zeigen lassen
    # (monkeypatch macht es nach dem Test automatisch rückgängig — kein Reload nötig).
    monkeypatch.setattr(vault, "VAULT_PATH", fresh / "vault.enc")
    monkeypatch.setattr(vault, "AUDIT_PATH", fresh / "audit.log")
    vault.lock()
    assert vault.unlock(TEST_PASSWORD) is True
    assert set(vault.secret_list(client="t")) == {"STRIPE_API_KEY", "OPENAI_API_KEY", "__2fa__"}
    assert vault.secret_get("STRIPE_API_KEY", client="t") == "sk_live_ABC"
    assert totp.status() == {"enabled": True, "recovery_left": 8}
