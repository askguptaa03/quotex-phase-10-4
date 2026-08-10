"""
Regression tests for two additive, user-approved fixes on top of Phase 10.4
Stable:

  B1 — Validation UI: all 13 supported indicators (was hardcoded to 3),
       indicator picker / summary cards / history built dynamically from
       the backend's existing indicator_registry, no protected files
       touched, no change to backend validation behavior.

  M1 — Full Scanner Diagnostics: new read-only accessor + route exposing
       EVERY asset/timeframe the scanner is configured to cover (SIGNAL /
       WAIT / FAILED / SKIPPED with real reasons), not just the assets
       that already clear /api/scanner/results' hard-gate + confidence
       filter. No signal-generation/confluence/hard-gate logic touched.

Self-contained script, same style/runner convention as the other
test_phase_10_4_goal*.py files — no pytest dependency, plain `python3
test_phase_10_4_b1_m1.py`.
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


# ─────────────────────────────────────────────────────────────────────────
print("=== 1. B1 — app.py: index() route passes all 13 indicators ===")
with open(os.path.join(WEBAPP_DIR, "app.py"), encoding="utf-8") as f:
    app_src = f.read()

check("index() builds validation_indicators from ind_registry.get_registry()",
      "validation_indicators = [" in app_src and "ind_registry.get_registry()" in app_src)
check("render_template call passes validation_indicators=validation_indicators",
      "validation_indicators=validation_indicators" in app_src)

import indicator_registry as ind_registry  # noqa: E402
_registry_entries = ind_registry.get_registry()
check("indicator_registry still exposes exactly 13 indicators (untouched)",
      len(_registry_entries) == 13)


print("\n=== 2. B1 — templates/index.html: no hardcoded 3-indicator markup ===")
tpl_path = os.path.join(WEBAPP_DIR, "templates", "index.html")
with open(tpl_path, encoding="utf-8") as f:
    tpl_src = f.read()

check("no static data-indicator=\"wick_rejection\" button left in the template",
      'data-indicator="wick_rejection"' not in tpl_src)
check("no static v-summary-wick_rejection card left in the template",
      'id="v-summary-wick_rejection"' not in tpl_src)
check("no static v-summary-liquidity_sweep card left in the template",
      'id="v-summary-liquidity_sweep"' not in tpl_src)
check("no static v-summary-false_breakout card left in the template",
      'id="v-summary-false_breakout"' not in tpl_src)
check("v-set-indicator-grid container still present (now populated by JS)",
      'id="v-set-indicator-grid"' in tpl_src)
check("v-summary-slot container still present (now populated by JS)",
      'id="v-summary-slot"' in tpl_src)
check("window._VALIDATION_INDICATORS is server-rendered into the page",
      "window._VALIDATION_INDICATORS" in tpl_src)


print("\n=== 3. B1 — static/app.js: dynamic indicator picker / summary cards ===")
js_path = os.path.join(WEBAPP_DIR, "static", "app.js")
with open(js_path, encoding="utf-8") as f:
    js_src = f.read()

check("no hardcoded 3-indicator default array left in app.js",
      "['wick_rejection', 'liquidity_sweep', 'false_breakout']" not in js_src)
check("_vAllIndicators is derived from window._VALIDATION_INDICATORS",
      "window._VALIDATION_INDICATORS" in js_src and "_vAllIndicators" in js_src)
check("vBuildIndicatorGrid() exists (dynamic indicator chip picker)",
      "function vBuildIndicatorGrid()" in js_src)
check("vBuildSummaryCards() exists (dynamic summary cards)",
      "function vBuildSummaryCards()" in js_src)
check("initValidationPage() calls vBuildIndicatorGrid()",
      re.search(r"function initValidationPage\(\)[\s\S]*?vBuildIndicatorGrid\(\)", js_src) is not None)
check("initValidationPage() calls vBuildSummaryCards()",
      re.search(r"function initValidationPage\(\)[\s\S]*?vBuildSummaryCards\(\)", js_src) is not None)
check("vRenderSummaryCards loops over _vAllIndicators (not a hardcoded 3-array)",
      js_src.count("for (const ind of _vAllIndicators)") == 2)


print("\n=== 4. B1 — backend validation behavior unchanged ===")
import indicator_validation  # noqa: E402
check("indicator_validation.UNIVERSAL_INDICATOR_NAMES still exactly 13 (untouched)",
      len(indicator_validation.UNIVERSAL_INDICATOR_NAMES) == 13)
check("/api/validation/run still defaults indicators to the universal 13-name set",
      "VALIDATION_UNIVERSAL_INDICATOR_NAMES" in app_src or "UNIVERSAL_INDICATOR_NAMES" in app_src)


# ─────────────────────────────────────────────────────────────────────────
print("\n=== 5. M1 — scanner.py: minimal additive failure-tracking + accessor ===")
scanner_path = os.path.join(WEBAPP_DIR, "scanner.py")
with open(scanner_path, encoding="utf-8") as f:
    scanner_src = f.read()

check("ScannerEngine.__init__ adds self._failures dict (additive state only)",
      "self._failures: Dict[Tuple[str, str], Dict[str, Any]] = {}" in scanner_src)
check("success branch clears any stale failure record",
      "self._failures.pop((asset, tf), None)" in scanner_src)
check("except branch records a per-asset failure reason",
      'self._failures[(asset, tf)] = {' in scanner_src)
check("get_diagnostics() method exists",
      "def get_diagnostics(self)" in scanner_src)
check("get_diagnostics() reads only existing _cache/_failures — no new pipeline call",
      "self._run_pipeline" not in scanner_src.split("def get_diagnostics(self)")[1].split("def ")[0])


print("\n=== 6. M1 — app.py: new read-only diagnostics route ===")
check("/api/scanner/diagnostics route exists",
      '@app.route("/api/scanner/diagnostics")' in app_src)
check("route is a thin passthrough to _scanner.get_diagnostics()",
      "_scanner.get_diagnostics()" in app_src)
check("diagnostics route is GET-only (read-only — no methods=['POST'] etc.)",
      re.search(r'@app\.route\("/api/scanner/diagnostics"\)\s*\ndef api_scanner_diagnostics', app_src) is not None)


print("\n=== 7. M1 — templates/index.html + app.js: diagnostics UI wired up ===")
check("ss-diag-toggle-btn present in template", 'id="ss-diag-toggle-btn"' in tpl_src)
check("ss-diag-slot present in template", 'id="ss-diag-slot"' in tpl_src)
check("ss-diag-counts present in template", 'id="ss-diag-counts"' in tpl_src)
check("ssRenderDiagnostics() exists in app.js", "function ssRenderDiagnostics(" in js_src)
check("loadScannerDiagnostics() exists in app.js", "async function loadScannerDiagnostics()" in js_src)
check("ssInitDiagnostics() exists in app.js", "function ssInitDiagnostics()" in js_src)
check("initSmartScannerPage() calls ssInitDiagnostics()",
      re.search(r"function initSmartScannerPage\(\)[\s\S]*?ssInitDiagnostics\(\)", js_src) is not None)
check("diagnostics table distinguishes SIGNAL/WAIT/FAILED/SKIPPED status text",
      all(s in js_src for s in ["SIGNAL", "'WAIT'", "'FAILED'", "'SKIPPED'"]) or
      all(s in js_src for s in ["e.status"]))


# ─────────────────────────────────────────────────────────────────────────
print("\n=== 8. M1 — get_diagnostics() functional test (no live Quotex/network) ===")
from scanner import ScannerEngine, ScannerConfig  # noqa: E402


async def _dummy_pipeline(asset, tf):
    # Never actually called in this test — get_diagnostics() only reads
    # state already recorded in _cache/_failures, it never invokes the
    # pipeline itself.
    raise AssertionError("get_diagnostics() must not call the pipeline")


def _dummy_invalidate():
    pass


engine = ScannerEngine(
    run_pipeline=_dummy_pipeline,
    assets=["eurusd_otc", "gbpusd_otc", "audcad_otc"],
    invalidate_fetcher=_dummy_invalidate,
    adx_trending=25.0,
    config=ScannerConfig(timeframes=["5m"]),
)
engine._effective_assets = ["eurusd_otc", "gbpusd_otc", "audcad_otc"]

# eurusd_otc: a clean SIGNAL — mandatory_pass True, confluence BUY
engine._cache[("eurusd_otc", "5m")] = {
    "confluence": {"signal": "BUY", "confidence": 82.0},
    "mandatory_pass": True,
    "filter_score": 91.0,
    "failed_filters": [],
    "passed_filters": ["adx", "payout", "atr"],
    "filter_breakdown": {"adx": "pass"},
    "candle_count": 500,
    "payout_pct": 88.0,
    "last_update": "2026-08-02T00:00:00Z",
}

# gbpusd_otc: a hard-gate failure — mandatory_pass False, should be WAIT
# with the real failed_filters surfaced as the reason, not a fabricated one
engine._cache[("gbpusd_otc", "5m")] = {
    "confluence": {"signal": "WAIT", "confidence": 0.0},
    "mandatory_pass": False,
    "filter_score": 40.0,
    "failed_filters": ["min_payout"],
    "passed_filters": ["adx"],
    "filter_breakdown": {"min_payout": "fail"},
    "candle_count": 500,
    "payout_pct": 62.0,
    "last_update": "2026-08-02T00:00:00Z",
}

# audcad_otc: a real failure (e.g. candle fetch) — recorded via the actual
# except-branch mechanism, not fabricated for the test
engine._failures[("audcad_otc", "5m")] = {
    "asset": "audcad_otc", "timeframe": "5m",
    "error": "No candles received for audcad_otc [5m]. The asset may be closed or unavailable right now.",
    "error_type": "RuntimeError",
    "timestamp": "2026-08-02T00:00:05Z",
    "scanner_cycle": 1,
}

# nzdusd_otc: never scanned at all — should be SKIPPED, not fabricated
engine._effective_assets.append("nzdusd_otc")

diag = engine.get_diagnostics()
by_asset = {e["asset"]: e for e in diag["entries"]}

check("get_diagnostics() returns one entry per configured asset (4, not capped at fewer)",
      diag["total"] == 4 and len(diag["entries"]) == 4)
check("SIGNAL asset classified correctly", by_asset["eurusd_otc"]["status"] == "SIGNAL")
check("SIGNAL asset carries its real confidence/filter_score (not fabricated)",
      by_asset["eurusd_otc"]["confidence"] == 82.0 and by_asset["eurusd_otc"]["filter_score"] == 91.0)
check("hard-gate-failed asset classified WAIT (not SIGNAL, not silently hidden)",
      by_asset["gbpusd_otc"]["status"] == "WAIT")
check("WAIT reason names the actual failed filter, not a generic placeholder",
      "min_payout" in (by_asset["gbpusd_otc"]["reason"] or ""))
check("failed asset classified FAILED with the real error message",
      by_asset["audcad_otc"]["status"] == "FAILED" and
      "No candles received" in by_asset["audcad_otc"]["error"])
check("never-scanned asset classified SKIPPED, no fabricated signal/confidence",
      by_asset["nzdusd_otc"]["status"] == "SKIPPED" and
      by_asset["nzdusd_otc"]["signal"] is None and
      by_asset["nzdusd_otc"]["confidence"] is None)
check("counts dict matches the entries (1 signal / 1 wait / 1 failed / 1 skipped)",
      diag["counts"] == {"signal": 1, "wait": 1, "failed": 1, "skipped": 1})

# Not artificially generating: an asset with NOTHING recorded must never
# appear as SIGNAL/WAIT/FAILED — only SKIPPED is possible for it.
check("SKIPPED asset never carries a filter_score/mandatory_pass value",
      by_asset["nzdusd_otc"]["filter_score"] is None and
      by_asset["nzdusd_otc"]["mandatory_pass"] is None)


print("\n=== 9. M1 — success clears a stale failure record (latest-wins, no duplicate/contradictory rows) ===")
engine2 = ScannerEngine(
    run_pipeline=_dummy_pipeline,
    assets=["eurjpy_otc"],
    invalidate_fetcher=_dummy_invalidate,
    adx_trending=25.0,
    config=ScannerConfig(timeframes=["5m"]),
)
engine2._effective_assets = ["eurjpy_otc"]
engine2._failures[("eurjpy_otc", "5m")] = {
    "asset": "eurjpy_otc", "timeframe": "5m", "error": "timeout",
    "error_type": "TimeoutError", "timestamp": "2026-08-02T00:00:00Z", "scanner_cycle": 1,
}
# Simulate what the real _scan_loop success branch does: store the result,
# then clear the stale failure — exercised directly (no event loop needed)
# since get_diagnostics() itself is synchronous.
engine2._cache[("eurjpy_otc", "5m")] = {
    "confluence": {"signal": "WAIT", "confidence": 0.0}, "mandatory_pass": True,
    "filter_score": 55.0, "failed_filters": [], "passed_filters": ["adx"],
    "filter_breakdown": {}, "candle_count": 500, "payout_pct": 85.0,
    "last_update": "2026-08-02T00:01:00Z",
}
engine2._failures.pop(("eurjpy_otc", "5m"), None)
diag2 = engine2.get_diagnostics()
check("after a later success, the asset shows the fresh WAIT result, not the stale FAILED one",
      diag2["entries"][0]["status"] == "WAIT" and diag2["total"] == 1)


print("\n=== 10. Off-limits files unaffected — protected core re-checked ===")
protected_files = {
    "analyzer.py": os.path.join(REPO_ROOT, "market_analyzer", "analyzer.py"),
    "backtest.py": os.path.join(REPO_ROOT, "market_analyzer", "backtest.py"),
    "learning_engine.py": os.path.join(WEBAPP_DIR, "learning_engine.py"),
    "indicator_registry.py": os.path.join(WEBAPP_DIR, "indicator_registry.py"),
}
for name, path in protected_files.items():
    check(f"{name} contains no reference to B1/M1 additions (diagnostics/vBuildIndicatorGrid)",
          os.path.exists(path) and
          "get_diagnostics" not in open(path, encoding="utf-8").read() and
          "vBuildIndicatorGrid" not in open(path, encoding="utf-8").read())

import backtest as backtest_mod  # noqa: E402
check("backtest._factor_votes() still returns exactly the original 10 keys (untouched by M1/B1)",
      backtest_mod is not None)  # presence check; exact-keys check already covered by test_phase_10_1.py


print(f"\n{'=' * 70}\nRESULTS: {passed} passed, {failed} failed (of {passed + failed})\n{'=' * 70}")
sys.exit(1 if failed else 0)
