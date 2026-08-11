"""
Part 3 approved-fix regression tests — live data path hardening.

Covers three approved, implemented changes:
  1. quotex/api_quotex/client.py — AsyncQuotexClient._on_candles_received()
     candle-response correlation fix (protected-file exception, approved
     for this change only): a response is now ONLY ever applied to the
     pending request whose (asset, period) it exactly matches. The
     previous "resolve the first pending future" fallback (which could
     misassign one asset's candles to a different asset's request, and
     contaminate FastCandleStore under the wrong key) has been removed.
  2. webapp/app.py + webapp/scanner.py — Analyzer priority over Scanner:
     a shared asyncio.Lock (app.py's _live_data_lock()) now serializes
     every live candle-fetch call the Scanner's loop makes with manual
     /api/signal and /api/ai/explain requests, and the Scanner checks
     manual_requests_in_flight both before AND immediately after
     acquiring that lock, backing off (yielding) if a manual request is
     active or starts concurrently.
  3. webapp/app.py — _fetch_current_prices() (/api/live-prices) now
     reuses the existing persistent shared fetcher (_get_shared_fetcher())
     instead of instantiating and connecting its own, independent
     QuotexDataFetcher/AsyncQuotexClient.

OFFLINE UNIT TESTS — no live Quotex session, no network access is
available in this environment. Sections A-E test client.py's candle-
response-correlation methods using their REAL, VERBATIM source (extracted
directly from the committed file and exec'd standalone, exactly the
established technique already used in
test_phase_p2p3_candle_reliability.py), driven with hand-built
asyncio.Future objects standing in for in-flight requests — this avoids
needing the loguru/websockets/pydantic/cloudscraper/playwright/bs4
third-party chain that api_quotex/__init__.py pulls in and that isn't
installed in this sandbox (all are pinned in requirements.txt for the
real deployment target). Sections F-H verify the Analyzer-priority-lock
and live-prices-shared-session changes by source inspection of the
actual committed app.py/scanner.py plus a live, real asyncio.Lock
priority-ordering simulation (Section F) — NOT a Flask test client, for
the same pre-existing sandbox limitation documented throughout this
suite (app.py cannot be imported here: fetch_data -> api_quotex ->
loguru). None of this is a substitute for live Quotex testing.

Run with: python3 Quotex/tests/test_phase_part3_live_data_hardening.py
"""
import sys
import os
import re
import time
import types
import asyncio
import typing
from datetime import datetime

_HERE = os.path.dirname(os.path.abspath(__file__))
_MARKET_ANALYZER = os.path.join(_HERE, "..", "market_analyzer")
_WEBAPP = os.path.join(_MARKET_ANALYZER, "webapp")
_QUOTEX_DIR = os.path.join(_HERE, "..", "quotex")
sys.path.insert(0, _MARKET_ANALYZER)
sys.path.insert(0, _WEBAPP)
sys.path.insert(0, _QUOTEX_DIR)

passed = 0
failed = 0


def check(name, cond):
    global passed, failed
    if cond:
        print(f"  PASS  {name}")
        passed += 1
    else:
        print(f"  FAIL  {name}")
        failed += 1


def run(coro):
    return asyncio.new_event_loop().run_until_complete(coro)


# ═══════════════════════════════════════════════════════════════════════════
print("=== 0. Extract the REAL, VERBATIM candle-correlation code from client.py ===")
# ═══════════════════════════════════════════════════════════════════════════
_client_src = open(os.path.join(_QUOTEX_DIR, "api_quotex", "client.py"), encoding="utf-8").read()

# FastCandleStore — self-contained, no third-party deps.
_fcs_match = re.search(r"\nclass FastCandleStore:.*?\n\nclass AsyncQuotexClient:", _client_src, re.S)
assert _fcs_match, "could not extract FastCandleStore source from client.py"
_fcs_src = _fcs_match.group(0).rsplit("\n\nclass AsyncQuotexClient:", 1)[0]

