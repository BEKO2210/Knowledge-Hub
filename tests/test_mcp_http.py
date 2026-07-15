"""Die MCP-Werkzeuge über ECHTES Streamable HTTP (Audit-Run 15).

test_mcp_protokoll.py fährt den fastmcp-In-Memory-Client — richtig fürs Protokoll,
aber ohne Netzwerk und ohne BearerGate. Hier läuft der volle ASGI-Stack in einem
uvicorn-Thread (mit initialisierter Task-Group, kein bare-TestClient-Artefakt), und
ein echter fastmcp-Client verbindet sich per StreamableHttpTransport mit Bearer-Token
durch das Gate. Zusätzlich: derselbe Zustand über MCP, HTTP, UI und die Datei.

Kein pytest-asyncio: die Aufrufe laufen über asyncio.run, wie in test_mcp_protokoll.
"""

from __future__ import annotations

import asyncio
import json
import socket
import threading
import time

import httpx
import pytest
import uvicorn
from conftest import TEST_MCP_TOKEN, TMP
from fastmcp import Client
from fastmcp.client.auth import BearerAuth
from fastmcp.client.transports import StreamableHttpTransport

import config
import server
import vault


def _freier_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture(scope="module")
def hub():
    """Echter ASGI-Stack (BearerGate + FastMCP-Lifespan) in einem uvicorn-Thread."""
    port = _freier_port()
    cfg = uvicorn.Config(server.application, host="127.0.0.1", port=port, log_level="error")
    srv = uvicorn.Server(cfg)
    t = threading.Thread(target=srv.run, daemon=True)
    t.start()
    for _ in range(100):
        if srv.started:
            break
        time.sleep(0.05)
    assert srv.started, "Server ist nicht hochgekommen"
    yield f"http://127.0.0.1:{port}"
    srv.should_exit = True
    t.join(timeout=5)


@pytest.fixture(autouse=True)
def konfiguration_aufraeumen():
    """note_save/project_create tragen Projekte in die geteilte Test-Config ein."""
    vorher = config.project_entries()
    yield
    config.save_projects(vorher)


def _mcp(hub_url):
    return Client(StreamableHttpTransport(f"{hub_url}/mcp", auth=BearerAuth(TEST_MCP_TOKEN)))


def _lauf(coro_factory):
    return asyncio.run(coro_factory())


ALLE_WERKZEUGE = {
    "projects_list",
    "graph_query",
    "graph_explain",
    "graph_path",
    "report_get",
    "graph_build",
    "graph_build_status",
    "secret_list",
    "secret_get",
    "secret_set",
    "secret_delete",
    "note_save",
    "note_list",
    "project_create",
}


def test_handshake_ohne_token_wird_abgewiesen(hub):
    """Der MCP-Handshake über HTTP muss ohne Bearer-Token scheitern (BearerGate)."""

    async def arbeit():
        with pytest.raises(Exception) as exc:  # noqa: PT011 - Transportfehler, Typ variiert
            async with Client(StreamableHttpTransport(f"{hub}/mcp")) as c:
                await c.list_tools()
        return str(exc.value)

    meldung = _lauf(arbeit)
    assert "401" in meldung or "unauthor" in meldung.lower(), meldung


def test_werkzeugliste_ueber_http_vollstaendig(hub, fresh_vault):
    async def arbeit():
        async with _mcp(hub) as c:
            return {t.name for t in await c.list_tools()}

    assert _lauf(arbeit) == ALLE_WERKZEUGE


def test_secret_roundtrip_und_verstecktes_secret_ueber_http(hub, fresh_vault):
    vault.secret_set("__2fa__", "SEED", client="test")

    async def arbeit():
        async with _mcp(hub) as c:
            await c.call_tool("secret_set", {"name": "http_key", "value": "via-mcp-http"})
            liste = list((await c.call_tool("secret_list", {})).data)
            wert = (await c.call_tool("secret_get", {"name": "http_key"})).content[0].text
            # verstecktes 2FA-Secret über MCP unsichtbar/unantastbar
            fehler = []
            for tool, args in (
                ("secret_get", {"name": "__2fa__"}),
                ("secret_delete", {"name": "__2fa__"}),
                ("secret_set", {"name": "__2fa__", "value": "x"}),
            ):
                try:
                    await c.call_tool(tool, args)
                except Exception as e:  # noqa: BLE001
                    fehler.append("no secret named" in str(e))
            return liste, wert, fehler

    liste, wert, fehler = _lauf(arbeit)
    assert "http_key" in liste and "__2fa__" not in liste
    assert wert == "via-mcp-http"
    assert fehler == [True, True, True]
    assert vault.secret_get("__2fa__", client="test") == "SEED"


