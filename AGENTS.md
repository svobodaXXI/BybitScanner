# BybitScanner — lean agent entry (Codex / repository agents)

Generated ContextDumps, reports, snapshots, caches, chat history, and memory are derived context, not authority.

Purpose: smallest safe, outcome-first entry. The complete prior `AGENTS.md` is
preserved **verbatim** at `DOCUMENTS/AGENT_GUIDE_FULL.md`; it remains authoritative
for its applicable contracts. **Do not eagerly read that entire document**:
follow the scoped routing below. Never replace a safety check with an economy shortcut.

## 1. Current owner outcome priority — 2026-10-15

**Top priority: advance toward a verified autonomous PAPER trade, not another research cycle.** At each next step, choose the shortest safe action that materially advances: canonical safe runtime stop (if required) → deploy merged process isolation (`4d97e56`) → verify Scanner/Robot separation and protection health → obtain explicit owner authorization for PAPER_AUTO → prove automatic admission, fill, active STOP/TAKE, terminal exit and fee-aware net PnL. Trading profit is not guaranteed; verified execution and risk compliance are acceptance criteria.

Defer standalone geometry, generic instrumentation, duplicate tests, broad audits, workflow/tooling and documentation work unless an evidenced **mandatory safety blocker** prevents the next trading step. For such blockers, make the smallest justified fix and return to PAPER acceptance; never bypass protection, admission, loss limits or owner approval. Preserve current Scanner progress where practical, but it must not delay PAPER trading acceptance indefinitely. Existing runtime remains SHADOW until explicitly authorized to change.

## Fast task entry

1. Name the owner's requested result and its observable acceptance criterion.
2. Inspect current branch/HEAD, relevant dirty files and the exact affected path.
3. Reuse existing worktree, proven diagnosis, benchmark, tests and PR before
   proposing new scaffolding or rediscovering past work.
4. Read **only the relevant sections** of the full guide and canonical specs.
   Use heading/grep/range lookup rather than copying whole documents into context.
5. Respect the current user instruction over stale queue items and historical
   milestones; identify actual runtime state from current evidence, never memory.
6. One logical change → one scoped task/worktree/PR; stop when verified.

## 2. Safety and ownership — always applicable

- **PAPER / LIVE separation is mandatory.** Never enable LIVE or issue real
  exchange mutations without explicit, task-specific owner authorization.
- Runtime start/stop, PAPER_AUTO enablement, emergency operations and merge
  require applicable owner approval and the host's own permissions. An older
  owner-only rule can be overridden only by an explicit new instruction; neither
  is a bypass of host permissions or fail-closed risk gates.
- Preserve STOP/TAKE, protection, reconciliation, data continuity, capital
  limits, daily loss safeguards, DB durability and SQLite consistency.
- Do not infer a safe position/flat state from a projection alone. Prove actual
  orders, fills, positions, obligations and late owner commands before shutdown.
- Do not kill a blocking process, overwrite a database, reset a worktree or
  remove user-owned files merely to finish a task. Fail safely with evidence.
- No bulk staging (`git add .` / `git add -A`), destructive reset/clean, forced
  push or unrelated edits; preserve secrets and never print local tokens.
- Full end-to-end trading acceptance means real PAPER lifecycle evidence,
  including fill, active protection, terminal exit and PnL—not just tests/READY.
- Safety and action details: see relevant headings in
  `DOCUMENTS/AGENT_GUIDE_FULL.md` and applicable strategy/runtime spec.

## 3. Avoid expensive context and testing

- Do **not** read `DOCUMENTS/PROJECT_STATE.md` (6347+ lines) from beginning to
  end for routine tasks. Target sections only when current-state authority is
  needed; confirm dynamic facts via Git, logs or local state.
- `CLAUDE.md` is the separate short Claude Code bridge. Do not concatenate
  `CLAUDE.md`, `AGENTS.md`, full guide, project state, backlogs and specs by
  default. Follow explicit dependencies, scoped to changed paths.
- Do not run full Project Sync, ContextDump, broad sweeps, extra worktrees,
  duplicate benchmarks, blanket audits or full test suites without a reason.
