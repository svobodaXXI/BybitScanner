# BybitScanner — AUTOPILOT Daily Loss Baseline Decision

Version: 1.0
Date: 2026-09-08
Status: ACTIVE / DESIGN-ONLY
Implementation authorization: NONE

Purpose: record the accepted baseline semantics for the AUTOPILOT daily-loss blocker.

## ACCEPTED DESIGN

The daily-loss percentage is measured against the account equity/capital captured at the start of the trading day.

The day-start baseline remains fixed for that trading day and is not raised if the account reaches a higher intraday equity peak.

Conceptually:

`DAILY_DRAWDOWN = (DAY_START_EQUITY - CURRENT_EQUITY) / DAY_START_EQUITY`

where `CURRENT_EQUITY` includes both realized PnL and current unrealized PnL according to the previously accepted daily-loss metric decision.

Example:

- day-start equity = 10,000 USDT;
- intraday equity rises to 11,000 USDT;
- later current equity falls to 10,200 USDT;
- daily loss vs day-start baseline = 0%; the account is still +2% versus the start of the day;
- the decline from the intraday peak is not part of this daily-loss blocker.

If an intraday peak-to-trough drawdown control is added later, it must be modeled as a separate risk safeguard rather than silently changing the daily-loss baseline.

The exact trading-day timezone/reset boundary remains NEEDS VALIDATION / NOT YET ACCEPTED.

# END_OF_DOCUMENT
