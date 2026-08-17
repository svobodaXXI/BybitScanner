# CR-DOC-AI-CONTEXT-001 — Documentation and AI Context Workflow Modernization

<!-- CHANGE_REQUEST_METADATA_BEGIN -->
```json
{
  "schema_version": "1.0",
  "id": "CR-DOC-AI-CONTEXT-001",
  "title": "Documentation and AI Context Workflow Modernization",
  "status": "IN_PROGRESS",
  "revision": "1.0",
  "lifecycle_stage": "IMPLEMENT",
  "objective": "Implement a compact TASK -> SPEC -> CONTEXT -> IMPLEMENT -> VERIFY -> RECORD workflow with durable task recovery and explicit legacy-risk handling.",
  "non_goals": [
    "Change production scanner or analytical behavior",
    "Run or redesign the complete Project Sync migration pipeline",
    "Implement ContextDump generation before Phase 3",
    "Delete, move, or rename legacy artifacts",
    "Add GitHub workflow templates"
  ],
  "approved_scope": [
    "Canonical agent and authority routing",
    "Durable ChangeRequest storage and focused validation",
    "LegacyWarning registry, validation, and read-only query",
    "Future ContextDump and Codex workflow integration in separately authorized phases"
  ],
  "prohibited_scope": [
    "Production scanner, Geometry, Wedge, Signal, confirmation, market-data, Telegram, charting, or trading logic",
    "ContextDump generator and runtime/context output",
    "Broad Project Sync pipeline behavior",
    "Automatic legacy-artifact deletion"
  ],
  "authoritative_references": [
    "DOCUMENTS/PROJECT_CONTRACTS.md#CONTRACT-DEVELOPMENT-LIFECYCLE-001",
    "DOCUMENTS/PROJECT_CONTRACTS.md#CONTRACT-CHANGE-REQUEST-001",
    "DOCUMENTS/PROJECT_CONTRACTS.md#CONTRACT-CONTEXT-DUMP-001",
    "DOCUMENTS/PROJECT_CONTRACTS.md#CONTRACT-LEGACY-WARNING-001",
    "DOCUMENTS/DECISION_LOG.md#DECISION-007",
    "DOCUMENTS/ROADMAP.md#CR-DOC-AI-CONTEXT-001",
    "DOCUMENTS/PROJECT_STATE.md#AI_CONTEXT_WORKFLOW_STATE"
  ],
  "approved_decisions": [
    "Current local checkout represents current working reality",
    "Git owns detailed implementation history",
    "Substantial work uses durable tracked Markdown ChangeRequests",
    "ContextDump remains disposable and non-authoritative",
    "Blocking LegacyWarnings require machine and agent enforcement"
  ],
  "unresolved_decisions": [],
  "acceptance_criteria": [
    "Routine recovery begins from tracked compact AGENTS.md",
    "Durable ChangeRequest validates independently of the full Project Sync pipeline",
    "LegacyWarning records are machine-readable and queryable by path or symbol",
    "Blocking warnings are machine-visible and cannot be silently treated as advisory",
    "ContextDump is not implemented before Phase 3",
    "Production behavior and unrelated dirty work remain unchanged"
  ],
  "verification_requirements": [
    "Focused ChangeRequest and LegacyWarning unit tests pass",
    "Current ChangeRequest validates",
    "Malformed and duplicate records fail deterministically",
    "Path and symbol warning queries return applicable records",
    "git diff --check and scoped allowlist review pass",
    "Fresh-agent recovery resolves this file without deep recovery"
  ],
  "risks": [
    "Schema growth could create documentation bureaucracy",
    "Generated or historical artifacts could be mistaken for authority",
    "Blocking warnings could overreach without explicit scope"
  ],
  "rollback_boundaries": [
    "Each implementation phase uses a separately revertible scoped commit",
    "Phase 2 infrastructure can be reverted without production-code rollback"
  ],
  "implementation_phases": [
    {"id": "PHASE_0", "status": "COMPLETED"},
    {"id": "PHASE_1", "status": "IMPLEMENTED_VERIFIED"},
    {"id": "PHASE_2", "status": "IMPLEMENTED_VERIFIED"},
    {"id": "PHASE_3", "status": "AWAITING_SEPARATE_AUTHORIZATION"},
    {"id": "PHASE_4", "status": "NOT_STARTED"},
    {"id": "PHASE_5", "status": "NOT_STARTED"},
    {"id": "PHASE_6", "status": "NOT_STARTED"}
  ],
  "current_phase": "PHASE_2",
  "current_checkpoint": "PHASE_2_COMPLETED",
  "implementation_status": "PHASE_2_IMPLEMENTED_VERIFIED",
  "next_phase": "PHASE_3",
  "next_phase_authorization": "AWAITING_SEPARATE_AUTHORIZATION",
  "related_commits": [
    {"phase": "PHASE_0", "commit": "24005986bc127f3d7da2bad19f528063280a0b6a"},
    {"phase": "PHASE_1", "commit": "2f503db280572cf5733ab130017ff0b6bba97644"}
  ],
  "amendment_history": []
}
```
<!-- CHANGE_REQUEST_METADATA_END -->

## Recovery summary

The approved architecture and rationale remain owned by the referenced contracts and `DECISION-007`.
This file is the durable task-specific authorization and recovery record, not a replacement for project authority.

Phase 0, Phase 1, and Phase 2 are complete and verified. Phase 3 awaits separate authorization.

## Amendment rule

Material changes to scope, behavior, risk, or acceptance require a new revision and renewed human approval before implementation continues.
