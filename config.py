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
import fcntl
import os
import re
import sys
import tempfile
import time
from collections.abc import Callable
from contextlib import contextmanager
from pathlib import Path

import yaml

CONFIG_PATH = Path(
    os.environ.get("KNOWLEDGE_CONFIG", str(Path.home() / ".config" / "knowledge-mcp" / "config.yaml"))
)


class ConfigError(RuntimeError):
    """config.yaml ist beschädigt (kein gültiges YAML oder kein Objekt).

    Bewusst ein klarer, eigener Fehler statt eines rohen YAMLError/AttributeError:
    eine kaputte Config soll eine eindeutige Meldung ergeben (und den Deploy-Health-Gate
    auslösen), nicht einen 500-Traceback — und NICHT still auf die Defaults zurückfallen,
    was Projekte/Backends unbemerkt verschlucken würde."""


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
            },
            # Keyloses Backend: mappt/labelt über die lokale Claude-Code-CLI (`claude -p`)
            # und das Abo statt über einen bezahlten API-Key. Kein secret/env nötig.
            "claude-cli": {
                "label": "Claude Code (CLI)",
                "api": "claude-cli",
                # local=True → die UI verlangt KEINEN Key (kein Onboarding, Health „ok"):
                # dieses Backend authentifiziert über die Claude-Code-Anmeldung, nicht per Vault-Key.
                "local": True,
                "key_hint": "Nutzt deine Claude-Code-Anmeldung — kein API-Key und kein Guthaben nötig.",
                "models": [{"id": "claude-code-plan", "hint": "über Claude-Code-Abo"}],
            },
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


# Kernsektionen, die YAML-Objekte sein MÜSSEN (Typ-Validierung, CE-10/OPS-07):
# „mapping: null" oder „server: text" kippte sonst erst später als roher TypeError/
# AttributeError (z. B. schon beim Modul-Import von server.py) — hier gibt es dafür
# eine klare ConfigError-Meldung, wie bei kaputtem YAML.
_KERN_OBJEKTE = ("server", "branding", "paths", "mapping")


def _validiere_typen(data: dict) -> None:
    """Typ-Guards für config.yaml — klare ConfigError statt späterer TypeErrors."""
    for schluessel in _KERN_OBJEKTE:
        if schluessel in data and not isinstance(data[schluessel], dict):
            raise ConfigError(
                f"config.yaml: Abschnitt „{schluessel}“ muss ein YAML-Objekt sein, "
                f"gefunden: {type(data[schluessel]).__name__}."
            )
    mapping = data.get("mapping")
    if isinstance(mapping, dict):
        projekte = mapping.get("projects")
        if projekte is not None:
            if not isinstance(projekte, list):
                raise ConfigError(
                    "config.yaml: mapping.projects muss eine Liste sein, "
                    f"gefunden: {type(projekte).__name__}."
                )
            for eintrag in projekte:
                if not isinstance(eintrag, (str, dict)):
                    raise ConfigError(
                        "config.yaml: mapping.projects-Einträge müssen Pfad-Texte oder "
                        f"Objekte mit „path“ sein, gefunden: {type(eintrag).__name__}."
                    )


def load() -> dict:
    data = {}
    if CONFIG_PATH.exists():
        try:
            data = yaml.safe_load(CONFIG_PATH.read_text()) or {}
        except yaml.YAMLError as e:
            raise ConfigError(f"config.yaml ist kein gültiges YAML: {str(e).splitlines()[0]}") from e
        if not isinstance(data, dict):
            raise ConfigError("config.yaml muss ein YAML-Objekt sein (kein Liste/Wert an oberster Stelle).")
        _validiere_typen(data)
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


@contextmanager
def _config_lock(target: Path, timeout: float = 10.0):
    """Exklusive Sperre auf eine Lock-Datei NEBEN der config.yaml.

    Warum überhaupt: save_projects, save_mapping und save_backup schreiben je die
    GANZE Datei über ein Lesen-Ändern-Schreiben. MCP-Tools laufen im Worker-Thread,
    HTTP-Handler in der Event-Loop — echte Parallelität. Ohne diese Sperre las der
    spätere Schreiber den Stand VOR der Änderung des früheren und schrieb ihn wieder
    weg: eine der beiden Änderungen ging unbemerkt verloren (R19-1). flock gehört dem
    Datei-Deskriptor und stirbt mit dem Prozess; die Lock-Datei liegt neben der Config,
    also isoliert pro Instanz (auch im Test).
    """
    target.parent.mkdir(parents=True, exist_ok=True)
    lock_path = target.with_name(target.name + ".lock")
    fd = os.open(lock_path, os.O_CREAT | os.O_RDWR, 0o600)
    frist = time.monotonic() + timeout
    try:
        while True:
            try:
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except BlockingIOError:
                if time.monotonic() >= frist:
                    raise TimeoutError(f"config.yaml ist gesperrt — {lock_path.name}") from None
                time.sleep(0.02)
        yield
    finally:
        try:
            fcntl.flock(fd, fcntl.LOCK_UN)
        finally:
            os.close(fd)


