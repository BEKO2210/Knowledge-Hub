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
# shellcheck source=/dev/null
if [ -f "$ENV_FILE" ]; then set -a; source "$ENV_FILE"; set +a; fi
PY="$HUB/.venv/bin/python"; [ -x "$PY" ] || PY="$(command -v python3)"
GRAPHIFY="$(command -v graphify || echo "$HOME/.local/bin/graphify")"
GRAPHIFY_SYNC="$(command -v graphify-sync || echo "$HOME/.local/bin/graphify-sync")"
PORT="$("$PY" "$HUB/config.py" get server.port 2>/dev/null || echo 8300)"

# Wissens-Repo: Umgebungsvariable schlägt Config (paths.knowledge_root),
# Config schlägt eingebauten Default — kein hartkodierter Heimatpfad mehr.
KNOWLEDGE_ROOT="${KNOWLEDGE_ROOT:-$("$PY" "$HUB/config.py" get paths.knowledge_root 2>/dev/null || echo "$HOME/graphify-knowledge")}"
KNOWLEDGE_ROOT="${KNOWLEDGE_ROOT/#\~/$HOME}"   # führendes ~ auflösen
# Export, damit Kindprozesse (graphify-sync, Semantik-Heredoc) die Werte sehen.
export HUB KNOWLEDGE_ROOT

LOGDIR="${KMCP_DATA_DIR:-$HUB}/build-logs"
LOG="$LOGDIR/nightly-$(date +%F).log"
mkdir -p "$LOGDIR"
exec >>"$LOG" 2>&1

# Backend-Konfiguration laden (BACKEND, MODEL, SECRET, ENVVAR, API_TIMEOUT, LOCAL)
eval "$("$PY" "$HUB/config.py" mapping)"
echo "=== nightly-map start $(date -Is) backend=$BACKEND model=$MODEL ==="
# Maschinenlesbares Lauf-Protokoll (Post-Run-40 Bug 1): die Historie liest ab jetzt
# build-logs/runs/run-*.json statt Regexe über diesen freien Logtext.
RUN_ID="$("$PY" "$HUB/runlog.py" start nightly "$BACKEND" "$MODEL" 2>/dev/null || echo "")"
runlog() { [ -n "$RUN_ID" ] && "$PY" "$HUB/runlog.py" "$@" 2>/dev/null || true; }

EXTRA_ARGS=()
if [ -n "$SECRET" ]; then
  KEY="$(curl -sf -m 10 -H "Authorization: Bearer ${MCP_TOKEN:-}" \
    "http://127.0.0.1:$PORT/ui/api/secrets/$SECRET" \
    | python3 -c 'import sys,json;print(json.load(sys.stdin).get("value",""))' 2>/dev/null)"
  if [ -z "$KEY" ]; then
    echo "HINWEIS: kein Key '$SECRET' im Vault — extraction.py mappt offline (Struktur: Überschriften, Definitionen, Config-Schlüssel); nur der graphify-Fallback bliebe --code-only"
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
  runlog finish "$RUN_ID"
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

LOCKDIR="${KMCP_LOCK_DIR:-$HOME/hub-data/locks}"
mkdir -p "$LOCKDIR"

