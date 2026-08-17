# CR-SCANNER-GEOMETRY-001 — Consolidate Directional Envelope Ownership in Wedge Layer

<!-- CHANGE_REQUEST_METADATA_BEGIN -->
```json
{
  "schema_version": "1.0",
  "id": "CR-SCANNER-GEOMETRY-001",
  "title": "Consolidate Directional Envelope Ownership in Wedge Layer",
  "status": "CLOSED",
  "revision": "1.4",
  "lifecycle_stage": "RECORD",
  "objective": "Apply directional envelope semantics in the Wedge Layer after operational pattern determination and remove the premature opposite-side interpretation from the Geometry Layer.",
  "non_goals": [
    "Change Geometry ranking, candidate generation, pair metrics, GeometryModel or the Geometry-to-Wedge contract",
    "Introduce a new hard pivot-envelope threshold or change trading score without separate evidence and approval",
    "Redesign Wedge classification, quality or scoring",
    "Modify production behavior outside directional envelope ownership"
  ],
  "approved_scope": [
    "Remove the premature pattern-like directional downgrade from geometry/evaluation.py while preserving raw direction-neutral metrics",
    "Extend wedge/integrity.py with pattern-aware STRICT and EXCURSION interpretation using existing envelope metrics",
    "Integrate directional envelope evaluation in wedge/detector.py only after the operational pattern is known",
    "Add focused directional matrix and regression tests"
  ],
  "prohibited_scope": [
    "geometry/ranking.py, geometry/envelope_metrics.py, geometry/pair_metrics.py or geometry/engine.py without new evidence and approved amendment",
    "wedge/classifier.py, wedge/quality.py or wedge/scoring.py without new evidence and approved amendment",
    "GeometryModel or Geometry-to-Wedge contract changes",
    "Unrelated production, documentation, training/reference or dirty-work changes"
  ],
  "authoritative_references": [
    "DOCUMENTS/PROJECT_CONTRACTS.md#CONTRACT-GEOMETRY-001",
    "DOCUMENTS/PROJECT_STATE.md#SCANNER_GEOMETRY_STATE",
    "DOCUMENTS/ROADMAP.md#CR-SCANNER-GEOMETRY-001",
    "AGENTS.md#Task-and-change-routing"
  ],
  "context_scope_paths": [
    "geometry/evaluation.py",
    "geometry/ranking.py",
    "geometry/envelope_metrics.py",
    "wedge/integrity.py",
    "wedge/detector.py",
    "wedge/classifier.py",
    "wedge/quality.py",
    "wedge/scoring.py",
    "tests/test_geometry.py",
    "tests/test_geometry_pipeline.py",
    "tests/test_wedge_pipeline.py"
  ],
  "context_test_paths": [
    "tests/test_directional_envelope_quality.py",
    "tests/test_geometry.py",
    "tests/test_geometry_pipeline.py",
    "tests/test_wedge_pipeline.py"
  ],
  "approved_decisions": [
    "Final operational direction is owned by the Wedge detector after Geometry construction",
    "Falling uses upper STRICT and lower EXCURSION; Rising uses lower STRICT and upper EXCURSION; Triangle uses both STRICT",
    "Geometry remains direction-neutral and rank_geometry remains symmetric",
    "Existing envelope metrics are reused; no parallel metric calculation is introduced",
    "Pivot-envelope directional quality is diagnostic/soft in this iteration"
  ],
  "implementation_summary": [
    "Removed the opposite Rising-upper and Falling-lower 0.20 directional downgrade from geometry/evaluation.py while preserving raw symmetric metrics and direction-neutral checks",
    "Added Wedge-owned Falling, Rising and Triangle STRICT/EXCURSION roles in wedge/integrity.py using existing envelope_metrics",
    "Integrated diagnostic directional evaluation in wedge/detector.py only after operational pattern determination",
    "Preserved strict-side full-candle run rejection above 2 and excursion-only non-rejection",
    "Introduced no hard pivot threshold, trading-score effect or GeometryModel/Geometry-to-Wedge contract change"
  ],
  "unresolved_decisions": [],
  "acceptance_criteria": [
    "Final direction is determined only after Geometry construction in the Wedge detector",
    "Falling Wedge assigns upper STRICT and lower EXCURSION",
    "Rising Wedge assigns lower STRICT and upper EXCURSION",
    "Triangle assigns both boundaries STRICT",
    "Geometry collects raw envelope metrics and remains direction-neutral",
    "rank_geometry remains symmetric and receives no Wedge pattern",
    "Existing envelope_metrics are reused without parallel calculation",
    "The existing severe strict-side candle-run rule greater than 2 is preserved",
    "An excursion-only violation is not independently a hard rejection",
    "Pivot-envelope directional quality remains diagnostic/soft; no new hard threshold or trading-score change is introduced",
    "The old opposite directional mapping is removed from geometry/evaluation.py and enforcement is not duplicated",
    "Focused directional matrix and existing Geometry/Wedge regression tests pass",
    "Known valid Falling/Rising examples do not lose Geometry quality without explicit evidence and approval"
  ],
  "verification_requirements": [
    "Focused Falling, Rising and Triangle STRICT/EXCURSION matrix tests",
    "Strict-side run boundary and excursion-only non-rejection tests",
    "Geometry ranking upper/lower symmetry regression test",
    "Existing Geometry and Wedge focused regression tests",
    "Known valid Falling/Rising reference-example comparison where authoritative fixtures are available",
    "Artifact-free compile, git diff --check and scoped allowlist review"
  ],
  "verification_results": [
    "Durable governance gate PASS",
    "Focused directional tests: 11 of 11 OK",
    "tests.test_geometry PASS",
    "tests.test_geometry_pipeline PASS",
    "Artifact-free compile PASS",
    "git diff --check PASS",
    "Protected-file allowlist PASS",
    "tests.test_wedge_pipeline has a confirmed pre-existing failure: committed HEAD also returns Geometry None before Wedge detector execution"
  ],
  "review_result": {
    "verdict": "READY_FOR_RECORD",
    "blocking_findings": [],
    "important_findings": [],
    "minor_non_blocking_findings": [
      "directional_envelope is exposed both top-level and inside features",
      "diagnostic output retains complete boundary metric dictionaries",
      "explicit run-equals-2 coverage is not separate for Rising and Triangle"
    ]
  },
  "acceptance_state": "SATISFIED_WITH_MANUAL_REFERENCE_VALIDATION_DEFERRED",
  "criterion_13_disposition": "NO_DEGRADATION_EVIDENCE_FOUND / MANUAL_REFERENCE_VALIDATION_DEFERRED",
  "criterion_13_reason": [
    "No authoritative executable reference-example regression harness currently exists",
    "Creating a new harness would expand the approved scope",
    "Candidate selection may change because the obsolete Geometry downgrade was removed"
  ],
  "risks": [
    "Removing the current CANONICAL-to-EXPLORATORY downgrade may change Geometry candidate selection",
    "The current pivot outside ratio 0.20 must not become a hard rejection without evidence",
    "Retaining old Geometry enforcement while adding Wedge enforcement would duplicate the gate",
    "Pivot outside metrics and severe full-candle containment are distinct signals and must not be mixed",
    "Existing directional-boundary test coverage is insufficient"
  ],
  "residual_risks": [
    "Candidate selection can change after removal of the obsolete CANONICAL-to-EXPLORATORY downgrade",
    "Known valid Falling/Rising examples still require separately authorized manual or automated reference validation",
    "The pre-existing tests.test_wedge_pipeline fixture remains unable to reach Wedge detection"
  ],
  "mission_outcome": [
    "Directional envelope ownership is consolidated in the Wedge Layer after operational pattern determination",
    "Geometry remains direction-neutral and the obsolete opposite-side 0.20 downgrade is removed",
    "STRICT/EXCURSION semantics and focused directional regression coverage are implemented and verified",
    "Acceptance is satisfied with manual reference validation deferred as recorded by criterion 13",
    "Production checkpoint commit 405aaf1bf6889fd51d07c478cf064c29c5620d41 was pushed with local main synchronized to origin/main"
  ],
  "rollback_boundaries": [
    "Implementation must be one scoped, independently revertible mission commit after verification",
    "Rollback restores the previous Geometry evaluation and Wedge integrity/detector behavior without changing GeometryModel or unrelated subsystems"
  ],
  "implementation_phases": [
    {"id": "SPEC", "status": "PRE_IMPLEMENTATION_CHECKPOINT"},
    {"id": "IMPLEMENT", "status": "COMPLETED"},
    {"id": "VERIFY", "status": "IMPLEMENTED_VERIFIED"},
    {"id": "RECORD", "status": "REVIEW_COMPLETED"},
    {"id": "CHECKPOINT_COMMIT", "status": "COMPLETED"},
    {"id": "MISSION_CLOSE", "status": "COMPLETED"},
    {"id": "NO_NEXT_PHASE", "status": "NOT_APPLICABLE"}
  ],
  "current_phase": "MISSION_CLOSE",
  "current_checkpoint": "MISSION_CLOSE_COMPLETED",
  "implementation_status": "IMPLEMENTED_VERIFIED",
  "next_phase": "NO_NEXT_PHASE",
  "next_phase_authorization": "NOT_APPLICABLE",
  "related_commits": [
    {"phase": "BASELINE", "commit": "6a1ee60908a95721db0367ccc6b2b0ff217af039"},
    {"phase": "PRE_IMPLEMENTATION_CHECKPOINT", "commit": "3fcbf8160ffc4eb4c41940560cbea76514d661e4"},
    {"phase": "IMPLEMENT_VERIFY_RECORD", "commit": "405aaf1bf6889fd51d07c478cf064c29c5620d41"}
  ],
  "repository_sync": {
    "branch": "main",
    "local_head": "405aaf1bf6889fd51d07c478cf064c29c5620d41",
    "origin_main": "405aaf1bf6889fd51d07c478cf064c29c5620d41",
    "status": "SYNCHRONIZED"
  },
  "amendment_history": [
    {"revision": "1.0", "reason": "Pre-implementation directional envelope ownership Task/Spec", "date": "2026-08-18"},
    {"revision": "1.1", "reason": "Human-authorized implementation without scope or acceptance changes", "date": "2026-08-18"},
    {"revision": "1.2", "reason": "Implementation, verification and independent review recorded as ready for scoped commit", "date": "2026-08-18"},
    {"revision": "1.3", "reason": "Human-authorized scoped checkpoint commit without implementation or acceptance changes", "date": "2026-08-18"},
    {"revision": "1.4", "reason": "Human-authorized mission close after verified checkpoint commit and push synchronization", "date": "2026-08-18"}
  ]
}
```
<!-- CHANGE_REQUEST_METADATA_END -->

## Recovery summary

Scoped reconnaissance confirmed that Geometry ranking is correctly direction-neutral, while
`geometry/evaluation.py` applies a premature opposite-side directional downgrade before the
operational Wedge pattern is known. Existing strict-side candle containment in `wedge/detector.py`
already follows the approved Falling/Rising/Triangle mapping.

Implementation, focused verification, independent review and checkpoint commit are complete.
Revision 1.4 closes the mission after commit `405aaf1bf6889fd51d07c478cf064c29c5620d41`
was pushed and local `main` synchronized with `origin/main`. Criterion 13 remains
`NO_DEGRADATION_EVIDENCE_FOUND / MANUAL_REFERENCE_VALIDATION_DEFERRED`; residual risks and
non-blocking review findings remain recorded. No later phase exists.
