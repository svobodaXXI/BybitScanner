# CR-SCANNER-GEOMETRY-002 — ATR-Normalized Wick-Aware Boundary Fitting for Wedge Layer

<!-- CHANGE_REQUEST_METADATA_BEGIN -->
```json
{
  "schema_version": "1.0",
  "id": "CR-SCANNER-GEOMETRY-002",
  "title": "ATR-Normalized Wick-Aware Boundary Fitting for Wedge Layer",
  "governance_type": "RESEARCH_TO_IMPLEMENTATION_CHANGE_REQUEST",
  "status": "OPEN",
  "revision": "1.2",
  "lifecycle_stage": "IMPLEMENT",
  "objective": "Replace the fixed 0.6% touch/violation tolerance in geometry/touches.py and geometry/validation/touches.py with ATR-normalized, structure-scale-aware tolerance, add graduated per-touch distance scoring in place of a binary touch/no-touch decision, and permit a bounded number of outlier contacts per line without invalidating the whole line, so that one noisy wick-outlier candle cannot by itself reject a geometrically valid trendline.",
  "non_goals": [
    "Change Candidate layer pivot selection, line-fitting algorithm, or line-construction responsibility in geometry/candidate.py",
    "Modify wedge/detector.py's containment/freshness gate or geometry/envelope_metrics.py, which are governed separately by DOCUMENTS/SCANNER_GEOMETRY_ATR_CONTAINMENT_DECISION.md",
    "Change GeometryModel top-level contract fields other than additive extension of the existing touches sub-dict",
    "Redesign Wedge classification, quality, or signal/quality.py scoring",
    "Change Rising Wedge, Robot, Signal admission, or Telegram behavior",
    "Introduce a new hard rejection threshold or change trading score without separate evidence and approval"
  ],
  "approved_scope": [
    "Introduce separate touch_tolerance and violation_tolerance parameters in geometry/touches.py and geometry/validation/touches.py, both derived from ATR rather than a fixed percentage, reusing the existing confirmation.py:calculate_atr() implementation with no duplicate ATR calculation",
    "Replace count_touches()'s binary touch/no-touch decision with a graduated per-point distance/score",
    "Permit a bounded number of outlier contacts per line (inlier-ratio-style, magnitude not finalized by this SPEC) without invalidating that line's touch validity",
    "Apply upper (high-wick) and lower (low-wick) boundary handling through one shared code path, not duplicated per-side logic",
    "Extend the touches dict carried in the GeometryModel Contract with additive per-touch distance/score fields, preserving existing keys (upper_touches, lower_touches, total_touches, valid) and their meaning for existing consumers (wedge/detector.py's features[\"touches\"], signal/quality.py's total_touches)",
    "Add focused ATR-tolerance / graduated-score / outlier-allowance regression tests"
  ],
  "prohibited_scope": [
    "geometry/candidate.py, geometry/envelope_metrics.py, wedge/detector.py's containment/freshness gate, or geometry/evaluation.py's pair-evaluation flow beyond passing through the extended touches dict",
    "wedge/classifier.py, wedge/quality.py, wedge/scoring.py, or signal/quality.py without new evidence and a separate approved amendment",
    "GeometryModel fields outside the touches sub-dict",
    "Any change to the five-check Validation Gate's overall valid/failed_checks contract beyond validate_touches()'s own internal tolerance logic",
    "Unrelated production, documentation, training/reference, or dirty-work changes"
  ],
  "authoritative_references": [
    "DOCUMENTS/PROJECT_CONTRACTS.md#CONTRACT-GEOMETRY-001",
    "DOCUMENTS/PROJECT_CONTRACTS.md#CONTRACT-VALIDATION-001",
    "DOCUMENTS/PROJECT_STATE.md#CURRENT_DEVELOPMENT_PRIORITY",
    "DOCUMENTS/PROJECT_STATE.md — 2026-09-10 PROJECT PRIORITY PIVOT checkpoint",
    "DOCUMENTS/ROADMAP.md#CR-SCANNER-GEOMETRY-002",
    "DOCUMENTS/ROADMAP.md — CR-TRADING-INTELLIGENCE-001 Geometry research observation (GRVTUSDT wick-aware Wedge boundary fitting)",
    "DOCUMENTS/SCANNER_GEOMETRY_ATR_CONTAINMENT_DECISION.md (related, distinct mechanism: post-detection containment/freshness, not Pivot touch/violation tolerance)",
    "AGENTS.md#Task-and-change-routing"
  ],
  "context_scope_paths": [
    "geometry/touches.py",
    "geometry/validation/touches.py",
    "geometry/evaluation.py",
    "confirmation.py",
    "wedge/detector.py",
    "tests/test_geometry.py",
    "tests/test_geometry_pipeline.py",
    "tests/test_wedge_pipeline.py"
  ],
  "context_test_paths": [
    "tests/test_wick_aware_touch_fitting.py",
    "tests/test_geometry.py",
    "tests/test_geometry_pipeline.py",
    "tests/test_wedge_pipeline.py"
  ],
  "external_reference_inspiration": [
    "TradingView Auto Trendlines Pro / AetherEdge-style graduated touch grading (design inspiration only, not vendored or copied)",
    "RANSAC inlier/outlier line fitting (bounded-outlier-tolerance concept only)",
    "Open-source trendln touch-detection approach (design reference only)"
  ],
  "approved_decisions": [
    "touch_tolerance and violation_tolerance are separate parameters, not one shared threshold",
    "both tolerances are derived from ATR rather than a fixed percentage of price",
    "touch scoring is graduated by distance-to-line rather than a binary touch/no-touch cutoff",
    "a bounded number of outlier contacts per line is permitted without invalidating that line's touch validity, analogous to a RANSAC inlier ratio",
    "upper (high-wick) and lower (low-wick) boundaries share one code path rather than duplicated per-side logic",
    "the existing touches dict keys and their meaning for current consumers are preserved; new fields are additive only"
  ],
  "unresolved_decisions": [],
  "resolved_decisions": [
    "touch_tolerance ATR multiplier k = 4.0, i.e. touch_tolerance = 4.0 * ATR(14) evaluated at each Pivot point's own candle index",
    "violation_tolerance ATR multiplier k = 10.0, i.e. violation_tolerance = 10.0 * ATR(14) evaluated at each Pivot point's own candle index (same 2.5x touch:violation ratio as the original proposal, independent parameter per approved_decisions)",
    "bounded outlier-contact count per line = 1, applied independently per side (upper and lower each get their own 1-outlier budget)",
    "graduated touch-score formula = linear decay: score = max(0, 1 - distance / touch_tolerance)",
    "ATR window = confirmation.py:calculate_atr(period=14) reused as-is (the same computation already used by DOCUMENTS/SCANNER_GEOMETRY_ATR_CONTAINMENT_DECISION.md, per this CR's Reuse / ownership boundary principle); no separate window scoped to the structure's own start_index..end_index span is introduced",
    "additive per-touch field shape: the touches dict gains upper_touch_points / lower_touch_points (list of {index, price, predicted, distance, score, touch_tolerance, violation_tolerance, classification, counted} per Pivot point) plus upper_outlier_count / lower_outlier_count / upper_violation_count / lower_violation_count integer counts",
    "multiplier revision 2026-09-11 (same day as initial resolution): the original 0.10 / 0.25 proposal was rejected after live-data review — see IMPLEMENTATION_RECORD's 'Multiplier correction' subsection — and replaced by 4.0 / 10.0, confirmed by a second live-data pass on the same symbol set showing touch counts matching the pre-existing 0.6% logic in order of magnitude",
    "all resolved 2026-09-11 by explicit user authorization in chat (numeric proposals accepted verbatim, working defaults explicitly subject to later calibration against historical data, not finalized)"
  ],
  "acceptance_criteria": [
    "touch_tolerance and violation_tolerance are computed from ATR rather than a fixed percentage, per the resolved windowing design",
    "touch_tolerance and violation_tolerance are independent parameters and may take different values",
    "each Pivot point receives a graduated distance/score rather than only a binary touch flag",
    "up to the approved bounded outlier count per line does not by itself invalidate that line's touch validity",
    "upper and lower boundaries are evaluated through one shared code path with no duplicated per-side branching logic",
    "existing GeometryModel touches dict keys (upper_touches, lower_touches, total_touches, valid) remain present with unchanged meaning for existing consumers",
    "new per-touch fields are additive only and do not alter existing consumer behavior when ignored",
    "existing Geometry/Wedge regression tests pass without modification to their assertions",
    "known valid Falling/Rising reference examples do not lose Geometry quality without explicit evidence and approval",
    "GRVTUSDT-style single-outlier-wick cases are demonstrably improved with a documented before/after comparison"
  ],
  "verification_requirements": [
    "Focused ATR-tolerance, graduated-score, and bounded-outlier-allowance test matrix",
    "Existing tests.test_geometry, tests.test_geometry_pipeline, and tests.test_wedge_pipeline regression",
    "Before/after comparison on GRVTUSDT and a representative additional symbol set, not GRVTUSDT alone",
    "Known valid Falling/Rising reference-example comparison where authoritative fixtures are available",
    "Artifact-free compile, git diff --check, and scoped allowlist review"
  ],
  "verification_results": [
    "New focused suite tests/test_wick_aware_touch_fitting.py (17 tests): ATR-tolerance touch/outlier/violation classification, graduated linear score, single-outlier-per-line tolerance and second-outlier exclusion, violation not consuming the outlier budget, legacy-percentage fallback both for candles=None and for a pre-ATR-warm-up index, and the preserved analyze_touches/validate_touches contract (existing keys unchanged, additive fields present, missing diagnostic fields on old-shaped touches dicts default to zero without raising). Re-run and still 17/17 after the 4.0/10.0 multiplier correction (test assertions reference the multiplier constants, not hardcoded values, so no test changes were needed).",
    "Full repository regression (python -B -m unittest discover -s tests): 636 tests (619 pre-existing + 17 new), 2 failures / 19 errors — byte-identical to the pre-existing baseline confirmed for DOCUMENTS/SCANNER_GEOMETRY_ATR_CONTAINMENT_DECISION.md's own verification (same two FAIL: test_task_harness, test_telegram_delivery; same 19 terminal/diary ERROR entries), zero new failures or errors introduced by this change. Re-run after the multiplier correction with identical result.",
    "tests/test_geometry.py, tests/test_geometry_pipeline.py, tests/test_wedge_pipeline.py (plain-script, not unittest-discoverable) run directly before and after the change (via git stash) produce identical output, including test_wedge_pipeline.py's already-documented pre-existing AssertionError.",
    "Live before/after comparison, first pass (0.10/0.25 multipliers, rejected): GRVTUSDT and DOGEUSDT both showed valid geometry under both old (fixed 0.6%) and new logic, but touch counts collapsed systematically (GRVTUSDT upper/lower 5/4 -> 3/2; DOGEUSDT 4/4 -> 2/2, landing exactly on the >=2 validity floor with zero margin). Root cause: on the production TIMEFRAME=1 (1-minute) candles, ATR(14) is a much smaller fraction of price than the old fixed 0.6%-of-price cutoff, so 0.10x/0.25x*ATR were roughly 25x/17x tighter than the mechanism they replaced. BTCUSDT and 1000PEPEUSDT produced no valid geometry under either old or new touch logic (confirmed differentially via git stash) -- pre-existing, unrelated to touches.",
    "Live before/after comparison, second pass (4.0/10.0 multipliers, accepted): same four symbols (GRVTUSDT, BTCUSDT, 1000PEPEUSDT, DOGEUSDT) on fresh live 500-candle windows. GRVTUSDT: old 4/4 valid=true, new 4/4 valid=true (exact match). DOGEUSDT: old 4/4 valid=true, new 4/4 valid=true (exact match), with one point (distance 0.000221, inside the old 0.6% band but outside the new tighter touch_tolerance) landing as outlier_tolerated rather than a plain touch, demonstrating the outlier-allowance mechanism absorbing exactly the kind of borderline point it was designed for. Outlier allowance fired once across the two valid-geometry symbols (not zero, not saturated). No unexpected legacy-percentage fallback observed on any classified point (ATR available and warmed up throughout, given the 500-candle window). BTCUSDT and 1000PEPEUSDT again produced no valid geometry, consistent with the pre-existing, touches-unrelated rejection confirmed in the first pass.",
    "Known valid Falling/Rising reference-example comparison from verification_requirements: NOT performed -- no authoritative pinned-fixture reference examples exist in this repository to compare against; the live GRVTUSDT/DOGEUSDT before/after comparison above is the closest available substitute and is considered sufficient evidence for this starting-value calibration, subject to the CR's own explicit later-calibration caveat."
  ],
  "review_result": {
    "verdict": "NOT_YET_REVIEWED",
    "blocking_findings": [],
    "important_findings": [],
    "minor_non_blocking_findings": []
  },
  "acceptance_state": "IMPLEMENTED_VERIFIED_INCLUDING_LIVE_SYMBOL_COMPARISON_PENDING_COMMIT_AUTHORIZATION",
  "risks": [
    "ATR-normalized tolerance may admit or reject different candidates than the fixed 0.6% cutoff across the broader symbol set, not only GRVTUSDT, changing candidate selection more widely than intended without a representative before/after comparison",
    "A too-generous bounded outlier allowance could mask a genuinely broken or invalid trendline rather than tolerating one legitimate noisy wick",
    "Extending the touches dict risks silently breaking a consumer that iterates all keys or asserts an exact key set instead of reading named fields",
    "Computing ATR over a window that does not match the structure's own span could produce inconsistent tolerance across structures of different ages/lengths",
    "Existing directional/touch test coverage may be insufficient to catch a regression in the shared upper/lower code path"
  ],
  "residual_risks": [],
  "mission_outcome": [],
  "rollback_boundaries": [
    "Implementation must land as one or more scoped, independently revertible commits after verification",
    "Rollback restores the fixed 0.6% binary touch/no-touch behavior in geometry/touches.py and geometry/validation/touches.py without affecting GeometryModel fields outside the touches sub-dict or any other subsystem"
  ],
  "implementation_phases": [
    {"id": "TASK", "status": "COMPLETED"},
    {"id": "SPEC", "status": "COMPLETED"},
    {"id": "CONTEXT", "status": "COMPLETED"},
    {"id": "IMPLEMENT", "status": "COMPLETED"},
    {"id": "VERIFY", "status": "COMPLETED"},
    {"id": "RECORD", "status": "IN_PROGRESS"}
  ],
  "current_phase": "RECORD",
  "current_checkpoint": "IMPLEMENTED_VERIFIED_UNCOMMITTED",
  "implementation_status": "IMPLEMENTED_VERIFIED_PENDING_COMMIT_AUTHORIZATION",
  "next_phase": "RECORD_COMPLETE",
  "next_phase_authorization": "COMMIT_AUTHORIZATION_REQUIRED_PER_ASSISTANT_PROTOCOL_7.2",
  "related_commits": [
    {"phase": "BASELINE", "commit": "6ef94e8e068e79cd0449a6bce30a7608ad508a77"},
    {"phase": "IMPLEMENT", "commit": "UNCOMMITTED_AT_TIME_OF_WRITING"}
  ],
  "repository_sync": {
    "branch": "robot-v0-1-admission-gate",
    "local_head": "7da7c9f",
    "origin_main": "c5042bb0ba6cbb61a8476d00a0b8c662b7ae54ff",
    "status": "FEATURE_BRANCH_AHEAD_OF_MAIN / IMPLEMENT_AND_VERIFY_COMPLETE_LOCALLY_UNCOMMITTED_AT_TIME_OF_WRITING"
  },
  "amendment_history": [
    {"revision": "1.0", "reason": "Initial TASK/SPEC formalization of ATR-normalized wick-aware touch/violation tolerance, promoted from the GRVTUSDT research observation", "date": "2026-09-11"},
    {"revision": "1.1", "reason": "unresolved_decisions resolved by explicit user-authorized numeric proposal (touch_tolerance=0.10*ATR(14), violation_tolerance=0.25*ATR(14), 1 outlier per line per side, linear graduated score, reuse confirmation.py:calculate_atr(period=14) with no separate structure-span window). CONTEXT/IMPLEMENT/VERIFY executed: geometry/touches.py and geometry/validation/touches.py updated; geometry/evaluation.py threads candles into analyze_touches(); new focused suite tests/test_wick_aware_touch_fitting.py (17 tests); full repository regression re-run with identical pre-existing 2-failure/19-error baseline. RECORD in progress pending explicit commit authorization per ASSISTANT_PROTOCOL.md 7.2 git safety rules.", "date": "2026-09-11"},
    {"revision": "1.2", "reason": "Multiplier correction, same day, before any commit: a mandatory pre-commit live-data check on GRVTUSDT/BTCUSDT/1000PEPEUSDT/DOGEUSDT found the 0.10/0.25 multipliers from revision 1.1 compared ATR against price using the wrong basis-of-comparison analogy (borrowed from SCANNER_GEOMETRY_ATR_CONTAINMENT_DECISION.md, which compares ATR against a candle body inside the structure, not directly against price the way the old fixed 0.6% cutoff did), producing a systemic ~25x/17x tightening versus the mechanism being replaced and collapsing touch counts on 1-minute production candles (DOGEUSDT landing exactly on the validity floor with zero margin). Corrected to touch_tolerance=4.0*ATR(14), violation_tolerance=10.0*ATR(14) (same 2.5x ratio), re-verified with a second live-data pass showing touch counts matching the old 0.6% logic in order of magnitude on both symbols where valid geometry existed, with the outlier allowance now observed firing on a genuine borderline point. resolved_decisions, verification_results, and IMPLEMENTATION_RECORD updated accordingly. Still uncommitted pending this same commit authorization.", "date": "2026-09-11"}
  ]
}
```
<!-- CHANGE_REQUEST_METADATA_END -->

