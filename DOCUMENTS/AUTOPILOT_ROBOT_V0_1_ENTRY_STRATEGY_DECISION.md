# BybitScanner — Robot v0.1 entry strategy decision

Version: 1.2
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

## 6. Partial LIMIT fill completion and later top-up rule

A partial fill is treated as an active entry attempt for the same intended `1 WV` position, not as an automatically finalized reduced-size trade.

After the first authoritative partial fill, Robot allows the remaining quantity of the existing LIMIT order up to **10 seconds** to fill naturally.

If the full intended `1 WV` position is still not filled after those 10 seconds, Robot evaluates the current authoritative market price relative to the LIMIT entry price.

If the price has moved in the adverse/less favorable entry direction by **no more than 0.5%**, Robot completes the missing quantity to the original intended `1 WV` size using a Market order.

Before sending that Market remainder, the still-working LIMIT remainder must first be authoritatively cancelled or otherwise proven incapable of further fill through the shared order lifecycle. The Market completion quantity is calculated only from authoritative filled/remaining position state. Parallel exposure from a still-fillable LIMIT plus Market completion is forbidden.

Direction semantics:
- LONG: an upward move from the LIMIT price is adverse for the completion-price test; Market completion is allowed only while that deterioration is `<= 0.5%`;
- SHORT: a downward move from the LIMIT price is adverse for the completion-price test; Market completion is allowed only while that deterioration is `<= 0.5%`.

The 10-second wait and 0.5% maximum deterioration are accepted Robot v0.1 PAPER prototype strategy parameters and must be recorded in trade telemetry for later validation/calibration.

If, after the 10-second wait, adverse price movement is greater than 0.5%, Robot does **not** chase the remainder by Market. The unfilled remainder is cancelled/reconciled and the already-filled quantity remains as a valid reduced-size Robot position.

The reduced-size position may later be topped back up toward the original `1 WV` intended size if price returns to the admissible retest-entry zone before the frozen wedge apex. Such a later top-up is another exposure-increasing action for the same immutable trade idea, not a new trade idea or a new wedge instance.

Any later top-up:
- may use only the missing quantity required to reach, but never exceed, the original `1 WV` idea size;
- must use the same authoritative order lifecycle, fill state, sizing, and reconciliation rules;
- remains allowed only while the original frozen wedge instance is still alive and before apex;
- is blocked if the projected top-up would reduce the resulting whole-position expected reward/risk below `1.0`;
- may be reconsidered later if a more favorable price restores projected whole-position reward/risk to at least `1.0` before apex.

A later top-up must never widen the already accepted structural STOP away from the market. It may change authoritative average entry, actual filled size, and current PnL/risk metrics, but it does not create a new wider invalidation level.

No blind retry is allowed for LIMIT placement, LIMIT cancellation, Market completion, or later top-up. Ambiguous state remains fail-closed and must reconcile before any exposure-increasing action.

## 7. Confirmation Market entry path

The confirmation path remains available when LIMIT entry has not filled.

After a retest:
- LONG confirmation requires a closed 1m candle again above the frozen upper boundary;
- SHORT confirmation requires a closed 1m candle again below the frozen lower boundary.

A qualifying confirmation close authorizes consideration of Market entry; it does not bypass the accepted entry-quality gates.

If a Robot LIMIT is still active when the Market confirmation path becomes eligible, Robot must first make the LIMIT authoritatively cancelled/inactive through the shared lifecycle. Market entry must not be sent while the old LIMIT can still fill.

This is a single-entry invariant: the LIMIT path and confirmation-Market path are alternatives for one immutable Robot idea, never simultaneous independent entry attempts.

## 8. Entry-quality gates for confirmation Market entry and top-ups

Immediately before actual Market entry, Robot evaluates the trade using authoritative current price/state and the already accepted STOP/TAKE calculations.

Confirmation Market entry is allowed only if both conditions hold:
- expected reward/risk is at least 1.0;
- expected reward from the prospective entry to TAKE is at least 1%.

If reward/risk is below 1.0, the idea terminates without entry as `SKIPPED_POOR_RR`.

If expected reward is below 1%, the idea terminates without entry as `SKIPPED_LOW_REWARD`.

For a later top-up of an already partially filled position, the relevant admission check is the projected reward/risk of the **whole resulting position** after the proposed additional fill. If that projected whole-position reward/risk would be below `1.0`, the top-up is blocked while the existing partial position continues under its current protection and target policy.

These are Robot v0.1 PAPER prototype filters and may later be calibrated from collected data.

## 9. STOP after retest LIMIT entry

The accepted Robot v0.1 STOP anchor remains the breakout-candle extreme rather than a later retest extreme.

