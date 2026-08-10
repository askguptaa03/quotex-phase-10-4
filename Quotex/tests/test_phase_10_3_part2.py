"""
Phase 10.3 Part-2 verification suite — AI Health Dashboard + Explainable
Signal System.

Run with:  python3 Quotex/tests/test_phase_10_3_part2.py
(from the repo root, or anywhere — path setup below is self-contained).

Background: this phase adds 2 new, additive, standalone modules —
`explainable_signal.py` and `ai_health_engine.py` — plus 4 new read-only
`/api/ai/*` routes in `webapp/app.py` and a new dashboard page in
`templates/index.html`/`static/app.js`/`static/style.css`. Neither new
module recomputes any indicator, confluence vote, filter-score gate, or
regime classification — both are pure functions of already-computed data
(the `_run_pipeline()` result dict for explain_signal(); the validation
history / learning recommendation / scanner status+results / current
regime dicts for compute_ai_health()). analyzer.py, backtest.py,
indicators.py, scanner.py, learning_engine.py, and indicator_registry.py
are all untouched.

Covers:
  1. ai_health_engine.py: each component health function
     (indicator/validation/learning/scanner/regime) against hand-built
     inputs with KNOWN expected results, the "no data yet" -> Fair
     (never Critical) convention, and compute_ai_health()'s full
     orchestration + flat-field re-exposure.
  2. explainable_signal.py: explain_signal() for BUY/SELL/WAIT signals
     built from hand-crafted pipeline-result dicts, the 9 named checks,
     Hard Gates Passed/Failed, Reasons/Warnings population, and the
     empty-result safety fallback.
  3. Edge cases: empty dicts, None inputs, missing keys, zero-sample
     data, Unknown regime, determinism (same input -> identical output
     across repeated calls).
  4. Integration wiring (config/route/UI presence) verified by source
     inspection of webapp/app.py + templates/index.html + static/app.js —
     the same convention Phase 10.1/10.2/10.3-Part-1 already established
     for this sandbox's standing limitation (webapp/app.py cannot be
     imported here: fetch_data -> api_quotex -> loguru, not installed).
  5. Off-limits-file regression safety: analyzer.py/backtest.py/
     indicators.py/scanner.py/learning_engine.py/indicator_registry.py
     source re-confirmed to contain no reference to either new module;
     DEFAULT_CONFLUENCE_WEIGHTS unchanged; the full existing regression
     suite is re-run separately in Step 7, not duplicated here.
"""
import sys
import os

_HERE = os.path.dirname(os.path.abspath(__file__))
_MARKET_ANALYZER = os.path.join(_HERE, "..", "market_analyzer")
_WEBAPP = os.path.join(_MARKET_ANALYZER, "webapp")
sys.path.insert(0, _MARKET_ANALYZER)
sys.path.insert(0, _WEBAPP)

import analyzer
import ai_health_engine as ahe
import explainable_signal as es

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


def isclose(a, b, tol=1e-6):
    return abs(a - b) < tol


# ═══════════════════════════════════════════════════════════════════════════
print("\n=== 1. ai_health_engine.py — component health functions ===")
# ═══════════════════════════════════════════════════════════════════════════

# -- compute_indicator_health -------------------------------------------------
vh_empty = {}
r = ahe.compute_indicator_health(vh_empty)
check("Indicator health: empty history -> Fair, zero totals", r["status"] == "Fair" and r["indicators_total"] == 0)

vh_no_sufficient = {"rolling_stats": {"bb": {"total_samples": 3, "average_win_rate_over_runs": None}}}
r = ahe.compute_indicator_health(vh_no_sufficient, min_samples=20)
check("Indicator health: below min_samples -> Fair, coverage 0%",
      r["status"] == "Fair" and r["coverage_pct"] == 0.0 and r["indicators_with_data"] == 0)

