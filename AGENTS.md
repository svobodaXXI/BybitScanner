# BybitScanner Agent Guide

Canonical compact entry point for coding agents. It routes to, but does not replace, project authority.

This root `AGENTS.md` applies to the entire repository tree and is Codex's mandatory project-level instruction file.

## Short-intent task entry

Routine Codex prompts carry only the intended outcome plus genuinely task-specific facts the repository cannot
infer — no recovery instructions, file lists, skills, safety checklists, or Git boilerplate; their omission never
waives a requirement (protocol §7.1). Codex owns scope discovery from repository authority; the CLI still requires
agent-supplied `--path` arguments, so short intent is the user interface, not a claim of automatic authorization.
Ask only for missing facts that materially block safe progress; preserve explicit constraints and approval gates.

## Staged recovery

0. **Local reality:** read this file; inspect branch, HEAD, index/working-tree status, the user task, and relevant dirty scope.
1. **Task authority:** read the active mission pointer in `DOCUMENTS/PROJECT_STATE.md` or the applicable Task/Spec or durable ChangeRequest. Follow only its owning references.
2. **Scoped authority:** load only relevant sections of contracts, rules, architecture, tree, roadmap, and assistant protocol required by the affected scope.
3. **Deep recovery:** broaden review to `PROJECT_STATE.md`, `PROJECT_TREE.md`, `PROJECT_RULES.md`, `ARCHITECTURE.md`, and `ASSISTANT_PROTOCOL.md` only when scope is unknown, authorities conflict, severe interruption requires reconstruction, or work is architecture-wide.

Routine scoped work must not require the complete deep-recovery set. Do not run Project Sync merely to restore context.
Stop recovery once scope, authority, constraints, affected state and the next safe action are established.

Generate a compact disposable bootstrap when useful with `python -m tools.dev.task_context --path EXACT_PATH`
(repeat as needed; optional `--hint`); its JSON output is derived, non-authoritative context that never replaces
repository authority or governance gates.

For any repository edit (including docs/skills), run `python -m tools.dev.task start --intent "SHORT INTENT"
--path EXACT_PATH` (repeat `--path`) before editing and `python -m tools.dev.task finish --task TASK_ID` after —
this facade composes sync preflight, scoped authority routing, transactions, exact-scope verification and the
user-owned-work guard; it does not replace their owning rules. Read-only work needs no transaction. On a gate
failure, stop and resolve the cause — never bypass the harness. New paths mid-task require stopping and opening a
revised protected transaction; material changes still need normal approval.

## Communication bootstrap — hard rule

Before the first project-specific user action in any session, load the scoped communication/user-action authority
from `DOCUMENTS/ASSISTANT_PROTOCOL.md` — mandatory in addition to Trading Workspace roadmap/ChangeRequest routing.
Reload changed sections if the protocol changes mid-session. This bootstrap stays compact and scoped; it does
not require full/deep recovery or duplication of the protocol.

## Enforcement bootstrap — hard rule

Repository authority beats assistant memory; a remembered rule never substitutes for loading current
`AGENTS.md` / `ASSISTANT_PROTOCOL.md` text before project-specific user actions (protocol §8.5). Read committed
authority through the repository connector directly; do not ask the user to paste files/diffs or run read-only
commands the connector can already answer, except for genuinely local-only facts — dirty/untracked state, running
processes, ports, runtime/API state, local configuration (protocol §8.7). Treat violating an explicit rule as an
enforcement failure to fix at its source, not a reason to duplicate the rule elsewhere; prefer a cheap deterministic
guard over a repeated reminder (protocol §8.6). For substantial multiline Windows file changes, prefer Codex/local
automation or an anchor/version-checked patch helper, fail closed on mismatched anchors, over PowerShell here-strings
or manual fragment editing (protocol §8.8).

## Project skills

No procedural skill is needed for ordinary tasks — recovery, safety, evidence, verification, reporting and Git
remain mandatory through central authority regardless. Load a skill only for its distinct procedure:

- **Diagnose an unknown cause:** `.agents/skills/systematic-debugging/SKILL.md` for non-trivial defects; skip proven local fixes.
- **Review a change:** `.agents/skills/change-review/SKILL.md` when requested or before material/high-risk behavioral acceptance; not every completion or cosmetic edit.
- **Capture strategy research:** `.agents/skills/strategy-hypothesis-capture/SKILL.md` for trading observations, cases or mechanics hypotheses; not chart/UI bug reports without strategy meaning.

Select by meaning/phase; don't load both eagerly — reviewing a diff isn't authority to implement a fix, nor does
research capture authorize trading changes. DEPRECATED/REFERENCE-ONLY `SKILL.md` stubs are inactive and must not
auto-load. Handoff/workflow-improvement checklists are references, consulted only under protocol §§2.4/8.

