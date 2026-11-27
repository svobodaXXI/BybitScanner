# 8. WORKFLOW RULE MAINTENANCE

Consult `.agents/references/workflow-improvement.md` only for an explicit process audit, evidenced recurring
friction, or a high-severity incident warranting prevention. Do not load it on ordinary tasks or turn routine
completion into process-improvement work. Proposed permanent changes remain review-required; the checklist does
not authorize implementation. Existing correction and rule-recording obligations below remain binding.

## 8.1 IMMEDIATE_WORKFLOW_RULE_RECORDING

When the user and assistant explicitly approve a permanent workflow rule, record it in the owning authoritative
document at the current or nearest safe checkpoint before resuming the main mission. Do not defer it with “later”.
If immediate interruption is unsafe, reach the nearest safe checkpoint first.

## 8.2 USER_CORRECTION_PROTOCOL_HARDENING_RULE

When the user identifies a protocol violation or recurring failure class, do not stop at apology or an informal
promise. Determine whether the canonical rule is missing, weak/ambiguous, or explicit but operationally easy to
miss. Then perform the applicable chain:

```text
USER CORRECTION
→ RULE-GAP / ENFORCEMENT ANALYSIS
→ CANONICAL PROTOCOL HARDENING
→ PERSISTED DOCUMENTATION FIX
```

Harden the whole failure class, preserve stronger higher-level rules, check for overlap/contradiction, and apply
`IMMEDIATE_WORKFLOW_RULE_RECORDING` when authorized.

## 8.3 SYSTEMIC REGRESSION ESCALATION — WHOLE-SYSTEM + EXTERNAL REFERENCE BEFORE PATCH

When development begins to regress in an unexplained way, stop treating symptoms independently. Re-evaluate the
affected behavior as part of the whole system, compare it with the project's intended architecture and proven
external implementations, establish the real failure boundary, then design the correction before writing another
patch.

This hard rule triggers for an unexplained, recurring, cross-boundary, architectural, or real-runtime regression,
including a previously working capability disappearing, neighboring behavior breaking, projections diverging,
tests passing while a real device/runtime fails, repeated local fixes failing to stabilize the system, or an
unexpected reliability, lifecycle, transport, authority, or synchronization failure. On trigger, the assistant
must stop the local patch loop and follow:

```text
UNEXPLAINED REGRESSION
→ STOP LOCAL PATCH LOOP
→ RECOVER ACTUAL PROJECT STATE
→ ANALYZE SYSTEM END-TO-END
→ CHECK EXISTING ARCHITECTURE / ROADMAP / INVARIANTS
→ RESEARCH EXTERNAL PROVEN IMPLEMENTATIONS
→ COMPARE PATTERNS AND FAILURE MODES
→ IDENTIFY ROOT CAUSE / FAILURE BOUNDARY
→ DESIGN CORRECT TARGET ARCHITECTURE
→ PLAN BOUNDED MIGRATION / CORRECTION
→ ONLY THEN IMPLEMENT
```

Before redesign or another patch, inspect the feature in its system context where relevant: source of truth,
ownership, lifecycle and state transitions, concurrency, transport, caches/projections, frontend/backend boundary,
persistence, reconnect/recovery, sequencing/generation/revision, failure states, contracts/invariants, and neighboring
subsystems. The latest visible symptom is not presumed to be the root cause.

Recover the applicable Task/ChangeRequest, roadmap, architecture decisions, prior research, invariants, and last
accepted implementation intent. Detect drift from an already-correct decision; do not preserve current code merely
because it exists. Then consult external evidence before selecting the target correction, preferring official
protocol/API/library documentation, mature open-source implementations, authoritative engineering design material,
and relevant issue/PR history. Extract ownership, lifecycle, and failure-handling patterns rather than cargo-culting
code.

The analysis must explicitly compare:

```text
CURRENT IMPLEMENTATION
vs
EXISTING PROJECT INTENT
vs
EXTERNAL PROVEN PATTERNS
```

Identify what remains correct, what is only a symptom, the wrong boundary, whether the failure is local or systemic,
and the minimum architectural correction that removes the failure class. Prefer correcting one broken
lifecycle/transport/authority model over adding symbol-, stream-, race-, timeout-, or retry-specific patches.

