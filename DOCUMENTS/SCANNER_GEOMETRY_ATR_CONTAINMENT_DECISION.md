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

## Implementation note - 2026-09-12: temporary global disablement

Status: TEMPORARILY DISABLED / CALIBRATION REQUIRED

The current Falling Wedge containment calibration proved excessively strict in practical scanning, producing too many unwanted quality downgrades and filtering out useful candidates. Containment violation evaluation is therefore temporarily disabled globally pending further calibration.

### Runtime behavior and implementation

`wedge.integrity.CONTAINMENT_VIOLATION_EVALUATION_ENABLED = False` now causes `evaluate_containment_violations()` to return a fresh copy of `ZERO_CONTAINMENT_VIOLATIONS` immediately for ALL pattern types, including Falling Wedge, Rising Wedge, and Triangle Compression, even when geometry contains body-zone breaches. These zero counts produce no containment-based quality penalty.

Rising Wedge and Triangle Compression already effectively had no active containment penalty. This change aligns Falling Wedge with that existing behavior; it does not implement containment protection for the other patterns.

This temporary disablement does NOT delete or supersede the previous ATR containment design. The existing Falling Wedge ATR handling, body-zone interpretation, upper/lower violation calculation, and reversal exception implementation are preserved in full below the switch for further recalibration and a subsequent controlled re-enable. Earlier decision and implementation records above remain unchanged as history.

### Unchanged boundaries

- Freshness remains a hard gate.
- The Geometry Validation Gate and touch logic are unchanged.
- Body-zone calculation and reversal-pattern recognizers are unchanged.
- The quality downgrade implementation is unchanged; the disabled evaluator supplies zero violations.
- Robot admission and runtime are unchanged.

### Re-enable condition

Containment evaluation must not be re-enabled merely by flipping the production flag. A separate calibration/verification task and a recorded decision are required before any controlled production re-enable.

### Verification

`tests/test_scanner_geometry_atr_containment.py` confirms default OFF behavior for Falling Wedge, Rising Wedge, and Triangle Compression with breaches present. Existing tests temporarily enable the switch through `unittest.mock.patch` to exercise the preserved Falling Wedge upper, lower-strict, late-flexible, reversal-exception, and missing-candles behavior. The focused module passed all 29 tests on 2026-09-12; this result verifies the switch behavior and retained implementation, not calibration acceptance.

## Approved narrow exception - 2026-09-21: Geometry-layer boundary validity

Status: APPROVED, NARROW

The soft-penalty policy recorded above is unchanged,
`CONTAINMENT_VIOLATION_EVALUATION_ENABLED` stays `False`, and no generic hard
containment gate on breach count, ratio or severity is authorized. This
section records one narrowly scoped exception, approved by the user on
2026-09-21 after the AAVE/POL/PONS historical review.

### Rule

`geometry/engine.py` rejects a candidate before ranking when, on ONE boundary
and at the SAME bar, all of the following hold:

- a confirmed pivot of that boundary's own type lies outside the line beyond
  the EXISTING pivot-line tolerance (`evaluate_boundary()` already filters
  these into `envelope_metrics[side]["outside_indices"]`);
- the candle body breaches that same line at that bar
  (`evaluate_body_zone_breaches()`);
- the bar is at or after that boundary's own primary anchor, so the boundary
  is applicable there;
- the bar is no later than the existing formation `end_index`.

An emptied pool is not rescued: no admissible candidate means no geometry.

### Applicable interval - measured limitation, 2026-09-21

`calculate_envelope_metrics()` computes BOTH evidence lists - the boundary's
`outside_indices` and the body-zone breach indices - starting at
`common_start`, the later of the two primary anchors. The rule as written
above says "at or after that boundary's own primary anchor"; for the
earlier-anchored boundary that evidence does not exist, so the check in fact
applies over `common_start..end_index` and the own-anchor condition is a
non-binding guard.

Extending the gate evidence to each boundary's own anchor was measured on the
saved snapshots and is NOT authorized: it rejects the committed AEVOUSDT
reference winner U156/L95 95-190 (lower contradictions at bars 102 and 140,
inside the 95..155 prefix) and moves the INJ winner 68-184 -> 77-184 and the
WLD winner 117-196 -> 129-196. That is the same class of reference regression
that closed PR #178, so the narrower `common_start..END` interval stands as
the approved applicability. Widening it would require a separate decision that
first resolves the AEVO reference.

