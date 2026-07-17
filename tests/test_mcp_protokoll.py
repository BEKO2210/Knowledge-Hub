"""Die MCP-Werkzeuge über das echte Protokoll — und die Fehler, die dabei auffielen.

Der In-Memory-Client von fastmcp spricht dasselbe Protokoll wie Claude oder ChatGPT,
nur ohne Netzwerk: gleiche Werkzeugliste, gleiche Argumentprüfung, gleiche Fehlerform.
Bis hierher waren note_save, note_list und project_create nur durch Unit-Tests belegt —
über das Protokoll hatte sie nie jemand aufgerufen.

Die Regressionen unten stammen aus genau diesem Lauf (D5).

Warum `asyncio.run` statt eines async-Testplugins: Die Suite kommt ohne pytest-asyncio
aus. Eine Abhängigkeit nur für vierzehn Aufrufe wäre der falsche Tausch.
"""

from __future__ import annotations

import asyncio
import threading

import pytest
from conftest import TMP
from fastmcp import Client
from fastmcp.exceptions import ToolError

import config
import server
import vault


@pytest.fixture(autouse=True)
def konfiguration_aufraeumen():
    """Notiz-Werkzeuge registrieren Projekte in der geteilten Test-Konfiguration —
    ohne Aufräumen sehen spätere Tests sie (siehe test_notizen.py)."""
    vorher = config.project_entries()
    yield
    config.save_projects(vorher)


def ueber_mcp(arbeit):
    """`arbeit(client)` mit einem verbundenen MCP-Client ausführen und das Ergebnis liefern."""

    async def lauf():
        async with Client(server.mcp) as c:
            return await arbeit(c)

    return asyncio.run(lauf())


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


def test_werkzeugliste_ist_vollstaendig(fresh_vault):
    namen = ueber_mcp(lambda c: c.list_tools())
    assert {t.name for t in namen} == ALLE_WERKZEUGE


def test_unbekanntes_projekt_ist_ein_sauberer_fehler(fresh_vault):
    """Kein Absturz, kein Traceback — ein Fehler, den der Client dem Nutzer zeigen kann."""

    async def arbeit(c):
        with pytest.raises(ToolError, match="unknown project"):
            await c.call_tool("graph_query", {"project": "../../etc", "question": "x"})

    ueber_mcp(arbeit)


def test_notiz_ueber_das_protokoll(fresh_vault):
    async def arbeit(c):
        r = await c.call_tool(
            "note_save",
            {
                "project": "Über Belkis",
                "title": "Wer ich bin",
                "content": "Ich baue einen Hub.",
            },
        )
        assert "saved" in r.content[0].text
        return (await c.call_tool("note_list", {"project": "Über Belkis"})).data

    dateien = ueber_mcp(arbeit)
    assert len(dateien) == 1
    assert dateien[0].endswith(".md")


def test_note_list_unbekanntes_projekt_ist_leer(fresh_vault):
    """Eine leere Liste, kein Fehler — sonst müsste jeder Client den Sonderfall kennen."""

    async def arbeit(c):
        return (await c.call_tool("note_list", {"project": "nie-gesehen"})).data

    assert ueber_mcp(arbeit) == []


def test_project_create_ist_idempotent(fresh_vault):
    async def arbeit(c):
        erst = (await c.call_tool("project_create", {"name": "Geschäfts-Ideen"})).content[0].text
        noch = (await c.call_tool("project_create", {"name": "Geschäfts-Ideen"})).content[0].text
        return erst, noch

    erst, noch = ueber_mcp(arbeit)
    assert "created and registered" in erst
    assert "already existed" in noch


