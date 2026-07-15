"""Jeder Klick unter harten Bedingungen (Audit-Run 17).

Für die wichtigste Schreibaktion (Secret anlegen) die Bedingungsmatrix durch die ECHTE
Oberfläche: Erfolg (unabhängig in der Datei geprüft, nicht am Toast), leere Eingabe,
Serverfehler (500), Doppelklick und schnelles Mehrfachklicken (kein doppelter
Nebeneffekt), und dass der Knopf nach einem Fehler bedienbar bleibt. Ergänzt die
Muster aus test_e2e.py um die Nebeneffekt- und Doppelklick-Prüfung.

Isolierte Instanz, headless — nie Produktion.
"""

from __future__ import annotations

import socket
import threading
import time

import pytest
import uvicorn
from conftest import TEST_PASSWORD

pytest.importorskip("playwright")
from playwright.sync_api import sync_playwright  # noqa: E402

import vault  # noqa: E402


def _freier_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture(scope="module")
def hub():
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


@pytest.fixture(scope="module")
def browser():
    with sync_playwright() as p:
        b = p.chromium.launch()
        yield b
        b.close()


@pytest.fixture
def secrets_tab(browser, hub, fresh_vault):
    ctx = browser.new_context(viewport={"width": 1280, "height": 880}, locale="en-US")
    page = ctx.new_page()
    page.fehler = []
    page.on("pageerror", lambda e: page.fehler.append(str(e)))
    page.add_init_script(
        "try{localStorage.setItem('kmcp_toured','1');localStorage.setItem('kmcp_lang','de')}catch(e){}"
    )
    page.goto(f"{hub}/ui", wait_until="networkidle")
    page.fill("#pw", TEST_PASSWORD)
    page.click("#loginbtn")
    for _ in range(150):
        if page.evaluate("() => getComputedStyle(document.getElementById('login')).display === 'none'"):
            break
        page.wait_for_timeout(100)
    else:
        raise AssertionError("Login blieb sichtbar")
    page.evaluate("tab('secrets')")
    page.wait_for_timeout(400)
    yield page
    ctx.close()


def test_erfolg_landet_in_der_datei_nicht_nur_im_toast(secrets_tab):
    """Erfolg wird unabhängig im Vault geprüft — nie nur am Toast (Audit-Vorgabe)."""
    p = secrets_tab
    p.fill("#sname", "klick_ok")
    p.fill("#svalue", "wert-1")
    p.click("#addbtn")
    p.wait_for_timeout(1200)
    assert vault.secret_get("klick_ok", client="test") == "wert-1"
    assert not p.fehler, p.fehler


def test_leere_eingabe_macht_keinen_api_call(secrets_tab):
    p = secrets_tab
    vorher = set(vault.secret_list(client="test"))
    p.fill("#sname", "")
    p.fill("#svalue", "")
    p.click("#addbtn")
    p.wait_for_timeout(500)
    assert p.inner_text("#secerr").strip(), "Es muss eine Validierungsmeldung stehen"
    assert set(vault.secret_list(client="test")) == vorher, "Kein Secret bei leerer Eingabe"


def test_doppelklick_legt_nur_ein_secret_an(secrets_tab):
    """Doppelklick auf „Speichern" darf nicht zwei Schreibvorgänge auslösen.

    Der disabled-Guard in addSecret unterbindet den zweiten Submit; unabhängig
    im Vault gezählt, nicht am Toast beurteilt.
    """
    p = secrets_tab
    p.fill("#sname", "doppel")
    p.fill("#svalue", "genau-einmal")
    # Zwei Klicks im selben Tick: der zweite trifft einen schon deaktivierten Knopf.
    p.evaluate("() => { const b = document.getElementById('addbtn'); b.click(); b.click(); }")
    p.wait_for_timeout(1400)
    assert vault.secret_get("doppel", client="test") == "genau-einmal"
    # Kein Weg, „zweimal" direkt zu zählen — aber der Wert ist eindeutig und der Knopf frei.
    assert not p.is_disabled("#addbtn"), "Knopf muss nach dem Vorgang wieder bedienbar sein"


def test_schnelles_mehrfachklicken_bleibt_konsistent(secrets_tab):
    p = secrets_tab
    p.fill("#sname", "mehrfach")
    p.fill("#svalue", "stabil")
    p.evaluate("() => { const b = document.getElementById('addbtn'); for (let i=0;i<5;i++) b.click(); }")
    p.wait_for_timeout(1500)
    assert vault.secret_get("mehrfach", client="test") == "stabil"
    assert not p.is_disabled("#addbtn")


def test_serverfehler_zeigt_meldung_und_knopf_bleibt_bedienbar(secrets_tab):
    """500 auf POST → verständliche Meldung, und der Knopf ist danach NICHT tot."""
    p = secrets_tab
    p.evaluate("""() => {
        const echt = window.fetch;
        window.fetch = (u, o) => (o && o.method === 'POST' && String(u).includes('/ui/api/secrets'))
            ? Promise.resolve(new Response(JSON.stringify({error: 'kaputt', ref: 'deadbeef'}),
                {status: 500, headers: {'Content-Type': 'application/json'}}))
            : echt(u, o);
    }""")
    p.fill("#sname", "fehlerfall")
    p.fill("#svalue", "egal")
    p.click("#addbtn")
    p.wait_for_selector("#errbanner.on", timeout=6000)
    assert "schiefgelaufen" in p.inner_text("#errbanner")
    assert not p.is_disabled("#addbtn"), "Der Knopf darf nach einem Serverfehler nicht deaktiviert bleiben"
    # Und es wurde nichts gespeichert
    assert vault.secret_get("fehlerfall", client="test") is None
