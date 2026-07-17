"""Vier Gesundheitsebenen für Blue-Green-Deployments.

- Liveness:  Prozess lebt (offen, ein Statuswort).
- Readiness: Instanz darf Traffic annehmen — Config, Datenpfade, Vault, Projektliste,
  Graphen, MCP-Toolliste, Assets, Migrationsstand (offen, ein Statuswort, KEINE Details).
- Deep:      dieselben Checks mit Befund je Check (nur mit Bearer, wie MCP).

Details dürfen Projektnamen nennen, aber niemals absolute Serverpfade oder Secrets —
die Endpunkte hängen hinter dem Tunnel am öffentlichen Hostnamen.
"""

from __future__ import annotations

import json
import os
import time
from pathlib import Path

import config
import vault
from api.common import DATA_DIR, KNOWLEDGE_ROOT, _projects
from ui import WEB_DIR as _WEB_DIR

# Modul-Variable statt Direktimport in den Checks: so können Tests sie ersetzen.
WEB_DIR: Path = _WEB_DIR

# Die MCP-Werkzeuge, die ein gesunder Hub anbieten muss. Bewusst hart kodiert:
# Verschwindet eines durch einen Refactor, soll Readiness rot werden — nicht still schrumpfen.
EXPECTED_TOOLS = frozenset(
    {
        "projects_list",
        "graph_query",
        "graph_explain",
        "graph_path",
        "report_get",
        "graph_build",
        "graph_build_status",
        "secret_list",
        "secret_get",
        "secret_set",
        "secret_delete",
        "note_save",
        "note_list",
        "project_create",
    }
)

# Bekannte Vault-Dokumentversionen; 0 = Vault existiert noch nicht (frischer Hub — gültig).
KNOWN_VAULT_VERSIONS = frozenset({0, 1, 2})

_ASSETS = ("index.html", "app.css", "app.js")


def _check_config() -> tuple[bool, str]:
    cfg = config.load()
    if not isinstance(cfg, dict) or "server" not in cfg:
        return False, "Konfiguration unvollständig (server-Sektion fehlt)"
    return True, "geladen"


def _check_datenpfade() -> tuple[bool, str]:
    fehler = []
    if not KNOWLEDGE_ROOT.is_dir():
        fehler.append("knowledge_root fehlt")
    elif not os.access(KNOWLEDGE_ROOT, os.R_OK | os.X_OK):
        fehler.append("knowledge_root nicht lesbar")
    if not DATA_DIR.is_dir():
        fehler.append("Datenverzeichnis fehlt")
    elif not os.access(DATA_DIR, os.W_OK):
        fehler.append("Datenverzeichnis nicht beschreibbar")
    return (False, "; ".join(fehler)) if fehler else (True, "lesbar und beschreibbar")


def _check_vault() -> tuple[bool, str]:
    st = vault.status()  # wirft nicht; interpretiert auch »existiert nicht« kontrolliert
    if not st["exists"]:
        return True, "kein Vault angelegt (frische Instanz)"
    return True, f"vorhanden, Version {st['version']}, entsperrbar: {st['unlocked'] or st['auto_unlock']}"


def _check_projektliste() -> tuple[bool, str]:
    return True, f"{len(_projects())} Projekte"


def _check_graphen() -> tuple[bool, str]:
    defekt = []
    geprueft = 0
    for name in _projects():
        pfad = KNOWLEDGE_ROOT / name / "graphify-out" / "graph.json"
        if not pfad.exists():
            continue
        geprueft += 1
        try:
            g = json.loads(pfad.read_text(encoding="utf-8"))
            if not isinstance(g.get("nodes"), list):
                defekt.append(f"{name} (keine nodes-Liste)")
        except (json.JSONDecodeError, OSError, UnicodeDecodeError) as e:
            defekt.append(f"{name} ({type(e).__name__})")
    if defekt:
        return False, "nicht parsebar: " + ", ".join(defekt)
    return True, f"{geprueft} Graphen parsebar"


# --- Gedrosselte Readiness-Probe (P0-7) --------------------------------------
# /healthz/ready ist offen (kein Bearer) und wird von Loadbalancern gepollt: Dürfte
# jede Probe ALLE graph.json vollständig parsen, fröre eine einfache curl-Schleife
# die einzige Event-Loop ein (SEC-06). Deshalb prüft ready_pruefung() die Graphen
# nur stichprobenartig (max_items), OHNE Voll-Parsing — Datei-Existenz, Größe und
# ein kurzer Kopf-Sniff genügen für Readiness — und cached das Ergebnis kurz
# (cache_seconds). Die vollständige Prüfung aller Graphen bleibt der Deep-Sicht
# (_check_graphen).
_GRAPH_CACHE: dict = {"schluessel": None, "zeit": 0.0, "ergebnis": None}


