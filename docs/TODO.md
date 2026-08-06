# TODO

## Completed
- [x] Quotex API/session audit (Phase 1)
- [x] `.env.example`, `preflight_check.py`, security `.gitignore` (Phase 2)
- [x] Indicator/analyzer/backtest audit (Phase 3)
- [x] Confidence dampener (Step 1)
- [x] MTF transparency (Step 2)
- [x] `MIN_SIGNALS_REQUIRED` unification (Step 3)
- [x] OBV confluence factor (Step 4) + regression audit + backup ZIP (Step 4.1/4.2)
- [x] Candlestick engine upgrade — 9 patterns (Phase 5)
- [x] Support/Resistance zone engine + 10th confluence factor (Phase 6)
- [x] Smart Scanner backend engine (Phase 7)
- [x] Filter Score v1 (binary) (Phase 7)
- [x] Filter Score v2 (graded) + `mandatory_pass` (Phase 7.1)
- [x] `settings_store.py` (full, tested) (Phase 7.2)
- [x] `backtest_engine.py` (full, tested, standalone) (Phase 7.2)
- [x] `indicator_registry.py` (Phase 7.3 Part 2)
- [x] Wick Rejection, Liquidity Sweep, False Breakout indicator functions (Phase 7.3 Part 3, additive)
- [x] This documentation handoff package (Phase 7.3 continuation)
- [x] Settings Flask routes (`GET/POST /api/settings`, reset/backup/restore/export/import) (Phase 7.4)
- [x] Wire `_run_pipeline()` to read effective weights/config from Settings (Phase 7.4)
- [x] Backtest Flask routes (run/pause/resume/stop/status/results/apply-weights) (Phase 7.4)
- [x] Quotex session management routes (SSID update -> `session.json`, validate -> existing `connect()`) (Phase 7.4)
- [x] Connect Wick Rejection / Liquidity Sweep / False Breakout to the confluence engine (Phase 8.6 — 10 -> 13 factors)

## Pending (backend/API)
- [ ] Reconcile duplicate config surfaces (`ScannerConfig` vs `settings.json`'s `scanner.*` keys; `backtest_engine.CANDLE_OPTIONS` vs `settings.json`'s `backtest.candle_options`)
- [ ] Wire the 3 Phase 7.3 indicators into `backtest_factor_accuracy()`'s factor set so backtest accuracy scoring covers all 13 confluence factors (deliberately deferred from Phase 8.6 — `backtest.py` was off-limits for that phase)
- [ ] Independently back-test/calibrate the 40.0 reliability-vote threshold used by the 3 newly-connected factors (currently just carried over from the `candle`/`sr` convention)

## Pending (frontend)
**Verified fact:** a 5-tab structure already exists (scanner/analyzer/
signals/history/settings) — pre-existing, byte-unchanged this project. The
existing Settings tab is static/read-only only, not connected to any new
backend.
- [ ] Make the existing Settings tab dynamic/editable, wired to new Settings routes
- [ ] Add a new Backtest tab (`VIEWS` entry + `page-backtest` section) — does not exist yet
- [ ] Quotex session UI (SSID paste box, validate button, masked display) — could extend the existing Settings tab's SSID-renewal card
- [ ] Advanced panel: Export/Import/Reset/Backup/Restore Settings, Clear Scanner/Backtest Cache buttons

## Pending (testing — needs a real environment, not this sandbox)
- [ ] Live Quotex connectivity test (never done — no network access in dev sandbox)
- [ ] Real Flask HTTP-layer test (Flask test client or curl against a running server — never done)
- [ ] Browser-based UI test (no display available in this sandbox)
- [ ] Scanner full-cycle timing against real Quotex latency (only estimated, never measured)

## Future (not yet scoped by the user — do not assume any of this)
- [ ] Phase 8 — Smart Scanner (user-facing) — explicitly not started
- [ ] Phase 9 — "Modern Dashboard" — mentioned once, never detailed
- [ ] Phase 10 — unscoped
- [ ] Any AI/ML-driven weight suggestion beyond the existing backtest-accuracy-based `compute_dynamic_weights()`
