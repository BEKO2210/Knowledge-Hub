'use strict';

/* ================= Sprache =================
   Muss GANZ oben stehen: Der Theme-Block weiter unten läuft beim Laden sofort los
   und ruft t() auf. Stünden LANG und EN erst darunter, läge beides noch in der
   temporalen Todeszone (let/const) — die Seite bliebe weiß. */
let LANG = 'de';
const EN = {
  'Der Hub hat die Anfrage abgelehnt.': 'The hub rejected the request.',
  'Der Hub hat keine gültige Antwort geschickt. Steht die Verbindung noch?': 'The hub did not send a valid response. Is the connection still up?',
  'Umschalten fehlgeschlagen': 'Could not switch it',
  'Entfernen fehlgeschlagen': 'Could not remove it',
  'Zwei-Faktor lässt sich gerade nicht einrichten.': 'Two-factor cannot be set up right now.',
  'gespeichert · {wann}': 'saved · {wann}',
  'Neu erklären': 'Explain again',
  'KI antwortet…': 'AI is answering…',
  'Durchsucht den Graphen und formuliert die Antwort — bis zu zwei Minuten.': 'Searching the graph and writing the answer — up to two minutes.',
  'KI-Antwort': 'AI answer',
  'Bitte Name und Wert ausfüllen.': 'Please fill in both name and value.',
  'Adresse kopiert': 'Address copied',
  'Token kopiert': 'Token copied',
  /* Fehler im Mapping-Verlauf */
  'Sicherung fehlgeschlagen': 'Backup failed',
  'erledigt': 'resolved',
  '„{p}“ konnte nicht gemappt werden.': '“{p}” could not be mapped.',
  '„{p}“ wurde gemappt, ließ sich aber nicht ins Wissens-Repo übertragen.': '“{p}” was mapped, but could not be synced to the knowledge repo.',
  'Prüfen & reparieren': 'Check & repair',
  'Öffne die Projektliste — dort „{p}“ reparieren.': 'Opening the project list — repair “{p}” there.',
  'Die verschlüsselte Sicherung lief nicht durch. Die Graphen sind davon nicht betroffen — aber der Vault liegt dann nur auf dieser Maschine.': 'The encrypted backup did not complete. Your graphs are unaffected — but the vault then exists only on this machine.',
  'Zur Sicherung': 'Go to backup',
  'Erledigt — nicht mehr melden': 'Resolved — stop warning me',
  'Wieder als offen markieren': 'Mark as open again',
  'Als erledigt abgehakt': 'Marked as resolved',
  'Wieder als offen markiert': 'Marked as open again',

  /* Rahmen, Netz, Anmeldung */
  'Zum Dunkelmodus': 'Switch to dark mode',
  'Zum Hellmodus': 'Switch to light mode',
  'Keine Verbindung zum Hub. Prüfe deine Internetverbindung.': 'Cannot reach the hub. Check your internet connection.',
  'Vault ist gesperrt — bitte neu anmelden': 'The vault is locked — please sign in again',
  'Im Hub ist etwas schiefgelaufen.': 'Something went wrong in the hub.',
  'Referenz: {ref}': 'Reference: {ref}',
  'Zu viele Fehlversuche — bitte 15 Minuten warten.': 'Too many failed attempts — please wait 15 minutes.',
  'Falsches Passwort — bitte erneut versuchen.': 'Wrong password — please try again.',
  'Server nicht erreichbar.': 'Server unreachable.',
  'Ein Fehler in der Oberfläche: {msg}': 'An error in the interface: {msg}',

  /* Allgemeine Rückmeldungen */
  'Gespeichert: {name}': 'Saved: {name}',
  'Gelöscht: {name}': 'Deleted: {name}',
  'Komplett entfernt: {name}': 'Completely removed: {name}',
  'Kopiert': 'Copied',
  'Kopieren': 'Copy',
  'Kopieren nicht möglich': 'Could not copy',
  'In Zwischenablage kopiert': 'Copied to clipboard',
  'Fehler': 'Error',
  'Fehlgeschlagen': 'Failed',
  'Fehler beim Speichern': 'Could not save',
  'Start fehlgeschlagen': 'Could not start',
  'Erneut versuchen': 'Try again',
  'Fertig': 'Done',
  'Aktiv': 'Active',
  'Problem': 'Problem',
  'Wert anzeigen': 'Show value',
  'Wert verbergen': 'Hide value',
  'Wert kopieren': 'Copy value',
  'Löschen': 'Delete',

  /* Fragen */
  'Im Graph zeigen: {label}': 'Show in graph: {label}',
  'Fehler bei der Anfrage.': 'The request failed.',
  'Knoten im aktuellen Ausschnitt nicht gefunden': 'Node not found in the current view',

  /* Mapping */
  'Eigenes Modell eingeben…': 'Enter a custom model…',
  'Lokales Modell — kostenlos, aber deutlich langsamer. Ollama muss auf dem Server laufen.': 'Local model — free, but noticeably slower. Ollama must be running on the server.',
  '{label}-Key': '{label} key',
  'Ollama läuft lokal — kein Key nötig': 'Ollama runs locally — no key needed',
  '{label}-Key ist hinterlegt (Vault: {secret})': '{label} key is stored (vault: {secret})',
  '{label}-Key gespeichert — Mapping ist einsatzbereit': '{label} key saved — mapping is ready to go',
  'Automatik aktiv': 'Automation on',
  'Automatik ausgeschaltet': 'Automation off',
  'Nächster Lauf: {when}': 'Next run: {when}',
  '{n} Projekte': '{n} projects',
  '— kein Key': '— no key',
  'Zuerst einen API-Key hinterlegen': 'Store an API key first',
  'Summe aller {n} Läufe · {tok} Tokens': 'Total across {n} runs · {tok} tokens',
  'Letzter Lauf ({date}) · {tok} Tokens': 'Last run ({date}) · {tok} tokens',
  '({n} Fehler)': '({n} errors)',
  '{n} Fehler': '{n} errors',
  'Projekte im letzten Lauf': 'Projects in the last run',
  '(noch kein Lauf protokolliert)': '(no run logged yet)',
  'Noch kein Lauf protokolliert — starte oben „Jetzt ausführen“.': 'No run logged yet — start one with “Run now” above.',
  'Geschätzte Kosten je Lauf · älteste links ({n} Läufe)': 'Estimated cost per run · oldest on the left ({n} runs)',
  'Lauf vom {date} {time} Uhr — Details': 'Run on {date} at {time} — details',
  '{time} Uhr': '{time}',
  '{tok} Tok · {n} Kn.': '{tok} tok · {n} nodes',
  'Keine Projektdaten für diesen Lauf.': 'No project data for this run.',
  'Fehlgeschlagen: {names}': 'Failed: {names}',
  'Nacht-Mapping eingeschaltet': 'Nightly mapping enabled',
  'Nacht-Mapping ausgeschaltet': 'Nightly mapping disabled',
  'Fehler beim Umschalten': 'Could not toggle',
  'Bitte ein Modell wählen oder eingeben': 'Please choose or enter a model',
  'Gespeichert — täglich um {time} mit {model}': 'Saved — daily at {time} using {model}',
  'Mapping gestartet': 'Mapping started',

  /* Projekte verwalten */
  'Noch keine Projekte': 'No projects yet',
  'Füge über „Hinzufügen“ ein Code-Verzeichnis hinzu — es wird dann im Nacht-Lauf automatisch zu einem Wissensgraphen verarbeitet.': 'Add a code directory via “Add” — the nightly run then turns it into a knowledge graph automatically.',
  'Projekt {name} im Nacht-Lauf': 'Project {name} in the nightly run',
  'noch nicht gemappt': 'not mapped yet',
  'Ausschluss-Regeln bearbeiten': 'Edit exclusion rules',
  'Ausschluss-Regeln': 'Exclusion rules',
  '(aktiv)': '(active)',
  'Projekt entfernen': 'Remove project',
  'Reparieren': 'Repair',
  'Repariere…': 'Repairing…',
  'Reparatur gestartet…': 'Repair started…',
  'Reparatur fehlgeschlagen — siehe Protokoll': 'Repair failed — see the log',
  '{name} repariert': '{name} repaired',
  'Das lässt sich nur direkt auf dem Server beheben — Befehl oben.': 'This can only be fixed directly on the server — see the command above.',
  '{name} vom Nacht-Lauf ausgenommen': '{name} excluded from the nightly run',
  '{name} wieder im Nacht-Lauf': '{name} back in the nightly run',
  '„{name}" komplett entfernen? Löscht auch den Graphen im Hub, lokale Graph-Daten und gespeicherte Antworten — der Projektordner selbst bleibt unberührt.': 'Remove “{name}” completely? Also deletes the graph in the hub, local graph data and saved answers — the project folder itself is untouched.',
  'Übergeordneter Ordner': 'Parent folder',
  'Keine Unterordner.': 'No subfolders.',
  'Projekt hinzugefügt — läuft ab jetzt im Nacht-Mapping mit': 'Project added — it will be part of nightly mapping from now on',
  'z. B.\nnode_modules/\ndata/\n.env\n*.key': 'e.g.\nnode_modules/\ndata/\n.env\n*.key',
  'Ausschluss-Regeln gespeichert': 'Exclusion rules saved',
  'Empfohlene Ausschlüsse vorbefüllt — Speichern übernimmt sie': 'Recommended exclusions prefilled — save to apply them',

  /* Graph */
  'Alle': 'All',
  'Knoten': 'nodes',
  '{n} Knoten': '{n} nodes',
  '{a}/{b} Knoten · {c} Kanten': '{a}/{b} nodes · {c} edges',
  'Kein Knoten gefunden': 'No node found',
  'Bereich {n}': 'Area {n}',
  'Community {n}': 'Community {n}',
  '{n} Verbindungen': '{n} connections',
  'Zielknoten anklicken — der kürzeste Weg wird angezeigt': 'Click a target node — the shortest path will be shown',
  'Pfad-Modus: klicke den Zielknoten (oder Esc zum Abbrechen)': 'Path mode: click the target node (or press Esc to cancel)',
  'Kein Weg zwischen den beiden Knoten gefunden': 'No path found between the two nodes',
  '{n} Knoten über {s} Schritte:': '{n} nodes across {s} steps:',
  'Weg gefunden: {n} Schritte': 'Path found: {n} steps',
  'Ziehen zum Verschieben · Scrollen zum Zoomen · Klick auf Knoten für Details': 'Drag to pan · scroll to zoom · click a node for details',
  'Keine Antwort erhalten.': 'No answer received.',
  'Rohdaten aus dem Graphen': 'Raw data from the graph',
  'Fehler bei der Erklärung — bitte erneut versuchen.': 'The explanation failed — please try again.',

  /* Secrets */
  'Der Vault ist noch leer': 'The vault is still empty',
  'Leg oben deinen ersten API-Key oder dein erstes Token ab — etwa den OpenAI-Key fürs Nacht-Mapping. Es wird sofort verschlüsselt.': 'Store your first API key or token above — the OpenAI key for nightly mapping, for instance. It is encrypted straight away.',
  '„{name}" wird unwiderruflich aus dem Vault gelöscht.': '“{name}” will be permanently deleted from the vault.',
  'Name und Wert eingeben': 'Enter a name and a value',

  /* Geräte / Sitzungen */
  'noch nie': 'never',
  'gerade eben': 'just now',
  'vor {n} Min.': '{n} min ago',
  'vor {n} Std.': '{n} h ago',
  'gestern': 'yesterday',
  'vor {n} Tagen': '{n} days ago',
  'Programm': 'Program',
  'dieses Gerät': 'this device',
  'läuft nie ab': 'never expires',
  'Gerät abmelden': 'Sign out device',
  'zuletzt aktiv {when}': 'last active {when}',
  'läuft in {n} Tagen ab': 'expires in {n} days',
  '„{label}" verliert sofort den Zugriff auf deinen Hub.': '“{label}” will lose access to your hub immediately.',
  '{label} abgemeldet': '{label} signed out',
  'Abmelden fehlgeschlagen': 'Sign-out failed',
  'Noch keine Clients verbunden — erzeuge oben ein Token oder verbinde claude.ai.': 'No clients connected yet — create a token above or connect claude.ai.',
  'Alle anderen Geräte und KI-Clients verlieren sofort den Zugriff. Du bleibst angemeldet.': 'All other devices and AI clients lose access immediately. You stay signed in.',
  '{n} Zugänge widerrufen': '{n} tokens revoked',

  /* Verbinden */
  'Token erzeugt für „{label}“': 'Token created for “{label}”',
  'teste…': 'testing…',
  'Verbindung steht': 'Connection works',
  'Token nicht akzeptiert': 'Token rejected',
  'Server erreichbar (HTTP {status})': 'Server reachable (HTTP {status})',
  'nicht erreichbar': 'unreachable',
  'DEIN_TOKEN': 'YOUR_TOKEN',
  'Öffne <b>claude.ai</b> → <b>Einstellungen</b> → <b>Connectors</b>.': 'Open <b>claude.ai</b> → <b>Settings</b> → <b>Connectors</b>.',
  'Klick auf <b>„Connector hinzufügen"</b> → <b>„Eigenen Connector"</b>.': 'Click <b>“Add connector”</b> → <b>“Add custom connector”</b>.',
  'Füge diese Adresse ein und bestätige:': 'Paste this address and confirm:',
  'claude.ai fragt einmalig dein <b>Zugangspasswort</b> ab (sichere OAuth-Anmeldung) — <b>kein Token nötig</b>.': 'claude.ai asks once for your <b>access password</b> (secure OAuth sign-in) — <b>no token needed</b>.',
  'Führe im Terminal diesen Befehl aus:': 'Run this command in your terminal:',
  '<b>Claude Code</b> kennt deinen Hub jetzt.': '<b>Claude Code</b> now knows your hub.',
  'Erzeuge oben zuerst ein <b>Geräte-Token</b> — es füllt den Befehl vollständig aus.': 'Create a <b>device token</b> above first — it fills in the command for you.',
  'Öffne <b>Claude Desktop</b> → <b>Einstellungen</b> → <b>Entwickler</b> → <b>Konfiguration bearbeiten</b>.': 'Open <b>Claude Desktop</b> → <b>Settings</b> → <b>Developer</b> → <b>Edit config</b>.',
  'Füge diesen Eintrag ein (benötigt <span class="mono">Node.js</span>) und starte Claude Desktop neu:': 'Add this entry (requires <span class="mono">Node.js</span>) and restart Claude Desktop:',
  'Jeder MCP-Client mit <b>Streamable-HTTP</b>-Transport verbindet sich mit dieser Adresse …': 'Any MCP client with <b>streamable HTTP</b> transport connects to this address …',
  '… und diesem Header:': '… and this header:',
  '↑ Erzeuge oben ein Geräte-Token — es ersetzt <DEIN_TOKEN> automatisch.': '↑ Create a device token above — it replaces <YOUR_TOKEN> automatically.',

  /* Diagnose */
  'Diagnose nicht abrufbar.': 'Diagnostics unavailable.',
  'Es gibt ein Problem': 'There is a problem',
  'Läuft — mit Hinweisen': 'Running — with warnings',
  'Alles in Ordnung': 'All good',
  '{n} Punkt(e) brauchen deine Aufmerksamkeit.': '{n} item(s) need your attention.',
  '{n} Hinweis(e) — das System läuft, könnte aber besser abgesichert sein.': '{n} warning(s) — the system runs, but could be better protected.',
  '{n} Prüfungen bestanden.': '{n} checks passed.',
  'Sperren aufheben': 'Lift blocks',
  'Sperren aufgehoben': 'Blocks lifted',
  'KI-Anbieter': 'AI provider',
  'Projekte': 'Projects',
  'Secrets im Vault': 'Secrets in the vault',
  'Wissensgraphen': 'Knowledge graphs',
  'Adresse für KI-Clients (MCP)': 'Address for AI clients (MCP)',

  /* Zwei-Faktor */
  'Beim Anmelden wird zusätzlich zum Passwort ein Code aus deiner App verlangt. Noch <b>{n}</b> Wiederherstellungscodes übrig.': 'Signing in requires a code from your app on top of the password. <b>{n}</b> recovery codes left.',
  'Aktueller Code zum Abschalten': 'Current code to switch it off',
  '2FA ausschalten': 'Disable 2FA',
  'Schütze deinen Zugang mit einer Authenticator-App (Google Authenticator, Aegis, 1Password …). Selbst wer dein Passwort kennt, kommt dann ohne dein Handy nicht rein.': 'Protect your access with an authenticator app (Google Authenticator, Aegis, 1Password …). Even someone who knows your password cannot get in without your phone.',
  'Einrichten': 'Set up',
  '<b>1.</b> Scanne diesen QR-Code mit deiner Authenticator-App:': '<b>1.</b> Scan this QR code with your authenticator app:',
  'Kein Scanner? Geheimnis von Hand eintragen:': 'No scanner? Enter the secret manually:',
  '<b>2.</b> Bestätige mit dem aktuellen Code aus der App:': '<b>2.</b> Confirm with the current code from the app:',
  '6-stelliger Code': '6-digit code',
  'Aktivieren': 'Activate',
  '2FA ist aktiv': '2FA is active',
  'Sichere diese Wiederherstellungscodes. Jeder ist einmal gültig und rettet dich, wenn du dein Handy verlierst — ohne sie wärst du ausgesperrt.': 'Keep these recovery codes safe. Each one works once and saves you if you lose your phone — without them you would be locked out.',
  'Zwei-Faktor-Authentifizierung aktiviert': 'Two-factor authentication enabled',
  'Codes kopiert': 'Codes copied',
  'Bitte abschreiben': 'Please write them down',
  'Zwei-Faktor-Schutz wirklich abschalten? Danach genügt wieder das Passwort allein.': 'Really switch off two-factor protection? The password alone will be enough again.',
  '2FA ausgeschaltet': '2FA disabled',

  /* Vault-Sicherheit */
  'Automatische Entsperrung': 'Automatic unlock',
  'Automatisch entsperren': 'Unlock automatically',
  'Der Vault öffnet sich nach einem Neustart von selbst — nötig, damit das Nacht-Mapping ohne dich an die API-Keys kommt. Der Schlüssel dafür liegt in der env-Datei: Wer dein Server-Konto übernimmt, kommt damit auch an die Secrets.': 'The vault unlocks itself after a restart — needed so nightly mapping can reach the API keys without you. The key for that sits in the env file: whoever takes over your server account can reach the secrets too.',
  '<b>Maximale Sicherheit:</b> Der Vault bleibt nach jedem Neustart gesperrt, bis du dich anmeldest. Selbst wer dein Server-Konto übernimmt, kann die Secrets nicht lesen. <b>Aber:</b> Das Nacht-Mapping überspringt dann die Dokumenten-Analyse, bis du dich einmal angemeldet hast.': '<b>Maximum security:</b> the vault stays locked after every restart until you sign in. Even someone who takes over your server account cannot read the secrets. <b>But:</b> nightly mapping will skip document analysis until you have signed in once.',
  'Vault-Format v{v} · Passwort-Entsperrung: {state}': 'Vault format v{v} · password unlock: {state}',
  'eingerichtet': 'set up',
  'nicht eingerichtet': 'not set up',
  'Zugangspasswort ändern': 'Change access password',
  'Aktuelles Passwort': 'Current password',
  'Neues Passwort (min. 8 Zeichen)': 'New password (min. 8 characters)',
  'Ändern': 'Change',
  'Ändere…': 'Changing…',
  'Die Secrets werden dabei nicht neu verschlüsselt — nur der Zugang. Dauert einen Moment (die Ableitung ist absichtlich langsam).': 'The secrets are not re-encrypted — only the access is. This takes a moment (key derivation is deliberately slow).',
  'Automatische Entsperrung aktiv': 'Automatic unlock is on',
  'Vault bleibt künftig nach Neustarts gesperrt': 'The vault will stay locked after restarts from now on',
  'Passwort geändert — beim nächsten Anmelden gilt das neue.': 'Password changed — the new one applies at your next sign-in.',

  /* Sicherung */
  'Es wird nichts gesichert': 'Nothing is being backed up',
  'Stirbt die Festplatte, sind alle Secrets unwiederbringlich weg. Richte eine Sicherung ein: Vault, Schlüssel und Einstellungen werden dann verschlüsselt in deinen Backup-Ordner und in dein privates Git-Repo gelegt — nur mit der Backup-Passphrase lesbar.': 'If the disk dies, every secret is gone for good. Set up a backup: vault, keys and settings are then written encrypted to your backup folder and to your private Git repo — readable only with the backup passphrase.',
  'Sicherung einrichten': 'Set up backup',
  'Offsite (Git)': 'Offsite (Git)',
  'Lokal': 'Local',
  'Letzte Sicherung': 'Last backup',
  'Sicherungen vorhanden': 'Backups stored',
  'Offsite-Ziel (Git-Repository) {action}': '{action} offsite target (Git repository)',
  'ändern': 'Change',
  'einrichten': 'Set up',
  'Damit die Sicherung einen Plattenausfall übersteht, gehört sie in ein Repository auf einem anderen Rechner. Die Datei ist verschlüsselt — das Repo sieht nur unlesbare Daten. Für GitHub brauchst du einen Zugriffstoken mit Schreibrecht auf genau dieses Repo (<span class="mono" style="font-size:.9em">Settings → Developer settings → Personal access tokens → Fine-grained → Contents: Read and write</span>). Der Token wird im Vault verschlüsselt.': 'For a backup to survive a disk failure, it belongs in a repository on another machine. The file is encrypted — the repo only ever sees unreadable data. For GitHub you need an access token with write permission on exactly this repo (<span class="mono" style="font-size:.9em">Settings → Developer settings → Personal access tokens → Fine-grained → Contents: Read and write</span>). The token is stored encrypted in the vault.',
  'https://github.com/deinname/dein-backup-repo.git': 'https://github.com/yourname/your-backup-repo.git',
  'Zugriffstoken': 'Access token',
  '— neuen Token eingeben —': '— enter a new token —',
  'GitHub-Token (ghp_… oder github_pat_…)': 'GitHub token (ghp_… or github_pat_…)',
  'Token anzeigen': 'Show token',
  'Unterordner': 'Subfolder',
  'Ziel speichern': 'Save target',
  'Ziel entfernen': 'Remove target',
  'Speichere…': 'Saving…',
  'Offsite-Ziel gespeichert — jetzt „Jetzt sichern“ drücken zum Testen': 'Offsite target saved — press “Back up now” to test it',
  'Das Offsite-Ziel wird entfernt. Künftige Sicherungen liegen dann nur noch lokal.': 'The offsite target will be removed. Future backups will then only be stored locally.',
  'Offsite-Ziel entfernt': 'Offsite target removed',
  'Sichere diese Passphrase JETZT': 'Save this passphrase NOW',
  'Sie ist der einzige Schlüssel zu deinen Sicherungen. Geht sie verloren, sind auch die Sicherungen wertlos. Leg sie in deinen Passwort-Manager — nicht auf diesen Server.': 'It is the only key to your backups. If it is lost, the backups are worthless too. Put it in your password manager — not on this server.',
  'Habe ich gesichert — jetzt sichern': 'Saved it — back up now',
  'Passphrase kopiert': 'Passphrase copied',
  'Kopieren nicht möglich — bitte abschreiben': 'Could not copy — please write it down',
  'aus dem Vault: {name}': 'from the vault: {name}',
  'Sicherung gestartet': 'Backup started',

  /* Audit */
  'Noch nichts protokolliert': 'Nothing logged yet',
  'Sobald ein Secret gelesen, gesetzt oder gelöscht wird, erscheint hier der Eintrag — mit Zeitpunkt und Client.': 'As soon as a secret is read, set or deleted, the entry shows up here — with timestamp and client.',
};

