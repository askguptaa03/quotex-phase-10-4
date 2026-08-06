# HANDOFF — Start Here

New to this project? Read this file first, then `PROJECT_STATUS.md` for
the full ground-truth snapshot, then `PROJECT_MEMORY.md` for *why* things
are built the way they are. `NEXT_PHASE.md` has the exact task-level
breakdown of what's left. This file is a fast orientation, not a
replacement for those.

## What this is
A manual-trading-assist analysis tool for Quotex OTC pairs. **It never
places trades.** It fetches candles, runs a 10-factor confluence engine
plus a graded Filter Score, and surfaces BUY/SELL/WAIT with a confidence
score for a human to act on. A background Scanner ranks all OTC assets
continuously (now with a real user-facing page as of Phase 8.2/8.3); a
Backtest Engine measures historical indicator accuracy; a Settings Store
persists user-tunable configuration.

## Where things stand right now (end of Phase 8.3 — this is the verified baseline)
- **Core signal engine** (indicators → analyzer → filter score →
  confluence): stable, byte-identical to the original project across
  every phase through 8.3 — confirmed by direct diff against the
  original upload, not just checksum comparison, immediately before this
  recovery snapshot was packaged.
- **Settings / Backtest / Indicators / Quotex Session** (Phase 7.4):
  fully wired — backend routes, `_run_pipeline()` integration, complete
  frontend pages.
- **3 new indicators** (Wick Rejection, Liquidity Sweep, False Breakout):
  exist, are registered, show up in the Indicators page — but are
  **deliberately not connected to the confluence vote**. This has been
  true since Phase 7.3 and remains an explicit, separate decision point
  requiring fresh approval before it changes. (A Phase 8.4.1 audit found
  that no existing function actually backtests these 3 — `backtest.py`'s
  `_factor_votes()` only vectorizes the original 10 — so validating them
  will need new, additive code, not a modification to `backtest.py`.)
- **Smart Scanner backend** (`ScannerEngine`, Phase 7 + 8.1): SettingsStore
  integration (`scanner_enabled`/`enabled_assets`/`enabled_timeframes`/
  `scan_interval`/`minimum_filter_score`/`top_signals`), full progress
  tracking (`assets_completed`/`percent_complete`/`elapsed_time`/
  `estimated_remaining`/`current_timeframe`/`last_scan_time`), and
  `status()`/`results()` aliases.
- **Smart Scanner UI** (Phase 8.2 + 8.3): a real, dedicated page
  (`page-smart-scanner`) driving `ScannerEngine`'s actual
  `/api/scanner/*` routes — Start/Stop/Pause/Resume, a full Scanner
  Settings card (assets/timeframes/min filter score/top signals/scan
  interval/enabled toggle, with Save/Reload/Reset), an 11-column ranked
  results table, and auto-refresh that only polls while running and
  stops when the tab is left.
- **Phase 8.4** (validating the 3 new indicators, in preparation for a
  possible future confluence connection — NOT an automatic connection)
  has had its first sub-phase (8.4.1, audit-only) done; nothing beyond
  that has started. See `NEXT_PHASE.md`.

## The single most important gotcha
The UI's "Auto Scanner" tab (`view-scanner`, an older client-side polling
loop hitting `/api/signal` directly) and the newer **Smart Scanner** page
(`page-smart-scanner`, Phase 8.2/8.3, driving the real `ScannerEngine`
routes) are **two separate, coexisting UI surfaces** — both are reachable
from the drawer nav as distinct entries. This split predates the project;
Phase 8.2 added the second surface without removing or altering the
first. Be aware "the scanner" could mean either one depending on context.

Phase 7.4 fixed a real bug in the *client-side* loop specifically: it
used to auto-start on every page load. It now only starts via an
explicit "Enable Auto Scanner" toggle and always defaults OFF. The
backend `ScannerEngine` has never auto-started at any point in this
project's history, verified by a dedicated test every phase since 8.1.

## Where the code actually lives
```
Quotex/
├── quotex/api_quotex/        # Quotex client — never touch without explicit approval
├── market_analyzer/
│   ├── analyzer.py            # confluence engine + filter score — 10 factors, unchanged
│   ├── backtest.py            # accuracy backtesting — unchanged, 10 factors only
│   ├── indicators.py          # all indicator math, including the 3 unconnected new ones
│   └── webapp/
│       ├── app.py              # Flask routes + _run_pipeline() + _scanner + settings_store wiring
│       ├── scanner.py          # ScannerEngine — single instance, SettingsStore-aware (Phase 8.1)
│       ├── settings_store.py   # persistent settings (JSON file, gitignored) + reset_section()
│       ├── backtest_engine.py  # background backtest job runner
│       ├── indicator_registry.py
│       ├── templates/index.html, static/{app.js,style.css}  # incl. Smart Scanner page (8.2/8.3)
```

## How to verify anything in this repo yourself
This sandbox has **no live network access** — nothing has ever run
against real Quotex data. What's been verified end-to-end instead is the
full Flask route surface via a test client, with only the missing
third-party network libraries (`loguru`/`websockets`/`aiohttp`/
`python-socketio`/`playwright`/`cloudscraper`/`pydantic`) stubbed out —
the real `ASSETS`/`TIMEFRAMES` constants and real application logic are
exercised directly. See `TEST_REPORT.md`'s Phase 8.2/8.3 sections for the
exact stubbing approach if you need to reproduce it.

## Read next
1. `PROJECT_STATUS.md` — the full current-state snapshot (Phase 8.3 baseline).
2. `NEXT_PHASE.md` — next task is **Phase 8.4.1** (already audited once;
   see that file for what's left).
3. `PROJECT_MEMORY.md` — design rationale for every non-obvious decision.
4. `CHANGELOG.md` / `TEST_REPORT.md` — what changed and how it was
   verified, phase by phase.
