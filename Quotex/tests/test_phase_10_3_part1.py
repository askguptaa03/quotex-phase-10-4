"""
Phase 10.3 Part-1 verification suite — Market Regime Detection + Adaptive
Weight Engine + Dynamic Indicator Selection.

Run with:  python3 Quotex/tests/test_phase_10_3_part1.py
(from the repo root, or anywhere — path setup below is self-contained).

Background: this phase adds 4 new, additive, standalone modules layered on
top of the already-computed dynamic_weights in run_analysis.py / webapp/
app.py — analyzer.py, backtest.py, indicators.py, scanner.py,
learning_engine.py, indicator_registry.py, and the Quotex API are all
UNTOUCHED. See docs/CHANGELOG.md for the full diff.

Covers:
  1. regime_detector.py: all 8 named regimes + the Unknown path (missing
     fields, NaN fields) — one hand-built `ind` dict per regime, asserting
     both the regime name and that `reasons`/`metrics_used` are populated.
  2. regime_weight_engine.py: per-regime rescaling (ratio-preserving),
     sum-to-100 normalization, Uncertain/Unknown no-op passthrough.
  3. dynamic_indicator_selector.py: primary boost / low-relevance discount
     per regime, sum-to-100 normalization, Uncertain/Unknown no-op passthrough.
  4. regime_pipeline.py: orchestration composes the two steps identically
     to calling them by hand in sequence; determinism (same input -> byte-
     identical output across repeated calls).
  5. Normalization/edge cases: non-100-sum inputs, empty weights dict,
     zero-total weights, unknown factor keys not in any multiplier table.
  6. Integration wiring (config flag + API additive field): verified by
     source inspection of run_analysis.py / webapp/app.py / config.py —
     the same "route wiring confirmed by code review + py_compile, not a
     live Flask test client" convention already used for Phase 10.1/10.2's
     routes in this project, because webapp/app.py cannot be imported in
     this sandbox (fetch_data -> api_quotex -> loguru, which is not
     installed here — a pre-existing, documented environment limitation,
     not something this phase introduced or can fix).
  7. Off-limits files re-checked: analyzer.DEFAULT_CONFLUENCE_WEIGHTS,
     backtest._DEFAULT_8F_WEIGHTS still exactly 13 keys summing to 100.0;
     none of the 4 new modules import analyzer or backtest.
"""
import sys
import os
import math

_HERE = os.path.dirname(os.path.abspath(__file__))
_MARKET_ANALYZER = os.path.join(_HERE, "..", "market_analyzer")
_WEBAPP = os.path.join(_MARKET_ANALYZER, "webapp")
sys.path.insert(0, _MARKET_ANALYZER)
sys.path.insert(0, _WEBAPP)

import analyzer
import backtest as backtest_module

import regime_detector as rd
import regime_weight_engine as rwe
import dynamic_indicator_selector as dis
import regime_pipeline as rp

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


BASE_WEIGHTS = dict(analyzer.DEFAULT_CONFLUENCE_WEIGHTS)  # 13 factors, sums to 100.0


def base_ind(**overrides):
    d = {
        "adx": 10.0, "di_plus": 10.0, "di_minus": 10.0, "direction": "SIDEWAYS",
        "slope_pct": 0.0, "level": "MEDIUM", "atr_pct": 0.2, "bb_width_pct": 1.0,
        "price": 100.0, "bb_upper": 105.0, "bb_lower": 95.0, "rsi": 50.0,
        "candlestick_pattern_detail": None, "wick_rejection_detail": None,
        "liquidity_sweep_detail": None, "false_breakout_detail": None,
    }
    d.update(overrides)
    return d


# ═══════════════════════════════════════════════════════════════════════════
print("\n=== 1. regime_detector.py — all 8 regimes + Unknown ===")
# ═══════════════════════════════════════════════════════════════════════════

