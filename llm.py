"""LLM-Aufrufe für die Web-UI (Knoten erklären, später: Fragen an den Graphen).

Nutzt dasselbe Backend + Modell + Vault-Secret wie das Nacht-Mapping — was in der
UI eingestellt ist, gilt auch hier. Der Key wird pro Aufruf aus dem Vault geholt
und nirgends zwischengespeichert.

Zwei API-Formen:
  * "openai"    — OpenAI-kompatibel (OpenAI, Gemini, DeepSeek, Kimi, Ollama)
  * "anthropic" — Anthropic Claude (offizielles SDK)
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import tempfile
import time
import urllib.error
import urllib.request

TIMEOUT = 120
# claude -p kann pro Aufruf deutlich länger brauchen als eine HTTP-API (es startet
# eine ganze Claude-Code-Instanz). Eigener, großzügigerer Deckel.
CLI_TIMEOUT = 300

# Transiente Antworten, bei denen sich ein Retry lohnt (Rate-Limit, Serverfehler) —
# der Anthropic-Pfad wiederholt die im SDK intern, der eigene urllib-Pfad hier.
_RETRIABLE_CODES = frozenset({429, 500, 502, 503, 504})
_MAX_VERSUCHE = 3


class LLMError(RuntimeError):
    pass


# Die neueren OpenAI-Modelle (gpt-5-Familie, o1/o3/o4) lehnen `max_tokens` ab und
# verlangen `max_completion_tokens`. Die älteren kennen den neuen Namen nicht.
# Genau daran waren „Erklären lassen" und der Fragen-Tab tot, sobald das Modell auf
# gpt-5 stand: 400 „Unsupported parameter: 'max_tokens'".
_NEUES_LIMIT = re.compile(r"^(gpt-5|o[1-9])", re.I)


def _openai_body(model: str, system: str, user: str, limit_key: str, limit: int = 900) -> bytes:
    return json.dumps(
        {
            "model": model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            limit_key: limit,
        }
    ).encode()


def _erwaehnt_token_limit(detail: str) -> bool:
    # Beide Schreibweisen einzeln prüfen — "max_tokens" ist KEIN Substring von
    # "max_completion_tokens", deshalb griff der alte Einzel-Check nur einseitig.
    return "max_tokens" in detail or "max_completion_tokens" in detail


# Ablehn-Stichworte der Anbieter: OpenAI/DeepSeek/Kimi sagen "unsupported",
# Gemini "Unknown name", andere OpenAI-kompatible Server (Ollama & Co.) ggf.
# "unrecognized"/"invalid" — deshalb nicht nur ein Wort matchen.
_ABLEHNUNG = ("unsupported", "not supported", "unknown", "unrecognized", "unexpected", "invalid")


def _ist_token_parameter_fehler(code: int, detail: str) -> bool:
    """Heilbarer 400er: der Anbieter lehnt den geratenen Token-Parameter ab
    und will den anderen Namen — in beide Richtungen erkennen."""
    return (
        code == 400 and _erwaehnt_token_limit(detail) and any(wort in detail.lower() for wort in _ABLEHNUNG)
    )


def _backoff_sekunden(fehler: urllib.error.HTTPError, versuch: int) -> float:
    # Retry-After des Anbieters respektieren (kommt bei 429 oft), sonst
    # exponentiell 1 s, 2 s — gedeckelt, damit die UI nicht ewig hängt.
    roh = fehler.headers.get("Retry-After") if fehler.headers else None
    try:
        vorgabe = float(roh) if roh else 0.0
    except ValueError:
        vorgabe = 0.0
    return min(max(vorgabe, 2.0**versuch), 10.0)


def _post_json(req: urllib.request.Request) -> dict:
    """POST mit Retry bei transienten Fehlern (429/5xx, exponentielles Backoff,
    max. _MAX_VERSUCHE) — analog zu den SDK-internen Retries im Anthropic-Pfad."""
    for versuch in range(_MAX_VERSUCHE):
        try:
            with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
                return json.load(r)
        except json.JSONDecodeError as e:
            # 200, aber der Body ist kein JSON (Proxy-HTML-Fehlerseite, leere Antwort,
            # abgeschnitten). Kein Retry — sauber als LLMError melden statt einen rohen
            # JSONDecodeError bis in einen 500-Traceback durchschlagen zu lassen.
            raise LLMError("Anbieter lieferte keine gültige JSON-Antwort.") from e
        except urllib.error.HTTPError as e:
            if e.code in _RETRIABLE_CODES and versuch < _MAX_VERSUCHE - 1:
                e.read()  # Body konsumieren, damit die Verbindung freigegeben wird
                time.sleep(_backoff_sekunden(e, versuch))
                continue
            raise
        except OSError as e:
            raise LLMError(f"Anbieter nicht erreichbar: {e}") from e
    raise LLMError("Anbieter nicht erreichbar: Versuche erschöpft.")  # pragma: no cover


def _call_openai(
    base_url: str, key: str, model: str, system: str, user: str, limit: int = 900
) -> tuple[str, dict[str, int]]:
    url = base_url.rstrip("/") + "/chat/completions"
    kopf = {"Content-Type": "application/json", "Authorization": f"Bearer {key}"}
    # Passenden Namen raten — und wenn der Anbieter widerspricht, den anderen nehmen.
    # Ein neues Modell soll nicht wieder alles lahmlegen, nur weil die Liste veraltet.
    erst = "max_completion_tokens" if _NEUES_LIMIT.match(model.strip()) else "max_tokens"
    dann = "max_tokens" if erst == "max_completion_tokens" else "max_completion_tokens"

    for versuch, limit_key in enumerate((erst, dann)):
        req = urllib.request.Request(
            url, data=_openai_body(model, system, user, limit_key, limit), headers=kopf
        )
        try:
            data = _post_json(req)
            break
        except urllib.error.HTTPError as e:
            detail = e.read().decode(errors="replace")[:300]
            # Genau dieser Fehler ist heilbar: der Anbieter will den anderen Namen.
            if versuch == 0 and _ist_token_parameter_fehler(e.code, detail):
                continue
            raise LLMError(f"Anbieter antwortete {e.code}: {detail}") from e

    try:
        wahl = data["choices"][0]
        content = wahl["message"]["content"]
    except (KeyError, IndexError, TypeError) as e:
        # TypeError: der Body war gültiges JSON, aber kein Objekt (Liste/String/Zahl) —
        # dann sind data["choices"] & Co. nicht indexierbar.
        raise LLMError("Unerwartete Antwort des Anbieters") from e
    if not isinstance(content, str) or not content.strip():
        # content kann null sein (OpenAI-Refusal, Azure-Content-Filter), leer oder eine
        # Parts-Liste (manche OpenAI-kompatible Server) — nie ein rohes AttributeError.
        raise LLMError("Anbieter lieferte keinen verwertbaren Text (leer oder abgelehnt).")
    if isinstance(wahl, dict) and wahl.get("finish_reason") == "length":
        # Am Token-Limit abgeschnitten — die Extraktion würde sonst halbes JSON
        # als „gültige" Antwort verbuchen.
        raise LLMError("Antwort abgeschnitten (Token-Limit erreicht) — Limit erhöhen.")
    # Usage für die Nachtlauf-Kostenverbuchung (e486ab4) mitgeben.
    u = data.get("usage") or {}
    return content.strip(), {"in": int(u.get("prompt_tokens", 0)), "out": int(u.get("completion_tokens", 0))}


def _call_anthropic(
    key: str, model: str, system: str, user: str, limit: int = 900
) -> tuple[str, dict[str, int]]:
    try:
        import anthropic
    except ImportError as e:  # pragma: no cover
        raise LLMError("Paket 'anthropic' fehlt — bitte nachinstallieren.") from e

    # Explizites Timeout — der SDK-Default (600 s) lässt UI-Aufrufe bis zu
    # 10 Minuten hängen, während der OpenAI-Pfad mit TIMEOUT=120 arbeitet.
    client = anthropic.Anthropic(api_key=key, timeout=TIMEOUT)
    try:
        msg = client.messages.create(
            model=model,
            max_tokens=limit,
            system=system,
            messages=[{"role": "user", "content": user}],
        )
    except anthropic.APIStatusError as e:
        raise LLMError(f"Claude antwortete {e.status_code}: {e.message}") from e
    except anthropic.APIConnectionError as e:
        raise LLMError(f"Claude nicht erreichbar: {e}") from e
    if msg.stop_reason == "refusal":
        raise LLMError("Claude hat die Anfrage abgelehnt.")
    if msg.stop_reason == "max_tokens":
        # Am Limit abgeschnitten — wie finish_reason == "length" im OpenAI-Pfad.
        raise LLMError("Antwort abgeschnitten (Token-Limit erreicht) — Limit erhöhen.")
    text = "".join(b.text for b in msg.content if b.type == "text").strip()
    # Usage für die Nachtlauf-Kostenverbuchung (e486ab4) mitgeben.
    usage = getattr(msg, "usage", None)
    return text, {
        "in": int(getattr(usage, "input_tokens", 0) or 0),
        "out": int(getattr(usage, "output_tokens", 0) or 0),
    }


def _claude_cli_envelope(stdout: str) -> dict:
    """Parst die JSON-Hülle von `claude -p --output-format json`.

    Je nach CLI-Version ist das ein Objekt {result, usage, …} oder eine Liste, in der
    das Ergebnis-Objekt (type=="result") gesucht werden muss.
    """
    try:
        data = json.loads(stdout)
    except json.JSONDecodeError as e:
        raise LLMError(f"claude -p lieferte kein gültiges JSON: {str(e)[:120]}") from e
    if isinstance(data, list):
        for eintrag in reversed(data):
            if isinstance(eintrag, dict) and (eintrag.get("type") == "result" or "result" in eintrag):
                return eintrag
        raise LLMError("claude -p JSON-Array ohne Ergebnis-Objekt.")
    if isinstance(data, dict):
        return data
    raise LLMError("claude -p JSON weder Objekt noch Liste.")


def _call_claude_cli(model: str, system: str, user: str, limit: int = 900) -> tuple[str, dict[str, int]]:
    """Ruft Claude über die lokale Claude-Code-CLI (`claude -p`) — nutzt das Abo statt
    eines bezahlten API-Keys. Kein Key nötig; die Auth der CLI wird verwendet.
    """
    claude = shutil.which("claude") or os.path.expanduser("~/.local/bin/claude")
    if not (claude and os.path.exists(claude)):
        raise LLMError("Claude-Code-CLI ('claude') nicht gefunden — für Backend 'claude-cli' nötig.")

    prompt = (
        f"{system}\n\n---\n"
        "Bearbeite ausschließlich die folgende Aufgabe/Quelle und gib NUR das geforderte "
        "JSON-Objekt aus — keine Prosa, keine Einleitung, keine Markdown-Zäune.\n\n"
        f"{user}"
    )
    args = [claude, "-p", "--output-format", "json", "--no-session-persistence"]
    # Modell nur weiterreichen, wenn es ein echter CLI-Wert ist (sonnet/haiku/opus oder
    # eine volle Modell-ID). Der Platzhalter "claude-code-plan" → Standardmodell des Abos.
    m = (model or "").strip()
    if m and m != "claude-code-plan" and re.match(r"^(sonnet|haiku|opus|claude-)", m):
        args += ["--model", m]

    try:
        # In neutralem cwd starten, damit die CLI nicht CLAUDE.md/Skills/MCP eines
        # Projektordners mitzieht (Kontext-Ballast, potenzielle Seiteneffekte).
        proc = subprocess.run(  # noqa: S603 - fixe Argumente, kein Shell
            args,
            input=prompt,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=CLI_TIMEOUT,
            cwd=tempfile.gettempdir(),
            check=False,
        )
    except subprocess.TimeoutExpired as e:
        raise LLMError(f"claude -p Zeitüberschreitung nach {CLI_TIMEOUT}s.") from e
    except OSError as e:
        raise LLMError(f"claude -p nicht ausführbar: {e}") from e
    if proc.returncode != 0:
        raise LLMError(f"claude -p endete mit Code {proc.returncode}: {proc.stderr.strip()[:200]}")

    env = _claude_cli_envelope(proc.stdout)
    text = (env.get("result") or "").strip()
    if not text:
        raise LLMError("claude -p lieferte keinen Text (leeres result).")
    u = env.get("usage") or {}
    tin = int(u.get("input_tokens", 0) or 0) + int(u.get("cache_read_input_tokens", 0) or 0)
    return text, {"in": tin, "out": int(u.get("output_tokens", 0) or 0)}


def ask(
    backend: dict,
    model: str,
    key: str,
    system: str,
    user: str,
    limit: int = 900,
    usage: dict | None = None,
) -> str:
    """Eine Frage an das konfigurierte Backend stellen.

    limit = maximale Antwort-Tokens. 900 reicht für Erklärungen und Chat-Antworten;
    die Graph-Extraktion braucht mehr (JSON mit bis zu 12 Entities + Fakten) und
    übergibt ein höheres Limit — sonst wird das JSON mittendrin abgeschnitten.

    usage (optional): wird — wenn übergeben — um die verbrauchten Tokens dieses
    Aufrufs erhöht (`in`/`out`/`calls`). So kann der Extraktor die Nachtlauf-Kosten
    verbuchen, während Chat/Explain den Parameter einfach weglassen.
    """
    api = backend.get("api", "openai")
    if api == "claude-cli":
        text, u = _call_claude_cli(model, system, user, limit)
    elif api == "anthropic":
        text, u = _call_anthropic(key, model, system, user, limit)
    else:
        base = backend.get("base_url")
        if not base:
            raise LLMError("Für dieses Backend ist keine base_url konfiguriert.")
        text, u = _call_openai(base, key or "local", model, system, user, limit)
    if usage is not None:
        usage["in"] = usage.get("in", 0) + u.get("in", 0)
        usage["out"] = usage.get("out", 0) + u.get("out", 0)
        usage["calls"] = usage.get("calls", 0) + 1
    return text


# Nutzereingaben (Frage/Knotenname) im Prompt deckeln — nur graph_context war
# bisher begrenzt; riesige Request-Bodies treiben sonst Input-Tokens/Kosten ungebunden.
_MAX_EINGABE = 2000

EXPLAIN_SYSTEM = (
    "Du erklärst Knoten aus einem Wissensgraphen über ein Software-Projekt. "
    "Antworte auf Deutsch, klar und in ganzen Sätzen, für jemanden, der den Code nicht kennt. "
    "Struktur: 1) Was ist das, in einem Satz. 2) Wozu dient es im Projekt. "
    "3) Wie hängt es mit den Nachbarknoten zusammen. "
    "Erfinde nichts dazu — stütze dich nur auf die gegebenen Daten. Höchstens 180 Wörter."
)


def explain_prompt(project: str, node: str, graph_context: str) -> str:
    node = node[:_MAX_EINGABE]
    return (
        f"Projekt: {project}\n"
        f"Knoten: {node}\n\n"
        f"Das sagt der Wissensgraph über diesen Knoten und seine Nachbarschaft:\n"
        f"```\n{graph_context[:12000]}\n```\n\n"
        f"Erkläre den Knoten „{node}“."
    )


QUERY_SYSTEM = (
    "Du hilfst beim Verstehen eines Software-Projekts, indem du Fragen anhand seines "
    "Wissensgraphen beantwortest. Du bekommst die Frage und die relevanten Knoten aus dem Graphen "
    "(mit Datei und Zeilennummer). Unter INHALT folgen die gespeicherten Inhalte der Knoten — dort "
    "stehen die konkreten Fakten (Ports, Versionen, Pfade, Entscheidungen); nutze sie bevorzugt. "
    "Antworte auf Deutsch, konkret und arbeitstauglich, in genau drei kurzen Absätzen, "
    "getrennt durch eine Leerzeile:\n"
    "Absatz 1: Direkte Antwort in ein, zwei Sätzen.\n"
    "Absatz 2: Die konkreten Stellen im Code als `datei:zeile` (Zeile weglassen, wenn keine bekannt).\n"
    "Absatz 3: Falls sinnvoll, der nächste Schritt — sonst weglassen.\n"
    "Nummeriere die Absätze NICHT. Stütze dich NUR auf die gegebenen Knoten — erfinde keine "
    "Dateien oder Funktionen. Wenn die Knoten die Frage nicht beantworten, sage das ehrlich. "
    "Höchstens 200 Wörter."
)


KEYWORDS_SYSTEM = (
    "Du hilfst, eine Frage in Suchbegriffe für einen Code-Wissensgraphen zu übersetzen. "
    "Der Graph enthält englische Code-Bezeichner (Funktions-, Datei-, Konzeptnamen). "
    "Gib 3–6 wahrscheinliche englische Suchbegriffe aus, durch Kommas getrennt, sonst nichts. "
    "Beispiel Frage „Wo werden Buchungen validiert?“ → booking, validate, validation, booking-actions"
)


def keywords_prompt(question: str) -> str:
    return f"Frage: {question[:_MAX_EINGABE]}\n\nSuchbegriffe:"


def query_prompt(project: str, question: str, graph_context: str) -> str:
    return (
        f"Projekt: {project}\n"
        f"Frage: {question[:_MAX_EINGABE]}\n\n"
        f"Relevante Knoten aus dem Wissensgraphen (BFS-Traversal):\n"
        f"```\n{graph_context[:13000]}\n```\n\n"
        f"Beantworte die Frage anhand dieser Knoten."
    )
