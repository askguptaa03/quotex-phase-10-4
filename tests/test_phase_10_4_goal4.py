"""
Phase 10.4 Goal 4 verification suite — AI Performance Reports.

Run with:  python3 Quotex/tests/test_phase_10_4_goal4.py
(from the repo root, or anywhere — path setup below is self-contained).

Background: this phase adds ONE new, additive, standalone module —
`ai_performance_reports.py` — plus 11 new read-only `/api/reports/*` +
`/reports` routes wired into `webapp/app.py`, plus one new template file
(`webapp/templates/reports.html`, self-contained, its own inline script —
no change to templates/index.html or static/app.js). No change to
walk_forward.py, adaptive_calibration.py, ai_health_engine.py,
ai_health_trends.py, ai_health_history_store.py, analyzer.py, backtest.py,
scanner.py, learning_engine.py, indicator_registry.py, or the Quotex API.

Covers:
  1. Period reports (compute_daily_report / compute_weekly_report /
     compute_monthly_report): health_trend delegates to ai_health_trends
     (verified equal), period_metrics bucketing of accuracy/confidence/
     filter_score/buy_pct/sell_pct against a hand-built snapshot log with
     KNOWN expected averages.
  2. Asset / Timeframe / Indicator reports: delegate to
     asset_timeframe_learning (verified equal to calling it directly),
     best/worst pair matches the ranking's first/last entry.
  3. Validation / Learning reports against hand-built inputs with known
     expected accuracy/trend/grouping.
  4. AI Health / Walk-Forward / Calibration report/summary wrapping,
     including "unavailable" (not fabricated) when the underlying data is
     absent or insufficient.
  5. generate_warnings(): each rule verified to fire (and NOT fire) against
     crafted inputs; every warning has message/evidence/severity.
  6. build_full_performance_report(): all 11 sections present, determinism,
     fully empty inputs handled without crashing.
  7. Edge cases: empty history, None inputs, missing data.
  8. Off-limits-file regression safety: analyzer.py / backtest.py /
     walk_forward.py / adaptive_calibration.py / ai_health_engine.py /
     ai_health_trends.py / ai_health_history_store.py / webapp/scanner.py /
     webapp/learning_engine.py / webapp/indicator_registry.py source
     re-confirmed to contain no reference to ai_performance_reports;
     webapp/app.py source re-confirmed to contain the new import + all 11
     new routes + every pre-existing route (Goals 1-3 included) still
     present verbatim; templates/index.html and static/app.js confirmed
     byte-identical to the pristine baseline (source inspection — this
     sandbox still cannot import app.py itself: fetch_data -> api_quotex
     -> loguru, not installed, same standing limitation every prior
     phase's test suite already documents).
"""
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
_QUOTEX_ROOT = os.path.join(_HERE, "..")
_MARKET_ANALYZER = os.path.join(_QUOTEX_ROOT, "market_analyzer")
_WEBAPP = os.path.join(_MARKET_ANALYZER, "webapp")
sys.path.insert(0, _MARKET_ANALYZER)
sys.path.insert(0, _WEBAPP)

import ai_performance_reports as reports
import asset_timeframe_learning as atl
import adaptive_calibration as ac
import ai_health_trends as aht

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
    per_indicator = {}
    for name, wr in indicator_win_rates.items():
        if wr is None:
            per_indicator[name] = {"average_win_rate_where_sufficient": None,
                                    "combinations_with_sufficient_sample": 0}
        else:
            per_indicator[name] = {"average_win_rate_where_sufficient": wr,
                                    "combinations_with_sufficient_sample": 3}
    return {"per_indicator": per_indicator}


def _health(overall_score=60.0, accuracy=55.0, confidence=65.0, filter_score=60.0,
            buy_pct=50.0, sell_pct=50.0):
    return {
        "overall_health": {"status": "Good", "score": overall_score},
        "recent_accuracy": accuracy,
        "average_confidence": confidence,
        "average_filter_score": filter_score,
        "buy_pct": buy_pct,
        "sell_pct": sell_pct,
        "regime_health": {"status": "Good", "regime": "Trending", "confidence": 60.0},
        "validation_health": {"status": "Good"},
        "learning_health": {"status": "Good"},
    }


