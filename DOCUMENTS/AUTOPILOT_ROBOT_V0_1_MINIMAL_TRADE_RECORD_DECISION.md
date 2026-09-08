# BybitScanner — Robot v0.1 minimal trade record decision

Version: 1.0
Date: 2026-09-08
Status: ACCEPTED DESIGN / PAPER PROTOTYPE
Implementation authorization: NONE

## Scope

Robot v0.1 must store only the basic trade fields required to operate the PAPER prototype, show Telegram status/statistics, and seed the future trading diary. Additional diary/research fields are intentionally deferred until practical PAPER usage shows that they are needed.

## Minimal stored fields

For each Robot v0.1 PAPER trade, retain at minimum:

- `trade_id`;
- symbol/ticker;
- direction: LONG or SHORT;
- pattern;
- source timeframe;
- signal time;
- entry time;
- entry type/path, sufficient to distinguish LIMIT, Market, and mixed partial-LIMIT/Market completion behavior;
- actual position size in WV/RO;
- authoritative average entry price;
- STOP price;
- TAKE price;
- exit time;
- exit price;
- exit reason, including at least STOP, TAKE, manual/takeover, and emergency close where applicable;
- realized PnL in USDT;
- realized PnL percent;
- fees/costs when already available from the shared authoritative execution/accounting path;
- reference/ID linking the trade back to the immutable approved Scanner signal snapshot.

## Reuse and scope rules

Robot must not create a duplicate accounting engine merely to populate these fields. Existing authoritative PAPER position, fill, order, execution, PnL, fee, and Scanner-signal data must be reused where available.

Missing non-critical diary enrichment must not block the prototype. Safety-critical execution/protection state remains governed by the existing Robot and Terminal contracts, not by this minimal record.

This minimal schema is a prototype baseline, not a final trading-diary schema. New fields should be added only when actual PAPER operation, statistics, debugging, or the later diary design demonstrates a concrete need.

# END_OF_DOCUMENT
