"""E2E: echter Browser gegen eine echte, frisch hochgefahrene Hub-Instanz.

Läuft headless und komplett isoliert (eigener Port, eigener Vault, eigene Konfiguration) —
niemals gegen den produktiven Hub. Damit ist der Durchlauf auch in CI reproduzierbar.
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


def _freier_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture(scope="module")
def hub():
    """Startet den echten ASGI-Stack (BearerGate + UI) in einem Thread."""
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
    assert srv.started, "Server ist nicht hochgekommen"
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
def seite(browser, hub, fresh_vault):
    """Deterministisch deutsch.

    Die Oberfläche richtet sich sonst nach der Browsersprache — auf einem deutschen
    Rechner startete sie deutsch, in CI englisch. Genau daran sind drei Tests
    zerbrochen. Die Sprache wird darum hier festgenagelt, nicht dem Zufall überlassen.
    """
    ctx = browser.new_context(viewport={"width": 1280, "height": 880}, locale="en-US")
    page = ctx.new_page()
    page.fehler = []
    page.on("pageerror", lambda e: page.fehler.append(str(e)))
    page.on("requestfailed", lambda r: page.fehler.append(f"Request fehlgeschlagen: {r.url}"))
    page.add_init_script(
        "try{localStorage.setItem('kmcp_toured','1');localStorage.setItem('kmcp_lang','de')}catch(e){}")
    page.goto(f"{hub}/ui", wait_until="networkidle")
    yield page
    ctx.close()


def _anmelden(page):
    """Anmelden und warten, bis der Login-Bildschirm weg ist.

    Bewusst KEIN wait_for_function: Playwright wertet die Bedingung per eval() in der
    Seite aus — und die CSP des Hubs verbietet 'unsafe-eval'. Dass das scheitert, ist
    ein gutes Zeichen; wir pollen stattdessen mit evaluate().
    """
    page.fill("#pw", TEST_PASSWORD)
    page.click("#loginbtn")
    for _ in range(150):
        weg = page.evaluate(
            "() => getComputedStyle(document.getElementById('login')).display === 'none'")
        if weg:
            return
        page.wait_for_timeout(100)
    raise AssertionError("Login-Bildschirm ist nicht verschwunden")


# --- Tests ---------------------------------------------------------------------
def test_stylesheet_und_skript_kommen_an(seite):
    """Ohne diese beiden ist die Seite unbenutzbar — genau das hat der Asset-Umbau berührt."""
    assert seite.evaluate("getComputedStyle(document.querySelector('header')).display") == "flex"
    assert seite.evaluate("typeof tab === 'function'"), "app.js wurde nicht geladen"
    assert not seite.fehler, seite.fehler


def test_login_mit_falschem_passwort_zeigt_fehler(seite):
    seite.fill("#pw", "voellig-falsch")
    seite.click("#loginbtn")
    seite.wait_for_timeout(1500)
    assert seite.evaluate("getComputedStyle(document.getElementById('login')).display") != "none"


def test_login_und_alle_tabs(seite):
    _anmelden(seite)
    for t in ("graph", "ask", "secrets", "mapping", "connect", "health", "audit"):
        seite.evaluate(f"tab('{t}')")
        seite.wait_for_timeout(400)
        assert seite.evaluate(f"document.getElementById('tab-{t}').classList.contains('on')"), t
    assert not seite.fehler, seite.fehler


def test_secret_anlegen_lesen_loeschen_im_browser(seite):
    """Der wichtigste Nutzerweg, komplett durch die echte Oberfläche geklickt."""
    _anmelden(seite)
    seite.evaluate("tab('secrets')")
    seite.wait_for_timeout(600)

    seite.fill("#sname", "e2e_key")
    seite.fill("#svalue", "e2e-geheim")
    seite.click("#addbtn")
    seite.wait_for_timeout(1500)
    assert "e2e_key" in seite.inner_text("#slist")

    # Der Wert wird erst auf Klick sichtbar — vorher steht er nirgends auf der Seite
    assert "e2e-geheim" not in seite.inner_text("body")

    # ... und ist wirklich verschlüsselt im Vault gelandet
    import vault
    assert vault.secret_get("e2e_key", client="test") == "e2e-geheim"

    # löschen — der Hub nutzt einen eigenen <dialog>, kein Browser-confirm
    seite.click("#slist .srow [data-a=del]")
    seite.wait_for_selector("#confirmdlg[open]", timeout=5000)
    assert "e2e_key" in seite.inner_text("#cdtext"), "Der Dialog muss sagen, WAS gelöscht wird"
    seite.click("#confirmdlg .btn.danger")
    seite.wait_for_timeout(1800)
    assert vault.secret_get("e2e_key", client="test") is None
    assert "e2e_key" not in seite.inner_text("#slist")
    assert not seite.fehler, seite.fehler


def test_theme_und_sprache_umschalten(seite):
    _anmelden(seite)
    assert seite.evaluate("currentTheme()") in ("dark", "light")
    seite.evaluate("toggleTheme()")
    seite.wait_for_timeout(300)
    seite.evaluate("toggleLang()")
    seite.wait_for_timeout(300)
    assert seite.evaluate("LANG") == "en"
    assert not seite.fehler, seite.fehler


@pytest.mark.parametrize("breite,modus", [(390, "bottom"), (1280, "desktop")])
def test_kopfleiste_bricht_auf_keiner_breite(browser, hub, fresh_vault, breite, modus):
    """Regressionsschutz für den reparierten Header: nie horizontaler Überlauf."""
    ctx = browser.new_context(viewport={"width": breite, "height": 880}, locale="en-US")
    page = ctx.new_page()
    page.add_init_script(
        "try{localStorage.setItem('kmcp_toured','1');localStorage.setItem('kmcp_lang','de')}catch(e){}")
    page.goto(f"{hub}/ui", wait_until="networkidle")
    page.fill("#pw", TEST_PASSWORD)
    page.click("#loginbtn")
    page.wait_for_timeout(2000)

    doc_breite = page.evaluate("document.documentElement.scrollWidth")
    fenster = page.evaluate("window.innerWidth")
    assert doc_breite <= fenster, f"Horizontaler Überlauf bei {breite}px"

    nav_sichtbar = page.evaluate(
        "getComputedStyle(document.querySelector('nav.desktop')).display !== 'none'")
    assert nav_sichtbar is (modus == "desktop")

    # Der Abmelden-Knopf muss vollständig im Bild sein
    rechts = page.evaluate("document.getElementById('logoutbtn').getBoundingClientRect().right")
    assert rechts <= fenster, "Abmelden-Knopf ragt aus dem Bild"
    ctx.close()


def test_serverfehler_erscheint_als_banner(seite):
    """Früher scheiterten Serverfehler stumm — der Nutzer sah gar nichts."""
    _anmelden(seite)
    # Eine 500er-Antwort erzwingen, ohne den Server anzufassen: fetch abfangen.
    seite.evaluate("""() => {
        const echt = window.fetch;
        window.fetch = () => Promise.resolve(new Response(
            JSON.stringify({error: 'kaputt', ref: 'abcd1234'}),
            {status: 500, headers: {'Content-Type': 'application/json'}}));
    }""")
    seite.evaluate("() => { api('/ui/api/health').catch(() => {}); }")
    seite.wait_for_selector("#errbanner.on", timeout=5000)
    text = seite.inner_text("#errbanner")
    assert "schiefgelaufen" in text
    assert "abcd1234" in text, "Die Referenznummer muss sichtbar sein"


def test_verbindungsabbruch_erscheint_als_banner(seite):
    _anmelden(seite)
    seite.evaluate("() => { window.fetch = () => Promise.reject(new TypeError('failed')); }")
    seite.evaluate("() => { api('/ui/api/health').catch(() => {}); }")
    seite.wait_for_selector("#errbanner.on", timeout=5000)
    assert "Keine Verbindung" in seite.inner_text("#errbanner")


@pytest.mark.parametrize("locale,erwartet", [("en-US", "en"), ("de-DE", "de")])
def test_browsersprache_bestimmt_die_startsprache(browser, hub, fresh_vault, locale, erwartet):
    """Ein Franzose soll Englisch sehen, ein Deutscher Deutsch — ohne einen Klick.

    Dieser Test hätte den CI-Fehler sofort gezeigt: Lokal (deutscher Rechner) startete
    die Oberfläche deutsch, in CI englisch — und drei Tests suchten die falschen Texte.
    """
    ctx = browser.new_context(locale=locale)
    page = ctx.new_page()
    page.add_init_script("try{localStorage.removeItem('kmcp_lang');localStorage.setItem('kmcp_toured','1')}catch(e){}")
    page.goto(f"{hub}/ui", wait_until="networkidle")
    page.wait_for_timeout(400)
    assert page.evaluate("LANG") == erwartet
    ctx.close()


def test_ungueltiger_secret_name_erklaert_sich(seite):
    """Der Fehler, der den Nutzer blockiert hat.

    Ein Secret-Name mit „@" wird vom Server abgelehnt — mit einer präzisen Begründung.
    Die Oberfläche warf sie weg und zeigte nur „Fehler beim Speichern". Der Nutzer stand
    ratlos da und dachte, das Speichern sei kaputt. Jetzt muss dastehen, WAS erlaubt ist.
    """
    _anmelden(seite)
    seite.evaluate("tab('secrets')")
    seite.wait_for_timeout(600)

    seite.fill("#sname", "api@key")
    seite.fill("#svalue", "geheim")
    seite.click("#addbtn")
    seite.wait_for_timeout(1500)

    meldung = seite.inner_text("#secerr")
    assert meldung.strip(), "Es muss eine Meldung im Formular stehen — nicht nur ein flüchtiger Toast"
    # Sie muss ERKLÄREN, nicht bloß melden.
    assert "Fehler beim Speichern" not in meldung
    assert any(w in meldung.lower() for w in ("erlaubt", "allowed", "zeichen", "characters")), meldung

    # Und das Secret darf natürlich nicht angelegt worden sein
    assert "api@key" not in seite.inner_text("#slist")


def test_gueltiger_secret_name_klappt_weiterhin(seite):
    """Die Gegenprobe: Die neue Fehlerzeile darf den guten Weg nicht stören."""
    _anmelden(seite)
    seite.evaluate("tab('secrets')")
    seite.wait_for_timeout(600)

    seite.fill("#sname", "OPENAI_API_KEY")
    seite.fill("#svalue", "sk-egal")
    seite.click("#addbtn")
    seite.wait_for_timeout(1500)

    assert "OPENAI_API_KEY" in seite.inner_text("#slist")
    assert not seite.inner_text("#secerr").strip(), "Nach Erfolg muss die Fehlerzeile leer sein"
