"""Eigene Graph-Extraktion — der Standard-Extraktor des Hubs (statt graphify extract).

Warum eigen: volle Datei-Coverage (Compose, Configs, Docs, .env-Beispiele — nicht nur
Code-AST) und faktenreiche rationale-Texte (Ports, Pfade, Hosts wörtlich). Benchmark:
Lumo-Stack 3/3 beantwortete Gold-Fragen statt 0/3, 76 statt 47 Knoten (2026-07-14).

Inkrementell: ein Datei-Hash-Cache (graphify-out/.extraction-cache.json) sorgt dafür,
dass unveränderte Dateien keinen einzigen LLM-Aufruf kosten — wie beim alten Extraktor
bleibt der Nacht-Lauf damit günstig. Gelöschte Dateien verschwinden aus dem Graphen.

Arbeitsteilung: dieses Modul liefert Knoten/Kanten/Fakten (graph.json). Clustering,
Community-Report und der interaktive Viewer (graph.html) kommen weiterhin von
`graphify cluster-only` + `label --missing-only` — beide arbeiten auf unserer
graph.json und erhalten die rationale-Felder (getestet).

CLI (läuft im Hub-venv, Key kommt aus dem Vault, nie auf Platte):
    .venv/bin/python extraction.py <projekt-pfad>
Exit-Code != 0 → der Aufrufer (nightly-map.sh) fällt auf `graphify extract` zurück.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import sys
import time
from pathlib import Path

CACHE_NAME = ".extraction-cache.json"
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
    "logs",
    "data",
}
# Minifizierter/generierter Code trägt kein Architekturwissen — Elementa wurde damit
# geflutet (GESAMTAUFTRAG 3.4, hub-audit Run 11).
SKIP_NAME_PATTERNS = ("*.min.js", "*.min.css", "*.min.mjs", "*.map", "*.bundle.js", "*.chunk.js")
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
    ".example",
    ".sample",
    ".service",
    ".timer",
}
SPECIAL_NAMES = {"Dockerfile", "docker-compose.yml", "docker-compose.yaml", "Caddyfile", "Makefile"}
MAX_CHARS = 7000  # pro LLM-Aufruf
MAX_FILE = 300_000

SYSTEM_PROMPT = """Du extrahierst einen Knowledge-Graphen aus einer Projektdatei.
Antworte NUR mit striktem JSON, ohne Markdown:
{"entities": [{"label": "...", "type": "service|code|config|concept|doc",
               "rationale": "1-2 Sätze mit den KONKRETEN Fakten (Ports, Pfade, Hosts, Versionen, Zwecke)"}],
 "relations": [{"source": "...", "target": "...", "relation": "uses|contains|configures|depends_on|documents|exposes"}]}

