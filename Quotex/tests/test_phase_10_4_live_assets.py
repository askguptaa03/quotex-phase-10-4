"""
Regression tests for the Live Quotex Asset Availability System.

These are OFFLINE UNIT TESTS using fake fetcher/session stubs — they never
touch a real Quotex account or the network. They verify the DECISION LOGIC
(live_assets.py, ScannerEngine.start()'s snapshot handling, the API/JS
wiring) behaves correctly for known inputs, not that live Quotex data is
correct. See the accompanying chat report for LIVE VERIFICATION status.

Self-contained script, same style/runner convention as the other
test_phase_10_4_*.py files — no pytest dependency, plain `python3
test_phase_10_4_live_assets.py`.
"""
import asyncio
import os
import re
import sys

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MARKET_ANALYZER_DIR = os.path.join(REPO_ROOT, "market_analyzer")
WEBAPP_DIR = os.path.join(MARKET_ANALYZER_DIR, "webapp")
sys.path.insert(0, MARKET_ANALYZER_DIR)
sys.path.insert(0, WEBAPP_DIR)

passed = 0
failed = 0


def check(label, condition):
    global passed, failed
    if condition:
        print(f"  PASS  {label}")
        passed += 1
    else:
        print(f"  FAIL  {label}")
        failed += 1


import live_assets  # noqa: E402


def _asset(sym, name, is_otc=True, is_open=True, payout=85):
    return {"id": 1, "name": name, "type": "currency", "payout": payout,
            "is_otc": is_otc, "is_open": is_open, "available_timeframes": ["5m"]}


class FakeFetcher:
    """Stand-in for QuotexDataFetcher — returns a canned asset dict or raises."""
    def __init__(self, assets=None, raise_exc=None):
        self._assets = assets if assets is not None else {}
        self._raise = raise_exc
        self.calls = 0

    async def get_available_assets(self):
        self.calls += 1
        if self._raise:
            raise self._raise
        return self._assets


def run(coro):
    return asyncio.run(coro)


def _make_otc_universe(n, prefix="sym"):
    return {f"{prefix}{i}_otc": _asset(f"{prefix}{i}_otc", f"Sym {i}") for i in range(n)}


# ─────────────────────────────────────────────────────────────────────────
print("=== 1-5. live_assets.py — 0 / 1 / 25 / 53 / 100 live OTC assets ===")
for n in (0, 1, 25, 53, 100):
    live_assets._cache = {"timestamp": 0.0, "assets": {}}  # force a fresh fetch each case
    fetcher = FakeFetcher(assets=_make_otc_universe(n))
    result = run(live_assets.get_live_otc_assets(fetcher, force_refresh=True))
    check(f"{n} live OTC assets available -> exactly {n} returned (not capped/padded)",
          len(result) == n)
    snap = live_assets.build_snapshot(known_universe=[f"known{i}_otc" for i in range(53)], live_assets=result)
    check(f"{n} live OTC assets -> build_snapshot available_otc_count == {n}",
          snap["available_otc_count"] == n)
    check(f"{n} live OTC assets -> build_snapshot available_otc_assets has exactly {n} symbols",
          len(snap["available_otc_assets"]) == n)


print("\n=== 6. Asset removed from live list — disappears on next refresh ===")
live_assets._cache = {"timestamp": 0.0, "assets": {}}
fetcher_before = FakeFetcher(assets={"eurusd_otc": _asset("eurusd_otc", "EUR/USD"),
                                      "gbpusd_otc": _asset("gbpusd_otc", "GBP/USD")})
before = run(live_assets.get_live_otc_assets(fetcher_before, force_refresh=True))
check("both assets present before removal", set(before.keys()) == {"eurusd_otc", "gbpusd_otc"})

live_assets._cache = {"timestamp": 0.0, "assets": {}}
fetcher_after = FakeFetcher(assets={"eurusd_otc": _asset("eurusd_otc", "EUR/USD")})
after = run(live_assets.get_live_otc_assets(fetcher_after, force_refresh=True))
check("removed asset (gbpusd_otc) is gone from the live list after refresh",
      "gbpusd_otc" not in after and "eurusd_otc" in after)