Whole-system analysis does not authorize guessing. When evidence is incomplete, diagnose first, collect objective
runtime evidence, separate upstream/backend/transport/frontend/state failures, and establish the narrowest proven
failure boundary. External research informs diagnosis and design; it does not replace project evidence.

Implementation authorization remains separate. Before implementation, present the proven root cause or narrowest
boundary, relevant external patterns, target architecture, valid existing behavior to preserve, bounded migration,
risks, and verification strategy; then follow the normal authorization lifecycle. Verification should exercise the
failure class where practical, including rapid transitions, stale state, reconnect, partial failure, unsupported
input, slow dependencies, process/network interruption, ordering/generation mismatch, previous-state preservation,
and fail-closed behavior—not only the first observed example.

This escalation is not required for a trivial deterministic defect with a proven local cause. It applies across
BybitScanner, Trading Workspace, Scanner, future Robot, Android terminal, and relevant infrastructure/tooling, and
never weakens fail-closed safety, correctness, governance, verification, or protection of user-owned work.

## 8.4 CHATGPT PROJECT INSTRUCTIONS GUARDRAIL SYNC NOTE

ChatGPT Project Instructions are manually maintained outside the repository and are not project authority.
If maintained, use a compact bootstrap pointer to `AGENTS.md` and this protocol, plus the short-intent entry model.
Do not mirror workflow checklists into every task prompt. The canonical communication, safety and governance rules
remain in the repository and must be loaded before project-specific user actions.


## 8.5 REPOSITORY AUTHORITY OVER MEMORY — HARD RULE

Assistant memory, chat context, summaries, handoffs, and remembered preferences are accelerators only. They are never
normative authority for project workflow rules when the repository authority is available.

For BybitScanner work, the assistant must recover applicable workflow rules from `AGENTS.md` and
`DOCUMENTS/ASSISTANT_PROTOCOL.md` before issuing project-specific user actions. A remembered rule may reduce search
cost, but it must not substitute for loading the current canonical text when enforcement matters.

Read accessible authority directly; section 8.7 owns the no-user-as-file-transport rule.

A failure to obey an already-explicit canonical rule is an `ENFORCEMENT FAILURE`, not a rule-definition gap. Do not
respond by duplicating the same rule in more documents. Instead, identify why bootstrap/preflight/enforcement failed
and strengthen the smallest existing mechanism that can prevent recurrence.

## 8.6 TECHNICAL GUARDRAIL OVER REMINDER — HARD RULE

Critical workflow rules should be technically enforced where practical. Documentation remains authoritative, but a
deterministic guard should prevent or fail closed on a known high-cost failure class whenever the environment or
project tooling can do so cheaply.

Examples include:
- non-interactive Git output for commands that may page;
- exact-path staging and receipt-bound checkpoints;
- preflight anchor/version checks before mechanical documentation rewrites;
- refusal to overwrite files when expected authority/version anchors do not match;
- scoped verification before commit/push.

The assistant must prefer `rule + technical guard` over `rule + repeated reminder` when the guard is simple,
deterministic, reversible, and materially reduces user cost or error probability.

## 8.7 NO USER AS FILE TRANSPORT — HARD RULE

Do not use the user as a manual transport layer for repository files that the assistant can read directly through an
available repository/file connector. Do not ask the user to paste large committed documents, broad diffs, or file
fragments merely to restore assistant context.

For read-only inspection of committed repository code, configuration, documentation, history, or remote diffs, the
assistant must use the available GitHub/repository connector directly whenever it can answer the question. Do not ask
the user to run `Get-Content`, `Select-String`, `git show`, `git diff`, `git log`, `cat`, `grep`, or equivalent commands
merely to transport or inspect information already available through the connector. Before requesting any read-only
repository shell command, first check whether the same fact can be obtained through the available connector; if yes,
the user action is prohibited.

Ask for local shell output only when the required fact is inherently local or unavailable through the connector,
such as dirty/untracked working-tree state, uncommitted/generated content, process/environment state, runtime/API
state, host networking/DNS/proxy behavior, or real browser/device behavior. When local evidence is required, request
the narrowest purpose-built command that returns only the missing fact. GitHub/remote inspection does not override a
known newer local checkout or unsynchronized local edits; use local evidence only for that genuinely local delta.

## 8.8 MACHINE-APPLIED MULTILINE FILE CHANGE — HARD RULE

