# AUTOPILOT Partial Close Completion Accounting Decision

Version: 1.0
Date: 2026-09-08
Status: ACTIVE / DESIGN-ONLY
Implementation authorization: NONE

## Decision

For STOP/recovery accounting, a partial close is not treated as a completed trade.

A trade contributes to STOP/recovery counters only after the entire position lifecycle is fully closed.

Consequences:
- partial realized P/L does not immediately increment or decrement STOP/recovery counters;
- no separate recovery unit is created for each partial exit;
- the final completed-trade result is evaluated only when the remaining position reaches zero;
- final classification still uses the accepted completed-trade rules, including actual fees/funding/executed prices and exit reason semantics.

This keeps STOP/recovery accounting aligned with the existing definition of a completed trade and avoids overcounting one position lifecycle as multiple trades.
