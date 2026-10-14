# Broadening Formation (Expanding Wedge) — HORN-1 design «Рупор»

Status: DESIGN (HORN-1), 2026-10-14. Base: `stable/adfb50b-forward` @ `df652788`.
Scope: an offline geometry detector for a symmetric broadening formation. It is
**not** connected to Scanner delivery, Telegram, Robot, PAPER_AUTO, LIVE or any
trading decision. Wedge and Triangle Compression detectors stay unchanged.
Entry: [SCANNER_GEOMETRY_CURRENT_COURSE.md](SCANNER_GEOMETRY_CURRENT_COURSE.md).

## 1. Pattern definition for HORN-1

A **symmetric broadening formation** (upper boundary rising, lower boundary falling):

- The upper boundary passes through ≥ 2 confirmed swing HIGHs, each higher than
  the previous one (HH). Its slope is > 0.
- The lower boundary passes through ≥ 2 confirmed swing LOWs, each lower than
  the previous one (LL). Its slope is < 0.
- The anchors form one adjacent alternating swing sequence (H, L, H, L… or
  L, H, L, H…), and every wave is strictly longer than the previous one:
  `abs(P[k+1] - P[k]) > abs(P[k] - P[k-1])`. This mirrors the owner's
  wedge contraction criterion (`abs(P[C]-P[B]) < abs(P[B]-P[A])`) without
  adding a threshold.
- The channel width at the decision bar is greater than at START (P1).

Out of scope for HORN-1: ascending or descending broadening wedges (both
boundaries sloped the same way but diverging). Their admission is a separate
owner decision.

## 2. Verified architecture (read-only, HEAD `df652788`)

`geometry.engine.analyze_geometry` builds pivots → regression candidate lines
(`candidate.build_candidate_lines`, `min_line_span=30`) → `filter_candidates`
(top 50 by error) → pair evaluation → validation → locality → body fit →
anchor sequence → **one winner** across all families. It is built for
convergence. A broadening pair is rejected **by design**:

| Stage | Behaviour for an expanding pair |
|---|---|
| `validation/compression.py` | requires `is_compressing` → "Structure is not compressing" |
| `validation/apex.py` | the apex lies before the structure → "Apex position invalid" |
| `pair_metrics.anchor_sequence` | slopes (+, −) → family `unknown` → `geometry_mode = REJECT` |
| `wedge/analyzer._freshness_predicate` | apex-based freshness, meaningless for a broadening |
| `triangle_boundaries` T/Q lines | admitted only for family `triangle` |

**Evidence** (`%USERPROFILE%\BybitScanner_evidence\HORN-1_20261014\proto*.py`,
`proto2_output.txt`):

- Setup: a synthetic megaphone, 5 legs with amplitudes growing 1.0→3.8.
- `analyze_geometry` → `None`.
- Evaluating the true pair (H71→H120 / L83→L107):
  - failed checks: `apex` (apex index 55.3, before START 71) and `compression` (−312.56 %);
  - family `unknown`;
  - envelope support 2/2.

**Decision.** HORN uses a **separate autonomous detector module**
(`geometry/broadening.py`), following the existing precedents
`geometry/l_shape.py` and `geometry/ikigai_box.py`. Placing it inside
`analyze_geometry` would require changing shared validators. It would also let a
broadening pair compete in the single-winner selection and hide or replace
Wedge/Triangle results, which this quest forbids.

### Reuse map

