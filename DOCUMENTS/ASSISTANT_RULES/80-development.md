# 6. IMPLEMENTATION AND DOCUMENT CHANGES

Use the smallest safe method: targeted patch first, larger mechanical replacement when justified, and full-file
replacement only for substantial restructuring or when explicitly requested. Preserve architecture, dependencies,
compatibility, syntax, and data contracts. Do not make the user manually assemble unrelated code fragments.

Before editing, identify applicable authority, callers, tests, runtime effects, data compatibility, and relevant
dirty scope in proportion to risk. Documentation changes only when owned current state, contract, decision, or plan
actually changes.

Ordinary work follows:

```text
Protected task start → Implementation → Targeted validation → Task finish / report → Authorized Git checkpoint
```

Detailed Project Sync, Migration, Pipeline, approval, and architecture mechanics are owned by
`PROJECT_CONTRACTS.md`, `PROJECT_RULES.md`, `ARCHITECTURE.md`, `PROJECT_STATE.md`, and applicable ChangeRequests.
The assistant must use their prescribed governance gate when applicable, must not create an alternative execution
pipeline, and must not execute approval-gated migration without approval. Routine scoped work must not trigger full
Migration/Project Sync merely because those systems exist.

## 6.1 OBJECTIVELY_NECESSARY_TESTING_RULE

Do not create synthetic/fake UI tests for behavior the user can immediately and reliably verify in the real UI.
Add or run tests only when they protect critical logic, a material regression, behavior not quickly/reliably checked
by hand, or a mandatory contract/safety/governance requirement. Validation remains proportional to risk.

## 6.2 VITE PREVIEW BUILD-BEFORE-ACCEPTANCE

For Trading Workspace changes under `terminal/frontend/src` served through `vite preview`:

1. finish source changes and objectively required targeted/type checks;
2. run `npm run build` and require PASS;
3. reload/refresh the served page;
4. only then begin browser or real-phone acceptance.

Never ask the user to search for source changes in a stale preview build. Diagnose cache/server/path/runtime only if
the change is still absent after a successful fresh build and reload. Provide any required build/reload instruction
proactively and beginner-safely.

## 6.3 UI_AND_IMAGE_GENERATION_HARD_GATE

Terminal/UI descriptions, screenshots, colors, layout, controls, charts, DOM, Tape, icons, spacing, and wording such
as “нарисовать кнопку” are real implementation/design requirements by default. Act on React/TypeScript/CSS/SVG or
the actual UI; do not reinterpret them as image-generation requests.

Image generation/editing is prohibited unless the **current user message** directly and unambiguously requests a
standalone generated or edited image:

```text
EXPLICIT_CURRENT_USER_IMAGE_REQUEST == TRUE
```

Prior messages, attachments, screenshots, general visual discussion, tool availability, or inferred usefulness do
not authorize image tools. Do not ask for image-generation permission during ordinary UI work.

## 6.4 GITHUB-FIRST CHANGE SURFACE — HARD RULE

For ChatGPT-led BybitScanner work, committed project code, configuration, documentation, tests, and repository-owned
tooling are read and changed through the available GitHub/repository connector whenever that connector can safely
perform the operation. The user's Windows checkout is a downstream synchronization, runtime, test, build, and
acceptance surface by default: pull repository changes to the PC, then use the local machine to prove behavior that
cannot be proven remotely.

Do not ask the user to patch, rewrite, replace, or manually edit project source/documentation on the PC merely
because a local shell is available. Local code/document writes require either an explicit user override for that
specific task or an objectively necessary operation that the repository connector cannot perform safely; they are
not the fallback path for convenience.

For material code changes, preserve the existing verification and approval model. When repository-native branch/PR
or CI evidence is available and appropriate, prefer it before changing `main`. If a direct remote commit is the only
practical connector path, mark code behavior as unverified until the synchronized checkout passes the required
local tests/build/runtime/device acceptance. This rule never weakens LIVE-mutation approval, fail-closed safety,
Task/Spec/ChangeRequest scope, branch protection, verification requirements, or protection of user-owned local work.
When the user explicitly chooses Codex/local implementation for a particular task, the Codex/local workflow remains
available for that task; otherwise GitHub-first is the default.

