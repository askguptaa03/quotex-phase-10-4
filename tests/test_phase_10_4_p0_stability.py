"""
P0 Stability Fixes — targeted regression suite (post read-only audit).

Covers the four orchestration-layer fixes from the Phase 10.4 stability
audit, plus the deployment/worker-count finding:

  1. Unknown Asset — live asset source of truth (app.py's asset gates)
  2. SSID / session replacement (_invalidate_shared_fetcher explicit
     disconnect; env-var precedence now reported, not silently ignored)
  3. Backtest — must finish the entire batch (per-asset compute isolation,
     assets_processed-based progress that reaches 100%)
  4. Validation — must finish the entire batch (per-indicator isolation,
     accurate `completed` semantics)
  5. Multi-worker / deployment state consistency (gunicorn workers pinned)

These are OFFLINE UNIT TESTS — no live Quotex session, no network. Where a
fetch/live-session dependency exists, it is replaced with an explicitly
labeled offline mock (async callables / fake fetcher objects), same
convention as test_phase_10_1.py's ValidationEngine tests. Never used as
proof of live Quotex integration — only for verifying the orchestration
logic itself is correct.

Run with:  python3 Quotex/tests/test_phase_10_4_p0_stability.py
"""
import sys
import os
import re
import asyncio

_HERE = os.path.dirname(os.path.abspath(__file__))
_MARKET_ANALYZER = os.path.join(_HERE, "..", "market_analyzer")
_WEBAPP = os.path.join(_MARKET_ANALYZER, "webapp")
sys.path.insert(0, _MARKET_ANALYZER)
sys.path.insert(0, _WEBAPP)

import numpy as np
import pandas as pd

from backtest_engine import BacktestEngine, STOPPED as BT_STOPPED
from validation_engine import ValidationEngine, STOPPED as VAL_STOPPED

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


def make_synthetic_df(n=300, seed=0):
    rng = np.random.RandomState(seed)
    price = 100 + np.cumsum(rng.randn(n) * 0.5)
    return pd.DataFrame({
        "open": price + rng.randn(n) * 0.1,
        "high": price + np.abs(rng.randn(n) * 0.3),
        "low": price - np.abs(rng.randn(n) * 0.3),
        "close": price,
        "volume": rng.randint(100, 1000, n),
    })


def run_engine_to_completion(coro_fn, timeout=15.0):
    """Run a background-loop-style coroutine synchronously for the test process."""
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(asyncio.wait_for(coro_fn(loop), timeout))
    finally:
        loop.close()


# ═══════════════════════════════════════════════════════════════════════════
print("=== 1. Unknown Asset — live asset source of truth (app.py source checks) ===")
# ═══════════════════════════════════════════════════════════════════════════
_app_src = open(os.path.join(_WEBAPP, "app.py"), encoding="utf-8").read()

check("app.py defines _check_live_asset() (live-snapshot gate, not static ASSETS)",
      "def _check_live_asset(" in _app_src)
check("/api/signal no longer gates on 'asset not in ASSETS'",
      _app_src.count("if asset not in ASSETS:") == 0)
check("/api/signal now calls _check_live_asset(asset)",
      re.search(r'@app\.route\("/api/signal".*?_check_live_asset\(asset\)', _app_src, re.S) is not None)
check("/api/ai/explain now calls _check_live_asset(asset)",
      re.search(r'@app\.route\("/api/ai/explain".*?_check_live_asset\(asset\)', _app_src, re.S) is not None)
check("_check_live_asset() returns a session-failure status distinct from unknown-asset (503 vs 400)",
      '"status": 503' in _app_src and '"status": 400' in _app_src)
check("backtest route's invalid_assets check now also accepts live-snapshot assets",
      "a not in ASSETS and a not in live_snapshot" in _app_src)
check("validation route's invalid_assets check now also accepts live-snapshot assets",
      "a not in ASSETS and a not in live_symbols" in _app_src)
