---
name: session-handoff
description: Create a compact BybitScanner handoff between ChatGPT, Codex, or interrupted development sessions while preserving exact actionable state and routing cold history to canonical sources.
---

# Session Handoff

Use the existing project state, ChangeRequest, roadmap, and Git records; never create a second `PROJECT_STATE` or copy their histories.

Capture only hot context:

- current mission and exact slice;
- current state and accepted/PASS state;
- exact dirty scope, distinguishing task changes from user-owned or unrelated work;
- current blocker and exact next action;
- verification and manual-acceptance state;
- critical temporary facts that cannot be recovered reliably.

Route cold context—architecture history, old decisions, completed slices, roadmap history, and detailed implementation history—to concise canonical references or Git.

For Trading Workspace, PAPER trading, or terminal work, also include the current roadmap stage, last completed and accepted roadmap stage, current blocker, exact next roadmap action, and any deliberate documented deviation. Read the active ChangeRequest, `DOCUMENTS/TRADING_WORKSPACE_MASTER_ROADMAP.md`, and relevant `DOCUMENTS/ASSISTANT_PROTOCOL.md` section before asserting those fields.

Before delivery, check that a new agent can identify authority, protect the dirty tree, and perform the next action without receiving tens of kilobytes of copied history. If a required fact is unresolved, label it unresolved rather than guessing.