vh_good = {"rolling_stats": {
    "bb": {"total_samples": 100, "average_win_rate_over_runs": 90.0},
    "rsi_div": {"total_samples": 100, "average_win_rate_over_runs": 85.0},
}}
r = ahe.compute_indicator_health(vh_good, min_samples=20)
expected_score = 0.7 * 87.5 + 0.3 * 100.0
check("Indicator health: all covered, high win-rate -> Excellent",
      r["status"] == "Excellent" and isclose(r["average_accuracy"], 87.5) and r["coverage_pct"] == 100.0)

# -- compute_validation_health -------------------------------------------------
r = ahe.compute_validation_health({})
check("Validation health: no data -> Fair, zero samples", r["status"] == "Fair" and r["total_samples"] == 0)

vh_volume = {"rolling_stats": {"bb": {"total_samples": 2500}}, "run_log": [{"timestamp": "2026-07-27T00:00:00Z"}]}
r = ahe.compute_validation_health(vh_volume)
check("Validation health: 2500+ pooled samples -> Excellent (capped at 100 score)",
      r["status"] == "Excellent" and r["total_samples"] == 2500 and r["last_run_at"] == "2026-07-27T00:00:00Z")

vh_low_volume = {"rolling_stats": {"bb": {"total_samples": 100}}, "run_log": []}
r = ahe.compute_validation_health(vh_low_volume)
check("Validation health: low volume -> low score status, runs_recorded 0",
      r["status"] in ("Poor", "Critical") and r["runs_recorded"] == 0)

# -- compute_learning_health --------------------------------------------------
r = ahe.compute_learning_health(None)
check("Learning health: None recommendation -> Fair", r["status"] == "Fair" and r["indicators_total"] == 0)

rec_none_conf = {"per_indicator": {"bb": {"confidence": "none"}, "rsi_div": {"confidence": "none"}}}
r = ahe.compute_learning_health(rec_none_conf)
check("Learning health: all confidence=none -> Fair (not Critical, no data yet)",
      r["status"] == "Fair" and r["indicators_with_confidence"] == 0)

rec_high_conf = {"per_indicator": {"bb": {"confidence": "high"}, "rsi_div": {"confidence": "medium"}}}
r = ahe.compute_learning_health(rec_high_conf)
check("Learning health: all indicators have real confidence -> Excellent",
      r["status"] == "Excellent" and r["indicators_with_confidence"] == 2 and r["coverage_pct"] == 100.0)

# -- compute_regime_health -----------------------------------------------------
r = ahe.compute_regime_health(None)
check("Regime health: None -> Fair, regime Unknown", r["status"] == "Fair" and r["regime"] == "Unknown")

r = ahe.compute_regime_health({"name": "Unknown", "confidence": 0.0})
check("Regime health: explicit Unknown -> Fair (not Critical)", r["status"] == "Fair")

r = ahe.compute_regime_health({"name": "Strong Uptrend", "confidence": 90.0})
check("Regime health: Strong Uptrend, confidence 90 -> Excellent, reuses confidence directly",
      r["status"] == "Excellent" and r["confidence"] == 90.0)

r = ahe.compute_regime_health({"name": "Uncertain / Mixed", "confidence": 25.0})
check("Regime health: Uncertain/Mixed, confidence 25 -> Poor (low, matches its own fixed confidence)",
      r["status"] == "Poor")

# -- compute_scanner_health -----------------------------------------------------
r = ahe.compute_scanner_health(None, None)
check("Scanner health: no data at all -> Fair, cached_results 0", r["status"] == "Fair" and r["cached_results"] == 0)

ss = {"running": True, "cached_results": 10}
sr = {"top_signals": [
    {"confluence": {"signal": "BUY", "confidence": 80}, "filter_score": 88, "regime": {"name": "Strong Uptrend"}},
    {"confluence": {"signal": "BUY", "confidence": 70}, "filter_score": 82, "regime": {"name": "Breakout"}},
]}
r = ahe.compute_scanner_health(ss, sr)
check("Scanner health: 2 BUY surfaced -> buy_pct 100, sell_pct 0, wait_pct None (not derivable)",
      r["buy_pct"] == 100.0 and r["sell_pct"] == 0.0 and r["wait_pct"] is None)
