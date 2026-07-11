"""Sprachschicht für serverseitig erzeugte Texte.

Diagnose-Befunde, Fehlermeldungen und Statusangaben entstehen im Python-Code und
landen unübersetzt in der Oberfläche — eine rein clientseitige Übersetzung hätte
den Diagnose-Tab deutsch gelassen, während alles ringsum englisch ist.

Prinzip wie im Frontend: Der DEUTSCHE Satz ist der Schlüssel. Fehlt eine Übersetzung,
fällt der Text weich auf Deutsch zurück, statt leer zu bleiben.

Die Sprache hängt an der Anfrage (contextvar), nicht am Prozess — zwei Nutzer mit
verschiedenen Sprachen dürfen sich nicht gegenseitig die Antworten verfälschen.
"""

from __future__ import annotations

import contextvars

_lang: contextvars.ContextVar[str] = contextvars.ContextVar("lang", default="de")


def set_lang(value: str) -> None:
    _lang.set("en" if str(value).lower().startswith("en") else "de")


def lang() -> str:
    return _lang.get()


def T(de: str, **werte: object) -> str:
    """Übersetzen und Platzhalter füllen: T("{n} Fehler", n=3)."""
    text = DE_EN.get(de, de) if _lang.get() == "en" else de
    return text.format(**werte) if werte else text


