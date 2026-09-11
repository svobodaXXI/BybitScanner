# BybitScanner — Scanner Geometry ATR Containment Decision

Version: 1.0
Date: 2026-09-10
Status: ACCEPTED DESIGN
Implementation authorization: APPROVED (2026-09-11) — see IMPLEMENTATION_RECORD below

## Supersession

This document **replaces**:

1. The hard binary containment/freshness gate currently in `wedge/detector.py:detect_structure()` — specifically the fixed `max_strict_severe_run = 2` severe-run cutoff and the fixed 15-bar freshness window (`0 <= freshness_bars <= 15`).
2. `DOCUMENTS/SCANNER_GEOMETRY_BOUNDARY_VIOLATION_DECISION.md` in its entirety, now marked `Status: SUPERSEDED` with an explanatory block, text preserved for decision history.

## Scope

Applies only to **Falling Wedge**. Rising Wedge (the mirrored rule: strict lower trendline, flexible upper trendline with bearish reversal patterns) remains a separate, unresolved future task, exactly as it was in the superseded document.

This was originally a design contract only, not authorizing implementation. Implementation was explicitly authorized on 2026-09-11; see `IMPLEMENTATION_RECORD` at the end of this document for what was actually built and what remains a working default pending later calibration.

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

## IMPLEMENTATION_RECORD

Implementation authorized and completed 2026-09-11. Working defaults (`0.15 * ATR(14)`, 60/40 zone split, `freshness_window = max(15, round(structure_length * 0.20))`, severity weights 2/2/1, and the reversal-pattern thresholds below) were implemented exactly as approved, without further negotiation, per explicit instruction. All are still unrehearsed against historical data and remain subject to later calibration.

### What was actually built (one deviation from the original plan text worth recording precisely)

The original "Decision" text above described retuning `evaluate_candle_containment()` in place. During implementation this turned out to be unsafe: `evaluate_candle_containment()`'s existing output (`candle_containment`, specifically `upper_early_max_run`/`lower_early_max_run`) is *also* consumed by `geometry/evaluation.py`'s unrelated CANONICAL→EXPLORATORY downgrade heuristic, which is explicitly out of scope for this decision and protected by the Geometry→Wedge contract. Retuning that function in place would have silently changed that unrelated heuristic's tolerance/zone too.

Actual implementation therefore **added** a new, separate function, `geometry/envelope_metrics.py:evaluate_body_zone_breaches()`, alongside the untouched `evaluate_candle_containment()`. Both are computed in `calculate_envelope_metrics()` and stored under different `envelope_metrics` keys (`candle_containment`, unchanged; `body_zone_breaches`, new). This still satisfies "no two parallel *hard-reject* mechanisms" — `wedge/detector.py` no longer reads `candle_containment` for any rejection purpose, and its old hard-reject block (`max_strict_severe_run`, `_max_consecutive_run`) was deleted outright, not left dormant. It does mean `evaluate_candle_containment()` itself remains in the codebase, but only for the unrelated, still-active CANONICAL/EXPLORATORY heuristic it always served.

Files changed:

- `geometry/envelope_metrics.py` — added `evaluate_body_zone_breaches()` (ATR-tolerance, 60/40 zone split, body-vs-line comparison for both boundaries in one shared code path) and wired its output into `calculate_envelope_metrics()` as `body_zone_breaches`.
- `geometry/reversal_patterns.py` (new file) — `is_bullish_engulfing`, `is_morning_star`, `is_smooth_arc`, `has_reversal_exception`, with named constants `LARGE_BODY_RATIO=0.5`, `SMALL_BODY_RATIO=0.3`, `ARC_MIN_RUN=4`, `ARC_MAX_RUN=6`, `ARC_MAX_SINGLE_STEP_ATR_MULTIPLIER=2.0`.
- `wedge/integrity.py` — added `evaluate_containment_violations(geometry, pattern, candles)`: the pattern-aware interpretation (Falling Wedge only; all other patterns get zero violations) that turns raw `body_zone_breaches` into `{upper_violations, lower_strict_violations, lower_flexible_unrecognized_breaches}`, applying the reversal-pattern exception only to late-zone lower breaches.
- `wedge/detector.py` — removed the old hard containment block entirely (`candle_containment` reading, `_max_consecutive_run`, `max_strict_severe_run`, `containment_valid`) and removed `containment` from the detection AND-gate; added `FRESHNESS_WINDOW_MIN_BARS=15` / `FRESHNESS_WINDOW_FACTOR=0.20` and the proportional freshness window; `detect_structure()` now accepts an optional `candles` parameter and exposes `features["containment_violations"]` / `features["freshness_window"]`.
- `wedge/analyzer.py` — threads `candles` into `detect_structure()`.
- `signal/quality.py` — `evaluate_quality()` gained an optional `containment_violations` parameter; base tier is now computed without early return, then downgraded per the approved severity/tier table (constants `CONTAINMENT_SEVERITY_WEIGHT_UPPER=2`, `CONTAINMENT_SEVERITY_WEIGHT_LOWER_STRICT=2`, `CONTAINMENT_SEVERITY_WEIGHT_LOWER_FLEXIBLE=1`, `CONTAINMENT_SEVERITY_TIER_1_MAX=2`, `CONTAINMENT_SEVERITY_TIER_2_MAX=4`). The `Invalid` tier is unaffected.
- `analyzer/core.py` — passes `containment_violations` from `result["detection"]["features"]` into `evaluate_quality()`.