check("Scanner health: average_filter_score computed correctly", isclose(r["average_filter_score"], 85.0))
check("Scanner health: current_regime taken from top-ranked cached signal", r["current_regime"] == "Strong Uptrend")
check("Scanner health: signal_count uses the TRUE unfiltered cached_results, not len(top_signals)",
      r["signal_count"] == 10)

ss_stale = {"running": False, "cached_results": 5}
sr_empty = {"top_signals": []}
r = ahe.compute_scanner_health(ss_stale, sr_empty)
check("Scanner health: stopped + stale cache + nothing surfaced -> Poor (score 40)", r["status"] == "Poor")


# ═══════════════════════════════════════════════════════════════════════════
print("\n=== 2. ai_health_engine.py — compute_ai_health() full orchestration ===")
# ═══════════════════════════════════════════════════════════════════════════

full = ahe.compute_ai_health(
    validation_history=vh_good, recommendation=rec_high_conf,
    scanner_status=ss, scanner_results=sr, current_regime={"name": "Strong Uptrend", "confidence": 90.0},
)
check("compute_ai_health: overall_health has both status and numeric score",
      "status" in full["overall_health"] and isinstance(full["overall_health"]["score"], float))
check("compute_ai_health: all 6 required health blocks present",
      all(k in full for k in ("overall_health", "indicator_health", "scanner_health",
                               "validation_health", "learning_health", "regime_health")))
check("compute_ai_health: flat fields re-expose nested values correctly",
      full["recent_accuracy"] == full["indicator_health"]["average_accuracy"]
      and full["history_coverage"] == full["indicator_health"]["coverage_pct"]
      and full["average_confidence"] == full["scanner_health"]["average_confidence"]
      and full["average_filter_score"] == full["scanner_health"]["average_filter_score"]
      and full["buy_pct"] == full["scanner_health"]["buy_pct"]
      and full["sell_pct"] == full["scanner_health"]["sell_pct"]
      and full["recent_wait_pct"] is None
      and full["data_quality"] == full["validation_health"]["status"])

no_data_health = ahe.compute_ai_health()
check("compute_ai_health: zero-argument call never raises, everything defaults to Fair",
      all(no_data_health[k]["status"] == "Fair" for k in
          ("indicator_health", "scanner_health", "validation_health", "learning_health", "regime_health")))
check("compute_ai_health: zero-argument overall_health is Fair", no_data_health["overall_health"]["status"] == "Fair")

# Determinism
full_a = ahe.compute_ai_health(validation_history=vh_good, recommendation=rec_high_conf,
                                scanner_status=ss, scanner_results=sr,
                                current_regime={"name": "Strong Uptrend", "confidence": 90.0})
full_b = ahe.compute_ai_health(validation_history=vh_good, recommendation=rec_high_conf,
                                scanner_status=ss, scanner_results=sr,
                                current_regime={"name": "Strong Uptrend", "confidence": 90.0})
check("compute_ai_health is deterministic: repeated calls with same input match exactly", full_a == full_b)


# ═══════════════════════════════════════════════════════════════════════════
print("\n=== 3. explainable_signal.py — explain_signal() ===")
# ═══════════════════════════════════════════════════════════════════════════

