#!/usr/bin/env bash
# Container-Start: beim ersten Lauf die Konfiguration ins Volume legen,
# danach den Server starten. Vorhandene Daten bleiben unangetastet.
set -e

if [ ! -f /data/config.yaml ] && [ -f /app/config.example.yaml ]; then
  cp /app/config.example.yaml /data/config.yaml
  echo "[hub] Standard-Konfiguration nach /data/config.yaml gelegt"
fi

# Wissenswurzel + Notizen auf frischem Volume anlegen — sonst liefern die
# Projekt-/Notiz-Endpunkte bis zum ersten Build FileNotFoundError.
mkdir -p "${KNOWLEDGE_ROOT:-/data/graphify-knowledge}" "${KMCP_NOTES_ROOT:-/data/knowledge-notes}"

# Secrets aus dem Volume in die Prozess-Umgebung laden (bei systemd macht das
# EnvironmentFile). Ohne das kennt der Server nach einem Neustart weder
# Vault-Schlüssel noch Zugangspasswort.
if [ -f /data/env ]; then
  set -a
  # shellcheck disable=SC1091
  . /data/env
  set +a
else
  echo "[hub] Noch nicht eingerichtet — Einrichtungs-Assistent im Browser öffnen."
fi

# Nacht-Mapping im Container: Standardmäßig triggert der Host (docker compose exec,
# siehe docker-compose.yml). Wer den Hub standalone (`docker run`) betreibt und keinen
# Host-Cron hat, setzt NIGHTLY_IN_CONTAINER=1 — dann läuft hier ein schlanker Scheduler,
# der nightly-map.sh täglich um 03:30 (Container-Zeit) startet. So hält der Container die
# über note_save/project_create gegebene Zusage „nightly mapping (03:30)" auch allein ein.
if [ "${NIGHTLY_IN_CONTAINER:-0}" = "1" ]; then
  (
    while true; do
      jetzt=$(date +%s)
      ziel=$(date -d "03:30 today" +%s)
      [ "$ziel" -le "$jetzt" ] && ziel=$(date -d "03:30 tomorrow" +%s)
      sleep "$((ziel - jetzt))"
      echo "[hub] Nacht-Mapping (In-Container-Scheduler) startet …"
      /app/nightly-map.sh || echo "[hub] Nacht-Mapping fehlgeschlagen (Lauf wird nächste Nacht erneut versucht)."
    done
  ) &
  echo "[hub] In-Container-Nacht-Mapping aktiv (täglich 03:30)."
fi

exec "$@"