function t(s) {
  if (LANG !== 'en') return s;
  return (typeof EN === 'object' && EN[s]) || s;
}
/* Platzhalter-Variante: t2('Entfernt: {x}', {x: name}) */
function t2(s, vars) {
  let out = t(s);
  for (const k in vars) out = out.replaceAll('{' + k + '}', vars[k]);
  return out;
}

let TOKEN = localStorage.getItem('kmcp_ui_token') || '';
const $ = id => document.getElementById(id);

/* ================= Theme (Hell/Dunkel) ================= */
let CANVAS_INK = '#e2e8f0', CANVAS_HALO = 'rgba(15,23,42,.88)';
function readCanvasColors() {
  const cs = getComputedStyle(document.documentElement);
  CANVAS_INK = cs.getPropertyValue('--canvas-ink').trim() || CANVAS_INK;
  CANVAS_HALO = cs.getPropertyValue('--canvas-halo').trim() || CANVAS_HALO;
}
function currentTheme() {
  return document.documentElement.dataset.theme
    || (matchMedia('(prefers-color-scheme: light)').matches ? 'light' : 'dark');
}
function updateThemeIcon() {
  const b = $('themebtn'); if (!b) return;
  const light = currentTheme() === 'light';
  b.innerHTML = `<svg class="ic" viewBox="0 0 24 24"><use href="#${light ? 'i-moon' : 'i-sun'}"/></svg>`;
  b.setAttribute('aria-label', light ? t('Zum Dunkelmodus') : t('Zum Hellmodus'));
}
function applyTheme(t) {
  if (t === 'light' || t === 'dark') document.documentElement.dataset.theme = t;
  else delete document.documentElement.dataset.theme;   // '' = Systemeinstellung
  readCanvasColors(); updateThemeIcon();
}
function toggleTheme() {
  const next = currentTheme() === 'light' ? 'dark' : 'light';
  try { localStorage.setItem('kmcp_theme', next); } catch {}
  applyTheme(next);
  try { navigator.vibrate && navigator.vibrate(8); } catch {}
}
(function initTheme() {
  let saved = ''; try { saved = localStorage.getItem('kmcp_theme') || ''; } catch {}
  applyTheme(saved);
  matchMedia('(prefers-color-scheme: light)').addEventListener('change', () => { readCanvasColors(); updateThemeIcon(); });
})();

/* ================= Sprache (DE/EN — i18n-Grundgerüst) =================
   Statische „Chrome"-Texte (Navigation, Überschriften, Untertitel, Login, Tour)
   tragen ein data-en-Attribut und werden per Umschalter getauscht; der DE-Text
   wird beim ersten Wechsel in data-de gesichert. Die tiefer liegenden, dynamisch
   erzeugten Detailtexte bleiben vorerst Deutsch (nächster Ausbauschritt). */
/* Übersetzung dynamisch erzeugter Texte (Toasts, Listen, Leerzustände, Befunde).
   Der deutsche Satz IST der Schlüssel — so bleibt der Code lesbar und eine fehlende
   Übersetzung fällt weich zurück, statt einen leeren Knopf zu hinterlassen.
   Statische Texte im Markup tragen stattdessen data-en. */
/* Deutsche Zeichenkette -> englische Entsprechung. Der deutsche Satz ist der Schlüssel. */


function setLang(l) {
  LANG = (l === 'en') ? 'en' : 'de';
  document.querySelectorAll('[data-en]').forEach(el => {
    if (el.dataset.de === undefined) el.dataset.de = el.textContent;
    el.textContent = (LANG === 'en') ? el.dataset.en : el.dataset.de;
  });
  /* Auch Platzhalter und Titel wollen übersetzt werden — sonst bleibt das
     Suchfeld deutsch, während alles ringsum englisch ist. */
  document.querySelectorAll('[data-en-ph]').forEach(el => {
    if (el.dataset.dePh === undefined) el.dataset.dePh = el.placeholder || '';
    el.placeholder = (LANG === 'en') ? el.dataset.enPh : el.dataset.dePh;
  });
  document.querySelectorAll('[data-en-title]').forEach(el => {
    /* aria-label und title getrennt behandeln: Ein Element, das nur ein aria-label
       trägt (Sektionen, Landmarken), darf KEINEN title bekommen — sonst klebt am
       Handy wie am Desktop plötzlich ein Tooltip über einem ganzen Bereich. */
    if (el.dataset.deLabel === undefined) el.dataset.deLabel = el.getAttribute('aria-label') || '';
    if (el.dataset.deTitle === undefined) el.dataset.deTitle = el.getAttribute('title') || '';
    const en = el.dataset.enTitle;
    if (el.dataset.deLabel) el.setAttribute('aria-label', (LANG === 'en') ? en : el.dataset.deLabel);
    if (el.dataset.deTitle) el.title = (LANG === 'en') ? en : el.dataset.deTitle;
  });
  document.documentElement.lang = LANG;
  const b = $('langbtn'); if (b) b.textContent = LANG === 'en' ? 'DE' : 'EN';
  const ml = $('morelanglbl'); if (ml) ml.textContent = LANG === 'en' ? 'Language: English' : 'Sprache: Deutsch';
  try { localStorage.setItem('kmcp_lang', LANG); } catch {}
  if ($('tourdlg') && $('tourdlg').open) renderTour();
  redrawDynamic();
}

/* Dynamisch gerenderte Bereiche neu aufbauen — sonst bliebe alles, was per
   JavaScript in die Seite geschrieben wurde, in der alten Sprache stehen. */
function redrawDynamic() {
  if (!window.BOOTED) return;
  try {
    if (typeof buildLegend === 'function' && window.FG) buildLegend();
    if (typeof CURRENT_TAB === 'string' && CURRENT_TAB) tab(CURRENT_TAB);
  } catch (e) { /* beim Start noch nichts zu zeichnen */ }
}

function toggleLang() { haptic(6); setLang(LANG === 'en' ? 'de' : 'en'); }
(function initLang() {
  /* Die Sprache des Browsers entscheidet: Wer Deutsch eingestellt hat, bekommt Deutsch,
     alle anderen Englisch. Eine bewusste Wahl des Nutzers sticht das immer. */
  let gewaehlt = null;
  try { gewaehlt = localStorage.getItem('kmcp_lang'); } catch {}
  const automatisch = (navigator.language || '').toLowerCase().startsWith('de') ? 'de' : 'en';
  setLang(gewaehlt || automatisch);
})();

async function api(path, opts = {}) {
  /* X-Lang: Diagnose-Befunde und Fehlermeldungen entstehen im Server. Ohne diesen
     Kopfzeilen-Eintrag bliebe der Diagnose-Tab deutsch, während alles ringsum englisch ist. */
  opts.headers = Object.assign({'Authorization': 'Bearer ' + TOKEN, 'X-Lang': LANG}, opts.headers || {});
  let r;
  try {
    r = await fetch(path, opts);
  } catch (e) {
    /* Ein ABGEBROCHENER Aufruf ist kein Fehler: Der Browser bricht laufende Anfragen ab,
       wenn der Nutzer die Seite verlässt oder neu lädt — und wir brechen selbst ab, wenn
       eine Anfrage veraltet ist. Ohne diese Zeile sah der Nutzer dann fälschlich
       „Keine Verbindung zum Hub", obwohl gar nichts kaputt war. */
    if (e.name === 'AbortError') throw e;
    // Kein Netz, Server weg, Tunnel unterbrochen — der häufigste Fall im Alltag.
    showError(t('Keine Verbindung zum Hub. Prüfe deine Internetverbindung.'));
    throw e;
  }
  if (r.status === 401) { logout(); throw new Error('unauthorized'); }
  if (r.status === 423) {                    // Vault gesperrt -> neu anmelden
    toast(t('Vault ist gesperrt — bitte neu anmelden'), false);
    logout();
    throw new Error('locked');
  }
  if (r.status >= 500) {
    // Bis hierher scheiterten Serverfehler stumm: Der Aufrufer rief .json() auf,
    // das warf, und der Nutzer sah — nichts. Jetzt sagen wir es ihm.
    let ref = '';
    try { ref = (await r.clone().json()).ref || ''; } catch (e) { /* keine JSON-Antwort */ }
    showError(t('Im Hub ist etwas schiefgelaufen.') + (ref ? ' ' + t2('Referenz: {ref}', {ref}) : ''));
    throw new Error('server error ' + r.status);
  }
  return r;
}

/* Fehlerbanner: bleibt stehen, bis der Nutzer es wegklickt oder etwas gelingt.
   Ein Toast wäre hier falsch — er verschwindet, bevor man ihn gelesen hat. */
function showError(text) {
  const b = $('errbanner');
  if (!b) return;
  b.querySelector('.errtext').textContent = text;
  b.classList.add('on');
}
function hideError() {
  const b = $('errbanner');
  if (b) b.classList.remove('on');
}

/* Die Erklärung des Servers herausholen — sicher.
   Vorher stand an mehreren Stellen `(await r.json()).error || '…'`. Antwortet der
   Server einmal NICHT mit JSON (Proxy-Fehlerseite, leerer Body), wirft r.json() und
   die Meldung verschwindet spurlos. Und an drei Stellen wurde die Erklärung gar nicht
   erst gelesen — der Nutzer sah nur „Fehler beim Speichern" und wusste nicht, warum.
   Genau daran ist das Anlegen eines Secrets mit „@" im Namen gescheitert. */
async function fehlerText(r, rueckfall) {
  try {
    const j = await r.clone().json();
    if (j && typeof j.error === 'string' && j.error.trim()) return j.error;
  } catch (e) { /* keine JSON-Antwort — dann eben der Rückfall */ }
  return rueckfall;
}
async function zeigeFehler(r, rueckfall) {
  toast(await fehlerText(r, rueckfall), false);
}

/* JSON vom Hub holen — und laut scheitern, statt still zu hängen.
   Vorher stand an 22 Stellen `await holeJson(x)`. Antwortet der Tunnel mit
   einer HTML-Fehlerseite (502) oder einem leeren Body, wirft .json() eine Ausnahme.
   Neun Stellen fingen sie gar nicht: Der Spinner drehte sich für immer. Die anderen
   dreizehn fingen sie und gaben stumm auf — die Karte blieb einfach leer, ohne dass
   der Nutzer je erfuhr, warum. Beides ist jetzt nicht mehr möglich. */
async function holeJson(pfad, opts) {
  const r = await api(pfad, opts);          // api() behandelt bereits 401/423/5xx
  if (!r.ok) {
    const msg = await fehlerText(r, t('Der Hub hat die Anfrage abgelehnt.'));
    showError(msg);
    throw new Error('http ' + r.status);
  }
  try {
    return await r.json();
  } catch (e) {
    showError(t('Der Hub hat keine gültige Antwort geschickt. Steht die Verbindung noch?'));
    throw e;
  }
}
function toast(msg, ok = true) {
  const t = document.createElement('div');
  t.className = 'toast' + (ok ? '' : ' err');
  t.innerHTML = `<svg class="ic" viewBox="0 0 24 24"><use href="#i-${ok ? 'check' : 'alert'}"/></svg><span></span>`;
  t.querySelector('span').textContent = msg;
  $('toasts').appendChild(t);
  setTimeout(() => t.remove(), 3200);
}
function askConfirm(text) {
  return new Promise(res => {
    $('cdtext').textContent = text;
    const dlg = $('confirmdlg');
    dlg.onclose = () => res(dlg.returnValue === 'yes');
    dlg.showModal();
  });
}
function togglePw(id, btn) {
  const inp = $(id);
  const show = inp.type === 'password';
  inp.type = show ? 'text' : 'password';
  btn.innerHTML = `<svg class="ic" viewBox="0 0 24 24"><use href="#i-${show ? 'eyeoff' : 'eye'}"/></svg>`;
  btn.setAttribute('aria-label', show ? t('Wert verbergen') : t('Wert anzeigen'));
}
async function doLogin(e) {
  e.preventDefault();
  const btn = $('loginbtn');
  btn.disabled = true;
  $('loginerr').textContent = '';
  try {
    const r = await fetch('/ui/api/login', {method: 'POST', headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({password: $('pw').value, code: $('code').value.trim()})});
    if (r.status === 429) { $('loginerr').textContent = t('Zu viele Fehlversuche — bitte 15 Minuten warten.'); return; }
    const j = await r.json().catch(() => ({}));
    if (r.status === 401 && j.need_2fa) {
      // Passwort stimmt, jetzt den Code abfragen
      $('coderow').style.display = 'block';
      $('code').focus();
      $('loginerr').textContent = j.error || '';
      return;
    }
    if (!r.ok) { $('loginerr').textContent = t('Falsches Passwort — bitte erneut versuchen.'); return; }
    TOKEN = j.token;
    localStorage.setItem('kmcp_ui_token', TOKEN);
    $('login').style.display = 'none';
    $('coderow').style.display = 'none'; $('code').value = '';
    boot();
  } catch { $('loginerr').textContent = t('Server nicht erreichbar.'); }
  finally { btn.disabled = false; }
}
function logout() {
  localStorage.removeItem('kmcp_ui_token'); TOKEN = '';
  $('login').style.display = 'flex';
}
let CURRENT_TAB = 'graph';
function tab(name) {
  CURRENT_TAB = name;
  document.querySelectorAll('.tab').forEach(t => t.classList.remove('on'));
  document.querySelectorAll('[data-tab]').forEach(b => {
    const on = b.dataset.tab === name;
    b.classList.toggle('on', on);
    if (on) b.setAttribute('aria-current', 'page'); else b.removeAttribute('aria-current');
  });
  $('tab-' + name).classList.add('on');
  /* Diagnose und Audit liegen hinter „Mehr“ — der Knopf zeigt an, dass man dort steht. */
  const nm = $('navmore');
  if (nm) nm.classList.toggle('on', name === 'health' || name === 'audit');
  if (name !== 'report') history.replaceState(null, '', '#' + name);
  closeSide();
  if (name === 'secrets') loadSecrets();
  if (name === 'audit') loadAudit();
  if (name === 'mapping') { loadMapping(); loadProjectsCard(); }
  if (name === 'health') { loadHealth(); loadTwoFA(); loadVault(); loadBackup(); }
  if (name === 'connect') loadConnect();
  if (name === 'graph') setTimeout(fgResize, 0);
  if (name === 'ask') loadAsk();
  // Handy: „Mehr"-Knopf hervorheben, wenn ein darin liegender Tab aktiv ist
  const more = $('morebtn');
  if (more) more.classList.toggle('on', name === 'health' || name === 'audit' || name === 'connect');
}
function openMore() { $('moredlg').showModal(); }

