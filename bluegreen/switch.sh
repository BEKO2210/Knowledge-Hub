#!/usr/bin/env bash
# Atomare Blue-Green-Umschaltung des Entry Points — mit automatischem Fallback.
#
#   switch.sh <instanz.conf> <blue|green>
#
# Garantien:
#   - flock verhindert parallele Switches/Deployments (Exit 75)
#   - Ziel-Slot wird VOR der Umschaltung über das Readiness-Modell geprüft;
#     ungesundes Ziel oder blockiertes Release ⇒ keine Änderung (Exit 69/65)
#   - Umschaltung = Drop-in atomar ersetzen + Proxy-Restart; der Entry-Socket
#     bleibt durchgehend gebunden (systemd-Socket-Activation)
#   - Nach der Umschaltung läuft ein Beobachtungsfenster (BG_OBSERVE_SECONDS,
#     Readiness-Polls DURCH den Entry Point). Jeder Fehlschlag löst den
#     automatischen Fallback aus: Rückschaltung, Health-Check des alten Slots,
#     strukturierter Incident, Release wandert in die Blockliste (Exit 70)
#   - Anti-Flapping: Nach einem Fallback verweigert switch.sh weitere Wechsel
#     für BG_COOLDOWN_SECONDS (Exit 76; Übersteuern nur bewusst mit BG_FORCE=1)
#   - „Beide ungesund" = Notfallmodus: EIN Rückschaltversuch, dann klarer
#     Fehlerzustand mit Incident + Recovery-Hinweis — kein Umschalt-Loop
#   - slot-state.json und Incidents werden atomar (tmp+rename) geschrieben
set -euo pipefail

CONF="${1:?Aufruf: switch.sh <instanz.conf> <blue|green>}"
ZIEL="${2:?Aufruf: switch.sh <instanz.conf> <blue|green>}"
# shellcheck source=/dev/null
source "$CONF"
: "${BG_STATE_DIR:?}" "${BG_ENTRY_UNIT:?}" "${BG_ENTRY_PORT:?}" "${BG_BLUE_PORT:?}" "${BG_GREEN_PORT:?}" "${BG_RELEASES_DIR:?}"

case "$ZIEL" in
  blue)  ZIEL_PORT="$BG_BLUE_PORT" ;;
  green) ZIEL_PORT="$BG_GREEN_PORT" ;;
  *) echo "FEHLER: Slot muss blue oder green sein, nicht '$ZIEL'"; exit 64 ;;
esac

STATE="$BG_STATE_DIR/slot-state.json"
INCIDENT_DIR="$BG_STATE_DIR/incidents"
DROPIN_DIR="$HOME/.config/systemd/user/$BG_ENTRY_UNIT.service.d"
# Standard-Probe ist das Readiness-Modell (health.py). /ui==200 reicht nicht.
# Für Alt-Releases ohne /healthz kann die Instanz-Config BG_PROBE_PATH=/ui setzen.
PROBE_PATH="${BG_PROBE_PATH:-/healthz/ready}"
OBSERVE="${BG_OBSERVE_SECONDS:-10}"
COOLDOWN="${BG_COOLDOWN_SECONDS:-300}"

log() { printf '[switch] %s\n' "$1"; }

probe() { # probe <port> — Readiness eines Ziels
  curl -sf -m 3 "http://127.0.0.1:$1$PROBE_PATH" >/dev/null
}

set_target() { # set_target <port> — Drop-in atomar ersetzen + Proxy neu starten
  mkdir -p "$DROPIN_DIR"
  local tmp
  tmp=$(mktemp "$DROPIN_DIR/.target.XXXXXX")
  printf '[Service]\nExecStart=\nExecStart=/usr/lib/systemd/systemd-socket-proxyd 127.0.0.1:%s\n' "$1" > "$tmp"
  mv "$tmp" "$DROPIN_DIR/10-target.conf"
  systemctl --user daemon-reload
  systemctl --user restart "$BG_ENTRY_UNIT"
}

# Slot-Unit-Namen (Prod: kmcp-blue/green; Testinstanz kann BG_SLOT_UNIT_PREFIX setzen)
SLOT_UNIT_PREFIX="${BG_SLOT_UNIT_PREFIX:-kmcp-}"
slot_unit() { printf '%s%s.service' "$SLOT_UNIT_PREFIX" "$1"; }

