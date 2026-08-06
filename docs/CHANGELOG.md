# CHANGELOG

## Phase 10.4 — Walk-Forward Testing, Adaptive Calibration, Historical AI Health, Performance Reports, Advanced Analytics Dashboard

**Scope:** five additive goals, each with its own audit → implement →
test → verify cycle, none modifying `analyzer.py`, `backtest.py`,
`scanner.py`, `learning_engine.py`, `indicator_registry.py`,
`ai_health_engine.py`, or `quotex/api_quotex/` (verified byte-identical
after every goal, and again at final release — see TEST_REPORT.md).

### Goal 1 — Walk-Forward Testing Engine
**Added:** `market_analyzer/walk_forward.py`. Rolling and expanding
window generators; per-split evaluation fits factor weights on the train
slice only (via unmodified `backtest.backtest_factor_accuracy()` +
`compute_dynamic_weights()`) and evaluates a weighted combined signal
out-of-sample on the test slice. Win rate, accuracy, precision, recall,
profit factor (flat ±1 payout assumption, documented), max drawdown,
stability, confidence distribution. Multi-asset/multi-timeframe batch
runner, factor-subset (indicator) comparison, strategy comparison.
**Tests:** `tests/test_phase_10_4_goal1.py` — 46/46 passing.

### Goal 2 — Adaptive AI Calibration
**Added:** `market_analyzer/adaptive_calibration.py`. Validation-history-
based (no df needed): validation trend, accuracy trend, indicator
stability, weight stability, asset/timeframe calibration — sourced from
`validation_history_store`'s `run_log` and `learning_engine`'s
`recommendation_log`. Walk-forward-based (requires a df, reuses Goal 1):
confidence calibration (bucketed win rate vs. signal strength),
confidence scaling, threshold optimization, rolling calibration.
Deterministic recommendation generator (reason/evidence/confidence/
severity per entry).
**Added (routes, read-only):** `/api/calibration/report`, `/status`,
`/history`, `/recommendations` — sourced entirely from stores `app.py`
already owned. No route triggers a live fetch, so the df-dependent
calibration functions aren't reachable from these routes yet (documented
scope boundary, not an oversight).
**Tests:** `tests/test_phase_10_4_goal2.py` — 59/59 passing.

### Goal 3 — Historical AI Health
**Added:** `market_analyzer/webapp/ai_health_history_store.py` (new
JSON-backed store, mirrors `validation_history_store.py`'s exact I/O
pattern) and `market_analyzer/ai_health_trends.py` (pure functions:
daily/weekly/monthly overall-health-score trend, health history,
confidence trend, validation/learning component-score trend, regime
trend — distribution + confidence trend, "Unknown" regime counted like
any other observed state, never dropped).
**Added (routes):** `/api/ai/history/health` (GET, records a throttled
snapshot via the same `_build_ai_health()` helper `/api/ai/health`
already used, then returns the log), `/api/ai/history/trends` (GET),
`/api/ai/history/reset` (POST, explicit only).
**Tests:** `tests/test_phase_10_4_goal3.py` — 58/58 passing.

### Goal 4 — AI Performance Reports
**Added:** `market_analyzer/ai_performance_reports.py`. Daily/weekly/
monthly reports (health-score trend + period-bucketed accuracy/
confidence/filter_score/buy%/sell%); asset/timeframe/indicator reports
(delegate entirely to the existing `asset_timeframe_learning.py` rather
than re-deriving ranking logic); validation/learning reports; AI Health
report (current snapshot + trends + regime distribution); Walk-Forward
Summary and Calibration Summary (condense Goal 1/2 output, `available:
false` rather than fabricated when no data was supplied); deterministic
warning rules.
**Added (routes):** `/api/reports/{daily,weekly,monthly,assets,
timeframes,indicators,validation,learning,ai-health,calibration,export}`
(all GET, read-only) and `/reports` — a minimal, self-contained new page
(`templates/reports.html`, own inline script, reuses `style.css`, no new
CSS framework, `templates/index.html`/`static/app.js` untouched).
**Tests:** `tests/test_phase_10_4_goal4.py` — 64/64 passing.

### Goal 5 — Advanced Analytics Dashboard
**Added:** `market_analyzer/analytics_dashboard.py` — reuses Goal 4's
`build_full_performance_report()` as-is, adds the one missing piece
(`compute_validation_distribution()`, per-indicator win/loss counts).
**Added (routes):** `/api/analytics/dashboard` (bundled payload) and
`/analytics` — a new page (`templates/analytics.html`, own inline
script, reuses the same Chart.js CDN build `templates/index.html`
already loads — not a new dependency, no new CSS framework) with
Historical Accuracy/Confidence trend chart, Walk-Forward Summary,
Calibration Summary, Best/Worst Indicators/Assets/Timeframes, Regime
Distribution, Validation Distribution, Learning Distribution, Warnings,
and Export/Report shortcuts.
**Tests:** `tests/test_phase_10_4_goal5.py` — 40/40 passing.

### Compatibility
`analyzer.py`, `backtest.py`, `scanner.py`, `learning_engine.py`,
`indicator_registry.py`, `ai_health_engine.py`, and `quotex/api_quotex/`
confirmed byte-identical to the pre-Phase-10.4 baseline via `diff -rq`
after every goal and again at final release. A full-repository-root diff
(not just the `Quotex/` folder) confirms no file anywhere outside the
listed additions/`webapp/app.py` changed.

### Known limitations (documented, not hidden)
- This sandbox cannot import/run `webapp/app.py` directly
  (`fetch_data` → `api_quotex` → `loguru`/`websockets`, not installed, no
  network access to add them). Every new route is verified by source
  inspection (import present, route decorator present, pre-existing
  routes still present verbatim) rather than an actual HTTP
  request/response — same standing limitation documented since Phase
  10.1. A minimal-stub import attempt (`loguru`, `websockets`,
  `cloudscraper`) was tried during Goal 6 and abandoned deliberately: it
  only would have validated that imports resolve, not real route
  behavior, and risked masking real bugs behind low-fidelity stubs —
  source inspection remains the honest verification method used.
- No route triggers a live Quotex data fetch, so Goal 1's walk-forward
  engine and Goal 2's df-dependent calibration functions aren't reachable
  from any new API route yet — `/api/reports/export`'s and
  `/api/analytics/dashboard`'s `walk_forward` section always reports
  `available: false` in this deployment (documented scope boundary).
- Daily/weekly/monthly reports and the Analytics Dashboard's trend chart
  depend on the AI Health snapshot log accumulating over time (throttled
  to at most 1 snapshot per 15 minutes) — sparse/empty on a
  freshly-deployed instance until snapshots build up.

## Phase 10.3 Part-2 — AI Health Dashboard + Explainable Signal System

**Scope:** two new additive modules — an Explainable Signal Engine that
turns an already-computed signal into a structured "why" (9 named
✔/✖ checks, Hard Gates Passed/Failed, Final Filter Score, Confidence,
Reasons, Warnings), and an AI Health Engine that scores 5 system
components (Indicator/Scanner/Validation/Learning/Regime) plus an
Overall AI Health rating — exposed via 4 new read-only `/api/ai/*` routes
and a new dashboard page. Zero changes to `analyzer.py`, `backtest.py`,
`indicators.py`, `scanner.py`, `learning_engine.py`, or
`indicator_registry.py`.

### Pre-implementation audit (Step 1)
Read `webapp/app.py`, `analyzer.py`, `learning_engine.py`,
`validation_history_store.py`, `asset_timeframe_learning.py`,
`templates/index.html`, and `static/app.js` before writing any code. Key
findings:
- `_run_pipeline()`'s result dict (also what `ScannerEngine._cache` stores
  verbatim) already contains everything an Explain engine needs:
  `confluence.{signal,confidence}`, `factors` (per-factor vote), `filter_
  score`/`passed_filters`/`failed_filters`/`filter_breakdown` (from
  `analyzer.calculate_filter_score()`), `multi_tf_status`, and `regime`
  (Phase 10.3 Part-1). Nothing needed recomputing.
- **One real constraint, resolved without touching `scanner.py`:** an
  accurate "Recent WAIT %" needs `ScannerEngine`'s full unfiltered signal
  history, which only lives in the private `_cache` attribute — there is
  no public accessor for it, and `get_results()` only exposes a GATED
  subset (`mandatory_pass=True`, `signal != WAIT`, `confidence >=
  min_confidence`). Since `scanner.py` is off-limits and no existing code
  anywhere in this project reads `_cache` from outside the class, this
  phase does not either. Resolution: BUY%/SELL% are computed from the
  gated `top_signals` subset only (honestly labeled "among currently-
  surfaced signals"), and `recent_wait_pct` is reported as `None` — not
  guessed — exactly like this project's existing "Unknown" conventions.
  `recent_signal_count` still uses the fully-accurate, unfiltered
  `cached_results` total from the public `get_status()`.
- Drawer-nav + `VIEWS` array + `navigateTo()` (same extension point
  Smart Scanner/Validation/Learning already used) is the safe place to
  add a new page. Phase 10.2 already uses an `ai-*` id/function prefix
  ("Asset Intelligence" inside the Learning page) — the new dashboard
  uses a distinct `aih-*` prefix and its own page id (`page-ai-health`)
  throughout to avoid any collision.

### New files (both additive, zero edits to any existing indicator/
analyzer/backtest/scanner function)

