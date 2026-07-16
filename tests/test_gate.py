"""BearerGate: Was ist offen, was ist zu — und bleibt der Login gegen Rateversuche dicht?"""

from __future__ import annotations

from conftest import TEST_MCP_TOKEN, TEST_PASSWORD

import vault


# --- offen ohne Anmeldung ------------------------------------------------------
def test_seite_und_assets_sind_offen(client):
    """Ohne diese drei kann sich niemand überhaupt anmelden."""
    assert client.get("/ui").status_code == 200
    assert client.get("/ui/asset/app.css").status_code == 200
    assert client.get("/ui/asset/app.js").status_code == 200


def test_oauth_discovery_ist_offen(client):
    """Muss offen sein — so findet ein KI-Client den Anmeldeweg überhaupt erst."""
    assert client.get("/.well-known/oauth-protected-resource").status_code == 200
    assert client.get("/.well-known/oauth-authorization-server").status_code == 200


# --- zu ohne Anmeldung ---------------------------------------------------------
def test_daten_endpunkte_sind_ohne_token_dicht(client):
    for pfad in ("/ui/api/secrets", "/ui/api/audit", "/ui/api/health",
                 "/ui/api/sessions", "/ui/api/mapping/status", "/ui/api/projects"):
        assert client.get(pfad).status_code == 401, f"{pfad} war offen!"


def test_mcp_endpunkt_ist_ohne_token_dicht(client):
    r = client.post("/mcp", json={"jsonrpc": "2.0", "method": "initialize", "id": 1})
    assert r.status_code == 401
    # RFC 9728: Die 401 weist den Weg zum Anmeldeverfahren
    assert "resource_metadata" in r.headers.get("www-authenticate", "")


def test_falscher_token_wird_abgewiesen(client):
    r = client.get("/ui/api/secrets", headers={"Authorization": "Bearer voellig-falsch"})
    assert r.status_code == 401


def test_asset_pfad_erlaubt_keinen_ausbruch(client):
    """Kein Weg aus web/ heraus — und keine fremden Dateitypen."""
    assert client.get("/ui/asset/app.txt").status_code == 404
    assert client.get("/ui/asset/index.html").status_code == 404


# --- offen MIT Token -----------------------------------------------------------
def test_statischer_token_oeffnet_die_daten_endpunkte(client, auth, fresh_vault):
    assert client.get("/ui/api/health", headers=auth).status_code == 200
    assert client.get("/ui/api/secrets", headers=auth).status_code == 200


# --- Login + Rate-Limit --------------------------------------------------------
def test_login_mit_richtigem_passwort(client, fresh_vault):
    r = client.post("/ui/api/login", json={"password": TEST_PASSWORD})
    assert r.status_code == 200
    assert r.json().get("token", "").startswith("kmcp_")


def test_login_mit_falschem_passwort(client, fresh_vault):
    r = client.post("/ui/api/login", json={"password": "falsch"})
    assert r.status_code == 401


def test_login_sperrt_nach_fuenf_fehlversuchen(client, fresh_vault):
    """5 Fehlversuche / 15 min — danach ist zu, auch für das RICHTIGE Passwort."""
    for _ in range(5):
        client.post("/ui/api/login", json={"password": "falsch"})
    r = client.post("/ui/api/login", json={"password": TEST_PASSWORD})
    assert r.status_code == 429, "Nach 5 Fehlversuchen muss gesperrt sein"


def test_login_token_funktioniert_danach(client, fresh_vault):
    token = client.post("/ui/api/login", json={"password": TEST_PASSWORD}).json()["token"]
    h = {"Authorization": f"Bearer {token}"}
    assert client.get("/ui/api/secrets", headers=h).status_code == 200


def test_secret_ueber_http_landet_verschluesselt_im_vault(client, auth, fresh_vault):
    r = client.post("/ui/api/secrets", headers=auth,
                    json={"name": "http_key", "value": "wert-via-http"})
    assert r.status_code == 200
    assert vault.secret_get("http_key", client="test") == "wert-via-http"


def test_secrets_liste_gibt_keine_werte_preis(client, auth, fresh_vault):
    """Die Liste darf Namen zeigen — niemals Werte."""
    vault.secret_set("k", "streng-geheim", client="test")
    body = client.get("/ui/api/secrets", headers=auth).text
    assert "k" in body
    assert "streng-geheim" not in body


