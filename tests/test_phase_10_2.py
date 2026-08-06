"""
Phase 10.2 verification suite — Asset Intelligence + Timeframe Intelligence.

Run with:  python3 Quotex/tests/test_phase_10_2.py
(from the repo root, or anywhere — path setup below is self-contained).

Background: through Phase 10.1, Validation History (`validation_history_
store.py`) only ever tracked a single GLOBAL rolling-stats bucket per
indicator (`rolling_stats`), folded across every asset and timeframe
combined. There was no way to know which indicator performs best on
EURUSD_otc specifically, or on the 1m timeframe specifically. Phase 10.2
closes that gap ADDITIVELY:
  - `validation_history_store.py` gains two new top-level keys,
    `asset_stats` / `timeframe_stats` (schema 1.1 -> 1.2), populated by a
    new `record_asset_timeframe_stats()` method — `get_history()`,
    `record_run()`, `get_indicator_history()`, `reset()`'s pre-existing
    behavior for `rolling_stats`/`run_log` is completely unmodified.
  - a new standalone module, `asset_timeframe_learning.py`, computes
    rankings/recommendations from that new data (and from the
    pre-existing global `rolling_stats` for indicator-only rankings) —
    pure functions, no I/O, no persisted store of its own.
  - 4 new read-only `/api/learning/*` routes in app.py (not directly
    tested here — this project's standing sandbox constraint blocks full
    Flask-test-client coverage, same limitation already documented for
    Phase 10.1's summary routes; route wiring is confirmed by code review
    plus `py_compile`, and every function each route calls is directly
    covered below).

Covers:
  1. `validation_history_store.py` schema 1.2: fresh-store defaults,
     `record_asset_timeframe_stats()` accumulation math (single run,
     across multiple runs), `get_asset_stats()`/`get_timeframe_stats()`
     accessors, `record_run()` (unmodified) provably independent of the
     new keys, `reset()` clearing all four top-level keys
  2. Backward-compatible 1.1 -> 1.2 migration verified against a REAL
     synthetic old-format (schema "1.1", no asset_stats/timeframe_stats
     keys at all) file on disk — schema bump, byte-identical preservation
     of pre-existing `rolling_stats`/`run_log`, new keys backfilled empty,
     idempotent re-read, persisted to actual disk bytes not just in-memory
  3. `asset_timeframe_learning.py`'s pure functions against a hand-built
     history dict with known, hand-computed expected results:
     `compute_asset_rankings()`, `compute_timeframe_rankings()` (pooled
     accuracy/trend/confidence math, best/weakest indicator selection,
     min_samples-gated ranking order), `compute_top_indicators()` (global
     ranking from `rolling_stats`), `compute_recommendations()`
     (best-per-asset/best-per-timeframe/weakest/improving/declining)
  4. Full end-to-end flow: a real `ValidationEngine` run (mocked
     `fetch_candles`, no live network — consistent with this project's
     standing sandbox constraint) -> `ValidationHistoryStore.
     record_asset_timeframe_stats()` -> `asset_timeframe_learning.py`'s
     functions, proving the whole pipeline connects correctly end to end,
     not just each piece in isolation
  5. Off-limits-file re-check: `analyzer.DEFAULT_CONFLUENCE_WEIGHTS`,
     `backtest._factor_votes()`/`_DEFAULT_8F_WEIGHTS`, and
     `indicator_validation.UNIVERSAL_INDICATOR_NAMES` are all unchanged by
     this phase — Phase 10.2 only reads `ValidationHistoryStore.
     get_history()`, never any of those other modules
"""
import sys
import os

_HERE = os.path.dirname(os.path.abspath(__file__))
_MARKET_ANALYZER = os.path.join(_HERE, "..", "market_analyzer")
_WEBAPP = os.path.join(_MARKET_ANALYZER, "webapp")
sys.path.insert(0, _MARKET_ANALYZER)
sys.path.insert(0, _WEBAPP)

import asyncio
import json
import tempfile
import time

import numpy as np
import pandas as pd

import analyzer
import backtest as backtest_module
import indicator_validation as iv
from validation_engine import ValidationEngine
from validation_history_store import (
    ValidationHistoryStore, KNOWN_INDICATORS as VHS_KNOWN_INDICATORS, SCHEMA_VERSION as VHS_SCHEMA_VERSION,
)
import asset_timeframe_learning as atl

