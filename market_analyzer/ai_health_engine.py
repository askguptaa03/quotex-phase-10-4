"""
Phase 10.3 Part-2 — AI Health Engine.

Pure functions computing a system-health snapshot from data other modules
already produce — same decoupling convention as `learning_engine.py`/
`asset_timeframe_learning.py`: no I/O of its own, no persisted store, no
import of analyzer.py/backtest.py/indicators.py/scanner.py. Every input is
a plain dict the caller (webapp/app.py) already has on hand:

  validation_history — `validation_history_store.get_history()`
  recommendation      — `learning_engine.compute_recommendation()`
  scanner_status       — `ScannerEngine.get_status()`  (public API only)
  scanner_results       — `ScannerEngine.get_results()` (public API only)
  current_regime        — the `"regime"` dict from the most recent
                           pipeline result (e.g. scanner's top-ranked
                           cached entry), or None

Deliberate, documented design choice on the one real constraint found
during Step 1's audit: `ScannerEngine._cache` (the unfiltered per-signal
history, including WAIT signals and gate-failed signals) is a private
attribute with no public accessor, and `scanner.py` is off-limits for
modification in this phase. `get_results()` only exposes a GATED subset
(`mandatory_pass=True`, `signal != WAIT`, `confidence >= min_confidence`).
Consequently:
  - BUY%/SELL% here are computed from that gated subset and are honestly
    labeled "among currently-surfaced signals" — not "of all signals".
  - Recent WAIT % cannot be derived from public data and is reported as
    `None` (not guessed), exactly like this project's "Unknown regime"
    convention elsewhere.
  - Recent Signal Count uses `scanner_status["cached_results"]`, which
    IS a true, unfiltered total (every (asset, timeframe) currently
    cached), so this one metric is fully accurate despite the above.

Health status is always one of exactly 5 labels: Excellent / Good / Fair /
Poor / Critical, computed via `_status_label(score)` on a fixed 0-100
scale, thresholds documented right there. A "no data yet" component is
explicitly given `Fair` (a deliberate, documented "neutral center" default
— NOT computed from a 0 score) so genuine absence-of-data is never
misreported as Critical, mirroring `regime_detector.py`'s own convention
of using a fixed 25.0 confidence for "Uncertain / Mixed" rather than
lower-bounding it to 0.
"""
from __future__ import annotations
from typing import Any, Dict, List, Optional

DEFAULT_MIN_SAMPLES = 20  # Same threshold convention as validation_history_store.py /
                          # asset_timeframe_learning.py / learning_engine.py (mirrored,
                          # not imported — same independent-constant convention those
                          # modules already use with each other).

# Regimes this project's own regime_weight_engine.py already treats as
# trend-continuation-favorable — reused as-is (see explainable_signal.py's
# identical constant; duplicated here rather than cross-imported to keep
# both modules independently importable with zero inter-dependency, same
# "mirrored constant, not shared code" convention validation_history_store.py's
# docstring establishes for DEFAULT_MIN_SAMPLES-style values).
_REGIME_NO_DATA = ("Unknown",)

_STATUS_THRESHOLDS = (  # (min_score_inclusive, label) — evaluated high to low
    (85.0, "Excellent"),
    (70.0, "Good"),
    (50.0, "Fair"),
    (25.0, "Poor"),
    (0.0, "Critical"),
)


def _status_label(score: Optional[float]) -> str:
    if score is None:
        return "Fair"  # neutral center — see module docstring
    for threshold, label in _STATUS_THRESHOLDS:
        if score >= threshold:
            return label
    return "Critical"