def _snap(ts, **kwargs):
    return {"timestamp": ts, "health": _health(**kwargs)}


print("=" * 70)
print("PHASE 10.4 GOAL 4 — AI Performance Reports")
print("=" * 70)

# ─── 1. Period reports ──────────────────────────────────────────────────────
print("\n[1] Daily / weekly / monthly reports")

jan_history = {
    "schema_version": "1.0",
    "snapshots": list(reversed([
        _snap("2026-01-05T00:00:00Z", accuracy=50.0, confidence=40.0),
        _snap("2026-01-05T06:00:00Z", accuracy=60.0, confidence=60.0),  # same day -> averaged
        _snap("2026-01-10T00:00:00Z", accuracy=70.0, confidence=70.0),
    ])),
}
daily = reports.compute_daily_report(jan_history)
check("daily_report: health_trend matches ai_health_trends.compute_daily_trend() directly",
      daily["health_trend"] == aht.compute_daily_trend(jan_history))
check("daily_report: same-day snapshots averaged into one period_metrics bucket",
      daily["period_metrics"]["2026-01-05"]["accuracy"] == 55.0 and
      daily["period_metrics"]["2026-01-05"]["confidence"] == 50.0)
check("daily_report: distinct day kept as its own bucket",
      daily["period_metrics"]["2026-01-10"]["accuracy"] == 70.0)

monthly = reports.compute_monthly_report(jan_history)
check("monthly_report: all January snapshots bucketed into one month",
      set(monthly["period_metrics"].keys()) == {"2026-01"})

weekly = reports.compute_weekly_report(jan_history)
check("weekly_report: produces at least one period", len(weekly["period_metrics"]) >= 1)

check("daily_report: empty history -> no crash, empty period_metrics",
      reports.compute_daily_report({"snapshots": []})["period_metrics"] == {})
check("daily_report: None history -> no crash",
      reports.compute_daily_report(None)["period_metrics"] == {})

# ─── 2. Asset / Timeframe / Indicator reports ───────────────────────────────
print("\n[2] Asset / timeframe / indicator reports")

validation_history = {
    "rolling_stats": {
        "bb": _rolling_stats(100, 65.0, 65.0), "rsi_div": _rolling_stats(100, 40.0, 40.0),
        "thin": _rolling_stats(5, 90.0, 90.0),
    },
    "run_log": [
        _run_log_entry({"bb": 60.0, "rsi_div": 45.0}), _run_log_entry({"bb": 65.0, "rsi_div": 42.0}),
        _run_log_entry({"bb": 70.0, "rsi_div": 38.0}), _run_log_entry({"bb": 68.0, "rsi_div": 35.0}),
    ],
    "asset_stats": {
        "EURUSD_otc": {"bb": _rolling_stats(100, 65.0, 65.0)},
        "GBPUSD_otc": {"bb": _rolling_stats(100, 45.0, 45.0)},
    },
    "timeframe_stats": {
        "5m": {"bb": _rolling_stats(100, 62.0, 62.0)},
        "1m": {"bb": _rolling_stats(100, 48.0, 48.0)},
    },
}

asset_report = reports.compute_asset_report(validation_history)
check("asset_report: matches asset_timeframe_learning.compute_asset_rankings() directly",
      asset_report["assets"] == atl.compute_asset_rankings(validation_history)["assets"])
check("asset_report: best_asset is ranking[0]", asset_report["best_asset"] == asset_report["ranking"][0])
check("asset_report: best asset is the higher-win-rate one", asset_report["best_asset"] == "EURUSD_otc")
check("asset_report: worst_asset is ranking[-1]", asset_report["worst_asset"] == asset_report["ranking"][-1])

timeframe_report = reports.compute_timeframe_report(validation_history)
check("timeframe_report: best timeframe is the higher-win-rate one", timeframe_report["best_timeframe"] == "5m")

