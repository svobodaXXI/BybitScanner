# BybitScanner — agent librarian / routing index

This file owns **routing only**, not duplicated safety, development, trading or
acceptance contracts. Load the **named sections** below when the task triggers
them; do not load entire documents by default. The original full guide remains
at `DOCUMENTS/AGENT_GUIDE_FULL.md`, authoritative for its applicable contracts.
Current owner instruction and actual repository/host evidence outrank dated
historical task snapshots; normative safety and approval contracts still apply.

**Coordination of existing BybitScanner chats (owner 2026-11-15):** read
[`DOCUMENTS/WORKSTREAM_COORDINATION.md`](DOCUMENTS/WORKSTREAM_COORDINATION.md)
and the relevant latest comments in [GitHub issue #1077](https://github.com/svobodaXXI/BybitScanner/issues/1077).
Until the owner finalizes the three-chat reorganization, the three existing
specialist chats finish **only their active bounded task**, record a handoff and
report READY_FOR_ARCHIVE or an exact blocker; do not start the proposed next
workstreams. This is routing, not a new approval or trading authority.

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
would grant Codex cursor/click/GUI automation. GitHub issue #1077 carries the
current coordination rule. No automatic retry of the blocked VPS preflight;
installed SHA and host readiness remain unproven. Independent merge,
deployment, STOP/START, admission, PAPER and LIVE safety gates remain in force.

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

## VPS access priority — single canonical SSH authority (owner updated 2026-11-18)

**FIRST READ for any VPS SSH, Windows PowerShell, VPN, Codex or VPS Manager access:** [canonical VPS connection register](DOCUMENTS/WINDOWS_PC_VPS_ACCESS_RECOVERY_20261108.md) (top section, **18.11.2026**). That document is the **only operative SSH route authority**; older sections 0/1 and other runbooks describe historical contexts, not a higher priority. Do not copy SSH commands, IPs, or a conflicting default into AGENTS or other docs.

**Critical verified recovery:** repeated `banner exchange timeout`/exit 255 did **not** mean SSH was permanently unavailable. Owner's main PC then authenticated as root with the documented standard PowerShell SSH invocation **without `-F none`**, and confirmed Happ/VPN was **ON**. Receipt: `SSH_OK`, expected VPS hostname, exit 0, followed by successful read-only Robot/Scanner/protection API calls. This supersedes the 17.11 assumption that VPN must be OFF for the old IP or that the new IP with `-F none` is always preferred. The exact VPN node and root cause remain unproven. Consult the register before any new retry; stop after failed evidence instead of broad alias/IP/key/VPN exploration.

**Documentation link graph:** AGENTS → [single SSH register](DOCUMENTS/WINDOWS_PC_VPS_ACCESS_RECOVERY_20261108.md) ↔ [VPS Manager interface/monolith guide](tools/WINDOWS_VPS_MANAGER.md). The register owns working Windows routes and incident chronology; the Manager guide owns GUI/CLI controls; [ASSISTANT_PROTOCOL](DOCUMENTS/ASSISTANT_PROTOCOL.md) owns operational authority. Source code or installed client behavior may differ from the successful manual PowerShell route; prove it before claiming equivalence.

Minimize owner time: GitHub evidence is not host access. If Windows host execution is unavailable, report the exact missing boundary, not another unproven SSH command. SSH_OK proves transport only, never deploy, STOP/START, PAPER/DB, admission, or LIVE authority; all fail-closed gates remain unchanged.

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

1. Identify the owner's actual outcome, intended GitHub ref or local worktree,
   and the immediate change/decision boundary.
2. Use the matching routes below; read only the indicated section(s) and
   owning task-specific specification. Reuse already-current evidence.
3. For each next action, follow the **Result-First** route in the table.
   The referenced contracts retain all approval and safety boundaries.

## Always-applicable routing

| When | Canonical destination (selective section read) |
| --- | --- |
| Strategic end-to-end execution / avoiding owner intervention | `DOCUMENTS/ASSISTANT_PROTOCOL.md` → `STRATEGIC EXECUTION / OWNER-TIME CONTRACT` (inside Result-First; no new workflow) |
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
| AI-first / vibe-coding owner outcome, reusable tests, optional high-risk review | `DOCUMENTS/ASSISTANT_PROTOCOL.md` → `AI-FIRST RESULT DELIVERY`; `DOCUMENTS/DEVELOPMENT_VALIDATION_LOOP_PLAN.md` → §14; priorities: current `DOCUMENTS/BACKLOG.md` and `DOCUMENTS/ROADMAP.md` → `AI_FIRST_RESULT_ROADMAP_20261102` |
| Repeated process friction | `.agents/references/workflow-improvement.md` → `Distill`, `Authority gate` |

## Trading, safety and product routes

| When | Canonical destination |
| --- | --- |
| Old PAPER exposure / missing STOP/TAKE during downtime / pre-run recovery | `DOCUMENTS/RUNTIME_KNOWN_FAILURE_FAST_PATH.md` → `Historical PAPER exposure → recovery → acceptance` |
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