- Use existing focused tests; do not repeat passing evidence unchanged.
- One bounded timeout; after expiry, diagnose the specific blocking step.
  No escalating wait ladder, endless polling or duplicate launches.
- Never infer cause merely from correlation. Reproduce with cheapest safe
  discriminating test; patch only a supported cause. No modifying safety limits,
  latency thresholds, queues or durability settings to hide a performance defect.
- Optimize owner's end-to-end time: **Outcome → Reuse → Eliminate → Fastest safe
  path → Safety → Stop**. This is a quick self-check, not a new planning workflow.

## 4. Task harness and GitHub

- For scoped repository edits use the existing protected task harness documented
  in `DOCUMENTS/AGENT_GUIDE_FULL.md`, section `Repository edits`:
  `python -m tools.dev.task start` and `finish` with the real path scope.
- `task start` already performs the required scoped preflight; do not
  duplicate it with the legacy lightweight workflow. `task finish` supplies
  completion proof; avoid redundant final verification.
- If harness fails, attempt at most one narrowly evidenced repair, within
  authorization; never turn it into an infrastructure side quest.
- Use GitHub-first branch/PR workflow from
  `DOCUMENTS/GITHUB_FIRST_WORKFLOW.md`; no automatic merge.
- If local `gh` is unavailable, push the prepared branch and report it; do
  not retrieve secrets or invent workarounds. The GitHub connector may create
  the PR separately.
- Update canonical documentation only when a contract, state or decision
  materially changes; avoid rewriting unrelated historical documents.

## 5. Routes into exact project authority

- Current user task + branch/HEAD govern immediate priorities. For dynamic
  mission consult **targeted** `DOCUMENTS/QUEST_STATE.md` and the top relevant
  `DOCUMENTS/BACKLOG.md` section, not a deep recovery.
- Wedge / triangle / L-shape geometry: first read the relevant heading of
  `DOCUMENTS/SCANNER_GEOMETRY_CURRENT_COURSE.md`, then linked owning spec.
- Ikigai Box admission and protection: scoped
  `DOCUMENTS/IKIGAI_BOX_STRATEGY_SPEC.md` and runtime code/tests.
- Telegram cards / controls: relevant `notification.py`, delivery and review
  modules, UX contract headings of the full guide.
- Windows launcher / runtime safety: applicable owner-launch and ownership
  headings in `DOCUMENTS/AGENT_GUIDE_FULL.md`.
- Full Scanner visual acceptance, 5m→1m order, Telegram signal delivery and
  pattern gates: relevant dedicated sections of the full guide.
- Communication, requested owner actions and evidence reporting:
  task-specific sections of `DOCUMENTS/ASSISTANT_PROTOCOL.md`.
- Historical decisions, game rewards and older priority notes: consult only
  when the task changes or needs those records; do not load for a routine bug.

## 6. Existing skills — load selectively

- Non-trivial defect, unknown cause:
  `.agents/skills/systematic-debugging/SKILL.md`.
- Material/high-risk change review:
  `.agents/skills/change-review/SKILL.md`.
- Research-only trading hypothesis capture:
  `.agents/skills/strategy-hypothesis-capture/SKILL.md`.
- Ordinary simple fixes require no skill. Do not eagerly load all three.
- The preserved full guide may point to other procedures; open only when the
  current task meets their conditions.

## 7. Interaction and reporting

- Speak Russian for project interactions; retain lightweight quest naming
  where relevant, without allowing presentation rules to delay technical work.
- For owner action provide one clear, copy-ready `Сейчас сделай:` instruction.
- Report actual PASS/BLOCKED, tests, diff, commit/PR, and what remains
  unverified. Never claim CI, runtime acceptance or merged code without proof.
- If work is blocked by lack of authority, disclose the exact boundary; do not
  retry through an alternative token, command or process.
- Prefer a single concise report after one bounded step over streams of
  unchanged “still waiting” messages.

## 8. Scope compatibility

The original full guide was moved, **not deleted**. For any rule not included
in this lean entry, the relevant full-guide section remains binding when its
trigger applies. This router does not override specific safety, acceptance,
owner-action, publishing or protected-task contracts. If there is ambiguity,
read only the pertinent original section and resolve it before taking action.