# _record_unmatched_candle_response() through _parse_candles_data() — one
# contiguous block in the real file (verified against the current source
# below), covering the entire correlation/diagnostics/parsing fix.
_block_match = re.search(
    r"\n    def _record_unmatched_candle_response\(self.*?\n    # endregion", _client_src, re.S
)
assert _block_match, "could not extract the candle-correlation method block from client.py"
_block_src = _block_match.group(0).rsplit("\n    # endregion", 1)[0]
# dedent method-level (4 spaces) -> module-level so these exec as free
# functions we can bind onto a lightweight fake object.
_block_src = "\n".join(
    line[4:] if line.startswith("    ") else line for line in _block_src.split("\n")
)

check("extracted block contains _record_unmatched_candle_response()",
      "def _record_unmatched_candle_response(" in _block_src)
check("extracted block contains get_recent_unmatched_candle_responses()",
      "def get_recent_unmatched_candle_responses(" in _block_src)
check("extracted block contains _on_candles_received()",
      "async def _on_candles_received(" in _block_src)
check("extracted block contains _parse_candles_data()",
      "def _parse_candles_data(" in _block_src)
check("_on_candles_received() no longer contains the removed unsafe fallback CODE "
      "(only a docstring reference to what was removed)",
      "for rid, fut in list(self._candle_requests.items()):\n                    if fut.done():\n                        continue"
      not in _client_src)
check("_on_candles_received() docstring documents the Part 3 correlation rule",
      "Correlation rule (Part 3 approved fix)" in _client_src)


class FakeCandle:
    """Stand-in for the real (pydantic) Candle model — same field set,
    plain attributes, since pydantic isn't installed in this sandbox."""
    def __init__(self, timestamp, open, high, low, close, volume, asset, timeframe):
        self.timestamp = timestamp
        self.open = open
        self.high = high
        self.low = low
        self.close = close
        self.volume = volume
        self.asset = asset
        self.timeframe = timeframe


class _FakeLogger:
    """Errors are surfaced (not swallowed) so a bug in the harness itself
    — e.g. a missing name in the exec namespace — fails loudly here rather
    than silently changing which code path the real _on_candles_received()
    fail-safe exception handler takes."""
    def error(self, *a, **k):
        print(f"  [HARNESS WARNING] logger.error() called inside extracted code: {a} {k}", file=sys.stderr)
    def info(self, *a, **k): pass
    def warning(self, *a, **k): pass


_exec_ns = {
    "asyncio": asyncio, "time": time, "datetime": datetime,
    "Dict": typing.Dict, "List": typing.List, "Optional": typing.Optional,
    "Any": typing.Any, "Tuple": typing.Tuple, "deque": __import__("collections").deque,
    "Candle": FakeCandle, "logger": _FakeLogger(),
}
exec(compile(_fcs_src, "<extracted FastCandleStore>", "exec"), _exec_ns)
FastCandleStore = _exec_ns["FastCandleStore"]
exec(compile(_block_src, "<extracted candle-correlation methods>", "exec"), _exec_ns)
_real_record_unmatched = _exec_ns["_record_unmatched_candle_response"]
_real_get_unmatched = _exec_ns["get_recent_unmatched_candle_responses"]
_real_on_candles_received = _exec_ns["_on_candles_received"]
_real_parse_candles_data = _exec_ns["_parse_candles_data"]


class ClientUnderTest:
    """
    Thin stand-in supplying exactly the attributes the REAL, extracted
    _on_candles_received()/_parse_candles_data() body touches
    (_candle_requests, _fast_store, _unmatched_candle_responses,
    enable_logging, _emit_event). The correlation logic itself is the
    untouched, extracted source — nothing about the fix is reimplemented.
    """
    def __init__(self):
        self._candle_requests: dict = {}
        self._fast_store = FastCandleStore()
        self._unmatched_candle_responses: list = []
        self.enable_logging = False
        self._emitted = []

    async def _emit_event(self, name, data):
        self._emitted.append((name, data))

    _record_unmatched_candle_response = _real_record_unmatched
    get_recent_unmatched_candle_responses = _real_get_unmatched
    _on_candles_received = _real_on_candles_received
    _parse_candles_data = _real_parse_candles_data


