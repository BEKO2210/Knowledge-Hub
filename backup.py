"""Verschlüsselte Sicherung des Knowledge Hub.

Sichert die Dinge, die man NICHT wiederherstellen kann, wenn die Platte stirbt:
  * vault.enc      — die verschlüsselten Secrets
  * env            — Vault-Schlüssel, MCP-Token, Zugangspasswort
  * config.yaml    — Einstellungen, Projekte, Backends

Warum eine eigene Verschlüsselung? Weil `vault.enc` ohne den Schlüssel aus `env`
wertlos ist — beide gehören also ins Backup. Dann liegen sie aber nebeneinander,
und die Vault-Verschlüsselung wäre wirkungslos. Deshalb wird das gesamte Archiv
mit einer **separaten Passphrase** verschlüsselt (scrypt + AES-256-GCM), die du
offline aufbewahrst. Erst damit darf das Backup an einen fremden Ort (GitHub, NAS,
Cloud) — dort ist es nur ein unlesbarer Blob.

Format:  KHUB1 | salt(16) | nonce(12) | AES-256-GCM(tar.gz)

CLI:
    python backup.py create  <ziel.khub>   # Passphrase aus $BACKUP_PASSPHRASE
    python backup.py restore <datei.khub> [--to <ordner>]
    python backup.py verify  <datei.khub>
"""

from __future__ import annotations

import argparse
import getpass
import io
import os
import sys
import tarfile
import time
from pathlib import Path

from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.scrypt import Scrypt

MAGIC = b"KHUB1"
SALT_LEN, NONCE_LEN = 16, 12
AAD = b"knowledge-hub:backup:v1"
# scrypt-Parameter: bewusst teuer (~100 ms), damit Rateangriffe auf die Passphrase
# unattraktiv werden. n=2^16 braucht ~64 MB Speicher pro Versuch.
SCRYPT_N, SCRYPT_R, SCRYPT_P = 2**16, 8, 1


def _paths() -> dict[str, Path]:
    """Was gesichert wird (Name im Archiv -> Datei auf der Platte)."""
    cfg_dir = Path(os.environ.get("KMCP_CONFIG_DIR", str(Path.home() / ".config" / "knowledge-mcp")))
    env_file = Path(os.environ.get("KMCP_ENV_FILE", str(cfg_dir / "env")))
    vault = Path(os.environ.get("VAULT_PATH", str(Path.home() / "knowledge-mcp" / "vault.enc")))
    config_file = Path(os.environ.get("KNOWLEDGE_CONFIG", str(cfg_dir / "config.yaml")))
    return {"env": env_file, "vault.enc": vault, "config.yaml": config_file}


def _derive(passphrase: str, salt: bytes) -> bytes:
    kdf = Scrypt(salt=salt, length=32, n=SCRYPT_N, r=SCRYPT_R, p=SCRYPT_P)
    return kdf.derive(passphrase.encode())


def create(passphrase: str) -> bytes:
    """Archiv bauen und verschlüsseln. Gibt den fertigen Blob zurück."""
    if len(passphrase) < 12:
        raise ValueError("Die Backup-Passphrase muss mindestens 12 Zeichen haben.")
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz") as tar:
        found = 0
        for name, path in _paths().items():
            if path.is_file():
                tar.add(path, arcname=name)
                found += 1
        if not found:
            raise FileNotFoundError("Nichts zu sichern — weder Vault noch env gefunden.")
        info = tarfile.TarInfo("BACKUP-INFO.txt")
        note = (
            f"Knowledge-Hub-Sicherung vom {time.strftime('%Y-%m-%d %H:%M:%S')}\n"
            f"Wiederherstellen:  python backup.py restore <diese-datei>\n"
            f"Ohne die Backup-Passphrase ist diese Datei nicht lesbar.\n"
        ).encode()
        info.size = len(note)
        tar.addfile(info, io.BytesIO(note))

    salt = os.urandom(SALT_LEN)
    nonce = os.urandom(NONCE_LEN)
    key = _derive(passphrase, salt)
    ct = AESGCM(key).encrypt(nonce, buf.getvalue(), AAD)
    return MAGIC + salt + nonce + ct


def open_archive(blob: bytes, passphrase: str) -> bytes:
    """Entschlüsseln — wirft bei falscher Passphrase oder Manipulation."""
    if not blob.startswith(MAGIC):
        raise ValueError("Keine Knowledge-Hub-Sicherung (falsche Datei?).")
    off = len(MAGIC)
    salt = blob[off:off + SALT_LEN]
    nonce = blob[off + SALT_LEN:off + SALT_LEN + NONCE_LEN]
    ct = blob[off + SALT_LEN + NONCE_LEN:]
    key = _derive(passphrase, salt)
    try:
        return AESGCM(key).decrypt(nonce, ct, AAD)
    except Exception as e:  # InvalidTag
        raise ValueError("Entschlüsselung fehlgeschlagen — falsche Passphrase "
                         "oder beschädigte Datei.") from e


