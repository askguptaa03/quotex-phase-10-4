"""
Phase 10.4 Goal 4 — AI Performance Reports.

Purely additive module. Does NOT modify walk_forward.py, adaptive_
calibration.py, ai_health_engine.py, ai_health_trends.py, analyzer.py,
backtest.py, scanner.py, learning_engine.py, indicator_registry.py, or the
Quotex API.

Same decoupling convention every Phase 10.4 module already establishes:
no I/O of its own, no persisted store. Every function is a pure function
of a plain dict the caller already has on hand — this module generates
reports FROM already-verified data other modules compute, it never
recomputes anything itself:

  validation_history   — validation_history_store.get_history()
  recommendation        — learning_engine.compute_recommendation()
  ai_health_snapshot    — ai_health_engine.compute_ai_health()
  ai_health_history      — ai_health_history_store.get_history()
  calibration_report    — adaptive_calibration.build_calibration_report()
  walk_forward_result    — walk_forward.run_walk_forward()

Reuses (never duplicates) two existing pure-function modules for their
exact documented purpose:
  - webapp/asset_timeframe_learning.py (not off-limits) for best/worst
    asset, timeframe, and indicator rankings — this project's own,
    already-verified ranking logic.
  - adaptive_calibration.py for accuracy trend / calibration
    recommendations.
  - ai_health_trends.py for daily/weekly/monthly health-score trend and
    regime distribution.

No machine-learning libraries. No external services. Every computation is
plain arithmetic (mean/counting/date-bucketing) over already-computed
data, plus straightforward re-bundling of other modules' outputs.
"""

from __future__ import annotations

import time
from datetime import datetime
from typing import Any, Dict, List, Optional

import numpy as np

try:
    import asset_timeframe_learning as _atl
except ImportError:
    from market_analyzer.webapp import asset_timeframe_learning as _atl

import adaptive_calibration as _ac
import ai_health_trends as _aht

__all__ = [
    "compute_daily_report",
    "compute_weekly_report",
    "compute_monthly_report",
    "compute_asset_report",
    "compute_timeframe_report",
    "compute_indicator_report",
    "compute_validation_report",
    "compute_learning_report",
    "compute_ai_health_report",
    "compute_walk_forward_summary",
    "compute_calibration_summary",
    "generate_warnings",
    "build_full_performance_report",
]

# Mirrors asset_timeframe_learning.DEFAULT_MIN_SAMPLES / adaptive_
# calibration.DEFAULT_MIN_SAMPLES (mirrored constant, not imported — same
# decoupling convention every module in this phase already establishes).
DEFAULT_MIN_SAMPLES = 20
DEFAULT_TOP_N = 3

# Below this system-wide average accuracy, compute_validation_report()'s
# data is considered warning-worthy — see generate_warnings().
LOW_ACCURACY_WARNING_THRESHOLD = 50.0


def _now() -> float:
    return time.time()


def _iso(ts: Optional[float] = None) -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(ts if ts is not None else _now()))


def _bucket_key(timestamp_iso: str, granularity: str) -> Optional[str]:
    """Mirrors ai_health_trends._bucket_key() exactly (mirrored, not
    imported — that helper is private to ai_health_trends.py; duplicating
    a 6-line pure function keeps both modules independently importable,
    same convention this codebase already uses for shared constants)."""
    date_part = timestamp_iso[:10]
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


# ─── Daily / Weekly / Monthly reports ────────────────────────────────────────

_TREND_FN = {
    "daily": _aht.compute_daily_trend,
    "weekly": _aht.compute_weekly_trend,
    "monthly": _aht.compute_monthly_trend,
}

_PERIOD_METRIC_FIELDS = ("recent_accuracy", "average_confidence", "average_filter_score", "buy_pct", "sell_pct")
_PERIOD_METRIC_LABELS = {
    "recent_accuracy": "accuracy", "average_confidence": "confidence",
    "average_filter_score": "filter_score", "buy_pct": "buy_pct", "sell_pct": "sell_pct",
}