for p in "${PROJECTS[@]}"; do
  echo "--- $p ($(date -Is))"
  # Projekt-Sperre (Run 9): gleicher Lock wie der graph_build-Worker (locks.py).
  # exec 8> schließt einen evtl. offenen fd der vorherigen Iteration automatisch.
  NAME_LC="$(basename "$p" | tr '[:upper:]' '[:lower:]')"
  exec 8>"$LOCKDIR/build-$NAME_LC.lock"
  if ! flock -w 60 8; then
    echo "ÜBERSPRUNGEN: $p ist seit 60s gesperrt (anderer Build läuft) — nächster Nachtlauf holt es nach"
    runlog project "$RUN_ID" "$p" skipped "gesperrt (anderer Build läuft)"
    continue
  fi
  if ! msg="$(preflight "$p")"; then
    echo "$msg"
    echo "extract ÜBERSPRUNGEN: $p — im Diagnose-Tab reparierbar"
    runlog project "$RUN_ID" "$p" skipped "$msg"
    continue
  fi
  [ -n "$msg" ] && echo "$msg"
  # Atomare Veröffentlichung (Run 8): aktuelle Generation sichern, bevor der Build sie anfasst.
  "$PY" "$HUB/buildmeta.py" snapshot "$p" >/dev/null 2>&1 || true
  # Eigene Extraktion (extraction.py) ist seit 2026-07-14 der Standard: inkrementell
  # (Datei-Hash-Cache, unveränderte Dateien kosten keinen LLM-Aufruf) und mit voller
  # Coverage (Compose, Configs, Docs — Benchmark: Lumo 3/3 statt 0/3). Clustering,
  # Report und graph.html liefert danach graphify cluster-only aus unserer graph.json.
  # extraction.py läuft IMMER zuerst — ohne Key/Guthaben schaltet es selbst auf
  # Offline-Struktur um (statt wie früher via --code-only Docs-Projekte leer zu lassen
  # und den Cluster-Schritt auf einer leeren graph.json crashen zu lassen). Nur wenn
  # extraction.py selbst scheitert, übernimmt das klassische graphify extract.
  if "$PY" "$HUB/extraction.py" "$p"; then
    if ! "$HUB/tools/graphify-cluster-force" "$p" --no-label; then
      echo "cluster-only fehlgeschlagen: $p — stelle vorherige Generation wieder her"
      "$PY" "$HUB/buildmeta.py" restore "$p" || echo "PROBLEM: restore fehlgeschlagen: $p"
      runlog project "$RUN_ID" "$p" failed "cluster-only fehlgeschlagen (vorherige Generation wiederhergestellt)"
      continue
    fi
  else
    echo "eigene Extraktion nicht möglich — Fallback auf graphify extract: $p"
    if ! "$GRAPHIFY" extract "$p" \
      --backend "$BACKEND" --model "$MODEL" --api-timeout "$API_TIMEOUT" "${EXTRA_ARGS[@]}"; then
      echo "extract FEHLGESCHLAGEN: $p — stelle vorherige Generation wieder her"
      "$PY" "$HUB/buildmeta.py" restore "$p" || echo "PROBLEM: restore fehlgeschlagen: $p"
      runlog project "$RUN_ID" "$p" failed "extract fehlgeschlagen (vorherige Generation wiederhergestellt)"
      continue
    fi
  fi

  # Bereiche benennen. OHNE diesen Schritt heißen alle neuen Bereiche in der Oberfläche
  # nur „Bereich 0, 1, 2…" — extract clustert zwar, vergibt aber keine Namen. Die
  # Benennung zerfiel dadurch bei jedem Nachtlauf wieder, sobald sich ein Projekt änderte.
  # --missing-only lässt bestehende Namen in Ruhe und benennt nur die neuen: kostet fast nichts.
  if [ ${#EXTRA_ARGS[@]} -eq 0 ]; then      # nur mit KI-Key sinnvoll (sonst --code-only)
    "$GRAPHIFY" label "$p" --missing-only --backend "$BACKEND" --model "$MODEL" \
      || echo "label fehlgeschlagen: $p (Bereiche bleiben unbenannt)"
  fi

  # Abnahme-Gate (Run 7+8): nur eine VALIDIERTE Generation bekommt ein Manifest und wird
  # veröffentlicht; ungültige Stände werden verworfen und die vorherige Generation kehrt zurück.
  if ! "$PY" "$HUB/buildmeta.py" finalize "$p"; then
    echo "Generation ABGELEHNT: $p — stelle vorherige wieder her"
    "$PY" "$HUB/buildmeta.py" restore "$p" || echo "PROBLEM: restore fehlgeschlagen: $p"
    runlog project "$RUN_ID" "$p" failed "Generation vom Abnahme-Gate abgelehnt"
    continue
  fi

  if "$GRAPHIFY_SYNC" "$p"; then
    runlog project "$RUN_ID" "$p" success
  else
    echo "sync fehlgeschlagen: $p"
    runlog project "$RUN_ID" "$p" success "sync fehlgeschlagen (Graph selbst ist abgenommen)"
  fi
  exec 8>&-   # Projekt-Sperre freigeben (continue-Pfade heilen sich beim nächsten exec 8> selbst)
done
exec 8>&-     # Sperre des letzten Projekts vor Index-Bau/Sicherung freigeben

# Semantische Indizes für den neuen Stand neu bauen (lokal, kostenlos).
# graph_query prüft mtime und heilt sich zwar selbst, aber so zahlt kein
# Nutzer-Request die Index-Baukosten.
echo "--- Semantik-Index ($(date -Is))"
"$PY" - <<'PYEOF' || echo "Semantik-Index fehlgeschlagen (graph_query baut ihn bei Bedarf selbst)"
import os
import sys

# HUB und KNOWLEDGE_ROOT kommen exportiert aus dem Shell-Skript — unter systemd
# ist cwd=$HOME, hartkodierte Entwicklerpfade funktionieren dort nicht.
sys.path.insert(0, os.environ["HUB"])
from pathlib import Path

import config
import semantic

root = Path(os.environ.get("KNOWLEDGE_ROOT", "~/graphify-knowledge")).expanduser()
if not root.is_dir():
    print(f"Wissens-Repo {root} existiert (noch) nicht — Index-Bau übersprungen")
    raise SystemExit(0)
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

# Log-Rotation: Nacht-Logs und maschinenlesbare Lauf-Protokolle wachsen sonst
# unbegrenzt (1 Log/Tag, 1 run-*.json/Lauf) — 60 Tage Aufbewahrung reichen für
# die Historie im Diagnose-Tab.
find "$LOGDIR" -maxdepth 1 -name 'nightly-*.log' -mtime +60 -delete 2>/dev/null || true
find "$LOGDIR/runs" -maxdepth 1 -name 'run-*.json' -mtime +60 -delete 2>/dev/null || true

runlog finish "$RUN_ID"
echo "=== nightly-map done $(date -Is) ==="
