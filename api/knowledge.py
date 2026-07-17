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
from starlette.responses import JSONResponse, Response

import config
import graph_context
import semantic
import vault
from api.common import DATA_DIR, GRAPHIFY_BIN, KNOWLEDGE_ROOT, _projects, json_object
from api.i18n import T

# graph.json wird bei jedem Aufruf von projects()/graph() gelesen und geparst. Ein
# großer Graph (20 k Knoten ≈ 20 MB) kostet ~140 ms Parse — synchron in der Event-Loop,
# also fror der ganze Server bei jeder Graph-Ansicht kurz ein und unter Last (viele
# gleichzeitige Leser) sekundenlang (R24-1). Die Datei ändert sich nur beim Rebuild,
# deshalb: geparsten Graphen UND fertige Antwort je nach mtime zwischenspeichern.
_parsed_cache: dict[str, tuple[float, dict | None]] = {}
_payload_cache: dict[tuple[str, int], tuple[float, bytes]] = {}
_CACHE_MAX = 12
# Harter Deckel für ?limit= in der Graph-Ansicht (SEC-06): ohne Obergrenze serialisierte
# ein einziger GET den VOLLEN Graphen (bei 100 k Knoten zig MB pro Request), und weil
# der Payload-Cache pro (name, limit) schlüsselt, umgingen variierte Werte (0,-1,-2,…)
# ihn komplett. limit<=0 (= „alle", schickt die UI bei Regler-Anschlag) wird auf
# GRAPH_LIMIT_MAX normalisiert — alle „alle"-Varianten teilen sich so einen Cache-Key.
GRAPH_LIMIT_MAX = 20_000


def _graph_mtime(name: str) -> float | None:
    try:
        return (KNOWLEDGE_ROOT / name / "graphify-out" / "graph.json").stat().st_mtime
    except OSError:
        return None


def _read_graph(name: str) -> dict | None:
    """graph.json eines Projekts lesen (mtime-gecacht). Gibt None zurück, wenn die
    Datei fehlt oder beschädigt ist (halb geschrieben, kein JSON) — statt einen rohen
    JSONDecodeError bis in einen 500-Traceback durchschlagen zu lassen. Ein kaputter
    Graph eines Projekts darf weder die Projektübersicht noch die Graph-Ansicht abreißen."""
    mtime = _graph_mtime(name)
    if mtime is None:
        _parsed_cache.pop(name, None)
        return None
    hit = _parsed_cache.get(name)
    if hit and hit[0] == mtime:
        return hit[1]
    try:
        g = json.loads((KNOWLEDGE_ROOT / name / "graphify-out" / "graph.json").read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, UnicodeDecodeError):
        # UnicodeDecodeError: Nicht-UTF-8-Bytes — der Graph gilt als „nicht lesbar",
        # statt mit einem 500-Traceback projects()/graph() abzureißen (BE-06).
        g = None
    g = g if isinstance(g, dict) else None
    if len(_parsed_cache) >= _CACHE_MAX:
        _parsed_cache.clear()
    _parsed_cache[name] = (mtime, g)
    return g


def _graph_listen(g: dict) -> tuple[list, list] | None:
    """nodes/links eines geparsten Graphen typsicher holen (BE-06): Ist einer der
    beiden Blöcke kein Array, ist der Graph strukturell kaputt → None; die Aufrufer
    melden dann „Graph nicht lesbar" statt mit KeyError/TypeError in einen 500 zu
    laufen. Einzelne Einträge ohne dict-Form oder ohne Pflichtschlüssel (id bzw.
    source/target) werden herausgefiltert — der Rest des Graphen bleibt nutzbar."""
    nodes = g.get("nodes", [])
    links = g.get("links", g.get("edges", []))
    if not isinstance(nodes, list) or not isinstance(links, list):
        return None
    nodes = [n for n in nodes if isinstance(n, dict) and n.get("id") is not None]
    links = [
        link
        for link in links
        if isinstance(link, dict) and link.get("source") is not None and link.get("target") is not None
    ]
    return nodes, links