### KNOWN_GAP — Rising Wedge / Triangle Compression have no containment gate at all

Detected: 2026-09-11 (during this implementation).
Status: OPEN (re-opened 2026-09-12 — see below; briefly MITIGATED 2026-09-11 through 2026-09-12 via a `main.py` exclusion filter that was itself explicitly reverted).

Mitigation recorded 2026-09-11, then reverted 2026-09-12: `main.py` briefly excluded both patterns from the scan loop entirely via `ROBOT_V0_1_ALLOWED_PATTERNS = {"Falling Wedge"}`, checked immediately after the existing junk-pattern filter (before diary recording, Telegram notification, or `create_signal_snapshot()` / Robot candidate creation). This was a scope-narrowing mitigation, not a containment fix: Rising Wedge and Triangle Compression were not scored, gated, or admitted at all while that filter was active, rather than being detected-with-no-containment-check as before. A previously-applied stop-gap restoring the old hard containment reject scoped to these two patterns (Option 2 below) was implemented, tested, then reverted in favor of this exclusion-based approach before being committed on 2026-09-11.

**Re-opened 2026-09-12**: the user made an explicit, conscious decision to remove the `main.py` exclusion filter and restore pre-`7da7c9f` behavior — all three pattern types (Falling Wedge, Rising Wedge, Triangle Compression) once again reach diary recording, Telegram notification, and Robot candidate creation, with no exclusion by pattern type. The user's stated rationale: mirrored ATR containment for Rising Wedge/Triangle Compression remains future work, exactly as originally scoped by this decision's own Section on future work — the user prefers to see all patterns now, unchecked, rather than hide them until containment is built. This is a deliberate acceptance of the practical consequence described below, not a fix to it; `wedge/detector.py` and `wedge/integrity.py:evaluate_containment_violations()` are unchanged by either the 2026-09-11 mitigation or this reversal — Falling Wedge keeps its ATR soft-penalty mechanism from this decision, and the other two patterns still have zero containment mechanism of any kind.

Rising Wedge and Triangle Compression candidates now pass through `wedge/detector.py:detect_structure()` with **zero containment protection of any kind**: the old hard reject (`max_strict_severe_run`, wick-based, flat 0.15%) was deleted outright as part of this implementation, and the new ATR-based soft mechanism (Sections 1–6 above) is scoped to Falling Wedge only, per this decision's own Scope and the explicit instruction to fully replace the old mechanism rather than run it in parallel for the patterns not yet covered. `wedge/integrity.py:evaluate_containment_violations()` returns all-zero violations for every pattern other than `"Falling Wedge"` — not "reduced protection," literally no check.

This is **not** a hypothetical or theoretical risk. Both patterns are active, in-scope parts of Robot v0.1's current work:

- **Rising Wedge**: confirmed implemented as Robot v0.1's SHORT-side counterpart to Falling Wedge LONG entries — see `DOCUMENTS/AUTOPILOT_ROBOT_V0_1_TELEGRAM_FEED_AND_SHORT_WEDGE_DECISION.md` ("Robot v0.1 trades both wedge directions: Falling Wedge -> LONG, Rising Wedge -> SHORT"), `DOCUMENTS/AUTOPILOT_ROBOT_V0_1_ENTRY_STRATEGY_DECISION.md`, and `DOCUMENTS/AUTOPILOT_ROBOT_V0_1_RESTART_RECOVERY_DECISION.md`.
- **Triangle Compression**: named as part of the existing baseline pattern set for the Robot Decision Model in `DOCUMENTS/ROBOT_STRATEGY_DESIGN.md` ("Falling Wedge; Rising Wedge; Triangle Compression").

