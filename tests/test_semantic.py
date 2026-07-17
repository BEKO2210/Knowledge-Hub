"""Tests für semantic.py — Index, Query, Hybrid und die Fallback-Garantien.

Nutzt einen synthetischen Mini-Graphen + Mini-Quellordner, kein echtes Modell
nötig: das Embedding wird durch einen deterministischen Fake ersetzt, damit die
Tests offline und in Millisekunden laufen.
"""

from __future__ import annotations

import json
import pickle

import numpy as np
import pytest

import semantic


class FakeModel:
    """Deterministisches 8-dim-Embedding: Hash-Buckets über Kleinbuchstaben-Wörter."""

    def embed(self, texts):
        for t in texts:
            v = np.zeros(8, dtype=np.float32)
            for w in str(t).lower().split():
                v[hash(w) % 8] += 1.0
            yield v


@pytest.fixture()
def fake_model(monkeypatch):
    monkeypatch.setattr(semantic, "_get_model", lambda: FakeModel())


@pytest.fixture()
def projekt(tmp_path):
    """Mini-Projekt: Graph mit 3 Knoten + Quellordner mit 2 Dateien."""
    out = tmp_path / "graph-kopie"
    (out / "graphify-out").mkdir(parents=True)
    graph = {
        "directed": True,
        "nodes": [
            {"id": "jelly", "label": "jellyfin server", "rationale": "läuft auf port 8097"},
            {"id": "vault", "label": "secrets vault", "rationale": "aes-256-gcm verschlüsselt"},
            {"id": "unrelated", "label": "random helper", "rationale": ""},
        ],
        "links": [
            {"source": "jelly", "target": "vault", "relation": "uses"},
        ],
    }
    (out / "graphify-out" / "graph.json").write_text(json.dumps(graph))

    src = tmp_path / "quelle"
    src.mkdir()
    (src / "DEPLOY.md").write_text("jellyfin server läuft auf port 8097 hinter dem tunnel")
    (src / "notes.txt").write_text("der vault nutzt aes-256-gcm mit scrypt ableitung")
    return out, src


def test_build_index_erzeugt_npz(fake_model, projekt):
    out, _ = projekt
    n = semantic.build_index(out)
    assert n == 3
    assert (out / "graphify-out" / semantic.INDEX_NAME).exists()


# --- R11-2: Community-Benennung fließt in den Embedding-Text ------------------
def test_node_text_nutzt_community_name():
    n = {"label": "next_js_16", "community_name": "Framework", "rationale": "Version 16"}
    t = semantic._node_text(n)
    assert "Framework" in t and "next_js_16" in t


def test_node_text_loest_community_ueber_labels_auf():
    # Älterer Graph: nur community-ID, Name steht in .graphify_labels.json
    n = {"label": "next_js_16", "community": 6}
    t = semantic._node_text(n, labels={"6": "PWA (Next.js)"})
    assert "PWA (Next.js)" in t


def test_node_text_ignoriert_leeres_community_label():
    # community_label ist in own-Graphen immer leer — kein leerer Trenner o. Ä.
    n = {"label": "x", "community_label": ""}
    assert semantic._node_text(n) == "x"


def test_query_findet_semantisch_passende_knoten(fake_model, projekt):
    out, _ = projekt
    semantic.build_index(out)
    text = semantic.query(out, "jellyfin server", budget=400)
    assert "Traversal: semantic" in text
    assert "jellyfin server" in text
    # BFS zieht den verbundenen Vault-Knoten mit rein
    assert "secrets vault" in text


def test_query_heilt_fehlenden_index_selbst(fake_model, projekt):
    out, _ = projekt
    # kein build_index vorher — query muss ihn selbst anlegen
    text = semantic.query(out, "vault", budget=400)
    assert "NODE" in text
    assert (out / "graphify-out" / semantic.INDEX_NAME).exists()


def test_query_baut_index_neu_wenn_graph_neuer(fake_model, projekt):
    out, _ = projekt
    semantic.build_index(out)
    idx = out / "graphify-out" / semantic.INDEX_NAME
    import os

    # Index künstlich alt machen — der Graph ist damit neuer
    os.utime(idx, (idx.stat().st_atime, idx.stat().st_mtime - 100))
    alt = idx.stat().st_mtime
    semantic.query(out, "vault", budget=400)
    assert idx.stat().st_mtime > alt


