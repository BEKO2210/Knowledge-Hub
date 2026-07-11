"""Secrets-Vault und Audit-Log."""

from __future__ import annotations

import re

from starlette.requests import Request
from starlette.responses import JSONResponse

import vault
from api.common import AUDIT_PATH
from api.i18n import T

HIDDEN_SECRETS = {"__2fa__"}


async def secrets_list(request: Request) -> JSONResponse:
    return JSONResponse([s for s in vault.secret_list(client="web-ui") if s not in HIDDEN_SECRETS])


SECRET_NAME_RE = re.compile(r"^[\w.\- ]{1,64}$")


async def secrets_set(request: Request) -> JSONResponse:
    body = await request.json()
    name, value = str(body.get("name", "")).strip(), str(body.get("value", ""))
    if not name or not value:
        return JSONResponse({"error": T("Name und Wert sind Pflicht")}, status_code=400)
    # Erlaubt: Buchstaben, Ziffern, _ . - und Leerzeichen. Alles andere (Steuerzeichen,
    # Zeilenumbrüche, Pfadtrenner) wird abgelehnt.
    if not SECRET_NAME_RE.match(name):
        return JSONResponse(
            {"error": T("Ungültiger Name — erlaubt sind Buchstaben, Ziffern, Punkt, Bindestrich, "
                        "Unterstrich und Leerzeichen (max. 64 Zeichen).")},
            status_code=400,
        )
    if len(value) > 20000:
        return JSONResponse({"error": T("Wert ist zu lang (max. 20.000 Zeichen)")}, status_code=400)
    vault.secret_set(name, value, client="web-ui")
    return JSONResponse({"ok": True})


async def secrets_get(request: Request) -> JSONResponse:
    name = request.path_params["name"]
    if name in HIDDEN_SECRETS:
        return JSONResponse({"error": "not found"}, status_code=404)
    value = vault.secret_get(name, client="web-ui")
    if value is None:
        return JSONResponse({"error": "not found"}, status_code=404)
    return JSONResponse({"value": value})


async def secrets_delete(request: Request) -> JSONResponse:
    name = request.path_params["name"]
    if name in HIDDEN_SECRETS:
        return JSONResponse({"error": "not found"}, status_code=404)
    existed = vault.secret_delete(name, client="web-ui")
    return JSONResponse({"ok": existed})


async def audit(request: Request) -> JSONResponse:
    lines = AUDIT_PATH.read_text().splitlines()[-200:] if AUDIT_PATH.exists() else []
    return JSONResponse(list(reversed(lines)))
