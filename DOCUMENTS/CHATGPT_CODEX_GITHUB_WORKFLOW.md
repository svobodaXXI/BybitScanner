# Claude + Claude Code + GitHub Workflow

Status: PLANNED / NOT YET ENABLED

Date: 2026-09-10

## Purpose

Reduce manual user relay between Claude and Claude Code by using GitHub as the shared collaboration surface for implementation tasks, reviews, CI evidence, and handoff state.

This workflow does not create a hidden direct channel between Claude and Claude Code. GitHub is the explicit shared medium.

## Roles

- User: product decisions, approvals, live acceptance, external authorization; provisions the GitHub token this workflow depends on.
- Claude: architecture, task framing, GitHub review, blocker detection, merge coordination — performed via the GitHub API using a user-provided token, without local file/git access.
- Claude Code: local implementation, tests, commit/push, PR updates, review fixes — the same local agent already doing this work today.
- GitHub: shared technical state through Issues, branches, commits, Pull Requests, review comments, and CI.

## Core flow

```text
User product decision
-> Claude task / Issue
-> feature branch
-> Claude Code implementation
-> tests
-> commit / push
-> Pull Request
-> Claude review
-> review comments in the same PR
-> Claude Code fixes in the same branch / PR
-> CI / verification
-> Claude acceptance / merge
-> Claude Code local main synchronization
-> user live acceptance when required
```

One logical task should normally remain in one Issue / feature branch / Pull Request.

## User shorthand: `х`

For BybitScanner, a standalone user message containing the single Cyrillic character:

```text
х
```

means:

> Claude Code has completed or updated the current GitHub-tracked task. Inspect GitHub immediately and determine the actual current result yourself.

On `х`, Claude must not ask the user to copy Claude Code output when GitHub already contains the needed information. Claude should locate the relevant current PR/branch via the GitHub API, determine the latest head SHA, inspect changed files/diff, review comments, and available CI/verification evidence, then decide the next action.

If a previous review exists, inspect only the new delta needed to determine whether the review blockers were resolved.

## What Claude Code publishes

Claude Code does not publish one special result file. The Pull Request is the task envelope and may contain any number of changed files.

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

When Claude finds a blocker, the preferred path is:

1. leave the precise technical finding in the existing PR review/comment;
2. do not create a replacement PR merely for the fix;
3. Claude Code reads that review and fixes the same branch;
4. Claude Code tests, commits, and pushes;
5. the user can send `х` again;
6. Claude checks the new head SHA and delta.

This keeps long technical feedback in GitHub instead of making the user relay it manually.

## Activation readiness check

Verify both sides before enabling this workflow.

Claude Code (local):

1. repository and `origin` are correct;
2. `git` is available;
3. GitHub CLI (`gh`) is available;
4. `gh auth status` succeeds;
5. the authenticated identity can read repository Issues and Pull Requests;
6. Claude Code can create/update feature branches and PRs under the project's existing approval rules;
7. secrets remain excluded from commits.

Claude (via GitHub API, no local access):

1. the user has provided a GitHub token scoped at minimum to `Pull requests: Read and write` on this repository;
2. Claude can use that token to read PR diffs, commits, and review comments, and to post review comments, without needing local git/file access;
3. the token itself is never treated as ordinary chat content — it is not echoed back, logged, or committed.

Do not enable automated PR-driven continuation until both sides pass.

## Optional future PR watcher

A later enhancement may keep a local orchestrator/watch process that checks the current PR for new Claude review comments and lets Claude Code continue technical fixes without requiring the user to paste the review text.

The watcher is not yet implemented or authorized.

If implemented, it must remain bounded by these gates:

- it may continue only the already-authorized logical task;
- review fixes remain in the same branch / PR;
- it must not invent a new product task after approval/merge;
- architectural changes, strategy changes, risk policy changes, and LIVE-money changes still require their normal explicit approval;
- destructive Git commands and secret handling remain prohibited;
- unknown local state must fail closed.

## No autonomous task chaining

Claude Code must not infer that completion of one roadmap stage authorizes the next stage.

A new logical task starts only when its scope is authorized through the normal BybitScanner governance path. Technical fixes for an already-authorized PR may continue automatically only if a future watcher/orchestrator is explicitly enabled.

## Local synchronization after merge

When Claude Code has terminal access, routine post-merge local synchronization should be performed by Claude Code rather than delegated to the user, unless local-only uncertainty or user-owned changes require user involvement.

Claude Code should establish local state, switch to `main`, fetch/pull safely, run objectively required checks, and report the resulting SHA and status.

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

As of 2026-09-10 this workflow is documented for use but is not enabled: the user has not yet provided a GitHub token scoped to `Pull requests: Read and write` on this repository for Claude to use.

When such a token is provided, begin with the readiness check above. After both sides pass, this document becomes the operating reference for GitHub-driven Claude/Claude Code collaboration together with `AGENTS.md` and `DOCUMENTS/ASSISTANT_PROTOCOL.md`.
