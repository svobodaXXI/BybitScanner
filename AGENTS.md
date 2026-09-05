# BybitScanner Agent Guide

Canonical compact entry point for coding agents. It routes to project authority; it does not replace that authority.

This root `AGENTS.md` applies to the entire repository tree rooted at `C:\BybitScanner` and is a mandatory project-level instruction file for Codex.

## Short-intent task entry

Routine Codex prompts contain only the intended outcome plus genuinely task-specific constraints or facts that
the repository cannot infer. Users do not have to supply recovery instructions, file lists, skills, safety
checklists, verification commands, report templates, or Git boilerplate. Their omission never waives a requirement.

Codex owns applicability decisions and scope discovery from current repository authority; the harness owns the
deterministic checks it implements. Discover the smallest exact scope before starting the task transaction. The
current CLI still requires agent-supplied `--path` arguments: short intent is the user interface, not a claim that
the harness discovers paths or grants authorization. Ask only for missing decisions or facts that materially
block safe progress. Preserve explicit task constraints and all existing approval gates.

## Staged recovery

0. **Local reality:** read this file; inspect branch, HEAD, index/working-tree status, the user task, and relevant dirty scope.
1. **Task authority:** read the active mission pointer in `DOCUMENTS/PROJECT_STATE.md` or the applicable Task/Spec or durable ChangeRequest. Follow only its owning references.
2. **Scoped authority:** load only relevant sections of contracts, rules, architecture, tree, roadmap, and assistant protocol required by the affected scope.
3. **Deep recovery:** broaden review to `PROJECT_STATE.md`, `PROJECT_TREE.md`, `PROJECT_RULES.md`, `ARCHITECTURE.md`, and `ASSISTANT_PROTOCOL.md` only when scope is unknown, authorities conflict, severe interruption requires reconstruction, or work is architecture-wide.

Routine scoped work must not require the complete deep-recovery set. Do not run Project Sync merely to restore context.
Stop recovery once scope, authority, constraints, affected state and the next safe action are established.

Generate a compact disposable bootstrap when useful with `python -m tools.dev.task_context --path EXACT_PATH` (repeat `--path` as needed; optional `--hint`). Its JSON output is derived, non-authoritative context and never replaces repository authority or governance gates.

For repository edits, including documentation and skills, use `python -m tools.dev.task start --intent "SHORT INTENT" --path EXACT_PATH` (repeat `--path` for the discovered scope) before edits and `python -m tools.dev.task finish --task TASK_ID` afterward. This facade composes sync preflight, scoped authority routing, task transactions, exact-scope verification, user-owned-work guards, and the standard completion report; it does not replace their owning rules or tools. Read-only work needs no edit transaction. On a gate failure, stop dependent work and resolve the cause; never bypass the harness or alter it merely to complete the task. If additional paths become necessary, stop before editing them and establish a protected transaction covering the revised authorized scope; material changes still require the normal approval.

## Communication bootstrap — hard rule

Before the first project-specific user action or technical instruction in every BybitScanner ChatGPT chat, load the scoped communication and user-action authority from `DOCUMENTS/ASSISTANT_PROTOCOL.md`. This remains mandatory for Trading Workspace work in addition to its existing roadmap/ChangeRequest routing. If `ASSISTANT_PROTOCOL.md` changes during the current chat/session, reload its changed communication/workflow sections before issuing the next user action. Keep this bootstrap compact and scoped; it does not require full/deep recovery or duplication of the protocol.

## Enforcement bootstrap — hard rule

Repository authority beats assistant memory. Chat memory, summaries, and remembered workflow rules may speed up
recovery but never replace loading the applicable current `AGENTS.md` / `ASSISTANT_PROTOCOL.md` authority before
project-specific user actions.

When committed authority is available through an integrated repository connector, read it directly. Do not ask the
user to manually paste committed project files or broad diffs. Request shell output only for local-only facts that
the remote repository cannot know, such as dirty/untracked state, running processes, ports, runtime logs, local
configuration, and uncommitted changes.

Treat violation of an already-explicit rule as an enforcement failure. Strengthen bootstrap/preflight or a
deterministic guard instead of duplicating the same rule. Prefer technical prevention when cheap and reliable.

For substantial multiline Windows file changes, prefer Codex/local automation or a deterministic downloadable
Python/patch helper with anchor/version checks over PowerShell here-strings or manual fragment editing. Preserve
encoding/newlines, fail closed on mismatched anchors, and verify only the authorized paths afterward.


## Project skills

Ordinary tasks require no procedural skill by default. Recovery, safety, evidence, verification, reporting and Git
remain mandatory through central authority and the harness. Load a skill only for its distinct procedure:

- **Diagnose an unknown cause:** `.agents/skills/systematic-debugging/SKILL.md` for non-trivial defects; skip proven local fixes.
- **Review a change:** `.agents/skills/change-review/SKILL.md` when requested or before material/high-risk behavioral acceptance; not every completion or cosmetic edit.
- **Capture strategy research:** `.agents/skills/strategy-hypothesis-capture/SKILL.md` for trading observations, cases or mechanics hypotheses; not chart/UI bug reports without strategy meaning.

Select by meaning and phase, without user invocation. A task may move from diagnosis to review, but do not load
both eagerly or treat reviewing a diff as authority to implement a fix. Research capture never authorizes trading
code changes. Inspecting instructions does not activate their domain procedure.

Legacy SKILL.md compatibility stubs marked DEPRECATED or REFERENCE-ONLY are not active skills and must not be automatically loaded.

Handoff and workflow-improvement checklists are references, not skills. Consult them only under
`ASSISTANT_PROTOCOL.md` §§2.4 and 8; routine recovery/completion does not load them.

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

Finish the protected task through `tools.dev.task finish`; it invokes the exact-scope `tools.dev.verify`, verifies
the task delta and unchanged index/user-owned work, and records the PASS receipt under `.git/bybitscanner/`.
Do not run a second standalone verifier solely to satisfy duplicated prose. Standalone verification, when
independently needed, uses `python -m tools.dev.verify` with repeated exact `--path` arguments; it does not replace
task finish. Codex selects any necessary focused checks not routed by the verifier and reports only actual evidence.

`python -m tools.dev.checkpoint --message "..."` is a user-run Git-write command. Codex must never invoke it automatically. It consumes the latest current PASS receipt, stages only its exact paths, checks the cached diff, commits, pushes to `origin`, and verifies the remote SHA; any mismatch or failure stops the workflow without touching unrelated work.

Validate in proportion to risk through the verifier: compile affected Python, run focused tests, check relevant integration paths, review the scoped diff, and run broader authoritative validation only when required. Never hide or overstate results.

Git owns detailed implementation history. Update authoritative documentation only when its owned current state, contract, decision, or planned work changed. Stage and commit only authorized scope; report checks, failures, unresolved risks, and unrelated dirty work.

For role, communication style, and mission/checkpoint behavior, follow `DOCUMENTS/ASSISTANT_PROTOCOL.md`.

Codex Desktop is the default user interface. Do not instruct the user to launch Codex from PowerShell unless explicitly requested. Codex task batching and decision batching remain mandatory.