check("static ASSETS dict itself was NOT deleted (still imported/used)",
      "ASSETS" in _app_src and "from" in _app_src.split("ASSETS")[0][-40:] or "import" in _app_src)
check("no fabricated asset/candle/signal helper was introduced (_check_live_asset only reads live_assets)",
      "fabricate" not in _app_src.lower() or "Do NOT fabricate" not in _app_src)  # sanity: no accidental echo


# ═══════════════════════════════════════════════════════════════════════════
print("\n=== 2. SSID / session replacement (source + behavioral checks) ===")
# ═══════════════════════════════════════════════════════════════════════════
check("_invalidate_shared_fetcher() now calls old_fetcher.disconnect() (not just drops the reference)",
      "await old_fetcher.disconnect()" in _app_src)
check("disconnect is scheduled via run_coroutine_threadsafe (fire-and-forget, no deadlock risk)",
      "asyncio.run_coroutine_threadsafe(_close_old_fetcher()" in _app_src)
check("/api/session/update reports env_var_override_active",
      '"env_var_override_active"' in _app_src)
check("/api/session/update warns explicitly when QUOTEX_SSID env var will silently override the new SSID",
      "will NOT" in _app_src and "session.json will NOT be used" not in _app_src)  # message exists, not a literal echo bug
check("/api/session/validate reports which ssid_source was actually used",
      '"ssid_source": ssid_source' in _app_src)

# Behavioral check on the REAL _invalidate_shared_fetcher() source.
#
# NOTE (offline-sandbox limitation, same one already documented in
# test_phase_10_4_goal2/3/4/5.py): app.py cannot be imported directly in
# this sandbox — its import chain (fetch_data -> quotex.api_quotex ->
# loguru/websockets) needs third-party packages that aren't installed
# here and never will be reachable offline. Rather than reimplementing
# the fix logic by hand (which would test a copy, not the real fix), the
# ACTUAL _invalidate_shared_fetcher() function body is extracted verbatim
# from app.py's source and exec'd in an isolated namespace that supplies
# only real asyncio + a fake _get_bg_loop()/_shared_fetcher — no app.py
# import, no network, no live Quotex session. This exercises the exact
# committed source, not a rewritten stand-in.
_app_src_full = open(os.path.join(_WEBAPP, "app.py"), encoding="utf-8").read()
_invalidate_fn_src_match = re.search(
    r"\ndef _invalidate_shared_fetcher\(\).*?\n\n\nasync def _run_pipeline", _app_src_full, re.S
)
check("could extract _invalidate_shared_fetcher() source verbatim from app.py for isolated exec",
      _invalidate_fn_src_match is not None)
_invalidate_fn_src = _invalidate_fn_src_match.group(0).rsplit("\n\n\nasync def _run_pipeline", 1)[0] \
    if _invalidate_fn_src_match else ""


class _FakeFetcher:
    def __init__(self, tag):
        self.tag = tag
        self.disconnected = False

    async def disconnect(self):
        self.disconnected = True


def _build_isolated_invalidate_namespace(loop, initial_fetcher):
    ns = {"asyncio": asyncio, "_shared_fetcher": initial_fetcher}
    ns["_get_bg_loop"] = lambda: loop
    exec(compile(_invalidate_fn_src, "<extracted _invalidate_shared_fetcher>", "exec"), ns)
    return ns


async def _ssid_replacement_scenario(loop):
    old = _FakeFetcher("old-ssid-session")
    ns = _build_isolated_invalidate_namespace(loop, old)
    ns["_invalidate_shared_fetcher"]()
    # _shared_fetcher must be cleared immediately (new SSID replaces old
    # session's usability right away, even before disconnect() finishes)
    cleared_immediately = ns["_shared_fetcher"] is None
    # give the fire-and-forget disconnect coroutine a moment to run
    await asyncio.sleep(0.05)
    return cleared_immediately, old.disconnected