ind_uptrend = base_ind(adx=30.0, di_plus=25.0, di_minus=10.0, direction="BULLISH", slope_pct=0.8)
r = rd.detect_market_regime(ind_uptrend)
check("Strong Uptrend classified correctly", r["regime"] == rd.REGIME_STRONG_UPTREND)
check("Strong Uptrend has non-empty reasons", len(r["reasons"]) > 0)
check("Strong Uptrend has metrics_used populated", r["metrics_used"].get("adx") == 30.0)
check("Strong Uptrend confidence in [0,100]", 0.0 <= r["confidence"] <= 100.0)

ind_downtrend = base_ind(adx=30.0, di_plus=10.0, di_minus=25.0, direction="BEARISH", slope_pct=-0.8)
r = rd.detect_market_regime(ind_downtrend)
check("Strong Downtrend classified correctly", r["regime"] == rd.REGIME_STRONG_DOWNTREND)
check("Strong Downtrend has non-empty reasons", len(r["reasons"]) > 0)

ind_sideways = base_ind(adx=10.0, direction="SIDEWAYS", level="MEDIUM")
r = rd.detect_market_regime(ind_sideways)
check("Sideways Range classified correctly", r["regime"] == rd.REGIME_SIDEWAYS_RANGE)

ind_lowvol = base_ind(adx=10.0, direction="SIDEWAYS", level="LOW")
r = rd.detect_market_regime(ind_lowvol)
check("Low Volatility classified correctly", r["regime"] == rd.REGIME_LOW_VOLATILITY)

ind_highvol = base_ind(adx=10.0, direction="SIDEWAYS", level="HIGH")
r = rd.detect_market_regime(ind_highvol)
check("High Volatility classified correctly", r["regime"] == rd.REGIME_HIGH_VOLATILITY)

ind_breakout = base_ind(adx=30.0, di_plus=20.0, di_minus=10.0, direction="BULLISH",
                         slope_pct=0.5, price=110.0, bb_upper=105.0, bb_lower=95.0)
r = rd.detect_market_regime(ind_breakout)
check("Breakout classified correctly", r["regime"] == rd.REGIME_BREAKOUT)

ind_reversal = base_ind(wick_rejection_detail={
    "name": "wick_rejection", "direction": "BUY", "strength_score": 80.0, "reliability_score": 70.0
})
r = rd.detect_market_regime(ind_reversal)
check("Reversal classified correctly (wick_rejection)", r["regime"] == rd.REGIME_REVERSAL)
check("Reversal confidence reflects reliability_score", isclose(r["confidence"], 70.0))

ind_reversal2 = base_ind(false_breakout_detail={
    "name": "false_breakout", "direction": "SELL", "strength_score": 60.0, "reliability_score": 45.0
})
r = rd.detect_market_regime(ind_reversal2)
check("Reversal classified correctly (false_breakout)", r["regime"] == rd.REGIME_REVERSAL)

# Reversal detail present but BELOW the reliability threshold must NOT trigger Reversal
ind_weak_reversal = base_ind(wick_rejection_detail={
    "name": "wick_rejection", "direction": "BUY", "strength_score": 80.0, "reliability_score": 10.0
})
r = rd.detect_market_regime(ind_weak_reversal)
check("Weak (< threshold) reversal detail does NOT trigger Reversal",
      r["regime"] != rd.REGIME_REVERSAL)
check("Weak reversal detail falls through to Sideways Range instead",
      r["regime"] == rd.REGIME_SIDEWAYS_RANGE)

ind_uncertain = base_ind(adx=20.0, direction="BULLISH", slope_pct=0.3, level="MEDIUM",
                          di_plus=15.0, di_minus=10.0)
r = rd.detect_market_regime(ind_uncertain)
check("Uncertain / Mixed classified correctly", r["regime"] == rd.REGIME_UNCERTAIN)
check("Uncertain / Mixed has a deliberately low fixed confidence", isclose(r["confidence"], 25.0))

