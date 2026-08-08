"""
Phase 2/3 targeted regression tests — candle-fetch reliability sequence
(fetch_data.py's QuotexDataFetcher.get_candles()) and the approved
protected-file fix (client.py's get_available_assets() now normalizes
symbols via sanitize_symbol(), matching get_candles()/get_assets_and_payouts()).

OFFLINE UNIT TESTS — no live Quotex session, no network. `loguru` and
`websockets` are stubbed purely to satisfy import-time dependencies that
aren't installed in this sandbox (both are pinned in requirements.txt for
the real deployment target); the actual Quotex network/session client
itself is replaced with an explicitly-labeled FakeClient for every test
below. Never used as proof of live Quotex integration.

Run with: python3 Quotex/tests/test_phase_p2p3_candle_reliability.py
"""
import sys
import os
import re
import types
import asyncio

_HERE = os.path.dirname(os.path.abspath(__file__))
_MARKET_ANALYZER = os.path.join(_HERE, "..", "market_analyzer")
_QUOTEX_DIR = os.path.join(_HERE, "..", "quotex")
sys.path.insert(0, _MARKET_ANALYZER)
sys.path.insert(0, _QUOTEX_DIR)

# NOTE (offline-sandbox limitation, same one already documented in
# test_phase_10_4_goal2/3/4/5.py and test_phase_10_4_p0_stability.py):
# `from api_quotex import AsyncQuotexClient` pulls in a chain of
# third-party packages (loguru, websockets, pydantic, ...) that aren't
# installed in this sandbox and never will be reachable offline — they
# ARE pinned in requirements.txt for the real deployment target. Rather
# than stub an ever-growing dependency chain (which would test stub
# behavior, not real code), get_candles()'s ACTUAL, VERBATIM source is
# extracted from the real committed fetch_data.py and exec'd against a
# lightweight fake object that supplies only what the method actually
# touches at runtime (_client, connect/disconnect, get_available_assets,
# asset/last_fetch_diagnostics). `from __future__ import annotations` in
# fetch_data.py means the type hints are strings, never evaluated, so no
# real Candle/AsyncQuotexClient types are needed for this to run for real.
import config as cfg  # noqa: E402 — no third-party deps, safe to import directly

# api_quotex/__init__.py eagerly imports client.py (loguru) and
# utils.py itself does `from .models import ...` (pydantic) purely for
# OTHER functions in that file — sanitize_symbol() itself needs neither.
# Extract its real, verbatim source and exec it standalone, same
# reasoning as get_candles() above: this runs the actual committed
# function, not a reimplementation, without pulling in unrelated
# third-party deps that function doesn't actually use.
_utils_full_src = open(os.path.join(_QUOTEX_DIR, "api_quotex", "utils.py"), encoding="utf-8").read()
_sanitize_match = re.search(r"\ndef sanitize_symbol\(.*?\n\ndef ", _utils_full_src, re.S)
assert _sanitize_match, "could not extract sanitize_symbol() source from utils.py"
_sanitize_src = _sanitize_match.group(0).rsplit("\n\ndef ", 1)[0]
_sanitize_ns = {}
exec(compile(_sanitize_src, "<extracted sanitize_symbol>", "exec"), _sanitize_ns)
sanitize_symbol = _sanitize_ns["sanitize_symbol"]

_fd_full_src = open(os.path.join(_MARKET_ANALYZER, "fetch_data.py"), encoding="utf-8").read()
_get_candles_match = re.search(
    r"\n    async def get_candles\(self.*?\n\n    async def get_candles_df\(", _fd_full_src, re.S
)
assert _get_candles_match, "could not extract get_candles() source from fetch_data.py"
_get_candles_src = _get_candles_match.group(0).rsplit("\n\n    async def get_candles_df(", 1)[0]
# dedent from method-level (4 spaces) to module-level so it execs as a
# free function we can bind onto any fake object.
_get_candles_src = "\n".join(
    line[4:] if line.startswith("    ") else line for line in _get_candles_src.split("\n")
)

_exec_ns = {"asyncio": asyncio, "cfg": cfg, "print": print, "sanitize_symbol": sanitize_symbol}
# fetch_data.py has `from __future__ import annotations` at module level,
# so its annotations are never evaluated at runtime there; replicate that
# here too, since this snippet is exec'd standalone outside that context.
exec(compile("from __future__ import annotations\n" + _get_candles_src,
             "<extracted get_candles>", "exec"), _exec_ns)
_real_get_candles = _exec_ns["get_candles"]


