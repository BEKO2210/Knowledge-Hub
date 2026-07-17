# Knowledge Hub — Container-Image
# Enthält den Server, die Web-UI und graphify (fürs Mapping).
FROM python:3.12-slim

# git: graphify liest Repo-Historie; curl: Health-Check; tini: sauberes Signal-Handling
# rsync: graphify-sync spiegelt graphify-out/ ins Wissens-Repo (rsync -a --delete)
RUN apt-get update && apt-get install -y --no-install-recommends \
      git curl tini rsync \
    && rm -rf /var/lib/apt/lists/*

# Nicht als root laufen
RUN useradd --create-home --uid 1000 hub
WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt \
    && pip install --no-cache-dir "graphifyy[openai]"

COPY --chown=hub:hub . /app
# graphify-sync wird vom Wheel NICHT mitgeliefert — das Repo-Skript kommt in den PATH,
# sonst schlägt jeder Sync ins Wissens-Repo mit FileNotFoundError fehl.
RUN chmod +x /app/nightly-map.sh /app/docker-entrypoint.sh \
      /app/tools/graphify-sync /app/tools/graphify-cluster-force \
    && cp /app/tools/graphify-sync /usr/local/bin/graphify-sync

# /data muss dem Nutzer gehören, BEVOR das Volume angelegt wird — sonst erbt
# das Volume root-Rechte und der Server kann Vault/Logs nicht schreiben.
RUN mkdir -p /data /app/build-logs \
    && chown -R hub:hub /data /app/build-logs \
    && chmod 700 /data

USER hub

# Konfiguration + Secrets + Vault liegen im Volume (bleiben über Updates erhalten).
# KMCP_NOTES_ROOT gehört ebenfalls ins Volume — Notizen sonst bei Container-Recreate weg.
# GRAPHIFY_BIN/SYNC: pip installiert nach /usr/local/bin, nicht nach ~/.local/bin —
# ohne diese ENVs crasht jeder Build/Sync im Container mit FileNotFoundError.
ENV KNOWLEDGE_CONFIG=/data/config.yaml \
    KMCP_ENV_FILE=/data/env \
    KMCP_DATA_DIR=/data \
    VAULT_PATH=/data/vault.enc \
    KNOWLEDGE_ROOT=/data/graphify-knowledge \
    KMCP_NOTES_ROOT=/data/knowledge-notes \
    GRAPHIFY_BIN=/usr/local/bin/graphify \
    GRAPHIFY_SYNC=/usr/local/bin/graphify-sync \
    KNOWLEDGE_HOST=0.0.0.0 \
    PYTHONUNBUFFERED=1
VOLUME ["/data"]

EXPOSE 8300
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s \
  CMD curl -sf http://127.0.0.1:8300/ui/setup/status || exit 1

# Hinweis: Im Container gibt es kein systemd — die Diagnose-/Mapping-Checks melden
# systemctl-Abfragen daher als "unavailable" (im Code abgesichert, kein Crash).
# Der Nacht-Job wird vom Host per `docker compose exec` getriggert (siehe docker-compose.yml).

ENTRYPOINT ["/usr/bin/tini", "--", "/app/docker-entrypoint.sh"]
CMD ["python", "server.py"]
