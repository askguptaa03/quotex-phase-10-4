"""
Phase 9 — Smart Learning & Adaptive Weight System
====================================================
A new, standalone, additive module. It NEVER places trades, NEVER bypasses
Hard Gates, NEVER changes BUY/SELL direction, NEVER changes mandatory
filters, and NEVER edits historical validation data. It may ONLY recommend
improved indicator weights using accumulated Validation History, subject to
configurable safety limits (min/max weight per factor).

This module does NOT import from, call, or modify analyzer.py, backtest.py,
validation_engine.py, indicator_validation.py, scanner.py, or
indicator_registry.py. It reads two already-computed, read-only inputs:
  - a `current_weights` dict (the caller's job to supply — e.g.
    analyzer.DEFAULT_CONFLUENCE_WEIGHTS or
    settings_store.get_effective_dynamic_weights()) — this module never
    imports analyzer.py itself, matching validation_history_store.py's own
    decoupling convention.
  - the `history` dict produced by validation_history_store.ValidationHistoryStore
    .get_history() (rolling_stats + run_log) — this module only ever READS
    that store via its existing get_history() method; it has no write path
    into validation_history_store.py, so historical validation data can
    never be edited by this module, structurally, not just by convention.

The only thing this module writes to is its OWN JSON file
(learning_history.json, a bounded log of past recommendation snapshots),
using the exact same atomic-write / corrupted-JSON-recovery / bounded-list
pattern validation_history_store.py already established.

Applying a recommendation (writing it into settings.json) is NOT done by
this module either — that reuses the existing, unmodified
settings_store.apply_suggested_weights() function (the same one
backtest's "Apply Suggested Weights" already uses), called by the Flask
route in app.py. This module only ever produces a recommendation dict; it
never writes indicator weights anywhere itself.
"""

from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

SCHEMA_VERSION = "1.0"

# Same "don't trust a tiny sample" threshold convention already used by
# validation_history_store.py / indicator_validation.py / backtest.py
# (mirrored as an independent constant, not imported — same decoupling
# convention this whole file follows).
DEFAULT_MIN_SAMPLES = 20

# Safety limits (Step 2 requirement: "Never exceed configured max/min
# weight"). These bound the recommended weight for any single factor,
# regardless of how strong its rolling win-rate trend is — a runaway
# recommendation (e.g. weight -> 100 for one factor) is structurally
# impossible even if the rolling stats are noisy or momentarily extreme.
DEFAULT_MIN_WEIGHT = 2.0
DEFAULT_MAX_WEIGHT = 20.0

# How strongly a rolling win-rate trend nudges the recommended weight away
# from the current weight. 0.0 = never move; 1.0 = full-strength nudge
# proportional to (win_rate - 50%) / 50%. Kept conservative by default.
DEFAULT_LEARNING_RATE = 0.5

# Trend classification band (percentage points of win-rate difference
# between the most recent run and the all-time rolling average) — inside
# this band, the trend is reported as "stable" rather than
# "improving"/"degrading", so single-run noise doesn't flip the label.
TREND_BAND_PCT = 2.0

MAX_RECOMMENDATION_LOG_ENTRIES = 200


def _now() -> float:
    return time.time()


def _iso(ts: Optional[float] = None) -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(ts if ts is not None else _now()))


def _clamp(value: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, value))


def _confidence_label(total_samples: int, min_samples: int) -> str:
    if total_samples < min_samples:
        return "none"
    if total_samples < min_samples * 2:
        return "low"
    if total_samples < min_samples * 5:
        return "medium"
    return "high"


def _renormalize(weights: Dict[str, float]) -> Dict[str, float]:
    """
    Rescale so the set sums to exactly 100.0 — same "assign the rounding
    residual to the largest weight" convention already used in
    analyzer.DEFAULT_CONFLUENCE_WEIGHTS, backtest.compute_dynamic_weights(),
    and settings_store.get_effective_dynamic_weights(). Pure arithmetic,
    no factor-specific logic.
    """
    if not weights:
        return weights
    total = sum(weights.values())
    if total <= 0:
        return weights
    out = {k: round(v * 100.0 / total, 4) for k, v in weights.items()}
    drift = round(100.0 - sum(out.values()), 4)
    if drift != 0.0:
        top_key = max(out, key=out.get)
        out[top_key] = round(out[top_key] + drift, 4)
    return out


