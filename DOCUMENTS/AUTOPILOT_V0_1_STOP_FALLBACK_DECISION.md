# BybitScanner — AUTOPILOT v0.1 STOP Fallback Decision

Version: 1.0
Date: 2026-09-08
Status: ACCEPTED DESIGN / PAPER PROTOTYPE
Implementation authorization: NONE

## Decision

For Robot v0.1 Falling Wedge LONG entries:

1. Preferred STOP candidate is below the low of the confirmed 1m breakout candle, plus the existing/specified small technical buffer.
2. Compute stop distance from the actual PAPER entry fill price.
3. If the preferred structural STOP distance is less than or equal to 2%, use that structural STOP.
4. If the preferred structural STOP distance is greater than 2%, do not reject the trade solely for this reason. Use a fallback fixed STOP at 2% below the actual entry fill price.
5. The robot owns only the STOP policy decision. STOP order creation, state, protection sizing, lifecycle, reconciliation, and close semantics must use the existing common STOP/execution capability.

For LONG:

```text
preferred_stop = breakout_candle.low - technical_buffer
preferred_distance = (actual_entry - preferred_stop) / actual_entry

if preferred_distance <= 0.02:
    stop = preferred_stop
else:
    stop = actual_entry * 0.98
```

Price normalization must use the existing authoritative instrument/order normalization path rather than robot-specific rounding.

## Rationale

This preserves a structure-aware STOP when it is reasonably close while imposing a simple maximum stop width for the prototype without adding a second structural-search algorithm, dynamic sizing branch, or separate robot STOP engine.

The 2% threshold is a prototype baseline and remains subject to later validation.

# END_OF_DOCUMENT
