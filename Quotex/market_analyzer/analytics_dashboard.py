"""
Phase 10.4 Goal 5 — Advanced Analytics Dashboard (data layer).

Purely additive module. Does NOT modify ai_performance_reports.py (Goal
4's verified file), adaptive_calibration.py, ai_health_trends.py,
ai_health_history_store.py, walk_forward.py, analyzer.py, backtest.py,
scanner.py, learning_engine.py, indicator_registry.py, or the Quotex API.

Same decoupling convention every Phase 10.4 module already establishes:
no I/O of its own, no persisted store. This module adds exactly ONE piece
of data no existing module computes (compute_validation_distribution —
per-indicator win/loss counts, for a distribution chart), then bundles it
together with ai_performance_reports.build_full_performance_report()'s
already-complete output (reused, not recomputed) into the single payload
the new /analytics dashboard page fetches.

No machine-learning libraries. No external services.
"""

from __future__ import annotations

from typing import Any, Dict, Optional

import ai_performance_reports as _reports

__all__ = ["compute_validation_distribution", "build_analytics_dashboard"]


def compute_validation_distribution(validation_history: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Validation Distribution — per-indicator win/loss counts straight from
    rolling_stats (already-recorded data, never recomputed), plus the
    system-wide win/loss totals. The one piece of data none of Goals
    1-4's modules already expose.
    """
    rolling_stats = (validation_history or {}).get("rolling_stats") or {}
    indicators: Dict[str, Any] = {}
    total_wins = 0
    total_losses = 0
    for name, stats in rolling_stats.items():
        stats = stats or {}
        wins = int(stats.get("total_wins", 0) or 0)
        losses = int(stats.get("total_losses", 0) or 0)
        indicators[name] = {
            "total_samples": int(stats.get("total_samples", 0) or 0),
            "total_wins": wins,
            "total_losses": losses,
            "average_win_rate": stats.get("average_win_rate_over_runs"),
        }
        total_wins += wins
        total_losses += losses
    return {"indicators": indicators, "total_wins": total_wins, "total_losses": total_losses}


def build_analytics_dashboard(validation_history: Optional[Dict[str, Any]] = None,
                               recommendation: Optional[Dict[str, Any]] = None,
                               ai_health_snapshot: Optional[Dict[str, Any]] = None,
                               ai_health_history: Optional[Dict[str, Any]] = None,
                               calibration_report: Optional[Dict[str, Any]] = None,
                               walk_forward_result: Optional[Dict[str, Any]] = None,
                               min_samples: int = _reports.DEFAULT_MIN_SAMPLES,
                               top_n: int = _reports.DEFAULT_TOP_N) -> Dict[str, Any]:
    """
    The exact payload /api/analytics/dashboard returns. Delegates the
    daily/weekly/monthly/assets/timeframes/indicators/validation/
    learning/ai_health/walk_forward/calibration/warnings sections
    entirely to ai_performance_reports.build_full_performance_report()
    (Goal 4, unmodified, reused as-is) and adds `validation_distribution`
    and a `regime_distribution` convenience alias (already present one
    level deeper at ai_health.regime_distribution — surfaced at the top
    level too, since the dashboard renders it as its own chart).
    """
    full = _reports.build_full_performance_report(
        validation_history=validation_history, recommendation=recommendation,
        ai_health_snapshot=ai_health_snapshot, ai_health_history=ai_health_history,
        calibration_report=calibration_report, walk_forward_result=walk_forward_result,
        min_samples=min_samples, top_n=top_n,
    )
    full["validation_distribution"] = compute_validation_distribution(validation_history)
    full["regime_distribution"] = full["ai_health"]["regime_distribution"]
    return full
