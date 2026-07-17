"""Datei-Sperren für Mapping-Builds und den Wissens-Repo-Sync.

Warum flock: Die Sperre gehört dem Datei-Deskriptor und stirbt mit dem Prozess —
ein Absturz (kill -9, Serverneustart, OOM) hinterlässt NIEMALS eine Leichen-Sperre,
die manuell weggeräumt werden müsste (GESAMTAUFTRAG Run 9). PID-Dateien tun das nicht.

Konvention (Python UND Shell nutzen dieselben Pfade):
    $KMCP_LOCK_DIR/build-<projekt>.lock   — ein Build/Purge je Projekt
    $KMCP_LOCK_DIR/sync-repo.lock         — genau ein Sync ins Wissens-Repo
Standard-Verzeichnis: ~/hub-data/locks (persistent, außerhalb der Releases).

Shell-Seite (nightly-map.sh, tools/graphify-sync) verwendet flock(1) auf dieselben
Dateien — Python- und Shell-Läufe sperren sich damit gegenseitig korrekt aus.
"""

from __future__ import annotations

import fcntl
import os
import time
from contextlib import contextmanager
from pathlib import Path

LOCK_DIR = Path(os.environ.get("KMCP_LOCK_DIR", str(Path.home() / "hub-data" / "locks")))


class LockedError(RuntimeError):
    """Die Sperre wird von einem anderen Lauf gehalten."""


def _norm(project: str) -> str:
    return project.rstrip("/").split("/")[-1].lower()


@contextmanager
def _flock(datei: str, timeout: float, beschreibung: str):
    LOCK_DIR.mkdir(parents=True, exist_ok=True)
    fd = os.open(LOCK_DIR / datei, os.O_CREAT | os.O_RDWR, 0o600)
    frist = time.monotonic() + timeout
    try:
        while True:
            try:
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except BlockingIOError:
                if time.monotonic() >= frist:
                    raise LockedError(
                        f"{beschreibung} ist gesperrt (anderer Lauf aktiv) — Sperre: {datei}"
                    ) from None
                time.sleep(0.2)
        yield
    finally:
        try:
            fcntl.flock(fd, fcntl.LOCK_UN)
        finally:
            os.close(fd)


@contextmanager
def project_lock(project: str, timeout: float = 0):
    """Exklusiver Build-/Purge-Zugriff auf ein Projekt. timeout 0 = sofort abweisen."""
    name = _norm(project)
    with _flock(f"build-{name}.lock", timeout, f"Projekt {name!r}"):
        yield


@contextmanager
def sync_lock(timeout: float = 120):
    """Exklusiver Zugriff auf das Wissens-Repo (rsync + git). Ein Sync zur Zeit.

    Vertrag mit der Shell-Seite: nightly-map.sh und tools/graphify-sync betreten
    das Repo nur unter derselben Datei (sync-repo.lock via flock(1)). Auch jede
    PYTHON-seitige Repo-Schreibung MUSS hier durch — insbesondere der
    Purge-Commit (api/mapping.py: _git_purge_commit), der sich sonst mit einem
    laufenden rsync+git-Sync verzahnen kann (CE-08). Deshalb NICHT entfernen,
    selbst wenn der Aufruf im eigenen Modul-Kontext nicht sichtbar ist.
    """
    with _flock("sync-repo.lock", timeout, "Wissens-Repo-Sync"):
        yield
