"""
Phase 8.6 verification suite — Confluence Engine 10 -> 13 factors.

Run with:  python3 Quotex/tests/test_phase_8_6.py
(from the repo root, or anywhere — path setup below is self-contained).

Covers:
  1. DEFAULT_CONFLUENCE_WEIGHTS shape (13 factors, sums to exactly 100.0)
  2. _confluence_factor_votes() returns all 13 keys, including on random data
  3. Each of the 3 new detectors, when fired on hand-built candles, produces
     the correct +1/-1 vote
  4. Reliability-threshold gating: a detail dict just under the 40.0
     threshold must NOT vote (stays neutral); at/above threshold, it must
  5. Backward compatibility: an indicators dict missing the new *_detail
     keys entirely (old-format caller) must not raise and must vote neutral
  6. generate_confluence_signal() end-to-end still returns the expected
     schema and a signal/confidence pair with no exceptions
  7. indicator_registry.get_registry() reflects in_confluence=True and a
     real (non-zero) weight for all 3 new indicators

No network access, no live Quotex connection required — all synthetic
in-memory candle data, matching this project's established sandbox-testing
convention (see docs/TEST_REPORT.md). This file intentionally does NOT
depend on having a copy of a prior ZIP on disk (unlike the ad hoc diff
check used during Phase 8.6 development itself) so it keeps working
standalone in any checkout of this repo.
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
import indicator_registry as reg

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


def make_df(rows):
    return pd.DataFrame(rows, columns=["open", "high", "low", "close", "volume"])


print("=== 1. DEFAULT_CONFLUENCE_WEIGHTS shape ===")
w = analyzer.DEFAULT_CONFLUENCE_WEIGHTS
check("exactly 13 factors", len(w) == 13)
check("sums to exactly 100.0", abs(sum(w.values()) - 100.0) < 1e-9)
for k in ("wick_rejection", "liquidity_sweep", "false_breakout"):
    check(f"'{k}' present in weights", k in w)
for k in ("bb", "rsi_div", "stoch", "cci", "candle", "mean_reversion",
          "exhaustion", "round_number", "obv", "sr"):
    check(f"original factor '{k}' preserved", k in w)

print("\n=== 2. _confluence_factor_votes() on random synthetic data ===")
np.random.seed(42)
n = 250
close = 100 + np.cumsum(np.random.randn(n) * 0.3)
high = close + np.abs(np.random.randn(n) * 0.2)
low = close - np.abs(np.random.randn(n) * 0.2)
open_ = close + np.random.randn(n) * 0.1
df_rand = make_df(list(zip(open_, high, low, close, np.random.randint(100, 1000, n))))
ind_rand = indicators.calculate_all(df_rand)
votes_rand = analyzer._confluence_factor_votes(df_rand, ind_rand)
check("votes dict has 13 keys", len(votes_rand) == 13)
for k in ("wick_rejection", "liquidity_sweep", "false_breakout"):
    check(f"vote key '{k}' present", k in votes_rand)
    check(f"vote value for '{k}' is -1/0/1", votes_rand[k] in (-1, 0, 1))

print("\n=== 3. Targeted detector firing -> correct vote sign ===")
base = [[100 + i * 0.01, 100 + i * 0.01 + 0.05, 100 + i * 0.01 - 0.05,
         100 + i * 0.01 + 0.02, 500] for i in range(40)]
last_close = base[-1][3]
wick_candle = [last_close, last_close + 0.02, last_close - 1.0, last_close + 0.01, 500]
df_wr = make_df(base + [wick_candle])
ind_wr = indicators.calculate_all(df_wr)
votes_wr = analyzer._confluence_factor_votes(df_wr, ind_wr)
check("wick_rejection detail fired BUY", ind_wr["wick_rejection_detail"] is not None
      and ind_wr["wick_rejection_detail"]["direction"] == "BUY")
check("wick_rejection vote == +1", votes_wr["wick_rejection"] == 1)

base2 = [[100 - i * 0.001, 100 - i * 0.001 + 0.05, 100 - i * 0.001 - 0.05,
          100 - i * 0.001 - 0.01, 500] for i in range(25)]
recent_low = min(r[2] for r in base2)
sweep_candle = [recent_low + 0.02, recent_low + 0.05, recent_low - 0.5, recent_low + 0.03, 500]
df_ls = make_df(base2 + [sweep_candle])
ind_ls = indicators.calculate_all(df_ls)
votes_ls = analyzer._confluence_factor_votes(df_ls, ind_ls)
check("liquidity_sweep detail fired BUY", ind_ls["liquidity_sweep_detail"] is not None
      and ind_ls["liquidity_sweep_detail"]["direction"] == "BUY")
check("liquidity_sweep vote == +1", votes_ls["liquidity_sweep"] == 1)

rows = []
level = 105.0
for i in range(40):
    c = level - 2 + np.sin(i / 3) * 0.3
    rows.append([c, c + 0.15, c - 0.15, c + 0.05, 500])
for i in range(6):
    rows.append([level - 0.1, level + 0.02, level - 0.2, level - 0.05, 600])
rows.append([level - 0.05, level + 0.6, level - 0.1, level - 0.08, 700])
df_fb = make_df(rows)
ind_fb = indicators.calculate_all(df_fb)
votes_fb = analyzer._confluence_factor_votes(df_fb, ind_fb)
check("false_breakout detail fired SELL", ind_fb["false_breakout_detail"] is not None
      and ind_fb["false_breakout_detail"]["direction"] == "SELL")
check("false_breakout vote == -1", votes_fb["false_breakout"] == -1)

print("\n=== 4. Reliability-threshold gating ===")
ind_gate = dict(ind_rand)
ind_gate["wick_rejection_detail"] = {"direction": "BUY", "reliability_score": 39.9}
ind_gate["liquidity_sweep_detail"] = {"direction": "SELL", "reliability_score": 10.0}
ind_gate["false_breakout_detail"] = {"direction": "BUY", "reliability_score": 0.0}
votes_gate = analyzer._confluence_factor_votes(df_rand, ind_gate)
check("wick_rejection below threshold -> neutral", votes_gate["wick_rejection"] == 0)
check("liquidity_sweep below threshold -> neutral", votes_gate["liquidity_sweep"] == 0)
check("false_breakout below threshold -> neutral", votes_gate["false_breakout"] == 0)

ind_gate2 = dict(ind_rand)
ind_gate2["wick_rejection_detail"] = {"direction": "BUY", "reliability_score": 40.0}
votes_gate2 = analyzer._confluence_factor_votes(df_rand, ind_gate2)
check("wick_rejection at threshold (40.0) -> votes +1", votes_gate2["wick_rejection"] == 1)

print("\n=== 5. Backward compatibility (missing *_detail keys) ===")
ind_old = dict(ind_rand)
del ind_old["wick_rejection_detail"]
del ind_old["liquidity_sweep_detail"]
del ind_old["false_breakout_detail"]
try:
    votes_old = analyzer._confluence_factor_votes(df_rand, ind_old)
    check("no exception with missing detail keys", True)
    check("missing keys default to neutral (wick_rejection)", votes_old["wick_rejection"] == 0)
    check("missing keys default to neutral (liquidity_sweep)", votes_old["liquidity_sweep"] == 0)
    check("missing keys default to neutral (false_breakout)", votes_old["false_breakout"] == 0)
except Exception as e:
    check(f"no exception with missing detail keys (raised {e!r})", False)

print("\n=== 6. generate_confluence_signal() end-to-end ===")
sig = analyzer.generate_confluence_signal(df_rand, ind_rand)
check("signal in {BUY,SELL,WAIT}", sig["signal"] in ("BUY", "SELL", "WAIT"))
check("factors has 13 entries", len(sig["factors"]) == 13)
check("weights_used sums to 100.0", abs(sum(sig["weights_used"].values()) - 100.0) < 1e-9)
check("confidence field present", "confidence" in sig)
check("confidence_raw field present (Step 1, must be preserved)", "confidence_raw" in sig)
check("market_condition field present (Step 1, must be preserved)", "market_condition" in sig)

sig_fb = analyzer.generate_confluence_signal(df_fb, ind_fb)
check("second dataset also returns a valid signal", sig_fb["signal"] in ("BUY", "SELL", "WAIT"))

print("\n=== 7. indicator_registry reflects the 3 newly-connected indicators ===")
entries = reg.get_registry()
check("registry has 13 entries", len(entries) == 13)
by_id = {e["id"]: e for e in entries}
for k in ("wick_rejection", "liquidity_sweep", "false_breakout"):
    check(f"registry['{k}'].in_confluence is True", by_id[k]["in_confluence"] is True)
    check(f"registry['{k}'].weight > 0", by_id[k]["weight"] > 0)
check("NEW_INDICATOR_IDS unchanged (still 3 ids, for 'new' badge)",
      reg.NEW_INDICATOR_IDS == ["wick_rejection", "liquidity_sweep", "false_breakout"])

print(f"\n=== RESULT: {passed} passed, {failed} failed ===")
sys.exit(1 if failed else 0)
