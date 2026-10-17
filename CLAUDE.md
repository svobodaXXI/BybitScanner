# BybitScanner — Claude Code Bridge

Short, always-loaded bootstrap for Claude Code sessions in this repository.
No current branch/mission snapshot lives here; the owner's current task,
intended GitHub ref and relevant host-local Git/runtime evidence supply
dynamic state. `DOCUMENTS/PROJECT_STATE.md` is a persisted checkpoint,
not an automatically current runtime fact.

## Fast bootstrap

Before acting:

1. inspect current branch/HEAD/status and the requested outcome;
2. load the active mission/owning record from `DOCUMENTS/PROJECT_STATE.md` only as needed;
3. load `AGENTS.md` for staged recovery, task harness, skill routing, and publication rules when the task requires repository work;
4. load only the scoped authority sections needed by the affected paths/risk.

Do not run full Project Sync, deep recovery, ContextDump generation, broad status/diff/test sweeps, or extra worktree/branch setup merely because those mechanisms exist.

## Authority and current-state routing

Current owner goal + mandatory safety gates come first. Use `AGENTS.md`
for scope routing, then the affected Task/Spec/ChangeRequest and relevant
contracts. For GitHub-published code/docs use the intended GitHub branch/PR
and HEAD; for local unsaved work/runtime trust actual host-local evidence.
`PROJECT_STATE.md`, BACKLOG and QUEST_STATE contain checkpoints, not a
license to override newer owner commands with dated "current" headings.
`DOCUMENTS/ASSISTANT_PROTOCOL.md` owns communication and Result-First
transitions. Avoid broad PROJECT_STATE reads on routine tasks.

Repository/host evidence beats conversational memory and generated snapshots.

## Git / user-owned-work safety

- Treat pre-existing dirty/untracked work as user-owned until proven otherwise.
- Never use destructive reset/clean, force-push, discard, or overwrite unrelated work without explicit authority.
- Never stage broad paths such as `git add -A` / `git add .` for a scoped task.
- `python -m tools.dev.checkpoint` is user-run only.
- For a GitHub origin, checkpoint is validation-only: it must not stage, commit, or push. GitHub branch/PR publication is owned by `DOCUMENTS/GITHUB_FIRST_WORKFLOW.md`.

## Result-first transition

At **every** task hand-off or suggested follow-up, use the mandatory
`AGENTS.md` Result-first transition gate: prefer the next directly observable
owner outcome over another audit, PR or check; reuse unchanged evidence,
stop only at proven safety/mandatory gates or a material safety unknown, and
choose one shortest authorized action. This creates no extra checklist or
report and cannot authorize a merge or Scanner/Robot runtime action.

## Economy rule

Prefer the smallest safe path from intent to evidence. Reuse already-loaded authority and successful checks while they remain current. Batch compatible work, avoid serial micro-questions, and escalate process only for a concrete risk, dependency, approval boundary, conflict, or failed proof.