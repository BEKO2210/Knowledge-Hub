"""Übersicht/Diagnose zählt Secrets wie die User-Liste — interne (__2fa__) NICHT mit.

Regression zu UI/Backend-Kampagne Run 13 (Befund R13-1): die Übersichts-Kachel und die
Diagnose-Karte „Secrets-Vault" zählten `vault.secret_list()` ungefiltert, während jede
User-Oberfläche (UI-Liste, UI-Get/Delete, MCP) `HIDDEN_SECRETS` ausblendet. Ergebnis:
„15 Secrets" in der Übersicht, aber 14 in der Liste — verwirrend und inkonsistent.
"""

from __future__ import annotations

import json


def test_health_zaehlt_interne_secrets_nicht_mit(client, auth, fresh_vault, monkeypatch):
    import vault

    # Zwei echte Secrets + ein internes (__2fa__). Nur die zwei echten dürfen zählen.
    monkeypatch.setattr(vault, "secret_list", lambda client="-": ["open_ai", "backup_git_token", "__2fa__"])
    r = client.get("/ui/api/health", headers=auth)
    assert r.status_code == 200
    body = r.json()

    # Übersichts-Kachel
    assert body["info"]["secrets"] == 2, body["info"]

    # Diagnose-Karte „Secrets-Vault" zeigt dieselbe (gefilterte) Zahl (sprach-robust)
    vault_check = next(c for c in body["checks"] if "secret" in c["name"].lower())
    detail = vault_check["detail"].lower()
    assert detail.startswith("2 ") and "secret" in detail, vault_check
    assert "3 secret" not in detail, vault_check

    # der interne Name darf nirgends in der Antwort auftauchen
    assert "__2fa__" not in json.dumps(body)