def compute_recommendation(current_weights: Dict[str, float],
                           history: Dict[str, Any],
                           min_weight: float = DEFAULT_MIN_WEIGHT,
                           max_weight: float = DEFAULT_MAX_WEIGHT,
                           learning_rate: float = DEFAULT_LEARNING_RATE,
                           min_samples: int = DEFAULT_MIN_SAMPLES) -> Dict[str, Any]:
    """
    Pure function, no I/O. Given today's confluence weights and the
    Validation History store's `get_history()` output, recommends an
    adjusted weight set.

    For any indicator NOT present in `history["rolling_stats"]` (currently
    everything except wick_rejection/liquidity_sweep/false_breakout — see
    validation_history_store.KNOWN_INDICATORS) or with fewer than
    `min_samples` accumulated samples, the recommendation is simply its
    current weight, unchanged — this module never fabricates a trend from
    data it doesn't have. Such factors are reported with trend="no_data",
    confidence="none".

    For indicators with sufficient rolling history, the recommended raw
    weight is:
        current_weight * (1 + learning_rate * (avg_win_rate - 50) / 50)
    clamped to [min_weight, max_weight] — never below min_weight, never
    above max_weight, regardless of how strong the trend is. The full
    13-factor set (unchanged factors + adjusted factors) is then
    renormalized to sum to exactly 100, preserving the same invariant
    every other weight set in this codebase already guarantees.

    Never reads or writes Hard Gates, Filter Score config, or BUY/SELL
    logic — it has no import of analyzer.py and no path to any of that.
    """
    rolling_stats = (history or {}).get("rolling_stats") or {}
    raw_weights: Dict[str, float] = {}
    per_indicator: Dict[str, Any] = {}

    for name, current_w in current_weights.items():
        stats = rolling_stats.get(name)
        total_samples = int(stats.get("total_samples", 0)) if stats else 0
        avg_win_rate = stats.get("average_win_rate_over_runs") if stats else None
        last_win_rate = stats.get("last_win_rate") if stats else None

        if not stats or total_samples < min_samples or avg_win_rate is None:
            raw_weights[name] = float(current_w)
            per_indicator[name] = {
                "current_weight": float(current_w),
                "recommended_weight": float(current_w),
                "trend": "no_data",
                "confidence": "none",
                "sample_count": total_samples,
                "average_win_rate": avg_win_rate,
                "last_win_rate": last_win_rate,
            }
            continue

        reference = last_win_rate if last_win_rate is not None else avg_win_rate
        diff = reference - avg_win_rate
        if diff > TREND_BAND_PCT:
            trend = "improving"
        elif diff < -TREND_BAND_PCT:
            trend = "degrading"
        else:
            trend = "stable"

        score_delta = (avg_win_rate - 50.0) / 50.0
        raw = float(current_w) * (1.0 + learning_rate * score_delta)
        recommended = round(_clamp(raw, min_weight, max_weight), 4)
        raw_weights[name] = recommended

        per_indicator[name] = {
            "current_weight": float(current_w),
            "recommended_weight": recommended,
            "trend": trend,
            "confidence": _confidence_label(total_samples, min_samples),
            "sample_count": total_samples,
            "average_win_rate": avg_win_rate,
            "last_win_rate": last_win_rate,
        }

    recommended_weights = _renormalize(raw_weights)
    # Reflect the post-renormalization value back into per_indicator so the
    # UI/API shows the number that would actually be applied.
    for name in per_indicator:
        per_indicator[name]["recommended_weight"] = recommended_weights.get(
            name, per_indicator[name]["recommended_weight"]
        )

    return {
        "generated_at": _iso(),
        "current_weights": dict(current_weights),
        "recommended_weights": recommended_weights,
        "per_indicator": per_indicator,
        "config_used": {
            "min_weight": min_weight,
            "max_weight": max_weight,
            "learning_rate": learning_rate,
            "min_samples": min_samples,
        },
    }


def _default_learning_history() -> Dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "recommendation_log": [],
    }


def _deep_merge_missing(data: Dict[str, Any], defaults: Dict[str, Any]) -> Dict[str, Any]:
    """Same forward-compatibility technique settings_store.py /
    validation_history_store.py use (reimplemented independently here,
    not imported — this module operates on its own, different schema)."""
    merged = dict(data)
    for key, default_value in defaults.items():
        if key not in merged:
            merged[key] = default_value
        elif isinstance(default_value, dict) and isinstance(merged.get(key), dict):
            merged[key] = _deep_merge_missing(merged[key], default_value)
    return merged


class LearningHistoryStore:
    """
    One JSON file, read-whole/write-whole, atomic on write — same pattern
    as validation_history_store.ValidationHistoryStore. Stores a bounded
    log of past recommendation snapshots (each one the full dict returned
    by compute_recommendation(), plus a timestamp). No locking (single-run
    assumption, same as the rest of this codebase's stores).
    """

    def __init__(self, path: str):
        self.path = Path(path)
        if not self.path.exists():
            self._write(_default_learning_history())

    def _read(self) -> Dict[str, Any]:
        try:
            with open(self.path, "r") as f:
                data = json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            data = _default_learning_history()
            self._write(data)
            return data
        defaults = _default_learning_history()
        merged = _deep_merge_missing(data, defaults)
        if merged != data:
            self._write(merged)
        return merged

    def _write(self, data: Dict[str, Any]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = str(self.path) + ".tmp"
        with open(tmp, "w") as f:
            json.dump(data, f, indent=2, sort_keys=True)
        os.replace(tmp, self.path)  # atomic on POSIX — avoids a torn write

    def get_history(self) -> Dict[str, Any]:
        """Bounded recommendation_log, most recent first."""
        return self._read()

    def record_recommendation(self, recommendation: Dict[str, Any]) -> Dict[str, Any]:
        """
        Appends one recommendation snapshot (as produced by
        compute_recommendation()) to the bounded log. Pure accumulation —
        does not recompute or reinterpret the recommendation.
        """
        data = self._read()
        data["recommendation_log"].insert(0, recommendation)
        data["recommendation_log"] = data["recommendation_log"][:MAX_RECOMMENDATION_LOG_ENTRIES]
        self._write(data)
        return data

    def reset(self) -> Dict[str, Any]:
        """Explicit, user-initiated only (never called automatically) —
        wipes recommendation_log back to empty. Does NOT touch
        validation_history_store.py's data — this only ever resets this
        module's own recommendation log, never historical validation
        results."""
        defaults = _default_learning_history()
        self._write(defaults)
        return defaults
