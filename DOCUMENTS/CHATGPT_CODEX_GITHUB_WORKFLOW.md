# ChatGPT + Codex + GitHub Workflow

Status: PLANNED / NOT YET ENABLED

Date: 2026-09-08

## Purpose

Reduce manual user relay between ChatGPT and Codex by using GitHub as the shared collaboration surface for implementation tasks, reviews, CI evidence, and handoff state.

This workflow does not create a hidden direct channel between ChatGPT and Codex. GitHub is the explicit shared medium.

## Roles

- User: product decisions, approvals, live acceptance, external authorization.
- ChatGPT: architecture, task framing, GitHub review, blocker detection, merge coordination.
- Codex: local implementation, tests, commit/push, PR updates, review fixes.
- GitHub: shared technical state through Issues, branches, commits, Pull Requests, review comments, and CI.

## Core flow

```text
User product decision
-> ChatGPT task / Issue
-> feature branch
-> Codex implementation
-> tests
-> commit / push
-> Pull Request
-> ChatGPT review
-> review comments in the same PR
-> Codex fixes in the same branch / PR
-> CI / verification
-> ChatGPT acceptance / merge
-> Codex local main synchronization
-> user live acceptance when required
```

One logical task should normally remain in one Issue / feature branch / Pull Request.

## User shorthand: `х`

For BybitScanner, a standalone user message containing the single Cyrillic character:

```text
х
```

means:

> Codex has completed or updated the current GitHub-tracked task. Inspect GitHub immediately and determine the actual current result yourself.

On `х`, ChatGPT must not ask the user to copy Codex output when GitHub already contains the needed information. ChatGPT should locate the relevant current PR/branch, determine the latest head SHA, inspect changed files/diff, review comments, and available CI/verification evidence, then decide the next action.

If a previous review exists, inspect only the new delta needed to determine whether the review blockers were resolved.

## What Codex publishes

Codex does not publish one special result file. The Pull Request is the task envelope and may contain any number of changed files.

The review surface consists of:

- PR head SHA;
- commits;
- complete changed-file set;
- diff;
- PR description;
- review comments;
- test/CI evidence;
- known limitations when relevant.

## Review loop

When ChatGPT finds a blocker, the preferred path is:

1. leave the precise technical finding in the existing PR review/comment;
2. do not create a replacement PR merely for the fix;
3. Codex reads that review and fixes the same branch;
4. Codex tests, commits, and pushes;
5. the user can send `х` again;
6. ChatGPT checks the new head SHA and delta.

This keeps long technical feedback in GitHub instead of making the user relay it manually.

## Planned Codex GitHub readiness check

When Codex limits are available again, verify the local Codex environment before enabling this workflow:

1. repository and `origin` are correct;
2. `git` is available;
3. GitHub CLI (`gh`) is available;
4. `gh auth status` succeeds;
5. the authenticated identity can read repository Issues and Pull Requests;
6. Codex can create/update feature branches and PRs under the project's existing approval rules;
7. secrets remain excluded from commits.

Do not enable automated PR-driven continuation until these checks pass.

## Optional future PR watcher

A later enhancement may keep a local orchestrator/watch process that checks the current PR for new ChatGPT review comments and lets Codex continue technical fixes without requiring the user to paste the review text.

The watcher is not yet implemented or authorized.

If implemented, it must remain bounded by these gates:

- it may continue only the already-authorized logical task;
- review fixes remain in the same branch / PR;
- it must not invent a new product task after approval/merge;
- architectural changes, strategy changes, risk policy changes, and LIVE-money changes still require their normal explicit approval;
- destructive Git commands and secret handling remain prohibited;
- unknown local state must fail closed.

## No autonomous task chaining

Codex must not infer that completion of one roadmap stage authorizes the next stage.

A new logical task starts only when its scope is authorized through the normal BybitScanner governance path. Technical fixes for an already-authorized PR may continue automatically only if a future watcher/orchestrator is explicitly enabled.

## Local synchronization after merge

When Codex has terminal access, routine post-merge local synchronization should be performed by Codex rather than delegated to the user, unless local-only uncertainty or user-owned changes require user involvement.

Codex should establish local state, switch to `main`, fetch/pull safely, run objectively required checks, and report the resulting SHA and status.

## Safety

Never automatically:

- `git reset --hard`;
- `git clean -fd`;
- force-push `main`;
- overwrite or delete unknown local changes;
- delete `.env` or local secrets;
- commit credentials/tokens/passwords;
- merge an unreviewed PR;
- continue into a new authorization scope.

When repository/local authority conflicts or local state is unknown, stop rather than repair destructively.

## Activation state

As of 2026-09-08 this workflow is documented for future use but is not fully enabled because Codex weekly limits are exhausted until the expected reset on 2026-09-10.

When Codex access resumes, begin with the readiness check above. After successful readiness validation, this document becomes the operating reference for GitHub-driven ChatGPT/Codex collaboration together with `AGENTS.md` and `DOCUMENTS/ASSISTANT_PROTOCOL.md`.