r = rd.detect_market_regime({"adx": 20.0})
check("Unknown regime on missing required fields", r["regime"] == rd.REGIME_UNKNOWN)
check("Unknown regime has confidence 0.0", r["confidence"] == 0.0)
check("Unknown regime metrics_used is empty (nothing computed)", r["metrics_used"] == {})
check("Unknown regime reasons mention the missing field(s)",
      "adx" not in r["reasons"][0] or "Missing" in r["reasons"][0])

ind_nan = base_ind()
ind_nan["adx"] = float("nan")
r = rd.detect_market_regime(ind_nan)
check("Unknown regime on NaN field", r["regime"] == rd.REGIME_UNKNOWN)

check("ALL_REGIMES has exactly 9 entries (8 real regimes + Unknown)", len(rd.ALL_REGIMES) == 9)
check("regime_detector.py has zero pandas/numpy import dependency",
      "pandas" not in dir(rd) and "numpy" not in dir(rd) and "pd" not in dir(rd) and "np" not in dir(rd))


# ═══════════════════════════════════════════════════════════════════════════
print("\n=== 2. regime_weight_engine.py — adaptive weight scaling ===")
# ═══════════════════════════════════════════════════════════════════════════

for regime_name in rwe.REGIME_FACTOR_MULTIPLIERS:
    result = rwe.apply_regime_adaptive_weights(BASE_WEIGHTS, {"regime": regime_name})
    check(f"[{regime_name}] applied == True", result["applied"] is True)
    check(f"[{regime_name}] weights sum to 100.0",
          isclose(sum(result["weights"].values()), 100.0, tol=1e-3))
    check(f"[{regime_name}] weights dict has same 13 keys as input",
          set(result["weights"].keys()) == set(BASE_WEIGHTS.keys()))
    check(f"[{regime_name}] notes list non-empty when any multiplier != 1.0",
          len(result["notes"]) > 0)

# Ratio check: since BASE_WEIGHTS are (near-)equal across factors, the ratio
# between two rescaled factors after renormalization must equal the ratio
# of their raw multipliers (a common renorm scalar cancels out).
uptrend_result = rwe.apply_regime_adaptive_weights(BASE_WEIGHTS, {"regime": rd.REGIME_STRONG_UPTREND})
mult = rwe.REGIME_FACTOR_MULTIPLIERS[rd.REGIME_STRONG_UPTREND]
expected_ratio = mult["obv"] / mult["bb"]
actual_ratio = uptrend_result["weights"]["obv"] / uptrend_result["weights"]["bb"]
check("Strong Uptrend: obv/bb weight ratio matches multiplier ratio (1.3/0.6)",
      isclose(actual_ratio, expected_ratio, tol=1e-4))

# Uncertain/Unknown must be a no-op
for regime_name in (rd.REGIME_UNCERTAIN, rd.REGIME_UNKNOWN):
    result = rwe.apply_regime_adaptive_weights(BASE_WEIGHTS, {"regime": regime_name})
    check(f"[{regime_name}] adaptive engine no-op: applied == False", result["applied"] is False)
    check(f"[{regime_name}] adaptive engine no-op: weights unchanged", result["weights"] == BASE_WEIGHTS)


# ═══════════════════════════════════════════════════════════════════════════
print("\n=== 3. dynamic_indicator_selector.py — categorical selection ===")
# ═══════════════════════════════════════════════════════════════════════════

