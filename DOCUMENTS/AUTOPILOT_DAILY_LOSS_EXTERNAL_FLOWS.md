# BybitScanner — AUTOPILOT Daily-Loss External Cash-Flow Treatment

Date: 2026-09-08
Status: ACTIVE / DESIGN-ONLY
Implementation authorization: NONE

## ACCEPTED DESIGN

External account cash flows must not be counted as trading profit or trading loss for the AUTOPILOT daily-loss blocker.

The daily-loss metric therefore uses the fixed day-start capital baseline and adjusts for net external transfers during the trading day.

Conceptually:

`DAILY_TRADING_RESULT`
`= CURRENT_ACCOUNT_EQUITY`
`- DAY_START_ACCOUNT_EQUITY`
`- NET_EXTERNAL_CASH_FLOW`

where positive net external cash flow means net deposits/transfers into the account and negative net external cash flow means net withdrawals/transfers out of the account.

Examples:

- day-start equity = 10,000 USDT;
- +2,000 USDT deposited during the day;
- current equity = 11,500 USDT;
- trading result = 11,500 - 10,000 - 2,000 = -500 USDT.

A withdrawal is treated symmetrically and must not create a false trading loss.

Rules:

- deposits/transfers in do not improve the trading PnL used by the daily blocker;
- withdrawals/transfers out do not worsen the trading PnL used by the daily blocker;
- cash-flow events must be timestamped and logged for later diary/research reconstruction;
- the day-start baseline itself is not reset merely because a transfer occurs;
- the accepted trading-day boundary remains 00:00 MSK (UTC+3);
- this note does not authorize runtime or LIVE implementation.

# END_OF_DOCUMENT
