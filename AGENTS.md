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
and its narrow changed-behavior checks during implementation; complete the
mandatory full-universe Scanner acceptance pass below for every new pattern
or Scanner correction, without redundant repeated passes.

## Scanner runtime ownership — MANUAL ONLY (OWNER RULE 2026-09-23)

**Only the owner manually starts the real Scanner through the verified existing
Scanner-only control surface.** ChatGPT, Codex, Claude Code and delegated agents
must not launch, resume, restart, schedule, or keep a full Scanner pass running
inside an agent session, including acceptance passes. No automatic/manual-via-
agent handoff that leaves the agent consuming quota while the Scanner runs.
Codex may perform a bounded read-only preflight and necessary focused developer
checks, then MUST terminate its task and hand back a concise result. The owner
separately decides when to launch the one complete real Scanner/Telegram pass.
A full-pass acceptance requirement does NOT authorize agents to execute it.
Do not stop an existing process blindly: identify ownership and impact on
Robot/positions first; if a possibly active agent-run Scanner is reported,
prioritize a safe owner-controlled stop of that specific process, not a broad
shutdown. Do not repeatedly poll/wait for a long run inside Codex. See
`DOCUMENTS/ASSISTANT_PROTOCOL.md` and `DOCUMENTS/BACKLOG.md`.

## Exclusive visual acceptance workflow — full real Scanner pass ONLY (OWNER OVERRIDE 2026-09-23)

**The owner inspects and accepts ALL Scanner changes solely via ONE COMPLETE
real Scanner pass across EVERY available eligible symbol, using normal
configured Telegram signal delivery for ALL integrated patterns.** This applies
to **every** new pattern, chart/caption/button/presentation adjustment,
detector/geometry fix and Scanner behavior change, including a seemingly
small Ikigai Box card change. Do not offer an isolated updated card, a
single-symbol chart, a hand-picked example, a two-candidate demo, a cropped
symbol set, a partial pass, a local PNG, a screenshot from a test, or a
silent/offline replay **as the owner's visual review or as a preliminary
visual acceptance step**. No substitute "quick look first" workflow.
Focused technical/unit tests and local developer diagnostics may be used
only to implement and check code, **not** to ask the owner to inspect an
artifact or to declare visual acceptance. Do not commission extra test
campaigns in place of the owner's visual process.

**Mandatory instruction-construction guard:** before asking the owner or
Codex to visually check a Scanner change, the assistant/agent must read
this rule and ask for exactly one complete eligible-universe production-path
Scanner pass with **ordinary real Telegram notifications and all integrated
patterns enabled**; collect the completion count, per-interval/per-pattern
signal totals, delivery failures and the charts actually received in Telegram.
If the requested change has been merged but full-pass acceptance is pending,
**the next visual step is the full pass, never an isolated proof image/card**.
Do not describe a 302/777-style interrupted run or 5m-only subset as
complete. When the required 5m→1m per-symbol workflow has been implemented,
verify 5m then immediately 1m for each ticker; until then, report the
current implementation truth rather than claiming dual-timeframe coverage.

**Safety is not a substitute for acceptance:** before launching, establish
the real entrypoint/side effects, process and Telegram-poller ownership,
current Robot/position state, and fail-closed boundaries. A full Scanner
pass does not authorize Robot/PAPER/LIVE trading, order placement, unsafe
service restart or risk changes. If a safe full pass is blocked, report
the *specific blocker and leave visual acceptance pending*; do not replace
the full pass with a shorter run or request a manual single-card review.
This rule is permanent and supersedes any conflicting older milestone,
queue phrasing or assistant/Codex prompt unless the owner explicitly
changes it.

## Telegram-first visual development for every new Scanner pattern — OWNER RULE (2026-09-23)