Regeln:
- Fakten in die rationale: Portnummern, Dateipfade, Domains, Container-Namen, Versionen wörtlich übernehmen.
- 3-12 Entities pro Datei, die WICHTIGEN Konzepte (Dienste, Komponenten, Konfigurationen), nicht jede Funktion.
- source/target in relations müssen Labels aus entities dieser Antwort sein (oder der Dateiname).
- Sprache der rationale: Deutsch."""


def _ignore_patterns(root: Path) -> list[str]:
    """Muster aus der .graphifyignore des Projekts — dieselbe Datei, die die UI pflegt
    und die graphify liest. Vorher galt sie NUR für graphify: in der Oberfläche
    ignorierte Dateien wurden von der eigenen Extraktion trotzdem gemappt (Run 11)."""
    f = root / ".graphifyignore"
    if not f.is_file():
        return []
    muster = []
    try:
        for zeile in f.read_text(encoding="utf-8", errors="ignore").splitlines():
            zeile = zeile.strip()
            if zeile and not zeile.startswith("#"):
                muster.append(zeile)
    except OSError:
        return []
    return muster


def _ignoriert(rel: str, name: str, muster: list[str]) -> bool:
    from fnmatch import fnmatch

    for pat in muster:
        if pat.endswith("/"):  # Verzeichnis-Muster: trifft jeden Pfadteil
            if pat.rstrip("/") in rel.split("/"):
                return True
        elif fnmatch(name, pat) or fnmatch(rel, pat):
            return True
    return False


def iter_files(root: Path):
    from fnmatch import fnmatch

    muster = _ignore_patterns(root)
    for p in sorted(root.rglob("*")):
        if any(part in SKIP_DIRS for part in p.parts):
            continue
        if not p.is_file():
            continue
        if any(fnmatch(p.name, pat) for pat in SKIP_NAME_PATTERNS):
            continue
        rel = str(p.relative_to(root))
        if muster and _ignoriert(rel, p.name, muster):
            continue
        if p.suffix.lower() in TEXT_SUFFIXES or p.name in SPECIAL_NAMES or p.name.startswith(".env"):
            try:
                if 0 < p.stat().st_size <= MAX_FILE and os.access(p, os.R_OK):
                    yield p
            except OSError:
                continue


def slug(label: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", label.lower()).strip("_")[:80] or "node"


def _parse_json(raw: str) -> dict | None:
    m = re.search(r"\{.*\}", raw, re.DOTALL)
    if not m:
        return None
    return json.loads(re.sub(r",\s*([}\]])", r"\1", m.group(0)))  # tolerante Kommas


def extract_file(ask, backend: dict, model: str, key: str, rel: str, text: str) -> dict | None:
    """Eine Datei durch das LLM — ein Retry, dann aufgeben (Datei wird übersprungen)."""
    user = f"Datei: {rel}\n\n{text[:MAX_CHARS]}"
    for attempt in (1, 2):
        try:
            return _parse_json(ask(backend, model, key, SYSTEM_PROMPT, user, limit=3000))
        except Exception as e:  # noqa: BLE001 - eine kaputte Datei stoppt nicht den Lauf
            if attempt == 2:
                print(f"  WARN {rel}: {e}", file=sys.stderr)
    return None


def build_graph(cache: dict) -> dict:
    """Cache (rel → entities/relations) zu einer graphify-kompatiblen graph.json mergen."""
    nodes: dict[str, dict] = {}
    links: list[dict] = []
    for rel, entry in sorted(cache.items()):
        label_to_id: dict[str, str] = {}
        for ent in entry.get("entities", []):
            label = str(ent.get("label", "")).strip()
            if not label:
                continue
            nid = slug(label)
            label_to_id[label] = nid
            rationale = str(ent.get("rationale", ""))
            if nid in nodes:
                if len(rationale) > len(nodes[nid].get("rationale", "")):
                    nodes[nid]["rationale"] = rationale
            else:
                nodes[nid] = {
                    "id": nid,
                    "label": label,
                    "norm_label": label.lower(),
                    "rationale": rationale,
                    "file_type": str(ent.get("type", "concept")),
                    "source_file": rel,
                    "source_location": "L1",
                    "_origin": "hub-extract",
                }
        # Eigener ID-Namensraum für Datei-Knoten: graphifys Fuzzy-Dedup verschmolz
        # slug(pfad) (z. B. engine_py) mit ähnlichen Entitäts-IDs und verweigerte dann
        # das Schreiben der geclusterten graph.json — Graphen blieben ohne Communities
        # neben Reports einer fremden Generation (hub-audit Run 10, asto-finance).
        fid = "file__" + slug(rel)
        if fid not in nodes:
            nodes[fid] = {
                "id": fid,
                "label": rel,
                "norm_label": rel.lower(),
                "rationale": "",
                "file_type": "file",
                "source_file": rel,
                "source_location": "L1",
                "_origin": "hub-extract",
            }
        label_to_id[rel] = fid
        linked: set[str] = set()
        for r in entry.get("relations", []):
            s = label_to_id.get(str(r.get("source", "")))
            t = label_to_id.get(str(r.get("target", "")))
            if s and t and s != t:
                links.append(
                    {
                        "source": s,
                        "target": t,
                        "relation": str(r.get("relation", "related_to")),
                        "confidence": "EXTRACTED",
                        "weight": 1.0,
                        "confidence_score": 1.0,
                        "source_file": rel,
                        "source_location": "L1",
                    }
                )
                linked.update((s, t))
        for nid in label_to_id.values():
            if nid != fid and nid not in linked:
                links.append(
                    {
                        "source": fid,
                        "target": nid,
                        "relation": "contains",
                        "confidence": "EXTRACTED",
                        "weight": 1.0,
                        "confidence_score": 1.0,
                        "source_file": rel,
                        "source_location": "L1",
                    }
                )
    return {
        "directed": True,
        "multigraph": False,
        "graph": {"engine": "hub-extract"},
        "nodes": list(nodes.values()),
        "links": links,
        "hyperedges": [],
    }


def extract_project(
    root: Path, ask=None, backend: dict | None = None, model: str = "", key: str = ""
) -> dict:
    """Inkrementelle Extraktion. Rückgabe: Statistik (files, changed, nodes, edges)."""
    out_dir = root / "graphify-out"
    out_dir.mkdir(exist_ok=True)
    cache_file = out_dir / CACHE_NAME
    try:
        cache = json.loads(cache_file.read_text())
    except Exception:  # noqa: BLE001 - kaputter Cache = voller Neuaufbau
        cache = {}

    seen, changed = set(), 0
    for f in iter_files(root):
        rel = str(f.relative_to(root))
        seen.add(rel)
        try:
            text = f.read_text(errors="ignore")
        except OSError:
            continue
        h = hashlib.sha256(text.encode()).hexdigest()
        if cache.get(rel, {}).get("hash") == h:
            continue  # unverändert → kein LLM-Aufruf
        data = extract_file(ask, backend, model, key, rel, text)
        if data is None:
            # Datei nicht extrahierbar: alter Stand bleibt, statt Wissen zu verlieren
            if rel in cache:
                cache[rel]["hash"] = h
            continue
        changed += 1
        cache[rel] = {
            "hash": h,
            "entities": data.get("entities", []),
            "relations": data.get("relations", []),
        }
    # Gelöschte Dateien fallen aus dem Graphen
    for rel in [r for r in cache if r not in seen]:
        del cache[rel]

    graph = build_graph(cache)
    (out_dir / "graph.json").write_text(json.dumps(graph, ensure_ascii=False, indent=1))
    cache_file.write_text(json.dumps(cache, ensure_ascii=False))
    return {
        "files": len(seen),
        "changed": changed,
        "nodes": len(graph["nodes"]),
        "edges": len(graph["links"]),
    }


def main() -> int:
    if len(sys.argv) < 2:
        print("Usage: extraction.py <projekt-pfad>", file=sys.stderr)
        return 2
    root = Path(sys.argv[1]).expanduser().resolve()
    if not root.is_dir():
        print(f"FEHLER: {root} ist kein Verzeichnis", file=sys.stderr)
        return 2

    sys.path.insert(0, str(Path(__file__).parent))
    import config
    import llm
    import vault

    cfg = config.load()
    _, backend = config.active_backend(cfg)
    model = cfg["mapping"].get("model", "gpt-4.1-mini")
    secret = backend.get("secret")
    key = vault.secret_get(secret, client="hub-extract") if secret else ""
    if secret and not key:
        print("FEHLER: kein LLM-Key im Vault", file=sys.stderr)
        return 1

    t0 = time.time()
    stats = extract_project(root, ask=llm.ask, backend=backend, model=model, key=key)
    print(
        f"[hub-extract] {root.name}: {stats['files']} Dateien, {stats['changed']} neu extrahiert, "
        f"{stats['nodes']} Knoten, {stats['edges']} Kanten in {time.time() - t0:.0f}s"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
