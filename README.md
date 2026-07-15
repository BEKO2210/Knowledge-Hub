<div align="center">

<img src="docs/images/icon.png" width="112" height="112" alt="Knowledge Hub logo" />

# Knowledge Hub

### Your knowledge. Your server. Your graph.

**Every project you own becomes a searchable knowledge graph. Your API keys live in an
encrypted vault. Claude — or any MCP client — gets both, and nobody else gets anything.**

[![CI](https://github.com/BEKO2210/Knowledge-Hub/actions/workflows/ci.yml/badge.svg)](https://github.com/BEKO2210/Knowledge-Hub/actions/workflows/ci.yml)
[![Tests](https://img.shields.io/badge/tests-366%20passing-22c55e)](tests/)
[![Python 3.12](https://img.shields.io/badge/Python-3.12-3776AB?logo=python&logoColor=white)](https://www.python.org/)
[![MCP](https://img.shields.io/badge/MCP-OAuth_2.1%20%2B%20PKCE-8b5cf6)](https://modelcontextprotocol.io)
[![Zero downtime](https://img.shields.io/badge/deploys-blue--green%2C%20zero%20downtime-1baf7a)](#architecture)
[![License: AGPL v3](https://img.shields.io/badge/License-AGPL_v3-blue.svg)](LICENSE)

<img src="docs/images/graph-dark.png" alt="The graph view: a project's knowledge graph with clusters, a selected node and its neighbours" width="100%" />

**[Website](https://hub.it-handwerk-stuttgart.de)** ·
**[Live benchmarks](https://hub.it-handwerk-stuttgart.de/benchmarks.html)** ·
**[Wiki](https://github.com/BEKO2210/Knowledge-Hub/wiki)**

</div>

---

## Why this exists

Every AI coding assistant has the same two blind spots.

**It doesn't know your codebase.** You paste files into the context window one at a time and hope
you picked the right ones. Knowledge Hub maps each project into a graph of concepts, modules and
documents — clusters, hub nodes, relations — and lets the assistant *traverse* it. Ask "how does a
refund actually reach the ledger?" and it walks the graph instead of guessing.

**It can't hold your secrets.** So the API key gets pasted into the chat and lives in a transcript
forever. Knowledge Hub keeps keys in an encrypted vault and gives the assistant a tool to fetch one
*when a task genuinely needs it* — and every access lands in an audit log.

It runs on **your** machine. No third party ever sees your code or your keys.

---

## What you get

|  |  |
|---|---|
| 🕸️ **A graph per project** | Code, Compose files, configs, docs and notes become nodes with hard facts — ports, paths, hosts, decisions. Interactive viewer with clusters, hub nodes and shortest paths. |
| 🎯 **Hybrid retrieval** | `graph_query` embeds your question with a local multilingual model (CPU, offline) and answers with graph structure *plus* the most relevant raw file excerpts. Benchmarked at **85 % hit rate** where lexical graph lookup scored 58 % — measured, not claimed ([benchmarks](#benchmarks)). |
| 🔐 **Encrypted vault** | AES-256-GCM with a double-wrapped master key: survives unattended reboots, stays useless on disk, never re-encrypts on password change. Every access audited. |
| 🤖 **A real MCP server** | Streamable HTTP, OAuth 2.1 + PKCE with dynamic client registration. Connect Claude with one URL — the hub even hands its own logo to the client during the handshake (`Implementation.icons`). |
| 🌙 **Nightly mapping — accountable** | A timer re-maps every project while you sleep, incrementally. Every run writes a **machine-readable run record** (per project: nodes, edges, communities, delta, build ID, status) — partial failures stay visible per project instead of silently vanishing. |
| 🗂️ **Graph inventory** | Every visible graph belongs to exactly one registered project — active or *archived with documented origin*. Orphans are flagged for a decision (register / archive / remove), never silently listed. Removal cascades through graph, report, viewer, indexes and saved answers; source folders are never touched. |
| 🔁 **Zero-downtime deploys** | Blue-green slots behind a systemd socket: health-gated switches, a watch window, automatic fallback and a warm previous release. Updates land in under a second of cutover. |
| 📱 **Works on a phone** | Installable PWA, bottom navigation, light and dark — the whole hub in your pocket. |
| 🛡️ **Built to be attacked** | Rate-limited login that survives restarts, optional TOTP, hashed tokens, strict `default-src 'self'` CSP, acknowledgeable error diagnostics, encrypted off-site backups. |

---

## Screenshots

<table>
<tr>
<td width="50%"><img src="docs/images/graph-light.png" alt="Graph view in light mode" /><br /><sub><b>Explore</b> — clusters, hub nodes, neighbours, shortest paths.</sub></td>
<td width="50%"><img src="docs/images/secrets-dark.png" alt="The secrets vault" /><br /><sub><b>Vault</b> — a value is never rendered until you ask for it.</sub></td>
</tr>
<tr>
<td><img src="docs/images/mapping-dark.png" alt="Nightly mapping with run history" /><br /><sub><b>Mapping</b> — every run with cost, duration, per-project results and status.</sub></td>
<td><img src="docs/images/health-dark.png" alt="Diagnostics" /><br /><sub><b>Diagnostics</b> — every check says what to do if it isn't green.</sub></td>
</tr>
<tr>
<td><img src="docs/images/connect-dark.png" alt="Connecting an AI client" /><br /><sub><b>Connect</b> — pair a device by QR code, then test the connection for real.</sub></td>
<td align="center"><img src="docs/images/mobile-graph.png" alt="The mobile interface" width="230" /><br /><sub><b>Phone</b> — installable, swipeable, yours.</sub></td>
</tr>
</table>

---

## Install

**Requirements:** Linux, Python 3.12+, and [graphifyy](https://pypi.org/project/graphifyy/) to build
the graphs — a third-party graph engine ([MIT, by Safi Shamsi](https://github.com/safishamsi/graphify)).
Knowledge Hub is the server, vault, scheduler, retrieval engine and UI *around* it.

```bash
git clone https://github.com/BEKO2210/Knowledge-Hub.git
cd Knowledge-Hub
./install.sh
```

The installer creates a virtualenv, generates your keys, installs a systemd user service plus the
nightly timer, and opens a **setup wizard** in your browser. It asks for a password, which projects
to map, and which AI provider to use for the semantic pass. On its first query the hybrid engine
downloads a local embedding model once (~470 MB); after that, retrieval is fully offline.

<details>
<summary><b>Docker instead</b></summary>

```bash
cp config.example.yaml config.yaml   # point knowledge_root at your projects
docker compose up -d
```

The compose file mounts your projects read-only and keeps the vault in a named volume.
</details>

<details>
<summary><b>Reaching it from outside (optional)</b></summary>

The hub binds to `127.0.0.1` on purpose. To reach it from your phone, or to connect a cloud AI
client, put it behind a tunnel that terminates TLS — a
[Cloudflare Tunnel](https://developers.cloudflare.com/cloudflare-one/connections/connect-networks/)
works well and opens no ports. Set `server.public_url` to the resulting HTTPS address; the hub
turns on HSTS automatically once it sees `https://`.

**Never expose it over plain HTTP.** The bearer token is the only thing between the internet and
your vault.
</details>

---

## Connect your AI assistant

Open the **Connect** tab. It shows the URL, a QR code for your phone, and a button that performs a
real MCP handshake against your own hub and tells you whether it worked.

For Claude, add a custom connector pointing at `https://your-hub/mcp`. The OAuth flow does the rest
— dynamic client registration, PKCE, refresh tokens — and the hub introduces itself with its name,
website and logo. Every connected client appears in the UI and can be revoked with one click; the
token dies instantly.

**The tools your assistant gets:**

| Tool | What it does |
|---|---|
| `projects_list` | Every mapped project with node, edge and cluster counts — archived graphs are labelled with their documented origin, unregistered ones are flagged instead of blending in |
| `graph_query` | Answers a question with hybrid retrieval: semantic graph traversal plus the most relevant file excerpts, in one context |
| `graph_explain` | Explains one node in plain language |
| `graph_path` | Shortest path between two concepts |
| `graph_build` | Maps (or re-maps) a project on demand — the run lands in the same accountable history as the nightly job |
| `report_get` | The full graph report: hub nodes, clusters, surprises |
| `note_save` · `note_list` | Saves conversation knowledge as markdown notes — they join the graph on the next mapping run |
| `project_create` | Creates a fresh notes project and registers it for nightly mapping |
| `secret_list` · `secret_get` · `secret_set` · `secret_delete` | The vault — every access audited |

---

## Architecture

```
                      ┌──────────────────────────┐
    Claude / any      │  OAuth 2.1 + PKCE        │
    MCP client  ─────▶│  Bearer gate             │───┐
                      └──────────────────────────┘   │
                                                     ▼
    Browser / PWA ──▶ /ui ─▶   ┌────────────────────────────────────┐
                               │  api/  auth · knowledge · secrets  │
                               │        mapping · system            │
                               └────────────────────────────────────┘
                                  │              │              │
                     ┌────────────▼───┐  ┌───────▼──────┐  ┌────▼───────────┐
                     │ semantic.py    │  │ vault.enc    │  │ nightly timer  │
                     │ hybrid engine: │  │ AES-256-GCM  │  │ + runlog.py    │
                     │ graph + chunks │  │ double-wrap  │  │ (machine-      │
                     └────────────────┘  └──────────────┘  │  readable runs)│
                                                           └────────────────┘

    Production serving (how this instance runs itself):
    entry socket :8300 ──▶ active slot (blue │ green) — health-gated switch,
    watch window, automatic fallback, previous release kept warm.
```

**Retrieval, specifically.** `semantic.py` is the hub's own engine: a local multilingual embedding
model (fastembed/ONNX, CPU-only, downloads once, then fully offline) picks graph entry points by
*meaning*, walks the graph, and blends in the most relevant raw file excerpts. Every index is
self-healing; a missing chunk index never blocks a request. If the engine fails entirely,
`graph_query` falls back to the classic graphify CLI. Three layers, no dead ends.

**The vault, specifically.** A random 256-bit master key encrypts your secrets. That master key is
wrapped twice: once with `scrypt(your password)`, once with a machine key from the environment.
Changing your password re-wraps the master key — it never re-encrypts anything, so it can never
lose your secrets. Turn the machine wrap off and the hub stays locked until a human signs in; leave
it on and the nightly job fetches its own API key at 03:30 without waking you.

**Runs, specifically.** Every mapping run — nightly, UI-triggered or via MCP — writes a JSON run
record: start, duration, status, and per project the node/edge/community counts, the delta against
the previous run, the build ID of the accepted generation, and the error if one failed. The history
in the UI reads these records; free-text log parsing exists only as a fallback for old logs.
A failed project never erases the results of the others.

---

## Benchmarks

Retrieval quality is measured, not claimed: gold questions with objectively known answers, scored
by exact match on the retrieved context, identical token budget and hardware for every engine. The
suite runs locally with zero LLM cost, and every run is stored as JSON.

Latest run — **41 gold questions across 11 projects** (2026-07-15), same questions and budgets:

| Engine | Hit rate @ 400 tokens | @ 1,200 tokens |
|---|---|---|
| Lexical graph lookup (graphify) | 56 % | 58 % |
| **Hybrid — what `graph_query` ships** | **68 %** | **85 %** |

Why hybrid wins twice: graph structure is cheap per token (wins tight budgets), raw file excerpts
carry the literal facts (win large budgets). The hybrid splits every budget between both.

The three public-library projects used in the hardest benchmark set (`requests`, `flask`,
`express`) are kept in the hub as **archived graphs with documented origin** — so the published
numbers stay reproducible against the exact graphs that produced them.

Full report with per-project results, methodology and the misses we publish alongside the hits:
**[hub.it-handwerk-stuttgart.de/benchmarks.html](https://hub.it-handwerk-stuttgart.de/benchmarks.html)**
— every figure on that page is loaded live from a schema-validated data file generated from the
build artifacts of the exact release you're looking at.

---

## Security

- Login is rate-limited (5 attempts / 15 minutes), and the block **survives a restart**.
- Optional TOTP two-factor, with recovery codes.
- Access tokens are stored as SHA-256 hashes — reading the state file gets an attacker nothing.
- CSP is `default-src 'self'`: no CDN, no external font, nothing leaves your machine.
- Secret **values** are never returned by the list endpoint and never rendered until requested;
  they appear in no log, no error message and no diagnostic — enforced by tests.
- Unexpected errors surface in Diagnostics with a reference ID; once fixed, you acknowledge them
  (audited) instead of staring at stale warnings.
- Encrypted off-site backups (local + git), verifiable with `python backup.py verify`.

Found a vulnerability? See [SECURITY.md](SECURITY.md) — please
[report it privately](https://github.com/BEKO2210/Knowledge-Hub/security/advisories/new).

---

## Documentation

The **[wiki](https://github.com/BEKO2210/Knowledge-Hub/wiki)** is the long version:
[Installation](https://github.com/BEKO2210/Knowledge-Hub/wiki/Installation) ·
[Configuration](https://github.com/BEKO2210/Knowledge-Hub/wiki/Configuration) ·
[Connecting AI clients](https://github.com/BEKO2210/Knowledge-Hub/wiki/Connecting-AI-clients) ·
[Backup and restore](https://github.com/BEKO2210/Knowledge-Hub/wiki/Backup-and-restore) ·
[Security model](https://github.com/BEKO2210/Knowledge-Hub/wiki/Security-model) ·
[Troubleshooting](https://github.com/BEKO2210/Knowledge-Hub/wiki/Troubleshooting) ·
[Architecture](https://github.com/BEKO2210/Knowledge-Hub/wiki/Architecture) ·
[FAQ](https://github.com/BEKO2210/Knowledge-Hub/wiki/FAQ)

Questions and ideas go in [Discussions](https://github.com/BEKO2210/Knowledge-Hub/discussions).

## Development

```bash
pip install -r requirements-dev.txt
playwright install chromium

pytest          # 366 tests: unit, HTTP contract, MCP over real streamable HTTP,
                # retrieval engine, run history, graph registry — and end-to-end
                # in a real browser
ruff check .    # lint
```

The suite runs against a **throwaway vault in a temp directory**; it never touches a real one. The
end-to-end tests boot the actual ASGI stack on a free port and drive it with headless Chromium.

```
api/         the endpoints, by topic (auth · knowledge · secrets · mapping · system)
web/         index.html, app.css, app.js — no build step, no bundler
ui.py        the web layer: assets, security headers, routes
server.py    the MCP server and tools
semantic.py  the hybrid retrieval engine: embeddings, graph traversal, file chunks
runlog.py    machine-readable run records for every mapping run
buildmeta.py the build contract: manifest, validation gate, atomic publish & restore
vault.py     encryption
oauth.py     OAuth 2.1 + PKCE
bluegreen/   the zero-downtime switch used in production
tests/       366 of them
```

The interface is English by default and German at the flick of a switch.
Code comments are in German.

---

## Licence

[AGPL-3.0](LICENSE). Self-host it, modify it, do as you like — but if you run a modified version
**as a service for other people**, you have to publish your changes.

Graph extraction is done by [graphifyy](https://github.com/safishamsi/graphify)
(MIT, © Safi Shamsi); retrieval is Knowledge Hub's own hybrid engine (`semantic.py`), with the
graphify CLI kept as a fallback. Credit where it is due, independence where it matters.

---

<div align="center">
<img src="docs/images/icon.png" width="40" height="40" alt="" /><br />
<sub>Built by <a href="https://github.com/BEKO2210">BEKO2210</a> in Stuttgart.
If it's useful to you, a ⭐ costs nothing.</sub>
</div>
