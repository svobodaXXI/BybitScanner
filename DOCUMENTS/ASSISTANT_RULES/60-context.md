# 3. SESSION BOOTSTRAP AND CONTEXT

## 3.1 AUTO_SESSION_BOOTSTRAP_RULE

On the first BybitScanner task in every new ChatGPT chat, the assistant automatically loads root `AGENTS.md` and
performs task-scoped staged recovery. The user must not be asked to remind the assistant to read project documents
or manually paste a bootstrap/handoff when authoritative state can be recovered from the repository.

Recovery contract:

Follow `AGENTS.md` staged recovery, short-intent entry and applicability-driven skill routing. Codex discovers
scope, owning references and necessary checks from the intended outcome and current checkout; the user is not
responsible for supplying them. Reuse fresh authority already loaded and reload only changed or uncertain scope.
Do not perform full/deep recovery, broad snapshots or Project Sync without the conditions defined by `AGENTS.md`.

Current project priority, phase, pipeline health, and implementation state never belong in this protocol. Their
authority is `PROJECT_STATE.md` and the applicable active Task/ChangeRequest.

For BybitScanner chats, session bootstrap also loads the compact Russian game
projection in `DOCUMENTS/QUEST_STATE.md` after the normal task-scoped authority
is known. `QUEST_STATE.md` must be checked against the owner's current message
and the current priority index in `DOCUMENTS/BACKLOG.md`; it cannot override
either. The assistant then continues in the Russian quest mode defined by
`DOCUMENTS/GTD_QUEST_SYSTEM.md` without asking the user to manually transfer a
handoff. While GAME_MODE is ACTIVE, keep the game layer visible in project replies; restore it from QUEST_STATE if needed. Update `QUEST_STATE.md` when the active quest, quest queue, XP, level
or achievements materially change. Do not create a ContextDump solely to carry
the game state between chats.

The stable ChatGPT instruction texts live in
`DOCUMENTS/CUSTOM_INSTRUCTIONS_BYBITSCANNER.md`. Global Custom Instructions
are a short conditional bootstrap applied account-wide; BybitScanner Project
Instructions route project-specific work to the current repository contracts and take precedence over global UI instructions
inside the project, without replacing mandatory repository safety and approval rules. Neither UI layer stores current SHA/PR/XP/quest/runtime
state; repository authority does. During an existing chat, perform a bounded context refresh when
the owner explicitly asks for it, returns to BybitScanner after a meaningful
interruption, repo state materially changed for the active task, or chat memory
conflicts with repository authority. Default refresh footprint:
`QUEST_STATE.md` + current BACKLOG priority section + the active quest's owning
spec; expand to staged/deep recovery only when the normal triggers below
justify it.

## 3.2 CONTEXT_AND_LIMIT_ECONOMY_RULE

Use the smallest reliable context footprint:

- do not repeat unchanged files, established history, known requirements, successful checks, or already-loaded authority;
- every read, search, status, diff, and test must have a concrete current-task necessity; do not repeat one when its
  relevant state has not changed;
- locate headings, symbols and owning references before reading; use targeted searches and scoped status/diffs instead of broad output;
- do not explore alternative architectures when the current solution remains authoritative and no new evidence
  invalidates it;
- on an unexpected blocker, localize the smallest failure boundary first; broad audit or research is escalation,
  not the default;
- report remaining-context estimates only on request or when loss of context is a real risk;
- batch compatible tasks and related decisions when scope, risk, approval, validation, and governance allow it;
- split work only for a concrete dependency, risk, approval/checkpoint, validation, safety, or governance reason.

For an actual recovery-footprint comparison, reuse `tools.project_sync.governance.context_budget`; do not recreate
its deterministic extraction or duplication measurement in prose or run it routinely.

Optimize for useful result per Codex limit consumed. Economy never weakens correctness, safety, fail-closed
behavior, contract checks, mandatory E2E, verification, or governance.

### 3.2.1 BOUNDED_SLICE_AND_NO_REPEAT_RULE — HARD RULE