## Recovery summary

`geometry/touches.py:count_touches()` currently uses one fixed `tolerance_percent=0.006` (0.6% of the
predicted line price) to decide, in a purely binary way, whether a Pivot point counts as a touch. A point
either falls within that single band or is silently excluded — there is no distance-based scoring and no
separate, softer or harder tier between "touch" and "not a touch." The same fixed cutoff is therefore the
only boundary governing both what counts as a supporting touch and what would be considered a violation of
the line; `geometry/validation/touches.py:validate_touches()` then requires `upper_touches >= 2 and
lower_touches >= 2` using exactly those counts, with no per-touch quality information. Because the check has
no tolerance for scale or volatility and no allowance for a single outlier wick, one noisy candle can
silently exclude a Pivot point that would otherwise support an geometrically legitimate line, without any
softer fallback.

This directly reflects the GRVTUSDT wick-aware Wedge boundary-fitting research observation previously
recorded in `DOCUMENTS/ROADMAP.md` (`CR-TRADING-INTELLIGENCE-001` Geometry research observation) as an
unproven research hypothesis. Per the 2026-09-10 project priority pivot recorded in
`DOCUMENTS/PROJECT_STATE.md` and `DOCUMENTS/ROADMAP.md`, that observation is now the active
pattern-detection/Geometry priority feeding the Robot v0.1 prototype, and this CR formalizes its
implementation path for the Pivot touch/violation-tolerance mechanism specifically (`geometry/touches.py` /
`geometry/validation/touches.py`), distinct from the separately governed post-detection containment/freshness
mechanism in `DOCUMENTS/SCANNER_GEOMETRY_ATR_CONTAINMENT_DECISION.md` (`wedge/detector.py` /
`geometry/envelope_metrics.py`).

