"""
Phase 10.3 Part-2 — Explainable Signal Engine.

Turns the already-computed pipeline result (the exact dict
`webapp/app.py::_run_pipeline()` returns, and what `ScannerEngine._cache`
stores verbatim per (asset, timeframe)) into a structured, human-readable
explanation: which checks passed/failed, the Hard Gates that passed/
failed, the Final Filter Score, Confidence, plain-English Reasons, and
Warnings.

This module NEVER recomputes an indicator, a confluence vote, a filter-
score gate, or a regime classification — it only reads fields that
`analyzer.calculate_filter_score()`, `analyzer.generate_confluence_signal()`,
`indicators.calculate_all()`, and `regime_pipeline.compute_regime_adjusted_
weights()` already produced upstream (in `_run_pipeline()`). Zero import of
analyzer.py/backtest.py/indicators.py — pure function of a plain dict,
independently testable with a hand-built dict.

Nine checks are reported (✔ / ✖), each derived from data already computed:
  Trend             — filter_breakdown["ema_trend"]["passed"]
  Momentum          — majority of rsi_div/stoch/cci confluence votes agree
                       with the signal direction
  Volatility        — filter_breakdown["atr"]["passed"]
  Volume            — the obv confluence vote agrees with the signal direction
  Price Action      — filter_breakdown["candlestick"]["passed"]
  Support/Resistance— filter_breakdown["support_resistance"]["passed"]
  ADX               — filter_breakdown["adx"]["passed"]
  MTF               — filter_breakdown["multi_timeframe"]["passed"]
  Regime            — the detected regime is one this project's own
                       regime_weight_engine.py already treats as trend-
                       continuation-favorable in the signal's direction
                       (Strong Uptrend/Strong Downtrend/Breakout) — reusing
                       that existing classification, not a new one.

For a WAIT signal there is no direction to confirm momentum/volume/regime
against, so those three checks are reported False with an explicit reason
rather than guessed from the (non-actionable) legacy signal.
"""
from __future__ import annotations
from typing import Any, Dict, List, Optional

# Presentation-only label maps — mirrors the existing, local (not imported)
# _FACTOR_LABELS convention already used in webapp/app.py for the same
# reason: analyzer.py's gate/factor keys are read as plain strings, never
# imported as constants, so this module has zero import-time coupling to
# analyzer.py.
_GATE_LABELS = {
    "ema_trend": "Trend (EMA)",
    "adx": "ADX Strength",
    "atr": "Volatility (ATR)",
    "support_resistance": "Support/Resistance",
    "multi_timeframe": "Multi-Timeframe",
    "payout": "Payout",
    "candlestick": "Candlestick Pattern",
}

_MOMENTUM_FACTOR_KEYS = ("rsi_div", "stoch", "cci")
_VOLUME_FACTOR_KEY = "obv"

# Regimes this project's own regime_weight_engine.py already treats as
# trend-continuation-favorable (boosted obv/sr/candle, discounted mean-
# reversion) in a given direction — reused here as-is, not redefined.
_REGIME_SUPPORTS_BUY = {"Strong Uptrend", "Breakout"}
_REGIME_SUPPORTS_SELL = {"Strong Downtrend", "Breakout"}


def _gate_passed(filter_breakdown: Dict[str, Any], key: str) -> bool:
    entry = (filter_breakdown or {}).get(key) or {}
    return bool(entry.get("passed"))


def _factor_vote_label(factors: List[Dict[str, Any]], key: str) -> Optional[str]:
    for f in factors or []:
        if f.get("key") == key:
            return f.get("vote")  # "BULLISH" / "BEARISH" / "NEUTRAL"
    return None


def _momentum_check(factors: List[Dict[str, Any]], direction: str) -> Dict[str, Any]:
    wanted = "BULLISH" if direction == "BUY" else "BEARISH"
    votes = [_factor_vote_label(factors, k) for k in _MOMENTUM_FACTOR_KEYS]
    votes = [v for v in votes if v is not None]
    if not votes:
        return {"passed": False, "detail": "No momentum factor data available (rsi_div/stoch/cci)."}
    agreeing = sum(1 for v in votes if v == wanted)
    passed = agreeing >= (len(votes) / 2.0)
    return {
        "passed": passed,
        "detail": f"{agreeing}/{len(votes)} momentum factors (RSI Divergence/Stochastic/CCI) agree with {direction}.",
    }


def _volume_check(factors: List[Dict[str, Any]], direction: str) -> Dict[str, Any]:
    wanted = "BULLISH" if direction == "BUY" else "BEARISH"
    vote = _factor_vote_label(factors, _VOLUME_FACTOR_KEY)
    if vote is None:
        return {"passed": False, "detail": "No OBV volume data available."}
    return {"passed": vote == wanted, "detail": f"OBV vote is {vote}, signal direction is {direction}."}


def _regime_check(regime: Dict[str, Any], direction: str) -> Dict[str, Any]:
    name = (regime or {}).get("name", "Unknown")
    supports = _REGIME_SUPPORTS_BUY if direction == "BUY" else _REGIME_SUPPORTS_SELL
    passed = name in supports
    return {
        "passed": passed,
        "detail": f"Regime is '{name}' — "
                  + ("consistent with continuation in this direction." if passed
                     else "not one of this direction's trend-continuation regimes."),
    }


