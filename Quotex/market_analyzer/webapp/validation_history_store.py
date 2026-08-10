"""
Phase 8.5 — Validation History Store
======================================
A new, standalone, additive module for persisting Indicator Validation
results ACROSS runs and restarts — the one real gap identified in the
Phase 8.5 audit: `ValidationEngine.results`/`.summary` are plain
in-memory dicts, wiped on every `start()` call, with nothing surviving
a process restart.

This module does NOT import from, call, or modify `validation_engine.py`,
`indicator_validation.py`, `analyzer.py`, `backtest.py`, `scanner.py`,
`settings_store.py`, or `indicator_registry.py`. It has no path back into
Confluence, the filter score, or indicator voting — it only ever reads a
`summary` dict already computed by `ValidationEngine._build_summary()`
and writes to its own JSON file. Learning/history stays completely
independent from the confluence engine by construction: there is no
import, no call, and no write target anywhere in this file that touches
any of those modules.

I/O pattern deliberately mirrors settings_store.py's own (read-only
reference — this module does not import it): atomic write via a
temp-file + `os.replace()` (POSIX-atomic, avoids a torn write), auto-
create sane defaults on first use, and a forward-compatible merge on
read so a future schema addition doesn't break an older history.json.

Bounded growth, by design:
  - `rolling_stats` is O(1) in size — exactly one entry per known
    indicator (currently 3), updated in place every run. It never grows
    with the number of runs.
  - `run_log` is the only part that grows with each run, so it is
    explicitly capped at `MAX_RUN_LOG_ENTRIES` (oldest entries are
    dropped first) — this file can never grow unbounded.
"""

from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Any, Dict, Optional

SCHEMA_VERSION = "1.2"
# History schema changelog:
#   1.0 (Phase 8.5)  — rolling_stats/run_log for the 3 OTC-specific
#                       indicators only (wick_rejection, liquidity_sweep,
#                       false_breakout).
#   1.1 (Phase 10.1) — KNOWN_INDICATORS widened to all 13 confluence
#                       factors (Universal Validation). BACKWARD-COMPATIBLE
#                       MIGRATION: an existing 1.0 history.json on disk is
#                       never rewritten or discarded — `_read()`'s existing
#                       "backfill any indicator missing from rolling_stats"
#                       loop (unchanged code, see below) transparently adds
#                       the 10 newly-known indicators' default rolling-stats
#                       entries the first time the file is read under this
#                       version, exactly the forward-compatibility path this
#                       module's docstring already promised when it was
#                       written. The 3 original indicators' accumulated
#                       history (`total_samples`, `total_wins`,
#                       `average_win_rate_over_runs`, etc.) is untouched —
#                       nothing is reset, renamed, or moved. `run_log`
#                       entries recorded under 1.0 remain valid as-is (a
#                       `per_indicator` dict with only 3 keys is still a
#                       well-formed entry; `record_run()` only ever adds
#                       keys for indicators actually present in a given
#                       run's summary, so old and new entries coexist in
#                       the same capped list without any special-casing).
#                       `schema_version` in an old file is bumped to "1.1"
#                       on next write (via the existing `if merged != data:
#                       self._write(merged)` check in `_read()`) purely as
#                       a record of when the migration happened — it does
#                       not gate or change any read/write behavior itself.
#   1.2 (Phase 10.2) — Asset Intelligence + Timeframe Intelligence. Adds
#                       two NEW top-level keys, `asset_stats` and
#                       `timeframe_stats` — each `{key: {indicator:
#                       rolling-stats-dict}}`, same per-indicator shape
#                       `rolling_stats` already uses (see
#                       `_default_indicator_rolling_stats()`), just grouped
#                       one level deeper by asset / by timeframe instead of
#                       folded into a single global total. BACKWARD-
#                       COMPATIBLE MIGRATION: an existing 1.0/1.1
#                       history.json is never rewritten or discarded — the
#                       existing `_deep_merge_missing()` call already
#                       backfills any top-level key present in
#                       `_default_history()` but missing from the file
#                       (`asset_stats`/`timeframe_stats` now included) the
#                       first time it's read under this version. Unlike
#                       `KNOWN_INDICATORS` (a small, fixed 13-entry set,
#                       eligible to be pre-populated with defaults),
#                       assets/timeframes are unbounded, freeform,
#                       caller-supplied strings — see `record_run()`'s own
#                       "no fixed enum anywhere in this codebase" note —
#                       so both new dicts start EMPTY (`{}`) rather than
#                       pre-populated, and entries are created lazily, one
#                       per distinct asset/timeframe actually seen, the
#                       first time `record_asset_timeframe_stats()` records
#                       data for it. `rolling_stats`/`run_log` (both
#                       pre-existing) are completely untouched by this
#                       migration — nothing in them is read, moved, or
#                       recalculated to populate the two new keys; they are
#                       populated ONLY going forward, by
#                       `record_asset_timeframe_stats()`, from data a
#                       caller explicitly supplies each time it's called
#                       (see that method's docstring). An old file that
#                       never has `record_asset_timeframe_stats()` called
#                       against it keeps `asset_stats`/`timeframe_stats`
#                       permanently empty — that is expected, not a bug;
#                       Asset/Timeframe Intelligence simply has no history
#                       to report until new validation runs are recorded
#                       with the new method. Growth is now proportional to
#                       (distinct assets + distinct timeframes actually
#                       validated) x 13 indicators, unlike `rolling_stats`
#                       which is a fixed O(1) size — documented and
#                       accepted, not unbounded like `run_log` (no per-run
#                       log is kept at this granularity, only rolling
#                       totals, same bounded-growth discipline as
#                       `rolling_stats`).

