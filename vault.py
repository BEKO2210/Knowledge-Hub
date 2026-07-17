"""Verschlüsselter Secrets-Vault (Format v2).

**Zwei-Schichten-Modell**

    Passwort ──scrypt──┐
                       ├──► entpackt ──► Hauptschlüssel (MK) ──► entschlüsselt die Secrets
    VAULT_KEY (env) ───┘        (optional, für den unbeaufsichtigten Betrieb)

Die Secrets sind mit einem zufälligen **Hauptschlüssel** verschlüsselt (AES-256-GCM).
Dieser Hauptschlüssel liegt selbst nur *verpackt* auf der Platte — in zwei Varianten:

  * **Passwort-Verpackung** (immer vorhanden): scrypt(Zugangspasswort) entpackt ihn.
    Damit ist das Passwort nirgends gespeichert — ein erfolgreiches Entpacken *ist* der Beweis,
    dass es stimmt.
  * **Env-Verpackung** (optional, Standard AN): der Schlüssel aus `VAULT_KEY` entpackt ihn.
    Nur dafür da, dass der Server nach einem Neustart ohne Menschen weiterarbeiten kann
    (Nacht-Mapping braucht den API-Key). Wer maximale Sicherheit will, schaltet sie ab —
    dann bleibt der Vault nach jedem Neustart gesperrt, bis sich jemand anmeldet.

Gegenüber v1 (nackter Schlüssel + Klartext-Passwort in `env`) gewonnen:
  * Das Zugangspasswort steht nirgendwo mehr im Klartext.
  * Ohne Env-Verpackung schützt der Vault auch gegen ein übernommenes Server-Konto.
  * Passwort ändern, ohne die Secrets neu zu verschlüsseln (nur die Verpackung wird getauscht).

v1-Vaults werden beim ersten Zugriff automatisch migriert (mit Sicherheitskopie).
"""

from __future__ import annotations

import base64
import fcntl
import json
import os
import re
import secrets
import tempfile
import threading
import time
from contextlib import contextmanager
from pathlib import Path

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.scrypt import Scrypt

VAULT_PATH = Path(os.environ.get("VAULT_PATH", str(Path.home() / "knowledge-mcp" / "vault.enc")))
AUDIT_PATH = VAULT_PATH.with_name("audit.log")
LOCK_PATH = VAULT_PATH.with_name("vault.lock")

# Interne Secrets: gehören der Anwendung, nicht dem Nutzer. Der 2FA-Seed ist das
# zweite Anmeldemerkmal — wer ihn lesen kann, umgeht die Zwei-Faktor-Anmeldung; wer
# ihn löschen kann, schaltet sie ab. Weder das eine noch das andere darf über einen
# verbundenen KI-Client gehen. Die Oberfläche verbarg ihn schon, die MCP-Werkzeuge nicht.
HIDDEN_SECRETS = {"__2fa__"}

# Erlaubte Secret-Namen. Die Regel stand bisher nur in der Weboberfläche — über MCP ließ
# sich „böse/../name@!" ablegen, was danach in der Oberfläche nicht mehr löschbar war
# (der Name steckt dort im Pfad). Jetzt gilt sie für jeden Weg in den Vault.
SECRET_NAME_RE = re.compile(r"^[\w.\- ]{1,64}$")

# Wertgrenze ebenfalls hier, nicht in der Oberfläche: Der Vault wird bei jedem Zugriff
# komplett entschlüsselt und neu geschrieben — ein einzelner Riesenwert (über MCP gab es
# keine Grenze) macht JEDEN späteren Secret-Zugriff langsam, nicht nur den eigenen.
SECRET_VALUE_MAX = 20_000

_RLOCK = threading.RLock()
_TX = threading.local()  # Tiefe der verschachtelten Transaktion je Thread (Reentranz)

_AAD = b"knowledge-mcp:vault:v1"  # v1-Daten (Migration)
_AAD_DATA = b"knowledge-hub:vault:data"  # v2-Nutzdaten
_AAD_WRAP = b"knowledge-hub:vault:wrap"  # v2-Schlüsselverpackung

# scrypt: bewusst teuer (~100 ms, 64 MB) — macht Rateangriffe auf das Passwort unattraktiv.
SCRYPT_N, SCRYPT_R, SCRYPT_P = 2**16, 8, 1

_b64 = lambda b: base64.b64encode(b).decode()  # noqa: E731
_unb64 = lambda s: base64.b64decode(s)  # noqa: E731