stop_standby() { # stop_standby <standby-slot> — Single-Writer: nie beide Slots gleichzeitig online
  # Erst NACH bestandenem Beobachtungsfenster bzw. erfolgreicher Rückschaltung rufen —
  # während des Fensters muss der alte Slot für den Sofort-Fallback weiterlaufen.
  # Folge: Ein späterer Switch braucht ein vorheriges `systemctl --user restart <slot>`
  # des Ziels (der dokumentierte Deploy-Ablauf tut das ohnehin; die Ziel-Probe in
  # Schritt 3 verweigert sonst sauber mit Exit 69).
  local standby="$1"
  systemctl --user stop "$(slot_unit "$standby")" >/dev/null 2>&1 \
    && log "Standby-Slot $standby gestoppt (Single-Writer: nur der aktive Slot läuft)." \
    || log "WARN: Standby-Slot $standby ließ sich nicht stoppen — läuft er noch, sind beide online!"
}

persist_autostart() { # persist_autostart <aktiver-slot> — Auto-Start dem aktiven Slot nachführen
  # Der Entry-Proxy zeigt persistent (Drop-in) auf den aktiven Slot. Damit ein Reboot
  # NICHT den falschen/keinen Slot hochbringt (Proxy -> toter Port = Hub extern down),
  # muss genau der aktive Slot enabled sein und der andere disabled. enable/disable ist
  # idempotent und ändert den LAUFZUSTAND nicht — nur das Boot-Verhalten. Ein Fehlschlag
  # ist kein Switch-Abbruch, nur ein Persistenz-Hinweis (Single-Writer bleibt zur Laufzeit
  # ohnehin durch den Proxy gewahrt).
  local aktiv="$1" ander
  ander=$([ "$aktiv" = blue ] && echo green || echo blue)
  systemctl --user enable "$(slot_unit "$aktiv")" >/dev/null 2>&1 \
    || log "WARN: $(slot_unit "$aktiv") ließ sich nicht enablen — Auto-Start nach Reboot prüfen."
  systemctl --user disable "$(slot_unit "$ander")" >/dev/null 2>&1 \
    || log "WARN: $(slot_unit "$ander") ließ sich nicht disablen — Auto-Start nach Reboot prüfen."
}

state_get() { # state_get <feld> <default>
  python3 -c "
import json, os
p = '$STATE'
d = json.load(open(p)) if os.path.exists(p) else {}
v = d.get('$1', '$2')
print(v if v is not None else '$2')"
}

state_update() { # state_update <python-dict-fragment>  (atomar, tmp+rename+fsync)
  python3 - "$STATE" <<PYEOF
import json, os, sys, datetime, tempfile
p = sys.argv[1]
s = json.load(open(p)) if os.path.exists(p) else {}
now = datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds")
s.setdefault("schema_version", "1.0")
s.setdefault("switch_count", 0)
s.setdefault("fallback_count", 0)
s.setdefault("blocked_releases", [])
s.update($1)
fd, tmp = tempfile.mkstemp(dir=os.path.dirname(p) or ".")
with os.fdopen(fd, "w") as f:
    json.dump(s, f, indent=2)
    f.flush(); os.fsync(f.fileno())
os.replace(tmp, p)
PYEOF
}

write_incident() { # write_incident <schwere> <grund>  — strukturiert, ohne Secrets/Pfade
  mkdir -p "$INCIDENT_DIR"
  python3 - "$INCIDENT_DIR" <<PYEOF
import json, os, sys, datetime, tempfile
d = sys.argv[1]
now = datetime.datetime.now(datetime.timezone.utc)
doc = {
    "schema_version": "1.0",
    "at": now.isoformat(timespec="seconds"),
    "severity": "$1",
    "reason": """$2""",
    "attempted_slot": "$ZIEL",
    "attempted_release": "$ZIEL_RELEASE",
    "previous_slot": "$AKTIV",
    "probe": "$PROBE_PATH",
}
fd, tmp = tempfile.mkstemp(dir=d)
with os.fdopen(fd, "w") as f:
    json.dump(doc, f, indent=2)
    f.flush(); os.fsync(f.fileno())
name = os.path.join(d, "incident-" + now.strftime("%Y%m%dT%H%M%SZ") + ".json")
os.replace(tmp, name)
print(name)
PYEOF
}