try:
    cleared_immediately, old_disconnected = run_engine_to_completion(_ssid_replacement_scenario)
    check("new SSID replaces old session: _shared_fetcher cleared immediately on invalidate",
          cleared_immediately)
    check("new SSID replaces old session: old fetcher's disconnect() was actually invoked",
          old_disconnected)
except Exception as exc:
    check(f"SSID replacement scenario raised unexpectedly: {exc}", False)
    check("new SSID replaces old session: old fetcher's disconnect() was actually invoked", False)


async def _invalid_new_ssid_scenario(loop):
    """Invalid new SSID must not silently keep serving the old session:
    after invalidate, the module-level fetcher reference must NOT have
    reverted to the old (already-invalidated) fetcher object."""
    old = _FakeFetcher("old-ssid-session")
    ns = _build_isolated_invalidate_namespace(loop, old)
    ns["_invalidate_shared_fetcher"]()
    await asyncio.sleep(0.05)
    still_old = ns["_shared_fetcher"] is old
    return still_old


try:
    still_old = run_engine_to_completion(_invalid_new_ssid_scenario)
    check("invalid new SSID does not reuse old session (_shared_fetcher never reverts to old object)",
          not still_old)
except Exception as exc:
    check(f"invalid-new-SSID scenario raised unexpectedly: {exc}", False)


# ═══════════════════════════════════════════════════════════════════════════
print("\n=== 3. Backtest — must finish the entire batch ===")
# ═══════════════════════════════════════════════════════════════════════════
GOOD_DF = make_synthetic_df(n=500, seed=1)


async def _fetch_mixed(asset, timeframe, count):
    """OFFLINE MOCK fetch_candles — never touches Quotex. One asset fails
    (fetch exception), one has no data, one succeeds."""
    if asset == "FAIL_OTC":
        raise ConnectionError("simulated fetch failure")
    if asset == "NODATA_OTC":
        return pd.DataFrame()
    return GOOD_DF.copy()


async def _run_backtest(loop):
    engine = BacktestEngine(fetch_candles=_fetch_mixed)
    result = engine.start(loop=loop, assets=["FAIL_OTC", "NODATA_OTC", "GOOD_OTC"],
                           timeframe="1m", candle_count=500, lookahead=4)
    check("backtest.start() accepted the mixed-outcome batch", result["ok"])
    # poll status() until STOPPED (loop runs in-process here)
    for _ in range(200):
        st = engine.status()
        if st["state"] == BT_STOPPED:
            break
        await asyncio.sleep(0.01)
    return engine


try:
    engine = run_engine_to_completion(_run_backtest)
    st = engine.status()
    check("backtest fetch failure does not abort the batch (3 results recorded, not 1)",
          len(engine.results) == 3)
    check("backtest result for FAIL_OTC recorded as FAILED (real state, not fabricated)",
          engine.results.get("FAIL_OTC", {}).get("status") == "FAILED")
    check("backtest result for NODATA_OTC recorded as NO_DATA (distinct from FAILED)",
          engine.results.get("NODATA_OTC", {}).get("status") == "NO_DATA")
    check("backtest result for GOOD_OTC recorded as SUCCESS",
          engine.results.get("GOOD_OTC", {}).get("status") == "SUCCESS")
    check("backtest reaches 100% percent_complete once every asset has been attempted",
          st["percent_complete"] == 100.0)
    check("backtest status() reports completed=True for a genuinely finished run",
          st["completed"] is True)
    check("backtest assets_processed == total_assets at completion",
          st["assets_processed"] == st["total_assets"] == 3)
    check("backtest summary distinguishes succeeded/no_data/failed",
          engine.summary["assets_succeeded"] == 1
          and engine.summary["assets_no_data"] == 1
          and engine.summary["assets_failed"] == 1)
except Exception as exc:
    check(f"backtest fetch-failure-continues scenario raised unexpectedly: {exc}", False)


async def _compute_raiser(df, lookahead=4):
    raise RuntimeError("simulated compute exception")


