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

## Closed experiments and current checkpoint (2026-09-21)

- PR #178 is CLOSED WITHOUT MERGE. It separated `common_start..END` for selection from `START..END` for diagnostics. JTO improved by excluding post-END price action, but POL then selected a Rising Wedge with 22 upper-boundary breaches in its anchored prefix. A proposed per-boundary prefix correction fixed POL but moved the committed AEVO reference (START 95 -> 102, three fixture failures) and replaced WLD's tighter local wedge with a broader, lower-score triangle. Neither code variant is accepted. Keep main's current metric and explicitly retain these findings as evidence, not as an implementation contract.
- The local AAVE 179->189/195 line was already paired and tested: a valid local EXPLORATORY Falling Wedge with lower anchor 145 lost to the existing CANONICAL U136/L140 candidate with eight late upper-body breaches. A global min_line_span 30->10 what-if across 31 saved windows did not repair AAVE, changed nine winners and degraded XRP. Do NOT repeat the experiment or lower the global generator span.
- The existing 31-window comparison, POL/AEVO/WLD postmortems and saved historical snapshots are the starting evidence, not a request to rerun an all-window investigation. Current Scanner remains stopped due to unreliable geometry. Keep unrelated Windows files, Robot/PAPER/LIVE state and Telegram delivery unchanged.

## Current order of work and acceptance

### 1. One bounded geometry-selection correction, not another interval/ranking campaign

Use AAVE as the target and POL, AEVO, WLD and XRP as **existing counterexamples**. The result must choose a genuinely supported local formation or explicitly leave the case unresolved; preserving `detected=True` is not an acceptance condition. Do not change global generator spacing, blindly privilege CANONICAL or raw breach counts, or tune a coin-specific threshold.

First identify the actual existing decision boundary that promotes an invalid line pair: assess primary/secondary pivot support, candle-body intersections **where the respective boundary is applicable**, the claimed START/END, envelope width relative to price action and the established structural checks. Keep confirmed pivots and historical as-of distinct from later price movement. Use the current metrics and evaluator; do not add an alternate trendline/pivot engine, a parallel ranking system or speculative pattern-specific exceptions.

The next implementation is authorized only after one concise, evidence-backed candidate correction explains AAVE and does not repeat the known POL, AEVO, WLD or XRP regressions. If that condition is not met with the existing snapshots, stop the change rather than create another multi-stage diagnostic campaign. If the actual fix requires a new hard containment gate or reinterpretation of existing soft-penalty policy, resolve the owning `DOCUMENTS/SCANNER_GEOMETRY_ATR_CONTAINMENT_DECISION.md` approval boundary before code changes.

### 1b. RESOLVED 2026-09-21: boundary-validity admission implemented

The bounded review finished. The decision boundary responsible for AAVE was not
the ranking order but a missing admission condition: nothing rejected a boundary
contradicted by its own evidence. AAVE's upper line is contradicted at bar 179
(pivot 0.909% outside, body breaching the same line, inside the 176-183 run),
16 bars before END 195; POL is the same class at bar 178.

An unscoped version of the rule was measured and rejected because it also
removed PONS, whose only contradiction sits at bar 193, seven bars AFTER its
END 186 - a legitimate post-completion breakout. Scoping the check to bars no
later than END preserves PONS with its original winner and still rejects AAVE
and POL. A pivot-only variant was also rejected: it removed INJ, whose lower
pivot at 172 is 1.422% outside yet has zero body breaches, so no pivot-only
metric separates INJ from AAVE.

