"""
Phase 10.2 — Asset Intelligence + Timeframe Intelligence
===========================================================
A new, standalone, additive module — same decoupling convention
`learning_engine.py` already established. Pure functions, no I/O of its
own, no persisted store. It NEVER places trades, NEVER touches Hard
Gates/Filter Score/BUY-SELL direction/confluence weights, and NEVER
writes anywhere — it only reads a `history` dict already produced by
`validation_history_store.ValidationHistoryStore.get_history()`
(specifically its Phase 10.2 `asset_stats`/`timeframe_stats` keys, plus
the pre-existing global `rolling_stats` for indicator-only rankings) and
returns computed rankings/recommendations.

This module does NOT import from, call, or modify analyzer.py,
backtest.py, validation_engine.py, indicator_validation.py, scanner.py,
settings_store.py, indicator_registry.py, or validation_history_store.py
itself — it has no write path into any of those, structurally, not just
by convention, matching every other "learning"-style module in this
project. It does not import learning_engine.py either — that module's
confluence-weight recommendation logic is a different concern (global
indicator weight tuning) from this one (which asset/timeframe/indicator
combination performs best); the two are independent and this phase does
not connect them.

Every function here is a pure function of its `history` argument: same
input always produces the same output, nothing is cached or mutated. No
history of past recommendation snapshots is persisted by this module —
unlike `learning_engine.py`'s `LearningHistoryStore`, Asset/Timeframe
Intelligence is always computed fresh from whatever `asset_stats`/
`timeframe_stats`/`rolling_stats` currently hold; there is no
`/api/learning/assets/history`-style endpoint in this phase's scope.
"""

from __future__ import annotations

import time
from typing import Any, Dict, List, Optional

# Same "don't trust a tiny sample" threshold convention already used by
# validation_history_store.py / indicator_validation.py / backtest.py /
# learning_engine.py (mirrored as an independent constant here, not
# imported — same decoupling convention this whole file follows).
DEFAULT_MIN_SAMPLES = 20

# Trend classification band (percentage points of win-rate difference
# between a pooled "recent" snapshot and a pooled "all-time" average) —
# inside this band the trend is reported as "stable" rather than
# "improving"/"declining", so single-run noise doesn't flip the label.
# Same value as learning_engine.TREND_BAND_PCT, mirrored independently.
TREND_BAND_PCT = 2.0

DEFAULT_TOP_N = 5


def _now() -> float:
    return time.time()


def _iso(ts: Optional[float] = None) -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(ts if ts is not None else _now()))


def _confidence_label(total_samples: int, min_samples: int) -> str:
    """Same banding convention as learning_engine._confidence_label(),
    reimplemented independently here (not imported)."""
    if total_samples < min_samples:
        return "none"
    if total_samples < min_samples * 2:
        return "low"
    if total_samples < min_samples * 5:
        return "medium"
    return "high"


def _pooled_indicator_stats(indicators: Dict[str, Dict[str, Any]], min_samples: int) -> Dict[str, Any]:
    """
    Pools rolling stats across every indicator recorded for ONE asset (or
    ONE timeframe) into a single group-level summary: total
    validations/wins/losses/accuracy, plus a trend/confidence computed
    from a SAMPLE-WEIGHTED pool of each indicator's `last_win_rate` (the
    "recent" snapshot) against a sample-weighted pool of each indicator's
    `average_win_rate_over_runs` (the "all-time" snapshot) — the same
    recent-vs-average comparison `learning_engine.py` uses per indicator,
    just weighted-pooled across every indicator in the group instead of
    read from a single indicator's stats. Indicators with no sufficient-
    sample win rate yet contribute their sample counts (they still count
    toward total_validations/wins/losses/accuracy) but not toward the
    trend pool, exactly mirroring how `record_run()`/
    `_apply_indicator_result_to_bucket()` never fold an insufficient-
    sample run's win_rate into `average_win_rate_over_runs` either.
    """
    total_samples = 0
    total_wins = 0
    total_losses = 0
    recent_weighted_sum = 0.0
    recent_weight = 0
    avg_weighted_sum = 0.0
    avg_weight = 0

    for stats in indicators.values():
        s = stats.get("total_samples", 0) or 0
        total_samples += s
        total_wins += stats.get("total_wins", 0) or 0
        total_losses += stats.get("total_losses", 0) or 0

        last_wr = stats.get("last_win_rate")
        if last_wr is not None and s > 0:
            recent_weighted_sum += last_wr * s
            recent_weight += s

        avg_wr = stats.get("average_win_rate_over_runs")
        if avg_wr is not None and s > 0:
            avg_weighted_sum += avg_wr * s
            avg_weight += s

    accuracy = round(total_wins / total_samples * 100, 2) if total_samples > 0 else None
    confidence = _confidence_label(total_samples, min_samples)

    trend = "no_data"
    if recent_weight > 0 and avg_weight > 0:
        recent_pooled = recent_weighted_sum / recent_weight
        avg_pooled = avg_weighted_sum / avg_weight
        diff = recent_pooled - avg_pooled
        if diff > TREND_BAND_PCT:
            trend = "improving"
        elif diff < -TREND_BAND_PCT:
            trend = "declining"
        else:
            trend = "stable"

    return {
        "total_validations": total_samples,
        "wins": total_wins,
        "losses": total_losses,
        "accuracy": accuracy,
        "trend": trend,
        "confidence": confidence,
    }