/* ================= Ergonomie: Haptik + Wisch-Gesten ================= */
function haptic(ms = 8) { try { navigator.vibrate && navigator.vibrate(ms); } catch {} }
/* Horizontaler Wisch wechselt zwischen den Kern-Tabs — außer auf dem Graph
   (dort ist die Fläche fürs Verschieben reserviert) und über dem Detail-Sheet. */
const SWIPE_TABS = ['graph', 'ask', 'secrets', 'mapping', 'connect'];
(() => {
  const main = document.querySelector('main');
  if (!main) return;
  let sx = null, sy = null, onCanvas = false;
  main.addEventListener('touchstart', e => {
    if (e.touches.length !== 1) { sx = null; return; }
    const t = e.target;
    onCanvas = !!(t.closest && (t.closest('#cv') || t.closest('#side') || t.closest('#legend') || t.closest('#searchdrop')));
    sx = e.touches[0].clientX; sy = e.touches[0].clientY;
  }, { passive: true });
  main.addEventListener('touchend', e => {
    if (sx === null || onCanvas) { sx = null; return; }
    const dx = e.changedTouches[0].clientX - sx, dy = e.changedTouches[0].clientY - sy;
    sx = null;
    if (Math.abs(dx) < 60 || Math.abs(dx) < Math.abs(dy) * 2) return;   // nur klar horizontale Wische
    const cur = document.querySelector('.tab.on')?.id?.replace('tab-', '');
    const i = SWIPE_TABS.indexOf(cur);
    if (i < 0) return;
    const next = SWIPE_TABS[i + (dx < 0 ? 1 : -1)];
    if (next) { haptic(); tab(next); }
  }, { passive: true });
})();

/* ================= Einführung / Tour ================= */
const TOUR = [
  {icon: 'i-graph', tab: null,
   title: 'Willkommen in deinem Knowledge Hub', titleEn: 'Welcome to your Knowledge Hub',
   text: 'Ein privater Ort für dein Wissen und deine Geheimnisse — nur für dich, verschlüsselt auf deinem Server. Diese kurze Tour zeigt dir, was die einzelnen Bereiche tun.',
   textEn: 'A private home for your knowledge and your secrets — just for you, encrypted on your own server. This short tour shows you what each area does.'},
  {icon: 'i-graph', tab: 'graph',
   title: 'Graphen — dein Code als Landkarte', titleEn: 'Graphs — your code as a map',
   text: 'Jedes Projekt wird zu einer Karte.', textEn: 'Every project becomes a map.',
   gl: 'Ein <b>Knoten</b> (Punkt) ist ein Stück deines Codes — eine Funktion, Datei oder ein Konzept. <b>Linien</b> zeigen, was zusammenhängt. Gleiche <b>Farben</b> markieren einen zusammengehörigen <b>Bereich</b> (Community). Klick einen Knoten für Details, Nachbarn und Pfade.',
   glEn: 'A <b>node</b> (dot) is a piece of your code — a function, file or concept. <b>Lines</b> show what connects. Matching <b>colours</b> mark a related <b>area</b> (community). Click a node for details, neighbours and paths.'},
  {icon: 'i-spark', tab: 'ask',
   title: 'Fragen — in normaler Sprache', titleEn: 'Ask — in plain language',
   text: 'Frag einfach, was du über ein Projekt wissen willst — „Wo wird die Anmeldung geprüft?". Die Antwort nennt dir die <b>konkrete Datei und Zeile</b>, kein Vorwissen nötig.',
   textEn: 'Just ask what you want to know about a project — “Where is login checked?”. The answer names the <b>exact file and line</b>, no prior knowledge needed.'},
  {icon: 'i-key', tab: 'secrets',
   title: 'Secrets — der verschlüsselte Tresor', titleEn: 'Secrets — the encrypted vault',
   text: 'Hier liegen deine API-Keys, Tokens und Passwörter — mit AES-256 verschlüsselt. Deine KI-Clients holen sie sich von hier, ohne dass du sie je in einen Chat tippst.',
   textEn: 'This is where your API keys, tokens and passwords live — encrypted with AES-256. Your AI clients fetch them from here without you ever typing them into a chat.'},
  {icon: 'i-moon', tab: 'mapping',
   title: 'Mapping — immer aktuell', titleEn: 'Mapping — always current',
   text: 'Jede Nacht liest der Hub deine Projekte neu ein und baut die Graphen frisch — automatisch, während du schläfst. Du bestimmst Uhrzeit, KI-Anbieter und Projekte.',
   textEn: 'Every night the hub re-reads your projects and rebuilds the graphs fresh — automatically, while you sleep. You set the time, AI provider and projects.'},
  {icon: 'i-link', tab: 'connect',
   title: 'Verbinden — Claude & Co. anbinden', titleEn: 'Connect — link up Claude & co.',
   text: 'Verbinde deinen Hub mit claude.ai, Claude Code oder Claude Desktop — mit fertigen Anleitungen zum Kopieren, QR-Code und einem eigenen Token pro Gerät. Fertig los!',
   textEn: 'Connect your hub with claude.ai, Claude Code or Claude Desktop — with ready-to-copy instructions, a QR code and a device token of your own. Off you go!'},
];
let tourIdx = 0;
function startTour() { tourIdx = 0; renderTour(); if (!$('tourdlg').open) $('tourdlg').showModal(); }
function renderTour() {
  const s = TOUR[tourIdx], en = LANG === 'en';
  if (s.tab) tab(s.tab);   // hinter dem Dialog auf den passenden Bereich wechseln
  $('tourbody').innerHTML =
    `<div class="tourico"><svg class="ic" viewBox="0 0 24 24"><use href="#${s.icon}"/></svg></div>` +
    `<h3></h3><p></p>` + (s.gl ? `<div class="gl"></div>` : '');
  $('tourbody').querySelector('h3').textContent = en ? s.titleEn : s.title;
  $('tourbody').querySelector('p').innerHTML = en ? s.textEn : s.text;
  if (s.gl) $('tourbody').querySelector('.gl').innerHTML = en ? s.glEn : s.gl;
  $('tourdots').innerHTML = TOUR.map((_, i) => `<span class="dot ${i === tourIdx ? 'on' : ''}"></span>`).join('');
  $('tourprev').style.visibility = tourIdx === 0 ? 'hidden' : 'visible';
  $('tourskip').textContent = en ? 'Skip' : 'Überspringen';
  $('tournext').textContent = tourIdx === TOUR.length - 1 ? (en ? 'Let’s go' : 'Los geht’s') : (en ? 'Next' : 'Weiter');
}
function tourStep(d) {
  tourIdx += d;
  if (tourIdx >= TOUR.length) { endTour(); return; }
  if (tourIdx < 0) tourIdx = 0;
  renderTour();
}
function endTour() { $('tourdlg').close(); try { localStorage.setItem('kmcp_toured', '1'); } catch {} }

