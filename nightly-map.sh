#!/usr/bin/env bash
# Nächtliches Deep-Mapping: alle aktivierten Projekte per graphify (AST + LLM-Semantik)
# neu extrahieren und in das Knowledge-Repo syncen.
#
# Backend, Modell und Projektliste kommen aus ~/.config/knowledge-mcp/config.yaml.
# Der API-Key liegt NUR im Vault und wird zur Laufzeit über die lokale UI-API geholt —
# er steht in keiner Datei auf der Platte. Semantische Extraktion ist pro Datei gecacht:
# unveränderte Dokumente kosten nichts.
set -uo pipefail

# Pfade aus dem Skript-Ort ableiten (funktioniert auch im Container unter /app)
HUB="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ENV_FILE="${KMCP_ENV_FILE:-$HOME/.config/knowledge-mcp/env}"
# set -a: alles aus der env-Datei wird exportiert, damit es auch die Kindprozesse
# (backup.py) erreicht — ohne das sieht nur die Shell selbst die Werte.
if [ -f "$ENV_FILE" ]; then set -a; source "$ENV_FILE"; set +a; fi
PY="$HUB/.venv/bin/python"; [ -x "$PY" ] || PY="$(command -v python3)"
GRAPHIFY="$(command -v graphify || echo "$HOME/.local/bin/graphify")"
GRAPHIFY_SYNC="$(command -v graphify-sync || echo "$HOME/.local/bin/graphify-sync")"
PORT="$("$PY" "$HUB/config.py" get server.port 2>/dev/null || echo 8300)"

LOG="${KMCP_DATA_DIR:-$HUB}/build-logs/nightly-$(date +%F).log"
mkdir -p "$(dirname "$LOG")"
exec >>"$LOG" 2>&1

# Backend-Konfiguration laden (BACKEND, MODEL, SECRET, ENVVAR, API_TIMEOUT, LOCAL)
eval "$("$PY" "$HUB/config.py" mapping)"
echo "=== nightly-map start $(date -Is) backend=$BACKEND model=$MODEL ==="

EXTRA_ARGS=()
if [ -n "$SECRET" ]; then
  KEY="$(curl -s -H "Authorization: Bearer $MCP_TOKEN" \
    "http://127.0.0.1:$PORT/ui/api/secrets/$SECRET" \
    | python3 -c 'import sys,json;print(json.load(sys.stdin).get("value",""))' 2>/dev/null)"
  if [ -z "$KEY" ]; then
    echo "HINWEIS: kein Key '$SECRET' im Vault — mappe nur Code (--code-only), Docs übersprungen"
    EXTRA_ARGS+=(--code-only)
  else
    export "$ENVVAR=$KEY"
  fi
elif [ -n "$LOCAL" ]; then
  # Lokales Backend (Ollama): Key ist nur ein Platzhalter, Dienst muss laufen.
  export "$ENVVAR=local"
  if ! curl -sf -m 3 http://127.0.0.1:11434/api/version > /dev/null; then
    echo "HINWEIS: Ollama antwortet nicht auf Port 11434 — mappe nur Code (--code-only)"
    EXTRA_ARGS+=(--code-only)
  fi
fi

