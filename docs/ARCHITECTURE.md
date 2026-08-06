# ARCHITECTURE

## Module-by-module

### `quotex/api_quotex/` — untouched all project
`client.py`, `websocket_client.py`, `login.py`, `config.py`,
`connection_keep_alive.py`, `monitoring.py` (unused — `HealthChecker`/
`ErrorMonitor`/`CircuitBreaker` classes exist but are never imported
anywhere in the webapp). SSID/session handling: `QUOTEX_SSID` env >
`session.json`, redacted logging, 14-day expiry.

### `market_analyzer/fetch_data.py`
`QuotexDataFetcher` — wraps the Quotex client, exposes `connect()`,
`disconnect()`, `get_candles_df(asset, timeframe, count)` returning a
pandas DataFrame with `open/high/low/close/volume` columns.

### `market_analyzer/indicators.py` (1133 lines)
Pure functions, no project-internal imports (deliberately decoupled).
`calculate_all(df, ...)` is the single entry point — computes every
indicator and returns one large dict. Notable sub-engines:
- `detect_candlestick_pattern_detailed()` — 9 patterns, geometry-derived
  strength/reliability (Phase 5). `detect_candlestick_pattern()` is a
  backward-compatible string-only wrapper.
- `detect_support_resistance_zones()` — swing detection + ATR-based zone
  merging (Phase 6). `support_resistance()` (simple min/max) is untouched.
- `detect_wick_rejection()`, `detect_liquidity_sweep()`,
  `detect_false_breakout()` — Phase 7.3, additive, NOT in confluence yet.

### `market_analyzer/analyzer.py` (849 lines)
- `generate_confluence_signal(df, indicators_result, dynamic_weights)` —
  the confluence engine. 10 factors, each votes -1/0/+1, weighted sum, min
  3 agreeing factors required for a real signal. `_apply_market_condition_dampener()`
  reduces (never increases) confidence for weak-ADX/extreme-volatility.
- `calculate_filter_score(indicators, signal_data, config)` — the graded
  0-100 quality metric + `mandatory_pass` boolean gate. Completely separate
  system from the confluence engine — never generates a signal itself.
- `DEFAULT_CONFLUENCE_WEIGHTS` — the single source of truth for default
  per-factor weights (10 factors x 10.0).

### `market_analyzer/backtest.py` (536 lines)
- `backtest_factor_accuracy(df, lookahead)` — replays each confluence
  factor's historical votes, measures forward-accuracy.
- `compute_dynamic_weights(accuracies)` — turns accuracy into a weight
  distribution (min-sample-size guarded, near-random factors penalized).
- `backtest_filter_score_report(df, lookahead)` — buckets historical bars
  by a REDUCED 5-criteria filter score (EMA/ADX/ATR/SR/Candlestick only —
  MTF and Payout are structurally unbacktestable, see PROJECT_MEMORY.md),
  reports win rate per bucket.

### `webapp/app.py` (637 lines)
- `_run_pipeline(asset, timeframe)` — the ONE function that ties
  everything together: fetch -> `calculate_all()` -> confluence -> MTF
  check -> `calculate_filter_score()`. This exact function is reused by
  `/api/signal` AND (once wired) by the scanner and backtest engine — never
  duplicated.
- `_BG_LOOP` / `_run_bg()` — a dedicated background thread running one
  asyncio event loop, used to serialize ALL Quotex I/O (comment in the code
  states only one request is ever in flight at the asyncio level). Both
  `scanner.py` and `backtest_engine.py` submit their work onto this SAME loop.
- `_shared_fetcher` — module-level singleton, one persistent Quotex
  connection reused across requests.

### `webapp/scanner.py` (417 lines)
`ScannerEngine` — background async state machine
(`STOPPED/RUNNING/PAUSED/YIELDING/DEGRADED/RECOVERING`). Calls
`_run_pipeline()` per asset (never duplicates its logic), gate-checks via
`analyzer.calculate_filter_score()` (never has its own gate logic — this
was refactored specifically to eliminate a duplication bug in Phase 7).
Ranks by `(filter_score, confidence, payout, freshness)`. Cache with TTL
cleanup, metrics, 10-cycle history, 100-event log.