# ---------------------------------------------------------------------------
# Deutscher Satz -> englische Entsprechung
#
# Die Schlüssel müssen zeichengenau mit dem T()-Argument im Code übereinstimmen —
# inklusive Platzhaltern, Geviertstrich und typografischen Anführungszeichen.
# ---------------------------------------------------------------------------
DE_EN: dict[str, str] = {
    "Kein Lauf angegeben.": "No run specified.",
    # --- ui.py: globale Fehlerbehandlung ---
    "Im Hub ist etwas schiefgelaufen. Der Vorfall wurde protokolliert.":
        "Something went wrong in the hub. The incident has been logged.",
    "Die Anfrage war kein gültiges JSON.": "The request was not valid JSON.",
    "Der Vault ist gesperrt — bitte neu anmelden.":
        "The vault is locked — please sign in again.",
    "Diesen Endpunkt gibt es nicht.": "No such endpoint.",
    "Nicht gefunden.": "Not found.",

    # --- api/auth.py: Anmeldung, Sitzungen, Geräte-Kopplung ---
    "Zu viele Fehlversuche — bitte 15 Minuten warten.":
        "Too many failed attempts — please wait 15 minutes.",
    "Falsches Passwort": "Wrong password",
    "Code stimmt nicht": "Wrong code",
    "Statisches Token (env-Datei)": "Static token (env file)",
    "Läuft nie ab. Zum Widerrufen den Wert MCP_TOKEN in "
    "~/.config/knowledge-mcp/env ersetzen und den Dienst neu starten.":
        "Never expires. To revoke it, replace the MCP_TOKEN value in "
        "~/.config/knowledge-mcp/env and restart the service.",
    "Das ist deine aktuelle Sitzung — nutze „Abmelden“.":
        "This is your current session — use “Sign out”.",
    "Sitzung nicht gefunden": "Session not found",
    "Name enthält ungültige Zeichen.": "The name contains invalid characters.",
    "Geräte-Token · {label}": "Device token · {label}",

    # --- api/secrets.py: Vault-Verwaltung ---
    "Name und Wert sind Pflicht": "Name and value are required",
    "Ungültiger Name — erlaubt sind Buchstaben, Ziffern, Punkt, Bindestrich, "
    "Unterstrich und Leerzeichen (max. 64 Zeichen).":
        "Invalid name — allowed are letters, digits, dot, hyphen, underscore "
        "and spaces (max. 64 characters).",
    "Wert ist zu lang (max. 20.000 Zeichen)": "Value is too long (max. 20,000 characters)",

    # --- api/knowledge.py: Graphen, Berichte, Fragen ---
    "(kein Report vorhanden)": "(no report available)",
    "Unbekanntes Projekt": "Unknown project",
    "Unbekanntes Projekt oder fehlender Knoten": "Unknown project or missing node",
    "Bitte eine Frage eingeben.": "Please enter a question.",
    "Kein {backend}-Key hinterlegt — hier stehen nur die Rohdaten aus dem "
    "Graphen. Key im Mapping-Tab eintragen für eine echte Erklärung.":
        "No {backend} key stored — this is just the raw data from the graph. "
        "Add a key in the Mapping tab for a real explanation.",
    "Zu dieser Frage habe ich im Graphen nichts gefunden. Versuch es mit anderen "
    "Begriffen — am besten mit Namen aus dem Code (Funktionen, Dateien, Konzepte).":
        "Nothing in the graph matches this question. Try different terms — ideally "
        "names from the code (functions, files, concepts).",
    "Kein KI-Key hinterlegt — hier sind nur die passenden Stellen aus dem "
    "Graphen. Für eine formulierte Antwort einen Key im Mapping-Tab eintragen.":
        "No AI key stored — these are just the matching spots from the graph. "
        "Add a key in the Mapping tab to get a written answer.",
    "KI nicht verfügbar: {msg}": "AI unavailable: {msg}",

    # --- api/mapping.py: Zeitplan, Läufe, Projekte, Reparatur ---
    "Ungültige Uhrzeit (Format HH:MM)": "Invalid time (format HH:MM)",
    "Unbekanntes Backend": "Unknown backend",
    "Ungültiger Modellname": "Invalid model name",
    "Läuft bereits": "Already running",
    "Kein gültiges Verzeichnis (erlaubt: Home und /opt)":
        "Not a valid directory (allowed: home and /opt)",
    "Projekt ist bereits eingetragen": "Project is already registered",
    "Projekt nicht gefunden": "Project not found",
    "Projekt nicht konfiguriert": "Project is not configured",
    "Keine Schreibrechte in diesem Projekt": "No write permission in this project",
    "Der Ordner {path} existiert nicht.": "The folder {path} does not exist.",
    "Projekt entfernen oder Pfad korrigieren.": "Remove the project or correct the path.",
    "Keine Leserechte auf {path}.": "No read permission for {path}.",
    "Auf dem Server ausführen:  sudo setfacl -m u:{user}:rx {path}":
        "Run on the server:  sudo setfacl -m u:{user}:rx {path}",
    "Der Ausgabeordner graphify-out fehlt.": "The output folder graphify-out is missing.",
    "Wird beim Reparieren angelegt.": "It will be created during the repair.",
    "{path} ist nicht beschreibbar (gehört einem anderen Nutzer).":
        "{path} is not writable (it belongs to another user).",
    "Auf dem Server ausführen:  sudo chown -R {user} {path}":
        "Run on the server:  sudo chown -R {user} {path}",
    "Reparatur läuft bereits": "A repair is already running",
    "Reparatur gestartet…": "Repair started…",
    "Ausgabeordner angelegt: {path}": "Output folder created: {path}",
    "Nicht automatisch behebbar:": "Cannot be fixed automatically:",
    "Kein API-Key hinterlegt — es wird nur Code gemappt (ohne Dokumente).":
        "No API key stored — only code is mapped (without documents).",
    "Mappe {name} neu ({backend} · {model})…":
        "Re-mapping {name} ({backend} · {model})…",
    "✓ Reparatur erfolgreich — Projekt ist wieder gemappt.":
        "✓ Repair successful — the project is mapped again.",
    "Fehler bei der Reparatur: {msg}": "Repair failed: {msg}",

    # --- api/system.py: Zwei-Faktor, Vault, Sicherung ---
    "Code stimmt nicht — bitte den aktuellen aus der App.":
        "Wrong code — please use the current one from your app.",
    "Zum Abschalten den aktuellen Code eingeben.":
        "Enter the current code to turn it off.",
    "Kein VAULT_KEY in der Umgebung.": "No VAULT_KEY in the environment.",
    "Vault ist gesperrt — bitte neu anmelden.":
        "The vault is locked — please sign in again.",
    "Aktuelles Passwort stimmt nicht.": "Current password is incorrect.",
    "Kein Secret namens „{name}“ im Vault.": "No secret named “{name}” in the vault.",
    "Repo-Adresse fehlt.": "Repository address is missing.",
    "Ungültige Repo-Adresse. Beispiel: https://github.com/name/repo.git":
        "Invalid repository address. Example: https://github.com/name/repo.git",
    "Ungültiger Ordner- oder Branch-Name.": "Invalid folder or branch name.",
    "Für HTTPS-Repos wird ein Zugriffstoken gebraucht — entweder neu eingeben "
    "oder ein vorhandenes Secret aus dem Vault wählen. "
    "(GitHub: Settings → Developer settings → Personal access tokens, "
    "Rechte: Contents read/write auf dieses Repo.)":
        "HTTPS repositories need an access token — either enter a new one or pick "
        "an existing secret from the vault. "
        "(GitHub: Settings → Developer settings → Personal access tokens, "
        "permissions: Contents read/write on this repository.)",
    "Keine Backup-Passphrase eingerichtet.": "No backup passphrase configured.",
    "Sicherung läuft bereits": "A backup is already running",
    "Sicherung läuft…": "Backup running…",
    "Es ist bereits eine Passphrase eingerichtet.": "A passphrase is already configured.",
    "Sicherung {file} ({size} Bytes) abgeschlossen.":
        "Backup {file} ({size} bytes) completed.",
    "Fehler: {msg}": "Error: {msg}",

    # --- api/system.py: Diagnose-Befunde ---
    "Server": "Server",
    "läuft": "running",
    "systemd meldet: {status}": "systemd reports: {status}",
    "Nacht-Mapping": "Nightly mapping",
    "aktiv · nächster Lauf: {t}": "active · next run: {t}",
    "ausgeschaltet": "off",
    "Im Mapping-Tab einschalten.": "Turn it on in the Mapping tab.",
    "nicht gefunden": "not found",
    "pipx install graphifyy — ohne graphify ist kein Mapping möglich.":
        "pipx install graphifyy — mapping is impossible without graphify.",
    "KI-Anbieter": "AI provider",
    "kein Key hinterlegt": "no key stored",
    "Key im Mapping-Tab eintragen — sonst werden Dokumente nicht analysiert.":
        "Add a key in the Mapping tab — otherwise documents are not analyzed.",
    "Secrets-Vault": "Secrets vault",
    "{n} Secrets · verschlüsselt ({size})": "{n} secrets · encrypted ({size})",
    "leer": "empty",
    "Sicherung": "Backup",
    "keine Backup-Passphrase gesetzt — es wird NICHT gesichert":
        "no backup passphrase set — NOTHING is being backed up",
    "Unten auf dieser Seite einrichten. Ohne Sicherung sind die Secrets "
    "bei einem Plattenausfall unwiederbringlich verloren.":
        "Set one up further down this page. Without a backup, the secrets are lost "
        "for good if the disk fails.",
    "eingerichtet, aber noch nie ausgeführt": "configured, but never run",
    "Unten „Jetzt sichern“ drücken.": "Press “Back up now” below.",
    "letzte: {name} · vor {h} Std.": "last: {name} · {h} h ago",
    "auch offsite (Git)": "also offsite (Git)",
    "nur lokal!": "local only!",
    "Letzte Sicherung ist älter als 36 Stunden.":
        "The last backup is more than 36 hours old.",
    "Von außen erreichbar": "Reachable from the internet",
    "{url} antwortet": "{url} responds",
    "{url} antwortet mit HTTP {code}": "{url} responds with HTTP {code}",
    "{url} nicht erreichbar ({error})": "{url} is not reachable ({error})",
    "nur lokal erreichbar ({url})": "reachable locally only ({url})",
    "Tunnel/Proxy prüfen — ohne das erreichen dich KI-Clients nicht.":
        "Check the tunnel/proxy — without it, AI clients cannot reach you.",
    "Projekte": "Projects",
    "{n} Ordner fehlen: {paths}": "{n} folder(s) missing: {paths}",
    "{n} noch nicht gemappt": "{n} not mapped yet",
    "{n} Projekte, alle gemappt": "{n} projects, all mapped",
    "Im Mapping-Tab prüfen.": "Check the Mapping tab.",
    "Speicherplatz": "Disk space",
    "{free} frei von {total} ({pct} %)": "{free} free of {total} ({pct} %)",
    "Platte wird knapp.": "Disk is running low.",
    "Angriffsschutz": "Attack protection",
    "{n} IP(s) gerade gesperrt: {ips}": "{n} IP(s) currently blocked: {ips}",
    "Jemand rät aktiv dein Passwort — die Bremse hält ihn auf.":
        "Someone is actively guessing your password — the rate limit is holding them off.",
    "{n} Sperre(n) in letzter Zeit — aktuell keine aktiv":
        "{n} block(s) recently — none active right now",
    "Audit-Log prüfen.": "Check the audit log.",
    "keine aktiven Sperren": "no active blocks",
    "{n} Fehlversuche protokolliert": "{n} failed attempts logged",
    "Unerwartete Fehler": "Unexpected errors",
    "{n} in den letzten 24 Std. · zuletzt {path} (Ref. {ref})":
        "{n} in the last 24 h · most recent {path} (ref. {ref})",
    "Details stehen in {file} — dort steht auch, woran es lag.":
        "Details are in {file} — including what went wrong.",
    "keine in den letzten 24 Std.": "none in the last 24 h",
    "keine protokolliert": "none logged",
}