- LONG: preferred STOP = breakout candle low - 1 tick;
- SHORT: preferred STOP = breakout candle high + 1 tick.

If the distance from the actual authoritative entry/average entry to that preferred STOP exceeds 2%, the accepted initial-entry fallback is a fixed 2% STOP distance.

After a position exists, later top-up fills must **not** move the existing accepted STOP farther from the market merely because the authoritative average entry changes. Top-up is rejected if it would violate the admitted risk constraints; risk is not repaired by widening STOP.

Shared authoritative tick-size, order normalization, position state, and protection synchronization must be used.

## 10. TAKE for Robot v0.1 PAPER

Robot v0.1 PAPER uses the scanner-provided pattern potential from the immutable approved signal snapshot. The pattern target is therefore known before execution and is not re-derived by Robot.

The prototype target uses the accepted **90% realization of scanner pattern potential** rule. Once the target price for the approved signal/pattern instance is established from that frozen signal potential, subsequent partial fills, Market completion, later top-ups, or changes in authoritative average entry do **not** change that pattern target.

Those execution events change position size, average entry, realized economics, and current reward/risk, but they do not rewrite the scanner's original pattern potential or move the Robot v0.1 PAPER target because of a later fill.

This fixed pattern-potential target is specific to the Robot v0.1 PAPER prototype. Future LIVE management is governed by separately documented strategy policy and must not inherit this simplification automatically.

## 11. Apex termination

If the frozen wedge apex is reached before either:
- a valid LIMIT entry has filled; or
- a valid confirmation Market entry has completed,

then the idea expires without entry.

If a partial position already exists, apex ends any further entry/top-up opportunity for that wedge instance but does not itself close the already-open position. The existing position continues under its accepted STOP/TAKE management.

Conceptually an unfilled idea may be represented as `EXPIRED_AT_APEX`; exact implementation enum naming is deferred until an implementation specification is authorized.

The same immutable wedge instance must not reactivate or initiate a new trade later beyond its apex. A later Robot trade on the same symbol requires a genuinely new scanner pattern/signal instance.

## 12. Conceptual lifecycle

```text
WAITING_BREAKOUT
  -> qualifying closed 1m breakout candle
  -> WAITING_RETEST

WAITING_RETEST
  -> retest zone reached
  -> LIMIT_WORKING at frozen boundary

LIMIT_WORKING
  -- full fill ------------------------------------------> ENTRY_FILLED
  -- partial fill ---------------------------------------> PARTIAL_FILL_WAIT_10S
  -- 5 new closed 1m candles, still unfilled ------------> authoritative reposition
  -- confirmation close becomes eligible ----------------> cancel/reconcile LIMIT first
                                                           -> entry-quality gates
                                                           -> Market entry or terminal skip
  -- apex reached without entry --------------------------> EXPIRED_AT_APEX

PARTIAL_FILL_WAIT_10S
  -- remainder fills within 10 s ------------------------> ENTRY_FILLED at intended 1 WV
  -- 10 s + adverse move <= 0.5% ------------------------> cancel/reconcile remainder
                                                           -> Market complete to 1 WV
  -- 10 s + adverse move > 0.5% -------------------------> cancel/reconcile remainder
                                                           -> keep reduced-size position
                                                           -> LATER_TOP_UP_ELIGIBLE until apex

LATER_TOP_UP_ELIGIBLE
  -- price returns to admissible retest zone
     + projected whole-position RR >= 1.0 ---------------> top-up toward max 1 WV
  -- projected whole-position RR < 1.0 ------------------> no top-up; keep existing position
  -- apex reached ----------------------------------------> no further top-up; manage existing position only

CONFIRMATION MARKET PATH
  -- RR < 1.0 -------------------------------------------> SKIPPED_POOR_RR
  -- reward < 1% ----------------------------------------> SKIPPED_LOW_REWARD
  -- gates pass + Market fill ----------------------------> ENTRY_FILLED
```

The lifecycle names above are conceptual design labels unless already present in the common architecture. Exact runtime state/enum naming is deferred until implementation authorization.

## 13. Direction symmetry

All accepted LONG mechanics are mirrored for SHORT unless an explicit direction-specific rule is stated.

LONG / Falling Wedge uses the upper boundary and Buy entry semantics.

SHORT / Rising Wedge uses the lower boundary and Sell entry semantics.

## 14. Prototype risk-limit scope

Robot v0.1 PAPER prototype currently has:
- no daily loss-limit stop;
- no entry block based solely on a sequence of STOP losses.

These omissions are prototype-only and must not be carried into future LIVE behavior without separate explicit authorization.

# END_OF_DOCUMENT