def _graph_fingerabdruck(max_items: int) -> tuple:
    """Billiger Änderungsdetektor über die Stichprobe — nur stat(), kein Parsen."""
    namen = sorted(_projects())
    spuren = []
    for name in namen[: max(max_items, 0)]:
        pfad = KNOWLEDGE_ROOT / name / "graphify-out" / "graph.json"
        try:
            st = pfad.stat()
            spuren.append((name, st.st_mtime_ns, st.st_size))
        except OSError:
            spuren.append((name, None))
    return (len(namen), tuple(spuren))


def _check_graphen_stichprobe(max_items: int) -> tuple[bool, str]:
    """Readiness-taugliche Graphen-Probe: gedeckelt UND ohne Voll-Parsing (P0-7).

    Pro Graph (höchstens max_items) nur stat() + die ersten Bytes: Existenz,
    Größe > 0 und ein JSON-Objekt-Beginn („{") genügen als Readiness-Signal —
    json.loads über megabytegroße Graphen wäre der DoS-Hebel, den diese Probe
    abschaffen soll (SEC-06). Der Sniff fängt trotzdem offensichtlich kaputte
    Dateien ab; der gründliche Voll-Parse bleibt der Deep-Sicht (_check_graphen).
    """
    defekt, geprueft, vorhanden = [], 0, 0
    for name in sorted(_projects()):
        pfad = KNOWLEDGE_ROOT / name / "graphify-out" / "graph.json"
        try:
            st = pfad.stat()
        except OSError:
            continue  # kein Graph vorhanden = kein Befund (Projektliste zählt separat)
        vorhanden += 1
        if geprueft >= max(max_items, 0):
            continue  # Stichprobe voll — der Rest wird nur noch gezählt, nicht gelesen
        geprueft += 1
        try:
            if st.st_size == 0:
                defekt.append(f"{name} (Datei leer)")
                continue
            with pfad.open("rb") as fh:
                kopf = fh.read(512).decode("utf-8", errors="replace").lstrip("\ufeff \t\r\n")
            if not kopf.startswith("{"):
                defekt.append(f"{name} (kein JSON-Objekt)")
        except OSError as e:
            defekt.append(f"{name} ({type(e).__name__})")
    if defekt:
        return False, "nicht lesbar: " + ", ".join(defekt)
    detail = f"{geprueft} Graphen vorhanden und plausibel"
    uebersprungen = vorhanden - geprueft
    if uebersprungen > 0:
        detail += f" (+{uebersprungen} nur gezählt — Stichprobe, voller Check in /healthz/deep)"
    return True, detail


def _graphen_gecached(max_items: int, cache_seconds: int) -> tuple[bool, str]:
    """Stichproben-Ergebnis mit TTL-Cache plus Fingerabdruck-Invalidierung.

    Der Cache darf Änderungen nicht verstecken: Weicht der stat-Fingerabdruck
    (Projektliste + mtime/Größe der Stichprobe) ab, wird sofort neu geprüft — die
    TTL deckt nur den änderungs-blinden Rest ab (z. B. Inhalt bei gleichem mtime).
    """
    jetzt = time.monotonic()
    schluessel = _graph_fingerabdruck(max_items)
    cache = _GRAPH_CACHE
    if (
        cache["ergebnis"] is not None
        and cache["schluessel"] == schluessel
        and jetzt - cache["zeit"] < cache_seconds
    ):
        return cache["ergebnis"]
    ergebnis = _check_graphen_stichprobe(max_items)
    cache.update(schluessel=schluessel, zeit=jetzt, ergebnis=ergebnis)
    return ergebnis


def _check_mcp_tools(tool_names: set[str] | None) -> tuple[bool, str]:
    if tool_names is None:
        return False, "MCP-Toolliste nicht ermittelbar"
    fehlend = EXPECTED_TOOLS - tool_names
    if fehlend:
        return False, "fehlende Werkzeuge: " + ", ".join(sorted(fehlend))
    return True, f"{len(EXPECTED_TOOLS)} Werkzeuge vollständig"


def _check_assets() -> tuple[bool, str]:
    fehlend = [n for n in _ASSETS if not (WEB_DIR / n).is_file() or (WEB_DIR / n).stat().st_size == 0]
    if fehlend:
        return False, "fehlt oder leer: " + ", ".join(fehlend)
    return True, f"{len(_ASSETS)} Kern-Assets vorhanden"