def make_pending(client, asset, period):
    fut = asyncio.get_event_loop().create_future()
    client._candle_requests[f"{asset}_{period}"] = fut
    return fut


# ═══════════════════════════════════════════════════════════════════════════
print("\n=== A. Orphan/mismatched candle response does not resolve any pending request ===")
# ═══════════════════════════════════════════════════════════════════════════
async def test_A():
    client = ClientUnderTest()
    fut_eur = make_pending(client, "EURUSD_otc", 60)
    fut_gbp = make_pending(client, "GBPUSD_otc", 60)

    await client._on_candles_received({
        "asset": "USDJPY_otc", "period": 60,
        "candles": [[1710000000, 1.2345, 1.2340, 1.2350, 1.2348, 100]],
    })

    check("A1: EURUSD_otc pending future NOT resolved by unrelated USDJPY_otc response",
          not fut_eur.done())
    check("A2: GBPUSD_otc pending future NOT resolved by unrelated USDJPY_otc response",
          not fut_gbp.done())
    unmatched = client.get_recent_unmatched_candle_responses(0)
    check("A3: unmatched response recorded diagnostically (exactly one entry)",
          len(unmatched) == 1 and unmatched[0]["asset"] == "USDJPY_otc" and unmatched[0]["period"] == 60)
    check("A4: unmatched diagnostic never resolves/consumes any pending future itself",
          len(client._candle_requests) == 2)

run(test_A())


# ═══════════════════════════════════════════════════════════════════════════
print("\n=== B. Cross-asset candle contamination is impossible ===")
# ═══════════════════════════════════════════════════════════════════════════
async def test_B():
    # Single pending request case (strongest form of the check: no other
    # pending future exists that a naive "resolve something" fallback
    # could even choose NOT to touch by accident).
    client = ClientUnderTest()
    fut_audcad = make_pending(client, "AUDCAD_otc", 60)

    await client._on_candles_received({
        "asset": "NZDUSD_otc", "period": 60,
        "candles": [[1710000000, 5.0, 4.9, 5.1, 5.05, 999]],
    })

    check("B1: sole pending AUDCAD_otc future left unresolved by unrelated NZDUSD_otc response",
          not fut_audcad.done())
    check("B2: AUDCAD_otc never receives NZDUSD_otc's candle values under any circumstance",
          client._fast_store.size("AUDCAD_otc", 60) == 0)
    check("B3: NZDUSD_otc's own data is still correctly stored under ITS OWN key (fix isn't over-broad)",
          client._fast_store.size("NZDUSD_otc", 60) == 1)

run(test_B())


# ═══════════════════════════════════════════════════════════════════════════
print("\n=== C. FastCandleStore/cache cannot be contaminated by an unmatched response ===")
# ═══════════════════════════════════════════════════════════════════════════
async def test_C():
    client = ClientUnderTest()
    fut_a = make_pending(client, "EURUSD_otc", 60)
    fut_b = make_pending(client, "GBPUSD_otc", 60)

    await client._on_candles_received({
        "asset": "USDJPY_otc", "period": 60,
        "candles": [[1710000000, 1.2345, 1.2340, 1.2350, 1.2348, 100],
                    [1710000060, 1.2348, 1.2343, 1.2353, 1.2351, 110]],
    })

    check("C1: cache for EURUSD_otc (a pending-but-unmatched asset) stays empty",
          client._fast_store.size("EURUSD_otc", 60) == 0)
    check("C2: cache for GBPUSD_otc (a pending-but-unmatched asset) stays empty",
          client._fast_store.size("GBPUSD_otc", 60) == 0)
    check("C3: the response's own data IS still cached, but ONLY under its own correct key",
          client._fast_store.size("USDJPY_otc", 60) == 2)

    # Also: zero-pending-requests case must not error and must not fabricate
    # any pending-future entry as a side effect.
    client2 = ClientUnderTest()
    await client2._on_candles_received({
        "asset": "USDCHF_otc", "period": 60,
        "candles": [[1710000000, 1.0, 0.99, 1.01, 1.005, 50]],
    })
    check("C4: orphan with zero pending requests is safely absorbed (no crash, own key only)",
          client2._fast_store.size("USDCHF_otc", 60) == 1 and len(client2._candle_requests) == 0)

