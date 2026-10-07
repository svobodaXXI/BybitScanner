# Wedge Geometry Contract — Owner Authority — 2026-10-07

Status: ACTIVE OWNER AUTHORITY for future Wedge geometry correction work.

Scope: Scanner geometry for Falling Wedge and Rising Wedge. This document consolidates
the owner's current wedge-geometry rules into one contract so future work does not
reconstruct them from scattered screenshots or backlog notes.

This contract is about formation construction, validity and geometry-derived target
measurement. It does not authorize any LIVE trading change and does not define Robot
risk, order sizing, re-entry or protection behavior except where a geometry-derived
level must be consistent with the accepted wedge.

## 1. Construction order is structural, not best-fit-first

Build the wedge from the structural pivot chronology first. Classification and scoring
come after the admissible structure exists.

The required high-level sequence is:

1. identify the preceding directional impulse;
2. freeze the reversal extremum that terminates that impulse as the first wedge anchor;
3. take the immediate neighboring confirmed pivot on the opposite side as the second
   anchor;
4. continue through the local alternating pivot sequence without skipping an
   intermediate opposite extremum;
5. establish the two wedge boundaries from structurally admissible same-side pivots;
6. validate the strict boundary against the required controlling extremum and every
   relevant same-side wick/extremum;
7. only then classify/rank the formation and derive its potential/TP from the accepted
   geometry.

A later prettier line fit, higher score or better convergence may not replace this
chronology.

## 2. First anchor: impulse-ending reversal extremum

For every corrective wedge, the first anchor is the extremum that terminates the
preceding directional impulse.

For a corrective Rising Wedge after a strong decline:
- the first anchor is the lowest reversal extremum that ends the decline and begins
  the correction;
- do not crop the formation to a later local low merely because the later subset fits
  a cleaner wedge.

For a corrective Falling Wedge after a strong rise, mirror the rule:
- the first anchor is the highest reversal extremum that ends the rise and begins the
  correction.

If the preceding impulse and its terminal reversal extremum cannot be established from
the source-time pivot/candle evidence, do not invent a later start.

Owner reference: CASHCATUSDT 5m.

## 3. Anchor adjacency: no skipped opposite extremum

An anchor transition is admissible only between neighboring opposite extrema in the
chronological confirmed-pivot sequence.

If the current anchor is a HIGH:
- the next opposite anchor must be the immediate next confirmed LOW.

If the current anchor is a LOW:
- the next opposite anchor must be the immediate next confirmed HIGH.

It is forbidden to choose a farther opposite pivot while another confirmed opposite
extremum lies between the two selected anchors.

This is a hard validity gate, not a score penalty.

Owner reference: CAPUSDT 5m.

This rule refines the older wording "next meaningful confirmed opposite-side pivot":
for Wedge geometry, "next" means the immediate chronological neighboring opposite
confirmed pivot unless the nearer point is not a valid confirmed pivot under the
shared pivot primitive itself.

## 4. Strict boundary: mandatory controlling extremum

A strict wedge boundary may not float through empty space near the apex.

For a Falling Wedge:
- the upper boundary is the strict boundary;
- it must pass through the relevant upper pivot immediately preceding the final lower
  extremum before the apex.

For a Rising Wedge, mirror the rule:
- the lower boundary is the strict boundary;
- it must pass through the relevant lower pivot immediately preceding the final upper
  extremum before the apex.

The controlling pivot is structural evidence for the boundary, not an optional visual
touch.

Owner reference: POWERUSDT 5m.

## 5. Strict boundary containment: zero protrusions

The strict boundary permits no relevant wick/extremum protrusion beyond it.

For a Falling Wedge:
- no relevant candle high / upper wick / confirmed upper extremum may lie above the
  accepted strict upper boundary over the wedge episode.

For a Rising Wedge:
- no relevant candle low / lower wick / confirmed lower extremum may lie below the
  accepted strict lower boundary over the wedge episode.

After fitting the boundary through the mandatory controlling extremum, every earlier
relevant same-side extremum must lie on the line or inside the wedge. Any protrusion
outside the strict boundary invalidates the candidate.

This is a hard structural gate. It is not an ATR-tolerated soft score downgrade for
the strict side.