### Why this is not the disabled containment penalty

- It is a *boundary-validity* statement, not a containment measurement: a line
  contradicted by its own confirmed extremum AND its own candle body at the
  same in-formation bar is not a boundary at all.
- It adds no threshold and no new constant; both inputs are already computed
  with existing tolerances.
- It never rejects on breach count, ratio or severity. Bodies alone never
  reject; an outside pivot alone never rejects; evidence split across the two
  different boundaries is not a contradiction.
- It does not enable or alter `evaluate_containment_violations()`, the Falling
  Wedge penalty, the tier-downgrade scale, or the Rising Wedge / Triangle
  KNOWN_GAP recorded above.

### Explicitly excluded

- **Post-END price action is never a formation defect.** A break after the
  structure completed is a breakout; the formation and its historical
  confirmation stand. PONSUSDT is the recorded reference for this.
- No symbol-specific rule, and no change to generator spacing, ranking
  priority, freshness, formation END or detector semantics.

### Unchanged boundaries

Freshness remains a hard gate. Validation, touch logic, body-zone calculation,
reversal-pattern recognizers, the disabled evaluator, the quality downgrade and
Robot admission are all unchanged.

### Verification

`tests/test_geometry_boundary_validity.py` covers the actual contradiction, the
same-boundary/same-bar requirement, boundary applicability, post-END exclusion,
the at-END case and the no-fallback empty pool. The existing AEVO fixture
regressions in `tests/test_geometry_candidate_selection_freshness.py` and
`tests/test_geometry_locality_admission.py` are run unchanged.

## Approved bounded revision — 2026-09-22: sustained formation body mismatch

Owner authorization: historical references may be revised when their structural
defect is evidenced; an isolated candle excursion must not automatically reject
a formation. The owner authorized one bounded implementation and historical
verification, not trading/risk changes or symbol-specific calibration.

This section supersedes the 2026-09-21 admission rule and its frozen-reference
restriction only as specified below. Earlier records remain historical evidence.

### Exact rule and ownership

- Reuse `evaluate_body_zone_breaches()` and its existing strict `> 0.15 * ATR(14)`
  body-edge comparison. A wick alone is not a body breach. No outside-pivot is
  required. The rule is symmetric and applies to the existing Wedge/Triangle pool.
- Evaluate the upper boundary from its own primary anchor through formation END,
  and the lower boundary from its own primary anchor through that same END,
  inclusively. Never evaluate a boundary before its own anchor. END remains the
  last supporting pivot of the existing candidate pair; it is not moved to excuse
  a breach. Post-END movement never contributes to this new admission or its
  body-count ranking preference.
- Replace single pivot-plus-body contradiction rejection with rejection when
  EITHER boundary has at least **7 consecutive applicable bars** whose bodies
  exceed the existing ATR tolerance. Isolated breaches, separated single bars,
  and shorter runs do not independently reject. A gap breaks a run; counts on
  opposite boundaries never combine into a run.
- Seven bars cover the current pivot observation context (3 left + center + 3
  right). This is an explicit engineering duration, not a new pivot algorithm,
  trading timeframe, or a claim of universal statistical calibration. It does
  not change automatically if pivot defaults change.
- Store the assessment in `envelope_metrics.formation_body_fit`, reusing the
  existing body evaluator rather than adding another candle/ATR implementation.
  Existing full-window diagnostic keys keep their historical meaning.
- Keep the existing single selection key: CANONICAL priority, fewer body
  breaches, then geometry ranking score, after locality and freshness handling.
  Its body count now comes from the respective own-anchor..END intervals. No
  alternate ranking system, new detector, generator spacing change or symbol
  exception is introduced. No admissible pool means no geometry; existing stale
  diagnostic fallback remains non-actionable under the unchanged freshness gate.
- Optional candle-free Geometry calls retain their prior ability to construct
  geometry: the body assessment is unavailable, not evidence of a clean envelope.
  The production Scanner supplies candles. Missing new metrics on legacy stubs
  are not represented as a successfully measured zero-breach assessment.
