"""Tests für den Graph-Build-Vertrag (buildmeta.py).

Jede Graph-Generation trägt ein build-manifest.json: Build-ID, Quelle, Zählungen und
Artefakt-Hashes. Graph, Report, Viewer und Semantik-Index gehören nachweisbar zu
DERSELBEN Generation — Misch-Stände (U-1, 2026-07-14) werden maschinell erkennbar.
"""

from __future__ import annotations

import json

import pytest

import buildmeta


@pytest.fixture
def projekt(tmp_path):
    out = tmp_path / "graphify-out"
    out.mkdir(parents=True)
    graph = {
        "nodes": [
            {"id": "a", "community": 0},
            {"id": "b", "community": 0},
            {"id": "c", "community": 1},
        ],
        "links": [{"source": "a", "target": "b"}],
    }
    (out / "graph.json").write_text(json.dumps(graph), encoding="utf-8")
    (out / "GRAPH_REPORT.md").write_text("# Report\n", encoding="utf-8")
    (out / "graph.html").write_text("<html></html>", encoding="utf-8")
    return tmp_path


def test_manifest_enthaelt_pflichtfelder(projekt):
    m = buildmeta.write_manifest(projekt)
    assert m["build_id"].startswith("g-")
    assert m["schema_version"] == "1.0"
    assert m["counts"] == {"nodes": 3, "edges": 1, "communities": 2}
    assert "graph.json" in m["artifacts"]
    assert "GRAPH_REPORT.md" in m["artifacts"]
    assert "graph.html" in m["artifacts"]
    assert m["created_at"]
    assert (projekt / "graphify-out" / buildmeta.BUILD_MANIFEST).exists()


def test_verify_ok_nach_write(projekt):
    buildmeta.write_manifest(projekt)
    v = buildmeta.verify(projekt)
    assert v["status"] == "ok", v


def test_verify_erkennt_veraenderten_graphen(projekt):
    buildmeta.write_manifest(projekt)
    g = projekt / "graphify-out" / "graph.json"
    doc = json.loads(g.read_text())
    doc["nodes"].append({"id": "geist", "community": 9})
    g.write_text(json.dumps(doc))
    v = buildmeta.verify(projekt)
    assert v["status"] == "mismatch"
    assert "graph.json" in v["detail"]


def test_verify_erkennt_fremden_report(projekt):
    buildmeta.write_manifest(projekt)
    (projekt / "graphify-out" / "GRAPH_REPORT.md").write_text("# anderer Stand\n")
    v = buildmeta.verify(projekt)
    assert v["status"] == "mismatch"
    assert "GRAPH_REPORT.md" in v["detail"]


def test_verify_ohne_manifest_ist_legacy(projekt):
    v = buildmeta.verify(projekt)
    assert v["status"] == "legacy"


def test_verify_erkennt_index_anderer_generation(projekt):
    buildmeta.write_manifest(projekt)
    out = projekt / "graphify-out"
    (out / "semantic-index.npz").write_bytes(b"x")
    (out / buildmeta.INDEX_META).write_text(json.dumps({"build_id": "g-fremd-00000000", "indexed_at": "x"}))
    v = buildmeta.verify(projekt)
    assert v["status"] == "mismatch"
    assert "Index" in v["detail"] or "index" in v["detail"]


def test_index_meta_wird_beim_indexbau_geschrieben(projekt, monkeypatch):
    import semantic

    class FakeModel:
        def embed(self, texts):
            import numpy as np

            for _ in texts:
                yield np.ones(4, dtype="float32")

    monkeypatch.setattr(semantic, "_get_model", lambda: FakeModel())
    buildmeta.write_manifest(projekt)
    semantic.build_index(projekt)
    meta = json.loads((projekt / "graphify-out" / buildmeta.INDEX_META).read_text())
    manifest = json.loads((projekt / "graphify-out" / buildmeta.BUILD_MANIFEST).read_text())
    assert meta["build_id"] == manifest["build_id"]
    assert buildmeta.verify(projekt)["status"] == "ok"
