"""Graphen, Berichte und die Frage-Antwort-Funktion."""

from __future__ import annotations

import asyncio
import json
import re
import subprocess

from starlette.requests import Request
from starlette.responses import JSONResponse

import config
import vault
from api.common import GRAPHIFY_BIN, KNOWLEDGE_ROOT, _projects
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
    return JSONResponse(
        {"markdown": path.read_text() if path.exists() else T("(kein Report vorhanden)")}
    )


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
                "note": T("Kein {backend}-Key hinterlegt — hier stehen nur die Rohdaten aus dem "
                          "Graphen. Key im Mapping-Tab eintragen für eine echte Erklärung.",
                          backend=backend.get("label", backend_name)),
            }
        )
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
    return JSONResponse(
        {"text": answer, "source": "llm", "model": model, "backend": backend.get("label", backend_name),
         "context": context}
    )


# Interne Secrets (2FA-Zustand u. Ä.) tauchen nicht in der Secrets-Verwaltung auf —
# sie sind kein Nutzer-Key und dürfen nicht gelöscht/ausgelesen werden.
HIDDEN_SECRETS = {"__2fa__"}


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
            cwd=KNOWLEDGE_ROOT / name, capture_output=True, text=True, timeout=60,
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
                _llm.ask, backend, model, key, _llm.KEYWORDS_SYSTEM, _llm.keywords_prompt(question),
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
        return JSONResponse({
            "answer": T("Zu dieser Frage habe ich im Graphen nichts gefunden. Versuch es mit anderen "
                        "Begriffen — am besten mit Namen aus dem Code (Funktionen, Dateien, Konzepte)."),
            "source": "graph", "sources": [],
        })

    # 2. KI-Antwort mit Belegen
    if secret and not key:
        return JSONResponse({
            "answer": T("Kein KI-Key hinterlegt — hier sind nur die passenden Stellen aus dem "
                        "Graphen. Für eine formulierte Antwort einen Key im Mapping-Tab eintragen."),
            "source": "graph", "sources": sources,
        })
    try:
        answer = await asyncio.to_thread(
            llm.ask, backend, model, key or "",
            llm.QUERY_SYSTEM, llm.query_prompt(name, question, context),
        )
    except llm.LLMError as e:
        return JSONResponse({"answer": T("KI nicht verfügbar: {msg}", msg=e),
                             "source": "graph", "sources": sources})
    vault.audit("QUERY", f"{name}: {question[:60]}", client="web-ui")
    return JSONResponse({
        "answer": answer, "source": "llm",
        "model": model, "backend": backend.get("label", backend_name),
        "sources": sources,
    })