---

# 7. CODEX EXECUTION AND VERIFICATION

## 7.1 MINIMAL_CODEX_DELTA_RULE

Routine Codex prompts must contain only task intent and genuinely task-specific constraints or facts that cannot
be inferred from repository authority. This applies both to user task entry and to prompts prepared by ChatGPT
for Codex. Do not append standard recovery, file-discovery, skill, safety, dirty-file, testing, reporting or Git
instructions. Do not require users to say "follow harness", name a skill, provide a test list or request protection
of unrelated work; those obligations apply automatically. A task-specific checkpoint, inaccessible runtime fact,
product choice or explicit restriction may be needed; carry it without expanding it into generic boilerplate.

The short prompt does not remove TASK/SPEC, scope, acceptance, approval or verification requirements. Codex recovers
or establishes them through the repository-owned workflow. `AGENTS.md` owns execution routing and skill selection;
the harness enforces its implemented deterministic guards. Codex still reads the routed authority, runs the
applicable governance gate, identifies missing checks and resolves ambiguity. Neither a short intent nor a harness
PASS authorizes a material scope amendment, LIVE mutation, deployment or Git write.

Batch approved compatible micro-tasks and related decisions. Do not interrupt implementation with serial
micro-questions when one safe decision batch suffices. Full research, status, diff, and verbose logs are off by
default. When Codex/local implementation is explicitly selected, use Codex primarily for current local
inspection/mutation, tests/build/runtime, and authorized Git work. Otherwise §6.4 makes GitHub-first the default
ChatGPT-led mutation surface. Do not perform opportunistic refactoring, cleanup, redesign, or “while here”
improvements. Prefer the smallest targeted tests and checks that prove the current delta; run full suites only when
objectively required.

Default execution loop:

```text
intent -> scoped recovery / skill selection -> protected task start + applicable gate
       -> (minimal patch -> cheap focused checks) -> task finish once / required build -> report
```

When manual, browser, or real-phone acceptance is required, stop after automated prerequisites and wait for user
evidence instead of continuing autonomously.

Default compact report:

```text
STATUS
CHANGED
TESTS
DIFF_CHECK
BLOCKERS
```

Long logs appear only when needed for diagnosis.

## 7.2 SCOPED_VERIFICATION_AND_CHECKPOINT_RULE

For edits, complete the transaction started under `AGENTS.md`:

```text
python -m tools.dev.task finish --task TASK_ID
```

Use `tools.dev.verify --focused --path EXACT_PATH` for development feedback, with repeated exact paths and
objectively needed targeted tests (direct runner or `--check-command`). It checks local working content without
the automatic frontend production build, removes any previous PASS receipt and never issues one. Focused mode
cannot be combined with `--transaction` and cannot establish completion, isolated proof or checkpoint eligibility.
Do not add a production build to each focused iteration.

After the patch settles, task finish invokes final exact-scope verification, including the required frontend
production build, checks the protected task delta, unrelated work and Git index, and
records a PASS receipt in `.git/bybitscanner/`. This satisfies the verifier requirement; do not duplicate it with
a standalone invocation unless new evidence or an independent verification purpose requires that invocation.
Standalone `tools.dev.verify --path EXACT_PATH` retains final behavior but does not substitute for task finish.
Run the final gate once; repeat only after resolving failure or changes that invalidate the evidence. No cached
verification is implied. For §6.2 preview acceptance, use the current final build if served there; an isolated
candidate build does not refresh the local preview artifact, which still requires a current build before acceptance.
Select focused tests by objective need and applicable authority; a routed build does not imply that tests ran.
Do not claim completion, acceptance, regression safety or readiness without current claim-matched evidence.
Automated PASS is not browser, live-data, touch or real-phone acceptance.

For every material claim, identify the minimum sufficient evidence before checking; stop when it is sufficient.
This applies without loading a skill and also to read-only work, which needs no edit transaction.

