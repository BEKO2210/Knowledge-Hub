#!/usr/bin/env bash
# Schreibt release-manifest.json in ein Release-Verzeichnis (git worktree/checkout).
#   make-release-manifest.sh <release-dir>
#
# Das Manifest ist der Konsistenz-Anker des Blue-Green-Deployments: volle
# Checksummen aller getrackten Dateien, atomares Schreiben (tmp+fsync+rename)
# und eine Selbstprüfung direkt danach — switch.sh soll nie auf ein trunkiertes
# oder halb geschriebenes Release losgehen.
set -euo pipefail
DIR="${1:?Aufruf: make-release-manifest.sh <release-dir>}"
cd "$DIR"
COMMIT=$(git rev-parse HEAD)
KURZ=$(git rev-parse --short HEAD)
STAMP=$(date -u +%Y%m%dT%H%M%SZ)
REQ_HASH=$(sha256sum requirements.txt | cut -d' ' -f1)
PYV=$(.venv/bin/python --version 2>&1 | awk '{print $2}')
# Nur getrackte Dateien zählen: untracked Build-Artefakte (.venv) gehören zum Release-Build
DIRTY=$(git status --porcelain --untracked-files=no | wc -l)
[ "$DIRTY" -eq 0 ] || { echo "FEHLER: Release-Verzeichnis hat $DIRTY veränderte getrackte Dateien — Releases sind unveränderlich."; exit 65; }
RELEASE_ID=$(python3 - "$COMMIT" "$KURZ" "$STAMP" "$REQ_HASH" "$PYV" <<'PYEOF'
import hashlib
import json
import os
import secrets
import subprocess
import sys
import tempfile

commit, kurz, stamp, req_hash, pyv = sys.argv[1:6]

# Vollständigkeit: Checksumme jeder getrackten Datei des Release-Baums.
dateien = {}
listing = subprocess.run(["git", "ls-files", "-z"], check=True, capture_output=True)
for pfad in listing.stdout.decode("utf-8", "surrogateescape").split("\0"):
    if not pfad or pfad == "release-manifest.json":
        continue
    with open(pfad, "rb") as f:
        dateien[pfad] = hashlib.sha256(f.read()).hexdigest()

manifest = {
    "schema_version": "1.0",
    # Sekundenauflösung + Zufallsanteil: zwei Builds in derselben Sekunde
    # dürfen nicht dieselbe release_id erhalten.
    "release_id": f"r-{stamp}-{kurz}-{secrets.token_hex(3)}",
    "commit": commit,
    "built_at": stamp,
    "python": pyv,
    "requirements_sha256": req_hash,
    "file_count": len(dateien),
    "files_sha256": dateien,
}

# Atomar schreiben: ein Abbruch darf kein trunkiertes Manifest hinterlassen.
fd, tmp = tempfile.mkstemp(dir=".")
with os.fdopen(fd, "w") as f:
    json.dump(manifest, f, indent=2)
    f.flush()
    os.fsync(f.fileno())
os.replace(tmp, "release-manifest.json")

# Selbstprüfung: lesbar, vollständig, Checksummen konsistent.
with open("release-manifest.json") as f:
    geladen = json.load(f)
for schluessel in ("release_id", "commit", "built_at", "files_sha256"):
    if not geladen.get(schluessel):
        raise SystemExit(f"FEHLER: Manifest unvollständig — '{schluessel}' fehlt")
if geladen["commit"] != commit:
    raise SystemExit("FEHLER: Manifest-Commit weicht vom HEAD ab")
for pfad, soll in geladen["files_sha256"].items():
    with open(pfad, "rb") as f:
        if hashlib.sha256(f.read()).hexdigest() != soll:
            raise SystemExit(f"FEHLER: Checksumme passt nicht: {pfad}")
print(manifest["release_id"])
PYEOF
)
echo "release-manifest.json: $RELEASE_ID"
