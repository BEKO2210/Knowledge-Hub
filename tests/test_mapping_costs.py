"""Kosten-/Preis-Verbuchung des Nacht-Mappings (Mapping-Kampagne, Befund M-1).

Der eigene Extraktor (extraction.py) löste graphify als Standard ab, meldete aber keine
Tokens/Kosten — die OpenAI-Antwort enthält `usage`, llm.py warf sie weg. Dadurch verbuchte
die Mapping-Kostenanzeige jeden aktuellen Lauf als $0. Fix: usage erfassen (llm.ask),
Preis aus config.yaml (config.model_price), Kostenzeile im Parser-Format ausgeben.
"""

from __future__ import annotations

import re

import config
import llm
from api import mapping

_CFG = {
    "mapping": {
        "backends": {
            "openai": {
                "models": [
                    {"id": "gpt-4.1", "hint": "stark · $2.00/$8.00"},
                    {"id": "gpt-4.1-mini", "hint": "empfohlen · $0.40/$1.60"},
                    {"id": "gpt-5", "hint": "am stärksten · $1.25/$10.00"},
                ]
            },
            "claude": {"models": [{"id": "claude-sonnet-5", "hint": "empfohlen · $3.00/$15.00"}]},
            "ollama": {"models": [{"id": "qwen2.5-coder:7b", "hint": "kostenlos, aber langsam"}]},
        }
    }
}


def test_model_price_aus_config_hints():
    assert config.model_price("gpt-4.1", _CFG) == (2.0, 8.0)
    assert config.model_price("gpt-4.1-mini", _CFG) == (0.4, 1.6)
    assert config.model_price("gpt-5", _CFG) == (1.25, 10.0)
    assert config.model_price("claude-sonnet-5", _CFG) == (3.0, 15.0)
    # Ollama (kostenlos, kein $-Hinweis) und Unbekanntes → gratis
    assert config.model_price("qwen2.5-coder:7b", _CFG) == (0.0, 0.0)
    assert config.model_price("gibt-es-nicht", _CFG) == (0.0, 0.0)


def test_ask_akkumuliert_usage_und_bleibt_ohne_param_textkompatibel(monkeypatch):
    monkeypatch.setattr(llm, "_call_openai", lambda *a, **k: ("TEXT", {"in": 100, "out": 40}))
    be = {"api": "openai", "base_url": "x"}
    acc: dict = {}
    assert llm.ask(be, "gpt-4.1", "k", "s", "u", usage=acc) == "TEXT"
    assert llm.ask(be, "gpt-4.1", "k", "s", "u", usage=acc) == "TEXT"
    assert acc == {"in": 200, "out": 80, "calls": 2}
    # Ohne usage-Param: unveränderte Rückgabe (Chat/Explain-Aufrufer bleiben heil)
    assert llm.ask(be, "gpt-4.1", "k", "s", "u") == "TEXT"


def _kostenzeile(model: str, tin: int, tout: int, price=(2.0, 8.0)) -> str:
    """Baut die Zeilen, die extraction.py main() ausgibt (identisches Format)."""
    cost = tin / 1_000_000 * price[0] + tout / 1_000_000 * price[1]
    label = model.replace(":", "-")
    return f"[hub-extract] proj: tokens: {tin:,} in / {tout:,} out\n[hub-extract] proj: est. cost {label}: ${cost:.4f}\n"


def test_extraktor_kostenformat_wird_vom_parser_erkannt():
    text = "--- /home/belkis/proj\n" + _kostenzeile("gpt-4.1", 362486, 170890) + "nightly-map done\n"
    parsed = mapping._parse_run(text)
    assert parsed["tokens_in"] == 362486
    assert parsed["tokens_out"] == 170890
    # 362486/1e6*2 + 170890/1e6*8 = 0.724972 + 1.36712 = 2.0921 (gerundet 4 Stellen)
    assert parsed["cost"] == round(362486 / 1e6 * 2.0 + 170890 / 1e6 * 8.0, 4)
    assert parsed["cost"] > 0


def test_ollama_label_mit_doppelpunkt_bricht_den_parser_nicht():
    # Sanitiertes Label (":" -> "-") bleibt für den Parser lesbar; Kosten 0 (gratis).
    line = _kostenzeile("qwen2.5-coder:7b", 5000, 2000, price=(0.0, 0.0))
    assert "est. cost qwen2.5-coder-7b: $0.0000" in line
    parsed = mapping._parse_run("--- /home/belkis/p\n" + line)
    assert parsed["tokens_in"] == 5000 and parsed["cost"] == 0.0
    # Gegenprobe: ein roher Doppelpunkt im Label würde die cost-Regex verfehlen
    assert not re.search(r"est\. cost [^:]*: \$", "est. cost qwen:7b: $0.0000")
