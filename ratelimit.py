"""Gemeinsame Brute-Force-Bremse für alle Anmelde-Wege.

Ein zentraler Zähler statt drei halber Lösungen: Web-Login, OAuth-Consent-Seite
und der Erststart-Wizard teilen sich dasselbe Fenster pro IP. Wer über den einen
Weg gesperrt ist, kann nicht einfach auf den anderen ausweichen.

Zusätzlich meldet die Bremse eine Sperre über einen Callback, damit der Betrieb
alarmiert werden kann (Audit + optional Push/Mail).
"""

from __future__ import annotations

import json
import os
import threading
import time
from collections.abc import Callable
from pathlib import Path

# Sperren überstehen einen Neustart (sonst könnte ein Angreifer ihn einfach abwarten).
_STATE = Path(os.environ.get("KMCP_DATA_DIR", str(Path(__file__).parent))) / "ratelimit.json"

# Fenster + Grenzen pro Aktion. Nach `limit` Fehlversuchen in `window` Sekunden
# ist die IP für den Rest des Fensters gesperrt.
_LIMITS = {
    "login": (900, 5),  # 5 Fehlversuche / 15 min
    "setup": (300, 10),  # frisches System: 10 / 5 min
    "write": (60, 120),  # 120 schreibende UI-Aufrufe / min (Drossel, kein Fehlversuchszähler)
    "register": (3600, 30),  # 30 Client-Registrierungen / Std / IP (Drossel, unauthentifiziert)
}


def _load() -> dict[str, list[float]]:
    if _STATE.exists():
        try:
            return json.loads(_STATE.read_text())
        except Exception:  # noqa: BLE001
            return {}
    return {}


_fails: dict[str, list[float]] = _load()
_lock = threading.Lock()
_alert: Callable[[str, str, int], None] | None = None


def _persist() -> None:
    """Nur nicht-leere Einträge speichern (hält die Datei klein)."""
    try:
        data = {k: v for k, v in _fails.items() if v}
        tmp = _STATE.with_suffix(".tmp")
        tmp.write_text(json.dumps(data))
        tmp.replace(_STATE)
    except OSError:
        pass


def set_alert(cb: Callable[[str, str, int], None]) -> None:
    """Callback für den Moment, in dem eine IP gesperrt wird: cb(action, ip, fails)."""
    global _alert
    _alert = cb


def _key(action: str, ip: str) -> str:
    return f"{action}:{ip}"


def check(action: str, ip: str) -> bool:
    """True = erlaubt, False = gesperrt (Grenze bereits erreicht)."""
    window, limit = _LIMITS.get(action, (900, 5))
    now = time.time()
    with _lock:
        fails = [t for t in _fails.get(_key(action, ip), []) if now - t < window]
        _fails[_key(action, ip)] = fails
        return len(fails) < limit


def record_failure(action: str, ip: str) -> int:
    """Fehlversuch zählen. Gibt die aktuelle Anzahl zurück; löst bei Erreichen
    der Grenze genau einmal den Alarm aus."""
    window, limit = _LIMITS.get(action, (900, 5))
    now = time.time()
    with _lock:
        fails = [t for t in _fails.get(_key(action, ip), []) if now - t < window]
        fails.append(now)
        _fails[_key(action, ip)] = fails
        count = len(fails)
        just_blocked = count == limit
        _persist()
    if just_blocked and _alert:
        try:
            _alert(action, ip, count)
        except Exception:  # noqa: BLE001 - Alarm darf den Login-Pfad nie stören
            pass
    return count


_hits: dict[str, list[float]] = {}


def throttle(action: str, ip: str) -> tuple[bool, bool]:
    """Jeden Aufruf zählen — nicht nur Fehlversuche. (erlaubt, gerade_gesperrt).

    Für die Schreib-Drossel: check()/record_failure() zählen Fehlschläge und
    bestrafen dauerhaft; eine Drossel bremst dagegen auch ERFOLGREICHE Aufrufe
    und vergisst von selbst, sobald das Fenster weiterwandert. Bewusst nur im
    Speicher (kein _persist): Eine Drossel muss keinen Neustart überstehen,
    und eine Datei pro Schreibzugriff wäre selbst eine Angriffsfläche.

    `gerade_gesperrt` ist genau beim ersten abgelehnten Aufruf wahr — damit der
    Aufrufer EINEN Audit-Eintrag schreibt statt einen pro geblocktem Versuch
    (sonst könnte ein Angreifer über die Drossel das Audit-Log fluten).
    """
    window, limit = _LIMITS.get(action, (60, 120))
    now = time.time()
    with _lock:
        hits = [t for t in _hits.get(_key(action, ip), []) if now - t < window]
        erlaubt = len(hits) < limit
        gerade_gesperrt = len(hits) == limit
        # Auch abgelehnte Versuche zählen (Fenster wandert mit), aber die Liste
        # deckeln — sonst wüchse sie mit jedem geblockten Versuch weiter.
        hits.append(now)
        _hits[_key(action, ip)] = hits[-(limit + 1) :]
    return erlaubt, gerade_gesperrt


def record_success(action: str, ip: str) -> None:
    """Erfolgreiche Anmeldung -> Zähler dieser IP zurücksetzen."""
    with _lock:
        if _fails.pop(_key(action, ip), None) is not None:
            _persist()


def unblock(ip: str = "") -> int:
    """Sperren aufheben (eine IP oder alle) — für den „Freigeben“-Knopf."""
    with _lock:
        keys = [k for k in _fails if not ip or k.endswith(":" + ip)]
        for k in keys:
            _fails.pop(k, None)
        _persist()
    return len(keys)


def blocked_ips() -> list[dict]:
    """Aktuell gesperrte IPs (für die Diagnose)."""
    now = time.time()
    out = []
    with _lock:
        for key, times in _fails.items():
            action, _, ip = key.partition(":")
            window, limit = _LIMITS.get(action, (900, 5))
            recent = [t for t in times if now - t < window]
            if len(recent) >= limit:
                out.append({"action": action, "ip": ip, "until": int(max(recent) + window)})
    return out
