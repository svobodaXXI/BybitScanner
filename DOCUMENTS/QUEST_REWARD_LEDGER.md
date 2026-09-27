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

## Reward reconciliation — 2026-09-27

The migration baseline above was written before several later verified outcomes
landed on the same day. The entries below restore those missed rewards from
repository/runtime evidence. They are outcome-based; PR count, commit count,
test count and documentation do not earn XP by themselves.

### REWARD-TELEGRAM-MENU-20260927

- Date: 2026-09-27
- Type: quest stage
- Outcome: permanent owner Telegram Menu control surface repaired after
  owner messages/callbacks while preserving the state-aware Scanner action
- Evidence: merged PR #271, merge commit
  `e0afeee776e274b617cae3fa48641d84953779dd`
- XP before: 140
- XP delta: +25
- XP after: 165
- Achievement changes: none
- Loot: reusable owner-menu reassert path

### REWARD-SHARED-PATTERN-HANDOFF-20260927

- Date: 2026-09-27
- Type: quest stage
- Outcome: Wedge and L-shape durable Scanner candidates now cross one shared
  Pattern -> Robot pre-admission boundary without a second execution engine
- Evidence: merged PR #274, merge commit
  `878d18d8a25d71c8b20c832549d53e892563f0f3`
- XP before: 165
- XP delta: +25
- XP after: 190
- Achievement opened: **«Новый монстр, старый движок»**
- Loot: shared `pattern_robot_integration.py` handoff boundary

### REWARD-BOX-TRUTHFUL-AFFORDANCE-20260927

- Date: 2026-09-27
- Type: quest stage
- Outcome: non-executable Ikigai Box signals no longer expose a misleading
  `🤖 Робот` action; unsupported Box execution remains fail-closed
- Evidence: merged PR #275, merge commit
  `03d19cb82b52741d38ec053ab09d66c820f5ac3f`
- XP before: 190
- XP delta: +25
- XP after: 215
- Achievement changes: none
- Loot: truthful capability-bound Telegram action contract

### REWARD-INGRESS-OVERFLOW-EVIDENCE-20260927

- Date: 2026-09-27
- Type: reconnaissance
- Outcome: a future protection `ingress_overflow` preserves current ingress
  metrics and lifecycle role in the fail-closed log, reducing postmortem
  uncertainty without changing recovery/trading semantics
- Evidence: merged PR #278, merge commit
  `188e68b92ead15475031c717706e1546b70bcaae`
- XP before: 215
- XP delta: +10
- XP after: 225
- Achievement changes: none
- Loot: reusable overflow postmortem evidence snapshot

### REWARD-DUAL-TIMEFRAME-CONTRACT-20260927

- Date: 2026-09-27
- Type: reconnaissance
- Outcome: existing Scanner behavior is now regression-proven to process each
  symbol in strict 5m -> 1m order and keep Wedge signal state independent by
  symbol x timeframe x pattern x formation
- Evidence: merged PR #279, merge commit
  `0037b9218900001d2f8a6e9f4ad44b7230ef0d4a`
- XP before: 225
- XP delta: +10
- XP after: 235
- Achievement changes: none; this focused contract proof is not the full
  owner-run acceptance required for «Оба этажа зачищены»
- Loot: dual-timeframe regression contract in Robot PAPER acceptance

### REWARD-DESKTOP-RUNTIME-COMPOSITION-20260927

- Date: 2026-09-27
- Type: big quest
- Outcome: canonical desktop PAPER Robot start/stop composition is complete and
  owner-verified end-to-end; safe-stop now reaches the repository module,
  returns exit code 0 and persists `ROBOT_STOPPED / ROBOT_STOPPED` while
  intentionally leaving backend/Telegram alive
- Evidence: merged PR #276
  (`0f72355eca73be2981d5e406614467fe7e27c7ff`), launcher fix PR #280
  (`adcd44e1580a1f7648abb79c20a84c6980859660`), Robot PAPER acceptance #218
  SUCCESS, and owner real-run safe-stop evidence
- XP before: 235
- XP delta: +50
- XP after: 285
- Level after: **3 — Следопыт клиньев**
- Achievement opened: **«Малый патч — большая добыча»**
- Loot: canonical desktop start/stop surface + known safe-stop recovery path

### REWARD-RECONCILIATION-NOTE-20260927

- Date: 2026-09-27
- Type: accounting correction
- Outcome: reward ledger caught up with verified post-baseline outcomes
- Evidence: repository history and the runtime evidence referenced above
- XP before: 285
- XP delta: 0
- **Canonical XP after reconciliation: 285**
- Level: **3 — Следопыт клиньев**
- Note: AIGENSYN PR #270 predates the 140-XP migration baseline and is not
  counted again; open draft PR #267 (position-card presentation) is not
  reward-eligible until its required acceptance/merge boundary is satisfied.

