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

**Overarching owner priority (reconfirmed 2026-11-04): maximize saved owner time**, including the shortest safe, efficient, autonomous development workflow. Technical BACKLOG P0 describes the current engineering task, **not** the project's overriding priority. Prefer end-to-end delivery with minimal owner interventions, approvals only at required boundaries, and observed outcomes over process/PR churn. This priority is **fixed across quests, backlogs, releases, and chats**: do not rename, replace, demote, or reinterpret it because the current technical P0 changes. Only a new **explicit owner instruction specifically changing this overarching priority** may revise it; ordinary task requests, planning, documents, and automation cannot. All trading/runtime safety gates and owner approvals remain binding.

**Owner escalation (2026-10-20):** Repeated decomposition of one end-to-end
PAPER goal into serial investigations, repeated prompts, and avoidable owner
approvals caused substantial lost time and damaged trust. The owner explicitly
warned that continuing this behavior may lead them to stop using ChatGPT.
Treat this as a concrete cost of non-delivery, not as a request for more
process documentation.

**Operational rule:** Start with the owner's measurable end result; delegate
or complete the whole authorized bounded workflow in one pass, including
necessary inspection, minimal fix, targeted proof and the next operational
handoff. Reuse existing findings; do not create new diagnostic quests or ask
the owner to shuttle intermediate reports. Escalate only a genuinely required
owner-only runtime/merge/trading authorization or proven critical safety
blocker, explaining the single needed decision. Never suppress safety gates,
assume authorization, or claim success without observed evidence. After the
blocker is resolved, return directly to the original end result.

## VPS access priority — single canonical SSH authority

For VPS SSH, VPN, PowerShell, or VPS Manager access, **first use the current
applicable device section** of the [canonical connection register](DOCUMENTS/WINDOWS_PC_VPS_ACCESS_RECOVERY_20261108.md).
Use the latest verified route and existing manager/monolith surface; do not
rediscover addresses, keys or commands from history or repeat equivalent probes.
The [VPS Manager guide](tools/WINDOWS_VPS_MANAGER.md) owns its interface;
[operational checks](DOCUMENTS/ASSISTANT_RULES/40-operational-checks.md) own the
applicable evidence. GitHub evidence is not host access; SSH_OK is transport only,
not deploy, STOP/START, admission or trading authority.

## Outcome-owned delegation — proven lesson (2026-10-28)

**One goal → one end-to-end assignment → observable acceptance.** Do not turn a
single owner outcome into serial prompts for logs, key searches, terminal tests,
preparatory reports or other subgoals. Give the executor the **end state, allowed
scope, non-negotiable invariants, minimal proof and STOP/escalation boundary**;
leave the choice of ordinary technical steps and tools to that executor.

**Change method, not goal:** If one terminal, tool or environment is demonstrably
blocking progress, use a different authorized route before asking the owner to
repeat the same input. Reuse prior PASS evidence and GitHub history first.
Diagnostic actions are subordinate to delivery, time-boxed by their decision
value, and cannot be reported as completion. Repeated diagnostics with no new
information are a workflow failure, not progress.

**Acceptance is real-world evidence:** Confirm the target operation actually
works in the intended environment (e.g. authenticated SSH exit 0 or observed UI
state), not merely that a command, file, test, PR or tool invocation exists.
When a protected action needs owner consent, ask for the **single required
approval at its boundary**, then resume the same goal. Keep all existing
trading, runtime, Git/harness and secret-protection contracts intact.

## Fast task entry

1. Identify the owner's observable outcome, intended repository ref or local
   worktree, and actual scope. Read [core](DOCUMENTS/ASSISTANT_RULES/00-core.md).
2. For a new chat, recover the relevant top of `DOCUMENTS/QUEST_STATE.md`,
   the current priority in `DOCUMENTS/BACKLOG.md`, and only the owning task/spec.
   Reconcile with the latest owner command and use the Russian GTD game mode;
   see `DOCUMENTS/GTD_QUEST_SYSTEM.md` only where needed. No manual game handoff.
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
| Local/Codex edits, dirty work, sync/handoff | [Workspace/continuation](DOCUMENTS/ASSISTANT_RULES/70-workspace-continuation.md); `DOCUMENTS/AGENT_GUIDE_FULL.md` → Change safety / Repository edits |
| Implementation, test selection, build, checkpoint | [Development](DOCUMENTS/ASSISTANT_RULES/80-development.md); task-specific code/spec |
| Architecture, structure, development contract | `DOCUMENTS/ARCHITECTURE.md`, `DOCUMENTS/PROJECT_TREE.md`, applicable `DOCUMENTS/PROJECT_CONTRACTS.md` / `DOCUMENTS/PROJECT_RULES.md`; `DOCUMENTS/WORKFLOW_RULES.md` only for its owning workflow |
| Substantial/risky change | Owning approved ChangeRequest; `.agents/skills/change-review/SKILL.md` when applicable |
| Recurring/unknown defect, workflow improvement | [Maintenance](DOCUMENTS/ASSISTANT_RULES/90-maintenance.md); applicable skill or `.agents/references/workflow-improvement.md` |
| Operational start/stop, release, SSH, runtime readiness | [Operational checks](DOCUMENTS/ASSISTANT_RULES/40-operational-checks.md); [runtime ownership](DOCUMENTS/ASSISTANT_RULES/20-runtime-ownership.md); VPS register/Manager for host access |
| New strategy / research / external reference | [Maintenance](DOCUMENTS/ASSISTANT_RULES/90-maintenance.md) §§8.9–8.10; strategy owning spec; `DOCUMENTS/EXTERNAL_REFERENCE_REUSE_POLICY.md` when applicable |

`DOCUMENTS/ASSISTANT_PROTOCOL.md` is a generated compatibility projection of
the numbered packages. Maintain the owning package, not two copies of a rule.

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