- **`market_analyzer/explainable_signal.py`** — `explain_signal(result)`.
  Pure function of the pipeline result dict; recomputes nothing. Nine
  checks (Trend/Volatility/Price Action/Support-Resistance/ADX/MTF read
  directly from `filter_breakdown[...]["passed"]`; Momentum from
  rsi_div/stoch/cci confluence-vote majority; Volume from the obv vote;
  Regime from whether the detected regime is one `regime_weight_
  engine.py` already treats as trend-continuation-favorable in that
  direction). For a WAIT signal, momentum/volume/regime are reported
  False with an explicit "no directional confirmation to check" reason
  rather than guessed from a non-actionable direction. Returns Hard
  Gates Passed/Failed (from `passed_filters`/`failed_filters` verbatim,
  with a local presentation-only label map — same convention as
  `app.py`'s own `_FACTOR_LABELS`), Reasons, and Warnings. Never raises —
  an empty/missing result yields an all-False explanation with one
  explanatory warning.
- **`market_analyzer/ai_health_engine.py`** — `compute_ai_health(...)`.
  Pure functions, no I/O, no persisted store (same decoupling convention
  as `learning_engine.py`/`asset_timeframe_learning.py`). Five component
  scorers (`compute_indicator_health`/`compute_validation_health`/
  `compute_learning_health`/`compute_scanner_health`/
  `compute_regime_health`), each reading only already-computed data
  (`validation_history_store.get_history()`'s `rolling_stats`/`run_log`,
  `learning_engine.compute_recommendation()`'s `per_indicator`, the
  public `ScannerEngine.get_status()`/`get_results()`, and the current
  regime dict). Every health status is one of exactly `Excellent / Good /
  Fair / Poor / Critical` via a fixed 0-100 `_status_label()` scale — a
  "no data yet" component is deliberately given `Fair` (never `Critical`)
  so absence of data is never misreported as a failure, mirroring
  `regime_detector.py`'s own fixed-25.0-confidence convention for
  "Uncertain / Mixed". `compute_ai_health()` orchestrates all five into
  an `overall_health` (equal-weighted average) plus the full flat metric
  set: `average_confidence`, `average_filter_score`, `recent_accuracy`,
  `recent_signal_count`, `recent_wait_pct` (always `None` — see the
  audit note above), `buy_pct`, `sell_pct`, `data_quality`,
  `history_coverage`. Every argument is optional and defaults to a safe
  "no data yet" snapshot — never raises.

### Modified files (minimal, additive only)

- **`market_analyzer/webapp/app.py`** — two new imports
  (`explainable_signal.explain_signal`, `ai_health_engine.compute_
  ai_health`); one new private helper, `_build_ai_health()`, gathering
  the inputs `compute_ai_health()` needs from the stores/engines `app.py`
  already owns; four new read-only routes: `GET /api/ai/health` (full
  snapshot), `GET /api/ai/status` (condensed status-labels-only view),
  `GET /api/ai/statistics` (flat numeric fields only), and `GET
  /api/ai/explain` (optional `?asset=&timeframe=` — reuses `_run_
  pipeline()` with the exact same error handling and manual-request
  bookkeeping `/api/signal` already uses when given, or explains the
  scanner's current top-ranked cached signal when not). No existing
  route, function, or line was changed.
- **`market_analyzer/webapp/templates/index.html`** — one new drawer-nav
  button (`data-nav="ai-health"`), one new page section
  (`id="page-ai-health"`, using only pre-existing classes:
  `.glass-card`/`.small-metrics-grid`/`.metric-card`/`.badge`/
  `.tab-empty`/`.history-row`/`.chip-toggle`/`.tab-refresh-btn`), and one
  new hand-rolled modal overlay for the Explain Signal popup. No existing
  page/section was changed.
- **`market_analyzer/webapp/static/app.js`** — `'ai-health'` added to the
  `VIEWS` array; one new `if (name === 'ai-health') initAiHealthPage();`
  branch in `navigateTo()`; ~12 new `aih*`-prefixed functions
  (`aihLoadHealth`, `aihLoadTopIndicators`, `aihLoadBestGroups`,
  `aihPopulateExplainSelectors`, `aihExplainSignal`,
  `aihCloseExplainModal`, `aihLoadAll`, `initAiHealthPage`, plus small
  helpers) appended at the end of the file. Reuses the existing
  `lIndicatorLabel()`/`fmtLabel()`/`$()` helpers and the existing
  `window._OTC_ASSETS`/`window._LIVE_ASSETS`/`window._TIMEFRAMES`
  globals — no new global state, no new CSS framework. No existing
  function was changed.
- **`market_analyzer/webapp/static/style.css`** — 5 new `.badge-health-*`
  status-color variants (reusing the existing `--accent`/`--accent-dk`/
  `--wait`/`--sell` custom properties, same convention as the existing
  `.badge-demo`/`.badge-live`/`.badge-readonly`), plus a small,
  hand-rolled `.aih-modal-overlay`/`.aih-modal`/`.aih-check-row` block
  for the Explain Signal popup (no popup component existed before this
  phase) — reusing `var(--panel)`/`var(--r-lg)`/`.glass-card` tokens
  only. No existing rule was changed.

**`analyzer.py`, `backtest.py`, `indicators.py`, `scanner.py`,
`learning_engine.py`, `indicator_registry.py`, and the entire Quotex
API/WebSocket/login stack remain byte-identical to Phase 10.3 Part-1** —
re-verified by `tests/test_phase_10_3_part2.py` §5 (source-inspection
re-checks) and by every prior phase's regression suite still passing
unchanged.

### `tests/test_phase_10_3_part2.py` (97/97 passed)
New suite covering: all 5 `ai_health_engine.py` component scorers against
hand-built inputs with known expected results (including the "no data
yet -> Fair, never Critical" convention); `compute_ai_health()`'s full
orchestration, flat-field re-exposure, zero-argument safety, and
determinism; `explain_signal()` for BUY/SELL/WAIT signals (9 checks, Hard
Gates Passed/Failed, Reasons/Warnings, the WAIT-signal no-direction
handling, Unknown-regime handling, missing-factor/missing-gate graceful
degradation, empty-result safety, determinism); integration wiring
verified by source inspection (routes registered, imports present, UI
element ids present, JS functions/VIEWS-entry present, CSS classes
present); and an off-limits-files re-check (analyzer/backtest/scanner/
learning_engine/indicator_registry source confirmed to contain zero
reference to either new module).

### Known limitations
- **`webapp/app.py` cannot be imported or exercised via a live Flask test
  client in this sandbox** — same pre-existing, documented environment
  limitation as every prior phase (`fetch_data.py` → `quotex/api_quotex/`
  → `loguru`, not installed here). The 4 new routes and the dashboard's
  JS/HTML wiring are verified by `py_compile` + `node --check` +
  Jinja2-standalone template rendering + HTML tag-balance checking +
  source-inspection assertions, not a live browser/HTTP round-trip.
- **`recent_wait_pct` is always `None`** — see the audit note above;
  this is a deliberate, documented, tested design choice (not a bug),
  made specifically to avoid reading `ScannerEngine`'s private `_cache`
  attribute from outside the class.
- **BUY%/SELL% reflect only the scanner's currently-surfaced (gate-
  passing) signals**, not the full universe of everything the scanner
  has attempted — labeled as such everywhere it's surfaced (API field
  names, dashboard UI copy, module docstrings).
- The AI Health scoring formulas (component weights, the fixed 0-100
  `_status_label()` thresholds, the "no data = Fair" default) are
  hand-authored and documented inline — not statistically calibrated
  against this project's own historical outcomes. Same provisional
  caveat already applied to Phase 10.3 Part-1's regime multiplier tables.
- No live-network verification was possible (standing sandbox
  constraint, same as every prior phase).

### Deferred (not started, no scope assumed)
- Historical/time-series charting of AI Health over time (currently a
  point-in-time snapshot only, recomputed fresh on every `/api/ai/*` call).
- Any change to `scanner.py` to expose its full unfiltered signal cache
  publicly (would unlock an accurate `recent_wait_pct`) — a real,
  identified opportunity, deliberately left out of scope per this
  phase's "never modify scanner.py" instruction.
- Calibrating the AI Health scoring formulas against real historical
  accuracy data.
- Phase 10.4 — not scoped, not started.

## Phase 10.3 Part-1 — Market Regime Detection + Adaptive Weight Engine + Dynamic Indicator Selection

**Scope:** classify the current market into one of 8 deterministic regimes
(or "Unknown" when data is insufficient) and use that classification to
rescale the confluence engine's per-factor weights before they reach
`generate_confluence_signal()`. Pure rule-based logic — no ML, no learned
weights. Additive-only; `analyzer.py` is untouched.

### Pre-implementation audit (Step 1)
Extracted the Phase 10.2 Stable ZIP, recompiled the entire project clean
(`market_analyzer/`, `webapp/`, `quotex/`, `tests/`, `main.py`), and re-ran
all 4 persisted regression suites before writing any Phase 10.3 code:
`test_phase_8_6.py` (51/51), `test_phase_9_pipeline_fix.py` (34/34),
`test_phase_10_1.py` (142/142), `test_phase_10_2.py` (74/74) — 301/301
total. Audited `analyzer.py`, `indicators.py`, `config.py`, `backtest.py`,
`run_analysis.py`, and `webapp/app.py`. Key findings that shaped the
design:
- `analyzer.generate_confluence_signal(df, indicators_result,
  dynamic_weights=None)` already accepts a full weight-override argument
  — no signature change needed to inject regime-adjusted weights.
- `webapp/app.py` already has a proven precedent for this exact kind of
  change: `_apply_settings_weight_overrides()` rescales the already-computed
  `dynamic_weights` right before `generate_confluence_signal()` is called,
  renormalizing back to 100 with the same "residual to the largest weight"
  convention. Phase 10.3 Part-1's integration follows this identical
  pattern as one more layer, placed just *before* it (so Settings —
  explicit user intent — still keeps final say).
- `indicators.calculate_all()` already produces every field a regime
  classifier needs on the latest bar: `adx`, `di_plus`/`di_minus`,
  `direction`/`slope_pct` (from `trend_direction()`), `level`/`atr_pct`/
  `bb_width_pct` (from `volatility()`), `bb_upper`/`bb_lower`, and the
  four existing reversal-geometry detail dicts (`candlestick_pattern_
  detail`, `wick_rejection_detail`, `liquidity_sweep_detail`,
  `false_breakout_detail`, each carrying a `reliability_score`). No new
  indicator calculation was needed anywhere in this phase.

### New files (all additive, zero edits to any existing indicator/analyzer/
backtest function)

- **`market_analyzer/regime_detector.py`** — `detect_market_regime(ind, ...)`.
  Pure function of an indicators dict (no pandas/numpy/analyzer/backtest
  import). Classifies into exactly one of 8 named regimes (`Strong
  Uptrend`, `Strong Downtrend`, `Sideways Range`, `High Volatility`, `Low
  Volatility`, `Breakout`, `Reversal`, `Uncertain / Mixed`) or `Unknown`
  (missing/NaN required fields — never guessed past). Evaluation order is
  fixed and documented in the module docstring: Reversal → Breakout →
  Strong Uptrend/Downtrend → High Volatility → Low Volatility → Sideways
  Range → Uncertain/Mixed. Every branch returns a `reasons` list stating
  exactly which fields/thresholds drove the call, plus a `metrics_used`
  snapshot and a geometry-derived `confidence` (0-100, not learned).
  Reuses the same `40.0` reliability-threshold convention already
  established in `analyzer.py` (`CANDLE_RELIABILITY_VOTE_THRESHOLD` /
  `SR_RELIABILITY_VOTE_THRESHOLD` / etc.) and the same `25.0` ADX-trending
  convention as `config.ADX_TRENDING` — as local defaults, not an import,
  so the module has zero import-time coupling and is trivially unit-testable
  with a hand-built dict.
- **`market_analyzer/regime_weight_engine.py`** — `apply_regime_adaptive_
  weights(weights, regime_result)`. A fixed, hand-authored per-regime
  multiplier table (`REGIME_FACTOR_MULTIPLIERS`) rescaling the 13
  confluence-factor weights the caller already has, renormalized back to
  100 (same residual-to-largest-weight convention as
  `_apply_settings_weight_overrides()`). `Uncertain / Mixed` and `Unknown`
  are a deliberate no-op — weights pass through completely unchanged when
  the regime itself isn't confidently known.
- **`market_analyzer/dynamic_indicator_selector.py`** —
  `apply_dynamic_indicator_selection(weights, regime_result)`. A second,
  *categorical* layer distinct in kind from the continuous multiplier
  table above: per regime, a small set of factors is marked `primary`
  (weight x1.15) and a small set `low_relevance` (weight x0.5 — discounted,
  **never zeroed**, specifically to avoid (a) silently duplicating the
  Settings Store's "disabled = weight 0" contract, which is a user
  decision, not an automatic one, and (b) starving
  `generate_confluence_signal()`'s "≥3 agreeing factors" rule of real
  information, since vote-counting is based on sign, not weight). Same
  no-op behavior for `Uncertain / Mixed`/`Unknown`.
- **`market_analyzer/regime_pipeline.py`** — `compute_regime_adjusted_
  weights(base_weights, ind)`. Single orchestration entry point composing
  the three modules above in sequence (`detect_market_regime` →
  `apply_regime_adaptive_weights` → `apply_dynamic_indicator_selection`),
  so every caller only needs one import and one call. Does not import
  `analyzer.py` or `backtest.py`.

### Modified files (minimal, additive only)

- **`market_analyzer/config.py`** — one new flag,
  `ENABLE_REGIME_ADAPTIVE_WEIGHTS = True`. `False` makes the regime layer
  a full no-op in both callers below (dynamic_weights passes through
  byte-identical to pre-Phase-10.3 behavior).
- **`market_analyzer/run_analysis.py`** — one new import
  (`regime_pipeline.compute_regime_adjusted_weights`) and, right after
  `dynamic_weights = compute_dynamic_weights(accuracies)`, a
  config-flag-gated call that reassigns `dynamic_weights` to the
  regime-adjusted result and prints the detected regime + its reasons to
  the console report. No other line in this file changed.
- **`market_analyzer/webapp/app.py`** — one new import, and inside
  `_run_pipeline()`: a config-flag-gated call to `compute_regime_adjusted_
  weights(dynamic_weights, indicators)` inserted *between* the existing
  precomputed-weights check and the existing
  `_apply_settings_weight_overrides()` call (which still runs last and is
  completely unmodified — Settings keeps final say). One additive,
  read-only `"regime"` key added to the route's JSON `result` dict
  (`name`, `confidence`, `reasons`, `adaptive_weight_applied`,
  `selection_applied`, `primary_indicators`, `low_relevance_indicators`) —
  every pre-existing key in that dict is untouched. No other line in this
  file changed.

**`analyzer.py`, `backtest.py`, `indicators.py`, `scanner.py`,
`learning_engine.py`, `indicator_registry.py`, and the entire Quotex
API/WebSocket/login stack are byte-identical to Phase 10.2** — re-verified
by `tests/test_phase_10_3_part1.py` §6-7 (source-inspection re-checks) and
by every prior phase's regression suite still passing unchanged.

### `tests/test_phase_10_3_part1.py` (149/149 passed)
New suite covering: all 8 regime classifications + the Unknown path (both
missing-field and NaN-field variants) + the "reversal detail present but
below threshold" edge case; per-regime adaptive-weight rescaling
(ratio-preserving, sums to 100, Uncertain/Unknown no-op); per-regime
dynamic-indicator-selection (primary boost, low-relevance discount, never
zeroed, Uncertain/Unknown no-op); full pipeline orchestration
(matches manual two-step composition, deterministic across repeated
calls, Unknown-regime end-to-end no-op); normalization edge cases
(non-100-sum input, empty weights dict, all-zero weights, unrecognized
factor keys); config-flag + API-additive-field integration wiring
(verified by source inspection — see Known Limitations); and an
off-limits-files re-check (analyzer/backtest weight constants unchanged,
zero import coupling from any new module back into analyzer/backtest,
scanner.py/learning_engine.py/indicator_registry.py contain no reference
to any Phase 10.3 module).

