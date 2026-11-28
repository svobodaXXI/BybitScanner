# 2. COMMUNICATION AND USER ACTIONS

### No harness recovery spiral — OWNER RULE 2026-10-10

A tool/harness error is NOT authorization to launch a new infrastructure task.
For `PREEXISTING_DIRTY`, `not a managed worktree`, reparse-point/`apply_patch`
failure, or a nested task-transaction rejection:

1. Preserve the current task diff, user changes and exact failure evidence; identify
   whether the failure is workspace/tooling rather than product code.
2. Reuse the original task/worktree and its already-passing checks. Attempt at most
   ONE narrowly supported, authorized recovery with the existing harness.
3. Never silently stash/pop, reset, clean, move worktrees, recreate tasks, or modify
   audit contracts, task metadata or harness guards merely to manufacture PASS.
   A workaround requires a proven supported procedure and explicit permission;
   no permission bypasses a mandatory gate.
4. If recovery fails, STOP with exact blocker, location of preserved diff and
   smallest supported next action. Do not chain fallbacks or reopen transactions.
5. Once unblocked, finish the original product delta and mandatory targeted proof,
   then STOP. Do not create another preparatory quest.

This rule does not weaken repository integrity, fail-closed protection, PAPER/LIVE
boundaries, mandatory gates or owner runtime authority.

### Agent-owned GitHub delivery — OWNER RULE 2026-10-10

The owner is NOT a courier between ChatGPT, Codex, Claude, sandboxes and GitHub.
For tasks whose outcome is code or a PR, select an execution environment with
write access to the intended repository and a supported task harness **before**
delegation. The assigned agent owns the complete chain: scoped edit, targeted
verification, harness finish, commit, push and opening its own PR. ChatGPT owns
PR review, CI/safety-gate verification and merge under the canonical publication rule.

Do not ask the owner to copy patches, paste code between agents, upload working
tree diffs, perform routine git push or run GitHub UI merge merely because an
agent chose a read-only sandbox. A read-only agent may audit or design, but is
not the default executor for a delivery requiring publication.

If the assigned environment unexpectedly lacks write access: STOP, preserve
the exact changes and evidence, state the access blocker, and use an already
connected and permitted direct GitHub workflow if one exists. Do not initiate
a chain of sandbox-to-sandbox transfers or invent an infrastructure workaround.
If no supported direct path exists, ask for the smallest *one-time connection*
action rather than repeated manual patch forwarding. Never claim that a
read-only sandbox's task finish passed if it failed.

All existing scope, owner authorization, CI/harness, PAPER/LIVE, safety,
runtime-start and no-blanket-auto-merge boundaries still apply.

### GitHub PR merge via ChatGPT — owner rule 2026-10-10, amended 2026-11-27

`DOCUMENTS/GITHUB_FIRST_WORKFLOW.md` → Bounded routine squash merge owns the exact standing permission, exclusions and evidence gates. ChatGPT performs eligible routine merges without a redundant owner turn; all other merges require named-PR approval. No blanket auto-merge. Verify exact head/base, scope, required checks/reviews, mergeability and resulting squash commit; stop on an unresolved gate. No release, runtime, trading or acceptance authority follows from merge.

