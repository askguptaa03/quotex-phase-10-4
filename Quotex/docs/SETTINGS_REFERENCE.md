# SETTINGS REFERENCE

All settings live in `settings_store.py`'s `_default_settings()`. Storage:
a JSON file (default path chosen by whoever instantiates `SettingsStore` —
no fixed path exists yet since no route wires it up). **No UI or route
currently reads/writes these except through direct Python calls in tests.**

| Setting | Default | Allowed values | Where stored | Where used |
|---|---|---|---|---|
| `general.default_timeframe` | `"5m"` | any configured timeframe string | settings.json | Not yet consumed by any route |
| `general.default_asset` | `"EURUSD_otc"` | any OTC asset key | settings.json | Not yet consumed |
| `general.refresh_interval_seconds` | `30` | int | settings.json | Not yet consumed |
| `general.scanner_speed` | `"normal"` | `"slow"/"normal"/"fast"` | settings.json | Not yet consumed (scanner reads its own `ScannerConfig`, not settings.json) |
| `general.auto_refresh` | `true` | bool | settings.json | Not yet consumed |
| `quotex.last_validated_at` | `null` | ISO timestamp | settings.json | Not yet consumed |
| `quotex.last_validation_status` | `"unknown"` | `"unknown"/"valid"/"invalid"/"error"` | settings.json | Not yet consumed |
| `indicators.<id>.enabled` | `true` | bool | settings.json | `get_effective_dynamic_weights()` (tested; not yet wired into `_run_pipeline()`) |
| `indicators.<id>.weight` | `10.0` | float | settings.json | same as above |
| `indicators.<id>.threshold` | `{}` | dict | settings.json | Not yet consumed |
| `filters.adx_threshold` | `25.0` | float | settings.json | `get_filter_score_config_overrides()` -> `calculate_filter_score(config=...)` (tested; not yet wired) |
| `filters.atr_threshold` | `1.5` | float | settings.json | same |
| `filters.min_payout` | `80.0` | float | settings.json | same |
| `filters.ema_lengths` | `[9, 21, 50]` | list[int] | settings.json | Not yet consumed (EMA periods are still hardcoded in `_run_pipeline()`'s call to `calculate_all()`) |
| `filters.min_confidence` | `70.0` | float | settings.json | Not yet consumed by scanner (scanner has its own `ScannerConfig.min_confidence`) |
| `filters.min_filter_score` | `60.0` | float | settings.json | Not yet consumed anywhere |
| `scanner.refresh_seconds` | `120` | int | settings.json | Not yet consumed (duplicate of `ScannerConfig`, needs reconciling in a future task) |
| `scanner.asset_gap_seconds` | `0.7` | float | settings.json | same |
| `scanner.top_n` | `10` | int | settings.json | same |
| `scanner.min_confidence` | `70.0` | float | settings.json | same |
| `backtest.min_candles` | `2000` | one of `500/1000/2000/5000` | settings.json | Not yet consumed by any route (`backtest_engine.CANDLE_OPTIONS` enforces the same set independently) |
| `backtest.candle_options` | `[500,1000,2000,5000]` | list[int] | settings.json | reference/UI dropdown source only |
| `backtest.min_indicator_sample_size` | `100` | int | settings.json | Intended for `evaluate_apply_conditions()`'s `min_indicator_sample_size` param — not yet wired |
| `backtest.auto_weight_update` | `false` | bool | settings.json | **Must always be respected as a UI-opt-in only** — per Phase 7.2's Step 6, weights must NEVER apply automatically regardless of this flag's value; this flag should only ever enable a button, never trigger an automatic write |
| `backtest.normalize_weights` | `true` | bool | settings.json | `get_effective_dynamic_weights()` (tested) |
| `ui_preferences.theme` | `"dark"` | string | settings.json | Not yet consumed (no UI exists) |
| `ui_preferences.active_tab` | `"dashboard"` | string | settings.json | Not yet consumed |

## Backup/Restore
- `create_backup(reason)` — snapshots the full settings dict, keeps last 10 (`max_backups` constructor param).
- `restore_backup(index)` — restores a snapshot by index (0-based, from `list_backups()`).
- `apply_suggested_weights(suggested_weights, reason)` — **always** calls `create_backup()` first, automatically, before writing — this cannot be bypassed by a caller.

## Export/Import
- `export_settings()` — returns the full current dict.
- `import_settings(data)` — deep-merges onto defaults (so a partial/older export never leaves required keys missing), then persists.

## IMPORTANT — not yet decided
There is currently **no fixed settings.json file path** wired into `app.py`
— `SettingsStore` takes a `path` constructor argument and nothing in the
Flask app instantiates it yet. Whoever adds the routes (see NEXT_PHASE.md)
needs to choose a path (e.g. `Quotex/quotex/settings.json`, alongside
`config.json`/`session.json`, which are already gitignored) and should add
that path to `.gitignore` if it isn't already covered by the existing
`config.json`/`session.json` patterns (verify — `settings.json` is a
different filename, so this needs an explicit new gitignore entry).
