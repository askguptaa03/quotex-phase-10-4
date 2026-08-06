# Release Notes

## Phase 8.1 – 8.3 — Smart Scanner: Settings, User Interface, and Advanced Controls

**The background Scanner (which continuously ranks every OTC asset by
signal quality) now has a real, dedicated page in the app — Settings,
live status, and ranked results, all in one place.**

### New: Smart Scanner page
A new "Smart Scanner" tab (separate from the older "Auto Scanner" tab,
which still works exactly as before) lets you:
- **Configure** which assets and timeframes it scans, the minimum Filter
  Score a signal must clear to show up, how many top signals to keep,
  and how often it scans — loaded automatically from your saved
  Settings, with Save / Reload / Reset-to-defaults buttons. Changing
  these never interrupts a scan already in progress — they take effect
  the next time you press Start.
- **Watch it run**: state (Running/Paused/Stopped), current asset and
  timeframe, percent complete, elapsed time, an ETA, assets completed
  out of the total, current scan cycle, and time of the last scan.
- **Control it**: Start / Pause / Resume / Stop, exactly mirroring the
  same safe lifecycle the backend has always enforced — it never starts
  on its own, only one scan runs at a time, and only your button press
  starts it.
- **See ranked results**: every qualifying asset with its rank, timeframe,
  direction, confidence, Filter Score, which filters passed/failed,
  payout, and how fresh the result is — sorted by Filter Score, then
  confidence, then payout, then freshness (a real bug in that last
  tiebreaker, found during this work, was fixed so the freshest result
  among ties now actually shows first).
- The page only refreshes itself while a scan is actually running, and
  stops the moment you leave the tab or the scan stops — no wasted
  background activity.

### Unchanged (by design)
The confluence engine (still exactly 10 voting factors), the Dynamic
Weight algorithm, all indicator math, and the Quotex connection itself
are completely untouched by this work. The 3 newer indicators (Wick
Rejection, Liquidity Sweep, False Breakout) still don't affect signals —
that remains a separate, deliberately deferred decision.

### Known limitations
- As with every prior release, this was verified end-to-end against the
  app's real routing/logic in a sandbox with no live network access —
  not against a real Quotex connection. Try it in your real environment
  before relying on it for anything time-sensitive.
- A first-pass audit toward eventually validating the 3 newer indicators
  found that no existing backtest function can actually measure their
  accuracy yet (the backtest engine only vectorizes the original 10) —
  that's flagged as follow-up work, not something this release attempted.

## Phase 7.4

**Settings, Backtest, Indicators, and Quotex Session are now fully usable
from the app — no code editing or redeploy required for day-to-day
tuning.**

### New: Settings page
Edit refresh intervals, scanner pacing, and filter thresholds (ADX/ATR/
payout/confidence/filter-score minimums) directly from the app. Save,
reset to defaults, create/restore backups (last 10 kept automatically),
and export/import your settings as a file.

### New: Backtest page
Run a historical accuracy backtest against real candle data for any OTC
asset (or all of them), choosing a timeframe and candle count (500 up to
5000, expanded this release to include 1500 and 3000 as well). Watch live
progress with an ETA, then review suggested indicator weights and either
leave them for reference or apply them with one tap — a safety check
blocks applying weights from a run that didn't gather enough data first,
and a backup is taken automatically before anything changes.

### New: Indicators page
See every indicator this app knows about — 10 that actively vote on
signals, plus 3 newer ones (Wick Rejection, Liquidity Sweep, False
Breakout) that are tracked and displayed but don't affect signals yet.
Toggle any of the 10 active ones on or off, and see their current weight,
live-computed dynamic weight, and backtested accuracy once you've run a
backtest.

### New: Quotex Session page
Paste your session SSID directly in the app instead of editing files by
hand, and validate the connection with one tap.

### Fixed: Auto Scanner no longer starts itself
Previously, opening the app (or just switching tabs) could silently start
the background scanner without you asking it to. It now only starts when
you explicitly turn on "Enable Auto Scanner," and it's always off again
the next time you open the app.

### Fixed: two internal bugs found while testing this release
- A rare rounding issue could leave indicator weights summing to 99.9999%
  instead of exactly 100% after disabling one indicator. Now always
  exact.
- Starting a backtest with invalid input (bad candle count, unknown
  asset) was returning the wrong type of error response internally; now
  correctly distinguished from "a backtest is already running."

### Unchanged (by design)
The core signal engine — the confluence vote, confidence scoring, and
Filter Score — is untouched this release. Nothing about how BUY/SELL/WAIT
signals are generated has changed. Settings only let you *tune* things
that were already configurable in code (thresholds, which indicators
count, how much weight each gets) — they don't change the underlying
logic itself.

### Known limitations
- This release's backend work (Settings/Backtest/Session routes) has been
  tested end-to-end against the app's real routing and validation logic,
  but not against a live Quotex connection — the development environment
  has no network access. Session validation and live backtests should be
  tried in your real environment before relying on them.
- The 3 newer indicators shown on the Indicators page don't affect
  signals yet — that's intentional, pending a separate decision.
