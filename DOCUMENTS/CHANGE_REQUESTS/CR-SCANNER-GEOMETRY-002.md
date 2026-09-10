# CR-SCANNER-GEOMETRY-002 — ATR-Normalized Wick-Aware Boundary Fitting for Wedge Layer

<!-- CHANGE_REQUEST_METADATA_BEGIN -->
```json
{
  "schema_version": "1.0",
  "id": "CR-SCANNER-GEOMETRY-002",
  "title": "ATR-Normalized Wick-Aware Boundary Fitting for Wedge Layer",
  "governance_type": "RESEARCH_TO_IMPLEMENTATION_CHANGE_REQUEST",
  "status": "OPEN",
  "revision": "1.0",
  "lifecycle_stage": "SPEC",
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
  "unresolved_decisions": [
    "exact ATR multiplier k for touch_tolerance — not specified, requires a numeric proposal and separate approval before IMPLEMENT",
    "exact ATR multiplier k for violation_tolerance — expected to differ from the touch-tolerance multiplier, not specified",
    "exact bounded outlier-contact count per line — the planning discussion's '1 per line' is illustrative, not confirmed final",
    "exact graduated touch-score formula shape (e.g. linear decay vs. other function of distance) — not specified",
    "exact ATR window definition — whether ATR is computed over confirmation.py:calculate_atr()'s existing recent-N-candle window as-is, or specifically over the structure's own start_index..end_index span ('ATR на окне структуры'), which may differ from the existing default window and requires explicit design before IMPLEMENT",
    "exact additive field names/shape for per-touch distance/score in the touches dict"
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
  "verification_results": [],
  "review_result": {
    "verdict": "NOT_YET_REVIEWED",
    "blocking_findings": [],
    "important_findings": [],
    "minor_non_blocking_findings": []
  },
  "acceptance_state": "NOT_APPLICABLE_SPEC_STAGE",
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
    {"id": "CONTEXT", "status": "NOT_STARTED"},
    {"id": "IMPLEMENT", "status": "NOT_STARTED"},
    {"id": "VERIFY", "status": "NOT_STARTED"},
    {"id": "RECORD", "status": "NOT_STARTED"}
  ],
  "current_phase": "SPEC",
  "current_checkpoint": "SPEC_RECORDED_CONTEXT_NOT_STARTED",
  "implementation_status": "NOT_STARTED_NOT_AUTHORIZED",
  "next_phase": "CONTEXT",
  "next_phase_authorization": "REQUIRED_EXPLICIT_HUMAN_AUTHORIZATION",
  "related_commits": [
    {"phase": "BASELINE", "commit": "6ef94e8e068e79cd0449a6bce30a7608ad508a77"}
  ],
  "repository_sync": {
    "branch": "robot-v0-1-admission-gate",
    "local_head": "6ef94e8e068e79cd0449a6bce30a7608ad508a77",
    "origin_main": "c5042bb0ba6cbb61a8476d00a0b8c662b7ae54ff",
    "status": "FEATURE_BRANCH_AHEAD_OF_MAIN / SPEC_RECORDED_LOCALLY_UNCOMMITTED_AT_TIME_OF_WRITING"
  },
  "amendment_history": [
    {"revision": "1.0", "reason": "Initial TASK/SPEC formalization of ATR-normalized wick-aware touch/violation tolerance, promoted from the GRVTUSDT research observation", "date": "2026-09-11"}
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

TASK and SPEC are recorded by this revision. CONTEXT, IMPLEMENT, VERIFY, and RECORD have not started and are
not authorized. In particular, the ATR multipliers for `touch_tolerance` and `violation_tolerance`, the exact
bounded-outlier count, the graduated-score formula, and the exact ATR windowing (existing
`confirmation.py:calculate_atr()` default window vs. a window scoped to the structure's own span) are
unresolved decisions requiring explicit numeric proposals and separate approval before implementation begins.
