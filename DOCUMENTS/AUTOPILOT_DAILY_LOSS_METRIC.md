# BybitScanner — AUTOPILOT Daily Loss Metric

Version: 1.0
Date: 2026-09-08
Status: ACTIVE / DESIGN-ONLY
Implementation authorization: NONE

Purpose: record the accepted calculation basis for the AUTOPILOT account-level daily-loss circuit breaker. This note refines Section 6 of `DOCUMENTS/AUTOPILOT_RISK_ADMISSION_REFINEMENTS.md` and does not authorize runtime, PAPER or LIVE implementation.

---

# 1. ACCEPTED DAILY-LOSS MEASURE

`ACCEPTED DESIGN`:

The daily-loss circuit breaker must use current account equity / mark-to-market drawdown rather than realized PnL alone.

Conceptually:

`DAILY_DRAWDOWN = DAY_START_EQUITY - CURRENT_ACCOUNT_EQUITY`

Therefore the metric includes both:

- realized PnL from trades already closed during the day;
- current unrealized PnL from positions that remain open.

The purpose is to prevent AUTOPILOT from continuing to add new risk merely because losses in open positions have not yet been realized.

Example:

- day-start equity: `10,000 USDT`;
- realized PnL: `-300 USDT`;
- current unrealized PnL: `-600 USDT`;
- current equity: approximately `9,100 USDT` before any separately defined accounting adjustments;
- daily drawdown: approximately `900 USDT = 9%`.

If the configured daily-loss threshold is crossed, the already accepted blocker behavior applies:

- reject new entries;
- reject position increases/additions;
- do not automatically close existing positions solely because of this blocker;
- preserve STOP, exit, risk-reduction and emergency-close actions.

Early PAPER research may keep enforcement disabled, but the system must still calculate and log the hypothetical trigger state.

---

# 2. STILL NEEDS VALIDATION / SEPARATE DESIGN DECISIONS

This decision does not yet define:

- the exact day-start equity baseline semantics;
- the trading-day timezone/reset boundary;
- treatment of commissions, funding and other account cash flows in the metric;
- the final threshold within or outside the current `8%–10%` research range;
- exact mark-price / equity source semantics for PAPER/LIVE parity.

These remain separate short design questions.

# END_OF_DOCUMENT