def _check_migrationen() -> tuple[bool, str]:
    st = vault.status()
    version = st.get("version", 0)
    if version not in KNOWN_VAULT_VERSIONS:
        return False, f"unbekannte Vault-Dokumentversion {version} — nicht ohne Migration starten"
    return True, f"Vault-Dokumentversion {version} bekannt"


def _check_generationen() -> tuple[bool, str]:
    """Deep-only: Graph, Report, Viewer und Index müssen je Projekt EINE Generation bilden."""
    import buildmeta

    mismatch, legacy, ok = [], 0, 0
    for name in _projects():
        pfad = KNOWLEDGE_ROOT / name
        if not (pfad / "graphify-out" / "graph.json").exists():
            continue
        v = buildmeta.verify(pfad)
        if v["status"] == "mismatch":
            mismatch.append(f"{name}: {v['detail']}")
        elif v["status"] == "legacy":
            legacy += 1
        else:
            ok += 1
    if mismatch:
        return False, " | ".join(mismatch)
    return True, f"{ok} konsistent, {legacy} legacy (vor Vertragseinführung)"


async def checks(mcp=None, deep: bool = False) -> list[dict]:
    """Alle Readiness-Checks mit Einzelbefund. Ein Check, der selbst wirft, ist ein Befund."""
    tool_names: set[str] | None = None
    if mcp is not None:
        try:
            tools = await mcp.list_tools()
            tool_names = {t.name for t in tools}
        except Exception:  # noqa: BLE001 - jeder Fehler hier IST das Ergebnis des Checks
            tool_names = None

    pruefungen: list[tuple] = [
        ("config", _check_config),
        ("datenpfade", _check_datenpfade),
        ("vault", _check_vault),
        ("projektliste", _check_projektliste),
        ("graphen", _check_graphen),
        ("mcp_tools", lambda: _check_mcp_tools(tool_names)),
        ("assets", _check_assets),
        ("migrationen", _check_migrationen),
    ]
    if deep:
        # Hash-Verifikation aller Generationen ist zu teuer für jede Readiness-Probe —
        # sie gehört in die Deep-Sicht (und in die Kandidaten-Gates vor einem Switch).
        pruefungen.append(("generationen", _check_generationen))
    ergebnisse = []
    for name, fn in pruefungen:
        try:
            ok, detail = fn()
        except Exception as e:  # noqa: BLE001 - Absturz eines Checks = unready, kein 500
            ok, detail = False, f"Check selbst fehlgeschlagen: {type(e).__name__}"
        ergebnisse.append({"check": name, "ok": ok, "detail": detail})
    return ergebnisse


async def ready(mcp=None, deep: bool = False) -> tuple[bool, list[dict]]:
    ergebnisse = await checks(mcp, deep=deep)
    return all(c["ok"] for c in ergebnisse), ergebnisse


async def ready_pruefung(max_items: int = 50, cache_seconds: int = 10) -> tuple[bool, list[dict]]:
    """Gedrosselte Readiness für die offene Probe /healthz/ready (P0-7).

    Rückgabe exakt wie ready(): (ok, checks). Damit die Probe billig bleibt, prüft
    der Graphen-Check höchstens max_items graph.json (Stichprobe) und zwar OHNE
    Voll-Parsing — nur stat() + kurzer Kopf-Sniff (_check_graphen_stichprobe) — und
    wird für cache_seconds Sekunden gecacht (Invalidierung zusätzlich per
    stat-Fingerabdruck). Ohne MCP-Handle kann die Toolliste hier nicht verifiziert
    werden — sie bleibt Teil der Deep-Sicht. Das bisherige Verhalten (ready) bleibt
    als Fallback bestehen.
    """
    pruefungen: list[tuple] = [
        ("config", _check_config),
        ("datenpfade", _check_datenpfade),
        ("vault", _check_vault),
        ("projektliste", _check_projektliste),
        ("graphen", lambda: _graphen_gecached(max_items, cache_seconds)),
        ("mcp_tools", lambda: (True, "ohne MCP-Handle nicht prüfbar — vollständig in /healthz/deep")),
        ("assets", _check_assets),
        ("migrationen", _check_migrationen),
    ]
    ergebnisse = []
    for name, fn in pruefungen:
        try:
            ok, detail = fn()
        except Exception as e:  # noqa: BLE001 - Absturz eines Checks = unready, kein 500
            ok, detail = False, f"Check selbst fehlgeschlagen: {type(e).__name__}"
        ergebnisse.append({"check": name, "ok": ok, "detail": detail})
    return all(c["ok"] for c in ergebnisse), ergebnisse
