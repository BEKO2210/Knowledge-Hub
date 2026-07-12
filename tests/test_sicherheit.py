"""D6 — Sicherheits-Härtung: CSP ohne Inline-Skripte, Schreib-Drossel, Wertgrenzen.

Jeder Test hier beschreibt eine Regel, die sich nicht von selbst hält:
  * Die CSP verbietet Inline-Skripte — aber nur, solange niemand wieder ein
    onclick="…" ins Markup schreibt. Der Wachhund unten schlägt dann an.
  * Der Setup-Wizard ist die eine erlaubte Ausnahme (ein Skriptblock per Hash) —
    und der Hash stimmt nur, solange render() den Block nicht anfasst.
"""

from __future__ import annotations

import re
from pathlib import Path

import ratelimit
import vault

WEB = Path(__file__).resolve().parent.parent / "web"

INLINE_HANDLER = re.compile(r'\son[a-z]+="')


# ---------------------------------------------------------------------------
# CSP: keine Inline-Skripte mehr
# ---------------------------------------------------------------------------
def test_csp_verbietet_inline_skripte(client, auth, fresh_vault):
    # fresh_vault: ohne Vault gilt das System als uneingerichtet und /ui wäre der
    # Wizard — geprüft werden soll aber die CSP der eigentlichen Oberfläche.
    csp = client.get("/ui", headers=auth).headers["content-security-policy"]
    script_src = next(t for t in csp.split(";") if t.strip().startswith("script-src"))
    assert "'unsafe-inline'" not in script_src, (
        "script-src darf 'unsafe-inline' nicht mehr enthalten — sonst führt "
        "eingeschleustes Markup wieder Code aus"
    )
    assert "'self'" in script_src


def test_markup_enthaelt_keine_inline_handler():
    """Der Wachhund: Ein einziges neues onclick="…" bräche die Oberfläche stumm —
    die CSP blockt es, der Knopf wäre einfach tot. Hier fällt es stattdessen auf."""
    for datei in ("index.html", "app.js"):
        text = (WEB / datei).read_text(encoding="utf-8")
        treffer = INLINE_HANDLER.findall(text)
        assert not treffer, (
            f"{datei} enthält Inline-Handler ({len(treffer)}x) — die CSP führt sie nicht aus. "
            "Stattdessen data-act/data-form/data-change verwenden (Aktions-Register in app.js)."
        )


def test_jede_aktion_im_markup_ist_registriert():
    """Ein data-act ohne Eintrag im Aktions-Register ist derselbe stumme Tod wie ein
    geblocktes onclick — der Knopf tut nichts. Markup und Register müssen zueinander passen."""
    html = (WEB / "index.html").read_text(encoding="utf-8")
    js = (WEB / "app.js").read_text(encoding="utf-8")

    def registriert(block: str) -> set[str]:
        m = re.search(rf"const {block} = \{{(.*?)\n\}};", js, re.S)
        assert m, f"Register {block} nicht in app.js gefunden"
        return set(re.findall(r"^\s*'?([\w-]+)'?:", m.group(1), re.M))

    aktionen, formulare, wechsel = registriert("AKTIONEN"), registriert("FORMULARE"), registriert("WECHSEL")
    for quelle in (html, js):
        for act in re.findall(r'data-act="([\w-]+)"', quelle):
            assert act in aktionen, f"data-act={act!r} hat keinen Eintrag im Aktions-Register"
        for form in re.findall(r'data-form="([\w-]+)"', quelle):
            assert form in formulare, f"data-form={form!r} hat keinen Eintrag in FORMULARE"
        for ch in re.findall(r'data-change="([\w-]+)"', quelle):
            assert ch in wechsel, f"data-change={ch!r} hat keinen Eintrag in WECHSEL"