run(test_C())


# ═══════════════════════════════════════════════════════════════════════════
print("\n=== D. Late response after timeout cannot resolve another request ===")
# ═══════════════════════════════════════════════════════════════════════════
async def test_D():
    client = ClientUnderTest()
    # Simulate request A having already timed out: _request_candles()'s own
    # `finally: self._candle_requests.pop(request_id, None)` already ran,
    # so by the time A's late response arrives, A's rid is no longer in
    # _candle_requests at all.
    stale_fut = asyncio.get_event_loop().create_future()
    stale_fut.set_result([])  # resolved empty, via the normal timeout path
    # (rid intentionally never inserted into client._candle_requests — this
    # models the post-timeout, already-popped state)

    # A different, newer request for a DIFFERENT asset is now pending.
    fut_new = make_pending(client, "GBPUSD_otc", 60)

    # A's late response finally arrives.
    await client._on_candles_received({
        "asset": "EURUSD_otc", "period": 60,
        "candles": [[1710000000, 9.99, 9.98, 10.0, 9.995, 1]],  # distinctive bogus values
    })

    check("D1: newer GBPUSD_otc request is NOT resolved by A's late response",
          not fut_new.done())
    check("D2: GBPUSD_otc's cache is NOT contaminated by A's late (EURUSD_otc) data",
          client._fast_store.size("GBPUSD_otc", 60) == 0)
    check("D3: the late response is still recorded diagnostically as unmatched",
          any(e["asset"] == "EURUSD_otc" for e in client.get_recent_unmatched_candle_responses(0)))

run(test_D())


# ═══════════════════════════════════════════════════════════════════════════
print("\n=== E. Two legitimate concurrent requests, correctly matched responses ===")
# ═══════════════════════════════════════════════════════════════════════════
async def test_E():
    client = ClientUnderTest()
    fut_eur = make_pending(client, "EURUSD_otc", 60)
    fut_gbp = make_pending(client, "GBPUSD_otc", 60)

    await client._on_candles_received({
        "asset": "EURUSD_otc", "period": 60,
        "candles": [[1710000000, 1.10, 1.09, 1.11, 1.105, 10]],
    })
    await client._on_candles_received({
        "asset": "GBPUSD_otc", "period": 60,
        "candles": [[1710000000, 1.30, 1.29, 1.31, 1.305, 20]],
    })

    check("E1: EURUSD_otc future resolved", fut_eur.done())
    check("E2: GBPUSD_otc future resolved", fut_gbp.done())
    eur_result = fut_eur.result()
    gbp_result = fut_gbp.result()
    check("E3: EURUSD_otc future's candles carry EURUSD_otc's own values only",
          len(eur_result) == 1 and eur_result[0].asset == "EURUSD_otc" and abs(eur_result[0].open - 1.10) < 1e-9)
    check("E4: GBPUSD_otc future's candles carry GBPUSD_otc's own values only",
          len(gbp_result) == 1 and gbp_result[0].asset == "GBPUSD_otc" and abs(gbp_result[0].open - 1.30) < 1e-9)
    check("E5: no cross-mixing between the two correctly-matched results",
          eur_result[0].open != gbp_result[0].open)

