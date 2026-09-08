# AUTOPILOT Global STOP Score — Authoritative Threshold Decision

Date: 2026-09-08
Status: ACTIVE / DESIGN-ONLY
Implementation authorization: NONE

## Accepted decision

For global STOP protection, the authoritative value for the trigger threshold is the separate overall `global STOP-score`.

Instrument-level STOP contributions are not summed to reconstruct or override the overall score. They are maintained for the diversity/distribution condition only.

Therefore:
- trigger threshold condition uses `global STOP-score >= 5`;
- diversity/distribution condition uses the instrument-level contribution ledger;
- both conditions must be true simultaneously for a global trigger;
- the sum of instrument contributions may differ from the global STOP-score because profitable trades on instruments with zero current contribution may reduce the overall global STOP-score by `0.5` without changing any instrument contribution.

Example:
- BTC contribution = 3
- ETH contribution = 2
- SOL contribution = 0
- sum of contributions = 5
- profitable SOL trade reduces global STOP-score from 5.0 to 4.5
- instrument contributions remain BTC=3, ETH=2, SOL=0
- global protection does not trigger while the authoritative global STOP-score is below 5, even though contribution sum is 5.

This decision keeps the threshold metric and the diversity evidence as two distinct state variables.
