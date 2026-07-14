"""Tests für semantic.py — Index, Query, Hybrid und die Fallback-Garantien.

Nutzt einen synthetischen Mini-Graphen + Mini-Quellordner, kein echtes Modell
nötig: das Embedding wird durch einen deterministischen Fake ersetzt, damit die
Tests offline und in Millisekunden laufen.
"""

from __future__ import annotations

import json
from pathlib import Path

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
    with pytest.raises(Exception):
        semantic.query(out, "vault", budget=400)
    # Selbstheilung: Graph anfassen → nächste Query baut neu und funktioniert
    graph = out / "graphify-out" / "graph.json"
    import os

    os.utime(graph, (graph.stat().st_atime, graph.stat().st_mtime + 10))
    assert "NODE" in semantic.query(out, "vault", budget=400)
