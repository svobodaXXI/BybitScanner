---
name: context-budget
description: Recover and manage BybitScanner task context economically for context-heavy, interrupted, or uncertain work without weakening safety or loading broad project history by default.
---

# Context Budget

Use this procedure with the staged recovery rules in the root `AGENTS.md`; it does not replace them.

1. Establish the current task, branch, HEAD, index/working-tree state, and relevant dirty scope.
2. Locate before reading broadly: search headings, symbols, paths, and owning references, then read only relevant sections or ranges.
3. Batch independent searches and reads. Reuse fresh evidence unless state changed or a conflict makes rereading necessary.
4. Use `python -m tools.dev.task_context --path EXACT_PATH` when its disposable bootstrap reduces recovery work. Do not require a ContextDump for routine scoped work.
5. Follow owning references only as far as needed for safe action. Do not copy full ChangeRequest history into working context.
6. Prefer hot current state plus canonical references over cold history; use Git for detailed implementation history.
7. Stop recovery when scope, authority, constraints, affected state, and the next safe action are sufficiently established.

Use full deep recovery only when scope is unknown, authorities conflict, interruption is severe, or the change is architecture-wide. For durable work, follow the ChangeRequest and governance gate selected by `AGENTS.md`.

Never trade correctness, dirty-tree safety, execution/risk checks, money-sensitive reasoning, or necessary verification for token savings. Optimize tokens per completed task, not the smallest possible prompt or answer.

When measuring or comparing recovery footprints is actually useful, reuse `tools.project_sync.governance.context_budget`; keep deterministic extraction and duplication detection in code rather than recreating them in prose.