# Der entpackte Hauptschlüssel lebt nur im Arbeitsspeicher.
_mk: bytes | None = None


class VaultLocked(RuntimeError):
    """Der Vault ist gesperrt — es muss erst entsperrt werden (Anmeldung)."""


class VaultCorrupt(VaultLocked):
    """Die Vault-Datei ist beschädigt (kaputtes JSON oder nicht entschlüsselbar).

    Unterklasse von VaultLocked, damit ein beschädigter Vault überall dort, wo
    ohnehin ‚Vault nicht verfügbar' behandelt wird, sauber greift — statt als
    nackter JSONDecodeError/InvalidTag bis in einen 500-Traceback durchzuschlagen."""


# ---------------------------------------------------------------------------
# Schlüsselableitung / Verpackung
# ---------------------------------------------------------------------------
def _derive(password: str, salt: bytes) -> bytes:
    return Scrypt(salt=salt, length=32, n=SCRYPT_N, r=SCRYPT_R, p=SCRYPT_P).derive(password.encode())


def _wrap(key: bytes, mk: bytes) -> dict:
    nonce = secrets.token_bytes(12)
    return {"nonce": _b64(nonce), "ct": _b64(AESGCM(key).encrypt(nonce, mk, _AAD_WRAP))}


def _unwrap(key: bytes, wrap: dict) -> bytes:
    return AESGCM(key).decrypt(_unb64(wrap["nonce"]), _unb64(wrap["ct"]), _AAD_WRAP)


def _env_key() -> bytes | None:
    raw = os.environ.get("VAULT_KEY", "")
    if not raw:
        return None
    try:
        key = base64.b64decode(raw)
    except ValueError:
        # Tippfehler in der Umgebung (ungültiges Base64; binascii.Error ist eine
        # ValueError-Unterklasse): wie „kein Schlüssel" behandeln — die Aufrufer
        # (status, init, set_auto_unlock, unlock_env) liefern dann ihren normalen
        # Kein-Schlüssel-/VaultLocked-Pfad, statt mit einem 500-Crash auszusteigen.
        return None
    return key if len(key) == 32 else None


# ---------------------------------------------------------------------------
# Datei lesen/schreiben
# ---------------------------------------------------------------------------
def _read_file() -> dict | None:
    if not VAULT_PATH.exists():
        return None
    raw = VAULT_PATH.read_bytes()
    if raw[:1] == b"{":
        try:
            return json.loads(raw)
        except (json.JSONDecodeError, UnicodeDecodeError) as e:
            # Beschädigte Datei (z. B. Torn-Write, halb überspielte Sicherung, Müll-
            # Bytes statt UTF-8): sauber melden statt als roher JSONDecodeError/
            # UnicodeDecodeError einen 500-Traceback (oder — schlimmer — eine 400
            # „kein gültiges JSON") zu erzeugen.
            raise VaultCorrupt(f"Vault-Datei ist beschädigt (kein gültiges JSON): {e}") from e
    return {"version": 1, "raw": raw}  # altes Format


def _ensure_dir() -> None:
    """Vault-Verzeichnis bei Bedarf anlegen.

    Bei der Ersteinrichtung auf Bare-Metal/systemd existiert das Verzeichnis
    (Standard: ~/knowledge-mcp) vor dem ersten Schreiben noch nicht — ohne das
    Anlegen crashte init() mit einem FileNotFoundError und die Einrichtung
    verklemmte (env schon geschrieben, Vault fehlt, Retry crasht erneut).
    """
    VAULT_PATH.parent.mkdir(parents=True, exist_ok=True)


def _write_file(doc: dict) -> None:
    """Vault atomar ersetzen.

    Die Zwischendatei bekommt einen EIGENEN Namen pro Schreibvorgang. Vorher hieß sie
    immer „vault.tmp": Schrieben zwei Aufrufe gleichzeitig (zwei MCP-Clients, Oberfläche
    + Nacht-Job), benutzten beide dieselbe Datei — der Schnellere schob sie mit replace()
    weg, der Langsamere fiel danach über ein `FileNotFoundError: vault.tmp` und sein
    Secret war verloren. Ein eindeutiger Name pro Schreibvorgang kann nicht kollidieren.
    """
    _ensure_dir()
    fd, pfad = tempfile.mkstemp(dir=VAULT_PATH.parent, prefix=".vault-", suffix=".tmp")
    tmp = Path(pfad)
    try:
        with os.fdopen(fd, "w") as fh:
            json.dump(doc, fh, indent=1)
            fh.flush()
            os.fsync(fh.fileno())  # erst auf die Platte, dann umbenennen
        tmp.chmod(0o600)
        os.replace(tmp, VAULT_PATH)
    except BaseException:
        tmp.unlink(missing_ok=True)
        raise


