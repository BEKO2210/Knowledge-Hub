"""Run-025: Barrierefreiheit — Regeln, die sich nicht von selbst halten.

Im Browser gegen eine isolierte Instanz geprüft (chrome-devtools): Kontrast (WCAG AA)
in Hell/Dunkel, Reflow bei 320 px, Tastatur-Erreichbarkeit, ARIA, DE/EN, Reduced-Motion.
Diese Tests sichern die vier gefundenen Fixes gegen Rückfall.
"""

from __future__ import annotations

import re
from pathlib import Path

WEB = Path(__file__).resolve().parent.parent / "web"
HTML = (WEB / "index.html").read_text(encoding="utf-8")
CSS = (WEB / "app.css").read_text(encoding="utf-8")


def test_graph_canvas_hat_zugaenglichen_namen():
    """R25-3: der Force-Graph (#cv) ist ein <canvas> ohne Textalternative — er braucht
    role=img + aria-label, sonst bekommt ein Screenreader nur eine unbenannte Fläche."""
    m = re.search(r'id="cv"[^>]*', HTML)
    assert m, "#cv nicht gefunden"
    tag = m.group(0)
    assert 'role="img"' in tag
    assert "aria-label=" in tag
    assert "data-en-title=" in tag  # zweisprachig


def test_tour_zurueck_button_hat_label():
    """R25-4: #tourprev ist ein Icon-only-Button — ohne aria-label nur „button"."""
    m = re.search(r'id="tourprev"[^>]*', HTML)
    assert m and "aria-label=" in m.group(0)


def test_hint_nutzt_kontraststarke_farbe():
    """R25-1: #hint lag mit --mut2 bei 4,39:1 unter WCAG AA — jetzt --mut (AA erfüllt)."""
    m = re.search(r"#hint\{[^}]*\}", CSS)
    assert m, "#hint-Regel nicht gefunden"
    assert "color:var(--mut)" in m.group(0)
    assert "color:var(--mut2)" not in m.group(0)


def test_markenname_kuerzt_auf_mobil():
    """R25-2: ein langer (konfigurierbarer) Markenname darf den Header bei 320 px nicht
    über den Rand schieben (WCAG 1.4.10 Reflow) — .brandtext wird gekürzt."""
    assert re.search(r"\.logo \.brandtext\{[^}]*text-overflow:ellipsis", CSS)


def test_kein_icon_button_ohne_zugaenglichen_namen():
    """Wächter: jeder <button>, der nur ein Icon (svg/use) und keinen Text trägt, MUSS
    ein aria-label haben — sonst ist er für Screenreader ein namenloser Knopf."""
    ohne_label = []
    for m in re.finditer(r"<button\b([^>]*)>(.*?)</button>", HTML, re.S):
        attrs, inner = m.group(1), m.group(2)
        text = re.sub(r"<[^>]+>", "", inner).strip()  # Markup raus -> sichtbarer Text
        hat_icon = "<svg" in inner or "<use" in inner
        hat_namen = "aria-label=" in attrs or bool(text)
        if hat_icon and not text and not hat_namen:
            ohne_label.append(attrs.strip()[:60])
    assert not ohne_label, f"Icon-Buttons ohne Namen: {ohne_label}"
