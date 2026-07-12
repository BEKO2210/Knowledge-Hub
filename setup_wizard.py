"""Erststart-Wizard des Knowledge Hub.

Zeigt sich nur, solange das System NICHT eingerichtet ist (env-Datei ohne die
drei Pflicht-Secrets). Er erzeugt den Vault-Schlüssel und das MCP-Token
automatisch, nimmt ein Zugangspasswort + Branding entgegen und schreibt env
(0600) + config.yaml. Danach sperren sich die Setup-Endpunkte selbst —
niemand kann über /ui/setup ein bereits eingerichtetes System übernehmen.

Design (nach First-Run-UX-Best-Practices): so wenige Schritte wie möglich,
schnell zum ersten Erfolg, Sicherheitskritisches (Vault-Key sichern!) klar
kommuniziert.
"""

from __future__ import annotations

import base64
import os
import re
import secrets
import shutil
import subprocess
from pathlib import Path

from starlette.requests import Request
from starlette.responses import HTMLResponse, JSONResponse

import config

ENV_FILE = Path(os.environ.get("KMCP_ENV_FILE", str(Path.home() / ".config" / "knowledge-mcp" / "env")))
# Seit Vault v2 steht das Zugangspasswort NICHT mehr in der env-Datei — es verpackt
# den Hauptschlüssel im Vault. Die env braucht nur noch Schlüssel und Token.
REQUIRED_KEYS = ("VAULT_KEY", "MCP_TOKEN")


def _parse_env(text: str) -> dict[str, str]:
    out: dict[str, str] = {}
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, _, v = line.partition("=")
        out[k.strip()] = v.strip()
    return out


def is_configured() -> bool:
    """True, sobald das System eingerichtet ist.

    Zwei Bedingungen — beide müssen stimmen, sonst könnte ein halb eingerichtetes
    System vom Wizard überschrieben werden (und der Vault wäre unerreichbar):
      1. env enthält Schlüssel und Token,
      2. es gibt einen Vault (dort liegt das Passwort als Verpackung).
    """
    if not ENV_FILE.exists():
        return False
    env = _parse_env(ENV_FILE.read_text())
    if not all(env.get(k) for k in REQUIRED_KEYS):
        return False
    import vault as _vault

    return _vault.VAULT_PATH.exists()


def _write_env(values: dict[str, str]) -> None:
    ENV_FILE.parent.mkdir(parents=True, exist_ok=True)
    existing = _parse_env(ENV_FILE.read_text()) if ENV_FILE.exists() else {}
    existing.update(values)
    body = "".join(f"{k}={v}\n" for k, v in existing.items())
    ENV_FILE.write_text(body)
    ENV_FILE.chmod(0o600)


def _activate(vault_key: str, mcp_token: str, password: str) -> None:
    """Neue Secrets sofort im laufenden Prozess wirksam machen.

    Ohne das wäre nach dem Wizard ein Dienst-Neustart nötig — der unter systemd
    funktioniert, im Container aber nicht. So ist der Hub direkt einsatzbereit.
    """
    import oauth as _oauth
    import server as _server

    os.environ["VAULT_KEY"] = vault_key  # vault liest den Key bei jedem Zugriff neu
    os.environ["MCP_TOKEN"] = mcp_token
    os.environ["OAUTH_PASSWORD"] = password
    _oauth.OAUTH_PASSWORD = password  # Modul-Konstanten nachziehen
    _server.MCP_TOKEN = mcp_token


async def setup_status(request: Request) -> JSONResponse:
    return JSONResponse({"configured": is_configured()})


_setup_attempts: list[float] = []


