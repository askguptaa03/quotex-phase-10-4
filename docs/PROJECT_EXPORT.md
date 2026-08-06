# PROJECT EXPORT — 5-Minute Summary for a New AI

## What this is
A **manual-trading-assist** analysis tool for Quotex OTC pairs. It never
places trades — it computes BUY/SELL/WAIT signals with a confidence score
and a separate 0-100 "Filter Score" quality metric, for a human to act on.

## Architecture in one paragraph
Quotex WebSocket client (untouched) -> `fetch_data.py` candle fetcher ->
`indicators.py::calculate_all()` (all technical indicators, pure functions)
-> `analyzer.py::generate_confluence_signal()` (10-factor weighted vote,
min 3 must agree) -> `analyzer.py::calculate_filter_score()` (separate
7-criteria graded quality score + binary `mandatory_pass` gate) ->
`webapp/app.py::_run_pipeline()` ties it all together and is reused
verbatim by the manual `/api/signal` route, the background
`scanner.py::ScannerEngine`, and (once wired) `backtest_engine.py`. All
async background work (scanner, future backtest routes) shares ONE event
loop (`_BG_LOOP`) to serialize Quotex I/O through the single persistent
connection.

## Completed work
- Full indicator engine: EMA/ADX/ATR/RSI/BB/OBV/CCI/Stochastic/Round-Number/
  Mean-Reversion/Exhaustion, 9-pattern candlestick detector, ATR-merged
  Support/Resistance zone engine, 3 new not-yet-connected OTC indicators
  (Wick Rejection, Liquidity Sweep, False Breakout).
- Confluence engine: 10 factors, backtest-driven dynamic weighting, always
  sums to 100, min-3-agree gate, confidence dampener for weak trend/extreme
  volatility, MTF confirmation with explicit CONFIRMED/DISAGREED/UNAVAILABLE
  status.
- Filter Score v2 (graded, 0-100, 7 criteria) + `mandatory_pass` (binary
  gate, decoupled from the score value — this decoupling was a deliberate
  fix, don't re-merge them).
- Smart Scanner: full async engine, tested, 6 working Flask routes
  (`status`, `results`, `start`, `stop`, `pause`, `resume`).
- Backtest Engine: full async engine, tested, **zero Flask routes yet**.
- Settings Store: full JSON-file persistence, tested, **zero Flask routes,
  and zero connection to the UI's existing (pre-project) static "Settings"
  tab** — that tab is read-only informational content, unrelated to this
  backend.
- Indicator Registry: metadata layer over the above, tested.

## Pending work (see NEXT_PHASE.md for task-level detail)
- Settings & Backtest Flask routes (backends exist, HTTP surface doesn't).
- Wiring Settings into `_run_pipeline()` (currently inert — nothing reads them).
- Quotex session management page.
- **Frontend UI wiring** — the UI already has a pre-existing 5-tab
  structure (scanner/analyzer/signals/history/settings, byte-unchanged by
  this project); its "Settings" tab is static/read-only and has no
  connection to `settings_store.py`; there is no Backtest tab at all yet.
- Connecting the 3 new indicators to Confluence (deliberately deferred,
  needs fresh explicit approval).
- Phase 8 (Scanner UI), Phase 9, Phase 10 — not started, barely scoped.

## Rules that must never be broken
1. Never place a trade. Analysis only, everywhere, always.
2. Never modify Quotex API / WebSocket / login / session handling code.
3. Never modify the Scanner's or Backtest Engine's core architecture without
   an explicit fresh approval cycle — they're separate modules on purpose.
4. Never duplicate logic that already exists — always import/reuse.
5. Backward compatibility is mandatory — additive fields only on any
   existing API response; never rename/remove an existing field.
6. `filter_score` (graded quality, 0-100, always computed) and
   `mandatory_pass` (binary gate, controls visibility) are DIFFERENT
   concepts — don't conflate them.

## Coding style established across this project
- Every new function gets a docstring explaining WHY, not just what, when
  a design tradeoff was involved.
- Geometry/data-derived scoring only — never a fixed per-name lookup table
  for reliability/strength scores.
- Vectorized (pandas) computation preferred; per-bar Python loops only used
  where genuinely unavoidable (documented explicitly when this happens,
  e.g. candlestick detection).
- Every phase: audit -> propose -> get approval -> implement -> regression
  test -> honest report (including bugs found, performance costs, and
  anything NOT done). Never claim more was done than actually was.

## Important constraints for whoever continues
- **No network access in the dev sandbox this project was built in.**
  Nothing has ever touched live Quotex data or a real HTTP request. Say so
  explicitly in any future report.
- The confluence engine currently has exactly 10 factors summing to weight
  100 — verify this invariant with a fuzz test before/after any change
  that touches weights.
- Read `PROJECT_MEMORY.md` for the "why" behind every non-obvious decision
  before changing anything that seems odd at first glance — it's very
  likely intentional and documented there.
