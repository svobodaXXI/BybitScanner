# BybitScanner — AUTOPILOT v0.1 TAKE Policy Decision

Version: 1.0
Date: 2026-09-08
Status: ACCEPTED DESIGN
Implementation authorization: NONE

## Decision

For the first PAPER robot prototype, Falling Wedge 1m LONG trades use one full-position TAKE target derived from the existing scanner-provided wedge potential.

The robot must not reconstruct or independently recalculate wedge geometry or pattern potential.

Given:

- `actual_entry_price` = the authoritative PAPER execution fill price;
- `scanner_potential_percent` = the versioned potential already produced for the accepted scanner signal;
- `realization_fraction = 0.90`;

then:

```text
take_percent = scanner_potential_percent × 0.90
take_price   = actual_entry_price × (1 + take_percent / 100)
```

Example:

```text
scanner potential = +5.0%
actual entry       = 100.00
TAKE               = 104.50
```

The entire remaining Robot-controlled position is exited at this TAKE in v0.1. No runner, staged realization, trailing target, retest target, or later geometry revision is used.

## Architectural boundary

- Scanner/Wedge owns pattern potential calculation and versioned signal output.
- Robot strategy policy consumes the existing potential value and applies only the accepted `0.90` realization fraction.
- Common execution owns TAKE order lifecycle, quantity synchronization, fills, cancellation and position state.
- Robot must not create a separate TAKE execution engine or duplicate position state.

## Validation status

`0.90` is an accepted prototype parameter for v0.1, not evidence of optimal expectancy. Future research may compare other realization fractions or management policies without changing the execution contract.

# END_OF_DOCUMENT
