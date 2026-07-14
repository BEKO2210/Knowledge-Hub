"""Tests für die Mapping-/Sync-Sperren (locks.py).

Am 2026-07-14 liefen manuelle Builds MITTEN im Nachtlauf auf denselben Projekten
(hub-audit Run 6). flock-basierte Sperren verhindern das — und sterben mit dem
Prozess, sodass ein Absturz niemals eine Leichen-Sperre hinterlässt.
"""

from __future__ import annotations

import fcntl
import os
import signal
import subprocess
import sys
import time

import pytest

import locks


@pytest.fixture
def lockdir(tmp_path, monkeypatch):
    d = tmp_path / "locks"
    monkeypatch.setattr(locks, "LOCK_DIR", d)
    return d


def _fremd_halten(lockdir, name):
    """Sperre wie ein fremder Prozess halten (eigener fd — flock kollidiert je fd)."""
    lockdir.mkdir(parents=True, exist_ok=True)
    fd = os.open(lockdir / f"{name}.lock", os.O_CREAT | os.O_RDWR, 0o600)
    fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    return fd


def test_zweiter_zugriff_wird_abgewiesen(lockdir):
    fd = _fremd_halten(lockdir, "build-demo")
    try:
        with pytest.raises(locks.LockedError):
            with locks.project_lock("demo"):
                pass
    finally:
        os.close(fd)


def test_wartender_zugriff_kommt_nach_freigabe_durch(lockdir):
    fd = _fremd_halten(lockdir, "build-demo")

    import threading

    threading.Timer(0.4, lambda: (fcntl.flock(fd, fcntl.LOCK_UN), os.close(fd))).start()
    t0 = time.monotonic()
    with locks.project_lock("demo", timeout=3):
        gewartet = time.monotonic() - t0
    assert 0.2 < gewartet < 3, f"sollte ~0.4s warten, war {gewartet:.2f}s"


def test_prozess_tod_hinterlaesst_keine_leiche(lockdir):
    """kill -9 auf den Halter → die Sperre ist SOFORT wieder frei (kein Aufräumen nötig)."""
    halter = subprocess.Popen(
        [
            sys.executable,
            "-c",
            f"""
import os, fcntl, time
fd = os.open(r"{lockdir}/build-demo.lock", os.O_CREAT | os.O_RDWR, 0o600)
fcntl.flock(fd, fcntl.LOCK_EX)
print("HALTE", flush=True)
time.sleep(60)
""",
        ],
        stdout=subprocess.PIPE,
        text=True,
    )
    lockdir.mkdir(parents=True, exist_ok=True)
    assert halter.stdout.readline().strip() == "HALTE"
    with pytest.raises(locks.LockedError):
        with locks.project_lock("demo"):
            pass
    os.kill(halter.pid, signal.SIGKILL)
    halter.wait(timeout=10)
    with locks.project_lock("demo"):  # darf sofort klappen
        pass


def test_projektname_wird_normalisiert(lockdir):
    fd = _fremd_halten(lockdir, "build-elementa")
    try:
        with pytest.raises(locks.LockedError):
            with locks.project_lock("Elementa"):  # Groß-/Kleinschreibung egal
                pass
    finally:
        os.close(fd)


def test_worker_bricht_bei_fremder_sperre_sauber_ab(lockdir, monkeypatch, tmp_path):
    """graph_build gegen ein gesperrtes Projekt: failed mit klarem Grund, NICHTS ausgeführt."""
    import server

    projekt = tmp_path / "demo"
    (projekt / "graphify-out").mkdir(parents=True)
    (projekt / "graphify-out" / "graph.json").write_text('{"nodes": [{"id": "a"}], "links": []}')
    befehle = []

    def fake_run(cmd, **kwargs):
        befehle.append(cmd)

        class P:
            returncode = 0

        return P()

    monkeypatch.setattr(server.subprocess, "run", fake_run)
    monkeypatch.setattr(server, "BUILD_LOG_DIR", tmp_path / "logs")
    fd = _fremd_halten(lockdir, "build-demo")
    try:
        server._builds["demo"] = {"status": "running", "started": 0, "finished": None}
        server._build_worker("demo", projekt)
    finally:
        os.close(fd)

    assert server._builds["demo"]["status"] == "failed"
    assert "Sperre" in (server._builds["demo"].get("error") or "")
    assert befehle == [], "bei fremder Sperre darf kein einziger Pipeline-Schritt laufen"