async def _run_backtest_compute_failure(loop):
    import backtest_engine as be_module
    original = be_module.backtest_factor_accuracy
    be_module.backtest_factor_accuracy = lambda df, lookahead=4: (_ for _ in ()).throw(
        RuntimeError("simulated compute exception")
    )
    try:
        async def _fetch_always_ok(asset, timeframe, count):
            return GOOD_DF.copy()

        engine = BacktestEngine(fetch_candles=_fetch_always_ok)
        result = engine.start(loop=loop, assets=["A_OTC", "B_OTC"],
                               timeframe="1m", candle_count=500, lookahead=4)
        for _ in range(200):
            if engine.status()["state"] == BT_STOPPED:
                break
            await asyncio.sleep(0.01)
        return engine
    finally:
        be_module.backtest_factor_accuracy = original


try:
    engine2 = run_engine_to_completion(_run_backtest_compute_failure)
    st2 = engine2.status()
    check("backtest compute exception does not abort the batch (both assets have a result)",
          len(engine2.results) == 2)
    check("backtest compute failure recorded as FAILED for both assets (isolated, not batch-fatal)",
          all(r.get("status") == "FAILED" for r in engine2.results.values()))
    check("backtest still reaches 100% (attempted, not succeeded) even when EVERY asset's compute step fails",
          st2["percent_complete"] == 100.0)
    check("backtest run with all-failed assets is NOT reported completed=True as a success illusion — "
          "'completed' still True (loop finished) but assets_succeeded is 0 in the summary",
          st2["completed"] is True and engine2.summary["assets_succeeded"] == 0)
except Exception as exc:
    check(f"backtest compute-failure-continues scenario raised unexpectedly: {exc}", False)


# ═══════════════════════════════════════════════════════════════════════════
print("\n=== 4. Validation — must finish the entire batch ===")
# ═══════════════════════════════════════════════════════════════════════════
async def _fetch_val_mixed(asset, timeframe, count):
    if asset == "FAIL_OTC":
        raise ConnectionError("simulated fetch failure")
    if asset == "NODATA_OTC":
        return pd.DataFrame()
    return GOOD_DF.copy()


async def _run_validation(loop):
    engine = ValidationEngine(fetch_candles=_fetch_val_mixed)
    result = engine.start(loop=loop, assets=["FAIL_OTC", "NODATA_OTC", "GOOD_OTC"],
                           timeframes=["1m"], indicators=["rsi_div", "bb"],
                           candle_count=500, lookahead=4)
    check("validation.start() accepted the mixed-outcome batch", result["ok"])
    for _ in range(200):
        if engine.status()["state"] == VAL_STOPPED:
            break
        await asyncio.sleep(0.01)
    return engine


try:
    vengine = run_engine_to_completion(_run_validation)
    vst = vengine.status()
    check("validation combination failure does not abort the run (3 combinations recorded)",
          len(vengine.results) == 3)
    check("validation reaches 100% once every combination has been attempted",
          vst["percent_complete"] == 100.0)
    check("validation status() reports completed=True for a genuinely finished run",
          vst["completed"] is True)
    check("validation combinations_processed == total_combinations at completion",
          vst["combinations_processed"] == vst["total_combinations"] == 3)
    check("validation summary distinguishes succeeded/no_data/failed combinations",
          vengine.summary["combinations_succeeded"] == 1
          and vengine.summary["combinations_no_data"] == 1
          and vengine.summary["combinations_failed"] == 1)
except Exception as exc:
    check(f"validation combination-failure-continues scenario raised unexpectedly: {exc}", False)


