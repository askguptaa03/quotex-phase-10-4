"""
Phase 10.4 Goal 2 — Adaptive AI Calibration for the Quotex Market Analyzer.

Purely additive module. Does NOT modify walk_forward.py, backtest.py,
analyzer.py, learning_engine.py, ai_health_engine.py,
validation_history_store.py, scanner.py, indicator_registry.py, app.py's
existing routes, or the Quotex API.

Same decoupling convention learning_engine.py / ai_health_engine.py already
establish: this module does no I/O of its own and has no persisted store.
Every function is a pure function of a plain dict/DataFrame the caller
already has on hand:

  validation_history — validation_history_store.get_history()
                        (rolling_stats + run_log)
  learning_history    — learning_engine.LearningHistoryStore.get_history()
                        (recommendation_log)
  asset_stats         — validation_history_store.get_asset_stats()
  timeframe_stats      — validation_history_store.get_timeframe_stats()
  df                  — optional already-fetched OHLCV DataFrame, for the
                        walk-forward-based functions only (confidence
                        calibration / confidence scaling / threshold
                        optimization / rolling calibration)

Two families of function, deliberately kept separate:

1. Validation-history-based (no df, no network, always available):
   compute_validation_trend, compute_accuracy_trend,
   compute_indicator_stability, compute_weight_stability,
   compute_asset_calibration, compute_timeframe_calibration.
   These read data walk_forward.py never touches — the project's real,
   already-recorded validation runs (run_log) and already-recorded
   weight-recommendation snapshots (recommendation_log) — so they work
   immediately with whatever history already exists, no live fetch
   required.

2. Walk-forward-based (require a df; reuse walk_forward.py's window
   generators and backtest.py's weight-fitting exactly as
   walk_forward.run_walk_forward_window() already does, adding
   bucket-level detail walk_forward.py's own summary doesn't expose):
   compute_confidence_calibration, compute_confidence_scaling,
   optimize_threshold, compute_rolling_calibration.

Deliberate scope boundary (documented, not hidden): no new API route in
this phase triggers a live Quotex data fetch to run family (2) — that
would require reusing app.py's existing fetch/pipeline path the way
/api/ai/explain already does, and this sandbox cannot import/execute
app.py (missing `loguru`, same standing limitation earlier phases'
test suites already document) to verify such a route end-to-end. Family
(2) functions are implemented, unit-tested against synthetic
DataFrames, and available to any caller that already has a df in hand
(e.g. a future reporting phase) — but are wired into new API routes
only in their no-df, always-safe form for this goal. See
docs/CHANGELOG.md / docs/NEXT_PHASE.md for this being called out
explicitly as a boundary, not an oversight.

No machine-learning libraries. No external services. Every computation
is plain arithmetic (mean/stddev/counting) over already-computed data.
"""

from __future__ import annotations

import time
from typing import Any, Dict, List, Optional, Sequence, Tuple

import numpy as np
import pandas as pd

try:
    import backtest as _bt
    import walk_forward as _wf
except ImportError:
    from market_analyzer import backtest as _bt
    from market_analyzer import walk_forward as _wf

__all__ = [
    "compute_validation_trend",
    "compute_accuracy_trend",
    "compute_indicator_stability",
    "compute_weight_stability",
    "compute_asset_calibration",
    "compute_timeframe_calibration",
    "compute_confidence_calibration",
    "compute_confidence_scaling",
    "apply_confidence_scaling",
    "optimize_threshold",
    "compute_rolling_calibration",
    "build_calibration_report",
    "generate_calibration_recommendations",
]

# Same threshold convention validation_history_store.py / learning_engine.py /
# ai_health_engine.py already use (mirrored as an independent constant, not
# imported — same decoupling convention those modules establish with each
# other).
DEFAULT_MIN_SAMPLES = 20

# Mirrors learning_engine.TREND_BAND_PCT — inside this band a trend is
# reported "stable" rather than "improving"/"degrading", so noise doesn't
# flip the label.
TREND_BAND_PCT = 2.0

# Reused (not duplicated) from walk_forward.py so both modules bucket
# confidence identically.
CONFIDENCE_BUCKETS = _wf.CONFIDENCE_BUCKETS

