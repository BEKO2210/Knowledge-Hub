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
    # Typ-Validierung vor jeder Weiterverarbeitung: eine str()-Koersion würde JSON-null
    # sonst still zu einem Secret namens "None" mit Wert "None" machen — ein
    # Aufruferfehler muss als 400 sichtbar sein, nicht als Daten-Müll im Vault.
    name, value = body.get("name"), body.get("value")
    if not isinstance(name, str) or not isinstance(value, str):
        return JSONResponse({"error": T("Name und Wert sind Pflicht")}, status_code=400)
    name = name.strip()
    if not name or not value:
        return JSONResponse({"error": T("Name und Wert sind Pflicht")}, status_code=400)
    # Erlaubt: Buchstaben, Ziffern, _ . - und Leerzeichen. Alles andere (Steuerzeichen,
    # Zeilenumbrüche, Pfadtrenner) wird abgelehnt. Der Vault prüft dasselbe noch einmal —
    # hier passiert es nur früher, damit die Meldung übersetzt ankommt. Abgelehnte
    # Versuche landen im Audit-Log: Herumprobieren hinterlässt eine Spur.
    # Reine Punkt-Namen (".", "..") bestehen die Regex, sind aber Pfad-Artefakte: Über
    # HTTP normalisieren Clients /ui/api/secrets/.. zur Elternroute — das Secret wäre in
    # der Oberfläche weder abruf- noch löschbar. Daher bereits beim Setzen ablehnen.
    if not SECRET_NAME_RE.match(name) or not name.strip("."):
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
    # Versteckte/interne Secrets (z. B. __2fa__) sind über die Oberfläche nicht setzbar —
    # sonst ließe sich per Web-SET der 2FA-Blob überschreiben (stilles Abschalten oder
    # injizierter TOTP-Seed). Dieselbe 404-Antwort wie bei get/delete, damit kein
    # Existenz-Orakel entsteht; der MCP-Weg sperrt das bereits genauso.
    if name in HIDDEN_SECRETS:
        return JSONResponse({"error": "not found"}, status_code=404)
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
