"""Sitzungen, Geräte und Refresh-Rotation (Audit-Run 18).

test_oauth.py deckt den Authorization-Code-Fluss ab, aber NICHT: den Refresh-Grant,
die Rotation (altes Refresh stirbt), den Replay eines rotierten Refresh, zwei gleichzeitig
angemeldete Profile, „alle anderen abmelden" und paralleles Refreshing. Genau das hier.

Zwei „Browserprofile" werden über zwei getrennte web-ui-Logins simuliert — keine
physischen Zwei-Geräte-Behauptungen (Audit-Vorgabe).
"""

from __future__ import annotations

import base64
import hashlib
import secrets as pysecrets
import socket
import threading
import time
from urllib.parse import parse_qs, urlparse

import pytest
from conftest import TEST_PASSWORD

import oauth

REDIRECT = "https://client.invalid/cb"


def _pkce():
    v = pysecrets.token_urlsafe(48)
    c = base64.urlsafe_b64encode(hashlib.sha256(v.encode()).digest()).decode().rstrip("=")
    return v, c


def _oauth_flow(client):
    """Voller PKCE-Fluss über den TestClient → (access, refresh, client_id)."""
    cid = client.post("/oauth/register", json={"client_name": "c", "redirect_uris": [REDIRECT]}).json()[
        "client_id"
    ]
    v, c = _pkce()
    az = client.post(
        "/oauth/authorize",
        data={
            "response_type": "code",
            "client_id": cid,
            "redirect_uri": REDIRECT,
            "code_challenge": c,
            "code_challenge_method": "S256",
            "password": TEST_PASSWORD,
        },
        follow_redirects=False,
    )
    code = parse_qs(urlparse(az.headers["location"]).query)["code"][0]
    tok = client.post(
        "/oauth/token",
        data={
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": REDIRECT,
            "client_id": cid,
            "code_verifier": v,
        },
    ).json()
    return tok["access_token"], tok["refresh_token"], cid


def _H(tok):
    return {"Authorization": f"Bearer {tok}"}


# --- Refresh-Grant: Rotation + Replay -----------------------------------------
def test_refresh_rotiert_und_altes_refresh_stirbt(client, fresh_vault):
    acc, ref, cid = _oauth_flow(client)
    assert client.get("/ui/api/health", headers=_H(acc)).status_code == 200

    tok2 = client.post(
        "/oauth/token", data={"grant_type": "refresh_token", "refresh_token": ref, "client_id": cid}
    ).json()
    assert tok2["access_token"] != acc
    assert tok2["refresh_token"] != ref, "Refresh muss rotieren"
    assert client.get("/ui/api/health", headers=_H(tok2["access_token"])).status_code == 200

    # Replay des ALTEN (rotierten) Refresh-Tokens ist wertlos
    replay = client.post(
        "/oauth/token", data={"grant_type": "refresh_token", "refresh_token": ref, "client_id": cid}
    )
    assert replay.status_code == 400, "rotiertes Refresh darf nicht erneut einlösbar sein"


def test_abgelaufener_access_wird_per_refresh_erneuert(client, fresh_vault):
    acc, ref, cid = _oauth_flow(client)
    st = oauth._load()
    st["tokens"][oauth._sha(acc)]["exp"] = oauth._now() - 5
    oauth._save(st)
    assert client.get("/ui/api/health", headers=_H(acc)).status_code == 401
    neu = client.post(
        "/oauth/token", data={"grant_type": "refresh_token", "refresh_token": ref, "client_id": cid}
    )
    assert neu.status_code == 200
    assert client.get("/ui/api/health", headers=_H(neu.json()["access_token"])).status_code == 200


# --- Zwei Profile gleichzeitig ------------------------------------------------
def _login(client):
    return client.post("/ui/api/login", json={"password": TEST_PASSWORD}).json()["token"]


def test_zwei_profile_gleichzeitig_angemeldet(client, fresh_vault):
    t1, t2 = _login(client), _login(client)
    assert t1 != t2
    assert client.get("/ui/api/health", headers=_H(t1)).status_code == 200
    assert client.get("/ui/api/health", headers=_H(t2)).status_code == 200

    sess = client.get("/ui/api/sessions", headers=_H(t1)).json()["sessions"]
    assert len([s for s in sess if s.get("kind") == "web"]) >= 2
    stat = [s for s in sess if s.get("kind") == "static"]
    assert stat and stat[0]["revocable"] is False, "Statisches Token: sichtbar, nicht per Klick widerrufbar"


