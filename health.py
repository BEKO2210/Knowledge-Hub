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
