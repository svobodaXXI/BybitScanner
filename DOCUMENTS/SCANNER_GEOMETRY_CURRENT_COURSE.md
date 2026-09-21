# Scanner geometry — current corrective course

Status: ACTIVE WORKING PLAN (not a detector contract or implementation authorization)
Date: 2026-09-21
Scope: BybitScanner 5m Wedge/Triangle geometry; historical acceptance before any new full Scanner pass.

## Why this record exists

The 2026-09-21 full Scanner pass exposed wrong local selections and boundary anchors. Repeatedly adding global gates without first checking candidate generation can suppress signals without finding the correct structure. This document records the current sequence and the evidence required to change it; read it at the start of the next Scanner-geometry task. Do not treat this as approval to override existing contracts or as proof that the proposed late line is valid.

## Known integrated state

- PR #173: candidate ranking incorporates freshness and body-zone breach counts.
- PR #175: approved chart header format implemented.
- PR #176: locality admission at 0.60 of analysed window, merged at 998481c65c9f9b8ddcbc4baecc862e4857213651; TOSHI/XEC long structures no longer emit the same signals.
- The local main was confirmed synced to this commit before this plan was recorded; verify current Git state before future operations, do not assume it remains so.
- Scanner was intentionally stopped by the user due to faulty signals. The ignored local start_runtime.local.bat was prepared with both Ikigai Box opt-in flags for the next start. Do not restart Scanner, Robot, PAPER backend, or Telegram Monitoring as part of geometry development.

## Reproduced observations and limitations

- AAOI, exact 200-candle window: after #176 the selected 95–196 triangle has extensive body breaches (offline measurement approximately 0.50 over its evaluated span); there is no acceptable fresh/local alternative in the inspected candidate pool. Simply declaring rising high→low sequences CANONICAL would instead prefer the 78/85 rising wedge with *more* breaches, without a meaningful preceding impulse. Do not make that change.
- AAVE, exact historical window: the 136–195 CANONICAL falling wedge has eight consecutive late upper-body breaches (176–183). Pivot highs 179, 189, 195 are approximately collinear under the existing 0.6% pivot-line tolerance, but candidate.py requires primary→secondary index separation >=30; 179→189/195 spans 10/16, so no line anchored at 179 is generated. This is a *candidate-generation gap*, not yet proof that pairing the late upper line with a lower line forms a valid wedge.
- A 31-window offline sample found a separation between body-breach ratios ~0.32 and ~0.44 among confirmed winners. A proposed 0.35 gate suppresses AAOI/FIL/ADA in that sample but does not repair AAVE. A consecutive-run gate that rejects AAVE suppresses many other signals. This small selected sample does not establish a generally calibrated threshold. Preserve measured evidence; do not present candidate thresholds as universal.
- Historical windows/scratchpad artefacts are local. Never invent a repo path for AAOI/AAVE or replace the exact historical reproduction with today's candles. Existing tracked TOSHI/XEC fixtures and the user-owned ignored debug/runtime artefacts must be preserved.

## Current order of work and acceptance

### 1. Integrate the evidenced containment interval correction (PR #178)

The AAVE 179→189/195 what-if produced a validated local Falling Wedge with lower
anchor 145 and one post-END breach, but its EXPLORATORY mode loses to the
existing 136/140 CANONICAL pair with eight late upper-body breaches. A global
min_line_span 30→10 what-if across the same 31 saved windows changed nine
winners, left detected=True at 27, did not repair AAVE and degraded XRP
(15 breaches inside the new winner, two after END). **Do not extend the
generator or mechanically upgrade anchor_sequence.**

A bounded production-pool comparison found eight of 27 fresh-window winners
differing from the cleanest full-formation alternative. A blanket
containment-before-CANONICAL swap is also unsafe: on PONS it would select
a triangle with 17 full-formation breaches rather than the existing winner
with two. The present cached body metric conflates unsupported prefix
START..common_start-1, common two-boundary interval common_start..END and
post-formation END+1..current.

