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

### 1. AAVE: make the missing late local line eligible, then evaluate it

Use the already recovered AAVE snapshot. First perform an isolated, read-only what-if: generate the upper candidate starting at pivot 179 with the **existing** pivot-line fit, tolerance, and forward confirmations; pair it through the normal evaluation, Validation, locality, freshness, classification, and ranking path. Report actual resulting lower anchor, pattern, mode, body breaches and detector decision. A plausible upper trendline alone is not enough.

Only if a correct pair survives, implement the smallest *scoped* change to the candidate generator to allow that late, adequately confirmed line. Avoid globally lowering DEFAULT_MIN_LINE_SPAN=30 or introducing a parallel Pivot/trendline engine. Verify effects on the saved sample and the earlier AEVO/TOSHI/XEC regression cases before publication. If no valid pair exists, stop: record the rejecting gate and reconsider the hypothesis rather than force a signal.

### 2. Absolute geometric admission, after the candidate-pool change

Rerun the same bounded offline sample after step 1. Evaluate absolute containment using existing body_zone_breaches and pivot-boundary metrics, rather than only relative ranking within a poor pool. Distinguish wrong anchors from a truly invalid shape; avoid duplicating the disabled wedge/integrity.py containment-penalty mechanism or silently overriding DOCUMENTS/SCANNER_GEOMETRY_ATR_CONTAINMENT_DECISION.md. If a new hard admission rule conflicts with that decision's soft-penalty/no-hard-reject boundary, update the owning decision/approval explicitly before code changes.

Do not implement GEOMETRY_MAX_BODY_BREACH_RATIO=0.35 solely on the 31-window sample. If still warranted, check a distinct historical period, effect on other patterns, absent/missing ATR data, and the precise denominator/index interval before selecting an operational threshold. With no acceptable candidate, return no confirmed signal; do not silently substitute another malformed figure.

### 3. Wedge subtype and anchor sequence

After reliable boundary selection, distinguish corrective vs deceleration wedges using an evidenced preceding impulse *and* chronological pivot order. For rising deceleration: impulse-ending high then later opposing low; do not upgrade every high→low candidate to CANONICAL. Preserve distinct corrective logic and triangle behavior. Use real positive and negative examples rather than calibrating on the sideways AAOI interval.

### 4. Acceptance and deployment

Focused historical replay, targeted tests and a compact comparison of selected geometry/alerts first; confirm no future-candle leakage and no accidental history-window dependence. One GitHub PR per logical validated change (reuse the same PR for small review fixes); integrate through GitHub-first; then safely sync local main while preserving unrelated tracked/untracked user work. Only after fixes pass, run one full Scanner acceptance, with the user's approval for actual launch and awareness that start_scanner.bat also starts PAPER backend and Telegram Monitoring. No LIVE/Robot state or trading policy changes.

## Course correction and time economy

Before any geometry micro-slice, consult this document, the current repository state, and only applicable scoped authority. Reuse earlier measurements; do not repeat full scans or create new infrastructure as a default. If stronger evidence or a better implementation route appears, compare it against the acceptance criteria, side effects, and existing architecture; revise **this document in the same scoped PR before/alongside changing direction**, noting why the former approach was discarded. Distinguish a working plan from an approved design/contract; do not quietly override authority. Ask the user only for material strategy/risk or otherwise consequential choices and host-local actions that available tools cannot perform.
