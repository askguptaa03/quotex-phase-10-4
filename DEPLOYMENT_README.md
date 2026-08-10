# Quotex Signal Platform — Deployment Guide

This ZIP is a complete, self-contained project root. It is the P0-Stability
application baseline (Unknown Asset fix, SSID/session replacement fix,
Backtest/Validation batch-completion fixes, `workers=1`) with corrected,
portable deployment files (`.replit`, `.replitignore`, `start-prod.sh`).

## What's in this ZIP

```
.replit                 — Replit project config (Python only, no Node/pnpm)
.replitignore           — build-artifact exclusions
start-prod.sh            — production startup script (no hardcoded paths)
DEPLOYMENT_README.md    — this file
Quotex/                 — the application itself (unchanged application logic)
  market_analyzer/
    webapp/              — Flask app, scanner, backtest/validation engines, static/, templates/
    analyzer.py, backtest.py, learning_engine.py, indicator_registry.py  — protected core logic
  quotex/api_quotex/     — Quotex API client (protected, untouched)
  tests/                 — full regression + P0 + B1/M1 test suite
  requirements.txt       — pinned dependencies (authoritative, unmodified)
```

## Steps to deploy

1. **Upload/extract this ZIP into a brand-new, empty Replit project.**
   Extract at the project root — `.replit` and `start-prod.sh` must sit
   next to `Quotex/`, not inside it.

2. **Confirm the project root** looks like the structure above (Replit's
   file tree, left sidebar).

3. **Confirm `.replit` was picked up.** Replit reads it automatically;
   no action needed unless your Replit UI prompts you to "trust" the
   imported config.

4. **Confirm `start-prod.sh` is present and executable.** It already has
   the executable bit set in this ZIP; if your upload path strips
   permissions, run once in the Shell: `chmod +x start-prod.sh`.

5. **Confirm the Python environment.** `.replit`'s `modules` field
   requests `python-base-3.13`; Replit will provision it automatically
   on first run.

6. **Install dependencies:**
   ```
   pip install -r Quotex/requirements.txt
   ```
   (Replit's package manager will typically prompt/do this automatically
   the first time you run or deploy; run it manually in the Shell if not.)

7. **Add your Quotex session as a Secret — never as a file.**
   Replit → **Tools → Secrets** → add key `QUOTEX_SSID`, value = your
   actual SSID string. The application reads it from the environment at
   startup (`fetch_data.py`'s `load_session_ssid()`); it is never written
   into this ZIP, never logged, and never printed by the application.

8. **Select Reserved VM in the Deploy tab — this is the one manual step
   that could not be encoded into `.replit`.** See "Why Reserved VM is
   required" below. Click **Deploy** (top right) → choose **Reserved
   VM** → pick a machine size → Deploy.

9. **NEVER select Autoscale for this project.** See below for why —
   it will silently corrupt session/scan/backtest/validation state if
   more than one instance or worker process ever runs concurrently.

10. **Press Deploy.**

## Why `workers = 1` is required

`Quotex/market_analyzer/webapp/gunicorn.conf.py` pins `workers = 1`
unconditionally. The application keeps its Quotex session, the Auto
Scanner, and the Backtest/Validation engines as **process-global,
in-memory Python objects** (`_shared_fetcher`, `_scanner`,
`_backtest_engine`, `_validation_engine`, `_BG_LOOP`). These are not
shared across OS processes. Running more than one worker process would
give each one its own independent (and inconsistent) copy of all of
that state — a request that starts a scan on worker A would appear to
have "vanished" to a status poll that lands on worker B.

## Why Autoscale is incompatible

Autoscale can run **multiple separate machine instances** of the app
simultaneously under load — an even stronger version of the same
problem `workers = 1` guards against, since separate instances don't
even share a filesystem or process table. A session opened on one
instance is invisible to another; a running backtest can appear to
"stall" simply because your next request landed on a different
instance. **Reserved VM** runs your app as exactly one always-on
process, which is what this architecture requires.

## Why `QUOTEX_SSID` is a Secret, not a file

Putting a real session credential in source code means it ends up in
ZIP backups, git history, and anywhere this project gets copied.
Replit Secrets are injected as environment variables at runtime and are
not part of the deployed source bundle.

## How to replace the SSID safely through the running application

Once deployed, use the app's own **Session** panel
(`/api/session/update` → `/api/session/validate`) to submit a new SSID
at runtime — don't edit the Secret and manually restart unless you
specifically want to change the *environment-level* SSID. Note: if the
`QUOTEX_SSID` Secret is set, it takes priority over any SSID saved
through the UI — the app will tell you this explicitly in the
`/api/session/update` response (`env_var_override_active`) rather than
silently ignoring what you typed.

## Known, intentionally-untouched items

- `Quotex/main.py` is a leftover generic Replit template stub
  (`print("Hello from repl-nix-workspace!")`). It is **not** referenced
  by `start-prod.sh`, `.replit`, or the Flask app — it is dead code, left
  in place rather than deleted per this project's "don't delete
  unrelated files blindly" policy. Safe to ignore or remove manually.