run(test_E())


# ═══════════════════════════════════════════════════════════════════════════
print("\n=== F. Analyzer request gets priority over Scanner (live asyncio.Lock simulation) ===")
# ═══════════════════════════════════════════════════════════════════════════
# This directly exercises the REAL priority algorithm as committed in
# scanner.py's _acquire_live_data_lock_with_priority() (extracted verbatim
# below, same technique as Section 0), driven with a real asyncio.Lock and
# a real manual_requests_in_flight counter — not a reimplementation.
_scanner_src = open(os.path.join(_WEBAPP, "scanner.py"), encoding="utf-8").read()
_prio_match = re.search(
    r"\n    async def _acquire_live_data_lock_with_priority\(self\).*?\n\n    # ── Cache",
    _scanner_src, re.S,
)
assert _prio_match, "could not extract _acquire_live_data_lock_with_priority() source from scanner.py"
_prio_src = _prio_match.group(0).rsplit("\n\n    # ── Cache", 1)[0]
_prio_src = "\n".join(line[4:] if line.startswith("    ") else line for line in _prio_src.split("\n"))

_yield_match = re.search(
    r"\n    async def _yield_to_manual_requests\(self\).*?\n\n    async def _acquire_live_data_lock_with_priority",
    _scanner_src, re.S,
)
assert _yield_match, "could not extract _yield_to_manual_requests() source from scanner.py"
_yield_src = _yield_match.group(0).rsplit("\n\n    async def _acquire_live_data_lock_with_priority", 1)[0]
_yield_src = "\n".join(line[4:] if line.startswith("    ") else line for line in _yield_src.split("\n"))

check("scanner.py defines _acquire_live_data_lock_with_priority()",
      "async def _acquire_live_data_lock_with_priority(self)" in _scanner_src)
check("priority method re-checks manual_requests_in_flight AFTER acquiring the lock (closes the race)",
      "if self.manual_requests_in_flight > 0:" in _prio_src and "lock.release()" in _prio_src)
check("scan loop acquires the priority lock before EVERY _run_pipeline() call (not just once per asset)",
      "_live_lock = await self._acquire_live_data_lock_with_priority()" in _scanner_src)
check("scan loop releases the lock in a finally (never left held on exception/timeout)",
      "if _live_lock is not None:\n                                    _live_lock.release()" in _scanner_src)

_exec_ns2 = {"asyncio": asyncio, "Optional": typing.Optional,
             "STOPPED": "STOPPED", "RUNNING": "RUNNING", "PAUSED": "PAUSED", "YIELDING": "YIELDING"}
exec(compile("from __future__ import annotations\n" + _yield_src, "<extracted yield>", "exec"), _exec_ns2)
exec(compile("from __future__ import annotations\n" + _prio_src, "<extracted priority>", "exec"), _exec_ns2)
_real_yield_to_manual = _exec_ns2["_yield_to_manual_requests"]
_real_acquire_priority = _exec_ns2["_acquire_live_data_lock_with_priority"]


class _Cfg:
    manual_priority_max_wait_seconds = 5.0


class ScannerPriorityUnderTest:
    def __init__(self, lock):
        self.manual_requests_in_flight = 0
        self.state = "RUNNING"
        self.cfg = _Cfg()
        self._live_data_lock_getter = lambda: lock

    def _set_state(self, state, reason=""):
        self.state = state

    _yield_to_manual_requests = _real_yield_to_manual
    _acquire_live_data_lock_with_priority = _real_acquire_priority


