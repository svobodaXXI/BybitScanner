# BybitScanner — Claude Code Bridge

Short, always-loaded bootstrap for Claude Code sessions in this repository. This is not a copy of `AGENTS.md`
(the Codex-facing entry point) and not an import of it — it carries only what must be known before any action,
every session. For staged recovery, the task harness (`tools.dev.task`, `tools.dev.verify`,
`tools.dev.checkpoint`), skill routing and full authority detail, read `AGENTS.md` on demand when a task
actually needs it — not as a standing load on every turn.

## Authority order

1. Current local filesystem and Git state (branch/HEAD/status) — what actually exists now.
2. `DOCUMENTS/PROJECT_STATE.md` — current mission, phase, priority, next action.
3. The active Task/Spec or durable ChangeRequest under `DOCUMENTS/CHANGE_REQUESTS/` for the task at hand.
4. `DOCUMENTS/PROJECT_CONTRACTS.md`, `PROJECT_RULES.md`, `ARCHITECTURE.md`, `PROJECT_TREE.md` — scoped normative
   authority.
5. `DOCUMENTS/ASSISTANT_PROTOCOL.md` — assistant behavior, communication, verification.
6. `AGENTS.md` — routing and harness detail, loaded on demand.

GitHub (`origin`) is for synchronization, review and history; the local checkout may be ahead of it. Chat memory
and summaries never override the current text of these documents.

## Git safety — hard rules (ASSISTANT_PROTOCOL §7.2)

- Never `git add`, `commit`, or `push` without the user's explicit go-ahead for that exact change — a prior
  approval never carries forward to a new action.
- `python -m tools.dev.checkpoint` is user-run only; never invoke it automatically.
- Never `reset --hard`, `clean -fd`, force-push, or discard/overwrite uncommitted or untracked work without
  explicit authorization. Treat existing dirty/untracked files as user-owned until proven otherwise.
- Stage exact paths for the task at hand, never `git add -A` / `git add .`, to avoid sweeping in unrelated work.
- `origin` is GitHub: the harness must not auto-publish. A GitHub-first `checkpoint` run only validates — it does
  not commit or push (`DOCUMENTS/GITHUB_FIRST_WORKFLOW.md`).

## Current snapshot — 2026-09-10 (verify against `PROJECT_STATE.md` / `git branch --show-current` if this looks stale)

- Priority: `TRADING_TERMINAL_TRADING_WORKSPACE` (HIGHEST) — Trading Workspace v1 / Manual Live Trading, active
  ChangeRequest `CR-TRADING-WORKSPACE-001`. Scanner Geometry remains ACTIVE but is no longer the top priority.
- Branch: `robot-v0-1-admission-gate` — Robot admission-gate feature work, not yet merged to `main`. This repo is
  GitHub-first with feature branches, not a fixed working branch; re-check before starting new work.