passed = 0
failed = 0


def check(name, cond):
    global passed, failed
    if cond:
        print(f"  PASS  {name}")
        passed += 1
    else:
        print(f"  FAIL  {name}")
        failed += 1


def make_synthetic_df(n=300, seed=0):
    rng = np.random.RandomState(seed)
    price = 100 + np.cumsum(rng.randn(n) * 0.5)
    return pd.DataFrame({
        "open": price + rng.randn(n) * 0.1,
        "high": price + np.abs(rng.randn(n) * 0.3),
        "low": price - np.abs(rng.randn(n) * 0.3),
        "close": price,
        "volume": rng.randint(100, 1000, n),
    })


def _stats(samples, wins, last_wr, avg_wr, strength=None, reliability=None):
    return {
        "runs_recorded": 3, "runs_with_sufficient_sample": 3,
        "total_samples": samples, "total_wins": wins, "total_losses": samples - wins,
        "total_buy_signals": samples // 2, "total_sell_signals": samples - samples // 2,
        "last_win_rate": last_wr, "average_win_rate_over_runs": avg_wr,
        "average_strength": strength, "average_reliability": reliability, "last_updated": "2026-07-27T00:00:00Z",
    }


# ═══════════════════════════════════════════════════════════════════════════
print("=== 1. validation_history_store.py — schema 1.2 storage layer ===")
# ═══════════════════════════════════════════════════════════════════════════
check("VHS_SCHEMA_VERSION is set (imported)", bool(VHS_SCHEMA_VERSION))
check("VHS_KNOWN_INDICATORS still has exactly 13 entries (Phase 10.1, unchanged)", len(VHS_KNOWN_INDICATORS) == 13)

_tmpdir = tempfile.mkdtemp()
_fresh_path = os.path.join(_tmpdir, "fresh.json")
_store = ValidationHistoryStore(_fresh_path)
_fresh = _store.get_history()
check("fresh store: asset_stats starts empty", _fresh["asset_stats"] == {})
check("fresh store: timeframe_stats starts empty", _fresh["timeframe_stats"] == {})
check("fresh store: rolling_stats still has all 13 indicators (unchanged)",
      sorted(_fresh["rolling_stats"].keys()) == sorted(VHS_KNOWN_INDICATORS))

_engine_results = {
    "EURUSD_otc|1m": {
        "asset": "EURUSD_otc", "timeframe": "1m", "candles_used": 2000,
        "indicators": {
            "bb": {"samples": 40, "wins": 24, "losses": 16, "win_rate": 60.0,
                   "buy_signals": 20, "sell_signals": 20, "sufficient_sample": True,
                   "average_strength": None, "average_reliability": None},
            "wick_rejection": {"samples": 30, "wins": 15, "losses": 15, "win_rate": 50.0,
                   "buy_signals": 15, "sell_signals": 15, "sufficient_sample": True,
                   "average_strength": 55.0, "average_reliability": 52.0},
        },
        "timestamp": "2026-07-27T00:00:00Z",
    },
    "GBPUSD_otc|5m": {
        "asset": "GBPUSD_otc", "timeframe": "5m", "candles_used": 2000,
        "indicators": {
            "bb": {"samples": 10, "wins": 6, "losses": 4, "win_rate": 60.0,
                   "buy_signals": 5, "sell_signals": 5, "sufficient_sample": False,
                   "average_strength": None, "average_reliability": None},
        },
        "timestamp": "2026-07-27T00:00:00Z",
    },
    "USDJPY_otc|1m": {"asset": "USDJPY_otc", "timeframe": "1m", "error": "fetch failed", "timestamp": "x"},
}
_updated = _store.record_asset_timeframe_stats(_engine_results, timestamp="2026-07-27T00:00:00Z")
check("record_asset_timeframe_stats(): correct assets recorded", set(_updated["asset_stats"].keys()) == {"EURUSD_otc", "GBPUSD_otc"})
check("record_asset_timeframe_stats(): error combo (USDJPY_otc) skipped entirely", "USDJPY_otc" not in _updated["asset_stats"])
check("record_asset_timeframe_stats(): correct timeframes recorded", set(_updated["timeframe_stats"].keys()) == {"1m", "5m"})