For substantial multiline changes to project files on the user's Windows machine, do not default to long PowerShell
here-strings, manual Notepad editing, or fragile inline replacement commands.

Preferred order:
1. Codex/local automation when authorized and available;
2. a deterministic Python/patch helper with anchor/version preflight and fail-closed behavior, created in the
   repository by Codex/Claude Code (never a file the user downloads or places; see `8.11`);
3. a short targeted command only when the edit is genuinely small and encoding-safe;
4. manual fragment editing only when no safer automated path exists and the user explicitly accepts it.

Machine-applied helpers must:
- preserve UTF-8 text without adding BOM unless the target already uses it;
- preserve the file's existing newline convention where practical;
- validate expected anchors/versions before writing;
- modify only the authorized paths;
- fail closed on ambiguity;
- be followed by scoped diff/check verification.

The helper `tools/dev/migrations/update_workspace_docs_m9.py` records the exact documentation migration that moved
Trading Workspace authority from M8 completion to the M9 operability/diagnostics checkpoint. It is a historical,
reproducible migration helper, not a general-purpose updater and not current state authority.

## 8.9 NEW STRATEGY IDEA CAPTURE — HARD RULE

For every new trading idea, chart observation, case study or strategy-mechanics refinement supplied by the user,
load `.agents/skills/strategy-hypothesis-capture/SKILL.md` and the current
`DOCUMENTS/TRADING_STRATEGY_SPEC.md` automatically; no skill name or capture checklist is required in the prompt.
A chart/UI screenshot without strategy meaning is not research capture. Capture an actual idea only through this research path:

```text
Observation / Case Study
  -> Formalized Setup
  -> Hypothesis H-xxx
  -> Required Dataset
  -> Validation Method
  -> Promotion Criterion
  -> Kill Criterion
  -> Research Backlog
```

The skill owns classification, semantic deduplication, H-ID allocation, data/validation fields, source-image
handling and the minimal patch procedure. Follow those steps without copying them into a generated Codex prompt.

Never:

* turn one chart or anecdote directly into a production strategy;
* claim proven edge or profitability without the required validation;
* rewrite the whole `TRADING_STRATEGY_SPEC.md` for one observation;
* mix `BASELINE`, `ACCEPTED DESIGN`, `HYPOTHESIS` or `NEEDS VALIDATION` authority states;
* promote example-specific prices, percentages or visual boundaries into universal parameters.

This is research-only capture, not authorization to change trading/runtime code. A chart remains evidence of the
observation, not proof of the generalized claim. Root `AGENTS.md` and section 7.2 own the protected edit, verification
and Git workflow; preserve reference-case storage rules and all approval boundaries.

## 8.10 EXTERNAL REFERENCE ACCELERATION — HARD RULE

Do not reserve external research only for severe regressions. For non-trivial architecture, debugging, reliability,
workflow, performance, state-management, transport, exchange-integration, or developer-productivity problems,
proactively consult proven external implementations when doing so is likely to reduce the search space or prevent a
local reinvention. Prefer official API/protocol/library documentation first, then mature relevant open-source
projects, high-signal issue/PR history, and authoritative engineering write-ups.

Use external reference as an accelerator, not as authority over this project. Compare candidate patterns against the
current BybitScanner architecture, contracts, invariants, safety model, runtime constraints, and user workflow before
adopting them. Extract the transferable ownership/lifecycle/failure-handling idea; do not cargo-cult code or import a
foreign architecture wholesale.

External research is especially appropriate when the project reaches an unfamiliar boundary, several plausible
solutions exist, tests disagree with runtime behavior, a repeated manual workaround appears, or another mature
project is likely to have already solved the same class of problem. It is not required for a trivial deterministic
fix with a proven local cause, and it must not become broad browsing that delays an obvious safe correction.

## 8.11 NO_MANUAL_FILE_PLACEMENT_RULE — HARD RULE

The user does not download, rename, drag, or manually place files (documents, patches, scripts) created by the
assistant. Such files are created in the repository through Claude Code (or Codex): the prompt contains the full text of
the file or the command Claude Code runs. For edits to existing files, the prompt contains the exact changes.

A manual path is allowed only when the automatic path is impossible and the user has explicitly agreed to it. This
extends `8.7` (no user as file transport) and `8.8` (machine-applied file changes) to files the assistant produces.

---

