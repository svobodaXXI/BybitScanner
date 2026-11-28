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

## Result-first hand-off between delivery stages

At each transition (scoped implementation → evidence → PR/CI review →
authorized integration → runtime acceptance), apply the
`AGENTS.md` Result-first transition gate. This is a decision inside the
existing PR/task workflow, not an extra ticket, approval or dashboard.

- State the nearest owner-visible outcome and the **one** unproven prerequisite
  on its critical path. Work in small batches; avoid parallel preparatory
  PRs that do not unblock that outcome.
- Reuse current CI, tests, merge/review and source evidence. Once the required
  checks pass, proceed to the next authorized dependent action rather than
  creating another inspection step.
- A tool, transaction or receipt failure is not automatically a product
  failure. Report its exact status, determine whether the failed evidence is
  *actually required* for this change, and fix only a proven mandatory gate.
  Never claim PASS on failed evidence or bypass an applicable requirement.
- A known bounded limitation may be accepted by the owner only where the
  relevant contract permits it. Unknown material safety facts still need
  narrow evidence. STOP/TAKE, fail-closed, continuity, reconciliation,
  PAPER/LIVE separation and owner-only runtime approvals are unchanged; merge authority is limited to the rule below.
- For a code-ready trading change, GitHub integration is **not** a claim of
  real PAPER success; after safe integration, offer the owner the smallest
  authorized runtime acceptance step. Count completed protected PAPER
  lifecycles and net PnL as product outcomes, not PR/check counts.

Do not change CI filters, branch protections, transaction/harness contracts
or trading safety rules to make the critical path appear green.

## Bounded routine squash merge — OWNER RULE 2026-11-27

The owner grants ChatGPT standing permission to squash-merge a single safe routine PR after required evidence passes. This is a narrow publication permission, not automatic task authorization, GitHub auto-merge, bulk merge, deployment or acceptance.

All of the following must hold:

- The task is already authorized, the complete reviewed diff is small and scoped to that task, and the PR belongs to the current workstream without unrelated or concurrent conflicting changes.
- The change is demonstrably routine and non-safety-critical (for example, editorial documentation, independent tests that do not weaken gates, or a bounded deterministic non-trading fix). Establish impact from actual callers, contracts and the diff, not title, file extension, label or CI alone.
- No direct or indirect change to strategy, signal selection or geometry affecting trades, execution, order/position lifecycle, risk, protection, admission, reconciliation, account/data ownership, financial calculations, PAPER/LIVE boundaries, runtime control, releases, credentials/security, persisted-data contracts, material architecture, governance/authority, CI or harness/required checks. No weakening, deletion or reinterpretation of a safety, verification or owner-approval requirement. Changes to this permission itself are excluded.
- Verify intended active base and exact current head, complete scope, mergeability, mandatory CI/reviews and applicable focused proof/acceptance prerequisites; no unresolved blocker or missing/ambiguous safety evidence. Never bypass branch protections or required reviews. A known restriction from the owner or owning spec prevails.

If any condition is false or unknown, retain the existing named-PR owner approval requirement after all mandatory gates pass. An explicit owner approval, or a standalone «э» directly answering an explicit proposal to merge that named PR, covers only that named scope. Re-review after material diff/base changes; stop on conflicts, changed head or unmet gates. No permission is inferred from CI, a PR description or another agent's status.

For an eligible PR, perform squash merge with expected head SHA, verify the resulting commit and report the PR, SHA, proof and bounded-routine basis in the existing PR/task record. Do not enable unattended auto-merge or create a separate approval workflow. A merge never grants local installation, VPS release, STOP/START, admission, trading, LIVE or owner-only real-world acceptance. If a separate pre-merge acceptance or permission applies, it remains binding. This rule takes effect only after its own separately owner-approved PR is merged into the active branch.

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