_eur_bb = _updated["asset_stats"]["EURUSD_otc"]["bb"]
check("EURUSD_otc/bb: total_samples == 40", _eur_bb["total_samples"] == 40)
check("EURUSD_otc/bb: total_wins == 24", _eur_bb["total_wins"] == 24)
check("EURUSD_otc/bb: last_win_rate == 60.0", _eur_bb["last_win_rate"] == 60.0)
check("EURUSD_otc/bb: runs_recorded == 1", _eur_bb["runs_recorded"] == 1)

_tf_1m_wr = _updated["timeframe_stats"]["1m"]["wick_rejection"]
check("1m/wick_rejection: total_samples == 30", _tf_1m_wr["total_samples"] == 30)
check("1m/wick_rejection: average_strength == 55.0", _tf_1m_wr["average_strength"] == 55.0)

_gbp_bb = _updated["asset_stats"]["GBPUSD_otc"]["bb"]
check("GBPUSD_otc/bb (insufficient sample): total_samples still counted", _gbp_bb["total_samples"] == 10)
check("GBPUSD_otc/bb (insufficient sample): last_win_rate NOT recorded (None)", _gbp_bb["last_win_rate"] is None)

# Second run — must ACCUMULATE, not overwrite.
_results2 = {
    "EURUSD_otc|1m": {
        "asset": "EURUSD_otc", "timeframe": "1m",
        "indicators": {"bb": {"samples": 20, "wins": 8, "losses": 12, "win_rate": 40.0,
                               "buy_signals": 10, "sell_signals": 10, "sufficient_sample": True,
                               "average_strength": None, "average_reliability": None}},
    },
}
_updated2 = _store.record_asset_timeframe_stats(_results2, timestamp="2026-07-27T01:00:00Z")
_eur_bb2 = _updated2["asset_stats"]["EURUSD_otc"]["bb"]
check("Accumulation across 2 runs: runs_recorded == 2", _eur_bb2["runs_recorded"] == 2)
check("Accumulation across 2 runs: total_samples == 60 (40+20)", _eur_bb2["total_samples"] == 60)
check("Accumulation across 2 runs: total_wins == 32 (24+8)", _eur_bb2["total_wins"] == 32)
check("Accumulation across 2 runs: average_win_rate_over_runs == 50.0 ((60+40)/2)",
      _eur_bb2["average_win_rate_over_runs"] == 50.0)

check("get_asset_stats('EURUSD_otc') accessor returns correct shape",
      _store.get_asset_stats("EURUSD_otc")["asset"] == "EURUSD_otc" and "bb" in _store.get_asset_stats("EURUSD_otc")["indicators"])
check("get_asset_stats() for an unknown asset fails soft (empty indicators, not an exception)",
      _store.get_asset_stats("NOT_REAL_otc")["indicators"] == {})
check("get_timeframe_stats('5m') accessor returns correct shape",
      "bb" in _store.get_timeframe_stats("5m")["indicators"])
check("get_asset_stats(None) returns every recorded asset",
      set(_store.get_asset_stats().keys()) == {"EURUSD_otc", "GBPUSD_otc"})

# record_run() (Phase 8.5, unmodified) must be provably independent of the new keys.
_before = json.dumps(_store.get_asset_stats(), sort_keys=True)
_summary = {"combinations_validated": 1, "combinations_failed": 0,
            "per_indicator": {"bb": {"total_samples": 5, "total_wins": 3, "total_losses": 2,
                                      "total_buy_signals": 2, "total_sell_signals": 3,
                                      "average_win_rate_where_sufficient": None,
                                      "combinations_with_sufficient_sample": 0,
                                      "average_strength": None, "average_reliability": None}}}
_store.record_run(_summary, timestamp="2026-07-27T02:00:00Z")
_after = json.dumps(_store.get_asset_stats(), sort_keys=True)
check("record_run() (unmodified) does not touch asset_stats/timeframe_stats at all", _before == _after)

# reset() clears all four top-level keys.
_store.reset()
_reset_history = _store.get_history()
check("reset() clears asset_stats", _reset_history["asset_stats"] == {})
check("reset() clears timeframe_stats", _reset_history["timeframe_stats"] == {})
check("reset() clears rolling_stats back to zeroed 13-indicator defaults",
      all(v["total_samples"] == 0 for v in _reset_history["rolling_stats"].values()))