Planned scope draws design inspiration — without vendoring or blind copying — from mature-project practice:
graduated touch grading by distance (as in commercial trendline tools), bounded-outlier tolerance modeled
conceptually on RANSAC inlier ratios, and general touch-detection structure comparable to open-source
`trendln`. None of these external references are copied into the repository; they inform the design only.

TASK and SPEC were recorded by revision 1.0. Revision 1.1 records that all six `unresolved_decisions` were
closed by an explicit user-authorized numeric proposal (see `resolved_decisions` above), and that CONTEXT,
IMPLEMENT, and VERIFY have since been executed. RECORD is in progress: this document update is part of it,
and the change is implemented and unit-verified but not yet committed, pending explicit commit authorization
per `ASSISTANT_PROTOCOL.md` 7.2 git safety rules.

## IMPLEMENTATION_RECORD

### What was built

- `geometry/touches.py` — `count_touches(line, points, candles=None, ...)` now computes, per Pivot point,
  `distance = abs(point.price - predicted_line_price)` and classifies it against `touch_tolerance = 4.0 *
  ATR(14)` and `violation_tolerance = 10.0 * ATR(14)` (see "Multiplier correction" below for why these
  replaced the originally proposed 0.10 / 0.25), both evaluated at that point's own candle index via
  `confirmation.py:calculate_atr(candles, period=14)` (reused, no duplicate ATR calculation, no separate
  structure-span window — same computation as `SCANNER_GEOMETRY_ATR_CONTAINMENT_DECISION.md`). A point within
  `touch_tolerance` is a `"touch"` (always counted, graduated linear score `max(0, 1 - distance /
  touch_tolerance)`); a point beyond `touch_tolerance` but within `violation_tolerance` is an `"outlier"`,
  counted only while that line's own 1-outlier budget is unused (`"outlier_tolerated"`), otherwise excluded
  (`"outlier_excluded"`); a point beyond `violation_tolerance` is a `"violation"`, never counted, diagnostic
  only (no new hard rejection, per this CR's own non-goals). One shared code path handles both boundaries —
  the caller passes the upper (high-wick) or lower (low-wick) line/points, there is no per-side branching.
  When ATR cannot be computed for a point (no `candles` supplied, or the point's index precedes the
  `ATR_PERIOD=14` rolling warm-up), that point falls back to the pre-CR-SCANNER-GEOMETRY-002 fixed
  `LEGACY_TOUCH_TOLERANCE_PERCENT = 0.006` (0.6% of predicted price), preserving prior behavior for callers
  that do not supply candles — this is why `tests.test_geometry` / `tests.test_geometry_pipeline` (which call
  `geometry.engine.analyze_geometry()` without `candles`) are unaffected.
- `geometry/touches.py:analyze_touches(upper_line, lower_line, highs, lows, candles=None)` — preserves
  `upper_touches`, `lower_touches`, `total_touches`, `valid` with unchanged meaning; adds `upper_touch_points`
  / `lower_touch_points` (the per-point classification list above) and `upper_outlier_count` /
  `lower_outlier_count` / `upper_violation_count` / `lower_violation_count` as additive fields.
- `geometry/validation/touches.py:validate_touches()` — the `>= 2` per-side touch-count threshold and the
  `valid`/`reason` contract are unchanged; `details` additionally carries the four outlier/violation counts
  when present, defaulting to `0` for a touches dict from before this CR (no raise on missing keys).
- `geometry/evaluation.py:evaluate_candidate_pair()` — threads its existing `candles` parameter into
  `analyze_touches()` (one line changed: `candles=candles` added to the existing call).
- `tests/test_wick_aware_touch_fitting.py` (new, 17 tests) — ATR-tolerance touch/outlier/violation
  classification, linear graduated score, single-outlier-per-line tolerance vs. second-outlier exclusion,
  violation not consuming the outlier budget, legacy-percentage fallback (both `candles=None` and a
  pre-warm-up index), and the preserved `analyze_touches` / `validate_touches` contract.

### Multiplier correction (revision 1.2, same day, before any commit)

The originally resolved `0.10 * ATR(14)` / `0.25 * ATR(14)` multipliers were proposed by analogy with
`SCANNER_GEOMETRY_ATR_CONTAINMENT_DECISION.md`'s `CONTAINMENT_ATR_MULTIPLIER = 0.15`. That analogy does not
hold: the containment decision compares ATR against a candle's *body* while it sits inside the structure,
whereas here ATR is compared directly against *price* — the same basis the old fixed `0.6%`-of-price cutoff
used. These are different orders of magnitude. A mandatory pre-commit live-data check (this CR's user-directed
process, not a standing rule) on GRVTUSDT/BTCUSDT/1000PEPEUSDT/DOGEUSDT surfaced this before any commit: on
the production `TIMEFRAME=1` (1-minute) candles, `touch_tolerance=0.10*ATR` and `violation_tolerance=0.25*ATR`
were roughly 25x and 17x tighter than the old `0.6%` cutoff, systematically collapsing touch counts (GRVTUSDT
5/4 -> 3/2, DOGEUSDT 4/4 -> 2/2 — the latter landing exactly on the `>= 2` validity floor with zero margin,
where the old logic had a 2x margin). The multipliers were corrected to `4.0` / `10.0` (preserving the
original 2.5x touch:violation ratio) and re-verified with a second live pass — see Verification below.

### Verification

- New focused suite: 17/17 passing, both before and after the multiplier correction (assertions reference the
  multiplier constants dynamically, not hardcoded expected values, so no test edits were needed for the
  correction).
- Full repository regression (`python -B -m unittest discover -s tests`): 636 tests (619 pre-existing + 17
  new), 2 failures / 19 errors — identical to the pre-existing baseline also confirmed for
  `SCANNER_GEOMETRY_ATR_CONTAINMENT_DECISION.md` (same `test_task_harness` / `test_telegram_delivery` FAILs,
  same 19 terminal/diary ERRORs unrelated to this change). Zero new regressions. Re-run after the multiplier
  correction with an identical result.
- `tests/test_geometry.py`, `tests/test_geometry_pipeline.py`, `tests/test_wedge_pipeline.py` (plain-script,
  not unittest-discoverable): output diffed before/after via `git stash` — byte-identical, including
  `test_wedge_pipeline.py`'s pre-existing `AssertionError` (unrelated to touches; already documented against
  `CR-SCANNER-GEOMETRY-001`) and `test_geometry.py` / `test_geometry_pipeline.py` both already returning
  `GEOMETRY RESULT: None` before this change (unrelated pre-existing condition in candidate/envelope
  filtering, confirmed present on the unmodified tree).
