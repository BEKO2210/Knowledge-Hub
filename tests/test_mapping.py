"""Nacht-Mapping: die oneshot-„activating"-Falle und der Log-Parser."""

from __future__ import annotations

import pytest

from api import mapping

LOG = """=== nightly-map start 2026-07-10T03:30:00+00:00 backend=openai model=gpt-4.1-mini ===
--- /srv/projects/payments-api (2026-07-10T03:30:01+00:00)
[graphify extract] wrote /srv/projects/payments-api/graphify-out/graph.json: 120 nodes, 340 edges
  est. cost (gpt-4.1-mini): $0.0210
  tokens: 12,000 in / 3,400 out
--- /srv/projects/web-storefront (2026-07-10T03:32:00+00:00)
[graphify extract] wrote /srv/projects/web-storefront/graphify-out/graph.json: 80 nodes, 150 edges
  est. cost (gpt-4.1-mini): $0.0090
--- /opt/lumo (2026-07-10T03:34:00+00:00)
extract FEHLGESCHLAGEN: /opt/lumo
=== nightly-map done 2026-07-10T03:36:00+00:00 ===
"""

LOG_ZWEITER_LAUF = """=== nightly-map start 2026-07-11T03:30:00+00:00 backend=openai model=gpt-4.1-mini ===
--- /srv/projects/payments-api (2026-07-11T03:30:01+00:00)
[graphify extract] wrote /srv/projects/payments-api/graphify-out/graph.json: 130 nodes, 350 edges
=== nightly-map done 2026-07-11T03:33:00+00:00 ===
"""


# --- die oneshot-Falle ---------------------------------------------------------
@pytest.mark.parametrize("zustand,laeuft", [
    ("active", True),
    ("activating", True),   # <- die Falle: oneshot meldet das, WÄHREND es läuft
    ("inactive", False),
    ("failed", False),
])
def test_oneshot_activating_gilt_als_laufend(client, auth, fresh_vault, monkeypatch, zustand, laeuft):
    """Ein Type=oneshot-Dienst ist während des Laufs „activating", nicht „active".

    Wer nur auf „active" prüft, hält einen laufenden Nacht-Lauf für beendet — und
    startet ihn ein zweites Mal parallel.
    """
    monkeypatch.setattr(mapping, "_sysctl", lambda *a: (0, zustand if a[0] == "is-active" else ""))
    r = client.get("/ui/api/mapping/status", headers=auth)
    assert r.status_code == 200
    assert r.json()["running"] is laeuft


def test_zweiter_start_waehrend_des_laufs_wird_abgelehnt(client, auth, fresh_vault, monkeypatch):
    monkeypatch.setattr(mapping, "_sysctl", lambda *a: (0, "activating"))
    r = client.post("/ui/api/mapping/run", headers=auth)
    assert r.status_code == 409, "Doppelstart muss verhindert werden"


def test_start_wenn_nichts_laeuft(client, auth, fresh_vault, monkeypatch):
    monkeypatch.setattr(mapping, "_sysctl", lambda *a: (0, "inactive"))
    r = client.post("/ui/api/mapping/run", headers=auth)
    assert r.status_code == 200


# --- Log-Parser ----------------------------------------------------------------
def _schreibe_logs(tmp, *inhalte):
    d = tmp / "build-logs"
    d.mkdir(exist_ok=True)
    for i, inhalt in enumerate(inhalte):
        (d / f"nightly-2026-07-{10 + i}.log").write_text(inhalt)
    return d


def test_parser_liest_lauf_korrekt(monkeypatch, tmp_path):
    monkeypatch.setattr(mapping, "NIGHTLY_LOG_DIR", _schreibe_logs(tmp_path, LOG))
    laeufe = mapping._parse_runs()
    assert len(laeufe) == 1
    lauf = laeufe[0]
    assert lauf["duration_s"] == 360           # 03:30:00 -> 03:36:00
    assert lauf["model"] == "gpt-4.1-mini"
    assert round(lauf["cost"], 4) == 0.03      # 0.0210 + 0.0090
    assert lauf["nodes_total"] == 200          # 120 + 80
    assert lauf["tokens_in"] == 12000 and lauf["tokens_out"] == 3400
    assert lauf["failed"] == 1
    assert lauf["failed_names"] == ["lumo"]
    assert lauf["project_count"] == 3