### Known limitations
- **`webapp/app.py` cannot be imported or exercised via a live Flask test
  client in this sandbox** — `fetch_data.py` → `quotex/api_quotex/` →
  `loguru`, which is not installed here. This is the same pre-existing,
  documented environment limitation noted for Phase 10.1/10.2's untested
  summary routes, not something this phase introduced. The `"regime"` API
  field and the config-flag gating are verified by `py_compile` (Step 8)
  plus source-inspection assertions in `tests/test_phase_10_3_part1.py`
  §6, exactly as those prior phases' route wiring was verified.
- The regime → factor-multiplier and regime → primary/low-relevance
  tables are hand-authored, fixed constants based on general technical-
  analysis reasoning (documented inline in each module) — they are **not**
  backtest-calibrated against this project's own historical data. Treat
  the resulting weight shifts as provisional, same caveat this project
  already applies to `DEFAULT_CONFLUENCE_WEIGHTS` before backtest data
  exists.
- No live-network verification was possible (standing sandbox constraint,
  same as every prior phase) — the regime classifier has only been
  exercised against hand-built indicator dicts, not real fetched candles.

### Deferred to Phase 10.3 Part-2 (not started, no scope assumed)
Per the Phase 10.3 request, only Part-1 (regime detection, adaptive
weights, dynamic selection, and their integration) was in scope. Not
started, not scoped, no code written:
- Any UI surface for the new `"regime"` field (Regime badge/panel on the
  dashboard, historical regime timeline, etc.).
- Persisting regime-classification history over time (there is no
  `RegimeHistoryStore` — every call recomputes fresh, same as every other
  advisory computation in this project before a dedicated history store
  was built for it).
- Backtest-calibrating `REGIME_FACTOR_MULTIPLIERS`/
  `DYNAMIC_SELECTION_TABLE` against real historical accuracy instead of
  hand-authored constants.
- Extending regime detection to consider multi-timeframe confirmation
  (currently single-timeframe only, matching the granularity of the
  `ind` dict it's given).
- Any change to `analyzer.py`, `backtest.py`, the confluence engine's 13
  factors, or `calculate_filter_score()` — none was needed for Part-1 and
  none should be assumed in scope for Part-2 without fresh approval, per
  this project's standing rule.



**Scope:** learn which indicator performs best on each OTC asset and on
each timeframe, from accumulated Validation History — plus system-wide
top/weak indicator rankings and advisory recommendations. Additive-only.

### Pre-implementation audit (Step 1)
Extracted the canonical Phase 10.1 Stable ZIP, recompiled clean, and
re-ran all 3 persisted regression suites (227/227) before writing any
Phase 10.2 code. Audited `validation_history_store.py`,
`learning_engine.py`, `validation_engine.py`, `indicator_validation.py`,
`app.py`, and `scanner.py`. Key finding: `ValidationEngine.results` has
full per-`(asset, timeframe)` granularity, but that detail is discarded
at the exact point `app.py`'s `_maybe_persist_validation_history()` folds
it into a single global `summary` before persisting — `rolling_stats` in
`validation_history_store.py` was (and remains) a single indicator-keyed
global bucket, folded across every asset/timeframe combined. Confirmed no
fixed asset/timeframe enum exists anywhere in the codebase (both are
freeform, caller-supplied strings), so any new per-asset/per-timeframe
storage had to be built dynamically, not from a hardcoded list. Confirmed
`scanner.py` needs no changes — it's a live orchestration engine unrelated
to persisted Validation History.

### `market_analyzer/webapp/validation_history_store.py` — schema 1.1 → 1.2
- Added two new top-level keys, `asset_stats` and `timeframe_stats`
  (`{key: {indicator: rolling-stats-dict}}`, same per-indicator shape
  `rolling_stats` already uses). Unlike the fixed 13-entry
  `KNOWN_INDICATORS`, both start **empty** — assets/timeframes are
  unbounded, freeform strings, populated lazily as they're actually
  validated.
- New method `record_asset_timeframe_stats(results, timestamp)` — accepts
  the RAW per-combination dict `ValidationEngine.get_results()["results"]`
  already produces (previously computed and then discarded once the
  flattened `summary` was built) and accumulates it via a new
  `_apply_indicator_result_to_bucket()` helper, using the same rolling-mean
  update convention `record_run()` already established for the global
  bucket. Completely independent of `record_run()` — neither reads or
  writes the other's keys; calling one, the other, both, or neither after
  a run completes has no effect on the other's behavior.
- New read-only accessors `get_asset_stats(asset=None)` /
  `get_timeframe_stats(timeframe=None)` — fail soft (empty dict, not an
  exception) for an asset/timeframe never recorded.
- **Backward-compatible migration, verified against a real synthetic
  1.1-format file**: schema bumped to `"1.2"` only when genuine migration
  happens (same pre-merge-snapshot detection technique already proven for
  the Phase 10.1 1.0→1.1 migration, extended to also cover the two new
  top-level keys); pre-existing `rolling_stats`/`run_log` preserved
  byte-identically; new keys backfilled empty; idempotent re-read; a
  freshly-migrated file immediately accepts new
  `record_asset_timeframe_stats()` calls correctly. `reset()` now also
  clears the two new keys, consistent with its pre-existing "wipe
  everything back to defaults" contract — not new logic.

### `market_analyzer/webapp/app.py`
- `_maybe_persist_validation_history()`: one additive call to
  `record_asset_timeframe_stats()` alongside the existing, unmodified
  `record_run()` call, passing `results["results"]` (previously fetched
  and then discarded — now also persisted).
- 4 new read-only routes: `GET /api/learning/assets`, `GET
  /api/learning/timeframes`, `GET /api/learning/top-indicators`, `GET
  /api/learning/recommendations`. All pure computation over
  `_validation_history_store.get_history()` via the new
  `asset_timeframe_learning.py` — none of them write anywhere.

### `market_analyzer/webapp/asset_timeframe_learning.py` (new, additive)
Standalone module, same decoupling convention `learning_engine.py`
established — pure functions, no I/O of its own, imports nothing from
`analyzer.py`/`backtest.py`/`validation_engine.py`/
`indicator_validation.py`/`scanner.py`/`learning_engine.py`.
- `compute_asset_rankings()` / `compute_timeframe_rankings()`: for every
  asset/timeframe with recorded history — total validations, wins,
  losses, accuracy, trend, confidence (pooled across every indicator
  recorded for that group, sample-weighted), plus that group's best- and
  weakest-performing indicator, plus a best-to-worst ranking. **Bug found
  and fixed during testing**: the ranking was initially ordered by raw
  accuracy alone, so a 3-of-5-sample group could outrank a 55-of-100
  group — fixed to gate ranking inclusion on the same `min_samples`
  threshold every other confidence-scored value in this codebase already
  applies (a below-threshold group still appears in the full response,
  just excluded from the authoritative ranked list).
- `compute_top_indicators()`: global (not asset/timeframe-scoped)
  strongest/weakest indicator ranking from the pre-existing
  `rolling_stats`.
- `compute_recommendations()`: best indicator per asset, best indicator
  per timeframe, lowest-performing indicators overall, and
  improving/declining indicators overall (system-wide trend, from
  `rolling_stats`). Advisory only — never applied automatically, no
  persisted recommendation log (unlike `learning_engine.py`'s
  `LearningHistoryStore` — this phase's scope has no
  history-of-recommendations endpoint).

### UI — `templates/index.html` / `static/app.js`
New sections added to the existing Learning page (not a new nav
item/page): Best Assets, Best Timeframes, Asset Rankings, Timeframe
Rankings, Top/Weak Indicators, Indicator Trends, Recommendation Cards.
Entirely read-only — no new buttons that write anywhere. Reuses
`metric-card`/`small-metrics-grid`/`ss-results-table`/`history-row`/
`tab-empty` — **zero new CSS**. One additive entry to the existing
`TREND_ICON` map (`declining: '📉'`) alongside the pre-existing
`degrading` key used by Phase 9's Learning page — neither key was
removed or renamed.

### Tests
Added `tests/test_phase_10_2.py` — 74 checks covering the storage layer
(accumulation math, both single-run and cross-run), the real-file
migration (byte-identical preservation of pre-existing data, idempotency,
on-disk persistence), `asset_timeframe_learning.py`'s pure functions
against hand-computed expectations, a full end-to-end
`ValidationEngine → ValidationHistoryStore → asset_timeframe_learning.py`
flow (mocked `fetch_candles`, no live network), and a re-check that
`analyzer.py`/`backtest.py`/`indicator_validation.py` are unaffected.

**Approved test-maintenance fix (not a behavior change)**: 4 assertions
in `tests/test_phase_10_1.py` hardcoded the literal schema version string
`"1.1"`, which the correct, intentional 1.1→1.2 schema bump above made
stale (not a real regression — independently re-verified). Updated those
4 assertions only, to reference `VHS_SCHEMA_VERSION` instead of a literal;
no other assertion in that file was touched, and no production code was
touched to make this change.

Full regression suite after this phase: **301/301 passing**
(51 + 34 + 142 + 74).

### Confirmed untouched (byte-diff against the Phase 10.1 Stable ZIP)
`analyzer.py`, `backtest.py`, `indicators.py`, `scanner.py`,
`settings_store.py`, `indicator_registry.py`, `backtest_engine.py`,
`indicator_validation.py`, `validation_engine.py`, `learning_engine.py`,
and everything under `quotex/api_quotex/` — confirmed byte-identical via
`diff -rq` against a fresh extraction of the Phase 10.1 Stable ZIP. Only 5
files were modified (`validation_history_store.py`, `app.py`,
`static/app.js`, `templates/index.html`, `tests/test_phase_10_1.py`),
plus 2 new files (`asset_timeframe_learning.py`, `tests/test_phase_10_2.py`).

### Known limitation (documented, not fixed here)
Same standing sandbox constraint as Phase 10.1: full Flask-app-level
(`app.py` test-client) request/response testing for the 4 new
`/api/learning/*` routes was not performed — blocked by missing
third-party dependencies not installable in this sandbox. Route wiring
verified by direct code review plus `py_compile`; every function each
route calls is directly covered by `test_phase_10_2.py`.

## Phase 10.1 — Universal Validation (all 13 confluence factors)

**Scope:** extend the Validation framework (`indicator_validation.py`,
`ValidationEngine`, the `/api/validation/*` routes, `ValidationHistoryStore`)
from measuring only the 3 OTC-specific detector-based indicators
(wick_rejection, liquidity_sweep, false_breakout) to measuring all 13
confluence factors. Adds Asset-wise and Timeframe-wise Validation Summary
aggregation. Additive-only — every function/route/file this phase touches
keeps 100% of its previous behavior available for existing callers;
nothing that worked before was rewritten.

### Pre-implementation audit (Step 1)
Compiled the full Phase 9 Stable codebase (clean) and re-ran both existing
regression suites (`test_phase_8_6.py`: 51/51, `test_phase_9_pipeline_fix.py`:
34/34 — 85/85 total) before writing any Phase 10.1 code. Audited
`indicator_validation.py`, `validation_engine.py`, `app.py`'s
`/api/validation/*` routes, and `validation_history_store.py`, and traced
`analyzer.py`'s `_confluence_factor_votes()` / `backtest.py`'s
`_factor_votes()` to establish the correct, single source of truth for
each of the 10 non-OTC factors' vote logic before deciding how to validate
them, rather than re-deriving that logic independently.

### `market_analyzer/indicator_validation.py` (additive)
- Added `UNIVERSAL_INDICATOR_NAMES` — all 13 confluence factors, mirroring
  `analyzer.DEFAULT_CONFLUENCE_WEIGHTS`'s keys and order exactly (read-only
  comparison, no import of `analyzer.py`).
- Added `validate_indicator_universal()` / `validate_all_universal()`. For
  the original 3 (`INDICATOR_NAMES`), these delegate straight to the
  unmodified `validate_indicator()`/`validate_all()` — verified
  byte-identical output, zero duplicated math. For the other 10, added a
  new vectorized bar-by-bar measurement that reuses `backtest.py`'s
  existing, unmodified `_factor_votes()` (read-only import — this module
  never calls `backtest_factor_accuracy()`/`compute_dynamic_weights()` and
  never writes anything back into `backtest.py`), computed once per
  (asset, timeframe) rather than once per indicator.
- Added `summarize_by_asset()` / `summarize_by_timeframe()` — pure
  aggregation over a flat validation-result list; no new measurement.