DEFAULT_THRESHOLD_CANDIDATES = [0.0, 0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9]

_COMMON_WF_KEYS = {"mode", "train_size", "test_size", "step", "lookahead", "factor_subset"}


def _now() -> float:
    return time.time()


def _iso(ts: Optional[float] = None) -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(ts if ts is not None else _now()))


def _confidence_label(total_samples: int, min_samples: int = DEFAULT_MIN_SAMPLES) -> str:
    """Same 4-band convention as learning_engine._confidence_label()."""
    if total_samples < min_samples:
        return "none"
    if total_samples < min_samples * 2:
        return "low"
    if total_samples < min_samples * 5:
        return "medium"
    return "high"


def _trend_label(reference: float, baseline: float, band: float = TREND_BAND_PCT) -> str:
    diff = reference - baseline
    if diff > band:
        return "improving"
    if diff < -band:
        return "degrading"
    return "stable"


# ─── 1. Validation-history-based calibration (no df required) ──────────────

def compute_validation_trend(validation_history: Optional[Dict[str, Any]],
                              min_samples: int = DEFAULT_MIN_SAMPLES) -> Dict[str, Any]:
    """
    Per-indicator trend from rolling_stats — same last-win-rate-vs-average
    convention learning_engine.compute_recommendation() already uses to
    decide nudge direction, exposed here as its own named calibration
    signal (not a weight recommendation).
    """
    rolling_stats = (validation_history or {}).get("rolling_stats") or {}
    out: Dict[str, Any] = {}
    for name, stats in rolling_stats.items():
        stats = stats or {}
        total = int(stats.get("total_samples", 0) or 0)
        avg = stats.get("average_win_rate_over_runs")
        last = stats.get("last_win_rate")
        if total < min_samples or avg is None:
            out[name] = {
                "trend": "no_data", "confidence": "none", "sample_count": total,
                "average_win_rate": avg, "last_win_rate": last,
            }
            continue
        reference = last if last is not None else avg
        out[name] = {
            "trend": _trend_label(reference, avg),
            "confidence": _confidence_label(total, min_samples),
            "sample_count": total,
            "average_win_rate": avg,
            "last_win_rate": last,
        }
    return out


def compute_accuracy_trend(validation_history: Optional[Dict[str, Any]],
                            min_runs: int = 3) -> Dict[str, Any]:
    """
    Sequence-based trend across recorded validation runs: for each run in
    run_log (oldest -> newest; the store keeps it most-recent-first), the
    overall accuracy for that run is the mean of
    `average_win_rate_where_sufficient` across indicators that had a
    sufficient sample in that run. First-half-vs-second-half comparison
    (plain arithmetic, no curve fitting) classifies the overall direction.
    """
    run_log = list((validation_history or {}).get("run_log") or [])
    if not run_log:
        return {"trend": "no_data", "confidence": "none", "sample_run_count": 0, "series": []}

    run_log_oldest_first = list(reversed(run_log))
    series: List[float] = []
    for run in run_log_oldest_first:
        per_ind = (run or {}).get("per_indicator") or {}
        vals = [
            v.get("average_win_rate_where_sufficient")
            for v in per_ind.values()
            if isinstance(v, dict)
            and v.get("average_win_rate_where_sufficient") is not None
            and (v.get("combinations_with_sufficient_sample") or 0) > 0
        ]
        if vals:
            series.append(round(float(np.mean(vals)), 2))

    if len(series) < min_runs:
        return {"trend": "no_data", "confidence": "none", "sample_run_count": len(series), "series": series}

    mid = len(series) // 2
    first_half_avg = round(float(np.mean(series[:mid])), 2)
    second_half_avg = round(float(np.mean(series[mid:])), 2)
    return {
        "trend": _trend_label(second_half_avg, first_half_avg),
        "confidence": _confidence_label(len(series), min_runs),
        "sample_run_count": len(series),
        "first_half_avg": first_half_avg,
        "second_half_avg": second_half_avg,
        "series": series,
    }


