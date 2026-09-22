# Scanner geometry — active rule and short work index

Status: ACTIVE; owner-defined wedge START is normative. Updated: 2026-09-22.
Entry: [AGENTS.md](../AGENTS.md#active-scanner-geometry-course).
Scope: 5m Scanner wedge geometry. This is a navigation/working index, not approval
to change strategy, risk, Robot/LIVE execution or running services.

## Universal wedge anchor rule — OWNER AUTHORITY

**For EVERY wedge:** preceding directional impulse → **first anchor is the
extreme ending that impulse** → **second anchor is the next meaningful,
confirmed pivot on the opposite side**.

After UP: terminal HIGH → next LOW. After DOWN: terminal LOW → next HIGH.
Both anchors belong to the same local formation episode and must have been
knowable at the historical decision time. First identify this chronological
start; then fit/validate the two boundaries using subsequent pivots. Rising vs
falling and corrective vs decelerating subtype are determined *separately* and
NEVER change first/second-anchor selection. Do not assign START retrospectively
from whichever two fitted lines have the highest score. If the required local
formation is absent or not confirmed, do not emit a wedge.

**Owner clarification — mandatory first-anchor criterion (2026-09-22).** With
A = first anchor, B = second anchor (the next confirmed opposite-side pivot)
and C = the next confirmed pivot on A's side after B:

    abs(P[C] - P[B]) < abs(P[B] - P[A])

If it fails, A was selected incorrectly: take the next admissible formation
start among the existing confirmed pivots/candidate pool and apply the same
full rule to it. Rejecting the pair A/B does not end the search, and A must
not be swapped for an arbitrary later pivot merely to pass the check. No
admissible start, or C not yet confirmed, means the wedge is not confirmed.

This section is the **only active wording** of the owner rule. The research
document in draft [PR #156](https://github.com/svobodaXXI/BybitScanner/pull/156)
links back here; any earlier subtype-specific START statements there describe
historical examples, not an alternative selection contract. Do not ask the
owner to restate this rule.

## Current state and next one bounded slice

- **Implemented on main:** candidate generation/ranking and measured
  own-anchor..formation-END body-fit gate; chart context from the earliest
  boundary anchor ([PR #186](https://github.com/svobodaXXI/BybitScanner/pull/186));
  triangle symmetric potential display ([PR #183](https://github.com/svobodaXXI/BybitScanner/pull/183)).
  The chart window is presentation only; it does not enforce the owner rule.
- **In PR #191 (not merged):** rising/falling pair admission requires
  chronological first anchor A, B = next opposite pivot, A the extreme of its
  leg from the previous opposite pivot to B, and the criterion above; failing
  pairs leave the pool and the remaining pool candidates compete under the
  same rule. Triangles are unchanged.
- **Not implemented on main:** source-time impulse-terminal/next-opposite-pivot
  episode ownership as a production wedge admission. Do not claim the
  universal rule is already enforced by the current detector.
- **Reproducible BONK negative:** original 1000BONKUSDT 5m as-of window
  0..198 reproduced the logged U81/L128, END191 rising-wedge winner,
  with 16/16 HIGH and 17/17 LOW pivots matching; last original index199
  was in progress. Body-fit found zero sustained/body breaches on both
  respective anchor..END intervals. U81 is after preceding impulse HIGH70;
  L128 belongs to the later recovery leg. The admitted pool has no
  rising-wedge pair anchored wholly in that recovery. A high score,
  candle containment or ranking cannot substitute for correct START.
  Do not fetch these candles or replay this selection again for reassurance.
- **Next:** implement the owner-defined universal first/second-anchor rule
  at the existing wedge candidate admission, reusing confirmed-as-of pivots
  and available price history. One focused BONK-negative + previously saved
  positive control proof; if an independently selected episode cannot be
  identified from existing evidence, report the precise input/implementation
  gap, not that the rule is unknown. No new thresholds, bulk parameter
  sweep, full Scanner acceptance, unrelated refactor, or runtime restart.

## Open only the evidence needed for the current task

| Need | Existing owner/evidence | Read policy |
| --- | --- | --- |
| Current code behavior | `geometry/engine.py`, `geometry/evaluation.py`, `geometry/pair_metrics.py`, `geometry/envelope_metrics.py`, `pivots.py` | Read affected functions, not all files by default. |
| Boundary/body tolerance decision and earlier failures | [SCANNER_GEOMETRY_ATR_CONTAINMENT_DECISION.md](SCANNER_GEOMETRY_ATR_CONTAINMENT_DECISION.md) — latest effective decision is “Approved bounded revision — 2026-09-22: sustained formation body mismatch”; older sections are historical and may be superseded. | Only for body/ATR scope. |
| Earlier boundary proposals | [SCANNER_GEOMETRY_BOUNDARY_VIOLATION_DECISION.md](SCANNER_GEOMETRY_BOUNDARY_VIOLATION_DECISION.md) | Historical proposal, **not** a second active gate. |
| Previous implementation/verification record | [CR-SCANNER-GEOMETRY-FORMATION-FIT-001.md](CHANGE_REQUESTS/CR-SCANNER-GEOMETRY-FORMATION-FIT-001.md), existing `tests/test_geometry_formation_fit.py` and scoped fixtures | Reuse passing evidence; retest only changed behavior. |
| Episode/pivot research and CRCL/0G/CRV saved controls | [draft PR #156](https://github.com/svobodaXXI/BybitScanner/pull/156), `DOCUMENTS/WEDGE_LOCAL_EPISODE_REFERENCE_AND_IMPLEMENTATION_PLAN_2026-09-20.md` **on that PR branch only** | Research-only; no automatic episode selector or production gate. Open only the applicable section, not its entire 697-line file or 24-file PR. |
| Scope and work cadence | [ASSISTANT_PROTOCOL.md](ASSISTANT_PROTOCOL.md) §3.2.1 and [GITHUB_FIRST_WORKFLOW.md](GITHUB_FIRST_WORKFLOW.md) | Short slices; no repeated diagnostics/checks without new evidence. |

## Documentation maintenance rule

Keep the universal rule here and route agents via AGENTS.md. Keep verified
historical decisions and regression evidence in their **existing** decision/CR
files; link rather than copying them into this index. Label superseded proposals
as historical instead of applying their old thresholds. Update only the
specific affected document and this short status when a real code/contract
change occurs. Do not create another geometry roadmap, status mirror, or
research log merely to record a completed micro-slice.
