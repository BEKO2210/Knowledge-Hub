#!/usr/bin/env bash
# Schreibt release-manifest.json in ein Release-Verzeichnis (git worktree/checkout).
#   make-release-manifest.sh <release-dir>
set -euo pipefail
DIR="${1:?Aufruf: make-release-manifest.sh <release-dir>}"
cd "$DIR"
COMMIT=$(git rev-parse HEAD)
KURZ=$(git rev-parse --short HEAD)
STAMP=$(date -u +%Y%m%dT%H%M%SZ)
REQ_HASH=$(sha256sum requirements.txt | cut -c1-16)
PYV=$(.venv/bin/python --version 2>&1 | awk '{print $2}')
# Nur getrackte Dateien zählen: untracked Build-Artefakte (.venv) gehören zum Release-Build
DIRTY=$(git status --porcelain --untracked-files=no | wc -l)
[ "$DIRTY" -eq 0 ] || { echo "FEHLER: Release-Verzeichnis hat $DIRTY veränderte getrackte Dateien — Releases sind unveränderlich."; exit 65; }
python3 - <<PYEOF
import json
json.dump({
  "schema_version": "1.0",
  "release_id": "r-$STAMP-$KURZ",
  "commit": "$COMMIT",
  "built_at": "$STAMP",
  "python": "$PYV",
  "requirements_sha256_16": "$REQ_HASH",
}, open("release-manifest.json", "w"), indent=2)
PYEOF
echo "release-manifest.json: r-$STAMP-$KURZ"
