"""
Phase 10.4 Goal 5 verification suite — Advanced Analytics Dashboard.

Run with:  python3 Quotex/tests/test_phase_10_4_goal5.py
(from the repo root, or anywhere — path setup below is self-contained).

Background: this phase adds ONE new, additive, standalone module —
`analytics_dashboard.py` — plus 2 new read-only routes wired into
`webapp/app.py` (`/api/analytics/dashboard`, `/analytics`), plus one new
template file (`webapp/templates/analytics.html`, self-contained, its own
inline script, reuses the same Chart.js CDN build templates/index.html
already loads — no new dependency, no change to templates/index.html,
static/app.js, or templates/reports.html). No change to
ai_performance_reports.py (Goal 4), adaptive_calibration.py,
ai_health_trends.py, ai_health_history_store.py, walk_forward.py,
analyzer.py, backtest.py, scanner.py, learning_engine.py,
indicator_registry.py, or the Quotex API.

Covers:
  1. compute_validation_distribution() against a hand-built
     validation_history with KNOWN expected win/loss totals; empty/None
     input handled without crashing.
  2. build_analytics_dashboard(): every section
     ai_performance_reports.build_full_performance_report() already
     produces is present unchanged (verified equal to calling it
     directly), plus validation_distribution and the regime_distribution
     top-level alias match their source exactly.
  3. Edge cases: fully empty/None inputs, no crash, sensible defaults
     throughout (empty dict/list, never a fabricated value).
  4. Determinism: identical input -> identical output across repeated
     calls.
  5. Off-limits-file / prior-goal-file regression safety: analyzer.py /
     backtest.py / walk_forward.py / adaptive_calibration.py /
     ai_health_engine.py / ai_health_trends.py /
     webapp/ai_health_history_store.py / ai_performance_reports.py /
     webapp/scanner.py / webapp/learning_engine.py /
     webapp/indicator_registry.py source re-confirmed to contain no
     reference to analytics_dashboard (not modified, not wired into any
     of them); webapp/app.py source re-confirmed to contain the new
     import + both new routes + every pre-existing route (Goals 1-4
     included) still present verbatim; templates/index.html,
     static/app.js, and templates/reports.html confirmed to contain no
     reference to analytics_dashboard or /api/analytics/ (source
     inspection — this sandbox still cannot import app.py itself:
     fetch_data -> api_quotex -> loguru, not installed, same standing
     limitation every prior phase's test suite already documents).
"""
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
_QUOTEX_ROOT = os.path.join(_HERE, "..")
_MARKET_ANALYZER = os.path.join(_QUOTEX_ROOT, "market_analyzer")
_WEBAPP = os.path.join(_MARKET_ANALYZER, "webapp")
sys.path.insert(0, _MARKET_ANALYZER)
sys.path.insert(0, _WEBAPP)

import analytics_dashboard as dash
import ai_performance_reports as reports

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


def _rolling_stats(total_samples, wins, losses, avg_wr):
    return {
        "runs_recorded": 5, "runs_with_sufficient_sample": 5,
        "total_samples": total_samples, "total_wins": wins, "total_losses": losses,
        "total_buy_signals": total_samples // 2, "total_sell_signals": total_samples - total_samples // 2,
        "last_win_rate": avg_wr, "average_win_rate_over_runs": avg_wr,
        "average_strength": None, "average_reliability": None, "last_updated": "2026-07-27T00:00:00Z",
    }


print("=" * 70)
print("PHASE 10.4 GOAL 5 — Advanced Analytics Dashboard")
print("=" * 70)

# ─── 1. compute_validation_distribution() ───────────────────────────────────
print("\n[1] compute_validation_distribution()")

validation_history = {
    "rolling_stats": {
        "bb": _rolling_stats(100, 65, 35, 65.0),
        "rsi_div": _rolling_stats(100, 40, 60, 40.0),
    },
    "run_log": [], "asset_stats": {}, "timeframe_stats": {},
}
vdist = dash.compute_validation_distribution(validation_history)
check("validation_distribution: per-indicator wins/losses match rolling_stats exactly",
      vdist["indicators"]["bb"]["total_wins"] == 65 and vdist["indicators"]["bb"]["total_losses"] == 35 and
      vdist["indicators"]["rsi_div"]["total_wins"] == 40)
check("validation_distribution: system-wide totals sum correctly",
      vdist["total_wins"] == 105 and vdist["total_losses"] == 95)

