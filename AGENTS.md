# BybitScanner Agent Guide

Canonical compact entry point for coding agents. It routes to project authority; it does not replace that authority.

## Staged recovery

0. **Local reality:** read this file; inspect branch, HEAD, index/working-tree status, the user task, and relevant dirty scope.
1. **Task authority:** read the active mission pointer in `DOCUMENTS/PROJECT_STATE.md` or the applicable Task/Spec or durable ChangeRequest. Follow only its owning references.
2. **Scoped authority:** load only relevant sections of contracts, rules, architecture, tree, roadmap, and assistant protocol required by the affected scope.
3. **Deep recovery:** broaden review to `PROJECT_STATE.md`, `PROJECT_TREE.md`, `PROJECT_RULES.md`, `ARCHITECTURE.md`, and `ASSISTANT_PROTOCOL.md` only when scope is unknown, authorities conflict, severe interruption requires reconstruction, or work is architecture-wide.

Routine scoped work must not require the complete deep-recovery set. Do not run Project Sync merely to restore context.

## Authority routing

- Current local filesystem: what actually exists now.
- Local Git state: branch/HEAD/index/working-tree relationship and detailed change history.
- `DOCUMENTS/PROJECT_STATE.md`: current mission, phase, priority, and next action.
- `DOCUMENTS/PROJECT_CONTRACTS.md`: normative subsystem and workflow contracts.
- `DOCUMENTS/PROJECT_RULES.md`: mandatory project and engineering rules.
- `DOCUMENTS/ARCHITECTURE.md`: architecture and responsibility boundaries.
- `DOCUMENTS/PROJECT_TREE.md`: important canonical path roles during staged modernization.
- `DOCUMENTS/ASSISTANT_PROTOCOL.md`: assistant-specific behavior and communication.

The current local checkout may be newer than GitHub. GitHub is for remote synchronization, collaboration, reviews, PRs, and remote history; remote changes become local working truth only after explicit synchronization. Dirty implementation does not silently override a normative contract: record the mismatch and resolve it through Task/Spec.

Generated ContextDumps, reports, snapshots, caches, backups, historical copies, chat, and memory are non-authoritative. Treat LEGACY/DEPRECATED artifacts according to applicable warnings; never revive or delete them without authority.

## Task and change routing

Use lightweight Task/Spec for small routine work. Substantial, risky, architectural, or multi-session work resolves its approved record under `DOCUMENTS/CHANGE_REQUESTS/` as defined by `CONTRACT-CHANGE-REQUEST-001`. Material scope or contract changes require an approved amendment before implementation continues. Applicable BLOCKING LegacyWarnings must not be bypassed.

Use `tools.project_sync.governance.codex_workflow` as the narrow pre-implementation gate. Lightweight work uses `lightweight --path PATH` (or `--symbol`) and direct scoped recovery. Durable work uses `durable CHANGE_REQUEST`; add `--context PATH` to validate an existing dump, or request generation only for multi-session, context-heavy, recovery-package, or explicitly requested context. `PASS` and `ADVISORY` may continue; `STALE`, `FAIL`, and `BLOCKING` must stop. Missing ContextDump permits direct recovery but never bypasses scoped LegacyWarnings. ContextDump remains derived and non-authoritative.

## Change safety

Before editing, inspect actual targets and `git status --short`. Treat unrelated pre-existing changes and untracked files as user-owned. Never overwrite, reformat, stage, clean, restore, reset, delete, move, discard, commit, or push user work unless explicitly authorized. Keep changes minimal, scoped, reversible, and contract-compatible.

Confirm existing components before adding modules, registries, paths, documents, or stores. Identify affected contracts, callers, tests, runtime behavior, and data compatibility.

## Verify and record

Validate in proportion to risk: compile affected Python, run focused tests, check relevant integration paths, review the scoped diff, and run broader authoritative validation only when required. Never hide or overstate results.

Git owns detailed implementation history. Update authoritative documentation only when its owned current state, contract, decision, or planned work changed. Stage and commit only authorized scope; report checks, failures, unresolved risks, and unrelated dirty work.

For role, communication style, and mission/checkpoint behavior, follow `DOCUMENTS/ASSISTANT_PROTOCOL.md`.
