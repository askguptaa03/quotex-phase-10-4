"""
Phase 8.4.3 — ValidationEngine
================================
A thin, additive wrapper around `indicator_validation.py`'s existing
`validate_indicator()` function (Phase 8.4.2 — imported here, UNCHANGED,
never duplicated or modified). Mirrors `backtest_engine.py`'s proven
async lifecycle pattern as closely as possible: STOPPED/RUNNING/PAUSED
states plus one addition explicitly requested for this engine —
STOPPING, a transitional state held between a stop() request and the
loop actually halting. Pause/resume via `asyncio.Event`, submitted onto
the CALLER-SUPPLIED shared `_BG_LOOP` — this module never creates its
own event loop or a second Quotex connection.

Reuses ONLY:
  - indicator_validation.validate_indicator() (Phase 8.4.2, unmodified)
  - indicator_validation.validate_indicator_universal() (Phase 10.1,
    additive — delegates straight to validate_indicator() for the
    original 3 OTC indicators, and to a new read-only
    backtest._factor_votes()-based path for the other 10 confluence
    factors; see indicator_validation.py's own docstring)
  - indicator_validation.INDICATOR_NAMES / UNIVERSAL_INDICATOR_NAMES
    (unmodified / additive)
  - a caller-supplied `fetch_candles` callable — app.py wires this to the
    SAME `_backtest_fetch_candles()` closure already built for
    `BacktestEngine`, so this introduces no new fetch/session logic and
    no second concurrent Quotex connection path.

Does NOT import, call, or modify: analyzer.py, backtest.py, scanner.py,
settings_store.py, indicator_registry.py, indicators.py,
backtest_engine.py, the Quotex API, or WebSocket code. (Phase 10.1's
extended coverage is implemented by indicator_validation.py reading —
never modifying — backtest._factor_votes(); this file still imports
nothing from backtest.py itself.) Does NOT connect any indicator to
Confluence, does NOT compute or apply dynamic weights, does NOT touch
voting or the filter score in any way. Analysis only — like every other
engine in this project, it never places an order and never mutates
anything outside its own in-memory `results`/`summary` state.
"""

from __future__ import annotations

import asyncio
import time
from typing import Any, Awaitable, Callable, Dict, List, Optional

try:
    from indicator_validation import (
        validate_indicator, INDICATOR_NAMES,
        validate_indicator_universal, UNIVERSAL_INDICATOR_NAMES,
    )
except ImportError:
    from market_analyzer.indicator_validation import (
        validate_indicator, INDICATOR_NAMES,
        validate_indicator_universal, UNIVERSAL_INDICATOR_NAMES,
    )

# Phase 10.1 — Universal Validation. `validate_indicator`/`INDICATOR_NAMES`
# (the original 3 OTC-specific indicators) stay imported and unused-but-kept
# for backward compatibility with anything importing them from this module;
# every actual call site below now uses `validate_indicator_universal()`
# (which itself delegates straight to `validate_indicator()`, unmodified,
# for those same 3 names — see indicator_validation.py) and
# `UNIVERSAL_INDICATOR_NAMES` (13 factors) instead of the old 3-only set.

STOPPED = "STOPPED"
RUNNING = "RUNNING"
PAUSED = "PAUSED"
STOPPING = "STOPPING"  # transitional only — set the instant stop() is called,
                       # cleared to STOPPED once the loop actually exits at its
                       # next checkpoint (mirrors backtest_engine.py's own
                       # "stop takes effect after the current work unit, never
                       # mid-fetch" guarantee, just made visible as a state
                       # rather than only an internal flag).

# Mirrors backtest_engine.py's CANDLE_OPTIONS/DEFAULT_CANDLE_COUNT exactly,
# for consistency between the two engines' APIs — an independent constant,
# not imported from backtest_engine.py (this module doesn't import that
# file at all).
VALIDATION_CANDLE_OPTIONS = (500, 1000, 1500, 2000, 3000, 5000)
DEFAULT_VALIDATION_CANDLE_COUNT = 2000
DEFAULT_LOOKAHEAD = 4


def _now() -> float:
    return time.time()


def _iso(ts: Optional[float]) -> Optional[str]:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(ts)) if ts else None