def compute_indicator_stability(validation_history: Optional[Dict[str, Any]],
                                 min_runs: int = 3) -> Dict[str, Any]:
    """
    Per-indicator stability from the per-run win-rate series in run_log
    (population stddev — lower = more consistent across recorded runs).
    Indicators present in rolling_stats but with fewer than `min_runs`
    qualifying run_log entries are reported "no_data", never guessed.
    """
    run_log = list((validation_history or {}).get("run_log") or [])
    run_log_oldest_first = list(reversed(run_log))

    per_indicator_series: Dict[str, List[float]] = {}
    for run in run_log_oldest_first:
        per_ind = (run or {}).get("per_indicator") or {}
        for name, entry in per_ind.items():
            if not isinstance(entry, dict):
                continue
            wr = entry.get("average_win_rate_where_sufficient")
            sufficient = (entry.get("combinations_with_sufficient_sample") or 0) > 0
            if wr is not None and sufficient:
                per_indicator_series.setdefault(name, []).append(wr)

    out: Dict[str, Any] = {}
    for name, series in per_indicator_series.items():
        if len(series) < min_runs:
            out[name] = {"stability": "no_data", "confidence": "none", "sample_run_count": len(series)}
            continue
        stdev = round(float(np.std(series)), 3)
        mean = round(float(np.mean(series)), 2)
        if stdev <= 3.0:
            label = "stable"
        elif stdev <= 8.0:
            label = "moderate"
        else:
            label = "unstable"
        out[name] = {
            "stability": label,
            "confidence": _confidence_label(len(series), min_runs),
            "sample_run_count": len(series),
            "mean_win_rate": mean,
            "stddev_win_rate": stdev,
            "series": series,
        }

    # Indicators with rolling_stats but zero qualifying run_log entries.
    rolling_stats = (validation_history or {}).get("rolling_stats") or {}
    for name in rolling_stats:
        if name not in out:
            out[name] = {"stability": "no_data", "confidence": "none", "sample_run_count": 0}
    return out


def compute_weight_stability(learning_history: Optional[Dict[str, Any]],
                              min_snapshots: int = 3) -> Dict[str, Any]:
    """
    Per-indicator stability of learning_engine's recommended_weights across
    recorded snapshots (recommendation_log — most-recent-first, same as
    validation_history_store's convention). Lower stddev = the learning
    engine has been recommending a consistently similar weight for that
    indicator over time.
    """
    log = list((learning_history or {}).get("recommendation_log") or [])
    log_oldest_first = list(reversed(log))

    per_indicator_series: Dict[str, List[float]] = {}
    for snap in log_oldest_first:
        rec_weights = (snap or {}).get("recommended_weights") or {}
        for name, w in rec_weights.items():
            try:
                per_indicator_series.setdefault(name, []).append(float(w))
            except (TypeError, ValueError):
                continue

    out: Dict[str, Any] = {}
    for name, series in per_indicator_series.items():
        if len(series) < min_snapshots:
            out[name] = {"stability": "no_data", "confidence": "none", "sample_count": len(series)}
            continue
        stdev = round(float(np.std(series)), 3)
        mean = round(float(np.mean(series)), 3)
        if stdev <= 0.5:
            label = "stable"
        elif stdev <= 1.5:
            label = "moderate"
        else:
            label = "unstable"
        out[name] = {
            "stability": label,
            "confidence": _confidence_label(len(series), min_snapshots),
            "sample_count": len(series),
            "mean_weight": mean,
            "stddev_weight": stdev,
            "series": series,
        }
    return out


def _aggregate_group_stats(group_stats: Optional[Dict[str, Dict[str, Any]]],
                            min_samples: int = DEFAULT_MIN_SAMPLES) -> Dict[str, Any]:
    """
    Shared aggregation for asset_stats / timeframe_stats — both are shaped
    {group_key: {indicator: rolling-stats-dict}} (validation_history_store's
    own documented shape). A group's score is the mean
    average_win_rate_over_runs across only the indicators within it that
    individually clear `min_samples` — never fabricated from thin data.
    """
    groups: Dict[str, Any] = {}
    for key, indicators in (group_stats or {}).items():
        win_rates: List[float] = []
        total_samples = 0
        for _, stats in (indicators or {}).items():
            stats = stats or {}
            n = int(stats.get("total_samples", 0) or 0)
            avg = stats.get("average_win_rate_over_runs")
            total_samples += n
            if n >= min_samples and avg is not None:
                win_rates.append(avg)
        if not win_rates:
            groups[key] = {
                "score": None, "confidence": "none",
                "total_samples": total_samples, "indicators_with_data": 0,
            }
            continue
        groups[key] = {
            "score": round(float(np.mean(win_rates)), 2),
            "confidence": _confidence_label(total_samples, min_samples),
            "total_samples": total_samples,
            "indicators_with_data": len(win_rates),
        }

    ranking = sorted(
        (k for k, v in groups.items() if v["score"] is not None),
        key=lambda k: groups[k]["score"], reverse=True,
    )
    return {"groups": groups, "ranking": ranking}