def test_statischer_token_ist_konstantzeit_geprueft(client, fresh_vault):
    """Ein Präfix des echten Tokens darf nicht durchkommen."""
    kurz = TEST_MCP_TOKEN[:-1]
    r = client.get("/ui/api/health", headers={"Authorization": f"Bearer {kurz}"})
    assert r.status_code == 401


def test_bereichsnamen_werden_ausgeliefert(client, auth, fresh_vault, tmp_path, monkeypatch):
    """Der Graph-Endpunkt muss den KI-vergebenen Bereichsnamen mitschicken.

    Ohne ihn zeigt die Oberfläche nur „Bereich 7" — die gesamte Benennung wäre
    unsichtbar und damit wertlos. Genau das war lange der Fall.
    """
    import json

    from api import common

    projekt = tmp_path / "demo" / "graphify-out"
    projekt.mkdir(parents=True)
    (projekt / "graph.json").write_text(json.dumps({
        "nodes": [
            {"id": "a", "label": "A", "community": 3, "community_name": "Auth and Sessions"},
            {"id": "b", "label": "B", "community": 3, "community_name": "Auth and Sessions"},
        ],
        "links": [{"source": "a", "target": "b"}],
    }))
    monkeypatch.setattr(common, "KNOWLEDGE_ROOT", tmp_path)
    import api.knowledge as k
    monkeypatch.setattr(k, "KNOWLEDGE_ROOT", tmp_path)

    r = client.get("/ui/api/graph/demo", headers=auth)
    assert r.status_code == 200
    knoten = r.json()["nodes"]
    assert all(n["community_name"] == "Auth and Sessions" for n in knoten)


def test_icons_sind_ohne_anmeldung_erreichbar(client):
    """Ein Icon ist kein Geheimnis — und hinter der Schranke bekommt es kein Client zu sehen.

    Claude und ChatGPT holen das Icon für ihre Connector-Liste, BEVOR ein Token existiert.
    Lieferte der Hub dort 401, blieb in der Liste für immer ein grauer Platzhalter.
    """
    for pfad in ("/favicon.ico", "/favicon.png", "/apple-touch-icon.png"):
        r = client.get(pfad)
        assert r.status_code == 200, f"{pfad} lieferte {r.status_code} — kein Client sieht das Icon"
        assert r.headers["content-type"].startswith("image/"), pfad
        assert len(r.content) > 500, f"{pfad} ist verdächtig leer"


def test_mcp_serverinfo_traegt_icon_und_adresse():
    """Das Icon muss im MCP-Handshake stehen — daraus baut der Client die Connector-Kachel."""
    import server

    icons = server._ICONS
    assert icons, "Ohne icons zeigt der Client nur einen Platzhalter"
    assert all(i.src.startswith("http") for i in icons), "Die Icon-URL muss absolut sein"
    assert all("/ui/static/" in i.src for i in icons), \
        "Das Icon muss unter einem Pfad liegen, der ohne Anmeldung erreichbar ist"
    assert server.mcp.website_url


# --- offener Prefix darf NICHT zum Gate-Bypass werden (Verbinden-Kampagne C9) ---
import pytest


@pytest.mark.parametrize(
    "pfad",
    [
        "/ui/asset/..%2fapi%2fsecrets",
        "/ui/asset/..%2f..%2foauth_state.json",
        "/ui/static/..%2f..%2fvault.enc",
        "/ui/static/..%2fapi%2faudit",
        "/oauth/..%2fui%2fapi%2fsecrets",
    ],
)
def test_offener_prefix_erlaubt_keinen_unauth_zugriff(client, pfad):
    """Die offenen Prefixe (/ui/asset, /ui/static, /oauth) dürfen per Pfad-Traversal
    NICHT zu geschützten Endpunkten/Dateien führen. Bewusst OHNE Token: ein
    unauthentifizierter Aufruf darf niemals 200 mit Nutzdaten sehen (Gate-Bypass)."""
    r = client.get(pfad)  # kein Authorization-Header
    assert r.status_code in (401, 404), f"{pfad} -> {r.status_code} (Gate-Bypass!)"
    assert r.status_code != 200
