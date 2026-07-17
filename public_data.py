"""Öffentlicher Datenvertrag — erzeugt eine sanitizierte, aggregierte ``public-data.json``
für die öffentliche Website (hub.it-handwerk-stuttgart.de).

**Sicherheitsgrenze (PUBLIC_DATA_POLICY):** Whitelist-Prinzip. Es werden AUSSCHLIESSLICH die im
Schema (``public-data.schema.json``) definierten, aggregierten Zahlen aufgenommen — nie Pfade,
Projektnamen, Secrets, IPs/Ports, Session-/Token-Werte, volle Commit-Hashes.

Zwei unabhängige Schutzschichten:
  1. **Schema-Validierung** (jsonschema, ``additionalProperties: false``) — strukturell kann nur
     Erlaubtes hinein.
  2. **Leak-Scanner** (``_leak_scan``) — verteidigend: durchsucht die serialisierte Ausgabe nach
     verbotenen Mustern (absolute Pfade, nicht freigegebene Projektnamen, Secret-Schlüsselwörter,
     E-Mail, IP:Port, 40-stelliger Hash). Ein Treffer verhindert das Schreiben.

Bei fehlenden/kaputten Quellen bricht der Generator SICHER ab (kein Teil-/Nullwert wird geschrieben);
die Website zeigt dann den letzten gültigen Stand + „Datenstand veraltet" (Stale-Verhalten, Konsument).
"""

from __future__ import annotations

import hashlib
import json
import math
import os
import re
import time
from pathlib import Path

import jsonschema

SCHEMA_PATH = Path(__file__).parent / "public-data.schema.json"
STALE_AFTER_DAYS = 14

# Nicht freigegebene Projektnamen (PUBLIC_DATA_POLICY: Blacklist schlägt Whitelist).
# Defense-in-depth: die Ausgabe enthält ohnehin KEINE Projektnamen, aber falls je einer
# durchrutschte, fängt ihn der Scanner.
NICHT_FREIGEGEBEN = (
    "tolga",
    "hub2",
    "cricket-brain",
    "specter",
    "belkis-aslani-besitzer",
    "app-marktluecken",
    "evolution-engine",
    "lumo-own",
)

# Verbotene Muster (Blacklist). Jeder Treffer in der serialisierten Ausgabe stoppt die Freigabe.
_LEAK_PATTERNS = [
    (re.compile(r"/(home|root|etc|opt|var|usr|tmp)/"), "absoluter Pfad"),
    (re.compile(r"\b\d{1,3}(\.\d{1,3}){3}\b"), "IP-Adresse"),
    # host:port bzw. ip:port — die IP fängt bereits das IP-Muster; hier nur Host:Port mit
    # Punkt/Klammer im Host (localhost/[::1]/domain), damit ISO-Zeitstempel (T03:33) NICHT triggern.
    (re.compile(r"[A-Za-z0-9\]][A-Za-z0-9.\-\]]*[.\]]:\d{2,5}\b"), "Host:Port"),
    (re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}"), "E-Mail"),
    (re.compile(r"\b[0-9a-f]{40}\b"), "voller 40-stelliger Hash (nur 7 erlaubt)"),
    (re.compile(r"kmcpr?_[A-Za-z0-9]"), "Token-Präfix (kmcp_/kmcpr_)"),
    (
        re.compile(
            r"(?i)\b(secret|token|passwo?rd|vault[_-]?key|recovery|bearer|session[_-]?id|oauth|__2fa__)\b"
        ),
        "Secret-Schlüsselwort",
    ),
    (re.compile("|".join(re.escape(p) for p in NICHT_FREIGEGEBEN), re.I), "nicht freigegebener Projektname"),
]


class PublicDataLeak(RuntimeError):
    """Der Leak-Scanner hat ein verbotenes Muster in der Ausgabe gefunden — NICHT veröffentlichen."""


class PublicDataInvalid(RuntimeError):
    """Die Daten verletzen das öffentliche Schema."""


