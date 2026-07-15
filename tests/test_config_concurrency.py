"""Lost-Update-Schutz für config.yaml (Audit-Run 19, R19-1/R19-2).

save_projects, save_mapping und save_backup schreiben ALLE die ganze config.yaml über
ein Lesen-Ändern-Schreiben. MCP-Tools laufen in Worker-Threads, HTTP-Handler in der
Event-Loop — echte Parallelität. Ohne gemeinsame Sperre überschrieb der spätere Schreiber
die Änderung des früheren (Backend-Änderung ging in ~92 % der Fälle verloren). Zusätzlich
schrieben save_mapping/save_backup nicht atomar (write_text statt temp+rename).
"""

from __future__ import annotations

import threading

import yaml

import config


def _reset(cfg_path):
    config.save_mapping("openai", "m0")
    config.save_projects([{"path": "~/p0", "enabled": True}])


def test_paralleles_speichern_verliert_keine_aenderung(tmp_path, monkeypatch):
    cfg = tmp_path / "config.yaml"
    monkeypatch.setattr(config, "CONFIG_PATH", cfg)

    for i in range(40):
        _reset(cfg)
        b = threading.Barrier(2)

        def aendere_backend(n=i, barr=b):
            barr.wait()
            config.save_mapping(f"backend{n}", "mx")

        def aendere_projekte(n=i, barr=b):
            barr.wait()
            config.save_projects([{"path": "~/p0", "enabled": True}, {"path": f"~/p{n}", "enabled": True}])

        t1 = threading.Thread(target=aendere_backend)
        t2 = threading.Thread(target=aendere_projekte)
        t1.start()
        t2.start()
        t1.join()
        t2.join()

        c = config.load()
        assert c["mapping"]["backend"] == f"backend{i}", f"Backend-Änderung verloren in Runde {i}"
        pfade = {e["path"] for e in config.project_entries(c)}
        assert f"~/p{i}" in pfade, f"Projekt-Änderung verloren in Runde {i}"


def test_paralleles_backup_und_mapping_bleiben_beide(tmp_path, monkeypatch):
    """save_backup und save_mapping betreffen verschiedene Abschnitte — beide müssen bleiben."""
    cfg = tmp_path / "config.yaml"
    monkeypatch.setattr(config, "CONFIG_PATH", cfg)

    for i in range(40):
        config.save_mapping("openai", "m0")
        config.save_backup([])
        b = threading.Barrier(2)

        def setze_backup(n=i, barr=b):
            barr.wait()
            config.save_backup([{"type": "git", "url": f"https://x/{n}.git"}])

        def setze_mapping(n=i, barr=b):
            barr.wait()
            config.save_mapping(f"b{n}", "mx")

        t1 = threading.Thread(target=setze_backup)
        t2 = threading.Thread(target=setze_mapping)
        t1.start()
        t2.start()
        t1.join()
        t2.join()

        raw = yaml.safe_load(cfg.read_text())
        assert raw["mapping"]["backend"] == f"b{i}", f"Mapping verloren, Runde {i}"
        assert raw["backup"]["targets"] and raw["backup"]["targets"][0]["url"].endswith(f"{i}.git"), (
            f"Backup verloren, Runde {i}"
        )


def test_schreibvorgang_ist_atomar_und_laesst_keine_tempdatei(tmp_path, monkeypatch):
    cfg = tmp_path / "config.yaml"
    monkeypatch.setattr(config, "CONFIG_PATH", cfg)
    config.save_mapping("openai", "m1")
    config.save_backup([{"type": "git", "url": "https://x/y.git"}])
    config.save_projects([{"path": "~/p", "enabled": True}])
    # Keine liegengebliebenen temporären Dateien (temp+rename sauber aufgeräumt)
    reste = list(tmp_path.glob(".config.yaml-*")) + list(tmp_path.glob("*.tmp"))
    assert not reste, f"temporäre Schreibdateien blieben liegen: {reste}"
    # Datei ist gültiges YAML mit allen drei Abschnitten
    data = yaml.safe_load(cfg.read_text())
    assert data["mapping"]["model"] == "m1"
    assert data["backup"]["targets"][0]["url"] == "https://x/y.git"
    assert data["mapping"]["projects"][0]["path"] == "~/p"
