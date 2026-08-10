"""
Phase 10.4 Goal 3 — Historical AI Health trend computation.

Purely additive module. Does NOT modify ai_health_engine.py (or anything
else). Same decoupling convention ai_health_engine.py / learning_engine.py
/ adaptive_calibration.py already establish: no I/O of its own, no
persisted store — every function is a pure function of the `history` dict
produced by the new (also additive) `webapp/ai_health_history_store.py`'s
`get_history()`:

    {"schema_version": "1.0",
     "snapshots": [{"timestamp": "<iso8601>", "health": <compute_ai_health() output>}, ...]}
    # most-recent-first, same convention validation_history_store.py's
    # run_log and learning_engine.py's recommendation_log already use.

This module never calls compute_ai_health() itself and never reads
validation_history_store.py, learning_engine.py, or scanner.py directly —
it only ever sees whatever `compute_ai_health()` output was already
captured in a snapshot, exactly as recorded, at the time it was recorded.

No machine-learning libraries. No external services. Every computation is
plain arithmetic (mean/counting/date-bucketing) over already-computed
snapshots.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional

import numpy as np

__all__ = [
    "compute_health_history",
    "compute_daily_trend",
    "compute_weekly_trend",
    "compute_monthly_trend",
    "compute_confidence_trend",
    "compute_validation_health_trend",
    "compute_learning_health_trend",
    "compute_regime_trend",
    "build_health_trends_report",
]

# Independent thresholds for THIS module's confidence label — deliberately
# not the same DEFAULT_MIN_SAMPLES=20 used elsewhere in this codebase for
# per-indicator win-rate samples. A health-dashboard snapshot is captured
# at most once per poll interval (see ai_health_history_store's throttle),
# so "20 samples" would mean weeks of uptime before any trend is ever
# reported. 5 is a documented, deliberately smaller floor appropriate for
# snapshot-frequency data, not win-rate data.
MIN_SNAPSHOTS_FOR_TREND = 5

# Mirrors learning_engine.TREND_BAND_PCT / adaptive_calibration.TREND_BAND_PCT
# — inside this band a trend is reported "stable" rather than
# "improving"/"degrading" (mirrored constant, not imported — same
# decoupling convention those modules already establish with each other).
TREND_BAND_PCT = 2.0

# Mirrors ai_health_engine.compute_ai_health()'s own status->score midpoint
# mapping (mirrored constant, not imported — same convention).
_STATUS_SCORE = {"Excellent": 92.5, "Good": 77.5, "Fair": 60.0, "Poor": 37.5, "Critical": 12.5}

_REGIME_NO_DATA = "Unknown"


def _confidence_label(n: int, min_n: int = MIN_SNAPSHOTS_FOR_TREND) -> str:
    if n < min_n:
        return "none"
    if n < min_n * 2:
        return "low"
    if n < min_n * 5:
        return "medium"
    return "high"


def _trend_label(reference: float, baseline: float, band: float = TREND_BAND_PCT) -> str:
    diff = reference - baseline
    if diff > band:
        return "improving"
    if diff < -band:
        return "degrading"
    return "stable"


def _status_score(status: Optional[str]) -> Optional[float]:
    return _STATUS_SCORE.get(status) if status else None


def _snapshots_oldest_first(history: Optional[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """The store keeps `snapshots` most-recent-first (index 0 = newest,
    matching run_log/recommendation_log's own convention) — every trend
    computation here needs chronological order, so this is the single
    place that reverses it."""
    snapshots = list((history or {}).get("snapshots") or [])
    return list(reversed(snapshots))


def _bucket_key(timestamp_iso: str, granularity: str) -> Optional[str]:
    date_part = timestamp_iso[:10]  # "YYYY-MM-DD" prefix of the "%Y-%m-%dT%H:%M:%SZ" format
    try:
        dt = datetime.strptime(date_part, "%Y-%m-%d")
    except ValueError:
        return None
    if granularity == "daily":
        return date_part
    if granularity == "monthly":
        return date_part[:7]
    if granularity == "weekly":
        iso_year, iso_week, _ = dt.isocalendar()
        return f"{iso_year}-W{iso_week:02d}"
    raise ValueError("granularity must be 'daily', 'weekly', or 'monthly'")


def _period_trend(history: Optional[Dict[str, Any]], granularity: str) -> Dict[str, Any]:
    """
    Shared implementation for compute_daily_trend / compute_weekly_trend /
    compute_monthly_trend: buckets each snapshot's overall_health score by
    calendar period, averages within each period, then classifies the
    overall direction via a first-half-vs-second-half comparison across
    periods (plain arithmetic, no curve fitting — same convention
    adaptive_calibration.compute_accuracy_trend() already uses across
    validation runs).
    """
    snapshots = _snapshots_oldest_first(history)
    if not snapshots:
        return {"trend": "no_data", "confidence": "none", "series": [], "period_count": 0}

    buckets: Dict[str, List[float]] = {}
    for snap in snapshots:
        ts = snap.get("timestamp")
        score = ((snap.get("health") or {}).get("overall_health") or {}).get("score")
        if not ts or score is None:
            continue
        key = _bucket_key(ts, granularity)
        if key is None:
            continue
        buckets.setdefault(key, []).append(float(score))

    if not buckets:
        return {"trend": "no_data", "confidence": "none", "series": [], "period_count": 0}

    ordered_keys = sorted(buckets.keys())
    series = [
        {"period": k, "average_score": round(float(np.mean(buckets[k])), 2), "sample_count": len(buckets[k])}
        for k in ordered_keys
    ]
    total_snapshots = sum(p["sample_count"] for p in series)

    if len(series) < 2:
        return {"trend": "no_data", "confidence": _confidence_label(total_snapshots),
                "series": series, "period_count": len(series)}

    mid = max(len(series) // 2, 1)
    first_avg = float(np.mean([p["average_score"] for p in series[:mid]]))
    second_avg = float(np.mean([p["average_score"] for p in series[mid:]])) if len(series) > mid else first_avg
    return {
        "trend": _trend_label(second_avg, first_avg),
        "confidence": _confidence_label(total_snapshots),
        "first_period_avg": round(first_avg, 2),
        "second_period_avg": round(second_avg, 2),
        "series": series,
        "period_count": len(series),
    }


def compute_daily_trend(history: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """Daily Trend — overall_health score averaged per calendar day."""
    return _period_trend(history, "daily")


def compute_weekly_trend(history: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """Weekly Trend — overall_health score averaged per ISO week."""
    return _period_trend(history, "weekly")


def compute_monthly_trend(history: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """Monthly Trend — overall_health score averaged per calendar month."""
    return _period_trend(history, "monthly")


def compute_health_history(history: Optional[Dict[str, Any]], limit: Optional[int] = None) -> Dict[str, Any]:
    """
    Health History — the stored snapshot log itself (most-recent-first,
    unchanged), optionally capped to the `limit` most recent entries. No
    aggregation, no fabrication — exactly what was recorded.
    """
    snapshots = list((history or {}).get("snapshots") or [])
    total = len(snapshots)
    if limit is not None and limit >= 0:
        snapshots = snapshots[:limit]
    return {"snapshots": snapshots, "total_snapshots": total, "returned": len(snapshots)}


def _raw_metric_trend(history: Optional[Dict[str, Any]], extractor, min_snapshots: int) -> Dict[str, Any]:
    """
    Shared implementation for compute_confidence_trend /
    compute_validation_health_trend / compute_learning_health_trend:
    pulls one numeric metric out of each snapshot (via `extractor`,
    skipping snapshots where it's None — never fabricated), then applies
    the same first-half-vs-second-half classification `_period_trend()`
    uses, but over the raw per-snapshot sequence rather than calendar
    buckets.
    """
    snapshots = _snapshots_oldest_first(history)
    series: List[float] = []
    for snap in snapshots:
        value = extractor(snap.get("health") or {})
        if value is not None:
            series.append(float(value))

    if len(series) < min_snapshots:
        return {"trend": "no_data", "confidence": "none", "sample_count": len(series), "series": series}

    mid = max(len(series) // 2, 1)
    first_avg = round(float(np.mean(series[:mid])), 2)
    second_avg = round(float(np.mean(series[mid:])), 2) if len(series) > mid else first_avg
    return {
        "trend": _trend_label(second_avg, first_avg),
        "confidence": _confidence_label(len(series), min_snapshots),
        "sample_count": len(series),
        "first_half_avg": first_avg,
        "second_half_avg": second_avg,
        "series": series,
    }


def compute_confidence_trend(history: Optional[Dict[str, Any]],
                              min_snapshots: int = MIN_SNAPSHOTS_FOR_TREND) -> Dict[str, Any]:
    """Confidence Trend — average_confidence across recorded snapshots."""
    return _raw_metric_trend(history, lambda h: h.get("average_confidence"), min_snapshots)


def compute_validation_health_trend(history: Optional[Dict[str, Any]],
                                     min_snapshots: int = MIN_SNAPSHOTS_FOR_TREND) -> Dict[str, Any]:
    """
    Validation Trend — the AI Health Dashboard's own validation_health
    component score over time (status mapped to its midpoint score, same
    mapping compute_ai_health() itself uses for overall_health). Distinct
    from adaptive_calibration.compute_validation_trend(), which tracks
    per-indicator win rate directly from Validation History rather than
    this dashboard's already-summarized component score.
    """
    return _raw_metric_trend(
        history, lambda h: _status_score((h.get("validation_health") or {}).get("status")), min_snapshots
    )


def compute_learning_health_trend(history: Optional[Dict[str, Any]],
                                   min_snapshots: int = MIN_SNAPSHOTS_FOR_TREND) -> Dict[str, Any]:
    """Learning Trend — the learning_health component score over time."""
    return _raw_metric_trend(
        history, lambda h: _status_score((h.get("learning_health") or {}).get("status")), min_snapshots
    )


def compute_regime_trend(history: Optional[Dict[str, Any]],
                          min_snapshots: int = MIN_SNAPSHOTS_FOR_TREND) -> Dict[str, Any]:
    """
    Regime Trend — two views over recorded snapshots:
      - `distribution`: how many recorded snapshots saw each regime name
        (most-common first). "Unknown" is counted like any other regime
        name here (it IS the observed state), never silently dropped.
      - `confidence_trend`: first-half-vs-second-half trend of the
        regime classifier's own confidence score, counting only
        snapshots where a real (non-Unknown) regime was observed — same
        "never guess from absence" convention regime_detector.py and
        ai_health_engine.compute_regime_health() already use.
    """
    snapshots = _snapshots_oldest_first(history)
    if not snapshots:
        return {"distribution": {}, "confidence_trend": {"trend": "no_data", "confidence": "none",
                                                           "sample_count": 0, "series": []}}

    counts: Dict[str, int] = {}
    confidence_series: List[float] = []
    for snap in snapshots:
        regime_health = (snap.get("health") or {}).get("regime_health") or {}
        name = regime_health.get("regime", _REGIME_NO_DATA)
        counts[name] = counts.get(name, 0) + 1
        if name != _REGIME_NO_DATA and regime_health.get("confidence") is not None:
            confidence_series.append(float(regime_health["confidence"]))

    distribution = dict(sorted(counts.items(), key=lambda kv: kv[1], reverse=True))

    if len(confidence_series) < min_snapshots:
        confidence_trend = {"trend": "no_data", "confidence": "none",
                             "sample_count": len(confidence_series), "series": confidence_series}
    else:
        mid = max(len(confidence_series) // 2, 1)
        first_avg = round(float(np.mean(confidence_series[:mid])), 2)
        second_avg = (round(float(np.mean(confidence_series[mid:])), 2)
                      if len(confidence_series) > mid else first_avg)
        confidence_trend = {
            "trend": _trend_label(second_avg, first_avg),
            "confidence": _confidence_label(len(confidence_series), min_snapshots),
            "sample_count": len(confidence_series),
            "first_half_avg": first_avg, "second_half_avg": second_avg,
            "series": confidence_series,
        }

    return {"distribution": distribution, "confidence_trend": confidence_trend}


def build_health_trends_report(history: Optional[Dict[str, Any]], history_limit: Optional[int] = 50) -> Dict[str, Any]:
    """Bundles every trend view into one dict — the shape the new
    /api/ai/history/trends route returns as-is."""
    return {
        "health_history": compute_health_history(history, limit=history_limit),
        "daily_trend": compute_daily_trend(history),
        "weekly_trend": compute_weekly_trend(history),
        "monthly_trend": compute_monthly_trend(history),
        "confidence_trend": compute_confidence_trend(history),
        "validation_trend": compute_validation_health_trend(history),
        "learning_trend": compute_learning_health_trend(history),
        "regime_trend": compute_regime_trend(history),
    }
