# Knowledge Hub — Container-Image
# Enthält den Server, die Web-UI und graphify (fürs Mapping).
FROM python:3.12-slim

# git: graphify liest Repo-Historie; curl: Health-Check; tini: sauberes Signal-Handling
RUN apt-get update && apt-get install -y --no-install-recommends \
      git curl tini \
    && rm -rf /var/lib/apt/lists/*

# Nicht als root laufen
RUN useradd --create-home --uid 1000 hub
WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt \
    && pip install --no-cache-dir "graphifyy[openai]"

COPY --chown=hub:hub . /app
RUN chmod +x /app/nightly-map.sh /app/docker-entrypoint.sh 2>/dev/null || true

# /data muss dem Nutzer gehören, BEVOR das Volume angelegt wird — sonst erbt
# das Volume root-Rechte und der Server kann Vault/Logs nicht schreiben.
RUN mkdir -p /data /app/build-logs \
    && chown -R hub:hub /data /app/build-logs \
    && chmod 700 /data

USER hub

# Konfiguration + Secrets + Vault liegen im Volume (bleiben über Updates erhalten)
ENV KNOWLEDGE_CONFIG=/data/config.yaml \
    KMCP_ENV_FILE=/data/env \
    KMCP_DATA_DIR=/data \
    VAULT_PATH=/data/vault.enc \
    KNOWLEDGE_ROOT=/data/graphify-knowledge \
    KNOWLEDGE_HOST=0.0.0.0 \
    PYTHONUNBUFFERED=1
VOLUME ["/data"]

EXPOSE 8300
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s \
  CMD curl -sf http://127.0.0.1:8300/ui/setup/status || exit 1

ENTRYPOINT ["/usr/bin/tini", "--", "/app/docker-entrypoint.sh"]
CMD ["python", "server.py"]
