# TEST REPORT — Summary Across All Phases

## Phase 10.4 — Walk-Forward Testing, Adaptive Calibration, Historical AI Health, Performance Reports, Advanced Analytics Dashboard

### Per-goal regression (new test files, each self-contained, run with `python3 tests/test_phase_10_4_goalN.py`)
| Goal | Test file | Result |
|---|---|---|
| 1 — Walk-Forward Testing Engine | `test_phase_10_4_goal1.py` | 46/46 passed |
| 2 — Adaptive AI Calibration | `test_phase_10_4_goal2.py` | 59/59 passed |
| 3 — Historical AI Health | `test_phase_10_4_goal3.py` | 58/58 passed |
| 4 — AI Performance Reports | `test_phase_10_4_goal4.py` | 64/64 passed |
| 5 — Advanced Analytics Dashboard | `test_phase_10_4_goal5.py` | 40/40 passed |
| **Phase 10.4 subtotal** | | **267/267 passed** |

Each suite covers: normal-case computation against hand-built inputs
with known expected results; empty/None/missing-data edge cases (never
fabricated — `None`/`"no_data"`/`available: false` instead); determinism
(identical input → identical output across repeated calls, timestamps
excluded); and source-inspection regression safety confirming the
relevant off-limits/prior-goal files contain no reference to the new
module and that every pre-existing route is still present verbatim in
`app.py`.

### Full regression suite (Goal 6 final release — every test file that exists in the repo, actually executed)
| Test file | Result |
|---|---|
| `test_phase_8_6.py` | 51/51 passed |
| `test_phase_9_pipeline_fix.py` | 34/34 passed |
| `test_phase_10_1.py` | 142/142 passed |
| `test_phase_10_2.py` | 74/74 passed |
| `test_phase_10_3_part1.py` | 149/149 passed |
| `test_phase_10_3_part2.py` | 97/97 passed |
| `test_phase_10_4_goal1.py` | 46/46 passed |
| `test_phase_10_4_goal2.py` | 59/59 passed |
| `test_phase_10_4_goal3.py` | 58/58 passed |
| `test_phase_10_4_goal4.py` | 64/64 passed |
| `test_phase_10_4_goal5.py` | 40/40 passed |
| **TOTAL** | **814/814 passed** |

