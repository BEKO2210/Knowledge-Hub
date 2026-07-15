"""Run-024: Performance/Last — Graph-Ansicht cacht (mtime), blockiert die Event-Loop
nicht mehr synchron bei jedem Aufruf.

Beleg: ~/hub-audit/EVIDENCE/run-024/perf_probe.py (20-MB-Graph: 201 ms Loop-Block je
Request inline; 100 gleichzeitige Aufrufe → 4049 ms Loop-Lag → nach Cache nahe 0).
"""

from __future__ import annotations

import json
import os
import shutil

import pytest

import api.knowledge as K
from api.common import KNOWLEDGE_ROOT


@pytest.fixture
def projekt():
    """Projekt mit graph.json unter KNOWLEDGE_ROOT anlegen, danach wegräumen +
    Modul-Caches leeren (persistieren sonst über Tests)."""
    created = []

    def mk(name: str, graph: dict):
        d = KNOWLEDGE_ROOT / name / "graphify-out"
        d.mkdir(parents=True, exist_ok=True)
        f = d / "graph.json"
        f.write_text(json.dumps(graph))
        created.append(KNOWLEDGE_ROOT / name)
        return f

    yield mk
    for c in created:
        shutil.rmtree(c, ignore_errors=True)
    K._parsed_cache.clear()
    K._payload_cache.clear()


def test_read_graph_cache_haelt_bis_mtime_wechsel(projekt):
    f = projekt("perf1", {"nodes": [{"id": "a"}], "links": []})
    assert K._read_graph("perf1")["nodes"] == [{"id": "a"}]

    # Inhalt ändern, aber die alte mtime erzwingen → Cache liefert weiter den alten Stand
    old = f.stat().st_mtime
    f.write_text(json.dumps({"nodes": [{"id": "b"}], "links": []}))
    os.utime(f, (old, old))
    assert K._read_graph("perf1")["nodes"] == [{"id": "a"}]

    # mtime vorschieben → neu gelesen
    os.utime(f, (old + 10, old + 10))
    assert K._read_graph("perf1")["nodes"] == [{"id": "b"}]


def test_graph_endpoint_ist_gecacht_und_korrekt(client, auth, projekt):
    projekt(
        "perf2",
        {
            "nodes": [{"id": "a"}, {"id": "b"}, {"id": "c"}],
            "links": [{"source": "a", "target": "b"}, {"source": "a", "target": "c"}],
        },
    )
    r1 = client.get("/ui/api/graph/perf2", headers=auth)
    r2 = client.get("/ui/api/graph/perf2", headers=auth)
    assert r1.status_code == 200
    assert r1.json() == r2.json()  # zweiter Aufruf aus dem Cache, identisch
    body = r1.json()
    assert body["total_nodes"] == 3 and body["total_links"] == 2
    # „a" hat den höchsten Grad (2) → steht vorn
    assert body["nodes"][0]["id"] == "a" and body["nodes"][0]["degree"] == 2


def test_graph_cache_invalidiert_bei_rebuild(client, auth, projekt):
    f = projekt("perf3", {"nodes": [{"id": "a"}], "links": []})
    assert client.get("/ui/api/graph/perf3", headers=auth).json()["total_nodes"] == 1

    # „Rebuild": neuer Inhalt mit neuer mtime → Endpunkt liefert den neuen Graphen
    old = f.stat().st_mtime
    f.write_text(json.dumps({"nodes": [{"id": "a"}, {"id": "b"}], "links": []}))
    os.utime(f, (old + 20, old + 20))
    assert client.get("/ui/api/graph/perf3", headers=auth).json()["total_nodes"] == 2


def test_kaputter_graph_wird_nicht_als_leer_gecacht(client, auth, projekt):
    # Kaputt → leere Antwort mit Hinweis, NICHT im Payload-Cache hängengeblieben,
    # sodass ein späterer Rebuild wieder greift.
    f = projekt("perf4", {"nodes": [{"id": "a"}], "links": []})
    old = f.stat().st_mtime
    f.write_text("{kaputt")
    os.utime(f, (old + 5, old + 5))
    r = client.get("/ui/api/graph/perf4", headers=auth)
    assert r.status_code == 200 and r.json()["total_nodes"] == 0

    f.write_text(json.dumps({"nodes": [{"id": "a"}], "links": []}))
    os.utime(f, (old + 30, old + 30))
    assert client.get("/ui/api/graph/perf4", headers=auth).json()["total_nodes"] == 1