async def test_F():
    lock = asyncio.Lock()
    scanner = ScannerPriorityUnderTest(lock)
    events = []

    async def scanner_worker():
        held = await scanner._acquire_live_data_lock_with_priority()
        events.append("scanner_acquired")
        await asyncio.sleep(0.05)  # simulate an in-flight fetch
        events.append("scanner_releasing")
        held.release()

    async def manual_worker():
        await asyncio.sleep(0.01)  # start slightly after the scanner
        scanner.manual_requests_in_flight += 1
        events.append("manual_flag_set")
        async with lock:
            events.append("manual_acquired")
            await asyncio.sleep(0.01)
        scanner.manual_requests_in_flight -= 1
        events.append("manual_released")

    await asyncio.gather(scanner_worker(), manual_worker())

    check("F1: scanner acquired the lock first (it started first, manual hadn't set its flag yet)",
          events[0] == "scanner_acquired")
    check("F2: scanner released before manual acquired (no simultaneous hold)",
          events.index("scanner_releasing") < events.index("manual_acquired"))
    check("F3: manual's flag was set BEFORE it acquired the lock (priority signal precedes acquisition)",
          events.index("manual_flag_set") < events.index("manual_acquired"))

    # Second scenario: manual flag is ALREADY set before the scanner even
    # tries to acquire — scanner must wait/yield, not barge in.
    lock2 = asyncio.Lock()
    scanner2 = ScannerPriorityUnderTest(lock2)
    scanner2.manual_requests_in_flight = 1  # manual already active
    events2 = []

    async def scanner_worker2():
        events2.append("scanner_start_waiting")
        held = await scanner2._acquire_live_data_lock_with_priority()
        events2.append("scanner_acquired")
        held.release()

    async def manual_worker2():
        async with lock2:
            events2.append("manual_holds_lock")
            await asyncio.sleep(0.05)
        scanner2.manual_requests_in_flight = 0
        events2.append("manual_flag_cleared")

    await asyncio.gather(scanner_worker2(), manual_worker2())

    check("F4: scanner does not acquire the lock while manual_requests_in_flight is set",
          events2.index("scanner_acquired") > events2.index("manual_flag_cleared"))
    check("F5: scanner's acquisition happens only after the manual flag clears (true priority, not FIFO luck)",
          events2.index("manual_holds_lock") < events2.index("scanner_acquired"))

run(test_F())


# ═══════════════════════════════════════════════════════════════════════════
print("\n=== G. Scanner pauses while Analyzer is running and resumes afterward ===")
# ═══════════════════════════════════════════════════════════════════════════
async def test_G():
    # G1-G2: state transitions of the underlying _yield_to_manual_requests()
    # mechanism itself (same one both the pre-existing per-asset yield and
    # the new per-fetch priority lock rely on).
    scanner = ScannerPriorityUnderTest(asyncio.Lock())
    check("G1: scanner state is RUNNING with no manual request active", scanner.state == "RUNNING")

    scanner.manual_requests_in_flight = 1
    yield_task = asyncio.create_task(scanner._yield_to_manual_requests())
    await asyncio.sleep(0.02)
    check("G2: scanner state becomes YIELDING while a manual request is in flight",
          scanner.state == "YIELDING")

    scanner.manual_requests_in_flight = 0
    await asyncio.wait_for(yield_task, timeout=2.0)
    check("G3: scanner state returns to RUNNING once the manual request finishes (resume)",
          scanner.state == "RUNNING")

    # G4: source-level check that api_signal()/api_ai_explain() actually
    # call manual_request_started()/finished() around every manual pipeline
    # invocation, and that a real Lock object exists to be shared. This is
    # the wiring between the real Flask routes and the extracted logic
    # exercised for real in G1-G3/F above (app.py itself can't be imported
    # in this sandbox — see module docstring).
    _app_src = open(os.path.join(_WEBAPP, "app.py"), encoding="utf-8").read()
    check("G4: app.py defines the shared _live_data_lock() getter",
          "def _live_data_lock() -> asyncio.Lock:" in _app_src)
    check("G5: app.py defines _run_pipeline_with_priority() wrapping _run_pipeline() with that lock",
          "async def _run_pipeline_with_priority(asset: str, timeframe: str)" in _app_src
          and "async with _live_data_lock():" in _app_src
          and "return await _run_pipeline(asset, timeframe)" in _app_src)
    check("G6: /api/signal marks manual_request_started() before invoking the priority wrapper",
          "_scanner.manual_request_started()" in _app_src
          and "_run_bg(_run_pipeline_with_priority(asset, timeframe))" in _app_src)
    check("G7: /api/ai/explain uses the SAME priority wrapper as /api/signal (consistent priority everywhere)",
          _app_src.count("_run_bg(_run_pipeline_with_priority(asset, timeframe))") >= 2)
    check("G8: _run_pipeline() itself is unmodified by this fix (still a single, undecorated definition)",
          _app_src.count("async def _run_pipeline(asset: str, timeframe: str) -> Dict[str, Any]:") == 1)
    check("G9: ScannerEngine is constructed with the shared live_data_lock getter (wired up, not orphaned)",
          "live_data_lock=_live_data_lock," in _app_src)

