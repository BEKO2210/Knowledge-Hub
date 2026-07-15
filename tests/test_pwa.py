"""PWA-Bausteine der Hub-UI: Manifest vollständig, Service Worker sicher ausgeliefert."""

from __future__ import annotations

import ui


def test_manifest_hat_maskable_icon_und_scope(client, auth, fresh_vault):
    m = client.get("/ui/manifest.json").json()
    assert m["scope"] == "/ui" and m["id"] == "/ui"
    zwecke = {i.get("purpose", "any") for i in m["icons"]}
    assert "maskable" in zwecke, "Android braucht ein maskable Icon"
    assert any(i["sizes"] == "512x512" for i in m["icons"])


def test_service_worker_wird_versioniert_ausgeliefert(client, auth, fresh_vault):
    r = client.get("/ui/sw.js")
    assert r.status_code == 200
    assert "javascript" in r.headers["content-type"]
    body = r.text
    assert f"VERSION = '{ui.ASSET_V}'" in body, "Cache-Version muss die Asset-Version tragen"
    assert "__V__" not in body, "Platzhalter muss ersetzt sein"


def test_service_worker_cached_nie_api_oder_mcp(client, auth, fresh_vault):
    """Die Sicherheitsregel steht im Code des Workers selbst — hier festgenagelt."""
    body = client.get("/ui/sw.js").text
    assert "/ui/api/" in body and "/mcp" in body and "return" in body
    # Der Precache darf keinerlei API-Pfade enthalten
    pre = body.split("PRECACHE")[1].split("]")[0]
    assert "/ui/api" not in pre and "/mcp" not in pre and "secret" not in pre.lower()
