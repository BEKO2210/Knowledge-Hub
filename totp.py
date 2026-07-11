"""Zwei-Faktor-Authentifizierung per TOTP (RFC 6238) + Wiederherstellungscodes.

Der 2FA-Zustand liegt als eigenes Secret im Vault (`__2fa__`), damit er genauso
verschlüsselt ist wie alles andere und mitgesichert wird. Aufbau:

    {"enabled": bool, "secret": "<base32>", "recovery": ["<sha256>", ...]}

Wiederherstellungscodes fangen den Fall „Handy weg“ ab — ohne sie wäre ein
verlorener Authenticator gleichbedeutend mit Aussperrung (die Lektion aus dem
Passwort-Zwischenfall). Sie werden nur als Hash gespeichert und sind einmal gültig.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import secrets
import struct
import time
from urllib.parse import quote

import vault

STORE_NAME = "__2fa__"
DIGITS = 6
PERIOD = 30
SKEW = 1  # ±1 Zeitfenster Toleranz (Uhr-Ungenauigkeit)


# ---------------------------------------------------------------------------
# TOTP-Kern
# ---------------------------------------------------------------------------
def _b32secret() -> str:
    return base64.b32encode(secrets.token_bytes(20)).decode().rstrip("=")


def _code_at(secret_b32: str, counter: int) -> str:
    key = base64.b32decode(secret_b32 + "=" * (-len(secret_b32) % 8))
    mac = hmac.new(key, struct.pack(">Q", counter), hashlib.sha1).digest()
    offset = mac[-1] & 0x0F
    val = struct.unpack(">I", mac[offset:offset + 4])[0] & 0x7FFFFFFF
    return str(val % (10**DIGITS)).zfill(DIGITS)


def verify_code(secret_b32: str, code: str) -> bool:
    """Prüft einen 6-stelligen Code gegen das aktuelle Zeitfenster (±1)."""
    code = (code or "").strip().replace(" ", "")
    if not code.isdigit() or len(code) != DIGITS:
        return False
    counter = int(time.time()) // PERIOD
    for delta in range(-SKEW, SKEW + 1):
        if hmac.compare_digest(_code_at(secret_b32, counter + delta), code):
            return True
    return False


def provisioning_uri(secret_b32: str, account: str, issuer: str) -> str:
    label = quote(f"{issuer}:{account}")
    return (f"otpauth://totp/{label}?secret={secret_b32}"
            f"&issuer={quote(issuer)}&digits={DIGITS}&period={PERIOD}")


def qr_svg(uri: str) -> str:
    """QR-Code als eingebettetes SVG (kein externer Host — CSP-konform)."""
    import io

    import segno

    qr = segno.make(uri, error="m")
    buf = io.BytesIO()
    qr.save(buf, kind="svg", scale=5, border=2, dark="#0f172a", light="#ffffff")
    svg = buf.getvalue().decode()
    # Nur das <svg>…</svg> zurück (ohne XML-Prolog), damit es sich einbetten lässt.
    return svg[svg.index("<svg"):]


# ---------------------------------------------------------------------------
# Zustand im Vault
# ---------------------------------------------------------------------------
def _load() -> dict:
    raw = vault.secret_get(STORE_NAME, client="system")
    if not raw:
        return {"enabled": False}
    try:
        return json.loads(raw)
    except Exception:  # noqa: BLE001
        return {"enabled": False}


def _save(state: dict) -> None:
    vault.secret_set(STORE_NAME, json.dumps(state), client="system")


def is_enabled() -> bool:
    return bool(_load().get("enabled"))


def status() -> dict:
    st = _load()
    return {
        "enabled": bool(st.get("enabled")),
        "recovery_left": len(st.get("recovery", [])),
    }


# ---------------------------------------------------------------------------
# Einrichtung
# ---------------------------------------------------------------------------
def begin_setup(account: str, issuer: str) -> dict:
    """Neues Geheimnis erzeugen (noch NICHT aktiv) und QR liefern.

    Das Geheimnis wird schon im Vault abgelegt (enabled=False), damit die
    Aktivierung ohne Zustands-Weitergabe über den Client auskommt.
    """
    secret = _b32secret()
    _save({"enabled": False, "secret": secret, "recovery": []})
    uri = provisioning_uri(secret, account, issuer)
    return {"secret": secret, "uri": uri, "qr": qr_svg(uri)}


def _gen_recovery(n: int = 8) -> list[str]:
    """Menschlich lesbare Codes (z. B. 4f2a-9c1e)."""
    return [f"{secrets.token_hex(2)}-{secrets.token_hex(2)}" for _ in range(n)]


def enable(code: str) -> list[str] | None:
    """Mit einem gültigen Code aktivieren. Gibt die Wiederherstellungscodes
    zurück (einmalig sichtbar) oder None bei falschem Code."""
    st = _load()
    secret = st.get("secret")
    if not secret or not verify_code(secret, code):
        return None
    recovery = _gen_recovery()
    st["enabled"] = True
    st["recovery"] = [hashlib.sha256(c.encode()).hexdigest() for c in recovery]
    _save(st)
    vault.audit("2FA-ENABLE", "aktiviert", client="web-ui")
    return recovery


def disable() -> None:
    _save({"enabled": False})
    vault.audit("2FA-DISABLE", "deaktiviert", client="web-ui")


# ---------------------------------------------------------------------------
# Prüfung beim Login
# ---------------------------------------------------------------------------
def check(code: str) -> bool:
    """Code oder Wiederherstellungscode beim Login prüfen.

    Ein verwendeter Wiederherstellungscode wird sofort verbraucht.
    """
    st = _load()
    if not st.get("enabled"):
        return True
    secret = st.get("secret", "")
    if secret and verify_code(secret, code):
        return True
    # Wiederherstellungscode?
    h = hashlib.sha256((code or "").strip().encode()).hexdigest()
    if h in st.get("recovery", []):
        st["recovery"].remove(h)
        _save(st)
        vault.audit("2FA-RECOVERY", f"Code verbraucht ({len(st['recovery'])} übrig)", client="web-ui")
        return True
    return False
