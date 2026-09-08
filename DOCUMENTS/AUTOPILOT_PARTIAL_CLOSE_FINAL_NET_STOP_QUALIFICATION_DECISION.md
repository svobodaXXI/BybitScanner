# AUTOPILOT Partial-Close Final-Net STOP Qualification Decision

Version: 1.0
Date: 2026-09-08
Status: ACTIVE / DESIGN-ONLY
Implementation authorization: NONE

## Accepted decision

For STOP/recovery accounting, a position that was partially closed one or more times and whose remaining quantity is later closed by protective STOP is evaluated using the final aggregate net result of the entire position lifecycle.

If the final aggregate result of the whole position is strictly positive after all actually charged trading fees and funding, the final protective STOP event is NOT a qualifying STOP and does not increment STOP counters.

This remains true even when the final exit reason for the remaining quantity is protective STOP.

## Example

- Earlier partial closes realize profit.
- Remaining position later exits through protective STOP.
- Aggregate final net result for the entire position lifecycle, after actual fees and funding, is > 0.

Result:
- qualifying STOP: NO
- STOP counter increment: NO
- completed trade classification: profitable

## Consistency with existing rules

- Partial closes do not create separate completed trades for STOP/recovery accounting.
- STOP/recovery classification occurs only after the full position lifecycle is closed.
- Protective STOP counts only when the final aggregate net result is negative.
- Exact break-even remains neutral.