def compute_indicator_health(validation_history: Dict[str, Any],
                              min_samples: int = DEFAULT_MIN_SAMPLES) -> Dict[str, Any]:
    """
    How much of the indicator space has enough Validation History to be
    trusted, and how well those indicators are performing. Reads
    `rolling_stats` only — the same field asset_timeframe_learning.py's
    `compute_top_indicators()` reads; no indicator accuracy is recomputed
    here, only pooled/counted.
    """
    rolling = (validation_history or {}).get("rolling_stats") or {}
    total = len(rolling)
    if total == 0:
        return {"status": "Fair", "indicators_with_data": 0, "indicators_total": 0,
                "coverage_pct": None, "average_accuracy": None}

    with_data = [s for s in rolling.values()
                 if (s.get("total_samples") or 0) >= min_samples
                 and s.get("average_win_rate_over_runs") is not None]
    coverage_pct = round(100.0 * len(with_data) / total, 1)
    if not with_data:
        return {"status": "Fair", "indicators_with_data": 0, "indicators_total": total,
                "coverage_pct": coverage_pct, "average_accuracy": None}

    avg_accuracy = round(sum(s["average_win_rate_over_runs"] for s in with_data) / len(with_data), 2)
    # Weighted: mostly how accurate the covered indicators are, some credit
    # for how much of the indicator space is covered at all.
    score = 0.7 * avg_accuracy + 0.3 * coverage_pct
    return {"status": _status_label(score), "indicators_with_data": len(with_data),
            "indicators_total": total, "coverage_pct": coverage_pct, "average_accuracy": avg_accuracy}


def compute_validation_health(validation_history: Dict[str, Any]) -> Dict[str, Any]:
    """
    How much validation VOLUME has been accumulated system-wide, and how
    recently. Reads `rolling_stats`/`run_log` only.
    """
    rolling = (validation_history or {}).get("rolling_stats") or {}
    run_log = (validation_history or {}).get("run_log") or []
    total_samples = sum((s.get("total_samples") or 0) for s in rolling.values())
    runs_recorded = len(run_log)
    # run_log[0] is the most recent entry — record_run() inserts at index 0.
    last_run_at = run_log[0].get("timestamp") if run_log and isinstance(run_log[0], dict) else None

    if total_samples <= 0:
        return {"status": "Fair", "total_samples": 0, "runs_recorded": runs_recorded,
                "last_run_at": last_run_at}

    # Fixed reference scale, documented: 2000+ pooled samples across all
    # known indicators is treated as a fully mature validation history.
    # Not backtest-calibrated — same provisional caveat as Phase 10.3
    # Part-1's regime multiplier tables.
    score = min(100.0, (total_samples / 2000.0) * 100.0)
    return {"status": _status_label(score), "total_samples": total_samples,
            "runs_recorded": runs_recorded, "last_run_at": last_run_at}


