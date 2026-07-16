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
from conftest import TEST_PASSWORD, TMP

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
        "try{localStorage.setItem('kmcp_toured','1');localStorage.setItem('kmcp_lang','de')}catch(e){}"
    )
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
        weg = page.evaluate("() => getComputedStyle(document.getElementById('login')).display === 'none'")
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
        "try{localStorage.setItem('kmcp_toured','1');localStorage.setItem('kmcp_lang','de')}catch(e){}"
    )
    page.goto(f"{hub}/ui", wait_until="networkidle")
    page.fill("#pw", TEST_PASSWORD)
    page.click("#loginbtn")
    page.wait_for_timeout(2000)

    doc_breite = page.evaluate("document.documentElement.scrollWidth")
    fenster = page.evaluate("window.innerWidth")
    assert doc_breite <= fenster, f"Horizontaler Überlauf bei {breite}px"

    nav_sichtbar = page.evaluate("getComputedStyle(document.querySelector('nav.desktop')).display !== 'none'")
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
    page.add_init_script(
        "try{localStorage.removeItem('kmcp_lang');localStorage.setItem('kmcp_toured','1')}catch(e){}"
    )
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


def test_projekt_umschalten_meldet_fehler_und_springt_zurueck(seite, monkeypatch):
    """Vorher: Der Schalter blieb umgelegt UND es kam eine Erfolgsmeldung — obwohl der
    Server abgelehnt hatte. Der Nutzer glaubte, es sei gespeichert."""
    import config
    from api import mapping as m

    # Der Hub erlaubt Projekte nur unter $HOME und /opt. Für den Test wird das
    # Wegwerf-Verzeichnis zusätzlich zugelassen — die Regel selbst bleibt unangetastet.
    (TMP / "projekt-x").mkdir(exist_ok=True)
    monkeypatch.setattr(m, "BROWSE_ROOTS", [*m.BROWSE_ROOTS, TMP])

    # Die Projektliste liegt in der GETEILTEN Test-Konfiguration. Ohne Aufräumen sähe
    # jeder spätere Test dieses Projekt — der Sprach-Wachhund hielt „projekt-x" prompt
    # für unübersetzten deutschen Text im Mapping-Tab.
    vorher_projekte = config.project_entries()

    _anmelden(seite)
    seite.evaluate("tab('projekte')")
    seite.wait_for_timeout(1200)

    seite.evaluate(
        """(pfad) => api('/ui/api/mapping/projects', {method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({path: pfad})})""",
        str(TMP / "projekt-x"),
    )
    seite.wait_for_timeout(1000)
    seite.evaluate("loadProjectsCard()")
    seite.wait_for_selector("#projlist input[type=checkbox]", timeout=10000)

    schalter = seite.locator("#projlist input[type=checkbox]").first
    vorher = schalter.is_checked()
    # Den Server zum Ablehnen zwingen
    seite.evaluate("""() => {
        const echt = window.fetch;
        window.fetch = (u, o) => (o && o.method === 'PATCH')
            ? Promise.resolve(new Response(JSON.stringify({error: 'Projekt nicht gefunden'}),
                {status: 404, headers: {'Content-Type': 'application/json'}}))
            : echt(u, o);
    }""")
    schalter.click()
    seite.wait_for_timeout(1200)

    try:
        assert schalter.is_checked() is vorher, "Der Schalter muss auf den echten Zustand zurückspringen"
        meldung = seite.inner_text("#toasts")
        assert "Projekt nicht gefunden" in meldung, f"Die Server-Erklärung muss ankommen, kam: {meldung!r}"
    finally:
        config.save_projects(vorher_projekte)