class PublicSourceError(RuntimeError):
    """Eine Quelle fehlt oder ist unlesbar — sicherer Abbruch, keine Teil-/Nullwerte."""


def _leak_scan(text: str) -> None:
    for rx, was in _LEAK_PATTERNS:
        m = rx.search(text)
        if m:
            raise PublicDataLeak(f"Verbotenes Muster in public-data ({was}): {m.group(0)!r}")


def _validate(doc: dict) -> None:
    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    try:
        jsonschema.validate(doc, schema)
    except jsonschema.ValidationError as e:
        raise PublicDataInvalid(
            f"Schema-Verstoß: {e.message} (Pfad: {'/'.join(map(str, e.absolute_path))})"
        ) from e


def _serialisieren(doc: dict, **kwargs: object) -> str:
    """JSON ohne NaN/Infinity — solche Werte bestehen die Schema-Prüfung (NaN-Vergleiche
    sind immer False), erzeugen aber als ``NaN``-Literal ungültiges JSON, an dem das
    JSON.parse der Website scheitert. Daher wie ein Schema-Verstoß behandeln."""
    try:
        return json.dumps(doc, ensure_ascii=False, allow_nan=False, **kwargs)
    except ValueError as e:
        raise PublicDataInvalid(f"Nicht darstellbarer Zahlenwert (NaN/Infinity): {e}") from e


def build(
    tests: dict,
    graph: dict,
    benchmark: dict,
    audit: dict,
    commit: str | None = None,
    now: float | None = None,
) -> dict:
    """Aus bereits gesammelten (aggregierten) Werten das öffentliche Dokument bauen,
    validieren und leak-scannen. Wirft bei Schema-Verstoß oder Leak — schreibt nichts."""
    now = now if now is not None else time.time()
    stamp = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime(now))
    payload = {"tests": tests, "graph": graph, "benchmark": benchmark, "audit": audit}
    digest = hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()[:8]
    doc = {
        "schema_version": "1.0",
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(now)),
        "build_id": f"pd-{stamp}-{digest}",
        "stale_after_days": STALE_AFTER_DAYS,
        **payload,
    }
    if commit:
        c = str(commit).strip()[:7]
        if re.fullmatch(r"[0-9a-f]{7}", c):
            doc["release"] = {"commit": c}
    _validate(doc)
    _leak_scan(_serialisieren(doc))
    return doc


def write(doc: dict, out_dir: Path) -> Path:
    """public-data.json + Manifest (Hash) atomar schreiben.

    Letzte Kontrollstelle vor dem Schreiben: erneute Schema-Validierung (Fremdfelder
    werden abgelehnt) und Leak-Scan — ein Dokument, das build() umgangen hat, darf
    nicht schwächer geprüft werden als eines aus build()."""
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    _validate(doc)  # Schema-Revalidierung: nur whiteliste Felder/Werte dürfen raus
    body = _serialisieren(doc, indent=2)
    _leak_scan(body)  # letzte Kontrolle unmittelbar vor dem Schreiben
    _write_atomar(out_dir / "public-data.json", body)
    manifest = {
        "build_id": doc["build_id"],
        "generated_at": doc["generated_at"],
        "sha256": hashlib.sha256(body.encode()).hexdigest(),
        "schema": "public-data.schema.json",
    }
    _write_atomar(out_dir / "public-data.manifest.json", json.dumps(manifest, indent=2))
    return out_dir / "public-data.json"


def _write_atomar(path: Path, text: str) -> None:
    import tempfile

    fd, tmp = tempfile.mkstemp(dir=str(path.parent), prefix=".pd-", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(text)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, path)
    except BaseException:
        Path(tmp).unlink(missing_ok=True)
        raise