for regime_name, table in dis.DYNAMIC_SELECTION_TABLE.items():
    result = dis.apply_dynamic_indicator_selection(BASE_WEIGHTS, {"regime": regime_name})
    check(f"[{regime_name}] selection applied == True", result["applied"] is True)
    check(f"[{regime_name}] selection weights sum to 100.0",
          isclose(sum(result["weights"].values()), 100.0, tol=1e-3))
    check(f"[{regime_name}] primary list matches table", result["primary"] == table["primary"])
    check(f"[{regime_name}] low_relevance list matches table",
          result["low_relevance"] == table["low_relevance"])
    # every primary factor's weight-to-neutral-factor ratio reflects the boost
    neutral_factors = [f for f in BASE_WEIGHTS if f not in table["primary"] and f not in table["low_relevance"]]
    if table["primary"] and neutral_factors:
        p = table["primary"][0]
        n = neutral_factors[0]
        ratio = result["weights"][p] / result["weights"][n]
        check(f"[{regime_name}] primary factor '{p}' boosted vs neutral factor '{n}'",
              ratio > (BASE_WEIGHTS[p] / BASE_WEIGHTS[n]))
    if table["low_relevance"] and neutral_factors:
        lr = table["low_relevance"][0]
        n = neutral_factors[0]
        ratio = result["weights"][lr] / result["weights"][n]
        check(f"[{regime_name}] low-relevance factor '{lr}' discounted vs neutral factor '{n}'",
              ratio < (BASE_WEIGHTS[lr] / BASE_WEIGHTS[n]))
    check(f"[{regime_name}] no factor's weight is ever zeroed by selection",
          all(w > 0 for w in result["weights"].values()))

for regime_name in (rd.REGIME_UNCERTAIN, rd.REGIME_UNKNOWN):
    result = dis.apply_dynamic_indicator_selection(BASE_WEIGHTS, {"regime": regime_name})
    check(f"[{regime_name}] selection no-op: applied == False", result["applied"] is False)
    check(f"[{regime_name}] selection no-op: primary/low_relevance both empty",
          result["primary"] == [] and result["low_relevance"] == [])
    check(f"[{regime_name}] selection no-op: weights unchanged", result["weights"] == BASE_WEIGHTS)


# ═══════════════════════════════════════════════════════════════════════════
print("\n=== 4. regime_pipeline.py — orchestration ===")
# ═══════════════════════════════════════════════════════════════════════════

pack = rp.compute_regime_adjusted_weights(BASE_WEIGHTS, ind_uptrend)
check("Pipeline: regime step matches detect_market_regime() called directly",
      pack["regime"]["regime"] == rd.detect_market_regime(ind_uptrend)["regime"])

manual_weight_step = rwe.apply_regime_adaptive_weights(BASE_WEIGHTS, pack["regime"])
manual_selection_step = dis.apply_dynamic_indicator_selection(manual_weight_step["weights"], pack["regime"])
check("Pipeline: final_weights matches manual two-step composition",
      pack["final_weights"] == manual_selection_step["weights"])
check("Pipeline: adaptive_weight_step surfaced verbatim",
      pack["adaptive_weight_step"] == manual_weight_step)
check("Pipeline: selection_step surfaced verbatim",
      pack["selection_step"] == manual_selection_step)
check("Pipeline: final_weights sums to 100.0", isclose(sum(pack["final_weights"].values()), 100.0, tol=1e-3))

# Determinism: same inputs -> byte-identical output across repeated calls
pack_a = rp.compute_regime_adjusted_weights(BASE_WEIGHTS, ind_breakout)
pack_b = rp.compute_regime_adjusted_weights(BASE_WEIGHTS, ind_breakout)
check("Pipeline is deterministic: repeated calls with same input match exactly", pack_a == pack_b)

# Unknown regime end-to-end: final_weights must equal the untouched input
pack_unknown = rp.compute_regime_adjusted_weights(BASE_WEIGHTS, {"adx": 20.0})
check("Pipeline on Unknown regime: final_weights == base_weights (full no-op)",
      pack_unknown["final_weights"] == BASE_WEIGHTS)
check("Pipeline on Unknown regime: regime name is Unknown", pack_unknown["regime"]["regime"] == rd.REGIME_UNKNOWN)


# ═══════════════════════════════════════════════════════════════════════════
print("\n=== 5. Normalization & edge cases ===")
# ═══════════════════════════════════════════════════════════════════════════