## Authority routing

- Current local filesystem: what actually exists now.
- Local Git state: branch/HEAD/index/working-tree relationship and detailed change history.
- `DOCUMENTS/PROJECT_STATE.md`: current mission, phase, priority, and next action.
- `DOCUMENTS/PROJECT_CONTRACTS.md`: normative subsystem and workflow contracts.
- `DOCUMENTS/PROJECT_RULES.md`: mandatory project and engineering rules.
- `DOCUMENTS/ARCHITECTURE.md`: architecture and responsibility boundaries.
- `DOCUMENTS/PROJECT_TREE.md`: important canonical path roles during staged modernization.
- `DOCUMENTS/ASSISTANT_PROTOCOL.md`: assistant-specific behavior and communication.
- `DOCUMENTS/CHATGPT_CODEX_GITHUB_WORKFLOW.md`: planned GitHub-driven ChatGPT/Codex collaboration (user shorthand
  `х`); load when that workflow is enabled, used, reviewed, or resumed.
- `DOCUMENTS/EXTERNAL_REFERENCE_REUSE_POLICY.md`: rule for retaining strong external design/metric/workflow
  references as implementation accelerators only — never authority over BybitScanner contracts, safety, approval
  gates or licensing; load when external examples materially inform a feature, recording the adapted pattern.

The local checkout may be newer than GitHub, which is for remote sync/collaboration/review/history — remote
changes become local truth only after explicit sync. Dirty implementation never silently overrides a normative
contract; record the mismatch via Task/Spec.

Generated ContextDumps, reports, snapshots, caches, backups, chat and memory are non-authoritative; treat
LEGACY/DEPRECATED artifacts per warnings and never revive/delete them without authority.

## Task and change routing

Use lightweight Task/Spec for small routine work; substantial, risky, architectural or multi-session work needs an
approved durable ChangeRequest under `DOCUMENTS/CHANGE_REQUESTS/` per `CONTRACT-CHANGE-REQUEST-001` — material
scope/contract changes require an approved amendment, and applicable BLOCKING LegacyWarnings must not be bypassed.

For Trading Workspace, PAPER trading, or terminal work, read `DOCUMENTS/TRADING_WORKSPACE_MASTER_ROADMAP.md`
with the active ChangeRequest and `DOCUMENTS/ASSISTANT_PROTOCOL.md` — it defines architectural sequencing and
acceptance gates across sessions. Any handoff/checkpoint records current roadmap stage, last accepted stage,
blocker and next action by reference, not by duplicating the roadmap into handoff text.

Use `tools.project_sync.governance.codex_workflow` as the narrow pre-implementation gate: `lightweight --path PATH`
(or `--symbol`) for lightweight work, `durable CHANGE_REQUEST` for durable work (add `--context PATH` to validate
an existing dump; generate one only for multi-session/context-heavy/recovery-package/explicit requests).
`PASS`/`ADVISORY` continue; `STALE`/`FAIL`/`BLOCKING` stop. A missing ContextDump permits direct recovery but never
bypasses scoped LegacyWarnings; ContextDump stays derived and non-authoritative.

## Change safety

Before editing, inspect actual targets and `git status --short`. Treat unrelated pre-existing changes and untracked
files as user-owned. Never overwrite, reformat, stage, clean, restore, reset, delete, move, discard, commit, or push
user work unless explicitly authorized. Keep changes minimal, scoped, reversible, and contract-compatible (protocol §4, §6).

## Verify and record

No synthetic/fake UI tests for behavior verifiable by hand; test only critical logic, material regressions, or
hard-to-verify behavior (protocol §6.1).

Development feedback: `python -m tools.dev.verify --focused --path EXACT_PATH` (repeat paths; `--check-command` as
needed). No production build, no PASS receipt, incompatible with `--transaction`.

Finish the protected task once via `python -m tools.dev.task finish --task TASK_ID`; it runs the final exact-scope
verifier (including the required frontend build), checks the task delta and unrelated work, and records a PASS
receipt under `.git/bybitscanner/`. Do not duplicate it with a standalone `tools.dev.verify` run without new cause.
Full evidence requirements: protocol §7.2.

`python -m tools.dev.checkpoint --message "..."` is a user-run Git-write command. Codex must never invoke it
automatically. It consumes the latest PASS receipt, stages only its exact paths, commits, pushes to `origin`, and
verifies the remote SHA; any mismatch stops the workflow without touching unrelated work.

Git owns detailed implementation history; update authoritative documentation only when its owned state, contract,
decision, or plan actually changed. Report checks, failures, unresolved risks, and unrelated dirty work. Follow
`DOCUMENTS/ASSISTANT_PROTOCOL.md` for role, communication style and checkpoint behavior. Codex Desktop is default;
don't tell the user to launch it from PowerShell unless asked.
