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

import fnmatch
import json
import os
import pickle
import tempfile
import threading
from contextlib import contextmanager
from pathlib import Path

import numpy as np

MODEL = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
INDEX_NAME = "semantic-index.npz"

# Chunk-Indizes (Roh-Datei-Auszüge) liegen hub-lokal, nicht im Wissens-Repo —
# sie enthalten Quelltext-Kopien und wären im Git-Sync nur Ballast.
# Env-überschreibbar: Bei unveränderlichen Blue-Green-Releases läge der Index sonst
# im Release-Verzeichnis und würde bei jedem Release neu gebaut (hub-audit, Umzug).
CHUNK_DIR = Path(os.environ.get("KMCP_CACHE_DIR", str(Path(__file__).parent))) / "chunk-index"
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
    "third_party",
    "test-results",
    "playwright-report",
    ".pytest_cache",
    ".ruff_cache",
    "backups",
    "backup-repo",  # verschlüsselte Off-Site-Backups ANDERER Projekte — nie ins Wissen
    "logs",
    "data",
    # Laufzeit-/Cache-Zustand des Hubs selbst — kein Architekturwissen. Ohne diese
    # Ausschlüsse zog der Chunk-Index answers/<fremdprojekt>/query-*.json und
    # build-logs/runs/*.json als „FUNDSTELLEN" in Antworten (deckungsgleich mit
    # extraction.SKIP_STATE_DIRS — beide Pipelines MÜSSEN identisch ausschließen).
    "answers",
    "chunk-index",
    "build-logs",
}
# Veränderliche Zustands-Dateien liegen teils direkt im Projektordner (nicht in einem
# SKIP_DIRS-Ordner) und sind .json/.log — würden also indexiert. Namentlich ausschließen.
SKIP_STATE_FILES = {
    "oauth_state.json",
    "ratelimit.json",
    "mapping_dismissed.json",
    "errors_ack.json",
    "audit.log",
    "errors.log",
    "errors.log.alt",
    "vault.enc",
    "vault.lock",
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
    ".conf",
    ".ini",
    ".sql",
    ".prisma",
    ".service",
    ".timer",
}
SPECIAL_NAMES = {"Dockerfile", "docker-compose.yml", "docker-compose.yaml", "Caddyfile", "Makefile"}
CHUNK, OVERLAP, MAX_FILE, MAX_CHUNKS = 800, 120, 200_000, 4000

# Zugangsdaten gehören nie in den Chunk-Index — sie kämen sonst wörtlich in
# FUNDSTELLEN-Antworten und ins LLM-Kontextfenster (CE-01/CE-02, P0-3).
# Gleiche Muster-Liste wie in extraction.py; Beispiel-/Vorlagen-Dateien sind erlaubt.
SECRET_GLOBS = (".env*", "*.key", "*.pem", "id_rsa*", "*secrets*", "*credentials*")
SECRET_EXAMPLES = (".example", ".sample", ".template", ".dist")
# Wartezeit auf eine fremde, laufende Index-Erstellung, bevor LockedError durchschlägt
# (die Aufrufer-Kette fällt dann wie gehabt auf die graphify-CLI zurück).
_INDEX_LOCK_TIMEOUT = 30


def _is_secret_file(name: str) -> bool:
    """True für Zugangsdaten-Dateien (.env, Schlüssel, *secrets*, *credentials* …).

    Beispiel-/Vorlagen-Dateien (.env.example, credentials.sample.yaml …) sind erlaubt.
    """
    low = name.lower()
    if low.endswith(SECRET_EXAMPLES):
        return False
    return any(fnmatch.fnmatch(low, pat) for pat in SECRET_GLOBS)


_model = None
_model_lock = threading.Lock()
_chunk_builds: set[str] = set()  # Projekte, deren Chunk-Index gerade im Hintergrund entsteht
_chunk_builds_lock = threading.Lock()  # macht Check-then-Add auf _chunk_builds atomar


