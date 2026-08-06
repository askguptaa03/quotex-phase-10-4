"""
Phase 9 prerequisite fix — live-pipeline weight-dropping bug.

Run with:  python3 Quotex/tests/test_phase_9_pipeline_fix.py
(from the repo root, or anywhere — path setup below is self-contained).

Background: Phase 8.6 connected wick_rejection/liquidity_sweep/false_breakout
to analyzer.DEFAULT_CONFLUENCE_WEIGHTS and _confluence_factor_votes(), but
backtest.py's _DEFAULT_8F_WEIGHTS (the dict compute_dynamic_weights() builds
its ENTIRE output from) still only had the original 10 factors, at their
pre-Phase-8.6 values (10.0 each, not the rebalanced 7.69). Since
generate_confluence_signal() REPLACES (not merges) its weights dict whenever
a non-empty dynamic_weights is passed, and app.py's real pipeline always
passes one (computed via compute_dynamic_weights()), the 3 new indicators'
votes were correctly computed but contributed exactly 0 weight to every real
signal the live app ever produced.

Covers:
  1. compute_dynamic_weights() output always has 13 keys and sums to 100.0,
     regardless of which factors have backtested accuracy data.
  2. The 3 Phase 8.6 indicators always receive their non-zero default
     weight (never silently dropped) since backtest_factor_accuracy() never
     scores them (that remains a separate, not-yet-done extension).
  3. The original 10 factors' accuracy-to-weight FORMULA is byte-identical
     to before this fix — same near-random-penalty rule, same
     score-proportional-to-accuracy split — just now correctly computed
     against a remaining_budget of 76.9 (100 - the 3 new factors' reserved
     23.1) instead of a full 100, which is the necessary and unavoidable
     consequence of no longer silently zeroing those 3 out.
  4. The full simulated live-pipeline path (backtest_factor_accuracy ->
     compute_dynamic_weights -> settings weight-scale overlay ->
     generate_confluence_signal) ends with all 13 weights present and
     summing to 100.0, with the 3 new indicators non-zero.
  5. Old behavior when dynamic_weights is not passed at all (still the
     library-level default path) is completely unaffected by this fix.

No network access, no live Quotex connection required — matches this
project's established sandbox-testing convention.
"""
import sys
import os

_HERE = os.path.dirname(os.path.abspath(__file__))
_MARKET_ANALYZER = os.path.join(_HERE, "..", "market_analyzer")
sys.path.insert(0, _MARKET_ANALYZER)
sys.path.insert(0, os.path.join(_MARKET_ANALYZER, "webapp"))

import pandas as pd
import numpy as np

import indicators
import analyzer
from backtest import backtest_factor_accuracy, compute_dynamic_weights, _DEFAULT_8F_WEIGHTS
import settings_store

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


NEW_INDICATORS = ("wick_rejection", "liquidity_sweep", "false_breakout")
ORIG_10 = ("bb", "rsi_div", "stoch", "cci", "candle", "mean_reversion",
           "exhaustion", "round_number", "obv", "sr")


def _apply_settings_weight_overrides(dynamic_weights, settings):
    """Reimplemented verbatim from webapp/app.py (lines ~565-620) for this
    test only — app.py itself has heavy import-time dependencies (Quotex
    client chain: loguru/websockets/pydantic) not installable in this
    offline sandbox. Not a redefinition the app uses; purely a test-side
    mirror of already-existing, unmodified logic, so the test exercises the
    exact same scaling behavior app.py's real function performs."""
    indicators_cfg = settings.get("indicators", {})
    out = {}
    for key, base_weight in dynamic_weights.items():
        ind_cfg = indicators_cfg.get(key)
        if ind_cfg is None:
            out[key] = base_weight
            continue
        if not ind_cfg.get("enabled", True):
            out[key] = 0.0
            continue
        scale = float(ind_cfg.get("weight", 10.0)) / 10.0
        out[key] = base_weight * scale
    return out


def make_synthetic_df(seed, n=300):
    rng = np.random.RandomState(seed)
    close = 100 + np.cumsum(rng.randn(n) * 0.3)
    high = close + np.abs(rng.randn(n) * 0.2)
    low = close - np.abs(rng.randn(n) * 0.2)
    open_ = close + rng.randn(n) * 0.1
    return pd.DataFrame({
        "open": open_, "high": high, "low": low, "close": close,
        "volume": rng.randint(100, 1000, n),
    })


print("=== 1. _DEFAULT_8F_WEIGHTS shape (13 factors, sums to 100.0) ===")
check("has 13 keys", len(_DEFAULT_8F_WEIGHTS) == 13)
check("sums to exactly 100.0", abs(sum(_DEFAULT_8F_WEIGHTS.values()) - 100.0) < 1e-9)
for name in NEW_INDICATORS:
    check(f"'{name}' present with non-zero default", _DEFAULT_8F_WEIGHTS.get(name, 0) > 0)
