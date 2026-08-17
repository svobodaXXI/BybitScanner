# CR-DOC-AI-CONTEXT-001 — Documentation and AI Context Workflow Modernization

<!-- CHANGE_REQUEST_METADATA_BEGIN -->
```json
{
  "schema_version": "1.0",
  "id": "CR-DOC-AI-CONTEXT-001",
  "title": "Documentation and AI Context Workflow Modernization",
  "status": "IN_PROGRESS",
  "revision": "1.7",
  "lifecycle_stage": "SPEC",
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
    "Phase 4 standalone ContextDump staleness validation and scoped LegacyWarning enforcement",
    "Phase 5 Codex workflow integration through the existing governance components",
    "Phase 6 measured context-budget reduction and safe documentation deduplication"
  ],
  "prohibited_scope": [
    "Production scanner, Geometry, Wedge, Signal, confirmation, market-data, Telegram, charting, or trading logic",
    "Unmeasured broad documentation rewrite or deletion of intentional authority overlap",
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
    "AGENTS.md",
    "tools/project_sync/governance/codex_workflow.py",
    "tools/project_sync/governance/context_dump.py",
    "tools/project_sync/governance/legacy_warning.py",
    "DOCUMENTS/CHANGE_REQUESTS/CR-DOC-AI-CONTEXT-001.md",
    "DOCUMENTS/LEGACY_WARNINGS.json",
    "DOCUMENTS/PROJECT_STATE.md",
    "DOCUMENTS/ROADMAP.md"
  ],
  "context_test_paths": [
    "tests/test_codex_workflow_governance.py",
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
  "phase_4_verification_evidence": [
    "32 focused ChangeRequest, ContextDump and LegacyWarning governance tests passed",
    "Artifact-free compile passed for the four affected Python files",
    "Real CR-DOC-AI-CONTEXT-001 ContextDump generated and standalone validation returned PASS with exit code 0",
    "git diff --check and scoped allowlist review passed"
  ],
  "phase_5_authorization": "HUMAN_APPROVED_2026-08-18",
  "phase_5_objective": "Integrate staged recovery, durable ChangeRequests, optional task-scoped ContextDump preparation/validation and scoped LegacyWarning enforcement into one practical Codex workflow without making generated context authoritative.",
  "phase_5_implementation_scope": [
    "Add one narrow governance orchestration entry that reuses change_request.py, context_dump.py and legacy_warning.py rather than duplicating their schemas or validation",
    "Update compact AGENTS.md routing so agents can deterministically select lightweight direct recovery or durable ChangeRequest preparation",
    "Add focused isolated workflow tests for decision flow, validation results and interruption recovery",
    "Register only genuinely new canonical paths and record verified Phase 5 state in the owning ChangeRequest, PROJECT_STATE and ROADMAP"
  ],
  "phase_5_expected_files": [
    "AGENTS.md",
    "tools/project_sync/governance/codex_workflow.py",
    "tests/test_codex_workflow_governance.py",
    "DOCUMENTS/PROJECT_TREE.md",
    "DOCUMENTS/CHANGE_REQUESTS/CR-DOC-AI-CONTEXT-001.md",
    "DOCUMENTS/PROJECT_STATE.md",
    "DOCUMENTS/ROADMAP.md"
  ],
  "phase_5_prohibited_scope": [
    "Production scanner, Geometry, Wedge, Signal, confirmation, market-data, Telegram, charting or trading behavior",
    "Phase 6 context-budget or broad documentation deduplication work",
    "Full Project Sync migration execution or pipeline redesign",
    "New task, context, warning or history registry parallel to existing governance components",
    "Automatic ContextDump authority, automatic legacy deletion, GitHub templates or unrelated dirty-work mutation"
  ],
  "phase_5_workflow": [
    "Begin from AGENTS.md and current local branch, HEAD, index, working tree and task identity",
    "Classify the work as lightweight Task/Spec or substantial durable ChangeRequest work",
    "For lightweight work, use direct staged task-scoped recovery; do not generate ContextDump by default",
    "For durable implementation, validate the approved ChangeRequest and generate a ContextDump when the task is multi-session, context-heavy, interruption recovery needs a package, or the user explicitly requests it",
    "Do not generate ContextDump for trivial actions, read-only status checks, or when direct scoped authority is smaller and sufficient",
    "Validate any ContextDump immediately before implementation; PASS and ADVISORY permit continuation, while STALE, FAIL and BLOCKING return non-zero and prohibit implementation",
    "Surface ADVISORY warnings without blocking; applicable BLOCKING warnings require an approved scope/contract amendment and must not be bypassed",
    "When ContextDump is absent, recover directly from current local state and owning task-scoped authority, and still enforce applicable LegacyWarnings against declared scope",
    "On interruption, resume from the durable ChangeRequest checkpoint, re-read local Git state, and regenerate or revalidate derived context before implementation",
    "After verification, record only current owned state and scoped Git history; never promote ContextDump to authority"
  ],
  "phase_5_authority_precedence": [
    "Current local filesystem and Git state establish working reality",
    "Owning authoritative documents and approved Task/Spec or ChangeRequest establish normative meaning and authorization",
    "AGENTS.md routes recovery but does not override owning authority",
    "ContextDump is derived and non-authoritative; stale or conflicting context is discarded and regenerated",
    "Git history and GitHub support history/collaboration but do not override newer local authority"
  ],
  "phase_5_acceptance_criteria": [
    "One bounded entry flow reuses existing standalone governance components without invoking the full Project Sync pipeline",
    "Lightweight tasks can proceed through direct scoped recovery without mandatory ContextDump generation",
    "Durable tasks can generate and validate task-scoped context with explicit machine-visible outcomes",
    "PASS and ADVISORY are non-blocking; STALE, FAIL and BLOCKING prevent implementation with non-zero status",
    "Absent ContextDump falls back to direct staged recovery without weakening scoped LegacyWarning enforcement",
    "Fresh-agent and interruption recovery resolve current phase, authority and next action from repository state",
    "Generated context remains ignored, disposable and non-authoritative",
    "No production behavior, unrelated dirty work, Project Sync pipeline architecture or Phase 6 scope changes"
  ],
  "phase_5_verification_requirements": [
    "Focused tests cover lightweight direct recovery, durable preparation, optional generation, absent context, fresh/advisory continuation and stale/fail/blocking rejection",
    "Focused tests prove existing ChangeRequest, ContextDump and LegacyWarning implementations are called rather than reimplemented",
    "CLI/function exit results are deterministic and machine-visible",
    "Artifact-free compile, existing focused governance regressions, git diff --check and scoped allowlist review pass",
    "Fresh-agent interruption simulation succeeds without full five-document recovery or full Project Sync execution"
  ],
  "phase_5_verification_evidence": [
    "16 focused Codex workflow orchestration tests passed",
    "48 combined ChangeRequest, ContextDump, LegacyWarning and Codex workflow governance tests passed",
    "Artifact-free compile passed for the Phase 5 module and focused test",
    "Representative CLI PASS returned 0, BLOCKING returned 2 and durable direct recovery returned 0",
    "Standalone ChangeRequest and generated ContextDump validation passed",
    "git diff --check and scoped implementation allowlist review passed"
  ],
  "phase_6_authorization": "HUMAN_APPROVED_2026-08-18",
  "phase_6_objective": "Measure actual staged-recovery context cost, identify material canonical documentation duplication by ownership, and make only evidence-backed reductions that preserve workflow safety and fresh-agent recovery.",
  "phase_6_initial_baseline": {
    "agents_bytes": 4425,
    "agents_lines": 48,
    "durable_change_request_bytes": 15876,
    "agents_plus_change_request_bytes": 20301,
    "existing_context_dump_bytes": 11880,
    "canonical_document_aggregate_bytes_not_routine_load": 273310
  },
  "phase_6_measured_baseline_plan": [
    "Measure bytes, characters and lines for AGENTS.md, the active State pointer, durable ChangeRequest, selected owning sections and generated ContextDump",
    "Measure lightweight direct recovery as AGENTS.md plus only the task-specific authority actually required, not the complete documentation set",
    "Measure durable recovery as AGENTS.md plus the durable ChangeRequest and only referenced owning sections actually loaded",
    "Classify repeated normalized paragraphs as normative owner text, intentional safety pointer, task-specific recovery state, historical record or removable duplication",
    "Record before/after measurements for every modified document and rerun fresh-agent lightweight, durable and interrupted recovery simulations"
  ],
  "phase_6_implementation_scope": [
    "Add one small read-only context-budget measurement utility and focused tests without creating a new registry or report authority",
    "Measure current lightweight, durable and ContextDump paths before editing canonical prose",
    "Reduce only confirmed duplication in AGENTS, active AI workflow State/Roadmap/ChangeRequest content, PROJECT_RULES and ASSISTANT_PROTOCOL while preserving each document owner",
    "Keep PROJECT_CONTRACTS and DECISION_LOG normative/rationale content unchanged unless a separately approved owner conflict is proven",
    "Register only a genuinely new measurement utility/test path and record verified Phase 6 state in existing owners"
  ],
  "phase_6_expected_files": [
    "AGENTS.md",
    "DOCUMENTS/CHANGE_REQUESTS/CR-DOC-AI-CONTEXT-001.md",
    "DOCUMENTS/PROJECT_STATE.md",
    "DOCUMENTS/ROADMAP.md",
    "DOCUMENTS/PROJECT_RULES.md",
    "DOCUMENTS/ASSISTANT_PROTOCOL.md",
    "DOCUMENTS/PROJECT_TREE.md",
    "tools/project_sync/governance/context_budget.py",
    "tests/test_context_budget_governance.py"
  ],
  "phase_6_prohibited_scope": [
    "Production scanner, Geometry, Wedge, Signal, confirmation, market-data, Telegram, charting, training/reference or trading behavior",
    "ContextDump authority, new parallel workflow/registry/history store, or automatic legacy-artifact deletion",
    "Normative contract weakening or removal based only on textual similarity",
    "Full Project Sync execution/redesign, GitHub templates, PROJECT_TREE redesign or unrelated documentation cleanup",
    "Modification of unrelated dirty work, backups, generated runtime context or historical artifacts"
  ],
  "phase_6_deduplication_safety_rules": [
    "Assign each normative fact to one owning authority and retain short routing or safety pointers where independent usability requires them",
    "Do not remove text until its owner, consumers and recovery consequence are identified",
    "Do not count intentional owner-to-router references as duplication merely because wording overlaps",
    "Do not move normative or durable state into ContextDump, generated reports, Git history alone or other non-authoritative artifacts",
    "Preserve ChangeRequest authorization, acceptance, unresolved decisions, current phase, rollback and interruption-recovery sufficiency",
    "Preserve staged recovery, direct lightweight fallback, LegacyWarning enforcement, stale-context blocking and deep recovery availability",
    "Use scoped before/after measurements and regression tests for every accepted reduction"
  ],
  "phase_6_acceptance_criteria": [
    "A reproducible read-only measurement reports routine AGENTS, lightweight direct, durable recovery and ContextDump footprints without running full Project Sync",
    "AGENTS.md remains below 10 KB and retains deterministic routing and safety boundaries",
    "Generated ContextDump remains below 30 KB, non-authoritative, scoped and stale-detectable",
    "AGENTS.md plus the durable ChangeRequest is reduced from the 20301-byte baseline by at least 15 percent without losing task recovery semantics",
    "Every removed passage has a documented surviving owner or is verified historical duplication owned by Git",
    "Fresh-agent lightweight, durable and interruption recovery remain deterministic with applicable ADVISORY/BLOCKING behavior unchanged",
    "No production behavior, governance schema semantics, unrelated dirty work or full Project Sync pipeline changes"
  ],
  "phase_6_verification_requirements": [
    "Focused measurement tests validate deterministic counts, scoped section selection, duplicate classification inputs and missing-source failure",
    "Existing ChangeRequest, ContextDump, LegacyWarning and Codex workflow governance tests pass",
    "Before/after byte, character and line counts are reported for every reduced document and recovery path",
    "Standalone ChangeRequest, ContextDump freshness and Codex workflow PASS/ADVISORY/BLOCKING gates remain valid",
    "Artifact-free compile, git diff --check, encoding checks for PROJECT_TREE and scoped allowlist review pass",
    "Fresh-agent recovery simulation succeeds without full five-document recovery"
  ],
  "phase_6_rollback_boundary": "One separately revertible Phase 6 implementation commit; rollback restores documentation text and measurement tooling without affecting Phase 1-5 governance or production behavior.",
  "phase_5_rollback_boundary": "One separately revertible scoped Phase 5 implementation commit; reverting it leaves Phase 1-4 governance and all production scanner behavior intact.",
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
    "Phase 4 enforcement can be reverted independently of Phase 3 generation and production code",
    "Phase 5 orchestration can be reverted independently without reverting Phase 1-4 governance"
  ],
  "implementation_phases": [
    {"id": "PHASE_0", "status": "COMPLETED"},
    {"id": "PHASE_1", "status": "IMPLEMENTED_VERIFIED"},
    {"id": "PHASE_2", "status": "IMPLEMENTED_VERIFIED"},
    {"id": "PHASE_3", "status": "IMPLEMENTED_VERIFIED"},
    {"id": "PHASE_4", "status": "IMPLEMENTED_VERIFIED"},
    {"id": "PHASE_5", "status": "IMPLEMENTED_VERIFIED"},
    {"id": "PHASE_6", "status": "AUTHORIZED_NOT_STARTED"},
    {"id": "MISSION_CLOSE", "status": "NOT_STARTED"}
  ],
  "current_phase": "PHASE_6",
  "current_checkpoint": "PHASE_6_PRE_IMPLEMENTATION_CHECKPOINT",
  "implementation_status": "PHASE_6_NOT_STARTED",
  "next_phase": "MISSION_CLOSE",
  "next_phase_authorization": "NOT_AUTHORIZED",
  "related_commits": [
    {"phase": "PHASE_0", "commit": "24005986bc127f3d7da2bad19f528063280a0b6a"},
    {"phase": "PHASE_1", "commit": "2f503db280572cf5733ab130017ff0b6bba97644"},
    {"phase": "PHASE_2", "commit": "5bb91e0a946101db26ddeb8002d179bfd2b70c78"},
    {"phase": "PHASE_3", "commit": "476cdd5ccaea927dc2b29c1f01ff6022cbf9bc97"},
    {"phase": "PHASE_4_CHECKPOINT", "commit": "a51a25e"}
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
    },
    {
      "revision": "1.4",
      "reason": "Phase 4 standalone staleness validation and scoped LegacyWarning enforcement implemented and verified",
      "date": "2026-08-17"
    },
    {
      "revision": "1.5",
      "reason": "Human authorization and bounded pre-implementation specification for Phase 5 Codex workflow integration",
      "date": "2026-08-18"
    },
    {
      "revision": "1.6",
      "reason": "Phase 5 Codex workflow orchestration implemented and verified; Phase 6 remains separately unauthorized",
      "date": "2026-08-18"
    },
    {
      "revision": "1.7",
      "reason": "Human authorization and bounded pre-implementation specification for Phase 6 measured context reduction and safe deduplication",
      "date": "2026-08-18"
    }
  ]
}
```
<!-- CHANGE_REQUEST_METADATA_END -->

## Recovery summary

The approved architecture and rationale remain owned by the referenced contracts and `DECISION-007`.
This file is the durable task-specific authorization and recovery record, not a replacement for project authority.

Phase 0 through Phase 5 are complete and verified. Phase 6 is human-authorized at its
pre-implementation checkpoint; Phase 6 implementation has not started.

## Amendment rule

Material changes to scope, behavior, risk, or acceptance require a new revision and renewed human approval before implementation continues.