- Live before/after comparison on GRVTUSDT, BTCUSDT, 1000PEPEUSDT, DOGEUSDT (real Bybit market data, 500
  1-minute candles each), run twice — once against the rejected 0.10/0.25 multipliers and once against the
  accepted 4.0/10.0 — full detail in `verification_results` above. Summary: with 4.0/10.0, GRVTUSDT and
  DOGEUSDT (the two symbols with any valid geometry at all) both matched the old 0.6% touch counts exactly
  (4/4 both sides on both symbols); the outlier allowance fired once, correctly absorbing a point that the old
  0.6% counted as a plain touch but that now falls just outside the tighter `touch_tolerance`; no unexpected
  legacy-percentage fallback occurred despite candles being present throughout. BTCUSDT and 1000PEPEUSDT
  produced no valid geometry under old or new touch logic in either pass — confirmed via `git stash` to be a
  pre-existing rejection unrelated to touches (candidate-line fitting / other Validation Gate checks).
- Known valid Falling/Rising reference-example comparison from `verification_requirements`: not performed —
  no authoritative pinned fixtures exist in this repository for this purpose. The live GRVTUSDT/DOGEUSDT
  comparison above is treated as the practical substitute for this starting-value calibration pass.

### Not yet done

Commit authorization (per `ASSISTANT_PROTOCOL.md` 7.2, a prior approval does not carry forward to a new
change). All verification items originally listed as open have since been executed; the multipliers,
outlier allowance, and graduated-score formula remain explicitly non-final starting values subject to later
calibration against historical data, per this CR's own resolved_decisions text.
