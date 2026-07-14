"""Semantischer Graph-Einstieg — eigener Retrieval-Kern statt graphify query.

Ein lokales, mehrsprachiges Embedding-Modell (fastembed/ONNX, CPU, offline) wählt
die Startknoten nach Bedeutung statt nach Substring: Deutsche Fragen finden
englische Code-Konzepte. Danach BFS Tiefe 2 über den Graphen. Die Ausgabe ist
zeilenkompatibel zu `graphify query`, damit graph_context.anreichern und alle
Konsumenten (MCP, UI) unverändert funktionieren.

Benchmark 2026-07-14 (~/graphify-bench): 65 % Hit-Rate vs. 46 % mit graphify.
Das Modell wird einmal pro Prozess geladen (~2 s) und bleibt danach warm (~50 ms/Query).
"""

from __future__ import annotations

import json
import threading
from pathlib import Path

import numpy as np

MODEL = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
INDEX_NAME = "semantic-index.npz"

# Chunk-Indizes (Roh-Datei-Auszüge) liegen hub-lokal, nicht im Wissens-Repo —
# sie enthalten Quelltext-Kopien und wären im Git-Sync nur Ballast.
CHUNK_DIR = Path(__file__).parent / "chunk-index"
SKIP_DIRS = {
    ".git",
    "node_modules",
    ".next",
    "dist",
    "build",
    "__pycache__",
    ".venv",
    "venv",
    "graphify-out",
    ".cache",
    "coverage",
    ".turbo",
    "vendor",
    "backups",
    "logs",
    "data",
}
TEXT_SUFFIXES = {
    ".py",
    ".ts",
    ".tsx",
    ".js",
    ".jsx",
    ".md",
    ".txt",
    ".yaml",
    ".yml",
    ".json",
    ".toml",
    ".sh",
    ".css",
    ".html",
    ".env",
    ".conf",
    ".ini",
    ".sql",
    ".prisma",
    ".service",
    ".timer",
}
SPECIAL_NAMES = {"Dockerfile", "docker-compose.yml", "docker-compose.yaml", "Caddyfile", "Makefile"}
CHUNK, OVERLAP, MAX_FILE, MAX_CHUNKS = 800, 120, 200_000, 4000

_model = None
_model_lock = threading.Lock()
_chunk_builds: set[str] = set()  # Projekte, deren Chunk-Index gerade im Hintergrund entsteht


def _get_model():
    global _model
    with _model_lock:
        if _model is None:
            from fastembed import TextEmbedding

            _model = TextEmbedding(MODEL)
        return _model


def _node_text(n: dict) -> str:
    parts = [n.get("label") or n.get("id") or ""]
    if n.get("community_label"):
        parts.append(str(n["community_label"]))
    if n.get("rationale"):
        parts.append(str(n["rationale"])[:600])
    if n.get("source_file"):
        parts.append(str(n["source_file"]))
    return " — ".join(p for p in parts if p)


def build_index(project_dir: Path) -> int:
    """Embedding-Index neben graph.json ablegen. Rückgabe: Anzahl Knoten."""
    graph_json = project_dir / "graphify-out" / "graph.json"
    g = json.loads(graph_json.read_text())
    nodes = g.get("nodes", [])
    if not nodes:
        return 0
    vecs = np.array(list(_get_model().embed([_node_text(n) for n in nodes])), dtype=np.float32)
    vecs /= np.linalg.norm(vecs, axis=1, keepdims=True) + 1e-9
    ids = np.array([n.get("id") or n.get("label") for n in nodes], dtype=object)
    np.savez_compressed(project_dir / "graphify-out" / INDEX_NAME, vecs=vecs, ids=ids)
    # Generation festhalten: der Index gehört zu genau diesem Graph-Stand (Build-Vertrag).
    import buildmeta

    buildmeta.write_index_meta(project_dir)
    return len(nodes)