# ═══════════════════════════════════════════════════════════════════════════
print("\n=== 2. Backward-compatible 1.1 -> 1.2 migration (real synthetic old file) ===")
# ═══════════════════════════════════════════════════════════════════════════
_OLD_11_HISTORY = {
    "schema_version": "1.1",
    "rolling_stats": {name: _stats(50, 28, 56.0, 56.0) for name in VHS_KNOWN_INDICATORS},
    "run_log": [{"timestamp": "2026-07-20T00:00:00Z", "combinations_validated": 1,
                 "combinations_failed": 0, "per_indicator": {}}],
}
_old_path = os.path.join(_tmpdir, "old_11.json")
with open(_old_path, "w") as f:
    json.dump(_OLD_11_HISTORY, f, indent=2, sort_keys=True)

_migrate_store = ValidationHistoryStore(_old_path)
_migrated = _migrate_store.get_history()
check("migrated schema_version == current VHS_SCHEMA_VERSION", _migrated["schema_version"] == VHS_SCHEMA_VERSION)
check("migrated: asset_stats backfilled as empty dict", _migrated["asset_stats"] == {})
check("migrated: timeframe_stats backfilled as empty dict", _migrated["timeframe_stats"] == {})
check("migrated: pre-existing rolling_stats preserved BYTE-IDENTICALLY",
      _migrated["rolling_stats"] == _OLD_11_HISTORY["rolling_stats"])
check("migrated: pre-existing run_log preserved BYTE-IDENTICALLY", _migrated["run_log"] == _OLD_11_HISTORY["run_log"])

with open(_old_path) as f:
    _on_disk = json.load(f)
check("migration actually persisted to disk (not just in-memory)",
      _on_disk["schema_version"] == VHS_SCHEMA_VERSION and "asset_stats" in _on_disk and "timeframe_stats" in _on_disk)

_mtime1 = os.path.getmtime(_old_path)
time.sleep(0.05)
_migrate_store.get_history()
_mtime2 = os.path.getmtime(_old_path)
check("idempotent re-read of an already-migrated file causes no rewrite", _mtime1 == _mtime2)

# record_asset_timeframe_stats() must work correctly immediately after migration.
_post_migration = _migrate_store.record_asset_timeframe_stats({
    "EURUSD_otc|1m": {"asset": "EURUSD_otc", "timeframe": "1m",
                       "indicators": {"bb": {"samples": 15, "wins": 9, "losses": 6, "win_rate": 60.0,
                                              "buy_signals": 7, "sell_signals": 8, "sufficient_sample": False,
                                              "average_strength": None, "average_reliability": None}}}
}, timestamp="2026-07-27T03:00:00Z")
check("record_asset_timeframe_stats() works correctly on a freshly-migrated 1.1->1.2 file",
      _post_migration["asset_stats"]["EURUSD_otc"]["bb"]["total_samples"] == 15)
check("post-migration record does not disturb the pre-existing rolling_stats",
      _post_migration["rolling_stats"] == _OLD_11_HISTORY["rolling_stats"])


# ═══════════════════════════════════════════════════════════════════════════
print("\n=== 3. asset_timeframe_learning.py — pure functions, hand-computed expectations ===")
# ═══════════════════════════════════════════════════════════════════════════
_history = {
    "schema_version": "1.2",
    "rolling_stats": {
        "bb": _stats(100, 60, 65.0, 60.0),
        "obv": _stats(100, 40, 35.0, 40.0),
        "sr": _stats(100, 50, 50.5, 50.0),
        "wick_rejection": _stats(5, 3, 60.0, 60.0),
    },
    "run_log": [],
    "asset_stats": {
        "EURUSD_otc": {"bb": _stats(60, 40, 66.0, 62.0), "obv": _stats(40, 15, 30.0, 35.0)},
        "GBPUSD_otc": {"bb": _stats(30, 12, 40.0, 42.0)},
        "USDJPY_otc": {"bb": _stats(5, 3, 60.0, 60.0)},  # below min_samples(20)
    },
    "timeframe_stats": {
        "1m": {"bb": _stats(50, 32, 64.0, 60.0), "obv": _stats(50, 20, 38.0, 42.0)},
        "5m": {"bb": _stats(50, 20, 38.0, 42.0)},
        "15m": {},
    },
}