Applies to ChatGPT, Codex, Claude Code, and delegated agents. Execute the smallest complete authorized workflow that achieves the current user outcome.
Internal slices and milestones are not owner handoffs: continue through dependent steps
under `11-result-first.md` until the outcome is proven or a genuine blocking dependency,
mandatory gate or owner-only decision is reached. Do not expand the authorized scope.

Apply §3.2 to every read, experiment, test or retry. Recheck only if relevant
code, inputs, environment, prior result, mandatory verification boundary or
observed failure changed; identify why existing evidence no longer suffices.
Use the smallest relevant focused check first. Do not invent tests for proven
unchanged behavior. Required safety, contract, harness, build and real-runtime
acceptance checks remain mandatory.

Do not loop through alternative thresholds, repeated reproductions, or new
research directions without new evidence. After two unsuccessful attempts at
the same hypothesis, stop that loop, record the narrowest known blocker and
the next specific missing evidence; escalate only when a distinct risk or
mandatory safety diagnosis justifies it. If roughly 10 minutes pass without a
verified intermediate result, stop expanding the investigation and report the
proven state and bounded next step. Continue an available authorized path without
requiring another owner prompt; pause only at the actual blocking boundary.
A previously authorized long-running scan/build/CI job with a clear purpose
may continue without repeated polling, redundant tests, or interrupting
unrelated processes. Do not claim completion for an unfinished step.

### 3.2.1a PROMPT BUDGET / NO TEST LOOPS — OWNER RULE 2026-09-23

Every ChatGPT-to-Codex/Claude Code prompt MUST be a short, outcome-oriented,
bounded end-to-end assignment: state the desired outcome, actual delta, relevant
existing evidence, minimum necessary verification and genuine stopping boundary. Do not include redundant task recaps, broad research,
multiple optional investigations, full-suite requests, repeated tests of
unchanged behavior, or instructions to keep iterating until a vaguely defined
"perfect" result. Do not append a generic battery of checks to every prompt.

Apply §3.2.1: run each necessary focused check once after the relevant change;
rerun only a failing check after a targeted fix or a check invalidated by changed inputs. On a failed ordinary check, correct the proven
cause within scope and repeat only the invalidated check. For mandatory gate
failures, unknown material risk or unavailable evidence, use the applicable
STOP/HOLD/CONTINUE policy in `11-result-first.md`; preserve stricter harness
recovery limits and every approval boundary. Do not start another exploratory
branch without new evidence. Existing mandatory safety/contract/final gates
remain in force, but prefer consuming their recorded results rather than
duplicating them with additional ad hoc runs. A code task ends promptly after
its scoped deliverable and required proof; no agent-supervised real Scanner
pass or owner visual preview outside the full-pass-only policy.

Apply this rule to every delegated prompt. If more than minimum checks are
required for safety, state the concrete mandatory exception.

### 3.2.2 Chat-independent task continuation

A workstream, not a particular chat or chat title, owns its active task. For
continuation, use the active workstream routing in
`DOCUMENTS/WORKSTREAM_COORDINATION.md`. Resolve the direction from the current
owner task and available conversation context; use the relevant workstream
checkpoint, not the newest unrelated entry in QUEST_STATE or #1077. Verify
changed or uncertain PR/issue/host facts against their actual authority.
An ambiguous bare continuation in a new chat with no recoverable direction
requires only the direction name, never a manually reconstructed handoff.

Persist material task transitions in the existing owning issue/PR or task
record, with the goal, binding decisions, verified state/evidence, blocker if
any, next action and done criterion. QUEST_STATE is a compact quest projection
and BACKLOG owns priorities; link to the existing checkpoint rather than copy
its detail. The shared #1077 journal is only for material cross-workstream
coordination. Ordinary same-direction chat replacement needs no HANDOFF or
HANDOFF_ACCEPTED ceremony. Follow the existing safety, acceptance, dirty-work
and approval boundaries; no full Project Sync or ContextDump just for a new chat.

---

