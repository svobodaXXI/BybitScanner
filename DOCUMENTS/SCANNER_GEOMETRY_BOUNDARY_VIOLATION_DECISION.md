# BybitScanner — Scanner Geometry Boundary Violation Decision

Version: 1.0
Date: 2026-09-10
Status: SUPERSEDED
Implementation authorization: NONE

SUPERSEDED by DOCUMENTS/SCANNER_GEOMETRY_ATR_CONTAINMENT_DECISION.md v1.0 (2026-09-10). This document was never implemented. Live tracing on the real, unmodified pipeline (`wedge/detector.py:detect_structure()`) found that a related boundary-containment mechanism already exists in production — a hard binary `containment` gate (`max_strict_severe_run=2`) that rejects the whole candidate outright rather than applying a graduated quality penalty — and that it already fires on real Falling Wedge candidates that otherwise pass all five Validation Gate checks (observed live on ARBUSDT: `containment_strict_run=50`, `detected=False`). Rather than layering a new, separate soft-penalty check (as this document proposed) alongside the pre-existing hard-reject gate, the superseding document replaces both the existing hard gate and this document's proposal with one ATR-normalized, zone-aware containment design reusing `geometry/envelope_metrics.py:evaluate_candle_containment()`. The reversal-pattern definitions (Bullish Engulfing / Morning Star / Arc) and the tier-downgrade scale approved below are carried forward unchanged into the superseding document.

## Scope

Applies only to **Falling Wedge**. Rising Wedge is an explicit non-goal of this document (see Non-goals).

This is a design contract only. It does not authorize implementation of the boundary-violation detector, the reversal-pattern recognizers, or any change to `signal/quality.py`'s numeric thresholds.

## Problem statement

`geometry/candidate.py` and `geometry/validation/*` (`slopes`, `apex`, `apex_quality`, `compression`, `touches`) only check that the *selected* Pivot points touch each trendline within `tolerance_percent` (0.6%). No existing check looks at whether candles that were **not** selected as Pivots violate the trendline between two touch points. A trendline can therefore be geometrically "valid" by the five existing Validation Gate checks while visually ignoring most of the price action between its anchor points — a formally correct but structurally loose wedge.

## Decision

Add a new **Boundary Violation** check for Falling Wedge, separate from and outside the five existing Validation Gate checks (`slopes`/`apex`/`apex_quality`/`compression`/`touches`). It is **non-blocking**: it never appears in `failed_checks` and never flips `valid`. Its only effect is to feed a penalty modifier into `signal/quality.py`'s tier decision.

### 1. Structure zones

The structure between `start_index` and `end_index` splits into:

- `STRICT_ZONE`: the first 60% of the structure (`start_index` through 60% of the way to `end_index`);
- `FLEXIBLE_ZONE`: the remaining 40%, nearer the apex.

### 2. Upper trendline (Falling Wedge upper boundary)

Checked across the **entire** structure, both zones, with no exception. Any candle whose `high` crosses above the line (`high > line_price(index)`, zero tolerance) counts as one upper violation.

### 3. Lower trendline in `STRICT_ZONE`

Any candle whose `low` crosses below the line (`low < line_price(index)`, zero tolerance) counts as one lower strict-zone violation.

### 4. Lower trendline in `FLEXIBLE_ZONE`

- A wick-only breach (`low < line_price(index)` but `close >= line_price(index)`) is, by itself, **not** a violation.
- A body breach (`close < line_price(index)`) **is** a violation, **unless** it is accompanied by one of three recognized reversal patterns on that candle or in a rolling window around it:

  1. **Bullish Engulfing**: previous candle bearish (`close < open`), current candle bullish (`close > open`), current body fully covers previous body (`open_current <= close_previous` and `close_current >= open_previous`).
  2. **Morning Star**: three candles — first bearish with a large body, second with a small body (gapping down from the first), third bullish with a large body closing above the midpoint of the first candle's body.
  3. **Arc**: a run of 4–6 consecutive local lows that visually forms a smooth rounding (decline, flattening at the bottom, then turning up) rather than a sharp V-shaped reversal.

  A body breach accompanied by a recognized pattern counts toward neither violations nor an exception log entry beyond being excused; it simply is not counted. An unaccompanied body breach counts as one lower flexible-zone unrecognized-body-breach violation.