def query(project_dir: Path, question: str, budget: int = 1200, seeds: int = 6) -> str:
    """Traversal-Kontext im graphify-query-Format (Traversal-Kopf + NODE-Zeilen)."""
    graph_json = project_dir / "graphify-out" / "graph.json"
    index_file = project_dir / "graphify-out" / INDEX_NAME
    if not index_file.exists() or index_file.stat().st_mtime < graph_json.stat().st_mtime:
        build_index(project_dir)  # fehlt oder veraltet — selbstheilend

    data = np.load(index_file, allow_pickle=True)
    vecs, ids = data["vecs"], data["ids"]
    q = np.array(list(_get_model().embed([question])), dtype=np.float32)[0]
    q /= np.linalg.norm(q) + 1e-9
    top = np.argsort(-(vecs @ q))[:seeds]
    seed_ids = [str(ids[i]) for i in top]

    g = json.loads(graph_json.read_text())
    by_id = {n.get("id") or n.get("label"): n for n in g.get("nodes", [])}
    adj: dict[str, set[str]] = {}
    for e in g.get("edges", g.get("links", [])):
        s, t = e.get("source"), e.get("target")
        adj.setdefault(s, set()).add(t)
        adj.setdefault(t, set()).add(s)

    seen, order, frontier = set(seed_ids), list(seed_ids), list(seed_ids)
    for _ in range(2):
        nxt = []
        for nid in frontier:
            for nb in sorted(adj.get(nid, ())):
                if nb not in seen:
                    seen.add(nb)
                    order.append(nb)
                    nxt.append(nb)
        frontier = nxt

    limit = budget * 4  # Budget in Tokens, ~4 Zeichen je Token
    start_labels = [by_id.get(s, {}).get("label", s) for s in seed_ids]
    lines = [
        f"Traversal: semantic top-{seeds} + BFS depth=2 | Start: {start_labels} | {len(order)} nodes found",
        "",
    ]
    used = sum(len(x) for x in lines)
    for nid in order:
        n = by_id.get(nid)
        if n is None:
            continue
        line = (
            f"NODE {n.get('label', nid)} [src={n.get('source_file')} "
            f"loc={n.get('loc')} community={n.get('community_label')}]"
        )
        if used + len(line) > limit:
            break
        lines.append(line)
        used += len(line)
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Hybrid-Modus: Graph-Kontext + Roh-Datei-Auszüge in einer Antwort.
# Benchmark-Motivation: Graph gewinnt bei kleinem Budget (65 % @400), Volltext-
# Chunks gewinnen bei großem (96 % @1200) — der Hybrid soll beides liefern.
# ---------------------------------------------------------------------------


def _iter_source_files(root: Path):
    import os

    for p in sorted(root.rglob("*")):
        if any(part in SKIP_DIRS for part in p.parts):
            continue
        if p.is_file() and (
            p.suffix.lower() in TEXT_SUFFIXES or p.name in SPECIAL_NAMES or p.name.startswith(".env")
        ):
            try:
                if 0 < p.stat().st_size <= MAX_FILE and os.access(p, os.R_OK):
                    yield p
            except OSError:
                continue


def build_chunk_index(project: str, source_dir: Path) -> int:
    """Datei-Chunks eines Quellprojekts embedden. Rückgabe: Anzahl Chunks."""
    chunks: list[str] = []
    for f in _iter_source_files(source_dir):
        try:
            text = f.read_text(errors="ignore")
        except OSError:
            continue
        rel = str(f.relative_to(source_dir))
        for i in range(0, max(len(text), 1), CHUNK - OVERLAP):
            piece = text[i : i + CHUNK]
            if piece.strip():
                chunks.append(f"[{rel}]\n{piece}")
        if len(chunks) >= MAX_CHUNKS:
            break
    if not chunks:
        return 0
    vecs = np.array(list(_get_model().embed(chunks)), dtype=np.float32)
    vecs /= np.linalg.norm(vecs, axis=1, keepdims=True) + 1e-9
    CHUNK_DIR.mkdir(exist_ok=True)
    np.savez_compressed(CHUNK_DIR / f"{project}.npz", vecs=vecs, chunks=np.array(chunks, dtype=object))
    return len(chunks)


def _chunk_index_background(project: str, source_dir: Path) -> None:
    """Fehlenden Chunk-Index nachziehen, ohne die laufende Anfrage zu blockieren."""
    if project in _chunk_builds:
        return
    _chunk_builds.add(project)

    def _run():
        try:
            build_chunk_index(project, source_dir)
        except Exception:  # noqa: BLE001 - Hintergrundaufbau darf nie stören
            pass
        finally:
            _chunk_builds.discard(project)

    threading.Thread(target=_run, daemon=True).start()


def _top_chunks(project: str, q_vec: np.ndarray, char_limit: int) -> list[str]:
    f = CHUNK_DIR / f"{project}.npz"
    if not f.exists():
        return []
    data = np.load(f, allow_pickle=True)
    vecs, chunks = data["vecs"], data["chunks"]
    out, used = [], 0
    for i in np.argsort(-(vecs @ q_vec)):
        c = str(chunks[i])
        if used + len(c) > char_limit:
            break
        out.append(c)
        used += len(c)
    return out


def hybrid_query(
    project_dir: Path,
    question: str,
    budget: int = 1200,
    source_dir: Path | None = None,
    graph_share: float = 0.4,
) -> str:
    """Graph-Traversal (~40 % Budget) + relevanteste Datei-Auszüge (~60 %).

    Fehlt der Chunk-Index oder das Quellverzeichnis, kommt Graph-only zurück —
    eine Anfrage wartet nie auf einen Index-Aufbau (der startet im Hintergrund).
    """
    project = project_dir.name
    graph_part = query(project_dir, question, budget=max(int(budget * graph_share), 150))

    if source_dir is None or not source_dir.is_dir():
        return graph_part
    if not (CHUNK_DIR / f"{project}.npz").exists():
        _chunk_index_background(project, source_dir)
        return graph_part

    q = np.array(list(_get_model().embed([question])), dtype=np.float32)[0]
    q /= np.linalg.norm(q) + 1e-9
    chunks = _top_chunks(project, q, char_limit=int(budget * 4 * (1 - graph_share)))
    if not chunks:
        return graph_part
    return graph_part + "\n\nFUNDSTELLEN (relevante Datei-Auszüge):\n" + "\n---\n".join(chunks)
