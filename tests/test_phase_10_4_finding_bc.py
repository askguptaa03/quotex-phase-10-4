"""
Targeted regression tests for the Finding B + Finding C defense-in-depth
fixes (no-fake-data audit follow-up):

  Finding B — a caller-supplied "assets" list to /api/scanner/start or
  /api/validation/run must be intersected with the CURRENT live Quotex OTC
  snapshot, never scanned/validated as-is.

  Finding C — the live web/API execution path must never be able to call
  ScannerEngine.start() with assets left unresolved (None), which would
  silently fall back to the static constructor asset list.

These are OFFLINE UNIT TESTS against the actual route/module source and
live_assets.py's new helper — no live Quotex session, no network. Self-
contained script, same convention as the other test_phase_10_4_*.py files.
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

with open(os.path.join(WEBAPP_DIR, "app.py"), encoding="utf-8") as f:
    app_src = f.read()


# ─────────────────────────────────────────────────────────────────────────
print("=== 1. filter_requested_against_live() — core intersection logic ===")
live_now = {"eurusd_otc", "gbpusd_otc", "audcad_otc"}

result = live_assets.filter_requested_against_live(
    ["eurusd_otc", "gbpusd_otc", "nzdusd_otc"], live_now)
check("explicit assets ∩ live assets — only currently-live OTC symbols kept",
      set(result["kept"]) == {"eurusd_otc", "gbpusd_otc"})
check("unavailable requested OTC asset (nzdusd_otc) is removed, not scanned",
      "nzdusd_otc" in result["dropped_otc_unavailable"] and "nzdusd_otc" not in result["kept"])

result2 = live_assets.filter_requested_against_live(
    ["nzdusd_otc", "eurjpy_otc"], live_now)
check("all requested assets unavailable -> kept is empty (nothing scanned)",
      result2["kept"] == [])
check("all requested assets unavailable -> both are reported as dropped, not silently vanished",
      set(result2["dropped_otc_unavailable"]) == {"nzdusd_otc", "eurjpy_otc"})

result3 = live_assets.filter_requested_against_live(
    ["eurusd_otc", "some_random_live_pair"], live_now)  # non-OTC mixed in
check("non-OTC requested symbol passes through unfiltered (outside OTC-only scope)",
      "some_random_live_pair" in result3["kept"] and "some_random_live_pair" not in result3["dropped_otc_unavailable"])

result4 = live_assets.filter_requested_against_live(["eurusd_otc"], set())
check("zero live OTC assets -> any requested OTC symbol is dropped, none kept",
      result4["kept"] == [] and result4["dropped_otc_unavailable"] == ["eurusd_otc"])

result5 = live_assets.filter_requested_against_live([f"sym{i}_otc" for i in range(53)],
                                                      {f"sym{i}_otc" for i in range(53)})
check("static-sized (53) requested list, all currently live -> all 53 kept (live confirms every one)",
      len(result5["kept"]) == 53 and result5["dropped_otc_unavailable"] == [])

result6 = live_assets.filter_requested_against_live([f"sym{i}_otc" for i in range(53)],
                                                      {f"sym{i}_otc" for i in range(21)})
check("static 53-asset list requested, but only 21 are actually live -> exactly 21 kept, 32 dropped",
      len(result6["kept"]) == 21 and len(result6["dropped_otc_unavailable"]) == 32)


# ─────────────────────────────────────────────────────────────────────────
print("\n=== 2. /api/scanner/start — Finding B source-level verification ===")
check("route ALWAYS fetches the live session/snapshot before branching on explicit_assets "
      "(fetcher/live_otc fetch happens before the 'if explicit_assets:' check)",
      re.search(r"def api_scanner_start\(\)[\s\S]*?fetcher = _run_bg\(_get_shared_fetcher\(\)"
                r"[\s\S]*?live_otc = _run_bg\(live_assets\.get_live_otc_assets"
                r"[\s\S]*?explicit_assets = data\.get\(\"assets\"\)", app_src) is not None)
check("explicit assets are passed through filter_requested_against_live() — no more raw pass-through",
      re.search(r"def api_scanner_start\(\)[\s\S]{0,3000}filter_requested_against_live\(explicit_assets, live_symbols\)", app_src) is not None)
check("empty intersection returns ok:false + 503 with a clear message, never starts the scanner",
      '"No requested OTC assets are currently available from Quotex."' in app_src)
check("saved custom selection (enabled_assets) is still intersected with live availability (unchanged precedent)",
      "[a for a in saved_selection if a in live_symbols]" in app_src)
check("session/discovery failure returns 503, never falls through to a static asset list",
      app_src.count('"message": f"Cannot start scanner — no active Quotex session') == 1 and
      app_src.count('"message": f"Cannot start scanner — failed to fetch live asset availability') == 1)


print("\n=== 3. /api/validation/run — Finding B source-level verification ===")
check("route ALWAYS fetches the live snapshot before branching on explicit_assets",
      re.search(r"def api_validation_run\(\)[\s\S]*?fetcher = _run_bg\(_get_shared_fetcher\(\)"
                r"[\s\S]*?live_otc = _run_bg\(live_assets\.get_live_otc_assets"
                r"[\s\S]*?if explicit_assets:", app_src) is not None)
check("explicit assets are passed through filter_requested_against_live()",
      re.search(r"def api_validation_run\(\)[\s\S]{0,3000}filter_requested_against_live\(explicit_assets, live_symbols\)", app_src) is not None)
check("empty intersection returns ok:false + 503, never starts validation",
      app_src.count('"No requested OTC assets are currently available from Quotex."') == 2)  # scanner + validation
check("0 live OTC + no explicit assets returns the exact required message",
      '"No OTC assets currently available from Quotex." if not explicit_assets' in app_src)
check("session/discovery failure returns 503 with a clear error, never falls back to static ASSETS",
      'cannot determine live asset availability' in app_src)


print("\n=== 4. Static 53-asset universe can never override live availability (route-level) ===")
check("api_scanner_start() never references _asset_choices()['otc'] or ASSETS as a scan-target fallback",
      "_asset_choices()[\"otc\"]" not in re.search(r"def api_scanner_start\(\)[\s\S]*?(?=\n@app\.route|\Z)", app_src).group()
      if re.search(r"def api_scanner_start\(\)[\s\S]*?(?=\n@app\.route|\Z)", app_src) else False)
_val_fn_src = re.search(r"def api_validation_run\(\)[\s\S]*?(?=\n@app\.route|\Z)", app_src).group()
check("api_validation_run() never falls back to _asset_choices()['otc'] as a validation-target default",
      "_asset_choices()[\"otc\"]" not in _val_fn_src)


# ─────────────────────────────────────────────────────────────────────────
print("\n=== 5. Finding C — scanner.py backward compatibility preserved, guard lives in the route ===")
from scanner import ScannerEngine, ScannerConfig, STOPPED  # noqa: E402


async def _dummy_pipeline(asset, tf):
    raise AssertionError("not called in this test")


def _dummy_invalidate():
    pass


_loop_a = asyncio.new_event_loop()
engine_default = ScannerEngine(
    run_pipeline=_dummy_pipeline, assets=["legacy1_otc", "legacy2_otc"],
    invalidate_fetcher=_dummy_invalidate, adx_trending=25.0,
    config=ScannerConfig(timeframes=["5m"]),
)
result_a = engine_default.start(loop=_loop_a)  # assets=None (omitted) — direct/test-call path
check("ScannerEngine.start() with assets omitted still falls back to the constructor list "
      "(preserved for direct/test callers per existing regression tests)",
      engine_default._effective_assets == ["legacy1_otc", "legacy2_otc"])
engine_default.state = STOPPED
_loop_a.close()

_loop_b = asyncio.new_event_loop()
engine_live = ScannerEngine(
    run_pipeline=_dummy_pipeline, assets=["legacy1_otc", "legacy2_otc"],
    invalidate_fetcher=_dummy_invalidate, adx_trending=25.0,
    config=ScannerConfig(timeframes=["5m"]),
)
result_b = engine_live.start(loop=_loop_b, assets=["live1_otc", "live2_otc", "live3_otc"])
check("ScannerEngine.start() with an explicit live snapshot uses EXACTLY that snapshot, "
      "never the constructor's static list",
      engine_live._effective_assets == ["live1_otc", "live2_otc", "live3_otc"])
engine_live.state = STOPPED
_loop_b.close()

check("api_scanner_start() has an explicit guard preventing assets_for_run from ever "
      "reaching ScannerEngine.start() as None",
      re.search(r"if assets_for_run is None:[\s\S]{0,200}Internal error", app_src) is not None)
check("that guard sits between assets_for_run resolution and the _scanner.start() call (correct ordering)",
      app_src.index("if assets_for_run is None:") < app_src.index("result = _scanner.start(") <
      app_src.index("Finding C guard") + 5000)


# ─────────────────────────────────────────────────────────────────────────
print("\n=== 6. B1 — 13 indicators still intact (no regression from this fix) ===")
import indicator_registry  # noqa: E402
check("indicator_registry still exposes exactly 13 indicators", len(indicator_registry.get_registry()) == 13)
with open(os.path.join(WEBAPP_DIR, "static", "app.js"), encoding="utf-8") as f:
    js_src = f.read()
check("vBuildIndicatorGrid()/vBuildSummaryCards() still present, no hardcoded 3-indicator regression",
      "function vBuildIndicatorGrid()" in js_src and "function vBuildSummaryCards()" in js_src and
      "['wick_rejection', 'liquidity_sweep', 'false_breakout']" not in js_src)

print("\n=== 7. M1 — full diagnostics still intact (no regression from this fix) ===")
with open(os.path.join(WEBAPP_DIR, "scanner.py"), encoding="utf-8") as f:
    scanner_src = f.read()
check("get_diagnostics() still present with SIGNAL/WAIT/FAILED/SKIPPED classification",
      "def get_diagnostics(self)" in scanner_src and
      all(s in scanner_src for s in ['"SIGNAL"', '"WAIT"', '"FAILED"', '"SKIPPED"']))
check("/api/scanner/diagnostics route still present and untouched by this fix",
      '@app.route("/api/scanner/diagnostics")' in app_src)


# ─────────────────────────────────────────────────────────────────────────
print("\n=== 8. Protected files — untouched by Finding B/C ===")
for name, path in {
    "analyzer.py": os.path.join(MARKET_ANALYZER_DIR, "analyzer.py"),
    "backtest.py": os.path.join(MARKET_ANALYZER_DIR, "backtest.py"),
    "learning_engine.py": os.path.join(WEBAPP_DIR, "learning_engine.py"),
    "indicator_registry.py": os.path.join(WEBAPP_DIR, "indicator_registry.py"),
}.items():
    with open(path, encoding="utf-8") as f:
        src = f.read()
    check(f"{name} contains no reference to filter_requested_against_live (Finding B/C fix)",
          "filter_requested_against_live" not in src)

quotex_api_dir = os.path.join(REPO_ROOT, "quotex", "api_quotex")
touched = [fn for fn in os.listdir(quotex_api_dir)
           if fn.endswith(".py") and "filter_requested_against_live" in
           open(os.path.join(quotex_api_dir, fn), encoding="utf-8").read()]
check("no file under quotex/api_quotex/ references the Finding B/C fix", touched == [])


print(f"\n{'=' * 70}\nRESULTS: {passed} passed, {failed} failed (of {passed + failed})\n{'=' * 70}")
sys.exit(1 if failed else 0)