**A newly developed pattern must reach the owner's ordinary Telegram signal
feed with its actual chart as part of its first Scanner integration.** The
owner visually tests formations **in Telegram**, not by inspecting hidden
local observer logs or `charts/` directories. Do not call a pattern integrated,
ready for owner acceptance or finished if it only prints local candidates,
saves local PNGs, or requires the owner to request notification wiring later.
When implementing a new pattern, include source-time detection → real Scanner
candidate → current shared Telegram presentation/photo and applicable
standard owner buttons → full-universe Scanner pass → owner visual feedback
in the same user-visible delivery milestone. Do not defer Telegram delivery
behind a separate silent-observer acceptance stage.

Local/offline/shadow runs are permitted **only for developer diagnosis and
focused regression**, never as a substitute for owner-visible Telegram
delivery or the mandated complete real Scanner pass. Deliver normal configured
notifications; do not unilaterally silence them or demand that the owner
search the filesystem for charts. Each emitted formation must have valid
owner-defined geometry at candidate construction; Telegram visibility is not
permission to distribute known malformed formations.

**Telegram visual signal != trading authorization.** Reuse the common chart/
caption/button layout; expose only actions that are supported and safe for
that pattern, never a nonfunctional Robot approval button. PAPER/LIVE order
placement, admission, risk and deployment require their separate approved
contracts. Before a real pass, check launcher side effects, duplicate workers
and current Robot/position safety; do not bypass fail-closed protection.

**Current milestone:** PR #204 integrated L-shape Telegram photos into
GitHub main. PR #205 simplified the Ikigai Box chart and Telegram card.
Their owner visual acceptance remains **pending until the single complete
real Scanner pass** specified above; do not offer either pattern or card
as an isolated owner visual sample. The 5m→1m per-symbol Scanner extension
is separately queued and not yet implemented.

## Permanent Scanner 5m → 1m per-symbol workflow — OWNER RULE (2026-09-23)

For **each eligible symbol**, the Scanner must process its **5-minute candles
first, then immediately its 1-minute candles**, before moving to the next
symbol. Run **every integrated Scanner pattern** on both intervals and deliver
each genuinely constructed formation in the ordinary Telegram signal feed
with its actual chart, clearly labeled `5м` or `1м`. A pattern must not be
silently excluded on 1m because its old path assumed 5m. Keep each
(symbol, timeframe, pattern, formation identity) independent in candidate
selection, closed-candle source-time anchors, signal memory, deduplication,
notifications and charts: a 1m result must not overwrite/suppress a 5m
result or vice versa. If one interval fails, record it and continue to the
other and the next symbol without fabricating a signal.

This is a **permanent desired Scanner behavior**, not a claim that the
current runtime already does it. Its implementation belongs **after the
ongoing Ikigai Box card simplification (including approximately 40% narrower
candlesticks) and before the queued geometry repairs**. Do not interrupt
that card task or start the full Scanner pass merely to document the rule.
After implementation, owner acceptance requires one full real eligible-symbol
Scanner pass showing the ordered 5m→1m coverage and Telegram charts for all
integrated patterns. Keep the existing 5m Robot/PAPER/LIVE admission, orders,
risk and protective state unchanged: 1m Scanner signals are observational
until trading behavior is separately approved.

## Current mandatory task sequence — OWNER UPDATE (2026-09-23)

The user's current execution order is **(1) L-shape Telegram integration
merged → (2) Ikigai Box card simplification and approximately 40% narrower
candles merged → (3) one complete real Scanner pass for owner visual review
of both integrations, with no isolated card preview → (4) implement
per-symbol 5m then 1m Scanner search and Telegram delivery for every
integrated pattern → (5) fix queued Scanner geometry errors** (APTUSDT, B3USDT, DASHUSDT, ATHUSDT; preserve B2USDT
as Box positive control). Follow
the top **"Binding owner execution order"** section of
`DOCUMENTS/BACKLOG.md` as the authoritative next-task index. Do **not**
advance geometry tasks ahead of Telegram integration or Box presentation by
reading generic priority labels or stale next-step statements elsewhere.
Correct candidate construction remains the mandatory end-state for all
patterns; this owner order governs **when** its work is resumed. Each changed
Scanner behavior still requires one complete real eligible-universe run for
the owner's Telegram visual acceptance. No automatic Robot/PAPER/LIVE
activation or risk changes.