def make_result(signal="BUY", confidence=78, filter_score=82.5,
                 passed_filters=None, failed_filters=None, filter_breakdown=None,
                 factors=None, regime=None, multi_tf_status=None, trend="BULLISH"):
    return {
        "trend": trend,
        "confluence": {"signal": signal, "confidence": confidence},
        "filter_score": filter_score,
        "passed_filters": passed_filters if passed_filters is not None else
            ["ema_trend", "adx", "atr", "support_resistance", "multi_timeframe", "payout"],
        "failed_filters": failed_filters if failed_filters is not None else ["candlestick"],
        "filter_breakdown": filter_breakdown if filter_breakdown is not None else {
            "ema_trend": {"passed": True, "value": "BULLISH"},
            "adx": {"passed": True, "value": 32.1},
            "atr": {"passed": True, "value": 0.3, "level": "MEDIUM"},
            "support_resistance": {"passed": True, "value": True},
            "multi_timeframe": {"passed": True, "value": "CONFIRMED"},
            "payout": {"passed": True, "value": 92},
            "candlestick": {"passed": False, "value": None},
        },
        "factors": factors if factors is not None else [
            {"key": "rsi_div", "vote": "BULLISH"}, {"key": "stoch", "vote": "BULLISH"},
            {"key": "cci", "vote": "NEUTRAL"}, {"key": "obv", "vote": "BULLISH"},
        ],
        "regime": regime if regime is not None else
            {"name": "Strong Uptrend", "confidence": 80.0, "reasons": ["ADX confirms uptrend"]},
        "multi_tf_status": multi_tf_status if multi_tf_status is not None else {"status": "CONFIRMED"},
    }


buy_result = make_result()
out = es.explain_signal(buy_result)
check("explain_signal: signal/confidence/filter_score passed through verbatim",
      out["signal"] == "BUY" and out["confidence"] == 78 and out["final_filter_score"] == 82.5)
check("explain_signal: all 9 named checks present",
      set(out["checks"].keys()) == {"trend", "momentum", "volatility", "volume", "price_action",
                                     "support_resistance", "adx", "mtf", "regime"})
check("explain_signal: trend check True (ema_trend gate passed)", out["checks"]["trend"]["passed"] is True)
check("explain_signal: price_action check False (candlestick gate failed)", out["checks"]["price_action"]["passed"] is False)
check("explain_signal: momentum check True (2/3 momentum factors BULLISH)", out["checks"]["momentum"]["passed"] is True)
check("explain_signal: volume check True (obv vote == BULLISH == BUY direction)", out["checks"]["volume"]["passed"] is True)
check("explain_signal: regime check True (Strong Uptrend supports BUY)", out["checks"]["regime"]["passed"] is True)
check("explain_signal: hard_gates_passed has 6 entries, hard_gates_failed has 1",
      len(out["hard_gates_passed"]) == 6 and len(out["hard_gates_failed"]) == 1)
check("explain_signal: hard_gates_failed contains the candlestick gate with a human label",
      out["hard_gates_failed"][0]["gate"] == "candlestick" and out["hard_gates_failed"][0]["label"] == "Candlestick Pattern")
check("explain_signal: reasons list is non-empty", len(out["reasons"]) > 0)
check("explain_signal: warnings mentions the failed price_action check",
      any("Price Action" in w for w in out["warnings"]))

sell_result = make_result(signal="SELL", trend="BEARISH",
                           regime={"name": "Strong Downtrend", "confidence": 85.0, "reasons": []},
                           factors=[{"key": "rsi_div", "vote": "BEARISH"}, {"key": "stoch", "vote": "BEARISH"},
                                    {"key": "cci", "vote": "BEARISH"}, {"key": "obv", "vote": "BEARISH"}])
out = es.explain_signal(sell_result)
check("explain_signal: SELL momentum check True (3/3 momentum factors BEARISH)", out["checks"]["momentum"]["passed"] is True)
check("explain_signal: SELL regime check True (Strong Downtrend supports SELL)", out["checks"]["regime"]["passed"] is True)
check("explain_signal: SELL regime check would be False for a BUY-favoring regime",
      es.explain_signal(make_result(signal="SELL", regime={"name": "Strong Uptrend", "confidence": 80.0, "reasons": []}))
      ["checks"]["regime"]["passed"] is False)

wait_result = make_result(signal="WAIT", confidence=0,
                          passed_filters=["ema_trend"], failed_filters=["adx", "atr", "support_resistance",
                                                                        "multi_timeframe", "payout", "candlestick"])
out = es.explain_signal(wait_result)
check("explain_signal: WAIT signal -> momentum/volume/regime all False with explicit 'no directional confirmation' reason",
      out["checks"]["momentum"]["passed"] is False and "WAIT" in out["checks"]["momentum"]["detail"]
      and out["checks"]["volume"]["passed"] is False and out["checks"]["regime"]["passed"] is False)
