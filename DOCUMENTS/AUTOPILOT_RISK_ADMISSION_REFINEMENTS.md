# BybitScanner — AUTOPILOT Risk Admission Refinements

Version: 1.0
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

# END_OF_DOCUMENT
