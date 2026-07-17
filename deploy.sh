#!/usr/bin/env bash
# Knowledge Hub auf dem eigenen Server ausrollen (Ein-Unit-Installation).
# Für Blue-Green-Installationen (bluegreen/) stattdessen switch.sh nutzen —
# ein Restart der Einzel-Unit kollidiert dort mit dem Entry-Port.
#
# Der Ablauf ist bewusst feige: Erst prüfen, dann erst anfassen. Und wenn der Hub
# nach dem Neustart nicht antwortet, wird automatisch zurückgerollt — ein kaputter
# Hub bedeutet, dass du an deinen eigenen Vault nicht mehr herankommst.
#
#   ./deploy.sh            # Update holen, prüfen, ausrollen, Gesundheit testen
#   ./deploy.sh --pruefen  # nur prüfen, nichts anfassen
#   ./deploy.sh --rollback # auf den vor dem letzten Ausrollen gesicherten Stand zurück
#
# Rollback-Vertrag: das Skript holt das Update SELBST (git pull --ff-only) und
# sichert den Commit VOR dem Pull als Rollback-Ref dauerhaft in
# ${XDG_STATE_HOME:-~/.local/state}/knowledge-hub/rollback-ziel. --rollback und
# der automatische Rückfall nach fehlgeschlagener Gesundheitsprüfung setzen per
# „git reset --hard" auf genau diesen Ref zurück — niemals auf den gerade
# (fehl-)deployten Stand. Kam der neue Stand per externem Pull ins Repo, wird
# ORIG_HEAD (Stand vor dem letzten Merge) als Rollback-Ref genutzt.
set -euo pipefail

HUB="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$HUB"
PY="$HUB/.venv/bin/python"
DIENST="knowledge-mcp"
STATE_DIR="${XDG_STATE_HOME:-$HOME/.local/state}/knowledge-hub"
ROLLBACK_DATEI="$STATE_DIR/rollback-ziel"

rot()  { printf '\033[31m✗ %s\033[0m\n' "$1"; }
gruen(){ printf '\033[32m✓ %s\033[0m\n' "$1"; }
info() { printf '\033[36m→ %s\033[0m\n' "$1"; }

NUR_PRUEFEN=0
ROLLBACK_MODUS=0
case "${1:-}" in
  "") ;;
  --pruefen)  NUR_PRUEFEN=1 ;;
  --rollback) ROLLBACK_MODUS=1 ;;
  *) echo "Aufruf: $0 [--pruefen|--rollback]" >&2; exit 2 ;;
esac

# --- 0. Voraussetzungen ----------------------------------------------------------
command -v git  >/dev/null || { rot "git fehlt — ohne Versionskontrolle kein sicheres Ausrollen"; exit 1; }
command -v curl >/dev/null || { rot "curl fehlt (apt install curl)"; exit 1; }
[ -x "$PY" ] || { rot "Kein lauffähiges .venv ($PY) — erst ./install.sh ausführen"; exit 1; }
systemctl --user show-environment >/dev/null 2>&1 \
  || { rot "systemd-Benutzerdienst nicht erreichbar — Dienst $DIENST lässt sich nicht steuern"; exit 1; }

# --- Rollback-Funktion -------------------------------------------------------------
zurueckrollen() { # zurueckrollen <commit> — auf den gesicherten Stand zurück + neu starten
  local ziel="$1"
  if [ -n "$(git status --porcelain)" ]; then
    rot "ACHTUNG: unkommittierte Änderungen gehen durch das Zurückrollen verloren:"
    git status --porcelain | sed 's/^/    /'
  fi
  git reset --hard "$ziel"
  systemctl --user restart "$DIENST"
  rot "Zurückgerollt auf $ziel. Bitte 'journalctl --user -u $DIENST -n 50' ansehen."
}

# --- Modus: nur zurückrollen ---------------------------------------------------------
if [ "$ROLLBACK_MODUS" = 1 ]; then
  [ -s "$ROLLBACK_DATEI" ] || { rot "Kein gesichertes Rollback-Ziel ($ROLLBACK_DATEI fehlt)"; exit 1; }
  info "Rolle zurück auf $(cat "$ROLLBACK_DATEI")"
  zurueckrollen "$(cat "$ROLLBACK_DATEI")"
  exit 0
fi

# --- Prüffunktion (Lint, Tests, Oberfläche) -------------------------------------------
pruefe_alles() {
  info "Lint"
  "$PY" -m ruff check . || { rot "Lint fehlgeschlagen"; return 1; }
  gruen "Lint sauber"
  info "Tests"
  "$PY" -m pytest -q || { rot "Tests fehlgeschlagen"; return 1; }
  gruen "Tests grün"
  info "Oberfläche vollständig?"
  local f
  for f in web/index.html web/app.css web/app.js; do
    [ -s "$f" ] || { rot "$f fehlt oder ist leer"; return 1; }
  done
  "$PY" -c "import ui; assert ui.ASSET_V" || { rot "Hub lässt sich nicht importieren"; return 1; }
  gruen "Oberfläche vollständig"
}

