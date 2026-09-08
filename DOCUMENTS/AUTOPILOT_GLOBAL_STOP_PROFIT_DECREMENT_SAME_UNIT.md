# AUTOPILOT Global STOP Profit Decrement — Same Unit Rule

Date: 2026-09-08
Status: ACTIVE / DESIGN-ONLY
Implementation authorization: NONE

## Accepted decision

When a profitable completed AUTOPILOT trade occurs on an instrument that currently has a non-zero contribution to the global STOP ledger:

- that instrument's global STOP contribution is reduced by `1` (floor `0`);
- the total global STOP-score is reduced by the same `1`;
- these are not two independent adjustments — they are the same accounting unit reflected in both the per-instrument ledger and the total score.

Example:

- BTC contribution = `3`
- ETH contribution = `2`
- global STOP-score = `5`
- profitable BTC trade

Result:

- BTC contribution = `2`
- ETH contribution = `2`
- global STOP-score = `4`

This rule coexists with the separately accepted special case where a profitable trade on an instrument whose global contribution is already `0` reduces only the total global STOP-score by `0.5` and does not debit another instrument's contribution.