def compute_learning_health(recommendation: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """
    How many indicators have enough accumulated history for Learning to
    have a real (non-"none") confidence opinion about them. Reads
    `per_indicator` only — the exact shape `learning_engine.compute_
    recommendation()` already returns; nothing recomputed.
    """
    per_indicator = (recommendation or {}).get("per_indicator") or {}
    total = len(per_indicator)
    if total == 0:
        return {"status": "Fair", "indicators_with_confidence": 0, "indicators_total": 0,
                "coverage_pct": None}

    with_confidence = sum(1 for v in per_indicator.values() if v.get("confidence") not in (None, "none"))
    coverage_pct = round(100.0 * with_confidence / total, 1)
    status = "Fair" if with_confidence == 0 else _status_label(coverage_pct)
    return {"status": status, "indicators_with_confidence": with_confidence,
            "indicators_total": total, "coverage_pct": coverage_pct}


def compute_regime_health(current_regime: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Reuses the regime classifier's OWN confidence score directly (no new
    computation) — Unknown is treated as "no data yet" (Fair), not as a
    failure, consistent with regime_detector.py's own "never guess" design.
    """
    regime = current_regime or {}
    name = regime.get("name", "Unknown")
    confidence = regime.get("confidence")
    if name in _REGIME_NO_DATA:
        return {"status": "Fair", "regime": name, "confidence": confidence}
    return {"status": _status_label(confidence), "regime": name, "confidence": confidence}


def compute_scanner_health(scanner_status: Optional[Dict[str, Any]],
                            scanner_results: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """
    See module docstring for the documented WAIT%/BUY%/SELL% limitation —
    `scanner_results["top_signals"]` is a GATED subset of everything the
    scanner has attempted, not the full unfiltered set.
    """
    status = scanner_status or {}
    results = scanner_results or {}
    running = bool(status.get("running"))
    cached_results = status.get("cached_results", 0) or 0
    top_signals = results.get("top_signals") or []

    buy = sum(1 for s in top_signals if (s.get("confluence") or {}).get("signal") == "BUY")
    sell = sum(1 for s in top_signals if (s.get("confluence") or {}).get("signal") == "SELL")
    surfaced = buy + sell

    buy_pct = round(100.0 * buy / surfaced, 1) if surfaced else None
    sell_pct = round(100.0 * sell / surfaced, 1) if surfaced else None
    wait_pct = None  # not derivable from public scanner data — see docstring

    avg_confidence = (round(sum((s.get("confluence") or {}).get("confidence", 0) or 0
                                 for s in top_signals) / surfaced, 1) if surfaced else None)
    avg_filter_score = (round(sum(s.get("filter_score", 0) or 0 for s in top_signals) / surfaced, 1)
                        if surfaced else None)
    current_regime_name = (top_signals[0].get("regime") or {}).get("name", "Unknown") if top_signals else "Unknown"

    if cached_results == 0:
        score = None  # no data yet
    elif not running and surfaced == 0:
        score = 40.0  # has stale cache, nothing currently surfaced, not running
    elif avg_filter_score is not None:
        score = avg_filter_score  # quality of what it's currently finding
    else:
        score = 55.0  # running, has cache, nothing surfaced yet (all WAIT/gated out)

    return {
        "status": _status_label(score),
        "running": running,
        "cached_results": cached_results,
        "signal_count": cached_results,
        "buy_pct": buy_pct,
        "sell_pct": sell_pct,
        "wait_pct": wait_pct,
        "average_confidence": avg_confidence,
        "average_filter_score": avg_filter_score,
        "current_regime": current_regime_name,
    }


def compute_ai_health(validation_history: Optional[Dict[str, Any]] = None,
                       recommendation: Optional[Dict[str, Any]] = None,
                       scanner_status: Optional[Dict[str, Any]] = None,
                       scanner_results: Optional[Dict[str, Any]] = None,
                       current_regime: Optional[Dict[str, Any]] = None,
                       min_samples: int = DEFAULT_MIN_SAMPLES) -> Dict[str, Any]:
    """
    Full Phase 10.3 Part-2 AI Health snapshot. Every argument is optional
    and defaults to "no data yet" (Fair) rather than raising — safe to call
    with a subset of stores available (e.g. before any Validation run).

    Returns a dict with:
      overall_health, indicator_health, scanner_health, validation_health,
      learning_health, regime_health  (each {"status": ..., ...detail...})
      average_confidence, average_filter_score, recent_accuracy,
      recent_signal_count, recent_wait_pct, buy_pct, sell_pct,
      data_quality, history_coverage
    """
    indicator_health = compute_indicator_health(validation_history, min_samples)
    validation_health = compute_validation_health(validation_history)
    learning_health = compute_learning_health(recommendation)
    scanner_health = compute_scanner_health(scanner_status, scanner_results)
    regime_health = compute_regime_health(current_regime)

    scores: List[float] = []
    for component in (indicator_health, validation_health, learning_health, scanner_health, regime_health):
        label = component["status"]
        # Map each component's own label back to a representative score for
        # the overall average — same fixed thresholds _status_label() uses,
        # taking the midpoint of each band.
        scores.append({"Excellent": 92.5, "Good": 77.5, "Fair": 60.0,
                        "Poor": 37.5, "Critical": 12.5}[label])
    overall_score = round(sum(scores) / len(scores), 1)
    overall_health = {"status": _status_label(overall_score), "score": overall_score}

    return {
        "overall_health": overall_health,
        "indicator_health": indicator_health,
        "scanner_health": scanner_health,
        "validation_health": validation_health,
        "learning_health": learning_health,
        "regime_health": regime_health,
        "average_confidence": scanner_health["average_confidence"],
        "average_filter_score": scanner_health["average_filter_score"],
        "recent_accuracy": indicator_health["average_accuracy"],
        "recent_signal_count": scanner_health["signal_count"],
        "recent_wait_pct": scanner_health["wait_pct"],
        "buy_pct": scanner_health["buy_pct"],
        "sell_pct": scanner_health["sell_pct"],
        "data_quality": validation_health["status"],
        "history_coverage": indicator_health["coverage_pct"],
    }