def _build_graph_payload(name: str, limit: int) -> bytes | None:
    """Der CPU-Kern der Graph-Ansicht: parsen, nach Grad ranken, deckeln, zu Antwort
    formen UND serialisieren. Gibt fertige JSON-Bytes zurück, damit auch die
    Serialisierung (≈1,6 MB bei großen Graphen) aus der Event-Loop ausgelagert und
    danach als Bytes gecacht wird — ein Cache-Hit serialisiert dann nichts mehr.
    Bewusst eine reine Funktion (via asyncio.to_thread aufrufbar)."""
    g = _read_graph(name)
    if g is None:
        return None
    teile = _graph_listen(g)
    if teile is None:
        return None
    nodes, links = teile
    degree: dict[str, int] = {}
    for link in links:
        degree[link["source"]] = degree.get(link["source"], 0) + 1
        degree[link["target"]] = degree.get(link["target"], 0) + 1
    ranked = sorted(nodes, key=lambda n: degree.get(n["id"], 0), reverse=True)
    keep_nodes = ranked[:limit]  # limit wird in graph() auf 1..GRAPH_LIMIT_MAX geclamppt
    keep_ids = {n["id"] for n in keep_nodes}
    out_nodes = [
        {
            "id": n["id"],
            "label": n.get("label", n["id"]),
            "community": n.get("community"),
            "community_name": n.get("community_name"),
            "file": n.get("source_file"),
            "rationale": str(n.get("rationale") or "")[:4000],
            "source_url": n.get("source_url") if n.get("source_url") not in (None, "None") else "",
            "degree": degree.get(n["id"], 0),
        }
        for n in keep_nodes
    ]
    out_links = [
        {"source": link["source"], "target": link["target"], "relation": link.get("relation", "")}
        for link in links
        if link["source"] in keep_ids and link["target"] in keep_ids
    ]
    return json.dumps(
        {"nodes": out_nodes, "links": out_links, "total_nodes": len(nodes), "total_links": len(links)}
    ).encode()


def _build_projects() -> list[dict]:
    out = []
    for name in _projects():
        g = _read_graph(name)  # mtime-gecacht
        teile = _graph_listen(g) if g is not None else None
        if teile is None:
            out.append(
                {"project": name, "nodes": 0, "edges": 0, "communities": 0, "error": T("Graph nicht lesbar")}
            )
            continue
        nodes, links = teile
        out.append(
            {
                "project": name,
                "nodes": len(nodes),
                "edges": len(links),
                "communities": len({n.get("community") for n in nodes if n.get("community") is not None}),
            }
        )
    return out


async def projects(request: Request) -> JSONResponse:
    # Über einen Thread: das Parsen mehrerer (ggf. großer) Graphen darf die Event-Loop
    # nicht blockieren. Nach dem ersten Aufruf liefern die mtime-Caches nahezu kostenlos.
    out = await asyncio.to_thread(_build_projects)
    return JSONResponse(out)


