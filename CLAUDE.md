# BybitScanner — Claude Code Bridge

Short, always-loaded bootstrap for Claude Code sessions in this repository. This file intentionally contains no current branch, mission, priority, checkpoint, or runtime snapshot; dynamic state belongs to current Git/filesystem reality and `DOCUMENTS/PROJECT_STATE.md`.

## Fast bootstrap

Before acting:

1. inspect current branch/HEAD/status and the requested outcome;
2. load the active mission/owning record from `DOCUMENTS/PROJECT_STATE.md` only as needed;
3. load `AGENTS.md` for staged recovery, task harness, skill routing, and publication rules when the task requires repository work;
4. load only the scoped authority sections needed by the affected paths/risk.

Do not run full Project Sync, deep recovery, ContextDump generation, broad status/diff/test sweeps, or extra worktree/branch setup merely because those mechanisms exist.

## Authority order

1. Current local filesystem and Git state.
2. `DOCUMENTS/PROJECT_STATE.md`.
3. Applicable Task/Spec or durable ChangeRequest.
4. Scoped `PROJECT_CONTRACTS.md`, `PROJECT_RULES.md`, `ARCHITECTURE.md`, `PROJECT_TREE.md`.
5. `DOCUMENTS/ASSISTANT_PROTOCOL.md` for assistant behavior and communication.
6. `AGENTS.md` for routing and harness detail.

Repository authority beats conversational memory and generated snapshots.

## Git / user-owned-work safety

- Treat pre-existing dirty/untracked work as user-owned until proven otherwise.
- Never use destructive reset/clean, force-push, discard, or overwrite unrelated work without explicit authority.
- Never stage broad paths such as `git add -A` / `git add .` for a scoped task.
- `python -m tools.dev.checkpoint` is user-run only.
- For a GitHub origin, checkpoint is validation-only: it must not stage, commit, or push. GitHub branch/PR publication is owned by `DOCUMENTS/GITHUB_FIRST_WORKFLOW.md`.

## Economy rule

Prefer the smallest safe path from intent to evidence. Reuse already-loaded authority and successful checks while they remain current. Batch compatible work, avoid serial micro-questions, and escalate process only for a concrete risk, dependency, approval boundary, conflict, or failed proof.