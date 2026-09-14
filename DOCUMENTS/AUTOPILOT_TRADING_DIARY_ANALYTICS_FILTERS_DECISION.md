# AUTOPILOT Trading Diary — Analytics Filters and Rankings

Date: 2026-09-14
Status: ACTIVE / DESIGN-ONLY
Implementation authorization: NONE

## Accepted requirement

The Robot / AUTOPILOT statistics system must provide a read-only analytics projection over durable Robot trade history without changing trading, admission, protection, recovery, or execution semantics.

Robot Statistics v1 is based on existing durable `robot_trades` joined to `robot_candidates` for signal identity and metadata.

The first implementation slice must not require a persistence schema migration.

## Authoritative data source

Primary durable source:

- `robot_trades` — Robot trade identity, entry, protection, exit and recorded PnL data;
- `robot_candidates` — immutable candidate / signal identity and snapshot metadata.

Statistics are account-scoped. General account execution episodes from Trading Diary must not be silently mixed with Robot-owned trades.

The statistics layer is read-only and must not depend on Robot being RUNNING.

## Required metrics

Robot Statistics must expose, for the selected observation window:

- cumulative profit graph;
- total realized PnL in USDT;
- Return on traded notional, %;
- average PnL per completed trade;
- average position holding time;
- win rate;
- total completed trades;
- profitable trades;
- losing trades;
- breakeven trades;
- profitable-to-losing trade ratio;
- daily PnL;
- per-day ticker breakdown;
- ticker ranking;
- signal ranking;
- profitability ranking by time of day in MSK.

Future required metrics, currently unavailable from durable evidence:

- number of STOP-protection blocking events;
- number of daily-drawdown blocking events.

Unavailable metrics must be reported as unavailable / not recorded. They must not be reconstructed heuristically.

A STOP exit is not equivalent to a STOP-protection blocking event.

## Currency

Robot Statistics v1 uses USDT.

USDT must not be labelled as USD.

## PnL basis

### Gross PnL

`gross_pnl_usdt` uses the existing durable `realized_pnl_usdt`.

### Known-cost-adjusted PnL

When durable cost evidence exists:

`known_cost_adjusted_pnl_usdt = realized_pnl_usdt - known recorded fees/costs`

This value must not be described as full net PnL unless complete entry fees, exit fees, funding and all other relevant costs are durably proven.

The API and presentation layer must expose the selected PnL basis and cost-coverage/completeness state.

Unknown costs must remain unknown rather than be substituted with zero.

## Trade PnL percentage

The existing durable `realized_pnl_pct` may be displayed for an individual completed Robot trade using its current writer convention.

It must not be described as account return or portfolio return.

## Period percentage return

Robot Statistics v1 defines aggregate period percentage as:

`Return on traded notional = SUM(selected_pnl_basis for eligible trades) / SUM(entry_quantity * average_entry for the same eligible trades) * 100`

Only trades with sufficient entry-notional evidence are eligible for this metric.

The numerator and denominator must use exactly the same eligible trade subset. PnL from a trade excluded from the denominator must also be excluded from the numerator.

Coverage must report excluded/incomplete trades.

This metric must be labelled `Return on traded notional`.

It must not be labelled account return, portfolio return, equity return, or ROI on account equity.

## Cumulative profit graph

The Statistics view must include a cumulative profit chart.

v1 semantics:

- X axis: completed Robot trades ordered deterministically by `exit_time_ms`, then `trade_id` as the stable tie-breaker;
- displayed time: MSK;
- Y axis: cumulative PnL in USDT;
- each point adds the selected PnL basis for that closed trade;
- default basis: the same basis selected for the surrounding statistics view;
- gross and known-cost-adjusted bases must remain distinguishable;
- incomplete cost coverage must be visible when the adjusted basis is selected.

The chart represents cumulative realized Robot trade PnL for the filtered dataset.

It must not be labelled a full account equity curve while deposits, withdrawals, unrealized PnL, complete fees, funding and equity baseline are not included.

Future filters must be able to recalculate the curve for:

- date/period;
- ticker;
- signal / pattern;
- timeframe;
- direction;
- PnL basis.

Point/drill-down information should support:

- trade identity;
- ticker;
- direction;
- exit timestamp;
- trade PnL;
- cumulative PnL after the trade.

## Daily grouping

Daily PnL attribution uses `exit_time_ms`.

Canonical analytics/display timezone is `Europe/Moscow` / MSK.

Each day must support drill-down to:

- tickers traded;
- number of completed trades per ticker;
- PnL per ticker;
- total daily PnL.

## Time-of-day ranking

Time-of-day profitability uses `entry_time_ms` converted to MSK.

Every time bucket must expose its sample count.

Raw groups must not be hidden merely because sample count is small, but presentation must distinguish low-sample observations from stronger evidence.

A one-trade bucket must not be presented as a statistically reliable best/worst trading period.

The implementation specification may select a practical warning threshold without changing this contract.

## Signal ranking

Primary Robot Statistics v1 signal grouping key:

`pattern + source_timeframe`

The system must expose the full ranked list, not only best/worst labels.

Each ranking row should include at least:

- pattern;
- timeframe;
- completed trade count;
- selected PnL basis;
- average PnL;
- win rate;
- sample count.

`candidate_id` remains the drill-down identity for an individual signal instance.

