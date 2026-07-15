# Contributing

Thanks for looking. This is a small project with a sharp focus: a self-hosted hub that gives your
AI assistant your knowledge graphs and your secrets, and gives nobody else anything.

## Before you open a PR

```bash
pip install -r requirements-dev.txt
playwright install chromium

ruff check .   # must be clean
pytest         # the full suite must pass
```

Both run in CI, so a red build is a red PR.

## Licensing of contributions

Knowledge Hub is licensed under the [AGPL-3.0](LICENSE). To keep the project sustainable, it is
additionally offered under a commercial licence by the maintainer (dual licensing) — for example
for managed/SaaS offerings.

For that to remain possible, every contribution needs a clear licensing basis. By opening a pull
request you agree that:

1. **You have the right to submit the work** (it is your own, or you are permitted to contribute
   it), in the sense of the [Developer Certificate of Origin](https://developercertificate.org/).
2. **Your contribution is licensed to the project under AGPL-3.0**, like the rest of the code.
3. **You additionally grant the maintainer (BEKO2210) a perpetual, worldwide, non-exclusive,
   irrevocable, royalty-free licence** to use, modify, sublicense and relicense your contribution
   as part of Knowledge Hub — including under commercial licence terms.

You keep the copyright to your work; nothing here takes it away. This grant simply keeps dual
licensing possible after your code is merged. If you cannot or do not want to agree to this,
please open an issue instead of a PR — ideas are just as welcome.

Please add a `Signed-off-by: Your Name <you@example.com>` line to your commits
(`git commit -s`) to confirm the above.

## What gets merged quickly

- **Bug fixes with a test that fails before and passes after.** This is the fastest path.
- **Security fixes.** See [SECURITY.md](SECURITY.md) — report privately first, don't open a public
  PR that advertises a hole.
- **Translations.** The interface carries English and German. The mechanism is simple: static text
  in `web/index.html` uses `data-en="…"`, dynamic text in `web/app.js` goes through `t('German
  sentence')`, and server-side text goes through `T('German sentence')` from `api/i18n.py`. In each
  case the **German sentence is the key**, and a missing translation falls back to it rather than
  rendering an empty button.

## What needs discussion first

Open an issue before you build:

- Anything that touches the vault format. There are people with secrets in there and no way back if
  we get it wrong.
- Anything that widens what is reachable without authentication (`server.py`, the `BearerGate`).
- New dependencies. The hub deliberately ships no CDN asset and has a strict CSP; every dependency
  is a new thing that can go wrong on someone else's machine.

## House style

- **Comments explain *why*, never *what*.** If a line needs a comment to say what it does, rewrite
  the line. If a decision looks odd, the comment says which failure it prevents.
- Code comments are in **German** (the codebase grew that way); user-facing text and documentation
  are in **English**. Don't mix them within one string.
- No build step for the frontend. `web/` is plain HTML, CSS and JavaScript, served as files. Keep it
  that way — it is the reason anyone can read and audit the interface.
- Tests are named for the behaviour they defend, not the function they call. `test_login_blocks_after_five_failures`
  tells the next person what breaks; `test_login_2` does not.

## Reporting a bug

Include: what you did, what you expected, what happened, and the reference number if the interface
showed you one (unexpected errors carry one — it maps to an entry in `errors.log` with the full
trace). The diagnostics tab (**More → Diagnostics**) is a good screenshot to attach.