# Same threshold ValidationEngine/indicator_validation.py use (mirrored as
# an independent constant here, not imported — this module has zero
# dependency on either file). Below this, a run's per-indicator win-rate
# is not folded into the rolling average, so accumulated noise from tiny
# samples can't masquerade as a real trend over time.
MIN_SIGNALS_REQUIRED = 20

# Bounded history: only the most recent N run summaries are kept. This
# value only affects `run_log`'s length — `rolling_stats` is unaffected
# and stays exactly 1 entry per indicator regardless of this number.
MAX_RUN_LOG_ENTRIES = 200

# Phase 10.1: widened from the original 3 (wick_rejection, liquidity_sweep,
# false_breakout) to the full 13-factor confluence set, mirroring
# indicator_validation.UNIVERSAL_INDICATOR_NAMES's value as an INDEPENDENT
# constant (not imported — this module's whole design point, stated in the
# module docstring above, is zero dependency on indicator_validation.py/
# validation_engine.py/analyzer.py/backtest.py). Order matches
# UNIVERSAL_INDICATOR_NAMES/analyzer.DEFAULT_CONFLUENCE_WEIGHTS for
# consistency, though dict key order has no behavioral effect here.
KNOWN_INDICATORS = (
    "bb", "rsi_div", "stoch", "cci", "candle", "mean_reversion",
    "exhaustion", "round_number", "obv", "sr",
    "wick_rejection", "liquidity_sweep", "false_breakout",
)
assert len(KNOWN_INDICATORS) == 13


def _now() -> float:
    return time.time()


def _iso(ts: Optional[float] = None) -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(ts if ts is not None else _now()))


def _default_indicator_rolling_stats() -> Dict[str, Any]:
    return {
        "runs_recorded": 0,
        "runs_with_sufficient_sample": 0,
        "total_samples": 0,
        "total_wins": 0,
        "total_losses": 0,
        "total_buy_signals": 0,
        "total_sell_signals": 0,
        "last_win_rate": None,
        "average_win_rate_over_runs": None,
        "average_strength": None,
        "average_reliability": None,
        "last_updated": None,
    }


def _default_history() -> Dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "rolling_stats": {name: _default_indicator_rolling_stats() for name in KNOWN_INDICATORS},
        "run_log": [],
        # Phase 10.2 — populated lazily by record_asset_timeframe_stats();
        # see the SCHEMA_VERSION changelog above for why these start empty
        # rather than pre-populated like rolling_stats.
        "asset_stats": {},
        "timeframe_stats": {},
    }


def _deep_merge_missing(data: Dict[str, Any], defaults: Dict[str, Any]) -> Dict[str, Any]:
    """
    Backfills any key present in `defaults` but missing from `data`,
    recursively — same forward-compatibility technique settings_store.py
    uses (reimplemented independently here, not imported, since
    settings_store.py is off-limits and this operates on a completely
    different schema). Existing values in `data` are never overwritten;
    only missing keys are added.
    """
    merged = dict(data)
    for key, default_value in defaults.items():
        if key not in merged:
            merged[key] = default_value
        elif isinstance(default_value, dict) and isinstance(merged.get(key), dict):
            merged[key] = _deep_merge_missing(merged[key], default_value)
    return merged


