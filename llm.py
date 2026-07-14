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
import re
import urllib.error
import urllib.request

TIMEOUT = 120


class LLMError(RuntimeError):
    pass


# Die neueren OpenAI-Modelle (gpt-5-Familie, o1/o3/o4) lehnen `max_tokens` ab und
# verlangen `max_completion_tokens`. Die älteren kennen den neuen Namen nicht.
# Genau daran waren „Erklären lassen" und der Fragen-Tab tot, sobald das Modell auf
# gpt-5 stand: 400 „Unsupported parameter: 'max_tokens'".
_NEUES_LIMIT = re.compile(r"^(gpt-5|o[1-9])", re.I)


def _openai_body(model: str, system: str, user: str, limit_key: str) -> bytes:
    return json.dumps(
        {
            "model": model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            limit_key: 900,
        }
    ).encode()


def _call_openai(base_url: str, key: str, model: str, system: str, user: str) -> str:
    url = base_url.rstrip("/") + "/chat/completions"
    kopf = {"Content-Type": "application/json", "Authorization": f"Bearer {key}"}
    # Passenden Namen raten — und wenn der Anbieter widerspricht, den anderen nehmen.
    # Ein neues Modell soll nicht wieder alles lahmlegen, nur weil die Liste veraltet.
    erst = "max_completion_tokens" if _NEUES_LIMIT.match(model.strip()) else "max_tokens"
    dann = "max_tokens" if erst == "max_completion_tokens" else "max_completion_tokens"

    for versuch, limit_key in enumerate((erst, dann)):
        req = urllib.request.Request(url, data=_openai_body(model, system, user, limit_key), headers=kopf)
        try:
            with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
                data = json.load(r)
            break
        except urllib.error.HTTPError as e:
            detail = e.read().decode(errors="replace")[:300]
            # Genau dieser Fehler ist heilbar: der Anbieter will den anderen Namen.
            heilbar = (
                e.code == 400 and versuch == 0 and "max_tokens" in detail and "unsupported" in detail.lower()
            )
            if heilbar:
                continue
            raise LLMError(f"Anbieter antwortete {e.code}: {detail}") from e
        except OSError as e:
            raise LLMError(f"Anbieter nicht erreichbar: {e}") from e

    try:
        return data["choices"][0]["message"]["content"].strip()
    except (KeyError, IndexError) as e:
        raise LLMError("Unerwartete Antwort des Anbieters") from e


def _call_anthropic(key: str, model: str, system: str, user: str) -> str:
    try:
        import anthropic
    except ImportError as e:  # pragma: no cover
        raise LLMError("Paket 'anthropic' fehlt — bitte nachinstallieren.") from e

    client = anthropic.Anthropic(api_key=key)
    try:
        msg = client.messages.create(
            model=model,
            max_tokens=900,
            system=system,
            messages=[{"role": "user", "content": user}],
        )
    except anthropic.APIStatusError as e:
        raise LLMError(f"Claude antwortete {e.status_code}: {e.message}") from e
    except anthropic.APIConnectionError as e:
        raise LLMError(f"Claude nicht erreichbar: {e}") from e
    if msg.stop_reason == "refusal":
        raise LLMError("Claude hat die Anfrage abgelehnt.")
    return "".join(b.text for b in msg.content if b.type == "text").strip()


def ask(backend: dict, model: str, key: str, system: str, user: str) -> str:
    """Eine Frage an das konfigurierte Backend stellen."""
    api = backend.get("api", "openai")
    if api == "anthropic":
        return _call_anthropic(key, model, system, user)
    base = backend.get("base_url")
    if not base:
        raise LLMError("Für dieses Backend ist keine base_url konfiguriert.")
    return _call_openai(base, key or "local", model, system, user)


EXPLAIN_SYSTEM = (
    "Du erklärst Knoten aus einem Wissensgraphen über ein Software-Projekt. "
    "Antworte auf Deutsch, klar und in ganzen Sätzen, für jemanden, der den Code nicht kennt. "
    "Struktur: 1) Was ist das, in einem Satz. 2) Wozu dient es im Projekt. "
    "3) Wie hängt es mit den Nachbarknoten zusammen. "
    "Erfinde nichts dazu — stütze dich nur auf die gegebenen Daten. Höchstens 180 Wörter."
)


def explain_prompt(project: str, node: str, graph_context: str) -> str:
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
    return f"Frage: {question}\n\nSuchbegriffe:"


def query_prompt(project: str, question: str, graph_context: str) -> str:
    return (
        f"Projekt: {project}\n"
        f"Frage: {question}\n\n"
        f"Relevante Knoten aus dem Wissensgraphen (BFS-Traversal):\n"
        f"```\n{graph_context[:13000]}\n```\n\n"
        f"Beantworte die Frage anhand dieser Knoten."
    )
