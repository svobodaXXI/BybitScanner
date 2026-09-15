# GitHub-First Repository Workflow

Status: ACTIVE

## Rule

For the BybitScanner repository, repository-owned source, tests, documentation, and tooling are changed through GitHub branches and pull requests by default.

The local Windows checkout is a verification and runtime workspace, not the publication authority.

For a GitHub origin, this document owns publication semantics and supersedes generic checkpoint wording elsewhere: `tools.dev.checkpoint` is validation-only and must not stage, commit, or push.

Default flow:

1. Assistant creates or updates one GitHub feature branch and pull request for one logical change.
2. Local/Codex verification is used only when the claim cannot be proven from repository-native evidence or when real runtime/device acceptance is required.
3. If local verification is used, `task finish` and user-run `checkpoint` validate the exact candidate and local invariants. They must not stage, commit, or push when `origin` is GitHub.
4. After required evidence passes, integration is performed on GitHub through the existing PR/merge workflow.
5. After GitHub merge, the local machine synchronizes from GitHub with a safe fast-forward/pull workflow.

Do not insert a local publication round-trip between GitHub-authored changes and GitHub integration merely because the local harness exists.

## Review-fix continuity

One logical PR remains one integration surface. Small review fixes within its authorized scope are published to that same branch and PR, then re-reviewed. Preserve a usable local worktree when local verification is actually needed.

Create a new PR/branch only for a real logical scope split or a demonstrated technical inability to continue safely. A stale receipt alone is not a reason for a new branch/worktree/consolidation cycle.

## Prohibited default behavior

For a GitHub origin, the harness must not automatically run:

- `git add`
- `git commit`
- `git push`
- force push
- destructive reset/clean operations

A user must not be asked to publish assistant-authored repository changes from the local machine when the GitHub connector can perform publication directly.

## Evidence routing

Use the smallest evidence source that proves the claim:

- repository text/config/doc change: GitHub diff/review plus applicable static checks;
- deterministic code behavior: focused automated regression;
- frontend bundle: current production build;
- runtime/network/process behavior: local runtime evidence;
- visual/touch/device behavior: real browser/phone acceptance;
- financial/LIVE behavior: applicable approval and fail-closed acceptance gates.

Do not duplicate a successful check in another environment unless the second environment proves a different claim.

## Compatibility boundary

The legacy local commit/push checkpoint implementation may remain available only for non-GitHub/local test repositories. It is not the BybitScanner GitHub workflow.

## Rationale

This keeps one publication authority, avoids local/GitHub integration drift, reduces branch/index churn and user turns, preserves user-owned local files, and makes the normal post-merge local action synchronization rather than publication.