def _apply_indicator_result_to_bucket(stats: Dict[str, Any], result: Dict[str, Any], ts: str) -> None:
    """
    Phase 10.2. Accumulates ONE `validate_indicator_universal()` result
    dict (a single (asset, timeframe, indicator) combination's outcome)
    into a rolling-stats bucket, in place. Same per-run rolling-mean
    convention `ValidationHistoryStore.record_run()` already uses for the
    global `rolling_stats` (incremental mean gated by sufficient-sample
    for win rate; strength/reliability averaged over every run
    regardless of sample size) — a separate, parallel implementation
    rather than shared code, since the input shape differs: this
    consumes ONE raw combination's result (`samples`/`wins`/`losses`/
    `win_rate`/`sufficient_sample`, from `indicator_validation.py`),
    while `record_run()` consumes an already-cross-combination-averaged
    summary entry (`total_samples`/`average_win_rate_where_sufficient`,
    from `ValidationEngine._build_summary()`) — genuinely different
    shapes, not the same logic duplicated.
    """
    samples = result.get("samples", 0) or 0
    stats["runs_recorded"] += 1
    stats["total_samples"] += samples
    stats["total_wins"] += result.get("wins", 0) or 0
    stats["total_losses"] += result.get("losses", 0) or 0
    stats["total_buy_signals"] += result.get("buy_signals", 0) or 0
    stats["total_sell_signals"] += result.get("sell_signals", 0) or 0

    win_rate = result.get("win_rate")
    sufficient = bool(result.get("sufficient_sample"))
    if win_rate is not None and sufficient:
        stats["last_win_rate"] = win_rate
        prev_n = stats["runs_with_sufficient_sample"]
        prev_avg = stats["average_win_rate_over_runs"] or 0.0
        new_n = prev_n + 1
        stats["average_win_rate_over_runs"] = round((prev_avg * prev_n + win_rate) / new_n, 2)
        stats["runs_with_sufficient_sample"] = new_n

    avg_strength = result.get("average_strength")
    if avg_strength is not None:
        prev_n = max(stats["runs_recorded"] - 1, 0)
        prev_avg = stats["average_strength"] or 0.0
        stats["average_strength"] = round((prev_avg * prev_n + avg_strength) / stats["runs_recorded"], 2)

    avg_reliability = result.get("average_reliability")
    if avg_reliability is not None:
        prev_n = max(stats["runs_recorded"] - 1, 0)
        prev_avg = stats["average_reliability"] or 0.0
        stats["average_reliability"] = round((prev_avg * prev_n + avg_reliability) / stats["runs_recorded"], 2)

    stats["last_updated"] = ts