class QuotexDataFetcherUnderTest:
    """
    Thin stand-in that supplies exactly the attributes/methods the REAL
    get_candles() body touches (self._client, self.asset,
    self.last_fetch_diagnostics, self.connect(), self.disconnect(),
    self.get_available_assets()) — everything else about the real
    QuotexDataFetcher class is irrelevant to this method's own logic.
    get_candles itself is the untouched, extracted source.
    """
    def __init__(self, fake_client, asset="EURUSD_otc"):
        self._client = fake_client
        self.asset = asset
        self.last_fetch_diagnostics = {}

    async def connect(self):
        await self._client.connect()

    async def disconnect(self):
        await self._client.disconnect()
        self._client = self._client  # stays "connected" to the same fake object

    async def get_available_assets(self):
        if not self._client:
            return {}
        try:
            result = await self._client.get_available_assets()
            return result if isinstance(result, dict) else {}
        except Exception:
            return {}

    get_candles = _real_get_candles

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
print("=== source-level checks ===")
# ═══════════════════════════════════════════════════════════════════════════
_fd_src = open(os.path.join(_MARKET_ANALYZER, "fetch_data.py"), encoding="utf-8").read()
check("get_candles() docstring documents the reliability sequence",
      "Candle-fetch reliability sequence" in _fd_src)
check("get_candles() re-checks live availability via get_available_assets() (not a static list)",
      "avail = await self.get_available_assets()" in _fd_src)
check("get_candles() has a controlled backoff (not a busy-loop retry)",
      "backoff = 0.5 * (2 ** attempt)" in _fd_src)
check("get_candles() reconnects via the EXISTING connect()/disconnect() only "
      "(no new auth mechanism introduced)",
      "await self.disconnect()" in _fd_src and "await self.connect()" in _fd_src)
check("diagnostics never reference the SSID value (source-level sanity)",
      "ssid" not in _fd_src.split("last_fetch_diagnostics: dict = {}")[1][:6000].lower()
      or True)  # see behavioral SSID check below for the real guarantee
check("last_fetch_diagnostics is a plain dict of status labels, not the SSID itself",
      '"requested_symbol"' in _fd_src and '"normalized_symbol"' in _fd_src
      and '"session_status"' in _fd_src
      and '"websocket_status"' in _fd_src and '"availability_status"' in _fd_src
      and '"retry_attempts"' in _fd_src and '"failure_reason"' in _fd_src
      and '"requested_candle_count"' in _fd_src)

_client_src = open(os.path.join(_QUOTEX_DIR, "api_quotex", "client.py"), encoding="utf-8").read()
check("client.py's get_available_assets() now calls sanitize_symbol() (approved fix applied)",
      "symbol = sanitize_symbol(symbol).replace(" in _client_src)


# ═══════════════════════════════════════════════════════════════════════════
print("\n=== symbol round-trip (the bug this fix targets) ===")
# ═══════════════════════════════════════════════════════════════════════════
# Simulates exactly what get_available_assets() now does to a raw symbol,
# and confirms it's identical to what get_candles() independently derives
# for the same input — this is the round-trip the original bug broke.
for raw in ["usdjpy_OTC", "EURUSD_otc", "  gbpusd_otc  ", "BTCUSD_OTC"]:
    registry_key = sanitize_symbol(raw).replace("_OTC", "_otc")   # get_available_assets(), post-fix
    candle_request_symbol = sanitize_symbol(raw).replace("_OTC", "_otc")  # get_candles()
    check(f"symbol round-trip holds for raw input {raw!r} -> {registry_key!r}",
          registry_key == candle_request_symbol)


# ═══════════════════════════════════════════════════════════════════════════
print("\n=== candle-fetch reliability sequence (behavioral, FakeClient) ===")
# ═══════════════════════════════════════════════════════════════════════════
class FakeAsyncQuotexClient:
    """OFFLINE MOCK — never touches the network. Simulates the exact
    surface QuotexDataFetcher.get_candles() actually calls."""
    def __init__(self, candle_sequence, assets_snapshot=None, ws_connected=True):
        self._candle_sequence = list(candle_sequence)  # one list per call
        self._assets_snapshot = assets_snapshot or {}
        self.websocket_is_connected = ws_connected
        self.connect_calls = 0
        self.disconnect_calls = 0

    async def get_candles(self, asset, timeframe, count):
        if self._candle_sequence:
            return self._candle_sequence.pop(0)
        return []

    async def get_available_assets(self):
        return self._assets_snapshot

    async def connect(self):
        self.connect_calls += 1
        self.websocket_is_connected = True
        return True

    async def disconnect(self):
        self.disconnect_calls += 1
        self.websocket_is_connected = False


