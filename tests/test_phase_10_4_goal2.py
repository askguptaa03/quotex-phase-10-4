"""
Phase 10.4 Goal 2 verification suite — Adaptive AI Calibration.

Run with:  python3 Quotex/tests/test_phase_10_4_goal2.py
(from the repo root, or anywhere — path setup below is self-contained).

Background: this phase adds ONE new, additive, standalone module —
`adaptive_calibration.py` — plus 4 new read-only `/api/calibration/*`
routes wired into `webapp/app.py` (an import line + one new route block,
appended after the existing AI Health/Explainable Signal block; every
route that already existed is untouched). No change to walk_forward.py,
backtest.py, analyzer.py, scanner.py, learning_engine.py,
indicator_registry.py, or the Quotex API.

Covers:
  1. Validation-history-based functions (no df): compute_validation_trend,
     compute_accuracy_trend, compute_indicator_stability,
     compute_weight_stability against hand-built history dicts with KNOWN
     expected results, plus the "no_data" convention for thin/absent data
     (never fabricated, never Critical-equivalent).
  2. Group calibration: compute_asset_calibration / compute_timeframe_
     calibration against hand-built asset_stats/timeframe_stats dicts,
     including an "unknown"/never-recorded group (analogous to this
     project's "Unknown regime" convention — adaptive_calibration.py takes
     no regime input directly, so the closest equivalent this module can
     exercise is a group key with zero recorded data, verified to return
     score=None/confidence="none" rather than a guess).
  3. Walk-forward-based functions (require a df): compute_confidence_
     calibration, compute_confidence_scaling + apply_confidence_scaling,
     optimize_threshold, compute_rolling_calibration against synthetic
     trending/noisy/flat DataFrames — bucket accounting, insufficient-data
     handling, deterministic output.
  4. build_calibration_report(): with and without a df, empty inputs
     (None/empty dicts) handled without crashing.
  5. generate_calibration_recommendations(): each generated recommendation
     has reason/evidence/confidence/severity; specific rule outcomes
     verified against hand-built inputs (unstable indicator ->
     ignore_unstable_indicator, improving trend -> increase_indicator_
     weight, etc.); empty report -> empty list, not a crash.
  6. Edge cases: empty history, missing validation, missing learning
     history, determinism (same input -> identical output across repeated
     calls).
  7. Off-limits-file regression safety: analyzer.py / backtest.py /
     walk_forward.py / webapp/scanner.py / webapp/learning_engine.py /
     webapp/indicator_registry.py source re-confirmed to contain no
     reference to adaptive_calibration (not modified, not wired into any
     of them); webapp/app.py source re-confirmed to contain the new
     import + all 4 new routes, and every Goal-1/pre-existing route
     signature still present verbatim (source inspection — this sandbox
     still cannot import app.py itself: fetch_data -> api_quotex ->
     loguru, not installed, same standing limitation Phase 10.1/10.2/
     10.3-Part-1/Part-2's test suites already document).
"""
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
_MARKET_ANALYZER = os.path.join(_HERE, "..", "market_analyzer")
_WEBAPP = os.path.join(_MARKET_ANALYZER, "webapp")
sys.path.insert(0, _MARKET_ANALYZER)
sys.path.insert(0, _WEBAPP)

import numpy as np
import pandas as pd

import backtest
import walk_forward as wf
import adaptive_calibration as ac

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


