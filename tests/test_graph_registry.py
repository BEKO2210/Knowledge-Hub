"""Post-Run-40 Bug 2: Registrierung ist die Quelle der Wahrheit für Graphen.

Auftrags-Testkategorien 4-7: Waise ohne Config-Eintrag, Wiederregistrierung,
vollständige Entfernung, Gleichstand zwischen UI-API, MCP-Sicht und Dateisystem.
"""

from __future__ import annotations

import json

from conftest import TMP

import config
from api import mapping

KNOWLEDGE = TMP / "projects"


def _hub_graph(name: str, nodes: int = 3) -> None:
    out = KNOWLEDGE / name / "graphify-out"
    out.mkdir(parents=True, exist_ok=True)
    (out / "graph.json").write_text(
        json.dumps(
            {
                "nodes": [{"id": f"n{i}", "community": i % 2} for i in range(nodes)],
                "links": [{"source": "n0", "target": "n1"}],
            }
        )
    )


def _quelle(name: str) -> str:
    p = TMP / "src" / name
    p.mkdir(parents=True, exist_ok=True)
    return str(p)


import pytest


@pytest.fixture(autouse=True)
def _sauberer_bestand():
    def _clean():
        import shutil

        for d in KNOWLEDGE.iterdir() if KNOWLEDGE.exists() else []:
            if d.is_dir():
                shutil.rmtree(d)
        config.save_projects([])
        config.save_archived_graphs([])

    _clean()
    yield
    _clean()


def test_waise_wird_erkannt_und_nicht_still_normal_gelistet(client, auth, fresh_vault):
    _hub_graph("geisterprojekt")
    inv = mapping.graph_inventory()
    assert [g["name"] for g in inv["unregistered"]] == ["geisterprojekt"]
    assert inv["registered"] == [] and inv["archived"] == []

    # MCP-Sicht kennzeichnet die Waise ebenfalls
    import server

    eintrag = next(p for p in server.projects_list() if p["project"] == "geisterprojekt")
    assert eintrag.get("unregistered") is True

    # Diagnose warnt
    r = client.get("/ui/api/health", headers=auth)
    check = next(c for c in r.json()["checks"] if c.get("id") == "graphs")
    assert check["status"] == "warn" and "geisterprojekt" in check["detail"]


def test_registrierung_macht_die_waise_zum_projekt(client, auth, fresh_vault):
    _hub_graph("wieder")
    config.save_projects([{"path": _quelle("wieder"), "enabled": True}])
    inv = mapping.graph_inventory()
    assert [g["name"] for g in inv["registered"]] == ["wieder"]
    assert inv["unregistered"] == []
    r = client.get("/ui/api/health", headers=auth)
    assert next(c for c in r.json()["checks"] if c.get("id") == "graphs")["status"] == "ok"


def test_archivieren_braucht_herkunft_und_dokumentiert_sie(client, auth, fresh_vault):
    _hub_graph("beweis")
    r = client.post("/ui/api/mapping/graphs", headers=auth, json={"name": "beweis", "action": "archive"})
    assert r.status_code == 400, "ohne origin darf nicht archiviert werden"

    r = client.post(
        "/ui/api/mapping/graphs",
        headers=auth,
        json={"name": "beweis", "action": "archive", "origin": "Benchmark-Beleg XY"},
    )
    assert r.status_code == 200
    inv = mapping.graph_inventory()
    a = inv["archived"][0]
    assert a["name"] == "beweis" and a["origin"] == "Benchmark-Beleg XY" and a["archived_at"]
    assert inv["unregistered"] == []
    # MCP-Sicht traegt das Archiv-Kennzeichen
    import server

    eintrag = next(p for p in server.projects_list() if p["project"] == "beweis")
    assert eintrag.get("archived") is True and eintrag.get("origin") == "Benchmark-Beleg XY"
    assert "GRAPH-ARCHIVE" in (TMP / "audit.log").read_text()


def test_entfernen_loescht_alle_hub_artefakte_aber_nie_die_quelle(client, auth, fresh_vault):
    _hub_graph("weg")
    _quelle("weg")
    (KNOWLEDGE / "weg" / "graphify-out" / "semantic-index.npz").write_bytes(b"x")
    (TMP / "answers" / "weg").mkdir(parents=True, exist_ok=True)
    import semantic

    (semantic.CHUNK_DIR / "weg").mkdir(parents=True, exist_ok=True)

    r = client.post("/ui/api/mapping/graphs", headers=auth, json={"name": "weg", "action": "remove"})
    assert r.status_code == 200
    assert not (KNOWLEDGE / "weg").exists(), (
        "Hub-Kopie (Graph, Report, Viewer, Index, Manifest) muss weg sein"
    )
    assert not (TMP / "answers" / "weg").exists()
    assert not (semantic.CHUNK_DIR / "weg").exists()
    assert (TMP / "src" / "weg").exists(), "Quellordner darf NIE angefasst werden"
    assert mapping.graph_inventory() == {"registered": [], "archived": [], "unregistered": []}
    assert "GRAPH-PURGE" in (TMP / "audit.log").read_text()


def test_geschuetzte_interne_ordner_sind_kein_bestand_und_nicht_entfernbar(client, auth, fresh_vault):
    _hub_graph("hub-backups")  # interner Name — darf nie als Benutzerprojekt auftauchen
    assert all("hub-backups" not in [g["name"] for g in v] for v in mapping.graph_inventory().values())
    r = client.post("/ui/api/mapping/graphs", headers=auth, json={"name": "hub-backups", "action": "remove"})
    assert r.status_code == 404
    assert (KNOWLEDGE / "hub-backups").exists()


def test_gleichstand_zwischen_mcp_api_und_dateisystem(client, auth, fresh_vault):
    _hub_graph("a", nodes=4)
    _hub_graph("b", nodes=2)
    config.save_projects([{"path": _quelle("a"), "enabled": True}])
    config.save_archived_graphs([{"name": "b", "origin": "Test", "archived_at": "2026-01-01T00:00:00Z"}])

    import server

    mcp_sicht = {p["project"]: p for p in server.projects_list()}
    inv = mapping.graph_inventory()
    fs = sorted(d.name for d in KNOWLEDGE.iterdir() if (d / "graphify-out" / "graph.json").exists())

    assert sorted(mcp_sicht) == fs == ["a", "b"]
    assert len(inv["registered"]) + len(inv["archived"]) + len(inv["unregistered"]) == len(fs)
    assert mcp_sicht["a"].get("archived") is None and mcp_sicht["a"].get("unregistered") is None
    assert mcp_sicht["b"].get("archived") is True
    ui = client.get("/ui/api/mapping/graphs", headers=auth).json()
    assert [g["name"] for g in ui["archived"]] == ["b"] and ui["unregistered"] == []
