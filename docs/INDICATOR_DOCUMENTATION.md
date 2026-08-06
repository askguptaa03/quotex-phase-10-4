# INDICATOR DOCUMENTATION

## Confluence-vote indicators (13 total as of Phase 8.6, weight ~7.69/7.72 each by default)

### RSI Divergence (`rsi_div`)
- **Purpose:** Detect price/momentum divergence.
- **Formula:** Standard RSI(14); vote when 5-bar price change and 5-bar RSI change disagree in sign.
- **Inputs:** close series, RSI series (reused from `calculate_all()`, not recomputed in backtest).
- **Outputs:** vote -1/0/+1.
- **Weight:** 10.0 default; dynamic weight from backtest accuracy.
- **Used in Confluence:** Yes. **Filter Score:** No. **Backtest:** Yes.
- **Status:** Complete, unchanged since Step 4-era design.

### Bollinger Bands Bounce (`bb`)
- **Purpose:** Mean-reversion signal at band extremes.
- **Formula:** price <= lower band -> bullish vote; price >= upper band -> bearish vote.
- **Used in Confluence:** Yes. **Filter Score:** No (ATR volatility criterion is separate). **Backtest:** Yes.

### OBV Divergence (`obv`)
- **Purpose:** Volume/price divergence (Step 4).
- **Formula:** cumulative On-Balance-Volume; vote on 5-bar price-vs-OBV divergence.
- **Note:** Quotex's "volume" is likely tick-count, not true traded volume — documented uncertainty, not claimed as verified.
- **Used in Confluence:** Yes. **Backtest:** Yes (fully vectorized, `shift/ffill` causal pattern).

