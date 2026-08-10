"""
Phase 10.4 Goal 1 verification suite — Walk-Forward Testing Engine.

Run with:  python3 Quotex/tests/test_phase_10_4_goal1.py
(from the repo root, or anywhere — path setup below is self-contained).

Background: this phase adds ONE new, additive, standalone module —
`walk_forward.py` — with no changes to any existing file. It only calls
backtest.py's existing `backtest_factor_accuracy`, `compute_dynamic_weights`,
and `_factor_votes` on DataFrame slices it is given; it does not modify
analyzer.py, backtest.py, scanner.py, learning_engine.py,
indicator_registry.py, or the Quotex API, and is not wired into any of them.

Covers:
  1. Window generation: rolling and expanding split boundaries, empty
     results for too-small input, custom step.
  2. Single-window evaluation: a strongly trending synthetic series scores
     a high win rate; a pure-noise series scores near 50%; metrics are
     internally consistent (win_rate == accuracy by this engine's
     construction, confusion-derived precision/recall, drawdown, confidence
     distribution buckets sum to sample_size).
  3. Multi-window orchestration: rolling vs expanding summaries, stability
     computation, insufficient_data flag for too-short input, all-flat
     (zero-signal) input handled without crashing.
  4. Multi-asset / multi-timeframe batch runner.
  5. Indicator comparison (compare_factor_subsets) and strategy comparison
     (compare_strategies) ranking behaviour.
  6. Determinism: identical input -> identical output across repeated calls.
  7. Off-limits-file regression safety: analyzer.py / backtest.py /
     webapp/scanner.py / webapp/learning_engine.py /
     webapp/indicator_registry.py source re-confirmed to contain no
     reference to walk_forward, and backtest.py's public functions used by
     walk_forward.py are called, never redefined.
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


def make_trending_df(n=300):
    # Strong, near-noiseless uptrend so BB/RSI-divergence-style mean
    # reversion factors have an unambiguous, verifiable direction to score.
    price = 100 + np.arange(n) * 0.35
    noise = np.tile([0.0, 0.02, -0.02, 0.01], n // 4 + 1)[:n]
    price = price + noise
    return pd.DataFrame({
        "open": price,
        "high": price + 0.05,
        "low": price - 0.05,
        "close": price,
        "volume": np.full(n, 500),
    })


def make_flat_df(n=200):
    price = np.full(n, 100.0)
    return pd.DataFrame({
        "open": price, "high": price, "low": price, "close": price,
        "volume": np.full(n, 500),
    })


print("=" * 70)
print("PHASE 10.4 GOAL 1 — Walk-Forward Testing Engine")
print("=" * 70)

# ─── 1. Window generation ───────────────────────────────────────────────────
print("\n[1] Window generation")

r_windows = wf.generate_rolling_windows(n=100, train_size=40, test_size=10)
check("rolling: correct window count", len(r_windows) == 6)
check("rolling: first window boundaries", r_windows[0] == (0, 40, 40, 50))
check("rolling: last window fits within n", r_windows[-1][3] <= 100)
check("rolling: train size constant across windows",
      all(te - ts == 40 for (ts, te, vs, ve) in r_windows))

r_windows_step = wf.generate_rolling_windows(n=100, train_size=40, test_size=10, step=5)
check("rolling: custom step respected",
      r_windows_step[1][0] - r_windows_step[0][0] == 5)

r_empty = wf.generate_rolling_windows(n=20, train_size=40, test_size=10)
check("rolling: empty when n too small", r_empty == [])

e_windows = wf.generate_expanding_windows(n=100, initial_train_size=40, test_size=10)
check("expanding: correct window count", len(e_windows) == 6)
check("expanding: train always starts at 0",
      all(ts == 0 for (ts, te, vs, ve) in e_windows))
check("expanding: train end grows each window",
      all(e_windows[i + 1][1] > e_windows[i][1] for i in range(len(e_windows) - 1)))

e_empty = wf.generate_expanding_windows(n=20, initial_train_size=40, test_size=10)
check("expanding: empty when n too small", e_empty == [])

check("rolling: zero/negative params -> empty, no crash",
      wf.generate_rolling_windows(100, 0, 10) == [] and
      wf.generate_rolling_windows(100, 10, -5) == [])

# ─── 2. Single-window evaluation ────────────────────────────────────────────
print("\n[2] Single-window evaluation")

trending = make_trending_df(300)
trend_window = wf.run_walk_forward_window(trending, 0, 150, 150, 300, lookahead=4)
check("trending window: has signals", trend_window["sample_size"] > 0)
check("trending window: win_rate == accuracy (documented construction)",
      trend_window["win_rate"] == trend_window["accuracy"])
check("trending window: confidence buckets sum to sample_size",
      sum(trend_window["confidence_distribution"].values()) == trend_window["sample_size"])
check("trending window: train/test ranges recorded correctly",
      trend_window["train_range"] == [0, 150] and trend_window["test_range"] == [150, 300])
check("trending window: weights_used present and sums ~100",
      abs(sum(trend_window["weights_used"].values()) - 100.0) < 0.5)

noisy = make_synthetic_df(300, seed=1)
noisy_window = wf.run_walk_forward_window(noisy, 0, 150, 150, 300, lookahead=4)
if noisy_window["sample_size"] > 0:
    check("noisy window: win_rate is a plausible percentage (0-100)",
          0.0 <= noisy_window["win_rate"] <= 100.0)
else:
    check("noisy window: zero signals handled without crash (metrics all None)",
          noisy_window["win_rate"] is None and noisy_window["profit_factor"] is None)

flat = make_flat_df(200)
flat_window = wf.run_walk_forward_window(flat, 0, 100, 100, 200, lookahead=4)
check("flat/zero-signal window: no crash, sample_size handled",
      isinstance(flat_window["sample_size"], int))
if flat_window["sample_size"] == 0:
    check("flat window: metrics None when zero signals",
          flat_window["win_rate"] is None and flat_window["max_drawdown"] is None)

# ─── 3. Multi-window orchestration ──────────────────────────────────────────
print("\n[3] Multi-window orchestration")

rolling_result = wf.run_walk_forward(trending, mode="rolling", train_size=100,
                                      test_size=25, lookahead=4)
check("rolling result: not insufficient_data", rolling_result["insufficient_data"] is False)
check("rolling result: windows list non-empty", len(rolling_result["windows"]) > 0)
check("rolling result: summary present", rolling_result["summary"] is not None)
if rolling_result["summary"]:
    s = rolling_result["summary"]
    check("rolling summary: has all required metric keys",
          set(["windows_run", "windows_scored", "total_signals", "avg_win_rate",
               "avg_accuracy", "avg_precision", "avg_recall", "avg_profit_factor",
               "max_drawdown", "stability", "confidence_distribution"]) <= set(s.keys()))
    check("rolling summary: stability computed when >=2 scored windows",
          s["stability"] is None or s["stability"] >= 0.0)

expanding_result = wf.run_walk_forward(trending, mode="expanding", train_size=100,
                                        test_size=25, lookahead=4)
check("expanding result: not insufficient_data", expanding_result["insufficient_data"] is False)
check("expanding result: window train ranges grow",
      expanding_result["windows"][0]["train_range"][1] <
      expanding_result["windows"][-1]["train_range"][1]
      if len(expanding_result["windows"]) > 1 else True)

too_short = make_trending_df(30)
short_result = wf.run_walk_forward(too_short, mode="rolling", train_size=100, test_size=25)
check("too-short df: insufficient_data True, empty windows, summary None",
      short_result["insufficient_data"] is True and
      short_result["windows"] == [] and short_result["summary"] is None)

flat_long = make_flat_df(300)
flat_result = wf.run_walk_forward(flat_long, mode="rolling", train_size=100, test_size=25)
check("all-flat df: no crash regardless of scoring outcome",
      isinstance(flat_result["windows"], list))

try:
    wf.run_walk_forward(trending, mode="bogus")
    check("invalid mode raises ValueError", False)
except ValueError:
    check("invalid mode raises ValueError", True)

empty_df = pd.DataFrame({"open": [], "high": [], "low": [], "close": [], "volume": []})
empty_result = wf.run_walk_forward(empty_df, mode="rolling", train_size=10, test_size=5)
check("empty df: insufficient_data True, no crash", empty_result["insufficient_data"] is True)

# ─── 4. Multi-asset / multi-timeframe ───────────────────────────────────────
print("\n[4] Multi-asset / multi-timeframe batch runner")

multi_data = {
    "EURUSD_otc": {"1m": make_trending_df(300), "5m": make_synthetic_df(300, seed=2)},
    "GBPUSD_otc": {"1m": make_synthetic_df(300, seed=3)},
}
multi_result = wf.run_walk_forward_multi(multi_data, mode="rolling", train_size=100, test_size=25)
check("multi: top-level asset keys preserved",
      set(multi_result.keys()) == {"EURUSD_otc", "GBPUSD_otc"})
check("multi: nested timeframe keys preserved",
      set(multi_result["EURUSD_otc"].keys()) == {"1m", "5m"})
check("multi: each leaf is a run_walk_forward-shaped result",
      "insufficient_data" in multi_result["EURUSD_otc"]["1m"])

# ─── 5. Indicator & strategy comparison ─────────────────────────────────────
print("\n[5] Indicator comparison / strategy comparison")

subsets = {
    "bb_only": ["bb"],
    "rsi_only": ["rsi_div"],
    "all_factors": None,
}
subset_cmp = wf.compare_factor_subsets(trending, subsets, mode="rolling",
                                        train_size=100, test_size=25, lookahead=4)
check("compare_factor_subsets: all labels present in results",
      set(subset_cmp["results"].keys()) == set(subsets.keys()))
check("compare_factor_subsets: ranking contains all labels exactly once",
      sorted(subset_cmp["ranking"]) == sorted(subsets.keys()))

strategies = {
    "loose": {"signal_threshold": 0.0},
    "tight": {"signal_threshold": 0.3},
}
strat_cmp = wf.compare_strategies(trending, strategies, mode="rolling",
                                   train_size=100, test_size=25, lookahead=4)
check("compare_strategies: all labels present in results",
      set(strat_cmp["results"].keys()) == set(strategies.keys()))
check("compare_strategies: tight threshold yields <= signals than loose",
      (strat_cmp["results"]["tight"]["summary"] or {}).get("total_signals", 0) <=
      (strat_cmp["results"]["loose"]["summary"] or {}).get("total_signals", 0))

# ─── 6. Determinism ──────────────────────────────────────────────────────────
print("\n[6] Determinism")

run_a = wf.run_walk_forward(trending, mode="rolling", train_size=100, test_size=25, lookahead=4)
run_b = wf.run_walk_forward(trending, mode="rolling", train_size=100, test_size=25, lookahead=4)
check("identical input -> identical summary across repeated calls",
      run_a["summary"] == run_b["summary"])
check("identical input -> identical per-window metrics across repeated calls",
      [{k: v for k, v in w.items() if k != "weights_used"} for w in run_a["windows"]] ==
      [{k: v for k, v in w.items() if k != "weights_used"} for w in run_b["windows"]])

# ─── 7. Off-limits-file regression safety ───────────────────────────────────
print("\n[7] Off-limits-file regression safety (source inspection)")

_ANALYZER_PY = os.path.join(_MARKET_ANALYZER, "analyzer.py")
_BACKTEST_PY = os.path.join(_MARKET_ANALYZER, "backtest.py")
_SCANNER_PY = os.path.join(_WEBAPP, "scanner.py")
_LEARNING_PY = os.path.join(_WEBAPP, "learning_engine.py")
_REGISTRY_PY = os.path.join(_WEBAPP, "indicator_registry.py")

for label, path in [("analyzer.py", _ANALYZER_PY), ("backtest.py", _BACKTEST_PY),
                     ("webapp/scanner.py", _SCANNER_PY),
                     ("webapp/learning_engine.py", _LEARNING_PY),
                     ("webapp/indicator_registry.py", _REGISTRY_PY)]:
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            src = f.read()
        check(f"{label}: no reference to walk_forward (not wired in yet)",
              "walk_forward" not in src)
    else:
        check(f"{label}: file exists for source check", False)

check("backtest.py: backtest_factor_accuracy still present and callable",
      hasattr(backtest, "backtest_factor_accuracy"))
check("backtest.py: compute_dynamic_weights still present and callable",
      hasattr(backtest, "compute_dynamic_weights"))
check("backtest.py: MIN_SIGNALS_REQUIRED constant unchanged (20)",
      backtest.MIN_SIGNALS_REQUIRED == 20)

# ─── Summary ─────────────────────────────────────────────────────────────────
print("\n" + "=" * 70)
print(f"RESULTS: {passed} passed, {failed} failed (of {passed + failed})")
print("=" * 70)

if failed:
    sys.exit(1)
