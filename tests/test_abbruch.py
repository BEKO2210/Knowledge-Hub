"""D7 — Belastung und Abbruch: Was passiert, wenn etwas mittendrin stirbt.

Der Normalfall ist getestet. Hier geht es um den Abbruch: ein Werkzeug, das fehlt,
eine Zeitüberschreitung, ein Thread, der stirbt. Genau dort entstehen die Zustände,
aus denen ein System sich nicht mehr von selbst befreit.
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

import pytest
from conftest import TMP

import server

WEB = Path(__file__).resolve().parent.parent / "web"


@pytest.fixture(autouse=True)
def builds_leeren():
    server._builds.clear()
    yield
    server._builds.clear()


def _warte_auf_ende(name: str, sekunden: float = 20.0) -> dict:
    import time

    frist = time.time() + sekunden
    while time.time() < frist:
        with server._builds_lock:
            b = dict(server._builds.get(name, {}))
        if b.get("status") not in ("running",):
            return b
        time.sleep(0.1)
    return {"status": "running (Zeitüberschreitung im Test)"}


# ---------------------------------------------------------------------------
# D7-Regression: ein sterbender Build-Thread fror den Status für immer ein
# ---------------------------------------------------------------------------
# `_build_worker` hatte keine Fehlerbehandlung. Fiel graphify-sync aus (Binary fehlt,
# Zeitüberschreitung, volle Platte), starb der Thread still. Der Status blieb auf
# „running“ — und graph_build weigerte sich ab da FÜR IMMER, dieses Projekt zu bauen
# („build is already running“). Nur ein Serverneustart holte es zurück.
def _mini_graph(projekt_dir):
    """Seit dem Build-Vertrag (Run 7) gehört zu einem erfolgreichen Lauf eine graph.json —
    ohne sie ist ein Build zu Recht 'failed'. Erfolgs-Szenarien brauchen daher eine."""
    out = projekt_dir / "graphify-out"
    out.mkdir(parents=True, exist_ok=True)
    (out / "graph.json").write_text('{"nodes": [{"id": "a"}], "links": []}', encoding="utf-8")


def test_fehlendes_werkzeug_endet_als_failed(monkeypatch, tmp_path):
    monkeypatch.setattr(server, "GRAPHIFY_BIN", "/bin/true")
    monkeypatch.setattr(server, "GRAPHIFY_SYNC", str(TMP / "gibt-es-nicht"))
    monkeypatch.setattr(server, "BUILD_LOG_DIR", tmp_path / "logs")
    # Extraktion + Clustering neutralisieren → das _mini_graph-Fixture überlebt
    monkeypatch.setattr(server, "EXTRACTION_BIN", "/bin/true")
    monkeypatch.setattr(server, "CLUSTER_BIN", "/bin/true")
    _mini_graph(tmp_path)

    server._builds["p"] = {"status": "running", "started": 0, "finished": None}
    server._build_worker("p", tmp_path)

    b = server._builds["p"]
    assert b["status"] == "failed", "Ein toter Arbeits-Thread darf den Status nicht einfrieren"
    assert b["finished"], "Ein Endzustand braucht einen Zeitstempel"
    assert "konnte nicht ausgeführt werden" in (b.get("error") or ""), (
        "Der Grund muss beim Nutzer ankommen, nicht nur im Serverlog"
    )


def test_zeitueberschreitung_endet_als_failed(monkeypatch, tmp_path):
    def haengt(*a, **k):
        raise subprocess.TimeoutExpired(cmd="graphify", timeout=1800)

    monkeypatch.setattr(server.subprocess, "run", haengt)
    monkeypatch.setattr(server, "BUILD_LOG_DIR", tmp_path / "logs")

    server._builds["p"] = {"status": "running", "started": 0, "finished": None}
    server._build_worker("p", tmp_path)

    assert server._builds["p"]["status"] == "failed"
    assert "Zeitüberschreitung" in (server._builds["p"].get("error") or "")


def test_nach_fehlschlag_ist_ein_neuversuch_moeglich(monkeypatch, tmp_path):
    """Der eigentliche Schaden des alten Fehlers: Das Projekt war nie wieder baubar."""
    monkeypatch.setattr(server, "GRAPHIFY_BIN", "/bin/false")  # scheitert sofort
    monkeypatch.setattr(server, "BUILD_LOG_DIR", tmp_path / "logs")
    projekt = tmp_path / "kaputt"
    projekt.mkdir()
    monkeypatch.setattr(server, "_resolve_project_dir", lambda p: projekt)

    server.graph_build("kaputt")
    assert _warte_auf_ende("kaputt")["status"] == "failed"

    antwort = server.graph_build("kaputt")
    assert "already running" not in antwort, (
        "Nach einem Fehlschlag muss ein neuer Versuch starten dürfen — sonst ist das "
        "Projekt bis zum nächsten Serverneustart tot"
    )
    _warte_auf_ende("kaputt")


def test_erfolgreicher_lauf_endet_als_done(monkeypatch, tmp_path):
    monkeypatch.setattr(server, "GRAPHIFY_BIN", "/bin/true")
    monkeypatch.setattr(server, "GRAPHIFY_SYNC", "/bin/true")
    monkeypatch.setattr(server, "BUILD_LOG_DIR", tmp_path / "logs")
    # Extraktion + Clustering neutralisieren → das _mini_graph-Fixture überlebt
    monkeypatch.setattr(server, "EXTRACTION_BIN", "/bin/true")
    monkeypatch.setattr(server, "CLUSTER_BIN", "/bin/true")
    _mini_graph(tmp_path)

    server._builds["p"] = {"status": "running", "started": 0, "finished": None}
    server._build_worker("p", tmp_path)

    assert server._builds["p"]["status"] == "done"
    assert server._builds["p"]["error"] is None
    # Build-Vertrag: ein erfolgreicher Lauf hinterlässt ein konsistentes Manifest
    import buildmeta

    assert buildmeta.verify(tmp_path)["status"] == "ok"


def test_lauf_ohne_graph_endet_als_failed_mit_manifestgrund(monkeypatch, tmp_path):
    """Kein graph.json = keine Generation = kein Erfolg (Invariante aus Kap. 7)."""
    monkeypatch.setattr(server, "GRAPHIFY_BIN", "/bin/true")
    monkeypatch.setattr(server, "GRAPHIFY_SYNC", "/bin/true")
    monkeypatch.setattr(server, "BUILD_LOG_DIR", tmp_path / "logs")
    # Extraktion neutralisieren → es entsteht KEIN Graph (echter Leer-Lauf)
    monkeypatch.setattr(server, "EXTRACTION_BIN", "/bin/true")
    monkeypatch.setattr(server, "CLUSTER_BIN", "/bin/true")

    server._builds["p"] = {"status": "running", "started": 0, "finished": None}
    server._build_worker("p", tmp_path)

    assert server._builds["p"]["status"] == "failed"
    assert "Generation" in (server._builds["p"].get("error") or "")
    assert "graph.json fehlt" in (server._builds["p"].get("error") or "")


# ---------------------------------------------------------------------------
# D7-Regression: ein Abbruch ist kein Fehler
# ---------------------------------------------------------------------------
# Bricht der Browser eine laufende Anfrage ab (Seitenwechsel, Neuladen), warf fetch()
# einen AbortError — und die Oberfläche zeigte „Keine Verbindung zum Hub. Prüfe deine
# Internetverbindung.“ Der Nutzer bekam also eine Störungsmeldung dafür, dass er
# weitergeklickt hat.
def test_abbruch_zeigt_kein_verbindungsbanner():
    js = (WEB / "app.js").read_text(encoding="utf-8")

    fang = re.search(r"async function api\(.*?\n\}", js, re.S).group(0)
    assert "AbortError" in fang, (
        "api() muss den Abbruch erkennen und durchreichen, statt ein Verbindungsbanner zu zeigen"
    )
    # Die Erkennung muss VOR dem showError stehen, sonst hilft sie nichts.
    # (Auf den Aufruf prüfen, nicht auf den Meldungstext — der steht auch im Kommentar.)
    zeigt_banner = fang.index("showError(t('Keine Verbindung zum Hub")
    assert fang.index("AbortError") < zeigt_banner

    netz = re.search(r"window\.addEventListener\('unhandledrejection'.*?\n\}\);", js, re.S).group(0)
    assert "AbortError" in netz, "Auch das Auffangnetz darf für einen Abbruch kein Banner zeigen"