| Claim | Minimum current evidence |
| --- | --- |
| Syntax/import or routed source correctness | Applicable compile, type, lint or exact-scope verifier result |
| Critical deterministic behavior | Focused regression exercising the real invariant |
| Frontend production bundle | Successful current `npm run build` |
| Visual, touch, browser or device behavior | Acceptance in the required real environment, following §6.2 |
| Safe checkpoint | Current PASS receipt plus the user-run checkpoint workflow |

Keep unperformed manual acceptance `NOT YET ACCEPTED`. Evidence becomes stale after a material change to its
files, diff, runtime or acceptance environment. Report failed required checks and partial successes without
claiming completion. Expand evidence where execution, risk, PnL, sizing, reconciliation, persistence or robot safety
requires it; economy never lowers that standard.

`python -m tools.dev.checkpoint --message "..."` is exclusively user-run. Codex must never invoke it automatically.
It must fail closed on a missing/stale receipt, changed branch/HEAD/content, or unexpected staged files; stage only
receipt paths, run cached diff-check, commit, push, and verify remote SHA.

Codex does not stage, commit, or push unless the user explicitly authorizes Git-write in the current task. Preserve
unrelated work at every checkpoint. Codex Desktop is the default interface; do not tell the user to launch Codex
from PowerShell unless explicitly requested.

Report the harness result plus material task-specific findings, checks, limitations and remaining acceptance.
Do not make the user specify a report template. "No checkpoint" means stop after verification and report without
Git writes or a checkpoint action request; leave the lifecycle's RECORD/Git checkpoint pending, not falsely complete.

---

## 7.3 WORKFLOW_PROPORTIONALITY / ANTI-OVERPROCESSING RULE

Workflow and governance serve safe, timely delivery; they are not independent product goals. Scale process to
the actual risk and size of the delta, not to the availability of a mechanism. At equal safety, choose fewer
worktrees, branches, tasks, commands, user turns and less context.

For a small review fix in an already-authorized logical scope, continue in the same PR, branch and worktree
when architecture, risk and product decisions are unchanged, the branch/worktree remain usable, and user-owned
work can be protected. Do not default to a new feature/review-fix branch, PR, consolidation worktree or cycle,
copying delta between worktrees, full recovery, or repeated full regression when targeted checks plus required
harness verification are sufficient and no new evidence calls for more.

**PASS receipt boundary:** a review-fix delta after `task finish STATUS PASS` is not covered by the old receipt.
First attempt the smallest protected task for the new delta in the same branch/worktree, using exact paths and
task-only proof under §7.2. A still-open transaction covering the authorized changes should be continued, not
fragmented. Certify the new delta without redoing unrelated accepted work; this does not waive required harness
checks or extend an old receipt to changed content. Fresh certification does not itself require fresh isolation.

A heavier isolation cycle requires a concrete reason: conflicting branch/base ancestry; unrelated dirty work
that cannot safely be isolated in place; a demonstrated harness inability to prove task-only delta there;
materially expanded scope or a new financial/LIVE/risk/architecture decision; cross-PR/shared-file conflict; or
specific evidence that baseline/reproducibility is unreliable. State the reason before escalating and retain
normal approval boundaries. An old PASS, project size, or "just in case" is not a reason. On a harness failure,
stop and resolve its actual cause; never bypass it or assume a new worktree is the only remedy.

Before adding any workflow layer, assess internally:

1. What concrete risk does it address?
2. Why does the existing branch/worktree/task/PR not already address it?
3. Is its expected benefit greater than its cost in turns, context and time?

Without clear answers, do not add the layer. This is an agent judgement check, not a new mandatory user approval
round, report artifact or procedural skill.

**Small review-blocker fast path:** fix only the blocker within the protected scope; run targeted tests relevant
to the delta and broader regression only when risk/contract requires it; run `git diff --check`; complete the
minimum required harness certification with `task finish`; publish through GitHub-first into the same PR; request
re-review. Open the protected task before editing when fresh certification is needed. Do not turn the review
loop into a new project or repeat successful required checks without new cause.

---