The scoped correction is to preserve common_start..current for legacy
candle_containment and structural support; calculate the candidate-selection
body metric on common_start..END, and record START..END separately as a raw
full-formation diagnostic. Do not route the unsupported prefix diagnostic
into ranking, CANONICAL, detection or quality penalties. Preserve the
approved soft-penalty/no-hard-gate decision and disabled containment switch.
PR #178 (`fix/scanner-formation-containment-interval`) implements this
separation. Local Codex verified the code at `4930ebc`: 43 focused tests
passed, 31/31 saved windows and 3,587 candidates compared, AEVO/INJ retained
their winners, and JTO no longer loses due to four post-END breaches. Seven
winners changed (APT, ATOM, JTO, NIL, POL, PTB, WLD), while confirmed
detection remained 27/31. POL changes Triangle -> Rising Wedge and its raw
full-formation breach count increases 13 -> 32. This number **alone** cannot
establish a regression: it includes the unsupported one-boundary prefix.

**Only remaining pre-merge check:** use the existing POL snapshot and diagnostic
artifacts to distinguish unsupported prefix from common_start..END breaches,
and compare actual boundary support, envelope width and shape credibility.
A genuine supported-interval regression requires a scoped fix in the same PR;
otherwise merge after the existing focused evidence, with no repeat of the
31-window experiment. Do not restart Scanner, synchronize the user's dirty
Windows checkout, or open another geometry PR before this checkpoint.

### 2. Correct local boundary selection, then evaluate signal admission

**Next mission after PR #178:** reliably select a *supported local* wedge or
triangle instead of merely the highest-ranked valid pair. AAVE remains
unrepaired: the late 179→189/195 upper line can pair with lower anchor 145
as a valid local EXPLORATORY Falling Wedge, but it loses to the old CANONICAL
136/140 winner with eight consecutive upper-body breaches. The short-span
generator change alone was measured and rejected. AAOI still has no
acceptable local alternative in its observed pool. Do not relaunch these
completed hypotheses as exploratory default work.

Use the existing supported-formation breach metric (`common_start..END`),
pivot-support evidence, envelope width and shape validity to determine the
*smallest failing selection or candidate-admission boundary* on AAVE and
one relevant counterexample (AAOI/POL, as evidence requires). Do not optimize
for keeping `detected=True` at 27/31: unchanged detection does not prove
unchanged signal quality. In particular, a zero-breach but extremely wide
backward-extrapolated envelope is not a verified local formation.

Explicitly keep three distinct concerns:
- **Geometry integrity:** actual anchor support, line/candle intersections,
  interval ownership, compression and credible envelope width.
- **Historical formation state:** confirmed pivots and original frozen
  as-of/END remain historically true even if the current detector later
  rejects a stale or broken setup; no future candles may confirm a pivot
  at an earlier decision point.
- **Actionable signal:** existing Validation/freshness, pattern and trading
  quality policies remain independently enforced; a visually nice line does
  not authorize a Robot trade.

Fix a demonstrated candidate-selection/anchor problem before tuning arbitrary
global breach thresholds. Neither globally lowering min_line_span nor
reordering CANONICAL ahead/behind breaches is authorized by the current
evidence. Do not promote an EXPLORATORY line to CANONICAL merely to make it win.

**Contract boundary:** `DOCUMENTS/SCANNER_GEOMETRY_ATR_CONTAINMENT_DECISION.md`
currently prescribes soft quality penalties and no new hard containment
reject; its evaluator is currently disabled and Rising Wedge / Triangle
Compression have no corresponding penalty. Never silently turn a raw
diagnostic or ranking metric into a hard gate, enable the penalty, or alter
Robot admission. If a verified malformed shape requires absolute rejection
with no acceptable alternative, establish and approve the narrowly owned
geometric-integrity/decision-contract change before implementation; keep
signal suppression distinct from downgrading trade-quality tiers.