run(test_G())


# ═══════════════════════════════════════════════════════════════════════════
print("\n=== H. /api/live-prices reuses the shared fetcher/session (no second Quotex client) ===")
# ═══════════════════════════════════════════════════════════════════════════
# app.py cannot be imported in this sandbox (fetch_data -> api_quotex ->
# loguru — same pre-existing limitation documented throughout this suite),
# so this is verified by source inspection of the actual committed file,
# same convention already used for other Flask-route checks in this
# project (see test_phase_10_2.py/test_phase_10_3_part2.py's own
# "Integration wiring — routes (source inspection)" sections).
_app_src = open(os.path.join(_WEBAPP, "app.py"), encoding="utf-8").read()

_fetch_prices_match = re.search(
    r"async def _fetch_current_prices\(assets: list\) -> dict:.*?\n\n\n@app\.route\(\"/api/live-prices\"\)",
    _app_src, re.S,
)
assert _fetch_prices_match, "could not locate _fetch_current_prices() in app.py"
_fetch_prices_src = _fetch_prices_match.group(0)

check("H1: _fetch_current_prices() calls the shared _get_shared_fetcher(), not a fresh QuotexDataFetcher()",
      "fetcher = await _get_shared_fetcher()" in _fetch_prices_src)
check("H2: _fetch_current_prices() no longer instantiates its own QuotexDataFetcher()",
      "QuotexDataFetcher()" not in _fetch_prices_src)
check("H3: _fetch_current_prices() no longer calls .connect() itself (shared fetcher owns that lifecycle)",
      "await fetcher.connect()" not in _fetch_prices_src)
check("H4: _fetch_current_prices() no longer calls .disconnect() itself "
      "(would kill the shared session for everyone else)",
      "await fetcher.disconnect()" not in _fetch_prices_src)
check("H5: exactly ONE QuotexDataFetcher(...) instantiation exists in the entire app.py "
      "(inside _get_shared_fetcher() only — the sole session-owning call site)",
      _app_src.count("QuotexDataFetcher(") == 1
      and "_shared_fetcher = QuotexDataFetcher(asset=cfg.DEFAULT_ASSET, is_demo=cfg.IS_DEMO)" in _app_src)
check("H6: the per-asset concurrent fetch pattern is preserved (feature not removed by the fix)",
      "await asyncio.gather(*(_fetch_one(a) for a in assets))" in _fetch_prices_src)
check("H7: /api/live-prices route itself is unchanged (still caches, still calls _fetch_current_prices via _run_bg)",
      'prices = _run_bg(_fetch_current_prices(_TOP_OTC))' in _app_src)


# ═══════════════════════════════════════════════════════════════════════════
print(f"\n=== RESULT: {passed} passed, {failed} failed (of {passed + failed}) ===")
# ═══════════════════════════════════════════════════════════════════════════
if failed:
    sys.exit(1)