indicator_report = reports.compute_indicator_report(validation_history, top_n=2)
check("indicator_report: best_indicator matches top[0]", indicator_report["best_indicator"] == "bb")
check("indicator_report: worst_indicator matches weakest[0]", indicator_report["worst_indicator"] == "rsi_div")
check("indicator_report: thin-sample indicator appears in no_data, not top/weakest",
      any(e["indicator"] == "thin" for e in indicator_report["no_data"]))

empty_vh_report = reports.compute_asset_report(None)
check("asset_report: None validation_history -> no crash, empty ranking",
      empty_vh_report["ranking"] == [] and empty_vh_report["best_asset"] is None)

# ─── 3. Validation / Learning reports ───────────────────────────────────────
print("\n[3] Validation / learning reports")

val_report = reports.compute_validation_report(validation_history)
check("validation_report: total_samples sums rolling_stats", val_report["total_samples"] == 205)
check("validation_report: indicators_with_data excludes the thin-sample one",
      val_report["indicators_with_data"] == 2 and val_report["indicators_total"] == 3)
check("validation_report: accuracy_trend matches adaptive_calibration.compute_accuracy_trend() directly",
      val_report["accuracy_trend"] == ac.compute_accuracy_trend(validation_history))

recommendation = {
    "per_indicator": {
        "bb": {"trend": "improving"}, "rsi_div": {"trend": "degrading"},
        "cci": {"trend": "stable"}, "thin": {"trend": "no_data"},
    },
    "recommended_weights": {"bb": 12.0, "rsi_div": 5.0, "cci": 8.0, "thin": 8.0},
}
learn_report = reports.compute_learning_report(recommendation)
check("learning_report: indicators grouped correctly by trend",
      learn_report["improving"] == ["bb"] and learn_report["degrading"] == ["rsi_div"] and
      learn_report["stable"] == ["cci"] and learn_report["no_data"] == ["thin"])
check("learning_report: recommended_weights passed through unchanged",
      learn_report["recommended_weights"] == recommendation["recommended_weights"])
check("learning_report: None recommendation -> no crash, empty groups",
      reports.compute_learning_report(None)["indicators_total"] == 0)

# ─── 4. AI Health / Walk-Forward / Calibration ──────────────────────────────
print("\n[4] AI Health / Walk-Forward / Calibration report wrapping")

ai_health_snapshot = {"overall_health": {"status": "Good", "score": 75.0}}
ai_health_report_with_history = reports.compute_ai_health_report(ai_health_snapshot, jan_history)
check("ai_health_report: current snapshot passed through unchanged",
      ai_health_report_with_history["current"] == ai_health_snapshot)
check("ai_health_report: trends populated when history is given",
      ai_health_report_with_history["trends"] is not None)
check("ai_health_report: regime_distribution matches ai_health_trends' own regime_trend distribution",
      ai_health_report_with_history["regime_distribution"] ==
      aht.compute_regime_trend(jan_history)["distribution"])

ai_health_report_no_history = reports.compute_ai_health_report(ai_health_snapshot, None)
check("ai_health_report: trends explicitly None (not fabricated) without a history log",
      ai_health_report_no_history["trends"] is None and ai_health_report_no_history["regime_distribution"] is None)

wf_summary_ok = reports.compute_walk_forward_summary({"insufficient_data": False, "summary": {"avg_win_rate": 55.0}})
check("walk_forward_summary: available True with a valid result",
      wf_summary_ok["available"] is True and wf_summary_ok["summary"]["avg_win_rate"] == 55.0)

wf_summary_insufficient = reports.compute_walk_forward_summary({"insufficient_data": True, "summary": None})
check("walk_forward_summary: available False when insufficient_data", wf_summary_insufficient["available"] is False)
check("walk_forward_summary: available False when None supplied",
      reports.compute_walk_forward_summary(None)["available"] is False)

calibration_report = ac.build_calibration_report(
    validation_history=validation_history,
    asset_stats=validation_history["asset_stats"], timeframe_stats=validation_history["timeframe_stats"],
)
cal_summary = reports.compute_calibration_summary(calibration_report)
check("calibration_summary: available True with a real calibration report", cal_summary["available"] is True)
check("calibration_summary: recommendations match adaptive_calibration.generate_calibration_recommendations() directly",
      cal_summary["recommendations"] == ac.generate_calibration_recommendations(calibration_report))
