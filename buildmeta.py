"""Graph-Build-Vertrag: ein build-manifest.json je Graph-Generation.

Warum: Am 2026-07-14 überschrieben zwei Pipelines abwechselnd dieselbe graph.json,
und Report, Viewer und Semantik-Index zeigten zeitweise verschiedene Generationen
(hub-audit Run 6). Das Manifest bindet alle Artefakte einer Generation aneinander:

    graphify-out/build-manifest.json   — Build-ID, Quelle, Zählungen, Artefakt-Hashes
    graphify-out/semantic-index.meta.json — welcher Generation der Index angehört

`verify()` prüft die Invarianten maschinell (GESAMTAUFTRAG Kap. 7): Ein Artefakt,
dessen Hash nicht zum Manifest passt, oder ein Index fremder Generation ist ein
Mismatch. Projekte ohne Manifest sind »legacy« (vor Einführung des Vertrags gebaut).

CLI:  python buildmeta.py write  <projekt-dir>
      python buildmeta.py verify <projekt-dir>
"""

from __future__ import annotations

import datetime
import hashlib
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

BUILD_MANIFEST = "build-manifest.json"
INDEX_META = "semantic-index.meta.json"

# Artefakte, die (sofern vorhanden) zur Generation gehören und gehasht werden.
_ARTIFACTS = ("graph.json", "GRAPH_REPORT.md", "graph.html", ".extraction-cache.json")


def _sha256_16(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(65536), b""):
            h.update(block)
    return h.hexdigest()[:16]


def _counts(graph: dict) -> dict:
    nodes = graph.get("nodes", [])
    edges = graph.get("links", graph.get("edges", []))
    communities = {n.get("community") for n in nodes if n.get("community") is not None}
    return {"nodes": len(nodes), "edges": len(edges), "communities": len(communities)}


def _source_commit(project_dir: Path) -> str | None:
    try:
        proc = subprocess.run(  # noqa: S603 - fixed binary, validated path
            ["git", "-C", str(project_dir), "rev-parse", "HEAD"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        return proc.stdout.strip() or None if proc.returncode == 0 else None
    except Exception:  # noqa: BLE001 - Metadatum, best effort: darf nie einen Build kippen
        return None


def _graphify_version() -> str | None:
    binary = os.environ.get("GRAPHIFY_BIN") or str(Path.home() / ".local" / "bin" / "graphify")
    try:
        proc = subprocess.run(  # noqa: S603 - fixed binary
            [binary, "--version"], capture_output=True, text=True, timeout=10
        )
        return proc.stdout.strip() or None if proc.returncode == 0 else None
    except Exception:  # noqa: BLE001 - Metadatum, best effort: darf nie einen Build kippen
        return None


def _mapping_config_hash() -> str | None:
    try:
        import config

        blob = json.dumps(config.load().get("mapping", {}), sort_keys=True, ensure_ascii=False)
        return hashlib.sha256(blob.encode()).hexdigest()[:16]
    except Exception:  # noqa: BLE001 - Manifest bleibt auch ohne Config-Hash gültig
        return None


def write_manifest(project_dir: Path) -> dict:
    """Schreibt build-manifest.json für den aktuellen Stand von graphify-out (atomar)."""
    project_dir = Path(project_dir)
    out = project_dir / "graphify-out"
    graph_file = out / "graph.json"
    graph = json.loads(graph_file.read_text(encoding="utf-8"))

    graph_hash = _sha256_16(graph_file)
    now = datetime.datetime.now(datetime.UTC)
    ignore = project_dir / ".graphifyignore"
    manifest = {
        "schema_version": "1.0",
        "build_id": f"g-{now.strftime('%Y%m%dT%H%M%SZ')}-{graph_hash[:8]}",
        "created_at": now.isoformat(timespec="seconds"),
        "source_commit": _source_commit(project_dir),
        "graphify_version": _graphify_version(),
        "mapping_config_sha256_16": _mapping_config_hash(),
        "ignore_sha256_16": _sha256_16(ignore) if ignore.is_file() else None,
        "counts": _counts(graph),
        "artifacts": {name: _sha256_16(out / name) for name in _ARTIFACTS if (out / name).is_file()},
    }
    fd, tmp = tempfile.mkstemp(dir=out)
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2, ensure_ascii=False)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, out / BUILD_MANIFEST)
    return manifest


def write_index_meta(project_dir: Path) -> dict | None:
    """Bindet den Semantik-Index an die aktuelle Generation (von semantic.build_index gerufen)."""
    out = Path(project_dir) / "graphify-out"
    mf = out / BUILD_MANIFEST
    if not mf.is_file():
        return None  # Legacy-Graph ohne Manifest — Index bleibt ungebunden
    manifest = json.loads(mf.read_text(encoding="utf-8"))
    meta = {
        "build_id": manifest["build_id"],
        "indexed_at": datetime.datetime.now(datetime.UTC).isoformat(timespec="seconds"),
    }
    fd, tmp = tempfile.mkstemp(dir=out)
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        json.dump(meta, f, indent=2)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, out / INDEX_META)
    return meta


SNAPSHOT_DIR = ".prev-generation"
_SNAPSHOT_FILES = (*_ARTIFACTS, BUILD_MANIFEST, INDEX_META, "semantic-index.npz")


