"""OAuth 2.1 + PKCE: der komplette Weg, den ein KI-Client geht — und die Fallen daneben."""

from __future__ import annotations

import base64
import hashlib
import secrets as pysecrets

from conftest import TEST_PASSWORD

import oauth

REDIRECT = "https://client.invalid/callback"


def _pkce() -> tuple[str, str]:
    verifier = pysecrets.token_urlsafe(48)
    challenge = base64.urlsafe_b64encode(
        hashlib.sha256(verifier.encode()).digest()
    ).decode().rstrip("=")
    return verifier, challenge


def _register(client) -> str:
    r = client.post("/oauth/register", json={
        "client_name": "Testclient",
        "redirect_uris": [REDIRECT],
    })
    assert r.status_code in (200, 201), r.text
    return r.json()["client_id"]


def _authorize(client, cid: str, challenge: str, password: str = TEST_PASSWORD):
    return client.post("/oauth/authorize", data={
        "response_type": "code",
        "client_id": cid,
        "redirect_uri": REDIRECT,
        "code_challenge": challenge,
        "code_challenge_method": "S256",
        "password": password,
    }, follow_redirects=False)


def _code_from(resp) -> str:
    from urllib.parse import parse_qs, urlparse

    return parse_qs(urlparse(resp.headers["location"]).query)["code"][0]


# --- der Glücksfall ------------------------------------------------------------
def test_kompletter_pkce_fluss_liefert_nutzbaren_token(client, fresh_vault):
    cid = _register(client)
    verifier, challenge = _pkce()

    r = _authorize(client, cid, challenge)
    assert r.status_code == 302, "richtiges Passwort -> Weiterleitung mit Code"
    code = _code_from(r)

    r = client.post("/oauth/token", data={
        "grant_type": "authorization_code",
        "code": code,
        "redirect_uri": REDIRECT,
        "client_id": cid,
        "code_verifier": verifier,
    })
    assert r.status_code == 200, r.text
    tok = r.json()
    assert tok["token_type"].lower() == "bearer"
    access = tok["access_token"]

    # ... und der Token öffnet tatsächlich die geschützten Endpunkte
    assert client.get("/ui/api/health",
                      headers={"Authorization": f"Bearer {access}"}).status_code == 200


# --- die Fallen ----------------------------------------------------------------
def test_falscher_verifier_wird_abgewiesen(client, fresh_vault):
    """Der Kern von PKCE: Ein abgefangener Code ist ohne den Verifier wertlos."""
    cid = _register(client)
    _, challenge = _pkce()
    code = _code_from(_authorize(client, cid, challenge))

    r = client.post("/oauth/token", data={
        "grant_type": "authorization_code",
        "code": code,
        "redirect_uri": REDIRECT,
        "client_id": cid,
        "code_verifier": _pkce()[0],   # fremder Verifier
    })
    assert r.status_code == 400


def test_code_ist_nur_einmal_einloesbar(client, fresh_vault):
    cid = _register(client)
    verifier, challenge = _pkce()
    code = _code_from(_authorize(client, cid, challenge))
    data = {
        "grant_type": "authorization_code",
        "code": code,
        "redirect_uri": REDIRECT,
        "client_id": cid,
        "code_verifier": verifier,
    }
    assert client.post("/oauth/token", data=data).status_code == 200
    assert client.post("/oauth/token", data=data).status_code == 400, "Wiederverwendung muss scheitern"


def test_ohne_pkce_keine_autorisierung(client, fresh_vault):
    cid = _register(client)
    r = client.get("/oauth/authorize", params={
        "response_type": "code",
        "client_id": cid,
        "redirect_uri": REDIRECT,
    })
    assert r.status_code == 400


def test_fremde_redirect_uri_wird_abgewiesen(client, fresh_vault):
    """Sonst könnte ein Angreifer den Code auf seinen eigenen Server umleiten."""
    cid = _register(client)
    _, challenge = _pkce()
    r = client.get("/oauth/authorize", params={
        "response_type": "code",
        "client_id": cid,
        "redirect_uri": "https://angreifer.invalid/klau",
        "code_challenge": challenge,
        "code_challenge_method": "S256",
    })
    assert r.status_code == 400


def test_falsches_passwort_liefert_keinen_code(client, fresh_vault):
    cid = _register(client)
    _, challenge = _pkce()
    r = _authorize(client, cid, challenge, password="falsch")
    assert r.status_code == 200        # Formular erneut, mit Fehlermeldung
    assert "location" not in r.headers  # aber KEINE Weiterleitung mit Code


def test_unbekannter_client_wird_abgewiesen(client, fresh_vault):
    _, challenge = _pkce()
    r = client.get("/oauth/authorize", params={
        "response_type": "code",
        "client_id": "gibt-es-nicht",
        "redirect_uri": REDIRECT,
        "code_challenge": challenge,
        "code_challenge_method": "S256",
    })
    assert r.status_code == 400


# --- Sitzungen ------------------------------------------------------------------
def test_sitzung_erscheint_und_laesst_sich_widerrufen(client, fresh_vault):
    cid = _register(client)
    verifier, challenge = _pkce()
    code = _code_from(_authorize(client, cid, challenge))
    access = client.post("/oauth/token", data={
        "grant_type": "authorization_code", "code": code, "redirect_uri": REDIRECT,
        "client_id": cid, "code_verifier": verifier,
    }).json()["access_token"]

    sitzungen = oauth.list_sessions()
    assert len(sitzungen) >= 1
    sid = oauth.session_of(access)
    assert sid

    assert oauth.revoke_session(sid) is True
    # Nach dem Widerruf ist der Token sofort wertlos
    assert client.get("/ui/api/health",
                      headers={"Authorization": f"Bearer {access}"}).status_code == 401


def test_tokens_liegen_nur_als_hash_auf_der_platte(client, fresh_vault):
    """Wer die Zustandsdatei liest, darf damit nichts anfangen können."""
    from conftest import TMP

    cid = _register(client)
    verifier, challenge = _pkce()
    code = _code_from(_authorize(client, cid, challenge))
    access = client.post("/oauth/token", data={
        "grant_type": "authorization_code", "code": code, "redirect_uri": REDIRECT,
        "client_id": cid, "code_verifier": verifier,
    }).json()["access_token"]

    roh = (TMP / "oauth_state.json").read_text()
    assert access not in roh, "Der Token selbst darf NICHT in der Datei stehen"
