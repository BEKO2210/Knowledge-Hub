#!/usr/bin/env bash
# Container-Start: beim ersten Lauf die Konfiguration ins Volume legen,
# danach den Server starten. Vorhandene Daten bleiben unangetastet.
set -e

if [ ! -f /data/config.yaml ] && [ -f /app/config.example.yaml ]; then
  cp /app/config.example.yaml /data/config.yaml
  echo "[hub] Standard-Konfiguration nach /data/config.yaml gelegt"
fi

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

exec "$@"