def compute_asset_calibration(asset_stats: Optional[Dict[str, Dict[str, Any]]],
                               min_samples: int = DEFAULT_MIN_SAMPLES) -> Dict[str, Any]:
    """Asset Calibration — from validation_history_store.get_asset_stats()."""
    return _aggregate_group_stats(asset_stats, min_samples)


def compute_timeframe_calibration(timeframe_stats: Optional[Dict[str, Dict[str, Any]]],
                                   min_samples: int = DEFAULT_MIN_SAMPLES) -> Dict[str, Any]:
    """Timeframe Calibration — from validation_history_store.get_timeframe_stats()."""
    return _aggregate_group_stats(timeframe_stats, min_samples)


# ─── 2. Walk-forward-based calibration (requires a df) ──────────────────────

def _iter_window_signals(df: pd.DataFrame, mode: str, train_size: int, test_size: int,
                          step: Optional[int], lookahead: int,
                          factor_subset: Optional[Sequence[str]]):
    """
    Shared walk-forward loop for the df-based functions below. Reuses
    walk_forward.py's window generators and its private `_combined_vote`
    helper exactly the way walk_forward.run_walk_forward_window() already
    does (train-slice weight fitting via backtest.py, applied out-of-sample
    to the test slice) — this function is additive plumbing, not a
    redefinition of that logic.
    """
    n = len(df)
    if mode == "rolling":
        splits = _wf.generate_rolling_windows(n, train_size, test_size, step)
    elif mode == "expanding":
        splits = _wf.generate_expanding_windows(n, train_size, test_size, step)
    else:
        raise ValueError("mode must be 'rolling' or 'expanding'")

    for (ts, te, vs, ve) in splits:
        train_df = df.iloc[ts:te]
        test_df = df.iloc[vs:ve]
        accuracies = _bt.backtest_factor_accuracy(train_df, lookahead=lookahead)
        weights = _bt.compute_dynamic_weights(accuracies)
        combined = _wf._combined_vote(test_df, weights, factor_subset)
        close = test_df["close"]
        future_return = close.shift(-lookahead) - close
        yield (ts, te, vs, ve), combined, future_return


