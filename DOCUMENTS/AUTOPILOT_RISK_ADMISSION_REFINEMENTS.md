# BybitScanner — AUTOPILOT Risk Admission Refinements

Version: 1.5
Date: 2026-09-07
Status: ACTIVE / DESIGN-ONLY
Implementation authorization: NONE

Purpose: capture accepted refinements to `DOCUMENTS/AUTOPILOT_PORTFOLIO_RISK_ARCHITECTURE.md` without changing runtime behavior.

---

# 1. REDUCED-SIZE ADMISSION MUST BE REVALIDATED BY STRATEGY

`ACCEPTED DESIGN`:

When the Portfolio Risk Engine cannot admit the full requested position size but can admit a smaller size, it may return a maximum admissible reduced size.

The strategy must then re-evaluate whether the trade is still economically meaningful at that reduced size.

Flow:

`STRATEGY REQUESTED SIZE`
`-> PORTFOLIO RISK ENGINE MAX ADMISSIBLE SIZE`
`-> STRATEGY REVALIDATION AT REDUCED SIZE`
`-> ACCEPT_REDUCED / REJECT_TOO_SMALL`

Rules:

- the Portfolio Risk Engine owns the maximum admissible size under account/asset/cluster/directional/liquidity constraints;
- the strategy owns the question of whether the reduced trade still satisfies setup economics and strategy semantics;
- reduced size must not bypass minimum viable trade economics, minimum meaningful exposure, fee/slippage considerations, or setup-specific sizing semantics;
- if the reduced trade remains valid, return `ACCEPT_REDUCED`;
- if the reduced trade becomes too small or economically meaningless, return `REJECT_TOO_SMALL`;
- exact minimum viable reduced-size threshold remains strategy-specific and/or `NEEDS VALIDATION` unless a stronger rule already defines it;
- the diary/research dataset must record requested size, maximum admissible size, final accepted size, and the revalidation result.

This prevents two failure modes:

1. rejecting otherwise useful opportunities merely because full size is unavailable;
2. executing tiny residual positions that are technically permitted by risk limits but no longer make strategic/economic sense.

---

# 2. COMBINED DIRECTIONAL-HEAT ADMISSION

`ACCEPTED DESIGN`:

Directional concentration must use a combined model rather than a single fixed LONG/SHORT count or cluster-only rule.

The Portfolio Risk Engine should maintain:

- an absolute hard ceiling for directional heat so one-sided exposure can never grow without bound;
- a lower effective directional allowance that changes dynamically with market regime and correlation state;
- the ability to reduce a new position size when the full request would exceed the current effective directional allowance;
- strategy revalidation of any reduced size under Section 1 before execution.

Conceptual behavior:

`ABSOLUTE_DIRECTIONAL_CEILING`
`+ MARKET_REGIME_ADJUSTMENT`
`+ CORRELATION / CLUSTER CONTEXT`
`-> CURRENT_EFFECTIVE_LONG_OR_SHORT_CAPACITY`
`-> ACCEPT_FULL / ACCEPT_REDUCED / REJECT_DIRECTIONAL_HEAT`

Examples of intended behavior:

- in a strong, validated bullish regime, admissible LONG heat may be higher than in a neutral or stressed regime;
- in a strong bearish regime, admissible SHORT heat may be higher;
- when many positions are highly correlated, effective one-direction capacity should decrease even if nominal symbol count is diversified;
- hard directional ceilings remain binding regardless of regime classification;
- exact regime definitions, adjustment factors, correlation weighting and numeric ceilings remain `NEEDS VALIDATION`.

This rule complements, but does not replace:

- `MAX_PER_ASSET_EXPOSURE = 2 WV`;
- `MAX_AUTOPILOT_EXPOSURE = 19 WV`;
- cluster-heat constraints;
- account/session/reconciliation health gates;
- liquidity/execution-risk checks.

Required diary/research fields should include at least:

- direction (`LONG` / `SHORT`);
- directional heat before/after;
- absolute directional ceiling in force;
- effective regime-adjusted capacity;
- market-regime state/version;
- correlation/cluster adjustment inputs;
- requested and admitted size;
- final decision code.

---

# 3. COMBINED MARKET-REGIME MODEL