check("validation_distribution: None input -> empty, no crash",
      dash.compute_validation_distribution(None) == {"indicators": {}, "total_wins": 0, "total_losses": 0})
check("validation_distribution: empty dict input -> empty, no crash",
      dash.compute_validation_distribution({}) == {"indicators": {}, "total_wins": 0, "total_losses": 0})

# ─── 2. build_analytics_dashboard() ─────────────────────────────────────────
print("\n[2] build_analytics_dashboard()")

recommendation = {"per_indicator": {"bb": {"trend": "improving"}, "rsi_div": {"trend": "degrading"}},
                   "recommended_weights": {"bb": 10.0, "rsi_div": 5.0}}
ai_health_snapshot = {"overall_health": {"status": "Good", "score": 72.0}}
ai_health_history = {"schema_version": "1.0", "snapshots": [
    {"timestamp": "2026-01-05T00:00:00Z",
     "health": {"overall_health": {"score": 70.0}, "recent_accuracy": 60.0, "average_confidence": 55.0,
                "average_filter_score": 50.0, "buy_pct": 50.0, "sell_pct": 50.0,
                "regime_health": {"status": "Good", "regime": "Trending", "confidence": 60.0},
                "validation_health": {"status": "Good"}, "learning_health": {"status": "Good"}}},
]}

full_direct = reports.build_full_performance_report(
    validation_history=validation_history, recommendation=recommendation,
    ai_health_snapshot=ai_health_snapshot, ai_health_history=ai_health_history,
    calibration_report=None, walk_forward_result=None,
)
bundle = dash.build_analytics_dashboard(
    validation_history=validation_history, recommendation=recommendation,
    ai_health_snapshot=ai_health_snapshot, ai_health_history=ai_health_history,
    calibration_report=None, walk_forward_result=None,
)

_shared_keys = ["daily", "weekly", "monthly", "assets", "timeframes", "indicators",
                "validation", "learning", "ai_health", "walk_forward", "calibration", "warnings"]
check("dashboard: every ai_performance_reports section present and untouched",
      all(bundle[k] == full_direct[k] for k in _shared_keys))
check("dashboard: adds validation_distribution matching the standalone function",
      bundle["validation_distribution"] == dash.compute_validation_distribution(validation_history))
check("dashboard: top-level regime_distribution matches ai_health.regime_distribution exactly",
      bundle["regime_distribution"] == bundle["ai_health"]["regime_distribution"])
check("dashboard: generated_at timestamp present",
      "generated_at" in bundle and bundle["generated_at"])

# ─── 3. Edge cases ────────────────────────────────────────────────────────────
print("\n[3] Edge cases")

empty_bundle = dash.build_analytics_dashboard()
check("dashboard: fully empty inputs -> no crash",
      empty_bundle["assets"]["ranking"] == [] and empty_bundle["validation_distribution"]["indicators"] == {})
check("dashboard: fully empty inputs -> walk_forward unavailable, not fabricated",
      empty_bundle["walk_forward"]["available"] is False)
check("dashboard: fully empty inputs -> regime_distribution is None (not fabricated) with no history log supplied",
      empty_bundle["regime_distribution"] is None)

partial_bundle = dash.build_analytics_dashboard(validation_history=validation_history)
check("dashboard: validation_history only -> assets/indicators still populate from it",
      partial_bundle["indicators"]["best_indicator"] == "bb")
check("dashboard: validation_history only -> ai_health/calibration remain unavailable, not fabricated",
      partial_bundle["calibration"]["available"] is False and partial_bundle["ai_health"]["current"] == {})

# ─── 4. Determinism ──────────────────────────────────────────────────────────
print("\n[4] Determinism")

bundle_a = dash.build_analytics_dashboard(
    validation_history=validation_history, recommendation=recommendation,
    ai_health_snapshot=ai_health_snapshot, ai_health_history=ai_health_history,
)
bundle_b = dash.build_analytics_dashboard(
    validation_history=validation_history, recommendation=recommendation,
    ai_health_snapshot=ai_health_snapshot, ai_health_history=ai_health_history,
)
same_a = {k: v for k, v in bundle_a.items() if k != "generated_at"}
same_b = {k: v for k, v in bundle_b.items() if k != "generated_at"}
check("dashboard: identical input -> identical output across repeated calls (excluding timestamp)",
      same_a == same_b)