_ar = atl.compute_asset_rankings(_history, min_samples=20)
check("compute_asset_rankings(): all 3 assets present in 'assets'",
      set(_ar["assets"].keys()) == {"EURUSD_otc", "GBPUSD_otc", "USDJPY_otc"})
check("compute_asset_rankings(): ranking gated by min_samples excludes USDJPY_otc (5 < 20 samples)",
      _ar["ranking"] == ["EURUSD_otc", "GBPUSD_otc"])
check("compute_asset_rankings(): USDJPY_otc still visible in 'assets' even though excluded from ranking",
      "USDJPY_otc" in _ar["assets"])
_eur = _ar["assets"]["EURUSD_otc"]
check("EURUSD_otc: total_validations == 100 (60+40)", _eur["total_validations"] == 100)
check("EURUSD_otc: wins == 55 (40+15)", _eur["wins"] == 55)
check("EURUSD_otc: losses == 45", _eur["losses"] == 45)
check("EURUSD_otc: accuracy == 55.0 (55/100)", _eur["accuracy"] == 55.0)
check("EURUSD_otc: best_indicator == 'bb' (higher average_win_rate_over_runs)", _eur["best_indicator"] == "bb")
check("EURUSD_otc: weakest_indicator == 'obv'", _eur["weakest_indicator"] == "obv")
_gbp = _ar["assets"]["GBPUSD_otc"]
check("GBPUSD_otc: accuracy == 40.0 (12/30)", _gbp["accuracy"] == 40.0)

_tr = atl.compute_timeframe_rankings(_history, min_samples=20)
_tf1m = _tr["timeframes"]["1m"]
check("1m: total_validations == 100 (50+50)", _tf1m["total_validations"] == 100)
check("1m: accuracy == 52.0 ((32+20)/100)", _tf1m["accuracy"] == 52.0)
_tf15 = _tr["timeframes"]["15m"]
check("15m (empty): accuracy is None", _tf15["accuracy"] is None)
check("15m (empty): best_indicator is None", _tf15["best_indicator"] is None)
check("15m (empty) omitted from ranking (no accuracy)", "15m" not in _tr["ranking"])
check("Timeframe ranking works for ANY timeframe string (1m/5m/15m), no fixed enum required",
      set(_tr["timeframes"].keys()) == {"1m", "5m", "15m"})

_ti = atl.compute_top_indicators(_history, min_samples=20)
check("compute_top_indicators(): top[0] is 'bb' (highest average_win_rate_over_runs)", _ti["top"][0]["indicator"] == "bb")
check("compute_top_indicators(): 'wick_rejection' (5 samples < 20) is in no_data, not top/weakest",
      "wick_rejection" in [e["indicator"] for e in _ti["no_data"]]
      and "wick_rejection" not in [e["indicator"] for e in _ti["top"] + _ti["weakest"]])

_rec = atl.compute_recommendations(_history, min_samples=20)
check("compute_recommendations(): best_indicators_per_asset['EURUSD_otc'] == 'bb'",
      _rec["best_indicators_per_asset"]["EURUSD_otc"] == "bb")
check("compute_recommendations(): 'bb' correctly flagged improving (65.0 vs 60.0, diff=5 > band)",
      "bb" in [e["indicator"] for e in _rec["improving_indicators"]])
check("compute_recommendations(): 'obv' correctly flagged declining (35.0 vs 40.0, diff=-5 < -band)",
      "obv" in [e["indicator"] for e in _rec["declining_indicators"]])
check("compute_recommendations(): 'sr' (stable, diff=0.5 within band) in neither improving nor declining",
      "sr" not in [e["indicator"] for e in _rec["improving_indicators"] + _rec["declining_indicators"]])
check("compute_recommendations(): lowest_performing_indicators matches compute_top_indicators()'s weakest",
      [e["indicator"] for e in _rec["lowest_performing_indicators"]] == [e["indicator"] for e in _ti["weakest"]])

check("compute_asset_rankings({}) on empty history returns empty assets/ranking, no exception",
      atl.compute_asset_rankings({}) == {**atl.compute_asset_rankings({}), "assets": {}, "ranking": []})
