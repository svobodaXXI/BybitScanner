# BybitScanner — Quest Reward Ledger

Status: ACTIVE  
Policy: APPEND-ONLY REWARD AUTHORITY  
Introduced: 2026-09-27

Purpose: make XP, achievements and loot auditable instead of relying on chat
memory or a single mutable total in `QUEST_STATE.md`.

## Rules

1. Every XP/achievement/loot change is appended here when its verified outcome
   is established.
2. Each entry records the outcome, evidence, XP before, delta, XP after,
   achievements and reusable loot.
3. `QUEST_STATE.md` is only the current projection of this ledger.
4. A chat message containing a different XP total is treated as a
   reconciliation request, not sufficient authority to silently rewrite the
   score. Reconcile against this ledger and the underlying outcome evidence.
5. Owner corrections can repair a factual ledger error, but the correction is
   itself recorded; history is not silently rewritten.
6. Commits, test counts, hours, documentation volume and planning do not earn
   XP by themselves.
7. Achievements may award 0 XP. XP is awarded only when the separately defined
   outcome threshold is met.
8. When a quest/boss/raid completion changes XP, achievements or loot, updating
   this ledger and `QUEST_STATE.md` is part of Definition of Done, not a
   follow-up documentation task.
9. Assistants must never claim a new total/level/achievement as canonical
   until the corresponding ledger entry exists.

## Migration baseline

Historical reward events before this ledger were not consistently itemized.
Do not invent a retroactive decomposition.

### REWARD-BASELINE-20260927

- Date: 2026-09-27
- Type: baseline migration
- Outcome: owner-confirmed canonical score carried into the append-only ledger
- Evidence: owner reconciliation during the 2026-09-27 campaign session;
  earlier `QUEST_STATE.md` projection was proven stale
- XP before: not reconstructed
- XP delta: not reconstructed
- **Canonical XP after migration: 140**
- Level: **2 — Охотник за пивотами**
- Achievement changes: none assigned by this baseline entry
- Loot: append-only reward accounting authority
- Note: this is not a new reward and must not be counted again

### ACH-CONTEXT-20260927

- Date: 2026-09-27
- Type: achievement
- Outcome: a new BybitScanner chat recovered repository authority, active
  project context and visible Russian game mode without the owner manually
  reconstructing the handoff
- Evidence: owner-observed new-chat bootstrap acceptance on 2026-09-27
- XP before: 140
- XP delta: 0
- XP after: 140
- Achievement opened: **«Контекст не потерян»**
- Loot: verified repository-driven game bootstrap