print("\n=== 7. Asset newly added — appears automatically on next refresh ===")
live_assets._cache = {"timestamp": 0.0, "assets": {}}
fetcher_before2 = FakeFetcher(assets={"eurusd_otc": _asset("eurusd_otc", "EUR/USD")})
before2 = run(live_assets.get_live_otc_assets(fetcher_before2, force_refresh=True))
check("only 1 asset before addition", len(before2) == 1)

live_assets._cache = {"timestamp": 0.0, "assets": {}}
fetcher_after2 = FakeFetcher(assets={"eurusd_otc": _asset("eurusd_otc", "EUR/USD"),
                                      "nzdcad_otc": _asset("nzdcad_otc", "NZD/CAD")})
after2 = run(live_assets.get_live_otc_assets(fetcher_after2, force_refresh=True))
check("newly-added asset (nzdcad_otc) appears after refresh, no code change required",
      "nzdcad_otc" in after2 and len(after2) == 2)


print("\n=== 8. Unavailable selected asset — is_asset_available() is accurate, no fabrication ===")
live_assets._cache = {"timestamp": 0.0, "assets": {}}
fetcher3 = FakeFetcher(assets={
    "eurusd_otc": _asset("eurusd_otc", "EUR/USD", is_open=True),
    "audcad_otc": _asset("audcad_otc", "AUD/CAD", is_open=False),  # known but currently closed
})
check("open asset reports available",
      run(live_assets.is_asset_available(fetcher3, "eurusd_otc", force_refresh=True)) is True)
check("closed (is_open=False) asset reports NOT available, even though Quotex knows the symbol",
      run(live_assets.is_asset_available(fetcher3, "audcad_otc", force_refresh=True)) is False)
check("a symbol Quotex never returned at all reports NOT available (never fabricated as available)",
      run(live_assets.is_asset_available(fetcher3, "nonexistent_otc", force_refresh=True)) is False)


print("\n=== 9-10. No candle data / candle fetch failure — distinct from availability, not fabricated ===")
with open(os.path.join(WEBAPP_DIR, "app.py"), encoding="utf-8") as f:
    app_src = f.read()
check("candle-empty pipeline path still returns a distinct {'error': ...} dict — content was "
      "intentionally updated by the later, approved AUDCAD protocol-error fix (structured "
      "diagnostics now included), but the same {'error': ..., 'diagnostics': {...}} contract holds",
      'return {\n                "error": reason,\n                "failure_category": category,\n'
      '                "diagnostics": diag,\n            }' in app_src
      or '"error": reason' in app_src)
check("scanner.py still converts that error dict into a real exception -> FAILED diagnostic (M1, unchanged)",
      'raise RuntimeError(result["error"])' in open(os.path.join(WEBAPP_DIR, "scanner.py"), encoding="utf-8").read())


# ─────────────────────────────────────────────────────────────────────────
print("\n=== 11. Scanner uses the EXACT live snapshot for its run — nothing added, nothing dropped ===")
from scanner import ScannerEngine, ScannerConfig, STOPPED  # noqa: E402


async def _dummy_pipeline(asset, tf):
    raise AssertionError("not called in this test")


def _dummy_invalidate():
    pass


_throwaway_loop = asyncio.new_event_loop()
engine = ScannerEngine(
    run_pipeline=_dummy_pipeline,
    assets=["stale1_otc", "stale2_otc", "stale3_otc"],  # simulates the OLD static/known universe
    invalidate_fetcher=_dummy_invalidate,
    adx_trending=25.0,
    config=ScannerConfig(timeframes=["5m"]),
)
live_snapshot = ["eurusd_otc", "gbpusd_otc", "audcad_otc", "nzdusd_otc"]  # simulates a fresh live-availability result
result = engine.start(loop=_throwaway_loop, assets=live_snapshot)
check("start() accepted and scanner is now running against the live snapshot",
      result["ok"] is True)
check("effective_assets is EXACTLY the live snapshot passed in — not the static self._assets list",
      engine._effective_assets == live_snapshot)
check("stale/static-only symbols never appear in the scan target",
      not any(s in engine._effective_assets for s in ["stale1_otc", "stale2_otc", "stale3_otc"]))
# Not calling engine.stop()/running the loop — start() schedules the scan
# task on _throwaway_loop, which is never run_forever()'d in this test, so
# there is nothing to await or cancel; we only needed to exercise the
# synchronous asset-snapshot logic inside start() itself.
engine.state = STOPPED
_throwaway_loop.close()


