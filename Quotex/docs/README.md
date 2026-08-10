# Quotex OTC Signal Platform

**Baseline: Phase 8.3 Complete.** A manual-trading-*assist* analysis tool
for Quotex OTC pairs. **It never places trades.** It fetches candles, runs
a 10-factor confluence engine plus a graded Filter Score, and surfaces
BUY/SELL/WAIT with a confidence score for a human to act on.

New to this project? Start with `HANDOFF.md`, then `PROJECT_STATUS.md`
for the full ground-truth snapshot. `NEXT_PHASE.md` has the exact
next task (Phase 8.4.1).

## What's included
- **Core signal engine** — indicators → 10-factor confluence vote →
  graded Filter Score → BUY/SELL/WAIT signal with confidence.
- **Smart Scanner** — a background engine (`ScannerEngine`) that
  continuously ranks every OTC asset, with a full user-facing page
  (status, live progress, Start/Stop/Pause/Resume, a Scanner Settings
  card, and a ranked results table). Off by default; only a user
  button press starts it.
- **Backtest Engine** — measures historical indicator accuracy against
  real candle data and suggests dynamic factor weights.
- **Settings Store** — a persistent, file-backed store for every
  user-tunable value (filter thresholds, scanner pacing, indicator
  weights, etc.), editable from the Settings page.
- **Indicators page** — the full 13-indicator registry (10 that vote on
  signals, 3 that don't yet — see below).
- **Quotex Session page** — paste a session SSID and validate the
  connection without editing files by hand.

## 3 indicators that exist but don't affect signals (yet)
Wick Rejection, Liquidity Sweep, and False Breakout are implemented and
visible in the Indicators page, but are **deliberately not connected**
to the confluence vote. This has been true since Phase 7.3 and remains
an explicit, separate decision point — see `NEXT_PHASE.md` for the
in-progress validation work (Phase 8.4) before that decision is revisited.

## Running it
```bash
pip install -r requirements.txt
cd Quotex/market_analyzer/webapp
python3 preflight_check.py   # verifies env, deps, Chromium, config, required files
gunicorn -c gunicorn.conf.py app:app
```
On Replit, `start-prod.sh` (invoked via `.replit`) does all of the above
automatically. Copy `.env.example` to `.env` and fill in `QUOTEX_SSID`
(preferred) or email/password before connecting to a real Quotex session
— never commit a filled-in `.env` or `session.json`.

**This development sandbox has no live network access.** Nothing in this
project has ever been exercised against a real Quotex connection — every
phase's testing has verified the app's own logic/routing end-to-end
(via a Flask test client with only third-party network libraries
stubbed out), not live connectivity. Verify against your real
environment before relying on it for anything time-sensitive.

## Where the code lives
```
Quotex/
├── requirements.txt, .env.example, start-prod.sh, .replit
├── quotex/api_quotex/        # Quotex client — never touch without explicit approval
├── market_analyzer/
│   ├── analyzer.py            # confluence engine + filter score — 10 factors
│   ├── backtest.py            # accuracy backtesting — 10 factors only
│   ├── indicators.py          # all indicator math, incl. the 3 unconnected new ones
│   ├── output/candles.csv     # sample historical OHLCV data (single asset, 200 candles)
│   └── webapp/
│       ├── app.py              # Flask routes + _run_pipeline() + _scanner/settings_store wiring
│       ├── scanner.py          # ScannerEngine — single instance, SettingsStore-aware
│       ├── settings_store.py   # persistent settings (JSON file, gitignored)
│       ├── backtest_engine.py  # background backtest job runner
│       ├── indicator_registry.py
│       └── templates/index.html, static/{app.js,style.css}
```

## Documentation map
| File | What it's for |
|---|---|
| `HANDOFF.md` | Fast orientation — read this first |
| `PROJECT_STATUS.md` | Full ground-truth state snapshot |
| `NEXT_PHASE.md` | Exact next task |
| `CHANGELOG.md` | What changed, phase by phase |
| `TEST_REPORT.md` | How every change was verified |
| `RELEASE_NOTES.md` | User-facing summary of each release |
| `PROJECT_MEMORY.md` | Design rationale for non-obvious decisions |
| `API_DOCUMENTATION.md` | Route reference |
| `SETTINGS_REFERENCE.md` | Every setting, what it does, its default |
| `INDICATOR_DOCUMENTATION.md` | Every indicator's math and status |
