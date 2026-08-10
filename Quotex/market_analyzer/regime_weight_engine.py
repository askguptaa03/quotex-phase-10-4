"""
Phase 10.3 Part-1 — Adaptive Weight Engine.

Layers a deterministic, hand-authored per-regime multiplier table on top of
whatever confluence-factor weights the caller already computed (defaults,
backtest-derived dynamic weights, or precomputed deep-backtest weights) —
exactly the same "scaling layer, never a replacement" idiom already used by
webapp/app.py's `_apply_settings_weight_overrides()`.

This module NEVER:
  - recomputes any indicator,
  - changes analyzer.DEFAULT_CONFLUENCE_WEIGHTS or the confluence vote logic,
  - touches backtest.compute_dynamic_weights()'s accuracy math.

It only rescales the 13 existing confluence-factor weights
(bb, rsi_div, stoch, cci, candle, mean_reversion, exhaustion, round_number,
obv, sr, wick_rejection, liquidity_sweep, false_breakout) based on which
factor TYPES are more/less trustworthy in the currently-detected regime —
e.g. mean-reversion factors (bb, stoch, cci, mean_reversion, round_number)
are boosted in ranging markets and reduced in trending ones; reversal
detectors (wick_rejection, liquidity_sweep, false_breakout, candle) are
boosted in a detected Reversal and reduced in a strong trend.

Every multiplier below is a fixed, documented constant — not learned, not
backtest-fitted. Nothing here is ML.
"""
from __future__ import annotations
from typing import Any, Dict, List

from regime_detector import (
    REGIME_STRONG_UPTREND, REGIME_STRONG_DOWNTREND, REGIME_SIDEWAYS_RANGE,
    REGIME_HIGH_VOLATILITY, REGIME_LOW_VOLATILITY, REGIME_BREAKOUT,
    REGIME_REVERSAL, REGIME_UNCERTAIN, REGIME_UNKNOWN,
)

# ─── Per-regime factor multiplier table ─────────────────────────────────────
# Factor not listed for a regime => multiplier 1.0 (unchanged).
# Uncertain/Mixed and Unknown are intentionally absent — see
# apply_regime_adaptive_weights()'s no-op branch below: when the regime
# itself is ambiguous or unclassifiable, this engine does not guess either,
# and leaves whatever weights were already in effect untouched.
REGIME_FACTOR_MULTIPLIERS: Dict[str, Dict[str, float]] = {
    # Trend-continuation favored; mean-reversion factors are prone to
    # fighting the trend and are discounted.
    REGIME_STRONG_UPTREND: {
        "bb": 0.6, "rsi_div": 0.8, "stoch": 0.6, "cci": 0.6, "candle": 1.1,
        "mean_reversion": 0.5, "exhaustion": 0.9, "round_number": 0.7,
        "obv": 1.3, "sr": 1.2, "wick_rejection": 0.7,
        "liquidity_sweep": 0.7, "false_breakout": 0.7,
    },
    REGIME_STRONG_DOWNTREND: {
        "bb": 0.6, "rsi_div": 0.8, "stoch": 0.6, "cci": 0.6, "candle": 1.1,
        "mean_reversion": 0.5, "exhaustion": 0.9, "round_number": 0.7,
        "obv": 1.3, "sr": 1.2, "wick_rejection": 0.7,
        "liquidity_sweep": 0.7, "false_breakout": 0.7,
    },
    # Range-bound: mean-reversion factors favored, trend-following (obv)
    # discounted since there's no sustained trend to confirm.
    REGIME_SIDEWAYS_RANGE: {
        "bb": 1.3, "rsi_div": 1.1, "stoch": 1.3, "cci": 1.2, "candle": 1.0,
        "mean_reversion": 1.3, "exhaustion": 1.1, "round_number": 1.2,
        "obv": 0.7, "sr": 1.1, "wick_rejection": 1.1,
        "liquidity_sweep": 1.1, "false_breakout": 1.1,
    },
    REGIME_LOW_VOLATILITY: {
        "bb": 1.2, "rsi_div": 1.0, "stoch": 1.2, "cci": 1.1, "candle": 0.9,
        "mean_reversion": 1.3, "exhaustion": 1.0, "round_number": 1.2,
        "obv": 0.8, "sr": 1.0, "wick_rejection": 0.8,
        "liquidity_sweep": 0.8, "false_breakout": 0.8,
    },
    # Turbulent, non-directional: discount noise-prone single-bar/tight
    # geometric factors; keep confirmation-heavy ones close to neutral.
    REGIME_HIGH_VOLATILITY: {
        "bb": 0.8, "rsi_div": 0.9, "stoch": 0.8, "cci": 0.8, "candle": 0.8,
        "mean_reversion": 0.7, "exhaustion": 0.7, "round_number": 0.6,
        "obv": 1.0, "sr": 1.0, "wick_rejection": 0.9,
        "liquidity_sweep": 0.9, "false_breakout": 0.9,
    },
    # Continuation of a fresh breakout favored; mean-reversion factors
    # would fight the move and are strongly discounted.
    REGIME_BREAKOUT: {
        "bb": 0.5, "rsi_div": 0.8, "stoch": 0.5, "cci": 0.5, "candle": 1.1,
        "mean_reversion": 0.5, "exhaustion": 0.8, "round_number": 0.6,
        "obv": 1.3, "sr": 1.3, "wick_rejection": 0.8,
        "liquidity_sweep": 0.8, "false_breakout": 0.8,
    },
    # Reversal detectors and divergence favored; pure trend-continuation
    # factors discounted since the trend is (per this regime) turning.
    REGIME_REVERSAL: {
        "bb": 1.1, "rsi_div": 1.3, "stoch": 1.1, "cci": 1.1, "candle": 1.3,
        "mean_reversion": 1.0, "exhaustion": 1.1, "round_number": 1.0,
        "obv": 0.8, "sr": 0.9, "wick_rejection": 1.3,
        "liquidity_sweep": 1.3, "false_breakout": 1.3,
    },
}