# ---------------------------------------------------------------------------
# D5-Regression 1: der 2FA-Seed war über MCP les- und löschbar
# ---------------------------------------------------------------------------
# Die Oberfläche verbarg "__2fa__" (HIDDEN_SECRETS), die MCP-Werkzeuge nicht. Jeder
# verbundene KI-Client konnte damit den zweiten Faktor auslesen — oder ihn löschen und
# die Zwei-Faktor-Anmeldung so abschalten. Die Regel gehört in den Vault, nicht in eine
# der beiden Oberflächen.
def test_zweiter_faktor_ist_ueber_mcp_unsichtbar(fresh_vault):
    vault.secret_set("__2fa__", "TOTP-SEED", client="test")
    vault.secret_set("normal", "wert", client="test")

    async def arbeit(c):
        assert (await c.call_tool("secret_list", {})).data == ["normal"]
        for werkzeug, args in (
            ("secret_get", {"name": "__2fa__"}),
            ("secret_delete", {"name": "__2fa__"}),
            ("secret_set", {"name": "__2fa__", "value": "gekapert"}),
        ):
            with pytest.raises(ToolError, match="no secret named"):
                await c.call_tool(werkzeug, args)

    ueber_mcp(arbeit)
    assert vault.secret_get("__2fa__", client="test") == "TOTP-SEED", "Seed muss unberührt sein"


# ---------------------------------------------------------------------------
# D5-Regression 2: die Namensregel galt nur in der Oberfläche
# ---------------------------------------------------------------------------
# Über MCP ließ sich ein Secret "böse/../name@!" ablegen. In der Oberfläche steckt der
# Name im Pfad (/ui/api/secrets/<name>) — der Eintrag war dort danach nicht mehr löschbar.
def test_ungueltiger_secret_name_wird_auch_ueber_mcp_abgelehnt(fresh_vault):
    async def arbeit(c):
        for name in ("böse/../name@!", "x" * 65, "neue\nzeile"):
            with pytest.raises(ToolError, match="Ungültiger Name"):
                await c.call_tool("secret_set", {"name": name, "value": "v"})
        return (await c.call_tool("secret_list", {})).data

    assert ueber_mcp(arbeit) == []


# ---------------------------------------------------------------------------
# D5-Regression 3: gleichzeitige Schreibvorgänge zerstörten den Vault
# ---------------------------------------------------------------------------
# `_write_file` benutzte für JEDEN Schreibvorgang dieselbe Zwischendatei "vault.tmp".
# Zwei gleichzeitige secret_set (zwei MCP-Clients, oder Oberfläche + Nacht-Job) traten
# sich gegenseitig auf die Datei: der Schnellere benannte sie um, der Langsamere starb
# an FileNotFoundError. Und selbst ohne Absturz überschrieb der Letzte die Secrets des
# Ersten, weil alle denselben Stand gelesen hatten (Lesen-Ändern-Schreiben ohne Sperre).
def test_parallele_secrets_gehen_nicht_verloren(fresh_vault):
    namen = [f"parallel-{i}" for i in range(12)]
    fehler: list[BaseException] = []

    def schreibe(name: str) -> None:
        try:
            vault.secret_set(name, f"wert-{name}", client="test")
        except BaseException as e:  # noqa: BLE001 - jeder Fehler ist hier ein Befund
            fehler.append(e)

    threads = [threading.Thread(target=schreibe, args=(n,)) for n in namen]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert not fehler, f"Schreibvorgänge sind abgestürzt: {fehler!r}"
    assert sorted(vault.secret_list(client="test")) == sorted(namen), "Kein Secret darf verloren gehen"
    for n in namen:
        assert vault.secret_get(n, client="test") == f"wert-{n}"


def test_keine_zwischendatei_bleibt_liegen(fresh_vault):
    vault.secret_set("eins", "1", client="test")
    liegengeblieben = [*TMP.glob(".vault-*.tmp"), *TMP.glob("vault.tmp")]
    assert not liegengeblieben, f"Zwischendateien müssen weg sein: {liegengeblieben}"


