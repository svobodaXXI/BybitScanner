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
handoff. Update `QUEST_STATE.md` when the active quest, quest queue, XP, level
or achievements materially change. Do not create a ContextDump solely to carry
the game state between chats.

The stable ChatGPT instruction texts live in
`DOCUMENTS/CUSTOM_INSTRUCTIONS_BYBITSCANNER.md`. Global Custom Instructions
are a short conditional bootstrap applied account-wide; BybitScanner Project
Instructions carry the fuller project-specific contract and take precedence
inside the project. Neither UI layer stores current SHA/PR/XP/quest/runtime
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

Applies to ChatGPT, Codex, Claude Code, and delegated agents. Execute the smallest
complete, independently verifiable step toward the current user outcome; agree
on a concrete stopping condition before extending scope. Batch inseparable
edits and their required proof, but do not silently expand a focused task into
another investigation, refactor, feature, or test campaign.

Before each further read, experiment, test, or retry, identify the **new**
question/evidence it will resolve. Reuse a passing check for unchanged inputs:
never rerun the same test, full suite, historical sample, fetch, or status
inspection for reassurance or "sanity" alone. Recheck only if relevant code,
inputs, environment, prior result, mandatory verification boundary, or observed
failure has changed and state why the existing evidence no longer suffices.
Use the smallest relevant focused check first; do not invent tests for already
proven unchanged behavior. Existing required safety, contract, harness, build,
and real-runtime acceptance checks remain mandatory when applicable.

Do not loop through alternative thresholds, repeated reproductions, or new
research directions without new evidence. After two unsuccessful attempts at
the same hypothesis, stop that loop, record the narrowest known blocker and
the next specific missing evidence; escalate only when a distinct risk or
mandatory safety diagnosis justifies it. If roughly 10 minutes pass without a
verified intermediate result, stop expanding the work and give a short progress
report explaining the delay, what is proven, and the bounded next step.
A previously authorized long-running scan/build/CI job with a clear purpose
may continue without repeated polling, redundant tests, or interrupting
unrelated processes. Do not claim completion for an unfinished step.

### 3.2.1a PROMPT BUDGET / NO TEST LOOPS — OWNER RULE 2026-09-23

Every ChatGPT-to-Codex/Claude Code prompt MUST be a short, outcome-oriented,
bounded micro-slice: state the actual delta, existing evidence to reuse, the
smallest genuinely necessary verification, the stopping point and a concise
result to return. Do not include redundant task recaps, broad research,
multiple optional investigations, full-suite requests, repeated tests of
unchanged behavior, or instructions to keep iterating until a vaguely defined
"perfect" result. Do not append a generic battery of checks to every prompt.

Require the agent to run each necessary focused check **once after the relevant
change**, reuse already successful evidence, and rerun **only a failing check
after a targeted fix** or where a changed input invalidates its result.
No automatic test/fix/test/fix cycles, alternative-threshold tuning loops,
repeated source fetches, continuous polling or waiting for long jobs. If one
bounded attempt fails or evidence is unavailable, STOP, report the precise
blocker and smallest next decision; do not start another exploratory branch
without a separate reason. Existing mandatory safety/contract/final gates
remain in force, but prefer consuming their recorded results rather than
duplicating them with additional ad hoc runs. A code task ends promptly after
its scoped deliverable and required proof; no agent-supervised real Scanner
pass or owner visual preview outside the full-pass-only policy.

The assistant MUST check this rule when writing each subsequent delegated
prompt and remove any instruction that would accidentally trigger repetitive
work, excessive test campaigns or unbounded autonomous cycles. If a task
cannot safely complete with the minimum checks, state the concrete mandatory
exception rather than silently expanding the prompt.

### 3.2.2 DEFERRED: chat-independent task continuation (idea, NOT an active migration)

Problem: repeated new-chat handoffs have accumulated overlapping summaries, indexes,
sync procedures and re-reading. Future simplification, **only when the owner
returns to this task**: let the repository own a single concise current-task
checkpoint (goal, binding decision, verified state, next action, done criterion).
A new chat follows the existing `AGENTS.md` staged entry to that checkpoint,
reads only necessary code/evidence and continues; ordinary chat changes must
not trigger full Project Sync, ContextDump, document audit, repeat diagnostics,
or a user-authored handoff. Prefer reusing the existing task/state location
and replacing duplicate text with links; create no new subsystem or protocol.
Trial on one active task, retain required safety and local dirty-work checks,
and stop if the short entry is sufficient. **No implementation or workflow
migration is authorized by this note; the owner is working on other tasks now.**

---