@contextmanager
def _transaktion():
    """Eine Änderung am Vault: Lesen, Ändern, Schreiben — ohne dass jemand dazwischenfunkt.

    Zwei Sperren, weil es zwei Arten von Nebenläufigkeit gibt:
      * `_RLOCK` hält gleichzeitige Anfragen im selben Prozess auseinander (mehrere
        MCP-Clients, Oberfläche und Werkzeug gleichzeitig).
      * die Dateisperre hält andere PROZESSE auseinander (der Nacht-Job, ein zweiter
        Serverstart, `backup.py`). Ein Thread-Lock allein hilft dort nicht.

    Ohne das ging bei parallelen Aufrufen die letzte Änderung verloren: Alle lasen
    denselben Stand, alle schrieben ihren eigenen zurück, und wer zuletzt schrieb,
    löschte die Secrets der anderen.

    **Reentrant:** Ein Aufrufer kann mehrere Secret-Operationen (z. B. Lesen +
    Zurückschreiben desselben Blobs, wie es totp für den 2FA-Zustand braucht) in
    EINE Transaktion klammern — die inneren secret_get/secret_set-Aufrufe re-betreten
    dieselbe Sperre, statt eine zweite Dateisperre auf einem zweiten Deskriptor zu
    ziehen (das würde im selben Thread verklemmen). Gezählt wird die Tiefe pro Thread;
    die flock wird nur auf Ebene 0 genommen und wieder freigegeben.
    """
    with _RLOCK:
        depth = getattr(_TX, "depth", 0)
        if depth == 0:
            _ensure_dir()  # vault.lock liegt neben der vault.enc
            LOCK_PATH.touch(exist_ok=True)
            fh = LOCK_PATH.open("r+")
            fcntl.flock(fh, fcntl.LOCK_EX)
            _TX.fh = fh
        _TX.depth = depth + 1
        try:
            yield
        finally:
            _TX.depth -= 1
            if _TX.depth == 0:
                try:
                    fcntl.flock(_TX.fh, fcntl.LOCK_UN)
                finally:
                    _TX.fh.close()
                    _TX.fh = None


# Öffentlicher Name für Module, die mehrere Secret-Operationen atomar zusammenfassen
# müssen (totp: den 2FA-Blob als Ganzes lesen-ändern-schreiben, ohne Zwischenfunker).
def transaction():
    return _transaktion()


def _new_vault(password: str, mk: bytes | None = None, secrets_map: dict | None = None) -> dict:
    """Frischen v2-Vault bauen (mit Passwort-Verpackung, optional Env-Verpackung)."""
    mk = mk or secrets.token_bytes(32)
    salt = secrets.token_bytes(16)
    doc = {
        "version": 2,
        "created": int(time.time()),
        "wraps": {
            "password": {
                "salt": _b64(salt),
                "n": SCRYPT_N,
                "r": SCRYPT_R,
                "p": SCRYPT_P,
                **_wrap(_derive(password, salt), mk),
            }
        },
    }
    ek = _env_key()
    if ek:
        doc["wraps"]["env"] = _wrap(ek, mk)  # unbeaufsichtigter Betrieb bleibt möglich
    _write_data(doc, mk, secrets_map or {})
    return doc


def _write_data(doc: dict, mk: bytes, store: dict) -> None:
    nonce = secrets.token_bytes(12)
    ct = AESGCM(mk).encrypt(nonce, json.dumps(store).encode(), _AAD_DATA)
    doc["data"] = {"nonce": _b64(nonce), "ct": _b64(ct)}


def _read_data(doc: dict, mk: bytes) -> dict:
    d = doc.get("data")
    if not d:
        return {}
    try:
        pt = AESGCM(mk).decrypt(_unb64(d["nonce"]), _unb64(d["ct"]), _AAD_DATA)
        return json.loads(pt)
    except (InvalidTag, ValueError, KeyError, json.JSONDecodeError) as e:
        # Datenblock nicht entschlüsselbar/lesbar, obwohl der Schlüssel stimmt:
        # die Datei ist beschädigt oder manipuliert — sauber melden.
        raise VaultCorrupt(f"Vault-Datenblock ist beschädigt: {type(e).__name__}") from e