# --- 1. Deployment-Lock -------------------------------------------------------
mkdir -p "$BG_STATE_DIR"
exec 9>"$BG_STATE_DIR/deploy.lock"
if ! flock -n 9; then
  log "FEHLER: Ein anderes Deployment/Switch läuft bereits (deploy.lock). Abbruch ohne Änderung."
  exit 75
fi

# --- 2. Zustand + Anti-Flapping ------------------------------------------------
AKTIV=$(state_get active_slot unbekannt)
if [ "$AKTIV" = "$ZIEL" ]; then
  log "Ziel-Slot $ZIEL ist bereits aktiv — nichts zu tun."
  exit 0
fi

if [ "${BG_FORCE:-0}" != "1" ]; then
  LETZTER_FALLBACK=$(state_get last_fallback_at "")
  if [ -n "$LETZTER_FALLBACK" ] && python3 -c "
import datetime, sys
t = datetime.datetime.fromisoformat('$LETZTER_FALLBACK')
alter = (datetime.datetime.now(datetime.timezone.utc) - t).total_seconds()
sys.exit(0 if alter < $COOLDOWN else 1)"; then
    log "FEHLER: Cooldown aktiv — letzter automatischer Fallback ist jünger als ${COOLDOWN}s."
    log "Erst Ursache klären (Incidents in $INCIDENT_DIR ansehen); bewusst übersteuern: BG_FORCE=1."
    exit 76
  fi
fi

ZIEL_MANIFEST="$BG_RELEASES_DIR/$ZIEL/release-manifest.json"
ZIEL_RELEASE="unbekannt"
if [ -f "$ZIEL_MANIFEST" ]; then
  ZIEL_RELEASE=$(python3 -c "import json;print(json.load(open('$ZIEL_MANIFEST'))['release_id'])")
  if [ -f "$STATE" ] && python3 -c "
import json,sys
s=json.load(open('$STATE'))
sys.exit(0 if '$ZIEL_RELEASE' in s.get('blocked_releases',[]) else 1)"; then
    log "FEHLER: Release $ZIEL_RELEASE ist blockiert (früherer Fallback). Abbruch."
    log "Freigeben nur bewusst: Blockliste in slot-state.json bereinigen, nachdem die Ursache behoben ist."
    exit 65
  fi
fi

# --- 3. Pre-Switch-Gate ---------------------------------------------------------
# Standby ist laut Deployment-Vorgabe „gestoppt-warm" (Code+venv bereit, Prozess aus).
# Damit `switch.sh <conf> <slot>` als Ein-Befehl-Rollback funktioniert, wird ein
# gestoppter Ziel-Slot hier gestartet und seine Readiness abgewartet.
if ! probe "$ZIEL_PORT" && ! systemctl --user is-active --quiet "$(slot_unit "$ZIEL")"; then
  log "Ziel-Slot $ZIEL ist gestoppt-warm — starte $(slot_unit "$ZIEL") …"
  systemctl --user start "$(slot_unit "$ZIEL")" 2>/dev/null || true
  for _ in $(seq 1 30); do
    probe "$ZIEL_PORT" && break
    sleep 1
  done
fi
log "Prüfe Ziel-Slot $ZIEL auf 127.0.0.1:$ZIEL_PORT$PROBE_PATH …"
if ! probe "$ZIEL_PORT"; then
  log "FEHLER: Ziel-Slot $ZIEL ist nicht bereit — Umschaltung NICHT durchgeführt, $AKTIV bleibt aktiv."
  exit 69
fi

# --- 4. Umschalten ----------------------------------------------------------------
set_target "$ZIEL_PORT"

