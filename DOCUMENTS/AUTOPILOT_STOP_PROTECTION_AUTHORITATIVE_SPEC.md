# AUTOPILOT STOP Protection — Authoritative Design Spec

Date: 2026-09-08
Status: ACTIVE / DESIGN COMPLETE
Implementation authorization: NONE

## 1. Scope

This document consolidates the accepted AUTOPILOT STOP-series protection and recovery rules. It is the authoritative design summary for implementation. Earlier decision notes remain historical evidence, but this document is the primary synthesis.

## 2. Qualifying completed trade

STOP/recovery accounting occurs only when the position lifecycle is fully closed.

Partial closes do not independently increment or decrement STOP/recovery counters.

When the position is fully closed, its final result is the cumulative realized result of the entire position lifecycle, including all partial closes and all actual fees/funding charged to that lifecycle.

Final net result classification:
- `> 0`: profitable completed trade;
- `= 0`: neutral / break-even;
- `< 0`: losing completed trade.

A qualifying STOP requires BOTH:
1. the final closing action that removes the remaining position is the protective STOP;
2. the cumulative final net result of the entire position lifecycle is `< 0`.

Therefore:
- a protective STOP that leaves the whole lifecycle net-positive is NOT a qualifying STOP;
- a lifecycle that is net-negative but whose final remainder was closed by strategy/manual/emergency/non-protective exit is NOT a qualifying STOP.

## 3. STOP score and recovery basics

A qualifying negative protective STOP contributes one STOP unit.

A profitable completed trade improves recovery according to the global/local rules below.

Break-even is neutral.

There is no rolling-window/frequency requirement.

When a relevant protection trigger actually fires, its relevant trigger counter resets to `0` and the next worsening step requires a fresh accumulation.

## 4. Pause ladder

STOP-protection pause is measured in closed candles of the strategy working timeframe.

Pause ladder:
`N -> 2N -> 3N -> 4N -> 5N ...`

`N` is NEEDS VALIDATION in PAPER.

## 5. Size ladder

Restriction ladder:
`100% -> 50% -> 25% -> 12.5%`

`12.5%` is the minimum size level.

Further worsening events at the floor do not reduce size further; they increase pause duration.

Recovery upward is gradual:
`12.5% -> 25% -> 50% -> 100%`

Each upward step requires exactly `5` recovery-progress units.

If a new STOP-protection trigger fires during recovery, the current recovery progress resets to `0` and ordinary worsening logic applies from the current internal recovery level.

## 6. Recovery-progress arithmetic

During recovery:
- profitable completed trade: recovery `+1`;
- losing completed trade: recovery `-1`, floor `0`;
- break-even: neutral.

An ordinary losing completed trade that is NOT a qualifying protective STOP does not increment the STOP trigger counter, but it still reduces recovery progress by `1`.

STOP trigger counters and recovery progress are separate state variables.

## 7. Local protection

Local protection is instrument-scoped.

Before the first local trigger on an instrument, LONG and SHORT maintain separate local STOP counters.

If either directional counter reaches `5` qualifying STOPs, local protection applies to the whole instrument, both directions.

After the first directional local trigger, the instrument enters aggregated local recovery. During aggregated local recovery:
- new qualifying STOPs from either LONG or SHORT worsen the instrument recovery state;
- profitable completed trades on that instrument improve local recovery;
- ordinary losing completed trades worsen local recovery progress;
- the whole instrument shares one effective local recovery restriction.

After full local recovery to `100%`:
- aggregated local recovery ends;
- separate LONG/SHORT counters resume;
- both directional counters restart from `0`.

A local trigger pauses only that instrument. Global AUTOPILOT may continue, subject to other restrictions.

Local STOPs still contribute to global statistics.

## 8. Global protection

Global protection uses:
1. an authoritative aggregate global STOP-score;
2. per-instrument contribution values used to validate current diversity/distribution.

These are intentionally allowed to diverge.

Global trigger requires BOTH conditions simultaneously at evaluation time:
- aggregate global STOP-score `>= 5`;
- current diversity/distribution is valid.

Diversity/distribution requirement:
- at least two distinct instruments must contribute;
- the second instrument must contribute at least `2` STOP units;
- therefore at threshold `5`, the minimum valid distribution is `3 + 2`.

Examples:
- `BTC=4, ETH=1, global=5` -> NO trigger;
- `BTC=3, ETH=2, global=5` -> trigger allowed;
- if global score is `<5`, no trigger even when contribution ledger still shows `3+2` or stronger.

A past threshold crossing does not latch. Trigger conditions must be valid at the current evaluation point.

When a real global trigger fires:
- global trigger counter/reset state is reset for the next cycle;
- local counters are NOT modified.

Global and local protections remain independent. Effective size restriction is the stricter of the two using `min`, never multiplication.

## 9. Global contribution arithmetic

On a qualifying STOP for an instrument:
- that instrument contribution `+1`;
- aggregate global STOP-score `+1`.

On a profitable completed trade when that instrument contribution is positive:
- that instrument contribution `-1`;
- aggregate global STOP-score `-1`;
- floors apply at `0`.