### `market_analyzer/webapp/validation_engine.py`
- `start()`'s indicator-name validation widened from `INDICATOR_NAMES` (3)
  to `UNIVERSAL_INDICATOR_NAMES` (13); default (when `indicators` is
  omitted) changed from the 3 to all 13 — this is the explicit point of
  "Universal Validation." Explicitly passing the original 3 still works
  exactly as before (verified: engine runs exactly those 3, not all 13,
  when requested that way).
- The per-indicator run loop now calls `validate_indicator_universal()`
  instead of `validate_indicator()` directly (identical results for the
  original 3, since that's exactly what it delegates to).
- Summary aggregation widened from `INDICATOR_NAMES` to
  `UNIVERSAL_INDICATOR_NAMES`.

### `market_analyzer/webapp/app.py`
- `/api/validation/run` and `/api/validation/history/<indicator>` now
  accept (and validate against) all 13 indicators instead of 3; `/run`'s
  default indicator list (when omitted from the request body) is now all
  13.
- Added `GET /api/validation/summary/by-asset` and
  `GET /api/validation/summary/by-timeframe` — thin, read-only routes over
  `indicator_validation.summarize_by_asset()`/`summarize_by_timeframe()`
  fed from the existing `ValidationEngine.results`. No new measurement, no
  write path.

### `market_analyzer/webapp/validation_history_store.py` — schema migration
- `KNOWN_INDICATORS` widened from 3 to 13 (schema `"1.0"` → `"1.1"`).
- **Backward-compatible migration, verified against a real synthetic
  old-format file**: an existing schema-`"1.0"` `history.json` with only
  the 3 original indicators' `rolling_stats` is, on first read under this
  version, backfilled with clean zeroed defaults for the 10 newly-known
  indicators; the 3 original indicators' accumulated stats
  (`total_samples`, `total_wins`, `average_win_rate_over_runs`, etc.) are
  preserved **byte-identically** — nothing reset, renamed, or moved. Old
  `run_log` entries (whose `per_indicator` dict only has 3 keys) remain
  valid as-is. The migration is idempotent — re-reading an already-current
  file causes no rewrite.
- **Bug found and fixed during verification**: the initial migration
  attempt correctly backfilled the 10 new `rolling_stats` entries but
  never advanced `schema_version` past `"1.0"`, because the general
  merge-missing-keys helper (`_deep_merge_missing()`) never overwrites a
  key that's already present — and it had *already* silently backfilled
  the missing indicator keys via its own recursion (since
  `_default_history()` now builds 13 keys), so the follow-up "did we just
  backfill anything?" check was comparing against data that already looked
  fully migrated and never fired. Fixed by detecting migration from the
  **pre-merge** indicator key set instead of the post-merge one. Caught by
  writing a real old-format file to disk and asserting on the actual
  written-back JSON, not just in-memory state — exactly what this
  project's audit-before-code discipline is for.

### Tests
Added `tests/test_phase_10_1.py` — 142 checks covering: universal-name-set
shape, all 13 indicators individually, byte-identical delegation for the
original 3, `validate_all_universal()` grouping/subsetting,
`summarize_by_asset()`/`summarize_by_timeframe()` arithmetic against
hand-computed expectations, `ValidationEngine` end-to-end (mocked
`fetch_candles`, no live network) for default/explicit-legacy/rejected/
mixed-subset indicator lists, the full history-store migration path
including the schema-version bugfix, idempotency, an empty-`rolling_stats`
edge case, and a final re-check that `analyzer.DEFAULT_CONFLUENCE_WEIGHTS`
and `backtest._DEFAULT_8F_WEIGHTS`/`_factor_votes()` are unchanged by this
phase. Full regression suite after this phase: **227/227 passing**
(51 + 34 + 142).

### Confirmed untouched (byte-diff against the Phase 9 Stable ZIP)
`analyzer.py`, `backtest.py`, `indicators.py`, `scanner.py`,
`settings_store.py`, `indicator_registry.py`, `backtest_engine.py`, and
everything under `quotex/api_quotex/` (the Quotex API/WebSocket layer) —
confirmed byte-identical via `diff -rq` against a fresh extraction of the
uploaded Phase 9 Stable ZIP, not just asserted. Only 4 files were modified
(`indicator_validation.py`, `validation_engine.py`, `app.py`,
`validation_history_store.py`), plus the new test file.

### Known limitation (documented, not fixed here)
Full Flask-app-level (`app.py` test client) request/response testing for
the two new summary routes was attempted but blocked by missing
third-party dependencies not installable in this sandbox (`pydantic` and
others, beyond the network-library stubs used for Phase 7.4's e2e pass).
Route wiring was verified by direct code review plus `py_compile`, and the
underlying aggregation functions the routes call
(`summarize_by_asset()`/`summarize_by_timeframe()`) are covered by
`test_phase_10_1.py` directly. Full Flask-level route testing for these
two endpoints remains an open item, consistent with this project's
standing "no live network access" sandbox constraint.

## Phase 9 — Smart Learning & Adaptive Weight System

**Scope:** a new, additive Learning module that reads accumulated Validation
History and recommends adjusted confluence weights, subject to configurable
safety limits. Advisory only — never places trades, never bypasses Hard
Gates, never changes BUY/SELL direction, never edits Validation History.

### Pre-implementation audit (Step 1) — found a real, severe blocker
Audited Confluence, Validation, Backtest, Validation History, Indicator
Registry, Filter Score, and the existing Dynamic Weight system before
writing any code. Tracing the **actual live production path** in `app.py`
(`backtest_factor_accuracy` → `compute_dynamic_weights` → settings overlay →
`generate_confluence_signal`) — not just `generate_confluence_signal()` in
isolation, which is all `test_phase_8_6.py` exercises — revealed that
`backtest.py`'s `_DEFAULT_8F_WEIGHTS` still only had the original 10
factors. Since `compute_dynamic_weights()` builds its entire output from
that dict's keys, and `generate_confluence_signal()` **replaces** (not
merges) its weights dict whenever a non-empty `dynamic_weights` is passed,
**Wick Rejection, Liquidity Sweep, and False Breakout received an effective
weight of exactly 0 on every real signal the live app ever produced**,
despite their votes being computed correctly since Phase 8.6. Verified
end-to-end with the real functions (not mocks) before concluding this was
real; stopped and reported it rather than proceeding, per this project's
own escalation rule for blockers that touch previously-approved
architecture. Approved as a prerequisite bug fix (Option A) before
continuing.

### Bug fix #1 — `backtest.py` (prerequisite, verified before Phase 9 proper)
`_DEFAULT_8F_WEIGHTS` extended from 10 to 13 keys, values realigned to
match `analyzer.DEFAULT_CONFLUENCE_WEIGHTS` exactly (7.69 × 12 + 7.72 × 1 =
100.0 — the original 10's values also had to move from the stale 10.0 each,
otherwise 13 keys would sum to 123.1 and break the reserved/remaining-budget
math). Data-only change — no rule inside `compute_dynamic_weights()` was
touched; `_factor_votes()`/`backtest_factor_accuracy()` still only score
the original 10 (extending backtested accuracy scoring to the 3 new
indicators remains the separately-tracked NEXT_PHASE.md pending item,
intentionally not done here). Re-verified end-to-end post-fix: all 13
weights now present in the live pipeline's `weights_used`, summing to
100.0.

### Bug fix #2 — `settings_store.py` (found while wiring the Apply route)
`INDICATOR_KEYS` also only had 10 entries — `apply_suggested_weights()`
only writes a weight for a key already present in `settings["indicators"]`,
so any recommended weight for the 3 new indicators would have silently
no-op'd on Apply, the exact same class of gap, just one file over. Extended
to 13 keys. Verified backward-compatible: an old-format `settings.json`
with only 10 indicator entries and a user customization on `bb` correctly
backfills the 3 new keys with their default (`enabled: true, weight: 10.0`)
via the pre-existing `_deep_merge_missing()` forward-compat mechanism,
without touching the user's existing customization.

### New: `market_analyzer/webapp/learning_engine.py`
Additive-only module — no import of `analyzer.py`/`backtest.py`/
`validation_engine.py`/`indicator_validation.py`/`scanner.py`/
`indicator_registry.py`, no write path into `validation_history.json`.
- `compute_recommendation(current_weights, history, min_weight=2.0,
  max_weight=20.0, learning_rate=0.5, min_samples=20)` — pure function. For
  any indicator without sufficient rolling Validation History (currently
  everything except wick_rejection/liquidity_sweep/false_breakout — see
  `validation_history_store.KNOWN_INDICATORS`), the recommendation is its
  current weight, unchanged, with `trend: "no_data"`. For indicators with
  enough history, the recommended weight is
  `current_weight * (1 + learning_rate * (avg_win_rate - 50) / 50)`,
  clamped to `[min_weight, max_weight]` — never below/above those bounds
  regardless of trend strength. The full weight set is renormalized to sum
  to exactly 100 afterward (same residual-to-largest convention already
  used everywhere else in this codebase).
- `LearningHistoryStore` — bounded (200-entry), atomic-write, corrupted-JSON-
  recovering JSON log of past recommendation snapshots. Same I/O pattern as
  `validation_history_store.ValidationHistoryStore`. `reset()` only clears
  this module's own log — never touches `validation_history.json`.

### New Flask routes (`app.py`, additive — every existing route unchanged)
`GET /api/learning/status`, `POST /api/learning/generate` (persists a
snapshot to history; optional JSON body overrides min_weight/max_weight/
learning_rate/min_samples), `GET /api/learning/history`,
`POST /api/learning/apply` (gate-checked — 409 if no indicator has real
Validation History data yet; reuses the existing, unmodified
`settings_store.apply_suggested_weights(reason="learning")`, same function
Backtest's "Apply Suggested Weights" already uses), `POST /api/learning/reset`.
Verified end-to-end with a stubbed Quotex dependency chain, including the
full success loop: seed Validation History → get recommendation → apply →
weight actually lands in `settings.json`.

### New Learning UI page (`index.html`/`app.js`)
Mirrors the Validation/Backtest pages' established component set exactly —
`.glass-card`/`.metric-card`/`.generate-btn`/`.secondary-btn`/
`.ss-controls-row`/`.history-row`/`.tab-empty`/`.error-box` — no new CSS
class introduced. Shows Current vs. Recommended weight per indicator with
trend/confidence/sample-count, a Recommendation History list, and Generate/
Apply/Reset buttons. Status refreshes every 15s while the tab is open (same
polling pattern as Validation/Smart Scanner), stops when navigating away.
Loading, empty, success, and error states all handled explicitly. Verified:
zero duplicate HTML ids, HTML tag balance clean, `node --check` clean, every
button has both markup and a wired listener, template renders with no Jinja
error.

### Also fixed: `.gitignore` gap
`validation_history.json` (pre-existing gap since Phase 8.5) and
`learning_history.json` (new this phase) were not covered by any gitignore
pattern — `settings.json`/`session.json`/`config.json` were, but these two
weren't. Added both to the existing Security section, same convention.

### New regression test — `tests/test_phase_9_pipeline_fix.py` (34/34)
Proves: (1) `_DEFAULT_8F_WEIGHTS` has 13 keys summing to 100.0, (2) the 3
new indicators are never silently dropped from `compute_dynamic_weights()`'s
output, (3) the original 10 factors' accuracy-to-weight formula is
mathematically unchanged — same proportional-to-accuracy split, same
near-random (≤52%) penalty rule — now correctly computed against a
76.9-point budget (100 minus the 3 previously-zeroed factors' reserved
23.1) instead of assuming a full 100, (4) the full simulated live-pipeline
path ends with all 13 weights present and non-zero, (5) the library-level
default path (no `dynamic_weights` argument) is completely unaffected.

### Testing
`python3 -m compileall` clean on the full tree; `node --check` clean on
`app.js`; `tests/test_phase_8_6.py` still 51/51; `tests/test_phase_9_pipeline_fix.py`
34/34. Full diff against the Phase 8.7 Stable baseline: exactly 6 files
modified (`backtest.py`, `app.py`, `settings_store.py`, `app.js`,
`index.html`, `.gitignore`) and 2 files added (`learning_engine.py`,
`tests/test_phase_9_pipeline_fix.py`) — nothing else.

### Explicitly NOT done, per this phase's own rules
No changes to Confluence vote logic, Hard Gates, Filter Score, BUY/SELL
direction, or confidence calculation beyond restoring the 3 missing
weights. No extension of `backtest_factor_accuracy()` to the 3 new
indicators (still the separately-tracked pending item). No auto-apply —
Apply is always an explicit, user-triggered action.

## Phase 8.7 — Final Stabilization & Release Audit (safe cleanup only, no behavior change)
**Scope:** not a feature phase — full repo/performance/security/production-readiness/UI/test/documentation
audit, followed by *safe cleanup only* after explicit approval. No algorithm, Confluence, Validation,
Scanner, API, or route changes; no new dependencies; no refactor of unrelated code.

**Audit findings (Steps 1–7, no code touched during the audit itself):**
- 4 genuinely unused imports found via occurrence-count static analysis (confirmed by hand, not just
  a heuristic): `fetch_data.py`'s `API_TIMEFRAMES`, `run_analysis.py`'s `os`, `settings_store.py`'s
  `shutil`, `validation_history_store.py`'s `List`.
- 4 stray runtime artifacts committed into the Phase 8.6 Stable upload (leftover run output, not
  source): `market_analyzer/output/candles.csv`, `market_analyzer/webapp/log-2026-07-{15,16,17}.txt`.
- One redundant (but harmless — idempotent) block in `navigateTo()` (`app.js`): a second
  `.seg-tab[data-view]` active-class pass that only ran for `name === 'scanner'`/`'analyzer'` and
  recomputed the exact same result the preceding pass already set for those two names.
- **Test coverage gap (the most significant finding):** `tests/test_phase_8_6.py` is the *only*
  persisted, re-runnable test file in the entire repository. Every earlier phase's documented suite
  (Phase 8.1, ValidationEngine, 8.4.2, 8.4.3, 8.5) was run in a sandbox at the time and never
  committed — the pass/fail counts in `TEST_REPORT.md` are accurate historical records, but none of
  those test files exist on disk today. `scanner.py`, `backtest.py`/`backtest_engine.py`,
  `settings_store.py`, `validation_engine.py`, `validation_history_store.py`,
  `indicator_validation.py`, every Flask route, and all frontend JS currently have zero automated
  coverage beyond what `test_phase_8_6.py` incidentally touches (byte-identity checks, not behavior).
  Not fixed this phase — flagged as a real gap for a future, explicitly-scoped phase.
- UI audit (all 10 pages): zero duplicate HTML ids, zero dangling `$('id')` references in `app.js`
  (3 initial hits were false positives — elements defined in JS-authored `innerHTML` strings, not the
  static template), every dynamic list has an empty-state fallback, icon-only buttons all have
  `aria-label`, zero `<form>`/`onclick=` attack surface. One cosmetic naming inconsistency noted (2 of
  10 pages use a `view-*` id prefix, the other 8 use `page-*`) — not changed, since it's naming-only,
  fully handled correctly in `navigateTo()`, and touching HTML ids risked exceeding "safe cleanup."
- Security/production-readiness: no secrets committed, `debug=False`, no bare `except:`/`eval`/`exec`/
  `subprocess`, corrupted/missing-JSON recovery confirmed working in `settings_store.py` and
  `validation_history_store.py`. `settings.json`/`session.json`/etc. confirmed correctly gitignored
  (rule lives in the parent workspace `.gitignore`, unanchored patterns match at any depth — initially
  looked like a gap, verified it isn't).
- Documentation: no mismatch found between the 4 core docs and the Phase 8.6 Stable code — nothing
  required correcting, only extending (this entry).

**Cleanup performed (Step 8, after explicit approval — 5 files changed, 4 files removed, zero files added):**
- Removed the 4 unused imports listed above — one line each, no other change to those files.
- Deleted the 4 stray runtime artifacts listed above.
- Removed the redundant `.seg-tab` active-class block in `navigateTo()` — proven behaviorally
  identical for every possible `name` value before removal (the deleted block only ever ran for
  `name === 'scanner'`/`'analyzer'`, and for those two values `b.dataset.view === name` is exactly
  the condition the preceding block already applied — so the removal is a pure no-op on runtime
  behavior). Verified with `node --check` post-edit.

**Explicitly NOT done, per this phase's own rules:** no algorithm changes, no Confluence/Validation/
Scanner logic touched, no API/route changes, no new dependencies, no refactor of anything not on the
approved cleanup list (the `view-*`/`page-*` naming inconsistency and the test-coverage gap are
flagged, not acted on).

**Testing:** `python3 -m compileall` clean on the full tree; `node --check` clean on `app.js`;
`tests/test_phase_8_6.py` still 51/51 (unaffected — none of the 5 changed files' behavior changed).
Full diff against the Phase 8.6 Stable baseline confirms exactly the 5 modified + 4 removed files
above and nothing else.

**Known limitations carried forward:** the test-coverage gap above; the `backtest.py` 10-factor/
confluence 13-factor divergence from Phase 8.6 (unchanged, out of scope); the `view-*`/`page-*` naming
inconsistency (cosmetic, not fixed).

## Phase 8.6 — Confluence Engine: connect Wick Rejection, Liquidity Sweep, False Breakout (10 -> 13 factors)
**Pre-phase audit:** extracted and inspected the full Phase 8.5 Stable upload before writing any code — `py_compile` clean across every `.py` file, a synthetic-data run confirmed the starting state exactly as documented: `DEFAULT_CONFLUENCE_WEIGHTS` at 10 factors summing to 100.0, and `wick_rejection_detail`/`liquidity_sweep_detail`/`false_breakout_detail` already present in `calculate_all()`'s output (Phase 7.3 Part 3) but not read anywhere in `analyzer.py`. No mismatch between docs and code found; proceeded.

**Changed — `market_analyzer/analyzer.py` (the only behavior change this phase):**
- `DEFAULT_CONFLUENCE_WEIGHTS` rebalanced from 10 factors x 10.0 to 13 factors x ~7.6923 (100/13), following the exact precedent set by Phase 6's SR rebalance ("keep every factor's default share equal"). 100/13 doesn't divide evenly at 2 decimals, so — same "assign the rounding residual to one weight" convention already used in `settings_store.get_effective_dynamic_weights()` — 12 factors get 7.69 and one (`false_breakout`, the last one added) gets 7.72, for an exact 100.00 sum (asserted at import time).
- Two new module constants, `WICK_REJECTION_VOTE_THRESHOLD`/`LIQUIDITY_SWEEP_VOTE_THRESHOLD`/`FALSE_BREAKOUT_VOTE_THRESHOLD = 40.0`, matching `CANDLE_RELIABILITY_VOTE_THRESHOLD`/`SR_RELIABILITY_VOTE_THRESHOLD`'s existing value and purpose (don't let a weak/marginal detector reading flip the vote).
- Three new vote blocks appended to `_confluence_factor_votes()`, reading the existing `wick_rejection_detail`/`liquidity_sweep_detail`/`false_breakout_detail` dicts (unchanged since Phase 7.3 — this phase only added a consumer of their output, not new detection logic). Same shape and pattern as the existing `candle`/`sr` blocks: `direction == "BUY"` and `reliability_score >= threshold` -> `+1`; `direction == "SELL"` and above threshold -> `-1`; otherwise (including a missing/`None` detail dict, for backward compatibility with any older-format indicators dict) -> `0`.
- `generate_confluence_signal()`'s docstring updated to list all 13 factors; the function body itself is untouched — it already iterated `votes`/`weights` dynamically, so no logic change was needed for it to handle 13 factors correctly.

**Changed — `market_analyzer/indicators.py` (documentation only, zero logic change):** the Phase 7.3 Part 3 header comment updated to reflect that the 3 detector functions are now consumed by the confluence engine — the detector functions themselves (`detect_wick_rejection`/`detect_liquidity_sweep`/`detect_false_breakout`) are byte-for-byte unchanged.

**Changed — `market_analyzer/webapp/indicator_registry.py` (documentation/comments only, zero logic change):** module docstring, `_INDICATOR_META` inline comments, `NEW_INDICATOR_IDS`'s comment block, and `get_registry()`'s docstring updated — all previously said the 3 indicators were "NOT yet in `DEFAULT_CONFLUENCE_WEIGHTS`" / "not yet connected", which became false the moment `analyzer.py` changed. `get_registry()`'s actual code was already correct and required zero changes: `weight`/`in_confluence` were always derived live from `analyzer.DEFAULT_CONFLUENCE_WEIGHTS` (imported, never duplicated), so they automatically resolve to a real weight (~7.69/7.72) and `in_confluence: True` the instant the import updates — confirmed directly.

**Zero frontend change required and none made:** `static/app.js`'s "Registered, not yet connected to the Confluence vote this phase" note is rendered conditionally on `!ind.in_confluence` (line ~1393), which is itself just a pass-through of the registry's `in_confluence` field — so the note disappears automatically for these 3 indicators once `/api/indicators` reports `in_confluence: true`, with no template/JS edit needed. Confirmed by reading `static/app.js` directly (unchanged, verified byte-identical) rather than assumed.

**Not touched, and deliberately out of scope for this phase (see NEXT_PHASE.md):** `backtest.py`'s `_factor_votes()` still only vectorizes the original 10 confluence factors — it does not yet include the 3 new ones. This was already a documented, separately-tracked pending item ("Wire the 3 new indicators into `backtest_factor_accuracy()`'s factor set") before this phase started, not something Phase 8.6 broke. `indicator_validation.py` (which already validates these 3 indicators standalone, bar-by-bar) is unrelated to and unaffected by this change. `scanner.py`, `settings_store.py`, `backtest_engine.py`, `validation_engine.py`, `validation_history_store.py`, `app.py`, `templates/index.html`, `static/app.js`, and all of `quotex/api_quotex/` — untouched, confirmed byte-identical to the Phase 8.5 Stable baseline.

**Testing:** new suite `Quotex/tests/test_phase_8_6.py` — 51/51 passing. Covers: weight-dict shape (13 factors, sum exactly 100.0); `_confluence_factor_votes()` returns all 13 keys on random synthetic data; each of the 3 new detectors fires the correct vote sign on hand-built candle sequences designed to trigger it (wick rejection BUY, liquidity sweep BUY, false breakout SELL); reliability-threshold gating (just-under-40.0 stays neutral, at-40.0-exactly votes); backward compatibility (an indicators dict with the 3 `*_detail` keys entirely absent votes neutral, no exception); `generate_confluence_signal()` end-to-end schema (including the Step 1 `confidence_raw`/`market_condition` fields, confirmed still present and unaffected); `indicator_registry.get_registry()` reflects `in_confluence: True` and a non-zero weight for all 3. A separate, sandbox-local byte-diff check (not shipped in the repo, since it depends on having the original ZIP on disk) additionally confirmed only 3 files differ anywhere in the entire project tree versus the Phase 8.5 Stable upload: `analyzer.py`, `indicators.py`, `webapp/indicator_registry.py` — everything else, including all of `quotex/api_quotex/`, is byte-identical.

**Known limitations (see also PROJECT_STATUS.md/NEXT_PHASE.md):**
- Live-signal behavior for the 3 new factors has only been exercised against synthetic candle data in this sandbox (same standing caveat as every prior phase — no live Quotex network access here).
- `backtest_factor_accuracy()`/`compute_dynamic_weights()` (`backtest.py`) do not yet score these 3 factors, so there is no backtest-derived dynamic weight for them yet — they'll always fall back to the static ~7.69/7.72 default until that separate work is done. This means the Settings/Backtest page's dynamic-weight suggestion will not include real accuracy data for these 3 factors even though they now vote live.
- The 40.0 reliability-vote threshold for all 3 new factors is carried over unchanged from the existing `candle`/`sr` convention — not independently back-tested/calibrated for these specific detectors, same honest caveat those two factors already carried.
- The rounding-residual weight assignment (`false_breakout` at 7.72 vs. 7.69 for the other 12) is a cosmetic/arbitrary tie-break for exact-100.0 math, not a statement that False Breakout is more reliable than the others.

## Phase 8.5 — Validation History Store (persistence for indicator validation results)
**Pre-phase audit:** re-verified the Phase 8.4.3 Stable baseline before writing any code — `py_compile`/`node --check` clean, all 4 existing suites passing (40/40, 46/46, 14/14, 18/18), all 12 off-limits files plus `scanner.py`/`settings_store.py`/`validation_engine.py`/`indicator_validation.py` reconfirmed byte-identical to their respective baselines, Confluence at exactly 10 factors. Audit found `ValidationEngine.results`/`.summary` are plain in-memory dicts wiped on every `start()` — nothing survives a restart or even a second run. This is the gap Phase 8.5 fills.

**Added — new file `market_analyzer/webapp/validation_history_store.py`:** a standalone, additive `ValidationHistoryStore` class, mirroring `settings_store.py`'s I/O pattern exactly (read-only reference, not imported — this module has zero dependency on it): atomic tempfile write + `os.replace()`, auto-create sane defaults on first use, forward-compatible backfill-missing-keys on read. Stores two things, both bounded: an O(1)-sized `rolling_stats` dict (one entry per known indicator, updated in place every run — never grows) and a capped `run_log` (most recent `MAX_RUN_LOG_ENTRIES=200` only, oldest dropped first — never an unbounded array). The rolling win-rate mean is gated by each run's own `combinations_with_sufficient_sample` check, so a tiny-sample run can't drag the historical trend around — the same `MIN_SIGNALS_REQUIRED` spirit applied again over time, per the Phase 8.5 audit's own risk analysis. Does not import or call `analyzer.py`, `backtest.py`, `scanner.py`, `settings_store.py`, `indicator_registry.py`, `validation_engine.py`, or `indicator_validation.py` — it only accepts a `summary` dict already computed by `ValidationEngine._build_summary()` and persists/rolls it up; no new statistic is invented.

**Added — `app.py` (additive only; the existing 6 `/api/validation/*` routes are byte-for-byte unchanged — confirmed via diff):**
- Import + `_validation_history_store = ValidationHistoryStore(...)` instantiation, same fixed-path/gitignored convention as `settings.json`.
- `_maybe_persist_validation_history()` — the **app.py-polling-and-persist** mechanism (per explicit decision: zero changes to `validation_engine.py`, no callback/hook added inside it). Checks `_validation_engine.status()`; if `STOPPED` with a `finished_at` not yet recorded, persists via `record_run()`. Called only from the 3 new routes below — the existing `GET /api/validation/status`/`GET /api/validation/results` routes are completely untouched, so persistence only actually happens once something polls one of the new routes (not on every existing status poll).
- 3 new routes: `GET /api/validation/history` (full rolling stats + run log), `GET /api/validation/history/<indicator>` (per-indicator view, 400 on an unrecognized name), `POST /api/validation/history/reset` (explicit, user-initiated only).
- `Optional` added to `app.py`'s existing `from typing import Any, Dict` line (needed for one new type hint) — the only change to a previously-existing line in the whole file.

**Testing:** new isolated store suite (`test_validation_history_store.py`): 40/40 — auto-create, rolling accumulation math, sufficient-sample gating on the trend mean, insufficient-sample/all-failed runs logged but not polluting rolling stats, bounded `run_log` capping (210 runs recorded → capped at 200), `get_indicator_history()` for known/unknown indicators, `reset()`, true persistence across a simulated restart (new instance, same file), forward-compatible backfill on an old-shaped file, no leftover `.tmp` file, unrecognized-indicator-name safety. New Flask API suite (`test_validation_history_api.py`): 15/15 — including confirming the existing `status`/`results` routes return identical shapes post-change, confirming polling `/api/validation/history` twice doesn't double-record the same run, and documenting one non-bug: `POST /api/validation/history/reset` clears the on-disk store but doesn't rewind `app.py`'s in-memory `_last_persisted_validation_run_at` dedup guard, so the very next history poll can immediately re-persist the already-completed run's summary — expected, not a defect, since the underlying `ValidationEngine` state itself wasn't reset. All 4 pre-existing suites re-run and passing (40/40, 46/46, 14/14, 18/18).

**Compatibility confirmed:** all 12 off-limits files, plus `scanner.py`, `settings_store.py`, `validation_engine.py`, and `indicator_validation.py`, byte-identical to their pre-Phase-8.5 state. Confluence still exactly 10 factors, 3 new indicators still disconnected. No Validation UI change this phase (persistence is backend-only; the UI's session-only History section from Phase 8.4.3 is unaffected and still works as before).

## Phase 8.4.3 — ValidationEngine, Validation Routes, Concurrency Bug Fix, and full Validation UI
**Pre-phase audit found a real mismatch and stopped:** the task assumed a `ValidationEngine` class and `/api/validation/*` routes already existed from Phase 8.4.2. Neither did — `indicator_validation.py` (Phase 8.4.2) is plain functions (`validate_indicator`/`validate_all`), and `grep`ing the whole repo found no `ValidationEngine` anywhere and no validation routes in `app.py` (the only "validation" hits were the unrelated Quotex-session-validation feature from Phase 7.4). Per this project's standing rule ("if documentation/instructions disagree with the code, the code is the source of truth — stop and report"), this was reported before any code was written, and the user confirmed proceeding with building the missing pieces as part of this phase.

**Added — new file `webapp/validation_engine.py`:** a thin `ValidationEngine` class wrapping `indicator_validation.validate_indicator()` (Phase 8.4.2, imported, never modified/duplicated), mirroring `backtest_engine.py`'s async lifecycle pattern as closely as possible: `STOPPED`/`RUNNING`/`PAUSED` states plus one addition explicitly requested — `STOPPING`, a transitional state between a stop() request and the loop actually halting. Sweeps `(asset, timeframe)` pairs (not just assets, since validation needs both dimensions), running all requested indicators per combination. `start()`/`stop()`/`pause()`/`resume()`/`status()`/`get_results()` — same method names and same "explicit args win, single-run-at-a-time" guarantees as `BacktestEngine`. Fetches candles via a caller-supplied `fetch_candles` callable — app.py wires this to the exact same `_backtest_fetch_candles()` closure `BacktestEngine` already uses, so no new fetch/session logic and no second Quotex connection path exists.

**Concurrency bug found and fixed (in this new file only):** `pause()`/`resume()`/`stop()` mutated `self._pause_event` (an `asyncio.Event`) directly from the Flask request thread — a different OS thread than the one running `_BG_LOOP`. `Event.set()` schedules its wake-up via `loop.call_soon()`, which is not thread-safe and does not interrupt the loop's blocking `epoll_wait()`. This was invisible in the first isolated lifecycle test (the synthetic fetch used `asyncio.sleep()`, whose internal timer gave the loop incidental real wake-ups anyway); it reproduced 100% of the time once tested through the real Flask app with a synchronously-failing fetch (no live Quotex network in this sandbox). Fixed by storing the loop reference at `start()` time and routing all three methods' event mutation through `loop.call_soon_threadsafe(...)`. Confirmed fixed via a 5-trial concurrency stress test (265-combination workload) — 100% of trials correctly paused, resumed, and processed every combination afterward. This fix is scoped entirely to `validation_engine.py` (new this phase, not off-limits); the same underlying pattern exists in `scanner.py`/`backtest_engine.py` too but those were not touched (off-limits) — flagged as a latent risk for awareness, not acted on.

**Added — `app.py`:** import block for `ValidationEngine`/`VALIDATION_CANDLE_OPTIONS`/`INDICATOR_NAMES` (mirrors the existing `BacktestEngine` import exactly); `_validation_engine = ValidationEngine(fetch_candles=_backtest_fetch_candles)` instantiated right after `_backtest_engine`; 6 new routes — `POST /api/validation/run`, `POST /api/validation/pause`, `POST /api/validation/resume`, `POST /api/validation/stop`, `GET /api/validation/status`, `GET /api/validation/results` — mirroring the exact 400/409/500 status-code pattern the backtest routes already use. No existing route, import, or line was modified — every change is a pure addition.

**Testing:** `py_compile` clean. New isolated lifecycle suite (`test_validation_engine.py`): 46/46. New Flask API + concurrency stress suite (`test_validation_api.py`): 18/18, including a 5-trial repeated concurrency regression test for the bug above. Existing Phase 8.1 regression suite: 40/40 (unaffected). Phase 8.4.2 validation suite: 14/14 (unaffected, `indicator_validation.py` untouched). All 12 off-limits files reconfirmed byte-identical to the original upload; `scanner.py`/`settings_store.py` reconfirmed byte-identical to the Phase 8.3 Recovery baseline specifically (not just the original pristine zip, since those two were legitimately modified in earlier phases). Confluence reconfirmed at exactly 10 factors.

**Also added — Validation UI (`templates/index.html`, `static/app.js` only — no backend file touched):** a full `page-validation` page, built and approved incrementally across 8 steps: (1) nav entry + page container, (2) Settings panel (asset/timeframe/indicator selectors, candle count/lookahead dropdowns, all reusing existing `.chip-toggle`/`.asset-grid`/`.field-select` components), (3) Controls card with a new status badge (`.v-status-badge`, ~7 lines of additive CSS reusing existing color tokens — the only new CSS this phase), (4) Progress card (percent/current asset-timeframe-indicator/processed-total combinations/elapsed/ETA), (5) 3 per-indicator Summary cards, (6) 11-column Results table (reusing `.ss-results-table` directly, no duplicate class), (7) session-only read-only History (reusing `.history-row`/`.history-list` from the Signal History page), (8) full API wiring: `initValidationPage()` reads the Settings panel into a request body, wires Run/Pause/Resume/Stop to the real routes, and a self-managing `pollValidationStatus()` (same pattern as `pollScannerStatus()`) that polls only while running and stops on tab-leave. One bug was introduced and caught during this work: a text-replacement step accidentally dropped a comment-block delimiter, breaking JS parsing — caught immediately by `node --check`, fixed by restoring the missing line (purely cosmetic, 4 lines, no logic change). Render functions (`vRenderSummaryCards`/`vRenderResultsTable`/`vRenderProgress`/`vAppendToHistory`) were verified by direct Node execution against a real validation results payload (not just shape-checking) — confirmed correct output (e.g. "54.74% / 380 samples / Validated" for a real Wick Rejection result). **Known, honestly-flagged limitation:** `validate_indicator()` doesn't compute per-direction (BUY vs. SELL) accuracy, so those two table/summary columns render "N/A" rather than a fabricated number — would require a `validation_engine.py`/`indicator_validation.py` change, out of scope without explicit approval.

**Not done this phase:** No dynamic weight, reliability score, or strength score calculation from these results yet (that's Phase 8.4.3's original roadmap item, effectively folded into a later step — see NEXT_PHASE.md). No write to `indicator_registry.py`. No Confluence connection.

## Phase 8.4.2 — Indicator Validation Framework
**Pre-phase audit:** re-verified the Phase 8.3 Recovery Baseline before writing any code — `py_compile` clean, Phase 8.1 regression suite 40/40, confluence confirmed at exactly 10 factors, all 3 new indicators confirmed still absent from `_confluence_factor_votes()`, single `ScannerEngine(` instance confirmed, scanner default `STOPPED` confirmed, and all 12 off-limits files re-diffed byte-for-byte against the original project upload — identical, zero mismatches. No mismatch found; proceeded.

**Added — new file `market_analyzer/indicator_validation.py`:**
- A standalone, additive bar-by-bar validation framework for the 3 new indicators (Wick Rejection, Liquidity Sweep, False Breakout). Built as a genuinely new module rather than an extension of `backtest.py`, because the Phase 8.4.1 audit found `backtest.py`'s `_factor_votes()` only vectorizes the existing 10 confluence factors — the 3 new detectors are single-call, non-vectorized functions structurally incompatible with that approach.
- `validate_indicator(df, name, asset, timeframe, lookahead=4)` — replays one indicator across an expanding window ending at each bar (mirroring how live/scanner code already calls these detectors), compares each fired signal's direction against the forward return `lookahead` bars later, and returns: `indicator`, `asset`, `timeframe`, `samples`, `buy_signals`, `sell_signals`, `no_signal_count`, `wins`, `losses`, `win_rate`, `accuracy`, `reliability`, `average_strength`, `average_reliability`, `average_holding_result`, `sufficient_sample`, `lookahead`.
- `validate_all(candle_sources, indicators, lookahead)` — runs `validate_indicator()` across every `(asset, timeframe) -> DataFrame` entry in a caller-supplied dict, naturally supporting multiple assets and multiple timeframes in one call.
- Mirrors `backtest.py`'s `MIN_SIGNALS_REQUIRED = 20` gate as an independent constant (same "mirror the value, don't cross-import" convention `backtest.py` itself already uses for `analyzer.py`'s threshold constants) — below this sample size, `reliability` is reported as `None` rather than a number that looks more trustworthy than it is. `accuracy` and `win_rate` are the same measurement (direction-correct vs. forward-return sign), kept as two separate keys only because the task specified both names, not because two different computations exist. `average_holding_result` is a stated interpretation (mean forward price change over `lookahead` bars) since the term wasn't formally defined.
- Does **not** fetch any candle data itself — every function takes an already-fetched `DataFrame`, matching `backtest.py`'s own "never duplicate the fetch system" convention. Does **not** import from, call, or modify `backtest.py`, `analyzer.py`, or any Confluence/Dynamic-Weight code. Does **not** write to `indicator_registry.py` (a possible future step, not this phase) or compute/apply any dynamic weight.

**Testing:** see `TEST_REPORT.md` for the full 14-test breakdown and the real-data validation run's results, including a significant directional-bias finding (near-universal SELL, 1 BUY out of 152 total signals across every asset/timeframe/indicator combination tested).

**Compatibility confirmed:** `analyzer.py`, `backtest.py`, `indicators.py`, and all other off-limits files are byte-identical to the original project upload (diffed directly, not just checksummed). No Confluence change, no dynamic-weight computation, no voting change, no `backtest_engine.py`/`indicator_registry.py` change. The 3 indicators remain fully disconnected from Confluence — nothing in this phase touches that boundary.

## Phase 8.3 — Smart Scanner Advanced Controls & Settings Integration
**Pre-phase audit (required before any code):** re-verified Phase 1-8.2 against actual code (not just docs) via `py_compile` on every touched module, a full re-run of the Phase 8.1 isolated test suite (40/40), and — this phase — a byte-for-byte `diff` of every off-limits file against the original, never-touched project zip (`analyzer.py`, `backtest.py`, `indicators.py`, `config.py`, `fetch_data.py`, `run_analysis.py`, `deep_backtest.py`, `indicator_registry.py`, `backtest_engine.py`, `preflight_check.py`, `gunicorn.conf.py`, everything under `quotex/api_quotex/`, `quotex/login.py`) — all identical (only difference: an auto-generated `__pycache__` directory, not source). Also re-confirmed via `grep` that none of the 3 new indicators (Wick Rejection, Liquidity Sweep, False Breakout) appear anywhere in `_confluence_factor_votes()`/`DEFAULT_CONFLUENCE_WEIGHTS` — still fully disconnected from Confluence, as required.

**Bug found and fixed (pre-existing, not introduced this phase) — `scanner.py`:** `get_results()`'s ranking tie-break on freshness compared raw ISO-8601 strings with no negation. Since `candidates.sort(key=_rank_key)` sorts ascending by default, this meant ties resolved oldest-first — the opposite of the adjacent code comment's own claim ("last_update (freshness) desc") and the opposite of this phase's explicit sort-order requirement. Fixed by adding a shared `_parse_iso_epoch()` static helper (also now used by `_cleanup_stale_cache()`, which previously had its own inline copy of the identical parse-with-try/except logic) and negating the resulting epoch in the sort key. `filter_score`/`confidence`/`payout` ordering were already correct and are unaffected. Verified with a dedicated test: two cache entries with identical filter_score/confidence/payout but different `last_update` now rank with the fresher one first (previously ranked the older one first).

**Added — `scanner.py`:**
- `self.current_timeframe` (set to the timeframe currently being scanned inside the per-asset loop, reset to `None` alongside `current_asset` at cycle/asset-loop end) — exposed as `current_timeframe` in `get_status()`.
- `self._last_scan_time` (epoch of the most recent per-timeframe scan attempt, success or failure — updated right after each attempt, same "counts attempts not just successes" semantics as `assets_completed`) — exposed as `last_scan_time` (ISO string) in `get_status()`.

**Added — `settings_store.py`:**
- `reset_section(section: str)` — resets exactly one top-level settings section (e.g. `"scanner"`) to its default value from `_default_settings()`, leaving every other section (indicators, backtest, filters, etc.) untouched. Raises `KeyError` on an unrecognized section name rather than silently no-op'ing. The existing `reset()` (full reset, used by the pre-existing global "Reset Settings" action) is completely unchanged.

**Added — `app.py`:**
- `POST /api/scanner/settings/reset` — thin wrapper around `settings_store.reset_section("scanner")`. Does not touch `_scanner` in any way (per spec, settings changes only take effect on the *next* `start()`).

**Added — Frontend (`templates/index.html`, `static/app.js`, `static/style.css`):**
- New Scanner Settings card on the Smart Scanner page: Enabled Assets (All-OTC/Choose… chip picker, reusing the exact UX pattern already established on the Backtest page's asset picker — same `.asset-chip`/`.asset-grid` CSS, no new picker paradigm introduced), Enabled Timeframes (Default/Choose… chip picker over the existing `timeframes` Jinja list), Minimum Filter Score (range slider, 0-100, live value display), Top Signals + Scan Interval (dropdowns; a "Default" option maps to `null`, matching `settings_store.py`'s existing null-means-default convention from Phase 8.1), Scanner Enabled (the existing `.switch` toggle component, reused), and Save/Reload/Reset buttons.
- `ssLoadSettings()` fetches `GET /api/settings` and populates the form automatically on first page visit (`initSmartScannerPage()`). `ssReadFormAsPatch()` builds a `{scanner: {...}}` patch from the current form state for Save. Reset calls the new scoped route and repopulates the form from its response. None of these three ever call any `/api/scanner/start|stop|pause|resume` route — settings and lifecycle stay fully decoupled, confirmed by an explicit test that saving settings while the scanner is `RUNNING` does not change its state.
- Status panel gained Current Cycle, Current Timeframe, Last Scan Time (rendered via a new `fmtAge()` helper for relative "Xs ago" display).
- Results table expanded from 8 to 11 columns: Rank, Asset, Timeframe, Direction, Confidence, Filter Score, Passed Filters, Failed Filters, Payout, Age, Last Update. All ranking/sorting continues to happen server-side in `get_results()` (unchanged — this phase only fixed the freshness tie-break bug noted above); the frontend purely renders the already-ranked list.
- `navigateTo()`: leaving the Smart Scanner tab now also calls `stopScannerPolling()` (previously polling only stopped when the scanner itself stopped). This only affects the client-side UI refresh timer — the scanner keeps running server-side regardless, exactly as before; revisiting the tab resyncs automatically via the existing self-managing `pollScannerStatus()`.

**Compatibility confirmed:**
- Settings changes never auto-restart a running scanner — verified by an explicit test: `POST /api/settings` with a scanner patch while `state == RUNNING` leaves the state `RUNNING`, unchanged, immediately after.
- Settings persist across a restart — verified by instantiating a brand-new `SettingsStore` pointed at the same file path (simulating a fresh process) and confirming previously-saved values were read back correctly.
- `analyzer.py`, `backtest.py`, `indicators.py`, `config.py`, `fetch_data.py`, `run_analysis.py`, `deep_backtest.py`, `indicator_registry.py`, `backtest_engine.py`, `preflight_check.py`, `gunicorn.conf.py`, and everything under `quotex/api_quotex/` + `quotex/login.py` are byte-identical to the original project upload (diffed directly against it, not just checksummed against a prior in-session snapshot).
- Exactly one `ScannerEngine(` instantiation in `app.py`; no second settings store; no new WebSocket/Quotex API code.

**Performance (see TEST_REPORT.md for full numbers):** all four benchmarked operations — `GET /api/settings`, `POST /api/settings`, `GET /api/scanner/status`, `GET /api/scanner/results` — average well under 1ms per call; no measurable regression from Phase 8.2.

**Not done (deferred to Phase 8.4+, per explicit instruction to stop after 8.3):** any change to `analyzer.py`, the confluence engine, dynamic weights, or connecting the 3 new indicators — none of that was in scope this phase and none of it was touched.

## Phase 8.2 — Smart Scanner (user-facing UI)
**Added — `templates/index.html`:**
- New `<section id="page-smart-scanner">` page: control card (Start/Stop/Pause/Resume + error box), progress card (state/percent/progress-bar/current-asset/assets-completed/elapsed/ETA, same visual pattern as the existing Backtest progress card), and a ranked-signals results table.
- New drawer-nav link `data-nav="smart-scanner"` and a matching quick-link button on the Settings page's quick-links row.

**Added — `static/style.css`:**
- `.ss-controls-row`, `.ss-results-table` (+ `.buy`/`.sell` direction cell coloring, using the existing `--bull`/`--sell` variables) — new classes only, no existing rule modified.

**Added — `static/app.js`:**
- `smart-scanner` registered in the `VIEWS` array; `navigateTo()` extended with one new show/hide line and one new `initSmartScannerPage()` call — same pattern as every other tab-page.
- `ssRenderStatus()`, `ssRenderResults()`, `loadScannerResults()`, `pollScannerStatus()`, `stopScannerPolling()`, `ssShowError()`, `initSmartScannerPage()` — all new functions, mirroring the existing `bt*`/`pollBacktestStatus` pattern. Reuses the existing top-level `fmtLabel()`/`fmtSeconds()` helpers rather than duplicating them.
- `pollScannerStatus()` is self-managing: every call (whether from the 2s interval, a button click, or the first page visit) checks the freshly-fetched `running` field and starts/stops its own `setInterval` accordingly — so polling stops the instant the server reports `running: false`, even if the scanner was stopped from a different tab or device, not just this page's own Stop button.
- Button visibility (`hidden` attribute) is derived purely from the polled status (`running`/`paused`), never from which button was last clicked — so two open tabs, or a scan already running when the page is (re)visited, both render correctly.

**Behavior confirmed unchanged / preserved:**
- No new `ScannerEngine`, no new `/api/scanner/*` routes, no new WebSocket or Quotex API code — this phase is 100% frontend, calling routes that already existed and were tested in Phase 7/8.1.
- Scanner still never auto-starts: page load, tab navigation, and revisiting the tab all only issue a `GET /api/scanner/status` (read-only) — confirmed via a dedicated test that the scanner's state is `STOPPED` immediately after `app.py` import/first page render, before any button is pressed.
- Still exactly one scanner instance, one shared Quotex connection, one shared background loop (`_BG_LOOP`) — confirmed via source grep (`ScannerEngine(` appears exactly once in `app.py`).

**Bugs found:** None in the modified files. (A test-harness bug was found and fixed in the *test script itself* — an initial lifecycle test asserted `STOPPED` immediately after `stop()` using a fixed `sleep(0.3)` instead of polling with a timeout, which is too short given the scan loop only checks the stop flag between asset attempts; switching to a `wait_until()` poll — the same pattern already used in the Phase 8.1 test suite — resolved it. This was a test-script timing issue, not a `scanner.py` defect; Phase 8.1's `stop()` behavior was not changed.)

## Phase 8.1 — Smart Scanner Core Enhancement (SettingsStore integration + progress tracking)
**Added:**
- `scanner.py`: `ScannerEngine.__init__` gained an optional `settings_store=` parameter (duck-typed, default `None`). New private helper `_read_scanner_settings()` — defensive read of `settings_store.get()["scanner"]`, returns `None`/`{}` and logs an event on ANY failure rather than raising, so a missing or corrupt settings store can never break scanner startup or the loop.
- `start()` now reads (when a settings_store was supplied): `scanner_enabled` (blocks the start with `{"ok": False, ...}` if `False` — does not force-stop an already-running scan), `enabled_timeframes`, `top_signals`, `scan_interval`, `enabled_assets` (narrows the per-run scan list into a new `self._effective_assets`, falling back to the full asset list if the configured subset doesn't intersect known assets), and `minimum_filter_score` (stored as `self._minimum_filter_score`, applied as an extra gate in `get_results()`). Explicit `start()`-call arguments always take precedence over settings values, consistent with the precedence pattern `app.py` already uses for filter-score overrides.
- `get_status()`: added `assets_completed`, `percent_complete`, `elapsed_time`, `estimated_remaining` (mirrors `backtest_engine.py`'s `status()` field style/semantics). `total_assets` now reports `len(self._effective_assets)` instead of always `len(self._assets)` — identical value in the default case (no `enabled_assets` configured). Added `settings_enabled` (bool, whether a settings_store was supplied) and `minimum_filter_score` fields for operator visibility.
- `get_results()`: added the `minimum_filter_score` gate (applied after the existing `mandatory_pass` check; a value of `0.0` — the default — excludes nothing beyond what was already excluded).
- New alias methods `status()` and `results()` — call `get_status()`/`get_results()` with no behavior change. Nothing internal calls the new names; the scan loop and existing Flask routes still use `get_status()`/`get_results()`.
- `settings_store.py`: 6 new keys added to the existing `"scanner"` section of `_default_settings()` — `scanner_enabled` (default `True`), `enabled_assets` (default `[]`), `enabled_timeframes` (default `[]`), `scan_interval` (default `None`), `minimum_filter_score` (default `0.0`), `top_signals` (default `None`). Existing keys in that section (`refresh_seconds`, `asset_gap_seconds`, `top_n`, `min_confidence`) untouched. `_deep_merge_missing()` (unmodified) backfills these into any pre-existing `settings.json` on next read, so no migration step is needed.
- `app.py`: `SettingsStore` instantiation moved earlier in the file (before `ScannerEngine`'s instantiation — same code, new position) so it can be passed to the scanner; `_scanner = ScannerEngine(...)` call now also passes `settings_store=settings_store`. This is the only functional line changed in `app.py` this phase.

**Compatibility:** `analyzer.py`, `backtest.py`, `indicators.py`, `config.py`, `fetch_data.py`, `indicator_registry.py`, `backtest_engine.py`, and everything under `quotex/api_quotex/` are byte-unchanged this phase (confirmed via checksum comparison before/after). No new `ScannerEngine` or duplicate websocket/login system was created — `scanner.py` remains the single scanner implementation, and `app.py` still constructs exactly one module-level `_scanner` instance.

**Design decisions:**
- `scanner_enabled=False` blocks only *new* `start()` calls. It does not force-stop a scan already in progress — the spec named "start only after user action" and "stops when requested" as the lifecycle contract; auto-stopping a running scan based on a settings change mid-run would be new behavior, not something requested, so it was deliberately left out.
- Settings-provided `enabled_assets`/`enabled_timeframes`/etc. are captured once, at `start()` time, into `self._effective_assets` / `self.cfg` — not re-read continuously during a running cycle. This mirrors the existing pattern where `start()`'s explicit args are also captured once at start time, and avoids restructuring `_scan_loop()`'s per-asset iteration to poll settings on every asset (a larger change than the additive scope called for).
- New setting keys were added as six *new* keys distinct from the pre-existing `top_n`/`refresh_seconds`/`min_confidence` (rather than renaming those), because the pre-existing keys are already wired into the tested Phase 7.4 Settings UI/routes under those names — renaming them would not be additive and would risk breaking that existing surface.

**Not done (out of scope for 8.1, per explicit instruction to stop after this phase):** a genuine user-facing Scanner page wired to these routes/fields (Phase 8.2+); any change to the client-side "Auto Scanner" tab in `static/app.js`, which remains the separate, pre-existing loop it always was.

## Phase 1-3 — Audit & Foundation
**Added:** `.env.example`, `preflight_check.py`, security `.gitignore` patterns.
**Changed:** `start-prod.sh` now runs preflight check before Gunicorn.
**Fixed:** N/A (audit phases — corrected an earlier mistaken "import bug" claim, no real bug found).
**Compatibility:** No existing behavior changed.

## Step 1 — Confidence Dampener
**Added:** `_apply_market_condition_dampener()` in analyzer.py; `confidence_raw`, `market_condition` fields (additive).
**Changed:** `generate_confluence_signal()` output now dampens confidence on weak ADX / extreme volatility.
**Compatibility:** Additive fields only; dampening never flips signal direction or creates a signal from WAIT.

## Step 2 — MTF Transparency
**Added:** `multi_tf_status` field (`CONFIRMED`/`DISAGREED`/`UNAVAILABLE` + reason + timeframe_checked).
**Changed:** Silent MTF failures now report a reason instead of `None`.
**Compatibility:** Existing `multi_tf` field byte-unchanged.

## Step 3 — Unified MIN_SIGNALS_REQUIRED
**Fixed:** Two separate thresholds (10 in one function, hardcoded 20 in another) unified to a single constant = 20 (the value that was already effectively binding).
**Performance:** No behavior change (verified via equivalence testing).

## Step 4 — OBV Integration
**Added:** `_obv_series` in `calculate_all()`; OBV divergence as 9th confluence factor.
**Changed:** `DEFAULT_CONFLUENCE_WEIGHTS`/`_DEFAULT_8F_WEIGHTS` rebalanced 8→9 factors (12.5 each → ~11.11 each).
**Fixed:** `_FACTOR_LABELS` in app.py was missing OBV — found and fixed same session.

## Phase 5 — Candlestick Engine Upgrade
**Added:** `detect_candlestick_pattern_detailed()` — 9 patterns (added Inverted Hammer, Shooting Star, Morning Star, Evening Star, Inside Bar) with geometry-derived strength/reliability scores.
**Changed:** `detect_candlestick_pattern()` kept as a byte-identical backward-compatible string wrapper. Confluence engine now gates candle votes by `reliability_score >= 40`.
**Performance:** Backtest candle-detection loop cost increased ~3x (45ms→130ms) due to richer per-bar geometry — documented, not hidden.

## Phase 6 — Support/Resistance Zone Engine
**Added:** `detect_support_resistance_zones()` — swing detection, ATR-based zone merging, geometry-derived strength; 10th confluence factor `sr`.
**Changed:** Weights rebalanced 9→10 factors (10.0 each exactly).
**Compatibility:** Original `support_resistance()` (min/max) function untouched, byte-identical.

## Phase 7 — Smart Scanner + Filter Score v1
**Added:** `scanner.py` (full async engine), `calculate_filter_score()` v1 (binary all-or-nothing per mandatory gate), 5 scanner routes.
**Fixed (found in Phase 7 validation):** Scanner's `_check_hard_gates()` duplicated gate logic — refactored to call `calculate_filter_score()` as single source of truth.
**Fixed:** Ranking bug — `failed_filters` non-empty (e.g. missing candlestick) incorrectly excluded valid signals; fixed to key off `filter_score`.

## Phase 7.1 — Graded Filter Score
**Changed:** Filter Score rewritten from binary (0 or 93-100) to graded per-criterion bands. Added `mandatory_pass` field, decoupled from `filter_score`'s value.
**Fixed:** Scanner visibility filter updated to use `mandatory_pass` (required, since `filter_score` no longer implies gate-passing).
**Fixed:** `backtest_filter_score_report()` referenced an undefined `_FS_SR_NEAR_ZONE_ATR` constant — added.
**Performance:** `calculate_filter_score()` overhead confirmed <0.02% of pipeline cost.

## Phase 7.2 — Settings Store + Backtest Engine
**Added:** `settings_store.py` (full: get/update/reset/backup/restore/export/import/effective-weights). `backtest_engine.py` (full: STOPPED/RUNNING/PAUSED state machine, reuses `backtest.py` exactly).
**Fixed (found in testing):** `evaluate_apply_conditions()` didn't check the run's actual candle count against the policy minimum — only internal consistency. Fixed.
**Compatibility:** Neither module modifies `analyzer.py`, `scanner.py`, or the confluence engine. No routes/UI added yet.

## Phase 7.3 (partial) — Indicator Registry + New Indicators
**Added:** `indicator_registry.py` (13-entry metadata registry). 3 new indicators: `detect_wick_rejection()`, `detect_liquidity_sweep()`, `detect_false_breakout()` — additive keys in `calculate_all()`.
**Compatibility:** Confirmed NOT connected to the confluence engine (deliberate, per explicit instruction — a future step).
**Not done:** Settings/Backtest routes+UI, Quotex session page, remaining Phase 7.3 parts — see NEXT_PHASE.md.

## Phase 7.4 — Settings/Backtest/Indicators/Session: routes, `_run_pipeline()` wiring, and full frontend
**Added (backend):**
- `webapp/app.py`: instantiated `SettingsStore` and `BacktestEngine` (the latter's `fetch_candles` wraps the SAME `_get_shared_fetcher()` machinery `_run_pipeline()` already used — no second Quotex connection path).
- Settings routes: `GET/POST /api/settings`, `POST /api/settings/reset`, `GET /api/settings/backups`, `POST /api/settings/backups/restore`, `GET /api/settings/export`, `POST /api/settings/import`, `POST /api/settings/backup`.
- Backtest routes: `POST /api/backtest/run|pause|resume|stop`, `GET /api/backtest/status|results`, `POST /api/backtest/apply-weights` (gate-checked via `evaluate_apply_conditions()`, unmodified).
- `GET /api/indicators` — the 13-entry registry, overlaid with Settings' enable/disable/weight, and (new) layered with real accuracy/dynamic_weight/sample_size from the most recently completed backtest run (`_backtest_engine.results`/`.summary`, read-only — no `backtest_engine.py` changes).
- Quotex Session routes: `GET /api/session/status`, `POST /api/session/update` (writes only to `quotex/session.json`, never an env var), `POST /api/session/validate` (forces a reconnect via the existing `connect()` path; reports Server/Gateway/Session-Valid together — see honesty note in the route's docstring, since the underlying client has no separate stage events).
**Added (frontend — new this phase; previously zero UI existed for any of this):**
- Settings page: dynamic editable form (General/Filters/Scanner), Save/Reset/Backup/Restore/Export/Import.
- Backtest page: asset picker (All OTC or custom), timeframe + candle-count selects, Run/Pause/Resume/Stop, live progress bar with ETA (2s polling), results table (suggested weights + min sample sizes), "Apply Suggested Weights" with gate-rejection reasons shown inline.
- Indicators page: all 13 indicators listed (10 confluence-connected + 3 not-yet-connected, clearly badged as such — toggling a not-yet-connected indicator is disabled with an explanatory tooltip since it would have zero effect on live signals), enable/disable toggle, weight/dynamic-weight/accuracy/sample-size display.
- Quotex Session page: status card (active source, session-file presence, fetcher connectivity, last validation), SSID paste + save, "Validate Session" with a Server/Gateway/Session-Valid readout.
- Quick-links row on the Settings page and 3 new drawer-nav entries for one-tap access to the 3 new pages; bottom nav left at 5 items (unchanged) to avoid mobile crowding.
**Changed:**
- `_run_pipeline()` now layers Settings' indicator enable/disable + weight-scale on top of the already-computed dynamic weights (live backtest-derived or precomputed — unchanged), and passes Settings' filter-score threshold overrides into `calculate_filter_score()`'s existing `config` parameter. Both are pure no-ops at default settings (verified byte-identical) — see the design-decision note below.
- `backtest_engine.CANDLE_OPTIONS` expanded from `(500, 1000, 2000, 5000)` to `(500, 1000, 1500, 2000, 3000, 5000)`; `settings_store.py`'s matching default synced.
- **Auto Scanner bug fixed:** the client-side scan loop (`static/app.js`) previously auto-started via `navigateTo('scanner')`, which ran unconditionally on every page load (`navigateTo('scanner')` at the bottom of `app.js`). Decoupled scan start/stop entirely from tab navigation; added an explicit "Enable Auto Scanner" toggle (in-memory `_autoScanEnabled` flag, never persisted to storage) as the only way to start it, plus a `beforeunload` handler to stop it. A fresh page load — or reopening the site — now always starts with the scanner OFF, satisfying the "never auto-start" requirement without any special-case "first load" logic (the flag simply defaults to `false` every time the script runs).
- `.gitignore`: added `settings.json` / `settings.json.backups` to the existing Security section.
**Fixed (found during Phase 7.4 regression testing):**
1. `settings_store.get_effective_dynamic_weights()`'s renormalization rounded each factor independently, which could leave the sum a few `0.0001` short of 100 (e.g. disabling one of 10 indicators produced 9 × 11.1111 = 99.9999, not 100.0) — breaking the documented "always sums to 100" invariant. Fixed by assigning the rounding residual to the largest weight; fuzz-tested across 200 randomized disable-subsets, sum is now always exactly 100.0 (or 0.0 if everything is disabled). The same fix was applied to the analogous rounding step in `app.py`'s new `_apply_settings_weight_overrides()`.
2. `/api/backtest/run` returned HTTP 409 for every `BacktestEngine.start()` failure, including a client input error (invalid `candle_count`) that should have been 400 — because `start()` returns the same `{"ok": False, "message": ...}` shape for both "already running" and "invalid input" (unmodified, by design, per its docstring). Fixed in `app.py` by checking the actual conflict condition (`state != STOPPED`) before calling `start()`, so 409 is reserved for a genuine concurrent-run conflict, 400 covers malformed/invalid input (including non-list `assets`, non-numeric `candle_count`, unknown asset symbols, invalid timeframe), and a new try/except around the `start()` call itself returns 500 only for a genuinely unexpected internal error.
**Compatibility:** `analyzer.py`, `scanner.py`'s core loop, `backtest.py`, the confluence engine, `calculate_filter_score()`'s formula, the Dynamic Weight algorithm, and everything in `quotex/api_quotex/` remain byte-unchanged this phase. Verified via the same "settings overlay is a no-op at defaults" test used for the filter-score overrides.
**Design decision (documented, not a deviation from correctness):** the original task text described passing `settings_store.get_effective_dynamic_weights()` directly as `generate_confluence_signal()`'s `dynamic_weights` argument. That would have silently discarded the existing live/precomputed dynamic-weight computation on every request. Implemented instead as a scaling layer on top of the already-computed weights (1.0× multiplier at default settings, 0 for disabled indicators, renormalized to sum 100) — preserves both "never modify the Dynamic Weight algorithm" and "byte-identical at default settings", which a direct replacement could not have guaranteed.
**Not done (explicitly out of scope, per repeated instruction):** connecting the 3 new indicators to the confluence engine (Wick Rejection/Liquidity Sweep/False Breakout remain registered but not voting); Phase 8.
