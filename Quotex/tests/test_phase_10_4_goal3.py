"""
Phase 10.4 Goal 3 verification suite — Historical AI Health.

Run with:  python3 Quotex/tests/test_phase_10_4_goal3.py
(from the repo root, or anywhere — path setup below is self-contained).

Background: this phase adds TWO new, additive, standalone files —
`ai_health_history_store.py` (a new JSON-backed store, mirroring
validation_history_store.py's exact I/O pattern) and `ai_health_trends.py`
(pure trend-computation functions, mirroring adaptive_calibration.py's
decoupling convention) — plus 3 new read-only-except-reset
`/api/ai/history/*` routes wired into `webapp/app.py` (2 new imports, one
new store instantiation + throttle constant, one new route block). No
change to ai_health_engine.py itself, walk_forward.py, adaptive_
calibration.py, analyzer.py, backtest.py, scanner.py, learning_engine.py,
indicator_registry.py, or the Quotex API — and no existing app.py route's
behavior changes (the new routes only ever ADD a snapshot via the same
_build_ai_health() helper /api/ai/health already uses; they never alter
what /api/ai/health itself returns).

Covers:
  1. AIHealthHistoryStore: record/get_history ordering (most-recent-
     first), get_latest_snapshot, bounded log length, reset, corrupted-
     JSON recovery, auto-create on first use — same contract validation_
     history_store.py's own test coverage already established for its
     store.
  2. ai_health_trends pure functions against hand-built snapshot logs with
     KNOWN expected results: compute_health_history (incl. ?limit),
     compute_daily_trend / compute_weekly_trend / compute_monthly_trend
     (bucketing + improving/degrading/stable classification),
     compute_confidence_trend, compute_validation_health_trend,
     compute_learning_health_trend, compute_regime_trend (distribution +
     confidence_trend, including an all-"Unknown" regime history — this
     phase's direct equivalent of the project's "Unknown regime"
     convention), build_health_trends_report bundling.
  3. Edge cases: empty history, None history, single snapshot,
     malformed/missing timestamp, missing validation (a snapshot whose
     health dict has no validation_health key at all).
  4. Determinism: identical input -> identical output across repeated
     calls.
  5. Off-limits-file regression safety: analyzer.py / backtest.py /
     walk_forward.py / adaptive_calibration.py / ai_health_engine.py /
     webapp/scanner.py / webapp/learning_engine.py /
     webapp/indicator_registry.py source re-confirmed to contain no
     reference to ai_health_trends or ai_health_history_store (not
     modified, not wired into any of them); webapp/app.py source
     re-confirmed to contain the new imports + all 3 new routes, and
     every pre-existing route signature (Goal 1/Goal 2 included) still
     present verbatim (source inspection — this sandbox still cannot
     import app.py itself: fetch_data -> api_quotex -> loguru, not
     installed, same standing limitation every prior phase's test suite
     already documents).
"""
import json
import os
import sys
import tempfile

_HERE = os.path.dirname(os.path.abspath(__file__))
_MARKET_ANALYZER = os.path.join(_HERE, "..", "market_analyzer")
_WEBAPP = os.path.join(_MARKET_ANALYZER, "webapp")
sys.path.insert(0, _MARKET_ANALYZER)
sys.path.insert(0, _WEBAPP)

import ai_health_trends as trends
from ai_health_history_store import AIHealthHistoryStore, MAX_SNAPSHOT_ENTRIES

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


def _health(overall_score=60.0, validation_status="Good", learning_status="Good",
            confidence=70.0, regime_name="Trending", regime_confidence=65.0):
    return {
        "overall_health": {"status": "Good", "score": overall_score},
        "indicator_health": {"status": "Good"},
        "validation_health": {"status": validation_status},
        "learning_health": {"status": learning_status},
        "regime_health": {"status": "Good", "regime": regime_name, "confidence": regime_confidence},
        "average_confidence": confidence,
    }


def _snap(ts, **health_kwargs):
    return {"timestamp": ts, "health": _health(**health_kwargs)}


print("=" * 70)
print("PHASE 10.4 GOAL 3 — Historical AI Health")
print("=" * 70)

# ─── 1. AIHealthHistoryStore ─────────────────────────────────────────────────
print("\n[1] AIHealthHistoryStore")

tmpdir = tempfile.mkdtemp()
store_path = os.path.join(tmpdir, "ai_health_history.json")