class ValidationEngine:
    """
    fetch_candles: async callable(asset, timeframe, count) -> DataFrame,
    supplied by app.py — reuses the SAME fetcher/session machinery
    BacktestEngine and _run_pipeline already use. This class never talks
    to Quotex itself, so it cannot introduce a second concurrent
    connection.
    """

    def __init__(self, fetch_candles: Callable[[str, str, int], Awaitable[Any]]):
        self._fetch_candles = fetch_candles

        self.state = STOPPED
        self._stop_requested = False
        self._cancelled = False  # True if stop() interrupted a run; False if it finished naturally
        self._pause_event = asyncio.Event()
        self._pause_event.set()  # not paused by default

        # Progress tracking — same field-naming spirit as backtest_engine.py,
        # extended with current_timeframe since this engine sweeps
        # (asset, timeframe) pairs rather than just assets.
        self.current_asset: Optional[str] = None
        self.current_timeframe: Optional[str] = None
        self.current_indicator: Optional[str] = None
        self.combinations_processed = 0
        self.total_combinations = 0
        self.started_at: Optional[float] = None
        self.finished_at: Optional[float] = None
        self.last_error: Optional[str] = None

        # keyed "asset|timeframe" -> {asset, timeframe, candles_used,
        # indicators: {name: validate_indicator() output}, timestamp}
        self.results: Dict[str, Any] = {}
        self.summary: Optional[Dict[str, Any]] = None

        # Bug found and fixed during Phase 8.4.3 testing (see class docstring
        # note below `stop()`/`pause()`/`resume()` for the full explanation):
        # stores the loop passed to start() so pause()/resume()/stop() can
        # signal `_pause_event` via `loop.call_soon_threadsafe()` instead of
        # mutating it directly from the calling (Flask) thread.
        self._loop: Optional[asyncio.AbstractEventLoop] = None

    # ── Lifecycle: start / stop / pause / resume ────────────────────────────
    def start(self, loop: asyncio.AbstractEventLoop, assets: List[str], timeframes: List[str],
              indicators: Optional[List[str]] = None,
              candle_count: int = DEFAULT_VALIDATION_CANDLE_COUNT,
              lookahead: int = DEFAULT_LOOKAHEAD) -> Dict[str, Any]:
        """
        Submits the validation coroutine onto the CALLER-SUPPLIED loop
        (the app's existing shared _BG_LOOP) — this method does not
        create or manage any event loop itself.

        Safety: one validation run at a time. A start() call while
        already RUNNING/PAUSED/STOPPING is ignored (returns ok=False)
        rather than queuing or interrupting the in-progress run — same
        guarantee backtest_engine.py's start() makes.
        """
        if self.state != STOPPED:
            return {"ok": False, "message": f"Validation already {self.state} — ignoring duplicate start request"}

        # Phase 10.1: default (when the caller omits `indicators` entirely)
        # is now the FULL 13-factor universal set — this is the explicit
        # point of "Universal Validation." Any caller that still wants the
        # pre-Phase-10.1 3-indicator-only behavior can simply pass
        # `indicators=list(INDICATOR_NAMES)` explicitly; nothing about how
        # those 3 are computed changed (see indicator_validation.py).
        indicators = list(indicators) if indicators else list(UNIVERSAL_INDICATOR_NAMES)
        unknown = [i for i in indicators if i not in UNIVERSAL_INDICATOR_NAMES]
        if unknown:
            return {"ok": False, "message": f"Unknown indicator(s): {unknown}. Must be from {list(UNIVERSAL_INDICATOR_NAMES)}"}
        if candle_count not in VALIDATION_CANDLE_OPTIONS:
            return {"ok": False, "message": f"candle_count must be one of {VALIDATION_CANDLE_OPTIONS}, got {candle_count}"}
        if not assets:
            return {"ok": False, "message": "No assets specified"}
        if not timeframes:
            return {"ok": False, "message": "No timeframes specified"}

        self._stop_requested = False
        self._cancelled = False
        self._pause_event.set()
        self.state = RUNNING
        self._loop = loop
        self.results = {}
        self.summary = None
        self.combinations_processed = 0
        self.total_combinations = len(assets) * len(timeframes)
        self.started_at = _now()
        self.finished_at = None
        self.last_error = None
        self.current_asset = None
        self.current_timeframe = None
        self.current_indicator = None

        asyncio.run_coroutine_threadsafe(
            self._run_loop(list(assets), list(timeframes), indicators, candle_count, lookahead), loop
        )
        return {"ok": True, "message": "Validation started", "total_combinations": self.total_combinations}

    def stop(self) -> Dict[str, Any]:
        """
        Requests a stop. Per the same guarantee backtest_engine.py makes:
        the in-progress (asset, timeframe) combination's fetch/replay is
        allowed to finish (never interrupting an active Quotex request),
        then the loop halts at the next checkpoint. State becomes
        STOPPING immediately (visible to status() pollers) and settles
        to STOPPED once `_run_loop()` actually exits.

        Bug found and fixed during Phase 8.4.3 testing: `_pause_event` is
        an `asyncio.Event`, and this method is called synchronously from
        the Flask request thread — a DIFFERENT OS thread than the one
        running `_BG_LOOP`. Calling `Event.set()` directly from a
        non-loop thread is not safe: `Future.set_result()` (which
        `Event.set()` triggers for any waiters) schedules its callback
        via `loop.call_soon()`, which is NOT thread-safe and does not
        interrupt the loop's blocking `epoll_wait()` — so if nothing
        else ever gives the loop a real I/O or timer event afterward,
        the paused coroutine can stay asleep forever. This was masked in
        the original single-threaded test because the synthetic fetch
        used `asyncio.sleep()`, whose internal `call_later()` timer kept
        giving the loop periodic real wakeups. Once tested through the
        actual Flask app with a synchronously-failing fetch (no live
        Quotex network in this sandbox — see TEST_REPORT.md), there was
        no such incidental wakeup and the bug reproduced 100% of the
        time. Fixed by routing the event mutation through
        `loop.call_soon_threadsafe()`, which uses the loop's self-pipe
        to guarantee a prompt, correct wakeup regardless of what else is
        happening on the loop.
        """
        if self.state == STOPPED:
            return {"ok": False, "message": "Validation is not running"}
        if self.state == STOPPING:
            return {"ok": False, "message": "Stop already in progress"}
        self._stop_requested = True
        self._cancelled = True
        self.state = STOPPING
        if self._loop is not None:
            self._loop.call_soon_threadsafe(self._pause_event.set)
        else:  # defensive fallback only; start() always sets self._loop first
            self._pause_event.set()
        return {"ok": True, "message": "Stop requested — will halt after the current work unit completes"}

    def pause(self) -> Dict[str, Any]:
        """Pause only takes effect between work units (asset/timeframe
        boundaries), never mid-fetch — same guarantee as stop(). See
        stop()'s docstring for why the event mutation is routed through
        call_soon_threadsafe() rather than called directly."""
        if self.state != RUNNING:
            return {"ok": False, "message": f"Cannot pause from state={self.state}"}
        self.state = PAUSED
        if self._loop is not None:
            self._loop.call_soon_threadsafe(self._pause_event.clear)
        else:
            self._pause_event.clear()
        return {"ok": True, "message": "Validation paused"}

    def resume(self) -> Dict[str, Any]:
        """See stop()'s docstring for why the event mutation is routed
        through call_soon_threadsafe() rather than called directly."""
        if self.state != PAUSED:
            return {"ok": False, "message": f"Validation is not paused (state={self.state})"}
        self.state = RUNNING
        if self._loop is not None:
            self._loop.call_soon_threadsafe(self._pause_event.set)
        else:
            self._pause_event.set()
        return {"ok": True, "message": "Validation resumed"}

    # ── The validation loop ──────────────────────────────────────────────────
    async def _run_loop(self, assets: List[str], timeframes: List[str], indicators: List[str],
                         candle_count: int, lookahead: int) -> None:
        try:
            for asset in assets:
                if self._stop_requested:
                    break
                await self._pause_event.wait()
                if self._stop_requested:
                    break

                for timeframe in timeframes:
                    # Checkpoint: honor stop/pause BEFORE starting the next
                    # (asset, timeframe) combination's Quotex fetch — never
                    # mid-fetch, identical guarantee to backtest_engine.py.
                    if self._stop_requested:
                        break
                    await self._pause_event.wait()
                    if self._stop_requested:
                        break

                    self.current_asset = asset
                    self.current_timeframe = timeframe
                    self.current_indicator = "fetching_candles"
                    key = f"{asset}|{timeframe}"

                    try:
                        df = await self._fetch_candles(asset, timeframe, candle_count)
                    except Exception as exc:  # noqa: BLE001 — logged, loop continues to next combination
                        self.last_error = f"{asset}/{timeframe}: fetch failed: {exc}"
                        self.results[key] = {
                            "asset": asset, "timeframe": timeframe, "status": "FAILED",
                            "error": self.last_error, "timestamp": _iso(_now()),
                        }
                        self.combinations_processed += 1
                        continue

                    if df is None or len(df) == 0:
                        # P0 fix — a real, honest NO_DATA outcome, distinct
                        # from a fetch exception (FAILED) or an indicator
                        # compute exception — never collapsed into one
                        # generic "error" bucket.
                        self.last_error = f"{asset}/{timeframe}: no candle data returned"
                        self.results[key] = {
                            "asset": asset, "timeframe": timeframe, "status": "NO_DATA",
                            "error": self.last_error, "timestamp": _iso(_now()),
                        }
                        self.combinations_processed += 1
                        continue

                    # ── Reuse validate_indicator_universal() exactly — no duplicated
                    # math. Phase 10.1: covers any of the 13 confluence factors;
                    # for the original 3 this is byte-identical to calling
                    # validate_indicator() directly (see indicator_validation.py).
                    #
                    # P0 fix — each indicator call is now individually isolated.
                    # Previously an exception from validate_indicator_universal()
                    # for ANY single indicator propagated out of _run_loop
                    # entirely, silently terminating the WHOLE validation run
                    # (combinations_processed never incremented for that
                    # combination, _build_summary() never ran, and status()
                    # could report completed=True on a truncated run since
                    # `_cancelled` was never set by this path). A failed
                    # indicator is now recorded per-indicator and the
                    # combination — and the run — continue.
                    combo_indicators: Dict[str, Any] = {}
                    indicator_failures: List[str] = []
                    for name in indicators:
                        if self._stop_requested:
                            break
                        self.current_indicator = name
                        await asyncio.sleep(0)  # yield to the event loop
                        try:
                            combo_indicators[name] = validate_indicator_universal(
                                df, name, asset, timeframe, lookahead=lookahead
                            )
                        except Exception as exc:  # noqa: BLE001 — isolated per indicator
                            combo_indicators[name] = {
                                "status": "FAILED", "error": f"{name}: {exc}",
                            }
                            indicator_failures.append(name)
                            self.last_error = f"{asset}/{timeframe}/{name}: indicator validation failed: {exc}"

                    # Deliberately NOT storing `df` itself — only derived,
                    # already-small result dicts, same memory-usage
                    # discipline backtest_engine.py already follows.
                    self.results[key] = {
                        "asset": asset,
                        "timeframe": timeframe,
                        "status": "SUCCESS",  # fetch + combination processing completed;
                                               # per-indicator outcomes are in `indicators`/`indicator_failures`
                        "candles_used": len(df),
                        "indicators": combo_indicators,
                        "indicator_failures": indicator_failures,
                        "timestamp": _iso(_now()),
                    }
                    del df
                    self.combinations_processed += 1

                    if self._stop_requested:
                        break

            self.current_asset = None
            self.current_timeframe = None
            self.current_indicator = None
            # P0 fix (defense-in-depth, mirrors the same fix in
            # backtest_engine.py) — _build_summary() aggregates across all
            # combinations after the loop finishes and is itself a compute
            # step; isolate it so an aggregation bug can't silently leave
            # self.summary as None on an otherwise genuinely finished run.
            try:
                self._build_summary()
            except Exception as exc:  # noqa: BLE001
                self.last_error = f"summary aggregation failed: {exc}"
                self.summary = {
                    "combinations_validated": 0,
                    "combinations_succeeded": sum(1 for r in self.results.values() if r.get("status") == "SUCCESS"),
                    "combinations_no_data": sum(1 for r in self.results.values() if r.get("status") == "NO_DATA"),
                    "combinations_failed": sum(1 for r in self.results.values() if r.get("status") == "FAILED"),
                    "combinations_skipped": max(0, self.total_combinations - len(self.results)),
                    "per_indicator": {},
                    "aggregation_error": self.last_error,
                }
        finally:
            self.finished_at = _now()
            self.state = STOPPED

    def _build_summary(self) -> None:
        """
        Aggregate per-indicator totals across all successfully-validated
        (asset, timeframe) combinations — pure arithmetic over
        validate_indicator()'s already-computed outputs. No new scoring
        system, no dynamic-weight computation, no write anywhere outside
        this engine's own in-memory `summary`.

        P0 fix: also reports the real per-status breakdown (SUCCESS /
        NO_DATA / FAILED / SKIPPED at the combination level, plus a
        per-indicator failure count) instead of a single pass/fail split —
        and rows for an indicator that itself failed (isolated per-
        indicator, see _run_loop) are excluded from that indicator's
        aggregate stats rather than crashing or being silently counted as
        zero-value success.
        """
        valid = {k: r for k, r in self.results.items() if r.get("status") == "SUCCESS"}
        no_data = {k: r for k, r in self.results.items() if r.get("status") == "NO_DATA"}
        failed = {k: r for k, r in self.results.items() if r.get("status") == "FAILED"}
        skipped_count = max(0, self.total_combinations - len(self.results))

        if not valid:
            self.summary = {
                "combinations_validated": 0,
                "combinations_succeeded": 0,
                "combinations_no_data": len(no_data),
                "combinations_failed": len(failed),
                "combinations_skipped": skipped_count,
                "per_indicator": {},
            }
            return

        per_indicator: Dict[str, Any] = {}
        for name in UNIVERSAL_INDICATOR_NAMES:
            all_rows = [r["indicators"][name] for r in valid.values() if name in r.get("indicators", {})]
            # Exclude per-indicator failures (isolated {"status": "FAILED", ...}
            # sentinels — see _run_loop) from the numeric aggregate; they're
            # counted separately below instead of silently treated as zeros.
            rows = [row for row in all_rows if row.get("status") != "FAILED"]
            indicator_failure_count = len(all_rows) - len(rows)
            if not rows:
                if indicator_failure_count:
                    per_indicator[name] = {
                        "combinations_tested": 0,
                        "combinations_failed": indicator_failure_count,
                    }
                continue
            total_samples = sum(row["samples"] for row in rows)
            total_wins = sum(row["wins"] for row in rows)
            total_buy = sum(row["buy_signals"] for row in rows)
            total_sell = sum(row["sell_signals"] for row in rows)
            sufficient_rows = [row for row in rows if row["sufficient_sample"]]
            avg_win_rate_where_sufficient = (
                round(sum(row["win_rate"] for row in sufficient_rows) / len(sufficient_rows), 2)
                if sufficient_rows else None
            )
            avg_strength = (
                round(sum((row["average_strength"] or 0.0) for row in rows) / len(rows), 2) if rows else None
            )
            avg_reliability_score = (
                round(sum((row["average_reliability"] or 0.0) for row in rows) / len(rows), 2) if rows else None
            )

            per_indicator[name] = {
                "combinations_tested": len(rows),
                "combinations_failed": indicator_failure_count,
                "combinations_with_sufficient_sample": len(sufficient_rows),
                "total_samples": total_samples,
                "total_wins": total_wins,
                "total_losses": total_samples - total_wins,
                "total_buy_signals": total_buy,
                "total_sell_signals": total_sell,
                "average_win_rate_where_sufficient": avg_win_rate_where_sufficient,
                "average_strength": avg_strength,
                "average_reliability": avg_reliability_score,
            }

        self.summary = {
            "combinations_validated": len(valid),
            "combinations_succeeded": len(valid),
            "combinations_no_data": len(no_data),
            "combinations_failed": len(failed),
            "combinations_skipped": skipped_count,
            "per_indicator": per_indicator,
        }

    # ── status() / get_results() — same naming as backtest_engine.py ────────
    def status(self) -> Dict[str, Any]:
        elapsed = ((self.finished_at or _now()) - self.started_at) if self.started_at else 0.0
        percent_complete = (
            round(min(100.0, self.combinations_processed / self.total_combinations * 100), 1)
            if self.total_combinations else 0.0
        )
        estimated_remaining = None
        if self.state in (RUNNING, STOPPING) and percent_complete > 0:
            estimated_remaining = round(elapsed / (percent_complete / 100.0) - elapsed, 1)

        # P0 fix — completed now also requires combinations_processed to
        # have actually reached total_combinations, not just finished_at
        # being set. Previously an uncaught per-indicator exception could
        # reach the same STOPPED/finished_at state as a genuine finish
        # while combinations_processed was still partial and `_cancelled`
        # was never set — reporting completed=True on a silently truncated
        # run. That specific exception path is now closed (see _run_loop),
        # but this flag is defined correctly regardless of the reason a
        # run might stop short.
        completed = (
            self.state == STOPPED and self.finished_at is not None
            and not self._cancelled and self.combinations_processed >= self.total_combinations
        )
        cancelled = self.state == STOPPED and self.finished_at is not None and self._cancelled

        return {
            "state": self.state,
            "running": self.state in (RUNNING, STOPPING),
            "paused": self.state == PAUSED,
            "stopping": self.state == STOPPING,
            "completed": completed,
            "cancelled": cancelled,
            "current_asset": self.current_asset,
            "current_timeframe": self.current_timeframe,
            "current_indicator": self.current_indicator,
            "combinations_processed": self.combinations_processed,
            "total_combinations": self.total_combinations,
            "percent_complete": percent_complete,
            "elapsed_time": round(elapsed, 1),
            "estimated_remaining": estimated_remaining,
            "last_error": self.last_error,
            "started_at": _iso(self.started_at),
            "finished_at": _iso(self.finished_at),
            "summary": self.summary,
        }

    def get_results(self) -> Dict[str, Any]:
        """Full per-combination results + summary — separate from
        status() so a lightweight progress poller doesn't have to pull
        the full payload, same split backtest_engine.py already uses."""
        return {"results": self.results, "summary": self.summary}