mapfile -t PROJECTS < <("$PY" "$HUB/config.py" projects)
if [ ${#PROJECTS[@]} -eq 0 ]; then
  echo "Keine aktivierten Projekte in config.yaml — nichts zu tun."
  echo "=== nightly-map done $(date -Is) ==="
  exit 0
fi

# Vorab-Prüfung: erkennt die typischen Stolpersteine (fehlender Ordner, keine
# Leserechte, kein Schreibrecht für graphify-out), BEVOR graphify daran scheitert.
# Und was sich reparieren lässt, wird gleich repariert.
preflight() {
  local p="$1"
  [ -d "$p" ] || { echo "PROBLEM: Ordner existiert nicht"; return 1; }
  [ -r "$p" ] && [ -x "$p" ] || { echo "PROBLEM: keine Leserechte auf $p"; return 1; }
  local out="$p/graphify-out"
  if [ ! -d "$out" ]; then
    mkdir -p "$out" 2>/dev/null || { echo "PROBLEM: $out lässt sich nicht anlegen (Schreibrechte)"; return 1; }
    echo "  repariert: $out angelegt"
  fi
  [ -w "$out" ] || { echo "PROBLEM: $out ist nicht beschreibbar"; return 1; }
  return 0
}

for p in "${PROJECTS[@]}"; do
  echo "--- $p ($(date -Is))"
  if ! msg="$(preflight "$p")"; then
    echo "$msg"
    echo "extract ÜBERSPRUNGEN: $p — im Diagnose-Tab reparierbar"
    continue
  fi
  [ -n "$msg" ] && echo "$msg"
  # Eigene Extraktion (extraction.py) ist seit 2026-07-14 der Standard: inkrementell
  # (Datei-Hash-Cache, unveränderte Dateien kosten keinen LLM-Aufruf) und mit voller
  # Coverage (Compose, Configs, Docs — Benchmark: Lumo 3/3 statt 0/3). Clustering,
  # Report und graph.html liefert danach graphify cluster-only aus unserer graph.json.
  # Schlägt die eigene Extraktion fehl, übernimmt das klassische graphify extract.
  if [ ${#EXTRA_ARGS[@]} -eq 0 ] && "$PY" "$HUB/extraction.py" "$p"; then
    "$GRAPHIFY" cluster-only "$p" --no-label || echo "cluster-only fehlgeschlagen: $p"
  else
    echo "eigene Extraktion nicht möglich — Fallback auf graphify extract: $p"
    "$GRAPHIFY" extract "$p" \
      --backend "$BACKEND" --model "$MODEL" --api-timeout "$API_TIMEOUT" "${EXTRA_ARGS[@]}" \
      || { echo "extract FEHLGESCHLAGEN: $p"; continue; }
  fi

  # Bereiche benennen. OHNE diesen Schritt heißen alle neuen Bereiche in der Oberfläche
  # nur „Bereich 0, 1, 2…" — extract clustert zwar, vergibt aber keine Namen. Die
  # Benennung zerfiel dadurch bei jedem Nachtlauf wieder, sobald sich ein Projekt änderte.
  # --missing-only lässt bestehende Namen in Ruhe und benennt nur die neuen: kostet fast nichts.
  if [ ${#EXTRA_ARGS[@]} -eq 0 ]; then      # nur mit KI-Key sinnvoll (sonst --code-only)
    "$GRAPHIFY" label "$p" --missing-only --backend "$BACKEND" --model "$MODEL" \
      || echo "label fehlgeschlagen: $p (Bereiche bleiben unbenannt)"
  fi

  # Build-Vertrag: Manifest bindet graph/report/viewer an EINE Generation (hub-audit Run 7).
  "$PY" "$HUB/buildmeta.py" write "$p" || echo "PROBLEM: build-manifest fehlgeschlagen: $p"

  "$GRAPHIFY_SYNC" "$p" || echo "sync fehlgeschlagen: $p"
done

# Semantische Indizes für den neuen Stand neu bauen (lokal, kostenlos).
# graph_query prüft mtime und heilt sich zwar selbst, aber so zahlt kein
# Nutzer-Request die Index-Baukosten.
echo "--- Semantik-Index ($(date -Is))"
"$PY" - <<'PYEOF' || echo "Semantik-Index fehlgeschlagen (graph_query baut ihn bei Bedarf selbst)"
import sys
sys.path.insert(0, "/home/belkis/knowledge-mcp")
from pathlib import Path
import config
import semantic
root = Path.home() / "graphify-knowledge"
sources = {}
for e in config.project_entries():
    p = Path(e["path"]).expanduser()
    sources[p.name.lower()] = p
for d in sorted(root.iterdir()):
    if (d / "graphify-out" / "graph.json").exists():
        n = semantic.build_index(d)
        src = sources.get(d.name)
        c = semantic.build_chunk_index(d.name, src) if src and src.is_dir() else 0
        print(f"{d.name}: {n} Knoten, {c} Chunks indiziert")
PYEOF

# Verschlüsselte Sicherung (Vault + Schlüssel + Konfiguration) an alle Ziele.
# Läuft am Ende, damit die frischen Stände mit erfasst sind.
if [ -n "${BACKUP_PASSPHRASE:-}" ]; then
  echo "--- Sicherung ($(date -Is))"
  "$PY" "$HUB/backup.py" run || echo "SICHERUNG FEHLGESCHLAGEN"
else
  echo "--- Sicherung übersprungen: keine BACKUP_PASSPHRASE gesetzt"
fi

echo "=== nightly-map done $(date -Is) ==="