def _update_yaml(mutate: Callable[[dict], None], cfg_path: Path | None = None) -> None:
    """Read-modify-write auf config.yaml unter Sperre + atomarem Schreibvorgang.

    Jeder Schreiber liest unter der Sperre FRISCH ein und schreibt atomar zurück —
    damit können sich parallele Schreiber verschiedener Abschnitte nicht mehr
    gegenseitig überschreiben (Lost-Update-Schutz, R19-1) und es entsteht nie eine
    halbe Datei (temp+rename, R19-2).
    """
    target = cfg_path or CONFIG_PATH
    with _config_lock(target):
        data = {}
        if target.exists():
            # Dieselben Guards wie in load(): kaputtes YAML oder falsche Top-Level-
            # Typen müssen auch hier eine klare ConfigError ergeben — sonst crasht
            # mutate() mit rohem YAMLError/AttributeError/TypeError (CE-10).
            try:
                data = yaml.safe_load(target.read_text()) or {}
            except yaml.YAMLError as e:
                raise ConfigError(f"config.yaml ist kein gültiges YAML: {str(e).splitlines()[0]}") from e
            if not isinstance(data, dict):
                raise ConfigError(
                    "config.yaml muss ein YAML-Objekt sein (kein Liste/Wert an oberster Stelle)."
                )
            _validiere_typen(data)
        mutate(data)
        _schreibe_atomar(target, _HEADER + yaml.safe_dump(data, allow_unicode=True, sort_keys=False))


def save_projects(project_entries: list[dict]) -> None:
    """Persistiert mapping.projects in config.yaml (Rest der Datei bleibt erhalten)."""

    def mutate(data: dict) -> None:
        data.setdefault("mapping", {})["projects"] = project_entries

    _update_yaml(mutate)


def save_backup(targets: list[dict], cfg_path: Path | None = None) -> None:
    """Backup-Ziele persistieren (Rest der config.yaml bleibt unangetastet)."""

    def mutate(data: dict) -> None:
        data.setdefault("backup", {})["enabled"] = True
        data["backup"]["targets"] = targets

    _update_yaml(mutate, cfg_path)


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


def archived_graphs(cfg: dict | None = None) -> list[dict]:
    """Archivierte Hub-Graphen (Post-Run-40, Bug 2): Bestände mit dokumentierter Herkunft.

    Ein archivierter Graph gehört zur Projektregistrierung (Quelle der Wahrheit), wird
    aber nicht nächtlich gemappt: typisch Benchmark-Beweismaterial oder stillgelegte
    Projekte, deren Graph als Beleg erhalten bleibt. Format je Eintrag:
    {"name": <hub-ordner>, "origin": <woher/warum>, "archived_at": <ISO>}.
    """
    cfg = cfg or load()
    out = []
    for e in cfg.get("archived_graphs", []) or []:
        if isinstance(e, dict) and e.get("name"):
            out.append(
                {
                    "name": str(e["name"]),
                    "origin": str(e.get("origin", "")),
                    "archived_at": str(e.get("archived_at", "")),
                }
            )
    return out


def save_archived_graphs(entries: list[dict]) -> None:
    """Persistiert archived_graphs in config.yaml (Rest bleibt erhalten)."""

    def mutate(data: dict) -> None:
        data["archived_graphs"] = entries

    _update_yaml(mutate)


def backends(cfg: dict | None = None) -> dict:
    return (cfg or load())["mapping"].get("backends", {})


_PRICE_RE = re.compile(r"\$([0-9.]+)\s*/\s*\$([0-9.]+)")


def model_price(model: str, cfg: dict | None = None) -> tuple[float, float]:
    """(Input, Output)-Preis pro 1 Mio. Tokens in USD für ein Modell.

    Einzige Quelle ist der `hint` in config.yaml (z. B. „empfohlen · $0.40/$1.60"),
    damit der Preis dort bleibt, wo er ohnehin gepflegt wird — keine zweite Tabelle,
    die auseinanderläuft. Unbekanntes oder kostenloses Modell (Ollama) → (0.0, 0.0).
    """
    cfg = cfg or load()
    for b in backends(cfg).values():
        for m in b.get("models", []):
            if m.get("id") == model:
                mt = _PRICE_RE.search(str(m.get("hint", "")))
                return (float(mt.group(1)), float(mt.group(2))) if mt else (0.0, 0.0)
    return 0.0, 0.0


def active_backend(cfg: dict | None = None) -> tuple[str, dict]:
    """(Name, Definition) des aktiven Mapping-Backends — fällt auf openai zurück."""
    cfg = cfg or load()
    name = cfg["mapping"].get("backend", "openai")
    defs = backends(cfg)
    if name not in defs:
        name = next(iter(defs), "openai")
    return name, defs.get(name, {})


def save_mapping(backend: str, model: str, cfg_path: Path | None = None) -> None:
    def mutate(data: dict) -> None:
        data.setdefault("mapping", {})["backend"] = backend
        data["mapping"]["model"] = model

    _update_yaml(mutate, cfg_path)


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
