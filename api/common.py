"""Gemeinsame Bausteine aller UI-Endpunkte: Konfiguration, Pfade, Anmeldung, Bearer-Token."""

from __future__ import annotations

import hmac
import json
import os
from pathlib import Path

from starlette.requests import Request

import config
import vault


class BadJSON(Exception):
    """Der Body war kein JSON-Objekt: leer, unlesbar, oder ein falscher Typ
    (Liste, Zahl, String). Wird global als 400 beantwortet — so kann kein
    Endpunkt mehr an ``body.get(...)`` auf einem Nicht-Objekt abstürzen (500)."""


async def json_object(request: Request) -> dict:
    """Body als JSON-Objekt lesen oder mit :class:`BadJSON` abbrechen.

    Alle schreibenden Endpunkte erwarten ein Objekt und greifen mit ``.get()``
    darauf zu. Ein gültiges, aber typfremdes JSON (``[1,2]``, ``"text"``, ``42``)
    ließ diesen Zugriff bisher als unerwarteten Serverfehler enden. Diese eine
    Stelle macht daraus einen sauberen Aufruferfehler.
    """
    try:
        data = await request.json()
    except (json.JSONDecodeError, ValueError):
        raise BadJSON from None
    if not isinstance(data, dict):
        raise BadJSON
    return data


CFG = config.load()
KNOWLEDGE_ROOT = config.path(os.environ.get("KNOWLEDGE_ROOT", CFG["paths"]["knowledge_root"]))
GRAPHIFY_BIN = os.environ.get("GRAPHIFY_BIN", str(config.path(CFG["paths"]["graphify_bin"])))
AUDIT_PATH = vault.AUDIT_PATH
DATA_DIR = Path(os.environ.get("KMCP_DATA_DIR", str(Path(__file__).resolve().parent.parent)))


def _projects() -> list[str]:
    return sorted(
        d.name
        for d in KNOWLEDGE_ROOT.iterdir()
        if d.is_dir() and (d / "graphify-out" / "graph.json").exists()
    )


def _check_password(password: str) -> bool:
    """Anmeldung prüfen und dabei den Vault entsperren.

    Fällt auf das alte Klartext-Passwort zurück, solange der Vault noch keine
    Passwort-Verpackung hat (frisch migrierte Systeme ohne bekanntes Passwort).
    """
    if not password:
        return False
    st = vault.status()
    if st.get("has_password"):
        return vault.unlock(password)  # entsperrt zugleich den Vault
    legacy = os.environ.get("OAUTH_PASSWORD", "")
    return bool(legacy) and hmac.compare_digest(password, legacy)


def _client_ip(request: Request) -> str:
    return request.headers.get("cf-connecting-ip") or (request.client.host if request.client else "?")


def _bearer(request: Request) -> str:
    auth = request.headers.get("authorization", "")
    return auth.removeprefix("Bearer ").strip() if auth.startswith("Bearer ") else ""


def _check(name: str, status: str, detail: str, fix: str = "") -> dict:
    return {"name": name, "status": status, "detail": detail, "fix": fix}


def _dir_size(p: Path) -> int:
    try:
        return sum(f.stat().st_size for f in p.rglob("*") if f.is_file())
    except OSError:
        return 0


def _human(n: float) -> str:
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024:
            return f"{n:.0f} {unit}" if unit == "B" else f"{n:.1f} {unit}"
        n /= 1024
    return f"{n:.1f} TB"