def _get_model():
    global _model
    with _model_lock:
        if _model is None:
            from fastembed import TextEmbedding

            _model = TextEmbedding(MODEL)
        return _model


def _load_labels(project_dir: Path) -> dict:
    """Community-Benennungen aus .graphify_labels.json (ID -> Name). graphify legt die
    Namen dort ab, NICHT als community_label am Knoten (R11-2)."""
    try:
        return json.loads((project_dir / "graphify-out" / ".graphify_labels.json").read_text())
    except (OSError, json.JSONDecodeError, ValueError):
        return {}


def _node_text(n: dict, labels: dict | None = None) -> str:
    parts = [n.get("label") or n.get("id") or ""]
    # Community-Benennung in den Embedding-Text ziehen (R11-2): der Knoten trägt sie als
    # community_name; ältere Graphen nur als community-ID -> über .graphify_labels.json
    # auflösen. Vorher wurde community_label geprüft — das ist in own-Graphen IMMER leer,
    # weshalb der thematische Bezug (z. B. „Framework") beim Ranking fehlte.
    cname = n.get("community_name") or n.get("community_label")
    if not cname and labels and n.get("community") is not None:
        cname = labels.get(str(n.get("community")))
    if cname:
        parts.append(str(cname))
    if n.get("rationale"):
        parts.append(str(n["rationale"])[:600])
    if n.get("source_file"):
        parts.append(str(n["source_file"]))
    return " — ".join(p for p in parts if p)


def _save_npz_atomic(ziel: Path, **arrays) -> None:
    """npz über Temp-Datei + os.replace schreiben (Muster wie buildmeta.write_manifest).

    Leser sehen entweder den alten oder den neuen kompletten Stand — nie eine halbe
    Datei (BadZipFile/EOFError bei parallelen oder abgebrochenen Builds, CE-02).
    """
    ziel.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=ziel.parent, suffix=".tmp")
    try:
        with os.fdopen(fd, "wb") as f:
            np.savez_compressed(f, **arrays)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, ziel)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


@contextmanager
def _build_lock(project: str, verzeichnis: Path):
    """Genau ein Index-Build je Projekt — prozess- UND threadübergreifend.

    Nutzt die Haus-Sperre aus locks.py (flock im KMCP_LOCK_DIR, stirbt mit dem Prozess,
    dieselbe Ordnung wie Graph-Build, Purge und Nachtlauf); ohne locks.py ein flock auf
    eine Lock-Datei neben dem Ziel. Bei Timeout schlägt locks.LockedError durch — die
    Aufrufer-Kette fällt dann wie gehabt auf die graphify-CLI zurück.
    """
    try:
        import locks
    except ImportError:  # locks.py fehlt (Minimal-Installation) — einfacher Fallback
        locks = None
    if locks is not None:
        with locks.project_lock(project, timeout=_INDEX_LOCK_TIMEOUT):
            yield
        return
    import fcntl

    verzeichnis.mkdir(parents=True, exist_ok=True)
    fd = os.open(verzeichnis / f"semantic-index-{project}.lock", os.O_CREAT | os.O_RDWR, 0o600)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX)
        yield
    finally:
        try:
            fcntl.flock(fd, fcntl.LOCK_UN)
        finally:
            os.close(fd)


class _LegacyIndexError(Exception):
    """Index im Altformat (Pickle-Objekt-Arrays) — einmalig neu bauen statt crashen."""


