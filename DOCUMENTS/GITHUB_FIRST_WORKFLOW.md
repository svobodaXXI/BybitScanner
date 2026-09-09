# GitHub-First Repository Workflow

Status: ACTIVE

## Rule

For the BybitScanner repository, repository-owned source, tests, and documentation are changed through GitHub branches and pull requests by default.

The local Windows checkout is a verification and runtime workspace, not the publication authority.

Default flow:

1. Assistant creates or updates a GitHub feature branch and pull request.
2. User-run local task harness may materialize the PR candidate only for isolated verification.
3. `task finish` and `checkpoint` validate the candidate and local invariants. They must not stage, commit, or push when `origin` is GitHub.
4. After local verification PASS, integration is performed on GitHub through the PR/merge workflow.
5. After GitHub merge, the local machine synchronizes with `git pull` (or an equally safe fast-forward synchronization when explicitly required).

## Prohibited default behavior

For a GitHub origin, the harness must not automatically run:

- `git add`
- `git commit`
- `git push`
- force push
- destructive reset/clean operations

A user must not be asked to publish assistant-authored repository changes from the local machine when the GitHub connector can perform that publication directly.

## Compatibility boundary

The legacy local commit/push checkpoint implementation may remain available only for non-GitHub/local test repositories. It is not the BybitScanner GitHub workflow.

## Rationale

This keeps one publication authority, avoids mixing local and GitHub-first integration paths, reduces branch/index drift, preserves user-owned local files, and makes the user's normal post-merge action a pull rather than a push.
