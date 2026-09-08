# BybitScanner — Robot v0.1 Restart / Offline Recovery Decision

Version: 1.0
Date: 2026-09-08
Status: ACCEPTED DESIGN / PAPER PROTOTYPE
Implementation authorization: NONE

## Decision

Robot v0.1 must preserve fail-closed lifecycle semantics across process/PC restart without introducing a second trading state engine.

### Open positions

Robot-controlled `OPEN` PAPER positions are not discarded after restart.

On recovery, Robot must rebuild orchestration context from the existing authoritative PAPER position/protection state and continue management through the common execution/protection/state mechanisms.

Robot must not create a duplicate position store, protection store, accounting source, or independent reconciliation path.

### Waiting candidates

Approved `WAITING_BREAKOUT` candidates may be recovered only from their persisted immutable approval snapshot and only if they remain admissible under the already accepted rules, including:

- exact signal instance has not been invalidated;
- the candidate has not expired under the 20-closed-1m-candle rule;
- no manual PAPER position conflict exists on the symbol;
- Robot is not stopped;
- authoritative runtime state is sufficiently reconciled to permit safe continuation.

If recovery is ambiguous, Robot remains fail-closed and does not create a new entry until reconciliation establishes safe state.

## Offline breakout policy

If the qualifying breakout candle closed while Robot runtime was offline, Robot v0.1 must **not** enter retroactively on restart.

The missed breakout is not replayed into a market entry.

After restart, if the candidate is still valid, Robot resumes observation and waits for a new closed 1m candle that satisfies the frozen breakout condition within the remaining candidate lifetime.

For Falling Wedge LONG:

```text
new_closed_1m.close > frozen_upper_boundary
```

For Rising Wedge SHORT:

```text
new_closed_1m.close < frozen_lower_boundary
```

Only a candle that closes after Robot has resumed active observation may authorize the automatic PAPER entry.

## Rationale

This avoids converting the defined setup into a delayed chase entry at an unrelated market price after downtime. It preserves the intended relationship between confirmation candle, actual entry, STOP basis, TAKE basis, and risk/reward.

A later version may evaluate replay-aware recovery as a separate strategy policy, but Robot v0.1 does not backfill missed breakout executions.

## Reuse / authority boundary

Recovery orchestration may persist Robot-owned lifecycle metadata and immutable candidate snapshots, but authoritative trading facts remain owned by existing shared capabilities:

- PAPER positions;
- orders and protections;
- actual fills;
- instrument metadata;
- market-data/candle source;
- accounting/PnL;
- reconciliation state.

Robot recovery must consume these capabilities rather than reconstruct or duplicate them.

# END_OF_DOCUMENT