def compute_confidence_calibration(df: pd.DataFrame, mode: str = "rolling",
                                    train_size: int = 100, test_size: int = 25,
                                    step: Optional[int] = None, lookahead: int = 4,
                                    factor_subset: Optional[Sequence[str]] = None) -> Dict[str, Any]:
    """
    Pools every out-of-sample bar across all walk-forward windows into
    walk_forward.CONFIDENCE_BUCKETS by |combined signal strength|, and
    measures the ACTUAL win rate observed in each bucket. Calibration
    error = mean absolute difference between a bucket's win rate and its
    numeric midpoint (a perfectly-calibrated signal's 60-80% bucket would
    win ~70% of the time; a large gap means raw signal strength doesn't
    track real outcomes).
    """
    bucket_totals = {f"{lo}-{hi}": {"sample_size": 0, "correct": 0} for lo, hi in CONFIDENCE_BUCKETS}
    any_window = False

    for _, combined, future_return in _iter_window_signals(
        df, mode, train_size, test_size, step, lookahead, factor_subset
    ):
        any_window = True
        valid = (combined.abs() > 0) & future_return.notna()
        if not valid.any():
            continue
        sig_combined = combined[valid]
        sig_return = future_return[valid]
        predicted_up = sig_combined > 0
        actual_up = sig_return > 0
        correct = (predicted_up & actual_up) | (~predicted_up & ~actual_up)
        strength_pct = sig_combined.abs() * 100.0

        for lo, hi in CONFIDENCE_BUCKETS:
            key = f"{lo}-{hi}"
            mask = (strength_pct >= lo) & (strength_pct <= hi if hi == 100 else strength_pct < hi)
            bucket_totals[key]["sample_size"] += int(mask.sum())
            bucket_totals[key]["correct"] += int((mask & correct).sum())

    if not any_window:
        return {"buckets": {}, "calibration_error": None, "confidence": "none",
                "total_samples": 0, "insufficient_data": True}

    buckets: Dict[str, Any] = {}
    errors: List[float] = []
    for lo, hi in CONFIDENCE_BUCKETS:
        key = f"{lo}-{hi}"
        n = bucket_totals[key]["sample_size"]
        if n == 0:
            buckets[key] = {"sample_size": 0, "win_rate": None}
            continue
        win_rate = round(bucket_totals[key]["correct"] / n * 100, 2)
        buckets[key] = {"sample_size": n, "win_rate": win_rate}
        errors.append(abs(win_rate - (lo + hi) / 2.0))

    total_samples = sum(b["sample_size"] for b in buckets.values())
    return {
        "buckets": buckets,
        "calibration_error": round(float(np.mean(errors)), 2) if errors else None,
        "confidence": _confidence_label(total_samples),
        "total_samples": total_samples,
        "insufficient_data": False,
    }