def _period_report(ai_health_history: Optional[Dict[str, Any]], granularity: str) -> Dict[str, Any]:
    """
    Shared implementation for compute_daily_report / compute_weekly_report
    / compute_monthly_report: reuses ai_health_trends' own period-trend
    function for the overall_health score series, and additionally
    period-buckets accuracy / confidence / filter_score / buy_pct /
    sell_pct from the same snapshot log (fields ai_health_trends.py
    doesn't itself bucket, since Goal 3's scope was the health score
    only).
    """
    health_trend = _TREND_FN[granularity](ai_health_history)

    snapshots = list((ai_health_history or {}).get("snapshots") or [])
    buckets: Dict[str, Dict[str, List[float]]] = {}
    for snap in snapshots:
        ts = snap.get("timestamp")
        health = snap.get("health") or {}
        if not ts:
            continue
        key = _bucket_key(ts, granularity)
        if key is None:
            continue
        bucket = buckets.setdefault(key, {label: [] for label in _PERIOD_METRIC_LABELS.values()})
        for field in _PERIOD_METRIC_FIELDS:
            value = health.get(field)
            if value is not None:
                bucket[_PERIOD_METRIC_LABELS[field]].append(float(value))

    period_metrics = {}
    for key in sorted(buckets.keys()):
        period_metrics[key] = {
            label: (round(float(np.mean(values)), 2) if values else None)
            for label, values in buckets[key].items()
        }

    return {
        "generated_at": _iso(),
        "granularity": granularity,
        "health_trend": health_trend,
        "period_metrics": period_metrics,
    }