# ---------------------------------------------------------------------------
# Migration v1 -> v2
# ---------------------------------------------------------------------------
def _migrate_v1(doc: dict) -> dict:
    """Alten Vault (nackter Schlüssel) in das Zwei-Schichten-Format überführen."""
    ek = _env_key()
    password = os.environ.get("OAUTH_PASSWORD", "")
    if not ek:
        raise VaultLocked("Alter Vault, aber kein VAULT_KEY in der Umgebung — Migration unmöglich.")
    blob = doc["raw"]
    try:
        store = json.loads(AESGCM(ek).decrypt(blob[:12], blob[12:], _AAD))
    except (InvalidTag, ValueError, KeyError, json.JSONDecodeError) as e:
        # Kein gültiger v1-Vault (Müll/abgeschnitten): nicht als Migration versuchen.
        raise VaultCorrupt(f"Vault-Datei ist beschädigt (kein lesbarer v1-Inhalt): {type(e).__name__}") from e

    backup = VAULT_PATH.with_name(f"vault.enc.v1-{time.strftime('%Y%m%d-%H%M%S')}")
    backup.write_bytes(blob)
    backup.chmod(0o600)

    if not password:
        # Ohne bekanntes Passwort können wir keine Passwort-Verpackung anlegen.
        # Dann bleibt es beim Env-Schlüssel (Sicherheitsniveau wie v1).
        new = {"version": 2, "created": int(time.time()), "wraps": {"env": _wrap(ek, ek)}}
        _write_data(new, ek, store)
        _write_file(new)
        audit("VAULT-MIGRATE", "v1->v2 (nur Env-Schlüssel)", client="system")
        return new

    new = _new_vault(password, mk=secrets.token_bytes(32), secrets_map=store)
    _write_file(new)
    audit("VAULT-MIGRATE", f"v1->v2, Sicherung {backup.name}", client="system")
    return new


def _doc() -> dict:
    doc = _read_file()
    if doc is None:
        raise VaultLocked("Kein Vault vorhanden.")
    if isinstance(doc, dict) and doc.get("version") == 1:
        if not isinstance(doc.get("raw"), bytes):
            raise VaultCorrupt("Vault-Datei ist beschädigt (v1 ohne Datenblock).")
        # Die Migration SCHREIBT die Vault-Datei — sie gehört unter dieselbe Sperre
        # wie jede andere Änderung, sonst migrieren zwei Prozesse parallel mit
        # verschiedenen Hauptschlüsseln (Lost Update, danach VaultCorrupt bis zum
        # Re-Login). Nach dem Sperr-Erwerb erneut lesen und prüfen: Der Wartende
        # vor uns hat vielleicht schon migriert.
        with _transaktion():
            doc = _read_file() or doc
            if isinstance(doc, dict) and doc.get("version") == 1 and isinstance(doc.get("raw"), bytes):
                doc = _migrate_v1(doc)
    if not isinstance(doc, dict) or not isinstance(doc.get("wraps"), dict):
        # Gültiges JSON reicht nicht: Ohne Verpackungs-Karte ist der Vault beschädigt —
        # sonst schlägt jeder Zugriff (status, unlock, secret_*) als nackter
        # KeyError/AttributeError in einem 500 durch.
        raise VaultCorrupt("Vault-Datei ist beschädigt (fehlende/fehlerhafte 'wraps'-Struktur).")
    return doc


# ---------------------------------------------------------------------------
# Entsperren / Sperren
# ---------------------------------------------------------------------------
def unlock(password: str) -> bool:
    """Mit dem Zugangspasswort entsperren. Erfolg = Passwort war richtig."""
    global _mk
    try:
        doc = _doc()
        w = doc["wraps"].get("password")
        if not w:
            return False
        key = Scrypt(
            salt=_unb64(w["salt"]),
            length=32,
            n=w.get("n", SCRYPT_N),
            r=w.get("r", SCRYPT_R),
            p=w.get("p", SCRYPT_P),
        ).derive(password.encode())
        _mk = _unwrap(key, w)
        return True
    except VaultLocked:
        # Gesperrt/KORRUPT ist kein „falsches Passwort": Bei einer beschädigten
        # Datei (VaultCorrupt) tippt der Nutzer sonst das richtige Passwort endlos
        # neu, ohne je eine brauchbare Fehlermeldung zu bekommen. Durchreichen —
        # die HTTP-Schicht hat dafür einen eigenen Handler (Beschädigungs-Hinweis).
        raise
    except Exception:  # noqa: BLE001 - falsches Passwort
        return False