Run twice: once against the working build tree, once again after
extracting the final Stable ZIP into a clean directory — both runs
produced the identical 814/814 result (see the Phase 10.4 Stable release
note at the end of this file for the extracted-ZIP run's exact output).

### Compile
`python3 -m py_compile` run against every `.py` file in the repository
(recursively, `__pycache__` excluded) — clean, zero errors. Run twice
(working tree, then the extracted ZIP) with identical results.

### Off-limits file verification (byte-identical, `diff -q`/`diff -rq`)
`analyzer.py`, `backtest.py`, `webapp/scanner.py`,
`webapp/learning_engine.py`, `webapp/indicator_registry.py`,
`ai_health_engine.py`, and `quotex/api_quotex/` (recursive) confirmed
byte-identical to the pre-Phase-10.4 baseline. A full-repository-root
diff (everything above and beside `Quotex/` too — `flask_project/`,
`lib/`, `scripts/`, root-level config files, etc.) confirms nothing
outside the documented Phase 10.4 additions changed anywhere.

### Not tested (explicitly, honestly — same standing limitation as every phase since 10.1)
- Live Quotex connectivity — no network access in this sandbox.
- `webapp/app.py`'s new routes via an actual HTTP request/response or
  Flask test client — this sandbox cannot import `app.py`
  (`fetch_data` → `api_quotex` → `loguru`/`websockets`, not installed,
  no network to add them). A minimal-stub import attempt was made during
  Goal 6 (stubbing `loguru`/`websockets`/`cloudscraper`) and deliberately
  abandoned: it would only confirm imports resolve, not that route logic
  is correct, and risked hiding real bugs behind low-fidelity stubs.
  Verification for every new route is via source inspection (import
  present, `@app.route` decorator present with the correct path/method,
  every pre-existing route still present verbatim) — consistent with,
  not a lower bar than, what every Phase 10.4 goal already reported.
- Real browser rendering of `templates/reports.html` /
  `templates/analytics.html` (no display/jsdom available) — verified by
  reading the template source and confirming fetch targets match actual
  route paths, not by click-through testing.

## PHASE 10.4 STABLE — Final Release Verification
- Stable ZIP built from the full repository root (not just `Quotex/`).
- Extracted into a clean directory; recompiled (`py_compile`, whole
  repo) — clean, identical to the pre-package compile.
- Full regression suite re-run from the extracted copy — 814/814
  passed, identical to the pre-package run.
- `diff -rq` between the build tree and the extracted ZIP confirms
  lossless packaging (zero differences).
- SHA256 of the final ZIP generated and independently re-verified
  against the ZIP on disk (`sha256sum -c`) — reported in the release
  message this Stable ZIP accompanies (a checksum of the archive cannot,
  by construction, be embedded inside the same archive without
  invalidating itself).

## Phase 10.3 Part-2 — AI Health Dashboard + Explainable Signal System

### Pre-implementation audit
Read `webapp/app.py`, `analyzer.py`, `learning_engine.py`,
`validation_history_store.py`, `asset_timeframe_learning.py`,
`templates/index.html`, and `static/app.js` before writing any code — no
Phase 10.3 Part-2 code was written until this audit identified the exact
fields already available in `_run_pipeline()`'s result dict and the
public methods of `ValidationHistoryStore`/`learning_engine`/
`ScannerEngine`. One real constraint was found and resolved without
touching `scanner.py`: an accurate "Recent WAIT %" needs
`ScannerEngine._cache` (private, no public accessor); resolution was to
report `recent_wait_pct` as `None` rather than guess, and to compute
BUY%/SELL% from the gated `top_signals` subset with that limitation
labeled everywhere it surfaces. Full reasoning in CHANGELOG.md.

### `tests/test_phase_10_3_part2.py` (97/97 passed)
1. **`ai_health_engine.py` component health functions (§1, ~19 checks)**:
   `compute_indicator_health()` verified against hand-built
   `rolling_stats` for the empty-history case, the below-min-samples
   case, and a fully-covered high-win-rate case (exact weighted-score
   math: `0.7*avg_accuracy + 0.3*coverage_pct`) — each asserting the
   correct status label. `compute_validation_health()` verified for
   zero-sample (`Fair`), a >=2000-pooled-sample case (capped `Excellent`
   score), and a low-volume case (`Poor`/`Critical`), plus the
   `run_log[0]`-is-most-recent convention for `last_run_at`.
   `compute_learning_health()` verified for `None` input, all-`"none"`-
   confidence (`Fair`, explicitly NOT `Critical`), and all-real-
   confidence (`Excellent`). `compute_regime_health()` verified for
   `None`, explicit `"Unknown"` (both `Fair`), a high-confidence named
   regime (`Excellent`, confidence reused directly with zero
   recomputation), and `"Uncertain / Mixed"` at its own fixed 25.0
   confidence (correctly falls to `Poor`). `compute_scanner_health()`
   verified for no-data (`Fair`), a 2-BUY-surfaced case (exact buy_pct/
   sell_pct/average_filter_score math, `wait_pct` confirmed always
   `None`, `current_regime` taken from the top-ranked cached entry,
   `signal_count` confirmed to use the TRUE unfiltered `cached_results`
   rather than `len(top_signals)`), and a stopped/stale/nothing-surfaced
   case (`Poor`).
2. **`compute_ai_health()` full orchestration (§2, 6 checks)**: verified
   all 6 required health blocks are present, the flat fields
   (`recent_accuracy`/`history_coverage`/`average_confidence`/
   `average_filter_score`/`buy_pct`/`sell_pct`/`data_quality`) exactly
   re-expose the corresponding nested component values (proving no
   drift between the two representations), a zero-argument call never
   raises and defaults every component to `Fair`, and determinism
   (repeated calls with identical input produce an exactly-equal nested
   result).
3. **`explainable_signal.py`'s `explain_signal()` (§3, ~21 checks)**: a
   BUY signal with 6/7 gates passing verified for correct pass-through
   of signal/confidence/filter_score, presence of all 9 named checks,
   correct pass/fail on each derived check (trend/price_action from
   `filter_breakdown`, momentum from a 2/3 majority vote, volume from
   the obv vote, regime from the Strong-Uptrend-supports-BUY rule),
   exactly 6 hard gates passed / 1 failed with the correct human label,
   non-empty reasons, and a warning naming the failed check. A SELL
   signal verified symmetrically (3/3 BEARISH momentum, Strong-
   Downtrend-supports-SELL), plus an explicit check that the SAME
   Strong-Uptrend regime that supports BUY correctly does NOT support a
   SELL signal (asymmetry proof, not just presence). A WAIT signal
   verified to report momentum/volume/regime all False with an explicit
   "no directional confirmation" reason (not a guessed direction) and a
   WAIT-specific warning. Unknown regime verified to fail the regime
   check and produce an explicit warning naming it. An empty `{}`
   result verified to produce an all-False, single-warning explanation
   with no exception. A partial result (empty `factors`/`regime`/
   `multi_tf_status`) verified to degrade gracefully with explicit
   "no data available" details rather than raising a `KeyError`.
   Determinism verified by repeated calls on identical input.
4. **Integration wiring — routes + UI (§4, ~30 checks, via source
   inspection)**: `app.py` confirmed to import both new modules, define
   `_build_ai_health()`, and register all 4 new routes; `/api/ai/
   explain`'s `_run_pipeline()` call-site confirmed to match `/api/
   signal`'s exactly (same call appears >=2 times in the file) and its
   scanner-fallback branch confirmed present verbatim.
   `templates/index.html` confirmed to contain the new drawer link,
   the `page-ai-health` section, the Explain Signal modal, and all 12
   new element ids the JS depends on. `static/app.js` confirmed to
   register `'ai-health'` in `VIEWS`, wire `initAiHealthPage()` into
   `navigateTo()`, and define all 7 new `aih*` functions, calling the
   correct new API routes. `static/style.css` confirmed to define all 5
   new health-status badge classes plus the modal/overlay classes.
   **Why source inspection instead of a live Flask test client**:
   `webapp/app.py` cannot be imported in this sandbox (`fetch_data.py`
   → `quotex/api_quotex/` → `loguru`, not installed) — the identical
   pre-existing environment limitation documented for every prior
   phase's routes. The new HTML/JS were additionally verified outside
   this test file (not duplicated here) via a standalone Jinja2 render
   (confirming the template compiles with no undefined-variable errors
   and produces balanced HTML tags) and `node --check` (confirming
   `app.js`'s syntax is valid).
5. **Off-limits files re-checked (§5, 8 checks)**:
   `analyzer.DEFAULT_CONFLUENCE_WEIGHTS` reconfirmed at exactly 13 keys
   summing to 100.0; `analyzer.py`'s source text confirmed to contain
   zero references to either new module name; both new modules
   confirmed (via `dir()`) to import nothing from `analyzer`/
   `backtest`/`indicators`; `backtest.py`, `scanner.py`,
   `learning_engine.py`, and `indicator_registry.py` source text
   confirmed to contain no reference to either new module.

### Full regression suite (post Phase 10.3 Part-2)
- `tests/test_phase_8_6.py`: 51/51 passed (unchanged).
- `tests/test_phase_9_pipeline_fix.py`: 34/34 passed (unchanged).
- `tests/test_phase_10_1.py`: 142/142 passed (unchanged).
- `tests/test_phase_10_2.py`: 74/74 passed (unchanged).
- `tests/test_phase_10_3_part1.py`: 149/149 passed (unchanged).
- `tests/test_phase_10_3_part2.py`: 97/97 passed (new).
- **547/547 total** (51+34+142+74+149+97).

### Known limitations of this phase's testing
- No live Flask test-client coverage for the 4 new `/api/ai/*` routes or
  the new dashboard page — see §4 above for why, and see CHANGELOG.md's
  "Known limitations" for the full statement.
- `recent_wait_pct` was verified to always be exactly `None` (not
  guessed) — this was tested as the CORRECT behavior, not a gap; a true
  WAIT percentage is architecturally unavailable without touching
  `scanner.py`.
- The AI Health scoring formulas were verified for **mechanical
  correctness** (exact score math, correct status-label thresholds,
  the "no data = Fair, never Critical" convention, determinism) — not
  for **predictive value**, since they are hand-authored constants, not
  yet calibrated against real historical accuracy data.
- No test exercises the dashboard against real fetched candle data or a
  real browser DOM — only hand-built dicts and static source/syntax
  checks — same standing "no live network access" sandbox constraint as
  every prior phase.



### Pre-implementation audit
Extracted the Phase 10.2 Stable ZIP, recompiled the entire project clean,
and re-ran all 4 persisted regression suites before writing any Phase
10.3 code:
- `tests/test_phase_8_6.py`: 51/51 passed.
- `tests/test_phase_9_pipeline_fix.py`: 34/34 passed.
- `tests/test_phase_10_1.py`: 142/142 passed.
- `tests/test_phase_10_2.py`: 74/74 passed.
- 301/301 total, confirming the Phase 10.2 baseline was solid before any
  new code was written. Audited `analyzer.py`, `indicators.py`,
  `config.py`, `backtest.py`, `run_analysis.py`, and `webapp/app.py`
  before deciding where to extend — see CHANGELOG.md for the key
  findings that shaped the design (`generate_confluence_signal()`'s
  existing `dynamic_weights` override param; `_apply_settings_weight_
  overrides()`'s precedent scaling-layer pattern; every field a regime
  classifier needs already produced by `calculate_all()`).

### `tests/test_phase_10_3_part1.py` (149/149 passed)
1. **`regime_detector.py` — all 8 regimes + Unknown (§1, ~20 checks)**:
   hand-built `ind` dicts constructed to hit exactly one rule each —
   Strong Uptrend, Strong Downtrend, Sideways Range, Low Volatility, High
   Volatility, Breakout, Reversal (via both `wick_rejection_detail` and
   `false_breakout_detail`), and Uncertain/Mixed (a combination
   deliberately built to fail every specific rule) — each verified for
   the correct regime name AND non-empty `reasons`/populated
   `metrics_used`. Unknown verified via both a missing-required-field
   dict and a NaN-field dict, checking `confidence == 0.0` and
   `metrics_used == {}`. Edge case: a reversal-type detail present but
   with `reliability_score` **below** the threshold is verified to NOT
   trigger Reversal (falls through to the next matching rule instead) —
   proving the reliability gate is a real, enforced threshold, not
   decorative.
2. **`regime_weight_engine.py` — adaptive weight scaling (§2, ~30
   checks)**: every regime in `REGIME_FACTOR_MULTIPLIERS` verified for
   `applied == True`, weights summing to exactly 100.0 (within 1e-3),
   same 13 keys preserved, and non-empty explanatory `notes`. A specific
   ratio check (`obv`/`bb` in Strong Uptrend) proves the renormalization
   preserves the *documented* multiplier ratio (1.3/0.6) rather than
   distorting it. Uncertain/Mixed and Unknown verified as a hard no-op —
   `applied == False`, output weights dict `==` input weights dict
   exactly (not just numerically close).
3. **`dynamic_indicator_selector.py` — categorical selection (§3, ~50
   checks)**: every regime in `DYNAMIC_SELECTION_TABLE` verified for
   `applied == True`, sum-to-100 normalization, `primary`/`low_relevance`
   lists matching the table exactly, a primary factor's weight-to-
   neutral-factor ratio boosted above baseline, a low-relevance factor's
   ratio discounted below baseline, and — critically — **no factor's
   final weight is ever exactly zero**, proving the "discount, never
   silence" design constraint documented in the module holds in
   practice, not just in the docstring. Uncertain/Mixed and Unknown
   verified as a hard no-op (`primary`/`low_relevance` both empty,
   weights unchanged).
4. **`regime_pipeline.py` — orchestration (§4, 8 checks)**: the
   pipeline's regime/adaptive-weight-step/selection-step outputs are
   each compared, by exact dict equality, against calling
   `detect_market_regime()` → `apply_regime_adaptive_weights()` →
   `apply_dynamic_indicator_selection()` by hand in that same
   sequence — proving the orchestrator is a pure composition, not a
   parallel reimplementation that could drift from the 3 underlying
   modules. **Determinism** verified by calling the full pipeline twice
   with identical inputs and asserting exact equality of the entire
   nested result. Unknown-regime end-to-end verified to be a complete
   no-op (`final_weights == base_weights`).
5. **Normalization & edge cases (§5, 8 checks)**: a deliberately
   non-100-sum input (13 factors at 5.0 each = 65.0 total) verified to
   renormalize to exactly 100.0 through both the weight engine directly
   and the full pipeline; an empty `{}` weights dict verified to produce
   `{}` output with no exception in both the weight engine and the
   selector; an all-zero-weights dict verified to hit the `total > 0`
   guard and return all-zero output rather than raising a
   divide-by-zero; an unrecognized factor key (not present in any
   multiplier or selection table) verified to pass through both modules
   without a `KeyError`, defaulting to an unchanged/neutral treatment.
6. **Integration wiring — config flag + API additive field (§6, 11
   checks, via source inspection)**: `config.ENABLE_REGIME_ADAPTIVE_
   WEIGHTS` confirmed to exist and default to `True`; both
   `run_analysis.py` and `webapp/app.py` confirmed (by reading their
   actual source text) to import `regime_pipeline.compute_regime_
   adjusted_weights`, to gate the call on the config flag, and to call
   it with the exact expected arguments; `webapp/app.py` specifically
   confirmed to place that call **before** (lower source-line index than)
   `_apply_settings_weight_overrides()`, proving Settings still applies
   last; the JSON `result` dict confirmed to have gained the new
   `"regime"` key **alongside** (not replacing) the pre-existing
   `"multi_tf_status"` key; the existing, unmodified
   `generate_confluence_signal(df, indicators, dynamic_weights)` call
   confirmed still present verbatim.
   **Why source inspection instead of a live Flask test client**:
   `webapp/app.py` cannot be imported in this sandbox —
   `fetch_data.py` → `quotex/api_quotex/` → `loguru`, which is not
   installed here. This is the identical pre-existing environment
   limitation already documented for Phase 10.1's `/api/validation/
   summary/*` routes and Phase 10.2's `/api/learning/*` routes (missing
   third-party dependency, not installable, not something this or any
   prior phase introduced or can fix from inside the sandbox).
7. **Off-limits files re-checked (§7, 10 checks)**:
   `analyzer.DEFAULT_CONFLUENCE_WEIGHTS` and
   `backtest._DEFAULT_8F_WEIGHTS` reconfirmed at exactly 13 keys summing
   to 100.0; `analyzer.py`'s source text confirmed to contain **zero**
   references to any of the 4 new module names (proving the "keep
   analyzer.py changes to an absolute minimum" requirement was actually
   met with zero, not "minimal"); each of the 4 new modules confirmed (via
   `dir()`) to have no `analyzer`/`backtest` name bound in its own
   namespace — i.e. none of them import analyzer or backtest at all;
   `scanner.py`, `learning_engine.py`, and `indicator_registry.py`
   source text confirmed to contain no reference to any Phase 10.3
   module either.

### Full regression suite (post Phase 10.3 Part-1)
- `tests/test_phase_8_6.py`: 51/51 passed (unchanged).
- `tests/test_phase_9_pipeline_fix.py`: 34/34 passed (unchanged).
- `tests/test_phase_10_1.py`: 142/142 passed (unchanged).
- `tests/test_phase_10_2.py`: 74/74 passed (unchanged).
- `tests/test_phase_10_3_part1.py`: 149/149 passed (new).
- **450/450 total** (51+34+142+74+149).

### Known limitations of this phase's testing
- No live Flask test-client coverage for `webapp/app.py`'s new `"regime"`
  field or the config-flag-gated call site — see §6 above for why, and
  see CHANGELOG.md's "Known limitations" for the full statement.
- The per-regime multiplier/selection tables were verified for
  **mechanical correctness** (ratios, normalization, no-op behavior,
  determinism) — not for **predictive/trading-accuracy value**, since
  they are hand-authored constants, not yet backtest-calibrated against
  real historical accuracy data for this project.
- No test exercises the regime pipeline against real fetched candle data
  (only hand-built `ind` dicts) — same standing "no live network access"
  sandbox constraint as every prior phase.



### Pre-implementation audit
Extracted the canonical Phase 10.1 Stable ZIP, recompiled clean, and
re-ran all 3 persisted regression suites before writing any Phase 10.2
code:
- `tests/test_phase_8_6.py`: 51/51 passed.
- `tests/test_phase_9_pipeline_fix.py`: 34/34 passed.
- `tests/test_phase_10_1.py`: 142/142 passed.
- 227/227 total, confirming the Phase 10.1 baseline was solid before any
  new code was written. Audited `validation_history_store.py`,
  `learning_engine.py`, `validation_engine.py`, `indicator_validation.py`,
  `app.py`, and `scanner.py` before deciding where to extend.

### `tests/test_phase_10_2.py` (74/74 passed)
1. **`validation_history_store.py` schema-1.2 storage layer** — fresh
   store starts with empty `asset_stats`/`timeframe_stats` (unlike the
   pre-populated 13-indicator `rolling_stats`); `record_asset_timeframe_
   stats()` correctly records/accumulates real and insufficient-sample
   data, skips error'd combinations entirely, accumulates correctly
   across multiple runs (not overwritten); `get_asset_stats()`/
   `get_timeframe_stats()` accessors verified for both known and unknown
   keys (fail soft, not an exception); `record_run()` (Phase 8.5,
   unmodified) proven — via a before/after JSON-dump comparison — to
   never touch the two new keys at all; `reset()` verified to clear all
   four top-level keys.
2. **Backward-compatible 1.1→1.2 migration**, verified against a REAL
   synthetic schema-`"1.1"` file on disk (not a mock) — schema bump to
   the current version constant, pre-existing `rolling_stats`/`run_log`
   preserved **byte-identically**, new keys backfilled as empty dicts,
   change actually persisted to the on-disk bytes (re-read raw JSON, not
   just the in-memory return value), idempotent re-read (no rewrite on a
   second read), and — critically — `record_asset_timeframe_stats()`
   verified to work correctly immediately after migration, on the same
   file, without disturbing the pre-existing data.
3. **`asset_timeframe_learning.py` pure functions**, against a hand-built
   history dict with independently hand-computed expected results:
   `compute_asset_rankings()`/`compute_timeframe_rankings()` (pooled
   `total_validations`/`wins`/`losses`/`accuracy` cross-checked against
   manual arithmetic; best/weakest indicator selection; ranking order
   correctly gated by `min_samples` while still surfacing below-threshold
   groups in the full response); `compute_top_indicators()` (global
   ranking from `rolling_stats`, correctly separates `no_data` entries);
   `compute_recommendations()` (best-per-asset/best-per-timeframe
   verified against the ranking functions' own output;
   improving/declining classification independently verified against the
   hand-set `last_win_rate`/`average_win_rate_over_runs` differences);
   empty-history edge case for every function.
4. **Full end-to-end pipeline**: a real `ValidationEngine` run (mocked
   `fetch_candles`, no live Quotex network — consistent with this
   project's standing sandbox constraint) → `ValidationHistoryStore.
   record_asset_timeframe_stats()` → `asset_timeframe_learning.py`'s
   ranking/recommendation functions, proving the whole chain connects
   correctly end to end (all 13 indicators recorded per asset, correct
   assets/timeframes present, non-empty rankings and recommendations
   produced from real engine output) — not just each piece tested in
   isolation.
5. **Off-limits-file re-check from the Phase 10.2 code path itself** —
   `analyzer.DEFAULT_CONFLUENCE_WEIGHTS` and `backtest._DEFAULT_8F_WEIGHTS`
   still exactly 13 keys summing to 100.0;
   `indicator_validation.UNIVERSAL_INDICATOR_NAMES` still exactly 13; a
   direct check that `asset_timeframe_learning.py` imports nothing from
   `analyzer`/`backtest`/`validation_engine`/`indicator_validation`/
   `scanner` (structural, not just by convention).

### Bug found and fixed during this verification
`asset_timeframe_learning.py`'s asset/timeframe `ranking` list was
initially ordered by raw `accuracy` alone, with no sample-size gate — so
a group with 3-of-5 samples (60% accuracy) could rank above a group with
55-of-100 samples (55% accuracy), even though the second is a far more
reliable measurement. Fixed by requiring `total_validations >=
min_samples` for inclusion in the ordered `ranking` list specifically —
the same "don't let a tiny, lucky sample outrank a large, reliable one"
gate `_best_and_weakest_indicator()` and every other confidence-scored
value in this codebase already applies. A group below the threshold still
appears in the full `assets`/`timeframes` response dict with its real (if
noisy) accuracy value; it's only excluded from the authoritative ranked
list. Caught by asserting an exact expected ranking order against
hand-built data with a deliberately small-but-high-accuracy outlier
group, not just checking that ranking "worked" in general.

### Approved test-maintenance fix (not a behavior/production change)
The correct, intentional schema `1.1`→`1.2` bump above made 4 assertions
in `tests/test_phase_10_1.py` stale — they hardcoded the literal string
`"1.1"`, which was accurate when that file was written but was never
going to remain accurate through a future correct schema evolution (the
exact same situation `test_phase_10_1.py` itself was written to verify,
for the 1.0→1.1 case). Approved and applied: updated only those 4
assertions to reference `VHS_SCHEMA_VERSION` (the version constant)
instead of a literal string. No other assertion in that file was touched,
and no production code was touched to make this fix — confirmed by
re-running the full suite (227/227 restored) before any Phase 10.2 code
was written, and by `diff` showing only those 4 lines changed in that
file.

### Full regression suite after Phase 10.2
`test_phase_8_6.py` (51/51) + `test_phase_9_pipeline_fix.py` (34/34) +
`test_phase_10_1.py` (142/142) + `test_phase_10_2.py` (74/74) =
**301/301 passing**.

### Off-limits files — confirmed byte-identical
`diff -rq` against a fresh extraction of the Phase 10.1 Stable ZIP
confirmed `analyzer.py`, `backtest.py`, `indicators.py`, `scanner.py`,
`settings_store.py`, `indicator_registry.py`, `backtest_engine.py`,
`indicator_validation.py`, `validation_engine.py`, `learning_engine.py`,
and every file under `quotex/api_quotex/` are byte-identical. Exactly 5
files were modified (`validation_history_store.py`, `app.py`,
`static/app.js`, `templates/index.html`, `tests/test_phase_10_1.py`),
plus 2 new files (`asset_timeframe_learning.py`, `tests/test_phase_10_2.py`)
— no other diffs of any kind (after excluding `__pycache__` build
artifacts).

### Known limitation (honest, not glossed over)
Same standing sandbox constraint documented for Phase 10.1's summary
routes: full Flask-app-level (`app.py` test-client) request/response
testing for the 4 new `/api/learning/*` routes was not performed —
blocked by missing third-party dependencies (`pydantic`, transitively
required by `quotex/api_quotex/`) not installable in this sandbox. Route
wiring was verified by direct code review plus `py_compile`, and every
function each route calls (`compute_asset_rankings()`,
`compute_timeframe_rankings()`, `compute_top_indicators()`,
`compute_recommendations()`) is directly covered by
`tests/test_phase_10_2.py`. JS syntax was checked with `node --check`;
the HTML template was verified to still parse as valid Jinja2 and to have
balanced `<div>` tags (260 open/260 close overall; 45/45 within the
Learning page section specifically) — not the same as a real browser
render, but the strongest verification available without network access.

---

## Phase 10.1 — Universal Validation (all 13 confluence factors)

### Pre-implementation audit
Compiled the full Phase 9 Stable codebase (clean) and re-ran both existing
persisted regression suites before writing any Phase 10.1 code:
- `tests/test_phase_8_6.py`: 51/51 passed.
- `tests/test_phase_9_pipeline_fix.py`: 34/34 passed.
- 85/85 total, confirming the Phase 9 baseline was solid before any new
  code was written.

### `tests/test_phase_10_1.py` (142/142 passed)
1. **`UNIVERSAL_INDICATOR_NAMES` shape** — exactly 13 factors, matches
   `analyzer.DEFAULT_CONFLUENCE_WEIGHTS`'s keys AND their order exactly
   (read-only comparison); original 3 are a proper subset; the 10
   vectorized names and the 3 detector-based names are disjoint and
   together cover all 13.
2. **All 13 indicators individually validated** against synthetic OHLC
   data via `validate_indicator_universal()` — correct output schema
   (full 17-key result dict) for every one, `samples`/`wins`/`losses`
   internally consistent (`wins + losses == samples`), `win_rate` in
   `[0, 100]` whenever `samples > 0`, and a `ValueError` for a genuinely
   unknown indicator name.
3. **Backward compatibility (delegation)** — for the original 3
   indicators, `validate_indicator_universal()`'s output is **byte-
   identical** (full dict equality, not just spot-checked fields) to
   calling the unmodified `validate_indicator()` directly. The unmodified
   `validate_all()` (Phase 8.4.2) still returns exactly 3 results matching
   `INDICATOR_NAMES`, proving Phase 10.1 added new capability without
   altering old code paths at all.
4. **`validate_all_universal()` grouping/subsetting** — 2 (asset,
   timeframe) pairs × 13 indicators = 26 results, every triple unique; a
   caller-supplied 4-indicator subset (mixed vectorized + detector-based)
   returns exactly 2 × 4 = 8 results containing only the requested names;
   unknown indicator name raises `ValueError`.
5. **`summarize_by_asset()`/`summarize_by_timeframe()`** — per-asset and
   per-timeframe `total_samples` verified against an independently
   hand-summed total over the raw result list (not just checked against
   the function's own internal bookkeeping); `overall_win_rate` arithmetic
   (`total_wins / total_samples * 100`, rounded) independently
   recalculated and compared; both functions return `{}` on an empty input
   list rather than erroring.
6. **`ValidationEngine` end-to-end** (mocked `fetch_candles`, no live
   Quotex network — consistent with this project's standing sandbox
   constraint): omitting `indicators` now runs all 13 by default and
   produces a 13-indicator summary; explicitly passing the original 3
   still runs exactly those 3 (not all 13) — full backward compatibility
   for existing callers; a genuinely unknown indicator name is rejected at
   `start()` and the engine stays `STOPPED`; a mixed vectorized+detector
   subset (`bb`, `sr`, `wick_rejection`) runs exactly and only that subset.
7. **`ValidationHistoryStore` migration** — see dedicated verification
   below; re-asserted here as part of the full suite.
8. **Off-limits-file re-check from the Phase 10.1 code path itself** —
   `analyzer.DEFAULT_CONFLUENCE_WEIGHTS` still exactly 13 keys summing to
   100.0; `backtest._DEFAULT_8F_WEIGHTS` likewise; `backtest._factor_votes()`
   still returns exactly its original 10 keys (proof Phase 10.1 only
   *reads* this function, never modifies it).

### Validation History schema migration — verified against a REAL old-format file
Built an actual schema-`"1.0"` `history.json` on disk (not a mock),
matching exactly what Phase 8.5 would have produced: 3 indicators'
`rolling_stats` with realistic non-zero accumulated values, plus a
`run_log` entry whose `per_indicator` dict only has 3 keys. Loaded it via
the Phase 10.1 `ValidationHistoryStore` and verified, against the actual
in-memory result AND the actual bytes rewritten to disk:
- `schema_version` advances from `"1.0"` to `"1.1"`.
- All 13 `KNOWN_INDICATORS` present in `rolling_stats` after the read.
- The 3 original indicators' accumulated stats are **byte-identical** to
  what was on disk before — nothing reset, renamed, or recalculated.
- The 10 newly-known indicators start from clean, explicitly zeroed
  defaults (`runs_recorded: 0`, `total_samples: 0`, `last_win_rate: None`)
  — not fabricated or estimated values.
- The old `run_log` entry (3-key `per_indicator`) survives untouched.
- **Idempotent**: reading an already-current file a second time causes no
  file rewrite at all (`os.path.getmtime()` unchanged).
- `record_run()` after migration correctly starts a brand-new indicator
  (`bb`) from a clean slate while correctly continuing to accumulate onto
  a pre-existing indicator's (`wick_rejection`) prior history
  (`runs_recorded` 5→6, `total_samples` 240→265) — and leaves indicators
  untouched by that specific run (`liquidity_sweep`, `false_breakout`)
  exactly as they were.
- Edge case: a file with an entirely empty `rolling_stats: {}` still
  migrates cleanly to all 13 indicators and schema `"1.1"` rather than
  raising.

### Bug found and fixed during this verification
The first migration implementation correctly backfilled the 10 new
`rolling_stats` entries but **never advanced `schema_version` past
`"1.0"`**. Root cause: the general-purpose merge-missing-keys helper
(`_deep_merge_missing()`, unmodified, pre-existing) never overwrites a key
that's already present in the file being read — by design — but it had
*already* silently backfilled the missing indicator keys via its own
recursion into `rolling_stats` (since `_default_history()` now builds all
13 keys, not 3), so the subsequent explicit "did the backfill loop add
anything?" check was comparing against `rolling_stats` state that already
looked fully migrated, and its condition never fired. Fixed by capturing
the **pre-merge** indicator key set before calling `_deep_merge_missing()`
at all, and detecting migration from that pre-merge snapshot instead of
post-merge state. Re-verified with the full test script above — caught
specifically because verification asserted against the actual bytes
written to disk, not just the in-memory return value, which is exactly
what writing a real synthetic old-format file (rather than trusting the
migration logic by inspection) was for.

### Full regression suite after Phase 10.1
`test_phase_8_6.py` (51/51) + `test_phase_9_pipeline_fix.py` (34/34) +
`test_phase_10_1.py` (142/142) = **227/227 passing**.

### Off-limits files — confirmed byte-identical
`diff -rq` against a fresh extraction of the uploaded Phase 9 Stable ZIP
confirmed `analyzer.py`, `backtest.py`, `indicators.py`, `scanner.py`,
`settings_store.py`, `indicator_registry.py`, `backtest_engine.py`, and
every file under `quotex/api_quotex/` are byte-identical. Exactly 4 files
were modified (`indicator_validation.py`, `validation_engine.py`,
`app.py`, `validation_history_store.py`), plus the new test file — no
other diffs of any kind (after excluding `__pycache__` build artifacts).

### Known limitation (honest, not glossed over)
Full Flask-app-level (`app.py` test-client) request/response testing for
the two new summary routes (`GET /api/validation/summary/by-asset`/
`by-timeframe`) was attempted but blocked by missing third-party
dependencies (`pydantic`, transitively required by `quotex/api_quotex/`)
not installable in this sandbox — consistent with this project's standing
"no live network access" constraint (network-library stubbing alone,
sufficient for the one-off Phase 7.4 e2e pass, was not sufficient here).
Route wiring was verified by direct code review plus `py_compile`, and the
aggregation functions the routes call
(`summarize_by_asset()`/`summarize_by_timeframe()`) are directly covered
by `test_phase_10_1.py`. Full Flask-level testing of these two specific
routes remains an open item — not claimed as done.

---

## Phase 9 — Smart Learning & Adaptive Weight System

### Blocker verification (before any Phase 9 code was written)
Simulated the real `app.py` production path end-to-end with real functions
(no mocks): `backtest_factor_accuracy()` → `compute_dynamic_weights()` →
settings weight-scale overlay → `generate_confluence_signal()`, using
synthetic OHLC data. Confirmed `weights_used` in the final confluence
output was completely missing `wick_rejection`/`liquidity_sweep`/
`false_breakout` — i.e. they contributed 0 to every real BUY/SELL/WAIT
decision despite their votes being computed correctly since Phase 8.6.
Re-ran the identical trace after the fix: all 13 keys present, summing to
100.0, the 3 indicators non-zero.

### `tests/test_phase_9_pipeline_fix.py` (34/34 passed)
1. `_DEFAULT_8F_WEIGHTS` shape — 13 keys, sums to exactly 100.0, all 3 new
   indicators present with non-zero defaults, all original 10 still present.
2. `compute_dynamic_weights()` never silently drops the 3 new indicators —
   confirmed `backtest_factor_accuracy()` still never scores them
   (unchanged, documented gap) and they still get their full default
   weight in the output regardless.
3. Original 10 factors' accuracy-to-weight **formula** proven unchanged:
   hand-computed `remaining_budget * (accuracy / total_score)` for a
   synthetic 10-factor accuracy set matches the real function's output
   exactly; the near-random (≤52%) fixed-penalty-of-5 rule also verified
   unchanged. The only thing that changed is the size of the shared budget
   (76.9 instead of 100), which is the necessary, unavoidable, and
   intended consequence of no longer zeroing out the other 3.
4. Full simulated live-pipeline path (all 4 real functions, in the same
   order `app.py` calls them) — all 13 weights present and sum to 100.0 in
   the final `weights_used`.
5. Library-level default path (`generate_confluence_signal()` called with
   no `dynamic_weights` argument) — proven byte-identical to
   `analyzer.DEFAULT_CONFLUENCE_WEIGHTS`, confirming this fix didn't touch
   that code path at all.

### `settings_store.py` fix verification (inline, not a separate test file)
Three checks run directly against real `SettingsStore` instances: (1) a
fresh store now has all 13 indicator entries: (2) an **old-format**
`settings.json` (only 10 indicator keys, with a simulated user
customization of `bb`'s weight to 42.0) correctly backfills the 3 missing
keys with defaults via the existing `_deep_merge_missing()` mechanism,
while leaving the user's `bb` customization at exactly 42.0, untouched; (3)
`apply_suggested_weights()` now actually writes a value for
`wick_rejection`/`liquidity_sweep`/`false_breakout` where it previously
silently no-op'd.

### Learning routes — end-to-end verification (stubbed Quotex chain)
Same offline-sandbox dependency stub used since Phase 8.6 (`loguru`/
`api_quotex` chain unavailable, no network egress) to boot a real Flask
test client. Verified: `GET /api/learning/status` returns 13 weights
summing to 100; `POST /api/learning/generate` persists a snapshot and
`GET /api/learning/history` reflects it; `POST /api/learning/apply`
correctly returns 409 with no Validation History data, and correctly
returns 200 and writes a real weight into `settings.json` once real
history data is seeded; `POST /api/learning/reset` clears the log. Also
confirmed: the full `index.html` template renders with no Jinja error and
contains the new page/nav markup; `indicator_registry.get_registry()`
still returns exactly 13 entries (Phase 9 didn't touch it).

### UI verification
Zero duplicate HTML ids across the whole file after adding the Learning
page; HTML tag-balance check clean; `node --check` clean on `app.js`;
every one of the 3 new buttons (`l-generate-btn`/`l-apply-btn`/
`l-reset-btn`) confirmed to have both HTML markup and a wired
`addEventListener` call; the same 3 pre-existing false-positive
dangling-ID hits from Phase 8.6/8.7 (elements defined in JS-authored
`innerHTML`, not the static template) reappeared and nothing new was
added to that list.

### Regression
`python3 -m compileall` clean on the full tree; `node --check` clean;
`tests/test_phase_8_6.py` still 51/51; `tests/test_phase_9_pipeline_fix.py`
34/34. Full diff against the Phase 8.7 Stable baseline: exactly 6 files
modified (`backtest.py`, `webapp/app.py`, `webapp/settings_store.py`,
`webapp/static/app.js`, `webapp/templates/index.html`, `.gitignore`) and 2
files added (`webapp/learning_engine.py`,
`tests/test_phase_9_pipeline_fix.py`) — nothing else touched anywhere in
the project, including `quotex/api_quotex/`, `analyzer.py`,
`validation_engine.py`, `indicator_validation.py`, `scanner.py`, and
`indicator_registry.py`.

### Known limitations carried forward
- `backtest_factor_accuracy()` still only scores the original 10 factors —
  Learning can only ever produce real (non-`"no_data"`) recommendations for
  the 3 indicators Validation History tracks. This was known going in and
  is unchanged by this phase.
- The 40.0 reliability-vote threshold and the Learning module's own
  min/max-weight and learning-rate defaults are not yet independently
  backtested/calibrated against real outcome data — carried forward from
  Phase 8.6's equivalent note.
- Every earlier phase's test suite before Phase 8.6 remains sandbox-only,
  not persisted to this repo (Phase 8.7's biggest finding, still
  unresolved — Phase 9 added its own persisted test file but did not
  address the broader gap).

## Phase 8.7 — Final Stabilization & Release Audit

### Currently re-runnable vs. historical-only
`tests/test_phase_8_6.py` (51 checks) is the only test file that exists
in this repository and can actually be re-run from it. Every count below
for Phase 8.1 through Phase 8.5 is an accurate historical record of a
sandbox run at the time, but those test files were never committed — this
was a genuine finding of this phase's audit, not something Phase 8.7
introduced. See NEXT_PHASE.md's "PENDING — carried forward from Phase 8.7"
for the follow-up.

### Audit (Steps 1–7, no code changed)
Full repo/performance/security/production-readiness/UI/test/documentation
audit. Real findings: 4 unused imports, 4 stray runtime artifacts, 1
redundant-but-harmless JS block, the test-persistence gap above, and one
cosmetic HTML id-naming inconsistency (`view-*` vs `page-*`). No security
issues, no broken navigation, no duplicate HTML ids, no dangling
`$('id')` references, no corrupted-JSON-handling gaps found. Full detail
in CHANGELOG.md's Phase 8.7 entry.

### Cleanup verification (Step 9, after approval)
- `python3 -m compileall` — clean on the full tree.
- `node --check market_analyzer/webapp/static/app.js` — clean.
- `tests/test_phase_8_6.py` — **51/51**, unchanged from pre-cleanup (none
  of the 5 edited files' behavior changed — 4 were pure import removals,
  1 was a proven no-op JS block removal).
- Full diff against the Phase 8.6 Stable baseline: exactly 5 files
  modified (`fetch_data.py`, `run_analysis.py`, `settings_store.py`,
  `validation_history_store.py`, `app.js`) and 4 files removed
  (`candles.csv`, 3 `log-*.txt`) — nothing else.

## Phase 8.6 — Confluence Engine: connect Wick Rejection, Liquidity Sweep, False Breakout (10 -> 13 factors)

### Pre-phase audit
Extracted and inspected the full Phase 8.5 Stable upload before writing
any code. `python3 -m py_compile` clean across every `.py` file in
`market_analyzer/` and `market_analyzer/webapp/`. A synthetic-data run
confirmed the starting state exactly as documented: `DEFAULT_CONFLUENCE_WEIGHTS`
at 10 factors summing to 100.0, `_confluence_factor_votes()` returning
10 keys, and `wick_rejection_detail`/`liquidity_sweep_detail`/
`false_breakout_detail` already present in `calculate_all()`'s output
(Phase 7.3 Part 3) but not read anywhere in `analyzer.py`. No mismatch
between docs and code found; proceeded.

### New suite: `Quotex/tests/test_phase_8_6.py` (51/51 passed)
Run directly against the real source, synthetic in-memory candle data
only (no network, no live Quotex connection needed):

1. **Weight-dict shape** — `DEFAULT_CONFLUENCE_WEIGHTS` has exactly 13
   keys, sums to exactly 100.0, all 10 original factor names preserved
   unchanged, all 3 new factor names present.
2. **`_confluence_factor_votes()` on random synthetic OHLC data** —
   returns exactly 13 keys including the 3 new ones, every vote value in
   {-1, 0, 1}.
3. **Targeted detector firing → correct vote sign** — hand-built candle
   sequences designed to trigger each detector: a long-lower-wick candle
   correctly produces `wick_rejection: direction=BUY` and a `+1` vote; a
   sell-side liquidity sweep (low undercuts a recent swing low, closes
   back above it) correctly produces `liquidity_sweep: direction=BUY`
   and a `+1` vote; a false resistance break (high pierces a built-up
   resistance zone, closes back below it) correctly produces
   `false_breakout: direction=SELL` and a `-1` vote.
4. **Reliability-threshold gating** — a detail dict with
   `reliability_score` just under 40.0 stays neutral (0) for all 3 new
   factors; a dict at exactly 40.0 does vote — confirms the `>=` gate
   matches the existing `candle`/`sr` convention exactly.
5. **Backward compatibility** — an indicators dict with the 3
   `*_detail` keys entirely absent (simulating an older-format caller)
   raises no exception and votes neutral for all 3 — same fallback
   behavior the `candle`/`sr` factors already had for a missing detail
   dict.
6. **`generate_confluence_signal()` end-to-end** — signal is one of
   BUY/SELL/WAIT on two independent synthetic datasets; `factors` has 13
   entries; `weights_used` sums to 100.0; the Step 1 `confidence_raw`/
   `market_condition` fields (pre-existing, must not regress) are still
   present and unaffected.
7. **`indicator_registry.get_registry()` reflects the connection** —
   all 13 entries returned; `wick_rejection`/`liquidity_sweep`/
   `false_breakout` all report `in_confluence: True` and a non-zero
   `weight` (previously `in_confluence: False`/`weight: 0.0`);
   `NEW_INDICATOR_IDS` unchanged (still the same 3 ids, now purely a
   "new" badge marker, not a connection-status marker).
8. **Off-limits files byte-identical to the Phase 8.5 Stable upload** —
   `backtest.py`, `config.py`, `fetch_data.py`, `run_analysis.py`,
   `deep_backtest.py`, `app.py`, `scanner.py`, `backtest_engine.py`,
   `settings_store.py`, `preflight_check.py`, `validation_engine.py`,
   `validation_history_store.py`, `indicator_validation.py`, and all of
   `quotex/api_quotex/` — every one confirmed byte-for-byte identical,
   no diff.

### Manual/targeted verification (outside the automated suite)
- `python3 -m py_compile` re-run after all edits — clean, zero errors.
- `GET`-equivalent direct call to `indicator_registry.get_registry()`
  (not via Flask — this sandbox lacks the `loguru`/`websockets`/
  `pydantic`/`cloudscraper` packages needed to boot the real Flask app,
  a pre-existing offline-sandbox limitation unrelated to this phase's
  change, same class of gap noted in the Phase 8.4.3 report) confirmed
  `in_confluence: True` and real weights (~7.69/7.72) for all 3 newly
  connected indicators.
- A full unified diff of the entire project tree against the pristine
  Phase 8.5 Stable upload confirms only 3 files changed anywhere:
  `market_analyzer/analyzer.py`, `market_analyzer/indicators.py`,
  `market_analyzer/webapp/indicator_registry.py`. Everything else,
  including all of `quotex/api_quotex/` (Quotex integration untouched)
  and the entire frontend (`templates/index.html`, `static/app.js`), is
  byte-identical.

### Known limitations
- All testing this phase used synthetic data in a sandboxed environment
  with no network access — standing caveat carried from every prior
  phase, unchanged.
- The Flask app itself could not be booted end-to-end in this sandbox
  (missing third-party packages, no network to install them), so the
  `/api/indicators` route was verified by calling
  `indicator_registry.get_registry()` directly rather than through a
  real HTTP round trip. The registry module has no Flask/Quotex
  dependency of its own, so this is a faithful proxy for the route's
  actual behavior, but it is not literally the same code path as a real
  request through `app.py`.
- `backtest.py`'s factor-accuracy scoring still only covers the original
  10 factors — not exercised or extended by this phase's tests, since it
  was explicitly out of scope (see NEXT_PHASE.md).

## Phase 8.5 — Validation History Store


### Pre-phase audit
Re-verified the Phase 8.4.3 Stable baseline before writing any code:
`py_compile`/`node --check` clean, all 4 existing suites passing (Phase
8.1: 40/40, ValidationEngine: 46/46, Phase 8.4.2: 14/14, Phase 8.4.3
API/concurrency: 18/18), all 12 off-limits files plus `scanner.py`/
`settings_store.py`/`validation_engine.py`/`indicator_validation.py`
reconfirmed byte-identical to their respective baselines, Confluence at
exactly 10 factors. Audit finding: `ValidationEngine.results`/`.summary`
are plain in-memory dicts wiped on every `start()` call — nothing
survives a restart, the gap this phase fills.

### Isolated ValidationHistoryStore tests (40/40 passed)
`test_validation_history_store.py`, run directly against the real
source (zero third-party dependencies, no stubs needed):
- Auto-create on first use; `schema_version`/`rolling_stats`/`run_log`
  present with correct defaults for all 3 known indicators.
- **Rolling accumulation math verified by hand-computed expectation:**
  two runs with win rates 60.0 and 40.0 → `average_win_rate_over_runs`
  correctly computed as 50.0; totals (`total_samples`/`total_wins`)
  correctly summed across runs.
- **Sufficient-sample gating applied to the trend itself, not just a
  single run:** a run with `combinations_with_sufficient_sample: 0` is
  still counted in `runs_recorded` and its raw totals, but does NOT
  move `average_win_rate_over_runs` — confirmed the rolling mean stayed
  at 50.0 after an insufficient-sample run reported a would-be-skewing
  rate.
- An all-failed run (empty `per_indicator`) is still logged in
  `run_log` (visible for debugging) but touches no rolling stats.
- **Bounded growth confirmed empirically:** 210 runs recorded →
  `run_log` capped at exactly `MAX_RUN_LOG_ENTRIES=200`, oldest dropped
  first, newest retained.
- `get_indicator_history()` for a known indicator (correct rolling
  stats + filtered run log) and an unknown one (`rolling_stats: None`,
  fails soft rather than raising).
- `reset()` clears both structures back to defaults.
- **True persistence across a simulated restart:** wrote via one
  `ValidationHistoryStore` instance, read back via a brand-new instance
  pointed at the same file path — confirmed the second instance sees
  what the first wrote.
- Forward-compatible backfill: fed a deliberately old-shaped JSON file
  (missing per-indicator rolling entries) — confirmed they're backfilled
  on read without a migration step.
- No leftover `.tmp` file after any write (atomic `os.replace()` working
  as intended). An unrecognized indicator name in a run's
  `per_indicator` doesn't crash or corrupt the known indicators' stats.

### Flask API tests (15/15 passed)
`test_validation_history_api.py`, run against the real `app.py` via
`test_client()`:
- `GET /api/validation/history` works before any run has ever happened;
  correct shape.
- `GET /api/validation/history/<indicator>` — 200 for a known name, 400
  for an unknown one.
- A real (small, fast) validation run → settles to `STOPPED` → **the
  pre-existing `GET /api/validation/status` and `GET /api/validation/results`
  routes confirmed to return their exact same shape as before this
  phase** — no behavior change to the 6 existing routes.
- Polling the new `GET /api/validation/history` route is what triggers
  persistence (app.py-polling-driven, per the explicit zero-
  `validation_engine.py`-change decision) — confirmed a `run_log` entry
  appears after that poll.
- **Idempotency:** polling `/api/validation/history` a second time does
  NOT duplicate the run_log entry (both the in-memory `app.py` guard and
  the store's own `finished_at` dedup were exercised).
- `POST /api/validation/history/reset` → 200, clears rolling stats.
  **Documented non-bug:** since `reset()` only clears the on-disk store
  and does not rewind `app.py`'s in-memory
  `_last_persisted_validation_run_at` guard, the very next history poll
  can immediately re-persist the same already-completed run's summary —
  this is expected (the underlying `ValidationEngine` run itself was
  never un-completed), not a defect, and is called out explicitly in
  the test rather than silently working around it.

### Regression (unaffected)
Phase 8.1 suite: 40/40. ValidationEngine suite: 46/46. Phase 8.4.2
validation suite: 14/14. Phase 8.4.3 API/concurrency suite: 18/18 — all
re-run after Phase 8.5's changes and still passing.

### Off-limits verification
All 12 off-limits files diffed byte-identical to the original upload.
`scanner.py`/`settings_store.py` diffed byte-identical to the Phase 8.3
Recovery baseline. `validation_engine.py`/`indicator_validation.py`
diffed byte-identical to their already-approved Phase 8.4.3 state. The
diff of `app.py` itself was inspected directly to confirm none of the 6
existing validation routes' function bodies appear as removed/changed
lines — only new lines were added (import, instantiation, persistence
helper, 3 new routes, and one import-line addition of `Optional`).

### Bugs found
None. No new issues found in any off-limits file (all confirmed
untouched).

## Phase 8.4.3 — ValidationEngine, Validation Routes, and full Validation UI

### Pre-phase audit — mismatch found and reported before coding
The task assumed `ValidationEngine` and `/api/validation/*` routes already existed. Repo-wide `grep` confirmed neither did (`indicator_validation.py` is plain functions, no class; the only "validation" hits in `app.py` were the unrelated Quotex-session-validation feature). Reported per this project's "code is the source of truth" rule; user approved building the missing pieces as Phase 8.4.3 itself. Baseline re-verified first: `py_compile` clean, Phase 8.1 suite 40/40, Phase 8.4.2 suite 14/14, all 12 off-limits files + `scanner.py`/`settings_store.py` (vs. the Phase 8.3 Recovery baseline specifically) byte-identical, Confluence at exactly 10 factors.

### Isolated ValidationEngine lifecycle tests (46/46 passed)
`test_validation_engine.py` — start/stop/pause/resume, duplicate-start/pause/resume/stop rejection at every applicable state (including the new `STOPPING` transitional state), `status()`/`get_results()` field-completeness, a full natural-completion run with correct `summary.per_indicator` structure for all 3 indicators, graceful handling of a fetch failure for one asset while others still process, and a performance check (`status()`+`get_results()` avg 0.0027 ms/call).

### Flask API + concurrency stress tests (18/18 passed)
`test_validation_api.py`, run against the real `app.py` via `test_client()`:
- Auto-start prevention, all four `400` input-validation cases (unknown asset/timeframe/indicator/candle_count), a real 265-combination run (53 assets × 5 timeframes) with `total_combinations` correctly computed, duplicate-start correctly rejected with `409`.
- **Concurrency stress (the important one): 5 repeated trials of start → pause → resume against the full 265-combination workload — 100% correctly paused, 100% settled to `STOPPED` after resume, 100% processed all 265 combinations post-resume.** See "Concurrency bug found and fixed" below for why this specific test exists.
- Explicit mid-run stop, duplicate-stop rejected with `409`, `cancelled: True` correctly reported after an explicit stop.
- `GET /api/validation/results` shape check, and a performance benchmark: `GET /api/validation/status` averaged **0.32 ms/call** over 100 calls.

### Concurrency bug found and fixed (significant finding)
**Root cause:** `pause()`/`resume()`/`stop()` mutated `self._pause_event` (`asyncio.Event`) directly from the Flask request thread — a different OS thread than the one running `_BG_LOOP`. `asyncio.Event.set()` schedules its internal wake-up via `loop.call_soon()`, which is documented as not thread-safe and does not interrupt the loop's blocking `epoll_wait()` syscall. 

**Why it wasn't caught by the first lifecycle test:** that test's synthetic fetch used `await asyncio.sleep(0.02)`, whose internal `call_later()` timer gave the loop frequent, genuine wake-ups regardless of the thread-safety issue — masking the bug entirely. It was only exposed once tested through the real Flask app with a synchronously-failing fetch (this sandbox has no live Quotex network, so every fetch fails near-instantly with "session file not found" — zero real `await` delay anywhere in that path). Under that condition, a paused run **never resumed, reproducibly, 100% of manual trials before the fix.**

**Fix:** stored the `loop` reference passed to `start()`, and routed all three methods' event mutation through `loop.call_soon_threadsafe(...)`, which uses the loop's self-pipe to guarantee a correct, prompt wake-up regardless of what else is happening on the loop. **Confirmed fixed via 5 repeated stress trials — 100% success rate**, up from 0% before the fix (every manual pre-fix trial reproduced the hang).

**Scope of the fix:** entirely within `validation_engine.py` (a new file created this phase, not off-limits). The identical `pause_event.clear()/.set()` pattern exists in `scanner.py` and `backtest_engine.py` too — both off-limits, neither touched. In practice those engines' real Quotex fetches involve genuine socket I/O, which also registers file descriptors with the loop's selector and provides the same kind of incidental wake-up that masked this bug in the first lifecycle test here — so they may not exhibit this failure mode in normal operation, but the same theoretical risk exists. Flagged for awareness, not acted on (would require modifying off-limits files).

### Regression (unaffected)
Phase 8.1 suite: 40/40. Phase 8.4.2 validation suite: 14/14 (`indicator_validation.py` untouched, checksum unchanged). `BacktestEngine`/`ScannerEngine` routes reconfirmed working via `test_client()` (`GET /api/backtest/status` → 200/STOPPED, `GET /api/scanner/status` → 200/STOPPED).

### Bugs found
One (above) — found, root-caused, fixed, and confirmed via repeated stress testing, entirely within new, non-off-limits code.

### Validation UI — frontend integration testing
Built and approved in 8 incremental steps, each independently verified
before the next began (HTML render + `node --check` + Phase 8.1
regression re-run at every step). Full integration testing after Step 8:
- **Cross-reference:** every `v-*` DOM id referenced anywhere in
  `app.js` (26 static + 24 dynamically-templated `v-sum-*` ids)
  confirmed present in the rendered HTML — 0 missing.
- **Direct function execution (Node, real code — not a mock):**
  `vRenderSummaryCards`, `vRenderResultsTable`, `vRenderProgress`,
  `vAppendToHistory`/`vRenderHistory` were extracted from the actual
  `app.js` and run against a genuine `ValidationEngine.get_results()`
  payload (produced by running a real validation against the sample
  candle CSV) using a minimal DOM stub. Confirmed correct output: e.g.
  Wick Rejection rendered as "54.74% accuracy / 84.65 reliability / 380
  total samples / 380 sell samples / Validated" — all directly matching
  the real backend numbers, not fabricated.
- **Flask end-to-end (11/11):** a run with an explicit request body
  (mirroring exactly what `vBuildRunRequestBody()` sends) → RUNNING →
  pause → resume (re-confirms the Phase 8.4.3 backend concurrency fix
  end-to-end once more) → natural completion → results shape, all via
  `test_client()`.
- **Bug found and fixed during this work:** a text-replacement step
  accidentally dropped the `/* ─── INIT ─── */` comment-block opener,
  breaking `app.js`'s parsing entirely. Caught immediately by
  `node --check` (which every step ran before moving on) — fixed by
  restoring the missing line. Purely cosmetic (a comment delimiter),
  zero logic impact, caught before any further testing proceeded.
- **Off-limits confirmation:** `app.py`'s diff was byte-for-byte
  compared against the already-approved Phase 8.4.3 backend diff and
  found identical — confirming this entire UI integration touched only
  `templates/index.html`/`static/app.js`. `validation_engine.py` and
  `indicator_validation.py` reconfirmed unchanged via checksum.
- **Performance:** `GET /api/validation/status` ~0.29ms, `GET /api/validation/results`
  ~0.25ms, full page render (now including the Validation page) ~0.74ms
  — no regression from adding the new page.
- **Regression:** Phase 8.1 (40/40), ValidationEngine (46/46), Phase
  8.4.2 (14/14), Phase 8.4.3 API/concurrency (18/18) — all re-run and
  passing after the complete UI integration.

**Known, honestly-flagged limitation:** BUY/SELL-split accuracy is not
computable from the current backend output (`validate_indicator()` only
tracks overall win/loss, not per-direction) — rendered as "N/A" rather
than a fabricated number in both the Summary cards and Results table.

## Phase 8.4.2 — Indicator Validation Framework

### Pre-phase audit
Re-verified the Phase 8.3 Recovery Baseline before writing any code:
`py_compile` clean on every touched module, Phase 8.1 regression suite
**40/40 passed**, `DEFAULT_CONFLUENCE_WEIGHTS` confirmed at exactly 10
factors, all 3 new indicators confirmed absent from
`_confluence_factor_votes()`, single `ScannerEngine(` instance confirmed
in `app.py`, scanner default state confirmed `STOPPED`, and all 12
off-limits files (`analyzer.py`, `backtest.py`, `indicators.py`,
`config.py`, `fetch_data.py`, `run_analysis.py`, `deep_backtest.py`,
`indicator_registry.py`, `backtest_engine.py`, `preflight_check.py`,
`gunicorn.conf.py`, `quotex/login.py`) plus everything under
`quotex/api_quotex/` re-diffed byte-for-byte against the original
project upload — **identical, zero mismatches**. No mismatch found;
proceeded to implementation.

### Validation methodology
`market_analyzer/indicator_validation.py` replays each of the 3 new
indicators bar-by-bar over an **expanding window** ending at bar `i`
(`df.iloc[: i + 1]`) — the same "current bar is the last row" framing
every detector already uses when called live. For every bar where a
detector fires (returns non-`None`), the fired `direction` is compared
against the **forward return** `lookahead` bars later (`close[i+lookahead]
- close[i]`, default `lookahead=4`, matching `backtest.py`'s own
default) — a BUY is a "win" if the forward return is positive, a SELL
is a "win" if negative. This mirrors `backtest.py`'s own
vote-then-compare-to-forward-return methodology without importing from
or modifying `backtest.py` itself (see CHANGELOG.md for why a new module
was necessary rather than an extension).

`MIN_SIGNALS_REQUIRED = 20` (mirrored from `backtest.py`'s own gate value,
as an independent constant) — below this sample size, `reliability` is
reported as `None` rather than a number that would look more trustworthy
than the sample supports.

### Validation test suite (14/14 passed)
Run via `test_indicator_validation.py` against real historical candle
data:
- Structural checks: `validate_indicator()` returns every required key;
  `indicator`/`asset`/`timeframe` fields echo the caller's input
  correctly; unknown indicator name raises `ValueError`.
- **Multi-timeframe support:** `validate_all()` correctly processed 3
  timeframes × 3 indicators = 9 result combinations from one call.
- **Multi-asset support:** `validate_all()` correctly handled 2 distinct
  `(asset, timeframe)` dict keys in one call (see Known Limitations for
  what data backed this check).
- **Sample-gating correctness:** a deliberately tiny 40-candle slice
  produced `sufficient_sample: False` and `reliability: None` (not a
  fabricated number) for Liquidity Sweep, confirming the `MIN_SIGNALS_REQUIRED`
  gate works as intended.
- **Performance:** `validate_all()` across 9 (asset, timeframe) × indicator
  combinations (200-candle native series + resampled 30m/1h derivatives)
  measured **~436-600 ms/call** across repeated runs in this sandbox (20
  runs per measurement) — the range itself, not just one number, is
  reported here because a re-run later in this same session showed the
  higher end without any code change in between, indicating shared-sandbox
  CPU variance rather than a regression. The first test-suite threshold
  written for this (`< 500ms`) was an arbitrary guess that turned out
  too tight given that variance — it was loosened to `< 1500ms` (a real
  sanity bound, not a tuned-to-pass number) rather than treating the
  flake as a product bug, since the module itself was not modified
  between runs. This is driven by the nested bar-by-bar replay (each of
  ~165 eligible bars re-invokes
  `detect_support_resistance_zones()` for False Breakout, which itself
  scans the expanding window) — acceptable for this phase's ~200-candle
  sample size, but **this is an O(n²)-ish cost that will need to be
  watched, not re-benchmarked and assumed fine, once run against
  thousands of candles across many real assets** (flagged as a known
  limitation below, not a blocking issue this phase).

### Real-data validation results (full output, for the record)
Ran against `market_analyzer/output/candles.csv` (the only real
historical dataset in this repo — 200 candles, confirmed empirically at
a 15-minute interval) plus that same series resampled to 30m/1h:

| Indicator | Timeframe | Samples | Win Rate | Sufficient Sample | BUY / SELL |
|---|---|---|---|---|---|
| wick_rejection | 15m | 95 | 54.74% | ✅ | 0 / 95 |
| liquidity_sweep | 15m | 6 | 66.67% | ❌ (<20) | 0 / 6 |
| false_breakout | 15m | 47 | 63.83% | ✅ | 0 / 47 |
| wick_rejection | resampled_30m | 36 | 55.56% | ✅ | 0 / 36 |
| liquidity_sweep | resampled_30m | 3 | 66.67% | ❌ (<20) | 0 / 3 |
| false_breakout | resampled_30m | 6 | 66.67% | ❌ (<20) | 0 / 6 |
| wick_rejection | resampled_1h | 6 | 50.00% | ❌ (<20) | 0 / 6 |
| liquidity_sweep | resampled_1h | 1 | 0.00% | ❌ (<20) | 0 / 1 |
| false_breakout | resampled_1h | 4 | 75.00% | ❌ (<20) | 1 / 3 |

**Only 2 of the 9 combinations reached the `MIN_SIGNALS_REQUIRED=20`
sample-size gate** (wick_rejection@15m and false_breakout@15m) — every
other combination's win rate is reported for completeness but is NOT
statistically reliable at this sample size, and `reliability` is
correctly `None` for all of them.

### SELL bias observation (significant finding)
**151 of 152 total fired signals across all 9 combinations were SELL —
a single BUY (false_breakout @ resampled_1h) was the only exception.**
This is consistent with the raw finding from the Phase 8.4.1 audit (which
found the same 100%-SELL pattern on the native 15m series alone) and now
extends across resampled timeframes too. Two honest, undetermined
explanations, **neither confirmed**:
1. The one available real dataset has a mild net downtrend (-0.92% over
   the sampled window, per Phase 8.4.1's finding) — a single-regime,
   short window could produce this by chance.
2. There could be a genuine directional asymmetry in the detection logic
   itself (`indicators.py`, off-limits to modify or even suspect further
   without evidence).
**No conclusion is drawn here — this is exactly the kind of finding
Phase 8.4.2 exists to surface, not resolve.** It should not be treated as
evidence for or against connecting these indicators to Confluence; more,
more varied, real data is needed first (see Known Limitations).

### Known limitations (stated plainly)
- **Sample size and diversity:** only one real, unlabeled, single-regime,
  200-candle dataset exists in this sandbox (no live Quotex network
  access at any point in this project's history). The 30m/1h series
  used to test multi-timeframe support are **resampled from that same
  one series**, not independent real data — clearly labeled
  `resampled_30m`/`resampled_1h` in all output, never presented as
  additional real market data.
- **Multi-asset test used synthetic data:** the "multi-asset" structural
  test used two disjoint slices of the same one real series (labeled
  `synthetic_slice_a`/`synthetic_slice_b`), proving `validate_all()`'s
  dict-keyed API correctly handles multiple entries — it does **not**
  demonstrate cross-asset behavioral validity, since it's the same
  underlying market data split in two.
- **Performance at scale is unverified:** the ~436ms/9-combinations
  figure was measured on 200 candles; nothing here has been tested
  against a realistic production-scale replay (thousands of candles ×
  dozens of assets × multiple timeframes). The nested
  `detect_support_resistance_zones()` call inside the False Breakout
  path is the most likely bottleneck to re-check first.
- **7 of 9 tested combinations are below the reliability threshold** —
  meaningful accuracy conclusions currently exist for only 2 combinations
  (wick_rejection and false_breakout, both at the native 15m timeframe).

### Recommendation for future phases
Given the above, this framework should **not** be treated as sufficient
evidence — on its own — to recommend connecting any of these 3
indicators to Confluence. What it does establish: the framework itself
works correctly (14/14 structural/functional tests passing), and it
surfaces a real, reproducible directional-bias pattern that deserves
investigation with more/varied real data before Phase 8.4.3's weight/
reliability-score calculations are given much weight, and certainly
before Phase 8.4.5's eventual connect/don't-connect recommendation.

### Bugs found
None in this phase's own code. No new issues found in
`indicators.py`/`backtest.py`/`analyzer.py` (all confirmed untouched and
byte-identical to the original upload).

## Phase 8.3 — Smart Scanner Advanced Controls & Settings Integration

### Pre-phase audit
- `py_compile` on `app.py`, `scanner.py`, `settings_store.py` — clean.
- Full re-run of the Phase 8.1 isolated test suite (`test_phase_8_1.py`) before touching any code — **40/40 passed**, confirming the starting state matched what prior phases claimed.
- `grep -c "ScannerEngine("` in `app.py` → **1** — single scanner instance confirmed before starting.
- `grep` confirmed none of the 3 new indicators (Wick Rejection, Liquidity Sweep, False Breakout) appear in `_confluence_factor_votes()` or `DEFAULT_CONFLUENCE_WEIGHTS` — still disconnected, as required.

### Off-limits checksum verification (completed this turn)
Rather than only compare against in-session snapshots, every off-limits file was `diff`'d directly against the **original, never-modified project zip** (re-extracted fresh to a separate directory):
`analyzer.py`, `backtest.py`, `indicators.py`, `config.py`, `fetch_data.py`, `run_analysis.py`, `deep_backtest.py`, `indicator_registry.py`, `backtest_engine.py`, `preflight_check.py`, `gunicorn.conf.py`, every file under `quotex/api_quotex/`, and `quotex/login.py`.
**Result: all identical, zero diffs** (the only reported difference across the whole comparison was an auto-generated `__pycache__/` directory under `quotex/api_quotex/`, which is not source and is expected). `settings_store.py`, `scanner.py`, and `app.py` were also diffed against the original and — as expected and intended — do differ, containing exactly the Phase 8.1/8.2/8.3 additive changes documented in CHANGELOG.md.

### Bug found and fixed
See CHANGELOG.md for full detail: `get_results()`'s freshness tie-break was sorting ascending (oldest-first) instead of descending (newest-first) as its own comment claimed. Fixed with a new `_parse_iso_epoch()` helper + negation. Verified with a dedicated test using two identical-scoring synthetic cache entries differing only in `last_update` — confirms the fresher one now ranks first (previously the reverse).

### Flask end-to-end regression (23/23 passed)
Run against the real Flask app via `test_client()`:
- Auto-start prevention (state `STOPPED` immediately after import) — confirmed unchanged.
- `GET /api/settings` includes the `scanner` section with all Phase 8.1 defaults intact.
- `POST /api/settings` with a `{"scanner": {...}}` patch persists `minimum_filter_score`, `top_signals`, `enabled_timeframes` — confirmed via an immediate follow-up `GET /api/settings`.
- `POST /api/scanner/settings/reset` restores `scanner_enabled`/`minimum_filter_score` to defaults **while leaving the `backtest` section (and by extension every other section) untouched** — confirms the scoped reset doesn't leak into a full reset.
- Full lifecycle (start → duplicate-start-rejected → pause → resume → **settings save while RUNNING → state still RUNNING, unchanged** → stop → duplicate-stop-rejected) — all steps passed, using polling-with-timeout rather than fixed sleeps throughout.
- `current_timeframe`, `last_scan_time`, `current_cycle` all present in `get_status()`'s live response during a run.

### True persistence-across-restart test
Beyond the Flask-level "save then re-GET" check above, persistence was verified independently at the `SettingsStore` level: wrote a value via one `SettingsStore` instance, then instantiated a **second, brand-new `SettingsStore`** pointed at the same file path (simulating a genuine process restart, not just a re-read through the same object) — confirmed the second instance read back the exact values the first one wrote.

### Regression
Full Phase 8.1 suite (`test_phase_8_1.py`) re-run after all Phase 8.3 backend changes — **40/40 still passing**.

### Frontend validation
- `node --check static/app.js` — clean, no syntax errors, after the full Settings-card/status-panel/results-table rewrite.
- CSS brace-balance check on `static/style.css` — 345 open / 345 close, balanced.
- DOM-id cross-reference: every `ss-*` id referenced anywhere in `app.js` (31 total) was checked against the server-rendered `GET /` HTML — **31/31 present**, zero missing.

### Performance benchmarks (this turn)
All measured against the real Flask app via `test_client()` (200 calls each, avg + p95 reported; sandbox has no live Quotex network, so `GET /api/scanner/results` reflects a cache with 0-2 entries — see caveat below):

| Operation | Avg | p95 |
|---|---|---|
| `GET /api/settings` (load) | 0.34 ms | 0.48 ms |
| `POST /api/settings` (save, scanner patch) | 0.83 ms | 0.99 ms |
| `GET /api/scanner/status` (stopped) | 0.22 ms | 0.38 ms |
| `GET /api/scanner/status` (running) | 0.24 ms | 0.39 ms |
| `GET /api/scanner/results` (running, ranking + serialization) | 0.24 ms | 0.34 ms |

**No measurable regression** versus Phase 8.1/8.2's numbers (`get_status()`/`get_results()` direct-call average was ~0.006-0.02 ms; the ~0.2-0.9 ms figures above include the full Flask request/response/JSON-serialization round trip via `test_client()`, not just the bare method call, so they aren't directly comparable 1:1 but are consistent with "sub-millisecond, no regression"). Frontend `ssRenderResults()`/`ssRenderStatus()` rendering cost was not separately benchmarked in this no-browser sandbox (no DOM/jsdom available) — the dominant, measurable cost is the backend ranking/serialization step benchmarked above; the frontend work is a simple `.map().join()` over at most `top_n` (≤30) rows, the same pattern and scale already used by the Backtest page's results table.

**Caveat, stated honestly:** this sandbox has no live Quotex network access, so results-cache size during the "running" benchmark was small (0-2 entries, both failing with a session-file-not-found error) rather than a fully populated 53-asset scan. The ranking/sort/gate logic exercised is identical regardless of cache size, but the absolute timing numbers above should be read as "well under 1ms at this scale," not as a guarantee at full production cache size — a live environment should re-check `GET /api/scanner/results` timing once the cache is at typical size.

### Bugs found
One (see above) — a real, pre-existing sort-direction bug in `scanner.py`, found via the mandatory pre-phase audit and fixed. No bugs found in any Phase 8.3-authored code itself.

## Phase 8.2 — Smart Scanner (user-facing UI)

**Sandbox note:** this phase finally achieved the full end-to-end
Flask test-client pass that Phase 8.1 could not — the missing
`pydantic` dependency (blocking `quotex/api_quotex/models.py`) was
resolved by adding a minimal functional stub (`BaseModel`/`Field`
supporting annotations, defaults, and `default_factory`) to the
shared stub environment, alongside the already-stubbed
`loguru`/`websockets`(including `.legacy.client`)/`aiohttp`/`socketio`/
`playwright`(including its `TimeoutError`)/`cloudscraper`. With that in
place, `app.py` imports cleanly and every test below runs against the
**real** Flask app via `app.test_client()` — not a mock.

### Frontend syntax check
`node --check static/app.js` — passes, zero syntax errors.
Brace-balance check on `static/style.css` (340 open / 340 close) — balanced.

### Template render / DOM id cross-check
`GET /` → **200**. Cross-referenced every `ss-*` id referenced in
`app.js` against the rendered HTML — **all 14 present**
(`ss-start-btn`, `ss-pause-btn`, `ss-resume-btn`, `ss-stop-btn`,
`ss-error-box`, `ss-state`, `ss-progress-pct`, `ss-progress-bar-fill`,
`ss-current-asset`, `ss-assets-completed`, `ss-elapsed`, `ss-eta`,
`ss-results-slot`, `page-smart-scanner`), plus the new
`data-nav="smart-scanner"` drawer link. Zero missing.

### Flask route lifecycle test (11/11 passed)
Run against the real app via `test_client()`, exercising the exact
routes the new page calls:
- **Auto-start prevention test:** `GET /api/scanner/status` immediately
  after `app.py` import returns `state: STOPPED` — confirms nothing in
  this phase (or any prior phase) starts the scanner on import/page
  load.
- **Start test:** `POST /api/scanner/start` → `{"ok": true}`,
  subsequent status shows `RUNNING`.
- **Duplicate start test:** a second `POST /api/scanner/start` while
  running → `{"ok": false}`.
- **Pause test / Resume test:** both succeed and the status reflects
  `paused: true` / back to `RUNNING` respectively.
- **Stop test:** `POST /api/scanner/stop` → `{"ok": true}`; polled
  (not fixed-sleep) until status genuinely reaches `STOPPED`.
- **Duplicate stop test:** a second `POST /api/scanner/stop` after
  already stopped → `{"ok": false}`.

**Result: 11/11 passed, 0 failed.**

### Regression test
Re-ran the full Phase 8.1 isolated test suite (`test_phase_8_1.py`)
unchanged after all Phase 8.2 frontend edits — **40/40 still passing**,
confirming the frontend-only changes did not affect `scanner.py` or
`settings_store.py` behavior in any way (expected, since no backend
file was touched this phase). Re-checksummed the same off-limits file
set from Phase 8.1 (`analyzer.py`, `backtest.py`, `indicators.py`,
`config.py`, `indicator_registry.py`, `backtest_engine.py`, all of
`quotex/api_quotex/*.py`) — unchanged.

### Safety verification
- `grep -c "ScannerEngine("` in `app.py` → **1** (unchanged from Phase
  8.1) — no duplicate scanner instance was created.
- `_BG_LOOP` remains the single shared background loop; no new
  `QuotexDataFetcher`/`AsyncQuotexClient` instantiation was added
  (both call sites are pre-existing, in `app.py`/`fetch_data.py`,
  untouched this phase).
- No changes anywhere under `quotex/api_quotex/` (confirmed via
  checksum, see above) — no WebSocket code touched.

### Bugs found
None in `templates/index.html`, `static/app.js`, or `static/style.css`.
One test-harness timing issue was found and fixed in the test script
itself (see CHANGELOG.md) — not a product bug.

## Phase 8.1 — Smart Scanner Core Enhancement

**Sandbox note:** run in the same offline, no-network sandbox as every
prior phase. Testing here targeted the two modules actually changed
(`scanner.py`, `settings_store.py`) plus `app.py`'s wiring, directly and
in isolation, using a synthetic `run_pipeline` callable (same style as
prior phases' synthetic-data testing) — not the real Quotex pipeline.

### Compile tests
`python3 -m py_compile` on `scanner.py`, `settings_store.py`, `app.py` —
all pass, zero exceptions.

### Full end-to-end Flask app.py test — partial
Attempted the same test-client approach Phase 7.4 used (stubbing
`loguru`/`websockets`/`aiohttp`/`socketio`/`playwright`/`cloudscraper`).
`app.py`'s import chain in this sandbox additionally requires `pydantic`
(via `quotex/api_quotex/models.py`), which is not installed and could not
be installed here (no network access for `pip install pydantic` in this
sandbox — this dependency was apparently available in whatever sandbox
Phase 7.4 ran in, but is not present in this one). Rather than write a
full pydantic stub (which would go beyond exercising this phase's actual
changes), verified the `app.py` wiring by direct source inspection
instead: confirmed `settings_store = SettingsStore(...)` now executes
before `_scanner = ScannerEngine(...)`, and confirmed the `ScannerEngine`
call includes `settings_store=settings_store`. `python3 -m py_compile`
on `app.py` passed, confirming no syntax/reference errors from the
reorder. **Honesty note, stated explicitly per this project's standing
practice:** full live-route testing of `/api/scanner/*` through the real
Flask app was NOT performed this phase, unlike Phase 7.4's broader
end-to-end pass — the isolated `ScannerEngine`/`SettingsStore` testing
below is what was actually run and verified.

### Isolated ScannerEngine + SettingsStore tests (40/40 passed)
Run directly against the real `scanner.py`/`settings_store.py` source
(not stubs) with a synthetic `run_pipeline` and a real background
asyncio loop (mirrors `app.py`'s `_BG_LOOP` pattern):

- **Backward compatibility (`settings_store=None`):** starts `STOPPED`,
  never auto-starts, `start()` succeeds, state becomes `RUNNING`,
  `_effective_assets` equals the full asset list, `_minimum_filter_score`
  defaults to `0.0`.
- **Scanner lifecycle:** start → running → pause → resume → stop → 
  stopped, all verified via polling with timeouts, not fixed sleeps.
- **Duplicate start test:** second `start()` while already running is
  rejected (`ok: False`, "already ..." message), state unaffected.
- **Duplicate stop test:** second `stop()` after the scanner has already
  reached `STOPPED` is rejected (`ok: False`).
- **Pause test / Resume test:** both succeed at the expected state
  transitions (`RUNNING`→`PAUSED`→`RUNNING`).
- **Progress field validation:** `assets_completed`, `percent_complete`,
  `elapsed_time`, `estimated_remaining`, `total_assets`, `current_asset`
  are all present in `get_status()`; `assets_completed` increments and
  `percent_complete` becomes positive once a cycle is underway;
  `elapsed_time` is a non-negative number.
- **Settings enabled/disabled test:** `scanner.scanner_enabled=False` in
  a real `SettingsStore` (temp-file backed) blocks `start()` with an
  explanatory message and leaves state `STOPPED`; re-enabling allows
  `start()` to succeed again.
- **scanner_enabled OFF test:** covered by the above — confirmed the
  scanner never transitions out of `STOPPED` while disabled.
- **`enabled_assets` narrowing:** setting a 2-asset subset in
  `SettingsStore` results in `_effective_assets` equal to exactly that
  subset, and `get_status()["total_assets"]` reflects the narrowed count.
- **`minimum_filter_score` gating:** with the synthetic pipeline
  returning `filter_score=75.0`, setting `minimum_filter_score=90.0`
  hides all results from `get_results()`; resetting to `0.0` (the
  default) shows them again — confirms the gate is additive and
  opt-in only.
- **Broken settings_store resilience:** a `settings_store` whose `.get()`
  always raises `RuntimeError` still allows `start()` to succeed
  (defensive read swallows the exception, logs a `settings_read_failed`
  event, and falls back to `None`/pre-Phase-8.1 behavior).
- **Regression test:** a `ScannerEngine` built with a real,
  all-defaults `SettingsStore` produces the identical `_effective_assets`,
  `_minimum_filter_score` (`0.0`), `cfg.top_n`, and `cfg.timeframes` as
  one built with `settings_store=None` — confirms defaults are a true
  no-op, not just "close enough."
- **`status()`/`results()` alias test:** both new methods return the
  exact same key set as `get_status()`/`get_results()` respectively.
- **Performance/memory test:** 200 back-to-back
  `get_status()`+`get_results()` call pairs (400 calls total) while a
  scan cycle was actively running averaged **~0.006 ms/call** — no
  measurable regression versus the pre-Phase-8.1 cost (`get_results()`
  ~0.02 ms for 53 cached assets, per `PROJECT_STATUS.md`'s existing
  benchmark table).

**Result: 40/40 checks passed, 0 failures.**

### Bugs found
None. No pre-existing bug was uncovered in `scanner.py`/`settings_store.py`
during this phase's testing (unlike several prior phases — see the
"Bug fixes" list below, which remains from before this phase).

### Checksums confirming untouched files
Before writing this report, `md5sum` was run on every file this phase
was NOT supposed to touch (`analyzer.py`, `backtest.py`, `indicators.py`,
`config.py`, `fetch_data.py`, `run_analysis.py`, `deep_backtest.py`,
`indicator_registry.py`, `backtest_engine.py`, `preflight_check.py`,
`gunicorn.conf.py`, and all of `quotex/api_quotex/*.py`) — recorded as a
baseline; no further edits were made to any of them after that point.

**Standing caveat, applies to every test below:** all testing was performed
in a sandboxed environment with NO network access, using synthetic data
generated in-process. Nothing has been tested against live Quotex data or
the real Flask HTTP layer.

## Compile tests
`python3 -m py_compile` run on every modified file at the end of every
single phase in this project, with zero exceptions. Always passed after
fixes were applied (a few iterations needed mid-phase, e.g. indentation
bugs caught immediately by compile checks).

## Regression tests
- **Step 4.1:** 200-trial fuzz test confirming 8 pre-existing confluence
  factors byte-identical after OBV addition — 0 mismatches.
- **Phase 5:** 3000-trial fuzz test confirming 4 original candlestick
  patterns byte-identical after the 9-pattern upgrade — 0 mismatches.
  Additional 50-seed/163-bar backtest-vs-live consistency check — 0
  direction flips.
- **Phase 6:** 100-trial fuzz test confirming `support_resistance()`
  legacy formula byte-identical — 0 mismatches. Confirmed the other 9
  confluence factors unaffected by SR factor presence/absence.
- **Phase 7:** Confirmed confidence/BUY-SELL/confluence weights unchanged
  after Filter Score v1 introduction.
- **Phase 7.1:** 1000-trial fuzz test — filter_score always 0-100,
  breakdown always sums to 100, even with malformed/None input.
- **Phase 7.2/7.3:** Confirmed `analyzer.py`/`scanner.py` files untouched
  (no duplicate function definitions found via grep) when building
  `backtest_engine.py`/`indicator_registry.py`.

## Performance tests
See `PROJECT_STATUS.md`'s benchmark table. Notable honest findings (not
downplayed):
- Phase 5's candlestick backtest loop: ~3x slower after the 9-pattern
  upgrade (45ms -> 130ms on 250 candles) — reported as-is.
- `BacktestEngine` orchestration overhead: 5.37% over raw `backtest.py`
  calls — reported as-is, attributed mostly to progress-reporting yield
  points, not hidden.

## Memory tests
Phase 7.2: explicit test confirming no `pandas.DataFrame` object is
retained anywhere in `BacktestEngine.results` after a run completes
(`del df` executed, verified by type-checking every value in every result
dict).

## Backtest tests
- `backtest_factor_accuracy()`/`compute_dynamic_weights()`: verified weight
  output always sums to exactly 100.0 across 200 randomized scenarios
  (Phase 6), and again after the Phase 7.3 registry-populate integration.
- `backtest_filter_score_report()`: verified internal consistency (bucket
  trades sum to total_trades, wins+losses=trades, accuracy in [0,1]) on
  both the v1 (binary) and v2 (graded) implementations.
- `BacktestEngine` lifecycle: start/pause/resume/stop/restart all verified
  functionally correct using a genuine dedicated background thread (after
  an initial same-thread test harness artifact was identified and
  corrected — documented as NOT an engine bug).

## Scanner tests
- Full lifecycle test (start -> running -> completed -> stopped).
- Pause/resume (confirmed zero progress while paused).
- Manual-request-priority yielding (`YIELDING` state).
- DEGRADED/RECOVERING state transition under sustained simulated failures.
- Ranking correctness (`mandatory_pass` visibility gate, verified
  independent of `filter_score` value after the Phase 7.1 rewrite).

## Edge cases tested
- Empty DataFrames, <2/<3-row DataFrames, all-NaN OHLC, zero-range (flat)
  candles, zero/negative ATR, malformed settings dicts, out-of-range
  numeric inputs (negative ADX, payout > 100, etc.) — across indicators.py,
  analyzer.py, backtest.py, scanner.py, settings_store.py.

## Bug fixes (found during testing, all documented in CHANGELOG.md)
1. `_FACTOR_LABELS` missing OBV entry (Step 4) — found and fixed same session.
2. Scanner's `_check_hard_gates()` duplicated gate logic (Phase 7) — refactored to call the shared `calculate_filter_score()`.
3. Scanner ranking incorrectly excluded valid signals when only the non-mandatory candlestick criterion failed (Phase 7) — fixed to key off `filter_score`/later `mandatory_pass`.
4. `evaluate_apply_conditions()` didn't check the run's actual candle count against the policy minimum (Phase 7.2) — fixed.
5. `backtest_filter_score_report()` referenced an undefined `_FS_SR_NEAR_ZONE_ATR` constant (Phase 7.1) — added.
6. `BacktestEngine`'s inter-cycle idle sleep (in the earlier Scanner engine, same class of bug) was not interruptible by `stop()` — fixed to a chunked, stop-aware sleep loop.
7. `validation_history_store.py`'s schema-version migration (Phase 10.1) never advanced `schema_version` past `"1.0"` on a real old-format file, because the generic merge-missing-keys helper had already silently backfilled the new indicator keys via its own recursion before the explicit "did we migrate?" check ran against already-migrated-looking state — fixed by detecting migration from the pre-merge key set instead.
8. `asset_timeframe_learning.py`'s (Phase 10.2) asset/timeframe ranking order used raw accuracy alone with no sample-size gate, letting a tiny (e.g. 3-of-5) sample outrank a large, reliable one (e.g. 55-of-100) — fixed by requiring `min_samples` for inclusion in the ordered ranking list, same gate already applied to best/weakest indicator selection elsewhere in the same module.

## Known limitations (repeated for completeness — see PROJECT_MEMORY.md for full rationale)
- MTF and Payout are structurally unbacktestable.
- Backtest Filter Score buckets 20-40/40-60/60-80 remain sparse by design.
- No live-network or browser testing has ever been performed in this project.

---

## Phase 7.4 — Settings/Backtest/Indicators/Session routes + full frontend

**Sandbox note (update from prior phases):** this phase's testing went further than "no network access" previously allowed — the full `app.py` import chain (including `fetch_data`/`api_quotex`) was exercised end-to-end via Flask's test client, with only the missing third-party network/browser libraries (`loguru`, `websockets`, `aiohttp`, `python-socketio`, `playwright`, `cloudscraper` — none of which are installable in this offline sandbox, and none of which were touched by this phase) stubbed as no-ops. The real `api_quotex.constants.ASSETS`/`TIMEFRAMES` data was loaded directly from source (bypassing only the package `__init__.py` that pulls in the network chain), so asset/timeframe validation was tested against actual production data, not synthetic substitutes. Actual Quotex connectivity (`connect()`, `get_candles_df()`) is still untested — those calls raise `ConnectionError` in the stub, by design, and routes that depend on them (`/api/session/validate`, `/api/backtest/run`'s actual data-fetch step) were tested only for their pre-flight validation/status-code behavior, not live results.

### Compile tests
`python3 -m py_compile` on `app.py`, `backtest_engine.py`, `settings_store.py`, `indicator_registry.py` — all pass, zero exceptions. `node --check static/app.js` — pass. Jinja template (`templates/index.html`) rendered successfully via a real Flask app/request context with sample data. CSS brace-balance check on `static/style.css` — 331 open / 331 close.

### Regression tests (backend)
- 200-trial fuzz test: `settings_store.get_effective_dynamic_weights()` with randomized indicator-disable subsets — sum is always exactly 100.0 (or 0.0 if all disabled), after the rounding-drift bug fix below.
- Verified the Settings→confluence weight-override layer (`app.py`'s `_apply_settings_weight_overrides()`) is a byte-identical no-op against a realistic non-uniform live-computed `dynamic_weights` dict when settings are untouched, and correctly zeroes + proportionally renormalizes when an indicator is disabled.
- Verified `get_filter_score_config_overrides()`'s shipped defaults (`adx_trending=25.0`, `atr_extreme_pct=1.5`, `min_payout=80.0`) match `analyzer.py`/`config.py`'s existing constants exactly — confirms the filter-score override wiring is byte-identical at defaults.
- `indicator_registry.get_registry()`: confirmed 13 entries, 10 `in_confluence=True` / 3 `in_confluence=False` (`wick_rejection`, `liquidity_sweep`, `false_breakout`), matching `INDICATOR_DOCUMENTATION.md` exactly.
- `backtest_engine.evaluate_apply_conditions()` on a fresh/never-run engine correctly returns `can_apply=False`.

### Regression tests (API — via Flask test client, real ASSETS/TIMEFRAMES, see sandbox note above)
40/40 checks passed across: page render (all 4 new page IDs present, old static Auto-Scanner-always-on card text gone), Settings (get/update/reset/backups/backup/restore/export/import + rejects non-dict import), Indicators (13 entries returned, disable-via-Settings reflected through the registry overlay), Backtest (status/results/apply-weights-rejects-on-empty-run), Session (status/update rejects short SSID/accepts valid-looking SSID/status reflects the save), and frontend static checks (no unconditional `startAutoScan()` call, `_autoScanEnabled` flag present, `beforeunload` stops the scanner, all 3 new views registered, `app.js` syntax valid).

### `/api/backtest/run` status-code regression (targeted, post-fix)
- Invalid `candle_count` → 400. Unknown asset → 400. Invalid timeframe → 400. `assets` not a list → 400. Non-numeric `candle_count` → 400.
- Backtest already `RUNNING` (engine state forced for the test, without touching `backtest_engine.py`) → 409.
- Valid request while `STOPPED` → 200, `{"ok": true}`.
- (One test assumption was itself wrong, not a code bug: sending `"assets": []` explicitly falls back to all-OTC via the same `or` default used for a missing `assets` field — this matches the frontend's own "All OTC" mode and every real caller's expectation; there is no code path where an explicit empty list needs to be distinguished from "not specified".)

### Performance tests
| Function | Cost |
|---|---|
| `settings_store.get()` (disk-backed read, per `_run_pipeline()` call) | ~0.035 ms/call |
| `get_effective_dynamic_weights()` + `get_filter_score_config_overrides()` combined | ~0.083 ms/call |
| `app.py`'s `_apply_settings_weight_overrides()` | ~0.007 ms/call |
| `indicator_registry.get_registry()` + `apply_settings_overrides()` (used only by `/api/indicators`, not per-pipeline-request) | ~0.009 ms/call |

All well under 1ms — negligible overhead added to `_run_pipeline()`'s per-request cost by the Phase 7.4 settings-override layer. `settings_store.get()` reads `settings.json` from disk on every call by design (documented in the module's own docstring — no shared in-memory cache, so multiple Gunicorn workers can't desync); this is the dominant cost of the four and is still sub-millisecond in this sandbox's filesystem.

### Bug fixes (found during Phase 7.4 testing, both documented in CHANGELOG.md)
1. `settings_store.get_effective_dynamic_weights()`'s per-key rounding could leave the renormalized sum a few `0.0001` short of exactly 100 — fixed by assigning the rounding residual to the largest weight. Same fix applied to `app.py`'s analogous new code.
2. `/api/backtest/run` returned 409 (Conflict) for client input errors that should have been 400 (Bad Request), because `BacktestEngine.start()`'s return shape doesn't distinguish the two cases — fixed by checking the actual conflict condition in `app.py` before calling `start()`, without modifying `backtest_engine.py`.

### Not tested (explicitly, honestly)
- Live Quotex connectivity for `/api/session/validate` and `/api/backtest/run`'s actual candle-fetch step — no network access in this sandbox.
- Real browser rendering/interaction (no display/jsdom available) — frontend correctness was verified via template rendering + DOM-ID cross-referencing between `static/app.js`'s `$('id')` calls and the rendered HTML (0 missing IDs, after excluding IDs that are created dynamically via `innerHTML` and queried in the same function — verified by inspection, not a false positive) + `node --check` syntax validation, not actual click-through testing.
