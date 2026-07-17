"""Gemeinsame Bausteine aller UI-Endpunkte: Konfiguration, Pfade, Anmeldung, Bearer-Token."""

from __future__ import annotations

import hmac
import ipaddress
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
    # Auf einer frischen Instanz existiert die Root noch nicht — anlegen statt
    # mit FileNotFoundError (500) zu enden: ein Hub ohne Projekte liefert dann
    # sauber die leere Liste (BE-04).
    try:
        KNOWLEDGE_ROOT.mkdir(parents=True, exist_ok=True)
        return sorted(
            d.name
            for d in KNOWLEDGE_ROOT.iterdir()
            if d.is_dir() and (d / "graphify-out" / "graph.json").exists()
        )
    except OSError:  # z. B. keine Schreibrechte auf die Root — dann lieber leer als 500
        return []


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
    if not legacy:
        return False
    try:
        # Byteweise vergleichen: compare_digest wirft auf str mit Nicht-ASCII
        # (Umlaute im Passwort) einen TypeError → 500 statt 401, und der
        # Fehlversuch würde nie ans Rate-Limit gemeldet (BE-04).
        return hmac.compare_digest(password.encode("utf-8"), legacy.encode("utf-8"))
    except UnicodeError:  # verwaiste Surrogate aus manipuliertem JSON-Body → sauberes 401
        return False


def _trusted_proxies() -> list[ipaddress.IPv4Network | ipaddress.IPv6Network]:
    """Vertraute Proxies aus Env TRUSTED_PROXIES (kommagetrennt, CIDR oder Einzel-IP).

    Leer (Default) = NIEMAND wird vertraut — fail-closed: Ungültige Einträge
    werden übersprungen statt zu crashen.
    """
    netze = []
    for eintrag in os.environ.get("TRUSTED_PROXIES", "").split(","):
        eintrag = eintrag.strip()
        if not eintrag:
            continue
        try:
            netze.append(ipaddress.ip_network(eintrag, strict=False))
        except ValueError:
            continue
    return netze


def _client_ip(request: Request) -> str:
    """Client-IP bestimmen — cf-connecting-ip NUR von vertrauten Proxies (P0-6).

    Der Header ist vom Aufrufer frei setzbar: Wer ihn ungeprüft übernimmt, macht
    die Rate-Limits (Login, TOTP, Register, Schreiben) per Header-Rotation
    wirkungslos und erlaubt gefälschte IPs im Audit-Log. Er gilt deshalb nur,
    wenn der DIREKTE Peer in TRUSTED_PROXIES steht (Default: leer = nie). Betrieb
    hinter Cloudflare: die echten CF-Ranges dort eintragen.
    """
    peer = request.client.host if request.client else ""
    header = request.headers.get("cf-connecting-ip", "").strip()
    if header and peer:
        try:
            peer_ip = ipaddress.ip_address(peer)
        except ValueError:
            peer_ip = None
        if peer_ip is not None and any(peer_ip in netz for netz in _trusted_proxies()):
            return header
    return peer or "?"


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