The narrow exception is recorded in
`DOCUMENTS/SCANNER_GEOMETRY_ATR_CONTAINMENT_DECISION.md` ("Approved narrow
exception - 2026-09-21"); the soft-penalty/no-generic-hard-containment policy
and the disabled evaluator are unchanged. Implemented in `geometry/engine.py`
as an admission step after the locality gate and before ranking, with focused
coverage in `tests/test_geometry_boundary_validity.py`.

AAOI remains a recorded caveat rather than a claim: its decisive bar 185 is 11
bars before END 196 and price never returns inside the lower boundary
afterwards, which is equally consistent with a late breakdown. AAOI is removed
by the rule, but that removal must not be presented as proof of an invalid
boundary. Breakout and END semantics were deliberately NOT redesigned here.

### 2. Execute and verify as one owned task

Choose direct GitHub authoring, local Codex or Claude Code case by case for the **least total user time** (prompt transfer, result relay, correction and verification included), not by a fixed tool preference. GitHub remains publication authority but need not be the editing engine. Give the local agent one task with implementation, focused fixture checks and a concise final report when local evidence is required. Reuse an existing PR for corrections to the same logical change; do not spread a single defect across serial PRs.

For the actual changed logic, assert the AAVE selected anchors/shape and inspect POL, AEVO, WLD and XRP from the existing saved inputs; cover post-END vs formation action and frozen as-of/pivot confirmation only when affected by the delta. Run the minimal affected focused tests **including existing AEVO fixture modules** rather than trusting a scoped harness PASS that missed them. Inspect any changed winner's actual shape, width and support instead of testing only detected-status parity. Do not rerun all 31 windows merely to check a documentation update or an unchanged algorithm; expand verification only when the changed selection has demonstrated broader effects.

### 3. Only after boundary selection: subtype, signal quality and launch

Once reliable local wedge/triangle selection is evidenced, distinguish corrective from deceleration wedges using preceding impulse and chronological pivots; do not relabel every convenient candidate CANONICAL. Historical formation status, geometry quality and current actionable signal are separate outputs. Do not turn diagnostic containment into a new hard signal gate or enable the currently disabled Falling-Wedge penalty, or add Rising-Wedge/Triangle penalties, without the applicable approved contract change.

After focused replay and tests, merge the scoped PR on GitHub, safely synchronize local main without disturbing user-owned tracked/untracked files, and perform **one** full Scanner acceptance with the user's explicit authorization and the launcher's real service/Telegram side effects checked. Do not start Scanner, Robot, PAPER backend or Telegram Monitoring during offline geometry work; do not change LIVE boundaries.

## External references — reuse, not engine replacement

Reviewed 2026-09-21 under `DOCUMENTS/EXTERNAL_REFERENCE_REUSE_POLICY.md`:

- pytrendline — https://github.com/ednunezg/pytrendline (ADAPT): separate pivot/point support, distance to trendline, candle-body crossings and near-duplicate line grouping. Use the *evidence separation* in our existing metrics and ranking; do not import its O(N^3) exhaustive search, default ignore-breakouts gate, or foreign thresholds.
- trendln — https://github.com/GregoryMorse/trendln (ADAPT): extrema and support/resistance lines are separate computations with bounded search windows and explicit fit-error diagnostics. Retain our pivot and candidate pipeline; consider de-duplicating equivalent lines only if measured candidate-pool redundancy becomes a real cost. No new Hough transform or replacement engine.
- Stock Indicators Zig Zag — https://python.stockindicators.dev/indicators/ZigZag/ (ADAPT): the latest pivot/segment may redraw when later bars arrive. Verify confirmed-as-of pivot ownership and frozen historical geometry without assuming that present-day extrema were available at signal time.
- vectorbt splitters — https://vectorbt.dev/api/generic/splitters/ (DEFER): use separate periods only when calibrating a new global threshold; no walk-forward framework or parameter hunt is justified for the current scoped defect.

These are engineering analogies, not evidence that another project's scoring, detector admission or trading policies are correct for BybitScanner.

## Course correction and time economy

**Primary priority: minimize the user's total time and manual work to a verified outcome**, including prompts, status relays, reviews and retries. Do not assume GitHub edits are faster than a single bounded local Codex/Claude Code task. Pick the route per task, reuse completed evidence and do not split independent checks into repeated user-mediated turns.

Before any geometry micro-slice, consult this document, the current repository state, and only applicable scoped authority. Reuse earlier measurements; do not repeat full scans or create new infrastructure as a default. If stronger evidence or a better implementation route appears, compare it against the acceptance criteria, side effects, and existing architecture; revise **this document in the same scoped PR before/alongside changing direction**, noting why the former approach was discarded. Distinguish a working plan from an approved design/contract; do not quietly override authority. Ask the user only for material strategy/risk or otherwise consequential choices and host-local actions that available tools cannot perform.