- The old #180 pivot/body intersection may remain a diagnostic fact, but is no
  longer an independent admission veto. In particular one candle cannot reject
  merely because it is also a confirmed pivot.

The disabled Wedge containment penalty stays OFF. Signal score/tier, Robot
admission code, risk, orders, runtime and Telegram behavior are out of scope.
100/100 continues to mean capped structural-plus-confirmation points; it is not
an envelope-fit guarantee. This bounded rule does not claim to catch every
intermittent or shallow unsupported line.

### Evidence and sensitivity (before algorithm edit)

Eleven frozen 200-bar historical windows were assessed. AZTEC/HIMS reuse the
previous matching-as-of reconstruction. QQQ/CHIP were recovered through two
bounded historical kline requests and matched to saved signal as-of, all report
pivots and selected anchors. Controls reuse the earlier saved windows, not the
later full-pass reports. No new full Scanner pass was run.

Longest own-anchor..END body-breach runs in the disputed historical boundaries:
AZTEC 16, HIMS 10, QQQ 45 (including the lower prefix), CHIP 8, AEVO 19,
INJ 7, WLD 15, AAVE 8, POL 9. XRP has none. PONS has a two-bar shallow
upper excursion (~0.20 ATR); its later breakout is outside END.

The SAME selected lines and START/END (or empty pool) result on ALL eleven
windows for every tested rejection duration 4, 5, 6, 7 and 8. At 9, the
known AAVE/CHIP defects return; at 10 POL returns; at 11 HIMS returns.
Seven is inside the stable interval and has the observation-context rationale
above; it was not selected to preserve old reference indices. This is bounded
historical sensitivity evidence, not out-of-sample calibration or launch approval.

### Reference dispositions to preserve in regression evidence

- AEVO U156/L95, END190: lower runs 101..111 and 128..146 precede
  common_start156; 35 body breaches, peaks ~3.73 and ~2.84 ATR. The old
  fixture is evidence of an unsupported lower boundary, not an immutable winner.
  No admissible replacement exists in this generator pool.
- INJ U105/L68: lower runs 77..83, 86..91, 94..97 (17 bars) precede
  common_start105. U105/L77, END184 instead has zero body breaches on both
  applicable boundaries. The isolated lower wick/pivot at172 is still allowed.
- WLD U117/L147: upper run126..140 (15 bars, peak ~2.03 ATR) precedes
  common_start147. The supported replacement is a DIFFERENT, earlier triangle,
  U129/L61, START61 END177, with zero body breaches; do not describe this as
  preserving or repairing the same late rising wedge.
- XRP U127/L89 END189 and PONS U143/L145 END186 remain unchanged.
- AZTEC selects U106/L102, START102 END148 with zero breaches but is stale:
  no fresh replacement signal. HIMS, QQQ, CHIP and POL have no admissible pair.
- AAVE retains only the existing stale U27/L46, START27 END108 diagnostic
  geometry; the rejected U136/L140 END195 is not rescued.

Verification and publication are recorded in
`CHANGE_REQUESTS/CR-SCANNER-GEOMETRY-FORMATION-FIT-001.md`.

## Investigated and NOT implemented — 2026-09-22: BONK/TURBO/XEC anchor-locality defect

Status: OPEN, NO CODE CHANGE. Recorded so the next attempt does not repeat this
diagnostic campaign from zero.

### The defect

