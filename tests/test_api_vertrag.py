"""HTTP-API-Vertrag (Audit-Run 14): Fehlerfälle jeder Route sauber beantworten.

Geprüft wird das Verhalten, das ein bösartiger oder schlampiger Aufrufer erzeugt —
typfremdes JSON, Unfug-Query-Parameter, Pfad-Traversal, falsche Verben, abgelaufene
Token, Registrierungs-Flut. Kein Fall darf mit 500 (Serverabsturz) enden, wo ein
Aufruferfehler (4xx) korrekt ist.
"""

from __future__ import annotations

import pytest

# --- 1. Typfremdes JSON: gültiges JSON, aber kein Objekt -> 400, NIE 500 --------
# Vorher: body.get() auf einer Liste/Zahl/String ließ den Endpunkt mit 500 enden.
NICHT_OBJEKT = [
    ("POST", "/ui/api/secrets"),
    ("POST", "/ui/api/connect/token"),
    ("POST", "/ui/api/2fa/enable"),
    ("POST", "/ui/api/2fa/disable"),
    ("POST", "/ui/api/vault/autounlock"),
    ("POST", "/ui/api/vault/password"),
    ("POST", "/ui/api/mapping/toggle"),
    ("POST", "/ui/api/mapping/config"),
    ("POST", "/ui/api/mapping/history/dismiss"),
    ("POST", "/ui/api/mapping/projects"),
    ("PATCH", "/ui/api/mapping/projects"),
    ("PUT", "/ui/api/mapping/ignore"),
    ("POST", "/ui/api/backup/target"),
]
# /ui/api/ask/{project} prüft zuerst das Projekt (404 bei Unbekanntem) und liest den
# Body erst danach — der Typ-Schutz greift dort hinter dem Projekt-Gate.


@pytest.mark.parametrize("methode,pfad", NICHT_OBJEKT)
@pytest.mark.parametrize("koerper", [[1, 2], "text", 42, True])
def test_typfremdes_json_ist_400_kein_500(client, auth, fresh_vault, methode, pfad, koerper):
    r = client.request(methode, pfad, headers=auth, json=koerper)
    assert r.status_code == 400, f"{methode} {pfad} mit {koerper!r} -> {r.status_code}"
    assert "error" in r.json()


def test_login_typfremdes_json_ist_400(client, fresh_vault):
    """Der Anmelde-Endpunkt ist offen — er muss typfremdes JSON besonders sauber abweisen."""
    r = client.post("/ui/api/login", json=[1, 2])
    assert r.status_code == 400


# --- 2. Query-Parameter-Unfug: ?limit=abc -> kein 500 --------------------------
def _demo_projekt(monkeypatch, tmp_path):
    import json as _json

    import api.knowledge as k
    from api import common

    projekt = tmp_path / "demo" / "graphify-out"
    projekt.mkdir(parents=True)
    (projekt / "graph.json").write_text(
        _json.dumps({"nodes": [{"id": "a", "label": "A", "community": 1}], "links": []})
    )
    monkeypatch.setattr(common, "KNOWLEDGE_ROOT", tmp_path)
    monkeypatch.setattr(k, "KNOWLEDGE_ROOT", tmp_path)


def test_graph_limit_unfug_faellt_auf_standard_zurueck(client, auth, fresh_vault, tmp_path, monkeypatch):
    _demo_projekt(monkeypatch, tmp_path)
    r = client.get("/ui/api/graph/demo?limit=abc", headers=auth)
    assert r.status_code == 200, f"Unsinniges limit darf nicht 500 sein: {r.status_code}"
    assert r.json()["nodes"], "Der Standardwert muss greifen"


# --- 3. Pfad-Traversal bleibt dicht (Regressionsschutz) ------------------------
@pytest.mark.parametrize(
    "pfad",
    [
        "/ui/api/report/../../etc/passwd",
        "/ui/static/..%2F..%2Fenv",
        "/ui/static/%2e%2e%2fconfig.yaml",
        "/ui/asset/..%2F..%2Fvault.enc",
        "/ui/api/graph/..%2F..%2Fetc",
    ],
)
def test_pfad_traversal_wird_abgewiesen(client, auth, fresh_vault, pfad):
    r = client.get(pfad, headers=auth)
    assert r.status_code == 404, f"{pfad} -> {r.status_code} (Ausbruch!)"