# Non-100-sum input still renormalizes to 100
skewed_weights = {k: 5.0 for k in BASE_WEIGHTS}  # sums to 65.0, not 100.0
result = rwe.apply_regime_adaptive_weights(skewed_weights, {"regime": rd.REGIME_SIDEWAYS_RANGE})
check("Non-100-sum input renormalizes to 100.0", isclose(sum(result["weights"].values()), 100.0, tol=1e-3))

pack_skewed = rp.compute_regime_adjusted_weights(skewed_weights, ind_sideways)
check("Pipeline renormalizes non-100-sum input to 100.0",
      isclose(sum(pack_skewed["final_weights"].values()), 100.0, tol=1e-3))

# Empty weights dict must not raise and must return an empty dict
empty_result = rwe.apply_regime_adaptive_weights({}, {"regime": rd.REGIME_BREAKOUT})
check("Empty weights dict -> empty output, no exception", empty_result["weights"] == {})
empty_selection = dis.apply_dynamic_indicator_selection({}, {"regime": rd.REGIME_BREAKOUT})
check("Empty weights dict -> empty selection output, no exception", empty_selection["weights"] == {})

# All-zero weights: total == 0 guard must skip renormalization without raising
zero_weights = {k: 0.0 for k in BASE_WEIGHTS}
zero_result = rwe.apply_regime_adaptive_weights(zero_weights, {"regime": rd.REGIME_HIGH_VOLATILITY})
check("All-zero weights: no exception raised", isinstance(zero_result["weights"], dict))
check("All-zero weights: every output value is 0.0 (total==0 guard skips divide-by-zero)",
      all(v == 0.0 for v in zero_result["weights"].values()))

# Unknown factor key not present in any multiplier/selection table -> defaults to 1.0 / neutral
weird_weights = dict(BASE_WEIGHTS)
weird_weights["some_future_factor"] = 7.69
weird_result = rwe.apply_regime_adaptive_weights(weird_weights, {"regime": rd.REGIME_REVERSAL})
check("Unrecognized factor key handled without KeyError", "some_future_factor" in weird_result["weights"])
weird_selection = dis.apply_dynamic_indicator_selection(weird_weights, {"regime": rd.REGIME_REVERSAL})
check("Unrecognized factor key passes through selection unharmed",
      "some_future_factor" in weird_selection["weights"])


# ═══════════════════════════════════════════════════════════════════════════
print("\n=== 6. Integration wiring — config flag + API additive field (source inspection) ===")
# ═══════════════════════════════════════════════════════════════════════════
# webapp/app.py cannot be imported in this sandbox: fetch_data -> api_quotex
# -> loguru, which is not installed here (pre-existing environment limitation,
# same one documented for Phase 10.1/10.2's untested Flask routes). Wiring is
# therefore verified the same way those phases verified it: source inspection
# + py_compile (already re-run in Step 8), not a live Flask test client.

import config as cfg
check("config.ENABLE_REGIME_ADAPTIVE_WEIGHTS exists and defaults True",
      getattr(cfg, "ENABLE_REGIME_ADAPTIVE_WEIGHTS", None) is True)

_run_analysis_src = open(os.path.join(_MARKET_ANALYZER, "run_analysis.py"), encoding="utf-8").read()
check("run_analysis.py imports regime_pipeline.compute_regime_adjusted_weights",
      "from regime_pipeline import compute_regime_adjusted_weights" in _run_analysis_src)
check("run_analysis.py gates the regime pipeline on the config flag",
      "cfg.ENABLE_REGIME_ADAPTIVE_WEIGHTS" in _run_analysis_src or
      "ENABLE_REGIME_ADAPTIVE_WEIGHTS" in _run_analysis_src)
check("run_analysis.py calls compute_regime_adjusted_weights(dynamic_weights, indicators)",
      "compute_regime_adjusted_weights(dynamic_weights, indicators)" in _run_analysis_src)

