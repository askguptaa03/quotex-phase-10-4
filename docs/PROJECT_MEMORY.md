# PROJECT MEMORY — Design Decisions & Rationale

This is the "why" document. Read this before changing anything.

## Why manual trading only, and why auto-trading is intentionally excluded
Every module's docstring states "analysis only — never places an order."
This was a constraint from Part 1 of the very first master prompt and has
been re-affirmed and re-verified at every subsequent phase. No code path
anywhere in this project calls a trade-placement API. This is a hard,
non-negotiable design boundary — any future task that would place an order
is out of scope for this codebase entirely.

## Why the project follows "audit first, then implement" for every phase
Established from Phase 1 onward: large or risky changes are preceded by a
tracing/audit step (who consumes this field, what breaks if I change it),
presented for approval, THEN implemented with regression tests. This caught
real bugs before they shipped (e.g., the OBV/Step-4 `_FACTOR_LABELS` gap,
the Phase 7 scanner ranking bug, the Phase 7.2 `evaluate_apply_conditions()`
gap) — the pattern has proven itself and should be continued.

## Why certain indicators were chosen
The original 4-indicator set (EMA/ADX/ATR/RSI/BB/OBV per the master prompt)
grew organically: OBV was added in Step 4 after being found "calculated but
never used" in an audit. Candlestick patterns were expanded from 4 to 9 in
Phase 5 because the original spec explicitly asked for the missing 5.
Support/Resistance was upgraded from a bare min/max to a full zone-clustering
engine in Phase 6 for the same reason. The 3 newest indicators (Wick
Rejection, Liquidity Sweep, False Breakout) were requested in Phase 7.3 to
round out OTC-specific price-action patterns not covered by classical TA.

## Why Scanner works this way (sequential, single-flight)
The existing app has exactly ONE shared Quotex connection
(`_shared_fetcher`), serialized through one background event loop
(`_BG_LOOP`) — this was true before this project began and was treated as
an immovable constraint. A concurrent scanner would either need a second
Quotex connection (risky, unproven, could violate rate limits) or fight the
existing serialization. The chosen design — one more coroutine on the SAME
loop — gets mutual exclusion for free, at the cost of scan-cycle time being
proportional to asset count (measured/estimated ~80-130s for 53 assets at
one timeframe). This tradeoff was made explicitly and documented, not
accidental.

## Why Backtest Engine is a separate module, not merged into Scanner
Explicit instruction, repeated across multiple messages: "Do NOT modify
Smart Scanner architecture." Even though the two engines share an almost
identical lifecycle pattern (STOPPED/RUNNING/PAUSED, pause/resume via
`asyncio.Event`, submit-onto-shared-loop), duplicating that pattern into a
second file was judged safer than risking any regression to the
already-tested, already-shipped Scanner.

## Why Settings are persistent (file-backed, not in-memory)
`ScannerConfig` (in-memory, scanner.py) was the first config surface built
and resets on every process restart. Phase 7.2 explicitly required
something that survives a restart — hence `settings_store.py`'s JSON-file
design, chosen to mirror the already-established `session.json` pattern
(same directory conventions, same atomic-write-via-tempfile-and-rename
safety pattern used nowhere else in this specific form until now, but
consistent with how a production trading tool should never risk a torn
write corrupting its config).

## Why Dynamic Weights exist
Static equal weights (10.0 x 10 factors) are a reasonable prior with zero
data. `backtest_factor_accuracy()` + `compute_dynamic_weights()` let real
historical performance override that prior — but ONLY when there's enough
data to trust it (`MIN_SIGNALS_REQUIRED = 20`, unified in Step 3 after
discovering two inconsistent thresholds were fighting each other). Weights
still always sum to exactly 100 — verified via fuzz testing at every phase
that touched the weight system.

## Why Filter Score changed (v1 -> v2, binary -> graded)
**v1 (Phase 7):** any mandatory gate failure forced `filter_score` to 0.
This was later found (Phase 7.1, user-reported) to make almost every result
land at either 0 or 93-100 — the middle of the scale was structurally
unreachable, making ranking uninformative.
**v2 (Phase 7.1):** each of the 7 criteria now grades independently on its
own band (e.g. ADX 20-25 -> 5pts, 25-30 -> 10pts, etc.), and `filter_score`
is ALWAYS the sum of graded points — it no longer collapses to 0. The
original binary hard-gate semantics were preserved in a SEPARATE new field,
`mandatory_pass`, which is what the Scanner uses to decide visibility.
**Key insight to preserve:** `filter_score` = quality (informational,
always graded); `mandatory_pass` = visibility gate (binary, unchanged
semantics). Do not re-merge these two concepts.

## Why the backtest Filter Score report has sparse middle buckets
Even after the v2 graded-scoring fix, the BACKTEST version (5 criteria
only — MTF and Payout excluded) still requires all 4 backtestable
mandatory gates (EMA/ADX/ATR/SR) to individually pass before a bar counts
as a "trade" at all. The mathematical floor for a passing bar is ~50 points
(weakest-passing grade on all 4 dimensions), so the `0-20`/`20-40` buckets
are structurally near-empty for genuine trades — this is a known,
documented, and accepted consequence of keeping trade-eligibility tied to
the mandatory gates, not a residual bug from the v1->v2 fix.

## Why MTF and Payout can never be backtested
- **Multi-Timeframe:** would require fetching and analyzing a SECOND
  historical timeframe in lockstep with the primary one, bar-by-bar. Not
  built — would be a substantial new data-plumbing effort, not a quick fix.
- **Payout:** Quotex's API only exposes CURRENT payout, never historical.
  There is no way to backtest this, ever, regardless of engineering effort.
This is why `backtest_filter_score_report()`'s docstring and return value
both explicitly flag these two exclusions — never silently omit this
caveat in any future report or documentation.

## Why the confluence engine requires >=3 agreeing factors
Pre-existing design (before this project's involvement) — preserved
throughout every phase as a stability/anti-noise measure: a single strong
factor alone cannot produce a signal. This is also why "helper" indicators
(CCI, Stochastic, Round Number, Mean Reversion, Exhaustion) are safe to
add without a separate enforcement mechanism — they mathematically cannot
generate BUY/SELL alone, since the vote-counting gate already requires
several factors to align.

## Why reliability/strength scores are geometry-derived, not fixed lookup tables
Explicit instruction from Phase 6 onward: "Do NOT assign fixed reliability
scores based only on pattern names... calculate reliability from
measurable candle geometry." This was to leave room for future
backtest-calibration (candidate follow-up work, never done) rather than
hardcoding subjective "hammer = 70% reliable" style tables that can't be
empirically validated or improved.

## Why the sandbox environment matters for every result reported
This entire project has been developed with **no network access**. Every
performance number, every "tested" claim, is against synthetic data
generated in-process. Nothing has ever touched a live Quotex connection or
the real Flask HTTP layer. This has been stated at the end of nearly every
phase's report and must continue to be stated — do not let this caveat
silently drop from future summaries.
