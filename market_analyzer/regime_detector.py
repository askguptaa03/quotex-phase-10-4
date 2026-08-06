"""
Phase 10.3 Part-1 — Market Regime Detection.

Classifies the current market into exactly one of 8 named regimes (or
"Unknown" when the inputs don't support a confident classification) using
ONLY fields already produced by indicators.calculate_all(). No indicator is
recomputed here — this module is a pure, read-only classifier layered on
top of the existing indicator pipeline.

Design rules (see Phase 10.3 Part-1 scope):
  - Pure deterministic logic. No ML, no randomness, no learned weights.
  - Every decision is explainable: the returned "reasons" list states
    exactly which fields and thresholds drove the classification.
  - "Unknown" is returned (never guessed past) when required fields are
    missing/NaN — see _missing_fields().
  - Independently testable: detect_market_regime() takes a plain dict and
    has no dependency on pandas, the Quotex API, or any other module in
    this project. A unit test can call it with a hand-built dict.

The 8 regimes:
  Strong Uptrend, Strong Downtrend, Sideways Range, High Volatility,
  Low Volatility, Breakout, Reversal, Uncertain / Mixed
"""
from __future__ import annotations
import math
from typing import Any, Dict, List, Optional

# ─── Regime name constants ─────────────────────────────────────────────────
REGIME_STRONG_UPTREND   = "Strong Uptrend"
REGIME_STRONG_DOWNTREND = "Strong Downtrend"
REGIME_SIDEWAYS_RANGE   = "Sideways Range"
REGIME_HIGH_VOLATILITY  = "High Volatility"
REGIME_LOW_VOLATILITY   = "Low Volatility"
REGIME_BREAKOUT         = "Breakout"
REGIME_REVERSAL         = "Reversal"
REGIME_UNCERTAIN        = "Uncertain / Mixed"
REGIME_UNKNOWN          = "Unknown"

ALL_REGIMES = (
    REGIME_STRONG_UPTREND, REGIME_STRONG_DOWNTREND, REGIME_SIDEWAYS_RANGE,
    REGIME_HIGH_VOLATILITY, REGIME_LOW_VOLATILITY, REGIME_BREAKOUT,
    REGIME_REVERSAL, REGIME_UNCERTAIN, REGIME_UNKNOWN,
)

# Reuses the same 40.0 reliability convention already established in
# analyzer.py for CANDLE_RELIABILITY_VOTE_THRESHOLD / SR_RELIABILITY_VOTE_THRESHOLD
# / WICK_REJECTION_VOTE_THRESHOLD / LIQUIDITY_SWEEP_VOTE_THRESHOLD /
# FALSE_BREAKOUT_VOTE_THRESHOLD — a value, not a duplicated calculation.
DEFAULT_RELIABILITY_THRESHOLD = 40.0

# Reuses the same value as config.ADX_TRENDING (25). Kept as a local default
# (rather than importing config.py) so this module has zero import-time
# dependencies and stays independently testable with a plain dict.
DEFAULT_ADX_TRENDING_THRESHOLD = 25.0

# Fields this module reads directly from calculate_all()'s output. If any of
# these are missing or NaN, we cannot classify and return Unknown.
_REQUIRED_FIELDS = (
    "adx", "di_plus", "di_minus", "direction", "slope_pct",
    "level", "atr_pct", "bb_width_pct", "price", "bb_upper", "bb_lower", "rsi",
)

# Reversal-type detail dicts already computed by indicators.calculate_all().
# Each is {"direction":..., "reliability_score":...} or None.
_REVERSAL_DETAIL_KEYS = (
    ("candlestick_pattern_detail", "candlestick pattern"),
    ("wick_rejection_detail",      "wick rejection"),
    ("liquidity_sweep_detail",     "liquidity sweep"),
    ("false_breakout_detail",      "false breakout"),
)


def _is_bad(value: Any) -> bool:
    if value is None:
        return True
    try:
        return isinstance(value, float) and math.isnan(value)
    except Exception:
        return True


def _missing_fields(ind: Dict[str, Any]) -> List[str]:
    return [k for k in _REQUIRED_FIELDS if _is_bad(ind.get(k))]