if [ "$NUR_PRUEFEN" = 1 ]; then
  pruefe_alles || { rot "Prüfung fehlgeschlagen — nichts ausgerollt"; exit 1; }
  gruen "Alles in Ordnung (nur geprüft, nichts geändert)"
  exit 0
fi

# --- 1. Stand VOR dem Update sichern ---------------------------------------------------
# Das Rollback-Ziel muss der Stand VOR dem Update sein — nicht der gerade
# ausgerollte Commit (der alte Fehler: VORHER wurde erst nach einem externen
# Pull gelesen und zeigte damit auf den kaputten Stand selbst).
GIT_OK=1
git rev-parse --git-dir >/dev/null 2>&1 || GIT_OK=0
VORHER="-"
ORIG_VORHER=""
if [ "$GIT_OK" = 1 ]; then
  VORHER="$(git rev-parse HEAD)"
  # ORIG_HEAD VOR dem eigenen Pull merken: kam der neue Stand per externem
  # `git pull` ins Repo, liegt dort der Stand davor — ein eigener (no-op) Pull
  # würde ORIG_HEAD sonst mit dem aktuellen HEAD überschreiben.
  ORIG_VORHER="$(git rev-parse --verify ORIG_HEAD 2>/dev/null || true)"
fi
info "Stand vor dem Ausrollen: $VORHER"

# --- 2. Update holen --------------------------------------------------------------------
if [ "$GIT_OK" = 1 ]; then
  # Das Skript holt das Update selbst: nur so ist der vorherige Stand bekannt.
  if ! git pull --ff-only; then
    rot "git pull fehlgeschlagen (offline? kein fast-forward?) — es wird der aktuelle Arbeitsbaum-Stand ausgerollt."
  fi
else
  rot "Kein Git-Repository — es wird nur neu gestartet, Zurückrollen ist nicht möglich."
fi

# Rollback-Ziel bestimmen und dauerhaft sichern:
#   - dieses Skript hat aktualisiert  → der Stand von vor dem Pull
#   - Update kam von außen (pull vor dem Aufruf) → ORIG_HEAD (Stand vor dem letzten Merge)
ROLLBACK_ZIEL=""
if [ "$GIT_OK" = 1 ]; then
  JETZT="$(git rev-parse HEAD)"
  if [ "$VORHER" != "$JETZT" ]; then
    ROLLBACK_ZIEL="$VORHER"
  elif [ -n "$ORIG_VORHER" ] && [ "$ORIG_VORHER" != "$JETZT" ] \
    && git merge-base --is-ancestor "$ORIG_VORHER" "$JETZT" 2>/dev/null; then
    ROLLBACK_ZIEL="$ORIG_VORHER"
  fi
fi
if [ -z "$ROLLBACK_ZIEL" ] && [ -s "$ROLLBACK_DATEI" ]; then
  ROLLBACK_ZIEL="$(cat "$ROLLBACK_DATEI")"   # letztes bekanntes Ziel (z. B. erneutes Ausrollen desselben Stands)
fi
if [ -n "$ROLLBACK_ZIEL" ]; then
  mkdir -p "$STATE_DIR"
  echo "$ROLLBACK_ZIEL" > "$ROLLBACK_DATEI"
  info "Rollback-Ziel gesichert: $ROLLBACK_ZIEL"
else
  rot "Kein früherer Stand bekannt — beim Fehlschlag wird nur neu gestartet, nicht zurückgerollt."
fi

# --- 3. Prüfen (auf dem neuen Stand) ------------------------------------------------------
if ! pruefe_alles; then
  rot "Prüfung fehlgeschlagen — der Dienst wurde NICHT neu gestartet und läuft auf dem alten Stand."
  rot "Der Arbeitsbaum enthält den neuen, ungeprüften Stand; bei Bedarf: ./deploy.sh --rollback"
  exit 1
fi

# --- 4. Ausrollen --------------------------------------------------------------------------
info "Dienst neu starten"
systemctl --user restart "$DIENST"

# --- 5. Gesundheit prüfen (und notfalls zurückrollen) ---------------------------------------
PORT="$("$PY" config.py get server.port 2>/dev/null || echo 8300)"
HOST="$("$PY" config.py get server.host 2>/dev/null || echo 127.0.0.1)"
case "$HOST" in 0.0.0.0|::|"") HOST=127.0.0.1 ;; esac
for _ in $(seq 1 20); do
  if curl -sf -m 2 "http://$HOST:$PORT/ui" >/dev/null 2>&1; then
    gruen "Hub antwortet auf Port $PORT"
    systemctl --user is-active --quiet "$DIENST" && gruen "Dienst läuft"
    exit 0
  fi
  sleep 1
done

rot "Hub antwortet nicht (20 Versuche à bis zu 3s)."
if [ -n "$ROLLBACK_ZIEL" ]; then
  rot "Rolle zurück auf $ROLLBACK_ZIEL"
  zurueckrollen "$ROLLBACK_ZIEL"
else
  systemctl --user restart "$DIENST" || true
  rot "Kein Rollback-Ziel bekannt — Dienst nur neu gestartet. Bitte 'journalctl --user -u $DIENST -n 50' ansehen."
fi
exit 1