def _best_and_weakest_indicator(indicators: Dict[str, Dict[str, Any]], min_samples: int) -> Dict[str, Optional[str]]:
    """
    Among indicators in this group with a confident (non-"none")
    win-rate reading, returns the highest- and lowest-`average_win_rate_
    over_runs` indicator name. Both are None if no indicator in the group
    has accumulated `min_samples` yet — this module never guesses a
    "best" indicator from data it doesn't have.
    """
    eligible = {
        name: stats for name, stats in indicators.items()
        if (stats.get("total_samples", 0) or 0) >= min_samples
        and stats.get("average_win_rate_over_runs") is not None
    }
    if not eligible:
        return {"best_indicator": None, "weakest_indicator": None}
    best = max(eligible, key=lambda n: eligible[n]["average_win_rate_over_runs"])
    weakest = min(eligible, key=lambda n: eligible[n]["average_win_rate_over_runs"])
    return {"best_indicator": best, "weakest_indicator": weakest}


def _rank_group(group_stats: Dict[str, Dict[str, Any]], min_samples: int) -> Dict[str, Any]:
    """One asset's (or one timeframe's) full computed entry: pooled
    totals/accuracy/trend/confidence + best/weakest indicator + the raw
    per-indicator stats passed through unmodified for callers that want
    the detail."""
    pooled = _pooled_indicator_stats(group_stats, min_samples)
    picks = _best_and_weakest_indicator(group_stats, min_samples)
    return {**pooled, **picks, "indicators": group_stats}


def _ranking_order(groups: Dict[str, Dict[str, Any]], min_samples: int) -> List[str]:
    """
    Best-to-worst key order by accuracy, restricted to groups that have
    reached `min_samples` total validations — same "don't let a tiny,
    lucky sample outrank a large, reliable one" gate every other
    confidence-scored value in this codebase already applies (e.g.
    `_best_and_weakest_indicator()` above, `learning_engine.
    _confidence_label()`). A group below `min_samples` still appears in
    the full `assets`/`timeframes` dict with its real (if noisy) accuracy
    value — it is only excluded from this specific ordered list, not
    hidden from the response entirely.
    """
    scored = [k for k, v in groups.items() if v["accuracy"] is not None and v["total_validations"] >= min_samples]
    return sorted(scored, key=lambda k: groups[k]["accuracy"], reverse=True)


def compute_asset_rankings(history: Dict[str, Any], min_samples: int = DEFAULT_MIN_SAMPLES) -> Dict[str, Any]:
    """
    Step 3 — Asset Learning. For every OTC asset with recorded Validation
    History (`history["asset_stats"]`, Phase 10.2): total validations,
    wins, losses, accuracy, trend, confidence, plus that asset's best-
    and weakest-performing indicator. `ranking` is a best-to-worst
    ordered list of asset names by accuracy (assets with zero recorded
    samples are included in `assets` but omitted from `ranking`).
    """
    asset_stats = (history or {}).get("asset_stats") or {}
    assets = {asset: _rank_group(indicators, min_samples) for asset, indicators in asset_stats.items()}
    return {"generated_at": _iso(), "min_samples": min_samples, "assets": assets, "ranking": _ranking_order(assets, min_samples)}


def compute_timeframe_rankings(history: Dict[str, Any], min_samples: int = DEFAULT_MIN_SAMPLES) -> Dict[str, Any]:
    """
    Step 4 — Timeframe Learning. Identical computation to
    `compute_asset_rankings()`, grouped by timeframe
    (`history["timeframe_stats"]`) instead of asset. Works for any
    timeframe string actually present in Validation History — 1m, 5m,
    15m, or any other supported timeframe — since neither this module nor
    `validation_history_store.py` hardcodes a fixed timeframe enum
    anywhere (see validation_history_store.py's SCHEMA_VERSION changelog).
    """
    timeframe_stats = (history or {}).get("timeframe_stats") or {}
    timeframes = {tf: _rank_group(indicators, min_samples) for tf, indicators in timeframe_stats.items()}
    return {"generated_at": _iso(), "min_samples": min_samples, "timeframes": timeframes,
            "ranking": _ranking_order(timeframes, min_samples)}


