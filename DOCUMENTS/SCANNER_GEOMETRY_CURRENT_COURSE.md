# Scanner geometry — active rule and short work index

Status: ACTIVE; owner-defined wedge START is normative. Updated: 2026-09-23.
Entry: [AGENTS.md](../AGENTS.md#active-scanner-geometry-course).
Scope: 5m Scanner wedge geometry and development of the separate L-shaped pattern.
This is a navigation/working index, not approval to change strategy, risk,
Robot/LIVE execution or running services.

**Owner's universal Scanner acceptance rule (2026-09-23):** for this L-shaped
pattern, every other new pattern, and every future Scanner correction, perform
a complete real Scanner pass on the entire available eligible symbol universe
before claiming owner visual acceptance. Short/sampled/offline checks may aid
development but never replace the full pass. Follow the safety and ordinary
delivery boundaries in [AGENTS.md](../AGENTS.md#scanner-visual-acceptance-full-passes-only--owner-rule-2026-09-23).

## Universal geometry-search invariant — OWNER AUTHORITY (2026-09-23)

**The search system must not generate geometry that violates the owner's
pattern definition.** Establish the correct local episode, impulse, START,
anchor chronology and pattern-specific structural conditions **during
candidate construction**, before line fitting, ranking or signal admission.
When that construction is not supported by source-time candles, emit no
candidate for the proposed episode; never build a malformed figure and then
mask it with score, Telegram or Robot filters. Fix reported false figures at
their earliest causative generation/anchor/geometry stage, not by moving
START or adjusting rendering, scores or chart windows. This is the
owner-expected end state for wedges, triangles, Ikigai Box, L-shapes and
every subsequent Scanner pattern. Refer to the prominent
[AGENTS.md rule](../AGENTS.md#geometry-construction-first--owner-defined-search-system-outcome-2026-09-23).

**Observed failure example:** B3USDT 5m triangle screenshot: a lower boundary
starts from the preceding rally while the displayed START and upper boundary
belong to the later local consolidation; this is an observed mismatch, not
a verified root-cause diagnosis without the exact frozen source candles.
APTUSDT wedge and ATHUSDT Box screenshots likewise require source-time
construction tracing. Pattern-specific candle-colour and setup-completion
rules belong to the owning specification; do not extrapolate one pattern's
constraints to another. A Robot trade's actual exit requires execution
evidence, not only an observed price touch.

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

## Active development priority — L-shaped formation, not wedge S1

**Owner direction (2026-09-23):** develop the preceding directional impulse
criterion **only within the new, independent L-shaped pattern detector**.
The wedge implementation route below is **DEFERRED**, including its S1
impulse/episode gate, candidate-generation expansion and Scanner integration.
Do not apply the L-shaped detector's impulse criterion as a new wedge
requirement or alter #191's universal wedge A/B/C rule during this work.
Sharing a proven future primitive with wedges would require a separate
scoped decision and validation.

**L-shaped geometry (pattern-specific, not an A/B/C wedge):** strong UP/DOWN
directional impulse from its source extremum to a new extreme, followed by a
short, narrow shelf near that extreme, with possible continuation. Keep LONG
and SHORT symmetric; pattern START is the impulse origin, not the shelf
start. Distinguish impulse evidence, shelf confirmation, and eventual
continuation instead of using later price action to retroactively validate
the original formation.

**L-shaped signal drawing — owner correction (2026-09-23):** no Fibonacci
levels or grid anywhere in this pattern's signal/preview. For the UP-impulse,
local-HIGH setup, show **only** (1) a horizontal rightward ray from the
impulse-terminal local HIGH at price H and (2) one horizontal potential-target
level T above H. Let L be the confirmed post-HIGH trough low of the same
formation, known on or before the signal's historical decision time. The
potential is the trough depth D = H - L, so **T = H + D = 2H - L**.
The ray and target use frozen H/L evidence available at signal time; do not
use later candles to redraw them retrospectively. This defines the requested
HIGH-first signal, not an extra wedge rule or automatic trade execution. Do
not add another visual overlay or invent an unapproved mirrored SHORT signal
formula while implementing this specific HIGH-first drawing. Do not infer a
universal numeric impulse threshold from one historical example.

**Implementation status (2026-09-23):** the detector and preview from the
isolated `C:\BybitScanner-lshape` checkpoint (`geometry/l_shape.py`,
`geometry/l_shape_preview.py`, `tests/test_l_shape_detector.py`,
`tests/test_l_shape_preview.py`) are published to GitHub `main` in
[PR #195](https://github.com/svobodaXXI/BybitScanner/pull/195), commit
`0d8966b`. The owner-corrected drawing above is implemented exactly:
`render_l_shape_preview()` draws only a dashed rightward ray at the confirmed
impulse HIGH `H` (`formation.impulse_high`) and one target level
`T = 2*H - L`, where `L = formation.shelf_low` -- already the detector's own
confirmed post-HIGH trough, read only up to `as_of_index`, so `T` is never
derived from a later candle. No Fibonacci levels or grid are drawn. This
applies to the UP-impulse/local-HIGH (LONG) case only; the SHORT preview is
unchanged and draws no target, since no mirrored formula is approved here.
12 focused tests pass (6 detector, 6 preview) -- reused, not rerun, when this
doc-only change is the only edit.

**Not yet implemented:** the preceding-impulse-vs-ordinary-swing distinction
this doc's "Next bounded step" originally called for. `detect_l_shape()`
still anchors the impulse at the most recent same-direction extremum inside a
bounded lookback (`geometry/l_shape.py`, `_last_index_of_min`/`_last_index_of_max`);
it does not yet prove that extremum ends a genuine preceding directional
impulse rather than an ordinary countertrend swing, the way #191 proves it
for the wedge A anchor. `LShapeFormation.start_index` is therefore not yet a
validated impulse origin.

**Next development step (unstarted):** add that preceding-impulse validation
inside the L-shaped detector, reusing already-available confirmed pivots and
candles exactly as #191 did for the wedge A/B/C rule, without importing or
altering the wedge's own A/B/C admission gate and without a new numeric
threshold invented from one example. Existing recorded visual reference
examples (SKHYNIXUSDT, RONIN) remain available for that step; do not invent
or refetch a historical signal snapshot.

## Deferred wedge implementation route — four dependent, bounded slices

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

**Resume boundary for this deferred wedge route:** do not begin wedge S1–S4
until the owner explicitly returns to wedge development. The active next step
is the L-shaped read-only checkpoint above. `AGENTS.md` routes both patterns
to this index; no chat handoff or repeated research is needed.

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