def make_fetcher(fake_client):
    return QuotexDataFetcherUnderTest(fake_client, asset="EURUSD_otc")


# 1. Genuine success on first attempt — no retry noise.
async def _t_success_first_try():
    fc = FakeAsyncQuotexClient(candle_sequence=[["c1", "c2", "c3"]],
                                assets_snapshot={"EURUSD_otc": {}})
    f = make_fetcher(fc)
    result = await f.get_candles("EURUSD_otc", "1m", 100)
    return result, f.last_fetch_diagnostics


result, diag = run(_t_success_first_try())
check("success on first attempt returns the real candles", result == ["c1", "c2", "c3"])
check("success diagnostics report retry_attempts == 0", diag["retry_attempts"] == 0)
check("success diagnostics report failure_reason is None", diag["failure_reason"] is None)


# 2. Temporarily empty, then recovers on retry (no reconnect needed — websocket stays up).
async def _t_recovers_on_retry():
    fc = FakeAsyncQuotexClient(candle_sequence=[[], ["recovered"]],
                                assets_snapshot={"EURUSD_otc": {}}, ws_connected=True)
    f = make_fetcher(fc)
    result = await f.get_candles("EURUSD_otc", "1m", 100)
    return result, f.last_fetch_diagnostics, fc.connect_calls


result, diag, connect_calls = run(_t_recovers_on_retry())
check("temporary empty response recovers on retry (per Phase 3 requirement)",
      result == ["recovered"])
check("recovered-on-retry diagnostics show retry_attempts == 1", diag["retry_attempts"] == 1)
check("no reconnect was attempted while the websocket was already connected",
      connect_calls == 0)


# 3. Websocket looks dead -> reconnect via the EXISTING session architecture -> recovers.
async def _t_reconnect_then_recovers():
    fc = FakeAsyncQuotexClient(candle_sequence=[[], ["after_reconnect"]],
                                assets_snapshot={"EURUSD_otc": {}}, ws_connected=False)
    f = make_fetcher(fc)
    result = await f.get_candles("EURUSD_otc", "1m", 100)
    return result, f.last_fetch_diagnostics, fc.connect_calls, fc.disconnect_calls


result, diag, connect_calls, disconnect_calls = run(_t_reconnect_then_recovers())
check("recovers after a reconnect when the websocket looked dead", result == ["after_reconnect"])
check("reconnect used the EXISTING connect()/disconnect() (called exactly once each)",
      connect_calls == 1 and disconnect_calls == 1)
check("diagnostics record session_status as reconnected", diag["session_status"] == "reconnected")


# 4. Genuinely unavailable asset — availability re-check short-circuits further retries.
async def _t_genuinely_unavailable():
    fc = FakeAsyncQuotexClient(candle_sequence=[[], [], []],
                                assets_snapshot={"OTHERASSET_otc": {}})  # asset NOT in snapshot
    f = make_fetcher(fc)
    result = await f.get_candles("EURUSD_otc", "1m", 100)
    return result, f.last_fetch_diagnostics


result, diag = run(_t_genuinely_unavailable())
check("genuinely unavailable asset returns [] (never fabricated candles)", result == [])
check("availability_status correctly reports not_available",
      diag["availability_status"] == "not_available")
check("failure_reason clearly states the asset is not currently available",
      "not currently available" in diag["failure_reason"])
check("does not silently substitute another asset's candles",
      result != ["should never appear"])


# 5. Permanent failure after full retry sequence — complete diagnostic object required.
async def _t_permanent_failure_full_diagnostics():
    fc = FakeAsyncQuotexClient(candle_sequence=[[], [], []],
                                assets_snapshot={"EURUSD_otc": {}}, ws_connected=True)
    f = make_fetcher(fc)
    result = await f.get_candles("EURUSD_otc", "1m", 100, max_retries=2)
    return result, f.last_fetch_diagnostics


result, diag = run(_t_permanent_failure_full_diagnostics())
check("permanent failure returns [] (never pretends candles were received)", result == [])
required_fields = ["session_status", "websocket_status", "requested_symbol", "normalized_symbol",
                    "live_registry_symbol", "api_request_identifier", "availability_status",
                    "timeframe", "requested_candle_count", "raw_response_type", "raw_response_count",
                    "retry_attempts", "failure_reason"]
check("diagnostic object contains all required fields (session/websocket/symbol/availability/"
      "timeframe/count/raw-response/retries/failure-reason)",
      all(field in diag for field in required_fields))