def contents(blob: bytes, passphrase: str) -> list[str]:
    with tarfile.open(fileobj=io.BytesIO(open_archive(blob, passphrase)), mode="r:gz") as tar:
        return tar.getnames()


def restore(blob: bytes, passphrase: str, dest: Path) -> list[str]:
    """Archiv nach `dest` auspacken (0600 für alles Sensible)."""
    dest.mkdir(parents=True, exist_ok=True)
    written = []
    with tarfile.open(fileobj=io.BytesIO(open_archive(blob, passphrase)), mode="r:gz") as tar:
        for member in tar.getmembers():
            if not member.isfile() or "/" in member.name or member.name.startswith("."):
                continue  # keine Pfade aus dem Archiv übernehmen (Traversal-Schutz)
            target = dest / member.name
            data = tar.extractfile(member)
            if data is None:
                continue
            target.write_bytes(data.read())
            target.chmod(0o600)
            written.append(member.name)
    return written


def _prune(files: list[Path], keep: int) -> list[str]:
    """Alte Sicherungen entfernen — die letzten `keep` bleiben."""
    removed = []
    for f in sorted(files, reverse=True)[keep:]:
        f.unlink(missing_ok=True)
        removed.append(f.name)
    return removed


def _target_local(blob: bytes, name: str, t: dict) -> str:
    d = Path(str(t["path"])).expanduser()
    d.mkdir(parents=True, exist_ok=True)
    d.chmod(0o700)
    out = d / name
    out.write_bytes(blob)
    out.chmod(0o600)
    _prune(list(d.glob("hub-*.khub")), int(t.get("keep", 14)))
    return f"lokal: {out}"


CACHE_DIR = Path(os.environ.get("KMCP_CACHE_DIR", str(Path.home() / ".cache" / "knowledge-hub")))


def _tokenized(url: str, token: str) -> str:
    """Zugangstoken in die HTTPS-URL einsetzen (nur im Speicher, nie auf Platte)."""
    if not token or not url.startswith("https://"):
        return url
    return url.replace("https://", f"https://x-access-token:{token}@", 1)


def _target_git(blob: bytes, name: str, t: dict, token: str = "") -> str:
    """In ein Git-Repo legen und pushen.

    Zwei Betriebsarten:
      * `repo:` — ein bereits vorhandener lokaler Klon (nutzt dessen Zugangsdaten, z. B. SSH).
      * `url:`  — eine Repo-Adresse; der Klon wird im Cache angelegt, Authentifizierung über
        einen Zugriffstoken aus dem Vault. Der Token wird NICHT in .git/config gespeichert.
    """
    import subprocess

    branch = str(t.get("branch", "main"))
    url = str(t.get("url", "")).strip()

    if url:
        repo = CACHE_DIR / "backup-repo"
        CACHE_DIR.mkdir(parents=True, exist_ok=True)
        if not (repo / ".git").is_dir():
            cl = subprocess.run(  # noqa: S603,S607
                ["git", "clone", "--depth", "1", _tokenized(url, token), str(repo)],
                capture_output=True, text=True, timeout=300,
            )
            if cl.returncode != 0:
                err = (cl.stderr or "").replace(token, "***") if token else (cl.stderr or "")
                raise RuntimeError(f"clone fehlgeschlagen: {err.strip()[:140]}")
            # Token sofort aus der Repo-Konfiguration entfernen
            subprocess.run(["git", "-C", str(repo), "remote", "set-url", "origin", url],  # noqa: S603,S607
                           capture_output=True, timeout=30)
    else:
        repo = Path(str(t["repo"])).expanduser()
        if not (repo / ".git").is_dir():
            raise FileNotFoundError(f"{repo} ist kein Git-Repository")

    def git(*args: str) -> subprocess.CompletedProcess:
        return subprocess.run(["git", "-C", str(repo), *args],  # noqa: S603,S607
                              capture_output=True, text=True, timeout=300)

    if url:
        git("fetch", "--depth", "1", _tokenized(url, token), branch)
        git("reset", "--hard", "FETCH_HEAD")

    sub = repo / str(t.get("subdir", "hub-backups"))
    sub.mkdir(parents=True, exist_ok=True)
    out = sub / name
    out.write_bytes(blob)
    out.chmod(0o600)
    _prune(list(sub.glob("hub-*.khub")), int(t.get("keep", 14)))

    git("add", "-A", str(sub.relative_to(repo)))
    if git("diff", "--cached", "--quiet").returncode == 0:
        return f"git: keine Änderung ({repo.name})"
    git("-c", "user.email=hub@localhost", "-c", "user.name=Knowledge Hub",
        "commit", "-q", "-m", f"hub-backup: {name}")

    push = git("push", "-q", _tokenized(url, token) if url else "origin", f"HEAD:{branch}")
    if push.returncode != 0:
        err = (push.stderr or "")
        if token:
            err = err.replace(token, "***")     # Token niemals ins Log
        raise RuntimeError(f"push fehlgeschlagen: {err.strip()[:140]}")
    where = url.split("/")[-1].removesuffix(".git") if url else repo.name
    return f"git: {where}/{t.get('subdir', 'hub-backups')} gepusht"