def test_zweifaktor_knopf_bleibt_nach_fehler_bedienbar(seite):
    """Vorher: Der Knopf wurde vor dem Aufruf deaktiviert und nie wieder aktiviert.
    Nach einem Fehler konnte man 2FA nur noch durch Neuladen der Seite einrichten."""
    _anmelden(seite)
    seite.evaluate("tab('settings')")
    # Auf das Element warten, nicht auf die Uhr — loadTwoFA() lädt asynchron.
    seite.wait_for_selector("#start2fa", timeout=15000)

    seite.evaluate("""() => {
        const echt = window.fetch;
        window.fetch = (u, o) => String(u).includes('/2fa/setup')
            ? Promise.resolve(new Response(JSON.stringify({error: 'kaputt'}),
                {status: 500, headers: {'Content-Type': 'application/json'}}))
            : echt(u, o);
    }""")
    seite.click("#start2fa")
    seite.wait_for_timeout(1500)

    assert seite.is_enabled("#start2fa"), "Der Knopf darf nach einem Fehler nicht tot bleiben"


def test_kaputte_antwort_haengt_nicht_ewig(seite):
    """Antwortet der Tunnel mit einer HTML-Fehlerseite statt JSON, darf die Oberfläche
    nicht endlos im Ladezustand stehen bleiben — der Nutzer muss erfahren, was los ist."""
    _anmelden(seite)

    # Eine 502-HTML-Antwort simulieren, wie sie ein kaputter Tunnel liefert
    seite.evaluate("""() => {
        const echt = window.fetch;
        window.fetch = (u, o) => String(u).includes('/ui/api/secrets')
            ? Promise.resolve(new Response('<html><body>502 Bad Gateway</body></html>',
                {status: 200, headers: {'Content-Type': 'text/html'}}))
            : echt(u, o);
    }""")
    seite.evaluate("() => { loadSecrets().catch(() => {}); }")
    seite.wait_for_selector("#errbanner.on", timeout=8000)

    text = seite.inner_text("#errbanner")
    assert "gültige Antwort" in text or "Verbindung" in text, text


def test_graph_ohne_projekt_erklaert_sich(seite):
    """Ein frisch installierter Hub hat kein gemapptes Projekt.

    Vorher zeigte der Graphen-Tab dann eine komplett leere Fläche — keine Erklärung,
    kein Hinweis. Für einen neuen Nutzer sieht das aus, als sei der Hub kaputt.
    """
    _anmelden(seite)
    seite.evaluate("tab('graph')")
    seite.wait_for_timeout(2000)

    assert seite.is_visible("#graphempty"), "Ohne Projekt muss ein Leerzustand erscheinen"
    text = seite.inner_text("#graphempty")
    assert "Mapping" in text, f"Der Leerzustand muss den Weg zeigen: {text!r}"

    # Und der Knopf muss wirklich dorthin führen
    seite.click("#graphempty button")
    seite.wait_for_timeout(600)
    assert seite.evaluate("document.getElementById('tab-mapping').classList.contains('on')")


def test_falsches_altes_vault_passwort_wirft_nicht_raus(seite):
    """Der Server antwortete mit 401 — und die Oberfläche hält JEDEN 401 für ein
    ungültiges Sitzungs-Token und meldet ab. Wer sich beim Passwortwechsel vertippte,
    flog aus dem Hub, statt „Aktuelles Passwort stimmt nicht." zu lesen.
    """
    _anmelden(seite)
    seite.evaluate("tab('settings')")
    seite.wait_for_selector("#pwnew", timeout=15000)

    seite.fill("#pwold", "das-ist-nicht-mein-passwort")
    seite.fill("#pwnew", "neues-langes-passwort")
    seite.click("#pwbtn")
    seite.wait_for_timeout(2500)

    # NICHT ausgeloggt
    assert seite.evaluate("() => getComputedStyle(document.getElementById('login')).display === 'none'"), (
        "Ein falsches altes Passwort darf den Nutzer nicht abmelden"
    )

    meldung = (
        seite.inner_text("#toasts") + seite.inner_text("#pwmsg")
        if seite.locator("#pwmsg").count()
        else seite.inner_text("#toasts")
    )
    assert "stimmt nicht" in meldung.lower() or "aktuelles passwort" in meldung.lower(), meldung
