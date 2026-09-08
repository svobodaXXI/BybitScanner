# BybitScanner — AUTOPILOT v0.1 STOP Technical Buffer Decision

Version: 1.0
Date: 2026-09-08
Status: ACCEPTED DESIGN / PAPER PROTOTYPE
Implementation authorization: NONE

## Decision

For Robot v0.1, the technical buffer used to place the preferred structural STOP beyond the confirmed 1m breakout candle extremum is exactly one instrument tick.

LONG / Falling Wedge:

```text
technical_buffer = tick_size
preferred_stop = breakout_candle.low - tick_size
```

SHORT / Rising Wedge:

```text
technical_buffer = tick_size
preferred_stop = breakout_candle.high + tick_size
```

The `tick_size` value must come from the existing authoritative instrument metadata / price-normalization capability. Robot must not maintain a duplicate tick-size table or implement a separate rounding source of truth.

After deriving the preferred STOP, apply the already accepted 2% fallback policy using the actual PAPER entry fill:

- if distance from actual entry to preferred STOP is `<= 2%`, use the preferred STOP;
- if distance is `> 2%`, use the fixed 2% fallback from actual entry;
- final order-price normalization and STOP lifecycle remain owned by the existing common execution/protection capability.

## Rationale

One tick is selected because the buffer's purpose in v0.1 is only to place the STOP strictly beyond the breakout candle extremum, not to introduce an additional volatility/risk model. The breakout candle itself supplies the structural distance, while the existing 2% fallback bounds excessive width.

This keeps the initial policy deterministic, instrument-aware, easy to test, and compatible with reuse-first / single-authoritative-capability architecture. ATR-based, percentage, or wider tick buffers may be evaluated later without changing Robot orchestration or common execution ownership.

# END_OF_DOCUMENT
