# AUTOPILOT Journal — Filters and Period Returns Decision

Date: 2026-09-08
Status: ACTIVE / DESIGN-ONLY
Implementation authorization: NONE

## Accepted analytics filters

The trading journal/dashboard must support filtering by:
- period: day / week / month / custom range;
- ticker;
- signal / pattern type;
- LONG / SHORT;
- profitable / losing / all trades;
- exit reason: STOP / TAKE / strategy / manual / emergency;
- position-size restriction level: 100% / 50% / 25% / 12.5%;
- STOP-protection active/inactive;
- daily-loss blocker active/inactive;
- market regime;
- time of day in MSK;
- PAPER / LIVE;
- actual trades / counterfactual without STOP protection.

All selected filters must recalculate the whole analytics dashboard, not only the trade list.

## Required return analytics

The journal must show return/performance in both absolute and relative form:
- net financial result in USDT;
- net return in percent;
- for multiple periods, including at minimum day / week / month / custom selected range.

The period-return figures must update under the currently selected filters.

## Daily financial result

The journal must include a day-by-day financial result view.

For each trading day, show at minimum:
- date;
- net PnL in USDT;
- net PnL in percent;
- number of completed trades;
- profitable vs losing trade count;
- daily STOP-protection block count;
- daily-loss block count.

The trading-day boundary follows the project's fixed `00:00 MSK` boundary.

## Existing mandatory analytics retained

This decision extends, rather than replaces, the previously accepted metrics:
- average return per trade;
- average holding time;
- win rate;
- most profitable / most losing time of day in MSK;
- full ranking of signals;
- most profitable / most losing ticker and full ticker ranking;
- number of STOP-protection blocks;
- number of daily-loss blocks;
- total completed-trade count;
- profitable-to-losing trade ratio.

The metric/filter set remains extensible; additional analytics may be added later without changing the core journal model.
