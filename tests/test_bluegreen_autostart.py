"""Blue-Green: der Auto-Start (systemd enable/disable) muss dem AKTIVEN Slot folgen.

Regression zu UI/Backend-Kampagne Run 1 (Befund R1-1): switch.sh schaltete den
Entry-Proxy um, fasste aber die systemd-enable-Flags nicht an. Nach einem Switch
war der aktive Slot disabled und der alte enabled -> ein Reboot hätte den falschen
bzw. keinen Slot gestartet, während der Proxy schon auf den aktiven zeigt = Hub
extern tot.

Der Test extrahiert die echte persist_autostart-Funktion aus bluegreen/switch.sh
und prüft ihr Verhalten mit gestubbtem systemctl (kein Eingriff in echten Zustand).
"""

from __future__ import annotations

import subprocess
from pathlib import Path

SWITCH = Path(__file__).resolve().parent.parent / "bluegreen" / "switch.sh"

# Schneidet SLOT_UNIT_PREFIX + slot_unit + persist_autostart aus dem echten Skript.
_EXTRACT = r"awk '/^SLOT_UNIT_PREFIX=/{f=1} f{print} f&&/^}/{exit}' " + str(SWITCH)


def _run(prefix: str, aktiv: str) -> str:
    """persist_autostart <aktiv> mit gestubbtem systemctl ausführen, Aufrufe zurückgeben."""
    harness = f"""
set -euo pipefail
CALLS=""
systemctl(){{ CALLS="$CALLS [$*]"; return 0; }}
log(){{ :; }}
export BG_SLOT_UNIT_PREFIX="{prefix}"
source <({_EXTRACT})
persist_autostart {aktiv}
printf '%s' "$CALLS"
"""
    out = subprocess.run(["bash", "-c", harness], capture_output=True, text=True, timeout=30)
    assert out.returncode == 0, out.stderr
    return out.stdout


def test_aktiver_slot_wird_enabled_anderer_disabled():
    calls = _run("kmcp-", "green")
    assert "--user enable kmcp-green.service" in calls
    assert "--user disable kmcp-blue.service" in calls
    # niemals den aktiven Slot disablen
    assert "disable kmcp-green.service" not in calls


def test_richtung_symmetrisch_fuer_blue():
    calls = _run("kmcp-", "blue")
    assert "--user enable kmcp-blue.service" in calls
    assert "--user disable kmcp-green.service" in calls


def test_prefix_konfigurierbar_fuer_testinstanz():
    # Testinstanz darf NIE die Prod-Units (kmcp-blue/green) anfassen.
    calls = _run("kmcp-test-", "green")
    assert "--user enable kmcp-test-green.service" in calls
    assert "--user disable kmcp-test-blue.service" in calls
    assert "kmcp-green.service" not in calls
    assert "kmcp-blue.service" not in calls


def test_switch_ruft_persist_autostart_im_erfolgs_und_fallback_pfad():
    # Strukturgarantie: beide Pfade führen den Auto-Start nach.
    text = SWITCH.read_text(encoding="utf-8")
    assert 'persist_autostart "$ZIEL"' in text, "Erfolgspfad muss Auto-Start nachführen"
    assert 'persist_autostart "$AKTIV"' in text, "Fallback-Pfad muss Auto-Start nachführen"