def test_fremde_sitzung_abmelden_eigene_bleibt(client, fresh_vault):
    t1, t2 = _login(client), _login(client)
    sess = client.get("/ui/api/sessions", headers=_H(t1)).json()
    me = sess["current"]
    fremd = next(
        s["id"]
        for s in sess["sessions"]
        if s.get("kind") == "web" and s["id"] != me and s.get("revocable", True)
    )

    assert client.delete(f"/ui/api/sessions/{fremd}", headers=_H(t1)).status_code == 200
    assert client.get("/ui/api/health", headers=_H(t1)).status_code == 200, "eigene Sitzung bleibt"
    assert client.get("/ui/api/health", headers=_H(t2)).status_code == 401, "fremde ist tot"

    # Die EIGENE Sitzung lässt sich nicht über die Geräte-Abmeldung entfernen (dafür: Abmelden)
    assert client.delete(f"/ui/api/sessions/{me}", headers=_H(t1)).status_code == 400


def test_alle_anderen_abmelden_eigene_bleibt(client, fresh_vault):
    t1 = _login(client)
    _login(client)
    _oauth_flow(client)  # zusätzlich eine mcp-Sitzung
    me = client.get("/ui/api/sessions", headers=_H(t1)).json()["current"]

    r = client.delete("/ui/api/sessions", headers=_H(t1))
    assert r.status_code == 200
    assert r.json()["revoked"] >= 2
    assert client.get("/ui/api/health", headers=_H(t1)).status_code == 200

    rest = client.get("/ui/api/sessions", headers=_H(t1)).json()["sessions"]
    uebrig = [s for s in rest if s.get("kind") in ("web", "mcp")]
    assert len(uebrig) == 1 and uebrig[0]["id"] == me, "nur die eigene Sitzung bleibt"


def test_token_liegt_nur_als_hash_vor(client, fresh_vault):
    from conftest import TMP

    t1 = _login(client)
    roh = (TMP / "oauth_state.json").read_text()
    assert t1 not in roh, "Sitzungs-Token darf nicht im Klartext in der Zustandsdatei stehen"


# --- Paralleles Refreshing (echte Nebenläufigkeit gegen einen Live-Server) ------
def _freier_port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture(scope="module")
def hub():
    import uvicorn

    import server

    port = _freier_port()
    cfg = uvicorn.Config(server.application, host="127.0.0.1", port=port, log_level="error")
    srv = uvicorn.Server(cfg)
    t = threading.Thread(target=srv.run, daemon=True)
    t.start()
    for _ in range(100):
        if srv.started:
            break
        time.sleep(0.05)
    assert srv.started
    yield f"http://127.0.0.1:{port}"
    srv.should_exit = True
    t.join(timeout=5)


def test_paralleles_refresh_erzeugt_keine_zwei_sitzungen(hub, fresh_vault):
    """Zwei gleichzeitige Refreshes desselben Tokens: genau EIN Erfolg, keine
    Doppel-Ausstellung. Ein Refresh-Token darf nicht zwei gültige Sitzungen erzeugen."""
    import asyncio

    import httpx

    async def lauf():
        async with httpx.AsyncClient() as hc:
            cid = (
                await hc.post(f"{hub}/oauth/register", json={"client_name": "p", "redirect_uris": [REDIRECT]})
            ).json()["client_id"]
            v, c = _pkce()
            az = await hc.post(
                f"{hub}/oauth/authorize",
                data={
                    "response_type": "code",
                    "client_id": cid,
                    "redirect_uri": REDIRECT,
                    "code_challenge": c,
                    "code_challenge_method": "S256",
                    "password": TEST_PASSWORD,
                },
            )
            code = parse_qs(urlparse(az.headers["location"]).query)["code"][0]
            tok = (
                await hc.post(
                    f"{hub}/oauth/token",
                    data={
                        "grant_type": "authorization_code",
                        "code": code,
                        "redirect_uri": REDIRECT,
                        "client_id": cid,
                        "code_verifier": v,
                    },
                )
            ).json()

            async def refresh():
                return await hc.post(
                    f"{hub}/oauth/token",
                    data={
                        "grant_type": "refresh_token",
                        "refresh_token": tok["refresh_token"],
                        "client_id": cid,
                    },
                )

            a, b = await asyncio.gather(refresh(), refresh())
            return sorted([a.status_code, b.status_code]), [a, b]

    codes, resp = asyncio.run(lauf())
    assert codes == [200, 400], f"erwartet genau ein Erfolg, kam {codes}"