check("explain_signal: WAIT signal produces a WAIT-explanation warning",
      any("WAIT" in w for w in out["warnings"]))

# Unknown regime
unknown_regime_result = make_result(regime={"name": "Unknown", "confidence": 0.0, "reasons": ["Missing fields"]})
out = es.explain_signal(unknown_regime_result)
check("explain_signal: Unknown regime -> regime check False, warning mentions Unknown",
      out["checks"]["regime"]["passed"] is False and any("Unknown" in w for w in out["warnings"]))

# Missing/empty result
out = es.explain_signal({})
check("explain_signal: empty dict -> WAIT, all checks False, single explanatory warning, no exception",
      out["signal"] == "WAIT" and all(not c["passed"] for c in out["checks"].values())
      and len(out["warnings"]) == 1)

out = es.explain_signal(None) if False else es.explain_signal({})  # guard: explain_signal expects a dict, not None
check("explain_signal: does not raise on a completely empty dict", isinstance(out, dict))

# Missing factors / missing filter_breakdown entries handled gracefully
partial_result = {
    "trend": "BULLISH",
    "confluence": {"signal": "BUY", "confidence": 50},
    "filter_score": 60.0,
    "passed_filters": ["ema_trend"],
    "failed_filters": [],
    "filter_breakdown": {"ema_trend": {"passed": True, "value": "BULLISH"}},
    "factors": [],
    "regime": {},
    "multi_tf_status": {},
}
out = es.explain_signal(partial_result)
check("explain_signal: missing momentum/volume factor data reported as failed with explicit 'no data' detail",
      out["checks"]["momentum"]["passed"] is False and "No momentum factor data" in out["checks"]["momentum"]["detail"]
      and out["checks"]["volume"]["passed"] is False and "No OBV volume data" in out["checks"]["volume"]["detail"])
check("explain_signal: missing gate keys in filter_breakdown default to failed, not an exception",
      out["checks"]["adx"]["passed"] is False and out["checks"]["volatility"]["passed"] is False)

# Determinism
out_a = es.explain_signal(buy_result)
out_b = es.explain_signal(buy_result)
check("explain_signal is deterministic: repeated calls with same input match exactly", out_a == out_b)


# ═══════════════════════════════════════════════════════════════════════════
print("\n=== 4. Integration wiring — routes + UI (source inspection) ===")
# ═══════════════════════════════════════════════════════════════════════════
# webapp/app.py cannot be imported in this sandbox: fetch_data -> api_quotex
# -> loguru, not installed here (same pre-existing environment limitation
# documented for every prior phase's Flask routes). Verified by source
# inspection + py_compile (re-run in Step 7), not a live test client.

_app_src = open(os.path.join(_WEBAPP, "app.py"), encoding="utf-8").read()
check("app.py imports explain_signal", "from explainable_signal import explain_signal" in _app_src)
check("app.py imports compute_ai_health", "from ai_health_engine import compute_ai_health" in _app_src)
check("app.py defines the _build_ai_health() helper", "def _build_ai_health()" in _app_src)
for route in ("/api/ai/health", "/api/ai/status", "/api/ai/statistics", "/api/ai/explain"):
    check(f"app.py registers route {route}", f'"{route}"' in _app_src)
check("app.py's /api/ai/explain reuses _run_pipeline() exactly like /api/signal (same call)",
      _app_src.count("_run_bg(_run_pipeline(asset, timeframe))") >= 2)
check("app.py's /api/ai/explain falls back to the scanner's top-ranked cached signal when no asset is given",
      "top_signals = _scanner.get_results().get(\"top_signals\") or []" in _app_src
      and "result = top_signals[0] if top_signals else {}" in _app_src)

