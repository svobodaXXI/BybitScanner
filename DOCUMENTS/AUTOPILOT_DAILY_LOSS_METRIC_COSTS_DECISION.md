# BybitScanner — AUTOPILOT Daily Loss Metric Costs Decision

Version: 1.0
Date: 2026-09-08
Status: ACTIVE / DESIGN-ONLY
Implementation authorization: NONE

Purpose: record the accepted definition of the daily-loss metric inputs for AUTOPILOT / PAPER research.

## ACCEPTED DESIGN

The daily-loss metric is based on the actual change in account equity from the fixed day-start baseline at 00:00 MSK (UTC+3).

The metric includes:

- realized PnL from closed trades;
- current unrealized PnL from open positions;
- trading fees already charged;
- funding already charged or credited.

Future hypothetical exit costs are not added to the daily-loss metric before they occur. In particular, expected future closing commission and estimated future slippage remain part of separate position/STOP risk estimation rather than the daily-loss circuit-breaker metric.

Conceptually:

`DAILY_ACCOUNT_CHANGE = CURRENT_ACCOUNT_EQUITY - DAY_START_ACCOUNT_EQUITY`

where current account equity already reflects realized PnL, unrealized PnL, charged trading fees, and charged/credited funding.

The daily blocker therefore tracks the real current state of the account rather than price-only PnL.

## RELATION TO EARLIER ACCEPTED DAILY-LOSS RULES

This decision supplements the already accepted rules that:

- the day-start baseline is fixed at the beginning of the trading day and does not rise with intraday profits;
- the trading-day boundary is 00:00 Moscow time (MSK, UTC+3);
- the research threshold remains approximately 8%–10% and is still NEEDS VALIDATION;
- early PAPER research may keep the blocker disabled while still logging hypothetical trigger points;
- LIVE AUTOPILOT must eventually enforce the validated daily-loss blocker.

# END_OF_DOCUMENT