def make_trending_df(n=300):
    price = 100 + np.arange(n) * 0.35
    noise = np.tile([0.0, 0.02, -0.02, 0.01], n // 4 + 1)[:n]
    price = price + noise
    return pd.DataFrame({
        "open": price, "high": price + 0.05, "low": price - 0.05,
        "close": price, "volume": np.full(n, 500),
    })


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


def _rolling_stats(total_samples, avg_wr, last_wr):
    return {
        "runs_recorded": 5, "runs_with_sufficient_sample": 5,
        "total_samples": total_samples, "total_wins": int(total_samples * (avg_wr or 0) / 100),
        "total_losses": total_samples - int(total_samples * (avg_wr or 0) / 100),
        "total_buy_signals": total_samples // 2, "total_sell_signals": total_samples - total_samples // 2,
        "last_win_rate": last_wr, "average_win_rate_over_runs": avg_wr,
        "average_strength": None, "average_reliability": None, "last_updated": "2026-07-27T00:00:00Z",
    }


def _run_log_entry(indicator_win_rates):
    """indicator_win_rates: {name: win_rate | None (None = insufficient sample)}"""
    per_indicator = {}
    for name, wr in indicator_win_rates.items():
        if wr is None:
            per_indicator[name] = {"average_win_rate_where_sufficient": None,
                                    "combinations_with_sufficient_sample": 0}
        else:
            per_indicator[name] = {"average_win_rate_where_sufficient": wr,
                                    "combinations_with_sufficient_sample": 3}
    return {"per_indicator": per_indicator}


print("=" * 70)
print("PHASE 10.4 GOAL 2 — Adaptive AI Calibration")
print("=" * 70)

# ─── 1. Validation-history-based functions ──────────────────────────────────
print("\n[1] Validation-history-based functions (no df)")

history_improving = {
    "rolling_stats": {
        "bb": _rolling_stats(100, 55.0, 62.0),   # last well above average -> improving
        "rsi_div": _rolling_stats(100, 55.0, 48.0),  # last well below average -> degrading
        "cci": _rolling_stats(100, 55.0, 55.5),  # inside band -> stable
        "thin": _rolling_stats(5, 60.0, 60.0),   # below min_samples -> no_data
    },
    "run_log": [],
}
vt = ac.compute_validation_trend(history_improving)
check("validation_trend: improving indicator classified correctly", vt["bb"]["trend"] == "improving")
check("validation_trend: degrading indicator classified correctly", vt["rsi_div"]["trend"] == "degrading")
check("validation_trend: in-band indicator classified stable", vt["cci"]["trend"] == "stable")
check("validation_trend: thin-sample indicator -> no_data, confidence none",
      vt["thin"]["trend"] == "no_data" and vt["thin"]["confidence"] == "none")

check("validation_trend: empty/None history -> empty dict, no crash",
      ac.compute_validation_trend(None) == {} and ac.compute_validation_trend({}) == {})

# Indicator stability + accuracy trend from run_log (oldest-first internally;
# store convention is most-recent-first, so index 0 below = most recent).
run_log_stable = [
    _run_log_entry({"bb": 61.0}), _run_log_entry({"bb": 60.0}), _run_log_entry({"bb": 59.0}),
    _run_log_entry({"bb": 60.5}),
]
run_log_unstable = [
    _run_log_entry({"noisy": 30.0}), _run_log_entry({"noisy": 80.0}), _run_log_entry({"noisy": 20.0}),
    _run_log_entry({"noisy": 75.0}),
]
history_stability = {
    "rolling_stats": {"bb": _rolling_stats(100, 60.0, 61.0), "noisy": _rolling_stats(100, 51.0, 75.0),
                       "no_runs": _rolling_stats(100, 50.0, 50.0)},
    "run_log": run_log_stable + run_log_unstable,
}
istab = ac.compute_indicator_stability(history_stability)
check("indicator_stability: consistent series -> stable", istab["bb"]["stability"] == "stable")
check("indicator_stability: volatile series -> unstable", istab["noisy"]["stability"] == "unstable")
check("indicator_stability: rolling_stats entry with zero run_log rows -> no_data",
      istab["no_runs"]["stability"] == "no_data" and istab["no_runs"]["sample_run_count"] == 0)

acc_trend_up = ac.compute_accuracy_trend({
    "run_log": [  # most-recent-first; second half (oldest->newest) should show improvement
        _run_log_entry({"a": 70.0}), _run_log_entry({"a": 68.0}), _run_log_entry({"a": 66.0}),
        _run_log_entry({"a": 50.0}), _run_log_entry({"a": 48.0}), _run_log_entry({"a": 46.0}),
    ]
})
check("accuracy_trend: rising overall win rate classified improving", acc_trend_up["trend"] == "improving")
check("accuracy_trend: sample_run_count matches usable run_log entries", acc_trend_up["sample_run_count"] == 6)

check("accuracy_trend: empty run_log -> no_data, no crash",
      ac.compute_accuracy_trend({"run_log": []})["trend"] == "no_data")
check("accuracy_trend: below min_runs -> no_data",
      ac.compute_accuracy_trend({"run_log": [_run_log_entry({"a": 60.0})]}, min_runs=3)["trend"] == "no_data")

# Weight stability from a recommendation_log (most-recent-first).
learning_history = {
    "recommendation_log": [
        {"recommended_weights": {"bb": 8.0, "erratic": 15.0}},
        {"recommended_weights": {"bb": 8.2, "erratic": 3.0}},
        {"recommended_weights": {"bb": 7.9, "erratic": 18.0}},
        {"recommended_weights": {"bb": 8.1, "erratic": 2.0}},
    ]
}
wstab = ac.compute_weight_stability(learning_history)
check("weight_stability: consistently-recommended weight -> stable", wstab["bb"]["stability"] == "stable")
check("weight_stability: erratically-recommended weight -> unstable", wstab["erratic"]["stability"] == "unstable")
check("weight_stability: empty/None learning_history -> empty dict, no crash",
      ac.compute_weight_stability(None) == {} and ac.compute_weight_stability({}) == {})

# ─── 2. Group calibration (asset / timeframe) ───────────────────────────────
print("\n[2] Asset / timeframe calibration")

asset_stats = {
    "EURUSD_otc": {"bb": _rolling_stats(100, 65.0, 65.0), "rsi_div": _rolling_stats(100, 63.0, 63.0)},
    "GBPUSD_otc": {"bb": _rolling_stats(100, 48.0, 48.0), "rsi_div": _rolling_stats(100, 50.0, 50.0)},
    "NEVER_TRADED_otc": {},  # analogous to "Unknown regime" — never recorded, must not be guessed
}
asset_cal = ac.compute_asset_calibration(asset_stats)
check("asset_calibration: higher win-rate asset scores higher",
      asset_cal["groups"]["EURUSD_otc"]["score"] > asset_cal["groups"]["GBPUSD_otc"]["score"])
check("asset_calibration: ranking puts the best asset first",
      asset_cal["ranking"][0] == "EURUSD_otc")
check("asset_calibration: never-recorded asset -> score None, confidence none, not guessed",
      asset_cal["groups"]["NEVER_TRADED_otc"]["score"] is None and
      asset_cal["groups"]["NEVER_TRADED_otc"]["confidence"] == "none")
check("asset_calibration: never-recorded asset excluded from ranking",
      "NEVER_TRADED_otc" not in asset_cal["ranking"])

timeframe_stats = {
    "5m": {"bb": _rolling_stats(100, 62.0, 62.0)},
    "1m": {"bb": _rolling_stats(100, 51.0, 51.0)},
}
tf_cal = ac.compute_timeframe_calibration(timeframe_stats)
check("timeframe_calibration: ranking puts the best timeframe first", tf_cal["ranking"][0] == "5m")

check("asset_calibration: empty/None input -> empty groups, no crash",
      ac.compute_asset_calibration(None)["groups"] == {} and ac.compute_asset_calibration({})["ranking"] == [])

# ─── 3. Walk-forward-based functions (require a df) ─────────────────────────
print("\n[3] Walk-forward-based calibration (df required)")

trending = make_trending_df(300)
cal = ac.compute_confidence_calibration(trending, train_size=100, test_size=25, lookahead=4)
check("confidence_calibration: not insufficient_data on a long trending df", cal["insufficient_data"] is False)
check("confidence_calibration: bucket sample sizes sum to total_samples",
      sum(b["sample_size"] for b in cal["buckets"].values()) == cal["total_samples"])
check("confidence_calibration: calibration_error is a non-negative number",
      cal["calibration_error"] is None or cal["calibration_error"] >= 0.0)

scaling = ac.compute_confidence_scaling(cal)
check("confidence_scaling: scaling_table has one entry per bucket",
      set(scaling["scaling_table"].keys()) == set(cal["buckets"].keys()))
sample_key = next(iter(cal["buckets"].keys()))
sample_win_rate = cal["buckets"][sample_key]["win_rate"]
lo = int(sample_key.split("-")[0])
applied = ac.apply_confidence_scaling(lo + 1, scaling["scaling_table"])
check("apply_confidence_scaling: maps a raw strength into its bucket's win_rate",
      applied == sample_win_rate)

too_short = make_trending_df(30)
cal_short = ac.compute_confidence_calibration(too_short, train_size=100, test_size=25)
check("confidence_calibration: too-short df -> insufficient_data True, no crash",
      cal_short["insufficient_data"] is True and cal_short["buckets"] == {})

thr = ac.optimize_threshold(trending, train_size=100, test_size=25, lookahead=4, min_sample_size=5)
check("optimize_threshold: evaluated one entry per candidate threshold",
      len(thr["evaluated"]) == len(ac.DEFAULT_THRESHOLD_CANDIDATES))
if not thr["insufficient_data"]:
    check("optimize_threshold: best entry meets the minimum sample size",
          thr["best"]["total_signals"] >= 5)
    check("optimize_threshold: best entry's threshold is one of the candidates",
          thr["best"]["threshold"] in ac.DEFAULT_THRESHOLD_CANDIDATES)

thr_impossible = ac.optimize_threshold(trending, train_size=100, test_size=25, min_sample_size=10 ** 9)
check("optimize_threshold: impossible sample floor -> insufficient_data True, no crash",
      thr_impossible["insufficient_data"] is True and thr_impossible["best"] is None)

rolling_cal = ac.compute_rolling_calibration(trending, train_size=100, test_size=25, lookahead=4)
check("compute_rolling_calibration: matches compute_confidence_calibration(mode='rolling')",
      rolling_cal == ac.compute_confidence_calibration(trending, mode="rolling", train_size=100,
                                                         test_size=25, lookahead=4))

try:
    list(ac._iter_window_signals(trending, "bogus", 100, 25, None, 4, None))
    check("_iter_window_signals: invalid mode raises ValueError", False)
except ValueError:
    check("_iter_window_signals: invalid mode raises ValueError", True)

# ─── 4. build_calibration_report() ──────────────────────────────────────────
print("\n[4] build_calibration_report()")

report_no_df = ac.build_calibration_report(
    validation_history=history_improving, learning_history=learning_history,
    asset_stats=asset_stats, timeframe_stats=timeframe_stats,
)
check("build_calibration_report: df-based sections are explicitly None without a df",
      report_no_df["confidence_calibration"] is None and
      report_no_df["confidence_scaling"] is None and
      report_no_df["threshold_optimization"] is None)
check("build_calibration_report: validation-history sections populated without a df",
      report_no_df["validation_trend"]["bb"]["trend"] == "improving")

report_with_df = ac.build_calibration_report(
    validation_history=history_improving, learning_history=learning_history,
    asset_stats=asset_stats, timeframe_stats=timeframe_stats,
    df=trending, walk_forward_kwargs={"train_size": 100, "test_size": 25, "lookahead": 4},
)
check("build_calibration_report: df-based sections populated when a df is given",
      report_with_df["confidence_calibration"] is not None and
      report_with_df["threshold_optimization"] is not None)

report_empty = ac.build_calibration_report()
check("build_calibration_report: fully empty inputs -> no crash, empty sub-dicts",
      report_empty["validation_trend"] == {} and report_empty["asset_calibration"]["groups"] == {})

# ─── 5. generate_calibration_recommendations() ──────────────────────────────
print("\n[5] generate_calibration_recommendations()")

recs = ac.generate_calibration_recommendations(report_no_df)
check("recommendations: every entry has reason/evidence/confidence/severity",
      all({"reason", "evidence", "confidence", "severity", "action"} <= set(r.keys()) for r in recs))
check("recommendations: improving indicator -> increase_indicator_weight present",
      any(r["action"] == "increase_indicator_weight" for r in recs))
check("recommendations: degrading indicator -> decrease_indicator_weight present",
      any(r["action"] == "decrease_indicator_weight" for r in recs))
check("recommendations: best asset -> recommend_best_asset present",
      any(r["action"] == "recommend_best_asset" and r["evidence"]["asset"] == "EURUSD_otc" for r in recs))
check("recommendations: best timeframe -> recommend_best_timeframe present",
      any(r["action"] == "recommend_best_timeframe" and r["evidence"]["timeframe"] == "5m" for r in recs))

recs_unstable = ac.generate_calibration_recommendations(ac.build_calibration_report(
    validation_history=history_stability, learning_history=learning_history,
))
check("recommendations: unstable indicator -> ignore_unstable_indicator present",
      any(r["action"] == "ignore_unstable_indicator" and "noisy" in r["reason"] for r in recs_unstable))
check("recommendations: erratic weight -> decrease_indicator_weight (weight-stability rule) present",
      any(r["action"] == "decrease_indicator_weight" and "erratic" in r["reason"] for r in recs_unstable))

check("recommendations: fully empty report -> empty list, no crash",
      ac.generate_calibration_recommendations(ac.build_calibration_report()) == [])

# ─── 6. Determinism ───────────────────────────────────────────────────────────
print("\n[6] Determinism")

report_a = ac.build_calibration_report(validation_history=history_improving, learning_history=learning_history,
                                        asset_stats=asset_stats, timeframe_stats=timeframe_stats,
                                        df=trending, walk_forward_kwargs={"train_size": 100, "test_size": 25})
report_b = ac.build_calibration_report(validation_history=history_improving, learning_history=learning_history,
                                        asset_stats=asset_stats, timeframe_stats=timeframe_stats,
                                        df=trending, walk_forward_kwargs={"train_size": 100, "test_size": 25})
same = {k: v for k, v in report_a.items() if k != "generated_at"}
same_b = {k: v for k, v in report_b.items() if k != "generated_at"}
check("identical input -> identical report across repeated calls (excluding timestamp)", same == same_b)
check("identical input -> identical recommendations across repeated calls",
      ac.generate_calibration_recommendations(report_a) == ac.generate_calibration_recommendations(report_b))

# ─── 7. Off-limits-file regression safety ───────────────────────────────────
print("\n[7] Off-limits-file regression safety (source inspection)")

_ANALYZER_PY = os.path.join(_MARKET_ANALYZER, "analyzer.py")
_BACKTEST_PY = os.path.join(_MARKET_ANALYZER, "backtest.py")
_WALK_FORWARD_PY = os.path.join(_MARKET_ANALYZER, "walk_forward.py")
_SCANNER_PY = os.path.join(_WEBAPP, "scanner.py")
_LEARNING_PY = os.path.join(_WEBAPP, "learning_engine.py")
_REGISTRY_PY = os.path.join(_WEBAPP, "indicator_registry.py")
_APP_PY = os.path.join(_WEBAPP, "app.py")

for label, path in [("analyzer.py", _ANALYZER_PY), ("backtest.py", _BACKTEST_PY),
                     ("walk_forward.py", _WALK_FORWARD_PY),
                     ("webapp/scanner.py", _SCANNER_PY),
                     ("webapp/learning_engine.py", _LEARNING_PY),
                     ("webapp/indicator_registry.py", _REGISTRY_PY)]:
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            src = f.read()
        check(f"{label}: no reference to adaptive_calibration (not modified, not wired in)",
              "adaptive_calibration" not in src)
    else:
        check(f"{label}: file exists for source check", False)

with open(_APP_PY, "r", encoding="utf-8") as f:
    app_src = f.read()
check("app.py: new adaptive_calibration import present",
      "from adaptive_calibration import" in app_src)
check("app.py: all 4 new /api/calibration/* routes present",
      all(route in app_src for route in [
          '"/api/calibration/report"', '"/api/calibration/status"',
          '"/api/calibration/history"', '"/api/calibration/recommendations"',
      ]))
check("app.py: pre-existing /api/ai/* routes still present verbatim (untouched)",
      all(route in app_src for route in [
          '"/api/ai/health"', '"/api/ai/status"', '"/api/ai/statistics"', '"/api/ai/explain"',
      ]))
check("app.py: pre-existing /api/learning/* and /api/validation/* routes still present (untouched)",
      '"/api/learning/recommendations"' in app_src and '"/api/validation/history"' in app_src)

check("backtest.py: backtest_factor_accuracy still present and callable",
      hasattr(backtest, "backtest_factor_accuracy"))
check("walk_forward.py: run_walk_forward still present and callable (Goal 1 untouched)",
      hasattr(wf, "run_walk_forward"))

# ─── Summary ─────────────────────────────────────────────────────────────────
print("\n" + "=" * 70)
print(f"RESULTS: {passed} passed, {failed} failed (of {passed + failed})")
print("=" * 70)

if failed:
    sys.exit(1)