def validate_graph(project_dir: Path) -> list[str]:
    """Invarianten aus GESAMTAUFTRAG Kap. 7 — Rückgabe: Liste der Probleme (leer = gültig)."""
    out = Path(project_dir) / "graphify-out"
    try:
        g = json.loads((out / "graph.json").read_text(encoding="utf-8"))
    except FileNotFoundError:
        return ["graph.json fehlt"]
    except (json.JSONDecodeError, UnicodeDecodeError) as e:
        return [f"graph.json ist kein gültiges JSON ({type(e).__name__})"]
    probleme: list[str] = []
    nodes = g.get("nodes")
    if not isinstance(nodes, list):
        return ["nodes ist keine Liste"]
    ids: set[str] = set()
    for n in nodes:
        nid = n.get("id")
        if nid in ids:
            probleme.append(f"Knoten-ID doppelt: {nid!r}")
        if nid is not None:
            ids.add(nid)
    for e in g.get("links", g.get("edges", [])):
        for ende in (e.get("source"), e.get("target")):
            if ende not in ids:
                probleme.append(f"Kante referenziert fehlenden Knoten: {ende!r}")
    return probleme


def snapshot_generation(project_dir: Path) -> bool:
    """Sichert die aktuelle Generation nach graphify-out/.prev-generation/ (vor einem Build)."""
    import shutil

    out = Path(project_dir) / "graphify-out"
    if not (out / "graph.json").is_file():
        return False  # nichts zu sichern (Erstbuild)
    snap = out / SNAPSHOT_DIR
    tmp = out / (SNAPSHOT_DIR + ".tmp")
    shutil.rmtree(tmp, ignore_errors=True)
    tmp.mkdir()
    for name in _SNAPSHOT_FILES:
        f = out / name
        if f.is_file():
            shutil.copy2(f, tmp / name)
    shutil.rmtree(snap, ignore_errors=True)
    os.replace(tmp, snap)
    return True


def restore_generation(project_dir: Path) -> bool:
    """Stellt die zuletzt gesicherte Generation wieder her (nach einem fehlgeschlagenen Build)."""
    import shutil

    out = Path(project_dir) / "graphify-out"
    snap = out / SNAPSHOT_DIR
    if not (snap / "graph.json").is_file():
        return False
    for name in _SNAPSHOT_FILES:
        s = snap / name
        ziel = out / name
        if s.is_file():
            shutil.copy2(s, out / (name + ".restore-tmp"))
            os.replace(out / (name + ".restore-tmp"), ziel)
        elif ziel.is_file():
            ziel.unlink()  # gehörte nicht zur alten Generation
    return True


def finalize(project_dir: Path) -> dict:
    """Abnahme-Gate: Nur eine GÜLTIGE Generation bekommt ein Manifest (sonst ValueError)."""
    probleme = validate_graph(project_dir)
    if probleme:
        raise ValueError("Generation ungültig: " + "; ".join(probleme[:5]))
    return write_manifest(project_dir)


def verify(project_dir: Path) -> dict:
    """Prüft die Generationskonsistenz. status: ok | legacy | mismatch."""
    out = Path(project_dir) / "graphify-out"
    mf = out / BUILD_MANIFEST
    if not mf.is_file():
        return {"status": "legacy", "detail": "kein build-manifest.json (vor Vertragseinführung gebaut)"}
    try:
        manifest = json.loads(mf.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError) as e:
        return {"status": "mismatch", "detail": f"Manifest nicht lesbar ({type(e).__name__})"}

    probleme = []
    for name, erwartet in manifest.get("artifacts", {}).items():
        f = out / name
        if not f.is_file():
            probleme.append(f"{name} fehlt")
        elif _sha256_16(f) != erwartet:
            probleme.append(f"{name} gehört nicht zur Generation {manifest['build_id']}")

    graph_file = out / "graph.json"
    if graph_file.is_file() and not any("graph.json" in p for p in probleme):
        counts = _counts(json.loads(graph_file.read_text(encoding="utf-8")))
        if counts != manifest.get("counts"):
            probleme.append(f"Zählungen weichen ab: {counts} != {manifest.get('counts')}")

    im = out / INDEX_META
    if (out / "semantic-index.npz").is_file() and im.is_file():
        try:
            meta = json.loads(im.read_text(encoding="utf-8"))
            if meta.get("build_id") != manifest["build_id"]:
                probleme.append(
                    f"Semantik-Index gehört zu Generation {meta.get('build_id')}, Graph zu {manifest['build_id']}"
                )
        except (json.JSONDecodeError, UnicodeDecodeError):
            probleme.append("Index-Meta nicht lesbar")

    if probleme:
        return {"status": "mismatch", "detail": "; ".join(probleme)}
    return {"status": "ok", "detail": f"Generation {manifest['build_id']} konsistent"}


def main() -> int:
    if len(sys.argv) != 3 or sys.argv[1] not in ("write", "verify", "snapshot", "restore", "finalize"):
        print(__doc__)
        return 64
    cmd, project = sys.argv[1], Path(sys.argv[2]).expanduser()
    if cmd == "write":
        m = write_manifest(project)
        print(f"build-manifest.json: {m['build_id']} ({m['counts']})")
        return 0
    if cmd == "snapshot":
        print(
            "Snapshot: " + ("gesichert" if snapshot_generation(project) else "nichts zu sichern (Erstbuild)")
        )
        return 0
    if cmd == "restore":
        if restore_generation(project):
            print("vorherige Generation wiederhergestellt")
            return 0
        print("kein Snapshot vorhanden — nichts wiederhergestellt")
        return 66
    if cmd == "finalize":
        try:
            m = finalize(project)
        except ValueError as e:
            print(f"ABGELEHNT: {e}")
            return 65
        print(f"Generation abgenommen: {m['build_id']} ({m['counts']})")
        return 0
    v = verify(project)
    print(f"{v['status']}: {v['detail']}")
    return 0 if v["status"] == "ok" else 65 if v["status"] == "mismatch" else 66


if __name__ == "__main__":
    raise SystemExit(main())
