# BybitScanner — Scanner Geometry ATR Containment Decision

Version: 1.0
Date: 2026-09-10
Status: ACCEPTED DESIGN
Implementation authorization: NONE

## Supersession

This document **replaces**:

1. The hard binary containment/freshness gate currently in `wedge/detector.py:detect_structure()` — specifically the fixed `max_strict_severe_run = 2` severe-run cutoff and the fixed 15-bar freshness window (`0 <= freshness_bars <= 15`).
2. `DOCUMENTS/SCANNER_GEOMETRY_BOUNDARY_VIOLATION_DECISION.md` in its entirety, now marked `Status: SUPERSEDED` with an explanatory block, text preserved for decision history.

## Scope

Applies only to **Falling Wedge**. Rising Wedge (the mirrored rule: strict lower trendline, flexible upper trendline with bearish reversal patterns) remains a separate, unresolved future task, exactly as it was in the superseded document.

This is a design contract only. It does not authorize implementation: no change to `geometry/envelope_metrics.py`, `wedge/detector.py`, or `signal/quality.py` is made by this decision.

## Background: why the existing hard gate is being replaced, not just supplemented

Live tracing on the real, unmodified pipeline confirmed that `wedge/detector.py:detect_structure()` already has a containment mechanism (`features["containment"]`, backed by `evaluate_directional_envelope()` and `_max_consecutive_run()` over `envelope_metrics.candle_containment`), and that it already fires in practice: observed live on `ARBUSDT`, a candidate that passed all five Validation Gate checks (`validation.valid = True`, `failed_checks = []`) and classified as Falling Wedge was rejected outright (`detected = False`, `reason = "Insufficient geometry features"`) because `containment_strict_run = 50` against a fixed cutoff of `max_strict_severe_run = 2`.

Two things follow from this:

- The problem the superseded Boundary Violation document set out to solve (candles between touch points ignoring the trendline) is **already partially handled** in production, just as an undifferentiated hard reject rather than a graduated signal.
- Adding a *second*, separate soft-penalty boundary check next to an *unchanged* hard-reject gate would leave two overlapping mechanisms disagreeing about the same candles. This decision instead replaces the existing hard gate's parameters and its all-or-nothing failure mode in one design, reusing the existing `evaluate_candle_containment()` machinery rather than adding a parallel one.

## Decision

### 1. ATR-normalized tolerance (replaces the fixed `tolerance_percent`)

`geometry/envelope_metrics.py:evaluate_candle_containment(upper_line, lower_line, candles, start_index, current_index, tolerance_percent=0.15)` keeps its existing `outside_percent()`-based comparison. Only the tolerance value changes: instead of the flat `tolerance_percent=0.15`, tolerance is computed from the instrument's ATR(14), reusing the existing `confirmation.py:calculate_atr(df, period=14)` — no new ATR implementation.

```text
tolerance = 0.15 * ATR(14)
```

expressed in the same unit `outside_percent()` already compares against, so `outside_percent()` itself is not rewritten — only the value passed in as `tolerance_percent` changes from a constant to this ATR-derived one.

### 2. Zone split (replaces the single fixed midpoint)

The structure between `start_index` and `end_index` splits into:

- early zone (`STRICT_ZONE`): the first 60% of the structure;
- late zone (`FLEXIBLE_ZONE`): the remaining 40%, nearer the apex.

The 50/50 midpoint implicit in the current containment evaluation becomes a configurable split, set to 60/40 by this decision.

### 3. Upper trendline (Falling Wedge upper boundary)

Strict across the **entire** structure, both zones, no exception. Any candle whose **body** (not wick) breaches the line by more than the ATR-derived tolerance is a violation.

### 4. Lower trendline, early zone (first 60%)

Same strict regime as the upper trendline: any candle whose body breaches the line by more than the ATR-derived tolerance is a violation.

### 5. Lower trendline, late zone (last 40%)

