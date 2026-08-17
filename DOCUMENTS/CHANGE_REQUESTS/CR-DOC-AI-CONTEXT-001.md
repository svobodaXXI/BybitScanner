# CR-DOC-AI-CONTEXT-001 — Documentation and AI Context Workflow Modernization

<!-- CHANGE_REQUEST_METADATA_BEGIN -->
```json
{
  "schema_version": "1.0",
  "id": "CR-DOC-AI-CONTEXT-001",
  "title": "Documentation and AI Context Workflow Modernization",
  "status": "IN_PROGRESS",
  "revision": "1.8",
  "lifecycle_stage": "RECORD",
  "objective": "Implement a compact TASK -> SPEC -> CONTEXT -> IMPLEMENT -> VERIFY -> RECORD workflow with durable task recovery and explicit legacy-risk handling.",
  "non_goals": [
    "Change production scanner or analytical behavior",
    "Run or redesign the complete Project Sync migration pipeline",
    "Delete, move or rename legacy artifacts",
    "Add GitHub workflow templates"
  ],
  "approved_scope": [
    "Canonical staged agent recovery and authority routing",
    "Durable ChangeRequest storage and standalone validation",
    "Machine-readable LegacyWarning validation and scoped enforcement",
    "Disposable task-scoped ContextDump generation and freshness validation",
    "Codex workflow orchestration using the existing governance components",
    "Measured context-budget reduction and safe documentation deduplication"
  ],
  "prohibited_scope": [
    "Production scanner, Geometry, Wedge, Signal, confirmation, market-data, Telegram, charting, training/reference or trading logic",
    "ContextDump authority or a parallel workflow, registry or history store",
    "Normative contract weakening based only on textual similarity",
    "Full Project Sync execution/redesign, automatic legacy cleanup or unrelated dirty-work mutation"
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
  "context_scope_paths": [
    "AGENTS.md",
    "tools/project_sync/governance/codex_workflow.py",
    "tools/project_sync/governance/context_dump.py",
    "tools/project_sync/governance/legacy_warning.py",
    "tools/project_sync/governance/context_budget.py",
    "DOCUMENTS/CHANGE_REQUESTS/CR-DOC-AI-CONTEXT-001.md",
    "DOCUMENTS/LEGACY_WARNINGS.json",
    "DOCUMENTS/PROJECT_STATE.md",
    "DOCUMENTS/ROADMAP.md"
  ],
  "context_test_paths": [
    "tests/test_change_request_governance.py",
    "tests/test_context_dump_governance.py",
    "tests/test_legacy_warning_governance.py",
    "tests/test_codex_workflow_governance.py",
    "tests/test_context_budget_governance.py"
  ],
  "context_excerpt_references": [
    "DOCUMENTS/PROJECT_CONTRACTS.md#CONTRACT-CONTEXT-DUMP-001",
    "DOCUMENTS/PROJECT_CONTRACTS.md#CONTRACT-LEGACY-WARNING-001",
    "DOCUMENTS/PROJECT_STATE.md#AI_CONTEXT_WORKFLOW_STATE"
  ],
  "phase_6_authorization": "HUMAN_APPROVED_2026-08-18",
  "phase_6_objective": "Measure actual recovery context cost and remove only classified, owner-safe duplication while preserving all Phase 1-5 behavior.",
  "phase_6_baseline": {
    "agents_bytes": 4425,
    "agents_lines": 48,
    "durable_change_request_bytes": 15876,
    "agents_plus_change_request_bytes": 20301,
    "context_dump_bytes": 11880,
    "canonical_document_aggregate_bytes_not_routine_load": 273310
  },
  "phase_6_final_measurements": {
    "measurement_status": "PASS",
    "agents_bytes": 4425,
    "lightweight_direct_recovery_bytes": 4425,
    "change_request_bytes": 8608,
    "agents_plus_change_request_bytes": 13033,
    "agents_plus_change_request_reduction_percent": 35.80,
    "context_dump_bytes": 11700,
    "agents_target_bytes_max": 10240,
    "context_dump_target_bytes_max": 30720,
    "agents_plus_change_request_reduction_target_percent": 15
  },
  "phase_6_duplication_classification": [
    "PROJECT_CONTRACTS and DECISION_LOG retain normative owner and rationale text",
    "AGENTS retains necessary routing and safety text",
    "PROJECT_RULES retains policy while routing repeated recovery mechanics to AGENTS and workflow contracts",
    "ASSISTANT_PROTOCOL retains an assistant-specific owner pointer instead of repeated recovery steps",
    "Completed phase details and superseded version narratives are Git-owned history",
    "PROJECT_STATE and ROADMAP retain only current operational/planning summaries"
  ],
  "approved_decisions": [
    "Current local checkout represents current working reality",
    "Git owns detailed implementation history",
    "Substantial work uses durable tracked Markdown ChangeRequests",
    "ContextDump remains disposable and non-authoritative",
    "Blocking LegacyWarnings require machine and agent enforcement",
    "Every removed semantic rule retains an explicit authoritative owner"
  ],
  "unresolved_decisions": [],
  "acceptance_criteria": [
    "Read-only measurement reports AGENTS, lightweight direct, durable and ContextDump footprints without full Project Sync",
    "AGENTS remains below 10 KB and ContextDump below 30 KB",
    "AGENTS plus this ChangeRequest is at least 15 percent smaller than the 20301-byte baseline",
    "Fresh-agent and interruption recovery remain deterministic",
    "LegacyWarning ADVISORY/BLOCKING and ContextDump freshness behavior remain unchanged",
    "Every removed passage has a surviving owner or is detailed history retained by Git",
    "Production behavior and unrelated dirty work remain unchanged"
  ],
  "verification_requirements": [
    "Focused context-budget and existing ChangeRequest, ContextDump, LegacyWarning and Codex workflow tests pass",
    "Standalone ChangeRequest and ContextDump validation pass",
    "Fresh-agent and interruption recovery simulations pass without deep recovery",
    "Artifact-free compile, git diff --check, PROJECT_TREE encoding check and scoped allowlist review pass",
    "Before/after sizes are recorded for every changed canonical document"
  ],
  "risks": [
    "Over-reduction could hide an authority or recovery boundary",
    "Generated context could be mistaken for authority",
    "Measurement output could become a parallel report authority"
  ],
  "rollback_boundaries": [
    "Phase 6 is one separately revertible implementation commit",
    "Rollback removes the measurement utility and restores documentation text without affecting Phase 1-5 governance or production behavior"
  ],
  "implementation_phases": [
    {"id": "PHASE_0", "status": "COMPLETED"},
    {"id": "PHASE_1", "status": "IMPLEMENTED_VERIFIED"},
    {"id": "PHASE_2", "status": "IMPLEMENTED_VERIFIED"},
    {"id": "PHASE_3", "status": "IMPLEMENTED_VERIFIED"},
    {"id": "PHASE_4", "status": "IMPLEMENTED_VERIFIED"},
    {"id": "PHASE_5", "status": "IMPLEMENTED_VERIFIED"},
    {"id": "PHASE_6", "status": "IMPLEMENTED_VERIFIED"},
    {"id": "MISSION_CLOSE", "status": "NOT_STARTED"}
  ],
  "current_phase": "PHASE_6",
  "current_checkpoint": "PHASE_6_COMPLETED",
  "implementation_status": "PHASE_6_IMPLEMENTED_VERIFIED",
  "next_phase": "MISSION_CLOSE",
  "next_phase_authorization": "NOT_AUTHORIZED",
  "related_commits": [
    {"phase": "PHASE_0", "commit": "24005986bc127f3d7da2bad19f528063280a0b6a"},
    {"phase": "PHASE_1", "commit": "2f503db280572cf5733ab130017ff0b6bba97644"},
    {"phase": "PHASE_2", "commit": "5bb91e0a946101db26ddeb8002d179bfd2b70c78"},
    {"phase": "PHASE_3", "commit": "476cdd5ccaea927dc2b29c1f01ff6022cbf9bc97"},
    {"phase": "PHASE_4_CHECKPOINT", "commit": "a51a25e"},
    {"phase": "PHASE_5", "commit": "2283b97"},
    {"phase": "PHASE_6_CHECKPOINT", "commit": "dd3bcf7d23a0ba49c5cb0c64170927404b734122"}
  ],
  "amendment_history": [
    {"revision": "1.6", "reason": "Phase 5 implemented and verified", "date": "2026-08-18"},
    {"revision": "1.7", "reason": "Phase 6 human-authorized bounded specification", "date": "2026-08-18"},
    {"revision": "1.8", "reason": "Phase 6 measured context reduction implemented and verified", "date": "2026-08-18"}
  ]
}
```
<!-- CHANGE_REQUEST_METADATA_END -->

## Recovery summary

Phase 0 through Phase 6 are implemented and verified. Detailed implementation deltas remain in Git.
The referenced contracts and `DECISION-007` own general semantics and rationale; this file owns task-specific authorization and recovery state.

Next action: review and separately authorize `MISSION_CLOSE`. No later phase is authorized.

## Amendment rule

Material scope, behavior, risk or acceptance changes require a new revision and renewed human approval.
