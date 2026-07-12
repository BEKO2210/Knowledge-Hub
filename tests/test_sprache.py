"""Wachhund für die Übersetzung.

Ohne diesen Test schleicht sich beim nächsten Feature wieder deutscher Text in die
englische Oberfläche — und niemand merkt es, weil man selbst deutsch liest.
Er ruft die Oberfläche auf Englisch auf und sucht jeden sichtbaren deutschen Text.
"""

from __future__ import annotations

import re

import pytest

pytest.importorskip("playwright")

from test_e2e import _anmelden, browser, hub  # noqa: E402,F401 - Fixtures wiederverwenden

UMLAUT = re.compile(r"[äöüÄÖÜß]")
DEUTSCH = re.compile(
    r"\b(alle|der|die|das|und|oder|nicht|kein|keine|wird|werden|wurde|ist|sind|hat|"
    r"eine|einen|dein|deine|sich|noch|mehr|auch|nur|kann|muss|beim|zum|zur|vom|"
    r"mit|aus|bei|nach|ohne|gegen|sicherung|fehler|lauf|knoten|projekt|projekte|"
    r"schlüssel|anmeldung|abmelden|geräte|sitzung|uhr|erledigt|gespeichert|"
    r"gelöscht|kopiert|passwort|läuft|hinweis|jetzt|hier|dann|wenn|damit|dass|"
    r"bereits|wieder|immer)\b",
    re.I,
)
# Englische Funktionswörter: Wo die stehen, ist der Satz englisch — auch wenn er
# zufällig ein Wort enthält, das im Deutschen ebenfalls vorkommt („is", „name").
ENGLISCH = re.compile(r"\b(the|and|or|not|is|are|you|your|this|that|with|for|from|will)\b", re.I)

SAMMLER = """() => {
    const out = [];
    const walk = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
    let n;
    while (n = walk.nextNode()) {
        const el = n.parentElement;
        if (!el || !el.offsetParent) continue;
        const s = n.textContent.trim();
        if (s.length > 2) out.push(s);
    }
    for (const el of document.querySelectorAll('[placeholder],[aria-label],[title]')) {
        if (!el.offsetParent) continue;
        for (const a of ['placeholder', 'aria-label', 'title']) {
            const v = el.getAttribute(a);
            if (v && v.trim().length > 2) out.push(v.trim());
        }
    }
    return out;
}"""


def _deutsch(text: str) -> bool:
    if UMLAUT.search(text):
        return True
    return bool(DEUTSCH.search(text)) and not ENGLISCH.search(text)


@pytest.fixture
def englische_seite(browser, hub, fresh_vault):  # noqa: F811
    ctx = browser.new_context(viewport={"width": 1440, "height": 1000}, locale="en-US")
    page = ctx.new_page()
    page.add_init_script(
        "try{localStorage.setItem('kmcp_toured','1');localStorage.setItem('kmcp_lang','en')}catch(e){}")
    page.goto(f"{hub}/ui", wait_until="networkidle")
    yield page
    ctx.close()


def test_login_ist_auf_englisch(englische_seite):
    reste = [s for s in englische_seite.evaluate(SAMMLER) if _deutsch(s)]
    assert not reste, f"Deutscher Text im englischen Login: {reste}"


@pytest.mark.parametrize("reiter", ["graph", "ask", "secrets", "mapping", "connect", "health", "audit"])
def test_kein_deutscher_text_im_englischen_modus(englische_seite, reiter):
    """Jeder Reiter muss im EN-Modus frei von deutschem Text sein."""
    _anmelden(englische_seite)
    englische_seite.evaluate(f"tab('{reiter}')")
    englische_seite.wait_for_timeout(1500)
    reste = [s for s in englische_seite.evaluate(SAMMLER) if _deutsch(s)]
    assert not reste, f"Deutscher Text im Reiter „{reiter}“: {reste}"


def test_umschalten_auf_deutsch_bringt_deutsch_zurueck(englische_seite):
    """Die Gegenprobe: Deutsch darf durch die Übersetzung nicht verloren gehen."""
    _anmelden(englische_seite)
    englische_seite.evaluate("toggleLang()")
    englische_seite.wait_for_timeout(800)
    assert englische_seite.evaluate("LANG") == "de"
    texte = englische_seite.evaluate(SAMMLER)
    assert any(_deutsch(s) for s in texte), "Nach dem Umschalten muss die Oberfläche deutsch sein"


def test_serverseitige_befunde_folgen_der_sprache(client, auth, fresh_vault):
    """Die Diagnose entsteht im Server — sie muss der Sprache der Anfrage folgen."""
    en = client.get("/ui/api/health", headers={**auth, "X-Lang": "en"}).json()["checks"]
    de = client.get("/ui/api/health", headers={**auth, "X-Lang": "de"}).json()["checks"]
    namen_en = {c["name"] for c in en}
    namen_de = {c["name"] for c in de}
    assert "Nightly mapping" in namen_en
    assert "Nacht-Mapping" in namen_de
    assert namen_en != namen_de