def test_chunk_index_und_topchunks(fake_model, projekt, tmp_path, monkeypatch):
    out, src = projekt
    monkeypatch.setattr(semantic, "CHUNK_DIR", tmp_path / "chunks")
    n = semantic.build_chunk_index("testprojekt", src)
    assert n == 2
    q = np.array(list(FakeModel().embed(["port 8097"])), dtype=np.float32)[0]
    q /= np.linalg.norm(q) + 1e-9
    chunks = semantic._top_chunks("testprojekt", q, char_limit=4000)
    assert chunks and "8097" in " ".join(chunks)


def test_hybrid_enthaelt_graph_und_fundstellen(fake_model, projekt, tmp_path, monkeypatch):
    out, src = projekt
    monkeypatch.setattr(semantic, "CHUNK_DIR", tmp_path / "chunks")
    semantic.build_chunk_index(out.name, src)
    text = semantic.hybrid_query(out, "port 8097", budget=1200, source_dir=src)
    assert "Traversal: semantic" in text
    assert "FUNDSTELLEN" in text
    assert "8097" in text


def test_hybrid_ohne_quellordner_faellt_auf_graph_zurueck(fake_model, projekt):
    out, _ = projekt
    text = semantic.hybrid_query(out, "vault", budget=800, source_dir=None)
    assert "Traversal: semantic" in text
    assert "FUNDSTELLEN" not in text


def test_hybrid_ohne_chunkindex_blockiert_nicht(fake_model, projekt, tmp_path, monkeypatch):
    """Fehlender Chunk-Index: sofort Graph-only-Antwort, Aufbau läuft im Hintergrund."""
    out, src = projekt
    monkeypatch.setattr(semantic, "CHUNK_DIR", tmp_path / "leer")
    text = semantic.hybrid_query(out, "vault", budget=800, source_dir=src)
    assert "Traversal: semantic" in text
    assert "FUNDSTELLEN" not in text  # Antwort kam, ohne auf den Build zu warten


def test_kaputter_index_wirft_und_stoert_query_nicht_dauerhaft(fake_model, projekt):
    """Ein korrupter Index darf nur die eine Anfrage betreffen — danach heilt mtime."""
    out, _ = projekt
    semantic.build_index(out)
    idx = out / "graphify-out" / semantic.INDEX_NAME
    idx.write_bytes(b"kaputt")
    with pytest.raises(pickle.UnpicklingError):
        semantic.query(out, "vault", budget=400)
    # Selbstheilung: Graph anfassen → nächste Query baut neu und funktioniert
    graph = out / "graphify-out" / "graph.json"
    import os

    os.utime(graph, (graph.stat().st_atime, graph.stat().st_mtime + 10))
    assert "NODE" in semantic.query(out, "vault", budget=400)


def test_chunk_index_schliesst_laufzeit_und_fremddaten_aus(tmp_path):
    """Regression: der Chunk-Index (semantic._iter_source_files) schloss answers/,
    build-logs/ und Hub-Zustandsdateien NICHT aus — so landeten fremde query-*.json und
    Build-Logs als FUNDSTELLEN in Antworten. Muss deckungsgleich mit extraction sein."""
    (tmp_path / "echt.py").write_text("def f():\n    return 1\n")
    (tmp_path / "answers").mkdir()
    (tmp_path / "answers" / "q.json").write_text('{"x": 1}')
    (tmp_path / "build-logs").mkdir()
    (tmp_path / "build-logs" / "run.json").write_text('{"x": 1}')
    (tmp_path / "oauth_state.json").write_text('{"tokens": {}}')
    gefunden = {p.name for p in semantic._iter_source_files(tmp_path)}
    assert "echt.py" in gefunden
    assert "q.json" not in gefunden, "answers/ darf nicht in den Chunk-Index"
    assert "run.json" not in gefunden, "build-logs/ darf nicht in den Chunk-Index"
    assert "oauth_state.json" not in gefunden, "Hub-Zustand darf nicht in den Chunk-Index"
    for d in ("answers", "chunk-index", "build-logs", "backup-repo"):
        assert d in semantic.SKIP_DIRS
