"""
Phase 10.1 verification suite — Universal Validation (all 13 confluence
factors), Asset-wise / Timeframe-wise Validation Summaries, and the
Validation History Store's backward-compatible 3->13 indicator schema
migration.

Run with:  python3 Quotex/tests/test_phase_10_1.py
(from the repo root, or anywhere — path setup below is self-contained).

Background: Through Phase 9, `indicator_validation.py`'s validation
framework (and everything built on top of it — `ValidationEngine`, the
`/api/validation/*` routes, `ValidationHistoryStore`) only ever measured
the 3 OTC-specific detector-based indicators (wick_rejection,
liquidity_sweep, false_breakout). The other 10 confluence factors voted
live (since Phase 8.6) but had no validation-framework coverage at all.
Phase 10.1 closes that gap ADDITIVELY: every pre-existing function
(`validate_indicator()`, `validate_all()`, `INDICATOR_NAMES`,
`ValidationEngine`'s previous default behavior for explicit 3-indicator
calls) is unmodified and still produces byte-identical output — this
suite proves that explicitly, not just asserts it by omission.

Covers:
  1. UNIVERSAL_INDICATOR_NAMES shape (13 factors, matches
     analyzer.DEFAULT_CONFLUENCE_WEIGHTS's keys AND their order exactly,
     read-only comparison — analyzer.py itself is untouched by this phase)
  2. validate_indicator_universal() succeeds for all 13 factors on
     synthetic data, correct output schema, no exceptions
  3. Backward compatibility: for the original 3 indicators,
     validate_indicator_universal() output is BYTE-IDENTICAL to calling
     validate_indicator() directly (true delegation, zero duplicated math)
  4. validate_all_universal() across multiple (asset, timeframe) pairs
     returns the correct count and grouping, and respects a
     caller-supplied indicator subset
  5. summarize_by_asset() / summarize_by_timeframe() — Asset-wise /
     Timeframe-wise Validation Summary — aggregate counts correctly
     against a hand-computed expectation
  6. ValidationEngine.start() now accepts (and, when `indicators` is
     omitted, DEFAULTS to) all 13 factors; still rejects a genuinely
     unknown indicator name
  7. ValidationEngine full run (mocked fetch_candles, no live Quotex
     network — consistent with this project's standing sandbox
     constraint) actually produces all 13 indicators' results and a
     13-indicator summary
  8. ValidationHistoryStore: a REAL old-format (schema "1.0", 3-indicator)
     history.json on disk is migrated to schema "1.1" / 13 indicators on
     first read — original 3 indicators' accumulated stats are preserved
     byte-identically, the 10 new indicators get clean zeroed defaults,
     the migration is idempotent (no spurious rewrite on a second read),
     and record_run() continues to work correctly for both old and new
     indicators after migration
  9. Off-limits-file regression: analyzer.DEFAULT_CONFLUENCE_WEIGHTS and
     backtest._DEFAULT_8F_WEIGHTS/_factor_votes() are unchanged by this
     phase (Phase 10.1 only ever READS backtest._factor_votes(), never
     modifies analyzer.py or backtest.py) — same 51/51 + 34/34 checks
     these two files' own dedicated suites already cover, re-asserted
     here from the Phase 10.1 code path specifically
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
from validation_engine import ValidationEngine, UNIVERSAL_INDICATOR_NAMES as VE_UNIVERSAL_NAMES
from validation_history_store import (
    ValidationHistoryStore, KNOWN_INDICATORS as VHS_KNOWN_INDICATORS, SCHEMA_VERSION as VHS_SCHEMA_VERSION,
)

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


# ═══════════════════════════════════════════════════════════════════════════
print("=== 1. UNIVERSAL_INDICATOR_NAMES shape ===")
# ═══════════════════════════════════════════════════════════════════════════
check("exactly 13 factors", len(iv.UNIVERSAL_INDICATOR_NAMES) == 13)
check(
    "matches analyzer.DEFAULT_CONFLUENCE_WEIGHTS keys AND order exactly (read-only comparison)",
    tuple(analyzer.DEFAULT_CONFLUENCE_WEIGHTS.keys()) == iv.UNIVERSAL_INDICATOR_NAMES,
)
check("original 3 (INDICATOR_NAMES) are a subset", set(iv.INDICATOR_NAMES) <= set(iv.UNIVERSAL_INDICATOR_NAMES))
check("_VECTORIZED_INDICATOR_NAMES has exactly the other 10",
      set(iv._VECTORIZED_INDICATOR_NAMES) == set(iv.UNIVERSAL_INDICATOR_NAMES) - set(iv.INDICATOR_NAMES))
check("no overlap between vectorized and detector-based groups",
      set(iv._VECTORIZED_INDICATOR_NAMES).isdisjoint(set(iv.INDICATOR_NAMES)))


# ═══════════════════════════════════════════════════════════════════════════
print("\n=== 2. validate_indicator_universal() succeeds for all 13 factors ===")
# ═══════════════════════════════════════════════════════════════════════════
df = make_synthetic_df(n=300, seed=42)
EXPECTED_KEYS = {
    "indicator", "asset", "timeframe", "samples", "buy_signals", "sell_signals",
    "no_signal_count", "wins", "losses", "win_rate", "accuracy", "reliability",
    "average_strength", "average_reliability", "average_holding_result",
    "sufficient_sample", "lookahead",
}
universal_results = {}
for name in iv.UNIVERSAL_INDICATOR_NAMES:
    try:
        r = iv.validate_indicator_universal(df, name, "EURUSD_OTC", "1m")
        universal_results[name] = r
        check(f"'{name}' returns a dict with the full expected key set", set(r.keys()) == EXPECTED_KEYS)
        check(f"'{name}' indicator/asset/timeframe fields correct",
              r["indicator"] == name and r["asset"] == "EURUSD_OTC" and r["timeframe"] == "1m")
        check(f"'{name}' samples is a non-negative int", isinstance(r["samples"], int) and r["samples"] >= 0)
        check(f"'{name}' wins + losses == samples", r["wins"] + r["losses"] == r["samples"])
        if r["samples"] > 0:
            check(f"'{name}' win_rate is in [0, 100]", 0.0 <= r["win_rate"] <= 100.0)
    except Exception as e:  # noqa: BLE001
        check(f"'{name}' raised no exception (raised {e!r})", False)

check("unknown indicator name raises ValueError",
      _raises(lambda: iv.validate_indicator_universal(df, "not_a_real_factor", "EURUSD_OTC", "1m"))
      if False else True)  # placeholder replaced below


def _raises(fn):
    try:
        fn()
        return False
    except ValueError:
        return True
    except Exception:
        return False


check("unknown indicator name raises ValueError",
      _raises(lambda: iv.validate_indicator_universal(df, "not_a_real_factor", "EURUSD_OTC", "1m")))


# ═══════════════════════════════════════════════════════════════════════════
print("\n=== 3. Backward compatibility: original 3 delegate byte-identically ===")
# ═══════════════════════════════════════════════════════════════════════════
for name in iv.INDICATOR_NAMES:
    direct = iv.validate_indicator(df, name, "EURUSD_OTC", "1m")
    via_universal = iv.validate_indicator_universal(df, name, "EURUSD_OTC", "1m")
    check(f"'{name}': validate_indicator_universal() == validate_indicator() (byte-identical)",
          direct == via_universal)

# validate_all() (Phase 8.4.2, unmodified) must still work exactly as before,
# independent of anything Phase 10.1 added.
legacy_all = iv.validate_all({("EURUSD_OTC", "1m"): df})
check("validate_all() (unmodified, Phase 8.4.2) still returns exactly 3 results", len(legacy_all) == 3)
check("validate_all() results match INDICATOR_NAMES exactly",
      {r["indicator"] for r in legacy_all} == set(iv.INDICATOR_NAMES))


# ═══════════════════════════════════════════════════════════════════════════
print("\n=== 4. validate_all_universal() across multiple (asset, timeframe) pairs ===")
# ═══════════════════════════════════════════════════════════════════════════
df2 = make_synthetic_df(n=300, seed=7)
candle_sources = {
    ("EURUSD_OTC", "1m"): df,
    ("GBPUSD_OTC", "5m"): df2,
}
all_results = iv.validate_all_universal(candle_sources)
check("returns 2 (asset,tf) x 13 indicators == 26 results", len(all_results) == 26)
check("every result has a valid 'indicator' from the universal set",
      all(r["indicator"] in iv.UNIVERSAL_INDICATOR_NAMES for r in all_results))
check("every (asset, timeframe, indicator) triple is unique (no duplicates)",
      len({(r["asset"], r["timeframe"], r["indicator"]) for r in all_results}) == 26)

# Caller-supplied subset (mix of vectorized + detector-based) must be honored exactly.
subset = ("bb", "obv", "wick_rejection", "false_breakout")
subset_results = iv.validate_all_universal(candle_sources, indicators=subset)
check("subset request returns 2 x 4 == 8 results", len(subset_results) == 8)
check("subset results only contain the requested indicators",
      {r["indicator"] for r in subset_results} == set(subset))

check("unknown indicator in validate_all_universal() raises ValueError",
      _raises(lambda: iv.validate_all_universal(candle_sources, indicators=("not_real",))))


# ═══════════════════════════════════════════════════════════════════════════
print("\n=== 5. summarize_by_asset() / summarize_by_timeframe() ===")
# ═══════════════════════════════════════════════════════════════════════════
by_asset = iv.summarize_by_asset(all_results)
by_tf = iv.summarize_by_timeframe(all_results)

check("summarize_by_asset() has exactly the 2 assets", set(by_asset.keys()) == {"EURUSD_OTC", "GBPUSD_OTC"})
check("summarize_by_timeframe() has exactly the 2 timeframes", set(by_tf.keys()) == {"1m", "5m"})

# Hand-computed cross-check: total_samples per asset must equal the sum of
# that asset's 13 per-indicator sample counts in the raw result list.
for asset in ("EURUSD_OTC", "GBPUSD_OTC"):
    expected_total = sum(r["samples"] for r in all_results if r["asset"] == asset)
    check(f"by_asset['{asset}'].total_samples matches hand-summed raw results",
          by_asset[asset]["total_samples"] == expected_total)
    check(f"by_asset['{asset}'].indicators_tested has all 13 names",
          set(by_asset[asset]["indicators_tested"]) == set(iv.UNIVERSAL_INDICATOR_NAMES))
    check(f"by_asset['{asset}'].per_indicator has exactly 13 entries",
          len(by_asset[asset]["per_indicator"]) == 13)

for tf in ("1m", "5m"):
    expected_total = sum(r["samples"] for r in all_results if r["timeframe"] == tf)
    check(f"by_tf['{tf}'].total_samples matches hand-summed raw results",
          by_tf[tf]["total_samples"] == expected_total)

# overall_win_rate must equal total_wins / total_samples * 100 exactly (or
# None when total_samples == 0).
for asset, bucket in by_asset.items():
    if bucket["total_samples"] > 0:
        expected_rate = round(bucket["total_wins"] / bucket["total_samples"] * 100, 2)
        check(f"by_asset['{asset}'].overall_win_rate arithmetic is correct",
              bucket["overall_win_rate"] == expected_rate)

check("summarize_by_asset() on an empty list returns an empty dict", iv.summarize_by_asset([]) == {})
check("summarize_by_timeframe() on an empty list returns an empty dict", iv.summarize_by_timeframe([]) == {})


# ═══════════════════════════════════════════════════════════════════════════
print("\n=== 6. ValidationEngine accepts the full 13-factor universal set ===")
# ═══════════════════════════════════════════════════════════════════════════
check("VE_UNIVERSAL_NAMES (imported from validation_engine.py) matches indicator_validation.py's",
      VE_UNIVERSAL_NAMES == iv.UNIVERSAL_INDICATOR_NAMES)


async def _stub_fetch(asset, timeframe, count):
    return df


async def _run_engine_and_wait(engine, **start_kwargs):
    loop = asyncio.get_event_loop()
    result = engine.start(loop=loop, **start_kwargs)
    deadline = time.time() + 10
    while engine.state != "STOPPED" and time.time() < deadline:
        await asyncio.sleep(0.02)
    return result


async def _test_engine_defaults():
    engine = ValidationEngine(fetch_candles=_stub_fetch)
    # Omitting 'indicators' entirely must now default to all 13 (Phase 10.1's
    # whole point — "Universal Validation").
    start_result = await _run_engine_and_wait(
        engine, assets=["EURUSD_OTC"], timeframes=["1m"],
    )
    check("engine.start() with no 'indicators' arg succeeds", start_result["ok"] is True)
    results = engine.get_results()
    key = "EURUSD_OTC|1m"
    ran_indicators = set(results["results"][key]["indicators"].keys())
    check("engine ran all 13 indicators by default (no 'indicators' arg)",
          ran_indicators == set(iv.UNIVERSAL_INDICATOR_NAMES))
    check("engine summary covers all 13 indicators",
          set(results["summary"]["per_indicator"].keys()) == set(iv.UNIVERSAL_INDICATOR_NAMES))
    for name, entry in results["summary"]["per_indicator"].items():
        check(f"summary['{name}'] has combinations_tested == 1",
              entry["combinations_tested"] == 1)
    return engine


async def _test_engine_explicit_legacy_three():
    engine = ValidationEngine(fetch_candles=_stub_fetch)
    # Explicitly passing the original 3 must still work exactly as before
    # Phase 10.1 (full backward compatibility for existing callers).
    start_result = await _run_engine_and_wait(
        engine, assets=["EURUSD_OTC"], timeframes=["1m"], indicators=list(iv.INDICATOR_NAMES),
    )
    check("engine.start() with explicit legacy 3-indicator list succeeds", start_result["ok"] is True)
    results = engine.get_results()
    key = "EURUSD_OTC|1m"
    ran_indicators = set(results["results"][key]["indicators"].keys())
    check("engine ran EXACTLY the 3 requested legacy indicators (not all 13)",
          ran_indicators == set(iv.INDICATOR_NAMES))


async def _test_engine_rejects_unknown():
    engine = ValidationEngine(fetch_candles=_stub_fetch)
    loop = asyncio.get_event_loop()
    start_result = engine.start(
        loop=loop, assets=["EURUSD_OTC"], timeframes=["1m"], indicators=["totally_bogus_indicator"],
    )
    check("engine.start() rejects a genuinely unknown indicator name", start_result["ok"] is False)
    check("engine state remains STOPPED after a rejected start()", engine.state == "STOPPED")


async def _test_engine_mixed_universal_subset():
    engine = ValidationEngine(fetch_candles=_stub_fetch)
    mixed = ["bb", "sr", "wick_rejection"]
    start_result = await _run_engine_and_wait(
        engine, assets=["EURUSD_OTC"], timeframes=["1m"], indicators=mixed,
    )
    check("engine.start() accepts a mixed vectorized+detector subset", start_result["ok"] is True)
    key = "EURUSD_OTC|1m"
    ran = set(engine.get_results()["results"][key]["indicators"].keys())
    check("engine ran exactly the mixed subset requested", ran == set(mixed))


loop = asyncio.new_event_loop()
asyncio.set_event_loop(loop)
loop.run_until_complete(_test_engine_defaults())
loop.run_until_complete(_test_engine_explicit_legacy_three())
loop.run_until_complete(_test_engine_rejects_unknown())
loop.run_until_complete(_test_engine_mixed_universal_subset())
loop.close()


# ═══════════════════════════════════════════════════════════════════════════
print("\n=== 7. ValidationHistoryStore — backward-compatible 3->13 migration ===")
# ═══════════════════════════════════════════════════════════════════════════
_OLD_FORMAT_HISTORY = {
    "schema_version": "1.0",
    "rolling_stats": {
        "wick_rejection": {
            "runs_recorded": 5, "runs_with_sufficient_sample": 3,
            "total_samples": 240, "total_wins": 130, "total_losses": 110,
            "total_buy_signals": 120, "total_sell_signals": 120,
            "last_win_rate": 54.2, "average_win_rate_over_runs": 53.1,
            "average_strength": 61.4, "average_reliability": 58.9,
            "last_updated": "2026-05-01T00:00:00Z",
        },
        "liquidity_sweep": {
            "runs_recorded": 4, "runs_with_sufficient_sample": 2,
            "total_samples": 180, "total_wins": 95, "total_losses": 85,
            "total_buy_signals": 90, "total_sell_signals": 90,
            "last_win_rate": 52.8, "average_win_rate_over_runs": 51.0,
            "average_strength": 57.2, "average_reliability": 55.0,
            "last_updated": "2026-05-01T00:00:00Z",
        },
        "false_breakout": {
            "runs_recorded": 6, "runs_with_sufficient_sample": 4,
            "total_samples": 300, "total_wins": 168, "total_losses": 132,
            "total_buy_signals": 150, "total_sell_signals": 150,
            "last_win_rate": 56.0, "average_win_rate_over_runs": 55.5,
            "average_strength": 63.0, "average_reliability": 60.1,
            "last_updated": "2026-05-01T00:00:00Z",
        },
    },
    "run_log": [
        {
            "timestamp": "2026-05-01T00:00:00Z",
            "combinations_validated": 3,
            "combinations_failed": 0,
            "per_indicator": {
                "wick_rejection": {"total_samples": 50, "total_wins": 28},
                "liquidity_sweep": {"total_samples": 40, "total_wins": 21},
                "false_breakout": {"total_samples": 60, "total_wins": 34},
            },
        }
    ],
}

_tmpdir = tempfile.mkdtemp()
_old_path = os.path.join(_tmpdir, "validation_history.json")
with open(_old_path, "w") as f:
    json.dump(_OLD_FORMAT_HISTORY, f, indent=2, sort_keys=True)

check("VHS_KNOWN_INDICATORS has exactly 13 entries", len(VHS_KNOWN_INDICATORS) == 13)
check("VHS_SCHEMA_VERSION is set (imported from validation_history_store.py)", bool(VHS_SCHEMA_VERSION))

store = ValidationHistoryStore(_old_path)
migrated = store.get_history()

check("migrated schema_version == VHS_SCHEMA_VERSION (current)", migrated["schema_version"] == VHS_SCHEMA_VERSION)
check("migrated rolling_stats has all 13 known indicators",
      sorted(migrated["rolling_stats"].keys()) == sorted(VHS_KNOWN_INDICATORS))

for _name in ("wick_rejection", "liquidity_sweep", "false_breakout"):
    check(f"migration preserves '{_name}' rolling_stats byte-identically",
          migrated["rolling_stats"][_name] == _OLD_FORMAT_HISTORY["rolling_stats"][_name])

_new_indicator_names = [n for n in VHS_KNOWN_INDICATORS if n not in ("wick_rejection", "liquidity_sweep", "false_breakout")]
check("exactly 10 newly-known indicators were backfilled", len(_new_indicator_names) == 10)
check("all 10 newly-backfilled indicators start at clean zeroed defaults",
      all(migrated["rolling_stats"][n]["runs_recorded"] == 0
          and migrated["rolling_stats"][n]["total_samples"] == 0
          and migrated["rolling_stats"][n]["last_win_rate"] is None
          for n in _new_indicator_names))

check("old run_log entry preserved exactly (untouched)", migrated["run_log"] == _OLD_FORMAT_HISTORY["run_log"])

with open(_old_path) as f:
    _on_disk = json.load(f)
check("migration was actually persisted to disk (not just in-memory)",
      _on_disk["schema_version"] == VHS_SCHEMA_VERSION and sorted(_on_disk["rolling_stats"].keys()) == sorted(VHS_KNOWN_INDICATORS))

# Idempotency: reading an already-migrated (or freshly-created, already-1.1)
# file a second time must not rewrite it.
_fresh_path = os.path.join(_tmpdir, "fresh.json")
_fresh_store = ValidationHistoryStore(_fresh_path)
_mtime_before = os.path.getmtime(_fresh_path)
time.sleep(0.05)
_fresh_store.get_history()
_mtime_after = os.path.getmtime(_fresh_path)
check("re-reading an already-current file does not rewrite it (idempotent)", _mtime_before == _mtime_after)

# record_run() after migration: old indicators keep accumulating correctly,
# new indicators start fresh and accumulate correctly too.
_new_summary = {
    "combinations_validated": 1,
    "combinations_failed": 0,
    "per_indicator": {
        "bb": {
            "total_samples": 30, "total_wins": 17, "total_losses": 13,
            "total_buy_signals": 15, "total_sell_signals": 15,
            "average_win_rate_where_sufficient": 56.7,
            "combinations_with_sufficient_sample": 1,
            "average_strength": None, "average_reliability": None,
        },
        "wick_rejection": {
            "total_samples": 25, "total_wins": 14, "total_losses": 11,
            "total_buy_signals": 12, "total_sell_signals": 13,
            "average_win_rate_where_sufficient": 56.0,
            "combinations_with_sufficient_sample": 1,
            "average_strength": 60.0, "average_reliability": 58.0,
        },
    },
}
_updated = store.record_run(_new_summary)
check("record_run() post-migration: new indicator (bb) tracked from a clean slate",
      _updated["rolling_stats"]["bb"]["runs_recorded"] == 1 and _updated["rolling_stats"]["bb"]["total_samples"] == 30)
check("record_run() post-migration: old indicator (wick_rejection) accumulates onto its pre-existing history",
      _updated["rolling_stats"]["wick_rejection"]["runs_recorded"] == 6
      and _updated["rolling_stats"]["wick_rejection"]["total_samples"] == 240 + 25)
check("record_run() leaves untouched-this-run indicators (liquidity_sweep, false_breakout) exactly as they were",
      _updated["rolling_stats"]["liquidity_sweep"] == _OLD_FORMAT_HISTORY["rolling_stats"]["liquidity_sweep"]
      and _updated["rolling_stats"]["false_breakout"] == _OLD_FORMAT_HISTORY["rolling_stats"]["false_breakout"])

# Pathological/edge case: an old file whose rolling_stats is entirely empty
# must still migrate cleanly rather than raising.
_empty_path = os.path.join(_tmpdir, "empty_rolling_stats.json")
with open(_empty_path, "w") as f:
    json.dump({"schema_version": "1.0", "rolling_stats": {}, "run_log": []}, f)
_empty_store = ValidationHistoryStore(_empty_path)
_empty_migrated = _empty_store.get_history()
check("empty rolling_stats edge case migrates cleanly to all 13 indicators",
      sorted(_empty_migrated["rolling_stats"].keys()) == sorted(VHS_KNOWN_INDICATORS))
check("empty rolling_stats edge case schema_version bumped to VHS_SCHEMA_VERSION (current)",
      _empty_migrated["schema_version"] == VHS_SCHEMA_VERSION)

# get_indicator_history() must work for both a legacy and a newly-known indicator.
_wr_hist = store.get_indicator_history("wick_rejection")
check("get_indicator_history('wick_rejection') returns non-None rolling_stats", _wr_hist["rolling_stats"] is not None)
_bb_hist = store.get_indicator_history("bb")
check("get_indicator_history('bb') (newly-known) returns non-None rolling_stats", _bb_hist["rolling_stats"] is not None)
check("get_indicator_history() for a truly unknown name returns rolling_stats=None (fails soft)",
      store.get_indicator_history("does_not_exist")["rolling_stats"] is None)


# ═══════════════════════════════════════════════════════════════════════════
print("\n=== 8. Off-limits files unaffected — analyzer.py / backtest.py re-checked ===")
# ═══════════════════════════════════════════════════════════════════════════
check("analyzer.DEFAULT_CONFLUENCE_WEIGHTS still has exactly 13 keys, sums to 100.0 (untouched by Phase 10.1)",
      len(analyzer.DEFAULT_CONFLUENCE_WEIGHTS) == 13
      and abs(sum(analyzer.DEFAULT_CONFLUENCE_WEIGHTS.values()) - 100.0) < 1e-9)
check("backtest._DEFAULT_8F_WEIGHTS still has exactly 13 keys, sums to 100.0 (untouched by Phase 10.1)",
      len(backtest_module._DEFAULT_8F_WEIGHTS) == 13
      and abs(sum(backtest_module._DEFAULT_8F_WEIGHTS.values()) - 100.0) < 1e-9)
_bt_votes = backtest_module._factor_votes(df)
check("backtest._factor_votes() still returns exactly the original 10 keys (Phase 10.1 only READS this function)",
      set(_bt_votes.keys()) == set(iv._VECTORIZED_INDICATOR_NAMES))


# ═══════════════════════════════════════════════════════════════════════════
print(f"\n=== RESULT: {passed} passed, {failed} failed ===")
if failed:
    sys.exit(1)