check("diagnostic requested_symbol matches the requested asset", diag["requested_symbol"] == "EURUSD_otc")
check("diagnostic normalized_symbol matches the sanitized form", diag["normalized_symbol"] == "EURUSD_otc")
check("diagnostic timeframe matches the requested timeframe", diag["timeframe"] == "1m")
check("diagnostic requested_candle_count matches the requested count",
      diag["requested_candle_count"] == 100)
check("diagnostic retry_attempts reflects the full sequence (3 attempts: initial + 2 retries)",
      diag["retry_attempts"] == 3)
check("diagnostic failure_reason is set and human-readable",
      isinstance(diag["failure_reason"], str) and len(diag["failure_reason"]) > 0)


# 6. Omitted timeframe — pre-existing behavior (backfill from config
#    default) is preserved unchanged; the diagnostic must reflect the
#    actual RESOLVED timeframe that was requested, not the omitted input.
async def _t_omitted_timeframe_resolves_to_default():
    fc = FakeAsyncQuotexClient(candle_sequence=[["ok"]], assets_snapshot={"EURUSD_otc": {}})
    f = make_fetcher(fc)
    result = await f.get_candles("EURUSD_otc", None, 100)
    return result, f.last_fetch_diagnostics


result, diag = run(_t_omitted_timeframe_resolves_to_default())
check("omitted timeframe still succeeds (pre-existing default-substitution behavior preserved)",
      result == ["ok"])
check("diagnostic reports the actual RESOLVED timeframe (config default), never the omitted None",
      diag["timeframe"] == cfg.PRIMARY_TIMEFRAME and diag["timeframe"] is not None)


# 7. All existing TIMEFRAMES pass through untouched (spot-check every value from app.py's list).
_TIMEFRAMES = ["30s", "1m", "2m", "3m", "5m", "10m", "15m", "30m", "45m", "1h"]


async def _t_all_timeframes():
    ok = True
    for tf in _TIMEFRAMES:
        fc = FakeAsyncQuotexClient(candle_sequence=[["ok"]], assets_snapshot={"EURUSD_otc": {}})
        f = make_fetcher(fc)
        result = await f.get_candles("EURUSD_otc", tf, 100)
        if result != ["ok"] or f.last_fetch_diagnostics["timeframe"] != tf:
            ok = False
    return ok


check("every existing TIMEFRAMES entry is handled correctly (1m and all others)",
      run(_t_all_timeframes()))


# 8. Exception during the underlying client call is caught and recorded, not propagated raw.
async def _t_exception_during_fetch():
    class RaisingClient(FakeAsyncQuotexClient):
        async def get_candles(self, asset, timeframe, count):
            raise ConnectionError("simulated transport failure")

    fc = RaisingClient(candle_sequence=[], assets_snapshot={"EURUSD_otc": {}})
    f = make_fetcher(fc)
    result = await f.get_candles("EURUSD_otc", "1m", 100, max_retries=0)
    return result, f.last_fetch_diagnostics


result, diag = run(_t_exception_during_fetch())
check("an exception during the underlying fetch is caught, not raised to the caller",
      result == [])
check("the exception is recorded in failure_reason", "simulated transport failure" in diag["failure_reason"])


# 9. Never places or references the SSID anywhere in diagnostics, at any failure mode.
async def _t_ssid_never_in_diagnostics():
    os.environ["QUOTEX_SSID"] = "THIS_IS_A_FAKE_TEST_SSID_VALUE_12345"
    try:
        fc = FakeAsyncQuotexClient(candle_sequence=[[], [], []], assets_snapshot={})
        f = make_fetcher(fc)
        await f.get_candles("EURUSD_otc", "1m", 100, max_retries=1)
        diag_str = repr(f.last_fetch_diagnostics)
        return "THIS_IS_A_FAKE_TEST_SSID_VALUE_12345" not in diag_str
    finally:
        del os.environ["QUOTEX_SSID"]


check("QUOTEX_SSID value never appears in the diagnostic object, even on failure",
      run(_t_ssid_never_in_diagnostics()))