def unlock_env() -> bool:
    """Ohne Menschen entsperren (Env-Verpackung) — für Neustarts und den Nacht-Job."""
    global _mk
    ek = _env_key()
    if not ek:
        return False
    try:
        doc = _doc()
        w = doc["wraps"].get("env")
        if not w:
            return False
        _mk = _unwrap(ek, w)
        return True
    except Exception:  # noqa: BLE001
        return False


def lock() -> None:
    global _mk
    _mk = None


def is_unlocked() -> bool:
    return _mk is not None


def _key() -> bytes:
    """Hauptschlüssel holen — notfalls automatisch per Env-Verpackung entsperren."""
    if _mk is None and not unlock_env():
        raise VaultLocked("Vault ist gesperrt — bitte anmelden.")
    return _mk  # type: ignore[return-value]


def status() -> dict:
    try:
        doc = _doc()
    except VaultLocked:
        return {"exists": False, "unlocked": False, "auto_unlock": False, "version": 0}
    return {
        "exists": True,
        "unlocked": is_unlocked() or bool(doc["wraps"].get("env") and _env_key()),
        "auto_unlock": bool(doc["wraps"].get("env")),
        "has_password": bool(doc["wraps"].get("password")),
        "version": doc.get("version", 1),
    }


def verify_password(password: str) -> bool:
    """Passwort prüfen, ohne den Zustand zu ändern (für Anmeldung)."""
    keep = _mk
    ok = unlock(password)
    if not ok:
        globals()["_mk"] = keep  # Zustand nicht zerstören
    return ok


# ---------------------------------------------------------------------------
# Verwaltung
# ---------------------------------------------------------------------------
def set_auto_unlock(enabled: bool) -> bool:
    """Env-Verpackung an-/abschalten. Ohne sie bleibt der Vault nach einem Neustart
    gesperrt, bis sich jemand anmeldet — dafür schützt er dann auch gegen ein
    übernommenes Server-Konto."""
    # Read-Modify-Write auf dem GESAMTEN Dokument (inkl. data-Block) — das gehört
    # komplett unter die Transaktionssperre, sonst überschreibt dieser Aufruf ein
    # paralleles secret_set still mit dem veralteten Stand (Lost Update).
    with _transaktion():
        doc = _doc()
        mk = _key()
        if enabled:
            ek = _env_key()
            if not ek:
                return False
            doc["wraps"]["env"] = _wrap(ek, mk)
        else:
            doc["wraps"].pop("env", None)
        _write_file(doc)
    audit("VAULT-AUTOUNLOCK", "an" if enabled else "aus", client="web-ui")
    return True


def change_password(old: str, new: str) -> bool:
    """Zugangspasswort ändern — die Secrets werden dabei NICHT neu verschlüsselt,
    nur die Verpackung des Hauptschlüssels."""
    if len(new) < 8:
        raise ValueError("Das neue Passwort muss mindestens 8 Zeichen haben.")
    # Read-Modify-Write komplett unter der Transaktionssperre: Zwischen Lesen und
    # Zurückschreiben liegt der langsame scrypt-Passwort-Beweis (~200 ms) — ohne
    # Sperre verliert ein paralleles secret_set in diesem Fenster still sein Secret.
    with _transaktion():
        doc = _doc()
        w = doc["wraps"].get("password")
        if w:
            if not verify_password(old):
                return False
            mk = _mk or _key()
            # Stand nach dem Passwort-Beweis erneut lesen: verify_password kann
            # selbst eine v1-Migration ausgelöst (und das Dokument getauscht) haben.
            doc = _doc()
        else:
            mk = _key()  # Vault ohne Passwort-Verpackung (migriert ohne Passwort)
        salt = secrets.token_bytes(16)
        doc["wraps"]["password"] = {
            "salt": _b64(salt),
            "n": SCRYPT_N,
            "r": SCRYPT_R,
            "p": SCRYPT_P,
            **_wrap(_derive(new, salt), mk),
        }
        _write_file(doc)
    audit("VAULT-PASSWORD", "geändert", client="web-ui")
    return True