### 5. Output shape

The check produces **counts**, not a valid/invalid verdict:

```text
boundary_violations = {
    "upper_violations": int,
    "lower_strict_violations": int,
    "lower_flexible_unrecognized_breaches": int,
}
```

This dict is passed into `signal/quality.py`'s `evaluate_quality()` as a new input parameter (e.g. `boundary_violations: dict`). It must not be written into `checks`/`failed_checks`/`valid` anywhere in `geometry/validation/*`.

## Proposed tier-downgrade scale (FOR APPROVAL — NOT FINALIZED)

This numeric scale is a proposal only, sized to be comparable in magnitude to the existing gaps between tiers in `signal/quality.py` (Elite `score >= 85` / A `score >= 75` / B `score >= 60`, roughly 10–15-point steps). It is not authorized for implementation until separately approved.

Define one combined severity number from the three counts, weighting a strict-side violation (upper, anywhere; lower, strict zone) above a flexible-zone unrecognized breach, since the strict sides carry zero tolerance by design while the flexible zone already has the wick-exception and pattern-exception built in:

```text
severity = 2 * upper_violations
         + 2 * lower_strict_violations
         + 1 * lower_flexible_unrecognized_breaches
```

Tier order for downgrade purposes (high to low): `Elite Setup(4) > A Setup(3) > B Setup(2) > Watch(1) > Weak Setup(0)`. A downgrade never raises a tier and never goes below `Weak Setup`.

| severity | downgrade steps | Elite Setup → | A Setup → | B Setup → | Watch → |
| --- | --- | --- | --- | --- | --- |
| 0 | 0 | Elite Setup | A Setup | B Setup | Watch |
| 1–2 | 1 | A Setup | B Setup | Watch | Weak Setup |
| 3–4 | 2 | B Setup | Watch | Weak Setup | Weak Setup |
| ≥5 | 3 | Watch | Weak Setup | Weak Setup | Weak Setup |

Rationale for this shape: a single flexible-zone unrecognized breach (severity 1) costs exactly one tier step, matching "any nontrivial defect drops one tier" from the instruction; a single strict-side violation (severity 2) already reaches the same one-tier step, reflecting that strict-zone/upper violations are more serious per occurrence; multiple or combined violations compound toward `Weak Setup` rather than being capped at a one-tier penalty regardless of count.

This table, the severity formula, and its weights (2/2/1) are all open for revision before approval — they are a starting proposal, not an accepted number.

## Explicit non-goals

- **Rising Wedge**: the mirrored rule (strict lower trendline, flexible upper trendline with bearish reversal patterns instead of bullish ones) is a separate, unresolved future task. Nothing in this decision applies to Rising Wedge.
- **Final penalty magnitude**: the severity formula and the tier-downgrade table above are a proposal to review, not a finalized, implementation-authorized scale.
- **Implementation of the detector**: the boundary-crossing check itself (per-candle `high`/`low`/`close` vs. `line_price(index)` evaluation across the structure) is not implemented by this decision.
- **Implementation of the three reversal-pattern recognizers** (Bullish Engulfing, Morning Star, Arc): not implemented by this decision; exact rolling-window size, "large/small body" thresholds, and the Arc run-length/shape criteria remain to be specified at implementation time.
- Any change to the five existing Validation Gate checks (`slopes`/`apex`/`apex_quality`/`compression`/`touches`) or to their pass/fail semantics.
- Any change to `geometry/candidate.py`'s Pivot-selection or `tolerance_percent` logic.

## Reuse / ownership boundary

Boundary Violation is a read-only diagnostic over already-computed trendlines, structure indices, and candle data. It must not recompute anchors, refit lines, or introduce a second geometry/trendline representation. It must not alter `GeometryModel`, the Validation Gate's `valid`/`checks`/`failed_checks` contract, or Geometry → Wedge detection behavior. Its only sanctioned effect is the new `boundary_violations` input to `signal/quality.py`'s tier decision.

# END_OF_DOCUMENT