for name in ORIG_10:
    check(f"'{name}' present", name in _DEFAULT_8F_WEIGHTS)

print("\n=== 2. compute_dynamic_weights(): 3 new indicators never silently dropped ===")
df1 = make_synthetic_df(seed=11)
ind1 = indicators.calculate_all(df1)
accuracies1 = backtest_factor_accuracy(df1, ind1, lookahead=4)
check("backtest_factor_accuracy() never scores the 3 new indicators (documented, unchanged gap)",
      all(name not in accuracies1 for name in NEW_INDICATORS))

dyn_weights1 = compute_dynamic_weights(accuracies1)
check("compute_dynamic_weights() output has 13 keys", len(dyn_weights1) == 13)
check("compute_dynamic_weights() output sums to 100.0",
      abs(sum(dyn_weights1.values()) - 100.0) < 1e-9)
for name in NEW_INDICATORS:
    check(f"'{name}' present in dynamic_weights with its default weight (not 0)",
          dyn_weights1.get(name, 0) == _DEFAULT_8F_WEIGHTS[name])

print("\n=== 3. Original 10 factors: accuracy-to-weight FORMULA unchanged ===")
synthetic_accs = {
    name: {"accuracy": 55.0 + i, "sample_size": 100}
    for i, name in enumerate(ORIG_10)
}
weights2 = compute_dynamic_weights(synthetic_accs)
reserved = sum(_DEFAULT_8F_WEIGHTS[n] for n in NEW_INDICATORS)
remaining_budget = 100.0 - reserved
total_score = sum(a["accuracy"] for a in synthetic_accs.values())
formula_matches = True
for name in ORIG_10:
    expected = round(remaining_budget * (synthetic_accs[name]["accuracy"] / total_score), 2)
    if abs(expected - weights2[name]) >= 0.01:
        formula_matches = False
check("each of the 10 factors' weight == remaining_budget * (its accuracy / total_score) "
      "(same proportional-split formula as before the fix, now correctly reserving budget "
      "for the 3 previously-zeroed factors instead of assuming a full 100)", formula_matches)
check("the 3 new factors got exactly their default weight (insufficient-data branch, unchanged rule)",
      all(weights2[n] == _DEFAULT_8F_WEIGHTS[n] for n in NEW_INDICATORS))

# Near-random-accuracy penalty rule (<=52%) — must still apply identically.
near_random_accs = dict(synthetic_accs)
near_random_accs["bb"] = {"accuracy": 51.0, "sample_size": 100}
weights3 = compute_dynamic_weights(near_random_accs)
other_scores_sum = sum(v["accuracy"] for k, v in synthetic_accs.items() if k != "bb")
expected_bb = round(remaining_budget * (5.0 / (5.0 + other_scores_sum)), 2)
check("near-random accuracy (<=52%) still gets the fixed penalty score of 5 (unchanged rule)",
      abs(weights3["bb"] - expected_bb) < 0.01)

print("\n=== 4. Full simulated live-pipeline path: all 13 weights survive ===")
df2 = make_synthetic_df(seed=42)
ind2 = indicators.calculate_all(df2)
accuracies2 = backtest_factor_accuracy(df2, ind2, lookahead=4)
dyn_weights2 = compute_dynamic_weights(accuracies2)

store = settings_store.SettingsStore("/tmp/_test_phase9_pipeline_settings.json")
overlaid = _apply_settings_weight_overrides(dyn_weights2, store.get())
check("settings overlay preserves all 13 keys", len(overlaid) == 13)

confluence = analyzer.generate_confluence_signal(df2, ind2, overlaid)
check("final weights_used has 13 keys", len(confluence["weights_used"]) == 13)
check("final weights_used sums to 100.0",
      abs(sum(confluence["weights_used"].values()) - 100.0) < 1e-9)
for name in NEW_INDICATORS:
    w = confluence["weights_used"].get(name)
    check(f"final weights_used['{name}'] is present and non-zero (was silently missing before fix)",
          w is not None and w > 0)
check("signal is still one of BUY/SELL/WAIT", confluence["signal"] in ("BUY", "SELL", "WAIT"))

print("\n=== 5. Library-level default path (no dynamic_weights arg) unaffected ===")
sig_default = analyzer.generate_confluence_signal(df2, ind2)
check("default-path weights_used still has 13 keys", len(sig_default["weights_used"]) == 13)
check("default-path weights_used still sums to 100.0",
      abs(sum(sig_default["weights_used"].values()) - 100.0) < 1e-9)
check("default-path weights are byte-identical to analyzer.DEFAULT_CONFLUENCE_WEIGHTS",
      sig_default["weights_used"] == analyzer.DEFAULT_CONFLUENCE_WEIGHTS)

try:
    os.remove("/tmp/_test_phase9_pipeline_settings.json")
except OSError:
    pass

print(f"\n=== RESULT: {passed} passed, {failed} failed ===")
sys.exit(1 if failed else 0)