def run(cfg: dict, passphrase: str) -> dict:
    """Sicherung anlegen und an alle konfigurierten Ziele verteilen."""
    bcfg = cfg.get("backup") or {}
    targets = bcfg.get("targets") or []
    if not targets:
        return {"ok": False, "error": "Keine Backup-Ziele konfiguriert.", "results": []}

    blob = create(passphrase)
    name = f"hub-{time.strftime('%Y-%m-%d_%H%M')}.khub"
    results, ok = [], True
    for t in targets:
        kind = t.get("type")
        try:
            if kind == "local":
                results.append({"target": "local", "ok": True, "detail": _target_local(blob, name, t)})
            elif kind == "git":
                # Zugriffstoken (GitHub/GitLab) liegt im Vault, nicht in der Konfiguration.
                token = ""
                secret = t.get("secret")
                if secret:
                    import vault as _vault

                    token = _vault.secret_get(str(secret), client="backup") or ""
                    if not token:
                        raise RuntimeError(f"Kein Token im Vault unter „{secret}“.")
                results.append({"target": "git", "ok": True,
                                "detail": _target_git(blob, name, t, token)})
            else:
                results.append({"target": str(kind), "ok": False, "detail": "Unbekannter Zieltyp"})
                ok = False
        except Exception as e:  # noqa: BLE001
            results.append({"target": str(kind), "ok": False, "detail": f"{type(e).__name__}: {e}"})
            ok = False
    return {"ok": ok, "file": name, "size": len(blob), "results": results}


def _passphrase(explicit: str = "") -> str:
    if explicit:
        return explicit
    env = os.environ.get("BACKUP_PASSPHRASE", "")
    if env:
        return env
    return getpass.getpass("Backup-Passphrase: ")


def main() -> int:
    ap = argparse.ArgumentParser(description="Verschlüsselte Sicherung des Knowledge Hub")
    sub = ap.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("create", help="Sicherung anlegen")
    c.add_argument("out")
    r = sub.add_parser("restore", help="Sicherung zurückspielen")
    r.add_argument("file")
    r.add_argument("--to", default=".", help="Zielordner (Standard: aktueller Ordner)")
    v = sub.add_parser("verify", help="Sicherung prüfen (entschlüsseln + Inhalt zeigen)")
    v.add_argument("file")
    sub.add_parser("run", help="Sicherung anlegen und an alle Ziele verteilen (für den Nacht-Job)")
    args = ap.parse_args()

    try:
        if args.cmd == "run":
            import config as _config

            report = run(_config.load(), _passphrase())
            for r in report["results"]:
                print(("✓ " if r["ok"] else "✗ ") + r["detail"])
            if not report["ok"]:
                return 1
            print(f"✓ Sicherung {report['file']} ({report['size']:,} Bytes)")
        elif args.cmd == "create":
            blob = create(_passphrase())
            out = Path(args.out)
            out.write_bytes(blob)
            out.chmod(0o600)
            print(f"✓ Gesichert: {out} ({len(blob):,} Bytes)")
        elif args.cmd == "verify":
            names = contents(Path(args.file).read_bytes(), _passphrase())
            print("✓ Sicherung ist lesbar. Enthalten:")
            for n in names:
                print("   ", n)
        elif args.cmd == "restore":
            dest = Path(args.to)
            names = restore(Path(args.file).read_bytes(), _passphrase(), dest)
            print(f"✓ Wiederhergestellt nach {dest}:")
            for n in names:
                print("   ", n)
            print("\nJetzt zurückkopieren:")
            print(f"  cp {dest}/env        ~/.config/knowledge-mcp/env")
            print(f"  cp {dest}/config.yaml ~/.config/knowledge-mcp/config.yaml")
            print(f"  cp {dest}/vault.enc   ~/knowledge-mcp/vault.enc")
            print("  systemctl --user restart knowledge-mcp")
    except (ValueError, FileNotFoundError) as e:
        print(f"✗ {e}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