# ---------------------------------------------------------------------------
# D5-Regression 4: gleichzeitige Notizen mit gleichem Titel überschrieben sich
# ---------------------------------------------------------------------------
# Die Nummerierung war ein Prüfen-dann-Schreiben (`while f.exists()`). Zwei Clients, die
# gleichzeitig eine Notiz mit demselben Titel speichern, sahen dieselbe freie Nummer.
def test_parallele_notizen_mit_gleichem_titel(fresh_vault):
    def schreibe(i: int) -> None:
        server._write_note("rennen", "Gleicher Titel", f"Inhalt {i}", None)

    threads = [threading.Thread(target=schreibe, args=(i,)) for i in range(6)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    dateien = server.note_list("rennen")
    assert len(dateien) == 6, f"6 Notizen gespeichert, nur {len(dateien)} Dateien: {dateien}"
    inhalte = {(server.NOTES_ROOT / "rennen" / d).read_text() for d in dateien}
    assert len(inhalte) == 6, "Keine Notiz darf den Inhalt einer anderen tragen"


def test_graph_query_lehnt_leere_frage_ab(monkeypatch):
    """Regression: das MCP-Tool graph_query hatte — anders als die Web-UI (graph_ask) —
    keine Frage-Guard. Für question="" wählte die Retrieval-Engine beliebige Startknoten
    und lieferte eine scheinbar gültige, aber unbegründete Antwort. Jetzt: klarer
    ValueError, bevor überhaupt ein Knoten angefasst wird — auch über den echten
    MCP-Client als ToolError sichtbar."""
    monkeypatch.setattr(server, "_projects", lambda: {"demo"})
    for frage in ("", "   ", "\n\t", "ab"):
        with pytest.raises(ValueError, match="question"):
            server.graph_query("demo", frage)
    # Gültige Frage passiert die Guard (Ergebnis egal — sie darf nur nicht AN der Guard scheitern).
    try:
        server.graph_query("demo", "was macht die Auth?")
    except ValueError as e:
        assert "question must not be empty" not in str(e)


def test_register_project_lehnt_basename_kollision_ab(tmp_path):
    """Regression (#2): Projekte werden hub-intern per Ordner-Basename identifiziert.
    Zwei verschiedene Pfade mit gleichem Basename würden sich Graph, Locks und Antworten
    teilen — jetzt hart abgelehnt (wie der Web-UI-Add-Pfad)."""
    a = tmp_path / "kunde-a" / "api"
    a.mkdir(parents=True)
    b = tmp_path / "kunde-b" / "api"
    b.mkdir(parents=True)
    assert server._register_project(a) is True
    with pytest.raises(ValueError, match="basename"):
        server._register_project(b)


def test_projects_list_ueberlebt_kaputte_graph_json():
    """Regression (#3): eine einzige beschädigte graph.json darf projects_list (MCP) nicht
    mit einem Toolfehler abbrechen — der Client sähe sonst nicht mal die gesunden Projekte."""
    import shutil

    root = server.KNOWLEDGE_ROOT
    (root / "gutp" / "graphify-out").mkdir(parents=True, exist_ok=True)
    (root / "gutp" / "graphify-out" / "graph.json").write_text('{"nodes": [], "links": []}')
    (root / "kaputtp" / "graphify-out").mkdir(parents=True, exist_ok=True)
    (root / "kaputtp" / "graphify-out" / "graph.json").write_text("{ kein json")
    try:
        liste = server.projects_list()
        namen = {p["project"] for p in liste}
        assert "gutp" in namen and "kaputtp" in namen
        assert next(p for p in liste if p["project"] == "kaputtp").get("status") == "invalid"
    finally:
        shutil.rmtree(root / "gutp", ignore_errors=True)
        shutil.rmtree(root / "kaputtp", ignore_errors=True)


def test_report_get_ohne_report_gibt_hinweis():
    """Regression (#7): ein Projekt gilt schon mit graph.json als vorhanden — fehlt
    GRAPH_REPORT.md, lieferte report_get einen ungefangenen Dateifehler statt Hinweis."""
    import shutil

    root = server.KNOWLEDGE_ROOT
    (root / "nurgraph" / "graphify-out").mkdir(parents=True, exist_ok=True)
    (root / "nurgraph" / "graphify-out" / "graph.json").write_text('{"nodes": [], "links": []}')
    try:
        text = server.report_get("nurgraph")
        assert "kein Graph-Report" in text
    finally:
        shutil.rmtree(root / "nurgraph", ignore_errors=True)
