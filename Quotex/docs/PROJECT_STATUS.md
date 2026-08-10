# PROJECT STATUS — Quotex OTC Signal Platform

Last updated: end of Phase 10.4 (Goals 1-5, complete). This document is the ground-truth
snapshot for continuation by another AI/engineer.

## Phase 10.4 — Walk-Forward Testing, Adaptive Calibration, Historical AI Health, Performance Reports, Advanced Analytics Dashboard (complete)

Five additive goals layered on top of the Phase 10.3 baseline, none
modifying `analyzer.py`, `backtest.py`, `scanner.py`, `learning_engine.py`,
`indicator_registry.py`, `ai_health_engine.py`, or `quotex/api_quotex/`
(verified byte-identical — see TEST_REPORT.md). See CHANGELOG.md for the
full per-goal breakdown; summary:
1. **Walk-Forward Testing Engine** (`walk_forward.py`) — rolling/expanding
   out-of-sample validation, reusing `backtest.py`'s existing weight-
   fitting functions.
2. **Adaptive AI Calibration** (`adaptive_calibration.py` +
   `/api/calibration/*`) — confidence calibration, threshold
   optimization, indicator/weight stability, asset/timeframe
   calibration, deterministic recommendations.
3. **Historical AI Health** (`ai_health_history_store.py` +
   `ai_health_trends.py` + `/api/ai/history/*`) — a new snapshot log of
   `compute_ai_health()` over time, daily/weekly/monthly/confidence/
   validation/learning/regime trend.
4. **AI Performance Reports** (`ai_performance_reports.py` +
   `/api/reports/*` + `/reports` page) — daily/weekly/monthly/asset/
   timeframe/indicator/validation/learning/AI-health/walk-forward/
   calibration reports, reusing `asset_timeframe_learning.py` for
   ranking rather than re-deriving it.
5. **Advanced Analytics Dashboard** (`analytics_dashboard.py` +
   `/api/analytics/dashboard` + `/analytics` page) — bundles Goal 4's
   report output plus a new validation win/loss distribution into one
   page with interactive charts (reuses the Chart.js build already
   loaded elsewhere in the app — not a new dependency).

267/267 new tests passing across the 5 goals; 814/814 across the full
repository's entire test suite (every test file that exists, actually
executed — see TEST_REPORT.md). Known, documented scope boundary: no
route triggers a live Quotex fetch, so the walk-forward engine and the
df-dependent calibration functions aren't reachable from any API route
yet — `walk_forward`/`available` reports `false` wherever surfaced.


## Overall Project Goal

A **manual-trading-assist** analysis platform for Quotex OTC pairs. It never
places trades. It fetches candle data, runs a multi-indicator confluence
engine, applies hard gates and a graded "Filter Score" quality metric, and
surfaces BUY/SELL/WAIT signals with confidence — for a human to act on
manually. A background Scanner continuously ranks all OTC assets; a
Backtest Engine measures historical indicator accuracy; a Settings Store
persists user-tunable configuration.

## Current Architecture (high level)

```
Quotex WebSocket/API (quotex/api_quotex/) ── unchanged since Phase 1
        │
fetch_data.py (QuotexDataFetcher) ── candle fetch/session mgmt
        │
indicators.py (calculate_all) ── all technical indicators, pure functions
        │
analyzer.py ── generate_confluence_signal() [BUY/SELL/WAIT + confidence]
            ── calculate_filter_score() [0-100 graded quality metric]
        │
backtest.py ── backtest_factor_accuracy(), compute_dynamic_weights(),
               backtest_filter_score_report()
        │
webapp/app.py (Flask) ── _run_pipeline() ties all of the above together
        │
webapp/scanner.py ── ScannerEngine: background async loop, ranks all assets
webapp/backtest_engine.py ── BacktestEngine: async backtest job runner
webapp/settings_store.py ── SettingsStore: JSON-file persistent settings
webapp/indicator_registry.py ── single metadata source for all indicators
```

All async orchestration (scanner, backtest engine) runs on **one shared
background asyncio event loop** (`_BG_LOOP` in `app.py`), which is also what
serializes all Quotex I/O — this is deliberate and load-bearing (see
PROJECT_MEMORY.md).

## Folder Structure (actual, as of now)

```
Quotex/
├── quotex/api_quotex/          # Quotex client, WebSocket, login — UNTOUCHED all project
├── market_analyzer/
│   ├── indicators.py           # 1136 lines — all indicator math
│   ├── analyzer.py             # 927 lines — confluence engine (13 factors as of Phase 8.6) + filter score
│   ├── backtest.py             # 536 lines — accuracy backtesting (unchanged Phase 7.4)
│   ├── config.py                # 86 lines — thresholds/constants + Phase 10.3 flag
│   ├── regime_detector.py       # NEW Phase 10.3 Part-1 — 8-regime classifier, pure/standalone
│   ├── regime_weight_engine.py  # NEW Phase 10.3 Part-1 — per-regime weight multiplier table
│   ├── dynamic_indicator_selector.py # NEW Phase 10.3 Part-1 — per-regime primary/low-relevance table
│   ├── regime_pipeline.py       # NEW Phase 10.3 Part-1 — orchestrates the 3 modules above
│   ├── explainable_signal.py    # NEW Phase 10.3 Part-2 — explains a BUY/SELL/WAIT signal (9 checks, gates, reasons, warnings)
│   ├── ai_health_engine.py      # NEW Phase 10.3 Part-2 — 5-component + overall AI Health scoring
│   ├── fetch_data.py           # candle fetcher wrapper
│   ├── run_analysis.py, deep_backtest.py  # CLI tools, mostly untouched
│   └── webapp/
│       ├── app.py               # ~1085 lines — Flask routes, _run_pipeline(), Phase 7.4 error handler
│       ├── scanner.py           # 417 lines — background scanner engine (unchanged Phase 7.4)
│       ├── backtest_engine.py   # ~333 lines — background backtest engine (CANDLE_OPTIONS expanded)
│       ├── settings_store.py    # ~285 lines — persistent settings (rounding-drift bug fixed)
│       ├── indicator_registry.py# 155 lines — indicator metadata registry
│       ├── preflight_check.py   # startup health check
│       ├── gunicorn.conf.py
│       ├── settings.json        # NEW — gitignored, created on first write, not committed
│       ├── templates/index.html # NEW: 4 pages added (Settings dynamic, Backtest, Indicators, Session)
│       └── static/app.js, static/style.css  # NEW: Phase 7.4 page logic + Auto Scanner bug fix
├── docs/                        # NEW this phase — PROJECT_STATUS/CHANGELOG/NEXT_PHASE/TEST_REPORT/
│                                 # HANDOFF/RELEASE_NOTES + the pre-existing architecture/API/indicator docs
├── .env.example
├── start-prod.sh (has preflight check wired in)
```

