# CR-SCANNER-GEOMETRY-FORMATION-FIT-001

<!-- CHANGE_REQUEST_METADATA_BEGIN -->
```json
{
  "schema_version": "1.0",
  "id": "CR-SCANNER-GEOMETRY-FORMATION-FIT-001",
  "title": "Reject sustained body mismatch within each boundary formation interval",
  "status": "VERIFIED",
  "revision": "1.0",
  "lifecycle_stage": "RECORD",
  "objective": "Correct unsupported candidate boundaries with sustained own-anchor..END body evidence and evidence-backed historical reference revision.",
  "current_phase": "RECORD",
  "current_checkpoint": "TARGETED_HISTORICAL_TESTS_PASSED",
  "implementation_status": "IMPLEMENTED_VERIFIED",
  "next_phase": "PUBLISH",
  "next_phase_authorization": "One PR explicitly requested; merge/runtime launch not included.",
  "non_goals": [
    "Trading/risk changes, service operations, full Scanner run, universal containment calibration"
  ],
  "approved_scope": [
    "geometry/envelope_metrics.py",
    "geometry/engine.py",
    "tests/test_geometry_boundary_validity.py",
    "tests/test_geometry_candidate_selection_freshness.py",
    "tests/test_geometry_locality_admission.py",
    "tests/test_geometry_formation_fit.py",
    "tests/fixtures/geometry_formation_fit/historical_cases.json",
    "DOCUMENTS/SCANNER_GEOMETRY_ATR_CONTAINMENT_DECISION.md",
    "DOCUMENTS/SCANNER_GEOMETRY_CURRENT_COURSE.md",
    "DOCUMENTS/BACKLOG.md"
  ],
  "context_scope_paths": [
    "geometry/envelope_metrics.py",
    "geometry/engine.py",
    "tests/test_geometry_boundary_validity.py",
    "tests/test_geometry_candidate_selection_freshness.py",
    "tests/test_geometry_locality_admission.py",
    "tests/test_geometry_formation_fit.py",
    "tests/fixtures/geometry_formation_fit/historical_cases.json",
    "DOCUMENTS/SCANNER_GEOMETRY_ATR_CONTAINMENT_DECISION.md",
    "DOCUMENTS/SCANNER_GEOMETRY_CURRENT_COURSE.md",
    "DOCUMENTS/BACKLOG.md"
  ],
  "context_test_paths": [
    "tests/test_geometry_formation_fit.py",
    "tests/test_geometry_boundary_validity.py",
    "tests/test_geometry_candidate_selection_freshness.py",
    "tests/test_geometry_locality_admission.py",
    "tests/test_scanner_geometry_atr_containment.py"
  ],
  "prohibited_scope": [
    "User-owned files, other worktrees, global generator spacing, coin-specific rules, order execution"
  ],
  "authoritative_references": [
    "DOCUMENTS/SCANNER_GEOMETRY_ATR_CONTAINMENT_DECISION.md#approved-bounded-revision",
    "DOCUMENTS/SCANNER_GEOMETRY_CURRENT_COURSE.md",
    "DOCUMENTS/BACKLOG.md#1a-current-queue"
  ],
  "approved_decisions": [
    "Owner permits evidence-backed revision of defective references and forbids automatic rejection of isolated candle excursions.",
    "Implement the exact bounded sustained-run rule recorded before code in the owning decision; keep trading containment penalties disabled."
  ],
  "unresolved_decisions": [],
  "acceptance_criteria": [
    "Eleven historical cases have exact anchor/line/START/END and per-boundary evidence assertions.",
    "One candle does not reject; post-END and pre-own-anchor evidence do not reject.",
    "AEVO/INJ/WLD revisions carry old-boundary candle evidence rather than relabeled expected indices."
  ],
  "verification_requirements": [
    "Historical eleven-window replay and sensitivity 4..8",
    "Focused formation, selection, locality, boundary and ATR tests",
    "Protected task finish and defect-focused review"
  ],
  "risks": [
    "Bounded sample does not establish universal calibration; short or intermittent violations may remain.",
    "WLD changes to an earlier supported triangle, not the previous wedge."
  ],
  "rollback_boundaries": [
    "Revert this scoped PR without touching runtime state or user-owned data."
  ],
  "implementation_phases": [
    {
      "id": "SPEC"
    },
    {
      "id": "IMPLEMENT"
    },
    {
      "id": "VERIFY"
    },
    {
      "id": "RECORD"
    },
    {
      "id": "PUBLISH"
    },
    {
      "id": "DONE"
    }
  ],
  "related_commits": [
    "5bc3572924cb0ee07910fd9f091b1ff36ba61453"
  ],
  "amendment_history": [],
  "implementation_summary": [
    "Two production files: shared formation-body evidence and replacement of single pivot/body veto by sustained-run admission.",
    "Existing ranking key consumes own-anchor..END counts; legacy diagnostic metrics and trading score remain unchanged.",
    "Committed eleven-case candle/line evidence supersedes ignored AEVO immutability assertions."
  ],
  "verification_results": [
    "Historical suite: exact lines, anchors, START/END, old-boundary candle defects, post-END invariance and sensitivity 4..8 passed.",
    "Boundary unit suite: 9 tests passed, including isolated pivot/body tolerance, both sides, anchor clipping and at-END behavior.",
    "Existing selection/locality/ATR suites passed in development loop; protected final task verification follows."
  ],
  "review_result": {
    "verdict": "No material defects found in reviewed scope",
    "scope": "Two Geometry production files, scoped contract and eleven-case offline regressions; no runtime/trading changes."
  }
}
```
<!-- CHANGE_REQUEST_METADATA_END -->
