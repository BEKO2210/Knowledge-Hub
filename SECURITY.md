# Security

Knowledge Hub holds two things worth stealing: knowledge about your source code, and your API
keys. It is built accordingly. This document says what it protects against, what it does *not*,
and how to report a hole.

## Reporting a vulnerability

**Please do not open a public issue.**

Use GitHub's private channel: **Security → Report a vulnerability** on this repository. That
report is visible only to the maintainer.

Tell us what you found, how to reproduce it, and what an attacker could do with it. Anything that
exposes a vault or bypasses authentication is treated as urgent.

## What the hub does

**The vault.** Secrets are encrypted with AES-256-GCM under a random 256-bit master key. That
master key never touches the disk in the clear — it is wrapped twice:

- with `scrypt(your password)`, and
- optionally with a machine key from the environment (`VAULT_KEY`), so the hub can unlock itself
  after a reboot and the nightly job can fetch its own API key at 03:30.

Turn the machine wrap off for maximum security: the vault then stays locked after every restart
until a human signs in. The trade-off is that unattended jobs can no longer read keys.

Changing your password only re-wraps the master key. It never re-encrypts the secrets — so a
password change cannot lose them.

**Authentication.** Two ways in: a long random static token, compared in constant time; or OAuth
2.1 with PKCE (S256 mandatory) and dynamic client registration. Authorisation codes are
single-use and expire after five minutes. Access tokens are persisted **only as SHA-256 hashes** —
an attacker who reads the state file learns nothing usable. Every session is listed in the UI and
can be revoked instantly.

**Brute force.** Five failed logins in fifteen minutes block the IP, and the block is persisted —
it survives a restart of the service, so an attacker cannot wait for a reboot. Failures and blocks
go to the audit log, and the diagnostics tab raises them.

**Two-factor.** Optional TOTP with recovery codes. Disabling it requires a current code, so a
hijacked browser session cannot quietly switch it off.

**The browser.** `Content-Security-Policy: default-src 'self'` — no CDN, no external font, no
telemetry. The interface ships its own copy of every asset, so nothing about your usage leaves the
machine. Plus `X-Frame-Options: DENY`, `X-Content-Type-Options: nosniff`,
`Referrer-Policy: no-referrer`, and HSTS as soon as the hub is reachable over HTTPS. API responses
are `no-store`, so secrets never land in a browser cache or in the back button.

**Secrets in transit.** The list endpoint returns names only, never values. A value is fetched only
on an explicit request, and that fetch is written to the audit log together with the client that
asked for it.

**Errors.** An unexpected failure returns a reference number — never a stack trace. The trace goes
to a local error log; nothing about the hub's internals reaches the caller.

**Backups.** Encrypted with a separate passphrase (`BACKUP_PASSPHRASE`) before they leave the
machine. Verify one at any time with `python backup.py verify <file>`.

## What the hub does not do

- **It does not protect you from your own machine.** Anyone who can read
  `~/.config/knowledge-mcp/env` can decrypt the vault. Keep that file at mode 600 and keep your
  user account secure.
- **It does not encrypt secrets in memory.** While the vault is unlocked, the master key lives in
  the process. Root on the host can read it.
- **It is not multi-tenant.** One hub, one owner. There are no per-user permissions.
- **It has not been independently audited.** It is written carefully and it is tested — 78
  automated tests, including the attack paths above — but no third party has reviewed it. Judge it
  accordingly.

## Deployment advice

- Keep it bound to `127.0.0.1` (the default) and put a TLS-terminating tunnel or reverse proxy in
  front of it. **Never serve it over plain HTTP**: the bearer token is the only thing between the
  internet and your vault.
- Set `server.public_url` to your HTTPS address so HSTS switches on.
- Turn on two-factor if the hub is reachable from the internet.
- Keep an off-site backup — and restore it once. A backup you have never restored is a rumour.