def explain_signal(result: Dict[str, Any]) -> Dict[str, Any]:
    """
    Build a full explanation from an already-computed pipeline result dict
    (same shape `_run_pipeline()` returns / `ScannerEngine._cache` stores).

    Returns:
        {
          "signal": "BUY"/"SELL"/"WAIT",
          "confidence": int,
          "final_filter_score": float,
          "checks": {  # each: {"passed": bool, "detail": str}
            "trend", "momentum", "volatility", "volume", "price_action",
            "support_resistance", "adx", "mtf", "regime"
          },
          "hard_gates_passed": [...],
          "hard_gates_failed": [...],
          "reasons": [...],
          "warnings": [...],
        }

    Never raises on a partially-populated `result` — every field is read
    via .get() with a safe default, and a missing/empty `result` yields an
    explanation with every check False and a single warning explaining why,
    rather than an exception.
    """
    confluence = result.get("confluence") or {}
    signal = confluence.get("signal", "WAIT")
    confidence = confluence.get("confidence", 0)
    filter_breakdown = result.get("filter_breakdown") or {}
    factors = result.get("factors") or []
    regime = result.get("regime") or {}
    multi_tf_status = result.get("multi_tf_status") or {}

    if not result:
        return {
            "signal": "WAIT",
            "confidence": 0,
            "final_filter_score": 0.0,
            "checks": {
                k: {"passed": False, "detail": "No pipeline result available."}
                for k in ("trend", "momentum", "volatility", "volume", "price_action",
                          "support_resistance", "adx", "mtf", "regime")
            },
            "hard_gates_passed": [],
            "hard_gates_failed": [],
            "reasons": [],
            "warnings": ["No signal data was provided to explain."],
        }

    checks: Dict[str, Dict[str, Any]] = {
        "trend": {
            "passed": _gate_passed(filter_breakdown, "ema_trend"),
            "detail": f"Direction is {result.get('trend', 'unknown')}.",
        },
        "volatility": {
            "passed": _gate_passed(filter_breakdown, "atr"),
            "detail": f"ATR%={filter_breakdown.get('atr', {}).get('value')}, "
                      f"level={filter_breakdown.get('atr', {}).get('level')}.",
        },
        "price_action": {
            "passed": _gate_passed(filter_breakdown, "candlestick"),
            "detail": f"Candlestick pattern: {filter_breakdown.get('candlestick', {}).get('value') or 'none detected'}.",
        },
        "support_resistance": {
            "passed": _gate_passed(filter_breakdown, "support_resistance"),
            "detail": f"Safe entry (S/R): {filter_breakdown.get('support_resistance', {}).get('value')}.",
        },
        "adx": {
            "passed": _gate_passed(filter_breakdown, "adx"),
            "detail": f"ADX={filter_breakdown.get('adx', {}).get('value')}.",
        },
        "mtf": {
            "passed": _gate_passed(filter_breakdown, "multi_timeframe"),
            "detail": f"Multi-timeframe status: {multi_tf_status.get('status', 'UNAVAILABLE')}.",
        },
    }

    if signal in ("BUY", "SELL"):
        checks["momentum"] = _momentum_check(factors, signal)
        checks["volume"] = _volume_check(factors, signal)
        checks["regime"] = _regime_check(regime, signal)
    else:
        no_direction = {"passed": False, "detail": "Signal is WAIT — no directional confirmation to check."}
        checks["momentum"] = dict(no_direction)
        checks["volume"] = dict(no_direction)
        checks["regime"] = dict(no_direction)

    hard_gates_passed = [
        {"gate": g, "label": _GATE_LABELS.get(g, g)} for g in result.get("passed_filters") or []
    ]
    hard_gates_failed = [
        {"gate": g, "label": _GATE_LABELS.get(g, g)} for g in result.get("failed_filters") or []
    ]

    reasons: List[str] = []
    if signal in ("BUY", "SELL"):
        reasons.append(f"{signal} because {sum(1 for c in checks.values() if c['passed'])}/9 checks confirmed.")
    for name, c in checks.items():
        if c["passed"]:
            reasons.append(f"{name.replace('_', ' ').title()}: {c['detail']}")
    for r in regime.get("reasons") or []:
        reasons.append(f"Regime: {r}")

    warnings: List[str] = []
    for name, c in checks.items():
        if not c["passed"]:
            warnings.append(f"{name.replace('_', ' ').title()} did not confirm: {c['detail']}")
    if signal == "WAIT":
        warnings.append("Signal is WAIT — the checks above explain why no trade is currently recommended.")
    if regime.get("name") in (None, "Unknown", "Uncertain / Mixed"):
        warnings.append(f"Market regime is '{regime.get('name', 'Unknown')}' — regime-based weighting was not applied.")

    return {
        "signal": signal,
        "confidence": confidence,
        "final_filter_score": result.get("filter_score", 0.0),
        "checks": checks,
        "hard_gates_passed": hard_gates_passed,
        "hard_gates_failed": hard_gates_failed,
        "reasons": reasons,
        "warnings": warnings,
    }
