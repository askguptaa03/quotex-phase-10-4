"""
Phase 10.3 Part-1 — Regime Pipeline (integration orchestrator).

Composes the three additive modules of this phase into a single call so
callers (run_analysis.py, webapp/app.py) only need one integration point:

    regime_detector.detect_market_regime(ind)
        -> regime_weight_engine.apply_regime_adaptive_weights(weights, regime)
            -> dynamic_indicator_selector.apply_dynamic_indicator_selection(weights, regime)

Does not import analyzer.py, backtest.py, or indicators.py — it only
consumes the `ind` dict and a `weights` dict the caller already has.
"""
from __future__ import annotations
from typing import Any, Dict

from regime_detector import detect_market_regime
from regime_weight_engine import apply_regime_adaptive_weights
from dynamic_indicator_selector import apply_dynamic_indicator_selection


def compute_regime_adjusted_weights(base_weights: Dict[str, float],
                                     ind: Dict[str, Any]) -> Dict[str, Any]:
    """
    Full Phase 10.3 Part-1 pipeline: detect the regime from `ind`, then
    apply the adaptive-weight layer and the dynamic-selection layer on top
    of `base_weights` (e.g. the dynamic_weights already computed by
    backtest.compute_dynamic_weights() or the precomputed deep-backtest
    weights) in sequence.

    Returns:
        {
          "final_weights": dict, same keys as base_weights, summing to
                           100.0 (unchanged from base_weights if the
                           regime is Uncertain/Mixed or Unknown),
          "regime": the full regime_detector.detect_market_regime() output,
          "adaptive_weight_step": the full apply_regime_adaptive_weights() output,
          "selection_step": the full apply_dynamic_indicator_selection() output,
        }

    Never raises for a well-formed `ind`/`base_weights` pair; if `ind` is
    missing required fields, the regime comes back "Unknown" and both
    downstream steps become no-ops — final_weights == base_weights.
    """
    regime_result = detect_market_regime(ind)
    weight_step = apply_regime_adaptive_weights(base_weights, regime_result)
    selection_step = apply_dynamic_indicator_selection(weight_step["weights"], regime_result)

    return {
        "final_weights": selection_step["weights"],
        "regime": regime_result,
        "adaptive_weight_step": weight_step,
        "selection_step": selection_step,
    }