`1000BONKUSDT`, `1000TURBOUSDT`, `1000XECUSDT` were admitted by the live Scanner
(post-#182) as `Rising Wedge`, `geometry_mode=EXPLORATORY`, `Pattern Score: 95/100`,
`signal=STRENGTHENING`, sent to Telegram. Signal-time evidence from the Scanner's
own debug log:

```
BONK  : upper_anchor=81  lower_anchor=128  upper_slope=1.5957e-07  lower_slope=1.9048e-06
TURBO : upper_anchor=81  lower_anchor=128  upper_slope=4.1739e-05  lower_slope=2.8049e-04
XEC   : upper_anchor=64  lower_anchor=132  upper_slope=3.5439e-06  lower_slope=5.6389e-06
```

All three: family=`rising`, `anchor_sequence.valid=False` (upper/secondary anchor
precedes the lower/primary anchor). Rendered charts (`charts/1000BONKUSDT_analysis.png`
etc., generated at signal time) show the upper boundary anchored at a swing high
that predates the sharp reversal impulse the lower boundary anchors to, then drawn
forward across a later consolidation, the user-reported anchor/formation
mismatch. The signal-time chart images suggest upper-line wick excursions, but
their resolution does not establish whether all original candle bodies stayed
inside the boundaries. Later or reconstructed 200-bar windows returned zero
measured breaches for different selected pairs; these measurements do NOT
verify the original signal-time candle-body fit. The exact signal-time OHLC
windows were not persisted, so the body-breach classification remains open.

### Why no fix was implemented this pass

Every existing, already-computed pair-level signal was tested as a candidate
admission gate against the frozen `tests/fixtures/geometry_formation_fit/historical_cases.json`
eleven-case set (including historical selections INJ, WLD, XRP, AAVE, AZTEC
and PONS). The tested one-number global gates did not isolate the new
anchor-context problem while preserving those historical selections. These
cases are regression evidence, NOT immutable winners: a structurally defective
historical selection may be replaced or rejected under the approved course:

- **Anchor chronological order** (secondary anchor precedes primary anchor):
  true for BONK/TURBO/XEC, but also true for the accepted INJ (`U105/L77`) and
  AAVE (`U27/L46` uses the same non-canonical shape) references. Not discriminating.
- **`formation_body_fit` sustained-run count** (the #182 admission gate): zero
  on later/reconstructed BONK/TURBO/XEC windows; original signal-time fit is
  unknown. Historical selected pairs measured 0-3. Lowering the global
  seven-bar threshold is neither demonstrated to correct anchor locality
  nor supported by these non-identical replay windows.
- **Slope-imbalance ratio** (`pair_metrics` convergence `slope_ratio`/`slope_balance`):
  signal-time values BONK=11.9x, TURBO=6.7x, XEC=1.6x vs. accepted INJ=6.4x,
  AAVE=6.6x. These values overlap the comparison set (TURBO/XEC sit inside or below its
  range); a threshold here would need to sit between 6.6 and 11.9 on a sample of
  two, which this document's own prior sections already treat as insufficient
  evidence for a general threshold.
- **`anchor_balance`, `shared_structure_span`/`common_span` ratio, candidate
  `support_ratio`, line `error_mean`, `convergence_strength`,
  `is_converging`/`true_converging`**: all measured and all overlap between the
  defective and the accepted set (full numbers kept in this task's session
  record, not restated here to avoid implying a precision this sample does not
  support).

A byte-identical replay of the exact signal-time 200-candle window could not be
obtained (the market moved during investigation; sliding-window reconstruction
converged to within 3 bars of the logged anchors but never exact, and every
re-fetch a few minutes apart selected a *different* winning candidate pair,
usually with 0 measured breaches). This limits what can be concluded from the
tested numeric comparisons; it does not establish that the original signals
had zero body breaches or that a particular new threshold would be valid.

### Disposition

Per this course's own standing rule ("stop the change rather than create another
multi-stage diagnostic campaign" if a bounded correction is not evidenced), no
admission/ranking change is made in `geometry/engine.py` or
`geometry/envelope_metrics.py` for this defect class. Next, define and test
ownership of each anchor by the actual local price phase (preceding impulse,
reversal pivot and subsequent consolidation),
using the existing pivot/candle pipeline and already retained historical
cases. Do not repeat the falsified global-threshold campaign or launch
another full scan to collect data by default. If signal-time OHLC is
essential for acceptance and unavailable, report that narrow evidence gap
rather than asserting a result from later candles. `1000BONKUSDT`
(signal-time anchors `U81/L128`) is the recommended primary target, with
`1000TURBOUSDT`/`1000XECUSDT` and the existing INJ/AAVE/WLD/XRP/PONS/AZTEC set as
comparison cases, with revisions allowed when the selected historical
anchors are themselves structurally unsupported.

Out of scope for this investigation and unaffected: the Triangle Compression
movement-potential display gap (`wedge/potential.py` returning `None` for any
pattern other than Falling/Rising Wedge) is a separate, independent presentation
defect with no admission/ranking effect; it is fixed in the same task and does not
require this decision boundary.

# END_OF_DOCUMENT