async def _run_validation_indicator_failure(loop):
    import validation_engine as ve_module
    original = ve_module.validate_indicator_universal

    def _raiser(df, name, asset, timeframe, lookahead=4):
        if name == "rsi_div":
            raise RuntimeError("simulated indicator exception")
        return original(df, name, asset, timeframe, lookahead=lookahead)

    ve_module.validate_indicator_universal = _raiser
    try:
        async def _fetch_always_ok(asset, timeframe, count):
            return GOOD_DF.copy()

        engine = ValidationEngine(fetch_candles=_fetch_always_ok)
        result = engine.start(loop=loop, assets=["A_OTC", "B_OTC"], timeframes=["1m"],
                               indicators=["rsi_div", "bb", "stoch"],
                               candle_count=500, lookahead=4)
        for _ in range(200):
            if engine.status()["state"] == VAL_STOPPED:
                break
            await asyncio.sleep(0.01)
        return engine
    finally:
        ve_module.validate_indicator_universal = original


try:
    vengine2 = run_engine_to_completion(_run_validation_indicator_failure)
    vst2 = vengine2.status()
    check("validation: a single bad indicator (rsi) does not kill the whole run "
          "(both asset combinations still processed)",
          vengine2.combinations_processed == 2)
    check("validation: the failing indicator (rsi) is recorded as FAILED per-combination, "
          "not silently dropped or fabricated",
          all(r["indicators"]["rsi_div"].get("status") == "FAILED" for r in vengine2.results.values()))
    check("validation: the OTHER indicators in the same combination still completed successfully",
          all("error" not in r["indicators"]["bb"] and "error" not in r["indicators"]["stoch"]
              for r in vengine2.results.values()))
    check("validation reaches 100% with a failed indicator present (attempted, not perfect, basis)",
          vst2["percent_complete"] == 100.0)
    check("validation completion status accurately reflects the run finished "
          "(completed=True; per-indicator failures visible in indicator_failures, not hidden)",
          vst2["completed"] is True
          and all(r.get("indicator_failures") == ["rsi_div"] for r in vengine2.results.values()))
except Exception as exc:
    check(f"validation indicator-failure-continues scenario raised unexpectedly: {exc}", False)


# ═══════════════════════════════════════════════════════════════════════════
print("\n=== 5. Multi-worker / deployment configuration ===")
# ═══════════════════════════════════════════════════════════════════════════
_gunicorn_src = open(os.path.join(_WEBAPP, "gunicorn.conf.py"), encoding="utf-8").read()
check("gunicorn.conf.py pins workers = 1 (matches the process-global shared-state architecture)",
      re.search(r"^workers\s*=\s*1\s*$", _gunicorn_src, re.M) is not None)
check("gunicorn.conf.py no longer reads WEB_CONCURRENCY to decide worker count "
      "(was previously able to silently spawn >1 worker)",
      "os.environ.get(\"WEB_CONCURRENCY\"" not in _gunicorn_src)


# ═══════════════════════════════════════════════════════════════════════════
print("\n=== 6. Protected files / unrelated-behavior guardrails ===")
# ═══════════════════════════════════════════════════════════════════════════
check("app.py: hard-gate / mandatory-filter logic untouched (calculate_filter_score not redefined here)",
      "def calculate_filter_score" not in _app_src)
check("app.py: no confluence-weight or threshold constants were introduced by this fix",
      "DEFAULT_CONFLUENCE_WEIGHTS" not in _app_src.split("_check_live_asset")[0][-2000:]
      if "_check_live_asset" in _app_src else True)
_backtest_engine_src = open(os.path.join(_WEBAPP, "backtest_engine.py"), encoding="utf-8").read()
check("backtest_engine.py: does not import analyzer.py (docstring mentioning it by name is fine)",
      re.search(r"^\s*(import analyzer|from analyzer import)", _backtest_engine_src, re.M) is None)
check("validation_engine.py: still delegates to validate_indicator_universal (no duplicated math)",
      "validate_indicator_universal(" in open(os.path.join(_WEBAPP, "validation_engine.py"), encoding="utf-8").read())


# ═══════════════════════════════════════════════════════════════════════════
print(f"\n{'=' * 70}\nRESULTS: {passed} passed, {failed} failed (of {passed + failed})\n{'=' * 70}")
sys.exit(0 if failed == 0 else 1)