/* ================= Fragen (Query-Konsole) ================= */
let askProjectsLoaded = false;
async function loadAsk() {
  if (!askProjectsLoaded) {
    try {
      const list = await holeJson('/ui/api/projects');
      $('askproj').innerHTML = list.map(p =>
        `<option value="${p.project}">${p.project}</option>`).join('');
      askProjectsLoaded = true;
    } catch {}
  }
  setTimeout(() => $('askinput')?.focus(), 100);
}
function askBubble(role, html) {
  const wrap = document.createElement('div');
  wrap.style.cssText = 'margin:var(--sp-3) 0';
  if (role === 'user') {
    wrap.innerHTML = `<div style="background:var(--acc);color:#052e16;padding:10px 14px;border-radius:14px 14px 4px 14px;
      max-width:85%;margin-left:auto;width:fit-content;font-size:.9rem;line-height:1.5;overflow-wrap:anywhere"></div>`;
    wrap.firstChild.textContent = html;
  } else {
    wrap.innerHTML = `<div style="background:var(--surface);border:1px solid var(--line);padding:12px 14px;
      border-radius:14px 14px 14px 4px;max-width:92%;font-size:.9rem;line-height:1.65">${html}</div>`;
  }
  return wrap;
}
async function sendAsk(e) {
  e.preventDefault();
  const q = $('askinput').value.trim();
  const proj = $('askproj').value;
  if (q.length < 3 || !proj) return;
  $('askempty')?.remove();
  const thread = $('askthread');
  thread.appendChild(askBubble('user', q));
  $('askinput').value = '';
  $('asksend').disabled = true;

  /* Der Nutzer soll SEHEN, dass jetzt die KI arbeitet — nicht raten, ob etwas hängt. */
  const loading = askBubble('ai',
    `<div style="display:flex;align-items:center;gap:10px">
       <div class="brandloader" style="transform:scale(.7);transform-origin:left"><svg viewBox="0 0 24 24" style="width:34px;height:34px">
         <path class="draw" pathLength="360" stroke="url(#g-a)" d="m8.59 13.51 6.83 3.98M15.41 6.51l-6.82 3.98"/>
         <circle class="orbit" pathLength="360" stroke="url(#g-b)" cx="12" cy="12" r="10.5"/>
         <circle class="draw" pathLength="360" stroke="url(#g-a)" cx="18" cy="5" r="2.6"/>
         <circle class="draw" pathLength="360" stroke="url(#g-a)" cx="6" cy="12" r="2.6"/>
         <circle class="draw" pathLength="360" stroke="url(#g-a)" cx="18" cy="19" r="2.6"/></svg></div>
       <div style="min-width:0">
         <div style="font-size:.86rem">${escapeHtml(t('KI antwortet…'))}</div>
         <div style="color:var(--mut2);font-size:.74rem">${escapeHtml(t('Durchsucht den Graphen und formuliert die Antwort — bis zu zwei Minuten.'))}</div>
       </div>
     </div>`);
  thread.appendChild(loading);
  $('askscroll').scrollTop = $('askscroll').scrollHeight;

  try {
    const r = await api('/ui/api/ask/' + encodeURIComponent(proj), {method: 'POST',
      headers: {'Content-Type': 'application/json'}, body: JSON.stringify({question: q})});
    const j = await r.json();
    loading.remove();
    if (j.error) { thread.appendChild(askBubble('ai', escapeHtml(j.error))); }
    else {
      const answer = document.createElement('div');
      answer.style.cssText = 'white-space:pre-wrap;overflow-wrap:anywhere';
      answer.textContent = formatAnswer(j.answer || '');
      const box = askBubble('ai', '');
      box.firstChild.appendChild(answer);
      // Belege als klickbare Chips
      if (j.sources && j.sources.length) {
        const src = document.createElement('div');
        src.style.cssText = 'margin-top:12px;display:flex;flex-wrap:wrap;gap:6px';
        for (const s of j.sources.slice(0, 12)) {
          const chip = document.createElement('button');
          chip.className = 'chip';
          chip.style.cssText = 'cursor:pointer;border:0;font-size:.74rem';
          chip.innerHTML = `<svg class="ic" style="width:12px;height:12px;color:var(--blue)" viewBox="0 0 24 24"><use href="#i-file2"/></svg>`;
          chip.append(s.file + locLabel(s.loc));
          chip.title = t2('Im Graph zeigen: {label}', {label: s.label});
          chip.onclick = () => showNodeFromAsk(proj, s.label);
          src.appendChild(chip);
        }
        box.firstChild.appendChild(src);
      }
      if (j.source === 'llm' || j.source === 'gespeichert') {
        /* Klar kennzeichnen, dass hier die KI geantwortet hat — mit Anbieter und Modell,
           im selben Chip-Stil wie im Erklär-Panel. */
        const foot = document.createElement('div');
        foot.style.cssText = 'margin-top:10px;display:flex;align-items:center;gap:6px;flex-wrap:wrap';
        foot.innerHTML = `<span class="chip"><svg class="ic" style="width:12px;height:12px;color:var(--acc)" viewBox="0 0 24 24"><use href="#i-spark"/></svg>${escapeHtml(t('KI-Antwort'))} · ${escapeHtml(j.backend || '')} · ${escapeHtml(j.model || '')}</span>`;
        if (j.source === 'gespeichert') {
          /* Der Nutzer soll wissen, dass er hier eine bereits bezahlte Antwort liest —
             und nicht rätseln, warum sie so schnell kam. */
          const chip = document.createElement('span');
          chip.className = 'chip';
          chip.textContent = t2('gespeichert · {wann}', {wann: relTime(j.gespeichert)});
          foot.appendChild(chip);
        }
        box.firstChild.appendChild(foot);
      }
      thread.appendChild(box);
    }
    $('askscroll').scrollTop = $('askscroll').scrollHeight;
  } catch { loading.remove(); thread.appendChild(askBubble('ai', escapeHtml(t('Fehler bei der Anfrage.')))); }
  finally { $('asksend').disabled = false; $('askinput').focus(); }
}
function escapeHtml(s) { const d = document.createElement('div'); d.textContent = s; return d.innerHTML; }
/* Zeilennummer nur zeigen, wenn es wirklich eine ist (Markdown-Knoten haben keine → "None"/"L1") */
function locLabel(loc) {
  const m = /^L?(\d+)$/.exec(String(loc || ''));
  return m && +m[1] > 1 ? ':' + m[1] : '';
}
/* Nummerierte Punkte auf eigene Zeilen setzen, falls die KI sie zusammenzieht (1) … 2) … 3) …) */
function formatAnswer(text) {
  return String(text)
    .replace(/([.!?)»"“”])\s*(?=[2-9]\)\s)/g, '$1\n\n')
    .replace(/\n{3,}/g, '\n\n')
    .trim();
}
/* Beleg anklicken -> in den Graph springen und den Knoten wählen */
async function showNodeFromAsk(proj, label) {
  tab('graph');
  if ($('proj').value !== proj) { $('proj').value = proj; await loadGraph(); }
  setTimeout(() => {
    const n = FG?.graphData().nodes.find(x => x.label === label);
    if (n) selectNode(n);
    else toast(t('Knoten im aktuellen Ausschnitt nicht gefunden'));
  }, 800);
}

/* ================= mapping ================= */
let mapPoll = null, BACKENDS = [];
const CUSTOM = '__custom__';

function backendById(id) { return BACKENDS.find(b => b.id === id) || BACKENDS[0]; }

/* Modell-Liste + Key-Karte an das gewählte Backend anpassen */
function renderBackend(backendId, selectedModel) {
  const b = backendById(backendId);
  if (!b) return;
  const sel = $('mapmodel');
  const known = b.models.some(m => m.id === selectedModel);
  sel.innerHTML = b.models.map(m =>
    `<option value="${m.id}" ${m.id === selectedModel ? 'selected' : ''}>${m.id}${m.hint ? ' — ' + m.hint : ''}</option>`).join('')
    + `<option value="${CUSTOM}" ${selectedModel && !known ? 'selected' : ''}>${t('Eigenes Modell eingeben…')}</option>`;
  const custom = $('mapmodelcustom');
  const useCustom = selectedModel && !known;
  custom.style.display = useCustom ? 'block' : 'none';
  custom.value = useCustom ? selectedModel : '';
  $('backendnote').textContent = b.local
    ? t('Lokales Modell — kostenlos, aber deutlich langsamer. Ollama muss auf dem Server laufen.')
    : (b.key_hint || '');
  // Key-Karte
  $('keycard').style.display = 'block';
  $('keytitle').textContent = b.local ? 'Ollama' : t2('{label}-Key', {label: b.label});
  $('keybackend').textContent = b.label;
  $('keyhint').textContent = b.key_hint ? b.key_hint + ' ' : '';
  $('keylink').href = b.key_url || '#';
  $('keylink').style.display = b.key_url ? 'inline' : 'none';
  $('keyokmsg').textContent = b.local
    ? t('Ollama läuft lokal — kein Key nötig')
    : t2('{label}-Key ist hinterlegt (Vault: {secret})', {label: b.label, secret: b.secret});
  $('keymissing').style.display = b.has_key ? 'none' : 'block';
  $('keyok').style.display = b.has_key ? 'flex' : 'none';
  return b;
}
function backendChanged() {
  const b = renderBackend($('mapbackend').value, null);
  if (b && b.models.length) $('mapmodel').value = b.models[0].id;  // Standard-Modell vorschlagen
  modelChanged();
}
function modelChanged() {
  const custom = $('mapmodel').value === CUSTOM;
  $('mapmodelcustom').style.display = custom ? 'block' : 'none';
  if (custom) $('mapmodelcustom').focus();
}
function chosenModel() {
  return $('mapmodel').value === CUSTOM ? $('mapmodelcustom').value.trim() : $('mapmodel').value;
}

async function loadMapping() {
  let s;
  try { s = await holeJson('/ui/api/mapping/status'); }
  catch { return; }
  BACKENDS = s.backends;
  $('maptoggle').checked = s.enabled;
  $('mapstate').textContent = s.enabled ? t('Automatik aktiv') : t('Automatik ausgeschaltet');
  $('mapnext').textContent = (s.enabled && s.next_run ? t2('Nächster Lauf: {when}', {when: s.next_run.replace(/ [A-Z]+$/, '')}) + ' · ' : '') + t2('{n} Projekte', {n: s.projects.length});
  $('maptime').value = s.time;
  $('mapbackend').innerHTML = BACKENDS.map(b =>
    `<option value="${b.id}" ${b.id === s.backend ? 'selected' : ''}>${b.label}${b.has_key ? '' : ' ' + t('— kein Key')}</option>`).join('');
  renderBackend(s.backend, s.model);
  $('maprunning').style.display = s.running ? 'flex' : 'none';
  $('runbtn').disabled = s.running || !s.has_key;
  $('runbtn').title = s.has_key ? '' : t('Zuerst einen API-Key hinterlegen');
  const c = s.costs, l = c.last;
  const tok = n => n >= 1000 ? (n / 1000).toFixed(1) + 'k' : String(n);
  $('mapcosts').innerHTML =
    `<div class="stat"><div class="v acc">$${c.total_cost.toFixed(2)}</div>
       <div class="k">${t2('Summe aller {n} Läufe · {tok} Tokens', {n: c.runs, tok: tok(c.total_in + c.total_out)})}</div></div>` +
    (l ? `<div class="stat"><div class="v">$${l.cost.toFixed(4)}</div>
       <div class="k">${t2('Letzter Lauf ({date}) · {tok} Tokens', {date: l.date, tok: tok(l.tokens_in + l.tokens_out)})}</div></div>
       <div class="stat"><div class="v">${l.projects}${l.failed ? ` <span style="color:var(--red);font-size:.9rem">${t2('({n} Fehler)', {n: l.failed})}</span>` : ''}</div>
       <div class="k">${t('Projekte im letzten Lauf')}</div></div>` : '');
  try {
    const log = await holeJson('/ui/api/mapping/log');
    $('maplog').textContent = log.lines.length ? log.lines.join('\n') : t('(noch kein Lauf protokolliert)');
    $('maplog').scrollTop = $('maplog').scrollHeight;
  } catch {}
  loadHistory();
  clearInterval(mapPoll);
  if (s.running) mapPoll = setInterval(() => {
    if ($('tab-mapping').classList.contains('on')) loadMapping(); else clearInterval(mapPoll);
  }, 6000);
}
/* --- Verlauf: Kosten-Sparkline + Lauf-Tabelle --- */
function fmtDur(s) { if (s < 60) return s + ' s'; const m = Math.floor(s / 60); return m + ' min ' + (s % 60) + ' s'; }
function sparkline(values) {
  const w = 100, h = 30, max = Math.max(...values, 0.00001);
  const pts = values.map((v, i) => [values.length < 2 ? 0 : (i / (values.length - 1)) * w, h - 2 - (v / max) * (h - 6)]);
  const line = pts.map(p => p[0].toFixed(1) + ',' + p[1].toFixed(1)).join(' ');
  const area = '0,' + h + ' ' + line + ' ' + w + ',' + h;
  return `<svg viewBox="0 0 ${w} ${h}" preserveAspectRatio="none" style="width:100%;height:44px;display:block">
    <defs><linearGradient id="sparkg" x1="0" y1="0" x2="0" y2="1">
      <stop offset="0" stop-color="var(--acc)" stop-opacity=".32"/><stop offset="1" stop-color="var(--acc)" stop-opacity="0"/>
    </linearGradient></defs>
    <polygon points="${area}" fill="url(#sparkg)"/>
    <polyline points="${line}" fill="none" stroke="var(--acc)" stroke-width="1.5" vector-effect="non-scaling-stroke" stroke-linejoin="round" stroke-linecap="round"/>
  </svg>`;
}
async function loadHistory() {
  let h;
  try { h = await holeJson('/ui/api/mapping/history'); } catch { return; }
  const runs = h.runs || [];
  const spark = $('sparkwrap'), table = $('histtable');
  if (!runs.length) {
    spark.innerHTML = '';
    table.innerHTML = `<div class="empty" style="padding:var(--sp-6)">${t('Noch kein Lauf protokolliert — starte oben „Jetzt ausführen“.')}</div>`;
    return;
  }
  const chron = [...runs].reverse();
  spark.innerHTML = chron.length > 1
    ? `<div style="color:var(--mut2);font-size:var(--fs-xs);margin-bottom:5px">${t2('Geschätzte Kosten je Lauf · älteste links ({n} Läufe)', {n: chron.length})}</div>` + sparkline(chron.map(r => r.cost))
    : '';
  const tok = n => n >= 1000 ? (n / 1000).toFixed(1) + 'k' : String(n);
  const deltaTxt = d => d > 0 ? '+' + d : (d < 0 ? String(d) : '±0');
  const deltaCls = d => d > 0 ? 'up' : (d < 0 ? 'down' : 'zero');
  table.innerHTML = '';
  for (const r of runs) {
    const row = document.createElement('div'); row.className = 'histrow';
    const when = r.start.replace('T', ' '), date = when.slice(0, 10), time = when.slice(11, 16);
    const dur = r.duration_s == null ? '' :
      `<span class="chip"><svg class="ic" style="width:12px;height:12px" viewBox="0 0 24 24"><use href="#i-clock"/></svg>${fmtDur(r.duration_s)}</span>`;
    /* Ein gescheitertes Projekt und eine gescheiterte Sicherung sind zwei verschiedene
       Dinge mit zwei verschiedenen Lösungen — sie bekommen darum eigene Chips. Quittierte
       Läufe zeigen keine Warnfarbe mehr; der Eintrag selbst bleibt aber ehrlich stehen. */
    const still = r.dismissed;
    const mid = `<span class="chip">${escapeHtml(r.model)}</span>${dur}<span class="chip">${t2('{n} Projekte', {n: r.project_count})}</span>` +
      (r.failed ? `<span class="chip" style="color:${still ? 'var(--mut2)' : 'var(--red)'}">${t2('{n} Fehler', {n: r.failed})}</span>` : '') +
      (r.backup_failed ? `<span class="chip" style="color:${still ? 'var(--mut2)' : 'var(--amber)'}">${t('Sicherung fehlgeschlagen')}</span>` : '') +
      (still ? `<span class="chip" style="color:var(--mut2)">${t('erledigt')}</span>` : '') +
      `<span class="delta ${deltaCls(r.node_delta)}">${deltaTxt(r.node_delta)} ${t('Knoten')}</span>`;
    const sum = document.createElement('button'); sum.className = 'histsum';
    sum.setAttribute('aria-label', t2('Lauf vom {date} {time} Uhr — Details', {date, time}));
    sum.innerHTML =
      `<span class="when"><span class="d">${date}</span><div class="t">${t2('{time} Uhr', {time})}</div></span>` +
      `<span class="mid">${mid}</span>` +
      `<span class="cost"><div class="c">$${r.cost.toFixed(4)}</div><div class="n">${t2('{tok} Tok · {n} Kn.', {tok: tok(r.tokens_in + r.tokens_out), n: r.nodes_total})}</div></span>` +
      `<svg class="ic caret" style="width:18px;height:18px" viewBox="0 0 24 24"><use href="#i-back"/></svg>`;
    sum.onclick = () => row.classList.toggle('open');
    const det = document.createElement('div'); det.className = 'histdetail';
    const prs = r.projects.filter(p => p.nodes != null).map(p => {
      const d = p.delta == null ? '' : `<span class="delta ${deltaCls(p.delta)}">${deltaTxt(p.delta)}</span>`;
      return `<div class="pr"><span class="pn">${escapeHtml(p.name)}</span><span class="pv">${t2('{n} Knoten', {n: p.nodes})}</span>${d}</div>`;
    }).join('');
    det.innerHTML = prs || `<div class="pr" style="color:var(--mut2)">${t('Keine Projektdaten für diesen Lauf.')}</div>`;

    /* Jeder Fehler bekommt gesagt, WAS kaputt war und WIE man es behebt — ein
       bloßer Zähler („1 Fehler") lässt einen ratlos zurück. */
    const failures = r.failures || [];
    if (failures.length || r.backup_failed) {
      const box = document.createElement('div');
      box.className = 'histfails';
      for (const f of failures) {
        const line = document.createElement('div');
        line.className = 'failline';
        line.innerHTML = `<svg class="ic" viewBox="0 0 24 24"><use href="#i-alert"/></svg>
          <span>${f.kind === 'sync'
            ? t2('„{p}“ wurde gemappt, ließ sich aber nicht ins Wissens-Repo übertragen.', {p: escapeHtml(f.project)})
            : t2('„{p}“ konnte nicht gemappt werden.', {p: escapeHtml(f.project)})}</span>`;
        const btn = document.createElement('button');
        btn.className = 'btn ghost sm';
        btn.textContent = t('Prüfen & reparieren');
        btn.onclick = () => { tab('mapping'); toast(t2('Öffne die Projektliste — dort „{p}“ reparieren.', {p: f.project})); loadProjectsCard(); };
        line.appendChild(btn);
        box.appendChild(line);
      }
      if (r.backup_failed) {
        const line = document.createElement('div');
        line.className = 'failline';
        line.innerHTML = `<svg class="ic" viewBox="0 0 24 24"><use href="#i-alert"/></svg>
          <span>${t('Die verschlüsselte Sicherung lief nicht durch. Die Graphen sind davon nicht betroffen — aber der Vault liegt dann nur auf dieser Maschine.')}</span>`;
        const btn = document.createElement('button');
        btn.className = 'btn ghost sm';
        btn.textContent = t('Zur Sicherung');
        btn.onclick = () => { tab('health'); setTimeout(() => $('backupcard')?.scrollIntoView({behavior: 'smooth', block: 'center'}), 300); };
        line.appendChild(btn);
        box.appendChild(line);
      }
      /* Behoben, aber der Eintrag bleibt rot? Dann kann man ihn abhaken. Der Lauf
         verschwindet nicht — er hört nur auf zu mahnen. */
      const done = document.createElement('button');
      done.className = 'btn ghost sm';
      done.style.alignSelf = 'flex-start';
      done.textContent = still ? t('Wieder als offen markieren') : t('Erledigt — nicht mehr melden');
      done.onclick = async () => {
        await api('/ui/api/mapping/history/dismiss', {
          method: 'POST', headers: {'Content-Type': 'application/json'},
          body: JSON.stringify({start: r.start, dismissed: !still}),
        });
        toast(still ? t('Wieder als offen markiert') : t('Als erledigt abgehakt'));
        loadHistory();
      };
      box.appendChild(done);
      det.appendChild(box);
    }
    row.appendChild(sum); row.appendChild(det);
    table.appendChild(row);
  }
}
/* --- Projekte verwalten --- */
async function loadProjectsCard() {
  const items = await holeJson('/ui/api/mapping/projects');
  const box = $('projlist');
  box.innerHTML = items.length ? '' :
    `<div class="empty"><svg class="ic" viewBox="0 0 24 24"><use href="#i-folder"/></svg><br>
      <span style="color:var(--txt);font-weight:600">${t('Noch keine Projekte')}</span><br>
      <span style="display:inline-block;margin-top:4px">${t('Füge über „Hinzufügen“ ein Code-Verzeichnis hinzu — es wird dann im Nacht-Lauf automatisch zu einem Wissensgraphen verarbeitet.')}</span></div>`;
  for (const p of items) {
    const row = document.createElement('div');
    row.className = 'srow';
    const broken = p.issues && p.issues.length;
    row.innerHTML = `<div class="top">
      <label class="switch" style="transform:scale(.82);margin:-4px">
        <input type="checkbox" ${p.enabled ? 'checked' : ''} aria-label="${t2('Projekt {name} im Nacht-Lauf', {name: p.name})}">
        <span class="slider"></span>
      </label>
      <div style="flex:1;min-width:0">
        <div style="display:flex;align-items:center;gap:8px;font-weight:600;font-size:.92rem;flex-wrap:wrap">
          <span class="pname"></span>
          ${broken ? `<span class="chip" style="color:var(--red)">${t('Problem')}</span>` : ''}
          ${p.nodes != null ? `<span class="chip">${t2('{n} Knoten', {n: p.nodes})}</span>` : `<span class="chip" style="color:var(--amber)">${t('noch nicht gemappt')}</span>`}
        </div>
        <div class="mono ppath" style="font-size:.72rem;color:var(--mut2);word-break:break-all"></div>
      </div>
      <span class="acts">
        <button data-a="ignore" aria-label="${t('Ausschluss-Regeln bearbeiten')}" title="${t('Ausschluss-Regeln')}${p.has_ignore ? ' ' + t('(aktiv)') : ''}">
          <svg class="ic" viewBox="0 0 24 24"><use href="#i-eyeoff"/></svg></button>
        <button data-a="del" class="del" aria-label="${t('Projekt entfernen')}"><svg class="ic" viewBox="0 0 24 24"><use href="#i-trash"/></svg></button>
      </span></div>
      ${broken ? `<div class="pissue" style="margin-top:10px;padding:10px 12px;border-radius:var(--r-sm);
           background:rgba(248,113,113,.08);border:1px solid rgba(248,113,113,.28)">
        <div class="pissuetext" style="color:var(--red);font-size:.8rem;line-height:1.55"></div>
        <div class="pissuefix" style="color:var(--mut);font-size:.76rem;line-height:1.55;margin-top:5px;overflow-wrap:anywhere"></div>
        ${p.repairable
          ? `<button class="btn repairbtn" style="margin-top:10px;min-height:38px;font-size:.82rem"><svg class="ic" viewBox="0 0 24 24"><use href="#i-wrench"/></svg>${t('Reparieren')}</button>`
          : `<div style="color:var(--mut2);font-size:.74rem;margin-top:8px">${t('Das lässt sich nur direkt auf dem Server beheben — Befehl oben.')}</div>`}
        <pre class="repairlog" style="display:none;margin:10px 0 0;font-size:.72rem;line-height:1.5;color:var(--mut);white-space:pre-wrap;overflow-wrap:anywhere"></pre>
      </div>` : ''}`;
    row.querySelector('.pname').textContent = p.name;
    row.querySelector('.ppath').textContent = p.path;
    if (broken) {
      row.querySelector('.pissuetext').textContent = p.issues.map(i => i.problem).join(' ');
      row.querySelector('.pissuefix').textContent = p.issues.map(i => i.fix).join(' ');
      const rb = row.querySelector('.repairbtn');
      if (rb) rb.onclick = () => repairProject(p, row);
    }
    row.querySelector('input[type=checkbox]').onchange = async (ev) => {
      /* Vorher wurde das Ergebnis gar nicht geprüft: Bei einem Fehler blieb das Häkchen
         umgelegt UND es kam eine Erfolgsmeldung — der Nutzer glaubte, es sei gespeichert. */
      const box = ev.currentTarget;
      box.disabled = true;
      try {
        const r = await api('/ui/api/mapping/projects', {method: 'PATCH', headers: {'Content-Type': 'application/json'},
          body: JSON.stringify({path: p.path, action: 'toggle'})});
        if (!r.ok) {
          box.checked = !box.checked;          // zurück auf den echten Zustand
          await zeigeFehler(r, t('Umschalten fehlgeschlagen'));
          return;
        }
        toast(p.enabled ? t2('{name} vom Nacht-Lauf ausgenommen', {name: p.name}) : t2('{name} wieder im Nacht-Lauf', {name: p.name}));
        loadProjectsCard(); loadMapping();
      } catch (e) {
        box.checked = !box.checked;
      } finally { box.disabled = false; }
    };
    row.querySelector('[data-a=ignore]').onclick = () => openIgnore(p);
    row.querySelector('[data-a=del]').onclick = async () => {
      if (!await askConfirm(t2('„{name}" komplett entfernen? Löscht auch den Graphen im Hub, lokale Graph-Daten und gespeicherte Antworten — der Projektordner selbst bleibt unberührt.', {name: p.name}))) return;
      const r = await api('/ui/api/mapping/projects', {method: 'PATCH', headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({path: p.path, action: 'remove'})});
      if (!r.ok) { await zeigeFehler(r, t('Entfernen fehlgeschlagen')); return; }
      toast(t2('Komplett entfernt: {name}', {name: p.name}));
      loadProjectsCard(); loadMapping();
    };
    box.appendChild(row);
  }
}
/* Projekt reparieren: behebt was geht und mappt danach neu — mit Live-Protokoll */
async function repairProject(p, row) {
  const btn = row.querySelector('.repairbtn');
  const log = row.querySelector('.repairlog');
  btn.disabled = true;
  btn.innerHTML = `<div class="spinner" style="--sz:16px"></div>${t('Repariere…')}`;
  log.style.display = 'block';
  log.textContent = t('Reparatur gestartet…');
  const r = await api('/ui/api/mapping/repair', {method: 'POST', headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({path: p.path})});
  if (!r.ok) { await zeigeFehler(r, t('Start fehlgeschlagen')); btn.disabled = false; return; }
  const poll = setInterval(async () => {
    const s = await holeJson('/ui/api/mapping/repair?path=' + encodeURIComponent(p.path));
    log.textContent = s.log || '';
    log.scrollTop = log.scrollHeight;
    if (s.status === 'done') {
      clearInterval(poll);
      toast(t2('{name} repariert', {name: p.name}));
      setTimeout(() => { loadProjectsCard(); loadMapping(); }, 800);
    } else if (s.status === 'failed') {
      clearInterval(poll);
      toast(t('Reparatur fehlgeschlagen — siehe Protokoll'), false);
      btn.disabled = false;
      btn.innerHTML = `<svg class="ic" viewBox="0 0 24 24"><use href="#i-wrench"/></svg>${t('Erneut versuchen')}`;
    }
  }, 2000);
}

let pickAt = null;
async function browseTo(path) {
  const d = await holeJson('/ui/api/browse?path=' + encodeURIComponent(path || ''));
  pickAt = d.path;
  $('pickpath').textContent = d.path;
  const box = $('pickdirs');
  box.innerHTML = '';
  const mk = (label, target, up) => {
    const b = document.createElement('button');
    b.className = 'btn ghost';
    b.style.cssText = 'justify-content:flex-start;font-size:.85rem;min-height:42px';
    b.innerHTML = up
      ? `<svg class="ic" style="width:16px;height:16px;transform:rotate(90deg)" viewBox="0 0 24 24"><use href="#i-back"/></svg>${t('Übergeordneter Ordner')}`
      : '<svg class="ic" style="width:16px;height:16px;color:var(--mut)" viewBox="0 0 24 24"><use href="#i-folder"/></svg>';
    if (!up) b.append(label);
    b.onclick = () => browseTo(target);
    box.appendChild(b);
  };
  if (d.parent) mk('', d.parent, true);
  else d.roots.forEach(r => { if (r !== d.path) mk(r, r, false); });
  d.dirs.forEach(name => mk(name, d.path.replace(/\/$/, '') + '/' + name, false));
  if (!d.dirs.length && !d.parent) box.innerHTML = `<span style="color:var(--mut)">${t('Keine Unterordner.')}</span>`;
}
function openPicker() { browseTo(''); $('pickerdlg').showModal(); }
async function pickCurrent() {
  $('pickok').disabled = true;
  try {
    const r = await api('/ui/api/mapping/projects', {method: 'POST', headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({path: pickAt})});
    if (r.ok) { toast(t('Projekt hinzugefügt — läuft ab jetzt im Nacht-Mapping mit')); $('pickerdlg').close(); }
    else await zeigeFehler(r, t('Fehler'));
  } finally { $('pickok').disabled = false; loadProjectsCard(); loadMapping(); }
}
let ignoreFor = null;
async function openIgnore(p) {
  ignoreFor = p.path;
  const d = await holeJson('/ui/api/mapping/ignore?path=' + encodeURIComponent(p.path));
  // Ohne eigene Regeln: empfohlene Standard-Ausschlüsse vorbefüllen — Speichern genügt.
  $('ignoretext').value = d.content || d.default || '';
  if (!d.content && d.default) toast(t('Empfohlene Ausschlüsse vorbefüllt — Speichern übernimmt sie'));
  $('ignoredlg').showModal();
}
async function saveIgnore() {
  $('ignoresave').disabled = true;
  try {
    const r = await api('/ui/api/mapping/ignore', {method: 'PUT', headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({path: ignoreFor, content: $('ignoretext').value})});
    if (r.ok) { toast(t('Ausschluss-Regeln gespeichert')); $('ignoredlg').close(); }
    else await zeigeFehler(r, t('Fehler beim Speichern'));
  } finally { $('ignoresave').disabled = false; loadProjectsCard(); }
}

async function saveApiKey(e) {
  e.preventDefault();
  const v = $('apikey').value.trim();
  const b = backendById($('mapbackend').value);
  if (!v || !b || !b.secret) return;
  $('keysave').disabled = true;
  try {
    const r = await api('/ui/api/secrets', {method: 'POST', headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({name: b.secret, value: v})});
    if (r.ok) { toast(t2('{label}-Key gespeichert — Mapping ist einsatzbereit', {label: b.label})); $('apikey').value = ''; }
    else await zeigeFehler(r, t('Fehler beim Speichern'));
  } finally { $('keysave').disabled = false; loadMapping(); }
}
async function toggleMapping(on) {
  haptic(10);
  const r = await api('/ui/api/mapping/toggle', {method: 'POST', headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({enabled: on})});
  if (r.ok) toast(on ? t('Nacht-Mapping eingeschaltet') : t('Nacht-Mapping ausgeschaltet'));
  else await zeigeFehler(r, t('Fehler beim Umschalten'));
  loadMapping();
}
async function saveMapping(e) {
  e.preventDefault();
  const model = chosenModel();
  if (!model) { toast(t('Bitte ein Modell wählen oder eingeben'), false); return; }
  $('mapsave').disabled = true;
  try {
    const r = await api('/ui/api/mapping/config', {method: 'POST', headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({time: $('maptime').value, backend: $('mapbackend').value, model})});
    if (r.ok) toast(t2('Gespeichert — täglich um {time} mit {model}', {time: $('maptime').value, model}));
    else await zeigeFehler(r, t('Fehler beim Speichern'));
  } finally { $('mapsave').disabled = false; loadMapping(); }
}
async function runMapping() {
  $('runbtn').disabled = true;
  const r = await api('/ui/api/mapping/run', {method: 'POST'});
  if (r.ok) toast(t('Mapping gestartet'));
  else await zeigeFehler(r, t('Start fehlgeschlagen'));
  setTimeout(loadMapping, 1500);
}

/* ================= graph ================= */
const PALETTE = ['#22c55e','#60a5fa','#fbbf24','#f87171','#c084fc','#2dd4bf','#f472b6','#a3e635',
                 '#fb923c','#38bdf8','#e879f9','#4ade80','#facc15','#818cf8','#fb7185','#34d399'];
const REDUCED = matchMedia('(prefers-reduced-motion: reduce)').matches;
var FG = null, selected = null, hoverNode = null, nbr = null;
let lastProject = null, limitTimer = null, firstLayout = true, searchQ = '';

function nodeColor(d) { return PALETTE[(d.community == null ? 0 : d.community) % PALETTE.length]; }
function isMatch(d) { return searchQ && d.label.toLowerCase().includes(searchQ); }
function isDimmed(d) {
  if (pathIds) return !pathIds.has(d.id);
  if (searchQ) return !isMatch(d);
  if (comFilter != null) return d.community !== comFilter;
  if (selected && nbr) return !nbr.has(d.id);
  return false;
}
function drawNode(d, ctx, scale) {
  if (!isFinite(d.x) || !isFinite(d.y) || !isFinite(d.r)) return; // erster Tick: noch keine Position
  const r = d.r, dim = isDimmed(d);
  if (d === selected) {
    const grad = ctx.createRadialGradient(d.x, d.y, 1, d.x, d.y, r + 18);
    grad.addColorStop(0, nodeColor(d) + '66');
    grad.addColorStop(1, nodeColor(d) + '00');
    ctx.fillStyle = grad;
    ctx.beginPath(); ctx.arc(d.x, d.y, r + 18, 0, 7); ctx.fill();
  }
  ctx.beginPath();
  ctx.arc(d.x, d.y, r, 0, 7);
  ctx.globalAlpha = dim ? 0.14 : 1;
  const g = ctx.createRadialGradient(d.x - r * .35, d.y - r * .35, r * .1, d.x, d.y, r);
  g.addColorStop(0, '#ffffff40'); g.addColorStop(.25, nodeColor(d)); g.addColorStop(1, nodeColor(d));
  ctx.fillStyle = g;
  ctx.fill();
  if (d === selected || d === hoverNode || isMatch(d)) {
    ctx.strokeStyle = CANVAS_INK; ctx.lineWidth = 1.5 / scale; ctx.stroke();
  }
  const showLabel = (scale > 1.3 && d.degree > 8) || d === selected || d === hoverNode || isMatch(d)
    || (selected && nbr && nbr.has(d.id) && scale > 1.1);
  if (showLabel && !dim) {
    const fs = Math.max(11 / scale, 2.4);
    ctx.font = `${fs}px Inter, system-ui`;
    ctx.lineWidth = fs * .28; ctx.lineJoin = 'round';
    ctx.strokeStyle = CANVAS_HALO;
    const text = d.label.slice(0, 32);
    ctx.strokeText(text, d.x + r + 2.5, d.y + fs * .35);
    ctx.fillStyle = CANVAS_INK;
    ctx.fillText(text, d.x + r + 2.5, d.y + fs * .35);
  }
  ctx.globalAlpha = 1;
}
function linkIds(l) { return [l.source.id ?? l.source, l.target.id ?? l.target]; }
function initFG() {
  FG = ForceGraph()($('cv'))
    .backgroundColor('rgba(0,0,0,0)')
    .nodeId('id')
    .nodeLabel(null)
    .autoPauseRedraw(false)
    .warmupTicks(REDUCED ? 200 : 80)           // Layout vorrechnen: kaum sichtbares Einpendeln
    .cooldownTime(REDUCED ? 0 : 3000)
    .d3AlphaDecay(0.04)
    .d3VelocityDecay(0.4)
    .nodeCanvasObject(drawNode)
    .nodePointerAreaPaint((d, color, ctx) => {  // große Trefferfläche für Finger
      if (!isFinite(d.x) || !isFinite(d.y) || !isFinite(d.r)) return;
      ctx.fillStyle = color;
      ctx.beginPath(); ctx.arc(d.x, d.y, d.r + 7, 0, 7); ctx.fill();
    })
    .linkColor(l => {
      const [s, t] = linkIds(l);
      if (pathIds) return (pathIds.has(s) && pathIds.has(t)) ? 'rgba(96,165,250,.9)' : 'rgba(100,130,180,.05)';
      if (selected && (s === selected.id || t === selected.id)) return 'rgba(34,197,94,.6)';
      if (selected || searchQ || comFilter != null) return 'rgba(100,130,180,.07)';
      return 'rgba(100,130,180,.18)';
    })
    .linkWidth(l => {
      const [s, t] = linkIds(l);
      if (pathIds && pathIds.has(s) && pathIds.has(t)) return 2.4;
      return selected && (s === selected.id || t === selected.id) ? 1.6 : 1;
    })
    .onNodeClick(d => selectNode(d))
    .onBackgroundClick(() => closeSide())
    .onNodeHover(d => { hoverNode = d; $('cv').style.cursor = d ? 'pointer' : 'grab'; })
    .onEngineStop(() => { if (firstLayout) { firstLayout = false; FG.zoomToFit(REDUCED ? 0 : 600, 70); } });
  FG.d3Force('charge').strength(-55).distanceMax(340);
  FG.d3Force('link').distance(45);
  fgResize();
}
function fgResize() {
  if (!FG) return;
  const box = $('canvasbox');
  FG.width(box.clientWidth).height(box.clientHeight);
}
window.addEventListener('resize', fgResize);

async function loadProjects() {
  const list = await holeJson('/ui/api/projects');
  const sel = $('proj');
  sel.innerHTML = list.map(p =>
    `<option value="${p.project}">${p.project} · ${t2('{n} Knoten', {n: p.nodes})}</option>`).join('');
  /* Ohne Projekt blieb die Graph-Fläche vorher einfach leer — ein frisch installierter
     Hub sah aus, als sei er kaputt. Jetzt steht dort, was zu tun ist. */
  const leer = $('graphempty');
  if (leer) leer.style.display = list.length ? 'none' : '';
  $('graphbar').style.display = list.length ? '' : 'none';
  if (list.length) loadGraph();
}
let ADJ = new Map(), NODEMAP = new Map(), comFilter = null, pathSource = null, pathIds = null;
function limitChanged() {
  clearTimeout(limitTimer);
  limitTimer = setTimeout(loadGraph, 450);
}
async function loadGraph() {
  const proj = $('proj').value;
  if (!proj) return;
  $('graphload').classList.add('on');
  try {
    const slider = $('limit');
    // Regler am Anschlag = ALLE Knoten (kein Deckel)
    const lim = +slider.value >= +slider.max ? 0 : slider.value;
    const g = await holeJson(`/ui/api/graph/${proj}?limit=${lim}`);
    // Regler-Maximum an die echte Projektgröße anpassen
    const atMax = +slider.value >= +slider.max;
    slider.max = Math.max(2000, Math.ceil(g.total_nodes / 50) * 50);
    if (atMax) { slider.value = slider.max; $('limlbl').textContent = t('Alle'); }
    if (!FG) initFG();
    const sameProject = proj === lastProject;
    if (sameProject) {
      // Positionen bekannter Knoten übernehmen → kein Springen beim Regler
      const old = new Map(FG.graphData().nodes.map(d => [d.id, d]));
      for (const d of g.nodes) {
        const p = old.get(d.id);
        if (p) { d.x = p.x; d.y = p.y; d.vx = 0; d.vy = 0; }
      }
    }
    for (const d of g.nodes) d.r = 3.5 + Math.min(13, Math.sqrt(d.degree));
    ADJ = new Map(g.nodes.map(d => [d.id, new Set([d.id])]));
    NODEMAP = new Map(g.nodes.map(d => [d.id, d]));
    for (const l of g.links) { ADJ.get(l.source)?.add(l.target); ADJ.get(l.target)?.add(l.source); }
    if (!sameProject) { comFilter = null; pathIds = null; $('pathbox').style.display = 'none'; }
    buildLegend(g.nodes);
    selected = null; nbr = null; closeSide();
    lastProject = proj;
    firstLayout = !sameProject;
    $('stats').textContent = t2('{a}/{b} Knoten · {c} Kanten', {a: g.nodes.length, b: g.total_nodes, c: g.links.length});
    FG.graphData({nodes: g.nodes, links: g.links});
    if (sameProject) FG.d3ReheatSimulation();
  } finally { $('graphload').classList.remove('on'); }
}
let searchResults = [], searchHi = -1;
function searchChanged(v) { searchQ = v.trim().toLowerCase(); updateSearchDrop(); }
/* Treffer sammeln: exakter Präfix zuerst, dann nach Verbindungsgrad */
function searchMatches() {
  if (!searchQ || !NODEMAP.size) return [];
  const q = searchQ;
  return [...NODEMAP.values()]
    .filter(n => n.label.toLowerCase().includes(q))
    .sort((a, b) => {
      const ap = a.label.toLowerCase().startsWith(q), bp = b.label.toLowerCase().startsWith(q);
      if (ap !== bp) return ap ? -1 : 1;
      return b.degree - a.degree;
    })
    .slice(0, 8);
}
function positionSearchDrop() {
  const r = $('search').getBoundingClientRect();
  const d = $('searchdrop');
  d.style.left = r.left + 'px';
  d.style.top = (r.bottom + 6) + 'px';
  d.style.width = Math.max(r.width, 240) + 'px';
}
function updateSearchDrop() {
  const d = $('searchdrop');
  if (!searchQ) { d.classList.remove('on'); $('search').setAttribute('aria-expanded', 'false'); return; }
  searchResults = searchMatches(); searchHi = -1;
  d.innerHTML = '';
  if (!searchResults.length) {
    d.innerHTML = `<div class="sdnone">${t('Kein Knoten gefunden')}</div>`;
  } else {
    searchResults.forEach((n, i) => {
      const b = document.createElement('button');
      b.className = 'sd'; b.setAttribute('role', 'option');
      const idx = n.label.toLowerCase().indexOf(searchQ);
      const before = n.label.slice(0, idx), hit = n.label.slice(idx, idx + searchQ.length), after = n.label.slice(idx + searchQ.length);
      b.innerHTML = `<span class="dot" style="background:${nodeColor(n)}"></span><span class="l"></span><span class="g"></span>`;
      const l = b.querySelector('.l');
      l.append(before); const bold = document.createElement('b'); bold.textContent = hit; l.append(bold); l.append(after);
      b.querySelector('.g').textContent = n.degree;
      b.onmousedown = e => { e.preventDefault(); jumpToNode(n); };
      d.appendChild(b);
    });
  }
  positionSearchDrop();
  d.classList.add('on'); $('search').setAttribute('aria-expanded', 'true');
}
function searchKey(e) {
  if (!searchResults.length && e.key !== 'Escape') { if (e.key === 'Enter') e.preventDefault(); return; }
  if (e.key === 'ArrowDown') { e.preventDefault(); searchHi = Math.min(searchHi + 1, searchResults.length - 1); markHi(); }
  else if (e.key === 'ArrowUp') { e.preventDefault(); searchHi = Math.max(searchHi - 1, 0); markHi(); }
  else if (e.key === 'Enter') { e.preventDefault(); jumpToNode(searchResults[searchHi >= 0 ? searchHi : 0]); }
  else if (e.key === 'Escape') { $('searchdrop').classList.remove('on'); $('search').blur(); }
}
function markHi() {
  const rows = $('searchdrop').querySelectorAll('.sd');
  rows.forEach((r, i) => r.classList.toggle('hi', i === searchHi));
  if (rows[searchHi]) rows[searchHi].scrollIntoView({ block: 'nearest' });
}
function hideSearchDropSoon() { setTimeout(() => $('searchdrop').classList.remove('on'), 150); }
function jumpToNode(n) {
  if (!n) return;
  $('searchdrop').classList.remove('on');
  $('search').value = n.label; searchQ = '';   // Filter lösen, Fokus auf den einen Knoten
  selectNode(n);
  if (FG && isFinite(n.x)) { FG.centerAt(n.x, n.y, 600); FG.zoom(Math.max(FG.zoom(), 2.6), 600); }
}
window.addEventListener('scroll', () => $('searchdrop').classList.contains('on') && positionSearchDrop(), true);
/* Community-Legende: farbige Bereiche mit Knotenzahl, Klick isoliert einen Bereich */
/* Namen der Bereiche, die die KI vergeben hat (Nummer -> Name). Fehlt einer,
   fällt die Legende auf „Bereich N" zurück — nie auf einen leeren Eintrag. */
let COMNAMES = new Map();
function comLabel(com) {
  const n = COMNAMES.get(com);
  return n ? n : t2('Bereich {n}', {n: com});
}
function buildLegend(nodes) {
  const counts = new Map();
  COMNAMES = new Map();
  for (const n of nodes) {
    if (n.community == null) continue;
    counts.set(n.community, (counts.get(n.community) || 0) + 1);
    if (n.community_name && !COMNAMES.has(n.community)) COMNAMES.set(n.community, n.community_name);
  }
  const leg = $('legend'), body = $('legendbody');
  if (counts.size < 2) { leg.classList.add('hidden'); comFilter = null; return; }
  leg.classList.remove('hidden');
  body.innerHTML = '';
  for (const [com, cnt] of [...counts.entries()].sort((a, b) => b[1] - a[1])) {
    const b = document.createElement('button');
    b.className = 'legrow' + (comFilter === com ? ' active' : '');
    b.dataset.com = com;
    b.innerHTML = `<span class="dot" style="background:${PALETTE[com % PALETTE.length]}"></span><span class="lc">${escapeHtml(comLabel(com))}</span><span class="ln"></span>`;
    b.querySelector('.ln').textContent = cnt;
    b.onclick = () => setComFilter(com);
    body.appendChild(b);
  }
}
function setComFilter(com) {
  comFilter = (comFilter === com) ? null : com;
  document.querySelectorAll('.legrow').forEach(r => r.classList.toggle('active', +r.dataset.com === comFilter));
  if (comFilter != null) { pathIds = null; $('pathbox').style.display = 'none'; closeSide(); }
}
function fitView() { if (FG) FG.zoomToFit(REDUCED ? 0 : 500, 70); }
function zoomBy(f) { if (FG) FG.zoom(FG.zoom() * f, REDUCED ? 0 : 250); }

function selectNode(d) {
  // Im Pfad-Modus wird der angeklickte Knoten zum Ziel: kürzesten Weg suchen und zeigen.
  if (pathSource && pathSource !== d.id) { finishPath(d); return; }
  selected = d;
  nbr = ADJ.get(d.id) || new Set([d.id]);
  $('ntitle').textContent = d.label;
  const com = d.community == null ? '–' : d.community;
  $('nmeta').innerHTML =
    `<span class="chip"><span style="width:9px;height:9px;border-radius:50%;background:${nodeColor(d)}"></span>${escapeHtml(comLabel(com))}</span>` +
    `<span class="chip">${t2('{n} Verbindungen', {n: d.degree})}</span>`;
  $('nfile').textContent = d.file || '';
  // Show the node's own content on click. Long text wraps and scrolls (see the
  // #ncontent rule in app.css); with a source URL we append it as a link.
  const cbox = $('ncontent');
  if (cbox) {
    const txt = (d.rationale || '').trim();
    if (txt) {
      cbox.textContent = txt;
      if (d.source_url) {
        const a = document.createElement('a');
        a.href = d.source_url; a.target = '_blank'; a.rel = 'noopener noreferrer';
        a.className = 'nsrc'; a.textContent = d.source_url;
        cbox.appendChild(document.createElement('br'));
        cbox.appendChild(a);
      }
      cbox.style.display = 'block';
    } else {
      cbox.textContent = '';
      cbox.style.display = 'none';
    }
  }
  $('explainout').style.display = 'none';
  $('explainwait').style.display = 'none';
  renderNeighbors(d);
  $('side').classList.add('on');
  setTimeout(fgResize, 0);
  if (!REDUCED && isFinite(d.x)) FG.centerAt(d.x, d.y, 500);
}
/* Nachbarn als klickbare Liste — nach Verbindungsgrad sortiert */
function renderNeighbors(d) {
  const ids = [...(ADJ.get(d.id) || [])].filter(id => id !== d.id);
  const neigh = ids.map(id => NODEMAP.get(id)).filter(Boolean).sort((a, b) => b.degree - a.degree);
  const wrap = $('nneighwrap'), box = $('nneigh');
  if (!neigh.length) { wrap.style.display = 'none'; return; }
  wrap.style.display = 'block';
  $('nneighcount').textContent = neigh.length;
  box.innerHTML = '';
  for (const n of neigh.slice(0, 60)) {
    const b = document.createElement('button');
    b.className = 'neighrow';
    b.innerHTML = `<span class="dot" style="background:${nodeColor(n)}"></span><span class="nl"></span><span class="nd tnum"></span>`;
    b.querySelector('.nl').textContent = n.label;
    b.querySelector('.nd').textContent = n.degree;
    b.title = n.label;
    b.onclick = () => selectNode(n);
    box.appendChild(b);
  }
}
function startPath() {
  if (!selected) return;
  pathSource = selected.id;
  toast(t('Zielknoten anklicken — der kürzeste Weg wird angezeigt'));
  $('hint').textContent = t('Pfad-Modus: klicke den Zielknoten (oder Esc zum Abbrechen)');
}
function finishPath(target) {
  const path = bfsPath(pathSource, target.id);
  const srcNode = NODEMAP.get(pathSource);
  pathSource = null;
  if (!path) { toast(t('Kein Weg zwischen den beiden Knoten gefunden'), false); return; }
  pathIds = new Set(path);
  selected = target; nbr = ADJ.get(target.id) || new Set([target.id]);
  // Panel auf den Zielknoten, mit Pfad-Auflistung
  $('ntitle').textContent = target.label;
  const com = target.community == null ? '–' : target.community;
  $('nmeta').innerHTML =
    `<span class="chip"><span style="width:9px;height:9px;border-radius:50%;background:${nodeColor(target)}"></span>${escapeHtml(comLabel(com))}</span>` +
    `<span class="chip">${t2('{n} Verbindungen', {n: target.degree})}</span>`;
  $('nfile').textContent = target.file || '';
  $('explainout').style.display = 'none'; $('explainwait').style.display = 'none';
  renderNeighbors(target);
  $('pathbox').style.display = 'block';
  $('pathout').innerHTML = '';
  const labels = path.map(id => NODEMAP.get(id)?.label || id);
  $('pathout').textContent = t2('{n} Knoten über {s} Schritte:', {n: labels.length, s: labels.length - 1}) + '  ' + labels.join('  →  ');
  $('side').classList.add('on');
  FG.d3ReheatSimulation && FG.d3ReheatSimulation();
  toast(t2('Weg gefunden: {n} Schritte', {n: path.length - 1}));
}
function clearPath() {
  pathIds = null;
  $('pathbox').style.display = 'none';
  $('hint').textContent = t('Ziehen zum Verschieben · Scrollen zum Zoomen · Klick auf Knoten für Details');
}
/* Breitensuche über die (client-seitige) Nachbarschaftsliste = kürzester Weg */
function bfsPath(src, dst) {
  if (src === dst) return [src];
  const queue = [[src]], seen = new Set([src]);
  while (queue.length) {
    const p = queue.shift(), last = p[p.length - 1];
    for (const nb of (ADJ.get(last) || [])) {
      if (nb === dst) return [...p, nb];
      if (!seen.has(nb)) { seen.add(nb); queue.push([...p, nb]); }
    }
  }
  return null;
}
function closeSide() {
  $('side').classList.remove('on');
  selected = null; nbr = null; pathSource = null;
  $('nneighwrap').style.display = 'none';
  setTimeout(fgResize, 0);
}
document.addEventListener('keydown', e => { if (e.key === 'Escape') { pathSource = null; clearPath(); } });
/* swipe-down dismiss for the bottom sheet */
(() => {
  const side = $('side');
  let startY = null;
  side.addEventListener('touchstart', e => { if (side.scrollTop <= 0) startY = e.touches[0].clientY; }, {passive: true});
  side.addEventListener('touchmove', e => {
    if (startY === null) return;
    const dy = e.touches[0].clientY - startY;
    if (dy > 70) { startY = null; closeSide(); }
  }, {passive: true});
  side.addEventListener('touchend', () => startY = null);
})();

async function doExplain(frisch) {
  if (!selected) return;
  const sel = selected;
  const out = $('explainout'), wait = $('explainwait');
  out.style.display = 'none';
  wait.style.display = 'flex';            // Marken-Loader statt Text-Platzhalter
  try {
    /* frisch=true umgeht den Speicher — für den Fall, dass die alte Erklärung nichts taugt.
       Ohne das Flag kommt eine bereits bezahlte Erklärung in Millisekunden zurück, statt
       dieselbe Frage ein zweites Mal zu bezahlen. */
    const q = frisch ? '&fresh=1' : '';
    const r = await api(`/ui/api/explain/${$('proj').value}?node=${encodeURIComponent(sel.label)}${q}`);
    const j = await r.json();
    out.innerHTML = '';
    if (j.error) { out.textContent = j.error; }
    else {
      const body = document.createElement('div');
      body.style.cssText = 'white-space:pre-wrap;line-height:1.65';
      body.textContent = j.text || t('Keine Antwort erhalten.');
      out.appendChild(body);
      if (j.note) {
        const n = document.createElement('div');
        n.style.cssText = 'margin-top:10px;color:var(--amber);font-size:.78rem;line-height:1.5';
        n.textContent = j.note;
        out.appendChild(n);
      }
      if (j.source === 'llm' || j.source === 'gespeichert') {
        const foot = document.createElement('div');
        foot.style.cssText = 'margin-top:12px;display:flex;align-items:center;gap:8px;flex-wrap:wrap';
        const gespeichert = j.source === 'gespeichert';
        foot.innerHTML = `<span class="chip"><svg class="ic" style="width:13px;height:13px;color:var(--acc)" viewBox="0 0 24 24"><use href="#i-spark"/></svg>${escapeHtml(t('KI-Antwort'))} · ${escapeHtml(j.backend || '')} · ${escapeHtml(j.model || '')}</span>`;
        if (gespeichert) {
          /* Ehrlich sagen, woher die Antwort kommt — und einen Weg anbieten, sie zu erneuern. */
          const chip = document.createElement('span');
          chip.className = 'chip';
          chip.textContent = t2('gespeichert · {wann}', {wann: relTime(j.gespeichert)});
          foot.appendChild(chip);
          const neu = document.createElement('button');
          neu.className = 'btn ghost sm';
          neu.textContent = t('Neu erklären');
          neu.onclick = () => doExplain(true);
          foot.appendChild(neu);
        }
        const det = document.createElement('details');
        det.style.cssText = 'margin-top:10px;font-size:.78rem;color:var(--mut2)';
        det.innerHTML = `<summary style="cursor:pointer">${t('Rohdaten aus dem Graphen')}</summary>`;
        const pre = document.createElement('pre');
        pre.style.cssText = 'white-space:pre-wrap;margin:8px 0 0;font-size:.74rem;line-height:1.5';
        pre.textContent = j.context || '';
        det.appendChild(pre);
        out.appendChild(foot);
        out.appendChild(det);
      }
    }
  } catch { out.textContent = t('Fehler bei der Erklärung — bitte erneut versuchen.'); }
  finally { wait.style.display = 'none'; out.style.display = 'block'; }
}

/* ================= report ================= */
function mdToHtml(md) {
  const esc = s => s.replace(/&/g, '&amp;').replace(/</g, '&lt;');
  const blocks = md.split(/```/);
  let html = '';
  blocks.forEach((b, i) => {
    if (i % 2) { html += '<pre><code>' + esc(b.replace(/^\w*\n/, '')) + '</code></pre>'; return; }
    html += esc(b)
      .replace(/^### (.*)$/gm, '<h3>$1</h3>')
      .replace(/^## (.*)$/gm, '<h2>$1</h2>')
      .replace(/^# (.*)$/gm, '<h1>$1</h1>')
      .replace(/\*\*([^*]+)\*\*/g, '<b>$1</b>')
      .replace(/`([^`]+)`/g, '<code>$1</code>')
      .replace(/^[-*] (.*)$/gm, '<li>$1</li>')
      .replace(/(<li>.*<\/li>\n?)+/g, m => '<ul>' + m + '</ul>')
      .replace(/\n\n/g, '<br>');
  });
  return html;
}
async function showReport() {
  const j = await holeJson(`/ui/api/report/${$('proj').value}`);
  $('reportout').innerHTML = mdToHtml(j.markdown);
  document.querySelectorAll('.tab').forEach(t => t.classList.remove('on'));
  $('tab-report').classList.add('on');
}

/* ================= secrets ================= */
async function loadSecrets() {
  const names = await holeJson('/ui/api/secrets');
  const box = $('slist');
  box.innerHTML = '';
  if (!names.length) {
    box.innerHTML = `<div class="empty"><svg class="ic" viewBox="0 0 24 24"><use href="#i-key"/></svg><br>
      <span style="color:var(--txt);font-weight:600">${t('Der Vault ist noch leer')}</span><br>
      <span style="display:inline-block;margin-top:4px">${t('Leg oben deinen ersten API-Key oder dein erstes Token ab — etwa den OpenAI-Key fürs Nacht-Mapping. Es wird sofort verschlüsselt.')}</span></div>`;
    return;
  }
  for (const n of names) {
    const row = document.createElement('div');
    row.className = 'srow';
    row.innerHTML = `<div class="top"><span class="name"></span><span class="acts">
      <button data-a="show" aria-label="${t('Wert anzeigen')}"><svg class="ic" viewBox="0 0 24 24"><use href="#i-eye"/></svg></button>
      <button data-a="copy" aria-label="${t('Wert kopieren')}"><svg class="ic" viewBox="0 0 24 24"><use href="#i-copy"/></svg></button>
      <button data-a="del" class="del" aria-label="${t('Löschen')}"><svg class="ic" viewBox="0 0 24 24"><use href="#i-trash"/></svg></button>
      </span></div><div class="val"></div>`;
    row.querySelector('.name').textContent = n;
    const val = row.querySelector('.val');
    row.querySelector('[data-a=show]').onclick = async (e) => {
      const btn = e.currentTarget;
      if (!val.classList.contains('on')) {
        const j = await holeJson('/ui/api/secrets/' + encodeURIComponent(n));
        val.textContent = j.value; val.classList.add('on');
        btn.innerHTML = '<svg class="ic" viewBox="0 0 24 24"><use href="#i-eyeoff"/></svg>';
        btn.setAttribute('aria-label', t('Wert verbergen'));
      } else {
        val.classList.remove('on'); val.textContent = '';
        btn.innerHTML = '<svg class="ic" viewBox="0 0 24 24"><use href="#i-eye"/></svg>';
        btn.setAttribute('aria-label', t('Wert anzeigen'));
      }
    };
    row.querySelector('[data-a=copy]').onclick = async () => {
      const j = await holeJson('/ui/api/secrets/' + encodeURIComponent(n));
      try { await navigator.clipboard.writeText(j.value); toast(t('In Zwischenablage kopiert')); }
      catch { toast(t('Kopieren nicht möglich'), false); }
    };
    row.querySelector('[data-a=del]').onclick = async () => {
      if (!await askConfirm(t2('„{name}" wird unwiderruflich aus dem Vault gelöscht.', {name: n}))) return;
      await api('/ui/api/secrets/' + encodeURIComponent(n), {method: 'DELETE'});
      toast(t2('Gelöscht: {name}', {name: n}));
      loadSecrets();
    };
    box.appendChild(row);
  }
}
/* --- Angemeldete Geräte --- */
function relTime(ts) {
  if (!ts) return t('noch nie');
  const s = Math.max(0, Math.floor(Date.now() / 1000 - ts));
  if (s < 90) return t('gerade eben');
  if (s < 3600) return t2('vor {n} Min.', {n: Math.floor(s / 60)});
  if (s < 86400) return t2('vor {n} Std.', {n: Math.floor(s / 3600)});
  const d = Math.floor(s / 86400);
  return d === 1 ? t('gestern') : t2('vor {n} Tagen', {n: d});
}
function deviceHint(ua) {
  if (!ua) return '';
  if (/iPhone|iPad/i.test(ua)) return 'iPhone/iPad';
  if (/Android/i.test(ua)) return 'Android';
  if (/Macintosh/i.test(ua)) return 'Mac';
  if (/Windows/i.test(ua)) return 'Windows';
  if (/Linux/i.test(ua)) return 'Linux';
  if (/python|curl|node/i.test(ua)) return t('Programm');
  return '';
}
function sessionRow(s, refresh) {
  const row = document.createElement('div');
  row.className = 'srow';
  const fixed = s.revocable === false;                     // statisches Token
  const icon = s.kind === 'web' ? 'i-devices' : (s.kind === 'static' ? 'i-key' : 'i-bot');
  row.innerHTML = `<div class="top">
    <svg class="ic" style="color:${s.current ? 'var(--acc)' : 'var(--mut)'};flex:none" viewBox="0 0 24 24">
      <use href="#${icon}"/></svg>
    <div style="flex:1;min-width:0">
      <div style="display:flex;align-items:center;gap:8px;flex-wrap:wrap">
        <span class="slabel" style="font-weight:600;font-size:.92rem"></span>
        ${s.current ? `<span class="chip" style="color:var(--acc)">${t('dieses Gerät')}</span>` : ''}
        ${fixed ? `<span class="chip" style="color:var(--amber)">${t('läuft nie ab')}</span>` : ''}
      </div>
      <div class="smeta" style="color:var(--mut2);font-size:.76rem;line-height:1.5;margin-top:2px;overflow-wrap:anywhere"></div>
    </div>
    ${(s.current || fixed) ? '' : `<span class="acts"><button data-a="revoke" class="del" aria-label="${t('Gerät abmelden')}"><svg class="ic" viewBox="0 0 24 24"><use href="#i-logout"/></svg></button></span>`}
  </div>`;
  row.querySelector('.slabel').textContent = s.label;
  const hint = deviceHint(s.ua);
  const days = s.expires ? Math.max(0, Math.round((s.expires - Date.now() / 1000) / 86400)) : null;
  row.querySelector('.smeta').textContent = fixed
    ? s.note
    : t2('zuletzt aktiv {when}', {when: relTime(s.last_seen)}) + (hint ? ` · ${hint}` : '') +
      (days !== null ? ' · ' + t2('läuft in {n} Tagen ab', {n: days}) : '');
  const rb = row.querySelector('[data-a=revoke]');
  if (rb) rb.onclick = async () => {
    if (!await askConfirm(t2('„{label}" verliert sofort den Zugriff auf deinen Hub.', {label: s.label}))) return;
    const r = await api('/ui/api/sessions/' + encodeURIComponent(s.id), {method: 'DELETE'});
    toast(r.ok ? t2('{label} abgemeldet', {label: s.label}) : t('Abmelden fehlgeschlagen'), r.ok);
    (refresh || loadConnSessions)();
  };
  return row;
}
async function loadConnSessions() {
  let d;
  try { d = await holeJson('/ui/api/sessions'); } catch { return; }
  const box = $('connsess');
  box.innerHTML = '';
  const others = d.sessions.filter(s => !s.current && s.revocable !== false).length;
  const rall = $('connrevokeall'); if (rall) rall.style.display = others ? 'inline-flex' : 'none';
  if (!d.sessions.length) {
    box.innerHTML = `<div class="empty">${t('Noch keine Clients verbunden — erzeuge oben ein Token oder verbinde claude.ai.')}</div>`;
    return;
  }
  for (const s of d.sessions) box.appendChild(sessionRow(s, loadConnSessions));
}
/* ================= verbinden (connect) ================= */
let CONN = null, deviceToken = '', currentClient = 'webai';
async function loadConnect() {
  if (!CONN) { try { CONN = await holeJson('/ui/api/connect/info'); } catch { return; } }
  $('mcpurl').textContent = CONN.mcp_url;
  $('qrimg').innerHTML = CONN.qr || '';
  renderClient(currentClient);
  loadConnSessions();
}
function copyText(text, msg) {
  navigator.clipboard.writeText(text).then(() => toast(msg || t('Kopiert')))
    .catch(() => toast(t('Kopieren nicht möglich'), false));
}
function toggleQr() { const b = $('qrbox'); b.style.display = b.style.display === 'none' ? 'block' : 'none'; }
async function genToken(e) {
  e.preventDefault();
  const label = $('tokenlabel').value.trim() || 'MCP client';
  $('genbtn').disabled = true;
  try {
    const r = await api('/ui/api/connect/token', {method: 'POST', headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({label})});
    const j = await r.json();
    if (!r.ok) { toast(j.error || t('Fehlgeschlagen'), false); return; }
    deviceToken = j.token;
    $('tokenval').textContent = deviceToken;
    $('tokenout').style.display = 'block';
    $('tokenlabel').value = '';
    renderClient(currentClient);            // Token gleich in die Anleitung einsetzen
    loadConnSessions();
    toast(t2('Token erzeugt für „{label}“', {label: j.label}));
  } finally { $('genbtn').disabled = false; }
}
async function testConnect() {
  const btn = $('testbtn'), out = $('testresult');
  btn.disabled = true; out.style.display = 'inline-flex';
  out.innerHTML = `<div class="spinner" style="--sz:16px"></div><span style="color:var(--mut)">${t('teste…')}</span>`;
  const mk = (col, icon, txt) => `<svg class="ic" style="width:16px;height:16px;color:${col}" viewBox="0 0 24 24"><use href="#${icon}"/></svg><span style="color:${col}">${txt}</span>`;
  try {
    const r = await fetch('/mcp', {method: 'POST',
      headers: {'Authorization': 'Bearer ' + (deviceToken || TOKEN), 'Content-Type': 'application/json',
                'Accept': 'application/json, text/event-stream'},
      body: JSON.stringify({jsonrpc: '2.0', id: 1, method: 'initialize',
        params: {protocolVersion: '2025-06-18', capabilities: {}, clientInfo: {name: 'hub-connect-test', version: '1'}}})});
    if (r.ok) out.innerHTML = mk('var(--acc)', 'i-check', t('Verbindung steht'));
    else if (r.status === 401 || r.status === 403) out.innerHTML = mk('var(--red)', 'i-alert', t('Token nicht akzeptiert'));
    else out.innerHTML = mk('var(--amber)', 'i-alert', t2('Server erreichbar (HTTP {status})', {status: r.status}));
  } catch { out.innerHTML = mk('var(--red)', 'i-alert', t('nicht erreichbar')); }
  finally { btn.disabled = false; }
}
function pickClient(c) {
  currentClient = c;
  document.querySelectorAll('.segbtn').forEach(b => b.classList.toggle('on', b.dataset.c === c));
  renderClient(c);
}
function codeBlock(inner) {
  const wrap = document.createElement('pre');
  wrap.className = 'codeblk';
  wrap.innerHTML = inner;
  const cp = document.createElement('button');
  cp.className = 'cp'; cp.setAttribute('aria-label', t('Kopieren'));
  cp.innerHTML = '<svg class="ic" style="width:16px;height:16px" viewBox="0 0 24 24"><use href="#i-copy"/></svg>';
  cp.onclick = () => copyText(wrap.textContent.replace(/\s+$/, ''), t('Kopiert'));
  wrap.appendChild(cp);
  return wrap;
}
function step(n, html) { return `<div class="step"><span class="num">${n}</span><div class="tx">${html}</div></div>`; }
function renderClient(c) {
  const url = CONN ? CONN.mcp_url : '';
  const tokSpan = deviceToken ? `<span class="tok">${escapeHtml(deviceToken)}</span>` : `<span class="ph">&lt;${t('DEIN_TOKEN')}&gt;</span>`;
  const body = $('clientbody');
  let steps = '', block;
  if (c === 'webai') {
    steps = step(1, t('Öffne <b>claude.ai</b> → <b>Einstellungen</b> → <b>Connectors</b>.')) +
            step(2, t('Klick auf <b>„Connector hinzufügen"</b> → <b>„Eigenen Connector"</b>.')) +
            step(3, t('Füge diese Adresse ein und bestätige:')) +
            step(4, t('claude.ai fragt einmalig dein <b>Zugangspasswort</b> ab (sichere OAuth-Anmeldung) — <b>kein Token nötig</b>.'));
    block = codeBlock(escapeHtml(url));
  } else if (c === 'code') {
    steps = step(1, t('Führe im Terminal diesen Befehl aus:')) +
            step(2, deviceToken ? t('<b>Claude Code</b> kennt deinen Hub jetzt.') : t('Erzeuge oben zuerst ein <b>Geräte-Token</b> — es füllt den Befehl vollständig aus.'));
    block = codeBlock(`claude mcp add --transport http knowledge ${escapeHtml(url)} \\\n  --header "Authorization: Bearer ${tokSpan}"`);
  } else if (c === 'desktop') {
    steps = step(1, t('Öffne <b>Claude Desktop</b> → <b>Einstellungen</b> → <b>Entwickler</b> → <b>Konfiguration bearbeiten</b>.')) +
            step(2, t('Füge diesen Eintrag ein (benötigt <span class="mono">Node.js</span>) und starte Claude Desktop neu:'));
    block = codeBlock(`{\n  "mcpServers": {\n    "knowledge": {\n      "command": "npx",\n      "args": ["-y", "mcp-remote", "${escapeHtml(url)}",\n        "--header", "Authorization: Bearer ${tokSpan}"]\n    }\n  }\n}`);
  } else {
    steps = step(1, t('Jeder MCP-Client mit <b>Streamable-HTTP</b>-Transport verbindet sich mit dieser Adresse …')) +
            step(2, t('… und diesem Header:'));
    block = codeBlock(escapeHtml(url) + '\n\nAuthorization: Bearer ' + tokSpan);
  }
  body.innerHTML = '';
  const st = document.createElement('div'); st.innerHTML = steps;
  body.appendChild(st); body.appendChild(block);
  if (c !== 'webai' && !deviceToken) {
    const hint = document.createElement('p');
    hint.style.cssText = 'color:var(--amber);font-size:var(--fs-sm);margin:10px 0 0';
    hint.textContent = t('↑ Erzeuge oben ein Geräte-Token — es ersetzt <DEIN_TOKEN> automatisch.');
    body.appendChild(hint);
  }
}
async function revokeAllSessions() {
  if (!await askConfirm(t('Alle anderen Geräte und KI-Clients verlieren sofort den Zugriff. Du bleibst angemeldet.'))) return;
  const r = await api('/ui/api/sessions', {method: 'DELETE'});
  const j = await r.json();
  toast(r.ok ? t2('{n} Zugänge widerrufen', {n: j.revoked}) : t('Fehlgeschlagen'), r.ok);
  loadConnSessions();
}

async function addSecret(e) {
  e.preventDefault();
  $('secerr').textContent = '';
  const name = $('sname').value.trim(), value = $('svalue').value;
  if (!name || !value) {
    const msg = t('Bitte Name und Wert ausfüllen.');
    $('secerr').textContent = msg;
    toast(msg, false);
    return;
  }
  const btn = $('addbtn');
  btn.disabled = true;
  try {
    const r = await api('/ui/api/secrets', {method: 'POST', headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({name, value})});
    if (r.ok) {
      toast(t2('Gespeichert: {name}', {name}));
      $('secerr').textContent = '';
      $('sname').value = ''; $('svalue').value = '';
      loadSecrets();
    } else {
      const msg = await fehlerText(r, t('Fehler beim Speichern'));
      $('secerr').textContent = msg;      // bleibt stehen, bis es behoben ist
      toast(msg, false);
    }
  } finally { btn.disabled = false; }
}

/* ================= diagnose ================= */
const HSTYLE = {
  /* Kein label-Feld: Es wurde nirgends gelesen und hätte nur deutschen Text
     am Leben gehalten, den keine Übersetzung je erreicht. */
  ok:   {col: 'var(--acc)',   bg: 'rgba(34,197,94,.10)',  icon: 'i-check'},
  warn: {col: 'var(--amber)', bg: 'rgba(251,191,36,.10)', icon: 'i-alert'},
  err:  {col: 'var(--red)',   bg: 'rgba(248,113,113,.10)',icon: 'i-alert'},
};
async function loadHealth() {
  const box = $('healthchecks');
  box.innerHTML = '<div style="display:flex;justify-content:center;padding:2rem"><div class="spinner" style="--sz:38px"></div></div>';
  let h;
  try { h = await holeJson('/ui/api/health'); }
  catch { box.innerHTML = `<div class="empty">${t('Diagnose nicht abrufbar.')}</div>`; return; }

  const bad = h.checks.filter(c => c.status !== 'ok').length;
  const errs = h.checks.filter(c => c.status === 'err').length;
  const s = errs ? HSTYLE.err : (bad ? HSTYLE.warn : HSTYLE.ok);
  $('healthsummary').innerHTML =
    `<div class="card" style="display:flex;align-items:center;gap:14px;border-color:${s.col};background:${s.bg}">
       <svg class="ic" style="width:26px;height:26px;color:${s.col};flex:none" viewBox="0 0 24 24"><use href="#${s.icon}"/></svg>
       <div style="min-width:0">
         <div style="font-weight:700;font-size:1.02rem">${errs ? t('Es gibt ein Problem') : (bad ? t('Läuft — mit Hinweisen') : t('Alles in Ordnung'))}</div>
         <div style="color:var(--mut);font-size:.85rem;line-height:1.5">${
           errs ? t2('{n} Punkt(e) brauchen deine Aufmerksamkeit.', {n: errs})
                : (bad ? t2('{n} Hinweis(e) — das System läuft, könnte aber besser abgesichert sein.', {n: bad})
                       : t2('{n} Prüfungen bestanden.', {n: h.checks.length}))}</div>
       </div>
     </div>`;

  box.innerHTML = '';
  for (const c of h.checks) {
    const st = HSTYLE[c.status] || HSTYLE.warn;
    const row = document.createElement('div');
    row.className = 'srow';
    row.innerHTML = `<div style="display:flex;gap:12px;align-items:flex-start">
      <svg class="ic" style="color:${st.col};flex:none;margin-top:2px" viewBox="0 0 24 24"><use href="#${st.icon}"/></svg>
      <div style="flex:1;min-width:0">
        <div class="hname" style="font-weight:600;font-size:.92rem"></div>
        <div class="hdetail" style="color:var(--mut);font-size:.82rem;line-height:1.55;overflow-wrap:anywhere"></div>
        <div class="hfix" style="color:${st.col};font-size:.78rem;line-height:1.5;margin-top:5px;display:none"></div>
      </div>
    </div>`;
    row.querySelector('.hname').textContent = c.name;
    row.querySelector('.hdetail').textContent = c.detail;
    if (c.fix) { const f = row.querySelector('.hfix'); f.textContent = '→ ' + c.fix; f.style.display = 'block'; }
    // Beim Angriffsschutz einen „Freigeben"-Knopf anbieten (falls Selbst-Aussperrung)
    if (c.name === 'Angriffsschutz' && c.status === 'err') {
      const ub = document.createElement('button');
      ub.className = 'btn ghost';
      ub.style.cssText = 'margin-top:10px;min-height:36px;font-size:.8rem;margin-left:34px';
      ub.textContent = t('Sperren aufheben');
      ub.onclick = async () => {
        const r = await api('/ui/api/unblock', {method: 'POST'});
        toast(r.ok ? t('Sperren aufgehoben') : t('Fehlgeschlagen'), r.ok);
        loadHealth();
      };
      row.querySelector('div > div').appendChild(ub);
    }
    box.appendChild(row);
  }

  const i = h.info;
  $('healthinfo').innerHTML =
    `<div class="stat"><div class="v" style="font-size:.95rem">${i.backend}</div><div class="k">${t('KI-Anbieter')}</div></div>
     <div class="stat"><div class="v">${i.projects}</div><div class="k">${t('Projekte')}</div></div>
     <div class="stat"><div class="v">${i.secrets}</div><div class="k">${t('Secrets im Vault')}</div></div>
     <div class="stat"><div class="v">${i.graphs_size}</div><div class="k">${t('Wissensgraphen')}</div></div>
     <div class="stat" style="grid-column:1/-1"><div class="v mono" style="font-size:.82rem;overflow-wrap:anywhere">${i.mcp_url}</div>
       <div class="k">${t('Adresse für KI-Clients (MCP)')}</div></div>`;

  if (h.errors && h.errors.length) {
    $('healtherrbox').style.display = 'block';
    $('healtherrs').textContent = h.errors.join('\n');
  } else $('healtherrbox').style.display = 'none';
}

/* --- Zwei-Faktor-Authentifizierung --- */
async function loadTwoFA() {
  let s;
  try { s = await holeJson('/ui/api/2fa'); } catch { return; }
  const box = $('twofabody');
  if (s.enabled) {
    box.innerHTML = `
      <div style="display:flex;gap:10px;align-items:flex-start">
        <svg class="ic" style="color:var(--acc);flex:none;margin-top:2px" viewBox="0 0 24 24"><use href="#i-check"/></svg>
        <div style="flex:1;min-width:0">
          <div style="font-weight:600;font-size:.92rem">${t('Aktiv')}</div>
          <p style="margin:4px 0 0;color:var(--mut);font-size:.82rem;line-height:1.55">
            ${t2('Beim Anmelden wird zusätzlich zum Passwort ein Code aus deiner App verlangt. Noch <b>{n}</b> Wiederherstellungscodes übrig.', {n: s.recovery_left})}</p>
          <form style="display:flex;gap:var(--sp-2);flex-wrap:wrap;margin-top:var(--sp-3)" data-form="twofa-disable">
            <input id="off2fa" placeholder="${t('Aktueller Code zum Abschalten')}" inputmode="numeric"
                   maxlength="9" style="flex:1;min-width:12rem">
            <button class="btn danger" style="min-height:44px">${t('2FA ausschalten')}</button>
          </form>
        </div>
      </div>`;
    return;
  }
  box.innerHTML = `
    <p style="margin:0 0 var(--sp-3);color:var(--mut);font-size:.84rem;line-height:1.6">
      ${t('Schütze deinen Zugang mit einer Authenticator-App (Google Authenticator, Aegis, 1Password …). Selbst wer dein Passwort kennt, kommt dann ohne dein Handy nicht rein.')}</p>
    <button class="btn" id="start2fa" data-act="twofa-setup">
      <svg class="ic" viewBox="0 0 24 24"><use href="#i-shieldcheck"/></svg>${t('Einrichten')}</button>`;
}
async function setup2fa() {
  const btn = $('start2fa');
  btn.disabled = true;
  let d;
  try {
    const r = await api('/ui/api/2fa/setup', {method: 'POST'});
    if (!r.ok) { await zeigeFehler(r, t('Zwei-Faktor lässt sich gerade nicht einrichten.')); return; }
    d = await r.json();
  } catch (e) {
    /* Ohne dieses finally blieb der Knopf nach einem Fehler FÜR IMMER deaktiviert —
       der Nutzer konnte 2FA nur noch durch Neuladen der Seite einrichten. */
    return;
  } finally { btn.disabled = false; }
  $('twofabody').innerHTML = `
    <p style="margin:0 0 var(--sp-3);color:var(--mut);font-size:.84rem;line-height:1.6">
      ${t('<b>1.</b> Scanne diesen QR-Code mit deiner Authenticator-App:')}</p>
    <div style="background:#fff;border-radius:var(--r-sm);padding:12px;display:inline-block">${d.qr}</div>
    <p style="margin:var(--sp-3) 0 6px;color:var(--mut2);font-size:.78rem">
      ${t('Kein Scanner? Geheimnis von Hand eintragen:')}</p>
    <div class="mono" style="background:var(--bg);border:1px solid var(--line2);border-radius:var(--r-sm);
         padding:10px 12px;font-size:.82rem;color:var(--acc);user-select:all;overflow-wrap:anywhere">${d.secret}</div>
    <form style="margin-top:var(--sp-4)" data-form="twofa-enable">
      <label style="font-size:.84rem;color:var(--mut);display:block;margin-bottom:.4rem">
        ${t('<b>2.</b> Bestätige mit dem aktuellen Code aus der App:')}</label>
      <div style="display:flex;gap:var(--sp-2);flex-wrap:wrap">
        <input id="verify2fa" placeholder="${t('6-stelliger Code')}" inputmode="numeric" maxlength="6"
               style="flex:1;min-width:10rem;text-align:center;letter-spacing:.12em;font-size:1.05rem" required>
        <button class="btn" style="min-height:44px">${t('Aktivieren')}</button>
      </div>
    </form>`;
  setTimeout(() => $('verify2fa')?.focus(), 100);
}
async function enable2fa(e) {
  e.preventDefault();
  // Doppelklick-Schutz wie bei allen anderen Schreibaktionen: Ein zweites Absenden
  // würde serverseitig zwar abgewiesen (409), aber der Knopf soll gar nicht erst
  // ein zweites Mal feuern. Der disabled Submit-Button unterbindet auch Enter-Doppel.
  const btn = e.submitter || (e.target.querySelector && e.target.querySelector('button'));
  if (btn) btn.disabled = true;
  try {
  const r = await api('/ui/api/2fa/enable', {method: 'POST', headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({code: $('verify2fa').value.trim()})});
  const j = await r.json();
  if (!r.ok) { toast(j.error || t('Fehlgeschlagen'), false); return; }
  // Wiederherstellungscodes EINMALIG zeigen
  $('twofabody').innerHTML = `
    <div style="display:flex;gap:10px;align-items:flex-start">
      <svg class="ic" style="color:var(--acc);flex:none;margin-top:2px" viewBox="0 0 24 24"><use href="#i-check"/></svg>
      <div style="flex:1;min-width:0">
        <div style="font-weight:700;margin-bottom:4px">${t('2FA ist aktiv')}</div>
        <div class="warn" style="margin:8px 0"><svg class="ic" viewBox="0 0 24 24"><use href="#i-alert"/></svg>
          <div>${t('Sichere diese Wiederherstellungscodes. Jeder ist einmal gültig und rettet dich, wenn du dein Handy verlierst — ohne sie wärst du ausgesperrt.')}</div></div>
        <div class="mono" id="reccodes" style="background:var(--bg);border:1px solid var(--line2);
             border-radius:var(--r-sm);padding:12px 14px;font-size:.86rem;line-height:1.9;
             color:var(--acc);user-select:all;columns:2"></div>
        <button class="btn ghost" style="margin-top:10px;min-height:38px;font-size:.82rem" data-act="twofa-copy">
          <svg class="ic" viewBox="0 0 24 24"><use href="#i-copy"/></svg>${t('Kopieren')}</button>
        <button class="btn" style="margin-top:10px;margin-left:8px;min-height:38px;font-size:.82rem"
                data-act="twofa-done">${t('Fertig')}</button>
      </div>
    </div>`;
  window.__recovery = j.recovery;
  $('reccodes').textContent = j.recovery.join('\n');
  toast(t('Zwei-Faktor-Authentifizierung aktiviert'));
  } finally { if (btn) btn.disabled = false; }
}
function copyRecovery() {
  navigator.clipboard.writeText((window.__recovery || []).join('\n'))
    .then(() => toast(t('Codes kopiert'))).catch(() => toast(t('Bitte abschreiben'), false));
}
async function disable2fa(e) {
  e.preventDefault();
  const btn = e.submitter || (e.target.querySelector && e.target.querySelector('button'));
  if (btn) btn.disabled = true;
  try {
    if (!await askConfirm(t('Zwei-Faktor-Schutz wirklich abschalten? Danach genügt wieder das Passwort allein.'))) return;
    const r = await api('/ui/api/2fa/disable', {method: 'POST', headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({code: $('off2fa').value.trim()})});
    const j = await r.json();
    toast(r.ok ? t('2FA ausgeschaltet') : (j.error || t('Fehlgeschlagen')), r.ok);
    loadTwoFA();
  } finally { if (btn) btn.disabled = false; }
}

/* --- Vault-Sicherheit --- */
async function loadVault() {
  let v;
  try { v = await holeJson('/ui/api/vault'); } catch { return; }
  const box = $('vaultbody');
  box.innerHTML = `
    <div style="display:flex;align-items:flex-start;gap:var(--sp-3)">
      <label class="switch" style="flex:none;margin-top:2px">
        <input type="checkbox" id="autounlock" ${v.auto_unlock ? 'checked' : ''}
               aria-label="${t('Automatische Entsperrung')}">
        <span class="slider"></span>
      </label>
      <div style="flex:1;min-width:0">
        <div style="font-weight:600;font-size:.92rem">${t('Automatisch entsperren')}</div>
        <p style="margin:4px 0 0;color:var(--mut);font-size:.82rem;line-height:1.6">
          ${v.auto_unlock
            ? t('Der Vault öffnet sich nach einem Neustart von selbst — nötig, damit das Nacht-Mapping ohne dich an die API-Keys kommt. Der Schlüssel dafür liegt in der env-Datei: Wer dein Server-Konto übernimmt, kommt damit auch an die Secrets.')
            : t('<b>Maximale Sicherheit:</b> Der Vault bleibt nach jedem Neustart gesperrt, bis du dich anmeldest. Selbst wer dein Server-Konto übernimmt, kann die Secrets nicht lesen. <b>Aber:</b> Das Nacht-Mapping überspringt dann die Dokumenten-Analyse, bis du dich einmal angemeldet hast.')}
        </p>
        <p style="margin:8px 0 0;color:var(--mut2);font-size:.76rem">
          ${t2('Vault-Format v{v} · Passwort-Entsperrung: {state}', {v: v.version, state: v.has_password ? t('eingerichtet') : t('nicht eingerichtet')})}
        </p>
      </div>
    </div>
    <form style="margin-top:var(--sp-4);border-top:1px solid var(--line);padding-top:var(--sp-4)"
          data-form="password">
      <div style="font-weight:600;font-size:.92rem;margin-bottom:var(--sp-3)">${t('Zugangspasswort ändern')}</div>
      <div style="display:flex;gap:var(--sp-2);flex-wrap:wrap">
        <input type="password" id="pwold" placeholder="${t('Aktuelles Passwort')}" autocomplete="current-password"
               style="flex:1;min-width:12rem" required>
        <input type="password" id="pwnew" placeholder="${t('Neues Passwort (min. 8 Zeichen)')}" autocomplete="new-password"
               style="flex:1;min-width:12rem" required>
        <button class="btn ghost" id="pwbtn" style="min-height:44px">${t('Ändern')}</button>
      </div>
      <p style="margin:8px 0 0;color:var(--mut2);font-size:.76rem;line-height:1.5">
        ${t('Die Secrets werden dabei nicht neu verschlüsselt — nur der Zugang. Dauert einen Moment (die Ableitung ist absichtlich langsam).')}</p>
    </form>`;
  $('autounlock').onchange = async (e) => {
    const on = e.target.checked;
    const r = await api('/ui/api/vault/autounlock', {method: 'POST', headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({enabled: on})});
    if (r.ok) toast(on ? t('Automatische Entsperrung aktiv') : t('Vault bleibt künftig nach Neustarts gesperrt'));
    else { await zeigeFehler(r, t('Fehlgeschlagen')); e.target.checked = !on; }
    loadVault(); loadHealth();
  };
}
async function changePassword(e) {
  e.preventDefault();
  const btn = $('pwbtn');
  btn.disabled = true; btn.textContent = t('Ändere…');
  try {
    const r = await api('/ui/api/vault/password', {method: 'POST', headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({old: $('pwold').value, new: $('pwnew').value})});
    const j = await r.json();
    if (r.ok) { toast(t('Passwort geändert — beim nächsten Anmelden gilt das neue.')); $('pwold').value = ''; $('pwnew').value = ''; }
    else toast(j.error || t('Fehlgeschlagen'), false);
  } finally { btn.disabled = false; btn.textContent = t('Ändern'); }
}

/* --- Sicherung --- */
let backupPoll = null;
async function loadBackup() {
  let b;
  try { b = await holeJson('/ui/api/backup'); } catch { return; }
  const box = $('backupbody');
  $('backupbtn').style.display = b.passphrase ? 'inline-flex' : 'none';

  if (!b.passphrase) {
    box.innerHTML = `
      <div style="display:flex;gap:10px;align-items:flex-start">
        <svg class="ic" style="color:var(--red);flex:none;margin-top:2px" viewBox="0 0 24 24"><use href="#i-alert"/></svg>
        <div style="min-width:0">
          <div style="font-weight:600;margin-bottom:2px">${t('Es wird nichts gesichert')}</div>
          <p style="margin:0 0 var(--sp-3);color:var(--mut);font-size:.84rem;line-height:1.6">
            ${t('Stirbt die Festplatte, sind alle Secrets unwiederbringlich weg. Richte eine Sicherung ein: Vault, Schlüssel und Einstellungen werden dann verschlüsselt in deinen Backup-Ordner und in dein privates Git-Repo gelegt — nur mit der Backup-Passphrase lesbar.')}</p>
          <button class="btn" id="bsetup" data-act="backupsetup">
            <svg class="ic" viewBox="0 0 24 24"><use href="#i-shield"/></svg>${t('Sicherung einrichten')}</button>
        </div>
      </div>`;
    return;
  }

  const l = b.last;
  const git = b.targets.find(t => t.type === 'git');
  const rows = b.targets.map(tg =>
    `<div class="stat"><div class="v" style="font-size:.85rem;overflow-wrap:anywhere">${tg.where}</div>
       <div class="k">${tg.type === 'git' ? t('Offsite (Git)') : t('Lokal')}</div></div>`).join('');
  box.innerHTML =
    `<div class="statgrid">
       <div class="stat"><div class="v ${l ? 'acc' : ''}" style="font-size:.95rem">${l ? relTime(l.ts) : t('noch nie')}</div>
         <div class="k">${t('Letzte Sicherung')}${l ? ' · ' + (l.size / 1024).toFixed(1) + ' KB' : ''}</div></div>
       <div class="stat"><div class="v">${b.count}</div><div class="k">${t('Sicherungen vorhanden')}</div></div>
       ${rows}
     </div>
     <pre id="backuplog" style="display:none;margin:var(--sp-3) 0 0;font-size:.76rem;line-height:1.6;
       color:var(--mut);white-space:pre-wrap;overflow-wrap:anywhere"></pre>

     <details style="margin-top:var(--sp-4);border-top:1px solid var(--line);padding-top:var(--sp-3)" ${git ? '' : 'open'}>
       <summary style="cursor:pointer;font-size:.86rem;font-weight:600">
         ${t2('Offsite-Ziel (Git-Repository) {action}', {action: git ? t('ändern') : t('einrichten')})}</summary>
       <p style="color:var(--mut);font-size:.82rem;line-height:1.6;margin:10px 0">
         ${t('Damit die Sicherung einen Plattenausfall übersteht, gehört sie in ein Repository auf einem anderen Rechner. Die Datei ist verschlüsselt — das Repo sieht nur unlesbare Daten. Für GitHub brauchst du einen Zugriffstoken mit Schreibrecht auf genau dieses Repo (<span class="mono" style="font-size:.9em">Settings → Developer settings → Personal access tokens → Fine-grained → Contents: Read and write</span>). Der Token wird im Vault verschlüsselt.')}</p>
       <form data-form="backuptarget" style="display:flex;flex-direction:column;gap:var(--sp-2)">
         <input id="giturl" placeholder="${t('https://github.com/deinname/dein-backup-repo.git')}"
                value="${git && git.url ? git.url : ''}" autocomplete="off" spellcheck="false" required>
         <label style="font-size:.78rem;color:var(--mut);margin-top:2px">${t('Zugriffstoken')}</label>
         <select id="gitsecret" data-change="gitsource">
           <option value="">${t('— neuen Token eingeben —')}</option>
         </select>
         <div class="pwwrap" id="gittokenwrap">
           <input type="password" id="gittoken" placeholder="${t('GitHub-Token (ghp_… oder github_pat_…)')}"
                  autocomplete="off">
           <button type="button" aria-label="${t('Token anzeigen')}" data-act="togglepw" data-arg="gittoken">
             <svg class="ic" viewBox="0 0 24 24"><use href="#i-eye"/></svg></button>
         </div>
         <div style="display:flex;gap:var(--sp-2);flex-wrap:wrap">
           <input id="gitsub" placeholder="${t('Unterordner')}" value="${git ? (git.subdir || 'hub-backups') : 'hub-backups'}"
                  style="flex:1;min-width:9rem">
           <input id="gitbranch" placeholder="Branch" value="${git ? (git.branch || 'main') : 'main'}"
                  style="flex:1;min-width:7rem">
         </div>
         <div style="display:flex;gap:var(--sp-2);flex-wrap:wrap">
           <button class="btn" id="gitsave" style="min-height:42px">${t('Ziel speichern')}</button>
           ${git ? `<button type="button" class="btn danger" style="min-height:42px" data-act="backupremove">${t('Ziel entfernen')}</button>` : ''}
         </div>
       </form>
     </details>`;

  fillGitSecrets(git && git.secret ? git.secret : '');

  if (b.run && b.run.status !== 'idle') {
    const log = $('backuplog');
    if (log) { log.style.display = 'block'; log.textContent = b.run.log; }
    $('backupbtn').disabled = b.run.status === 'running';
    clearInterval(backupPoll);
    if (b.run.status === 'running') backupPoll = setInterval(loadBackup, 2500);
  }
}
async function setupBackup() {
  $('bsetup').disabled = true;
  const r = await api('/ui/api/backup/setup', {method: 'POST'});
  const j = await r.json();
  if (!r.ok) { toast(j.error || t('Fehlgeschlagen'), false); return; }
  // Passphrase EINMALIG zeigen — ohne sie ist jede Sicherung wertlos.
  $('backupbody').innerHTML = `
    <div style="display:flex;gap:10px;align-items:flex-start">
      <svg class="ic" style="color:var(--amber);flex:none;margin-top:2px" viewBox="0 0 24 24"><use href="#i-alert"/></svg>
      <div style="min-width:0;flex:1">
        <div style="font-weight:700;margin-bottom:4px">${t('Sichere diese Passphrase JETZT')}</div>
        <p style="margin:0 0 10px;color:var(--mut);font-size:.84rem;line-height:1.6">
          ${t('Sie ist der einzige Schlüssel zu deinen Sicherungen. Geht sie verloren, sind auch die Sicherungen wertlos. Leg sie in deinen Passwort-Manager — nicht auf diesen Server.')}</p>
        <div class="mono" id="ppval" style="background:var(--bg);border:1px solid var(--line2);
             border-radius:var(--r-sm);padding:12px 14px;color:var(--acc);font-size:.9rem;
             overflow-wrap:anywhere;user-select:all"></div>
        <button class="btn ghost" style="margin-top:10px;min-height:38px;font-size:.82rem" id="ppcopy">
          <svg class="ic" viewBox="0 0 24 24"><use href="#i-copy"/></svg>${t('Kopieren')}</button>
        <button class="btn" style="margin-top:10px;margin-left:8px;min-height:38px;font-size:.82rem"
                data-act="backupconfirmed">${t('Habe ich gesichert — jetzt sichern')}</button>
      </div>
    </div>`;
  $('ppval').textContent = j.passphrase;
  $('ppcopy').onclick = async () => {
    try { await navigator.clipboard.writeText(j.passphrase); toast(t('Passphrase kopiert')); }
    catch { toast(t('Kopieren nicht möglich — bitte abschreiben'), false); }
  };
}
/* Token-Quelle: vorhandenes Vault-Secret ODER neue Eingabe */
async function fillGitSecrets(selected) {
  const sel = $('gitsecret');
  if (!sel) return;
  let names = [];
  try { names = await holeJson('/ui/api/secrets'); } catch { return; }
  sel.innerHTML = `<option value="">${t('— neuen Token eingeben —')}</option>` +
    names.map(n => `<option value="${n}" ${n === selected ? 'selected' : ''}>${t2('aus dem Vault: {name}', {name: n})}</option>`).join('');
  gitTokenSourceChanged();
}
function gitTokenSourceChanged() {
  const useVault = !!$('gitsecret').value;
  $('gittokenwrap').style.display = useVault ? 'none' : 'block';
  if (useVault) $('gittoken').value = '';
}
async function saveBackupTarget(e) {
  e.preventDefault();
  const btn = $('gitsave');
  btn.disabled = true; btn.textContent = t('Speichere…');
  try {
    const r = await api('/ui/api/backup/target', {method: 'POST', headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({url: $('giturl').value.trim(), token: $('gittoken').value.trim(),
                            secret: $('gitsecret').value,
                            subdir: $('gitsub').value.trim(), branch: $('gitbranch').value.trim()})});
    const j = await r.json();
    if (r.ok) { toast(t('Offsite-Ziel gespeichert — jetzt „Jetzt sichern“ drücken zum Testen')); loadBackup(); }
    else toast(j.error || t('Fehlgeschlagen'), false);
  } finally { btn.disabled = false; btn.textContent = t('Ziel speichern'); }
}
async function removeBackupTarget() {
  if (!await askConfirm(t('Das Offsite-Ziel wird entfernt. Künftige Sicherungen liegen dann nur noch lokal.'))) return;
  const r = await api('/ui/api/backup/target', {method: 'DELETE'});
  toast(r.ok ? t('Offsite-Ziel entfernt') : t('Fehlgeschlagen'), r.ok);
  loadBackup();
}
async function runBackup() {
  const btn = $('backupbtn');
  if (btn) btn.disabled = true;
  const r = await api('/ui/api/backup/run', {method: 'POST'});
  if (!r.ok) { await zeigeFehler(r, t('Start fehlgeschlagen')); if (btn) btn.disabled = false; return; }
  toast(t('Sicherung gestartet'));
  setTimeout(loadBackup, 1200);
}

/* ================= audit ================= */
function badgeFor(action) {
  if (action.startsWith('GET-MISS') || action.endsWith('MISS')) return 'b-miss';
  if (action.startsWith('GET')) return 'b-get';
  if (action.startsWith('SET')) return 'b-set';
  if (action.startsWith('DELETE')) return 'b-del';
  return 'b-list';
}
async function loadAudit() {
  const lines = await holeJson('/ui/api/audit');
  const box = $('auditlist');
  box.innerHTML = '';
  if (!lines.length) {
    box.innerHTML = `<div class="empty"><svg class="ic" viewBox="0 0 24 24"><use href="#i-scroll"/></svg><br>
      <span style="color:var(--txt);font-weight:600">${t('Noch nichts protokolliert')}</span><br>
      <span style="display:inline-block;margin-top:4px">${t('Sobald ein Secret gelesen, gesetzt oder gelöscht wird, erscheint hier der Eintrag — mit Zeitpunkt und Client.')}</span></div>`;
    return;
  }
  for (const line of lines) {
    const m = line.match(/^(\S+)\s+(\S+)\s+(.*?)\s+client=(\S+)$/);
    const row = document.createElement('div');
    row.className = 'arow';
    if (m) {
      const [, ts, action, name, client] = m;
      const when = ts.replace('T', ' ').replace('Z', '');
      row.innerHTML = `<span class="badge ${badgeFor(action)}">${action}</span>
        <span class="aname"></span><span class="ameta">${client}<br>${when.slice(5, 16)}</span>`;
      row.querySelector('.aname').textContent = name;
    } else {
      row.innerHTML = `<span class="aname"></span>`;
      row.querySelector('.aname').textContent = line;
    }
    box.appendChild(row);
  }
}

/* ================= boot ================= */
async function boot() {
  window.BOOTED = true;
  const h = location.hash.slice(1);
  if (h === 'secrets' || h === 'audit') tab(h);
  try { await loadProjects(); } catch {}
  // Beim allerersten Login die Einführung zeigen (danach über „?" oben erreichbar)
  let toured = true;
  try { toured = !!localStorage.getItem('kmcp_toured'); } catch {}
  if (!toured) setTimeout(startTour, 700);
}
if (TOKEN) {
  api('/ui/api/projects').then(() => {
    $('login').style.display = 'none';
    boot();
  }).catch(() => {});
}

/* Auffangnetz: Was hier landet, hätte der Nutzer sonst nie erfahren —
   es stünde nur in der Browser-Konsole, die niemand offen hat. */
window.addEventListener('error', e => {
  if (e.message) showError(t2('Ein Fehler in der Oberfläche: {msg}', {msg: e.message}));
});
window.addEventListener('unhandledrejection', e => {
  const m = String(e.reason && e.reason.message || e.reason || '');
  // Ein Abbruch ist kein Fehler (Seitenwechsel, veraltete Anfrage) — kein Banner dafür.
  if (e.reason && e.reason.name === 'AbortError') return;
  // Diese drei behandeln wir bereits gezielt — kein doppeltes Banner.
  if (/unauthorized|locked|server error/.test(m)) return;
  if (m) showError(t2('Ein Fehler in der Oberfläche: {msg}', {msg: m}));
});

/* ================= Aktions-Register =================
   Ersatz für Inline-Handler (onclick="…"): Die CSP verbietet Inline-Skripte
   (script-src 'self'), damit eingeschleustes Markup niemals Code ausführen kann.
   Jedes klickbare Element trägt data-act (+ data-arg), Formulare data-form,
   Auswahlfelder data-change — drei Delegations-Listener rufen die Funktion auf.
   Delegation statt Einzelbindung, damit auch dynamisch erzeugtes Markup
   (2FA-Karte, Backup-Karte) ohne Extra-Schritt funktioniert. */
const AKTIONEN = {
  tab: el => tab(el.dataset.arg),
  more: () => openMore(),
  lang: () => toggleLang(),
  theme: () => toggleTheme(),
  tour: () => startTour(),
  logout: () => logout(),
  togglepw: el => togglePw(el.dataset.arg, el),
  report: () => showReport(),
  zoom: el => zoomBy(el.dataset.arg === 'in' ? 1.3 : 1 / 1.3),
  fit: () => fitView(),
  legend: () => $('legend').classList.toggle('collapsed'),
  closeside: () => closeSide(),
  explain: () => doExplain(),
  clearpath: () => clearPath(),
  startpath: () => startPath(),
  runmapping: () => runMapping(),
  picker: () => openPicker(),
  history: () => loadHistory(),
  copy: el => copyText($(el.dataset.arg).textContent, t(el.dataset.msg)),
  qr: () => toggleQr(),
  test: () => testConnect(),
  client: el => pickClient(el.dataset.arg),
  revokeall: () => revokeAllSessions(),
  sessions: () => loadConnSessions(),
  health: () => loadHealth(),
  backup: () => runBackup(),
  audit: () => loadAudit(),
  hideerr: () => hideError(),
  moretab: el => { $('moredlg').close(); tab(el.dataset.arg); },
  moretour: () => { $('moredlg').close(); startTour(); },
  closedlg: el => $(el.dataset.arg).close(),
  pickok: () => pickCurrent(),
  saveignore: () => saveIgnore(),
  confirm: el => $('confirmdlg').close(el.dataset.arg),
  tourend: () => endTour(),
  tourstep: el => tourStep(+el.dataset.arg),
  'twofa-setup': () => setup2fa(),
  'twofa-copy': () => copyRecovery(),
  'twofa-done': () => loadTwoFA(),
  backupsetup: () => setupBackup(),
  backupremove: () => removeBackupTarget(),
  backupconfirmed: () => { loadBackup(); runBackup(); },
};

const FORMULARE = {
  login: e => doLogin(e),
  ask: e => sendAsk(e),
  secret: e => addSecret(e),
  apikey: e => saveApiKey(e),
  mapping: e => saveMapping(e),
  token: e => genToken(e),
  'twofa-disable': e => disable2fa(e),
  'twofa-enable': e => enable2fa(e),
  password: e => changePassword(e),
  backuptarget: e => saveBackupTarget(e),
};

const WECHSEL = {
  loadgraph: () => loadGraph(),
  maptoggle: el => toggleMapping(el.checked),
  backend: () => backendChanged(),
  model: () => modelChanged(),
  gitsource: () => gitTokenSourceChanged(),
};

document.addEventListener('click', e => {
  const el = e.target.closest('[data-act]');
  if (!el) return;
  const fn = AKTIONEN[el.dataset.act];
  if (!fn) return;
  if (el.tagName === 'A') e.preventDefault();   // Sprung-Links (#secrets) nicht ausführen
  fn(el, e);
});
document.addEventListener('submit', e => {
  const fn = e.target.dataset && FORMULARE[e.target.dataset.form];
  if (fn) fn(e);                                 // die Handler rufen selbst preventDefault()
});
document.addEventListener('change', e => {
  const el = e.target.closest('[data-change]');
  const fn = el && WECHSEL[el.dataset.change];
  if (fn) fn(el, e);
});

/* Sonderfälle mit Ereignissen jenseits von click/submit/change: direkt binden.
   Das Skript lädt am Ende von <body>, die Elemente existieren also schon. */
const suchfeld = $('search');
suchfeld.addEventListener('input', () => searchChanged(suchfeld.value));
suchfeld.addEventListener('keydown', e => searchKey(e));
suchfeld.addEventListener('focus', () => searchChanged(suchfeld.value));
suchfeld.addEventListener('blur', () => hideSearchDropSoon());
const regler = $('limit');
regler.addEventListener('input', () => {
  $('limlbl').textContent = (+regler.value >= +regler.max) ? t('Alle') : regler.value;
  limitChanged();
});