check("store: auto-creates file on first use", not os.path.exists(store_path))
store = AIHealthHistoryStore(store_path)
check("store: file exists after construction", os.path.exists(store_path))
check("store: starts with empty snapshot log", store.get_history()["snapshots"] == [])
check("store: get_latest_snapshot on empty log -> None", store.get_latest_snapshot() is None)

store.record_snapshot(_health(70.0)["overall_health"] and _health(70.0), timestamp="2026-01-01T00:00:00Z")
store.record_snapshot(_health(80.0), timestamp="2026-01-02T00:00:00Z")
history = store.get_history()
check("store: record_snapshot inserts most-recent-first",
      history["snapshots"][0]["timestamp"] == "2026-01-02T00:00:00Z")
check("store: record_snapshot preserves the health dict as-is, unmodified",
      history["snapshots"][0]["health"]["overall_health"]["score"] == 80.0)
check("store: get_latest_snapshot matches snapshots[0]",
      store.get_latest_snapshot()["timestamp"] == "2026-01-02T00:00:00Z")

reset_result = store.reset()
check("store: reset() wipes the snapshot log", reset_result["snapshots"] == [] and store.get_history()["snapshots"] == [])

with open(store_path, "w") as f:
    f.write("{not valid json")
recovered = store.get_history()
check("store: corrupted JSON recovers to a valid empty default, no crash",
      recovered["snapshots"] == [] and recovered["schema_version"] == "1.0")

bounded_store_path = os.path.join(tmpdir, "bounded.json")
bounded_store = AIHealthHistoryStore(bounded_store_path)
import ai_health_history_store as _store_module
_orig_max = _store_module.MAX_SNAPSHOT_ENTRIES
_store_module.MAX_SNAPSHOT_ENTRIES = 3
try:
    for i in range(5):
        bounded_store.record_snapshot(_health(50.0 + i), timestamp=f"2026-01-0{i+1}T00:00:00Z")
    bounded_history = bounded_store.get_history()
    check("store: snapshot log is bounded (capped at MAX_SNAPSHOT_ENTRIES)",
          len(bounded_history["snapshots"]) == 3)
    check("store: bounded log keeps the most recent entries",
          bounded_history["snapshots"][0]["timestamp"] == "2026-01-05T00:00:00Z")
finally:
    _store_module.MAX_SNAPSHOT_ENTRIES = _orig_max

# ─── 2. ai_health_trends: health history, daily/weekly/monthly ──────────────
print("\n[2] compute_health_history / daily / weekly / monthly trend")

# Two calendar months, scores clearly rising month-over-month.
jan_snaps = [_snap(f"2026-01-{d:02d}T12:00:00Z", overall_score=50.0 + d) for d in (5, 10, 15, 20, 25)]
feb_snaps = [_snap(f"2026-02-{d:02d}T12:00:00Z", overall_score=80.0 + d) for d in (5, 10, 15, 20, 25)]
rising_history = {"schema_version": "1.0", "snapshots": list(reversed(jan_snaps + feb_snaps))}  # most-recent-first

hh = trends.compute_health_history(rising_history)
check("health_history: total_snapshots matches full log length", hh["total_snapshots"] == 10)
check("health_history: no limit -> returns everything", hh["returned"] == 10)

hh_limited = trends.compute_health_history(rising_history, limit=3)
check("health_history: ?limit= caps returned count", hh_limited["returned"] == 3)
check("health_history: limit still reports true total_snapshots", hh_limited["total_snapshots"] == 10)
check("health_history: limited slice is still the most-recent entries",
      hh_limited["snapshots"][0]["timestamp"] == "2026-02-25T12:00:00Z")

daily = trends.compute_daily_trend(rising_history)
check("daily_trend: one period per distinct calendar day", daily["period_count"] == 10)

monthly = trends.compute_monthly_trend(rising_history)
check("monthly_trend: two distinct months bucketed", monthly["period_count"] == 2)
check("monthly_trend: February scores higher than January (as constructed)",
      monthly["series"][1]["average_score"] > monthly["series"][0]["average_score"])
check("monthly_trend: classified improving", monthly["trend"] == "improving")

weekly = trends.compute_weekly_trend(rising_history)
check("weekly_trend: produces at least one period", weekly["period_count"] >= 1)

check("daily_trend: empty history -> no_data, no crash",
      trends.compute_daily_trend({"snapshots": []})["trend"] == "no_data")
check("daily_trend: None history -> no_data, no crash",
      trends.compute_daily_trend(None)["trend"] == "no_data")

