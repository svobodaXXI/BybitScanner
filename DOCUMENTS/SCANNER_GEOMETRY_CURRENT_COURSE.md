# Scanner geometry — active rule and short work index

Status: ACTIVE; owner-defined wedge START is normative. Updated: 2026-09-23.
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

## Current state — after PR #191

- **Implemented on main:** PR [#191](https://github.com/svobodaXXI/BybitScanner/pull/191)
  merged as `3cfaea3` (2026-09-22): chronological A/B, B = next confirmed
  opposite pivot, A = extreme of its local leg, C = next confirmed same-side
  pivot, and `abs(P[C]-P[B]) < abs(P[B]-P[A])`. Invalid wedge pairs are
  rejected before ranking; the remaining existing candidate pool competes.
  Triangles are unchanged. Historical INJ/XRP/AAVE expectations were updated:
  their old wedges violate the rule; no confirmed wedge remains on those saved
  windows. Focused checks were completed in PR #191; do not repeat them without
  a relevant code/input change.
- **Remaining gaps (not implied to be solved by #191):** a local extreme is
  not necessarily the end of the *preceding directional impulse*; a regular
  countertrend swing can pass the local A/B/C checks. Also, the existing
  `geometry/candidate.py` generator requires `min_line_span=30`, and
  `geometry/filter.py` retains the 50 lowest-error lines **before** A/B/C
  admission; an otherwise valid local start can be absent from that pool.
  This is a proven pipeline limitation, not proof that a particular missing
  wedge exists. The current `geometry/pre_pattern.py` fixed-lookback close
  direction is context evidence, not independent impulse/episode proof.
- **Prior research, not production:** draft [PR #156](https://github.com/svobodaXXI/BybitScanner/pull/156)
  has source-time swing/episode shadow helpers and saved CRCL/0G/CRV controls.
  Reuse only compatible, independently verified minimal pieces; do not merge
  that 24-file draft wholesale or treat its shadow verdicts as trade admission.

## Implementation route — four dependent, bounded slices

**S1 — Prove the preceding impulse and own the initial episode.**
Use already saved as-of-closed OHLC and confirmed pivots to distinguish
(a) a preceding UP/DOWN directional impulse ending at A, from (b) an ordinary
countertrend or unproven swing. Check the previous opposite-side origin and
preceding same-side structural extreme, plus the local leg and A/B/C already
enforced by #191. An A beyond an earlier same-side structural extreme is useful
evidence, **not yet an owner-approved universal higher-high/lower-low gate**:
such a gate could lose genuine corrective/decelerating wedges. Explicitly keep
`UNKNOWN` when source history, pivot confirmation, episode separation or
intrabar ordering is insufficient; do not relabel an unproved countertrend leg
as an impulse. First resolve this discriminant on **one saved positive and one
saved negative** with their original as-of timestamps and no future bars.
Then add only the minimum wedge-specific source-time criterion justified by
those results; if the examples cannot distinguish the cases, report the single
missing fact and stop rather than inventing a threshold or running a broad
research campaign. **Done:** the chosen positive and negative produce the
expected impulse/episode verdict without changing the confirmed owner A/B/C
rule; no retrospective change to already frozen decisions.

**S2 — Make the admissible local start reachable by the generator.**
Only after S1's start criterion is established, enumerate confirmed A/B/C
starts within their local episodes before line fitting/ranking; reuse existing
`geometry/candidate.py` and `geometry/evaluation.py` for subsequent line
anchors and validation. Do not let the global error-first top-50 truncation
silently discard an otherwise eligible episode; retain a bounded search scoped
to viable episodes rather than globally disabling resource limits. Examine
`min_line_span=30` only if an already saved, rule-valid local candidate is
demonstrably excluded by it. No arbitrary new line-span or scoring thresholds.
**Done:** one saved eligible local start previously absent from the candidate
pool can reach ordinary geometry admission, while one saved invalid start
still cannot; if no such reproducible positive exists, report that evidence
gap rather than claiming recovered detection.

**S3 — Wire episode-scoped wedge candidates into the existing selector.**
Admit and rank *only* fully validated wedge candidates from S1/S2 using the
existing body-fit, convergence, freshness and A/B/C gates. Keep triangle
generation/selection and its contracts unchanged; if the shared geometry
winner hides an independently admissible wedge behind a stale triangle,
make the smallest wedge-only selection/interface correction rather than adding
another Geometry Engine. Assign historical START from the proven episode,
not by moving it to improve line fit or chart presentation. Keep corrective vs
decelerating subtype classification separate from A/B/C order; do not change
Robot, PAPER/LIVE execution, strategy, sizing, STOP/TAKE or running services.
**Done:** an offline production-path check on the saved target yields the
verified local wedge or an explicit no-wedge reason; triangles remain
unaffected. Any execution-path integration needs separate authorization.

**S4 — Focused acceptance and stop.**
Use the existing saved source-time positive/negative controls, one
prefix-vs-future check for newly changed source-time behavior, and the
smallest tests required by the actual delta. Inspect resulting chart anchors
on saved real cases where source-time/user alignment is available. Do not
refetch BONK, repeat unchanged #191 checks, sweep parameters, run the whole
Scanner or restart Scanner/Robot/backend/Telegram for reassurance.
**Done:** correct impulse → A → B → C → local boundaries and START are
demonstrated without hindsight, and changed-path regression is green.
Real Scanner/PAPER Robot rollout and live operational acceptance remain
separate, explicitly authorized steps.

**Next action, without a new owner handoff:** S1 only — reuse the current
main implementation and existing saved positive/negative evidence to isolate
one concrete impulse-vs-countertrend discriminator at historical as-of. Do
not start S2 or broaden research before this bounded result. For any new chat,
`AGENTS.md` already routes wedge work to this section; reread applicable
current protocol once per session, not historical handoff notes by default.

## Open only the evidence needed for the current task

| Need | Existing owner/evidence | Read policy |
| --- | --- | --- |
| Current code behavior | `geometry/engine.py`, `geometry/evaluation.py`, `geometry/pair_metrics.py`, `geometry/candidate.py`, `geometry/filter.py`, `geometry/pre_pattern.py`, `pivots.py` | Read affected functions, not all files by default. |
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
