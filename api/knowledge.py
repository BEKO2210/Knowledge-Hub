"""Graphen, Berichte und die Frage-Antwort-Funktion."""

from __future__ import annotations

import asyncio
import hashlib
import json
import re
import subprocess
import time
from pathlib import Path

from starlette.requests import Request
from starlette.responses import JSONResponse

import config
import vault
from api.common import DATA_DIR, GRAPHIFY_BIN, KNOWLEDGE_ROOT, _projects
from api.i18n import T


async def projects(request: Request) -> JSONResponse:
    out = []
    for name in _projects():
        g = json.loads((KNOWLEDGE_ROOT / name / "graphify-out" / "graph.json").read_text())
        nodes = g.get("nodes", [])
        out.append(
            {
                "project": name,
                "nodes": len(nodes),
                "edges": len(g.get("links", g.get("edges", []))),
                "communities": len({n.get("community") for n in nodes if n.get("community") is not None}),
            }
        )
    return JSONResponse(out)


async def graph(request: Request) -> JSONResponse:
    name = request.path_params["project"]
    if name not in _projects():
        return JSONResponse({"error": "unknown project"}, status_code=404)
    limit = int(request.query_params.get("limit", 2000))
    g = json.loads((KNOWLEDGE_ROOT / name / "graphify-out" / "graph.json").read_text())
    nodes = g.get("nodes", [])
    links = g.get("links", g.get("edges", []))

    degree: dict[str, int] = {}
    for link in links:
        degree[link["source"]] = degree.get(link["source"], 0) + 1
        degree[link["target"]] = degree.get(link["target"], 0) + 1

    ranked = sorted(nodes, key=lambda n: degree.get(n["id"], 0), reverse=True)
    keep_nodes = ranked if limit <= 0 else ranked[:limit]  # limit<=0 = alle Knoten, kein Deckel
    keep_ids = {n["id"] for n in keep_nodes}
    out_nodes = [
        {
            "id": n["id"],
            "label": n.get("label", n["id"]),
            "community": n.get("community"),
            # Der von der KI vergebene Bereichsname. Ohne ihn zeigt die Oberfläche
            # nur „Bereich 7" — die Benennung wäre unsichtbar und damit sinnlos.
            "community_name": n.get("community_name"),
            "file": n.get("source_file"),
            "degree": degree.get(n["id"], 0),
        }
        for n in keep_nodes
    ]
    out_links = [
        {"source": link["source"], "target": link["target"], "relation": link.get("relation", "")}
        for link in links
        if link["source"] in keep_ids and link["target"] in keep_ids
    ]
    return JSONResponse(
        {"nodes": out_nodes, "links": out_links, "total_nodes": len(nodes), "total_links": len(links)}
    )


async def report(request: Request) -> JSONResponse:
    name = request.path_params["project"]
    if name not in _projects():
        return JSONResponse({"error": "unknown project"}, status_code=404)
    path = KNOWLEDGE_ROOT / name / "graphify-out" / "GRAPH_REPORT.md"
    return JSONResponse({"markdown": path.read_text() if path.exists() else T("(kein Report vorhanden)")})


# ---------------------------------------------------------------------------
# Antwort-Speicher
# ---------------------------------------------------------------------------
# Jede Erklärung und jede Frage kostet Geld und Wartezeit. Bisher war beides nach
# dem Schließen des Panels weg — dieselbe Frage zweimal gestellt hieß: zweimal
# bezahlt. Antworten werden darum gespeichert und wiederverwendet.
#
# Der Schlüssel enthält den Stand des Graphen (mtime): Wird ein Projekt neu gemappt,
# sind die alten Antworten ungültig und verfallen von selbst — eine veraltete
# Erklärung wäre schlimmer als gar keine.
#
# Zusätzlich wandert jede Antwort in graphify-out/memory/ (`graphify save-result`).
# Das ist der Rückkanal, aus dem `graphify reflect` lernt, welche Wege getragen haben.
ANTWORT_DIR = DATA_DIR / "answers"


def _graph_stand(projekt: str) -> str:
    g = KNOWLEDGE_ROOT / projekt / "graphify-out" / "graph.json"
    return str(int(g.stat().st_mtime)) if g.exists() else "0"


def _speicher_pfad(projekt: str, art: str, frage: str, modell: str) -> Path:
    roh = f"{art}|{projekt}|{_graph_stand(projekt)}|{modell}|{frage}"
    h = hashlib.sha256(roh.encode()).hexdigest()[:16]
    return ANTWORT_DIR / projekt / f"{art}-{h}.json"


def _antwort_lesen(projekt: str, art: str, frage: str, modell: str) -> dict | None:
    f = _speicher_pfad(projekt, art, frage, modell)
    try:
        return json.loads(f.read_text())
    except Exception:  # noqa: BLE001 - fehlend oder kaputt = kein Treffer
        return None