class ValidationHistoryStore:
    """
    One JSON file, read-whole/write-whole, atomic on write. No locking
    (same as settings_store.py) — acceptable because ValidationEngine
    already enforces single-run-at-a-time, so concurrent writers are not
    expected in normal operation.
    """

    def __init__(self, path: str):
        self.path = Path(path)
        if not self.path.exists():
            self._write(_default_history())

    # ── Low-level I/O (mirrors settings_store.py's pattern exactly) ─────────
    def _read(self) -> Dict[str, Any]:
        try:
            with open(self.path, "r") as f:
                data = json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            data = _default_history()
            self._write(data)
            return data
        defaults = _default_history()
        # Detect whether this file predates Phase 10.1's 13-indicator
        # KNOWN_INDICATORS, and/or Phase 10.2's asset_stats/timeframe_stats
        # keys (i.e. genuine migration, not just a routine read) BEFORE
        # merging — `_deep_merge_missing()` below already recursively
        # backfills any key present in `defaults` but missing from `data`
        # on its own (since `_default_history()` now includes all of
        # these), so checking `merged` AFTER that call would always find
        # everything already present and never detect that a migration
        # just happened. Same fix already proven for the 1.0->1.1
        # indicator migration, applied again here for 1.1->1.2.
        pre_merge_indicator_keys = set((data.get("rolling_stats") or {}).keys())
        migrated_indicators = bool(set(KNOWN_INDICATORS) - pre_merge_indicator_keys)
        migrated_asset_timeframe_stats = (
            "asset_stats" not in data or "timeframe_stats" not in data
        )

        merged = _deep_merge_missing(data, defaults)
        # Extra defensive backfill (belt-and-suspenders): covers the
        # pathological case of a `rolling_stats` value that isn't itself a
        # dict (so the recursive branch above wouldn't have fired) or any
        # other structural drift — same intent as the original Phase 8.5
        # loop, just re-checked post-merge in case anything is still
        # missing.
        for name in KNOWN_INDICATORS:
            if name not in merged["rolling_stats"]:
                merged["rolling_stats"][name] = _default_indicator_rolling_stats()
                migrated_indicators = True
        for key in ("asset_stats", "timeframe_stats"):
            if key not in merged or not isinstance(merged.get(key), dict):
                merged[key] = {}
                migrated_asset_timeframe_stats = True

        # Bump `schema_version` to the CURRENT SCHEMA_VERSION specifically
        # (and only) when real migration happened — `_deep_merge_missing()`
        # never overwrites an already-present key, so an old file's
        # `schema_version: "1.0"`/`"1.1"` would otherwise never advance
        # even though it just gained new entries/keys.
        if (migrated_indicators or migrated_asset_timeframe_stats) and merged.get("schema_version") != SCHEMA_VERSION:
            merged["schema_version"] = SCHEMA_VERSION

        if merged != data:
            self._write(merged)
        return merged

    def _write(self, data: Dict[str, Any]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = str(self.path) + ".tmp"
        with open(tmp, "w") as f:
            json.dump(data, f, indent=2, sort_keys=True)
        os.replace(tmp, self.path)  # atomic on POSIX — avoids a torn write

    # ── Public API ───────────────────────────────────────────────────────────
    def get_history(self) -> Dict[str, Any]:
        """Full stored history: rolling_stats (all indicators) + the
        capped run_log (most recent first)."""
        return self._read()

    def get_indicator_history(self, indicator: str) -> Dict[str, Any]:
        """
        Rolling stats for ONE indicator plus only the run_log entries
        that mention it. Returns rolling_stats=None (not an exception)
        for an indicator this store has never heard of, so a typo/future
        indicator name fails soft rather than 500ing a route.
        """
        data = self._read()
        rolling = data["rolling_stats"].get(indicator)
        matching_runs = [
            run for run in data["run_log"]
            if indicator in (run.get("per_indicator") or {})
        ]
        return {"indicator": indicator, "rolling_stats": rolling, "run_log": matching_runs}

    def record_run(self, summary: Dict[str, Any], timestamp: Optional[str] = None) -> Dict[str, Any]:
        """
        Records ONE completed validation run's summary (the exact dict
        shape `ValidationEngine.get_results()["summary"]` already
        produces — this function does not recompute or reinterpret any
        indicator statistic, it only accumulates what's already been
        calculated). Updates the O(1)-sized rolling_stats in place and
        appends a capped entry to run_log. Returns the updated full
        history (same shape as get_history()).

        Safe to call with a summary that has an empty/missing
        `per_indicator` (e.g. every combination in that run failed to
        fetch) — such a run is still logged (so its failure is visible
        in run_log) but contributes nothing to rolling_stats.
        """
        data = self._read()
        ts = timestamp or _iso()
        per_indicator = (summary or {}).get("per_indicator") or {}

        for name in KNOWN_INDICATORS:
            stats = data["rolling_stats"].setdefault(name, _default_indicator_rolling_stats())
            entry = per_indicator.get(name)
            if not entry:
                continue  # this indicator wasn't part of this run — leave its rolling stats untouched

            stats["runs_recorded"] += 1
            stats["total_samples"] += entry.get("total_samples", 0) or 0
            stats["total_wins"] += entry.get("total_wins", 0) or 0
            stats["total_losses"] += entry.get("total_losses", 0) or 0
            stats["total_buy_signals"] += entry.get("total_buy_signals", 0) or 0
            stats["total_sell_signals"] += entry.get("total_sell_signals", 0) or 0

            win_rate = entry.get("average_win_rate_where_sufficient")
            has_sufficient = (entry.get("combinations_with_sufficient_sample") or 0) > 0
            if win_rate is not None and has_sufficient:
                stats["last_win_rate"] = win_rate
                # Incremental mean across only the runs that had a sufficient
                # sample — same MIN_SIGNALS_REQUIRED-gated spirit as the
                # per-run summary itself, applied again over time so a run
                # of tiny/unreliable samples can't drag the trend around.
                prev_n = stats["runs_with_sufficient_sample"]
                prev_avg = stats["average_win_rate_over_runs"] or 0.0
                new_n = prev_n + 1
                stats["average_win_rate_over_runs"] = round((prev_avg * prev_n + win_rate) / new_n, 2)
                stats["runs_with_sufficient_sample"] = new_n

            avg_strength = entry.get("average_strength")
            if avg_strength is not None:
                prev_n = max(stats["runs_recorded"] - 1, 0)
                prev_avg = stats["average_strength"] or 0.0
                stats["average_strength"] = round((prev_avg * prev_n + avg_strength) / stats["runs_recorded"], 2)

            avg_reliability = entry.get("average_reliability")
            if avg_reliability is not None:
                prev_n = max(stats["runs_recorded"] - 1, 0)
                prev_avg = stats["average_reliability"] or 0.0
                stats["average_reliability"] = round((prev_avg * prev_n + avg_reliability) / stats["runs_recorded"], 2)

            stats["last_updated"] = ts

        data["run_log"].insert(0, {
            "timestamp": ts,
            "combinations_validated": (summary or {}).get("combinations_validated", 0),
            "combinations_failed": (summary or {}).get("combinations_failed", 0),
            "per_indicator": per_indicator,
        })
        data["run_log"] = data["run_log"][:MAX_RUN_LOG_ENTRIES]  # bounded — oldest entries dropped first

        self._write(data)
        return data

    def reset(self) -> Dict[str, Any]:
        """Explicit, user-initiated only (never called automatically) —
        wipes rolling_stats, run_log, asset_stats, and timeframe_stats
        back to empty defaults."""
        defaults = _default_history()
        self._write(defaults)
        return defaults

    # ── Phase 10.2 — Asset Intelligence + Timeframe Intelligence ───────────
    # Everything below this line is ADDITIVE. get_history()/
    # get_indicator_history()/record_run()/reset() above are completely
    # unmodified in behavior (reset() now also clears the two new keys —
    # see its docstring above — but that is reset()'s pre-existing
    # "wipe everything back to defaults" contract, not new logic).

    def get_asset_stats(self, asset: Optional[str] = None) -> Dict[str, Any]:
        """
        Per-indicator rolling stats for ONE asset (or every asset this
        store has ever recorded data for, if `asset` is omitted). Shaped
        exactly like `rolling_stats`, just one level deeper (asset ->
        indicator -> rolling-stats-dict). Returns an empty
        `{"indicators": {}}` (not an exception) for an asset this store
        has never heard of — same fails-soft convention
        `get_indicator_history()` already uses for an unknown indicator.
        """
        data = self._read()
        if asset is not None:
            return {"asset": asset, "indicators": data["asset_stats"].get(asset, {})}
        return data["asset_stats"]

    def get_timeframe_stats(self, timeframe: Optional[str] = None) -> Dict[str, Any]:
        """Same as `get_asset_stats()`, grouped by timeframe instead."""
        data = self._read()
        if timeframe is not None:
            return {"timeframe": timeframe, "indicators": data["timeframe_stats"].get(timeframe, {})}
        return data["timeframe_stats"]

    def record_asset_timeframe_stats(self, results: Dict[str, Any],
                                      timestamp: Optional[str] = None) -> Dict[str, Any]:
        """
        Records ONE completed validation run's RAW per-combination
        results into per-asset and per-timeframe rolling stats. Expects
        exactly the dict shape `ValidationEngine.get_results()["results"]`
        already produces: keyed `"asset|timeframe" -> {asset, timeframe,
        indicators: {name: validate_indicator_universal() output}, ...}`
        for a successful combination, or `{asset, timeframe, error: ...}`
        for a failed one — failed combinations are skipped here, the same
        way `ValidationEngine._build_summary()` already filters them out
        one layer up before `record_run()` ever sees them.

        Purely additive accumulation via `_apply_indicator_result_to_bucket()`
        below — does not recompute or reinterpret any statistic
        `validate_indicator_universal()` already computed. Completely
        INDEPENDENT of `record_run()`: this method never reads or writes
        `rolling_stats`/`run_log`, and `record_run()` never reads or
        writes `asset_stats`/`timeframe_stats`. A caller can call either,
        both, or neither after a run completes without affecting the
        other's behavior at all.

        Any indicator name not in `KNOWN_INDICATORS` is silently ignored
        (defensive — mirrors `record_run()`'s own implicit gating, since
        that loop only ever iterates `KNOWN_INDICATORS`); any combination
        missing an `asset`/`timeframe` field is skipped rather than
        raising, so a malformed entry can't crash persistence for an
        entire run.
        """
        data = self._read()
        ts = timestamp or _iso()

        for combo in (results or {}).values():
            if not isinstance(combo, dict) or "error" in combo:
                continue
            asset = combo.get("asset")
            timeframe = combo.get("timeframe")
            indicators = combo.get("indicators") or {}
            if not asset or not timeframe:
                continue

            asset_bucket = data["asset_stats"].setdefault(asset, {})
            timeframe_bucket = data["timeframe_stats"].setdefault(timeframe, {})

            for name, result in indicators.items():
                if name not in KNOWN_INDICATORS or not isinstance(result, dict):
                    continue
                a_stats = asset_bucket.setdefault(name, _default_indicator_rolling_stats())
                _apply_indicator_result_to_bucket(a_stats, result, ts)
                t_stats = timeframe_bucket.setdefault(name, _default_indicator_rolling_stats())
                _apply_indicator_result_to_bucket(t_stats, result, ts)

        self._write(data)
        return data