def test_parser_erkennt_knoten_zuwachs_zum_vorlauf(monkeypatch, tmp_path):
    """Der Zuwachs gegenüber dem Vorlauf ist die eigentliche Aussage der Historie."""
    monkeypatch.setattr(mapping, "NIGHTLY_LOG_DIR",
                        _schreibe_logs(tmp_path, LOG, LOG_ZWEITER_LAUF))
    laeufe = mapping._parse_runs()
    assert len(laeufe) == 2
    neuester = max(laeufe, key=lambda r: r["start"])
    assert neuester["nodes_total"] == 130
    # elementa wuchs von 120 auf 130 Knoten
    elementa = next(p for p in neuester["projects"] if p["name"] == "payments-api")
    assert elementa["delta"] == 10


def test_parser_stolpert_nicht_ueber_muell(monkeypatch, tmp_path):
    """Ein abgeschnittenes oder leeres Log darf die Oberfläche nicht zerlegen."""
    monkeypatch.setattr(mapping, "NIGHTLY_LOG_DIR",
                        _schreibe_logs(tmp_path, "", "=== nightly-map start kaputt ==="))
    assert mapping._parse_runs() == [] or isinstance(mapping._parse_runs(), list)


def test_historie_ueber_http(client, auth, fresh_vault, monkeypatch, tmp_path):
    monkeypatch.setattr(mapping, "NIGHTLY_LOG_DIR", _schreibe_logs(tmp_path, LOG))
    r = client.get("/ui/api/mapping/history", headers=auth)
    assert r.status_code == 200
    assert len(r.json()["runs"]) == 1


# --- Fehlerarten unterscheiden -------------------------------------------------
LOG_MIT_SICHERUNGSFEHLER = """=== nightly-map start 2026-07-12T03:30:00+00:00 backend=openai model=gpt-4.1-mini ===
--- /srv/projects/payments-api (2026-07-12T03:30:01+00:00)
[graphify extract] wrote /srv/projects/payments-api/graphify-out/graph.json: 130 nodes, 350 edges
--- Sicherung (2026-07-12T03:31:00+00:00)
SICHERUNG FEHLGESCHLAGEN
=== nightly-map done 2026-07-12T03:32:00+00:00 ===
"""


def test_sicherungsfehler_ist_kein_projektfehler(monkeypatch, tmp_path):
    """Die Sicherung trägt keinen Projektnamen — früher erschien sie als „1 Fehler ?".

    Ein gescheitertes Projekt repariert man anders als eine gescheiterte Sicherung;
    die Oberfläche muss beides auseinanderhalten können.
    """
    monkeypatch.setattr(mapping, "NIGHTLY_LOG_DIR",
                        _schreibe_logs(tmp_path, LOG_MIT_SICHERUNGSFEHLER))
    lauf = mapping._parse_runs()[0]
    assert lauf["backup_failed"] is True
    assert lauf["failed"] == 0, "Die Sicherung ist KEIN Projektfehler"
    assert lauf["failed_names"] == []
    assert "?" not in str(lauf["failed_names"])


def test_projektfehler_behaelt_namen_und_art(monkeypatch, tmp_path):
    monkeypatch.setattr(mapping, "NIGHTLY_LOG_DIR", _schreibe_logs(tmp_path, LOG))
    lauf = mapping._parse_runs()[0]
    assert lauf["backup_failed"] is False
    assert lauf["failed"] == 1
    assert lauf["failures"] == [{"project": "lumo", "kind": "extract"}]


def test_lauf_laesst_sich_abhaken_und_wieder_oeffnen(client, auth, fresh_vault, monkeypatch, tmp_path):
    """Wer die Ursache behoben hat, muss die Warnung loswerden können — ohne dass
    der Eintrag selbst verschwindet (der Lauf ist eine Tatsache)."""
    monkeypatch.setattr(mapping, "NIGHTLY_LOG_DIR", _schreibe_logs(tmp_path, LOG))
    monkeypatch.setattr(mapping, "DISMISSED_FILE", tmp_path / "dismissed.json")

    lauf = client.get("/ui/api/mapping/history", headers=auth).json()["runs"][0]
    assert lauf["dismissed"] is False
    start = lauf["start"]

    r = client.post("/ui/api/mapping/history/dismiss", headers=auth,
                    json={"start": start, "dismissed": True})
    assert r.status_code == 200
    runs = client.get("/ui/api/mapping/history", headers=auth).json()["runs"]
    assert runs[0]["dismissed"] is True
    assert runs[0]["failed"] == 1, "Der Fehler bleibt sichtbar — er mahnt nur nicht mehr"

    client.post("/ui/api/mapping/history/dismiss", headers=auth,
                json={"start": start, "dismissed": False})
    assert client.get("/ui/api/mapping/history", headers=auth).json()["runs"][0]["dismissed"] is False


def test_abhaken_ohne_lauf_ist_ein_400(client, auth, fresh_vault):
    r = client.post("/ui/api/mapping/history/dismiss", headers=auth, json={})
    assert r.status_code == 400