def _antwort_schreiben(projekt: str, art: str, frage: str, modell: str, daten: dict) -> None:
    f = _speicher_pfad(projekt, art, frage, modell)
    try:
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_text(json.dumps({**daten, "gespeichert": int(time.time()), "frage": frage}))
    except Exception:  # noqa: BLE001 - ein kaputter Speicher darf die Antwort nicht kosten
        pass


def _ins_graph_gedaechtnis(projekt: str, art: str, frage: str, antwort: str) -> None:
    """Antwort in graphify-out/memory/ ablegen — der Rückkanal für `graphify reflect`."""
    try:
        subprocess.run(  # noqa: S603 - fester Binary, geprüftes Projekt
            [
                GRAPHIFY_BIN,
                "save-result",
                "--question",
                frage[:500],
                "--answer",
                antwort[:4000],
                "--type",
                art,
            ],
            cwd=KNOWLEDGE_ROOT / projekt,
            capture_output=True,
            timeout=20,
            check=False,
        )
    except Exception:  # noqa: BLE001 - reine Zugabe, darf nie die Antwort verhindern
        pass


async def antworten_liste(request: Request) -> JSONResponse:
    """Die gespeicherten Erklärungen und Antworten eines Projekts (neueste zuerst)."""
    name = request.path_params["project"]
    if name not in _projects():
        return JSONResponse({"error": T("Unbekanntes Projekt")}, status_code=404)
    ordner = ANTWORT_DIR / name
    out = []
    if ordner.is_dir():
        for f in ordner.glob("*.json"):
            try:
                d = json.loads(f.read_text())
            except Exception:  # noqa: BLE001
                continue
            out.append(
                {
                    "art": "explain" if f.name.startswith("explain") else "query",
                    "frage": d.get("frage", ""),
                    "text": (d.get("text") or d.get("answer") or "")[:400],
                    "modell": d.get("model", ""),
                    "gespeichert": d.get("gespeichert"),
                }
            )
    out.sort(key=lambda x: x.get("gespeichert") or 0, reverse=True)
    return JSONResponse({"items": out[:100]})


async def explain(request: Request) -> JSONResponse:
    """Knoten erklären: Graph-Nachbarschaft holen und von der KI in verständliche
    Sprache übersetzen — mit demselben Anbieter/Key wie das Mapping."""
    import llm

    name = request.path_params["project"]
    node = request.query_params.get("node", "")
    if name not in _projects() or not node:
        return JSONResponse({"error": T("Unbekanntes Projekt oder fehlender Knoten")}, status_code=400)

    # 1. Fakten aus dem Graphen (lokal, schnell, kostenlos)
    proc = subprocess.run(  # noqa: S603 - fester Binary, geprüftes Projekt, Listenargumente
        [GRAPHIFY_BIN, "explain", node],
        cwd=KNOWLEDGE_ROOT / name,
        capture_output=True,
        text=True,
        timeout=120,
    )
    if proc.returncode != 0:
        return JSONResponse({"error": proc.stderr.strip()[:2000] or "graphify failed"}, status_code=500)
    context = proc.stdout.strip()

    # 2. Von der KI in verständliche Sprache bringen
    cfg = config.load()
    backend_name, backend = config.active_backend(cfg)
    model = cfg["mapping"].get("model", "")
    secret = backend.get("secret")
    key = vault.secret_get(secret, client="web-ui") if secret else ""
    if secret and not key:
        return JSONResponse(
            {
                "text": context,
                "source": "graph",
                "note": T(
                    "Kein {backend}-Key hinterlegt — hier stehen nur die Rohdaten aus dem "
                    "Graphen. Key im Mapping-Tab eintragen für eine echte Erklärung.",
                    backend=backend.get("label", backend_name),
                ),
            }
        )
    # Schon einmal erklärt? Dann nicht noch einmal bezahlen.
    if not request.query_params.get("fresh"):
        alt = _antwort_lesen(name, "explain", node, model)
        if alt:
            return JSONResponse({**alt, "source": "gespeichert", "context": context})

    try:
        answer = await asyncio.to_thread(
            llm.ask,
            backend,
            model,
            key or "",
            llm.EXPLAIN_SYSTEM,
            llm.explain_prompt(name, node, context),
        )
    except llm.LLMError as e:
        return JSONResponse(
            {"text": context, "source": "graph", "note": T("KI nicht verfügbar: {msg}", msg=e)}
        )
    vault.audit("EXPLAIN", f"{name}/{node}", client="web-ui")
    ergebnis = {
        "text": answer,
        "source": "llm",
        "model": model,
        "backend": backend.get("label", backend_name),
    }
    _antwort_schreiben(name, "explain", node, model, ergebnis)
    await asyncio.to_thread(_ins_graph_gedaechtnis, name, "explain", node, answer)
    return JSONResponse({**ergebnis, "context": context})


