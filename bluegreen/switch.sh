#!/usr/bin/env bash
# Atomare Blue-Green-Umschaltung des Entry Points.
#
#   switch.sh <instanz.conf> <blue|green>
#
# Garantien:
#   - flock verhindert parallele Switches/Deployments (Exit 75, EX_TEMPFAIL)
#   - Ziel-Slot wird VOR der Umschaltung geprüft; ungesundes Ziel ⇒ keine Änderung
#   - Umschaltung = Drop-in atomar ersetzen + Proxy-Restart; der Entry-Socket
#     bleibt durchgehend gebunden (systemd-Socket-Activation)
#   - Verifikation erfolgt DURCH den Entry Point; schlägt sie fehl, wird das
#     vorherige Ziel wiederhergestellt und erneut verifiziert
#   - slot-state.json wird atomar (tmp+rename) geschrieben
set -euo pipefail

CONF="${1:?Aufruf: switch.sh <instanz.conf> <blue|green>}"
ZIEL="${2:?Aufruf: switch.sh <instanz.conf> <blue|green>}"
# shellcheck source=/dev/null
source "$CONF"   # BG_STATE_DIR BG_ENTRY_UNIT BG_ENTRY_PORT BG_BLUE_PORT BG_GREEN_PORT BG_RELEASES_DIR
: "${BG_STATE_DIR:?}" "${BG_ENTRY_UNIT:?}" "${BG_ENTRY_PORT:?}" "${BG_BLUE_PORT:?}" "${BG_GREEN_PORT:?}" "${BG_RELEASES_DIR:?}"

case "$ZIEL" in
  blue)  ZIEL_PORT="$BG_BLUE_PORT" ;;
  green) ZIEL_PORT="$BG_GREEN_PORT" ;;
  *) echo "FEHLER: Slot muss blue oder green sein, nicht '$ZIEL'"; exit 64 ;;
esac

STATE="$BG_STATE_DIR/slot-state.json"
DROPIN_DIR="$HOME/.config/systemd/user/$BG_ENTRY_UNIT.service.d"
# Standard-Probe ist das echte Readiness-Modell (health.py): Config, Datenpfade, Vault,
# Projektliste, Graphen, MCP-Toolliste, Assets, Migrationsstand. /ui==200 reicht nicht.
# Für Alt-Releases ohne /healthz kann die Instanz-Config BG_PROBE_PATH=/ui setzen.
PROBE_PATH="${BG_PROBE_PATH:-/healthz/ready}"

log() { printf '[switch] %s\n' "$1"; }

# --- 1. Deployment-Lock -----------------------------------------------------
mkdir -p "$BG_STATE_DIR"
exec 9>"$BG_STATE_DIR/deploy.lock"
if ! flock -n 9; then
  log "FEHLER: Ein anderes Deployment/Switch läuft bereits (deploy.lock). Abbruch ohne Änderung."
  exit 75
fi

# --- 2. Zustand lesen --------------------------------------------------------
AKTIV="unbekannt"
[ -f "$STATE" ] && AKTIV=$(python3 -c "import json;print(json.load(open('$STATE')).get('active_slot','unbekannt'))")
if [ "$AKTIV" = "$ZIEL" ]; then
  log "Ziel-Slot $ZIEL ist bereits aktiv — nichts zu tun."
  exit 0
fi

# Blockierte Releases respektieren (Liste wird ab Run 5 automatisch gepflegt)
ZIEL_MANIFEST="$BG_RELEASES_DIR/$ZIEL/release-manifest.json"
ZIEL_RELEASE="unbekannt"
if [ -f "$ZIEL_MANIFEST" ]; then
  ZIEL_RELEASE=$(python3 -c "import json;print(json.load(open('$ZIEL_MANIFEST'))['release_id'])")
  if [ -f "$STATE" ] && python3 -c "
import json,sys
s=json.load(open('$STATE'))
sys.exit(0 if '$ZIEL_RELEASE' in s.get('blocked_releases',[]) else 1)"; then
    log "FEHLER: Release $ZIEL_RELEASE ist blockiert (frühere Fehlschläge). Abbruch."
    exit 65
  fi
fi

