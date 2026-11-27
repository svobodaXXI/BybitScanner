# 4. LOCAL REALITY AND USER-OWNED WORK

For local/Codex tasks, start from the current local checkout and inspect actual targets before editing. For
ChatGPT-led GitHub-first work, use the current remote repository state plus known synchronization evidence and treat
local-only state as a separate runtime/verification concern. Existing dirty and untracked work is user-owned unless
proven otherwise. Never overwrite, reformat, stage, clean, restore, reset, move, delete, discard, commit, or push
unrelated work.

## 4.1 PC/VPS GIT SYNC PREFLIGHT — HARD GATE

Before starting a new repository task on any development host, including the Windows PC or VPS, apply the checks
below. For edit tasks, `task start` performs this preflight against the intended branch's remote tracking ref; consume its
result instead of repeating a successful fetch/comparison. These checks concern the current host only and do not
prove that another host or its running services are synchronized.

1. fetch current remote state from `origin`;
2. compare local `HEAD` with the intended branch's remote tracking ref (`origin/main` on `main`, otherwise `origin/<task-branch>`);
3. start new work only when local `HEAD` matches that intended remote tracking ref;
4. if local state is `ahead`, `behind`, or `diverged`, stop before editing and resolve synchronization explicitly;
5. preserve all dirty and untracked user-owned work while diagnosing synchronization;
6. never use `reset --hard`, `clean`, force-push, discard, or equivalent destructive actions merely to make states match;
7. if independent progress already exists on two hosts, preserve both histories first, then inspect and resolve them through an explicit merge, rebase, or other reviewed reconciliation path.

The synchronization preflight is fail-closed: uncertainty about repository ancestry or remote freshness means `SAFE TO START: NO` until resolved.

## 4.2 GITHUB ↔ CODEX/LOCAL HANDOFF SYNC GUARD — HARD GATE

A tool-boundary handoff is itself a synchronization trigger when the next step
will mutate repository state.

Before the first mutating Codex/local task after ChatGPT-led GitHub-first work,
or the first GitHub-first repository edit after Codex/local changes, the
assistant must automatically initiate or propose a bounded synchronization
preflight. Do not wait for the owner to remember this step.

The preflight must establish only what is necessary for the intended task:

1. intended destination checkout/worktree and branch/HEAD;
2. current remote state after fetch;
3. ahead/behind/diverged ancestry against the intended remote ref;
4. dirty/untracked/stashed user-owned work relevant to safe reconciliation;
5. whether the destination contains commits or file changes not represented on
   the other side.

If the states do not match, preserve both histories/work products first and
resolve the mismatch explicitly before editing. Never hide the mismatch with
`reset --hard`, `clean`, force-push, discard, blind pull/rebase, or checkout
that could overwrite unrelated work.

This guard is required for **mutating handoffs**, not for ordinary read-only
inspection. A previously proven synchronization result may be reused while its
branch/HEAD/remote inputs remain unchanged.


### 4.2.1 STALE WORKTREE / DUPLICATE-WORK PREVENTION — OWNER RULE 2026-09-26

A stale local worktree can make already-merged, superseded, or otherwise
absorbed work look active and can cause duplicate implementation or repeated
investigation. Treat this as a process defect, not as harmless repository
clutter.

Before resuming implementation from an old/detached/dirty worktree, or before
re-implementing work that appears unfinished locally, the assistant must first
establish whether its commits and relevant file deltas are already represented
on current `origin/main` or an active remote branch/PR. Use ancestry plus
patch-equivalence/content comparison where hashes differ; do not infer from
commit counts alone.

Required no-repeat behavior:

1. if a local commit/patch is already merged or patch-equivalent on current
   `main`, classify the local branch/worktree as historical/superseded rather
   than active work;
2. if current `main` has structurally replaced the code a dirty local edit
   depends on, preserve that edit first, then treat it as superseded unless a
   current task explicitly reauthorizes porting its behavior;
3. preserve unique dirty/untracked/runtime/user-owned artifacts before any
   cleanup or checkout move; do not use stale worktree state as authority after
   a successful reconciliation;
4. after reconciliation, record the surviving authoritative state and avoid
   repeating tests, implementation, or diagnosis whose outcome is already
   established by the merged/current state.

The purpose of this gate is to prevent the observed failure mode:
`stale worktree -> mistaken unfinished work -> duplicate or obsolete work -> owner time lost`.


### 4.2.2 CLAUDE MODEL / EFFORT HANDOFF — OWNER RULE 2026-09-26

Before every copy-ready prompt intended for Claude Code, state the recommended
model and reasoning mode **before** the prompt so the owner knows whether to
switch models.

Default routing:

- `Sonnet 5 / Medium` — routine Git/reconciliation/retirement work, bounded
  repository inspection, mechanical implementation with clear architecture,
  straightforward tests and PR maintenance;
- `Sonnet 5 / High` — non-trivial bounded implementation where architecture
  and invariants are already fixed but the code path is complex enough to
  benefit from deeper reasoning;
- `Opus 5.5` — the first slice of a difficult implementation, architecture
  decisions, ambiguous runtime/ownership/race defects, geometry/algorithm
  changes with competing invariants, or reconciliation where semantic
  equivalence is uncertain.

Preferred development pattern for difficult work:

1. use `Opus 5.5` for the first architectural/diagnostic slice to define
   invariants, scope and failure modes;
2. once those decisions are explicit and stable, subsequent bounded slices may
   move to `Sonnet 5 / High`;
3. do not downgrade while material architectural questions remain unresolved;
4. do not use Opus for routine mechanical cleanup when Sonnet is sufficient.

If switching models would not materially improve correctness or owner time,
say `Остаться на текущей модели` rather than recommending a change.

Model choice never changes project authority, safety gates, scope ownership,
runtime restrictions, acceptance rules, or verification requirements.

Destructive or broad Git/filesystem actions require explicit authority and verified exact targets. In particular,
`reset`, `restore`, `clean`, and discard operations are prohibited without explicit authorization. Prefer minimal,
scoped, reversible changes. Do not request content already accessible in the repository or current context.

`PROJECT_TREE.md` owns canonical path roles when path authority is needed. Do not guess or invent paths.

---

# 5. ARTIFACT AND CONTINUATION STATE

## 5.1 ARTIFACT_STATE_AND_NO_DUPLICATE_RULE

Track each working artifact by name, path, role, version, received/delivered state, and whether it changed. Do not
request, reopen, or redeliver an unchanged artifact unless the user explicitly asks. Full files are appropriate for
new files, substantial structural replacement, safety, or an explicit request; otherwise prefer a precise patch or
targeted result.

If an assistant-created artifact has a wrong canonical name, path, identifier, or metadata, correcting it also
requires verified scoped cleanup of the erroneous artifact and its downstream duplicate/generated/install tails.
Never delete merely similar or unrelated user work. Retention of an erroneous artifact requires an independent
explicit project/audit/training requirement.

Training/reference archive delivery normally consists of a direct ZIP link plus one exact invocation of
`tools/training/install_reference_archive.ps1`; do not require manual extraction when the canonical installer can
consume it. Detailed archive semantics remain owned by `PROJECT_RULES.md` and reference-storage rules.

## 5.2 CONTINUATION_COMMAND_RULE

The command `э` means “continue the current project workflow”. It does not mean repeat the last file, command,
result, or `notepad` instruction. Determine the next unfinished step, reuse already received artifacts, request only
the exact missing artifact if necessary, and return only a new result. If no new result exists, do not manufacture a
duplicate response.

---