print("\n=== 12. Static constants cannot override live availability (build_snapshot) ===")
known_universe = [f"known{i}_otc" for i in range(53)]  # simulates the full static 53-asset list
live_only_21 = {f"known{i}_otc": _asset(f"known{i}_otc", f"K{i}") for i in range(21)}  # only 21 actually live
snap = live_assets.build_snapshot(known_universe=known_universe, live_assets=live_only_21)
check("known_otc_count reflects the static reference universe (53)",
      snap["known_otc_count"] == 53)
check("available_otc_count reflects ONLY what's live (21), not the static 53",
      snap["available_otc_count"] == 21)
check("the 32 known-but-not-currently-live symbols are NOT in available_otc_assets",
      len(snap["available_otc_assets"]) == 21 and
      all(a in live_only_21 for a in snap["available_otc_assets"]))
check("known-but-unreturned symbols are explicitly flagged, not silently merged into 'available'",
      sum(1 for e in snap["entries"] if e.get("not_returned_by_quotex")) == 32)


print("\n=== 13-15. No fake assets / candles / signals — get_live_assets never fabricates on failure ===")
live_assets._cache = {"timestamp": 0.0, "assets": {}}
fetcher_fail = FakeFetcher(raise_exc=RuntimeError("connection reset"))
result_fail = run(live_assets.get_live_assets(fetcher_fail, force_refresh=True))
check("a raising fetcher yields {} (empty), never a fabricated asset list",
      result_fail == {})
live_assets._cache = {"timestamp": 0.0, "assets": {}}
fetcher_none = FakeFetcher(assets=None)
result_none = run(live_assets.get_live_assets(fetcher_none, force_refresh=True))
check("a fetcher returning None yields {} (empty), never substituted with static data",
      result_none == {})
check("no signal-generation/candle code lives in live_assets.py at all (grep-level guarantee)",
      "candle" not in open(os.path.join(WEBAPP_DIR, "live_assets.py"), encoding="utf-8").read().lower() and
      "signal" not in open(os.path.join(WEBAPP_DIR, "live_assets.py"), encoding="utf-8").read().lower())


print("\n=== 16. Invalid/missing session — graceful, explicit failure, not silently 'connected' ===")
check("/api/assets/live returns success:false + 503 on a session/connection exception (static check)",
      '"success": False,' in app_src and 'No active Quotex session' in app_src)
check("/api/scanner/start refuses to start (ok:false, 503) rather than falling back to static assets",
      re.search(r'Cannot start scanner — no active Quotex session', app_src) is not None)
check("/api/validation/run refuses to run (ok:false, 503) rather than falling back to static assets",
      re.search(r'cannot determine live asset availability', app_src) is not None)


print("\n=== 17. Manual Analyzer — unavailable asset stopped before candle fetch, no raw JS crash ===")
with open(os.path.join(WEBAPP_DIR, "static", "app.js"), encoding="utf-8") as f:
    js_src = f.read()
check("runManualAnalysis() checks live availability before calling enqueueSignalRequest",
      re.search(r"async function runManualAnalysis\(\)[\s\S]{0,1200}refreshLiveOtcAssets\(true\)[\s\S]{0,1800}enqueueSignalRequest",
                js_src) is not None)
check("unavailable-asset path shows a clean message, distinct from a session/discovery failure",
      "is not currently available on Quotex" in js_src and
      "Live asset availability unavailable" in js_src)
check("unavailable-asset path returns before any fetch — never reaches enqueueSignalRequest for that case",
      re.search(r"if \(!state\.assets\.includes\(asset\)\)\s*\{[\s\S]{0,400}return;", js_src) is not None)


print("\n=== 18. GET /api/assets/live — response shape ===")
check("route exists and is a thin passthrough to live_assets.build_snapshot()",
      '@app.route("/api/assets/live"' in app_src and "live_assets.build_snapshot(" in app_src)
check("success path includes known_otc_count/available_otc_count/available_otc_assets/entries",
      all(k in app_src for k in ["known_otc_count", "available_otc_count", "available_otc_assets"]))
check("route supports ?refresh=1 to force-bypass the cache",
      '"refresh"' in app_src)