async def graph(request: Request) -> JSONResponse:
    name = request.path_params["project"]
    if name not in _projects():
        return JSONResponse({"error": "unknown project"}, status_code=404)
    # Ein unsinniges ?limit= (Buchstaben) ist ein Aufruferfehler, kein Serverabsturz —
    # der Endpunkt fällt auf den Standardwert zurück statt mit 500 zu enden.
    try:
        limit = int(request.query_params.get("limit", 2000))
    except (TypeError, ValueError):
        limit = 2000
    # Clampen auf 1..GRAPH_LIMIT_MAX (SEC-06): limit<=0 heißt „alle" und wird auf das
    # harte Maximum normalisiert — sonst gäbe es keinen Deckel und jede Negative
    # (0,-1,-2,…) einen eigenen Cache-Schlüssel (= Cache-Umgehung per Parameter-Drehen).
    limit = GRAPH_LIMIT_MAX if limit <= 0 else min(limit, GRAPH_LIMIT_MAX)

    # Fertige Antwort je nach graph.json-mtime aus dem Cache — so zahlt nur der erste
    # Aufruf nach einem Rebuild die Parse-/Rank-Kosten, nicht jeder Leser (R24-1).
    mtime = _graph_mtime(name)
    ck = (name, limit)
    hit = _payload_cache.get(ck)
    if hit and mtime is not None and hit[0] == mtime:
        return Response(hit[1], media_type="application/json")

    # Cache-Miss: die CPU-Arbeit (Parse + Rank + Serialisierung) in einen Thread
    # auslagern, damit ein großer Graph die Event-Loop nicht sekundenlang blockiert.
    body = await asyncio.to_thread(_build_graph_payload, name, limit)
    if body is None:
        # Kaputte/fehlende graph.json: leeren Graphen mit Hinweis liefern statt 500.
        return JSONResponse(
            {"nodes": [], "links": [], "total_nodes": 0, "total_links": 0, "error": T("Graph nicht lesbar")}
        )
    if mtime is not None:
        if len(_payload_cache) >= _CACHE_MAX:
            _payload_cache.clear()
        _payload_cache[ck] = (mtime, body)
    return Response(body, media_type="application/json")


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
    # st_mtime_ns (Nanosekunden) statt int(st_mtime) (Sekunden): Zwei Graph-Generationen
    # innerhalb derselben Sekunde (schneller os.replace beim Re-Mapping) hätten sonst
    # denselben Cache-Schlüssel — der Fragen-Tab lieferte eine Antwort der Vorgänger-
    # generation, obwohl der Graph schon neu ist.
    return str(g.stat().st_mtime_ns) if g.exists() else "0"


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

    # 1. Anbieter/Key bestimmen (lokal, billig) — erst danach entscheidet sich,
    #    ob der teure graphify-Lauf überhaupt nötig ist.
    cfg = config.load()
    backend_name, backend = config.active_backend(cfg)
    model = cfg["mapping"].get("model", "")
    secret = backend.get("secret")
    key = vault.secret_get(secret, client="web-ui") if secret else ""

    # 2. Schon einmal erklärt? Der Speicher-Check muss VOR dem Subprocess stehen
    #    (SEC-06): ein Treffer darf die Event-Loop nicht mit einem bis zu 120 s
    #    langen graphify-Lauf blockieren. Läuft unter denselben Bedingungen wie
    #    zuvor — ohne nutzbaren Key bleibt es bei den Rohdaten (s. Schritt 4).
    if not (secret and not key) and not request.query_params.get("fresh"):
        alt = _antwort_lesen(name, "explain", node, model)
        if alt:
            # Ohne frischen Graph-Kontext (der käme erst aus dem Subprocess) —
            # die UI zeigt den Rohdaten-Kasten dann einfach leer an.
            return JSONResponse({**alt, "source": "gespeichert", "context": ""})

    # 3. Fakten aus dem Graphen (lokal, kostenlos) — im Thread: synchron aufgerufen
    #    blockierte der Subprocess die gesamte Event-Loop bis zum 120-s-Timeout (BE-06).
    try:
        proc = await asyncio.to_thread(
            subprocess.run,  # noqa: S603 - fester Binary, geprüftes Projekt, Listenargumente
            [GRAPHIFY_BIN, "explain", node],
            cwd=KNOWLEDGE_ROOT / name,
            capture_output=True,
            text=True,
            timeout=120,
        )
    except subprocess.TimeoutExpired:
        return JSONResponse(
            {"error": T("Zeitüberschreitung beim Lesen des Graphen — bitte erneut versuchen.")},
            status_code=504,
        )
    except OSError:
        # graphify fehlt (FileNotFoundError) oder das Projekt wurde seit der Prüfung
        # oben entfernt (Race mit dem Remove-Endpunkt) — saubere Antwort statt 500-Traceback.
        return JSONResponse({"error": T("Graph nicht lesbar")}, status_code=500)
    if proc.returncode != 0:
        return JSONResponse({"error": proc.stderr.strip()[:2000] or "graphify failed"}, status_code=500)
    context = graph_context.anreichern(KNOWLEDGE_ROOT / name, proc.stdout.strip())

    # 4. Von der KI in verständliche Sprache bringen
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
    body = await json_object(request)
    question = str(body.get("question", "")).strip()
    if len(question) < 3:
        return JSONResponse({"error": T("Bitte eine Frage eingeben.")}, status_code=400)

    def graphify_query(q: str) -> str:
        # Dreistufige Kette wie im MCP-graph_query: Hybrid → Graph → graphify-CLI
        try:
            src = None
            for e in config.project_entries():
                p = Path(e["path"]).expanduser()
                if p.name.lower() == name.lower() and p.is_dir():
                    src = p
                    break
            raw = semantic.hybrid_query(KNOWLEDGE_ROOT / name, q, budget=1500, source_dir=src)
        except Exception:
            try:
                raw = semantic.query(KNOWLEDGE_ROOT / name, q, budget=1500)
            except Exception:
                # Letzte Stufe: graphify-CLI. Fehlt sie (FileNotFoundError) oder hängt
                # sie (TimeoutExpired), NICHT bis in einen 500-Traceback durchschlagen —
                # dann gilt „nichts gefunden" und die UI zeigt den Hinweis.
                try:
                    raw = subprocess.run(  # noqa: S603 - fester Binary, geprüftes Projekt
                        [GRAPHIFY_BIN, "query", q, "--budget", "1500"],
                        cwd=KNOWLEDGE_ROOT / name,
                        capture_output=True,
                        text=True,
                        timeout=60,
                    ).stdout.strip()
                except Exception:
                    raw = ""
        return graph_context.anreichern(KNOWLEDGE_ROOT / name, raw)

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