async def setup_submit(request: Request) -> JSONResponse:
    if is_configured():
        return JSONResponse({"error": "System ist bereits eingerichtet"}, status_code=409)

    # NOTBREMSE: Existiert bereits ein Vault, wird hier NIEMALS eingerichtet — auch wenn
    # is_configured() aus irgendeinem Grund False liefert (z. B. beschädigte env-Datei).
    # Sonst würde der Wizard einen leeren Vault über die vorhandenen Secrets schreiben.
    import vault as _vault

    if _vault.VAULT_PATH.exists():
        return JSONResponse(
            {
                "error": "Es existiert bereits ein Vault mit Secrets. Die Einrichtung würde ihn "
                "überschreiben und wurde deshalb abgebrochen. Wenn die env-Datei fehlt, "
                "spiele sie aus deiner Sicherung zurück (backup.py restore) — "
                "nicht neu einrichten!",
            },
            status_code=409,
        )

    # Bremse gegen automatisierte Einrichtungs-Versuche (gemeinsamer Zähler).
    import ratelimit

    ip = request.headers.get("cf-connecting-ip") or (request.client.host if request.client else "?")
    if not ratelimit.check("setup", ip):
        return JSONResponse({"error": "Zu viele Versuche — bitte kurz warten."}, status_code=429)
    ratelimit.record_failure("setup", ip)  # jeder Setup-Aufruf zählt (seltenes Ereignis)

    try:
        body = await request.json()
    except Exception:
        return JSONResponse({"error": "bad request"}, status_code=400)

    password = str(body.get("password", ""))
    if len(password) < 8:
        return JSONResponse({"error": "Das Passwort muss mindestens 8 Zeichen haben."}, status_code=400)

    name = str(body.get("name", "")).strip() or "Knowledge Hub"
    public_url = str(body.get("public_url", "")).strip() or "http://127.0.0.1:8300"
    if not re.match(r"^https?://", public_url):
        return JSONResponse(
            {"error": "Öffentliche URL muss mit http:// oder https:// beginnen."}, status_code=400
        )

    vault_key = base64.b64encode(secrets.token_bytes(32)).decode()
    mcp_token = secrets.token_urlsafe(32)

    # VAULT_KEY dient nur noch der Auto-Entsperrung (unbeaufsichtigter Betrieb).
    # Das Passwort wird NICHT gespeichert — es verpackt den Hauptschlüssel im Vault.
    _write_env({"VAULT_KEY": vault_key, "MCP_TOKEN": mcp_token})
    _activate(vault_key, mcp_token, password)

    import vault as _vault

    _vault.init(password)  # legt Vault v2 an: Passwort- + Env-Verpackung

    # config.yaml um Branding/URL ergänzen, Rest unangetastet lassen
    cfg = {}
    if config.CONFIG_PATH.exists():
        import yaml

        cfg = yaml.safe_load(config.CONFIG_PATH.read_text()) or {}
    cfg.setdefault("server", {})["public_url"] = public_url
    cfg.setdefault("branding", {})["name"] = name
    config.CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    import yaml

    config.CONFIG_PATH.write_text(
        "# Knowledge Hub — zentrale Konfiguration\n"
        "# Secrets gehören NICHT hierher, sondern in ./env.\n\n"
        + yaml.safe_dump(cfg, allow_unicode=True, sort_keys=False)
    )

    return JSONResponse(
        {
            "ok": True,
            "vault_key": vault_key,
            "mcp_token": mcp_token,
            "mcp_url": public_url.rstrip("/") + "/mcp",
        }
    )


async def setup_restart(request: Request) -> JSONResponse:
    """Optionaler Dienst-Neustart nach dem Wizard.

    Die Secrets sind dank _activate() bereits aktiv — der Neustart ist nur Kosmetik
    (sauberer Zustand). Fehlt systemd (z. B. im Container), passiert einfach nichts.
    """
    if not is_configured():
        return JSONResponse({"error": "noch nicht eingerichtet"}, status_code=400)
    if shutil.which("systemctl"):
        subprocess.Popen(  # noqa: S603,S607 - fester Unit-Name, abgekoppelter Neustart
            ["bash", "-c", "sleep 1; systemctl --user restart knowledge-mcp || true"],
            start_new_session=True,
        )
    return JSONResponse({"ok": True})


async def wizard_page(request: Request) -> HTMLResponse:
    import ui

    return HTMLResponse(ui.render(WIZARD_HTML), headers={"Content-Security-Policy": WIZARD_CSP})