def compute_daily_report(ai_health_history: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """Daily Report — health-score trend + per-day accuracy/confidence/filter_score/buy%/sell%."""
    return _period_report(ai_health_history, "daily")


def compute_weekly_report(ai_health_history: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """Weekly Report — same shape as compute_daily_report(), bucketed by ISO week."""
    return _period_report(ai_health_history, "weekly")


def compute_monthly_report(ai_health_history: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """Monthly Report — same shape as compute_daily_report(), bucketed by calendar month."""
    return _period_report(ai_health_history, "monthly")


# ─── Asset / Timeframe / Indicator reports ───────────────────────────────────

def compute_asset_report(validation_history: Optional[Dict[str, Any]],
                          min_samples: int = DEFAULT_MIN_SAMPLES) -> Dict[str, Any]:
    """Asset Report — delegates entirely to asset_timeframe_learning.compute_asset_rankings()
    (this project's own, already-verified ranking logic), condensed with an explicit
    best/worst pair."""
    rankings = _atl.compute_asset_rankings(validation_history, min_samples=min_samples)
    ranking = rankings.get("ranking") or []
    return {
        "generated_at": rankings["generated_at"],
        "assets": rankings["assets"],
        "ranking": ranking,
        "best_asset": ranking[0] if ranking else None,
        "worst_asset": ranking[-1] if ranking else None,
    }


def compute_timeframe_report(validation_history: Optional[Dict[str, Any]],
                              min_samples: int = DEFAULT_MIN_SAMPLES) -> Dict[str, Any]:
    """Timeframe Report — identical shape to compute_asset_report(), via
    asset_timeframe_learning.compute_timeframe_rankings()."""
    rankings = _atl.compute_timeframe_rankings(validation_history, min_samples=min_samples)
    ranking = rankings.get("ranking") or []
    return {
        "generated_at": rankings["generated_at"],
        "timeframes": rankings["timeframes"],
        "ranking": ranking,
        "best_timeframe": ranking[0] if ranking else None,
        "worst_timeframe": ranking[-1] if ranking else None,
    }


def compute_indicator_report(validation_history: Optional[Dict[str, Any]],
                              min_samples: int = DEFAULT_MIN_SAMPLES,
                              top_n: int = DEFAULT_TOP_N) -> Dict[str, Any]:
    """Indicator Report — via asset_timeframe_learning.compute_top_indicators()."""
    top = _atl.compute_top_indicators(validation_history, min_samples=min_samples, top_n=top_n)
    return {
        "generated_at": top["generated_at"],
        "top": top["top"],
        "weakest": top["weakest"],
        "no_data": top["no_data"],
        "best_indicator": top["top"][0]["indicator"] if top["top"] else None,
        "worst_indicator": top["weakest"][0]["indicator"] if top["weakest"] else None,
    }


# ─── Validation / Learning reports ──────────────────────────────────────────

def compute_validation_report(validation_history: Optional[Dict[str, Any]],
                               min_samples: int = DEFAULT_MIN_SAMPLES) -> Dict[str, Any]:
    """
    Validation Report — system-wide validation volume/coverage/accuracy,
    plus adaptive_calibration.compute_accuracy_trend()'s run-log-based
    trend (reused, not recomputed).
    """
    rolling = (validation_history or {}).get("rolling_stats") or {}
    run_log = (validation_history or {}).get("run_log") or []
    total_samples = sum((s.get("total_samples") or 0) for s in rolling.values())
    with_data = [
        s for s in rolling.values()
        if (s.get("total_samples") or 0) >= min_samples and s.get("average_win_rate_over_runs") is not None
    ]
    avg_accuracy = round(float(np.mean([s["average_win_rate_over_runs"] for s in with_data])), 2) if with_data else None
    return {
        "generated_at": _iso(),
        "total_samples": total_samples,
        "runs_recorded": len(run_log),
        "indicators_with_data": len(with_data),
        "indicators_total": len(rolling),
        "average_accuracy": avg_accuracy,
        "accuracy_trend": _ac.compute_accuracy_trend(validation_history),
    }


def compute_learning_report(recommendation: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Learning Report — condenses a learning_engine.compute_recommendation()
    output into per-trend indicator groupings + the recommended weight
    set, without recomputing any of it.
    """
    per_indicator = (recommendation or {}).get("per_indicator") or {}
    groups: Dict[str, List[str]] = {"improving": [], "degrading": [], "stable": [], "no_data": []}
    for name, info in per_indicator.items():
        groups.setdefault(info.get("trend", "no_data"), []).append(name)
    return {
        "generated_at": _iso(),
        "indicators_total": len(per_indicator),
        "improving": groups["improving"],
        "degrading": groups["degrading"],
        "stable": groups["stable"],
        "no_data": groups["no_data"],
        "recommended_weights": (recommendation or {}).get("recommended_weights"),
    }


# ─── AI Health / Walk-Forward / Calibration reports ─────────────────────────

def compute_ai_health_report(ai_health_snapshot: Optional[Dict[str, Any]] = None,
                              ai_health_history: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """
    AI Health Report — the current compute_ai_health() snapshot, plus
    (when a history log is supplied) the full ai_health_trends bundle
    including Regime Distribution.
    """
    report: Dict[str, Any] = {"generated_at": _iso(), "current": ai_health_snapshot or {}}
    if ai_health_history is not None:
        report["trends"] = _aht.build_health_trends_report(ai_health_history)
        report["regime_distribution"] = report["trends"]["regime_trend"]["distribution"]
    else:
        report["trends"] = None
        report["regime_distribution"] = None
    return report


def compute_walk_forward_summary(walk_forward_result: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Walk-Forward Summary — condenses a walk_forward.run_walk_forward()
    result. `available=False` (not a crash, not a guess) when no result
    was supplied or it had insufficient data — same convention every
    other report function in this module uses for missing input.
    """
    if not walk_forward_result or walk_forward_result.get("insufficient_data"):
        return {"available": False, "summary": None}
    return {"available": True, "summary": walk_forward_result.get("summary")}


def compute_calibration_summary(calibration_report: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Calibration Summary — condenses an adaptive_calibration.
    build_calibration_report() output, plus its own generated
    recommendations (reused, not recomputed).
    """
    if not calibration_report:
        return {"available": False}
    asset_cal = calibration_report.get("asset_calibration") or {}
    tf_cal = calibration_report.get("timeframe_calibration") or {}
    asset_ranking = asset_cal.get("ranking") or []
    tf_ranking = tf_cal.get("ranking") or []
    return {
        "available": True,
        "validation_trend_summary": {
            name: info.get("trend") for name, info in (calibration_report.get("validation_trend") or {}).items()
        },
        "indicator_stability_summary": {
            name: info.get("stability") for name, info in (calibration_report.get("indicator_stability") or {}).items()
        },
        "best_asset": asset_ranking[0] if asset_ranking else None,
        "best_timeframe": tf_ranking[0] if tf_ranking else None,
        "recommendations": _ac.generate_calibration_recommendations(calibration_report),
    }


# ─── Warnings ─────────────────────────────────────────────────────────────────

def generate_warnings(validation_report: Optional[Dict[str, Any]] = None,
                       indicator_report: Optional[Dict[str, Any]] = None,
                       ai_health_report: Optional[Dict[str, Any]] = None,
                       calibration_summary: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
    """
    Deterministic warning rules over already-built report sections — no
    scoring model, no ML. Every entry has message/evidence/severity.
    Returns an empty list (not an error) when nothing clears a threshold.
    Every input is optional; a section that wasn't supplied simply
    contributes no warnings from that source.
    """
    warnings: List[Dict[str, Any]] = []

    if validation_report:
        avg_acc = validation_report.get("average_accuracy")
        if avg_acc is not None and avg_acc < LOW_ACCURACY_WARNING_THRESHOLD:
            warnings.append({
                "message": f"System-wide average accuracy is {avg_acc}%, below the {LOW_ACCURACY_WARNING_THRESHOLD}% reference floor.",
                "evidence": {"average_accuracy": avg_acc}, "severity": "high",
            })
        if validation_report.get("total_samples", 0) < DEFAULT_MIN_SAMPLES * 5:
            warnings.append({
                "message": "Validation history is still thin system-wide — recent reports may be noisy.",
                "evidence": {"total_samples": validation_report.get("total_samples")}, "severity": "low",
            })
        acc_trend = validation_report.get("accuracy_trend") or {}
        if acc_trend.get("trend") == "degrading" and acc_trend.get("confidence") in ("medium", "high"):
            warnings.append({
                "message": "System-wide accuracy is trending downward across recent validation runs.",
                "evidence": acc_trend, "severity": "medium",
            })

    if indicator_report:
        no_data = indicator_report.get("no_data") or []
        top = indicator_report.get("top") or []
        weakest = indicator_report.get("weakest") or []
        total = len(no_data) + len(top) + len(weakest)
        if total > 0 and len(no_data) / total > 0.5:
            warnings.append({
                "message": "Over half of tracked indicators still lack enough Validation History to be scored.",
                "evidence": {"no_data_count": len(no_data), "total_indicators": total}, "severity": "low",
            })

    if ai_health_report:
        overall = ((ai_health_report.get("current") or {}).get("overall_health") or {})
        if overall.get("status") in ("Poor", "Critical"):
            warnings.append({
                "message": f"Overall AI Health is currently {overall.get('status')}.",
                "evidence": overall, "severity": "high" if overall.get("status") == "Critical" else "medium",
            })

    if calibration_summary and calibration_summary.get("available"):
        for rec in calibration_summary.get("recommendations") or []:
            if rec.get("severity") == "high":
                warnings.append({
                    "message": rec.get("reason"), "evidence": rec.get("evidence"), "severity": "high",
                })

    return warnings


# ─── Orchestration ───────────────────────────────────────────────────────────

def build_full_performance_report(validation_history: Optional[Dict[str, Any]] = None,
                                   recommendation: Optional[Dict[str, Any]] = None,
                                   ai_health_snapshot: Optional[Dict[str, Any]] = None,
                                   ai_health_history: Optional[Dict[str, Any]] = None,
                                   calibration_report: Optional[Dict[str, Any]] = None,
                                   walk_forward_result: Optional[Dict[str, Any]] = None,
                                   min_samples: int = DEFAULT_MIN_SAMPLES,
                                   top_n: int = DEFAULT_TOP_N) -> Dict[str, Any]:
    """
    Export-ready bundle of every report section this module produces —
    the shape /api/reports/export returns as-is.
    """
    asset_report = compute_asset_report(validation_history, min_samples)
    timeframe_report = compute_timeframe_report(validation_history, min_samples)
    indicator_report = compute_indicator_report(validation_history, min_samples, top_n)
    validation_report = compute_validation_report(validation_history, min_samples)
    learning_report = compute_learning_report(recommendation)
    ai_health_report = compute_ai_health_report(ai_health_snapshot, ai_health_history)
    calibration_summary = compute_calibration_summary(calibration_report)
    walk_forward_summary = compute_walk_forward_summary(walk_forward_result)

    return {
        "generated_at": _iso(),
        "daily": compute_daily_report(ai_health_history),
        "weekly": compute_weekly_report(ai_health_history),
        "monthly": compute_monthly_report(ai_health_history),
        "assets": asset_report,
        "timeframes": timeframe_report,
        "indicators": indicator_report,
        "validation": validation_report,
        "learning": learning_report,
        "ai_health": ai_health_report,
        "walk_forward": walk_forward_summary,
        "calibration": calibration_summary,
        "warnings": generate_warnings(validation_report, indicator_report, ai_health_report, calibration_summary),
    }
