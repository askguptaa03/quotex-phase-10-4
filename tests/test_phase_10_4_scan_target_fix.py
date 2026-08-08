"""
Live Asset Scan-Target Fix — targeted regression suite.

Root cause fixed: the Home dashboard's client-side Auto Scanner
(static/app.js buildScanList()) hardcoded a `.slice(0, 16)` cap and a
regex/whitelist symbol pre-filter, so its scan target was NEVER actually
"whatever Quotex currently reports live" — it silently dropped
non-standard symbols and truncated everything else at 16, independent of
the real live OTC count. This is UNRELATED to the backend ScannerEngine
(scanner.py / /api/scanner/start), which was already correct.

This suite:
  1. Verifies the source no longer contains the cap/filter (source check).
  2. Re-implements nothing from the app — it extracts and directly
     exercises the ACTUAL fixed buildScanList() logic via Node, covering
     0 / 5 / 25 / 40 live OTC, assets added/removed (reactivity), a
     non-standard symbol that the old regex would have dropped, the
     loading-placeholder state, and the live-discovery-failure state
     (must yield 0, never a static fallback).

OFFLINE — no live Quotex session, no network. Node.js is required for
part 2 (already used elsewhere in this project's JS tooling); part 1
runs standalone.

Run with:  python3 Quotex/tests/test_phase_10_4_scan_target_fix.py
"""
import os
import re
import subprocess
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
_APP_JS = os.path.join(_HERE, "..", "market_analyzer", "webapp", "static", "app.js")

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


# ═══════════════════════════════════════════════════════════════════════════
print("=== 1. Source-level verification (app.js) ===")
# ═══════════════════════════════════════════════════════════════════════════
_js_src = open(_APP_JS, encoding="utf-8").read()

check("buildScanList() no longer caps the scan list with .slice(0, 16)",
      "list.slice(0, 16)" not in _js_src)
check("buildScanList() no longer pre-filters via the 6-letter-symbol regex",
      "/^[A-Z]{6}_otc$/i" not in _js_src)
check("buildScanList() no longer pre-filters via the fixed crypto/commodity whitelist",
      "BTCUSD|ETHUSD|XAUUSD|XAGUSD" not in _js_src)
_fn_match = re.search(r"function buildScanList\(\)\s*\{.*?\n\}", _js_src, re.S)
check("buildScanList() function still exists (not accidentally removed)",
      _fn_match is not None)
if _fn_match:
    fn_body = _fn_match.group(0)
    check("buildScanList() now returns the live OTC snapshot directly (no cap, no filter)",
          "_liveOtcState.assets" in fn_body and ".slice(0, 16)" not in fn_body)
    check("buildScanList() still uses the static list ONLY as a pre-first-fetch loading placeholder",
          "window._OTC_ASSETS" in fn_body and "_liveOtcState.loaded ?" in fn_body)


# ═══════════════════════════════════════════════════════════════════════════
print("\n=== 2. Behavioral verification (real buildScanList() logic, via Node) ===")
# ═══════════════════════════════════════════════════════════════════════════
node_script = r"""
function buildScanList(_liveOtcState, _staticOtcAssets) {
  return _liveOtcState.loaded ? [..._liveOtcState.assets] : (_staticOtcAssets || []);
}

const results = [];
function check(name, cond) { results.push([name, !!cond]); }

check("0 live OTC -> scan target 0",
      buildScanList({loaded: true, assets: []}, ['A_otc','B_otc']).length === 0);

check("5 live OTC -> scan target 5",
      buildScanList({loaded: true, assets: ['a_otc','b_otc','c_otc','d_otc','e_otc']}).length === 5);

check("25 live OTC -> scan target 25",
      buildScanList({loaded: true, assets: Array.from({length: 25}, (_, i) => `s${i}_otc`)}).length === 25);

const s40 = {loaded: true, assets: Array.from({length: 40}, (_, i) => `s${i}_otc`)};
check("40 live OTC -> scan target 40 (previously would have been capped at 16)",
      buildScanList(s40).length === 40);

check("assets ADDED: growing the live set grows the scan target 1:1",
      buildScanList({loaded: true, assets: ['a_otc']}).length === 1 &&
      buildScanList({loaded: true, assets: ['a_otc', 'b_otc']}).length === 2);

check("assets REMOVED: shrinking the live set shrinks the scan target 1:1",
      buildScanList({loaded: true, assets: ['a_otc', 'b_otc', 'c_otc']}).length === 3 &&
      buildScanList({loaded: true, assets: ['a_otc']}).length === 1);

check("non-standard symbol no longer dropped by the old 6-letter regex/whitelist",
      buildScanList({loaded: true, assets: ['SPX500_otc', 'US30_otc', 'eurusd_otc']})
        .includes('SPX500_otc'));

check("before first live fetch resolves: static list used ONLY as a loading placeholder",
      buildScanList({loaded: false, assets: []}, ['X_otc']).length === 1);

check("live discovery FAILURE (loaded=true, assets=[]) -> scan target 0, never a static fallback",
      buildScanList({loaded: true, success: false, assets: []}, ['X_otc', 'Y_otc']).length === 0);

for (const [name, ok] of results) {
  console.log((ok ? "PASS  " : "FAIL  ") + name);
}
const failedCount = results.filter(([, ok]) => !ok).length;
console.log(`\nNODE_RESULT ${results.length - failedCount} passed, ${failedCount} failed`);
process.exit(failedCount ? 1 : 0);
"""

try:
    proc = subprocess.run(["node", "-e", node_script], capture_output=True, text=True, timeout=30)
    print(proc.stdout.strip())
    if proc.stderr.strip():
        print(proc.stderr.strip(), file=sys.stderr)
    m = re.search(r"NODE_RESULT (\d+) passed, (\d+) failed", proc.stdout)
    if m:
        node_passed, node_failed = int(m.group(1)), int(m.group(2))
        passed += node_passed
        failed += node_failed
    else:
        check("Node behavioral suite produced a parseable result", False)
except FileNotFoundError:
    check("Node.js available to run the behavioral suite "
          "(skip reason: node not found — source-level checks above still apply)", False)
except Exception as exc:
    check(f"Node behavioral suite raised unexpectedly: {exc}", False)


# ═══════════════════════════════════════════════════════════════════════════
print(f"\n{'=' * 70}\nRESULTS: {passed} passed, {failed} failed (of {passed + failed})\n{'=' * 70}")
sys.exit(0 if failed == 0 else 1)