| Primitive | HORN use |
|---|---|
| `pivots.find_pivots` (3/3, min_change 0.003) | reuse as-is; confirmed pivots on the decision prefix only |
| two-point boundary through first/last same-side anchor (`trendline` / `triangle_boundaries` style) | reuse; no regression fit, no `min_line_span`, no top-50 error filter |
| hull property (`triangle_boundaries._is_hull_edge` semantics) | reuse: no confirmed same-side pivot from P1 to the decision bar lies beyond its boundary |
| `envelope_metrics.evaluate_formation_body_fit` + `engine.GEOMETRY_MAX_BODY_BREACH_RUN` | reuse: sustained body excursion rejects; an isolated wick does not |
| `engine.GEOMETRY_MAX_STRUCTURE_SPAN_RATIO` | reuse as the locality bound |
| `compression.calculate_compression` | reuse as a measurement: expansion = `end_width > start_width` (negative compression %) |
| TRI-WAVE-1 adjacency (PR #499) | reuse the principle: anchors are adjacent in the alternating confirmed sequence |
| `confirmation.calculate_atr` | diagnostic only (width/ATR), **no gate** |
| `triangle_boundaries.local_alternation_pivots` | diagnostic only (detect a global-filter-dropped swing) |

Not reused, because they would wrongly reject broadening geometry:

- `validate_compression`, `validate_apex`, `apex_quality`;
- the apex-based Wedge freshness predicate;
- `pair_metrics.anchor_sequence` (its first-anchor/TRI-START semantics assume convergence);
- regression candidates with `min_line_span=30` and the top-50 filter.

## 3. Owner addendum (open-source detector study): classification, not automatic gates

| # | Proposal | Already provided | New code | False-reject risk / decision |
|---|---|---|---|---|
| 1 | Two stages: 4 confirmed anchors = preliminary candidate; extra waves = maturity | — | stage logic | **Evidence:** 30 saved windows (2 recovered windows duplicate their Gold fixtures) give 25 expanding runs; only 2 have 5 pivots and both fail the gates. 8 runs (7 unique) pass locality+hull+body, and **none** of them reached a 5th expanding pivot (each was broken by the next confirmed pivot). A 4-pivot stage must not be user-facing. Stage 2 (5th pivot) may miss broadenings that resolve after 4 pivots: accepted for now and measured later |
| 2 | Width at start vs end; ATR as diagnostic | width via `calculate_compression`; ATR via `calculate_atr` | report fields only | none; no new threshold |
| 3 | Alternating HH/LL, no split structural waves | TRI-WAVE-1 principle, owner contraction rule (mirrored) | run builder over the confirmed sequence | **medium:** the global `min_change` filter can drop a real swing, so two same-side pivots appear adjacent and the run breaks. Record `local_alternation_pivots` disagreement as a diagnostic; no gate change until evidence |
| 4 | Line support; protection from a single extreme wick | anchors give 2 points per side; hull; body fit tolerates an isolated wick and rejects sustained body excursion | wick/body ratio of anchor candles as a diagnostic | **high** if made a gate: broadening extremes are typically wick sweeps. Diagnostic only in HORN-2 |
| 5 | Gold negatives: Triangle, Wedge, range, single spike, wrong pivot order | owner-labeled Triangle (MEGA, RSR) and Wedge (PONS) fixtures exist | synthetic range / spike / split sequence | none: negatives only |
| 6 | Only pivots confirmed at the decision time | `find_pivots` needs 3 right bars; the detector reads the prefix only | prefix-vs-future test | none |

## 4. HORN detector contract (for HORN-2)

`detect_broadening(candles, as_of_index)` reads candles `0..as_of_index` only and
returns `None` or one formation with diagnostics.

1. Confirmed pivots: `find_pivots(prefix)`. Build the alternating sequence. A
   same-side pivot between two anchors breaks the run (no skipped or split wave).
2. Expanding run: maximal adjacent run with HH, LL and strictly growing waves.
   START = P1 of that run (never moved later for fit). **Current:** the run must
   reach the latest confirmed pivot at `as_of_index` (no later confirmed pivot
   has already broken it), and the decision close lies between the boundaries.
3. Boundaries: two-point lines through the first and last HIGH / LOW of the run.
   The upper slope must be > 0 and the lower slope < 0. Width at `as_of_index`
   must exceed width at P1.
4. Admission: hull on both sides, body fit (`< GEOMETRY_MAX_BODY_BREACH_RUN`),
   locality (`GEOMETRY_MAX_STRUCTURE_SPAN_RATIO`).
5. Stage: `PRELIMINARY` with 4 anchors (internal only); `MATURE` with ≥ 5 anchors
   (the next expanding wave confirmed). `waves` = anchor count − 1.
6. Diagnostics (no gates): width_start / width_end / ratio, width/ATR at both
   ends, anchor wick/body ratios, global-vs-local pivot disagreement.

## 5. Controls

**Negative Gold (existing reproducible OHLC, owner-labeled).** Expected: no
current broadening at the decision bar. The prototype finds none in any of them.

- `MEGAUSDT_5m_triangle_local_positive_20261012` — owner Triangle positive.
- `RSRUSDT_5m_triangle_owner_reference_20261012` — owner Triangle reference.
- `manifest_v1` PONS — Gold falling-wedge positive.
- `1000XECUSDT_5m_window` — no-local-geometry negative.

**Synthetic (deterministic, HORN-2 tests).**

- Positives: a megaphone with growing legs, plus its mirror.
- Negatives:
  - converging zigzag (Triangle-like);
  - flat range;
  - one isolated spike;
  - split wave (same-side pivot between anchors);
  - HH without LL (rising channel/wedge);
  - a 4-pivot run broken by the next pivot (must not be current).

**Real positive Gold: none available.** No owner-labeled broadening chart exists
in `training/reference_patterns`, the Gold manifests or the evidence store. The
prototype's real expanding runs are historical Stage-1 episodes that later broke:

- ARX 142→169;
- MEGA 115→131 (immediately before the owner triangle 119→186);
- BONK 159→175;
- CAKE 152→177;
- formation_fit XRP 127→146;
- formation_fit POL 105→144 and 164→183.

They are **owner-review hypotheses, not positives**. A real positive Gold needs
one owner-labeled chart (symbol, timeframe, decision time). Its OHLC is then
recovered with the G-TRI-1 method and frozen.

## 6. Implementation plan

- **HORN-2 (next minimal slice).**
  - Add `geometry/broadening.py` per §4 and `tests/test_broadening_detector.py`.
  - Tests: synthetic positives/negatives, the four negative Gold windows, and one prefix-vs-future check.
  - No Scanner/Telegram/Robot wiring. Wedge/Triangle code and Gold identities unchanged (re-run `test_geometry_gold`, `test_geometry_triangle_local_anchors`, `test_geometry_triangle_rsr_anchors`).
- **HORN-3.**
  - Freeze the first owner-labeled positive Gold.
  - Produce a reproducible Stage-2 candidate list from saved OHLC for owner review (hypotheses only).
- **HORN-4 (separately authorized).** Telegram presentation and the mandatory full-universe Scanner pass. Trading/Robot remain out of this quest.

**HORN-2 acceptance:**

- the synthetic positive is detected with the exact anchors and stage;
- every negative (synthetic and Gold) returns `None`;
- the prefix verdict does not change when future bars are appended;
- existing geometry tests show no new failures (the 7 known formation_fit subtests stay as on base);
- harness `task finish` PASS.

## 7. Open owner decisions (do not invent)

1. May anything user-visible use Stage 1, or is Stage 2 (5 pivots) required?
2. Are ascending/descending broadening wedges in a later scope?
3. START rule against lead noise. In the synthetic case, low-amplitude pivots before the
   formation (H5/L14) joined the expanding run, and only locality rejected it.
   Resolve this on a real owner positive, not by a new threshold.
4. Anchor-wick policy (diagnostic now; gate only with evidence).