## Active feedback queue and resumption

For the current owner-prioritized Scanner geometry → Box setup lifecycle →
PAPER execution → unified Telegram work, open the **first section** of
`DOCUMENTS/BACKLOG.md` ("ACTIVE owner-feedback action plan — 2026-09-23")
before selecting the next slice. It records APTUSDT/B3USDT false construction,
ATHUSDT Box impulse/completion and B2USDT positive control. **The immediate
user-visible blocker is L-shape Telegram delivery**: PR #197's local-only
observer is not the owner-accepted integration. Complete its ordinary
Telegram photo/caption/buttons path first, while keeping Robot execution
separately unauthorized.

## Geometry construction first — owner-defined search-system outcome (2026-09-23)

**Invalid geometry must never be constructed as a search candidate.** This is
the required end state for **every pattern**, not a notification/admission
filtering task. Search begins with the owner's pattern-specific structural
definition: identify the real local episode, directional impulse, chronologically
valid anchors and START, and all required legs/shelf using evidence available
at the original decision candle. Only **structurally valid formations** may
proceed to line fitting, ranking, quality scores, presentation, Telegram or
Robot. No valid construction means **no formation candidate** for that
episode, not a false candidate subsequently hidden by score, freshness,
delivery, or Robot filters.

For an observed false formation, trace the actual selected candidate backward
through generation, episode/anchor selection and geometry construction;
fix the **earliest causative stage** and the general pattern rule, not the
display, score threshold or signal-delivery gate. Never rescue an invalid
construction by moving START, fitting visually convenient boundaries,
enlarging the chart or adding downstream suppression. Preserve source-time
reproducibility; do not invent a universal rule from a single screenshot.
The owner reviews the output of a correctly constructed search system, not
a stream of malformed proposals requiring manual rejection.

Pattern rules stay distinct: Ikigai first-impulse candle-colour constraints
must be resolved in its owning strategy specification and enforced at its
first-leg construction stage, not copied to wedges, triangles or L-shapes.
A formation's historical market completion and a Robot trade's proven fill/
exit lifecycle are separate states; do not infer execution from a chart.

## Scanner visual acceptance: full passes only — owner rule (2026-09-23)

**Permanent, universal rule for ALL new Scanner patterns and ALL future
Scanner corrections** (detector, geometry, candidate selection, signal/chart
presentation and other scan-pass behavior): after implementation and focused
code verification, perform **one complete real Scanner pass across the entire
available eligible symbol universe** for the owner's visual/operational
acceptance. This applies even when a small offline sample or focused tests
already passed. Do not wait for the owner to reassert this rule per pattern,
bugfix or session. For the currently integrated L-shaped observer, enable its
opt-in observation/preview for the pass.

Use the normal Scanner flow, configured delivery, and actual production-path
chart generation; collect the resulting pattern charts and per-symbol
candidate/skip/error summary for owner review. **No truncated/sampled runs,
`MAX_SYMBOLS` caps, two-candidate demos, synthetic/offline-only replays, or
unilaterally notification-suppressed runs in place of full acceptance.**
Do not silently disable existing Telegram delivery to make the pass "quiet".
If no candidate is found, report zero honestly; do not invent one or claim
visual acceptance. If market-data access or safe execution blocks the full
pass, report the specific blocker and leave acceptance open, rather than
substituting a short run.

A full Scanner pass is **not** blanket authorization to enable Robot/LIVE
trading, place orders, change risk/strategy, deploy, change credentials or
override protective controls. Resolve the actual launcher dependency and
side-effect chain before running; preserve existing approval and fail-closed
boundaries. This rule governs **real Scanner acceptance**, not the scope of
unit/regression suites: keep focused development tests proportionate, and
avoid redundant full passes when neither implementation nor acceptance
evidence changed.

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