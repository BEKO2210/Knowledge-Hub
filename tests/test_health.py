"""Tests für das Health-Modell: /healthz/live, /healthz/ready, /healthz/deep.

Liveness und Readiness sind bewusst detailarm (nur ein Status-Wort) — sie sind über
den Tunnel erreichbar. Die Detailsicht (deep) verlangt denselben Bearer wie MCP und
darf trotzdem keine absoluten Serverpfade oder Secrets ausgeben.
"""

from __future__ import annotations

import json

from conftest import TMP


def test_live_ist_offen_und_minimal(client):
    r = client.get("/healthz/live")
    assert r.status_code == 200
    assert r.json() == {"status": "ok"}


def test_ready_gesund_ohne_details(client):
    r = client.get("/healthz/ready")
    assert r.status_code == 200
    assert r.json() == {"status": "ready"}  # exakt ein Feld — keine Check-Details nach außen


def test_ready_wird_unready_bei_kaputtem_graphen(client):
    """Ein existierendes Projekt mit nicht parsebarer graph.json macht die Instanz unready."""
    kaputt = TMP / "projects" / "kaputtes-projekt" / "graphify-out"
    kaputt.mkdir(parents=True, exist_ok=True)
    (kaputt / "graph.json").write_text("das ist kein json {", encoding="utf-8")
    try:
        r = client.get("/healthz/ready")
        assert r.status_code == 503
        assert r.json() == {"status": "unready"}  # auch im Fehlerfall keine Details
    finally:
        (kaputt / "graph.json").unlink()
        kaputt.rmdir()
        kaputt.parent.rmdir()


def test_ready_wird_unready_bei_fehlenden_assets(client, monkeypatch):
    import health

    monkeypatch.setattr(health, "WEB_DIR", TMP / "gibt-es-nicht")
    r = client.get("/healthz/ready")
    assert r.status_code == 503


def test_deep_verlangt_auth(client):
    assert client.get("/healthz/deep").status_code == 401


def test_deep_listet_alle_checks_ohne_interne_pfade(client, auth):
    r = client.get("/healthz/deep", headers=auth)
    assert r.status_code == 200
    body = r.json()
    assert body["status"] in ("ready", "unready")
    namen = {c["check"] for c in body["checks"]}
    erwartet = {
        "config",
        "datenpfade",
        "vault",
        "projektliste",
        "graphen",
        "mcp_tools",
        "assets",
        "migrationen",
    }
    assert erwartet <= namen, f"fehlende Checks: {erwartet - namen}"
    # Kein Check-Detail darf absolute Serverpfade oder Secret-Werte enthalten
    text = json.dumps(body)
    assert "/home/" not in text
    assert "/tmp/" not in text
    assert TMP.name not in text  # der konkrete Testverzeichnisname wäre ein Pfadleck


def test_deep_meldet_vollstaendige_toolliste(client, auth):
    body = client.get("/healthz/deep", headers=auth).json()
    tools = next(c for c in body["checks"] if c["check"] == "mcp_tools")
    assert tools["ok"] is True, tools


def test_deep_findet_kaputten_graphen_mit_projektname(client, auth):
    kaputt = TMP / "projects" / "defektes-projekt" / "graphify-out"
    kaputt.mkdir(parents=True, exist_ok=True)
    (kaputt / "graph.json").write_text("{", encoding="utf-8")
    try:
        body = client.get("/healthz/deep", headers=auth).json()
        assert body["status"] == "unready"
        graphen = next(c for c in body["checks"] if c["check"] == "graphen")
        assert graphen["ok"] is False
        assert "defektes-projekt" in graphen["detail"]  # Projektname ja — Pfad nein
    finally:
        (kaputt / "graph.json").unlink()
        kaputt.rmdir()
        kaputt.parent.rmdir()