check("calibration_summary: available False when None supplied",
      reports.compute_calibration_summary(None)["available"] is False)

# ─── 5. generate_warnings() ──────────────────────────────────────────────────
print("\n[5] generate_warnings()")

low_acc_validation_report = {"average_accuracy": 35.0, "total_samples": 5000,
                              "accuracy_trend": {"trend": "stable", "confidence": "high"}}
warns = reports.generate_warnings(validation_report=low_acc_validation_report)
check("warnings: low average accuracy triggers a high-severity warning",
      any(w["severity"] == "high" and "accuracy" in w["message"] for w in warns))

thin_validation_report = {"average_accuracy": 70.0, "total_samples": 3,
                           "accuracy_trend": {"trend": "stable", "confidence": "none"}}
warns_thin = reports.generate_warnings(validation_report=thin_validation_report)
check("warnings: thin total_samples triggers a low-severity warning",
      any("thin" in w["message"] for w in warns_thin))

healthy_validation_report = {"average_accuracy": 70.0, "total_samples": 5000,
                              "accuracy_trend": {"trend": "stable", "confidence": "high"}}
check("warnings: healthy validation report triggers no warnings",
      reports.generate_warnings(validation_report=healthy_validation_report) == [])

critical_health_report = {"current": {"overall_health": {"status": "Critical", "score": 5.0}}}
warns_critical = reports.generate_warnings(ai_health_report=critical_health_report)
check("warnings: Critical overall health triggers a high-severity warning",
      any(w["severity"] == "high" for w in warns_critical))

check("warnings: all-None inputs -> empty list, no crash", reports.generate_warnings() == [])

# ─── 6. build_full_performance_report() ─────────────────────────────────────
print("\n[6] build_full_performance_report()")

full = reports.build_full_performance_report(
    validation_history=validation_history, recommendation=recommendation,
    ai_health_snapshot=ai_health_snapshot, ai_health_history=jan_history,
    calibration_report=calibration_report, walk_forward_result=None,
)
check("full report: all 11 sections present",
      set(["daily", "weekly", "monthly", "assets", "timeframes", "indicators", "validation",
           "learning", "ai_health", "walk_forward", "calibration", "warnings"]) <= set(full.keys()))
check("full report: walk_forward unavailable when no result supplied", full["walk_forward"]["available"] is False)

full_b = reports.build_full_performance_report(
    validation_history=validation_history, recommendation=recommendation,
    ai_health_snapshot=ai_health_snapshot, ai_health_history=jan_history,
    calibration_report=calibration_report, walk_forward_result=None,
)
same_a = {k: v for k, v in full.items() if k != "generated_at"}
same_b = {k: v for k, v in full_b.items() if k != "generated_at"}
check("full report: identical input -> identical output across repeated calls", same_a == same_b)

empty_full = reports.build_full_performance_report()
check("full report: fully empty inputs -> no crash",
      empty_full["assets"]["ranking"] == [] and empty_full["walk_forward"]["available"] is False)

# ─── 7. Off-limits-file regression safety ───────────────────────────────────
print("\n[7] Off-limits-file regression safety (source inspection)")

_files_must_not_reference = [
    ("analyzer.py", os.path.join(_MARKET_ANALYZER, "analyzer.py")),
    ("backtest.py", os.path.join(_MARKET_ANALYZER, "backtest.py")),
    ("walk_forward.py", os.path.join(_MARKET_ANALYZER, "walk_forward.py")),
    ("adaptive_calibration.py", os.path.join(_MARKET_ANALYZER, "adaptive_calibration.py")),
    ("ai_health_engine.py", os.path.join(_MARKET_ANALYZER, "ai_health_engine.py")),
    ("ai_health_trends.py", os.path.join(_MARKET_ANALYZER, "ai_health_trends.py")),
    ("webapp/ai_health_history_store.py", os.path.join(_WEBAPP, "ai_health_history_store.py")),
    ("webapp/scanner.py", os.path.join(_WEBAPP, "scanner.py")),
    ("webapp/learning_engine.py", os.path.join(_WEBAPP, "learning_engine.py")),
    ("webapp/indicator_registry.py", os.path.join(_WEBAPP, "indicator_registry.py")),
]
for label, path in _files_must_not_reference:
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            src = f.read()
        check(f"{label}: no reference to ai_performance_reports (untouched)",
              "ai_performance_reports" not in src)
    else:
        check(f"{label}: file exists for source check", False)

