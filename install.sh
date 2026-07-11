#!/usr/bin/env bash
# Knowledge Hub — Ein-Befehl-Installation.
#
#   git clone <repo> ~/knowledge-hub && cd ~/knowledge-hub && ./install.sh
#
# Legt venv + Abhängigkeiten an, schreibt eine Standard-config.yaml, installiert die
# systemd-User-Dienste (Server + Nacht-Timer) und startet den Server. Passwort, Vault-Key
# und Token werden NICHT hier abgefragt — das erledigt der Erststart-Wizard im Browser.
#
# Idempotent: mehrfaches Ausführen aktualisiert nur, was fehlt oder veraltet ist.
set -euo pipefail

HUB="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CFG_DIR="${XDG_CONFIG_HOME:-$HOME/.config}/knowledge-mcp"
UNIT_DIR="${XDG_CONFIG_HOME:-$HOME/.config}/systemd/user"
PORT_DEFAULT=8300

c_ok()   { printf '\033[32m✓\033[0m %s\n' "$1"; }
c_info() { printf '\033[36m•\033[0m %s\n' "$1"; }
c_warn() { printf '\033[33m!\033[0m %s\n' "$1"; }
c_err()  { printf '\033[31m✗\033[0m %s\n' "$1" >&2; }

echo
echo "  Knowledge Hub — Installation"
echo "  ────────────────────────────"
echo

# --- 1. Voraussetzungen -----------------------------------------------------
command -v python3 >/dev/null || { c_err "python3 fehlt. Bitte installieren (z. B. apt install python3 python3-venv)."; exit 1; }
PY_OK=$(python3 -c 'import sys; print(1 if sys.version_info >= (3, 10) else 0)')
[ "$PY_OK" = "1" ] || { c_err "Python 3.10+ nötig (gefunden: $(python3 --version))."; exit 1; }
python3 -c 'import venv' 2>/dev/null || { c_err "python3-venv fehlt (apt install python3-venv)."; exit 1; }
command -v curl >/dev/null || { c_err "curl fehlt (apt install curl)."; exit 1; }
c_ok "Python $(python3 --version | cut -d' ' -f2) und curl gefunden"

# systemd nur nutzen, wenn die User-Instanz auch wirklich erreichbar ist
# (bei SSH ohne Session oder im Container fehlt der DBus — dann sauber ausweichen).
NO_SYSTEMD=""
if ! command -v systemctl >/dev/null || ! systemctl --user show-environment >/dev/null 2>&1; then
  NO_SYSTEMD=1
  c_warn "Kein nutzbarer systemd-Benutzerdienst — Dienste werden nicht eingerichtet."
fi

# --- 2. Virtuelle Umgebung + Abhängigkeiten ---------------------------------
if [ ! -d "$HUB/.venv" ]; then
  c_info "Lege virtuelle Umgebung an…"
  python3 -m venv "$HUB/.venv"
fi
c_info "Installiere Abhängigkeiten…"
"$HUB/.venv/bin/pip" install -q --upgrade pip
"$HUB/.venv/bin/pip" install -q -r "$HUB/requirements.txt"
c_ok "Abhängigkeiten installiert"

# --- 3. Konfiguration -------------------------------------------------------
mkdir -p "$CFG_DIR" && chmod 700 "$CFG_DIR"
if [ ! -f "$CFG_DIR/config.yaml" ]; then
  if [ -f "$HUB/config.example.yaml" ]; then
    cp "$HUB/config.example.yaml" "$CFG_DIR/config.yaml"
    c_ok "Standard-Konfiguration angelegt: $CFG_DIR/config.yaml"
  else
    c_warn "config.example.yaml fehlt — es gelten die eingebauten Standardwerte."
  fi
else
  c_ok "Vorhandene Konfiguration behalten: $CFG_DIR/config.yaml"
fi
PORT=$("$HUB/.venv/bin/python" "$HUB/config.py" get server.port 2>/dev/null || echo "$PORT_DEFAULT")

# graphify: nötig fürs Mapping, aber keine harte Voraussetzung für den Server
if ! command -v graphify >/dev/null && [ ! -x "$HOME/.local/bin/graphify" ]; then
  c_warn "graphify nicht gefunden — der Hub läuft, aber Projekte lassen sich noch nicht mappen."
  c_warn "Installation:  pipx install graphifyy   (oder: pip install --user graphifyy)"
