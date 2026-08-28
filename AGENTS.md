# BybitScanner Agent Guide

Canonical compact entry point for coding agents. It routes to project authority; it does not replace that authority.

This root `AGENTS.md` applies to the entire repository tree rooted at `C:\BybitScanner` and is a mandatory project-level instruction file for Codex.

## Staged recovery

0. **Local reality:** read this file; inspect branch, HEAD, index/working-tree status, the user task, and relevant dirty scope.
1. **Task authority:** read the active mission pointer in `DOCUMENTS/PROJECT_STATE.md` or the applicable Task/Spec or durable ChangeRequest. Follow only its owning references.
2. **Scoped authority:** load only relevant sections of contracts, rules, architecture, tree, roadmap, and assistant protocol required by the affected scope.
3. **Deep recovery:** broaden review to `PROJECT_STATE.md`, `PROJECT_TREE.md`, `PROJECT_RULES.md`, `ARCHITECTURE.md`, and `ASSISTANT_PROTOCOL.md` only when scope is unknown, authorities conflict, severe interruption requires reconstruction, or work is architecture-wide.

Routine scoped work must not require the complete deep-recovery set. Do not run Project Sync merely to restore context.

Generate a compact disposable bootstrap when useful with `python -m tools.dev.task_context --path EXACT_PATH` (repeat `--path` as needed; optional `--hint`). Its JSON output is derived, non-authoritative context and never replaces repository authority or governance gates.

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

For any Trading Workspace, PAPER trading, or terminal implementation or diagnosis, read `DOCUMENTS/TRADING_WORKSPACE_MASTER_ROADMAP.md` together with the active ChangeRequest and `DOCUMENTS/ASSISTANT_PROTOCOL.md`. The roadmap canonically defines architectural sequencing and acceptance gates across Codex sessions and ChatGPT handoffs. Any Trading Workspace handoff or checkpoint must record the current roadmap stage, last completed and accepted roadmap stage, current blocker, exact next roadmap action, and any deliberate documented deviation from the master roadmap; do not duplicate the roadmap into handoff text.

Use `tools.project_sync.governance.codex_workflow` as the narrow pre-implementation gate. Lightweight work uses `lightweight --path PATH` (or `--symbol`) and direct scoped recovery. Durable work uses `durable CHANGE_REQUEST`; add `--context PATH` to validate an existing dump, or request generation only for multi-session, context-heavy, recovery-package, or explicitly requested context. `PASS` and `ADVISORY` may continue; `STALE`, `FAIL`, and `BLOCKING` must stop. Missing ContextDump permits direct recovery but never bypasses scoped LegacyWarnings. ContextDump remains derived and non-authoritative.

## Change safety

Before editing, inspect actual targets and `git status --short`. Treat unrelated pre-existing changes and untracked files as user-owned. Never overwrite, reformat, stage, clean, restore, reset, delete, move, discard, commit, or push user work unless explicitly authorized. Keep changes minimal, scoped, reversible, and contract-compatible.

Confirm existing components before adding modules, registries, paths, documents, or stores. Identify affected contracts, callers, tests, runtime behavior, and data compatibility.

## Verify and record

Codex must not create synthetic/fake UI tests for behavior the user can immediately verify in the real interface. Do not add or run tests without objective necessity; add an automated test only when it protects critical logic, a material regression, or behavior that cannot be verified reliably and quickly by hand.

After implementation, Codex must run `python -m tools.dev.verify` once with repeated `--path` arguments matching the exact task/changed paths. The verifier routes only the required scoped checks, avoids redundant broad/full tests, remains read-only with respect to Git/index, and writes its PASS receipt under `.git/bybitscanner/`.

`python -m tools.dev.checkpoint --message "..."` is a user-run Git-write command. Codex must never invoke it automatically. It consumes the latest current PASS receipt, stages only its exact paths, checks the cached diff, commits, pushes to `origin`, and verifies the remote SHA; any mismatch or failure stops the workflow without touching unrelated work.

Validate in proportion to risk through the verifier: compile affected Python, run focused tests, check relevant integration paths, review the scoped diff, and run broader authoritative validation only when required. Never hide or overstate results.

Git owns detailed implementation history. Update authoritative documentation only when its owned current state, contract, decision, or planned work changed. Stage and commit only authorized scope; report checks, failures, unresolved risks, and unrelated dirty work.

For role, communication style, and mission/checkpoint behavior, follow `DOCUMENTS/ASSISTANT_PROTOCOL.md`.

Codex Desktop is the default user interface. Do not instruct the user to launch Codex from PowerShell unless explicitly requested. Codex task batching and decision batching remain mandatory.