- A wick-only breach beyond the ATR tolerance is, by itself, **not** a violation.
- A body breach is a violation **unless** it is accompanied by one of three recognized reversal patterns on that candle or in a rolling window around it. These definitions are carried forward unchanged from the superseded document:

  1. **Bullish Engulfing**: previous candle bearish (`close < open`), current candle bullish (`close > open`), current body fully covers previous body (`open_current <= close_previous` and `close_current >= open_previous`).
  2. **Morning Star**: three candles — first bearish with a large body, second with a small body (gapping down from the first), third bullish with a large body closing above the midpoint of the first candle's body.
  3. **Arc**: a run of 4–6 consecutive local lows that visually forms a smooth rounding (decline, flattening at the bottom, then turning up) rather than a sharp V-shaped reversal.

  A body breach accompanied by a recognized pattern is excused and not counted. An unaccompanied body breach counts as one violation.

### 6. Violation handling — soft penalty, not hard reject

This is the central change from the current production behavior: `features["containment"]` in `wedge/detector.py:detect_structure()` is currently a hard boolean that, when `False`, forces `detected = False` regardless of the five Validation Gate checks. This decision removes that hard-reject role for containment. Violations instead produce counts:

```text
containment_violations = {
    "upper_violations": int,
    "lower_strict_violations": int,
    "lower_flexible_unrecognized_breaches": int,
}
```

fed into `signal/quality.py`'s tier decision as a penalty modifier — the same mechanism, same input shape, and same approved severity/downgrade scale as the superseded document, carried forward unchanged:

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

This table and the severity weights (2/2/1) are unchanged from the superseded document and remain approved as of this decision.

### 7. Freshness — remains a hard gate, window changes from fixed to proportional

Unlike containment, the "apex is still ahead" requirement (`features["freshness"]`, currently `freshness_bars is not None and 0 <= freshness_bars <= 15 and before_apex`) is **not** softened into a penalty. It remains a hard gate: a structure whose apex has already passed, or that is too far removed from the current candle, is not an actionable setup regardless of quality tier.

What changes is only the fixed 15-bar window, replaced with a window proportional to the structure's own length:

```text
freshness_window = max(15, round(structure_length * 0.20))
```

**This 0.20 factor is a starting proposal, not finalized.** It is presented here for approval alongside the rest of this document, not authorized ahead of that approval. `before_apex` and the `current_index is not None` / `end_index is not None` preconditions are unchanged.

## Explicit non-goals

- **Rising Wedge**: the mirrored rule (strict lower trendline, flexible upper trendline with bearish reversal patterns) is a separate, unresolved future task, as it was in the superseded document.
- **Implementation**: no change to `geometry/envelope_metrics.py:evaluate_candle_containment()`, `outside_percent()`, `wedge/detector.py:detect_structure()`, or `signal/quality.py` is authorized by this decision.
- **Final numeric values**: the `0.15 * ATR(14)` tolerance multiplier, the 60/40 zone split, and the `freshness_window` `0.20` factor are proposals for review, not finalized, implementation-authorized numbers.
- **Reversal-pattern recognizer implementation**: exact rolling-window size, "large/small body" thresholds, and the Arc run-length/shape criteria remain to be specified at implementation time, as in the superseded document.
- Any change to the five existing Validation Gate checks (`slopes`/`apex`/`apex_quality`/`compression`/`touches`) or their pass/fail semantics.
- Any change to `geometry/candidate.py`'s Pivot-selection or its own `tolerance_percent` logic (distinct from the containment `tolerance_percent` this decision retunes).

## Reuse / ownership boundary

This decision retunes and reuses existing capabilities; it does not introduce a parallel one:

- `geometry/envelope_metrics.py:evaluate_candle_containment()` and `outside_percent()` remain the sole containment-evaluation implementation — only the `tolerance_percent` value and the zone split passed into it change.
- `confirmation.py:calculate_atr()` remains the sole ATR implementation — no second ATR calculation is introduced.
- The reversal-pattern recognizers and the tier-downgrade scale are the same ones approved in the superseded document, not reimplemented.

This decision must not alter `GeometryModel`, the Validation Gate's `valid`/`checks`/`failed_checks` contract, or introduce a second trendline/geometry representation. Its only sanctioned effects are: (a) retuning containment's tolerance and zone parameters and removing its hard-reject role in `detect_structure()` in favor of feeding `containment_violations` into `signal/quality.py`, and (b) widening the freshness window formula while keeping freshness itself a hard gate.

# END_OF_DOCUMENT