def _read_index(index_file: Path) -> tuple[np.ndarray, np.ndarray]:
    """npz OHNE Pickle laden (graphify-out kommt per graphify-sync aus Quellrepos —
    eine präparierte npz mit Pickle-Payload wäre sonst Code-Ausführung auf dem Hub).

    Korrupte Dateien werfen weiterhin UnpicklingError (Aufrufer fallen auf die
    graphify-CLI zurück); das Altformat mit Objekt-Arrays meldet _LegacyIndexError,
    damit der Aufrufer den Index einmalig neu baut statt dauerhaft zu scheitern.
    """
    try:
        with np.load(index_file, allow_pickle=False) as data:
            vecs = np.asarray(data["vecs"], dtype=np.float32)
            ids = np.asarray(data["ids"], dtype=str)
    except ValueError as e:
        if "Object arrays" in str(e):
            raise _LegacyIndexError(str(e)) from e
        raise pickle.UnpicklingError(f"{index_file.name} unlesbar: {e}") from e
    except Exception as e:  # BadZipFile, EOFError, OSError, KeyError — alles „unlesbar"
        raise pickle.UnpicklingError(f"{index_file.name} unlesbar: {e}") from e
    return vecs, ids


def build_index(project_dir: Path, force: bool = False) -> int:
    """Embedding-Index neben graph.json ablegen. Rückgabe: Anzahl Knoten.

    Leerer oder fehlender Graph: 0 ohne Datei — query() behandelt das als leeres
    Ergebnis statt mit FileNotFoundError zu crashen. force=True baut auch bei frischem
    mtime neu (Altformat oder Modellwechsel mit anderer Embedding-Dimension).
    """
    graph_json = project_dir / "graphify-out" / "graph.json"
    if not graph_json.exists():
        return 0  # noch kein Graph gebaut — nichts zu indizieren, kein Fehler
    index_file = graph_json.parent / INDEX_NAME
    with _build_lock(project_dir.name, graph_json.parent):
        g = json.loads(graph_json.read_text())
        nodes = g.get("nodes", [])
        if not nodes:
            return 0
        if not force and index_file.exists() and index_file.stat().st_mtime >= graph_json.stat().st_mtime:
            return len(nodes)  # ein paralleler Build war schneller — Index ist schon frisch
        labels = _load_labels(project_dir)
        vecs = np.array(list(_get_model().embed([_node_text(n, labels) for n in nodes])), dtype=np.float32)
        vecs /= np.linalg.norm(vecs, axis=1, keepdims=True) + 1e-9
        # ids als Unicode-Array (dtype=str): lädt ohne Pickle (allow_pickle=False).
        ids = np.array([str(n.get("id") or n.get("label")) for n in nodes], dtype=str)
        _save_npz_atomic(index_file, vecs=vecs, ids=ids)
        # Generation festhalten: der Index gehört zu genau diesem Graph-Stand (Build-Vertrag).
        import buildmeta

        buildmeta.write_index_meta(project_dir)
        return len(nodes)


