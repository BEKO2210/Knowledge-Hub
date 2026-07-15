"""Post-Run-40 Bug 3: Diagnostics-Warnungen für unerwartete Fehler sind quittierbar.

Der 500er selbst (typfremdes JSON auf /ui/api/secrets, Ref 5b8f0e8a) ist seit Run 14
durch api.common.json_object behoben und in test_api_vertrag.py dauerhaft abgesichert.
Hier steht der Rest des Auftrags: Warn-Zählung, Quittierung mit Audit-Spur, Robustheit
gegen kaputte Logzeilen, keine Secretwerte in Logs, parallele Schreibvorgänge.
"""

from __future__ import annotations

import json
import threading
import time

from conftest import TMP

ERRORS_LOG = TMP / "errors.log"
ACK_FILE = TMP / "errors_ack.json"


def _log_eintrag(ref: str, alter_s: int = 60, pfad: str = "/ui/api/secrets") -> str:
    zeit = time.strftime("%Y-%m-%dT%H:%M:%S+0000", time.gmtime(time.time() - alter_s))
    return json.dumps(
        {"zeit": zeit, "ref": ref, "methode": "POST", "pfad": pfad, "fehler": "X", "spur": "..."}
    )


def _errors_check(client, auth) -> dict:
    r = client.get("/ui/api/health", headers=auth)
    assert r.status_code == 200
    return next(c for c in r.json()["checks"] if c.get("id") == "errors")


import pytest


@pytest.fixture(autouse=True)
def _saubere_fehlerdaten():
    ERRORS_LOG.unlink(missing_ok=True)
    ACK_FILE.unlink(missing_ok=True)
    yield
    ERRORS_LOG.unlink(missing_ok=True)
    ACK_FILE.unlink(missing_ok=True)


def test_frischer_fehler_warnt_mit_referenz(client, auth, fresh_vault):
    ERRORS_LOG.write_text(_log_eintrag("abc12345") + "\n")
    c = _errors_check(client, auth)
    assert c["status"] == "warn"
    assert "abc12345" in c["detail"]
    assert c.get("id") == "errors"


def test_quittieren_entfernt_warnung_aber_nicht_das_log(client, auth, fresh_vault):
    ERRORS_LOG.write_text(_log_eintrag("abc12345") + "\n")
    vorher = ERRORS_LOG.read_text()

    r = client.post("/ui/api/errors/ack", headers=auth)
    assert r.status_code == 200
    assert r.json()["acked"] == 1

    assert _errors_check(client, auth)["status"] == "ok"
    assert ERRORS_LOG.read_text() == vorher, "errors.log darf durch Quittierung nicht verändert werden"
    audit = (TMP / "audit.log").read_text()
    assert "ERROR-ACK" in audit and "abc12345" in audit, "Quittierung muss im Audit nachvollziehbar sein"


def test_neuer_fehler_nach_quittierung_warnt_wieder(client, auth, fresh_vault):
    ERRORS_LOG.write_text(_log_eintrag("alt00001") + "\n")
    client.post("/ui/api/errors/ack", headers=auth)
    with ERRORS_LOG.open("a") as fh:
        fh.write(_log_eintrag("neu00002") + "\n")
    c = _errors_check(client, auth)
    assert c["status"] == "warn"
    assert "neu00002" in c["detail"]


def test_alte_fehler_zaehlen_nicht(client, auth, fresh_vault):
    ERRORS_LOG.write_text(_log_eintrag("uralt001", alter_s=90000) + "\n")  # > 24 h
    assert _errors_check(client, auth)["status"] == "ok"


def test_kaputte_logzeile_kippt_diagnose_nicht(client, auth, fresh_vault):
    ERRORS_LOG.write_text('{"zeit": "kaputt\n' + _log_eintrag("gut00001") + "\n" + "kein json\n")
    c = _errors_check(client, auth)
    assert c["status"] == "warn"
    assert "gut00001" in c["detail"]


def test_keine_secretwerte_in_logs(client, auth, fresh_vault):
    """Fehlerhafte UND erfolgreiche Secret-Requests dürfen den Wert nirgends protokollieren."""
    geheim = "SUPERGEHEIM-xyzzy-42!"
    client.post("/ui/api/secrets", headers=auth, json=[geheim])  # typfremd -> 400
    client.post("/ui/api/secrets", headers=auth, json={"name": "t1", "value": geheim})  # 200
    for f in (ERRORS_LOG, TMP / "audit.log"):
        if f.exists():
            assert geheim not in f.read_text(errors="replace"), f"Secretwert in {f.name}"


def test_typfremder_body_bleibt_400_und_landet_nicht_im_errors_log(client, auth, fresh_vault):
    """Regression Ref 5b8f0e8a: Liste als Body -> 400 mit Meldung, kein unerwarteter Fehler."""
    r = client.post("/ui/api/secrets", headers=auth, json=[1, 2])
    assert r.status_code == 400
    assert "error" in r.json()
    assert not ERRORS_LOG.exists() or ERRORS_LOG.stat().st_size == 0


def test_parallele_secret_schreibvorgaenge(client, auth, fresh_vault):
    """10 gleichzeitige Schreiber: keine 500er, Vault-Datei bleibt konsistent lesbar."""
    codes: list[int] = []

    def schreibe(i: int) -> None:
        r = client.post("/ui/api/secrets", headers=auth, json={"name": f"par-{i % 3}", "value": f"w{i}"})
        codes.append(r.status_code)

    threads = [threading.Thread(target=schreibe, args=(i,)) for i in range(10)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert all(c in (200, 201) for c in codes), codes
    r = client.get("/ui/api/secrets", headers=auth)
    namen = set(r.json()["secrets"]) if isinstance(r.json(), dict) else set(r.json())
    assert {"par-0", "par-1", "par-2"} <= {str(n) for n in namen} or len(namen) >= 3
