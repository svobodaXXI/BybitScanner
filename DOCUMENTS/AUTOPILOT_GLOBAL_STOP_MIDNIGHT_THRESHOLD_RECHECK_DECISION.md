# AUTOPILOT Global STOP Midnight Threshold Recheck Decision

Version: 1.0
Date: 2026-09-08
Status: ACTIVE / DESIGN-ONLY
Implementation authorization: NONE

## Decision
At `00:00 MSK`, after the accepted daily reduction of the aggregate global STOP-score, global protection is evaluated using the current aggregate score and the current diversity ledger.

If the aggregate global STOP-score is below `5`, global STOP protection is not active and must not trigger, even when per-instrument STOP contributions still satisfy or exceed the accepted diversity distribution such as `BTC=3`, `ETH=2`.

Global trigger requires both conditions at the same time:

1. aggregate global STOP-score `>= 5`;
2. accepted multi-instrument diversity/distribution requirement is currently satisfied.

Therefore a midnight reduction such as `5 -> 4` (or `5.5 -> 4.5`) suppresses the global trigger until later qualifying STOP activity raises the aggregate score back to at least `5` while the diversity condition is also satisfied.

## Rationale
The aggregate global STOP-score is the authoritative threshold metric. Per-instrument contributions are used only to validate diversity/distribution and do not independently activate global protection.