def query(project_dir: Path, question: str, budget: int = 1200, seeds: int = 6) -> str:
    """Traversal-Kontext im graphify-query-Format (Traversal-Kopf + NODE-Zeilen)."""
    graph_json = project_dir / "graphify-out" / "graph.json"
    index_file = graph_json.parent / INDEX_NAME
    g: dict = {}
    if graph_json.exists():  # fehlende graph.json = leerer Graph — kein FileNotFoundError
        g = json.loads(graph_json.read_text())
    nodes = g.get("nodes", []) or []

    seed_ids: list[str] = []
    if nodes:  # leerer/fehlender Graph → leeres Traversal-Ergebnis statt Crash
        if not index_file.exists() or index_file.stat().st_mtime < graph_json.stat().st_mtime:
            build_index(project_dir)  # fehlt oder veraltet — selbstheilend
        if index_file.exists():  # kann bei paralleler Löschung/Purge immer noch fehlen
            q = np.array(list(_get_model().embed([question])), dtype=np.float32)[0]
            q /= np.linalg.norm(q) + 1e-9
            try:
                vecs, ids = _read_index(index_file)
                dim_passt = vecs.ndim == 2 and vecs.shape[1] == q.shape[0]
            except _LegacyIndexError:
                dim_passt = False  # Altformat (Objekt-Arrays) — einmalig neu bauen
            if not dim_passt:
                # Modellwechsel/Altbestand: Embedding-Dimensionen passen nicht zusammen.
                # Nie „ValueError: matmul" durchreichen — Index automatisch neu bauen.
                build_index(project_dir, force=True)
                vecs, ids = _read_index(index_file)
                if vecs.ndim != 2 or vecs.shape[1] != q.shape[0]:
                    raise ValueError(
                        f"Semantik-Index {vecs.shape} passt nicht zum Modell ({q.shape[0]}d) — "
                        f"{index_file} löschen und build_index erneut rufen"
                    )
            top = np.argsort(-(vecs @ q))[:seeds]
            seed_ids = [str(ids[i]) for i in top]

    by_id = {n.get("id") or n.get("label"): n for n in nodes}
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

    wurzel = root.resolve()
    for p in sorted(root.rglob("*")):
        # SKIP_DIRS nur gegen die Teile UNTERHALB der Wurzel prüfen: ein Elternordner
        # namens data/build/logs darf nicht den ganzen Quellbaum wegmatchen (CE-01/CE-02).
        if any(part in SKIP_DIRS for part in p.relative_to(root).parts):
            continue
        if not (p.suffix.lower() in TEXT_SUFFIXES or p.name in SPECIAL_NAMES):
            continue
        if p.name in SKIP_STATE_FILES:
            continue  # Hub-Laufzeitzustand (oauth_state.json, audit.log …) ist kein Wissen
        if _is_secret_file(p.name):
            continue  # keine Zugangsdaten in Index, FUNDSTELLEN oder LLM-Kontext
        if p.is_symlink():
            continue  # Symlinks grundsätzlich nicht folgen
        try:
            # rglob folgt Verzeichnis-Symlinks — der aufgelöste Pfad muss unterhalb der
            # Wurzel bleiben, sonst landen fremde Dateien (/etc, ~/.ssh) im Index.
            if not p.resolve().is_relative_to(wurzel):
                continue
            if p.is_file() and 0 < p.stat().st_size <= MAX_FILE and os.access(p, os.R_OK):
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
    with _build_lock(project, CHUNK_DIR):
        # chunks als Unicode-Array (dtype=str): lädt ohne Pickle (allow_pickle=False).
        _save_npz_atomic(CHUNK_DIR / f"{project}.npz", vecs=vecs, chunks=np.array(chunks, dtype=str))
    return len(chunks)


def _chunk_index_background(project: str, source_dir: Path) -> None:
    """Fehlenden Chunk-Index nachziehen, ohne die laufende Anfrage zu blockieren."""
    with _chunk_builds_lock:  # Check-then-Add atomar — sonst startet derselbe Build doppelt
        if project in _chunk_builds:
            return
        _chunk_builds.add(project)

    def _run():
        try:
            build_chunk_index(project, source_dir)
        except Exception:  # noqa: BLE001 - Hintergrundaufbau darf nie stören
            pass
        finally:
            with _chunk_builds_lock:
                _chunk_builds.discard(project)

    threading.Thread(target=_run, daemon=True).start()


def _top_chunks(project: str, q_vec: np.ndarray, char_limit: int) -> list[str]:
    f = CHUNK_DIR / f"{project}.npz"
    if not f.exists():
        return []
    try:
        with np.load(f, allow_pickle=False) as data:
            vecs = np.asarray(data["vecs"], dtype=np.float32)
            chunks = np.asarray(data["chunks"], dtype=str)
    except Exception:  # korrupt oder Altformat (Pickle) — wegwerfen statt crashen
        try:
            f.unlink()  # hybrid_query legt ihn daraufhin im Hintergrund neu an
        except OSError:
            pass
        return []
    if vecs.ndim != 2 or vecs.shape[0] != len(chunks) or vecs.shape[1] != q_vec.shape[0]:
        # Modellwechsel (andere Embedding-Dimension) oder inkonsistenter Bestand —
        # nie „ValueError: matmul": Datei wegwerfen, der Hintergrund-Build heilt nach.
        try:
            f.unlink()
        except OSError:
            pass
        return []
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