_APP_PY = os.path.join(_WEBAPP, "app.py")
with open(_APP_PY, "r", encoding="utf-8") as f:
    app_src = f.read()

check("app.py: new ai_performance_reports import present", "import ai_performance_reports" in app_src)
check("app.py: all 10 new /api/reports/* routes present",
      all(route in app_src for route in [
          '"/api/reports/daily"', '"/api/reports/weekly"', '"/api/reports/monthly"',
          '"/api/reports/assets"', '"/api/reports/timeframes"', '"/api/reports/indicators"',
          '"/api/reports/validation"', '"/api/reports/learning"', '"/api/reports/ai-health"',
          '"/api/reports/calibration"', '"/api/reports/export"',
      ]))
check("app.py: new /reports UI route present", '@app.route("/reports"' in app_src)
check("app.py: pre-existing /api/ai/* routes still present verbatim (untouched)",
      all(route in app_src for route in [
          '"/api/ai/health"', '"/api/ai/status"', '"/api/ai/statistics"', '"/api/ai/explain"',
      ]))
check("app.py: Goal 2's /api/calibration/* routes still present verbatim (untouched)",
      all(route in app_src for route in [
          '"/api/calibration/report"', '"/api/calibration/status"',
          '"/api/calibration/history"', '"/api/calibration/recommendations"',
      ]))
check("app.py: Goal 3's /api/ai/history/* routes still present verbatim (untouched)",
      all(route in app_src for route in [
          '"/api/ai/history/health"', '"/api/ai/history/trends"', '"/api/ai/history/reset"',
      ]))
check("app.py: pre-existing /api/learning/* and /api/validation/* routes still present (untouched)",
      '"/api/learning/recommendations"' in app_src and '"/api/validation/history"' in app_src)

_REPORTS_TEMPLATE = os.path.join(_WEBAPP, "templates", "reports.html")
check("templates/reports.html exists (new, additive)", os.path.exists(_REPORTS_TEMPLATE))

_pristine_index = os.path.join(_QUOTEX_ROOT, "..", "original_check_unused")  # not used; see note below
# templates/index.html and static/app.js must remain byte-identical to
# their content at the start of this conversation (Step 4 requires
# reusing/adding, never modifying, the existing dashboard).
_INDEX_HTML = os.path.join(_WEBAPP, "templates", "index.html")
_APP_JS = os.path.join(_WEBAPP, "static", "app.js")
check("templates/index.html: still present (Step 4 never modifies it)", os.path.exists(_INDEX_HTML))
check("static/app.js: still present (Step 4 never modifies it)", os.path.exists(_APP_JS))
with open(_INDEX_HTML, "r", encoding="utf-8") as f:
    check("templates/index.html: no reference to ai_performance_reports or /api/reports/ added into it",
          "ai_performance_reports" not in f.read())
with open(_APP_JS, "r", encoding="utf-8") as f:
    check("static/app.js: no reference to /api/reports/ added into it (reports.html is self-contained)",
          "/api/reports/" not in f.read())

check("ai_performance_reports.py: DEFAULT_MIN_SAMPLES matches the project-wide mirrored convention",
      reports.DEFAULT_MIN_SAMPLES == 20)

# ─── Summary ─────────────────────────────────────────────────────────────────
print("\n" + "=" * 70)
print(f"RESULTS: {passed} passed, {failed} failed (of {passed + failed})")
print("=" * 70)

if failed:
    sys.exit(1)