def _reliable_detail(ind: Dict[str, Any], key: str, threshold: float) -> Optional[Dict[str, Any]]:
    detail = ind.get(key)
    if not isinstance(detail, dict):
        return None
    score = detail.get("reliability_score")
    if _is_bad(score):
        return None
    try:
        return detail if float(score) >= threshold else None
    except (TypeError, ValueError):
        return None


def detect_market_regime(
    ind: Dict[str, Any],
    *,
    adx_trending_threshold: float = DEFAULT_ADX_TRENDING_THRESHOLD,
    reliability_threshold: float = DEFAULT_RELIABILITY_THRESHOLD,
) -> Dict[str, Any]:
    """
    Classify the current market regime from an indicators dict (the output
    of indicators.calculate_all(), or any dict exposing the same keys).

    Returns:
        {
          "regime": one of ALL_REGIMES,
          "confidence": float 0-100 (geometry/threshold-derived, not learned),
          "reasons": [explainability strings, in decision order],
          "metrics_used": {snapshot of the raw fields that drove the decision},
        }

    Evaluation order (first matching rule wins — kept deterministic and
    mutually exclusive by design):
      1. Reversal        — a reliable (>= reliability_threshold) reversal-type
                            detail (candlestick / wick rejection / liquidity
                            sweep / false breakout) fired on the latest bar.
      2. Breakout        — price is outside the Bollinger Bands AND ADX
                            confirms trending strength.
      3. Strong Uptrend / Strong Downtrend — ADX, +DI/-DI, trend_direction,
                            and EMA slope all agree on a direction.
      4. High Volatility — volatility level == HIGH (and nothing more
                            specific already matched).
      5. Low Volatility  — volatility level == LOW AND market is non-trending
                            AND sideways.
      6. Sideways Range  — non-trending AND sideways (level == MEDIUM catch-all).
      7. Uncertain/Mixed — valid data, but no rule above cleanly matched.
      0. Unknown         — required fields missing/NaN; never guessed past.
    """
    missing = _missing_fields(ind)
    if missing:
        return {
            "regime": REGIME_UNKNOWN,
            "confidence": 0.0,
            "reasons": [
                f"Missing or invalid indicator field(s): {', '.join(missing)} "
                "— cannot classify a regime from incomplete data, returning "
                "Unknown rather than guessing."
            ],
            "metrics_used": {},
        }

    adx        = float(ind["adx"])
    di_plus    = float(ind["di_plus"])
    di_minus   = float(ind["di_minus"])
    direction  = ind["direction"]
    slope_pct  = float(ind["slope_pct"])
    vol_level  = ind["level"]
    atr_pct    = float(ind["atr_pct"])
    bb_width_pct = float(ind["bb_width_pct"])
    price      = float(ind["price"])
    bb_upper   = float(ind["bb_upper"])
    bb_lower   = float(ind["bb_lower"])

    metrics_used = {
        "adx": adx, "di_plus": di_plus, "di_minus": di_minus,
        "direction": direction, "slope_pct": slope_pct,
        "volatility_level": vol_level, "atr_pct": atr_pct,
        "bb_width_pct": bb_width_pct, "price": price,
        "bb_upper": bb_upper, "bb_lower": bb_lower,
    }

    # ── 1. Reversal ─────────────────────────────────────────────────────────
    fired: List[tuple] = []
    for key, label in _REVERSAL_DETAIL_KEYS:
        detail = _reliable_detail(ind, key, reliability_threshold)
        if detail is not None:
            fired.append((label, detail))
    if fired:
        labels = ", ".join(label for label, _ in fired)
        best_score = max(float(d.get("reliability_score", 0)) for _, d in fired)
        return {
            "regime": REGIME_REVERSAL,
            "confidence": round(min(100.0, best_score), 1),
            "reasons": [
                f"Reliable reversal-type signal(s) on the latest bar: {labels} "
                f"(reliability_score >= {reliability_threshold}) — classifying as "
                f"{REGIME_REVERSAL}."
            ],
            "metrics_used": metrics_used,
        }

    # ── 2. Breakout ──────────────────────────────────────────────────────────
    if (price > bb_upper or price < bb_lower) and adx >= adx_trending_threshold:
        side = "upper" if price > bb_upper else "lower"
        band_value = bb_upper if side == "upper" else bb_lower
        return {
            "regime": REGIME_BREAKOUT,
            "confidence": round(min(100.0, 50.0 + (adx - adx_trending_threshold)), 1),
            "reasons": [
                f"Price {price} is beyond the Bollinger {side} band ({band_value}) "
                f"while ADX {adx} >= {adx_trending_threshold} (trending strength "
                f"confirms this is not just band noise) — classifying as {REGIME_BREAKOUT}."
            ],
            "metrics_used": metrics_used,
        }

    # ── 3. Strong Uptrend / Strong Downtrend ────────────────────────────────
    if adx >= adx_trending_threshold and direction == "BULLISH" and di_plus > di_minus and slope_pct > 0:
        return {
            "regime": REGIME_STRONG_UPTREND,
            "confidence": round(min(100.0, adx * 2), 1),
            "reasons": [
                f"ADX {adx} >= {adx_trending_threshold}, trend_direction=BULLISH, "
                f"+DI {di_plus} > -DI {di_minus}, EMA fast-slope {slope_pct}% > 0 "
                f"— all four agree on an established uptrend."
            ],
            "metrics_used": metrics_used,
        }
    if adx >= adx_trending_threshold and direction == "BEARISH" and di_minus > di_plus and slope_pct < 0:
        return {
            "regime": REGIME_STRONG_DOWNTREND,
            "confidence": round(min(100.0, adx * 2), 1),
            "reasons": [
                f"ADX {adx} >= {adx_trending_threshold}, trend_direction=BEARISH, "
                f"-DI {di_minus} > +DI {di_plus}, EMA fast-slope {slope_pct}% < 0 "
                f"— all four agree on an established downtrend."
            ],
            "metrics_used": metrics_used,
        }

    # ── 4. High Volatility ───────────────────────────────────────────────────
    if vol_level == "HIGH":
        return {
            "regime": REGIME_HIGH_VOLATILITY,
            "confidence": round(min(100.0, 50.0 + atr_pct * 10), 1),
            "reasons": [
                f"Volatility level=HIGH (ATR%={atr_pct}, BB width%={bb_width_pct}) "
                "with no stronger trend/breakout/reversal signal present "
                f"— classifying as {REGIME_HIGH_VOLATILITY}."
            ],
            "metrics_used": metrics_used,
        }

    # ── 5. Low Volatility ────────────────────────────────────────────────────
    if vol_level == "LOW" and adx < adx_trending_threshold and direction == "SIDEWAYS":
        return {
            "regime": REGIME_LOW_VOLATILITY,
            "confidence": round(min(100.0, 60.0 + (adx_trending_threshold - adx)), 1),
            "reasons": [
                f"Volatility level=LOW (ATR%={atr_pct}), ADX {adx} < "
                f"{adx_trending_threshold} (non-trending), trend_direction=SIDEWAYS "
                f"— classifying as {REGIME_LOW_VOLATILITY}."
            ],
            "metrics_used": metrics_used,
        }

    # ── 6. Sideways Range ────────────────────────────────────────────────────
    if adx < adx_trending_threshold and direction == "SIDEWAYS":
        return {
            "regime": REGIME_SIDEWAYS_RANGE,
            "confidence": round(min(100.0, 55.0 + (adx_trending_threshold - adx)), 1),
            "reasons": [
                f"ADX {adx} < {adx_trending_threshold} (non-trending), "
                f"trend_direction=SIDEWAYS, volatility level={vol_level} (not LOW) "
                f"— classifying as {REGIME_SIDEWAYS_RANGE}."
            ],
            "metrics_used": metrics_used,
        }

    # ── 7. Uncertain / Mixed (valid data, no rule matched cleanly) ──────────
    return {
        "regime": REGIME_UNCERTAIN,
        "confidence": 25.0,  # deliberately low & fixed: this regime IS the ambiguity
        "reasons": [
            f"No regime rule matched cleanly (adx={adx}, direction={direction}, "
            f"di_plus={di_plus}, di_minus={di_minus}, slope_pct={slope_pct}, "
            f"volatility level={vol_level}) — signals conflict or are borderline; "
            f"classifying as {REGIME_UNCERTAIN} rather than forcing a specific regime."
        ],
        "metrics_used": metrics_used,
    }