`ACCEPTED DESIGN`:

`MARKET_REGIME` must not be derived from a single instrument or one indicator. AUTOPILOT should combine several independent market-state blocks and produce a versioned regime state used by the Portfolio Risk Engine.

Primary input blocks:

1. `BTC_ETH_TREND` — directional state and structure of BTC and ETH;
2. `MARKET_BREADTH` — how broadly the traded universe participates in rising/falling movement;
3. `VOLATILITY_STATE` — calm/normal/elevated/stress volatility context;
4. `MOMENTUM_STATE` — strength/persistence of directional movement across the market;
5. `CORRELATION_STRESS` — whether cross-asset correlation is normal or converging toward a common stressed move.

The final state should be richer than simple `BULL / BEAR`.

Candidate initial taxonomy:

- `BULL_CALM`;
- `BULL_VOLATILE`;
- `NEUTRAL`;
- `BEAR_CALM`;
- `BEAR_STRESS`;
- optionally later additional transitional/uncertain states if research shows they add value.

Rules:

- no single input block may silently become the sole market-regime authority unless a later versioned rule explicitly says so;
- exact indicators, windows, weights, thresholds and state-transition hysteresis remain `NEEDS VALIDATION`;
- regime classification must use decision-time data only and must not be rewritten after the outcome is known;
- stale or materially incomplete regime inputs must expose explicit data-health state and participate in degraded/fail-closed risk behavior rather than being silently ignored;
- the regime state is context for admission sizing and directional heat, not an unconditional trade signal by itself.

Required diary/research fields should include at least:

- `market_regime_state`;
- `market_regime_model_version`;
- BTC/ETH trend features;
- breadth features;
- volatility features;
- momentum features;
- correlation/stress features;
- regime confidence/data-health state;
- regime transition timestamp;
- effective LONG/SHORT capacity derived from the regime.

---

# 4. ASYMMETRIC MARKET-REGIME TRANSITION / HYSTERESIS POLICY

`ACCEPTED DESIGN`:

Changes in effective LONG/SHORT capacity must not mirror every raw regime-classifier fluctuation immediately. AUTOPILOT should use asymmetric confirmation and smoothing so risk can contract quickly when conditions worsen but expand more cautiously when conditions improve.

Policy:

- ordinary non-stress regime changes require confirmation across multiple decision cycles and should move effective directional capacity gradually rather than by a full one-step jump;
- transitions into a materially worse or `STRESS` state may reduce admissible **new** directional risk quickly;
- transitions into a better regime should restore directional capacity more slowly and only after persistence/confirmation, reducing false-recovery risk;
- regime changes primarily affect admission of new entries and position increases;
- existing positions are not automatically cut solely because the market-regime label changed; they remain governed by setup invalidation, STOP, management and stronger emergency-risk rules;
- hard absolute directional ceilings remain binding at all times;
- exact confirmation length, smoothing function, stress override threshold, recovery delay and transition coefficients remain `NEEDS VALIDATION`.

Conceptual behavior:

`RAW_REGIME_STATE`
`-> CONFIDENCE / PERSISTENCE CHECK`
`-> ASYMMETRIC TRANSITION FILTER`
`-> EFFECTIVE_REGIME_FOR_RISK`
`-> EFFECTIVE_LONG/SHORT_CAPACITY`

The transition filter should favor:

- fast defensive contraction;
- slower offensive expansion;
- reduced oscillation/churn around state boundaries.

Required diary/research fields should include at least:

- raw regime state;
- effective regime state used for risk;
- transition direction (`IMPROVING` / `WORSENING` / `STRESS` / `STABLE`);
- persistence/confidence values;
- prior and new effective directional capacity;
- transition reason and model version;
- timestamp of both raw and effective state changes.

---

# 5. COMBINED EXPOSURE + STOP-RISK HEAT

`ACCEPTED DESIGN`:

AUTOPILOT must control two different things at the same time:

1. **how much capital is exposed** in positions;
2. **how much can realistically be lost** if current protective STOP orders are hit.

Nominal exposure limits remain independent hard safeguards:

- `MAX_PER_ASSET_EXPOSURE = 2 WV`;
- `MAX_AUTOPILOT_EXPOSURE = 19 WV`.