WIZARD_HTML = r"""<!doctype html>
<html lang="de"><head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">
<meta name="theme-color" content="#0f172a">
<link rel="icon" type="image/png" href="/ui/static/favicon.png">
<title>Einrichtung — __BRAND__</title>
<style>
:root{--bg:#0f172a;--surface:#1e293b;--surface2:#273449;--line:#334155;--line2:#475569;
--txt:#f8fafc;--mut:#94a3b8;--mut2:#64748b;--acc:#22c55e;--blue:#60a5fa;--red:#f87171;--amber:#fbbf24;
--r-sm:8px;--r-md:12px;--r-lg:16px;--dur:220ms;--ease:cubic-bezier(.2,.8,.3,1)}
@media(prefers-reduced-motion:reduce){:root{--dur:1ms}}
*{box-sizing:border-box;-webkit-tap-highlight-color:transparent}
body{margin:0;min-height:100dvh;font-family:system-ui,-apple-system,"Segoe UI",Roboto,sans-serif;
background:radial-gradient(1200px 700px at 50% -15%,#16233c,var(--bg)) fixed;color:var(--txt);
display:flex;align-items:center;justify-content:center;padding:max(20px,env(safe-area-inset-top)) 20px}
.mono{font-family:ui-monospace,SFMono-Regular,Menlo,Consolas,monospace}
svg.ic{width:20px;height:20px;stroke:currentColor;fill:none;stroke-width:2;stroke-linecap:round;stroke-linejoin:round;flex:none}
.card{background:var(--surface);border:1px solid var(--line);border-radius:var(--r-lg);
width:min(100%,30rem);padding:clamp(1.5rem,5vw,2.5rem);box-shadow:0 24px 70px rgba(0,0,0,.45)}
.brand{display:flex;align-items:center;gap:12px;margin-bottom:1.5rem}
.brand img{width:46px;height:46px;border-radius:12px}
.brand b{font-size:1.15rem}.brand b em{font-style:normal;color:var(--acc)}
/* progress */
.steps{display:flex;gap:8px;margin-bottom:1.75rem}
.steps .dot{height:5px;flex:1;border-radius:999px;background:var(--line);transition:background var(--dur)}
.steps .dot.on{background:var(--acc)}
.steps .dot.done{background:var(--acc-dim,#16a34a)}
.step{display:none;animation:fade var(--dur) var(--ease)}
.step.on{display:block}
@keyframes fade{from{opacity:0;transform:translateY(6px)}}
h1{font-size:1.4rem;margin:0 0 .4rem}
p.lead{color:var(--mut);margin:0 0 1.5rem;line-height:1.55}
label{display:block;font-size:.82rem;color:var(--mut);margin:1rem 0 .4rem}
input{width:100%;font-size:16px;background:var(--bg);border:1px solid var(--line2);color:var(--txt);
border-radius:var(--r-sm);padding:12px 14px;min-height:48px}
input:focus-visible{outline:2px solid var(--blue);outline-offset:2px}
.pwwrap{position:relative}.pwwrap input{padding-right:52px}
.pwwrap button.eye{position:absolute;right:4px;top:50%;transform:translateY(-50%);background:none;border:0;
color:var(--mut);min-height:44px;min-width:44px;display:flex;align-items:center;justify-content:center;cursor:pointer}
.strength{height:5px;border-radius:999px;background:var(--line);margin-top:.5rem;overflow:hidden}
.strength i{display:block;height:100%;width:0;transition:width var(--dur),background var(--dur)}
.hint{font-size:.78rem;color:var(--mut2);margin-top:.4rem}
.err{color:var(--red);font-size:.85rem;min-height:1.1em;margin:.6rem 0 0}
.btn{width:100%;margin-top:1.75rem;min-height:50px;border:0;border-radius:var(--r-sm);background:var(--acc);
color:#052e16;font-weight:700;font-size:1rem;cursor:pointer;display:flex;align-items:center;justify-content:center;gap:8px;
transition:transform var(--dur) var(--ease),opacity var(--dur)}
.btn:active{transform:scale(.98)}.btn[disabled]{opacity:.5;cursor:not-allowed}
.btn.ghost{background:var(--surface2);color:var(--txt)}
.feat{display:flex;gap:12px;align-items:flex-start;margin:.9rem 0}
.feat svg{color:var(--acc);margin-top:2px}
.feat b{display:block}.feat span{color:var(--mut);font-size:.86rem}
.keybox{background:var(--bg);border:1px solid var(--line2);border-radius:var(--r-sm);padding:12px 14px;margin-top:.5rem}
.keybox .k{font-size:.72rem;color:var(--mut2);margin-bottom:3px}
.keybox .v{font-family:ui-monospace,Menlo,monospace;font-size:.82rem;color:var(--acc);word-break:break-all}
.warn{display:flex;gap:10px;background:rgba(251,191,36,.1);border:1px solid rgba(251,191,36,.3);
border-radius:var(--r-sm);padding:12px 14px;margin-top:1.25rem;font-size:.84rem;line-height:1.5}
.warn svg{color:var(--amber);flex:none;margin-top:1px}
.copybtn{background:var(--surface2);border:1px solid var(--line2);color:var(--txt);border-radius:6px;
padding:6px 10px;font-size:.78rem;cursor:pointer;display:inline-flex;gap:6px;align-items:center;margin-top:.75rem}
</style></head><body>

<svg style="display:none"><defs>
<g id="i-eye"><path d="M2 12s3.5-7 10-7 10 7 10 7-3.5 7-10 7-10-7-10-7z"/><circle cx="12" cy="12" r="3"/></g>
<g id="i-eyeoff"><path d="M17.94 17.94A10.07 10.07 0 0 1 12 20c-7 0-11-8-11-8a18.45 18.45 0 0 1 5.06-5.94M9.9 4.24A9.12 9.12 0 0 1 12 4c7 0 11 8 11 8a18.5 18.5 0 0 1-2.16 3.19m-6.72-1.07a3 3 0 1 1-4.24-4.24"/><path d="m1 1 22 22"/></g>
<g id="i-graph"><circle cx="18" cy="5" r="3"/><circle cx="6" cy="12" r="3"/><circle cx="18" cy="19" r="3"/><path d="m8.59 13.51 6.83 3.98M15.41 6.51l-6.82 3.98"/></g>
<g id="i-key"><path d="M2.586 17.414A2 2 0 0 0 2 18.828V21a1 1 0 0 0 1 1h3a1 1 0 0 0 1-1v-1a1 1 0 0 1 1-1h1a1 1 0 0 0 1-1v-1a1 1 0 0 1 1-1h.172a2 2 0 0 0 1.414-.586l.814-.814a6.5 6.5 0 1 0-4-4z"/></g>
<g id="i-shield"><path d="M20 13c0 5-3.5 7.5-7.66 8.95a1 1 0 0 1-.67-.01C7.5 20.5 4 18 4 13V6a1 1 0 0 1 1-1c2 0 4.5-1.2 6.24-2.72a1.17 1.17 0 0 1 1.52 0C14.51 3.81 17 5 19 5a1 1 0 0 1 1 1z"/><path d="m9 12 2 2 4-4"/></g>
<g id="i-check"><path d="M20 6 9 17l-5-5"/></g>
<g id="i-copy"><rect x="9" y="9" width="13" height="13" rx="2"/><path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"/></g>
<g id="i-alert"><path d="m21.73 18-8-14a2 2 0 0 0-3.48 0l-8 14A2 2 0 0 0 4 21h16a2 2 0 0 0 1.73-3z"/><path d="M12 9v4M12 17h.01"/></g>
<g id="i-arrow"><path d="M5 12h14M12 5l7 7-7 7"/></g>
<g id="i-spark"><path d="M9.94 15.5A2 2 0 0 0 8.5 14.06l-6.14-1.58a.5.5 0 0 1 0-.96L8.5 9.94A2 2 0 0 0 9.94 8.5l1.58-6.14a.5.5 0 0 1 .96 0L14.06 8.5A2 2 0 0 0 15.5 9.94l6.14 1.58a.5.5 0 0 1 0 .96L15.5 14.06a2 2 0 0 0-1.44 1.44l-1.58 6.14a.5.5 0 0 1-.96 0z"/></g>
</defs></svg>

<div class="card">
  <div class="brand"><img src="/ui/static/icon-192.png" alt="">
    <b>__BRAND_HTML__</b></div>
  <div class="steps"><span class="dot on"></span><span class="dot"></span><span class="dot"></span></div>

  <!-- Schritt 1: Willkommen -->
  <section class="step on" data-step="0">
    <h1>Willkommen</h1>
    <p class="lead">Dein privater Wissens-Hub — Graphen aller Projekte und ein verschlüsselter
      Secrets-Vault, erreichbar von überall. Die Einrichtung dauert unter einer Minute.</p>
    <div class="feat"><svg class="ic" viewBox="0 0 24 24"><use href="#i-graph"/></svg>
      <div><b>Wissensgraphen</b><span>Deine Projekte als durchsuchbare, interaktive Karte.</span></div></div>
    <div class="feat"><svg class="ic" viewBox="0 0 24 24"><use href="#i-key"/></svg>
      <div><b>Secrets-Vault</b><span>API-Keys & Passwörter AES-256-verschlüsselt an einem Ort.</span></div></div>
    <div class="feat"><svg class="ic" viewBox="0 0 24 24"><use href="#i-spark"/></svg>
      <div><b>Automatisches Mapping</b><span>Nächtlich hält sich dein Wissen selbst aktuell.</span></div></div>
    <button class="btn" id="startbtn">Los geht's<svg class="ic" viewBox="0 0 24 24"><use href="#i-arrow"/></svg></button>
  </section>

  <!-- Schritt 2: Passwort + Branding -->
  <section class="step" data-step="1">
    <h1>Zugang festlegen</h1>
    <p class="lead">Mit diesem Passwort meldest du dich künftig an — an der Weboberfläche und
      beim Verbinden von KI-Clients.</p>
    <label for="pw">Zugangspasswort</label>
    <div class="pwwrap">
      <input type="password" id="pw" autocomplete="new-password" placeholder="mindestens 8 Zeichen"
             autofocus>
      <button type="button" class="eye" id="pweye" aria-label="Passwort anzeigen">
        <svg class="ic" viewBox="0 0 24 24"><use href="#i-eye"/></svg></button>
    </div>
    <div class="strength"><i id="strbar"></i></div>
    <div class="hint" id="strhint">Tipp: mehrere Wörter oder ein Satz sind sicherer als Sonderzeichen.</div>
    <label for="pw2">Passwort wiederholen</label>
    <input type="password" id="pw2" autocomplete="new-password" placeholder="zur Bestätigung">
    <label for="hubname">Name des Hubs <span style="color:var(--mut2)">(optional)</span></label>
    <input type="text" id="hubname" value="Knowledge Hub" maxlength="40">
    <p class="err" id="err2" role="alert"></p>
    <button class="btn" id="next2" disabled>
      Einrichten & Schlüssel erzeugen<svg class="ic" viewBox="0 0 24 24"><use href="#i-arrow"/></svg></button>
  </section>

  <!-- Schritt 3: Fertig -->
  <section class="step" data-step="2">
    <h1><svg class="ic" style="width:26px;height:26px;color:var(--acc);vertical-align:-4px" viewBox="0 0 24 24"><use href="#i-shield"/></svg> Fast fertig</h1>
    <p class="lead">Dein Vault-Schlüssel und dein API-Token wurden erzeugt und sicher gespeichert.</p>
    <div class="keybox"><div class="k">VAULT-SCHLÜSSEL (entschlüsselt deinen Vault)</div><div class="v" id="vk"></div></div>
    <div class="keybox"><div class="k">MCP-TOKEN (für Nicht-Browser-Clients)</div><div class="v" id="mt"></div></div>
    <button class="copybtn" id="copybtn"><svg class="ic" style="width:15px;height:15px" viewBox="0 0 24 24"><use href="#i-copy"/></svg>Beide kopieren</button>
    <div class="warn"><svg class="ic" viewBox="0 0 24 24"><use href="#i-alert"/></svg>
      <div><b>Sichere den Vault-Schlüssel jetzt.</b> Ohne ihn sind gespeicherte Secrets unwiederbringlich verloren.
      Er liegt auf dem Server, aber ein Offline-Backup schützt zusätzlich.</div></div>
    <button class="btn" id="finishbtn">Server starten & anmelden<svg class="ic" viewBox="0 0 24 24"><use href="#i-arrow"/></svg></button>
    <p class="hint" id="restarthint" style="text-align:center;margin-top:1rem"></p>
  </section>
</div>

<script>
'use strict';
const $ = id => document.getElementById(id);
let step = 0;
function go(n) {
  step = n;
  document.querySelectorAll('.step').forEach(s => s.classList.toggle('on', +s.dataset.step === n));
  document.querySelectorAll('.steps .dot').forEach((d, i) => {
    d.classList.toggle('on', i === n);
    d.classList.toggle('done', i < n);
  });
}
function eye(id, btn) {
  const inp = $(id), show = inp.type === 'password';
  inp.type = show ? 'text' : 'password';
  btn.innerHTML = `<svg class="ic" viewBox="0 0 24 24"><use href="#i-${show ? 'eyeoff' : 'eye'}"/></svg>`;
}
function scorePw(p) {
  // Länge zählt am meisten (lange Passphrasen schlagen kurze Sonderzeichen-Wüsten)
  let s = 0;
  if (p.length >= 8) s++;
  if (p.length >= 12) s++;
  if (p.length >= 20) s++;                              // lange Passphrase = stark
  if (/[a-z]/.test(p) && /[A-Z]/.test(p) || /\d/.test(p) || /[^\w]/.test(p)) s++;
  return Math.min(s, 4);
}
function strength() {
  const p = $('pw').value, p2 = $('pw2').value;
  const s = scorePw(p);
  const cols = ['#f87171', '#fbbf24', '#fbbf24', '#22c55e'];
  const labels = ['zu kurz', 'schwach', 'ok', 'gut', 'stark'];
  $('strbar').style.width = (p ? (s / 4 * 100) : 0) + '%';
  $('strbar').style.background = cols[Math.max(0, s - 1)] || '#f87171';
  $('strhint').textContent = p ? 'Stärke: ' + labels[s] : 'Tipp: mehrere Wörter sind sicherer als Sonderzeichen.';
  const match = p.length >= 8 && p === p2;
  $('err2').textContent = (p2 && p !== p2) ? 'Die Passwörter stimmen nicht überein.' : '';
  $('next2').disabled = !match;
}
async function submitSetup() {
  const btn = $('next2');
  btn.disabled = true; btn.textContent = 'Wird eingerichtet…';
  try {
    const r = await fetch('/ui/setup/submit', {method: 'POST', headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({password: $('pw').value, name: $('hubname').value, public_url: location.origin})});
    const j = await r.json();
    if (!r.ok) { $('err2').textContent = j.error || 'Fehler bei der Einrichtung.'; btn.disabled = false;
      btn.innerHTML = 'Einrichten & Schlüssel erzeugen<svg class="ic" viewBox="0 0 24 24"><use href="#i-arrow"/></svg>'; return; }
    $('vk').textContent = j.vault_key;
    $('mt').textContent = j.mcp_token;
    go(2);
  } catch { $('err2').textContent = 'Server nicht erreichbar.'; btn.disabled = false; }
}
function copyKeys() {
  navigator.clipboard.writeText('VAULT_KEY=' + $('vk').textContent + '\nMCP_TOKEN=' + $('mt').textContent);
}
async function finish() {
  const btn = $('finishbtn');
  btn.disabled = true; btn.textContent = 'Server startet…';
  $('restarthint').textContent = 'Einen Moment, der Dienst wird neu gestartet…';
  try { await fetch('/ui/setup/restart', {method: 'POST'}); } catch {}
  // auf Wiedererreichbarkeit warten, dann zur Anmeldung
  let tries = 0;
  const poll = setInterval(async () => {
    tries++;
    try {
      const s = await (await fetch('/ui/setup/status', {cache: 'no-store'})).json();
      if (s.configured) { clearInterval(poll); location.href = '/ui'; }
    } catch {}
    if (tries > 40) { clearInterval(poll); location.href = '/ui'; }
  }, 1000);
}

// Ereignisse hier statt als onclick-Attribute: Die CSP erlaubt nur diesen einen
// Skriptblock (per Hash) — Inline-Handler im Markup führt der Browser nicht aus.
$('startbtn').addEventListener('click', () => go(1));
$('pweye').addEventListener('click', e => eye('pw', e.currentTarget));
$('pw').addEventListener('input', strength);
$('pw2').addEventListener('input', strength);
$('next2').addEventListener('click', submitSetup);
$('copybtn').addEventListener('click', copyKeys);
$('finishbtn').addEventListener('click', finish);
</script></body></html>
"""

# CSP-Hash über den einen Skriptblock des Wizards. Die Oberfläche verbietet Inline-
# Skripte (script-src 'self'); der Wizard ist aber eine einzelne, in sich geschlossene
# Seite ohne eigene Asset-Dateien. Der Hash erlaubt GENAU diesen Block — würde ihn
# jemand unterwegs verändern, führt der Browser ihn nicht mehr aus.
# Wichtig: ui.render() ersetzt __BRAND__/__V__ nur im Markup, nie im Skriptblock —
# sonst stimmte der Hash nicht mehr (test_sicherheit prüft das).
import hashlib as _hashlib  # noqa: E402 - direkt beim Verbraucher

_SCRIPT = re.search(r"<script>(.*)</script>", WIZARD_HTML, re.S).group(1)
WIZARD_SCRIPT_HASH = "sha256-" + base64.b64encode(_hashlib.sha256(_SCRIPT.encode()).digest()).decode()
WIZARD_CSP = (
    f"default-src 'self'; script-src '{WIZARD_SCRIPT_HASH}'; "
    "style-src 'self' 'unsafe-inline'; img-src 'self' data:; "
    "connect-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'"
)
