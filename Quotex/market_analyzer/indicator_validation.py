"""
Phase 8.4.2 — Indicator Validation Framework
=============================================
A NEW, standalone module for validating the 3 new (not yet
Confluence-connected) indicators — Wick Rejection, Liquidity Sweep,
False Breakout — against historical candle data, bar-by-bar.

Why a new module instead of extending backtest.py:
    The Phase 8.4.1 audit found that backtest.py's `_factor_votes()` (the
    function `backtest_factor_accuracy()` depends on) only vectorizes the
    10 existing confluence factors. The 3 new indicators are single-call,
    non-vectorized detectors (they inspect `df.iloc[-1]` as "the current
    bar", the same way live/scanner code calls them) — structurally
    incompatible with `_factor_votes()`'s vectorized approach. Rather than
    force-fit them in (which would mean modifying backtest.py, off-limits
    this phase), this module implements its own bar-by-bar replay loop,
    mirroring backtest.py's *methodology* (vote at bar i -> compare to
    forward return `lookahead` bars later -> win/loss) without touching
    or importing from backtest.py itself.

What this module does NOT do (by design, per Phase 8.4.2 scope):
    - Does NOT import from, call, or modify backtest.py, analyzer.py, or
      any Confluence/Dynamic-Weight code.
    - Does NOT connect these 3 indicators to the confluence vote.
    - Does NOT compute or write dynamic weights.
    - Does NOT fetch candle data itself — every function here takes an
      already-fetched `pd.DataFrame` as input, the same "never duplicate
      the fetch system" principle backtest.py and backtest_engine.py
      already follow. Callers are responsible for supplying real candle
      data (e.g. from `fetch_data.QuotexDataFetcher`, from
      `market_analyzer/output/candles.csv`, or from a Scanner/Backtest
      cache) — this module only replays and measures.
    - Does NOT write to indicator_registry.py — Phase 8.4.4 is where a
      *future* step may wire these results into the registry's existing
      placeholder fields. This module only returns structured dicts
      "suitable for future registry integration" (2.4.2's own wording).
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

import pandas as pd

try:
    from indicators import (
        detect_wick_rejection,
        detect_liquidity_sweep,
        detect_false_breakout,
        detect_support_resistance_zones,
        atr as _atr_fn,
    )
except ImportError:  # pragma: no cover - import-path fallback, same pattern used throughout this project
    from market_analyzer.indicators import (
        detect_wick_rejection,
        detect_liquidity_sweep,
        detect_false_breakout,
        detect_support_resistance_zones,
        atr as _atr_fn,
    )

# Phase 10.1 — Universal Validation. Reuses backtest.py's existing,
# UNCHANGED, already-tested `_factor_votes()` (vectorized, bar-by-bar
# vote series for the original 10 confluence factors) rather than
# duplicating that logic here. This is a READ-ONLY import — this module
# never calls backtest_factor_accuracy()/compute_dynamic_weights() and
# never writes anything back into backtest.py. Same import-path-fallback
# convention as above.
try:
    from backtest import _factor_votes as _bt_factor_votes
except ImportError:  # pragma: no cover - import-path fallback
    from market_analyzer.backtest import _factor_votes as _bt_factor_votes

# Mirrors backtest.py's MIN_SIGNALS_REQUIRED value (20) as an INDEPENDENT
# constant — same "no cross-import, mirror the value" convention backtest.py
# itself already uses for analyzer.py's threshold constants (see
# backtest.py's CANDLE_RELIABILITY_VOTE_THRESHOLD/SR_RELIABILITY_VOTE_THRESHOLD
# module comments). Below this sample size, `reliability` is reported as
# None rather than a number that looks more trustworthy than it is.
MIN_SIGNALS_REQUIRED = 20

# Same default lookahead backtest.backtest_factor_accuracy() uses, for
# direct comparability between the two measurement approaches even though
# they're separate code paths.
DEFAULT_LOOKAHEAD = 4

# Bars needed before the first replay attempt — detect_liquidity_sweep()'s
# default lookback is 20, detect_false_breakout()'s default lookback is 30;
# 35 gives every detector a full window on its very first replay bar.
MIN_WARMUP_BARS = 35

INDICATOR_NAMES = ("wick_rejection", "liquidity_sweep", "false_breakout")

# ─── Phase 10.1 — Universal Validation (all 13 confluence factors) ───────────
#
# Everything below this line is ADDITIVE. `INDICATOR_NAMES`, `_detect()`,
# `_replay_indicator()`, `validate_indicator()`, and `validate_all()` above
# are completely unmodified — every existing caller (ValidationEngine's
# previous behavior, the original 8.4.2/8.4.3/8.5 test suites) keeps working
# byte-identically.
#
# Mirrors analyzer.DEFAULT_CONFLUENCE_WEIGHTS's 13 keys (and their exact
# order) as an INDEPENDENT constant — not imported — same "mirror the
# value, don't cross-import the module" convention `backtest.py` already
# uses for its own `_DEFAULT_8F_WEIGHTS`. Keeping this independent avoids
# a hard dependency on analyzer.py from this validation-only module.
UNIVERSAL_INDICATOR_NAMES = (
    "bb", "rsi_div", "stoch", "cci", "candle", "mean_reversion",
    "exhaustion", "round_number", "obv", "sr",
    "wick_rejection", "liquidity_sweep", "false_breakout",
)
assert len(UNIVERSAL_INDICATOR_NAMES) == 13
assert set(INDICATOR_NAMES) <= set(UNIVERSAL_INDICATOR_NAMES)

# The 10 factors backtest._factor_votes() already computes in vectorized
# (whole-Series, not bar-by-bar Python loop) form. Exactly
# UNIVERSAL_INDICATOR_NAMES minus the 3 OTC-specific detector-based ones.
_VECTORIZED_INDICATOR_NAMES = tuple(
    name for name in UNIVERSAL_INDICATOR_NAMES if name not in INDICATOR_NAMES
)
assert len(_VECTORIZED_INDICATOR_NAMES) == 10


def _validate_vectorized_factors(df: pd.DataFrame, names: Tuple[str, ...], asset: str,
                                  timeframe: str, lookahead: int = DEFAULT_LOOKAHEAD
                                  ) -> Dict[str, Dict[str, Any]]:
    """
    Bar-by-bar validation for one or more of the 10 vectorized confluence
    factors, computed in ONE pass over `df` (not once per indicator) via
    `backtest._factor_votes()` — the same vote logic
    `analyzer.generate_confluence_signal()` uses live, and the same
    function `backtest.backtest_factor_accuracy()` already relies on, so
    this measures the identical thing that file measures, just returned in
    `validate_indicator()`'s richer output shape instead of
    `backtest_factor_accuracy()`'s `{accuracy, sample_size}` pair.

    Returns {name: result_dict} for every name in `names`, each shaped
    exactly like `validate_indicator()`'s return value (same keys), so
    callers can treat the 3 detector-based indicators and these 10
    vectorized ones identically. `average_strength`/`average_reliability`
    are always None here — `_factor_votes()`'s vote Series are +1/0/-1
    only, with no per-bar strength/reliability score attached (unlike the
    3 OTC detectors' `*_detail` dicts) — reported as None rather than a
    fabricated number, same "don't invent data" principle
    `indicator_validation.py` already followed for `reliability` below
    `MIN_SIGNALS_REQUIRED`.
    """
    unknown = [n for n in names if n not in _VECTORIZED_INDICATOR_NAMES]
    if unknown:
        raise ValueError(f"Not a vectorized factor: {unknown!r}. Must be from {_VECTORIZED_INDICATOR_NAMES}")

    close = df["close"]
    future_return = close.shift(-lookahead) - close
    all_votes = _bt_factor_votes(df)  # {factor_name: pd.Series of -1/0/1}, all 10 keys, one pass

    out: Dict[str, Dict[str, Any]] = {}
    for name in names:
        vote = all_votes[name]
        eligible = future_return.notna()
        fired = (vote != 0) & eligible
        samples = int(fired.sum())
        buy_signals = int(((vote == 1) & eligible).sum())
        sell_signals = int(((vote == -1) & eligible).sum())
        no_signal_count = int(eligible.sum()) - samples

        if samples > 0:
            wins = int((((vote[fired] > 0) & (future_return[fired] > 0))
                        | ((vote[fired] < 0) & (future_return[fired] < 0))).sum())
            losses = samples - wins
            win_rate = round(wins / samples * 100, 2)
            avg_holding_result = round(float(future_return[fired].mean()), 6)
        else:
            wins = 0
            losses = 0
            win_rate = None
            avg_holding_result = None

        sufficient_sample = samples >= MIN_SIGNALS_REQUIRED
        reliability = win_rate if sufficient_sample else None

        out[name] = {
            "indicator": name,
            "asset": asset,
            "timeframe": timeframe,
            "samples": samples,
            "buy_signals": buy_signals,
            "sell_signals": sell_signals,
            "no_signal_count": no_signal_count,
            "wins": wins,
            "losses": losses,
            "win_rate": win_rate,
            "accuracy": win_rate,
            "reliability": reliability,
            "average_strength": None,
            "average_reliability": None,
            "average_holding_result": avg_holding_result,
            "sufficient_sample": sufficient_sample,
            "lookahead": lookahead,
        }
    return out


def validate_indicator_universal(df: pd.DataFrame, name: str, asset: str, timeframe: str,
                                  lookahead: int = DEFAULT_LOOKAHEAD) -> Dict[str, Any]:
    """
    Validates ONE indicator, from the FULL 13-factor confluence set,
    against ONE (asset, timeframe) candle series. Same return shape as
    `validate_indicator()`.

    For the original 3 OTC-specific detectors (`INDICATOR_NAMES`), this
    delegates STRAIGHT to `validate_indicator()` — zero duplicated logic,
    guaranteed identical results to calling `validate_indicator()`
    directly. For the other 10, uses the vectorized path above.
    """
    if name in INDICATOR_NAMES:
        return validate_indicator(df, name, asset, timeframe, lookahead=lookahead)
    if name in _VECTORIZED_INDICATOR_NAMES:
        return _validate_vectorized_factors(df, (name,), asset, timeframe, lookahead=lookahead)[name]
    raise ValueError(f"Unknown indicator: {name!r}. Must be one of {UNIVERSAL_INDICATOR_NAMES}")


def validate_all_universal(candle_sources: Dict[Tuple[str, str], pd.DataFrame],
                            indicators: Tuple[str, ...] = UNIVERSAL_INDICATOR_NAMES,
                            lookahead: int = DEFAULT_LOOKAHEAD) -> List[Dict[str, Any]]:
    """
    `validate_all()`'s Phase 10.1 counterpart, covering any subset of the
    full 13-factor `UNIVERSAL_INDICATOR_NAMES` (defaults to all 13) across
    every (asset, timeframe) -> DataFrame pair in `candle_sources`.

    Per (asset, timeframe): the 10 vectorized factors present in
    `indicators` are computed in one batched `_validate_vectorized_factors()`
    call (one `_factor_votes()` pass, not one per indicator); the 3
    detector-based factors present in `indicators` are computed via
    `validate_indicator()`, exactly as `validate_all()` already does.
    Results are returned in `UNIVERSAL_INDICATOR_NAMES` order for each
    (asset, timeframe), independent of the order `indicators` was given in.
    """
    unknown = [i for i in indicators if i not in UNIVERSAL_INDICATOR_NAMES]
    if unknown:
        raise ValueError(f"Unknown indicator(s): {unknown!r}. Must be from {UNIVERSAL_INDICATOR_NAMES}")

    requested = set(indicators)
    ordered_names = [n for n in UNIVERSAL_INDICATOR_NAMES if n in requested]
    vectorized_requested = tuple(n for n in ordered_names if n in _VECTORIZED_INDICATOR_NAMES)
    detector_requested = tuple(n for n in ordered_names if n in INDICATOR_NAMES)

    results: List[Dict[str, Any]] = []
    for (asset, timeframe), df in candle_sources.items():
        by_name: Dict[str, Dict[str, Any]] = {}
        if vectorized_requested:
            by_name.update(_validate_vectorized_factors(df, vectorized_requested, asset, timeframe, lookahead=lookahead))
        for name in detector_requested:
            by_name[name] = validate_indicator(df, name, asset, timeframe, lookahead=lookahead)
        for name in ordered_names:
            results.append(by_name[name])
    return results


def summarize_by_asset(results: List[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    """
    Phase 10.1 — Asset-wise validation summary. Pure aggregation over a
    flat result list (e.g. `validate_all_universal()`'s output) — no new
    measurement, no re-fetching, no re-running any detector. Groups every
    result row by `asset`, folding across all timeframes and indicators
    tested for that asset.

    Returns {asset: {indicators_tested, total_samples, total_wins,
    total_losses, overall_win_rate, sufficient_sample_count,
    per_indicator: {name: {samples, wins, win_rate, sufficient_sample}}}}
    """
    by_asset: Dict[str, Dict[str, Any]] = {}
    for row in results:
        asset = row["asset"]
        bucket = by_asset.setdefault(asset, {
            "asset": asset,
            "indicators_tested": set(),
            "total_samples": 0,
            "total_wins": 0,
            "total_losses": 0,
            "sufficient_sample_count": 0,
            "per_indicator": {},
        })
        bucket["indicators_tested"].add(row["indicator"])
        bucket["total_samples"] += row["samples"]
        bucket["total_wins"] += row["wins"]
        bucket["total_losses"] += row["losses"]
        if row["sufficient_sample"]:
            bucket["sufficient_sample_count"] += 1

        pi = bucket["per_indicator"].setdefault(row["indicator"], {
            "samples": 0, "wins": 0, "losses": 0, "sufficient_sample": False,
        })
        pi["samples"] += row["samples"]
        pi["wins"] += row["wins"]
        pi["losses"] += row["losses"]
        pi["sufficient_sample"] = pi["sufficient_sample"] or row["sufficient_sample"]

    for bucket in by_asset.values():
        bucket["indicators_tested"] = sorted(bucket["indicators_tested"])
        total = bucket["total_samples"]
        bucket["overall_win_rate"] = round(bucket["total_wins"] / total * 100, 2) if total > 0 else None
        for pi in bucket["per_indicator"].values():
            pi["win_rate"] = round(pi["wins"] / pi["samples"] * 100, 2) if pi["samples"] > 0 else None

    return by_asset


def summarize_by_timeframe(results: List[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    """
    Phase 10.1 — Timeframe-wise validation summary. Identical aggregation
    approach to `summarize_by_asset()` (in fact delegates to the same
    grouping logic), just grouped by `timeframe` instead of `asset`.
    Returns the same shape, keyed by timeframe, with an `"timeframe"` key
    per bucket instead of `"asset"`.
    """
    by_tf: Dict[str, Dict[str, Any]] = {}
    for row in results:
        tf = row["timeframe"]
        bucket = by_tf.setdefault(tf, {
            "timeframe": tf,
            "indicators_tested": set(),
            "total_samples": 0,
            "total_wins": 0,
            "total_losses": 0,
            "sufficient_sample_count": 0,
            "per_indicator": {},
        })
        bucket["indicators_tested"].add(row["indicator"])
        bucket["total_samples"] += row["samples"]
        bucket["total_wins"] += row["wins"]
        bucket["total_losses"] += row["losses"]
        if row["sufficient_sample"]:
            bucket["sufficient_sample_count"] += 1

        pi = bucket["per_indicator"].setdefault(row["indicator"], {
            "samples": 0, "wins": 0, "losses": 0, "sufficient_sample": False,
        })
        pi["samples"] += row["samples"]
        pi["wins"] += row["wins"]
        pi["losses"] += row["losses"]
        pi["sufficient_sample"] = pi["sufficient_sample"] or row["sufficient_sample"]

    for bucket in by_tf.values():
        bucket["indicators_tested"] = sorted(bucket["indicators_tested"])
        total = bucket["total_samples"]
        bucket["overall_win_rate"] = round(bucket["total_wins"] / total * 100, 2) if total > 0 else None
        for pi in bucket["per_indicator"].values():
            pi["win_rate"] = round(pi["wins"] / pi["samples"] * 100, 2) if pi["samples"] > 0 else None

    return by_tf


def _detect(name: str, window: pd.DataFrame, atr_value: Optional[float]) -> Optional[Dict[str, Any]]:
    """Dispatches to the correct unmodified indicators.py detector for one indicator name."""
    if name == "wick_rejection":
        return detect_wick_rejection(window, atr_value=atr_value)
    if name == "liquidity_sweep":
        return detect_liquidity_sweep(window, atr_value=atr_value)
    if name == "false_breakout":
        # Reuses detect_support_resistance_zones() per-window, exactly the
        # way indicators.calculate_all() already does for live analysis —
        # no new S/R logic invented here.
        sr_detail = detect_support_resistance_zones(window, atr_value=atr_value)
        return detect_false_breakout(window, sr_detail=sr_detail, atr_value=atr_value)
    raise ValueError(f"Unknown indicator: {name!r}")


def _replay_indicator(df: pd.DataFrame, name: str, lookahead: int = DEFAULT_LOOKAHEAD,
                       min_warmup_bars: int = MIN_WARMUP_BARS) -> Tuple[List[Dict[str, Any]], int]:
    """
    Bar-by-bar replay of one detector across df's full history, using an
    EXPANDING window ending at each bar i (`df.iloc[: i + 1]`) — the same
    "current bar is the last row" framing every detector already expects
    when called live. Returns (records, eligible_bar_count).

    Each record (one per bar where the detector actually fired):
        bar_index, direction, strength_score, reliability_score,
        forward_return, win
    """
    if len(df) < min_warmup_bars + lookahead + 1:
        return [], 0

    close = df["close"]
    atr_series = _atr_fn(df)
    records: List[Dict[str, Any]] = []
    eligible = 0

    for i in range(min_warmup_bars, len(df) - lookahead):
        eligible += 1
        window = df.iloc[: i + 1]
        atr_v = float(atr_series.iloc[i]) if i < len(atr_series) and pd.notna(atr_series.iloc[i]) else None

        detail = _detect(name, window, atr_v)
        if detail is None:
            continue

        entry_close = float(close.iloc[i])
        future_close = float(close.iloc[i + lookahead])
        forward_return = future_close - entry_close
        direction = detail.get("direction")
        win = (direction == "BUY" and forward_return > 0) or (direction == "SELL" and forward_return < 0)

        records.append({
            "bar_index": i,
            "direction": direction,
            "strength_score": detail.get("strength_score"),
            "reliability_score": detail.get("reliability_score"),
            "forward_return": forward_return,
            "win": bool(win),
        })

    return records, eligible


def validate_indicator(df: pd.DataFrame, name: str, asset: str, timeframe: str,
                        lookahead: int = DEFAULT_LOOKAHEAD) -> Dict[str, Any]:
    """
    Validates ONE indicator against ONE (asset, timeframe) candle series.

    Returns the structured result shape requested for Phase 8.4.2 (plus a
    few extra fields the spec's example didn't list by name but the task's
    own bullet list of required metrics does — losses, average_holding_result,
    no_signal_count, sufficient_sample):

        indicator, asset, timeframe, samples, wins, losses, win_rate,
        accuracy, reliability, average_strength, average_reliability,
        average_holding_result, buy_signals, sell_signals,
        no_signal_count, sufficient_sample

    `accuracy` and `win_rate` are the SAME measurement here (direction
    correct vs. forward return sign) — kept as two separate keys only
    because the task named both explicitly, not because this framework
    computes them two different ways. `average_holding_result` is the
    mean forward price change (`future_close - entry_close`) over
    `lookahead` bars across every signal — the task didn't formally define
    this term, so this is a stated interpretation, not an assumed
    industry-standard definition.
    """
    if name not in INDICATOR_NAMES:
        raise ValueError(f"Unknown indicator: {name!r}. Must be one of {INDICATOR_NAMES}")

    records, eligible_bars = _replay_indicator(df, name, lookahead=lookahead)
    samples = len(records)
    buy_signals = sum(1 for r in records if r["direction"] == "BUY")
    sell_signals = sum(1 for r in records if r["direction"] == "SELL")
    wins = sum(1 for r in records if r["win"])
    losses = samples - wins
    no_signal_count = max(eligible_bars - samples, 0)

    win_rate = round(wins / samples * 100, 2) if samples > 0 else None
    accuracy = win_rate
    sufficient_sample = samples >= MIN_SIGNALS_REQUIRED
    reliability = win_rate if sufficient_sample else None

    avg_strength = (
        round(sum((r["strength_score"] or 0.0) for r in records) / samples, 2) if samples > 0 else None
    )
    avg_reliability_score = (
        round(sum((r["reliability_score"] or 0.0) for r in records) / samples, 2) if samples > 0 else None
    )
    avg_holding_result = (
        round(sum(r["forward_return"] for r in records) / samples, 6) if samples > 0 else None
    )

    return {
        "indicator": name,
        "asset": asset,
        "timeframe": timeframe,
        "samples": samples,
        "buy_signals": buy_signals,
        "sell_signals": sell_signals,
        "no_signal_count": no_signal_count,
        "wins": wins,
        "losses": losses,
        "win_rate": win_rate,
        "accuracy": accuracy,
        "reliability": reliability,
        "average_strength": avg_strength,
        "average_reliability": avg_reliability_score,
        "average_holding_result": avg_holding_result,
        "sufficient_sample": sufficient_sample,
        "lookahead": lookahead,
    }


def validate_all(candle_sources: Dict[Tuple[str, str], pd.DataFrame],
                  indicators: Tuple[str, ...] = INDICATOR_NAMES,
                  lookahead: int = DEFAULT_LOOKAHEAD) -> List[Dict[str, Any]]:
    """
    Runs validate_indicator() for every indicator in `indicators` across
    every (asset, timeframe) -> DataFrame pair in `candle_sources`.

    `candle_sources` keys are (asset, timeframe) tuples so this naturally
    supports multiple assets and multiple timeframes in one call — this
    function does not fetch or generate any data itself; every DataFrame
    must already be supplied by the caller (reusing whatever candles the
    existing fetch/cache system already produced), matching backtest.py's
    own "never duplicate fetch logic" convention.

    Returns a flat list of result dicts (one per indicator x asset x
    timeframe combination), each shaped exactly like validate_indicator()'s
    return value.
    """
    results: List[Dict[str, Any]] = []
    for (asset, timeframe), df in candle_sources.items():
        for name in indicators:
            results.append(validate_indicator(df, name, asset, timeframe, lookahead=lookahead))
    return results
