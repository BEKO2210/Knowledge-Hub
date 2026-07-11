"""Testumgebung: vollständig isoliert vom echten Hub.

WICHTIG: Die Module lesen ihre Pfade beim Import aus der Umgebung. Deshalb werden
die Variablen hier gesetzt, BEVOR irgendetwas importiert wird — sonst würde die
Suite den echten Vault und die echte Konfiguration anfassen.
"""

from __future__ import annotations

import atexit
import base64
import os
import shutil
import tempfile
from pathlib import Path

_TMP = Path(tempfile.mkdtemp(prefix="kmcp-test-"))
atexit.register(shutil.rmtree, _TMP, True)

TEST_PASSWORD = "test-passwort-123"
TEST_MCP_TOKEN = "kmcp_test_static_token"
TEST_VAULT_KEY = base64.urlsafe_b64encode(b"\x11" * 32).decode()

(_TMP / "config.yaml").write_text(
    "server:\n"
    "  port: 8399\n"
    "  public_url: https://test.invalid\n"
    "paths:\n"
    f"  knowledge_root: {_TMP / 'projects'}\n"
    f"  graphify_bin: {_TMP / 'graphify'}\n"
    "branding:\n"
    "  name: Test Hub\n",
    encoding="utf-8",
)
(_TMP / "projects").mkdir()

# Eine eigene env-Datei. Ohne sie fiele setup_wizard.is_configured() auf
# ~/.config/knowledge-mcp/env zurück: Auf einem Entwicklerrechner existiert die und
# die Tests liefen grün — auf einer frischen Maschine (CI) nicht, und der Hub zeigte
# statt der Oberfläche den Erststart-Assistenten. Genau das hat CI aufgedeckt.
(_TMP / "env").write_text(
    f"VAULT_KEY={TEST_VAULT_KEY}\nMCP_TOKEN={TEST_MCP_TOKEN}\n", encoding="utf-8"
)

os.environ.update(
    KNOWLEDGE_CONFIG=str(_TMP / "config.yaml"),
    KMCP_ENV_FILE=str(_TMP / "env"),
    VAULT_PATH=str(_TMP / "vault.enc"),
    KMCP_DATA_DIR=str(_TMP),
    KNOWLEDGE_ROOT=str(_TMP / "projects"),
    MCP_TOKEN=TEST_MCP_TOKEN,
    OAUTH_PASSWORD="",
    VAULT_KEY=TEST_VAULT_KEY,
)

import pytest  # noqa: E402
from starlette.testclient import TestClient  # noqa: E402

import ratelimit  # noqa: E402
import vault  # noqa: E402

TMP = _TMP


@pytest.fixture(autouse=True)
def fresh_state():
    """Jeder Test startet mit leerem Vault, leerem Rate-Limit und leerem OAuth-Zustand."""
    for f in ("vault.enc", "audit.log", "ratelimit.json", "oauth_state.json"):
        (_TMP / f).unlink(missing_ok=True)
    vault.lock()
    ratelimit._fails.clear()   # der Zähler lebt im Speicher, nicht nur in der Datei
    yield
    vault.lock()


@pytest.fixture
def fresh_vault():
    """Ein frisch angelegter, entsperrter Vault mit bekanntem Passwort."""
    vault.init(TEST_PASSWORD)
    return vault


@pytest.fixture
def client():
    """HTTP-Client gegen die echte ASGI-App inklusive BearerGate.

    raise_server_exceptions=False: Sonst wirft der Testclient unerwartete Fehler direkt
    durch, statt die Antwort zu liefern, die der echte Server erzeugt. Wir wollen aber
    genau prüfen, WAS beim Aufrufer ankommt (500 + Referenz, kein Traceback).
    """
    import server

    with TestClient(server.application, raise_server_exceptions=False) as c:
        yield c


@pytest.fixture
def auth():
    return {"Authorization": f"Bearer {TEST_MCP_TOKEN}"}
