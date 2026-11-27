# BybitScanner — agent librarian / routing index

This file owns **routing only**, not duplicated safety, development, trading or
acceptance contracts. Read the core and the task-matched packages below, not the
full generated `DOCUMENTS/ASSISTANT_PROTOCOL.md` by default. The original full
guide remains at `DOCUMENTS/AGENT_GUIDE_FULL.md` for its applicable contracts.
Current owner instruction and actual repository/host evidence outrank dated
historical task snapshots; normative safety and approval contracts still apply.
Resolve the intended working ref from the current task and live coordination;
a stale default branch is not evidence that the current work is absent.

**Coordination:** use the current task, [workstream routing](DOCUMENTS/WORKSTREAM_COORDINATION.md)
and only the relevant latest decisions in [#1077](https://github.com/svobodaXXI/BybitScanner/issues/1077).
Preserve each direction's ownership. Historical reorganization instructions are
not a reason to stop an otherwise authorized current task.

## Owner directive — human acceptance and Codex GUI boundary (2026-11-16)

**Owner-only real-world acceptance.** The owner personally performs and confirms
local UI, Simulator, PAPER and VPS acceptance. CI, automated tests and technical
receipts may establish engineering evidence, not substitute for owner acceptance.
Do not claim `ACCEPTED` without the owner's explicit confirmation.

**Never delegate interactive desktop control to Codex.** Do not give Codex the
owner's mouse pointer, clicks, GUI buttons, keyboard entry into windows, or
remote-control access to their PC/laptop desktop. This restriction does **not**
ban Codex command-line/terminal work: exceptional owner-directed tasks and
approved VPS synchronization may still use existing authorized terminal routes,
subject to scope, secrets, Git protections, and host/trading approval gates.
Do not equate terminal-based SSH or a checked-out repository with permission to
control the graphical desktop. Actual UI acceptance remains the owner's task.

This clarification supersedes the earlier overly broad statement that Codex
had no computer access at all; it also supersedes any older instructions that
would grant Codex cursor/click/GUI automation. GitHub issue #1077 carries the current coordination rule. Establish actual host
readiness only when the current task needs it. Independent merge, deployment,
STOP/START, admission, PAPER and LIVE safety gates remain in force.

## Owner time and trust — mandatory at every new task

Maximize saved owner time within safety and authorization boundaries. The fixed
priority is owned by [core](DOCUMENTS/ASSISTANT_RULES/00-core.md); execution and
stopping decisions are owned by [Result-first](DOCUMENTS/ASSISTANT_RULES/11-result-first.md).

## VPS access priority — single canonical SSH authority

For VPS SSH, VPN, PowerShell, or VPS Manager access, **first use the current
applicable device section** of the [canonical connection register](DOCUMENTS/WINDOWS_PC_VPS_ACCESS_RECOVERY_20261108.md).
Use the latest verified route and existing manager/monolith surface; do not
rediscover addresses, keys or commands from history or repeat equivalent probes.
The [VPS Manager guide](tools/WINDOWS_VPS_MANAGER.md) owns its interface;
[operational checks](DOCUMENTS/ASSISTANT_RULES/40-operational-checks.md) own the
applicable evidence. GitHub evidence is not host access; SSH_OK is transport only,
not deploy, STOP/START, admission or trading authority.

**Select the execution surface before delegation:** follow [Development §7.0](DOCUMENTS/ASSISTANT_RULES/80-development.md#70-execution-surface-routing--direct-command-first--owner-rule-2026-11-27). Prefer deterministic direct PowerShell to routine Codex VPS work; all existing authority gates remain binding.

## Outcome-owned delegation — proven lesson (2026-10-28)

Use [Result-first](DOCUMENTS/ASSISTANT_RULES/11-result-first.md) for one bounded
end-to-end assignment, evidence reuse, alternate authorized routes and the actual
stopping boundary. Do not create serial owner handoffs.

## Fast task entry

1. Identify the owner's observable outcome, intended repository ref or local
   worktree, and actual scope. Read [core](DOCUMENTS/ASSISTANT_RULES/00-core.md).
2. For a new ChatGPT project chat or an open-ended workstream continuation, resolve the workstream using the current task and [workstream routing](DOCUMENTS/WORKSTREAM_COORDINATION.md).
   Recover its relevant `QUEST_STATE.md` entry, `BACKLOG.md` priority and owning
   issue/PR/spec checkpoint via [Context §3.2.2](DOCUMENTS/ASSISTANT_RULES/60-context.md#322-chat-independent-task-continuation).
   Reconcile with the latest owner command; continue in Russian GTD mode. No manual handoff.
3. Choose applicable routes below. Follow conditional links inside the owning
   rules as facts change; these are knowledge routes, not extra workflow stages.
   Keep loaded authority and evidence for the same task. Do not follow unrelated
   links or revisit an unchanged step. Applicable safety and approval gates
   remain binding regardless of route.
4. Finish the full authorized goal with proportionate evidence and minimal
   owner interventions; ask only at an actual required boundary.

## Cross-cutting routes — load only when applicable

| When | Canonical destination |
| --- | --- |
| Authority, scope, safety and current facts | [Core](DOCUMENTS/ASSISTANT_RULES/00-core.md); current owner task and actual target ref/host |
| End-to-end delivery, choosing the next action, owner time | [Result-first](DOCUMENTS/ASSISTANT_RULES/11-result-first.md) — relevant section |
| Session bootstrap, compact context, prompt budget | [Context](DOCUMENTS/ASSISTANT_RULES/60-context.md); current BACKLOG/QUEST_STATE, owning spec |
| Required user action or copy-ready command | [User actions](DOCUMENTS/ASSISTANT_RULES/30-user-actions.md); [communication](DOCUMENTS/ASSISTANT_RULES/50-communication.md) when applicable |
| Chat coordination, handoff, current ownership | `DOCUMENTS/WORKSTREAM_COORDINATION.md` + relevant #1077 decisions; [workspace/continuation](DOCUMENTS/ASSISTANT_RULES/70-workspace-continuation.md) |
| Russian GTD and verified rewards | `DOCUMENTS/GTD_QUEST_SYSTEM.md`, `DOCUMENTS/QUEST_STATE.md`, `DOCUMENTS/QUEST_REWARD_LEDGER.md` |

## Development and delivery routes

| When | Canonical destination |
| --- | --- |
| GitHub branches, PR, CI, merge | `DOCUMENTS/GITHUB_FIRST_WORKFLOW.md`; [harness/publication](DOCUMENTS/ASSISTANT_RULES/10-harness-and-publication.md) |
| Codex quota economy, authorized local-only checks or VPS synchronization | [Context §§3.2–3.2.1a](DOCUMENTS/ASSISTANT_RULES/60-context.md#32-context_and_limit_economy_rule); [workspace/continuation](DOCUMENTS/ASSISTANT_RULES/70-workspace-continuation.md) for sync; VPS register and operational checks only for host tasks |
| Local/Codex edits, dirty work, sync/handoff | [Workspace/continuation](DOCUMENTS/ASSISTANT_RULES/70-workspace-continuation.md); `DOCUMENTS/AGENT_GUIDE_FULL.md` → Change safety / Repository edits |
| Implementation, test selection, build, checkpoint | [Development](DOCUMENTS/ASSISTANT_RULES/80-development.md); task-specific code/spec |
| Architecture, structure, development contract | `DOCUMENTS/ARCHITECTURE.md`, `DOCUMENTS/PROJECT_TREE.md`, applicable `DOCUMENTS/PROJECT_CONTRACTS.md` / `DOCUMENTS/PROJECT_RULES.md`; `DOCUMENTS/WORKFLOW_RULES.md` only for its owning workflow |
| Substantial/risky change | Owning approved ChangeRequest; `.agents/skills/change-review/SKILL.md` when applicable |
| Recurring/unknown defect, workflow improvement | [Maintenance](DOCUMENTS/ASSISTANT_RULES/90-maintenance.md); applicable skill or `.agents/references/workflow-improvement.md` |
| Operational start/stop, release, SSH, runtime readiness | [Operational checks](DOCUMENTS/ASSISTANT_RULES/40-operational-checks.md); [runtime ownership](DOCUMENTS/ASSISTANT_RULES/20-runtime-ownership.md); VPS register/Manager for host access |
| New strategy / research / external reference | [Maintenance](DOCUMENTS/ASSISTANT_RULES/90-maintenance.md) §§8.9–8.10; strategy owning spec; `DOCUMENTS/EXTERNAL_REFERENCE_REUSE_POLICY.md` when applicable |

`DOCUMENTS/ASSISTANT_PROTOCOL.md` is a generated compatibility projection of
the numbered packages. Maintain the owning package, not two copies of a rule.

### Codex — task-scoped economy route

Use GitHub-native evidence and implementation first. Apply `80-development.md`
§7.0 before delegation: direct commands for deterministic host work; Codex only
when explicitly selected or a genuine authorized host/local dependency requires
it and outweighs delegation overhead. After the mandatory core, load
only the applicable route above and the owning task references. A concrete
local assignment with sufficient authority and evidence does not require a
project-wide chat bootstrap or unrelated quest-history reads. Reuse current
Git/CI/host evidence when it actually proves the claim. A read-only local check
needs no edit transaction. For authorized local edits use the existing `task
start` / `task finish` facade in `DOCUMENTS/AGENT_GUIDE_FULL.md` → Repository
edits; do not repeat its successful sync, context, governance or final checks.
Return the bounded result and stop at the applicable outcome or real blocker;
no repeated polling, broad recovery or agent-supervised Scanner pass. Use the
existing `context_budget` tool only when measuring recovery footprint, not as
a routine gate. This route changes no delegation, host, trading, merge or
acceptance authority.

## Trading, safety and product routes

| When | Canonical destination |
| --- | --- |
| Old PAPER exposure / missing STOP/TAKE during downtime / pre-run recovery | `DOCUMENTS/RUNTIME_KNOWN_FAILURE_FAST_PATH.md` → `Historical PAPER exposure → recovery → acceptance` |
| Scanner/Robot/PAPER_AUTO, position, protection, LIVE or financial risk | `DOCUMENTS/ASSISTANT_RULES/20-runtime-ownership.md` → Scanner runtime; `DOCUMENTS/ASSISTANT_RULES/40-operational-checks.md` → §§2.2.3–2.2.4; `DOCUMENTS/AGENT_GUIDE_FULL.md` → `Trading / durable scope`, `Scanner runtime ownership` |
| Runtime shortcuts, start/stop ownership | `DOCUMENTS/ASSISTANT_RULES/20-runtime-ownership.md` → Owner desktop launch surface; `DOCUMENTS/AGENT_GUIDE_FULL.md` → `Owner desktop launch surface` |
| PAPER robot lifecycle, shared candidate/admission, Telegram Robot UX | `DOCUMENTS/PATTERN_ROBOT_INTEGRATION_STANDARD.md`; for Box `DOCUMENTS/IKIGAI_BOX_STRATEGY_SPEC.md`; for Autopilot `DOCUMENTS/ROBOT_AUTOPILOT_IMPLEMENTATION_PLAN.md` |
| Scanner acceptance, complete universe, Telegram delivery, 5m→1m | `DOCUMENTS/AGENT_GUIDE_FULL.md` → `Exclusive visual acceptance workflow`, `Permanent Scanner 5m → 1m per-symbol workflow`, `Observable acceptance and incremental evidence` |

## Active Scanner geometry course

For Wedge, Triangle Compression, L-shape or channel geometry, start with
`DOCUMENTS/SCANNER_GEOMETRY_CURRENT_COURSE.md` → the relevant pattern heading
and follow its owning spec. This heading also retains existing links to
`AGENTS.md#active-scanner-geometry-course`.

## Skills — on-demand only

| Trigger | Skill |
| --- | --- |
| Unknown-cause material defect | `.agents/skills/systematic-debugging/SKILL.md` |
| Material/high-risk change review | `.agents/skills/change-review/SKILL.md` |
| New strategy/trading hypothesis (research only) | `.agents/skills/strategy-hypothesis-capture/SKILL.md` |

Other applicable skills or legacy contracts: use the **relevant heading only**
in `DOCUMENTS/AGENT_GUIDE_FULL.md` → `Skills`, `Authority routing`, or the
owning Task/Spec. Do not promote an archived `CURRENT` heading to a new goal.
