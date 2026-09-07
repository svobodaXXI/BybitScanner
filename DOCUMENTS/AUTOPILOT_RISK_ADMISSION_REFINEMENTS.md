# BybitScanner — AUTOPILOT Risk Admission Refinements

Version: 1.1
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

Version 1.1 records this combined directional-heat policy.

# END_OF_DOCUMENT