# --- 4. Falsches Verb -> 405 (Regressionsschutz) -------------------------------
@pytest.mark.parametrize(
    "methode,pfad",
    [
        ("DELETE", "/ui/api/projects"),
        ("PUT", "/ui/api/login"),
        ("GET", "/oauth/token"),
        ("GET", "/oauth/register"),
    ],
)
def test_falsches_verb_ist_405(client, auth, fresh_vault, methode, pfad):
    r = client.request(methode, pfad, headers=auth)
    assert r.status_code == 405, f"{methode} {pfad} -> {r.status_code}"


# --- 5. Abgelaufener Token -> 401 ----------------------------------------------
def test_abgelaufener_token_ist_401(client, fresh_vault):
    import oauth

    state = oauth._load()
    payload = oauth._issue(state, "test-client")
    state["tokens"][oauth._sha(payload["access_token"])]["exp"] = oauth._now() - 10
    oauth._save(state)
    r = client.get("/ui/api/health", headers={"Authorization": f"Bearer {payload['access_token']}"})
    assert r.status_code == 401


# --- 6. Zu große Payload: sauber begrenzt, kein Absturz ------------------------
def test_uebergrosser_secret_wert_wird_abgewiesen(client, auth, fresh_vault):
    # Wert über der Vault-Grenze (SECRET_VALUE_MAX = 20 k), aber unter dem globalen
    # Body-Limit (2 MiB, R23-1) — so prüft der Test weiterhin genau den 400-Pfad der
    # Vault-Wertgrenze, nicht das (ebenfalls korrekte) 413 des Body-Limits.
    r = client.post("/ui/api/secrets", headers=auth, json={"name": "gross", "value": "x" * 50_000})
    assert r.status_code == 400
    assert "error" in r.json()


# --- 7. OAuth-Registrierung: unauthentifiziert, aber gedrosselt & typfest ------
def test_register_typfremde_redirect_uris_sind_400(client, fresh_vault):
    r = client.post("/oauth/register", json={"redirect_uris": [1, 2, 3]})
    assert r.status_code == 400
    r = client.post("/oauth/register", json=[1])
    assert r.status_code == 400
    # Absurd lange oder zu viele redirect_uris werden abgewiesen (Zustandsdatei klein halten)
    r = client.post("/oauth/register", json={"redirect_uris": ["https://a.example/" + "y" * 5000]})
    assert r.status_code == 400
    r = client.post("/oauth/register", json={"redirect_uris": ["https://a.example/cb"] * 20})
    assert r.status_code == 400


def test_register_wird_pro_ip_gedrosselt(client, fresh_vault):
    """Ein Flut von Registrierungen (unauthentifiziert) muss irgendwann 429 liefern —
    sonst wüchse oauth_state.json unbegrenzt."""
    codes = set()
    for _ in range(40):
        r = client.post("/oauth/register", json={"redirect_uris": ["https://c.example/cb"]})
        codes.add(r.status_code)
        if r.status_code == 429:
            break
    assert 429 in codes, "Die Registrierung muss pro IP gedrosselt werden"


def test_client_obergrenze_verwirft_verwaiste_clients():
    """Über der Obergrenze werden Clients ohne gültige Tokens verworfen — der Zustand
    bleibt beschränkt, aktive Clients (mit Token) überleben."""
    import oauth

    state = {"clients": {}, "codes": {}, "tokens": {}, "refresh": {}}
    # Ein aktiver Client mit Token, der NICHT verworfen werden darf
    state["clients"]["aktiv"] = {"redirect_uris": [], "name": "aktiv", "created": 0}
    state["tokens"]["h1"] = {"client_id": "aktiv", "sid": "s", "exp": oauth._now() + 1000}
    # Weit über die Grenze mit verwaisten Clients auffüllen
    for i in range(oauth.MAX_CLIENTS + 50):
        state["clients"][f"orphan{i}"] = {"redirect_uris": [], "name": "", "created": i + 1}
    oauth._prune_clients(state)
    assert len(state["clients"]) <= oauth.MAX_CLIENTS
    assert "aktiv" in state["clients"], "Ein Client mit gültigem Token darf nie verworfen werden"


# --- 8. Sonderzeichen im Namen werden abgewiesen, im Wert akzeptiert -----------
def test_secret_name_mit_zeilenumbruch_wird_abgewiesen(client, auth, fresh_vault):
    r = client.post("/ui/api/secrets", headers=auth, json={"name": "a\nb", "value": "v"})
    assert r.status_code == 400


def test_secret_wert_mit_sonderzeichen_wird_akzeptiert(client, auth, fresh_vault):
    import vault

    r = client.post("/ui/api/secrets", headers=auth, json={"name": "umlaut test", "value": "wärt-öüß-🙂"})
    assert r.status_code == 200
    assert vault.secret_get("umlaut test", client="test") == "wärt-öüß-🙂"
