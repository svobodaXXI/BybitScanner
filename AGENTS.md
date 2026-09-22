# BybitScanner Agent Guide

Compact mandatory entry point for coding agents. It routes to project authority; it does not duplicate it.

## Fast task entry

## Outcome-first Scanner / PAPER Robot priorities — owner direction

**Business goal:** a Scanner that shows faithful, independently checkable
formation geometry and a PAPER Robot that reliably completes the signal →
order → protection → closure lifecycle. Optimize for working results, not
more test campaigns, new infrastructure, prettier charts or more alerts.

**When choosing the next dependent development slice, use this order:**

1. **False patterns first:** eliminate demonstrably wrong formations and
   misplaced anchors/START using real saved decision-time candles. A strong
   score, display adjustment or retrospective fit does not make a wrong
   structure acceptable.
2. **Reliable PAPER execution next:** for already confirmed signals, make the
   Robot's entry, protection, reconciliation and exit work end-to-end and
   fail-closed. Do not enable or alter LIVE trading or change risk/strategy
   parameters merely to advance this priority.
3. **Missed patterns systematically, not by owner manual browsing:** compare
   source-time Scanner outputs against independently generated potential
   formation windows in saved OHLC history; surface reproducible chart cases
   for review. These proposals are **hypotheses**, not proof of real missed
   patterns or permission to lower admission gates. Measure coverage only
   after false positives and PAPER reliability are under control.

The owner can visually identify wrong drawn formations and broken PAPER
execution, but cannot reasonably discover all missed patterns by manually
watching charts. **Do not outsource missed-pattern discovery to the owner.**
Follow the currently authorized, task-specific route (the L-shaped detector
is the active geometry implementation scope); this priority ordering is a
decision guide, **not permission to switch tasks, restart services, start
trading, or expand the current slice**. Prefer one evidence-backed micro-slice
and its narrow changed-behavior check over repeated whole-Scanner runs.

For routine work, start from the intended outcome. Do not require the user to provide recovery boilerplate, file lists, skills, Git commands, safety checklists, or test lists that the repository can infer.

Recovery is staged and stops as soon as the task is safe to execute:

1. **Local reality** — branch/HEAD/status, requested outcome, relevant dirty scope.
2. **Task authority** — active mission pointer in `DOCUMENTS/PROJECT_STATE.md` or the applicable Task/Spec/ChangeRequest.
3. **Scoped authority** — only owning sections required by the affected paths and risk.
4. **Deep recovery** — `PROJECT_STATE.md`, `PROJECT_TREE.md`, `PROJECT_RULES.md`, `ARCHITECTURE.md`, and `ASSISTANT_PROTOCOL.md` only for unknown scope, authority conflict, severe interruption, or architecture-wide work.

Routine scoped work must not run full Project Sync, generate a ContextDump, or load the deep-recovery set merely to restore context. Reuse fresh authority already loaded.

**Operational requests:** For start/stop/restart, enable/configure, deploy, or synchronize requests, resolve the actual entrypoint and invoked dependency/side-effect chain from repository sources before asking the user to inspect files or run commands. Follow `DOCUMENTS/ASSISTANT_PROTOCOL.md` §2.2.3; request only genuinely host-local evidence that the connector cannot provide. A launcher name alone never proves which services it starts. This is a task-triggered check, not another routine recovery stage.

## Repository edits

For a local/Codex edit, use the protected task facade:

```text
python -m tools.dev.task start --intent "SHORT INTENT" --path EXACT_PATH
...minimal implementation...
python -m tools.dev.task finish --task TASK_ID
```

Repeat `--path` only for paths genuinely in scope. Read-only work needs no transaction. New paths mid-task require a revised protected transaction; do not widen scope silently.

`task start` owns sync preflight, compact task-context generation, the routine scoped LegacyWarning gate, and protected transaction setup. Do not run a second `codex_workflow lightweight` command after a successful `task start`, and do not repeat successful fetch/status/context checks without new cause. `task finish` owns final exact-scope verification and the PASS receipt; do not duplicate it with a standalone final verifier unless evidence changed or an independent check is required.

For development feedback only:

```text
python -m tools.dev.verify --focused --path EXACT_PATH
```

Use additional tests/builds only when the changed behavior or applicable contract requires them.

## Project Sync / governance escalation

Full Project Sync is an escalation mechanism, not a routine task step.

The standalone `tools.project_sync.governance.codex_workflow lightweight` command remains available for read-only diagnosis or compatibility, but routine edit tasks receive the same scoped LegacyWarning enforcement from `task start` and must not run both gates.

Use the durable governance path only when its distinct value is needed:

- `durable CHANGE_REQUEST` for an approved durable/multi-session change;
- ContextDump generation only for multi-session, context-heavy, recovery-package, or explicit requests.

`PASS`/`ADVISORY` may continue; `STALE`/`FAIL`/`BLOCKING` stop. Never add recovery, worktrees, branches, full regression, ContextDump, or Project Sync “just in case”.

## Communication bootstrap

Before the first project-specific user action in a session, load the relevant communication/user-action rules from `DOCUMENTS/ASSISTANT_PROTOCOL.md`. Reload only changed/uncertain sections.

If user action is objectively required, follow the protocol’s exact `Сейчас сделай:` and copy-ready rules. Do not ask the user to run read-only repository inspection that an available repository connector can perform.

## Active Scanner geometry course

For any Wedge/Triangle or L-shaped formation geometry task, open the **short current index** `DOCUMENTS/SCANNER_GEOMETRY_CURRENT_COURSE.md` first. Its `Universal wedge anchor rule` is mandatory for wedges only. The active L-shaped formation scope and next step are recorded separately in the same index; follow scoped links only for evidence the task actually needs. It names implemented vs pending behavior and historical vs active decisions. Do not load lengthy past research, run Project Sync or repeat closed diagnostics by default.

## Authority routing

Use the narrowest owner that answers the current question:

- current local filesystem/Git — actual checkout/runtime state;
- `DOCUMENTS/PROJECT_STATE.md` — current mission, phase, priority, next action;
- active Task/Spec/ChangeRequest — authorized scope;
- `DOCUMENTS/PROJECT_CONTRACTS.md` / `PROJECT_RULES.md` — normative contracts/rules;
- `DOCUMENTS/ARCHITECTURE.md` / `PROJECT_TREE.md` — architecture and canonical path roles;
- `DOCUMENTS/ASSISTANT_PROTOCOL.md` — assistant communication/execution behavior;
- `DOCUMENTS/GITHUB_FIRST_WORKFLOW.md` — GitHub publication behavior;
- `DOCUMENTS/EXTERNAL_REFERENCE_REUSE_POLICY.md` — external-reference reuse when external examples materially inform a feature.

Generated ContextDumps, reports, snapshots, caches, chat history, and memory are derived context, not authority.

## Skills

No procedural skill is required for ordinary work. Load a skill only for its distinct procedure:

- unknown/non-trivial defect → `.agents/skills/systematic-debugging/SKILL.md`;
- requested/material high-risk change review → `.agents/skills/change-review/SKILL.md`;
- trading strategy observation/hypothesis capture → `.agents/skills/strategy-hypothesis-capture/SKILL.md`.

Do not eagerly load multiple skills. Handoff/workflow-improvement references are consulted only when their specific trigger applies.

## Trading / durable scope

Small routine changes use the lightweight task path. Substantial, risky, architectural, or multi-session work requires the applicable approved durable ChangeRequest under `DOCUMENTS/CHANGE_REQUESTS/`.

For Trading Workspace, PAPER trading, or terminal behavior, route through the active ChangeRequest and `DOCUMENTS/TRADING_WORKSPACE_MASTER_ROADMAP.md` when those records own the affected behavior. Financial/LIVE/risk decisions never become authorized merely because a task or verification gate passes.

## Change safety

Treat unrelated pre-existing dirty/untracked work as user-owned. Never overwrite, stage, restore, reset, clean, move, delete, discard, commit, or push it without explicit authority. Keep changes minimal, scoped, reversible, and contract-compatible.

Do not create speculative infrastructure or refactor adjacent code “while here”. At equal safety, prefer fewer files, commands, worktrees, branches, PRs, tests, and user turns.

## Verification and publication

Use the minimum evidence that proves the claim. Critical deterministic trading behavior requires focused regression evidence; frontend source changes require the production build before browser/phone acceptance; real UI/touch/live claims require real-environment acceptance.

For GitHub origins, `python -m tools.dev.checkpoint --message "..."` is **user-run validation only**. It validates the current PASS receipt and must not stage, commit, or push. Publication belongs to the GitHub branch/PR flow in `DOCUMENTS/GITHUB_FIRST_WORKFLOW.md`; after merge, local checkouts synchronize from GitHub.

For non-GitHub/local test repositories, legacy checkpoint publication semantics may apply.

## Workflow proportionality

One logical change should normally remain one branch/PR and one usable worktree. Continue small review fixes in the same integration surface. Add isolation, a new task/branch/worktree/PR, broad recovery, or full regression only for a concrete dependency, risk, conflict, approval boundary, or demonstrated inability of the current workflow to prove the delta safely.

Git owns detailed implementation history. Update authoritative documentation only when the state/contract/decision it owns actually changes.