# ---------------------------------------------------------------------------
# Sammler aus realen Quellen (env-überschreibbare Pfade). Aggregiert/anonymisiert.
# ---------------------------------------------------------------------------
def gather_benchmark(bench_dir: Path | None = None) -> dict:
    """Neuester hybrid- + graphify-Lauf (graphify-bench). Nur Trefferquoten/Zählwerte, keine Fragen."""
    import glob

    bd = Path(bench_dir or os.environ.get("GRAPHIFY_BENCH_DIR", str(Path.home() / "graphify-bench")))
    res = bd / "results"

    def newest(pattern: str) -> dict:
        files = sorted(glob.glob(str(res / pattern)))
        if not files:
            raise PublicSourceError(f"Kein Benchmark-Lauf für {pattern!r} in {res}")
        return json.loads(Path(files[-1]).read_text(encoding="utf-8"))

    def hit_rate(totals: dict, engine: str, budget: str) -> float:
        # Defensiv lesen: ein Lauf mit anderen/fehlenden Budgets (z. B. nur 800) darf
        # nicht mit KeyError abbrechen, sondern bricht als dokumentierter Quellfehler
        # sicher ab. NaN/Infinity wird ebenfalls abgelehnt (ungültiges JSON).
        eintrag = totals.get(budget)
        wert = eintrag.get("hit_rate") if isinstance(eintrag, dict) else None
        if not isinstance(wert, (int, float)) or isinstance(wert, bool) or not math.isfinite(wert):
            raise PublicSourceError(
                f"Benchmark-Lauf ({engine}) ohne verwertbare Trefferquote für Budget {budget} — Abbruch."
            )
        return round(float(wert), 3)

    hy = newest("*hybrid*.json")
    # Kein Jahr im Muster: mit "2026-*graphify*.json" fände der Generator ab dem
    # Jahreswechsel keinen Lauf mehr und bliebe dauerhaft auf dem alten Stand (stale).
    gf = newest("*graphify*.json")
    ht, gt = hy.get("totals", {}), gf.get("totals", {})
    # Fragen/Projekte aus dem hybrid-Lauf (der vollständige Gold-Satz)
    projects = hy.get("projects", {})
    n_proj = len(projects) if isinstance(projects, (dict, list)) else 0
    n_q = int(ht.get("1200", {}).get("hits", "0/0").split("/")[1])
    measured = str(hy.get("timestamp", ""))[:10] or time.strftime("%Y-%m-%d")
    return {
        "measured_at": measured,
        "questions": n_q,
        "projects": n_proj,
        "budgets": sorted(int(b) for b in ht if b.isdigit()) or [400, 1200],
        "engines": {
            "hybrid": {
                "hit_rate_400": hit_rate(ht, "hybrid", "400"),
                "hit_rate_1200": hit_rate(ht, "hybrid", "1200"),
            },
            "graphify": {
                "hit_rate_400": hit_rate(gt, "graphify", "400"),
                "hit_rate_1200": hit_rate(gt, "graphify", "1200"),
            },
        },
    }


def gather_graph(knowledge_root: Path | None = None, projekte: list | None = None) -> dict:
    """Aggregat über die gemappten Hub-Projekte — NUR Summen, keine Namen."""
    root = Path(knowledge_root or os.environ.get("KNOWLEDGE_ROOT", str(Path.home() / "graphify-knowledge")))
    if projekte is None:
        import config

        projekte = [p.name for p in config.projects()]
    n = e = c = ok = 0
    for name in projekte:
        f = root / name / "graphify-out" / "graph.json"
        if not f.is_file():
            cand = [x for x in root.iterdir() if x.name.lower() == str(name).lower()]
            f = (cand[0] / "graphify-out" / "graph.json") if cand else f
        if not f.is_file():
            continue
        g = json.loads(f.read_text(encoding="utf-8"))
        ns = g.get("nodes", [])
        n += len(ns)
        e += len(g.get("links", g.get("edges", [])))
        c += len({x.get("community") for x in ns if x.get("community") is not None})
        ok += 1
    if ok == 0:
        raise PublicSourceError("Kein einziger Hub-Graph lesbar — Abbruch (keine Nullwerte).")
    return {"projects": ok, "nodes": n, "edges": e, "communities": c}