def test_vier_wege_vergleich_secret_mcp_http_datei(hub, fresh_vault):
    """Derselbe Secret-Zustand über MCP, HTTP-API (=UI-Quelle) und die persistierte Datei."""

    async def arbeit():
        async with _mcp(hub) as c:
            await c.call_tool("secret_set", {"name": "vier_wege", "value": "w"})
            mcp_liste = list((await c.call_tool("secret_list", {})).data)
        async with httpx.AsyncClient() as hc:
            http_liste = (
                await hc.get(f"{hub}/ui/api/secrets", headers={"Authorization": f"Bearer {TEST_MCP_TOKEN}"})
            ).json()
        return mcp_liste, http_liste

    mcp_liste, http_liste = _lauf(arbeit)
    datei_liste = [s for s in vault.secret_list(client="test") if not s.startswith("__")]
    assert "vier_wege" in mcp_liste
    assert "vier_wege" in http_liste
    assert "vier_wege" in datei_liste


def test_vier_wege_vergleich_projekt_mcp_http_datei(hub, fresh_vault, monkeypatch):
    """projects_list (MCP) == /ui/api/projects (HTTP) == graph.json (Datei)."""
    projekt = TMP / "projects" / "vergleich" / "graphify-out"
    projekt.mkdir(parents=True, exist_ok=True)
    projekt.joinpath("graph.json").write_text(
        json.dumps(
            {
                "nodes": [{"id": "a", "community": 1}, {"id": "b", "community": 1}],
                "links": [{"source": "a", "target": "b"}],
            }
        )
    )

    async def arbeit():
        async with _mcp(hub) as c:
            mcp_proj = list((await c.call_tool("projects_list", {})).data)
        async with httpx.AsyncClient() as hc:
            http_proj = (
                await hc.get(f"{hub}/ui/api/projects", headers={"Authorization": f"Bearer {TEST_MCP_TOKEN}"})
            ).json()
        return mcp_proj, http_proj

    mcp_proj, http_proj = _lauf(arbeit)
    datei_nodes = len(json.loads(projekt.joinpath("graph.json").read_text())["nodes"])
    mcp_v = next(p for p in mcp_proj if p["project"] == "vergleich")
    http_v = next(p for p in http_proj if p["project"] == "vergleich")
    assert mcp_v["nodes"] == http_v["nodes"] == datei_nodes == 2


def test_note_vier_wege_mcp_und_datei(hub, fresh_vault):
    """note_save (MCP über HTTP) landet als Datei; note_list (MCP) == Dateien auf der Platte."""

    async def arbeit():
        async with _mcp(hub) as c:
            r = (
                (
                    await c.call_tool(
                        "note_save", {"project": "http-notiz", "title": "Titel", "content": "Inhalt"}
                    )
                )
                .content[0]
                .text
            )
            liste = sorted((await c.call_tool("note_list", {"project": "http-notiz"})).data)
        return r, liste

    text, mcp_liste = _lauf(arbeit)
    datei_liste = sorted(f.name for f in (TMP / "notes" / "http-notiz").glob("*.md"))
    assert "saved" in text
    assert mcp_liste == datei_liste
    assert len(mcp_liste) == 1


def test_fehlerfaelle_ueber_http(hub, fresh_vault):
    """Ein Querschnitt der Fehlerverträge über das echte Protokoll."""

    async def arbeit():
        out = {}
        async with _mcp(hub) as c:

            async def fehler(tool, args):
                try:
                    await c.call_tool(tool, args)
                    return None
                except Exception as e:  # noqa: BLE001
                    return str(e)

            out["unbekanntes_projekt"] = await fehler(
                "graph_query", {"project": "../../etc", "question": "x"}
            )
            out["ungueltiger_name"] = await fehler("secret_set", {"name": "bad/../x@!", "value": "v"})
            out["wertgrenze"] = await fehler("secret_set", {"name": "gross", "value": "x" * 20001})
            out["graph_build_extern"] = await fehler("graph_build", {"project": "/etc"})
            out["leerer_projektname"] = await fehler("project_create", {"name": "!!!"})
            out["unbekannter_build"] = await fehler("graph_build_status", {"project": "nie-gebaut"})
        return out

    out = _lauf(arbeit)
    assert out["unbekanntes_projekt"] and "unknown project" in out["unbekanntes_projekt"]
    assert out["ungueltiger_name"] and "Ungültiger Name" in out["ungueltiger_name"]
    assert out["wertgrenze"] and "zu lang" in out["wertgrenze"]
    assert out["graph_build_extern"] and "home directory" in out["graph_build_extern"]
    assert out["leerer_projektname"] and "letters or digits" in out["leerer_projektname"]
    assert out["unbekannter_build"] and "no build known" in out["unbekannter_build"]


def test_project_create_idempotent_ueber_http(hub, fresh_vault):
    async def arbeit():
        async with _mcp(hub) as c:
            erst = (await c.call_tool("project_create", {"name": "Ideen-HTTP"})).content[0].text
            noch = (await c.call_tool("project_create", {"name": "Ideen-HTTP"})).content[0].text
        return erst, noch

    erst, noch = _lauf(arbeit)
    assert "created and registered" in erst
    assert "already existed" in noch