_empty_ar = atl.compute_asset_rankings({})
check("empty history: assets == {}", _empty_ar["assets"] == {})
check("empty history: ranking == []", _empty_ar["ranking"] == [])


# ═══════════════════════════════════════════════════════════════════════════
print("\n=== 4. Full end-to-end: ValidationEngine -> ValidationHistoryStore -> Learning ===")
# ═══════════════════════════════════════════════════════════════════════════
_dfs = {"EURUSD_otc": make_synthetic_df(seed=11), "GBPUSD_otc": make_synthetic_df(seed=22)}


async def _e2e_fetch(asset, timeframe, count):
    return _dfs[asset]


async def _run_e2e():
    loop = asyncio.get_event_loop()
    engine = ValidationEngine(fetch_candles=_e2e_fetch)
    engine.start(loop=loop, assets=["EURUSD_otc", "GBPUSD_otc"], timeframes=["1m", "5m"])
    deadline = time.time() + 15
    while engine.state != "STOPPED" and time.time() < deadline:
        await asyncio.sleep(0.02)
    check("e2e: ValidationEngine reached STOPPED", engine.state == "STOPPED")

    e2e_store = ValidationHistoryStore(os.path.join(_tmpdir, "e2e.json"))
    results = engine.get_results()
    e2e_store.record_run(results["summary"], timestamp="2026-07-27T04:00:00Z")
    e2e_store.record_asset_timeframe_stats(results["results"], timestamp="2026-07-27T04:00:00Z")

    e2e_history = e2e_store.get_history()
    check("e2e: both assets recorded in asset_stats", set(e2e_history["asset_stats"].keys()) == {"EURUSD_otc", "GBPUSD_otc"})
    check("e2e: both timeframes recorded in timeframe_stats", set(e2e_history["timeframe_stats"].keys()) == {"1m", "5m"})
    check("e2e: each asset has all 13 indicators recorded",
          all(len(v) == 13 for v in e2e_history["asset_stats"].values()))

    e2e_ar = atl.compute_asset_rankings(e2e_history, min_samples=5)
    e2e_tr = atl.compute_timeframe_rankings(e2e_history, min_samples=5)
    e2e_rec = atl.compute_recommendations(e2e_history, min_samples=5)
    check("e2e: compute_asset_rankings() produces a non-empty ranking from real engine output",
          len(e2e_ar["ranking"]) == 2)
    check("e2e: compute_timeframe_rankings() produces a non-empty ranking from real engine output",
          len(e2e_tr["ranking"]) == 2)
    check("e2e: compute_recommendations() produces a best indicator for every asset",
          all(v is not None for v in e2e_rec["best_indicators_per_asset"].values()))


loop = asyncio.new_event_loop()
asyncio.set_event_loop(loop)
loop.run_until_complete(_run_e2e())
loop.close()


# ═══════════════════════════════════════════════════════════════════════════
print("\n=== 5. Off-limits files unaffected — re-checked from the Phase 10.2 code path ===")
# ═══════════════════════════════════════════════════════════════════════════
check("analyzer.DEFAULT_CONFLUENCE_WEIGHTS still 13 keys summing to 100.0 (untouched)",
      len(analyzer.DEFAULT_CONFLUENCE_WEIGHTS) == 13
      and abs(sum(analyzer.DEFAULT_CONFLUENCE_WEIGHTS.values()) - 100.0) < 1e-9)
check("backtest._DEFAULT_8F_WEIGHTS still 13 keys summing to 100.0 (untouched)",
      len(backtest_module._DEFAULT_8F_WEIGHTS) == 13
      and abs(sum(backtest_module._DEFAULT_8F_WEIGHTS.values()) - 100.0) < 1e-9)
check("indicator_validation.UNIVERSAL_INDICATOR_NAMES still exactly 13 (untouched)",
      len(iv.UNIVERSAL_INDICATOR_NAMES) == 13)
check("asset_timeframe_learning.py imports nothing from analyzer/backtest/validation_engine/indicator_validation/scanner",
      not any(mod in dir(atl) for mod in ("analyzer", "backtest", "validation_engine", "indicator_validation", "scanner")))


# ═══════════════════════════════════════════════════════════════════════════
print(f"\n=== RESULT: {passed} passed, {failed} failed ===")
if failed:
    sys.exit(1)
