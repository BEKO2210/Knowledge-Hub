# Änderungsverlauf

Alle nennenswerten Änderungen an diesem Projekt. Format angelehnt an
[Keep a Changelog](https://keepachangelog.com/de/1.1.0/), Versionierung nach
[SemVer](https://semver.org/lang/de/).

## [Unveröffentlicht]

### Hinzugefügt
- **Übersetzung vollständig.** Ein Prüf-Skript ruft die Oberfläche auf Englisch auf und sucht
  jeden sichtbaren deutschen Text — Ergebnis: **null**. Die letzten Lücken saßen an Stellen, die
  keine Übersetzung je erreicht hätte: deutsche Literale in `oninput`/`onclick`-Attributen im
  Markup („Alle", „Adresse kopiert", „Token kopiert") und der Gerätename „Weboberfläche", der in
  `oauth.py` entsteht. Dazu **10 neue Tests** als Wachhund: Sie öffnen jeden Reiter auf Englisch
  und lassen die Suite platzen, sobald wieder deutscher Text hineinrutscht — sonst merkt das
  niemand, weil man selbst deutsch liest.
- Sponsor-Knopf (`FUNDING.yml`), Social-Preview-Karte, Issues/Projects/Discussions/Wiki aktiviert.

### Behoben
- **Der Fehlerzähler im Mapping-Verlauf log.** Er zählte jede Zeile mit „FEHLGESCHLAGEN" als
  Projektfehler — auch die gescheiterte *Sicherung*, die keinen Projektnamen trägt. Ergebnis war
  ein namenloser Fehler „?", gegen den man nichts tun konnte. Jetzt werden Projekt-, Sync- und
  Sicherungsfehler getrennt, jeder erklärt in einem Satz, was kaputt ist, und bietet den passenden
  Knopf an (Reparieren bzw. Zur Sicherung). Erledigte Läufe lassen sich abhaken — der Eintrag
  bleibt stehen, er mahnt nur nicht mehr.
- **Die Tests hingen an der Entwicklermaschine** — an der echten `env`-Datei im Home-Verzeichnis
  und an der Systemsprache. Auf einer frischen Maschine (CI) zeigte der Hub darum den
  Erststart-Assistenten, und drei Tests suchten deutsche Texte in einer englischen Oberfläche.
  Beides von CI aufgedeckt, beides behoben.

### Bekannt
- **Kein Coverage/Codecov.** `coverage` bricht beim Messen mit einem Zirkelimport ab: Der
  Import-Hook von `beartype` (kommt über `key_value.aio` aus `fastmcp`) umschließt den Loader von
  `coverage` und ruft sich dabei selbst auf. Mit beartype 0.21 und 0.22 geprüft — beide betroffen.
  Es ist kein Fehler dieses Projekts; sobald er behoben ist, genügen `pytest-cov` und ein
  Upload-Schritt.

## [0.5.0] — 2026-07-11 — Erste öffentliche Fassung

### Hinzugefügt
- **Englische Oberfläche.** Die gesamte Bedienoberfläche liegt jetzt zweisprachig vor: Englisch ist
  Standard, Deutsch einen Klick entfernt (die Browsersprache entscheidet beim ersten Besuch).
  Übersetzt werden statische Texte (`data-en` im Markup), dynamisch erzeugte Texte (`t()` in
  `app.js`) **und die serverseitig erzeugten Texte** — Diagnose-Befunde und Fehlermeldungen
  entstehen in Python und wären sonst deutsch geblieben. Dafür gibt es `api/i18n.py`: Die Sprache
  hängt per contextvar an der Anfrage, nicht am Prozess, damit zwei Nutzer mit verschiedenen
  Sprachen sich nicht gegenseitig die Antworten verfälschen. In allen drei Schichten gilt: Der
  **deutsche Satz ist der Schlüssel**, eine fehlende Übersetzung fällt weich zurück, statt einen
  leeren Knopf zu hinterlassen.
- Englisches README mit Screenshots und Architektur-Übersicht, `CONTRIBUTING.md`,
  englische `SECURITY.md`, **AGPL-3.0**-Lizenz.

### Geändert
- `.gitignore` gehärtet: Auch alte Vault-Stände (`vault.enc.*`), `errors.log` und `config.yaml`
  sind jetzt ausgeschlossen — der bisherige Filter hätte einen migrierten Vault durchgelassen.

## [0.4.0] — 2026-07-11

### Hinzugefügt
- **Testsuite (52 Tests)** — Vault (Verschlüsselung, Passwort-Verpackung, Auto-Entsperren,
  Audit-Log), BearerGate (was ist offen, was ist zu), Login-Rate-Limit, kompletter
  OAuth-2.1-PKCE-Fluss inklusive der Angriffsfälle (fremder Verifier, Code-Wiederverwendung,
  fremde Redirect-URI), Nacht-Mapping (die `oneshot`-„activating"-Falle) und Log-Parser.
- **E2E-Tests im echten Browser** — headless Chromium gegen eine frisch hochgefahrene,
  isolierte Instanz: Login, alle Tabs, Secret anlegen→lesen→löschen durchgeklickt,
  Theme/Sprache, und ein Regressionsschutz gegen einen brechenden Header.
- **CI** (GitHub Actions) — Lint (ruff), Tests, Auslieferbarkeits-Prüfung und ein
  Secrets-Scan, der anschlägt, falls je eine Schlüsseldatei eingecheckt wird.
- Verbinden-Tab: Geräte-Kopplung per QR-Code, echter Verbindungstest gegen `/mcp`.
- Nacht-Mapping: Verlauf der letzten Läufe mit Kosten, Dauer und Knoten-Zuwachs.
- Zwei-Faktor-Anmeldung (TOTP), Hell-/Dunkel-Modus, Erst-Tour, Sprachumschalter (DE/EN).

### Geändert
- **`ui.py` aufgeteilt** — aus einem 4.467-Zeilen-Monolithen (mit 2.850 Zeilen HTML/CSS/JS
  als Python-String) wurde: `web/` (echte `index.html`, `app.css`, `app.js`) und `api/`
  (`auth`, `knowledge`, `secrets`, `mapping`, `system`, `common`). `ui.py` ist auf 249 Zeilen
  reine Web-Schicht geschrumpft.
- Assets werden über eine **inhaltsgehashte URL** (`/ui/asset/app.js?v=…`) ausgeliefert und
  dürfen dadurch `immutable` gecacht werden — ein Update kommt trotzdem sofort an.
- Kopfleiste: fünf Haupttabs, sekundäre Ansichten (Diagnose, Audit) hinter „Mehr" — auf
  Desktop und Handy dieselbe Aufteilung.

### Behoben
- **Die nächtliche Sicherung lief seit jeher ins Leere.** `nightly-map.sh` las die env-Datei
  per `source`, wodurch die Passphrase nur als Shell-Variable existierte. Der Kindprozess
  `backup.py` sah sie nicht, fiel auf die interaktive Abfrage zurück und starb ohne Terminal
  an `EOFError` — in *jedem* Nachtlauf. Behoben mit `set -a`.
- Kopfleiste brach auf jeder Breite: am Handy wurde „Abmelden" aus dem Bild geschoben, bei
  1280 px lief sie über und schnitt den Knopf ab.
- `/ui/asset/` fehlte in der Freigabeliste der `BearerGate` — der Login-Bildschirm hätte sein
  eigenes Stylesheet nicht laden können.
- Fragen-Tab: Quellenangabe zeigte `datei.md:None` bei Dokumenten ohne Zeilennummer;
  nummerierte Antwortpunkte liefen ineinander.

## [0.3.0] — Phase 2: Sicherheit
- Verschlüsselter Vault v2 (zweistufig: Hauptschlüssel, verpackt per Passwort **und** per
  `VAULT_KEY` für den unbeaufsichtigten Betrieb), Audit-Log, Rate-Limit, Schutz-Header,
  verschlüsselte Offsite-Sicherung.

## [0.2.0] — Phase 1: Entkopplung
- Konfiguration statt fest verdrahteter Pfade, Setup-Assistent, Docker-Variante,
  Installationsskript.

## [0.1.0] — Erste Fassung
- MCP-Hub mit Graphify-Wissensgraphen und Secrets-Vault.