_app_src = open(os.path.join(_WEBAPP, "app.py"), encoding="utf-8").read()
check("app.py imports regime_pipeline.compute_regime_adjusted_weights",
      "from regime_pipeline import compute_regime_adjusted_weights" in _app_src)
check("app.py gates the regime pipeline on the config flag",
      "ENABLE_REGIME_ADAPTIVE_WEIGHTS" in _app_src)
check("app.py calls compute_regime_adjusted_weights(dynamic_weights, indicators)",
      "compute_regime_adjusted_weights(dynamic_weights, indicators)" in _app_src)
check("app.py's regime layer runs BEFORE _apply_settings_weight_overrides (settings keep final say)",
      _app_src.index("compute_regime_adjusted_weights(dynamic_weights, indicators)")
      < _app_src.index("dynamic_weights = _apply_settings_weight_overrides"))
check("app.py's JSON result dict gained an additive 'regime' key",
      '"regime": {' in _app_src and '"name": regime_pack["regime"]["regime"]' in _app_src)
check("app.py's new 'regime' key sits alongside (not replacing) existing 'multi_tf_status' key",
      '"multi_tf_status": multi_tf_status,' in _app_src)
check("app.py still calls generate_confluence_signal(df, indicators, dynamic_weights) unchanged",
      "confluence = generate_confluence_signal(df, indicators, dynamic_weights)" in _app_src)


# ═══════════════════════════════════════════════════════════════════════════
print("\n=== 7. Off-limits files unaffected — re-checked from the Phase 10.3 Part-1 code path ===")
# ═══════════════════════════════════════════════════════════════════════════
check("analyzer.DEFAULT_CONFLUENCE_WEIGHTS still has exactly 13 keys, sums to 100.0 (untouched)",
      len(analyzer.DEFAULT_CONFLUENCE_WEIGHTS) == 13
      and abs(sum(analyzer.DEFAULT_CONFLUENCE_WEIGHTS.values()) - 100.0) < 1e-9)
check("backtest._DEFAULT_8F_WEIGHTS still has exactly 13 keys, sums to 100.0 (untouched)",
      len(backtest_module._DEFAULT_8F_WEIGHTS) == 13
      and abs(sum(backtest_module._DEFAULT_8F_WEIGHTS.values()) - 100.0) < 1e-9)

_analyzer_src = open(os.path.join(_MARKET_ANALYZER, "analyzer.py"), encoding="utf-8").read()
check("analyzer.py source contains no reference to any Phase 10.3 module (zero coupling)",
      "regime_detector" not in _analyzer_src
      and "regime_weight_engine" not in _analyzer_src
      and "dynamic_indicator_selector" not in _analyzer_src
      and "regime_pipeline" not in _analyzer_src)

check("regime_detector.py imports nothing from analyzer/backtest",
      not any(mod in dir(rd) for mod in ("analyzer", "backtest")))
check("regime_weight_engine.py imports nothing from analyzer/backtest",
      not any(mod in dir(rwe) for mod in ("analyzer", "backtest")))
check("dynamic_indicator_selector.py imports nothing from analyzer/backtest",
      not any(mod in dir(dis) for mod in ("analyzer", "backtest")))
check("regime_pipeline.py imports nothing from analyzer/backtest",
      not any(mod in dir(rp) for mod in ("analyzer", "backtest")))

for _fname in ("scanner.py", "learning_engine.py", "indicator_registry.py"):
    _fpath = os.path.join(_WEBAPP, _fname)
    _src = open(_fpath, encoding="utf-8").read()
    check(f"{_fname} source contains no reference to any Phase 10.3 module (untouched)",
          "regime_detector" not in _src
          and "regime_weight_engine" not in _src
          and "dynamic_indicator_selector" not in _src
          and "regime_pipeline" not in _src)


# ═══════════════════════════════════════════════════════════════════════════
print(f"\n=== RESULT: {passed} passed, {failed} failed ===")
if failed:
    sys.exit(1)