### Support/Resistance Zone (`sr`)
- **Purpose:** Proximity-to-level signal (Phase 6).
- **Formula:** fractal swing detection -> ATR-merged zones -> vote BUY near safe support / SELL near safe resistance, gated by `zone_reliability >= 40`.
- **Also feeds:** Filter Score's `support_resistance` criterion (20 pts, graded: safe/near-safe/neutral/unsafe).
- **Used in Confluence:** Yes. **Filter Score:** Yes. **Backtest:** Yes (vectorized approximation — single most-recent confirmed swing, documented simplification vs. live's full clustering).

### Candlestick Pattern (`candle`)
- **Purpose:** 9-pattern detector (Phase 5): Doji, Hammer, Inverted Hammer, Shooting Star, Bullish/Bearish Engulfing, Morning/Evening Star, Inside Bar.
- **Formula:** geometry-derived per pattern (wick/body ratios, engulf %, gap quality, ATR normalization) — see `indicators.py::detect_candlestick_pattern_detailed()` docstring for exact per-pattern math.
- **Also feeds:** Filter Score's `candlestick` criterion (5 pts, graded by `reliability_score`).
- **Used in Confluence:** Yes (gated by `reliability_score >= 40`). **Filter Score:** Yes. **Backtest:** Yes (per-bar loop — documented ~3x cost vs. old 4-pattern version).

### CCI Extreme (`cci`) — Helper
Standard CCI(20); vote on extreme + reversal. Never generates BUY/SELL alone (helper group).

### Stochastic Cross (`stoch`) — Helper
Classic %K/%D cross in overbought/oversold zones.

### Round Number (`round_number`) — Helper
Psychological level proximity — **always votes 0 in the backtest replay by design** (documented, not a bug); live vote logic exists but is intentionally neutral in historical replay since "proximity to round number" isn't itself directional.

### Mean Reversion (`mean_reversion`) — Helper
Z-score-style extremity from a rolling mean.

### Candle Exhaustion (`exhaustion`) — Helper
Consecutive same-direction candle streak detection.

## Filter Score gate criteria (NOT confluence-vote factors — different mechanism)

### EMA Trend (20 pts)
Strong (trending + ADX >= threshold) = 20; weak (trending, low ADX) = 10; sideways = 0. Mandatory: direction != SIDEWAYS.

### ADX (15 pts)
>=35->15, 30-35->13, 25-30->10, 20-25->5, <20->0. Mandatory: adx >= 25 (config.ADX_TRENDING).

### ATR (15 pts)
Ideal (MEDIUM volatility level) -> 15; slightly high/low (LOW/HIGH) -> 10; extreme (>1.5% per analyzer.VOLATILITY_EXTREME_ATR_PCT) -> 0. Mandatory: not extreme.

### Multi-Timeframe (15 pts)
CONFIRMED -> 15; UNAVAILABLE -> 8 (neutral); DISAGREED -> 0. Mandatory: CONFIRMED.

### Payout (10 pts)
>=90->10, 85-90->8, 80-85->5, <80->0. Mandatory: >= config.MIN_PAYOUT (80.0).

## New OTC Indicators (Phase 7.3 detectors; connected to Confluence in Phase 8.6)

### Wick Rejection (`wick_rejection`)
- **Purpose:** Single-candle wick-dominance rejection signal.
- **Formula:** lower_wick_ratio >= 0.5 and > 2x upper_wick_ratio -> BUY; mirror for SELL. `strength_score` scales with wick ratio; `reliability_score` combines wick ratio + range-to-ATR significance.
- **Outputs:** `{name, direction, strength_score, reliability_score}`.
- **Weight:** 7.69 default (in `DEFAULT_CONFLUENCE_WEIGHTS` as of Phase 8.6).
- **Confluence vote:** BUY -> +1 / SELL -> -1 when `reliability_score >= 40.0` (`analyzer.WICK_REJECTION_VOTE_THRESHOLD`), else neutral.
- **Used in Confluence:** **Yes (Phase 8.6).** **Filter Score:** No. **Backtest:** Available as a raw function call; not yet wired into `backtest_factor_accuracy()`'s factor set (separately tracked in `NEXT_PHASE.md`).
- **Current status:** Implemented, tested, additive key in `calculate_all()` (`wick_rejection_detail`, unchanged since Phase 7.3). Registered in `indicator_registry.py`.

### Liquidity Sweep (`liquidity_sweep`)
- **Purpose:** Detect stop-hunt reversal — price spikes beyond a recent swing extreme then closes back inside it.
- **Formula:** Buy Side Sweep (high > recent high, close < recent high) -> SELL; Sell Side Sweep (low < recent low, close > recent low) -> BUY. Uses raw swing extremes over `lookback=20`, distinct from the SR engine's clustered zones.
- **Outputs:** `{name, sweep_type, direction, strength_score, reliability_score}`.
- **Weight:** 7.69 default (Phase 8.6).
- **Confluence vote:** BUY -> +1 / SELL -> -1 when `reliability_score >= 40.0` (`analyzer.LIQUIDITY_SWEEP_VOTE_THRESHOLD`), else neutral.
- **Used in Confluence:** **Yes (Phase 8.6).** **Filter Score:** No. **Backtest:** Not wired yet.
- **Current status:** Implemented, tested (both sweep directions verified), additive key `liquidity_sweep_detail`.

### False Breakout (`false_breakout`)
- **Purpose:** Detect a false break of a KNOWN Support/Resistance zone (reuses Phase 6's `detect_support_resistance_zones()`, distinct from Liquidity Sweep's raw-swing framing).
- **Formula:** False Support Break (low < support, close > support) -> BUY; False Resistance Break (high > resistance, close < resistance) -> SELL. `reliability_score` incorporates the SR zone's own `zone_reliability`.
- **Outputs:** `{name, break_type, direction, strength_score, reliability_score}`.
- **Weight:** 7.72 default (Phase 8.6 — gets the rounding residual so the 13-factor sum is exactly 100.0; not a claim of higher reliability, purely a tie-break).
- **Confluence vote:** BUY -> +1 / SELL -> -1 when `reliability_score >= 40.0` (`analyzer.FALSE_BREAKOUT_VOTE_THRESHOLD`), else neutral.
- **Used in Confluence:** **Yes (Phase 8.6).** **Filter Score:** No. **Backtest:** Not wired yet.
- **Current status:** Implemented, tested, additive key `false_breakout_detail`.

**Note on "Fake Breakout" from the original spec:** the spec listed "Fake Breakout" as a sub-case of Liquidity Sweep. It's covered by `detect_false_breakout()` instead — a deliberate design choice to give the two indicators genuinely distinct market-structure framing (raw swing points vs. established S/R zones) rather than one indicator computing the same thing twice under two names.

**Backtest divergence (Phase 8.6 known limitation):** these 3 factors now vote in live signals (`generate_confluence_signal()`) but are still absent from `backtest.py`'s `_factor_votes()`/`backtest_factor_accuracy()`, so backtest-derived dynamic weights do not yet cover them — they always fall back to the static default weight above until that separate, currently-unstarted task is done (see `NEXT_PHASE.md`).