Where older containment documents allow soft body/ATR penalties on the same strict
wedge boundary, this 2026-10-07 owner rule supersedes them for future Wedge geometry
implementation. Historical documents remain evidence of earlier policy, not current
authority on this point.

## 6. Opposite boundary and convergence

The opposite wedge boundary must still be supported by real pivots belonging to the
same local episode and must form a converging wedge with the strict boundary.

Do not admit:
- a boundary supported only by extrapolation with no structural pivot support;
- a pair of lines whose apparent convergence depends on skipped pivots;
- a local subset that discards the true impulse-ending start to improve fit;
- a wedge whose apex/shape is produced by lines unrelated to the actual alternating
  extrema.

Existing confirmed-pivot, convergence, freshness and source-time requirements remain
in force unless they conflict with a stronger rule in this contract.

## 7. Corrective impulse context is part of selection

A wedge is not selected as an isolated attractive polygon.

When a strong directional move precedes the formation, the selector must preserve the
relationship:

preceding impulse -> terminal reversal extremum -> corrective wedge.

Impulse context may help rank between otherwise valid candidates, but it may not relax
the hard rules above. A candidate with invalid anchor adjacency or invalid strict
boundary is rejected regardless of score or contextual attractiveness.

Do not add coin-specific thresholds to encode this rule.

## 8. Wedge base, potential and TP must be one measurement

The wedge potential is measured from the accepted wedge base. The displayed potential
percentage and the plotted TP must derive from the same frozen base measurement.

For an accepted wedge:
- establish one authoritative base span from the accepted geometry at the formation
  base;
- use that same span for the wedge potential calculation and the TP displacement;
- do not calculate the caption from one geometry/span and draw TP from another;
- do not substitute a wider historical range, unrelated swing or later refit.

If a valid base span cannot be established from the accepted wedge geometry, do not
publish an inflated or guessed TP; reject the target calculation or mark it
unavailable according to the existing presentation contract.

Owner reference: CTUSDT 1m Falling Wedge.

## 9. Hard gates versus ranking

The following are HARD REJECT conditions:
- first anchor is not the impulse-ending reversal extremum for the owned corrective
  episode;
- selected opposite anchor skips an intermediate confirmed opposite pivot;
- strict boundary does not pass through its mandatory controlling extremum;
- any relevant same-side wick/extremum protrudes outside the strict boundary;
- a boundary lacks real structural pivot support;
- the accepted wedge base cannot be reconciled with the geometry used for potential/TP.

Ranking/scoring may choose among candidates only after all hard structural gates pass.
A 100/100 score cannot rescue invalid geometry.

## 10. Symmetry

Every directional rule in this contract is mirrored:
- Falling Wedge: strict upper boundary, corrective context typically after a rise for
  the first reversal high, converging downward structure;
- Rising Wedge: strict lower boundary, mirrored reversal/containment logic.

Do not implement one direction with a weaker structural standard than the other.

## 11. Regression references

The minimum owner-reference set for implementation is:
- CAPUSDT 5m — reject non-adjacent opposite-anchor selection;
- CASHCATUSDT 5m — first anchor must be the impulse-ending lowest reversal extremum
  for the corrective Rising Wedge;
- POWERUSDT 5m — reject a strict upper boundary that misses the controlling upper
  extremum / floats near the apex; reject strict-side protrusions;
- CTUSDT 1m Falling Wedge — potential and plotted TP must equal the same wedge-base
  measurement.

Future owner-confirmed cases should be added to the Geometry Gold/reference set rather
than replacing these cases.

## 12. Implementation boundary

Apply fixes as bounded defect-class slices:
1. pin the owner reference at source-time;
2. add a focused RED regression;
3. implement the smallest general rule;
4. verify the reference plus accepted positive controls;
5. merge only when no valid case regresses.

Do not solve these requirements by:
- ticker-specific exceptions;
- arbitrary score thresholds;
- retrospective re-anchoring;
- presentation-only line movement while the underlying candidate remains wrong;
- broad parameter sweeps before the structural contract is implemented.

Related execution requirements such as structural STOP placement and bounded Robot
re-entry are tracked separately in BACKLOG.md and are not geometry admission rules.
