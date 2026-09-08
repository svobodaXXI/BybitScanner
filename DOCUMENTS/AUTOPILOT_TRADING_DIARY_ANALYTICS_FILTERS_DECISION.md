# AUTOPILOT Trading Diary — Analytics Filters and Rankings

Date: 2026-09-08
Status: ACTIVE / DESIGN-ONLY
Implementation authorization: NONE

## Accepted requirement

The trading diary must support an analytics layer that can be filtered and ranked across the selected observation window.

Required metrics / filters:
- average return per completed trade;
- average position holding time;
- win rate;
- most profitable time of day in MSK;
- most unprofitable time of day in MSK;
- signal ranking across all signal types, including identification of the most profitable and most unprofitable signal;
- ticker ranking, including the most profitable and most unprofitable ticker;
- number of STOP-protection blocking events;
- number of daily-drawdown blocking events;
- total number of completed trades;
- profitable-to-losing trade ratio.

## Ranking requirement

Signal and ticker analytics should not be limited to only best/worst labels. The diary should expose the full ranked list so the operator can compare all signals and all tickers over the selected period.

## Time-of-day requirement

Time-of-day profitability analysis uses MSK as the canonical display/analysis timezone.

## Extensibility

This is an initial mandatory analytics set, not a closed schema. Additional diary metrics and filters may be added later without changing the accepted meaning of the metrics above.

## Implementation note

Exact UI layout, aggregation granularity, storage model, and query mechanics are implementation details and do not require separate product decisions unless they materially change trading interpretation or risk behavior.
