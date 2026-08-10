# NEXT PHASE — Exact Remaining Work

This is the most important file for a continuing AI/engineer. Read this
before touching any code.

---

## PHASE 10.4 (GOALS 1-5) — COMPLETE

Everything in CHANGELOG.md's Phase 10.4 entry was scoped, built, tested,
and documented this phase. Do not re-implement any of it — see
CHANGELOG.md for the full diff and TEST_REPORT.md for what was verified
(267/267 new tests, 814/814 full-suite, off-limits files byte-identical).

### Candidate PHASE 10.5 work (not started, not scoped — suggestions only)
- Wire a live-fetch route for Walk-Forward Testing and the df-dependent
  Adaptive Calibration functions (Goal 1/2's documented scope boundary)
  — needs a decision on which existing fetch path to reuse
  (`_run_pipeline()`'s candle-fetch, most likely) and how to bound
  request cost, since a walk-forward run needs substantially more
  candles than a single-signal request.
- A background scheduler to record AI Health snapshots on a fixed
  cadence independent of `/api/ai/history/*` being polled (currently
  the log only grows when those routes are hit) — would need a new,
  carefully-scoped audit of whether that belongs next to the scanner's
  existing loop or as a fully separate thread, since `scanner.py` itself
  is off-limits.
- Real end-to-end route testing once network access to install
  `loguru`/`websockets`/`cloudscraper` (or equivalent) is available in
  the development sandbox — every Phase 10.4 route has been verified by
  source inspection only, never an actual HTTP request/response.

---

## PHASE 7.4 — COMPLETE

Everything below was scoped, built, tested, and documented this phase.
Do not re-implement any of it; see `CHANGELOG.md` for the full diff and
`TEST_REPORT.md` for what was verified.

- Settings Flask routes (`GET/POST /api/settings`, `/reset`, `/backups`,
  `/backups/restore`, `/export`, `/import`, `/backup`) — done.
- Backtest Flask routes (`/run`, `/pause`, `/resume`, `/stop`, `/status`,
  `/results`, `/apply-weights`) — done, with correct 400/409/500 status
  codes (a real bug in the original 400/409 split was found and fixed).
- Quotex Session routes (`/status`, `/update`, `/validate`) — done.
- Indicator Registry route (`GET /api/indicators`), now also layering in
  real accuracy/dynamic_weight/sample_size from the most recently
  completed backtest run — done.
- `_run_pipeline()` wired to Settings (indicator enable/disable + weight
  scale, filter-score threshold overrides) — done, verified byte-identical
  at default settings, verified NOT to touch `analyzer.py`'s Dynamic
  Weight algorithm (see the Design Decision note in `CHANGELOG.md` for
  why a scaling layer was used instead of the literal replacement
  originally described).
- Backtest candle-count options expanded to 500/1000/1500/2000/3000/5000.
- Full frontend: Settings page (dynamic/editable), Backtest page
  (run/pause/resume/stop, progress+ETA, results table, apply weights),
  Indicators page (all 13 shown, 10 toggleable, 3 clearly badged as not
  yet connected), Quotex Session page (SSID paste/save/validate) — done.
- Auto Scanner auto-start bug fixed: it previously started on every page
  load via an unconditional `navigateTo('scanner')` call; now it only
  starts via an explicit "Enable Auto Scanner" toggle, stops on page
  close, and is always OFF on a fresh load/reopen — done.
- Generic `/api/*` error handler added (`@app.errorhandler(500)` +
  `@app.errorhandler(Exception)`, HTTPExceptions like 404 pass through
  unchanged) — done.
- `.gitignore`: `settings.json`/`settings.json.backups` added — done.
- Full doc suite regenerated (this file, `PROJECT_STATUS.md`,
  `CHANGELOG.md`, `TEST_REPORT.md`, `README.md`, plus new `HANDOFF.md`
  and `RELEASE_NOTES.md`) — done.

**Deliberately still NOT done, unchanged from Phase 7.3 (same reason as
before — explicit deferral, not an oversight):**
- Connecting the 3 new indicators (Wick Rejection, Liquidity Sweep, False
  Breakout) to the confluence engine. `DEFAULT_CONFLUENCE_WEIGHTS` in
  `analyzer.py` and `_DEFAULT_8F_WEIGHTS` in `backtest.py` are still
  10-factor; both vote functions still only handle the original 10.
  **Do not do this without fresh, explicit approval** — the Indicators
  page in the UI shows all 13 with the 3 disconnected ones clearly badged
  and their toggle disabled, specifically so this remains visibly true.

---

## PHASE 8.1 — Smart Scanner Core Enhancement — COMPLETE

Done this phase, additive only, `analyzer.py`/`backtest.py`/the Quotex
API/WebSocket/login code and the confluence engine untouched:

- `scanner.py`: `ScannerEngine.__init__` gained an optional
  `settings_store=` param (defaults to `None` — fully backward
  compatible). Added `_read_scanner_settings()` (defensive read, never
  raises). `start()` now consults `settings.scanner.scanner_enabled`
  (blocks the start if `False`), `enabled_timeframes`, `top_signals`,
  `scan_interval`, `enabled_assets` (narrows the per-run asset list —
  stored as `self._effective_assets`), and `minimum_filter_score` (an
  extra gate applied in `get_results()`, on top of the existing
  `mandatory_pass` gate). Explicit `start()`-call args still always win
  over settings, matching the precedence already used elsewhere in this
  project (e.g. `app.py`'s filter-score overrides).
- Progress tracking added to `get_status()`: `assets_completed` (reset
  every cycle, incremented once per asset after all its timeframes are
  attempted), `percent_complete`, `elapsed_time`, `estimated_remaining`
  (same style as `backtest_engine.py`'s `status()`). `total_assets` now
  reflects the effective (possibly settings-narrowed) asset list rather
  than always the full list — byte-identical to before when no
  narrowing is configured. `current_asset` already existed, unchanged.
- Compatibility aliases added: `status()` → `get_status()`, `results()`
  → `get_results()`. Pure aliases, no new behavior; nothing internal
  calls them (the loop and existing routes still use the original
  `get_status()`/`get_results()` names).
- `settings_store.py`: added 6 new keys under the existing `"scanner"`
  section (`scanner_enabled`, `enabled_assets`, `enabled_timeframes`,
  `scan_interval`, `minimum_filter_score`, `top_signals`), all with
  defaults chosen so a first-time read behaves exactly as before Phase
  8.1 (`scanner_enabled=True`, everything else empty/`None`/`0.0`).
  Existing keys (`refresh_seconds`, `asset_gap_seconds`, `top_n`,
  `min_confidence`) untouched.
- `app.py`: `SettingsStore` instantiation moved a few lines earlier
  (before `ScannerEngine`'s instantiation, so it can be passed in);
  `_scanner = ScannerEngine(..., settings_store=settings_store)` — the
  only functional line changed in `app.py` this phase.

See `TEST_REPORT.md` and `CHANGELOG.md` for the full test/bug list.
`scanner_enabled=False` only blocks *new* `start()` calls — it does not
force-stop an already-running scan; there was no spec for that behavior
and adding it would have been a redesign, not an additive change.

## PHASE 8.2 — Smart Scanner (user-facing UI) — COMPLETE

Done this phase, additive only — no new scanner engine, no new routes,
`ScannerEngine`/`SettingsStore`/`analyzer.py`/the Quotex API/WebSocket all
untouched:

- New dedicated **Smart Scanner** page (`page-smart-scanner`), reachable
  via a new drawer-nav link and a quick-link on the Settings page.
  Deliberately named and positioned distinctly from the pre-existing
  "Auto Scanner" tab (`view-scanner`), which remains the separate,
  older client-side polling loop it always was — this new page is the
  first UI surface to actually call `ScannerEngine`'s real
  `/api/scanner/*` routes.
- Shows: state, running/stopped, current asset, percent complete, ETA,
  elapsed, assets completed/total — all sourced directly from Phase
  8.1's `get_status()` fields, no new backend fields needed.
- Start/Stop/Pause/Resume buttons call the existing
  `/api/scanner/start|stop|pause|resume` routes exactly as they were.
  Button visibility is derived purely from the polled status response
  (`running`/`paused`), same pattern as the existing Backtest page.
- Results table: Asset, Direction, Confidence, Filter Score, Passed
  Filters, Failed Filters, Timeframe, Updated — sourced directly from
  `get_results()`'s existing `top_signals[]` entries (`confluence.signal`,
  `confluence.confidence`, `filter_score`, `passed_filters`,
  `failed_filters`, `timeframe`, `last_update`) — no new backend fields
  needed here either.
- Auto-refresh: a single self-managing `pollScannerStatus()` polls every
  2s **only while `running` is true** (per the server's own state,
  checked on every poll) and clears its own interval the moment the
  server reports `running: false` — including if the scanner was
  stopped from a different tab/device, not just this page's own Stop
  button. Visiting/leaving the tab never starts or stops anything by
  itself; the very first status check on page visit only reflects
  already-true server state (e.g. scanner started earlier this
  session), mirroring how visiting the Backtest tab doesn't start a
  backtest.
- Scanner still never auto-starts: confirmed via a dedicated test that
  the scanner's state is `STOPPED` immediately after `app.py` import,
  before any request is made.

See `TEST_REPORT.md`/`CHANGELOG.md` for the full test list.

## PHASE 8.3 — Smart Scanner Advanced Controls & Settings Integration — COMPLETE

Done this phase, additive only — no new scanner engine, no second
settings store, `analyzer.py`/confluence/dynamic weights/indicators/
Quotex API/WebSocket/login/`fetch_data.py` all untouched (checksummed
before and after):

- **Bug fix in `scanner.py`** (found during the required pre-phase
  audit, not introduced this phase): `get_results()`'s ranking tie-break
  on freshness compared raw ISO-8601 strings with no negation, which
  sorts ascending (oldest-first) — the opposite of what the adjacent
  comment claimed ("last_update (freshness) desc") and the opposite of
  what this phase's spec requires. Fixed with a new `_parse_iso_epoch()`
  helper (shared with `_cleanup_stale_cache()`, which had its own
  inline copy of the same parse) and a proper negation. Verified with a
  dedicated test: two identical-scoring entries now rank with the
  fresher one first.
- **`scanner.py`**: added `current_timeframe` and `last_scan_time`
  tracking (set during the scan loop, exposed in `get_status()`) for
  the expanded status panel.
- **`settings_store.py`**: added `reset_section(section)` — resets one
  top-level settings section (used here for `"scanner"`) without
  touching any other section. The existing global `reset()` (full
  reset) is unchanged.
- **`app.py`**: added `POST /api/scanner/settings/reset`, a thin wrapper
  around the above. No other route added or changed.
- **Frontend**: the Smart Scanner page (`page-smart-scanner`) gained a
  full Settings card — Enabled Assets (all-OTC/custom chip picker, same
  UX pattern as the Backtest page's asset picker), Enabled Timeframes
  (default/custom chip picker), Minimum Filter Score (slider),
  Top Signals + Scan Interval (dropdowns, "Default" maps to `null`),
  Scanner Enabled (toggle), and Save/Reload/Reset buttons. Settings
  load automatically on first visit via `GET /api/settings`; Save uses
  the existing generic `POST /api/settings`; Reset uses the new scoped
  route. The status panel gained Current Cycle, Current Timeframe, and
  Last Scan Time. The results table gained Rank, Payout, and Age
  columns (11 total). Client-side polling now also stops when
  navigating away from the tab (previously only stopped when the
  scanner itself stopped) — the scan itself is unaffected either way,
  since it always ran server-side independent of any client polling.
- **Confirmed by explicit test**: saving Scanner Settings while the
  scanner is actively `RUNNING` does **not** stop, restart, or
  reconfigure it — `ScannerEngine` only reads settings at its own
  `start()` time (a Phase 8.1 design decision, unchanged), so a save
  mid-run simply updates the file on disk for the *next* start.
  Settings persistence across a restart was verified by instantiating
  a brand-new `SettingsStore` against the same file path (simulating a
  fresh process) and confirming the saved values were still there.

See `TEST_REPORT.md`/`CHANGELOG.md` for the full test/benchmark list.
The 3 new indicators (Wick Rejection, Liquidity Sweep, False Breakout)
remain disconnected from the Confluence vote — confirmed via grep
during the pre-phase audit, not touched this phase either.

## PHASE 8.4.1 — Indicator Validation Audit — COMPLETE

Audit-only sub-phase (no code changes). Found:
- No existing function can backtest the 3 new indicators — `backtest.py`'s
  `_factor_votes()` only vectorizes the original 10 confluence factors;
  the 3 new detectors are single-call, non-vectorized functions, so any
  validation work needs new, additive code rather than a `backtest.py`
  extension.
- Only one real historical dataset exists in this repo
  (`market_analyzer/output/candles.csv`, 200 candles, 15-minute interval,
  one unlabeled asset) — no live Quotex network access anywhere in this
  project's history.
- Running the unmodified detectors against that one dataset found **100%
  SELL, 0% BUY** across all three indicators (151 SELL / 1 BUY total, the
  single BUY appearing only in Phase 8.4.2's later resampled-1h test) —
  flagged for investigation, not explained or resolved.

## PHASE 8.4.2 — Indicator Validation Framework — COMPLETE

Built `market_analyzer/indicator_validation.py` — a new, standalone,
additive module (does not import from or modify `backtest.py`/
`analyzer.py`). Bar-by-bar replay methodology (expanding window, forward
return vs. `lookahead` bars later, same 4-bar default as `backtest.py`).
`validate_indicator()` / `validate_all()` return structured dicts
(`indicator`/`asset`/`timeframe`/`samples`/`wins`/`losses`/`win_rate`/
`accuracy`/`reliability`/`average_strength`/`average_reliability`/
`average_holding_result`/`buy_signals`/`sell_signals`/`no_signal_count`/
`sufficient_sample`) suitable for future registry integration — nothing
was written to `indicator_registry.py` this phase. `MIN_SIGNALS_REQUIRED
= 20` mirrored as an independent constant; below that, `reliability` is
`None` rather than a fabricated-looking number.

**14/14 validation tests passed.** Confirmed multi-asset/multi-timeframe
support structurally (9 combinations from one `validate_all()` call).
**Key finding, carried forward from 8.4.1 and now broader:** 151 of 152
total fired signals across every tested asset/timeframe/indicator
combination were SELL — only 2 of the 9 combinations reached the
sample-size reliability gate at all. See `TEST_REPORT.md` for full
numbers, methodology, and stated known limitations (small single-regime
sample, resampled — not independently real — 30m/1h data, unverified
performance at production scale).

Confluence (still exactly 10 factors), Dynamic Weights, `backtest.py`,
`analyzer.py`, the Quotex API, and the Scanner are all confirmed
untouched by this work — re-diffed byte-for-byte against the original
project upload immediately before and after implementation.

## PHASE 8.4.3 — ValidationEngine, Routes & Full Validation UI — COMPLETE

**Backend:** Built `webapp/validation_engine.py` (new file) — a thin
`ValidationEngine` class wrapping Phase 8.4.2's `validate_indicator()`,
mirroring `backtest_engine.py`'s lifecycle pattern (`STOPPED`/`RUNNING`/
`PAUSED` plus a new `STOPPING` transitional state) as closely as
possible. Added 6 routes: `POST /api/validation/run|pause|resume|stop`,
`GET /api/validation/status|results`. Reuses the exact same
`_backtest_fetch_candles()` closure `BacktestEngine` already uses — no
new fetch/session logic, no second Quotex connection.

**Found and fixed a real concurrency bug** during backend testing:
`pause()`/`resume()`/`stop()` mutated an `asyncio.Event` directly from
the Flask request thread, which is not thread-safe and could leave a
paused run stuck forever under the right timing conditions. Fixed by
routing the event mutation through `loop.call_soon_threadsafe()`.
Confirmed fixed via a 5-trial concurrency stress test — 100% pass rate.
Fix scoped entirely to the new file; `scanner.py`/`backtest_engine.py`
share the same underlying pattern but were not touched (off-limits) —
flagged as a latent risk worth knowing about, not acted on.

**Frontend (Validation UI, `page-validation`):** Built and approved
incrementally across 8 steps — nav entry/container, Settings panel
(asset/timeframe/indicator selectors + candle count/lookahead
dropdowns), Controls card with a new status badge, Progress card, 3
per-indicator Summary cards, 11-column Results table, session-only
read-only History, and full API wiring (`initValidationPage()`:
Run/Pause/Resume/Stop + a self-managing status poll mirroring
`pollScannerStatus()`'s exact pattern — polls only while running, stops
on tab-leave). Every existing component was reused
(`.chip-toggle`/`.asset-grid`/`.field-select`/`.small-metrics-grid`/
`.metric-card`/`.ss-results-table`/`.history-row`) — the only new CSS
this phase was a ~7-line status-badge block reusing existing color
tokens. `app.py`, `validation_engine.py`, `indicator_validation.py` all
confirmed byte-identical to the already-approved backend state
throughout — this was a frontend-only addition on top of it.

One bug was introduced and caught during frontend assembly: a
text-replacement step accidentally dropped a comment-block delimiter,
breaking JS parsing — caught immediately by `node --check`, fixed
(purely cosmetic, no logic impact).

**46/46 + 18/18 backend tests, plus a full frontend integration pass**
(DOM cross-reference, direct Node execution of the render functions
against real validation data, 11/11 Flask end-to-end) — all passing.
`indicator_validation.py`, all 12 off-limits files, and
`scanner.py`/`settings_store.py` (checked against the Phase 8.3 Recovery
baseline specifically) all reconfirmed untouched throughout. Confluence
still exactly 10 factors. See CHANGELOG.md/TEST_REPORT.md for full
detail.

**Known, honestly-flagged limitation:** BUY/SELL-split accuracy isn't
computable from the current backend output (`validate_indicator()` only
tracks overall win/loss, not per-direction) — rendered as "N/A" in the
UI rather than a fabricated number. Addressing this would require a
`validation_engine.py`/`indicator_validation.py` change, out of scope
without explicit approval.

## PHASE 8.5 — Validation History Store — COMPLETE

Built `webapp/validation_history_store.py` (new file) — a standalone
`ValidationHistoryStore` class persisting `ValidationEngine` results
across runs and restarts, the one real gap found in this phase's own
pre-audit (`ValidationEngine.results`/`.summary` are in-memory only,
wiped on every `start()`). Mirrors `settings_store.py`'s I/O pattern
exactly (atomic tempfile write + `os.replace()`, auto-create defaults,
forward-compatible backfill) without importing it — fully decoupled.
Bounded by design: O(1) `rolling_stats` (one entry per indicator,
updated in place) + a capped `run_log` (200 most recent runs, oldest
dropped). The rolling win-rate mean is gated by each run's own
sufficient-sample check, so a tiny-sample run can't skew the historical
trend — addressing a risk flagged in this phase's own audit.

**Persistence strategy (explicit decision):** app.py-polling-driven
only — `validation_engine.py` was NOT modified, no callback/hook added
inside it. `app.py` gained a `_maybe_persist_validation_history()`
helper called only from the 3 new routes below; the existing 6
`/api/validation/*` routes are byte-for-byte unchanged (confirmed via
direct diff inspection of every route's function body).

3 new routes: `GET /api/validation/history`, `GET
/api/validation/history/<indicator>`, `POST
/api/validation/history/reset`. **40/40 store tests + 15/15 API tests**,
all 4 pre-existing suites re-run and passing (40/40, 46/46, 14/14,
18/18). All 12 off-limits files, plus `scanner.py`/`settings_store.py`/
`validation_engine.py`/`indicator_validation.py`, reconfirmed
byte-identical to their respective baselines. Confluence still exactly
10 factors. See CHANGELOG.md/TEST_REPORT.md for full detail.

**Not done this phase:** no Validation UI wiring to the new history
routes — the Phase 8.4.3 UI's History section still shows session-only,
in-memory data. A future phase could wire it to `GET
/api/validation/history` for true cross-session history, but that
wasn't in this phase's explicit scope.

## PHASE 8.6 — Confluence Engine: 10 -> 13 factors — COMPLETE

Connected the 3 Phase 7.3 Part 3 indicators (Wick Rejection, Liquidity
Sweep, False Breakout) to the live confluence vote. `analyzer.py` is the
only file with a real logic change: `DEFAULT_CONFLUENCE_WEIGHTS`
rebalanced to 13 equal-ish shares (12 x 7.69 + 1 x 7.72 = 100.0 exactly,
same rounding-residual convention `settings_store.py` already uses), plus
3 new reliability-gated vote blocks in `_confluence_factor_votes()`
following the exact `candle`/`sr` pattern (threshold 40.0, `direction`/
`reliability_score` read from the existing `*_detail` dicts that
`calculate_all()` has produced since Phase 7.3 — no new detection math
was written this phase).

`indicators.py` and `webapp/indicator_registry.py` got comment-only
updates (their prior text asserted the 3 indicators were NOT connected,
which became false). No frontend file changed — `in_confluence`/`weight`
in the `/api/indicators` response were already derived live from
`analyzer.DEFAULT_CONFLUENCE_WEIGHTS`, so the Indicators page's "not yet
connected" badge disappears automatically for these 3 the moment the
backend import resolves differently.

New suite `Quotex/tests/test_phase_8_6.py`: **51/51**. All 12 off-limits
files, `scanner.py`, `settings_store.py`, `backtest_engine.py`,
`validation_engine.py`, `validation_history_store.py`, `app.py`,
`templates/index.html`, `static/app.js`, and all of `quotex/api_quotex/`
confirmed byte-identical to the Phase 8.5 Stable baseline. See
CHANGELOG.md for the full diff and known limitations.

**Explicitly NOT done this phase (see "Pending" below):**
`backtest.py`'s `_factor_votes()`/`backtest_factor_accuracy()` were not
extended to the 3 new factors — `backtest.py` was off-limits for this
phase's stated scope ("Confluence Engine" only). Live signals now use 13
factors; backtest accuracy scoring still only covers the original 10.
This is a real, currently-live divergence between the two systems, not a
bug — but the next engineer should know about it before assuming
backtest-derived dynamic weights say anything about these 3 factors.

## PENDING — carried forward from Phase 8.6 (do not begin without fresh approval)

- Wire Wick Rejection / Liquidity Sweep / False Breakout into
  `backtest.py`'s `_factor_votes()` and `backtest_factor_accuracy()` so
  backtest accuracy/dynamic-weight scoring covers all 13 confluence
  factors, matching what `generate_confluence_signal()` now votes on
  live. This requires modifying `backtest.py` itself (previously
  off-limits) — get explicit approval before touching it, per this
  project's standing rule.
- Independently back-test/calibrate the 40.0 reliability-vote threshold
  used by the 3 newly-connected factors (currently just inherited from
  the pre-existing `candle`/`sr` convention, not derived from real
  accuracy data for these specific detectors).

## PHASE 8.7 — Final Stabilization & Release Audit — COMPLETE

Not a feature phase — full audit (structure, performance, security,
production-readiness, UI, tests, docs), then *safe cleanup only* after
explicit approval, per the phase's own mandatory rules. No algorithm,
Confluence, Validation, Scanner, API, or route change; no new dependency;
no refactor of anything outside the approved list.

**Cleanup performed (5 files modified, 4 removed, 0 added):**
- Removed 4 confirmed-unused imports (`fetch_data.py`'s `API_TIMEFRAMES`,
  `run_analysis.py`'s `os`, `settings_store.py`'s `shutil`,
  `validation_history_store.py`'s `List`).
- Deleted 4 stray runtime artifacts (`market_analyzer/output/candles.csv`,
  `market_analyzer/webapp/log-2026-07-{15,16,17}.txt`).
- Removed one redundant, provably no-op block in `app.js`'s
  `navigateTo()` — a second `.seg-tab` active-class pass that only ran
  for `name === 'scanner'`/`'analyzer'` and recomputed exactly what the
  preceding pass already set for those two names.

**51/51 regression suite still passing post-cleanup.** Full diff against
the Phase 8.6 Stable baseline confirms exactly those 5 modified + 4
removed files and nothing else — no algorithm, route, or API touched.

**Real gap found and explicitly NOT fixed this phase (see below):**
`tests/test_phase_8_6.py` is the only persisted, re-runnable test file in
the entire repository. Every earlier phase's suite (8.1, ValidationEngine,
8.4.2, 8.4.3, 8.5) was sandbox-only and never committed — those numbers
in `TEST_REPORT.md` are accurate history, not something you can re-run
today. `scanner.py`, `backtest.py`/`backtest_engine.py`,
`settings_store.py`, `validation_engine.py`,
`validation_history_store.py`, `indicator_validation.py`, every Flask
route, and all frontend JS have zero automated behavioral coverage right
now.

**Also flagged, not fixed (cosmetic, not a defect):** 2 of the 10 UI
pages (`view-scanner`/`view-analyzer`) use a different id-prefix
convention than the other 8 (`page-*`). `navigateTo()` already handles
both correctly — this is naming-only.

## PENDING — carried forward from Phase 8.7 (do not begin without fresh approval)

- **Build a real, persisted, re-runnable regression suite** covering
  `scanner.py`, `backtest.py`/`backtest_engine.py`, `settings_store.py`,
  `validation_engine.py`, `validation_history_store.py`,
  `indicator_validation.py`, the Flask routes in `app.py`, and ideally
  some frontend coverage — the single biggest gap found across Phases
  8.1–8.7. This is a substantial, separately-scoped effort, not a "safe
  cleanup" item.
- (Carried from Phase 8.6, still pending) Wire the 3 new indicators into
  `backtest.py`'s factor-accuracy scoring.
- (Optional, cosmetic) Normalize `view-scanner`/`view-analyzer` to the
  `page-*` naming convention used by the other 8 pages — purely
  cosmetic, touches HTML ids + `navigateTo()` + any other references, so
  treat as its own small phase rather than "safe cleanup."

## PHASE 9 — Smart Learning & Adaptive Weight System — COMPLETE

Pre-implementation audit found a severe, pre-existing bug (not introduced
by Phase 9, but a necessary prerequisite fix before Phase 9 could mean
anything): the live pipeline silently gave Wick Rejection/Liquidity Sweep/
False Breakout a weight of exactly 0 on every real signal since Phase 8.6,
because `backtest.py`'s `_DEFAULT_8F_WEIGHTS` (which `compute_dynamic_weights()`
builds its entire output from) was never extended past the original 10
factors. Verified end-to-end with real functions before and after the fix.
Stopped and reported this before touching any code, per the standing
escalation rule for blockers touching previously-approved architecture;
proceeded only after explicit approval.

**Prerequisite fixes (both verified, both backward-compatible):**
- `backtest.py`: `_DEFAULT_8F_WEIGHTS` extended to 13 keys, realigned to
  `analyzer.DEFAULT_CONFLUENCE_WEIGHTS`'s values exactly.
- `settings_store.py`: `INDICATOR_KEYS` extended to 13 keys (found while
  wiring the Apply route — same class of gap: `apply_suggested_weights()`
  would have silently no-op'd for the 3 new indicators otherwise).

**New, additive Learning module (`learning_engine.py`):**
`compute_recommendation()` — reads Validation History, computes a
trend (`improving`/`degrading`/`stable`/`no_data`) and confidence
(`none`/`low`/`medium`/`high`) per indicator, recommends a new weight
clamped to `[min_weight, max_weight]` (defaults 2.0/20.0), renormalized to
sum to 100. `LearningHistoryStore` — bounded, atomic-write log of past
recommendations. Structurally isolated: no import of `analyzer.py`/
`backtest.py`/`validation_engine.py`/`indicator_validation.py`/
`scanner.py`/`indicator_registry.py`, no write path into
`validation_history.json`.

**5 new routes** (`/api/learning/status`, `/generate`, `/history`,
`/apply`, `/reset`) — Apply reuses the existing
`settings_store.apply_suggested_weights()`, no new settings-write path.

**New Learning UI page** — same component set as Validation/Backtest, no
new CSS. Current vs. recommended weights table, trend/confidence/sample
count per indicator, Recommendation History, Generate/Apply/Reset buttons,
15s status polling while the tab is open.

**34/34 new regression tests** (`tests/test_phase_9_pipeline_fix.py`),
51/51 existing tests still passing. 6 files modified, 2 files added,
nothing else touched.

## PENDING — carried forward from Phase 9 (do not begin without fresh approval)

- **Extend `backtest_factor_accuracy()`/`_factor_votes()` to score the 3
  Phase 8.6 indicators too** (still the same item carried since Phase 8.6,
  now doubly relevant: Learning can only ever produce a real, non-`"no_data"`
  recommendation for indicators Validation History tracks, which today
  means it can only meaningfully advise on these same 3 — extending
  backtest accuracy scoring wouldn't feed Learning directly, but it's the
  same underlying "10 vs 13" gap and worth doing together).
- **Build a real, persisted, re-runnable regression suite** for the rest of
  the app (still open from Phase 8.7 — `scanner.py`, `backtest_engine.py`,
  `validation_engine.py`, `validation_history_store.py`,
  `indicator_validation.py`, the Flask routes generally, frontend). Phase 9
  added one more persisted test file but did not close this broader gap.
- **Independently calibrate** Learning's `min_weight`/`max_weight`/
  `learning_rate`/`min_samples` defaults, and the shared 40.0
  reliability-vote threshold, against real outcome data rather than
  inherited conventions.
- (Optional, cosmetic, carried from Phase 8.7) Normalize `view-scanner`/
  `view-analyzer` to the `page-*` naming convention.

## PHASE 10.1 — Universal Validation (all 13 confluence factors) — COMPLETE

Extended the Validation framework from measuring only the 3 OTC-specific
detector-based indicators to measuring all 13 confluence factors, plus
Asset-wise/Timeframe-wise Validation Summary aggregation. Full detail in
CHANGELOG.md/TEST_REPORT.md; summary here:

- `indicator_validation.py`: additive `UNIVERSAL_INDICATOR_NAMES` (13),
  `validate_indicator_universal()`/`validate_all_universal()` (delegate
  byte-identically to the unmodified `validate_indicator()`/`validate_all()`
  for the original 3; reuse `backtest.py`'s existing, unmodified
  `_factor_votes()` — read-only import — for the other 10),
  `summarize_by_asset()`/`summarize_by_timeframe()`.
- `validation_engine.py`: widened to accept/default-to all 13.
- `app.py`: `/api/validation/run` + `/api/validation/history/<indicator>`
  widened to 13; added `GET /api/validation/summary/by-asset` +
  `GET /api/validation/summary/by-timeframe`.
- `validation_history_store.py`: `KNOWN_INDICATORS` 3→13, schema
  `1.0`→`1.1`, backward-compatible migration verified against a real
  synthetic old-format file (found + fixed a real bug where
  `schema_version` wasn't advancing during that verification).
- `analyzer.py`/`backtest.py`/`indicators.py`/`scanner.py`/
  `settings_store.py`/`indicator_registry.py`/`backtest_engine.py`/
  `quotex/api_quotex/` all reconfirmed byte-identical (diffed against the
  Phase 9 Stable ZIP).
- New `tests/test_phase_10_1.py`, 142/142. Full suite: 227/227.

**What this phase deliberately did NOT do** (still pending, see below):
did not wire the 3 OTC indicators into `backtest_factor_accuracy()`/
`compute_dynamic_weights()` itself (that's the separate item carried since
Phase 8.6/9); did not change the Validation UI's indicator-selector chip
grid in `templates/index.html`/`static/app.js` (`v-set-indicator-grid`
still only renders 3 chips — Wick Rejection/Liquidity Sweep/False
Breakout — so a user driving the UI, as opposed to calling the API
directly, still can't select any of the other 10 factors without a
frontend change); did not add any UI surface for the two new summary
routes (`by-asset`/`by-timeframe`) — they're API-only this phase.

## PENDING — carried forward from Phase 10.1 (do not begin without fresh approval)

- **Validation UI indicator-selector chip grid** — extend
  `v-set-indicator-grid` (and its `_vSelectedIndicators` JS state) from 3
  chips to all 13, so a user can actually drive Universal Validation from
  the UI, not just via a direct API call with an explicit `indicators`
  list. Not started.
- **Surface the two new summary routes in the UI** — `GET
  /api/validation/summary/by-asset`/`by-timeframe` currently have no
  frontend consumer at all. Not started.
- **Extend `backtest_factor_accuracy()`/`_factor_votes()` (in
  `backtest.py` itself) to score the 3 Phase 8.6 indicators** — still the
  same item carried since Phase 8.6/Phase 9, NOT resolved by this phase.
  Phase 10.1's `_validate_vectorized_factors()` in `indicator_validation.py`
  reuses `backtest._factor_votes()` for measurement purposes only (a
  read-only import into a different module); `compute_dynamic_weights()`'s
  own accuracy scoring is untouched, and dynamic-weight suggestions on the
  Settings/Backtest page still do not include real accuracy data for
  those 3 factors.

## PHASE 10.2 — Asset Intelligence + Timeframe Intelligence — COMPLETE

Learns which indicator performs best on each OTC asset and each
timeframe from accumulated Validation History, plus system-wide top/weak
indicator rankings and advisory recommendations. Full detail in
CHANGELOG.md/TEST_REPORT.md; summary here:

- `validation_history_store.py`: schema `1.1`→`1.2`, two new top-level
  keys `asset_stats`/`timeframe_stats` (start empty — no fixed
  asset/timeframe enum exists anywhere in this codebase, both are
  freeform caller-supplied strings), new `record_asset_timeframe_stats()`
  persists the RAW per-(asset,timeframe) `ValidationEngine.results`
  (previously computed then discarded before this phase), fully
  independent of the unmodified `record_run()`. Migration verified
  against a real synthetic 1.1-format file.
- New standalone `asset_timeframe_learning.py` (same decoupling
  convention as `learning_engine.py`): `compute_asset_rankings()`/
  `compute_timeframe_rankings()`, `compute_top_indicators()`,
  `compute_recommendations()`. **Bug found and fixed during testing**: a
  ranking-quality issue where raw-accuracy-only ordering let a
  tiny-sample group outrank a large one — fixed by gating ranking
  inclusion on the same `min_samples` threshold used everywhere else.
- `app.py`: 4 new read-only routes — `GET /api/learning/assets`, `GET
  /api/learning/timeframes`, `GET /api/learning/top-indicators`, `GET
  /api/learning/recommendations`.
- New Learning-page UI sections (Best Assets, Best Timeframes, Asset/
  Timeframe Rankings, Top/Weak Indicators, Indicator Trends,
  Recommendation Cards) — zero new CSS, reuses existing components.
- `analyzer.py`/`backtest.py`/`indicators.py`/`scanner.py`/
  `settings_store.py`/`indicator_registry.py`/`backtest_engine.py`/
  `indicator_validation.py`/`validation_engine.py`/`learning_engine.py`/
  `quotex/api_quotex/` all reconfirmed byte-identical.
- New `tests/test_phase_10_2.py`, 74/74. Approved test-maintenance fix:
  4 stale hardcoded-schema-version assertions in `tests/test_phase_10_1.py`
  updated to reference the version constant instead of a literal — no
  other assertion touched, no production code touched for that fix. Full
  suite: 301/301 (51+34+142+74).

**What this phase deliberately did NOT do** (see the pending section
below): did not wire the 3 OTC indicators into `backtest_factor_accuracy()`
(unaffected, still the Phase 8.6/9 item); did not add a persisted
history-of-recommendations log for Asset/Timeframe Intelligence (unlike
Phase 9's `LearningHistoryStore`); did not add `min_samples`/`top_n` UI
controls (routes accept them as query params, frontend always uses
defaults); did not build a "rank assets for indicator X specifically"
view — only pooled-across-indicators rankings plus each group's single
best/weakest indicator.

## PENDING — carried forward from Phase 10.2 (do not begin without fresh approval)

- **Persisted recommendation history for Asset/Timeframe Intelligence** —
  every `/api/learning/{assets,timeframes,recommendations}` call
  recomputes fresh; there's no way to see how a ranking changed over
  time, unlike Phase 9's `LearningHistoryStore`/`recommendation_log`. Not
  started, deliberately deferred (see `asset_timeframe_learning.py`'s own
  docstring).
- **`min_samples`/`top_n` UI controls** — the 4 new routes accept these
  as query params; the frontend always calls with no query string (route
  defaults only). Not started.
- **Per-indicator asset/timeframe views** — e.g. "rank every asset
  specifically by how `bb` performs on it," as opposed to the current
  pooled-across-all-indicators ranking. Not started.
- **Full Flask-app-level testing for the 4 new routes** — same standing
  sandbox constraint as Phase 10.1's summary routes (missing third-party
  deps, not installable here). Route wiring verified by code review +
  `py_compile` only; underlying functions fully covered by
  `tests/test_phase_10_2.py`.
- **`backtest_factor_accuracy()`/`_factor_votes()` (in `backtest.py`
  itself) still don't score the 3 OTC indicators** — same item carried
  since Phase 8.6/9/10.1, unaffected by this phase either.

## PHASE 10.3 Part-1 — Market Regime Detection + Adaptive Weight Engine + Dynamic Indicator Selection — COMPLETE

Classifies the current market into 1 of 8 deterministic regimes (or
`Unknown` when data is insufficient) purely from fields
`indicators.calculate_all()` already produces, then rescales the 13
confluence-factor weights in two layered steps before they reach
`generate_confluence_signal()`. Pure rule-based logic — no ML. Full detail
in CHANGELOG.md/TEST_REPORT.md; summary here:

- New standalone `regime_detector.py` — `detect_market_regime(ind)`. 8
  named regimes (Strong Uptrend, Strong Downtrend, Sideways Range, High
  Volatility, Low Volatility, Breakout, Reversal, Uncertain / Mixed) or
  `Unknown` on missing/NaN required fields. Fixed evaluation order,
  every branch returns explainable `reasons` + `metrics_used` +
  a geometry-derived `confidence`. Zero pandas/numpy/analyzer/backtest
  import dependency — unit-testable with a hand-built dict.
- New standalone `regime_weight_engine.py` —
  `apply_regime_adaptive_weights(weights, regime_result)`. Fixed,
  hand-authored per-regime multiplier table rescaling whatever weights
  the caller already has, renormalized to 100 (same residual-to-largest-
  weight convention as Phase 7.4's `_apply_settings_weight_overrides()`).
  Uncertain/Unknown regimes are a deliberate no-op.
- New standalone `dynamic_indicator_selector.py` —
  `apply_dynamic_indicator_selection(weights, regime_result)`. A second,
  categorical layer: per-regime primary (x1.15) / low-relevance (x0.5,
  never zeroed) factor tables — orthogonal to the continuous multiplier
  table above. Same Uncertain/Unknown no-op.
- New standalone `regime_pipeline.py` — `compute_regime_adjusted_weights
  (base_weights, ind)`, composing the three modules above into one call.
- `config.py`: new `ENABLE_REGIME_ADAPTIVE_WEIGHTS` flag (default `True`).
- `run_analysis.py`/`webapp/app.py`: one import + a config-flag-gated call
  each, inserted right after `dynamic_weights` is computed. In `app.py`
  specifically, placed *before* the existing `_apply_settings_weight_
  overrides()` call — Settings still applies last and keeps final say.
  `webapp/app.py`'s JSON response gained one additive `"regime"` key.
- `analyzer.py`/`backtest.py`/`indicators.py`/`scanner.py`/
  `learning_engine.py`/`indicator_registry.py`/`quotex/api_quotex/` all
  reconfirmed byte-identical — `analyzer.py` was not touched at all.
- New `tests/test_phase_10_3_part1.py`, 149/149. Full suite: 450/450
  (51+34+142+74+149).

**What this phase deliberately did NOT do** (see the pending section
below): no UI surface for the new `"regime"` field; no persisted
`RegimeHistoryStore`; the per-regime multiplier/selection tables are
hand-authored constants, not backtest-calibrated; regime detection is
single-timeframe only; no Flask-app-level test-client coverage for the
new API field (same standing sandbox limitation as Phase 10.1/10.2).

## PENDING — carried forward from Phase 10.3 Part-1 (do not begin without fresh approval)

- **UI surface for the raw `"regime"` field** — Phase 10.3 Part-2's AI
  Health Dashboard now shows Current Market Regime + a Regime Health
  badge, but there is still no historical regime timeline/chart.
- **`RegimeHistoryStore`** — every call recomputes the regime fresh from
  the latest bar; no persisted log of how the regime has changed over
  time. Not started, deliberately deferred.
- **Backtest-calibrate `REGIME_FACTOR_MULTIPLIERS`/
  `DYNAMIC_SELECTION_TABLE`** against this project's own historical
  accuracy data, instead of the current hand-authored constants. Not
  started.
- **Multi-timeframe regime confirmation** — currently single-timeframe
  only (whatever granularity the `ind` dict passed in has). Not started.
- **Full Flask-app-level testing for the `"regime"` field** — same
  standing sandbox constraint as Phase 10.1/10.2's routes (`loguru`/
  `websockets` not installable here). Wiring verified by code review +
  `py_compile` + source-inspection assertions in
  `tests/test_phase_10_3_part1.py`.

## PHASE 10.3 Part-2 — AI Health Dashboard + Explainable Signal System — COMPLETE

Two new additive modules — `explainable_signal.py` (turns an already-
computed signal into 9 named ✔/✖ checks + Hard Gates Passed/Failed +
Final Filter Score + Confidence + Reasons + Warnings) and
`ai_health_engine.py` (scores 5 components — Indicator/Scanner/
Validation/Learning/Regime — plus an Overall AI Health, each one of
`Excellent/Good/Fair/Poor/Critical`) — exposed via 4 new read-only
`/api/ai/*` routes and a new dashboard page. Full detail in
CHANGELOG.md/TEST_REPORT.md; summary here:

- `explain_signal(result)` reads only fields `_run_pipeline()` already
  produced (`filter_breakdown`, `factors`, `regime`) — nothing
  recomputed. WAIT signals get an explicit "no direction to confirm"
  explanation rather than a guess.
- `compute_ai_health(...)` reads only already-computed data
  (`validation_history_store.get_history()`, `learning_engine.
  compute_recommendation()`, `ScannerEngine.get_status()`/
  `get_results()` — public API only). "No data yet" is deliberately
  `Fair`, never `Critical`.
- **One identified constraint, resolved without touching `scanner.py`**:
  an accurate "Recent WAIT %" needs `ScannerEngine`'s full unfiltered
  signal history, which is a private attribute with no public accessor.
  Since `scanner.py` is off-limits, `recent_wait_pct` is honestly `None`
  (not guessed), and BUY%/SELL% are computed from the gated `top_
  signals` subset only, labeled as such everywhere.
- 4 new routes: `/api/ai/health`, `/api/ai/status`, `/api/ai/statistics`,
  `/api/ai/explain` (reuses `_run_pipeline()` exactly like `/api/signal`,
  or falls back to the scanner's top-ranked cached signal).
- New `page-ai-health` dashboard: Overall Health badge, 5 component
  Health Cards, a Statistics grid, Validation/Learning status text, Best/
  Worst Indicators, Best Assets/Timeframes (reusing Phase 10.2's
  `/api/learning/*` routes directly, not duplicated), and a hand-rolled
  Explain Signal modal popup. Zero new CSS framework — 5 new
  `.badge-health-*` variants + one modal block, reusing existing design
  tokens only.
- `analyzer.py`/`backtest.py`/`indicators.py`/`scanner.py`/
  `learning_engine.py`/`indicator_registry.py`/`quotex/api_quotex/` all
  reconfirmed byte-identical.
- New `tests/test_phase_10_3_part2.py`, 97/97. Full suite: 547/547
  (51+34+142+74+149+97).

**What this phase deliberately did NOT do**: no historical AI-Health
time-series charting; no change to `scanner.py` to expose its full
signal cache (would unlock an accurate WAIT%, but requires approval
first); no backtest-calibration of the health-scoring formulas; no
Flask-app-level test-client coverage (same standing sandbox limitation).

## PENDING — carried forward from Phase 10.3 Part-2 (do not begin without fresh approval)

- **Expose a public, read-only accessor on `ScannerEngine` for its full
  unfiltered signal history** — the only way to get an accurate `recent_
  wait_pct` / true BUY%/SELL%. Requires touching `scanner.py`, which is
  off-limits without explicit approval. Not started.
- **Historical/time-series AI Health charting** — every `/api/ai/*` call
  is a fresh point-in-time snapshot; nothing is persisted. Not started.
- **Backtest-calibrate the AI Health scoring formulas** (component
  weights, `_status_label()` thresholds) against real historical
  outcomes, instead of the current hand-authored constants. Not started.
- **Full Flask-app-level testing** for the 4 new `/api/ai/*` routes and
  the new dashboard page — same standing sandbox constraint as every
  prior phase (`loguru`/`websockets` not installable here). Wiring
  verified by code review + `py_compile` + `node --check` +
  Jinja2-standalone template rendering + source-inspection assertions in
  `tests/test_phase_10_3_part2.py`.
- **Phase 10.4** — not scoped, not started. Do not assume any scope for
  it without fresh, explicit approval (this project's standing pattern
  is audit → propose → approve → implement → test → report, every
  phase, no exceptions).

## PHASE 8.4.4+ — still not started

Per the original Phase 8.4 roadmap: calculating Dynamic Weight/
Reliability Score/Strength Score from validation results (still NOT
connecting anything to Confluence), then exposing those in
`indicator_registry.py`. **Given the SELL-bias and small-sample-size
findings from Phase 8.4.1/8.4.2 — only 2 of 9 originally-tested
combinations were statistically reliable, and 151/152 signals were
SELL — any such calculation should be read as provisional and heavily
caveated,** not as a step that quietly resolves the bias question.
**Do not begin without fresh approval.** With Phase 8.5's history store
now in place, this would be a natural consumer of the rolling stats it
persists — but that connection itself still needs explicit approval
before any code is written.

## PHASE 9 — Modern Dashboard (mentioned once, not scoped)
Referenced in Phase 7.2 ("so Phase 8 and Phase 9 can directly reuse these
APIs") but never detailed. Do not assume scope — ask.

## PHASE 10 — Not scoped beyond 10.3 Part-2
Mentioned only as a placeholder in Phase 7.3's framing ("Phase 8, Phase 9,
Phase 10"). Phase 10.1 (Universal Validation), Phase 10.2 (Asset
Intelligence + Timeframe Intelligence), Phase 10.3 Part-1 (Market
Regime Detection + Adaptive Weight Engine + Dynamic Indicator Selection),
and Phase 10.3 Part-2 (AI Health Dashboard + Explainable Signal System)
are now COMPLETE — see the dedicated sections above. Phase 10.4 has no
content to summarize; do not assume any scope for it without fresh
approval.

---

## General rules for whoever continues this project
1. Read `PROJECT_MEMORY.md` before making any design decision — it
   explains *why*, not just *what*. Read `HANDOFF.md` for a fast
   orientation before diving into `PROJECT_MEMORY.md`'s full detail.
2. Every phase in this project followed a strict pattern: **audit first
   → propose architecture → get approval → implement → test → report**.
   Continue that pattern.
3. Never modify: Quotex API, WebSocket, login/session handling, the
   confluence engine's existing 10 factors, `calculate_filter_score()`'s
   existing 7-criteria formula, the Dynamic Weight algorithm, without a
   fresh, explicit audit-and-approval cycle — even though some future
   phase's tasks may touch adjacent files (Settings/Backtest/UI layers
   are designed specifically to sit *on top of* these without altering
   them — follow that same pattern for anything new).
4. Always run compile checks + regression tests (fuzz-testing existing
   behavior for byte-identical output) before considering any change
   complete — this was done for every single change across the whole
   project, including this phase, and caught several real bugs (see
   `TEST_REPORT.md` and `CHANGELOG.md`'s "Fixed" entries).
5. This project's development sandbox has **no live network access** —
   nothing has ever been tested against real Quotex data. Phase 7.4 went
   further than prior phases by exercising the full `app.py` Flask route
   surface end-to-end via a test client (stubbing only the missing
   third-party network/browser libraries, using the real `ASSETS`/
   `TIMEFRAMES` constants) — but actual Quotex connectivity
   (`connect()`, `get_candles_df()`) remains untested. Say so explicitly
   in any future report; do not imply otherwise.