Practical consequence: a candidate of either pattern that would previously have been silently hard-rejected for heavy containment violations (candles grossly outside the trendlines) can reach detection, quality scoring, diary recording, Telegram notification, and — for Rising Wedge specifically — Robot admission, with no containment-based penalty or rejection whatsoever. Between 2026-09-11 and 2026-09-12 the `main.py` exclusion mitigation removed this consequence by keeping both patterns out of Robot v0.1's output entirely; as of 2026-09-12 the user has explicitly chosen to accept this consequence again rather than continue hiding the two patterns, so it is live once more.

Required before Robot v0.1 relies on Rising Wedge or Triangle Compression signals in production with containment protection — one of, subject to a separate explicit decision:

1. Design and implement the mirrored Rising Wedge containment rule (strict lower trendline, flexible upper trendline with bearish reversal-pattern exceptions) already flagged as future work in this decision's Scope, plus an analogous rule for Triangle Compression (both boundaries strict, per the old `DIRECTIONAL_BOUNDARY_ROLES` mapping). This remains the only path to actual containment protection for these two patterns — Option 2 below was evaluated and rejected on 2026-09-11, and the 2026-09-11/12 exclusion-then-reversal cycle did not change that.
2. ~~As a temporary measure, restore a hard containment reject scoped only to Rising Wedge and Triangle Compression (reusing the still-intact `evaluate_candle_containment()` / `candle_containment` data, which this implementation left untouched) until (1) is authorized and built.~~ Superseded 2026-09-11: implemented and unit-tested, then explicitly reverted before commit in favor of the (now also reverted) exclusion mitigation — restoring the old gate would have kept `wedge/detector.py`'s pre-`ddd0466` hard-reject path alive indefinitely for two patterns, which the decision's own Section 6 (single-mechanism intent) argues against.

Re-opened, not resolved: the underlying containment gap for Rising Wedge / Triangle Compression remains exactly as originally described in this section, with no mitigation of any kind currently in effect. Tracked here and in `DOCUMENTS/PROJECT_STATE.md`.

### Verification

- New focused suite `tests/test_scanner_geometry_atr_containment.py` (28 tests): `evaluate_body_zone_breaches`, all three reversal-pattern recognizers, `evaluate_containment_violations` (including the Falling-Wedge-only scope gate and candles-unavailable fail-to-violation default), the severity/downgrade table end to end, and the freshness window formula.
- `tests/test_directional_envelope_quality.py` updated: the five tests exercising the old hard-reject mechanism were replaced with tests of the new soft mechanism; the unrelated CANONICAL/EXPLORATORY downgrade test (`test_geometry_evaluation_has_no_directional_outside_downgrade`) was left unchanged and still passes, confirming `evaluate_candle_containment()`'s other consumer was not disturbed.
- Full repository regression (`python -B -m unittest discover -s tests`): 619 tests, identical 2 failures and 19 errors to the pre-existing baseline (confirmed by diffing against the unmodified tree), zero new failures. `tests/test_geometry.py`, `tests/test_geometry_pipeline.py`, `tests/test_wedge_pipeline.py` (plain-script, not unittest-discoverable) were run directly and produce byte-identical output to the unmodified baseline, including `test_wedge_pipeline.py`'s already-documented pre-existing `AssertionError` (see `CR-SCANNER-GEOMETRY-001` `verification_results`).
- Live end-to-end check on real ARBUSDT market data: previously hard-rejected (`containment_strict_run=50` against the old `max_strict_severe_run=2`), now `detected=True` with `containment_violations={"upper_violations": 63, "lower_strict_violations": 16, "lower_flexible_unrecognized_breaches": 7}` (4 late-zone breaches excused by recognized reversal patterns), `freshness_window=38`, and quality correctly downgraded from `B Setup` to `Weak Setup` (severity 165, ≥5 → 3-step downgrade per the approved table). The large severity value on this real example is itself useful early evidence for later calibration, not a defect.

# END_OF_DOCUMENT
