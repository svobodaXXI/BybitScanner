# BybitScanner — Robot v0.1 entry strategy decision

Version: 1.0
Date: 2026-09-08
Status: ACCEPTED DESIGN / PAPER PROTOTYPE
Implementation authorization: NONE

## Scope

This document records the accepted Robot v0.1 wedge-entry lifecycle after the strategy change from direct breakout entry to breakout -> retest -> LIMIT/confirmation entry.

It is a design contract only. It does not authorize Robot runtime implementation.

The Robot remains an orchestration/strategy layer. It must reuse the existing authoritative scanner geometry, market data, instrument metadata/tick size, PAPER sizing/execution, order lifecycle, position state, protection, and reconciliation capabilities. No Robot-specific trading engine, price feed, geometry refit, or duplicate order-state subsystem is introduced.

## 1. Frozen pattern geometry

Approval transfers an immutable scanner signal/pattern snapshot to Robot.

All breakout, retest, LIMIT, confirmation, and apex calculations use that same frozen wedge instance. The boundary value may be evaluated at a later candle/time coordinate, but the wedge itself is not refit, redetected, or replaced during the entry lifecycle.

## 2. Breakout is no longer the entry trigger

The first qualifying closed 1m candle beyond the frozen wedge boundary establishes the breakout but does not directly trigger Market entry.

LONG / Falling Wedge:
- breakout is a closed 1m candle above the frozen upper boundary.

SHORT / Rising Wedge:
- breakout is a closed 1m candle below the frozen lower boundary.

After breakout, the idea transitions into the post-breakout retest/entry phase.

Any earlier Robot v0.1 design note that directly entered Market on the first qualifying breakout close is superseded by this document.

## 3. Retest policy

Robot waits for price to retest the broken pattern boundary.

A retest may be shallow or deep. Price is allowed to move back inside the wedge during the retest; that fact alone does not invalidate the trading idea.

No separate maximum retest-depth filter is added in Robot v0.1.

The ultimate post-breakout entry horizon is the frozen wedge apex. Where an earlier design note conflicts by imposing a shorter global post-breakout entry expiry, this accepted apex-based lifecycle governs the retest/LIMIT phase.

## 4. Aggressive LIMIT entry path

Robot may attempt to enter with a LIMIT order in the retest zone before a confirmation candle has closed.

This is intentionally a more aggressive entry path whose purpose is to obtain a better price near the broken pattern boundary.

Initial LIMIT placement:
- LONG: `Buy Limit` at the frozen upper-boundary value at the relevant current retest time/candle coordinate;
- SHORT: `Sell Limit` at the frozen lower-boundary value at the relevant current retest time/candle coordinate.

The price is normalized only through the shared authoritative instrument metadata/order-normalization capability.

A LIMIT fill during the retest is a valid Robot entry even though the later confirmation candle has not yet occurred.

No independent Robot-specific definition of retest-zone width is introduced in v0.1.

## 5. Unfilled LIMIT repositioning

If the active retest LIMIT has not filled after 5 newly closed 1m candles, Robot may reposition it using the same frozen boundary evaluated at the current candle/time coordinate.

Reposition price:
- LONG: current-coordinate frozen upper-boundary value + 2 ticks;
- SHORT: current-coordinate frozen lower-boundary value - 2 ticks.

If the repositioned LIMIT remains unfilled, the same 5-closed-candle cadence continues. Robot may keep repositioning the order in this manner up to the frozen wedge apex.

The 2-tick offset is a Robot v0.1 prototype strategy parameter, not a separate geometry rule.

Every reposition must use the shared authoritative order amend/cancel/reconciliation lifecycle. Blind resend, duplicate entry orders, or a second Robot-owned order-state engine are forbidden.

## 6. Confirmation Market entry path

The confirmation path remains available when LIMIT entry has not filled.

After a retest:
- LONG confirmation requires a closed 1m candle again above the frozen upper boundary;
- SHORT confirmation requires a closed 1m candle again below the frozen lower boundary.

A qualifying confirmation close authorizes consideration of Market entry; it does not bypass the accepted entry-quality gates.

If a Robot LIMIT is still active when the Market confirmation path becomes eligible, Robot must first make the LIMIT authoritatively cancelled/inactive through the shared lifecycle. Market entry must not be sent while the old LIMIT can still fill.

This is a single-entry invariant: the LIMIT path and confirmation-Market path are alternatives for one immutable Robot idea, never simultaneous independent entry attempts.

## 7. Entry-quality gates for confirmation Market entry

Immediately before actual Market entry, Robot evaluates the trade using authoritative current price/state and the already accepted STOP/TAKE calculations.

Market entry is allowed only if both conditions hold:
- expected reward/risk is at least 1.0;
- expected reward from the prospective entry to TAKE is at least 1%.

If reward/risk is below 1.0, the idea terminates without entry as `SKIPPED_POOR_RR`.

If expected reward is below 1%, the idea terminates without entry as `SKIPPED_LOW_REWARD`.

These are Robot v0.1 PAPER prototype filters and may later be calibrated from collected data.

## 8. Apex termination

If the frozen wedge apex is reached before either:
- a valid LIMIT entry has filled; or
- a valid confirmation Market entry has completed,

then the idea expires without entry.

Conceptually this may be represented as `EXPIRED_AT_APEX`; exact implementation enum naming is deferred until an implementation specification is authorized.

The same immutable wedge instance must not reactivate or enter later beyond its apex. A later Robot trade on the same symbol requires a genuinely new scanner pattern/signal instance.

## 9. Conceptual lifecycle

```text
WAITING_BREAKOUT
  -> qualifying closed 1m breakout candle
  -> WAITING_RETEST

WAITING_RETEST
  -> retest zone reached
  -> LIMIT_WORKING at frozen boundary

LIMIT_WORKING
  -- filled ---------------------------------------------> ENTRY_FILLED
  -- 5 new closed 1m candles, still unfilled ------------> authoritative reposition
  -- confirmation close becomes eligible ----------------> cancel/reconcile LIMIT first
                                                           -> entry-quality gates
                                                           -> Market entry or terminal skip
  -- apex reached without entry --------------------------> EXPIRED_AT_APEX

CONFIRMATION MARKET PATH
  -- RR < 1.0 -------------------------------------------> SKIPPED_POOR_RR
  -- reward < 1% ----------------------------------------> SKIPPED_LOW_REWARD
  -- gates pass + Market fill ----------------------------> ENTRY_FILLED
```

The lifecycle names above are conceptual design labels unless already present in the common architecture. Exact runtime state/enum naming is deferred until implementation authorization.

## 10. Direction symmetry

All accepted LONG mechanics are mirrored for SHORT unless an explicit direction-specific rule is stated.

LONG / Falling Wedge uses the upper boundary and Buy entry semantics.

SHORT / Rising Wedge uses the lower boundary and Sell entry semantics.

## 11. Prototype risk-limit scope

Robot v0.1 PAPER prototype currently has:
- no daily loss-limit stop;
- no entry block based solely on a sequence of STOP losses.

These omissions are prototype-only and must not be carried into future LIVE behavior without separate explicit authorization.

# END_OF_DOCUMENT
