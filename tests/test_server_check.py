"""Post-Run-40 Nachtrag: Der Diagnose-Check „Server" muss die Blue-Green-Architektur kennen.

Vorher prüfte er nur die alte Einzel-Unit knowledge-mcp — seit dem Umzug (Run 28) ist die
bewusst inaktiv, und die Diagnose zeigte eine falsche Dauerwarnung mit einem Fix-Hinweis,
der im Blue-Green-Betrieb sogar schaden würde (Port-Kollision mit dem Entry-Socket).
"""

from __future__ import annotations

from api import system


def _mit_units(monkeypatch, zustand: dict[str, str]):
    echt = system._sysctl

    def fake(*args: str):
        if args[0] == "is-active" and args[1] in zustand:
            return 0, zustand[args[1]]
        return echt(*args)

    monkeypatch.setattr(system, "_sysctl", fake)


def _server_check(client, auth) -> dict:
    r = client.get("/ui/api/health", headers=auth)
    assert r.status_code == 200
    return next(c for c in r.json()["checks"] if c["name"] in ("Server",))


def test_bluegreen_aktiver_slot_ist_ok(client, auth, fresh_vault, monkeypatch):
    _mit_units(monkeypatch, {"kmcp-entry.socket": "active", "kmcp-blue": "inactive", "kmcp-green": "active"})
    c = _server_check(client, auth)
    assert c["status"] == "ok"
    assert "green" in c["detail"]
    assert "knowledge-mcp" not in c.get("fix", ""), (
        "Alt-Unit-Hinweis darf im Blue-Green-Betrieb nicht erscheinen"
    )


def test_bluegreen_ohne_slot_ist_fehler_mit_slot_hinweis(client, auth, fresh_vault, monkeypatch):
    _mit_units(
        monkeypatch, {"kmcp-entry.socket": "active", "kmcp-blue": "inactive", "kmcp-green": "inactive"}
    )
    c = _server_check(client, auth)
    assert c["status"] == "err"
    assert "kmcp-" in c.get("fix", "")


def test_bluegreen_beide_slots_warnen_single_writer(client, auth, fresh_vault, monkeypatch):
    _mit_units(monkeypatch, {"kmcp-entry.socket": "active", "kmcp-blue": "active", "kmcp-green": "active"})
    c = _server_check(client, auth)
    assert c["status"] == "warn"


def test_legacy_ohne_entry_socket_prueft_alte_unit(client, auth, fresh_vault, monkeypatch):
    _mit_units(
        monkeypatch,
        {"kmcp-entry.socket": "inactive", "knowledge-mcp": "active"},
    )
    c = _server_check(client, auth)
    assert c["status"] == "ok"
