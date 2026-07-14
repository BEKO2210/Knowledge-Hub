"""Knoten-Inhalte (rationale) in Graph-Kontexte einmischen.

graphify query/explain geben nur Knoten-NAMEN aus (NODE …/Node: …). Der eigentliche
Inhalt eines Knotens steht aber im Feld `rationale` in graph.json — ohne ihn kann die
KI Fakten wie „Host-Port 8097" nicht nennen, obwohl sie im Graphen stehen. Dieses Modul
schlägt die rationale der im Kontext erwähnten Knoten nach und hängt sie als
INHALT-Block an, damit die Antworten aus den Daten kommen statt aus Vermutungen.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

# graph.json wird pro (Pfad, mtime) gecacht — die Dateien ändern sich nur beim Mapping.
_CACHE: dict[str, tuple[float, dict[str, str]]] = {}

# Knoten-Namen in graphify-Ausgaben:
#   query:   "NODE <label> [src=…"
#   explain: "Node: <label>" und "  --> <label> [relation]"
_NODE_RE = re.compile(r"^NODE (.+?) \[src=", re.MULTILINE)
_EXPLAIN_RE = re.compile(r"^Node: (.+?)\s*$|^\s*(?:-->|<--) (.+?) \[", re.MULTILINE)

_PRO_KNOTEN = 700  # Zeichen je Knoten — genug für Fakten, zu wenig zum Ausufern


def _rationale_map(graph_json: Path) -> dict[str, str]:
    try:
        mtime = graph_json.stat().st_mtime
    except OSError:
        return {}
    key = str(graph_json)
    cached = _CACHE.get(key)
    if cached and cached[0] == mtime:
        return cached[1]
    try:
        nodes = json.loads(graph_json.read_text()).get("nodes", [])
    except Exception:  # noqa: BLE001 - kaputter Graph darf keine Antwort verhindern
        return {}
    m: dict[str, str] = {}
    for n in nodes:
        r = (n.get("rationale") or "").strip()
        if not r:
            continue
        label = str(n.get("label") or n.get("id") or "").strip()
        if label:
            m.setdefault(label.casefold(), r)
    _CACHE[key] = (mtime, m)
    return m


def _labels(context: str) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for m in _NODE_RE.finditer(context):
        out.append(m.group(1))
    for m in _EXPLAIN_RE.finditer(context):
        out.append(m.group(1) or m.group(2))
    result = []
    for label in out:
        label = (label or "").strip()
        if label and label.casefold() not in seen:
            seen.add(label.casefold())
            result.append(label)
    return result


def anreichern(project_dir: Path, context: str, char_budget: int = 6000) -> str:
    """Kontext um einen INHALT-Block mit den rationale der erwähnten Knoten ergänzen.

    Reihenfolge = Reihenfolge im Kontext (Seeds zuerst, dann nach Relevanz), damit
    beim Budget-Schnitt die wichtigsten Inhalte überleben. Gibt bei Problemen den
    Kontext unverändert zurück — Anreicherung ist Zugabe, nie Voraussetzung.
    """
    if not context:
        return context
    rationale = _rationale_map(project_dir / "graphify-out" / "graph.json")
    if not rationale:
        return context
    lines: list[str] = []
    used = 0
    for label in _labels(context):
        text = rationale.get(label.casefold())
        if not text:
            continue
        text = " ".join(text.split())[:_PRO_KNOTEN]
        line = f"- {label}: {text}"
        if used + len(line) > char_budget:
            break
        lines.append(line)
        used += len(line)
    if not lines:
        return context
    return (
        context + "\n\nINHALT (gespeicherter Inhalt der Knoten — maßgeblich für Fakten):\n" + "\n".join(lines)
    )
