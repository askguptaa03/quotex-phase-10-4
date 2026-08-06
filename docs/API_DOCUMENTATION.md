# API DOCUMENTATION

Only these routes actually exist in `webapp/app.py`. Anything else
described in earlier planning documents (Settings routes, Backtest routes,
Quotex session routes) is **NOT YET IMPLEMENTED** — do not assume they work.

## `GET /`
Renders the single-page dashboard (`templates/index.html`).

## `POST /api/signal`
The core manual analysis endpoint — calls `_run_pipeline(asset, timeframe)`.
**Parameters (JSON body):** `asset` (str), `timeframe` (str, one of the
configured `TIMEFRAMES`).
**Response (abridged, additive fields added across every phase):**
```json
{
  "asset": "EURUSD_otc", "timeframe": "5m",
  "trend": "BULLISH",
  "confluence": {"signal": "BUY", "confidence": 82.5},
  "legacy": {"signal": "BUY", "confidence": 78.0},
  "agree": true,
  "indicators": { "...": "full calculate_all() output, incl. *_detail keys" },
  "payout_pct": 92.0,
  "multi_tf": {"status": "CONFIRMED", "...": "..."},
  "multi_tf_status": {"status": "CONFIRMED", "reason": "...", "timeframe_checked": "1m"},
  "filter_score": 87.5,
  "mandatory_pass": true,
  "passed_filters": ["ema_trend","adx","atr","support_resistance","multi_timeframe","payout","candlestick"],
  "failed_filters": [],
  "filter_breakdown": { "ema_trend": {"max": 20.0, "points": 20.0, "passed": true, "value": "BULLISH"}, "...": "..." }
}
```
**Errors:** connection failures return an `"error"` key; the scanner treats
this as a failed gate (`quotex_connection`).

## `GET /healthz`
Basic health check (pre-existing, unmodified this project).

## `GET /api/live-prices`
Pre-existing, unmodified this project.

## `GET /api/scanner/status`
Returns `ScannerEngine.get_status()`: state, metrics, history (last 10
cycles), recent events (last 25 of 100 kept), cached-result count, etc.

## `GET /api/scanner/results`
**Query params:** `min_confidence` (float), `timeframe` (str), `limit` (int).
Returns ranked `top_signals` — only entries where `mandatory_pass` is true
and `confluence.signal` is BUY/SELL (not WAIT), sorted by
`(filter_score desc, confidence desc, payout desc, freshness desc)`.

## `POST /api/scanner/start`
**Body:** `{"timeframes": ["5m"], "top_n": 10, "min_confidence": 70, "refresh_seconds": 120}`.
Returns `{"ok": true/false, "message": "..."}`. `409` if already running.

## `POST /api/scanner/stop`
No body. Returns `{"ok": true/false, "message": "..."}`.

## `POST /api/scanner/pause`
No body.

## `POST /api/scanner/resume`
No body.

---

## NOT YET IMPLEMENTED (documented here so a continuing AI doesn't assume they exist)

These were designed (functions exist and are tested) but have **zero Flask
route wiring**:

| Planned route | Backing function (exists, tested) |
|---|---|
| `GET/POST /api/settings` | `settings_store.SettingsStore.get()`/`.update()` |
| `POST /api/settings/reset` | `.reset()` |
| `GET /api/settings/backups` | `.list_backups()` |
| `POST /api/settings/backups/restore` | `.restore_backup(index)` |
| `GET /api/settings/export` | `.export_settings()` |
| `POST /api/settings/import` | `.import_settings(data)` |
| `POST /api/backtest/run` | `backtest_engine.BacktestEngine.start(...)` |
| `POST /api/backtest/pause` | `.pause()` |
| `POST /api/backtest/resume` | `.resume()` |
| `POST /api/backtest/stop` | `.stop()` |
| `GET /api/backtest/status` | `.status()` |
| `GET /api/backtest/results` | `.get_results()` |
| `POST /api/backtest/apply-weights` | `evaluate_apply_conditions()` + `settings_store.apply_suggested_weights()` |
| Quotex session routes | design only, no backing function beyond existing `connect()` |

See `NEXT_PHASE.md` for the exact task breakdown to build these.
