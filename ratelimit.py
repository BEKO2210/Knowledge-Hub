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

# Speicher-Deckel (CE-08): Ohne Aufräumen wüchsen die IP-Maps mit jedem neu
# gesehenen Client unbegrenzt (Memory-DoS, wachsende ratelimit.json) — besonders
# fies, solange IPs gefälscht werden konnten (P0-6, TRUSTED_PROXIES in
# api/common.py). Deshalb: periodisch fegen + harte Obergrenze je Map.
_MAX_KEYS = 50_000  # harte Obergrenze an Schlüsseln je Map; älteste werden verworfen
_JANITOR_INTERVALL = 300  # Sekunden — höchstens so oft fegen (Zugriffs-pfad-schonend)
_last_janitor = 0.0


def _janitor_locked(now: float) -> bool:
    """Abgelaufene Einträge fegen und die Obergrenze durchsetzen.

    NUR unter _lock aufrufen. Rückgabe: True, wenn _fails verändert wurde
    (→ Aufrufer persistiert, damit auch die Datei klein bleibt).
    """
    global _last_janitor
    if now - _last_janitor < _JANITOR_INTERVALL:
        return False
    _last_janitor = now
    geaendert = False
    for store in (_fails, _hits):
        for key in [
            k
            for k, times in store.items()
            if not times or now - max(times) >= _LIMITS.get(k.partition(":")[0], (900, 5))[0]
        ]:
            store.pop(key, None)
            geaendert = geaendert or store is _fails
        if len(store) > _MAX_KEYS:  # Obergrenze: älteste (nach letztem Zeitstempel) wegwerfen
            for key in sorted(store, key=lambda k: max(store[k] or [0.0]))[: len(store) - _MAX_KEYS]:
                store.pop(key, None)
            geaendert = geaendert or store is _fails
    return geaendert


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
        if _janitor_locked(now):
            _persist()
        key = _key(action, ip)
        fails = [t for t in _fails.get(key, []) if now - t < window]
        if fails:
            _fails[key] = fails
        else:
            _fails.pop(key, None)  # leere Listen gar nicht erst speichern (Map-Größe)
        return len(fails) < limit


def record_failure(action: str, ip: str) -> int:
    """Fehlversuch zählen. Gibt die aktuelle Anzahl zurück; löst bei Erreichen
    der Grenze genau einmal den Alarm aus."""
    window, limit = _LIMITS.get(action, (900, 5))
    now = time.time()
    with _lock:
        _janitor_locked(now)  # _persist() folgt unten ohnehin
        key = _key(action, ip)
        fails = [t for t in _fails.get(key, []) if now - t < window]
        fails.append(now)
        _fails[key] = fails
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
        if _janitor_locked(now):  # räumt auch _fails mit auf → Datei klein halten
            _persist()
        key = _key(action, ip)
        hits = [t for t in _hits.get(key, []) if now - t < window]
        erlaubt = len(hits) < limit
        gerade_gesperrt = len(hits) == limit
        # Auch abgelehnte Versuche zählen (Fenster wandert mit), aber die Liste
        # deckeln — sonst wüchse sie mit jedem geblockten Versuch weiter.
        hits.append(now)
        _hits[key] = hits[-(limit + 1) :]
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