def compute_top_indicators(history: Dict[str, Any], min_samples: int = DEFAULT_MIN_SAMPLES,
                            top_n: int = DEFAULT_TOP_N) -> Dict[str, Any]:
    """
    Global (not asset/timeframe-scoped) indicator ranking from the
    pre-existing `rolling_stats` (Phase 8.5/10.1 data — unchanged by this
    phase). "Which indicators are currently weak" / "which should be
    preferred" at the whole-system level. Only indicators with
    `min_samples`+ accumulated samples and a computed
    `average_win_rate_over_runs` are eligible for `top`/`weakest`;
    everything else is reported in `no_data` instead of guessed at.
    """
    rolling_stats = (history or {}).get("rolling_stats") or {}
    eligible = []
    no_data = []
    for name, stats in rolling_stats.items():
        total_samples = stats.get("total_samples", 0) or 0
        avg_wr = stats.get("average_win_rate_over_runs")
        if total_samples >= min_samples and avg_wr is not None:
            eligible.append({
                "indicator": name,
                "average_win_rate": avg_wr,
                "last_win_rate": stats.get("last_win_rate"),
                "total_samples": total_samples,
                "confidence": _confidence_label(total_samples, min_samples),
            })
        else:
            no_data.append({"indicator": name, "total_samples": total_samples, "confidence": "none"})

    ranked = sorted(eligible, key=lambda e: e["average_win_rate"], reverse=True)
    return {
        "generated_at": _iso(),
        "min_samples": min_samples,
        "top": ranked[:top_n],
        "weakest": list(reversed(ranked[-top_n:])) if ranked else [],
        "no_data": no_data,
    }


def compute_recommendations(history: Dict[str, Any], min_samples: int = DEFAULT_MIN_SAMPLES,
                             top_n: int = DEFAULT_TOP_N) -> Dict[str, Any]:
    """
    Step 5 — Learning Recommendations. Advisory only, same as every other
    "recommend" function in this project — never applied automatically,
    never writes anywhere. Combines:
      - best_indicators_per_asset:     {asset: best_indicator or None}
      - best_indicators_per_timeframe: {timeframe: best_indicator or None}
      - lowest_performing_indicators:  from compute_top_indicators()'s
                                        global `weakest`
      - improving_indicators / declining_indicators: from the GLOBAL
        `rolling_stats` trend (same recent-vs-average comparison
        `_pooled_indicator_stats()` uses, applied to a single indicator's
        own `last_win_rate` vs `average_win_rate_over_runs` rather than a
        pooled group — i.e. genuinely per-indicator, system-wide trend,
        not asset/timeframe-scoped)
    """
    asset_rankings = compute_asset_rankings(history, min_samples)
    timeframe_rankings = compute_timeframe_rankings(history, min_samples)
    top_indicators = compute_top_indicators(history, min_samples, top_n)

    best_per_asset = {asset: v["best_indicator"] for asset, v in asset_rankings["assets"].items()}
    best_per_timeframe = {tf: v["best_indicator"] for tf, v in timeframe_rankings["timeframes"].items()}

    rolling_stats = (history or {}).get("rolling_stats") or {}
    improving: List[Dict[str, Any]] = []
    declining: List[Dict[str, Any]] = []
    for name, stats in rolling_stats.items():
        total_samples = stats.get("total_samples", 0) or 0
        avg_wr = stats.get("average_win_rate_over_runs")
        last_wr = stats.get("last_win_rate")
        if total_samples < min_samples or avg_wr is None or last_wr is None:
            continue
        diff = last_wr - avg_wr
        entry = {
            "indicator": name, "average_win_rate": avg_wr, "last_win_rate": last_wr,
            "difference": round(diff, 2), "total_samples": total_samples,
            "confidence": _confidence_label(total_samples, min_samples),
        }
        if diff > TREND_BAND_PCT:
            improving.append(entry)
        elif diff < -TREND_BAND_PCT:
            declining.append(entry)

    improving.sort(key=lambda e: e["difference"], reverse=True)
    declining.sort(key=lambda e: e["difference"])

    return {
        "generated_at": _iso(),
        "min_samples": min_samples,
        "best_indicators_per_asset": best_per_asset,
        "best_indicators_per_timeframe": best_per_timeframe,
        "lowest_performing_indicators": top_indicators["weakest"],
        "improving_indicators": improving,
        "declining_indicators": declining,
    }
