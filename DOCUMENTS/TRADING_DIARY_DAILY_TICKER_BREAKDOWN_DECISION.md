# Trading Diary — Daily Ticker Breakdown

Date: 2026-09-08
Status: ACTIVE / DESIGN-ONLY
Implementation authorization: NONE

## Accepted requirement

For every individual trading day, the trading diary must provide a ticker-level breakdown showing which instruments were traded that day.

For each ticker in the selected day, show at minimum:
- ticker / symbol;
- number of completed trades;
- net profit/loss in USDT;
- net profit/loss in percent.

The daily ticker breakdown must respect the active diary filters and remain drill-down compatible with the underlying trade list.

This requirement is additive to the already accepted daily financial result, period return metrics, ticker ranking, signal ranking, win rate, holding-time, STOP-block, daily-drawdown-block and other diary analytics.

The diary design remains extensible so additional per-ticker daily metrics can be added later without changing the core model.