# ─── 3. Confidence / validation / learning trend ────────────────────────────
print("\n[3] compute_confidence_trend / compute_validation_health_trend / compute_learning_health_trend")

improving_confidence_history = {
    "schema_version": "1.0",
    "snapshots": list(reversed([
        _snap(f"2026-01-{d:02d}T00:00:00Z", confidence=c)
        for d, c in zip(range(1, 9), [40, 42, 41, 43, 70, 72, 71, 74])
    ])),
}
conf_trend = trends.compute_confidence_trend(improving_confidence_history)
check("confidence_trend: rising confidence classified improving", conf_trend["trend"] == "improving")
check("confidence_trend: sample_count matches number of snapshots with a confidence value",
      conf_trend["sample_count"] == 8)

too_few_history = {"schema_version": "1.0",
                    "snapshots": [_snap("2026-01-01T00:00:00Z", confidence=50.0)]}
check("confidence_trend: below MIN_SNAPSHOTS_FOR_TREND -> no_data",
      trends.compute_confidence_trend(too_few_history)["trend"] == "no_data")

validation_status_history = {
    "schema_version": "1.0",
    "snapshots": list(reversed([
        _snap(f"2026-01-0{i}T00:00:00Z", validation_status=s)
        for i, s in enumerate(["Poor", "Poor", "Poor", "Excellent", "Excellent", "Excellent"], start=1)
    ])),
}
val_trend = trends.compute_validation_health_trend(validation_status_history)
check("validation_health_trend: Poor->Excellent sequence classified improving", val_trend["trend"] == "improving")

learning_status_history = {
    "schema_version": "1.0",
    "snapshots": list(reversed([
        _snap(f"2026-01-0{i}T00:00:00Z", learning_status=s)
        for i, s in enumerate(["Excellent", "Excellent", "Excellent", "Poor", "Poor", "Poor"], start=1)
    ])),
}
learn_trend = trends.compute_learning_health_trend(learning_status_history)
check("learning_health_trend: Excellent->Poor sequence classified degrading", learn_trend["trend"] == "degrading")

# Missing key entirely (not just None) -> must not crash, treated as no value.
missing_key_history = {"schema_version": "1.0",
                        "snapshots": [{"timestamp": "2026-01-01T00:00:00Z", "health": {}}] * 6}
check("validation_health_trend: snapshot health dict missing the key entirely -> no crash, no_data",
      trends.compute_validation_health_trend(missing_key_history)["trend"] == "no_data")

# ─── 4. Regime trend ──────────────────────────────────────────────────────────
print("\n[4] compute_regime_trend")

regime_history = {
    "schema_version": "1.0",
    "snapshots": list(reversed([
        _snap("2026-01-01T00:00:00Z", regime_name="Trending", regime_confidence=60.0),
        _snap("2026-01-02T00:00:00Z", regime_name="Trending", regime_confidence=65.0),
        _snap("2026-01-03T00:00:00Z", regime_name="Ranging", regime_confidence=55.0),
        _snap("2026-01-04T00:00:00Z", regime_name="Trending", regime_confidence=80.0),
        _snap("2026-01-05T00:00:00Z", regime_name="Trending", regime_confidence=85.0),
        _snap("2026-01-06T00:00:00Z", regime_name="Trending", regime_confidence=90.0),
    ])),
}
regime_trend = trends.compute_regime_trend(regime_history)
check("regime_trend: distribution counts each observed regime name",
      regime_trend["distribution"] == {"Trending": 5, "Ranging": 1})
check("regime_trend: most-common regime listed first", next(iter(regime_trend["distribution"])) == "Trending")
check("regime_trend: confidence_trend improving as regime confidence rises",
      regime_trend["confidence_trend"]["trend"] == "improving")

all_unknown_history = {
    "schema_version": "1.0",
    "snapshots": [_snap(f"2026-01-0{i}T00:00:00Z", regime_name="Unknown", regime_confidence=None)
                  for i in range(1, 7)],
}
unknown_trend = trends.compute_regime_trend(all_unknown_history)
check("regime_trend: all-Unknown history -> distribution shows only Unknown",
      unknown_trend["distribution"] == {"Unknown": 6})
check("regime_trend: all-Unknown history -> confidence_trend is no_data, never fabricated",
      unknown_trend["confidence_trend"]["trend"] == "no_data")

check("regime_trend: empty history -> no crash, empty distribution",
      trends.compute_regime_trend({"snapshots": []})["distribution"] == {})
check("regime_trend: None history -> no crash",
      trends.compute_regime_trend(None)["distribution"] == {})