These limits protect against asset-specific and operational force-majeure risk that a STOP may not contain.

Separately, portfolio and cluster risk should be based primarily on estimated worst-case loss to the current valid STOP, including an allowance for fees and adverse execution/slippage.

Conceptually:

`POSITION_STOP_RISK`
`≈ POSITION_QUANTITY × ADVERSE_DISTANCE_TO_STOP`
`+ FEES`
`+ SLIPPAGE_ALLOWANCE`

Portfolio and cluster stop-risk should then be adjusted by correlation / common-market stress so several positions that are likely to lose together consume more effective risk capacity than independent positions.

Therefore admission requires both classes of constraint to pass:

- exposure caps in WV;
- stop-risk / portfolio-heat limits.

A trade may be rejected or size-reduced even when there is spare WV exposure capacity if its stop-risk would exceed the current portfolio, cluster or directional risk budget.

Conversely, a tight-stop trade may consume relatively little stop-risk budget while still remaining subject to the same hard WV exposure caps.

Rules:

- WV exposure and stop-risk must never be treated as the same quantity;
- valid protective STOP data is required for stop-risk-based admission unless a later explicit degraded-policy rule defines otherwise;
- estimated loss must use decision-time STOP, quantity, fees and slippage assumptions and must not be rewritten after outcome;
- correlation/stress adjustment should increase effective risk for positions expected to fail together rather than provide false diversification from symbol count alone;
- exact portfolio stop-risk ceiling, cluster stop-risk ceiling, slippage allowance and correlation/stress formula remain `NEEDS VALIDATION`.

Required diary/research fields should include at least:

- exposure in WV;
- entry/reference price;
- STOP price and STOP source/version;
- raw loss-to-STOP estimate;
- fee allowance;
- slippage allowance;
- correlation/stress adjustment;
- effective position risk;
- cluster risk before/after;
- portfolio risk before/after;
- requested and admitted size;
- final risk decision code.

---

# 6. DAILY LOSS TRADING BLOCKER

`ACCEPTED DESIGN DIRECTION`:

AUTOPILOT should have a separate account-level daily-loss circuit breaker for future real-money operation.

Target research range:

- daily loss threshold under consideration: approximately `8%–10%` of the account deposit / day-start capital baseline;
- the exact final threshold remains `NEEDS VALIDATION` and must be chosen from virtual-account statistics before LIVE use.

Behavior after the threshold is reached:

- block all **new risk** for the remainder of the trading day;
- block new entries and position increases/additions;
- existing positions continue only under their already-authorized STOP / exit / risk-reduction management;
- risk-reducing actions and emergency close must remain available;
- normal new-risk admission resumes only on the next trading day after the daily baseline is reset and account/risk state is healthy.

This daily blocker is distinct from the simultaneous portfolio stop-risk budget in Section 5. The Section 5 budget limits how much can be lost across currently open positions if protective STOPs are hit; the daily blocker limits how much account loss may accumulate across the whole day before trading is suspended.

Testing / rollout policy:

- early PAPER / virtual-account research may run with the daily blocker disabled so the system can collect an unbiased distribution of natural daily losses and identify where the blocker would have triggered;
- even when disabled in PAPER, the system should preferably calculate and log the hypothetical trigger state for later analysis;
- before transition to real-money AUTOPILOT, the daily-loss blocker becomes a required safety layer and its final threshold/reset semantics must be explicitly validated;
- this document does not authorize LIVE implementation.

Calculation details still `NEEDS VALIDATION`:

- whether the daily loss measure uses realized PnL only or realized + current unrealized PnL;
- exact day-start baseline definition;
- exchange/trading-day timezone and reset boundary;
- whether commissions/funding/slippage are included in the trigger metric;
- exact threshold within the `8%–10%` research range.

Required diary/research fields should include at least:

- day-start capital baseline;
- current daily PnL / drawdown measure;
- hypothetical blocker threshold;
- blocker enabled/disabled state;
- trigger timestamp if crossed;
- maximum further drawdown after hypothetical trigger during PAPER research;
- next-day reset timestamp;
- reason code for blocked new-risk decisions.

Version 1.5 records this daily-loss circuit-breaker design direction.

# END_OF_DOCUMENT