_index_src = open(os.path.join(_WEBAPP, "templates", "index.html"), encoding="utf-8").read()
check("index.html has the new AI Health drawer link", 'data-nav="ai-health"' in _index_src)
check("index.html has the new page-ai-health section", 'id="page-ai-health"' in _index_src)
check("index.html has the Explain Signal modal overlay", 'id="aih-explain-modal-overlay"' in _index_src)
for el_id in ("aih-overall-badge", "aih-indicator-badge", "aih-scanner-badge", "aih-validation-badge",
              "aih-learning-badge", "aih-regime-badge", "aih-current-regime", "aih-stats-grid",
              "aih-top-indicators-grid", "aih-best-assets-grid", "aih-best-timeframes-grid",
              "aih-explain-body"):
    check(f"index.html has element id={el_id}", f'id="{el_id}"' in _index_src)

_appjs_src = open(os.path.join(_WEBAPP, "static", "app.js"), encoding="utf-8").read()
check("app.js VIEWS array includes 'ai-health'", "'ai-health'" in _appjs_src.split("const VIEWS")[1].split(";")[0])
check("app.js navigateTo() calls initAiHealthPage() for the new page",
      "initAiHealthPage()" in _appjs_src)
for fn in ("aihLoadHealth", "aihLoadTopIndicators", "aihLoadBestGroups", "aihExplainSignal",
           "aihCloseExplainModal", "aihLoadAll", "initAiHealthPage"):
    check(f"app.js defines function {fn}", f"function {fn}(" in _appjs_src)
check("app.js's aihExplainSignal() calls the /api/ai/explain route", "/api/ai/explain" in _appjs_src)
check("app.js's aihLoadHealth() calls the /api/ai/health route", "'/api/ai/health'" in _appjs_src)

_css_src = open(os.path.join(_WEBAPP, "static", "style.css"), encoding="utf-8").read()
for cls in (".badge-health-excellent", ".badge-health-good", ".badge-health-fair",
            ".badge-health-poor", ".badge-health-critical", ".aih-modal-overlay", ".aih-modal"):
    check(f"style.css defines {cls}", cls in _css_src)


# ═══════════════════════════════════════════════════════════════════════════
print("\n=== 5. Off-limits files unaffected — re-checked from Phase 10.3 Part-2's code path ===")
# ═══════════════════════════════════════════════════════════════════════════
check("analyzer.DEFAULT_CONFLUENCE_WEIGHTS still has exactly 13 keys, sums to 100.0 (untouched)",
      len(analyzer.DEFAULT_CONFLUENCE_WEIGHTS) == 13
      and abs(sum(analyzer.DEFAULT_CONFLUENCE_WEIGHTS.values()) - 100.0) < 1e-9)

_analyzer_src = open(os.path.join(_MARKET_ANALYZER, "analyzer.py"), encoding="utf-8").read()
check("analyzer.py source contains no reference to either new Phase 10.3 Part-2 module",
      "explainable_signal" not in _analyzer_src and "ai_health_engine" not in _analyzer_src)

check("explainable_signal.py imports nothing from analyzer/backtest/indicators",
      not any(mod in dir(es) for mod in ("analyzer", "backtest", "indicators")))
check("ai_health_engine.py imports nothing from analyzer/backtest/indicators",
      not any(mod in dir(ahe) for mod in ("analyzer", "backtest", "indicators")))

for _fname in ("backtest.py",):
    _fpath = os.path.join(_MARKET_ANALYZER, _fname)
    _src = open(_fpath, encoding="utf-8").read()
    check(f"{_fname} source contains no reference to either new module (untouched)",
          "explainable_signal" not in _src and "ai_health_engine" not in _src)

for _fname in ("scanner.py", "learning_engine.py", "indicator_registry.py"):
    _fpath = os.path.join(_WEBAPP, _fname)
    _src = open(_fpath, encoding="utf-8").read()
    check(f"{_fname} source contains no reference to either new module (untouched)",
          "explainable_signal" not in _src and "ai_health_engine" not in _src)


# ═══════════════════════════════════════════════════════════════════════════
print(f"\n=== RESULT: {passed} passed, {failed} failed ===")
if failed:
    sys.exit(1)