# --- 3. Ziel-Slot muss VOR der Umschaltung gesund sein ------------------------
log "Prüfe Ziel-Slot $ZIEL auf 127.0.0.1:$ZIEL_PORT$PROBE_PATH …"
if ! curl -sf -m 3 "http://127.0.0.1:$ZIEL_PORT$PROBE_PATH" >/dev/null; then
  log "FEHLER: Ziel-Slot $ZIEL antwortet nicht — Umschaltung NICHT durchgeführt, $AKTIV bleibt aktiv."
  exit 69
fi

# --- 4. Drop-in atomar ersetzen + Proxy neu starten ---------------------------
mkdir -p "$DROPIN_DIR"
TMP=$(mktemp "$DROPIN_DIR/.target.XXXXXX")
printf '[Service]\nExecStart=\nExecStart=/usr/lib/systemd/systemd-socket-proxyd 127.0.0.1:%s\n' "$ZIEL_PORT" > "$TMP"
mv "$TMP" "$DROPIN_DIR/10-target.conf"
systemctl --user daemon-reload
systemctl --user restart "$BG_ENTRY_UNIT"

# --- 5. Verifikation DURCH den Entry Point ------------------------------------
if curl -sf -m 5 "http://127.0.0.1:$BG_ENTRY_PORT$PROBE_PATH" >/dev/null; then
  log "Umschaltung OK: Entry Point :$BG_ENTRY_PORT bedient jetzt $ZIEL (:$ZIEL_PORT)."
else
  log "FEHLER: Entry Point antwortet nach Umschaltung nicht — stelle $AKTIV wieder her!"
  case "$AKTIV" in
    blue)  ALT_PORT="$BG_BLUE_PORT" ;;
    green) ALT_PORT="$BG_GREEN_PORT" ;;
    *) log "KRITISCH: Vorheriger Slot unbekannt — manueller Eingriff nötig (Notfallmodus Run 5)."; exit 70 ;;
  esac
  TMP=$(mktemp "$DROPIN_DIR/.target.XXXXXX")
  printf '[Service]\nExecStart=\nExecStart=/usr/lib/systemd/systemd-socket-proxyd 127.0.0.1:%s\n' "$ALT_PORT" > "$TMP"
  mv "$TMP" "$DROPIN_DIR/10-target.conf"
  systemctl --user daemon-reload
  systemctl --user restart "$BG_ENTRY_UNIT"
  if curl -sf -m 5 "http://127.0.0.1:$BG_ENTRY_PORT$PROBE_PATH" >/dev/null; then
    log "Rückschaltung auf $AKTIV erfolgreich — Zustand unverändert gesund."
  else
    log "KRITISCH: Auch $AKTIV antwortet nicht mehr — beide Ziele ungesund (Notfallmodus Run 5)."
  fi
  exit 70
fi

# --- 6. Zustand atomar persistieren -------------------------------------------
AKTIV_RELEASE="unbekannt"
AKTIV_MANIFEST="$BG_RELEASES_DIR/$AKTIV/release-manifest.json"
[ -f "$AKTIV_MANIFEST" ] && AKTIV_RELEASE=$(python3 -c "import json;print(json.load(open('$AKTIV_MANIFEST'))['release_id'])")
python3 - "$STATE" <<PYEOF
import json, os, sys, datetime, tempfile
state_path = sys.argv[1]
s = {}
if os.path.exists(state_path):
    s = json.load(open(state_path))
s.update({
    "schema_version": "1.0",
    "active_slot": "$ZIEL",
    "previous_slot": "$AKTIV",
    "active_release": "$ZIEL_RELEASE",
    "previous_release": "$AKTIV_RELEASE",
    "last_switch_at": datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds"),
    "switch_count": s.get("switch_count", 0) + 1,
})
s.setdefault("fallback_count", 0)
s.setdefault("blocked_releases", [])
fd, tmp = tempfile.mkstemp(dir=os.path.dirname(state_path))
with os.fdopen(fd, "w") as f:
    json.dump(s, f, indent=2)
    f.flush(); os.fsync(f.fileno())
os.replace(tmp, state_path)
PYEOF
log "slot-state.json aktualisiert (aktiv: $ZIEL, vorher: $AKTIV)."
