"""
Phase 10.4 Goal 1 — Walk-Forward Testing Engine for the Quotex Market Analyzer.

Purely additive module. Does NOT modify analyzer.py, backtest.py, scanner.py,
learning_engine.py, indicator_registry.py, or the Quotex API. It only *calls*
two already-existing, unmodified backtest.py functions
(`backtest_factor_accuracy`, `compute_dynamic_weights`) and one already-
existing private helper (`_factor_votes`) exactly the way backtest.py's own
callers already use them — on whatever DataFrame slice it is given. No new
indicator logic, no new confluence rule, no order placement, no network call.

What "walk-forward" means here:
    For each split, factor weights are derived ONLY from the TRAIN slice
    (backtest_factor_accuracy + compute_dynamic_weights, in-sample), then
    applied to combine per-bar votes on the TEST slice (out-of-sample) to
    produce a single weighted directional signal per bar. Metrics are
    computed by comparing that signal to the bar's realised
    `lookahead`-candle-ahead return. Train and test never overlap.

Two split modes:
    - rolling:    fixed-size train window slides forward each step.
    - expanding:  train window starts at index 0 and grows each step
                  (test window slides forward, same size each time).

Known, explicitly-documented modelling limitations (not hidden):
    - The combined per-bar signal is an independent, walk-forward-only
      combiner (weighted sum of the same 10 factor votes backtest.py already
      scores). It approximates but does NOT call or duplicate
      analyzer.generate_confluence_signal() and is not used anywhere in the
      live pipeline — it exists solely to evaluate factor weights
      out-of-sample.
    - Profit Factor assumes a flat, symmetric 1-unit payout per correct call
      and -1 unit per incorrect call (no real Quotex payout percentage is
      modelled). This is a simplification, not a real P&L estimate.
    - Because Win Rate and Accuracy are both computed over the same set of
      signalled test-window bars with a binary (up/down) outcome, they are
      numerically identical by construction in this engine — Win Rate is the
      trade-level framing, Accuracy is the classification-level framing of
      the same underlying count. This is documented rather than
      artificially differentiated.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Sequence, Tuple

import numpy as np
import pandas as pd

try:
    import backtest as _bt
except ImportError:
    from market_analyzer import backtest as _bt

__all__ = [
    "generate_rolling_windows",
    "generate_expanding_windows",
    "run_walk_forward_window",
    "run_walk_forward",
    "run_walk_forward_multi",
    "compare_factor_subsets",
    "compare_strategies",
]

CONFIDENCE_BUCKETS = [(0, 20), (20, 40), (40, 60), (60, 80), (80, 100)]


# ─── Window generation ──────────────────────────────────────────────────────

def generate_rolling_windows(n: int, train_size: int, test_size: int,
                              step: Optional[int] = None) -> List[Tuple[int, int, int, int]]:
    """
    Fixed-size train window, slides forward `step` bars each iteration.

    Returns a list of (train_start, train_end, test_start, test_end)
    index tuples. `train_end`/`test_end` are exclusive (Python slice
    convention), so df.iloc[train_start:train_end] is the train slice.
    Empty list if `n` is too small for even one window.
    """
    if step is None:
        step = test_size
    windows: List[Tuple[int, int, int, int]] = []
    if train_size <= 0 or test_size <= 0 or step <= 0:
        return windows
    train_start = 0
    while True:
        train_end = train_start + train_size
        test_start = train_end
        test_end = test_start + test_size
        if test_end > n:
            break
        windows.append((train_start, train_end, test_start, test_end))
        train_start += step
    return windows


def generate_expanding_windows(n: int, initial_train_size: int, test_size: int,
                                step: Optional[int] = None) -> List[Tuple[int, int, int, int]]:
    """
    Train window always starts at index 0 and grows by `step` bars each
    iteration; test window is the next `test_size` bars after train.

    Same return shape as generate_rolling_windows().
    """
    if step is None:
        step = test_size
    windows: List[Tuple[int, int, int, int]] = []
    if initial_train_size <= 0 or test_size <= 0 or step <= 0:
        return windows
    train_end = initial_train_size
    while True:
        test_start = train_end
        test_end = test_start + test_size
        if test_end > n:
            break
        windows.append((0, train_end, test_start, test_end))
        train_end += step
    return windows


# ─── Per-window evaluation ──────────────────────────────────────────────────

def _combined_vote(df: pd.DataFrame, weights: Dict[str, float],
                    factor_subset: Optional[Sequence[str]] = None) -> pd.Series:
    """
    Weighted sum of backtest._factor_votes() for `df`, restricted to
    `factor_subset` if given. Range is roughly [-1, 1] since `weights`
    sums to 100 and each vote is -1/0/1.
    """
    votes = _bt._factor_votes(df)
    names = factor_subset if factor_subset is not None else list(votes.keys())
    combined = pd.Series(0.0, index=df.index)
    for name in names:
        vote = votes.get(name)
        if vote is None:
            continue
        w = weights.get(name, 0.0)
        combined = combined + vote.astype(float) * (w / 100.0)
    return combined


def _confusion_and_metrics(combined: pd.Series, future_return: pd.Series,
                            signal_threshold: float = 0.0) -> Dict[str, Any]:
    """
    Turn a combined signal series + forward-return series into the metric
    set requested for Phase 10.4: Win Rate, Accuracy, Precision, Recall,
    Profit Factor, Drawdown, Confidence Distribution.

    A bar is "signalled" if |combined| > signal_threshold AND future_return
    is not NaN (i.e. not in the last `lookahead` bars of the slice).
    """
    valid = (combined.abs() > signal_threshold) & future_return.notna()
    n_signals = int(valid.sum())

    empty_result = {
        "sample_size": n_signals,
        "win_rate": None,
        "accuracy": None,
        "precision": None,
        "recall": None,
        "profit_factor": None,
        "max_drawdown": None,
        "confidence_distribution": {f"{lo}-{hi}": 0 for lo, hi in CONFIDENCE_BUCKETS},
    }
    if n_signals == 0:
        return empty_result

    sig_combined = combined[valid]
    sig_return = future_return[valid]

    predicted_up = sig_combined > 0
    actual_up = sig_return > 0

    tp = int((predicted_up & actual_up).sum())
    fp = int((predicted_up & ~actual_up).sum())
    tn = int((~predicted_up & ~actual_up).sum())
    fn = int((~predicted_up & actual_up).sum())

    correct = tp + tn
    accuracy = round(correct / n_signals * 100, 2)
    win_rate = accuracy  # identical by construction here — see module docstring

    precision = round(tp / (tp + fp) * 100, 2) if (tp + fp) > 0 else None
    recall = round(tp / (tp + fn) * 100, 2) if (tp + fn) > 0 else None

    # Flat, symmetric 1-unit payout per correct call, -1 per incorrect call.
    outcomes = np.where(
        (predicted_up & actual_up) | (~predicted_up & ~actual_up), 1.0, -1.0
    )
    wins_sum = float(outcomes[outcomes > 0].sum())
    losses_sum = float(-outcomes[outcomes < 0].sum())
    if losses_sum > 0:
        profit_factor = round(wins_sum / losses_sum, 3)
    elif wins_sum > 0:
        profit_factor = None  # undefined (no losses to divide by) rather than fabricated "infinity"
    else:
        profit_factor = None

    equity = np.cumsum(outcomes)
    running_peak = np.maximum.accumulate(equity) if len(equity) else equity
    drawdown = running_peak - equity
    max_drawdown = round(float(drawdown.max()), 2) if len(drawdown) else None

    strength_pct = sig_combined.abs() * 100.0
    confidence_distribution = {}
    for lo, hi in CONFIDENCE_BUCKETS:
        if hi == 100:
            mask = (strength_pct >= lo) & (strength_pct <= hi)
        else:
            mask = (strength_pct >= lo) & (strength_pct < hi)
        confidence_distribution[f"{lo}-{hi}"] = int(mask.sum())

    return {
        "sample_size": n_signals,
        "win_rate": win_rate,
        "accuracy": accuracy,
        "precision": precision,
        "recall": recall,
        "profit_factor": profit_factor,
        "max_drawdown": max_drawdown,
        "confidence_distribution": confidence_distribution,
    }


def run_walk_forward_window(df: pd.DataFrame, train_start: int, train_end: int,
                             test_start: int, test_end: int, lookahead: int = 4,
                             factor_subset: Optional[Sequence[str]] = None,
                             signal_threshold: float = 0.0) -> Dict[str, Any]:
    """
    Run a single walk-forward split: fit factor weights on
    df.iloc[train_start:train_end], evaluate the weighted combined signal
    on df.iloc[test_start:test_end] against `lookahead`-bar-ahead returns.
    """
    train_df = df.iloc[train_start:train_end]
    test_df = df.iloc[test_start:test_end]

    accuracies = _bt.backtest_factor_accuracy(train_df, lookahead=lookahead)
    weights = _bt.compute_dynamic_weights(accuracies)

    combined = _combined_vote(test_df, weights, factor_subset)
    close = test_df["close"]
    future_return = close.shift(-lookahead) - close

    metrics = _confusion_and_metrics(combined, future_return, signal_threshold)
    metrics["train_range"] = [train_start, train_end]
    metrics["test_range"] = [test_start, test_end]
    metrics["weights_used"] = weights
    return metrics


# ─── Multi-window orchestration ─────────────────────────────────────────────

def run_walk_forward(df: pd.DataFrame, mode: str = "rolling",
                      train_size: int = 100, test_size: int = 20,
                      step: Optional[int] = None, lookahead: int = 4,
                      factor_subset: Optional[Sequence[str]] = None,
                      signal_threshold: float = 0.0) -> Dict[str, Any]:
    """
    Run walk-forward validation across the full length of `df`.

    mode: "rolling" or "expanding".
    Returns {"windows": [...], "summary": {...} | None,
             "insufficient_data": bool}.
    "summary" is None when there are zero windows (insufficient_data=True)
    or when every window produced zero signals.
    """
    if mode not in ("rolling", "expanding"):
        raise ValueError("mode must be 'rolling' or 'expanding'")

    n = len(df)
    if mode == "rolling":
        splits = generate_rolling_windows(n, train_size, test_size, step)
    else:
        splits = generate_expanding_windows(n, train_size, test_size, step)

    if not splits:
        return {"windows": [], "summary": None, "insufficient_data": True}

    windows = [
        run_walk_forward_window(df, ts, te, vs, ve, lookahead, factor_subset, signal_threshold)
        for (ts, te, vs, ve) in splits
    ]

    scored = [w for w in windows if w["sample_size"] > 0 and w["accuracy"] is not None]
    if not scored:
        return {"windows": windows, "summary": None, "insufficient_data": False}

    win_rates = [w["win_rate"] for w in scored]
    accuracies = [w["accuracy"] for w in scored]
    precisions = [w["precision"] for w in scored if w["precision"] is not None]
    recalls = [w["recall"] for w in scored if w["recall"] is not None]
    profit_factors = [w["profit_factor"] for w in scored if w["profit_factor"] is not None]
    drawdowns = [w["max_drawdown"] for w in scored if w["max_drawdown"] is not None]
    total_signals = sum(w["sample_size"] for w in scored)

    # Stability = population stddev of per-window win rate. Lower = more
    # consistent across out-of-sample windows. None if fewer than 2 scored
    # windows (stddev undefined with a single sample).
    stability = round(float(np.std(win_rates)), 3) if len(win_rates) >= 2 else None

    pooled_confidence: Dict[str, int] = {f"{lo}-{hi}": 0 for lo, hi in CONFIDENCE_BUCKETS}
    for w in scored:
        for bucket, count in w["confidence_distribution"].items():
            pooled_confidence[bucket] += count

    summary = {
        "windows_run": len(windows),
        "windows_scored": len(scored),
        "total_signals": total_signals,
        "avg_win_rate": round(float(np.mean(win_rates)), 2),
        "avg_accuracy": round(float(np.mean(accuracies)), 2),
        "avg_precision": round(float(np.mean(precisions)), 2) if precisions else None,
        "avg_recall": round(float(np.mean(recalls)), 2) if recalls else None,
        "avg_profit_factor": round(float(np.mean(profit_factors)), 3) if profit_factors else None,
        "max_drawdown": round(float(max(drawdowns)), 2) if drawdowns else None,
        "stability": stability,
        "confidence_distribution": pooled_confidence,
    }
    return {"windows": windows, "summary": summary, "insufficient_data": False}


def run_walk_forward_multi(data: Dict[str, Dict[str, pd.DataFrame]],
                            **wf_kwargs: Any) -> Dict[str, Dict[str, Any]]:
    """
    Run run_walk_forward() across multiple assets and timeframes.

    `data` shape: {asset_name: {timeframe_label: df}}.
    Returns the same nested shape with each df replaced by its
    run_walk_forward() result.
    """
    results: Dict[str, Dict[str, Any]] = {}
    for asset, timeframes in data.items():
        results[asset] = {}
        for tf_label, tf_df in timeframes.items():
            results[asset][tf_label] = run_walk_forward(tf_df, **wf_kwargs)
    return results


def compare_factor_subsets(df: pd.DataFrame, subsets: Dict[str, Sequence[str]],
                            **wf_kwargs: Any) -> Dict[str, Any]:
    """
    Indicator comparison: run the same walk-forward splits once per named
    factor subset (e.g. {"trend_only": ["bb","sr"], "all": None}) and
    return each result keyed by label, plus a "ranking" list of labels
    sorted by avg_win_rate (best first, unscored labels last).
    """
    results = {
        label: run_walk_forward(df, factor_subset=subset, **wf_kwargs)
        for label, subset in subsets.items()
    }
    ranking = sorted(
        results.keys(),
        key=lambda lbl: (results[lbl]["summary"] or {}).get("avg_win_rate", -1.0),
        reverse=True,
    )
    return {"results": results, "ranking": ranking}


def compare_strategies(df: pd.DataFrame, strategies: Dict[str, Dict[str, Any]],
                        **shared_wf_kwargs: Any) -> Dict[str, Any]:
    """
    Strategy comparison: each entry in `strategies` is a label -> dict of
    run_walk_forward() kwarg overrides (e.g. {"tight": {"signal_threshold":
    0.3}, "loose": {"signal_threshold": 0.0}}). Shared kwargs (mode,
    train_size, test_size, step, lookahead) can be passed once via
    `shared_wf_kwargs` and are overridden per-strategy where specified.
    """
    results = {}
    for label, overrides in strategies.items():
        merged = {**shared_wf_kwargs, **overrides}
        results[label] = run_walk_forward(df, **merged)
    ranking = sorted(
        results.keys(),
        key=lambda lbl: (results[lbl]["summary"] or {}).get("avg_win_rate", -1.0),
        reverse=True,
    )
    return {"results": results, "ranking": ranking}