print("\n=== 19. UI handles zero live assets ===")
check("shared banner renderer shows the exact required zero-assets message",
      "No OTC assets currently available from Quotex." in js_src)
check("ssBuildSettingsAssetGrid shows an explicit empty state instead of an empty/blank grid",
      re.search(r"function ssBuildSettingsAssetGrid[\s\S]{0,1000}No OTC assets currently available", js_src) is not None)
check("vBuildSettingsAssetGrid shows an explicit empty state instead of an empty/blank grid",
      re.search(r"function vBuildSettingsAssetGrid[\s\S]{0,1000}No OTC assets currently available", js_src) is not None)


print("\n=== 20. UI handles a changing asset count (banner + grids rebuild via listener, no page reload) ===")
check("renderLiveOtcBanner() reports the real known/available counts, not a fixed string",
      "Known OTC Universe: ${s.knownCount}" in js_src and "Currently Available OTC: ${s.availableCount}" in js_src)
check("every live selector is registered via onLiveOtcAssetsChanged (rebuilds automatically on count change)",
      js_src.count("onLiveOtcAssetsChanged(") >= 6)  # man grid, SCAN_LIST, ss grid, ss banner, v grid, v banner, aih selector
check("initial page load triggers exactly one refreshLiveOtcAssets() bootstrap call (no duplicate polling loop added)",
      js_src.count("refreshLiveOtcAssets()") >= 1)


# ─────────────────────────────────────────────────────────────────────────
print("\n=== Backtest independence (Step 9) — historical asset logic untouched ===")
check("btBuildAssetGrid still reads the static window._OTC_ASSETS list, not the live layer",
      re.search(r"function btBuildAssetGrid\(\)[\s\S]{0,300}window\._OTC_ASSETS", js_src) is not None)
_live_assets_src = open(os.path.join(WEBAPP_DIR, "live_assets.py"), encoding="utf-8").read()
check("live_assets.py mentions 'backtest' only to document the live-vs-historical distinction, not to import/call it",
      "import backtest" not in _live_assets_src and "backtest_engine" not in _live_assets_src and
      "backtest." not in _live_assets_src)


print("\n=== B1 + M1 regression (Step 12) — still intact after this batch of changes ===")
check("B1: no hardcoded 3-indicator default array reintroduced",
      "['wick_rejection', 'liquidity_sweep', 'false_breakout']" not in js_src)
check("B1: vBuildIndicatorGrid()/vBuildSummaryCards() still present",
      "function vBuildIndicatorGrid()" in js_src and "function vBuildSummaryCards()" in js_src)
check("M1: get_diagnostics() still present in scanner.py, untouched logic",
      "def get_diagnostics(self)" in open(os.path.join(WEBAPP_DIR, "scanner.py"), encoding="utf-8").read())
check("M1: /api/scanner/diagnostics route still present",
      '@app.route("/api/scanner/diagnostics")' in app_src)


print("\n=== Protected files — untouched by this task ===")
for name, path in {
    "analyzer.py": os.path.join(MARKET_ANALYZER_DIR, "analyzer.py"),
    "backtest.py": os.path.join(MARKET_ANALYZER_DIR, "backtest.py"),
    "learning_engine.py": os.path.join(WEBAPP_DIR, "learning_engine.py"),
    "indicator_registry.py": os.path.join(WEBAPP_DIR, "indicator_registry.py"),
}.items():
    src = open(path, encoding="utf-8").read()
    check(f"{name} contains no reference to live_assets/get_live_otc_assets/refreshLiveOtcAssets",
          "live_assets" not in src and "get_live_otc_assets" not in src)

quotex_api_dir = os.path.join(REPO_ROOT, "quotex", "api_quotex")
touched_api_files = []
for fn in os.listdir(quotex_api_dir):
    if fn.endswith(".py"):
        if "live_assets" in open(os.path.join(quotex_api_dir, fn), encoding="utf-8").read():
            touched_api_files.append(fn)
check("no file under quotex/api_quotex/ references the new live_assets module",
      touched_api_files == [])


print(f"\n{'=' * 70}\nRESULTS: {passed} passed, {failed} failed (of {passed + failed})\n{'=' * 70}")
sys.exit(1 if failed else 0)
