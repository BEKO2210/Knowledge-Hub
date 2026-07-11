#!/usr/bin/env bash
# Knowledge Hub auf dem eigenen Server ausrollen.
#
# Der Ablauf ist bewusst feige: Erst prüfen, dann erst anfassen. Und wenn der Hub
# nach dem Neustart nicht antwortet, wird automatisch zurückgerollt — ein kaputter
# Hub bedeutet, dass du an deinen eigenen Vault nicht mehr herankommst.
#
#   ./deploy.sh            # prüfen, ausrollen, Gesundheit testen
#   ./deploy.sh --pruefen  # nur prüfen, nichts anfassen
set -euo pipefail

HUB="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$HUB"
PY="$HUB/.venv/bin/python"
DIENST="knowledge-mcp"
NUR_PRUEFEN=0
[ "${1:-}" = "--pruefen" ] && NUR_PRUEFEN=1

rot()  { printf '\033[31m✗ %s\033[0m\n' "$1"; }
gruen(){ printf '\033[32m✓ %s\033[0m\n' "$1"; }
info() { printf '\033[36m→ %s\033[0m\n' "$1"; }

# --- 1. Prüfen -----------------------------------------------------------------
info "Lint"
"$PY" -m ruff check . || { rot "Lint fehlgeschlagen — nichts ausgerollt"; exit 1; }
gruen "Lint sauber"

info "Tests"
"$PY" -m pytest -q || { rot "Tests fehlgeschlagen — nichts ausgerollt"; exit 1; }
gruen "Tests grün"

info "Oberfläche vollständig?"
for f in web/index.html web/app.css web/app.js; do
  [ -s "$f" ] || { rot "$f fehlt oder ist leer"; exit 1; }
done
"$PY" -c "import ui; assert ui.ASSET_V" || { rot "Hub lässt sich nicht importieren"; exit 1; }
gruen "Oberfläche vollständig"

if [ "$NUR_PRUEFEN" = 1 ]; then
  gruen "Alles in Ordnung (nur geprüft, nichts geändert)"
  exit 0
fi

# --- 2. Sicherung vor dem Eingriff ---------------------------------------------
VORHER="$(git rev-parse HEAD 2>/dev/null || echo '-')"
info "Stand vor dem Ausrollen: $VORHER"

# --- 3. Ausrollen ---------------------------------------------------------------
info "Dienst neu starten"
systemctl --user restart "$DIENST"

# --- 4. Gesundheit prüfen (und notfalls zurückrollen) ---------------------------
PORT="$("$PY" config.py get server.port 2>/dev/null || echo 8300)"
for i in $(seq 1 20); do
  if curl -sf -m 2 "http://127.0.0.1:$PORT/ui" >/dev/null 2>&1; then
    gruen "Hub antwortet auf Port $PORT"
    systemctl --user is-active --quiet "$DIENST" && gruen "Dienst läuft"
    exit 0
  fi
  sleep 1
done

rot "Hub antwortet nach 20s nicht — rolle zurück"
if [ "$VORHER" != "-" ]; then
  git reset --hard "$VORHER"
  systemctl --user restart "$DIENST"
  rot "Zurückgerollt auf $VORHER. Bitte 'journalctl --user -u $DIENST -n 50' ansehen."
fi
exit 1