## Completed Phases

| Phase | What it did | Status |
|---|---|---|
| 1 | Audit of pre-existing codebase | ✅ Complete |
| 2 | `.env.example`, `preflight_check.py`, `start-prod.sh` health check | ✅ Complete |
| 2 (security) | `.gitignore` secret protection | ✅ Complete |
| 3 | Audit of indicators/analyzer/backtest | ✅ Complete |
| Step 1 | ADX/volatility confidence dampener | ✅ Complete |
| Step 2 | MTF transparency (`multi_tf_status`: CONFIRMED/DISAGREED/UNAVAILABLE) | ✅ Complete |
| Step 3 | Unified `MIN_SIGNALS_REQUIRED` threshold | ✅ Complete |
| Step 4 | OBV integrated into confluence (9th factor) | ✅ Complete |
| Step 4.1/4.2 | Regression audit + backup ZIP | ✅ Complete |
| Phase 5 | Candlestick engine upgrade (9 patterns, geometry-derived scores) | ✅ Complete |
| Phase 6 | Support/Resistance zone engine (10th confluence factor `sr`) | ✅ Complete |
| Phase 7 | Smart Scanner architecture + Filter Score v1 (binary gates) | ✅ Complete |
| Phase 7.1 | Filter Score v2 — graded scoring, `mandatory_pass` field | ✅ Complete |
| Phase 7.2 | `settings_store.py` (full), `backtest_engine.py` (full, standalone) | ✅ Complete (engine only — no routes/UI) |
| Phase 7.3 | `indicator_registry.py` + 3 new indicators (Wick Rejection, Liquidity Sweep, False Breakout) | ✅ Complete (confluence connection finished in Phase 8.6) |
| Phase 7.4 | Settings/Backtest/Indicators/Quotex-Session routes + `_run_pipeline()` wiring + full frontend (4 new pages) + Auto Scanner auto-start bug fix | ✅ Complete |
| Phase 8.1 | Smart Scanner Core Enhancement — `ScannerEngine` SettingsStore integration (`scanner_enabled`/`enabled_assets`/`enabled_timeframes`/`scan_interval`/`minimum_filter_score`/`top_signals`), progress tracking (`assets_completed`/`percent_complete`/`elapsed_time`/`estimated_remaining`), `status()`/`results()` compatibility aliases | ✅ Complete |
| Phase 8.2 | Smart Scanner user-facing UI — new dedicated page (`page-smart-scanner`) driving the real `/api/scanner/*` routes: status/progress display, Start/Stop/Pause/Resume controls, ranked-signals results table, auto-refresh only while running | ✅ Complete |
| Phase 8.3 | Smart Scanner Advanced Controls & Settings Integration — Scanner Settings card (assets/timeframes/min filter score/top signals/scan interval/enabled toggle) wired to `SettingsStore` with Save/Reload/Reset, `reset_section()`, `POST /api/scanner/settings/reset`, expanded status panel (`current_timeframe`/`last_scan_time`/`current_cycle`), 11-column results table, freshness-sort bug fix | ✅ Complete |
| Phase 8.3 Recovery | Verified recovery snapshot/baseline packaged — clean ZIP, all off-limits files diffed byte-identical to original upload, SHA256 checksum issued | ✅ Complete |
| Phase 8.4.1 | Audit-only sub-phase: confirmed the 3 new indicators have no existing backtest-compatible validation path (`backtest.py`'s `_factor_votes()` only vectorizes the 10 confluence factors); ran the unmodified detectors against real sample data and found a 100%-SELL pattern | ✅ Complete |
| Phase 8.4.2 | Indicator Validation Framework — new standalone `indicator_validation.py` (bar-by-bar replay, multi-asset/multi-timeframe capable, `MIN_SIGNALS_REQUIRED` sample-size gating); 14/14 tests passing; confirmed the SELL-bias finding persists across resampled timeframes (151/152 signals SELL) | ✅ Complete |
| Phase 8.4.3 | `ValidationEngine` (new `webapp/validation_engine.py`) + 6 new `/api/validation/*` routes, mirroring `BacktestEngine`'s architecture; found and fixed a real cross-thread `asyncio.Event` concurrency bug (confirmed via 5-trial stress test, 100% pass rate after fix); **full Validation UI** (`page-validation`) built incrementally in 8 verified steps — Settings panel, Controls with status badge, Progress card, 3 Indicator Summary cards, 11-column Results table, session-only History, and complete Run/Pause/Resume/Stop + self-managing polling wired to the real API; 46/46 + 18/18 backend tests, all frontend steps individually verified (HTML/JS/regression each step); render functions confirmed executing correctly against real validation data via direct Node execution | ✅ Complete |
| Phase 8.4.3 Recovery | Verified Stable Recovery ZIP packaged (`Quotex_Signal_Platform_Phase8.4.3_Stable.zip`) — all off-limits files diffed byte-identical, checksum issued | ✅ Complete |
| Phase 8.5 | Validation History Store — new standalone `webapp/validation_history_store.py`, JSON-backed (mirrors `settings_store.py`'s I/O pattern exactly), bounded growth (O(1) rolling stats + capped 200-entry run log), sufficient-sample-gated rolling mean; 3 new `/api/validation/history*` routes, app.py-polling-driven persistence (zero changes to `validation_engine.py`); existing 6 validation routes confirmed byte-identical; 40/40 store tests + 15/15 API tests, all 4 pre-existing suites re-passing | ✅ Complete |
| Phase 8.6 | Confluence Engine expanded 10 -> 13 factors: connected Wick Rejection, Liquidity Sweep, False Breakout (Phase 7.3 Part 3 detectors) to `analyzer._confluence_factor_votes()`/`DEFAULT_CONFLUENCE_WEIGHTS` (rebalanced to ~7.69/7.72 each, sum exactly 100.0); same reliability-threshold-gated vote pattern as `candle`/`sr`. `indicator_registry.py`'s `in_confluence`/`weight` fields (and therefore the Indicators-page "not yet connected" badge) update automatically — zero frontend files changed. `backtest.py` intentionally NOT touched (still 10-factor accuracy scoring; separately tracked). 51/51 new tests passing; only 3 files changed project-wide (`analyzer.py`, `indicators.py` comment-only, `indicator_registry.py` comment-only); all other files, including `quotex/api_quotex/`, confirmed byte-identical | ✅ Complete |
| Phase 8.7 | Final Stabilization & Release Audit — full repo/performance/security/production-readiness/UI/test/documentation audit (no code changed during the audit), then *safe cleanup only* after explicit approval: removed 4 confirmed-unused imports, 4 stray runtime artifacts (`candles.csv`, 3 `log-*.txt`), and one redundant (provably no-op) block in `navigateTo()`. No algorithm/Confluence/Validation/Scanner/API/route changes; no new dependencies. Biggest audit finding: `tests/test_phase_8_6.py` is the only persisted, re-runnable test file in the repo — every earlier phase's suite was sandbox-only and no longer exists on disk; flagged as a real gap, not fixed this phase. 51/51 regression suite still passing post-cleanup; 5 files modified + 4 removed, diffed and verified | ✅ Complete |
| Phase 9 | Smart Learning & Adaptive Weight System. Pre-implementation audit found a severe, pre-existing bug: the live pipeline (`backtest_factor_accuracy` → `compute_dynamic_weights` → `generate_confluence_signal`) silently gave Wick Rejection/Liquidity Sweep/False Breakout an effective weight of 0 on every real signal since Phase 8.6, because `backtest.py`'s `_DEFAULT_8F_WEIGHTS` was never extended past 10 factors. Fixed as an approved prerequisite (`backtest.py`, plus `settings_store.py`'s `INDICATOR_KEYS` — same class of gap, found wiring Apply) before any Phase 9 feature work, both verified end-to-end and backward-compatible. New additive `learning_engine.py` (`compute_recommendation()` + `LearningHistoryStore`) reads Validation History and recommends confluence weight adjustments — advisory only, never places trades, never touches Hard Gates/Filter Score/BUY-SELL direction, never edits Validation History, weights always clamped to `[min_weight, max_weight]` and renormalized to sum to 100. 5 new `/api/learning/*` routes, reusing the existing `settings_store.apply_suggested_weights()` for Apply (no new settings-write path). New Learning UI page, same component set as Validation/Backtest, no new CSS. `tests/test_phase_9_pipeline_fix.py` (34/34) proves the fix and that the original 10 factors' scoring formula is unchanged. 6 files modified + 2 new files, diffed and verified | ✅ Complete |
| Phase 10.1 | Universal Validation — extended the Validation framework from measuring only the 3 OTC-specific indicators to all 13 confluence factors. `indicator_validation.py`: added `UNIVERSAL_INDICATOR_NAMES`, `validate_indicator_universal()`/`validate_all_universal()` (delegate byte-identically to the unmodified `validate_indicator()`/`validate_all()` for the original 3; reuse `backtest.py`'s existing, unmodified `_factor_votes()` — read-only import — for the other 10, computed once per (asset,timeframe) not once per indicator), `summarize_by_asset()`/`summarize_by_timeframe()`. `validation_engine.py` widened to accept/default-to all 13. `app.py`: `/api/validation/run` + `/api/validation/history/<indicator>` widened to 13; added `GET /api/validation/summary/by-asset` + `GET /api/validation/summary/by-timeframe`. `validation_history_store.py`: `KNOWN_INDICATORS` widened 3→13, schema `1.0`→`1.1`, backward-compatible migration verified against a real synthetic old-format file (found and fixed a real bug where `schema_version` wasn't advancing, caught via that same verification). `analyzer.py`/`backtest.py`/`indicators.py`/`scanner.py`/`settings_store.py`/`indicator_registry.py`/`backtest_engine.py`/`quotex/api_quotex/` all reconfirmed byte-identical. New `tests/test_phase_10_1.py`, 142/142. Full regression suite: 227/227 (51+34+142). 4 files modified + 1 new test file, diffed and verified | ✅ Complete |
| Phase 10.2 | Asset Intelligence + Timeframe Intelligence — learns which indicator performs best on each OTC asset and each timeframe, plus system-wide top/weak indicator rankings and advisory recommendations. `validation_history_store.py`: schema `1.1`→`1.2`, two new top-level keys `asset_stats`/`timeframe_stats` (start empty — unbounded, freeform assets/timeframes, no fixed enum), new `record_asset_timeframe_stats()` persists the RAW per-(asset,timeframe) `ValidationEngine.results` (previously computed then discarded before this phase), fully independent of the unmodified `record_run()`; migration verified against a real synthetic 1.1-format file. New standalone `asset_timeframe_learning.py` (same decoupling convention as `learning_engine.py` — pure functions, zero cross-imports): `compute_asset_rankings()`/`compute_timeframe_rankings()` (pooled accuracy/trend/confidence, best/weakest indicator, min_samples-gated ranking — a real ranking-quality bug, raw-accuracy-only ordering letting a tiny sample outrank a large one, was found and fixed during testing), `compute_top_indicators()`, `compute_recommendations()`. `app.py`: 4 new read-only `/api/learning/*` routes. New Learning-page UI sections (Best Assets, Best Timeframes, Asset/Timeframe Rankings, Top/Weak Indicators, Indicator Trends, Recommendation Cards) — zero new CSS. `analyzer.py`/`backtest.py`/`indicators.py`/`scanner.py`/`settings_store.py`/`indicator_registry.py`/`backtest_engine.py`/`indicator_validation.py`/`validation_engine.py`/`learning_engine.py`/`quotex/api_quotex/` all reconfirmed byte-identical. New `tests/test_phase_10_2.py`, 74/74; 4 stale hardcoded-schema-version assertions in `tests/test_phase_10_1.py` updated (approved test-maintenance, not a behavior change — no other assertion touched, no production code touched for that fix). Full regression suite: 301/301 (51+34+142+74). 5 files modified + 2 new files, diffed and verified | ✅ Complete |
| Phase 10.3 Part-1 | Market Regime Detection + Adaptive Weight Engine + Dynamic Indicator Selection — classifies the current market into 1 of 8 deterministic regimes (or `Unknown`) purely from fields `indicators.calculate_all()` already produces (ADX/DI±, `trend_direction()`, `volatility()`, BB bands, and the 3 existing reversal-geometry detail dicts + candlestick detail), then rescales the 13 confluence-factor weights in two layered, independently-testable steps: a continuous per-regime multiplier table (`regime_weight_engine.py`) and a categorical primary/low-relevance table that discounts but never zeroes a factor (`dynamic_indicator_selector.py`). New standalone `regime_detector.py`/`regime_weight_engine.py`/`dynamic_indicator_selector.py`/`regime_pipeline.py` — zero imports of `analyzer.py`/`backtest.py`, fully unit-testable with hand-built dicts. Integrated as one more scaling layer (same idiom as Phase 7.4's `_apply_settings_weight_overrides()`) in `run_analysis.py` and `webapp/app.py`, placed *before* the Settings layer so Settings keeps final say; gated by new `config.ENABLE_REGIME_ADAPTIVE_WEIGHTS` flag (default `True`). API gained one additive, read-only `"regime"` JSON key. `analyzer.py`/`backtest.py`/`indicators.py`/`scanner.py`/`learning_engine.py`/`indicator_registry.py`/`quotex/api_quotex/` all reconfirmed byte-identical. New `tests/test_phase_10_3_part1.py`, 149/149. Full regression suite: 450/450 (51+34+142+74+149). 4 new modules + 3 files modified (`config.py`, `run_analysis.py`, `webapp/app.py`), diffed and verified | ✅ Complete |
| Phase 10.3 Part-2 | AI Health Dashboard + Explainable Signal System — `explainable_signal.py`'s `explain_signal(result)` turns an already-computed pipeline result into 9 named ✔/✖ checks (Trend/Momentum/Volatility/Volume/Price Action/Support-Resistance/ADX/MTF/Regime — all read from existing `filter_breakdown`/`factors`/`regime` fields, nothing recomputed), Hard Gates Passed/Failed, Final Filter Score, Confidence, Reasons, and Warnings; WAIT signals get an explicit "no direction to confirm" explanation instead of a guess. `ai_health_engine.py`'s `compute_ai_health(...)` scores 5 components (Indicator/Scanner/Validation/Learning/Regime) plus an Overall AI Health, each one of exactly `Excellent/Good/Fair/Poor/Critical` via a fixed 0-100 scale — "no data yet" is deliberately `Fair`, never `Critical`. One identified, deliberately-not-taken shortcut: `ScannerEngine._cache` (the only place a true, unfiltered "Recent WAIT %" could come from) is private with no public accessor, and `scanner.py` is off-limits — `recent_wait_pct` is honestly reported as `None` rather than guessed, and BUY%/SELL% are computed from the gated `top_signals` subset only, labeled as such. 4 new read-only routes (`/api/ai/health`, `/api/ai/status`, `/api/ai/statistics`, `/api/ai/explain` — the last reusing `_run_pipeline()` exactly like `/api/signal`, or falling back to the scanner's top-ranked cached signal). New `page-ai-health` dashboard (drawer nav, health badges, stats grid, best indicators/assets/timeframes reusing the existing `/api/learning/*` routes, and a hand-rolled Explain Signal modal popup) — zero new CSS framework, only 5 new `.badge-health-*` variants + one modal block reusing existing design tokens. `analyzer.py`/`backtest.py`/`indicators.py`/`scanner.py`/`learning_engine.py`/`indicator_registry.py`/`quotex/api_quotex/` all reconfirmed byte-identical. New `tests/test_phase_10_3_part2.py`, 97/97. Full regression suite: 547/547 (51+34+142+74+149+97). 2 new modules + 4 files modified (`webapp/app.py`, `webapp/templates/index.html`, `webapp/static/app.js`, `webapp/static/style.css`), diffed and verified | ✅ Complete (Part-2 only — Phase 10.4 not started, no scope assumed) |

## In Progress / Partial

**Phase 7.3** — now fully complete (as of Phase 8.6):
- Part 2: Indicator Registry (`indicator_registry.py`) — done, tested.
- Part 3: 3 new indicator detector functions in `indicators.py`, wired as
  additive keys in `calculate_all()` — done, tested. Connected to the
  confluence engine in Phase 8.6 (see that phase's CHANGELOG.md entry) —
  nothing about Phase 7.3 remains partial.

## Pending (not started — do not assume any code exists for these)

- Phase 8.1 (Smart Scanner core enhancement) — ✅ complete; see
  CHANGELOG.md/NEXT_PHASE.md for the full diff.
- Phase 8.2 (Smart Scanner — user-facing page wired to
  `/api/scanner/*`) — ✅ complete; new `page-smart-scanner` page, see
  CHANGELOG.md/NEXT_PHASE.md for the full diff. The pre-existing
  client-side "Auto Scanner" tab in `static/app.js` (`view-scanner`)
  remains the separate, older polling loop it always was — deliberately
  untouched, and still reachable from the drawer as a distinct nav
  entry so nothing that worked before regressed.
- Phase 8.3 (Smart Scanner Advanced Controls & Settings Integration) —
  ✅ complete; see CHANGELOG.md/NEXT_PHASE.md for the full diff,
  including a pre-existing freshness-sort bug found and fixed during
  the mandatory pre-phase audit.
- Phase 8.3 Recovery Snapshot — ✅ complete; a verified, cleaned ZIP
  baseline was packaged and its checksum issued separately from this
  repo (not tracked in-repo).
- Phase 8.4.1 (indicator-validation audit) — ✅ complete; found the 3
  new indicators have no existing backtest-compatible path, and found a
  100%-SELL pattern on the one available real dataset.
- Phase 8.4.2 (Indicator Validation Framework) — ✅ complete as of this
  update; see CHANGELOG.md/TEST_REPORT.md for the full methodology,
  results, and known limitations (most importantly: only 2 of 9 tested
  asset/timeframe/indicator combinations reached the sample-size
  reliability gate, and the SELL-bias finding persists across every
  timeframe tested). Confluence, Dynamic Weights, `backtest.py`, and
  `analyzer.py` remain completely untouched by this work.
- Phase 8.4.3 backend (`ValidationEngine` + `/api/validation/*` routes)
  — ✅ complete as of this update; see CHANGELOG.md/TEST_REPORT.md for
  the full diff, including a real concurrency bug found and fixed
  (cross-thread `asyncio.Event` signaling — fix scoped entirely to the
  new `validation_engine.py`, confirmed via a 5-trial stress test).
  `indicator_validation.py`, all 12 off-limits files, and `scanner.py`/
  `settings_store.py` (checked against the Phase 8.3 Recovery baseline
  specifically) all reconfirmed untouched. Confluence still exactly 10
  factors.
- Phase 8.4.3 UI (Validation dashboard page, `page-validation`) — ✅
  complete as of this update. Built incrementally across 8 approved
  steps (nav/container → settings panel → controls → progress →
  summary cards → results table → history → full API wiring), each
  step individually HTML/JS/regression-verified before the next began.
  Reuses `.history-row`, `.small-metrics-grid`/`.metric-card`,
  `.ss-results-table`, `.chip-toggle`/`.asset-grid` — no duplicate CSS/JS
  introduced. `app.py`/`validation_engine.py`/`indicator_validation.py`
  confirmed byte-identical to the already-approved backend state
  throughout (only `templates/index.html`/`static/app.js` changed this
  phase's UI work).
- Phase 8.5 (Validation History Store) — ✅ complete as of this update;
  see CHANGELOG.md/TEST_REPORT.md for the full diff. Persistence is
  backend-only this phase — the Validation UI's History section still
  shows session-only in-memory data (Phase 8.4.3); wiring the frontend
  to the new `/api/validation/history*` routes is explicitly deferred,
  not started.
- Phase 8.6 (Confluence Engine 10 -> 13 factors) — ✅ complete as of
  this update; see CHANGELOG.md for the full diff. Wick Rejection,
  Liquidity Sweep, and False Breakout (Phase 7.3 Part 3 detectors,
  unchanged) are now voted on by `generate_confluence_signal()`.
  `backtest.py`'s factor-accuracy scoring was deliberately NOT
  extended to include them this phase (separately tracked below) —
  live signals and backtest accuracy now measure different factor
  sets until that follow-up is done. No frontend file was changed;
  the Indicators page's `in_confluence` badge updates automatically
  from the registry.
- Phase 9 (Smart Learning & Adaptive Weight System) — ✅ complete; see
  CHANGELOG.md for the full diff, including the pre-existing 0-weight
  bug found and fixed as a prerequisite.
- Phase 10.1 (Universal Validation) — ✅ complete as of this update; see
  CHANGELOG.md/TEST_REPORT.md for the full diff, including a real
  schema-migration bug found and fixed during verification. IMPORTANT
  DISTINCTION: this phase extended the *Validation framework*
  (`indicator_validation.py`/`ValidationEngine`/`/api/validation/*`) to
  all 13 factors by reusing `backtest.py`'s `_factor_votes()` — it did
  **not** wire the 3 OTC indicators into `backtest_factor_accuracy()`/
  `compute_dynamic_weights()` itself. That remains the separate,
  still-not-started item below, carried forward unchanged from Phase
  8.6 — dynamic-weight suggestions on the Settings/Backtest page still
  do not include real accuracy data for those 3 factors.
- Phase 10.2 (Asset Intelligence + Timeframe Intelligence) — ✅ complete
  as of this update; see CHANGELOG.md/TEST_REPORT.md for the full diff,
  including a real ranking-quality bug found and fixed during
  verification (raw-accuracy-only ordering letting a tiny sample outrank
  a large one — fixed by gating ranking inclusion on `min_samples`, same
  as every other confidence-scored value in this codebase). Adds
  per-asset/per-timeframe Validation History (`asset_stats`/
  `timeframe_stats`, schema `1.1`→`1.2`) and a new standalone
  `asset_timeframe_learning.py` module computing rankings/
  recommendations from it. Does NOT touch `backtest_factor_accuracy()`/
  `compute_dynamic_weights()` (the Phase 8.6 pending item just above
  remains exactly as-is) and does NOT persist a history-of-
  recommendations log the way Phase 9's `LearningHistoryStore` does —
  Asset/Timeframe Intelligence is always computed fresh on each request.

## Pending — carried forward from Phase 8.6

- Wire the 3 newly-connected indicators (Wick Rejection, Liquidity
  Sweep, False Breakout) into `backtest.py`'s `_factor_votes()`/
  `backtest_factor_accuracy()` so backtest accuracy scoring covers
  all 13 confluence factors, not just the original 10 — explicitly
  deferred from Phase 8.6 (out of that phase's stated scope, and
  `backtest.py` was on the off-limits list for it). Until this is
  done, the Settings/Backtest page's dynamic-weight suggestions will
  not include real accuracy data for these 3 factors even though
  they now vote live in `generate_confluence_signal()`.
- Independently back-test/calibrate the 40.0 reliability-vote
  threshold for the 3 new factors (currently carried over unchanged
  from the pre-existing `candle`/`sr` convention) — not started.

## Pending — carried forward from Phase 10.1

- Validation UI's indicator-selector chip grid (`v-set-indicator-grid`
  in `templates/index.html`/`static/app.js`) still only renders 3 of
  the 13 universal indicators — a user driving the UI, as opposed to
  calling `/api/validation/run` directly with an explicit `indicators`
  list, still can't select any of the other 10. Not started.
- Phase 10.1's two summary routes (`GET /api/validation/summary/
  by-asset`/`by-timeframe`) have no UI consumer. Not started — separate
  from Phase 10.2's UI, which surfaces the historical/learned
  per-asset/per-timeframe data instead, not these session-only ones.
- `backtest_factor_accuracy()`/`compute_dynamic_weights()` (in
  `backtest.py` itself) still don't score the 3 OTC indicators — same
  item carried since Phase 8.6/9, unaffected by either 10.1 or 10.2.

## Pending — carried forward from Phase 10.2

- No UI consumer yet for the 4 new `/api/learning/*` routes' *response
  detail* beyond what's rendered — the per-indicator raw stats each
  group's `indicators` key carries (e.g. `asset_stats["EURUSD_otc"]
  ["bb"]`) are fetched but not separately displayed; only the pooled
  group-level summary and the best/weakest picks are shown. Not
  started, not required by Phase 10.2's stated scope.
- No `min_samples`/`top_n` controls in the UI — the 4 new routes accept
  `?min_samples=`/`?top_n=` query params, but the frontend always calls
  them with no query string (i.e. the route defaults). Not started.
- No persisted history-of-recommendations for Asset/Timeframe
  Intelligence (unlike Phase 9's `LearningHistoryStore` for confluence-
  weight recommendations) — every `/api/learning/{assets,timeframes,
  recommendations}` call recomputes fresh from current
  `asset_stats`/`timeframe_stats`/`rolling_stats`; there is no
  `recommendation_log` equivalent to look back at how a ranking has
  changed over time. Deliberately out of this phase's scope (see
  `asset_timeframe_learning.py`'s own docstring) — not a bug, but a
  real capability gap if trend-of-rankings-over-time is ever wanted.
- Full Flask-app-level (`app.py` test-client) request/response testing
  for the 4 new `/api/learning/*` routes was not performed — same
  standing sandbox constraint documented for Phase 10.1's summary
  routes (missing third-party dependencies, not installable here). Route
  wiring verified by code review + `py_compile`; every function each
  route calls is directly covered by `tests/test_phase_10_2.py`.
- Asset/Timeframe rankings are pooled ACROSS indicators, not filtered
  by any particular one — there's no "rank assets by how well indicator
  X specifically performs on them" view yet, only "rank assets by
  overall pooled accuracy, and separately, which single indicator is
  strongest for this asset." Combining the two (e.g. "show me EURUSD_otc
  ranked among assets specifically for `bb`") is not implemented.

## Pending — carried forward from Phase 10.3 Part-1

- No dedicated UI surface for the raw `"regime"` API field itself (no
  historical regime timeline). Partially addressed by Phase 10.3 Part-2's
  AI Health Dashboard, which does show the Current Market Regime and a
  Regime Health badge — but there is still no historical timeline/chart.
- No `RegimeHistoryStore` — every `/api/signal`-driven call recomputes the
  regime fresh from the latest bar; there is no persisted log of how the
  regime has changed over time (same "computed fresh, not persisted"
  pattern Phase 10.2's Asset/Timeframe Intelligence uses before a history
  store existed for it).
- `REGIME_FACTOR_MULTIPLIERS`/`DYNAMIC_SELECTION_TABLE` are hand-authored,
  fixed constants (documented inline in each module) — not yet
  backtest-calibrated against this project's own historical accuracy
  data. Treat as provisional, same caveat already applied to
  `DEFAULT_CONFLUENCE_WEIGHTS` pre-backtest.
- Regime detection is single-timeframe only (whatever granularity the
  `ind` dict passed in has) — no multi-timeframe regime confirmation.
- Full Flask-app-level (`app.py` test-client) request/response testing for
  the `"regime"` field was not performed — same standing sandbox
  constraint documented for Phase 10.1/10.2's untested routes (`loguru`/
  `websockets` not installed here). Wiring verified by code review +
  `py_compile` + source-inspection assertions in
  `tests/test_phase_10_3_part1.py`.

## Pending — carried forward from Phase 10.3 Part-2

- **`recent_wait_pct` is always `None`** — an accurate value would
  require reading `ScannerEngine`'s private `_cache` attribute (no public
  accessor exists), which this phase deliberately did not do since
  `scanner.py` is off-limits. Exposing a public, read-only accessor on
  `ScannerEngine` for its full unfiltered signal history (not just the
  gated `top_signals`) is a real, identified opportunity for a future
  phase — but that would mean touching `scanner.py`, so it needs
  explicit approval first.
- BUY%/SELL% in `/api/ai/statistics`/the dashboard reflect only the
  scanner's currently-surfaced (gate-passing) signals, not the true
  universe of everything attempted — labeled as such everywhere, but
  still a real precision limitation worth fixing once the above is
  approved.
- No historical/time-series charting of AI Health over time — every
  `/api/ai/*` call recomputes a fresh point-in-time snapshot; nothing is
  persisted (same "computed fresh, not persisted" pattern several other
  advisory features in this project used before a dedicated history
  store existed for them).
- The AI Health scoring formulas (component weights, the fixed 0-100
  `_status_label()` thresholds, the "no data = Fair" default) are
  hand-authored, not statistically calibrated against this project's own
  historical outcomes. Same provisional caveat as Phase 10.3 Part-1's
  regime multiplier tables.
- Full Flask-app-level (`app.py` test-client) testing of the 4 new
  `/api/ai/*` routes and the new dashboard page was not performed — same
  standing sandbox constraint as every prior phase. Verified by code
  review + `py_compile` + `node --check` + Jinja2-standalone template
  rendering + HTML tag-balance checking + source-inspection assertions
  in `tests/test_phase_10_3_part2.py`.
- Phase 10.4 (not scoped, not started — see NEXT_PHASE.md).

## Current Progress Percentage

Rough, honest estimate based on scope discussed vs. built:
- **Backend analysis/confluence/filter-score/backtest/scanner engines: ~90% complete** for what's been specified so far.
- **Settings/Backtest/Session UI and routes: 100% complete** for what was scoped in Phase 7.4 (routes + `_run_pipeline()` wiring + frontend pages). The 3 Phase 7.3 indicators are now connected to the confluence engine (Phase 8.6) — they still are not yet part of `backtest.py`'s factor-accuracy scoring, a separately tracked follow-up (see "Pending — carried forward from Phase 8.6" above).
- **Overall project (including undiscussed future phases 8-10): impossible to give a meaningful %** since scope keeps growing: treat as "core signal engine is production-quality; operator-facing tooling (settings/backtest/session UI) is now feature-complete for what's been scoped; Phase 8's user-facing Scanner page has not been started."

## Important Design Decisions
See PROJECT_MEMORY.md for the full rationale list.

## Technical Limitations
- Backtest cannot ever use historical Payout (Quotex has no historical payout API) or historical Multi-Timeframe confirmation (would need dual-timeframe historical replay, not built) — permanently and structurally excluded, not a bug.
- All testing in this project has used **synthetic data in a sandboxed environment with no network access** — nothing has been run against live Quotex data or through the real Flask route end-to-end. This is a standing caveat across every phase.
- Filter Score backtest buckets 20-40/40-60/60-80 are sparse for the reduced 5-criteria backtest version because "trade" eligibility still requires 4 mandatory gates to individually pass (see PROJECT_MEMORY.md).

## Performance Benchmarks (most recent measurements, synthetic 250-candle data unless noted)
| Function | Cost |
|---|---|
| `calculate_all()` | ~35-55 ms |
| `calculate_filter_score()` | ~0.005 ms |
| `generate_confluence_signal()` | included in calculate_all-adjacent pipeline, sub-ms |
| `backtest_factor_accuracy()` (10 factors — still 10 post-Phase-8.6, see Pending) | ~80-130 ms |
| `backtest_filter_score_report()` | ~85-90 ms |
| `scanner.get_results()` (53 cached assets) | ~0.02 ms |
| `BacktestEngine` orchestration overhead | ~5.4% over raw backtest.py calls |
| Estimated full scanner cycle (53 OTC assets, 1 timeframe) | ~80-130s (estimate, unverified against live Quotex latency) |
| `settings_store.get()` (Phase 7.4, disk-backed, per `_run_pipeline()` call) | ~0.035 ms |
| Settings weight/filter-score override layer combined (Phase 7.4, per request) | ~0.09 ms |
| `indicator_registry` get+overlay (Phase 7.4, `/api/indicators` only, not per-pipeline-request) | ~0.009 ms |
| `scanner.get_status()` + `scanner.get_results()` combined, Phase 8.1 (synthetic 6-asset scan, 400-call average) | ~0.006 ms/call |
| `GET /api/settings` (Phase 8.3, full Flask round trip via test_client, 200-call average) | ~0.34 ms |
| `POST /api/settings` (Phase 8.3, scanner-section patch, full Flask round trip, 200-call average) | ~0.83 ms |
| `GET /api/scanner/status` (Phase 8.3, full Flask round trip, running or stopped, 200-call average) | ~0.22-0.24 ms |
| `GET /api/scanner/results` (Phase 8.3, full Flask round trip incl. ranking+serialization, 200-call average) | ~0.24 ms |

## Security Decisions
- Quotex SSID: env var `QUOTEX_SSID` takes priority over `session.json`; SSID value never logged (only length). `.gitignore` updated to exclude `config.json`, `session.json`, `.env*`, credential/key files, browser storage dirs, and (Phase 7.4) `settings.json`/`settings.json.backups`.
- Phase 7.4's `/api/session/update` route writes only to `session.json`, never to an env var; the SSID value itself is never echoed back in any API response (only its length).
- No new secrets or credential handling introduced by any phase in this doc.

## Deployment Decisions
- `.replit` → `start-prod.sh` → `gunicorn -c gunicorn.conf.py app:app`. `start-prod.sh` now runs `preflight_check.py` before starting Gunicorn (aborts on critical failure, warns-only on Chromium/session gaps).
- Single shared `_BG_LOOP` background thread handles all async Quotex work; Scanner and BacktestEngine both submit onto this same loop — never create their own.

## Scanner Workflow
1. `POST /api/scanner/start` → `ScannerEngine.start()` submits `_scan_loop()` onto `_BG_LOOP`.
2. Loop sequentially calls `_run_pipeline(asset, timeframe)` (the SAME function `/api/signal` uses) for every OTC asset, paced by `asset_gap_seconds`.
3. Each result is gate-checked via `analyzer.calculate_filter_score()` (single source of truth — scanner has no gate logic of its own).
4. Results cached; `GET /api/scanner/results` filters by `mandatory_pass` (and, since Phase 8.1, an optional additional `minimum_filter_score` gate from settings) and ranks by `(filter_score, confidence, payout, freshness)` — all four descending. **Phase 8.3 bug fix:** freshness was previously compared as an unnegated ISO string, which actually sorted ascending (oldest-first) on ties; now parsed to epoch and negated so ties correctly resolve newest-first, matching what this line always claimed.
5. Manual `/api/signal` calls take soft priority — scanner yields (`YIELDING` state) between assets if a manual request is in flight.
6. States: `STOPPED/RUNNING/PAUSED/YIELDING/DEGRADED/RECOVERING`. Note: this is the *backend* `ScannerEngine`'s state machine — the UI's "Auto Scanner" tab (see below) drives a separate, simpler client-side polling loop that has never called these routes at all (a pre-existing architecture split, not something this project introduced or changed).
7. **(Phase 7.4)** The UI's client-side Auto Scanner loop (`static/app.js`) never starts automatically — not on page load, not on tab navigation. It starts only when the user presses the "Enable Auto Scanner" toggle on the scanner tab, and stops on page/tab close (`beforeunload`) or when toggled off. Reopening the site always starts with it OFF (the toggle's state lives only in an in-memory JS variable, never written to any storage). This fixes a pre-existing bug where `navigateTo('scanner')` — called once, unconditionally, at the bottom of `app.js` on every page load — started the scan loop automatically.
8. **(Phase 8.1)** `ScannerEngine` now optionally reads `settings.scanner` (via a defensive, exception-safe helper) at `start()` time: `scanner_enabled=false` blocks the start entirely (does not stop an already-running scan); `enabled_assets`/`enabled_timeframes` narrow that run's scope if set; `scan_interval`/`top_signals` are fallback defaults used only when the route call didn't pass an explicit value; `minimum_filter_score` adds an extra, opt-in gate in `get_results()` on top of the existing `mandatory_pass` check. All six default to values that reproduce pre-Phase-8.1 behavior exactly. `get_status()` also gained `assets_completed`/`percent_complete`/`elapsed_time`/`estimated_remaining`, and `status()`/`results()` now exist as aliases of `get_status()`/`get_results()`. None of this changes `/api/scanner/*` routes' existing response shape — only adds new keys to it.
9. **(Phase 8.2)** The new Smart Scanner page (`page-smart-scanner`) is the first UI surface to actually drive `ScannerEngine`'s real routes. Same "never auto-start" guarantee as the older Auto Scanner tab, enforced the same way: nothing in `navigateTo()`/`initSmartScannerPage()` ever calls `POST /api/scanner/start` — visiting the tab (or revisiting it, or the page loading at all) only issues a read-only `GET /api/scanner/status`. Auto-refresh (`pollScannerStatus()`, every 2s) is self-managing: it starts its own interval only when the fetched status says `running: true`, and clears it the moment `running` becomes `false` for any reason (including a stop triggered from a different tab/device) — not tied to which button the user last clicked on this page.
10. **(Phase 8.3)** The Smart Scanner page gained a Scanner Settings card (assets/timeframes/min filter score/top signals/scan interval/enabled toggle) that reads from and writes to `settings.scanner` via the existing generic `GET`/`POST /api/settings`, plus a new scoped `POST /api/scanner/settings/reset`. Settings and lifecycle are fully decoupled: saving/resetting settings never calls any `/api/scanner/start|stop|pause|resume` route, and `ScannerEngine` only reads settings at its own `start()` time (unchanged Phase 8.1 design) — so a save while `RUNNING` has zero effect on the active run, confirmed by an explicit test. The status panel gained `current_timeframe`/`last_scan_time`/`current_cycle`; the results table gained Rank/Payout/Age columns. Leaving the Smart Scanner tab now also stops the client-side status-polling timer (the scan itself is unaffected, since it always ran server-side independent of any client polling).

## Backtest Workflow
1. **(Phase 7.4)** `POST /api/backtest/run` (body: `assets`, `timeframe`, `candle_count`, `lookahead`) → validates input (400 for bad timeframe/assets/candle_count/malformed types), checks for a real conflict (409 if already running), then calls `BacktestEngine.start(loop, assets, timeframe, candle_count)` — candle_count must be one of 500/1000/1500/2000/3000/5000 (expanded from 500/1000/2000/5000 this phase).
2. For each asset: fetch candles (via the SAME shared fetcher `_run_pipeline()` uses — no second Quotex connection) → `backtest_factor_accuracy()` → `compute_dynamic_weights()` → `backtest_filter_score_report()` — all reused unmodified.
3. Progress fields (`current_asset`, `current_indicator`, `percent_complete`, elapsed/ETA) polled live via `GET /api/backtest/status` (frontend polls every 2s while a run is active).
4. On completion, `summary` aggregates suggested weights across assets (simple average) — **held in memory only** until explicitly applied. `GET /api/backtest/results` returns it; the Backtest page renders it as a table.
5. `POST /api/backtest/apply-weights` — gate-checks via `evaluate_apply_conditions()` (unmodified) before writing anything; on success calls `settings_store.apply_suggested_weights()` (which creates its own backup automatically). Only ever user-triggered (this route IS the explicit action — nothing calls it automatically).
6. `Pause/Resume/Stop` all wired to `/api/backtest/pause|resume|stop`.

## Settings Workflow
1. `SettingsStore(path)` — JSON file (`webapp/settings.json`, gitignored — pattern added to the repo-root `.gitignore` this phase), atomic writes, auto-backfills missing keys from defaults.
2. `get_effective_dynamic_weights()` — disabled indicators get weight 0, optionally renormalized to sum 100. **Bug fixed this phase:** per-key rounding could leave the sum a few `0.0001` off 100 — now the rounding residual is assigned to the largest weight, guaranteeing an exact 100.0 (or 0.0) sum (fuzz-tested, 200+ trials, 0 mismatches).
3. **(Phase 7.4)** `_run_pipeline()` layers this on top of the existing live/precomputed `dynamic_weights` computation (a scaling multiplier, 1.0× at default settings — see the Design Decision note in CHANGELOG.md for why this isn't a direct replacement) rather than replacing it outright, so `generate_confluence_signal()` and the Dynamic Weight algorithm itself remain untouched.
4. Backup/restore (`create_backup`/`restore_backup`, last 10 kept), export/import, reset — all implemented and tested, all now exposed over `GET/POST /api/settings`, `/reset`, `/backups`, `/backups/restore`, `/export`, `/import`, `/backup`.
5. **(Phase 7.4)** Settings page in the UI: dynamic editable form (General/Filters/Scanner sections), Save/Reset/Backup/Restore/Export/Import all wired.

## Regime Pipeline Workflow (Phase 10.3 Part-1)
1. Both `run_analysis.py` and `webapp/app.py`'s `_run_pipeline()` compute
   `dynamic_weights` exactly as before (unchanged `compute_dynamic_weights()`
   call, or the precomputed deep-backtest weights).
2. If `config.ENABLE_REGIME_ADAPTIVE_WEIGHTS` (default `True`):
   `regime_pipeline.compute_regime_adjusted_weights(dynamic_weights,
   indicators)` runs `regime_detector.detect_market_regime()` on the
   already-computed `indicators` dict, then layers
   `regime_weight_engine.apply_regime_adaptive_weights()` and
   `dynamic_indicator_selector.apply_dynamic_indicator_selection()` on top,
   in that order, renormalizing back to 100 each time.
3. In `webapp/app.py` specifically, this runs *before* the existing Phase
   7.4 `_apply_settings_weight_overrides()` layer — Settings (explicit user
   intent: enable/disable an indicator, manual weight scale) always applies
   last and has final say over whatever the regime layer produced.
4. `generate_confluence_signal(df, indicators, dynamic_weights)` — same
   call, same signature, as every prior phase.
5. `webapp/app.py`'s JSON response gains one additive `"regime"` key
   (name/confidence/reasons/which factors were boosted or discounted) —
   purely informational, does not feed back into signal/confidence/any
   other existing field.

## AI Health Dashboard + Explainable Signal Workflow (Phase 10.3 Part-2)
1. `/api/ai/health` (and `/status`/`/statistics`, which are condensed
   views of the same data) call `_build_ai_health()` in `app.py`, which
   gathers `validation_history_store.get_history()`, `learning_engine.
   compute_recommendation()`, `ScannerEngine.get_status()`/
   `get_results()`, and the current regime from the scanner's top-ranked
   cached signal, then delegates entirely to `ai_health_engine.
   compute_ai_health()` — no scoring logic lives in `app.py` itself.
2. `/api/ai/explain?asset=&timeframe=` runs the exact same `_run_
   pipeline()` `/api/signal` uses (same error handling, same manual-
   request bookkeeping — never places an order) when an asset is given;
   without one, it explains the scanner's current top-ranked cached
   signal instead. Either way the result dict is handed to
   `explainable_signal.explain_signal()`, which only reads fields — nothing
   is recomputed.
3. The AI Health dashboard page (`page-ai-health`) polls `/api/ai/health`
   plus the pre-existing `/api/learning/top-indicators`, `/api/learning/
   assets`, and `/api/learning/timeframes` routes directly (no new
   backend logic duplicated for Best Indicators/Assets/Timeframes — the
   dashboard just reuses Phase 10.2's routes). The Explain Signal button
   opens a hand-rolled modal calling `/api/ai/explain` on demand.
4. Every route in this workflow is read-only (GET) and touches no
   persisted state — the AI Health snapshot and every explanation are
   recomputed fresh on each call.

## Quotex Session Workflow
- Unchanged from original codebase: `QUOTEX_SSID` env var > `session.json`, redacted logging, 14-day session file expiry. `quotex/api_quotex/` (WebSocket, login, config) untouched.
- **(Phase 7.4 — implemented, not just proposed)** `POST /api/session/update` writes a pasted SSID to `session.json` only (never an env var), preserving any other keys already in the file; `POST /api/session/validate` forces a reconnect via the existing `connect()` path and reports the outcome. Honesty note (documented in the route itself): `AsyncQuotexClient.connect()` performs auth + WebSocket-gateway attachment as one handshake with no separate stage events, so "Connected to Server" / "Connected to Gateway" / "Session Valid" are reported together as one outcome, not as three independently-verified stages — the route does not fabricate finer-grained status than the client actually provides.
- `GET /api/session/status` reports active source (env vs session.json), whether a session file SSID is present (length only, never the value), fetcher connectivity, and the last validation result.
- Quotex Session page in the UI: status card, SSID paste + save, "Validate Session" button with a Server/Gateway/Session-Valid readout.
