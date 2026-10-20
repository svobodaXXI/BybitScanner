# BybitScanner — agent librarian / routing index

This file owns **routing only**, not duplicated safety, development, trading or
acceptance contracts. Load the **named sections** below when the task triggers
them; do not load entire documents by default. The original full guide remains
at `DOCUMENTS/AGENT_GUIDE_FULL.md`, authoritative for its applicable contracts.
Current owner instruction and actual repository/host evidence outrank dated
historical task snapshots; normative safety and approval contracts still apply.

## Owner time and trust — mandatory at every new task

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

## Fast task entry

1. Identify the owner's actual outcome, intended GitHub ref or local worktree,
   and the immediate change/decision boundary.
2. Use the matching routes below; read only the indicated section(s) and
   owning task-specific specification. Reuse already-current evidence.
3. For each next action, follow the **Result-First** route in the table.
   The referenced contracts retain all approval and safety boundaries.

## Always-applicable routing

| When | Canonical destination (selective section read) |
| --- | --- |
| Choosing any next task, prompt or post-CI action | `DOCUMENTS/ASSISTANT_PROTOCOL.md` → `RESULT-FIRST NEXT-ACTION GATE`; `3.2.1 BOUNDED_SLICE_AND_NO_REPEAT_RULE` |
| Determining owner priority and current facts | `DOCUMENTS/ASSISTANT_PROTOCOL.md` → `1. ROLE AND AUTHORITY`; current owner task, target Git ref or host state; only relevant top of `DOCUMENTS/BACKLOG.md` / `DOCUMENTS/QUEST_STATE.md` |
| Any edit or handling existing user files | `DOCUMENTS/AGENT_GUIDE_FULL.md` → `Change safety`; `DOCUMENTS/ASSISTANT_PROTOCOL.md` → `4. LOCAL REALITY AND USER-OWNED WORK` |
| Reporting / responding / requesting owner action | `DOCUMENTS/ASSISTANT_PROTOCOL.md` → `2. COMMUNICATION AND USER ACTIONS`, then relevant `2.1`–`2.5` sections |

## Development and delivery routes

| When | Canonical destination |
| --- | --- |
| GitHub code/docs, branch, PR, review, integration | `DOCUMENTS/GITHUB_FIRST_WORKFLOW.md` → `Rule`, `Result-first hand-off`, `Review-fix continuity`, `Evidence routing`; for merge `DOCUMENTS/ASSISTANT_PROTOCOL.md` → `GitHub PR merge via ChatGPT` |
| Local/Codex edit, protected task, checkpoint or receipt | `DOCUMENTS/AGENT_GUIDE_FULL.md` → `Repository edits`, `Verification and publication`; `DOCUMENTS/ASSISTANT_PROTOCOL.md` → `7.2 SCOPED_VERIFICATION_AND_CHECKPOINT_RULE` |
| Tool/harness failure or redundant checks | `DOCUMENTS/ASSISTANT_PROTOCOL.md` → `No harness recovery spiral`, `3.2.1a PROMPT BUDGET / NO TEST LOOPS`, `7.3 WORKFLOW_PROPORTIONALITY` |
| Material architecture/governance/contract change | Applicable `DOCUMENTS/PROJECT_CONTRACTS.md`, `DOCUMENTS/PROJECT_RULES.md`, `DOCUMENTS/WORKFLOW_RULES.md`; `DOCUMENTS/AGENT_GUIDE_FULL.md` → `Trading / durable scope` where applicable |
| Repeated process friction | `.agents/references/workflow-improvement.md` → `Distill`, `Authority gate` |

## Trading, safety and product routes

| When | Canonical destination |
| --- | --- |
| Scanner/Robot/PAPER_AUTO, position, protection, LIVE or financial risk | `DOCUMENTS/ASSISTANT_PROTOCOL.md` → `Scanner runtime is owner-manual`, `2.2.3 OPERATIONAL ENTRYPOINT TRACE`, `2.2.4 MULTI-COMPONENT READINESS CLAIM GATE`; `DOCUMENTS/AGENT_GUIDE_FULL.md` → `Trading / durable scope`, `Scanner runtime ownership` |
| Runtime shortcuts, start/stop ownership | `DOCUMENTS/ASSISTANT_PROTOCOL.md` → `Owner desktop launch surface`; `DOCUMENTS/AGENT_GUIDE_FULL.md` → `Owner desktop launch surface` |
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
