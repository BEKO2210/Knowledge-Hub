"""Secrets-Vault und Audit-Log."""

from __future__ import annotations

from starlette.requests import Request
from starlette.responses import JSONResponse

import vault
from api.common import AUDIT_PATH, json_object
from api.i18n import T

# Eine Quelle für beide Wege in den Vault (Oberfläche UND MCP) — definiert in vault.py.
# Vorher standen die Regeln nur hier: über MCP galten sie nicht.
HIDDEN_SECRETS = vault.HIDDEN_SECRETS
SECRET_NAME_RE = vault.SECRET_NAME_RE


async def secrets_list(request: Request) -> JSONResponse:
    return JSONResponse([s for s in vault.secret_list(client="web-ui") if s not in HIDDEN_SECRETS])


async def secrets_set(request: Request) -> JSONResponse:
    body = await json_object(request)
    name, value = str(body.get("name", "")).strip(), str(body.get("value", ""))
    if not name or not value:
        return JSONResponse({"error": T("Name und Wert sind Pflicht")}, status_code=400)
    # Erlaubt: Buchstaben, Ziffern, _ . - und Leerzeichen. Alles andere (Steuerzeichen,
    # Zeilenumbrüche, Pfadtrenner) wird abgelehnt. Der Vault prüft dasselbe noch einmal —
    # hier passiert es nur früher, damit die Meldung übersetzt ankommt. Abgelehnte
    # Versuche landen im Audit-Log: Herumprobieren hinterlässt eine Spur.
    if not SECRET_NAME_RE.match(name):
        vault.audit("SET-REJECT", f"{name} (Name unzulässig)", client="web-ui")
        return JSONResponse(
            {
                "error": T(
                    "Ungültiger Name — erlaubt sind Buchstaben, Ziffern, Punkt, Bindestrich, "
                    "Unterstrich und Leerzeichen (max. 64 Zeichen)."
                )
            },
            status_code=400,
        )
    if len(value) > vault.SECRET_VALUE_MAX:
        vault.audit("SET-REJECT", f"{name} (Wert {len(value)} Zeichen)", client="web-ui")
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