Stable additional metadata from `signal_snapshot_json` may become future optional dimensions, but must not silently change the v1 grouping key.

## Ticker ranking

Ticker grouping key is `symbol`.

The full ranking must be available.

Each row should include at least:

- symbol;
- selected PnL;
- trade count;
- win rate;
- average PnL;
- sample count.

Best/worst ticker labels are derived from this ranking rather than maintained as separate state.

## Win / loss / breakeven semantics

Completed trades are classified into three distinct result groups:

- profitable;
- losing;
- breakeven.

Breakeven trades must not be silently counted as wins or losses.

Profitable-to-losing ratio uses profitable and losing counts only and must define behavior when the losing count is zero.

## Holding time

Holding time is defined as:

`exit_time_ms - entry_time_ms`

Known limitation: current durable `entry_time_ms` is the Robot trade-finalization entry timestamp and is not guaranteed to equal the timestamp of the first fill.

The UI/contract must not imply greater timestamp precision than the durable evidence provides.

## Filters

The read model should support, or remain structurally ready for, filters by:

- observation period;
- symbol;
- direction;
- pattern;
- source timeframe;
- exit reason;
- PnL basis.

Filtering must recompute aggregates and the cumulative PnL series from the same selected trade set.

## Read-only architecture

Recommended architecture:

1. `RobotStatisticsReader`
   - opens a true SQLite read-only boundary;
   - no WAL configuration;
   - no schema initialization;
   - no migrations;
   - no writes;
   - account-scoped queries only.

2. Pure projection / aggregation layer
   - Decimal arithmetic for monetary and percentage calculations;
   - deterministic MSK time conversion/grouping;
   - explicit coverage/completeness metadata;
   - no dependency on active Robot runtime.

3. Thin API layer
   - exposes the projection;
   - does not own trading behavior;
   - does not mutate Robot state.

4. Terminal Statistics view
   - consumes the API projection;
   - contains no authoritative trading calculations.

`SQLiteStore.open()` must not be reused as a supposedly read-only statistics boundary if opening it performs WAL setup, schema initialization or migrations.

## Reuse boundary

Existing pure Trading Diary analytics/presentation helpers may be reused only where their data semantics match exactly.

Robot trade history must not be merged with general account execution episodes merely to reuse an existing endpoint.

Reuse-first does not permit changing Robot ownership semantics.

## API response concept

A future thin Robot Statistics endpoint should return one account-scoped projection containing conceptually:

- filter/basis metadata;
- coverage metadata;
- summary metrics;
- cumulative PnL series;
- daily series;
- ticker ranking;
- signal ranking;
- time-of-day ranking;
- unavailable-metric indicators.

Exact transport field names are implementation details, but monetary values must preserve Decimal-safe semantics rather than introducing binary-float authority.

## Statistics UI information architecture

Statistics are opened from the AUTOPILOT / Robot area through the existing planned `Статистика` entrypoint.

The primary Statistics view should contain:

1. Summary
   - PnL USDT;
   - Return on traded notional %;
   - trade count;
   - win rate;
   - profitable / losing / breakeven counts;
   - average PnL;
   - average holding time.

2. Cumulative profit chart
   - cumulative closed-trade PnL in USDT;
   - selected PnL basis;
   - filter-aware.

3. Daily statistics
   - PnL by day;
   - ticker breakdown inside each day.

4. Rankings
   - tickers;
   - signals;
   - time of day.

5. Drill-down
   - individual Robot trades / candidates and their stored entry, exit, protection and result data.

Unavailable risk-block counters must be visibly unavailable rather than displayed as zero.

## Schema-change boundary

Robot Statistics v1 must be implementable without changing persistence schema.

A later dedicated scope may add durable evidence for:

- STOP-protection blocking events;
- daily-drawdown blocking events;
- complete fee/funding/cost attribution;
- missing close-path coverage;
- precise first-fill timing;
- account-equity baseline / cash-flow history required for true account/equity return.

Those changes must not be bundled into the v1 read-only projection merely to make statistics appear complete.

## Implementation acceptance criteria

A future Robot Statistics v1 implementation slice is acceptable only when:

- reads are truly SQLite read-only;
- data are account-scoped;
- no schema initialization/migration/write occurs;
- only completed Robot trades contribute to realized performance aggregates;
- Decimal arithmetic is used for authoritative calculations;
- daily and time-of-day grouping is deterministic in MSK;
- cumulative PnL is deterministically ordered by `exit_time_ms`, then `trade_id` as the stable tie-breaker;
- PnL basis and cost coverage are explicit;
- incomplete cost evidence is not represented as full net PnL;
- Return on traded notional is not represented as account/equity return;
- breakeven remains distinct from wins/losses;
- STOP exits are not counted as STOP blocking events;
- unavailable risk metrics remain unavailable;
- filters consistently affect summary, rankings, daily series and cumulative series;
- unit tests cover formulas, grouping, rankings, coverage, filtering and cumulative-curve ordering;
- implementation does not modify Robot admission, execution, protection, recovery or control semantics.

## Extensibility

This is the mandatory Robot Statistics v1 analytics contract, not a closed analytics schema.

Additional dimensions and metrics may be added later when durable evidence exists, provided they do not silently change the accepted meaning of existing statistics.