def apply_regime_adaptive_weights(weights: Dict[str, float],
                                   regime_result: Dict[str, Any]) -> Dict[str, Any]:
    """
    Rescale `weights` (any dict of factor_name -> weight, e.g. dynamic_weights
    from backtest.compute_dynamic_weights()) according to the regime in
    `regime_result` (the output of regime_detector.detect_market_regime()).

    Returns:
        {
          "weights": {same keys as input, rescaled, summing to 100.0
                      if the input summed to > 0},
          "regime": the regime name used,
          "applied": bool — False for Uncertain/Mixed/Unknown (no-op),
          "notes": [explainability strings — which factor changed and why],
        }

    Uncertain/Mixed and Unknown regimes are a deliberate no-op: this engine
    never guesses an adjustment when the regime itself isn't confidently known.
    """
    regime = regime_result.get("regime", REGIME_UNKNOWN)
    multipliers = REGIME_FACTOR_MULTIPLIERS.get(regime)

    if not multipliers or regime in (REGIME_UNCERTAIN, REGIME_UNKNOWN):
        return {
            "weights": dict(weights),
            "regime": regime,
            "applied": False,
            "notes": [
                f"Regime '{regime}' -> no adaptive weight adjustment applied; "
                "weights passed through unchanged."
            ],
        }

    adjusted: Dict[str, float] = {}
    notes: List[str] = []
    for factor, base_w in weights.items():
        mult = multipliers.get(factor, 1.0)
        new_w = base_w * mult
        adjusted[factor] = new_w
        if mult != 1.0:
            notes.append(f"{factor}: {base_w:.2f} x {mult} = {new_w:.2f} (regime={regime})")

    total = sum(adjusted.values())
    if total > 0:
        adjusted = {k: round(v * 100.0 / total, 4) for k, v in adjusted.items()}
        # Same "assign rounding residual to the largest weight" convention
        # already used by webapp/app.py's _apply_settings_weight_overrides()
        # and settings_store.get_effective_dynamic_weights().
        drift = round(100.0 - sum(adjusted.values()), 4)
        if drift != 0.0:
            top_key = max(adjusted, key=adjusted.get)
            adjusted[top_key] = round(adjusted[top_key] + drift, 4)

    return {"weights": adjusted, "regime": regime, "applied": True, "notes": notes}
