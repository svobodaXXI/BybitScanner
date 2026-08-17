# CR-DOC-AI-CONTEXT-001 — Documentation and AI Context Workflow Modernization

<!-- CHANGE_REQUEST_METADATA_BEGIN -->
```json
{
  "schema_version": "1.0",
  "id": "CR-DOC-AI-CONTEXT-001",
  "title": "Documentation and AI Context Workflow Modernization",
  "status": "IN_PROGRESS",
  "revision": "1.3",
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
    "Minimal Phase 3 task-scoped ContextDump generator targeting runtime/context/",
    "Phase 4 standalone ContextDump staleness validation and scoped LegacyWarning enforcement"
  ],
  "prohibited_scope": [
    "Production scanner, Geometry, Wedge, Signal, confirmation, market-data, Telegram, charting, or trading logic",
    "Phase 5 Codex workflow integration or automatic ContextDump consumption",
    "Full-repository dependency graph or broad static-analysis framework",
    "Broad Project Sync pipeline behavior",
    "Automatic legacy-artifact deletion, migration, rename, or rewrite"
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
    "tools/project_sync/governance/context_dump.py",
    "tools/project_sync/governance/legacy_warning.py",
    "DOCUMENTS/CHANGE_REQUESTS/CR-DOC-AI-CONTEXT-001.md",
    "DOCUMENTS/LEGACY_WARNINGS.json",
    "DOCUMENTS/PROJECT_STATE.md",
    "DOCUMENTS/ROADMAP.md"
  ],
  "context_test_paths": [
    "tests/test_context_dump_governance.py",
    "tests/test_legacy_warning_governance.py"
  ],
  "context_excerpt_references": [
    "DOCUMENTS/PROJECT_CONTRACTS.md#CONTRACT-CONTEXT-DUMP-001",
    "DOCUMENTS/PROJECT_CONTRACTS.md#CONTRACT-LEGACY-WARNING-001",
    "DOCUMENTS/PROJECT_STATE.md#AI_CONTEXT_WORKFLOW_STATE"
  ],
  "phase_4_implementation_scope": [
    "Extend tools/project_sync/governance/context_dump.py with read-only provenance/staleness validation",
    "Extend tools/project_sync/governance/legacy_warning.py only where needed for deterministic scoped enforcement",
    "Extend the two existing focused governance test modules",
    "Record verified Phase 4 state in the owning ChangeRequest, PROJECT_STATE and ROADMAP"
  ],
  "phase_4_enforcement_boundary": [
    "Validate task identity/revision, branch, HEAD, ChangeRequest hash, authority hashes, scoped-file hashes and relevant LegacyWarning state against the current local checkout",
    "Ignore unrelated dirty paths when evaluating scoped ContextDump freshness",
    "Surface ADVISORY warnings without a blocking exit",
    "Return a machine-visible non-zero result for applicable BLOCKING warnings or stale/invalid context",
    "Apply warnings only through declared task path/symbol scope; do not build a full-repository dependency graph"
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
    "ContextDump is generated only for declared task scope at ignored runtime/context/",
    "ContextDump records task revision, local branch and HEAD, dirty-state digest, authority hashes and relevant LegacyWarnings",
    "ContextDump excludes unrelated dirty paths and complete unrelated authority documents",
    "Fresh ContextDump validates against the unchanged scoped local checkout",
    "Task revision, branch, HEAD, task record, authority, scoped-file or relevant LegacyWarning changes are detected as stale",
    "Unrelated dirty-work changes do not make scoped context stale",
    "Applicable ADVISORY warnings remain visible and non-blocking while applicable BLOCKING warnings produce machine-visible failure",
    "Staleness and warning validation are read-only and independent of the full Project Sync pipeline",
    "Production behavior and unrelated dirty work remain unchanged"
  ],
  "verification_requirements": [
    "Focused ContextDump, ChangeRequest and LegacyWarning unit tests pass",
    "Current ChangeRequest validates and generates a ContextDump below the initial 30 KB target",
    "Missing task scope or unresolved authority fails clearly",
    "Authoritative source files remain unchanged during generation",
    "Focused tests cover fresh, stale, advisory, blocking, malformed and unrelated-dirty-state boundaries",
    "Standalone CLI/function exit status distinguishes successful, stale/invalid and blocking outcomes deterministically",
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
    "Phase 2 infrastructure can be reverted without production-code rollback",
    "Phase 4 enforcement can be reverted independently of Phase 3 generation and production code"
  ],
  "implementation_phases": [
    {"id": "PHASE_0", "status": "COMPLETED"},
    {"id": "PHASE_1", "status": "IMPLEMENTED_VERIFIED"},
    {"id": "PHASE_2", "status": "IMPLEMENTED_VERIFIED"},
    {"id": "PHASE_3", "status": "IMPLEMENTED_VERIFIED"},
    {"id": "PHASE_4", "status": "APPROVED_NOT_IMPLEMENTED"},
    {"id": "PHASE_5", "status": "NOT_STARTED"},
    {"id": "PHASE_6", "status": "NOT_STARTED"}
  ],
  "current_phase": "PHASE_4",
  "current_checkpoint": "PHASE_4_PRE_IMPLEMENTATION_CHECKPOINT",
  "implementation_status": "PHASE_4_IMPLEMENTATION_NOT_STARTED",
  "next_phase": "PHASE_5",
  "next_phase_authorization": "NOT_AUTHORIZED",
  "related_commits": [
    {"phase": "PHASE_0", "commit": "24005986bc127f3d7da2bad19f528063280a0b6a"},
    {"phase": "PHASE_1", "commit": "2f503db280572cf5733ab130017ff0b6bba97644"},
    {"phase": "PHASE_2", "commit": "5bb91e0a946101db26ddeb8002d179bfd2b70c78"},
    {"phase": "PHASE_3", "commit": "476cdd5ccaea927dc2b29c1f01ff6022cbf9bc97"}
  ],
  "amendment_history": [
    {
      "revision": "1.1",
      "reason": "Human authorization for bounded Phase 3 Minimal ContextDump generator implementation",
      "date": "2026-08-17"
    },
    {
      "revision": "1.2",
      "reason": "Phase 3 Minimal ContextDump generator implemented and verified; Phase 4 remains separately unauthorized",
      "date": "2026-08-17"
    },
    {
      "revision": "1.3",
      "reason": "Human authorization and bounded pre-implementation specification for Phase 4 staleness and LegacyWarning enforcement",
      "date": "2026-08-17"
    }
  ]
}
```
<!-- CHANGE_REQUEST_METADATA_END -->

## Recovery summary

The approved architecture and rationale remain owned by the referenced contracts and `DECISION-007`.
This file is the durable task-specific authorization and recovery record, not a replacement for project authority.

Phase 0 through Phase 3 are complete and verified. Phase 4 is authorized by revision 1.3 but implementation has not started. Phase 5 is not authorized.

## Amendment rule

Material changes to scope, behavior, risk, or acceptance require a new revision and renewed human approval before implementation continues.