### `webapp/backtest_engine.py` (332 lines)
`BacktestEngine` — same lifecycle pattern as scanner, deliberately a
SEPARATE module (not merged into scanner.py, per explicit instruction).
Reuses `backtest.py`'s 3 functions exactly. Never auto-applies suggested
weights — `evaluate_apply_conditions()` only evaluates, never applies.

### `webapp/settings_store.py` (281 lines)
`SettingsStore` — JSON-file-backed (`settings.json`), atomic writes,
auto-backfill of missing keys, backup/restore (last 10), export/import.
`get_effective_dynamic_weights()` is the mechanism for indicator
enable/disable: disabled -> weight 0, then optional renormalize to 100 —
this is how Settings is meant to influence the confluence engine WITHOUT
modifying it (weight override, not a code branch).

### `webapp/indicator_registry.py` (155 lines)
Pure metadata layer. Imports `DEFAULT_CONFLUENCE_WEIGHTS` (never
duplicates it). 13 entries (10 existing confluence factors + 3 new,
not-yet-connected indicators). `populate_from_backtest()` /
`apply_settings_overrides()` are pure merge functions.

## Data Flow (single asset analysis)
```
asset, timeframe
  -> fetch_data.get_candles_df()
  -> indicators.calculate_all()             [all technical indicators]
  -> analyzer.generate_confluence_signal()  [BUY/SELL/WAIT + confidence]
  -> MTF comparison-timeframe re-run (same pipeline, 1m or 5m)
  -> analyzer.calculate_filter_score()      [0-100 quality + mandatory_pass]
  -> JSON response (additive fields layered on every phase since Phase 1)
```

## How the Scanner works
Sequential loop over all 53 OTC assets, calling the exact same pipeline as
a manual request, paced by `asset_gap_seconds`. Never runs concurrently
with itself (single coroutine on `_BG_LOOP`). Yields to manual requests.
Visibility gated by `mandatory_pass`; ranking by `filter_score`.

## How the Backtest works
On-demand job (not yet exposed via HTTP) that fetches N candles per asset,
runs the 3 existing backtest functions, and reports — never mutates any
indicator weight on its own.

## How Settings work
File-backed, read fresh on every `get()` call (no in-memory cache that
could desync across Gunicorn workers). Effective weights/config are
computed on demand from stored values, never baked into a running process.

## How the Quotex connection works
Unchanged since before this project began. One persistent connection
(`_shared_fetcher`), serialized through `_BG_LOOP`.

## How WebSocket works
Entirely within `quotex/api_quotex/websocket_client.py` — never touched by
any phase documented here.

## How Filter Score works
See `INDICATOR_DOCUMENTATION.md` and `PROJECT_MEMORY.md` for the full
graded-band rationale. Summary: 7 criteria, 6 mandatory (individually
binary pass/fail, feeding `mandatory_pass`) + graded points (feeding
`filter_score`, always computed, never force-zeroed) + 1 non-mandatory
bonus (Candlestick).

## How Confidence works
Confluence engine's weighted vote -> optional dampener (weak trend/extreme
volatility) -> optional MTF boost/veto. Entirely separate from Filter Score.

## How Dynamic Weights work
`backtest_factor_accuracy()` measures real historical accuracy per factor
-> `compute_dynamic_weights()` converts to a weight distribution (min
20-signal sample size required, near-random factors penalized) -> passed as
`generate_confluence_signal(dynamic_weights=...)`, overriding
`DEFAULT_CONFLUENCE_WEIGHTS` for that call only — the default constant
itself is never mutated.

## How the Indicator Registry works
Read-only metadata view, sourced from `analyzer.DEFAULT_CONFLUENCE_WEIGHTS`
(imported) + optionally overlaid with real backtest results and settings
overrides. Never a second source of truth for weights.