# Interne Secrets (2FA-Zustand u. Ä.) tauchen nicht in der Secrets-Verwaltung auf —
# sie sind kein Nutzer-Key und dürfen nicht gelöscht/ausgelesen werden. Die Liste steht
# in vault.py: sie muss für JEDEN Weg in den Vault gelten, nicht nur für die Oberfläche.
HIDDEN_SECRETS = vault.HIDDEN_SECRETS


_CITE_RE = re.compile(r"NODE (.+?) \[src=(.+?) loc=(\S+)")


def _extract_sources(context: str) -> list[dict]:
    """Aus der graphify-Ausgabe die belegten Stellen (Knoten/Datei/Zeile) ziehen."""
    seen: set[str] = set()
    out: list[dict] = []
    for m in _CITE_RE.finditer(context):
        label, src, loc = m.group(1), m.group(2), m.group(3)
        key = f"{src}:{loc}"
        if key in seen:
            continue
        seen.add(key)
        out.append({"label": label, "file": src, "loc": loc})
    return out[:25]


async def graph_ask(request: Request) -> JSONResponse:
    """Natürlichsprachige Frage an einen Projektgraphen: relevante Knoten per BFS
    holen und von der KI mit Belegen beantworten lassen."""
    import llm

    name = request.path_params["project"]
    if name not in _projects():
        return JSONResponse({"error": T("Unbekanntes Projekt")}, status_code=404)
    body = await request.json()
    question = str(body.get("question", "")).strip()
    if len(question) < 3:
        return JSONResponse({"error": T("Bitte eine Frage eingeben.")}, status_code=400)

    def graphify_query(q: str) -> str:
        return subprocess.run(  # noqa: S603 - fester Binary, geprüftes Projekt
            [GRAPHIFY_BIN, "query", q, "--budget", "1500"],
            cwd=KNOWLEDGE_ROOT / name,
            capture_output=True,
            text=True,
            timeout=60,
        ).stdout.strip()

    cfg = config.load()
    backend_name, backend = config.active_backend(cfg)
    model = cfg["mapping"].get("model", "")
    secret = backend.get("secret")
    key = vault.secret_get(secret, client="web-ui") if secret else ""

    # 1. Relevante Knoten aus dem Graphen (lokal, kostenlos)
    context = await asyncio.to_thread(graphify_query, question)

    # 1b. Nichts gefunden? graphify braucht Code-Vokabular — die KI übersetzt die
    #     Frage in englische Suchbegriffe und wir versuchen es erneut.
    if (not context or "No matching nodes" in context) and key:
        import llm as _llm

        try:
            kw = await asyncio.to_thread(
                _llm.ask,
                backend,
                model,
                key,
                _llm.KEYWORDS_SYSTEM,
                _llm.keywords_prompt(question),
            )
            terms = [t.strip() for t in kw.replace("\n", ",").split(",") if t.strip()][:6]
            for term in terms:
                context = await asyncio.to_thread(graphify_query, term)
                if context and "No matching nodes" not in context:
                    break
        except Exception:  # noqa: BLE001
            pass

    sources = _extract_sources(context)
    if not context or "No matching nodes" in context:
        return JSONResponse(
            {
                "answer": T(
                    "Zu dieser Frage habe ich im Graphen nichts gefunden. Versuch es mit anderen "
                    "Begriffen — am besten mit Namen aus dem Code (Funktionen, Dateien, Konzepte)."
                ),
                "source": "graph",
                "sources": [],
            }
        )

    # 2. KI-Antwort mit Belegen
    if secret and not key:
        return JSONResponse(
            {
                "answer": T(
                    "Kein KI-Key hinterlegt — hier sind nur die passenden Stellen aus dem "
                    "Graphen. Für eine formulierte Antwort einen Key im Mapping-Tab eintragen."
                ),
                "source": "graph",
                "sources": sources,
            }
        )
    # Dieselbe Frage schon einmal beantwortet? Antwort aus dem Speicher.
    if not str(body.get("fresh", "")):
        alt = _antwort_lesen(name, "query", question, model)
        if alt:
            return JSONResponse({**alt, "source": "gespeichert", "sources": sources})

    try:
        answer = await asyncio.to_thread(
            llm.ask,
            backend,
            model,
            key or "",
            llm.QUERY_SYSTEM,
            llm.query_prompt(name, question, context),
        )
    except llm.LLMError as e:
        return JSONResponse(
            {"answer": T("KI nicht verfügbar: {msg}", msg=e), "source": "graph", "sources": sources}
        )
    vault.audit("QUERY", f"{name}: {question[:60]}", client="web-ui")
    ergebnis = {
        "answer": answer,
        "source": "llm",
        "model": model,
        "backend": backend.get("label", backend_name),
    }
    _antwort_schreiben(name, "query", question, model, ergebnis)
    await asyncio.to_thread(_ins_graph_gedaechtnis, name, "query", question, answer)
    return JSONResponse({**ergebnis, "sources": sources})
