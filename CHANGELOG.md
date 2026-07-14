# Änderungsverlauf

Alle nennenswerten Änderungen an diesem Projekt. Format angelehnt an
[Keep a Changelog](https://keepachangelog.com/de/1.1.0/), Versionierung nach
[SemVer](https://semver.org/lang/de/).

## [Unveröffentlicht]

### Hinzugefügt
- **Eigene Extraktion ist jetzt der Standard (`extraction.py`).** Inkrementell über einen
  Datei-Hash-Cache (unveränderte Dateien kosten keinen LLM-Aufruf), volle Coverage inkl.
  Docker-Compose, Configs, Docs und .env-Vorlagen, faktenreiche rationale-Texte.
  Clustering/Report/graph.html liefert weiterhin `graphify cluster-only` auf unserer
  graph.json; schlägt die eigene Extraktion fehl, fällt der Nacht-Lauf auf
  `graphify extract` zurück. Nebenbefund behoben: das 900-Token-Antwortlimit in `llm.py`
  schnitt Extraktions-JSON ab (Tolga: 27 → 93 Knoten nach dem Fix) — das Limit ist jetzt
  parametrierbar. Tests: `tests/test_extraction.py` (6 Tests, u. a. Inkrementalität und
  „kaputte Antwort verliert kein altes Wissen").
- **Eigene Hybrid-Retrieval-Engine (`semantic.py`).** `graph_query` (MCP) und der Fragen-Tab
  steigen jetzt semantisch in den Graphen ein (lokales mehrsprachiges Embedding-Modell,
  fastembed/ONNX, CPU, offline) und mischen die relevantesten Roh-Datei-Auszüge dazu.
  Benchmark (26 Gold-Fragen, 7 Projekte): **96 % Hit-Rate @1200 Tokens / 69 % @400** statt
  46 %/42 % mit dem bisherigen lexikalischen graphify-Lookup. Dreistufige Fallback-Kette
  (Hybrid → Graph → graphify-CLI), selbstheilende Indizes, fehlender Chunk-Index blockiert
  nie eine Anfrage. Neue Tests: `tests/test_semantic.py` (9 Tests, 83 % Modul-Coverage);
  Stresstest: 80 parallele Hybrid-Queries ohne Fehler.

### Behoben (UI)
- **WCAG-Kontrast im Light-Theme:** Akzent-Grün `#16a34a` → `#15803d`, gedämpftes Grau
  `#7a889f` → `#64708a` (beide vorher unter 4.5:1 auf Weiß). Lighthouse-Accessibility jetzt
  100 (mobil + desktop); Meta-Description ergänzt.

### Geändert
- **Projekt entfernen löscht jetzt komplett.** Bisher entfernte der Papierkorb-Knopf in der
  Projektliste nur den Eintrag aus dem Nacht-Mapping — der Graph blieb im Hub sichtbar und
  abfragbar. Jetzt fallen mit: die Hub-Kopie im Wissens-Repo (inkl. Git-Commit + Push wie bei
  graphify-sync), das lokale `graphify-out/` im Projektordner und die gespeicherten Antworten.
  Der Projektordner selbst bleibt unberührt; `hub-backups`/`_claude` sind vor Namenskollisionen
  geschützt. Bestätigungsdialog sagt jetzt ehrlich, was gelöscht wird; Audit-Log erhält einen
  `GRAPH-PURGE`-Eintrag mit allen gelöschten Pfaden.

### Behoben
- **„Erklären lassen" und der Fragen-Tab waren tot**, sobald das Modell auf die gpt-5-Familie
  stand. Die schickt `max_tokens` — die neuen Modelle verlangen `max_completion_tokens` und
  antworten sonst mit HTTP 400. Der Hub fiel still auf die Graph-Rohdaten zurück, sodass der
  Nutzer statt einer Erklärung eine Knotenliste sah. `llm.py` wählt den Namen jetzt nach Modell
  **und heilt sich selbst**: Widerspricht der Anbieter trotzdem, wird einmal mit dem anderen
  Namen wiederholt — das nächste neue Modell legt den Hub nicht wieder lahm.
- **Der Nacht-Lauf zerstörte die Bereichsnamen.** Er rief `graphify extract` + `sync` auf, aber nie
  `graphify label`. Clustern ohne Benennen heißt: Jeder neue Bereich hieß in der Oberfläche wieder
  „Bereich 0, 1, 2…". Jede Benennung zerfiel damit in der nächsten Nacht, sobald sich ein Projekt
  änderte. Jetzt läuft `label --missing-only` nach jedem Extract — bestehende Namen bleiben, nur
  neue werden benannt (kostet fast nichts).
- **Die Oberfläche verschluckte Server-Fehler.** Drei Stellen zeigten nur „Fehler beim Speichern"
  und warfen die Erklärung des Servers weg; sieben weitere lasen sie über ein zerbrechliches
  `(await r.json()).error`, das bei einer nicht-JSON-Antwort selbst wirft. Alle zehn laufen jetzt
  über ein sicheres `fehlerText()`. Das Secret-Formular hat eine **stehende** Fehlerzeile statt
  eines Toasts, der nach 3 Sekunden weg ist. (Genau daran scheiterte das Anlegen eines Secrets
  mit „@" im Namen — der Nutzer sah nie, welche Zeichen erlaubt sind.)

### Hinzugefügt
- **Antwort-Speicher.** Jede Erklärung und jede Frage wird gespeichert und beim nächsten Mal
  wiederverwendet: 7,9 s und echtes Geld → **0,3 s und gratis**. Der Schlüssel enthält den Stand
  des Graphen, sodass Antworten nach einem Neu-Mapping von selbst verfallen — eine veraltete
  Erklärung wäre schlimmer als gar keine. Die Oberfläche sagt ehrlich „gespeichert · vor 4 Min."
  und bietet „Neu erklären" an. Jede Antwort wandert zusätzlich per `graphify save-result` ins
  Graph-Gedächtnis, den Rückkanal für `graphify reflect`.

### Hinzugefügt
- **Notizen aus dem Chat.** Drei neue MCP-Werkzeuge: `note_save` legt Wissen aus einem
  Gespräch als Markdown-Datei unter `~/knowledge-notes/<projekt>/` ab und registriert das
  Projekt automatisch fürs Nacht-Mapping; `note_list` zeigt die Notizen eines Projekts;
  `project_create` legt ein leeres Wissensgebiet an. Bewusst kein eigenes Datenbankformat:
  graphify liest Markdown ohnehin semantisch, und die Dateien bleiben mit jedem Editor
  lesbar. Der Kreislauf ist damit geschlossen — „merk dir das" im Chat wird zur Notiz,
  die Notiz zum Graphen, der Graph per `graph_query` befragbar. Gleicher Titel am selben
  Tag überschreibt nie (wird nummeriert), Projektnamen können nicht aus dem Notiz-Ordner
  ausbrechen, jede Speicherung landet im Audit-Log. +8 Tests.

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
