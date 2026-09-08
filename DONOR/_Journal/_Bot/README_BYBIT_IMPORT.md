# Bybit read-only import

The Bybit integration is read-only. It requests `execType=Trade`; Funding rows
are ignored defensively and never become Journal executions.

## Automatic market snapshot V1

When an execution creates or closes a logical Trade, the existing execution
pipeline captures the V1 automatic factors through generic
`AutomaticFactorObservation` persistence. Entry snapshots use the Trade's
`opened_at`, including during delayed historical import. The existing
`entry_hour` identity is preserved: it remains the user's local opening hour
(definition/calculation `1/1`), using the explicit capture timezone when one is
configured and otherwise the timezone carried by the opening timestamp. It is
not relabeled as UTC. `entry_day_of_week` is ISO weekday in UTC (Monday=1,
Sunday=7). Bybit linear volume is base-coin volume and turnover is USDT.

`rvol_at_entry` is the current UTC day's cumulative volume through the last
closed one-minute candle before the entry minute divided by the average
cumulative volume through the same elapsed UTC-day minute over the five prior
complete UTC days. Previous-day and five-day daily factors use closed daily
candles only. Missing market data is persisted as a missing observation, never
as zero. Available observations retain the timestamp of the last contributing
closed kline: the last current 1m candle for intraday factors and RVOL, the
actual previous D candle for previous-day factors, and the latest contributing
D candle for five-day averages. RVOL provenance records its current cutoff and
the five-day same-elapsed-minute comparison window; average provenance records
the contributing daily-candle bounds. Replaying the same import/sync is
idempotent by the existing versioned observation identity.

`holding_duration_seconds` is an exact DECIMAL value, including fractional
seconds. Its compatibility identity is definition/calculation version `2/2`;
the former integer contract remains a distinct historical identity.

## Historical compatibility policy

Historical discovery is scoped by the request itself to `category=linear`,
`settleCoin=USDT`, and `execType=Trade`. Therefore `execFee` is normalized as
`USDT` even when the old response has a blank or contradictory `feeCurrency`.
That field is retained only as a safe diagnostic anomaly and cannot move the
history boundary. Required factual fields (`symbol`, `side`, `execQty`,
`execPrice`, `execFee`, `execTime`, and `execId`) remain mandatory.

Historical symbols absent from the current active catalog receive a stable,
inactive historical-only instrument identity. It is persisted only as part of
the confirmed import transaction and is never returned by normal active
instrument search.

History scans use gap-free seven-day windows with bounded concurrency controlled
by `BYBIT_HISTORY_CONCURRENCY` (default `4`). Telegram keeps a short-lived
eight-minute raw snapshot for repeated previews; the persisted boundary remains
the authoritative fast path for opening the history menu.

## Catalog sync

Run the explicit admin operation after configuring the existing Bybit and
database environment variables:

```text
python -m app.infrastructure.exchanges.bybit.catalog_sync
```

The sync uses the public `instruments-info` endpoint, follows cursors, assigns
stable IDs, upserts by the `(symbol, exchange, market)` natural key, and marks
missing entries inactive without deleting historical catalog rows.

## Preview

Preview a range before writing anything:

```text
python -m app.infrastructure.exchanges.bybit.preview --start 2026-08-01T00:00:00Z --sample 10
```

The output contains execution count, symbol count, first/last timestamps,
counts by symbol and sanitized sample rows. API credentials and auth headers
are never printed.

## Historical import

The importer queries bounded seven-day windows, paginates each window, sorts
facts globally, and sends every fact through the existing UoW/idempotency path:

```text
python -m app.infrastructure.exchanges.bybit.historical_import \
  --start 2026-08-01T00:00:00Z \
  --end 2026-09-05T00:00:00Z \
  --allow-unsafe-boundary
```

An arbitrary historical start can be in the middle of an already-open exchange
position. The importer therefore refuses unattended writes unless
`--allow-unsafe-boundary` is explicitly supplied after a preview. It never
guesses a missing opening execution. Replaying the same range is safe because
external execution identity remains durable and idempotent.