fi

# --- 4. systemd-Dienste -----------------------------------------------------
if [ -z "${NO_SYSTEMD:-}" ]; then
  mkdir -p "$UNIT_DIR"

  cat > "$UNIT_DIR/knowledge-mcp.service" <<EOF
[Unit]
Description=Knowledge Hub (MCP-Server + Web-UI)
After=network.target

[Service]
EnvironmentFile=-$CFG_DIR/env
WorkingDirectory=$HUB
ExecStart=$HUB/.venv/bin/python server.py
Restart=always
RestartSec=5

[Install]
WantedBy=default.target
EOF

  cat > "$UNIT_DIR/nightly-map.service" <<EOF
[Unit]
Description=Knowledge Hub — nächtliches Deep-Mapping

[Service]
Type=oneshot
ExecStart=$HUB/nightly-map.sh
Nice=10
IOSchedulingClass=idle
EOF

  if [ ! -f "$UNIT_DIR/nightly-map.timer" ]; then
    cat > "$UNIT_DIR/nightly-map.timer" <<'EOF'
[Unit]
Description=Startet das nächtliche Deep-Mapping um 03:30

[Timer]
OnCalendar=*-*-* 03:30:00
Persistent=true
RandomizedDelaySec=600

[Install]
WantedBy=timers.target
EOF
  fi

  chmod +x "$HUB/nightly-map.sh"
  systemctl --user daemon-reload
  if systemctl --user enable --now knowledge-mcp.service >/dev/null 2>&1; then
    c_ok "Dienst knowledge-mcp gestartet (Port $PORT)"
  else
    c_err "Dienst ließ sich nicht starten:"
    systemctl --user status knowledge-mcp.service --no-pager -n 10 || true
    exit 1
  fi

  # Dienste sollen auch ohne aktive Anmeldung laufen
  if command -v loginctl >/dev/null && [ "$(loginctl show-user "$USER" --property=Linger --value 2>/dev/null)" != "yes" ]; then
    loginctl enable-linger "$USER" 2>/dev/null \
      && c_ok "Autostart ohne Login aktiviert (linger)" \
      || c_warn "Autostart ohne Login nicht aktiviert — bitte einmalig: sudo loginctl enable-linger $USER"
  fi
fi

# --- 5. Ohne systemd: Startbefehl ausgeben und hier enden -------------------
if [ -n "$NO_SYSTEMD" ]; then
  echo
  c_ok "Installation abgeschlossen."
  echo
  echo "    Server starten:"
  echo "      cd $HUB && .venv/bin/python server.py"
  echo
  echo "    Danach im Browser einrichten:  http://127.0.0.1:$PORT/ui"
  echo "    (Für automatischen Start empfiehlt sich Docker: docker compose up -d)"
  echo
  exit 0
fi

# --- 6. Bereitschaft prüfen -------------------------------------------------
for _ in $(seq 1 20); do
  curl -sf -m 2 "http://127.0.0.1:$PORT/ui/setup/status" >/dev/null && break
  sleep 0.5
done

if curl -sf -m 2 "http://127.0.0.1:$PORT/ui/setup/status" | grep -q '"configured":true'; then
  echo
  c_ok "Knowledge Hub läuft und ist bereits eingerichtet."
  echo
  echo "    Öffnen:  http://127.0.0.1:$PORT/ui"
  echo
elif curl -sf -m 2 "http://127.0.0.1:$PORT/ui/setup/status" >/dev/null 2>&1; then
  echo
  c_ok "Fertig! Jetzt im Browser einrichten:"
  echo
  echo "    →  http://127.0.0.1:$PORT/ui"
  echo
  echo "    Der Assistent fragt nur nach einem Zugangspasswort;"
  echo "    Vault-Schlüssel und API-Token werden automatisch erzeugt."
  echo
  echo "    Von außen erreichbar machen (optional): Reverse-Proxy oder"
  echo "    Cloudflare Tunnel auf 127.0.0.1:$PORT, danach die öffentliche"
  echo "    Adresse in $CFG_DIR/config.yaml unter server.public_url eintragen."
  echo
else
  c_err "Server antwortet nicht auf Port $PORT."
  echo "    Log ansehen:  journalctl --user -u knowledge-mcp -n 30 --no-pager"
  exit 1
fi
