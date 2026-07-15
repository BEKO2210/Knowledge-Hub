"""Run-022: Fehler-Injektion — der Hub degradiert sauber statt abzustürzen.

Beleg: ~/hub-audit/EVIDENCE/run-022/fault_probe.py (vor Fix: LLM HTML/leer/nicht-Objekt
→ JSONDecodeError/TypeError; kaputte Config → ParserError/AttributeError; kaputte
graph.json → JSONDecodeError — jeweils 500-Traceback).
"""

from __future__ import annotations

import io

import pytest

import config
import llm


class _FakeResp(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


# --- R22-1: unbrauchbare LLM-Antwort → LLMError -------------------------------
@pytest.mark.parametrize(
    "body",
    [
        b"<html><body>502 Bad Gateway</body></html>",  # HTML statt JSON
        b"",  # leere Antwort
        b'"nur ein string"',  # gültiges JSON, aber kein Objekt
        b"[]",  # Liste statt Objekt
        b'{"foo": 1}',  # Objekt ohne choices
    ],
)
def test_unbrauchbare_llm_antwort_wird_llmerror(monkeypatch, body):
    monkeypatch.setattr(llm.urllib.request, "urlopen", lambda req, timeout=0: _FakeResp(body))
    with pytest.raises(llm.LLMError):
        llm.ask({"api": "openai", "base_url": "http://x/v1"}, "gpt-4", "k", "sys", "user")


def test_llm_http_500_wird_llmerror(monkeypatch):
    def boom(req, timeout=0):
        raise llm.urllib.error.HTTPError(req.full_url, 500, "Server Error", {}, io.BytesIO(b"kaputt"))

    monkeypatch.setattr(llm.urllib.request, "urlopen", boom)
    with pytest.raises(llm.LLMError):
        llm.ask({"api": "openai", "base_url": "http://x/v1"}, "gpt-4", "k", "sys", "user")


def test_llm_timeout_wird_llmerror(monkeypatch):
    def slow(req, timeout=0):
        raise TimeoutError("timed out")  # Subklasse von OSError

    monkeypatch.setattr(llm.urllib.request, "urlopen", slow)
    with pytest.raises(llm.LLMError):
        llm.ask({"api": "openai", "base_url": "http://x/v1"}, "gpt-4", "k", "sys", "user")


# --- R22-2: kaputte Config → klarer ConfigError ------------------------------
# CONFIG_PATH auf eine Wegwerf-Datei zeigen lassen, damit die geteilte Test-config.yaml
# unangetastet bleibt (die autouse-Fixture stellt sie nicht wieder her).
def test_kaputtes_yaml_meldet_configerror(tmp_path, monkeypatch):
    cfg_file = tmp_path / "config.yaml"
    cfg_file.write_text("server: {port: 8300\n  kaputt: : :\n")
    monkeypatch.setattr(config, "CONFIG_PATH", cfg_file)
    with pytest.raises(config.ConfigError):
        config.load()


def test_config_ist_kein_objekt_meldet_configerror(tmp_path, monkeypatch):
    cfg_file = tmp_path / "config.yaml"
    cfg_file.write_text("- a\n- b\n")  # Top-Level-Liste
    monkeypatch.setattr(config, "CONFIG_PATH", cfg_file)
    with pytest.raises(config.ConfigError):
        config.load()


def test_leere_config_ist_ok(tmp_path, monkeypatch):
    cfg_file = tmp_path / "config.yaml"
    cfg_file.write_text("")  # leer → Defaults, kein Fehler
    monkeypatch.setattr(config, "CONFIG_PATH", cfg_file)
    cfg = config.load()
    assert isinstance(cfg, dict) and "mapping" in cfg


# --- R22-3: kaputte graph.json → sauber, kein 500 ----------------------------
@pytest.fixture
def projektordner():
    """Legt Projekte unter KNOWLEDGE_ROOT an und räumt sie danach wieder weg,
    damit sie keine anderen Tests (die _projects() scannen) beeinflussen."""
    import shutil

    from api.common import KNOWLEDGE_ROOT

    angelegt = []

    def anlegen(name: str, text: str):
        gdir = KNOWLEDGE_ROOT / name / "graphify-out"
        gdir.mkdir(parents=True, exist_ok=True)
        (gdir / "graph.json").write_text(text)
        angelegt.append(KNOWLEDGE_ROOT / name)

    yield anlegen
    for d in angelegt:
        shutil.rmtree(d, ignore_errors=True)


def test_kaputte_graphjson_kein_500(client, auth, projektordner):
    projektordner("kaputt", '{"nodes": [')
    r = client.get("/ui/api/graph/kaputt", headers=auth)
    assert r.status_code != 500, r.text
    assert "nodes" in r.json()  # degradiert zu leerem/klar markiertem Graphen


def test_projektuebersicht_ueberlebt_kaputten_graph(client, auth, projektordner):
    projektordner("gut", '{"nodes": [{"id": "a"}], "links": []}')
    projektordner("kaputt", "\x00 kein json")
    r = client.get("/ui/api/projects", headers=auth)
    assert r.status_code == 200, r.text
    namen = {p["project"] for p in r.json()}
    assert {"gut", "kaputt"} <= namen  # beide gelistet, keiner reißt die Liste ab