On a profitable completed trade when that instrument contribution is already `0`:
- instrument contribution stays `0`;
- aggregate global STOP-score decreases by `0.5`;
- no negative or hidden per-instrument credit is created.

Therefore aggregate global STOP-score may be fractional and may differ from the sum of current per-instrument contributions.

Global STOP-score floor is `0`.

If an instrument with contribution `0` later has a qualifying STOP after a previous zero-contribution profit credit:
- contribution changes `0 -> 1`;
- aggregate global STOP-score increases by `1`;
- no hidden `-0.5` must first be repaid.

Threshold logic uses aggregate global STOP-score, not the arithmetic sum of contributions.

## 10. Global recovery

Global recovery uses the same size ladder:
`12.5% -> 25% -> 50% -> 100%`

Each upward step requires exactly `5` global recovery units.

All profitable completed AUTOPILOT trades improve global recovery by `+1`, regardless of which instrument originally contributed to the trigger.

All losing completed AUTOPILOT trades reduce global recovery by `-1`, floor `0`, including non-STOP losses.

At full global recovery to `100%`:
- global recovery progress resets to `0`;
- global STOP counter/trigger-cycle state resets to `0`;
- next global protection cycle starts clean.

## 11. Midnight rule — 00:00 MSK

Trading-day boundary is fixed at `00:00 MSK`.

At midnight:
- active recovery restriction becomes one size level milder;
- if restriction is already `100%`, remaining recovery progress resets to `0`;
- when a one-level relaxation occurs, recovery progress resets to `0`;
- pause resets to base `N`;
- aggregate global STOP-score decreases by exactly `1`, floor `0`;
- per-instrument global contribution ledger is NOT changed by this midnight global decay.

Thus the divergence between aggregate global STOP-score and contribution ledger is intentional and preserved.

After midnight, global trigger still requires aggregate global STOP-score `>=5` AND valid current diversity. Contribution distribution alone never triggers protection.

## 12. Open positions during protection

A STOP-protection trigger does NOT force-close existing positions.

Protection blocks new risk and new entries as defined below. Existing positions continue ordinary management through STOP, TAKE, strategy exit, partial close, full close, and emergency exit.

All risk-reducing actions are allowed during STOP protection:
- partial close;
- full close;
- tighter protective STOP;
- TAKE/strategy/emergency exits.

Risk-increasing actions remain blocked.

A reversal is treated as close + new entry. During an active pause, closing is allowed but the opposite new entry is blocked unless emergency override explicitly removes the STOP pause.

## 13. STOP modification invariant

During STOP protection, protective STOP may:
- remain unchanged;
- move toward price if that reduces risk.

Protective STOP may NOT be moved farther away when that increases potential loss.

This prohibition remains active even during emergency override.

## 14. Emergency STOP override

Emergency override is specific to STOP-series protection.

Activation requires:
- separate emergency confirmation;
- explicit warning;
- audit/logging.

Override removes current STOP-series pause and STOP-series size restriction, but does NOT erase internal STOP/recovery state.

While override is active:
- effective STOP-related permitted size may return to normal `100%`;
- internal recovery accounting continues in the background;
- profitable/loss/break-even completed trades continue ordinary recovery arithmetic;
- midnight recovery relaxation still changes INTERNAL recovery state;
- if internal recovery naturally reaches `100%`, override ends automatically because nothing remains to bypass.

Override lasts only until the next NEW STOP-protection trigger. When a new trigger occurs, STOP protection re-engages from the CURRENT internal recovery state under ordinary worsening rules.

Override applies to all currently active STOP-series restrictions together; local/global STOP restrictions are not separately bypassed.

Override does NOT bypass independent risk circuits such as daily-loss protection or other Portfolio Risk Engine constraints.

## 15. Existing-position add-on prohibition

Emergency STOP override does NOT authorize increasing the size/risk of an already-open position.

During STOP protection or STOP override:
- existing position may be reduced or fully closed;
- protective STOP may be tightened;
- existing position may NOT be enlarged by averaging/add-on;
- after a partial close, previously removed size may NOT be restored;
- once the old position is fully closed, a later entry is a NEW position and may be allowed under override, subject to all other independent risk gates.

## 16. Interaction with Portfolio Risk Engine

STOP protection is only one risk layer.

Independent constraints remain authoritative, including accepted caps such as:
- per-asset hard cap: `2 WV`;
- aggregate AUTOPILOT cap: `19 WV`;
- correlation/regime/risk-engine restrictions;
- daily-loss blocker.

Emergency STOP override does not bypass these independent constraints.

## 17. NEEDS VALIDATION

The design is closed. The following numerical parameters are intentionally not finalized until PAPER evidence exists:
- base pause duration `N`;
- any daily-loss numerical thresholds/hysteresis values that belong to the separate daily-loss circuit;
- any strategy-specific calibration values not fixed by this STOP-protection architecture.

These are tuning/validation tasks, not unresolved architecture.

## 18. Design status

STOP-protection architecture is considered DESIGN COMPLETE.

Next phase:
1. implementation plan;
2. targeted tests for state transitions and edge cases already specified here;
3. PAPER validation of `N` and other tuning parameters;
4. LIVE enablement only after PAPER evidence and explicit acceptance.