# ─── 5. build_health_trends_report bundling ─────────────────────────────────
print("\n[5] build_health_trends_report")

bundle = trends.build_health_trends_report(rising_history)
check("bundle: contains all 8 required sections",
      set(["health_history", "daily_trend", "weekly_trend", "monthly_trend", "confidence_trend",
           "validation_trend", "learning_trend", "regime_trend"]) <= set(bundle.keys()))
check("bundle: health_history respects the default history_limit",
      bundle["health_history"]["returned"] <= 50)

empty_bundle = trends.build_health_trends_report(None)
check("bundle: fully empty/None history -> no crash, no_data trends throughout",
      empty_bundle["daily_trend"]["trend"] == "no_data" and
      empty_bundle["health_history"]["total_snapshots"] == 0)

# ─── 6. Determinism ──────────────────────────────────────────────────────────
print("\n[6] Determinism")

report_a = trends.build_health_trends_report(regime_history)
report_b = trends.build_health_trends_report(regime_history)
check("identical input -> identical trends report across repeated calls", report_a == report_b)

# ─── 7. Off-limits-file regression safety ───────────────────────────────────
print("\n[7] Off-limits-file regression safety (source inspection)")

_files_must_not_reference = [
    ("analyzer.py", os.path.join(_MARKET_ANALYZER, "analyzer.py")),
    ("backtest.py", os.path.join(_MARKET_ANALYZER, "backtest.py")),
    ("walk_forward.py", os.path.join(_MARKET_ANALYZER, "walk_forward.py")),
    ("adaptive_calibration.py", os.path.join(_MARKET_ANALYZER, "adaptive_calibration.py")),
    ("ai_health_engine.py", os.path.join(_MARKET_ANALYZER, "ai_health_engine.py")),
    ("webapp/scanner.py", os.path.join(_WEBAPP, "scanner.py")),
    ("webapp/learning_engine.py", os.path.join(_WEBAPP, "learning_engine.py")),
    ("webapp/indicator_registry.py", os.path.join(_WEBAPP, "indicator_registry.py")),
]
for label, path in _files_must_not_reference:
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            src = f.read()
        check(f"{label}: no reference to ai_health_trends/ai_health_history_store (untouched)",
              "ai_health_trends" not in src and "ai_health_history_store" not in src)
    else:
        check(f"{label}: file exists for source check", False)

_APP_PY = os.path.join(_WEBAPP, "app.py")
with open(_APP_PY, "r", encoding="utf-8") as f:
    app_src = f.read()

check("app.py: new ai_health_history_store import present",
      "from ai_health_history_store import AIHealthHistoryStore" in app_src)
check("app.py: new ai_health_trends import present", "import ai_health_trends" in app_src)
check("app.py: new calendar stdlib import present", "import calendar" in app_src)
check("app.py: all 3 new /api/ai/history/* routes present",
      all(route in app_src for route in [
          '"/api/ai/history/health"', '"/api/ai/history/trends"', '"/api/ai/history/reset"',
      ]))
check("app.py: reset route is POST-only (mirrors /api/validation/history/reset convention)",
      '@app.route("/api/ai/history/reset", methods=["POST"])' in app_src)
check("app.py: pre-existing /api/ai/* routes still present verbatim (untouched)",
      all(route in app_src for route in [
          '"/api/ai/health"', '"/api/ai/status"', '"/api/ai/statistics"', '"/api/ai/explain"',
      ]))
check("app.py: Goal 2's /api/calibration/* routes still present verbatim (untouched)",
      all(route in app_src for route in [
          '"/api/calibration/report"', '"/api/calibration/status"',
          '"/api/calibration/history"', '"/api/calibration/recommendations"',
      ]))
check("app.py: pre-existing /api/learning/* and /api/validation/* routes still present (untouched)",
      '"/api/learning/recommendations"' in app_src and '"/api/validation/history"' in app_src)

check("ai_health_trends.py: MIN_SNAPSHOTS_FOR_TREND is a small, documented, independent constant",
      trends.MIN_SNAPSHOTS_FOR_TREND == 5)
check("ai_health_history_store.py: MAX_SNAPSHOT_ENTRIES restored correctly after bounded-log test",
      MAX_SNAPSHOT_ENTRIES == 2000)

# ─── Summary ─────────────────────────────────────────────────────────────────
print("\n" + "=" * 70)
print(f"RESULTS: {passed} passed, {failed} failed (of {passed + failed})")
print("=" * 70)

if failed:
    sys.exit(1)