def init(password: str) -> None:
    """Frischen Vault anlegen (Erststart-Wizard).

    Weigert sich, einen vorhandenen Vault zu überschreiben — das wäre der sichere Weg
    in den Totalverlust aller Secrets.
    """
    global _mk
    if VAULT_PATH.exists():
        raise FileExistsError(
            f"{VAULT_PATH} existiert bereits — Anlegen würde vorhandene Secrets vernichten."
        )
    doc = _new_vault(password)
    _write_file(doc)
    _mk = _unwrap(_derive(password, _unb64(doc["wraps"]["password"]["salt"])), doc["wraps"]["password"])


# ---------------------------------------------------------------------------
# Audit
# ---------------------------------------------------------------------------
def _clean(value: str, limit: int = 120) -> str:
    """Steuerzeichen entfernen — sonst ließen sich mit einem Zeilenumbruch im
    Secret-Namen gefälschte Audit-Einträge einschleusen (Log-Injection)."""
    safe = "".join(c for c in str(value) if c.isprintable() and c not in "\r\n")
    return safe[:limit] if safe else "?"


def audit(action: str, name: str, client: str = "-") -> None:
    line = (
        f"{time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())} "
        f"{_clean(action, 24)} {_clean(name)} client={_clean(client, 24)}\n"
    )
    _ensure_dir()  # audit.log liegt neben der vault.enc (Ersteinrichtung)
    # Größenbegrenzung: audit.log wuchs bislang unbegrenzt (dokumentierte Schuld). Bei
    # >5 MB einmal atomar nach audit.log.1 rotieren (eine Vorgängerdatei, erbt 0600 via
    # os.replace) — deckelt den Verbrauch auf ~10 MB statt unbegrenzt.
    try:
        if AUDIT_PATH.stat().st_size > 5_000_000:
            os.replace(AUDIT_PATH, AUDIT_PATH.with_name("audit.log.1"))
    except OSError:
        pass
    with AUDIT_PATH.open("a") as fh:
        # 0600 bei jedem Schreiben erzwingen: schützt Secret-Namen + Zugriffszeiten
        # vor Gruppen-/Weltlesern und heilt eine mit falscher umask (664) angelegte
        # Alt-Datei beim nächsten Eintrag selbst.
        os.fchmod(fh.fileno(), 0o600)
        fh.write(line)


# ---------------------------------------------------------------------------
# Secrets (öffentliche API — unverändert)
# ---------------------------------------------------------------------------
def _load() -> dict[str, str]:
    return _read_data(_doc(), _key())


def _save(store: dict[str, str]) -> None:
    doc = _doc()
    _write_data(doc, _key(), store)
    _write_file(doc)


def secret_set(name: str, value: str, client: str = "-") -> None:
    # Abgelehnte Schreibversuche stehen im Audit-Log (SET-REJECT): Wer mit einem
    # gestohlenen Token am Vault herumprobiert, hinterlässt eine Spur — nicht nur
    # die Erfolge.
    if not SECRET_NAME_RE.match(name):
        audit("SET-REJECT", f"{name} (Name unzulässig)", client)
        raise ValueError(
            "Ungültiger Name — erlaubt sind Buchstaben, Ziffern, Punkt, "
            "Bindestrich, Unterstrich und Leerzeichen (1–64 Zeichen)."
        )
    if not value:
        audit("SET-REJECT", f"{name} (leerer Wert)", client)
        raise ValueError("Der Wert darf nicht leer sein.")
    if len(value) > SECRET_VALUE_MAX:
        audit("SET-REJECT", f"{name} (Wert {len(value)} Zeichen)", client)
        raise ValueError(f"Wert ist zu lang (max. {SECRET_VALUE_MAX:,} Zeichen).".replace(",", "."))
    with _transaktion():
        store = _load()
        store[name] = value
        _save(store)
    audit("SET", name, client)


def secret_get(name: str, client: str = "-") -> str | None:
    with _transaktion():
        store = _load()
    audit("GET" if name in store else "GET-MISS", name, client)
    return store.get(name)


def secret_list(client: str = "-") -> list[str]:
    with _transaktion():
        store = _load()
    audit("LIST", f"({len(store)} entries)", client)
    return sorted(store)


def secret_delete(name: str, client: str = "-") -> bool:
    with _transaktion():
        store = _load()
        existed = name in store
        store.pop(name, None)
        _save(store)
    audit("DELETE" if existed else "DELETE-MISS", name, client)
    return existed