def compute_confidence_scaling(calibration_result: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Turns a compute_confidence_calibration() result into a lookup table
    mapping each confidence bucket to its OBSERVED win rate — a
    deterministic, historically-grounded replacement for treating raw
    signal-strength percentage as if it were already a calibrated
    probability. `None` for any bucket with no observed samples (never
    fabricated).
    """
    buckets = (calibration_result or {}).get("buckets") or {}
    return {"scaling_table": {key: info.get("win_rate") for key, info in buckets.items()}}


def apply_confidence_scaling(raw_strength_pct: float, scaling_table: Dict[str, Optional[float]],
                              buckets: Sequence[Tuple[int, int]] = CONFIDENCE_BUCKETS) -> Optional[float]:
    """Maps one raw |combined signal| percentage to its calibrated win rate via `scaling_table`."""
    for lo, hi in buckets:
        in_bucket = (lo <= raw_strength_pct <= hi) if hi == 100 else (lo <= raw_strength_pct < hi)
        if in_bucket:
            return scaling_table.get(f"{lo}-{hi}")
    return None


def optimize_threshold(df: pd.DataFrame, candidates: Optional[Sequence[float]] = None,
                        min_sample_size: int = 20, mode: str = "rolling",
                        train_size: int = 100, test_size: int = 25,
                        step: Optional[int] = None, lookahead: int = 4,
                        factor_subset: Optional[Sequence[str]] = None) -> Dict[str, Any]:
    """
    Sweeps candidate `signal_threshold` values through
    walk_forward.run_walk_forward() (unmodified) and picks the one with
    the highest avg_win_rate among candidates whose total_signals meets
    `min_sample_size` — a floor that exists specifically so a
    threshold that happens to produce one lucky signal can't win by
    accident.
    """
    candidates = list(candidates) if candidates is not None else DEFAULT_THRESHOLD_CANDIDATES
    evaluated: List[Dict[str, Any]] = []
    for thr in candidates:
        result = _wf.run_walk_forward(df, mode=mode, train_size=train_size, test_size=test_size,
                                       step=step, lookahead=lookahead, factor_subset=factor_subset,
                                       signal_threshold=thr)
        summary = result.get("summary") or {}
        evaluated.append({
            "threshold": thr,
            "win_rate": summary.get("avg_win_rate"),
            "total_signals": summary.get("total_signals", 0),
            "stability": summary.get("stability"),
        })

    eligible = [e for e in evaluated if e["win_rate"] is not None and e["total_signals"] >= min_sample_size]
    if not eligible:
        return {"evaluated": evaluated, "best": None, "insufficient_data": True}

    best = max(eligible, key=lambda e: (e["win_rate"], e["total_signals"]))
    return {"evaluated": evaluated, "best": best, "insufficient_data": False}


def compute_rolling_calibration(df: pd.DataFrame, **kwargs: Any) -> Dict[str, Any]:
    """Rolling Calibration — compute_confidence_calibration() pinned to mode='rolling'."""
    kwargs.pop("mode", None)
    return compute_confidence_calibration(df, mode="rolling", **kwargs)


# ─── Orchestration ───────────────────────────────────────────────────────────

def build_calibration_report(validation_history: Optional[Dict[str, Any]] = None,
                              learning_history: Optional[Dict[str, Any]] = None,
                              asset_stats: Optional[Dict[str, Dict[str, Any]]] = None,
                              timeframe_stats: Optional[Dict[str, Dict[str, Any]]] = None,
                              df: Optional[pd.DataFrame] = None,
                              walk_forward_kwargs: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """
    Assembles every calibration signal into one report. The
    validation-history-based sections are always computed (no df needed).
    The walk-forward-based sections (confidence_calibration /
    confidence_scaling / threshold_optimization) are only computed when a
    `df` is supplied — otherwise they are explicitly `None`, never
    silently omitted.
    """
    walk_forward_kwargs = walk_forward_kwargs or {}
    report: Dict[str, Any] = {
        "generated_at": _iso(),
        "validation_trend": compute_validation_trend(validation_history),
        "accuracy_trend": compute_accuracy_trend(validation_history),
        "indicator_stability": compute_indicator_stability(validation_history),
        "weight_stability": compute_weight_stability(learning_history),
        "asset_calibration": compute_asset_calibration(asset_stats),
        "timeframe_calibration": compute_timeframe_calibration(timeframe_stats),
    }

    if df is not None:
        common = {k: v for k, v in walk_forward_kwargs.items() if k in _COMMON_WF_KEYS}
        cal = compute_confidence_calibration(df, **common)
        report["confidence_calibration"] = cal
        report["confidence_scaling"] = compute_confidence_scaling(cal)

        threshold_kwargs = dict(common)
        threshold_kwargs.update({
            k: v for k, v in walk_forward_kwargs.items() if k in ("candidates", "min_sample_size")
        })
        report["threshold_optimization"] = optimize_threshold(df, **threshold_kwargs)
    else:
        report["confidence_calibration"] = None
        report["confidence_scaling"] = None
        report["threshold_optimization"] = None

    return report


# ─── Step 3: Calibration recommendations ─────────────────────────────────────

def generate_calibration_recommendations(report: Dict[str, Any]) -> List[Dict[str, Any]]:
    """
    Turns a build_calibration_report() result into a flat list of
    recommendations. Every entry has reason / evidence / confidence /
    severity, per the phase spec. Deterministic rules only — no scoring
    model, no ML. Returns an empty list (not an error) when nothing in the
    report clears the relevant confidence/threshold bar.
    """
    recs: List[Dict[str, Any]] = []

    # ── Confidence calibration -> threshold direction ──────────────────────
    cal = report.get("confidence_calibration")
    if cal and not cal.get("insufficient_data"):
        populated = {k: v for k, v in (cal.get("buckets") or {}).items() if v.get("sample_size", 0) > 0}
        if len(populated) >= 2:
            ordered_keys = sorted(populated.keys(), key=lambda k: int(k.split("-")[0]))
            lowest = populated[ordered_keys[0]]
            highest = populated[ordered_keys[-1]]
            if lowest["win_rate"] is not None and highest["win_rate"] is not None:
                gap = highest["win_rate"] - lowest["win_rate"]
                if gap > 10.0:
                    recs.append({
                        "action": "increase_confidence_threshold",
                        "reason": (f"Signals in the {ordered_keys[0]}% confidence bucket win "
                                   f"{lowest['win_rate']}% of the time vs {highest['win_rate']}% for the "
                                   f"{ordered_keys[-1]}% bucket — raising the threshold to filter out "
                                   f"low-strength signals would likely raise the overall win rate."),
                        "evidence": {"lowest_bucket": ordered_keys[0], "highest_bucket": ordered_keys[-1],
                                     "lowest": lowest, "highest": highest},
                        "confidence": cal.get("confidence", "low"),
                        "severity": "high" if gap > 25.0 else "medium",
                    })
                elif gap < -10.0:
                    recs.append({
                        "action": "decrease_confidence_threshold",
                        "reason": (f"Low-confidence signals are outperforming high-confidence ones "
                                   f"({lowest['win_rate']}% vs {highest['win_rate']}%) — the current "
                                   f"threshold may be discarding profitable signals."),
                        "evidence": {"lowest_bucket": ordered_keys[0], "highest_bucket": ordered_keys[-1],
                                     "lowest": lowest, "highest": highest},
                        "confidence": cal.get("confidence", "low"),
                        "severity": "low",
                    })

    # ── Threshold optimization -> concrete setting ──────────────────────────
    thr = report.get("threshold_optimization")
    if thr and not thr.get("insufficient_data") and thr.get("best"):
        best = thr["best"]
        recs.append({
            "action": "set_optimal_signal_threshold",
            "reason": (f"Threshold {best['threshold']} produced the highest walk-forward win rate "
                       f"({best['win_rate']}%) among candidates meeting the minimum sample size."),
            "evidence": best,
            "confidence": "medium",
            "severity": "info",
        })

    # ── Indicator stability -> ignore / prefer ──────────────────────────────
    for name, info in (report.get("indicator_stability") or {}).items():
        if info.get("stability") == "unstable":
            recs.append({
                "action": "ignore_unstable_indicator",
                "reason": (f"{name}'s win rate varies widely across recorded validation runs "
                           f"(stddev {info.get('stddev_win_rate')} points)."),
                "evidence": info,
                "confidence": info.get("confidence", "low"),
                "severity": "medium",
            })
        elif info.get("stability") == "stable" and info.get("confidence") in ("medium", "high"):
            recs.append({
                "action": "prefer_stable_indicator",
                "reason": (f"{name} has a consistent win rate across recorded validation runs "
                           f"(stddev {info.get('stddev_win_rate')} points)."),
                "evidence": info,
                "confidence": info.get("confidence"),
                "severity": "info",
            })

    # ── Weight stability -> decrease weight on erratic recommendations ─────
    for name, info in (report.get("weight_stability") or {}).items():
        if info.get("stability") == "unstable":
            recs.append({
                "action": "decrease_indicator_weight",
                "reason": (f"{name}'s recommended weight has swung widely across recent learning "
                           f"snapshots (stddev {info.get('stddev_weight')})."),
                "evidence": info,
                "confidence": info.get("confidence", "low"),
                "severity": "medium",
            })

    # ── Validation trend -> increase / decrease weight ──────────────────────
    for name, info in (report.get("validation_trend") or {}).items():
        if info.get("confidence") not in ("medium", "high"):
            continue
        if info.get("trend") == "improving":
            recs.append({
                "action": "increase_indicator_weight",
                "reason": f"{name}'s recent win rate is trending above its historical average.",
                "evidence": info, "confidence": info.get("confidence"), "severity": "info",
            })
        elif info.get("trend") == "degrading":
            recs.append({
                "action": "decrease_indicator_weight",
                "reason": f"{name}'s recent win rate is trending below its historical average.",
                "evidence": info, "confidence": info.get("confidence"), "severity": "medium",
            })

    # ── Best asset / timeframe ──────────────────────────────────────────────
    asset_cal = report.get("asset_calibration") or {}
    if asset_cal.get("ranking"):
        best_asset = asset_cal["ranking"][0]
        info = asset_cal["groups"][best_asset]
        recs.append({
            "action": "recommend_best_asset",
            "reason": f"{best_asset} has the highest calibrated average win rate among assets with sufficient data.",
            "evidence": {"asset": best_asset, **info},
            "confidence": info.get("confidence", "low"),
            "severity": "info",
        })

    tf_cal = report.get("timeframe_calibration") or {}
    if tf_cal.get("ranking"):
        best_tf = tf_cal["ranking"][0]
        info = tf_cal["groups"][best_tf]
        recs.append({
            "action": "recommend_best_timeframe",
            "reason": f"{best_tf} has the highest calibrated average win rate among timeframes with sufficient data.",
            "evidence": {"timeframe": best_tf, **info},
            "confidence": info.get("confidence", "low"),
            "severity": "info",
        })

    return recs