def test_wizard_csp_erlaubt_genau_seinen_skriptblock():
    """Der Wizard ist die eine Ausnahme: sein Skriptblock ist per Hash erlaubt.
    render() darf den Block deshalb niemals verändern — sonst stimmt der Hash
    nicht mehr und die Einrichtung ist auf jedem frischen System tot."""
    import setup_wizard
    import ui

    assert "sha256-" in setup_wizard.WIZARD_CSP
    assert "'unsafe-inline'" not in setup_wizard.WIZARD_CSP.split("style-src")[0]

    skript_vorher = re.search(r"<script>(.*)</script>", setup_wizard.WIZARD_HTML, re.S).group(1)
    skript_nachher = re.search(r"<script>(.*)</script>", ui.render(setup_wizard.WIZARD_HTML), re.S).group(1)
    assert skript_vorher == skript_nachher, (
        "render() hat den Skriptblock des Wizards verändert — der CSP-Hash passt nicht mehr"
    )


# ---------------------------------------------------------------------------
# Schreib-Drossel
# ---------------------------------------------------------------------------
def test_drossel_bremst_und_erholt_sich(monkeypatch):
    monkeypatch.setitem(ratelimit._LIMITS, "write", (60, 3))
    assert [ratelimit.throttle("write", "1.2.3.4")[0] for _ in range(3)] == [True, True, True]
    erlaubt, gerade = ratelimit.throttle("write", "1.2.3.4")
    assert not erlaubt and gerade, "Der vierte Aufruf muss ablehnen — und zwar als ERSTE Ablehnung"
    erlaubt, gerade = ratelimit.throttle("write", "1.2.3.4")
    assert not erlaubt and not gerade, "Folgeablehnungen dürfen keinen weiteren Audit-Eintrag auslösen"
    # andere IP bleibt unberührt
    assert ratelimit.throttle("write", "5.6.7.8")[0] is True


def test_schreib_drossel_liefert_429(client, auth, fresh_vault, monkeypatch):
    monkeypatch.setitem(ratelimit._LIMITS, "write", (60, 2))
    ratelimit._hits.clear()
    for _ in range(2):
        client.post("/ui/api/secrets", json={"name": "d6", "value": "x"}, headers=auth)
    r = client.post("/ui/api/secrets", json={"name": "d6", "value": "x"}, headers=auth)
    assert r.status_code == 429
    assert r.headers.get("retry-after") == "60"
    assert "error" in r.json()
    # Die Sperre steht im Audit-Log — genau einmal
    audit = vault.AUDIT_PATH.read_text() if vault.AUDIT_PATH.exists() else ""
    assert audit.count("WRITE-THROTTLED") == 1


def test_lesende_endpunkte_werden_nicht_gedrosselt(client, auth, fresh_vault, monkeypatch):
    monkeypatch.setitem(ratelimit._LIMITS, "write", (60, 1))
    ratelimit._hits.clear()
    client.post("/ui/api/secrets", json={"name": "d6", "value": "x"}, headers=auth)
    for _ in range(5):
        assert client.get("/ui/api/secrets", headers=auth).status_code == 200


# ---------------------------------------------------------------------------
# Wertgrenzen gelten im Vault, nicht nur in der Oberfläche
# ---------------------------------------------------------------------------
def test_wertgrenze_gilt_im_vault(fresh_vault):
    import pytest

    with pytest.raises(ValueError, match="zu lang"):
        vault.secret_set("gross", "x" * (vault.SECRET_VALUE_MAX + 1), client="test")
    with pytest.raises(ValueError, match="leer"):
        vault.secret_set("leer", "", client="test")
    assert vault.secret_list(client="test") == []
    # Beide Ablehnungen stehen im Audit-Log
    audit = vault.AUDIT_PATH.read_text()
    assert audit.count("SET-REJECT") == 2


def test_abgelehnter_name_steht_im_audit(client, auth, fresh_vault):
    r = client.post("/ui/api/secrets", json={"name": "böse/../x", "value": "v"}, headers=auth)
    assert r.status_code == 400
    assert "SET-REJECT" in vault.AUDIT_PATH.read_text()