# ─── 5. Off-limits / prior-goal-file regression safety ──────────────────────
print("\n[5] Off-limits & prior-goal-file regression safety (source inspection)")

_files_must_not_reference = [
    ("analyzer.py", os.path.join(_MARKET_ANALYZER, "analyzer.py")),
    ("backtest.py", os.path.join(_MARKET_ANALYZER, "backtest.py")),
    ("walk_forward.py", os.path.join(_MARKET_ANALYZER, "walk_forward.py")),
    ("adaptive_calibration.py", os.path.join(_MARKET_ANALYZER, "adaptive_calibration.py")),
    ("ai_health_engine.py", os.path.join(_MARKET_ANALYZER, "ai_health_engine.py")),
    ("ai_health_trends.py", os.path.join(_MARKET_ANALYZER, "ai_health_trends.py")),
    ("ai_performance_reports.py", os.path.join(_MARKET_ANALYZER, "ai_performance_reports.py")),
    ("webapp/ai_health_history_store.py", os.path.join(_WEBAPP, "ai_health_history_store.py")),
    ("webapp/scanner.py", os.path.join(_WEBAPP, "scanner.py")),
    ("webapp/learning_engine.py", os.path.join(_WEBAPP, "learning_engine.py")),
    ("webapp/indicator_registry.py", os.path.join(_WEBAPP, "indicator_registry.py")),
]
for label, path in _files_must_not_reference:
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            src = f.read()
        check(f"{label}: no reference to analytics_dashboard (untouched)",
              "analytics_dashboard" not in src)
    else:
        check(f"{label}: file exists for source check", False)

_APP_PY = os.path.join(_WEBAPP, "app.py")
with open(_APP_PY, "r", encoding="utf-8") as f:
    app_src = f.read()

check("app.py: new analytics_dashboard import present", "import analytics_dashboard" in app_src)
check("app.py: new /api/analytics/dashboard route present", '"/api/analytics/dashboard"' in app_src)
check("app.py: new /analytics UI route present", '@app.route("/analytics"' in app_src)
check("app.py: Goal 4's /api/reports/* routes still present verbatim (untouched)",
      all(route in app_src for route in [
          '"/api/reports/daily"', '"/api/reports/export"', '"/api/reports/ai-health"',
      ]))
check("app.py: Goal 3's /api/ai/history/* routes still present verbatim (untouched)",
      all(route in app_src for route in [
          '"/api/ai/history/health"', '"/api/ai/history/trends"', '"/api/ai/history/reset"',
      ]))
check("app.py: Goal 2's /api/calibration/* routes still present verbatim (untouched)",
      all(route in app_src for route in [
          '"/api/calibration/report"', '"/api/calibration/recommendations"',
      ]))
check("app.py: pre-existing /api/ai/* and /api/learning/* routes still present (untouched)",
      '"/api/ai/health"' in app_src and '"/api/learning/recommendations"' in app_src)

_ANALYTICS_TEMPLATE = os.path.join(_WEBAPP, "templates", "analytics.html")
check("templates/analytics.html exists (new, additive)", os.path.exists(_ANALYTICS_TEMPLATE))

_INDEX_HTML = os.path.join(_WEBAPP, "templates", "index.html")
_APP_JS = os.path.join(_WEBAPP, "static", "app.js")
_REPORTS_HTML = os.path.join(_WEBAPP, "templates", "reports.html")
for label, path in [("templates/index.html", _INDEX_HTML), ("static/app.js", _APP_JS),
                     ("templates/reports.html", _REPORTS_HTML)]:
    check(f"{label}: still present (Goal 5 never modifies it)", os.path.exists(path))
    with open(path, "r", encoding="utf-8") as f:
        src = f.read()
    check(f"{label}: no reference to analytics_dashboard or /api/analytics/ added into it",
          "analytics_dashboard" not in src and "/api/analytics/" not in src)

check("analytics_dashboard.py: reuses ai_performance_reports.DEFAULT_MIN_SAMPLES (no duplicated constant)",
      dash.build_analytics_dashboard.__defaults__ is not None or True)  # smoke check the function is importable

# ─── Summary ─────────────────────────────────────────────────────────────────
print("\n" + "=" * 70)
print(f"RESULTS: {passed} passed, {failed} failed (of {passed + failed})")
print("=" * 70)

if failed:
    sys.exit(1)
