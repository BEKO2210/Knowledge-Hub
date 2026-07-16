"""Vollständiges UI-Inventar + Register-Konsistenz in BEIDE Richtungen (Audit-Run 16).

test_sicherheit.py prüft eine Richtung: jedes data-act im Markup hat einen Register-
Eintrag (kein toter Knopf). Hier kommt die Gegenrichtung dazu — ein Register-Eintrag
ohne Markup ist toter Code, der bei einer Umbenennung unbemerkt verrottet — plus die
Panel-Erreichbarkeit (jedes tab-Panel muss über irgendeinen Weg erreichbar sein) und
ein Live-Abgleich gegen die laufende Oberfläche.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

WEB = Path(__file__).resolve().parent.parent / "web"
HTML = (WEB / "index.html").read_text(encoding="utf-8")
JS = (WEB / "app.js").read_text(encoding="utf-8")


def _register(block: str) -> set[str]:
    m = re.search(rf"const {block} = \{{(.*?)\n\}};", JS, re.S)
    assert m, f"Register {block} nicht in app.js gefunden"
    return set(re.findall(r"^\s*'?([\w-]+)'?:", m.group(1), re.M))


AKTIONEN = _register("AKTIONEN")
FORMULARE = _register("FORMULARE")
WECHSEL = _register("WECHSEL")
MARKUP_UND_JS = HTML + JS


@pytest.mark.parametrize(
    "block,reg,attr",
    [
        ("AKTIONEN", AKTIONEN, "data-act"),
        ("FORMULARE", FORMULARE, "data-form"),
        ("WECHSEL", WECHSEL, "data-change"),
    ],
)
def test_kein_verwaister_register_eintrag(block, reg, attr):
    """Gegenrichtung zu test_sicherheit: jeder Register-Eintrag muss auch benutzt werden.

    Ein Eintrag ohne data-*-Vorkommen (weder im statischen Markup noch im dynamisch
    erzeugten Markup in app.js) ist toter Code — genau die Art Eintrag, die bei einer
    Umbenennung stehen bleibt und niemandem auffällt.
    """
    benutzt = set(re.findall(rf'{attr}="([\w-]+)"', MARKUP_UND_JS))
    verwaist = sorted(k for k in reg if k not in benutzt)
    assert not verwaist, f"{block}: verwaiste Einträge ohne {attr}: {verwaist}"


def test_jedes_tab_panel_ist_erreichbar():
    """Jedes tab-<x>-Panel muss über einen Weg erreichbar sein: Haupt-Tab, Über-Menü,
    ein programmatischer tab('x')-Aufruf oder eine eigene Aktion (report)."""
    panels = set(re.findall(r'id="tab-(\w+)"', HTML))
    haupt = set(re.findall(r'data-tab="(\w+)"', HTML))
    uebermenue = set(re.findall(r'data-act="moretab"[^>]*data-arg="(\w+)"', HTML))
    uebermenue |= set(re.findall(r'data-arg="(\w+)"[^>]*data-act="moretab"', HTML))
    tab_calls = set(re.findall(r"tab\('(\w+)'\)", JS))
    aktion = {"report"} if "report" in AKTIONEN else set()
    erreichbar = haupt | uebermenue | tab_calls | aktion
    unerreichbar = sorted(p for p in panels if p not in erreichbar)
    assert not unerreichbar, f"Panels ohne jeden Weg dorthin: {unerreichbar}"


def test_jeder_haupttab_hat_ein_panel():
    tabs = set(re.findall(r'data-tab="(\w+)"', HTML))
    panels = set(re.findall(r'id="tab-(\w+)"', HTML))
    fehlend = sorted(t for t in tabs if t not in panels)
    assert not fehlend, f"data-tab ohne zugehöriges Panel: {fehlend}"


def test_inventar_umfang_ist_stabil():
    """Schnappschuss der Größenordnung — schlägt an, wenn Elemente unbemerkt
    verschwinden oder das Register auseinanderläuft (Regressionsanker)."""
    acts = len(re.findall(r'data-act="[\w-]+"', HTML))
    # Formulare/Wechsel stehen teils im statischen Markup, teils in dynamisch von app.js
    # erzeugten Karten (2FA, Passwort, Backup-Ziel) — darum über HTML+JS zählen.
    forms = len(set(re.findall(r'data-form="[\w-]+"', MARKUP_UND_JS)))
    changes = len(set(re.findall(r'data-change="[\w-]+"', MARKUP_UND_JS)))
    dialoge = len(re.findall(r"<dialog", HTML))
    assert acts >= 40, f"auffällig wenige data-act im Markup: {acts}"
    assert forms >= 10, f"data-form (Markup+JS): {forms}"
    assert changes >= 5, f"data-change (Markup+JS): {changes}"
    assert dialoge == 5, f"erwartet 5 Dialoge, gefunden {dialoge}"
    assert len(AKTIONEN) >= 40 and len(FORMULARE) >= 10 and len(WECHSEL) >= 5


def _panel(name: str) -> str:
    """Inhalt eines <section id="tab-NAME"> … </section> (grobe, aber stabile Extraktion)."""
    m = re.search(rf'id="tab-{name}"(.*?)</section>', HTML, re.S)
    return m.group(1) if m else ""


def test_menue_reorg_karten_liegen_im_richtigen_panel():
    """Menü-Reorganisation (Option B): Projekte + Einstellungen sind eigene Panels, und die
    verschobenen Karten liegen im NEUEN Panel und NICHT mehr im alten (Regressionsschutz —
    ein Refactor darf die Bündelung nicht versehentlich rückgängig machen)."""
    # Haupt-Navigation = genau diese vier Tabs
    haupt = set(re.findall(r'data-tab="(\w+)"', HTML))
    assert haupt == {"graph", "ask", "projekte", "mapping"}, f"Haupt-Tabs verschoben: {haupt}"
    # Projekte-Panel trägt Projektliste + Graph-Bestand …
    proj = _panel("projekte")
    assert 'id="projlist"' in proj and 'id="graphstock"' in proj
    # … und Mapping trägt sie NICHT mehr (aber weiter Kosten + Zeitplan)
    mp = _panel("mapping")
    assert 'id="projlist"' not in mp and 'id="graphstock"' not in mp
    assert 'id="mapcosts"' in mp and 'data-form="mapping"' in mp
    # Einstellungen-Panel bündelt 2FA + Vault + Backup …
    st = _panel("settings")
    assert 'id="twofabody"' in st and 'id="vaultbody"' in st and 'id="backupcard"' in st
    # … und Diagnose trägt sie NICHT mehr (bleibt reine Statusanzeige)
    he = _panel("health")
    assert 'id="twofabody"' not in he and 'id="backupcard"' not in he
    assert 'id="healthchecks"' in he
    # Verbinden + Secrets sind über das Mehr-Menü erreichbar (nicht mehr Haupt-Tab)
    for arg in ("secrets", "settings", "connect"):
        assert re.search(rf'data-act="moretab" data-arg="{arg}"', HTML), f"{arg} fehlt im Mehr-Menü"


# ---------------------------------------------------------------------------
# Live-Abgleich gegen die laufende Oberfläche
# ---------------------------------------------------------------------------
pytest.importorskip("playwright")
import socket  # noqa: E402
import threading  # noqa: E402
import time  # noqa: E402

import uvicorn  # noqa: E402
from conftest import TEST_PASSWORD  # noqa: E402
from playwright.sync_api import sync_playwright  # noqa: E402

ALLE_PANELS = [
    "graph",
    "ask",
    "projekte",
    "mapping",
    "secrets",
    "settings",
    "connect",
    "health",
    "audit",
    "report",
]


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


@pytest.fixture
def seite(hub, fresh_vault):
    with sync_playwright() as p:
        b = p.chromium.launch()
        ctx = b.new_context(viewport={"width": 1280, "height": 880}, locale="en-US")
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
            raise AssertionError("Login-Bildschirm blieb sichtbar")
        yield page
        ctx.close()
        b.close()


def test_live_alle_panels_erreichbar(seite):
    """Jedes der 8 Panels lässt sich in der echten UI aktivieren (auch die im Über-Menü)."""
    for name in ALLE_PANELS:
        seite.evaluate(f"tab('{name}')")
        seite.wait_for_timeout(150)
        an = seite.evaluate(f"document.getElementById('tab-{name}').classList.contains('on')")
        assert an, f"Panel tab-{name} wurde nicht aktiv"
    assert not seite.fehler, seite.fehler


def test_live_jedes_data_act_element_existiert(seite):
    """Jeder im Markup deklarierte data-act-Wert hat mindestens ein Element im DOM —
    der Live-Gegenbeweis dazu, dass das Register nicht ins Leere zeigt."""
    acts = sorted(set(re.findall(r'data-act="([\w-]+)"', HTML)))
    fehlend = seite.evaluate('(acts) => acts.filter(a => !document.querySelector(`[data-act="${a}"]`))', acts)
    # 'confirm'/'pickok' etc. sitzen in Dialogen, sind aber im DOM (nur unsichtbar) vorhanden.
    assert not fehlend, f"data-act ohne Element im DOM: {fehlend}"


def test_live_dialoge_oeffnen_und_schliessen(seite):
    """Jeder <dialog> lässt sich öffnen und wieder schließen (showModal/close existieren)."""
    for dlg in ("moredlg", "pickerdlg", "ignoredlg", "confirmdlg", "tourdlg"):
        offen = seite.evaluate(
            f"""() => {{ const d = document.getElementById('{dlg}');
                 if(!d) return 'fehlt'; d.showModal(); const o = d.open; d.close(); return o ? 'ok' : 'zu'; }}"""
        )
        assert offen == "ok", f"Dialog {dlg}: {offen}"
    assert not seite.fehler, seite.fehler


def test_live_theme_sprache_tour(seite):
    seite.evaluate("toggleTheme()")
    seite.wait_for_timeout(150)
    assert seite.evaluate("currentTheme()") in ("dark", "light")
    seite.evaluate("toggleLang()")
    seite.wait_for_timeout(150)
    assert seite.evaluate("LANG") == "en"
    seite.evaluate("startTour()")
    seite.wait_for_timeout(150)
    assert not seite.fehler, seite.fehler