The existing 31-window sample already covered PR #178. Reuse its saved
snapshots and prior candidate evidence for focused changes; reserve a distinct
historical period for a *new calibrated numeric threshold* only if one
actually proves necessary. Do not introduce the proposed
`GEOMETRY_MAX_BODY_BREACH_RATIO=0.35` on the selected sample alone.

### 3. Wedge subtype and anchor sequence

After reliable boundary selection, distinguish corrective vs deceleration wedges using an evidenced preceding impulse *and* chronological pivot order. For rising deceleration: impulse-ending high then later opposing low; do not upgrade every high→low candidate to CANONICAL. Preserve distinct corrective logic and triangle behavior. Use real positive and negative examples rather than calibrating on the sideways AAOI interval.

### 4. Acceptance and deployment

Use the few frozen positive/negative cases relevant to each demonstrated
defect, plus one affected counterexample, before a bounded historical replay
of any changed winners/signals. Include actual selected anchors, containment
and envelope width (not just the count of detected signals). Confirm that
each candidate uses only pivots confirmed by its original as-of candle and
that the same as-of decision does not depend on later history. Preserve
historical confirmation separately from current actionable status.

One logical change per GitHub branch/PR; keep review fixes in the existing
PR. After required focused evidence passes, merge on GitHub and safely sync
the local main without altering user-owned dirty/untracked files. A single
approved full Scanner acceptance follows *the geometry-selection fix*, not
every diagnostic or PR. Before launching, inspect the actual launcher
dependency/side-effect chain: start_scanner.bat may also start the PAPER
backend and Telegram Monitoring. No implicit Robot/LIVE activation, trading
policy change, or unauthorized Telegram alerts.

## External reference reuse — scoped adaptation (reviewed 2026-09-21)

- **pytrendline** — https://github.com/ednunezg/pytrendline
  (ADAPT): pivot-count/support requirements, point-to-line error and
  candle-body intersections are separately configurable in its trendline
  detector. Reuse the *separation of evidence* with our existing geometry
  and ATR metrics; do not import its exhaustive O(N^3) search, default
  breakout rejection or arbitrary tolerances. Post-END breakout/retest is
  not historical formation damage in BybitScanner.
- **Stock Indicators, Zig Zag** —
  https://python.stockindicators.dev/indicators/ZigZag/
  (ADAPT): its last Zig Zag segment can redraw as later quotes arrive.
  Protect our decision-time pivot-confirmation cursor/frozen as-of boundary;
  verify this in focused replay, without replacing the pivot engine.
- **vectorbt splitters** — https://vectorbt.dev/api/generic/splitters/
  (DEFER): separate parameter-development and later historical validation
  periods if calibrating a new global threshold. Do not add a framework
  or run broad optimization merely for this scoped geometry repair.

These references supply engineering patterns, not trading performance
evidence or authority to change BybitScanner detector/risk contracts.

## Course correction and time economy

**Top priority: minimize the user's time and manual involvement**, not merely minimize calendar time to a working Scanner or the number of engineering steps. Prefer completing repository inspection, source/document edits, GitHub PR review/publication and available verification autonomously. Use local Codex only for host-local evidence or execution unavailable to the assistant; when indispensable, bundle independently safe related checks into one copy-ready prompt and reuse its outputs instead of asking the user to relay many small reports. Never replace necessary safety/accuracy checks with risky shortcuts, and request user decisions only when truly required by strategy/risk, approval, or host-local access.

Before any geometry micro-slice, consult this document, the current repository state, and only applicable scoped authority. Reuse earlier measurements; do not repeat full scans or create new infrastructure as a default. If stronger evidence or a better implementation route appears, compare it against the acceptance criteria, side effects, and existing architecture; revise **this document in the same scoped PR before/alongside changing direction**, noting why the former approach was discarded. Distinguish a working plan from an approved design/contract; do not quietly override authority. Ask the user only for material strategy/risk or otherwise consequential choices and host-local actions that available tools cannot perform.
