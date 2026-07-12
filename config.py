"""Zentrale Konfiguration des Knowledge Hub.

Aufteilung nach 12-Factor-Hybrid:
  * Secrets (VAULT_KEY, MCP_TOKEN, OAUTH_PASSWORD) bleiben in der env-Datei
    (~/.config/knowledge-mcp/env, 0600) — niemals in config.yaml.
  * Struktur-Konfiguration (Pfade, Ports, Domain, Projektliste, Modelle) liegt in
    ~/.config/knowledge-mcp/config.yaml und kann gefahrlos geteilt werden.

Pfad überschreibbar via KNOWLEDGE_CONFIG. Fehlt die Datei, gelten die DEFAULTS —
das System startet also auch ohne config.yaml (wichtig für den Erststart-Wizard).

CLI-Helfer für Shell-Skripte:
  python config.py projects   -> aktivierte Projektpfade, einer pro Zeile
  python config.py get a.b.c  -> einzelner Wert
"""

from __future__ import annotations

import copy
import os
import sys
import tempfile
from pathlib import Path

import yaml

CONFIG_PATH = Path(
    os.environ.get("KNOWLEDGE_CONFIG", str(Path.home() / ".config" / "knowledge-mcp" / "config.yaml"))
)

DEFAULTS: dict = {
    "server": {
        "host": "127.0.0.1",
        "port": 8300,
        # Öffentliche Basis-URL (Cloudflare-Tunnel o. Ä.) — auch OAuth-Issuer
        "public_url": "http://127.0.0.1:8300",
    },
    "branding": {
        "name": "Knowledge Hub",
    },
    "paths": {
        "knowledge_root": "~/graphify-knowledge",
        "graphify_bin": "~/.local/bin/graphify",
        "graphify_sync": "~/.local/bin/graphify-sync",
    },
    "mapping": {
        "backend": "openai",
        "model": "gpt-4.1-mini",
        "api_timeout": 300,
        "backends": {
            "openai": {
                "label": "OpenAI",
                "secret": "open_ai",
                "env": "OPENAI_API_KEY",
                "key_url": "https://platform.openai.com/api-keys",
                "models": [{"id": "gpt-4.1-mini", "hint": "recommended"}],
            }
        },
        "projects": [],  # Liste von {path: str, enabled: bool}
    },
}


def _deep_merge(base: dict, override: dict) -> dict:
    out = copy.deepcopy(base)
    for k, v in (override or {}).items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = _deep_merge(out[k], v)
        else:
            out[k] = v
    return out


def load() -> dict:
    data = {}
    if CONFIG_PATH.exists():
        data = yaml.safe_load(CONFIG_PATH.read_text()) or {}
    return _deep_merge(DEFAULTS, data)


def path(value: str) -> Path:
    return Path(value).expanduser()


def projects(cfg: dict | None = None) -> list[Path]:
    """Aktivierte Projektpfade für das Nacht-Mapping."""
    cfg = cfg or load()
    out = []
    for p in cfg["mapping"]["projects"]:
        if isinstance(p, str):
            out.append(path(p))
        elif p.get("enabled", True):
            out.append(path(p["path"]))
    return out


_HEADER = (
    "# Knowledge Hub — zentrale Konfiguration\n"
    "# Secrets gehören NICHT hierher, sondern in ./env (VAULT_KEY, MCP_TOKEN, OAUTH_PASSWORD).\n\n"
)


def _schreibe_atomar(ziel: Path, text: str) -> None:
    """Erst vollständig danebenschreiben, dann umbenennen.

    write_text() schreibt an Ort und Stelle: Bricht der Vorgang mittendrin ab (Absturz,
    voller Datenträger) oder liest jemand gleichzeitig, steht eine halbe YAML-Datei auf
    der Platte — und der Hub startet danach ohne Konfiguration. os.replace() ist atomar:
    entweder die alte Datei oder die neue, nie etwas dazwischen.
    """
    ziel.parent.mkdir(parents=True, exist_ok=True)
    fd, pfad = tempfile.mkstemp(dir=ziel.parent, prefix=f".{ziel.name}-", suffix=".tmp")
    tmp = Path(pfad)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(text)
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp, ziel)
    except BaseException:
        tmp.unlink(missing_ok=True)
        raise


def save_projects(project_entries: list[dict]) -> None:
    """Persistiert mapping.projects in config.yaml (Rest der Datei bleibt erhalten)."""
    data = {}
    if CONFIG_PATH.exists():
        data = yaml.safe_load(CONFIG_PATH.read_text()) or {}
    data.setdefault("mapping", {})["projects"] = project_entries
    _schreibe_atomar(CONFIG_PATH, _HEADER + yaml.safe_dump(data, allow_unicode=True, sort_keys=False))


def save_backup(targets: list[dict], cfg_path: Path | None = None) -> None:
    """Backup-Ziele persistieren (Rest der config.yaml bleibt unangetastet)."""
    path = cfg_path or CONFIG_PATH
    data = (yaml.safe_load(path.read_text()) if path.exists() else {}) or {}
    data.setdefault("backup", {})["enabled"] = True
    data["backup"]["targets"] = targets
    path.write_text(_HEADER + yaml.safe_dump(data, allow_unicode=True, sort_keys=False))


def project_entries(cfg: dict | None = None) -> list[dict]:
    """mapping.projects normalisiert als [{path, enabled}, ...]."""
    cfg = cfg or load()
    out = []
    for p in cfg["mapping"]["projects"]:
        if isinstance(p, str):
            out.append({"path": p, "enabled": True})
        else:
            out.append({"path": p["path"], "enabled": bool(p.get("enabled", True))})
    return out


def backends(cfg: dict | None = None) -> dict:
    return (cfg or load())["mapping"].get("backends", {})


def active_backend(cfg: dict | None = None) -> tuple[str, dict]:
    """(Name, Definition) des aktiven Mapping-Backends — fällt auf openai zurück."""
    cfg = cfg or load()
    name = cfg["mapping"].get("backend", "openai")
    defs = backends(cfg)
    if name not in defs:
        name = next(iter(defs), "openai")
    return name, defs.get(name, {})


def save_mapping(backend: str, model: str, cfg_path: Path | None = None) -> None:
    path = cfg_path or CONFIG_PATH
    data = yaml.safe_load(path.read_text()) if path.exists() else {}
    data = data or {}
    data.setdefault("mapping", {})["backend"] = backend
    data["mapping"]["model"] = model
    path.write_text(_HEADER + yaml.safe_dump(data, allow_unicode=True, sort_keys=False))


def get(dotted: str, cfg: dict | None = None):
    cur: object = cfg or load()
    for part in dotted.split("."):
        cur = cur[part]  # type: ignore[index]
    return cur


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else ""
    if cmd == "projects":
        print("\n".join(str(p) for p in projects()))
    elif cmd == "mapping":
        # Shell-auswertbare Zeilen für nightly-map.sh
        cfg = load()
        name, b = active_backend(cfg)
        print(f"BACKEND={name}")
        print(f"MODEL={cfg['mapping'].get('model', '')}")
        print(f"SECRET={b.get('secret') or ''}")
        print(f"ENVVAR={b.get('env') or ''}")
        print(f"API_TIMEOUT={cfg['mapping'].get('api_timeout', 300)}")
        print(f"LOCAL={'1' if b.get('local') else ''}")
    elif cmd == "get" and len(sys.argv) > 2:
        print(get(sys.argv[2]))
    else:
        print("usage: config.py projects | mapping | get <a.b.c>", file=sys.stderr)
        sys.exit(1)