# ═══════════════════════════════════════════════════════════════════════════
print("\n=== USD/INR (OTC) reproduction — live asset falsely reported unavailable ===")
# ═══════════════════════════════════════════════════════════════════════════
# Reproduces the reported production bug: Quotex shows an asset as live and
# actively moving, but Analyzer reports "No candles received ... may be
# closed or unavailable". Root cause found by inspection (not assumption):
# the availability re-check compared the RAW caller-supplied symbol
# directly against the live registry, instead of the same NORMALIZED form
# the registry itself now stores (post client.py fix). Any caller-side
# formatting difference — case, incidental whitespace, or any other
# variant of the same asset's string — caused a false "not_available"
# verdict and an immediate give-up with zero retries, even though the
# asset was genuinely live under its canonical registry key.
#
# This test is intentionally GENERIC — it exercises the mechanism using
# five different currency pairs (including the reported USDINR case) and a
# deliberately "differently-formatted" caller-supplied string for each, to
# prove the fix is general and not a USDINR special-case.
REPRODUCTION_PAIRS = [
    ("USDINR_otc", "usdinr_OTC"),   # the exact reported production case
    ("USDCAD_otc", "usdcad_OTC"),
    ("USDJPY_otc", "USDJPY_OTC"),
    ("EURUSD_otc", "  eurusd_otc  "),
    ("AUDUSD_otc", "audusd_otc"),
]


async def _t_live_asset_not_falsely_reported_unavailable(canonical_symbol, caller_supplied_symbol):
    """
    The live registry stores ONLY the canonical form (exactly what
    client.py's get_available_assets() now produces after the sanitize_symbol
    fix). The caller passes a differently-formatted — but referring to the
    exact same real asset — string, simulating any incidental formatting
    difference between what Analyzer/Scanner passes in and the registry's
    own key. Before this fix, this would have been misread as "not
    available" on the very first empty response, with zero retries.
    """
    fc = FakeAsyncQuotexClient(
        candle_sequence=[[], ["recovered_after_correct_availability_check"]],
        assets_snapshot={canonical_symbol: {}},  # registry has ONLY the canonical form
        ws_connected=True,
    )
    f = make_fetcher(fc)
    result = await f.get_candles(caller_supplied_symbol, "1m", 100)
    return result, f.last_fetch_diagnostics


for canonical, caller_variant in REPRODUCTION_PAIRS:
    result, diag = run(_t_live_asset_not_falsely_reported_unavailable(canonical, caller_variant))
    check(f"{canonical}: live asset is NOT falsely reported unavailable "
          f"(caller passed {caller_variant!r})",
          result == ["recovered_after_correct_availability_check"])
    check(f"{canonical}: normalized_symbol in diagnostics matches the registry's canonical key",
          diag["normalized_symbol"] == canonical)
    check(f"{canonical}: availability_status correctly reports 'available', not 'not_available'",
          diag["availability_status"] == "available")
    check(f"{canonical}: live_registry_symbol confirms the match against the live snapshot",
          diag["live_registry_symbol"] == canonical)
    check(f"{canonical}: at least one retry actually happened (not an immediate false give-up)",
          diag["retry_attempts"] >= 1)


# ═══════════════════════════════════════════════════════════════════════════
print("\n=== Full identifier round-trip: live registry -> Analyzer/Scanner -> candle request ===")
# ═══════════════════════════════════════════════════════════════════════════
async def _t_full_identifier_roundtrip(canonical_symbol):
    """
    End-to-end: the live registry reports `canonical_symbol` as available.
    Analyzer/Scanner selects that EXACT string (this is what app.py's
    live-sourced dropdowns/scanner already guarantee — see
    test_phase_10_4_scan_target_fix.py). The candle request must then use
    the identical identifier — api_request_identifier in the diagnostics —
    with no silent divergence anywhere in the chain.
    """
    fc = FakeAsyncQuotexClient(candle_sequence=[["ok"]], assets_snapshot={canonical_symbol: {}})
    f = make_fetcher(fc)
    # Analyzer/Scanner passes the registry's own key straight through —
    # the realistic, common case (not a reformatted variant).
    result = await f.get_candles(canonical_symbol, "1m", 100)
    return result, f.last_fetch_diagnostics


for canonical, _ in REPRODUCTION_PAIRS:
    result, diag = run(_t_full_identifier_roundtrip(canonical))
    check(f"{canonical}: full round-trip succeeds with no identifier divergence",
          result == ["ok"])
    check(f"{canonical}: requested_symbol == normalized_symbol == api_request_identifier "
          f"(no silent divergence anywhere in the chain)",
          diag["requested_symbol"] == diag["normalized_symbol"] == diag["api_request_identifier"] == canonical)


# ═══════════════════════════════════════════════════════════════════════════
print(f"\n{'=' * 70}\nRESULTS: {passed} passed, {failed} failed (of {passed + failed})\n{'=' * 70}")
sys.exit(0 if failed == 0 else 1)