fallback() { # fallback <grund>
  log "FALLBACK: $1 — stelle $AKTIV wieder her."
  local incident
  incident=$(write_incident automatic_fallback "$1")
  log "Incident: $incident"
  case "$AKTIV" in
    blue)  ALT_PORT="$BG_BLUE_PORT" ;;
    green) ALT_PORT="$BG_GREEN_PORT" ;;
    *)
      write_incident critical "Vorheriger Slot unbekannt — kein Rückschaltziel. Manuelle Recovery nötig." >/dev/null
      state_update "{'emergency': True, 'last_fallback_at': now, 'fallback_count': s['fallback_count'] + 1}"
      log "KRITISCH: Vorheriger Slot unbekannt — Notfallmodus. Recovery: siehe ROLLBACK_AND_FALLBACK_REPORT.md."
      exit 70 ;;
  esac
  set_target "$ALT_PORT"
  # Rollback-Health-Check: der wiederhergestellte Slot muss selbst bereit sein
  if probe "$ALT_PORT" && curl -sf -m 5 "http://127.0.0.1:$BG_ENTRY_PORT$PROBE_PATH" >/dev/null; then
    state_update "{'active_slot': '$AKTIV', 'last_fallback_at': now, 'fallback_count': s['fallback_count'] + 1, 'blocked_releases': sorted(set(s['blocked_releases']) | {'$ZIEL_RELEASE'})}"
    persist_autostart "$AKTIV"
    stop_standby "$ZIEL"
    log "Rückschaltung auf $AKTIV erfolgreich; Release $ZIEL_RELEASE ist jetzt blockiert (Auto-Start folgt $AKTIV)."
  else
    # Beide ungesund: EIN Versuch wurde gemacht — kein Loop, klarer Notfallzustand.
    write_incident critical "Beide Slots ungesund: $ZIEL fiel im Fenster aus, $AKTIV besteht den Health-Check nach Rückschaltung nicht." >/dev/null
    state_update "{'active_slot': '$AKTIV', 'emergency': True, 'last_fallback_at': now, 'fallback_count': s['fallback_count'] + 1, 'blocked_releases': sorted(set(s['blocked_releases']) | {'$ZIEL_RELEASE'})}"
    log "KRITISCH: Auch $AKTIV ist nicht bereit — beide Ziele ungesund. NOTFALLMODUS:"
    log "  kein weiterer automatischer Wechsel; Logs: journalctl --user -u <slot-unit> -n 100"
    log "  Recovery-Befehle: ROLLBACK_AND_FALLBACK_REPORT.md (hub-audit)."
  fi
  exit 70
}

# --- 5. Sofort-Verifikation + Beobachtungsfenster ---------------------------------
if ! curl -sf -m 5 "http://127.0.0.1:$BG_ENTRY_PORT$PROBE_PATH" >/dev/null; then
  fallback "Entry Point besteht die Readiness-Probe direkt nach der Umschaltung nicht"
fi
log "Umschaltung aktiv — Beobachtungsfenster ${OBSERVE}s (Readiness-Polls durch den Entry Point) …"
ENDE=$((SECONDS + OBSERVE))
while [ $SECONDS -lt $ENDE ]; do
  if ! curl -sf -m 3 "http://127.0.0.1:$BG_ENTRY_PORT$PROBE_PATH" >/dev/null; then
    fallback "Readiness-Ausfall im Beobachtungsfenster (nach $((SECONDS - ENDE + OBSERVE))s)"
  fi
  sleep 1
done
log "Beobachtungsfenster bestanden: Entry Point :$BG_ENTRY_PORT bedient jetzt $ZIEL (:$ZIEL_PORT)."

# --- 6. Zustand atomar persistieren -------------------------------------------------
AKTIV_RELEASE="unbekannt"
AKTIV_MANIFEST="$BG_RELEASES_DIR/$AKTIV/release-manifest.json"
[ -f "$AKTIV_MANIFEST" ] && AKTIV_RELEASE=$(python3 -c "import json;print(json.load(open('$AKTIV_MANIFEST'))['release_id'])")
state_update "{'active_slot': '$ZIEL', 'previous_slot': '$AKTIV', 'active_release': '$ZIEL_RELEASE', 'previous_release': '$AKTIV_RELEASE', 'last_switch_at': now, 'switch_count': s['switch_count'] + 1, 'emergency': False}"
persist_autostart "$ZIEL"
stop_standby "$AKTIV"
log "slot-state.json aktualisiert (aktiv: $ZIEL, vorher: $AKTIV; Auto-Start folgt $ZIEL)."
