# BybitScanner Quest System — GTD Gamification Layer

Status: ACTIVE PROCESS LAYER  
Date adopted: 2026-09-25  
Purpose: make project execution more engaging without weakening GTD, safety, evidence or delivery discipline.

## 1. Core rule

The Quest System is a presentation/motivation layer over the existing GTD and
project-governance system. It never replaces backlog priority, ChangeRequests,
tests, acceptance, safety gates, Git history or owner decisions.

**No farming rule:** XP is awarded for verified outcomes, not activity volume.

Do not award XP for:

- writing more tests than necessary;
- adding documentation that does not change project authority;
- splitting one task into artificial subtasks;
- number of commits, PRs, messages or hours;
- repeating already-green checks;
- speculative refactors.

Reward only evidence-backed progress that reduces distance to the project goal.

## 2. GTD -> Quest mapping

The existing GTD flow remains authoritative:

```text
CAPTURE -> CLARIFY -> ORGANIZE -> REFLECT -> ENGAGE
```

Game layer:

```text
CAPTURE  = Quest Inbox
CLARIFY  = Identify quest / boss / side quest / trash loot
ORGANIZE = Quest Log + dependencies + rewards
REFLECT  = Campfire Review
ENGAGE   = Active Quest
DONE     = Quest Complete / Achievement unlock
WAITING  = Tavern / Waiting on external event
SOMEDAY  = World Map / Fog of War
```

### Quest Inbox

Every new idea/bug/request is captured first without immediately changing the
active mission.

### Quest Log

Only clarified work enters the Quest Log. Every quest needs:

- outcome;
- why it matters;
- completion evidence;
- priority;
- dependencies;
- safety/runtime boundary if relevant.

### Active Quest

One primary quest at a time unless two tasks are objectively independent.

The current owner-priority queue still decides what is active. The game layer
must not reorder work on its own.

### Tavern

Waiting-for-external-event items live here:

- CI;
- owner visual acceptance;
- exchange/runtime evidence;
- future market event;
- dependency PR.

Waiting does not count as active work.

### World Map

Someday/maybe ideas remain visible but do not consume attention.

Examples:

- future Flag detector;
- close-and-reverse;
- LIVE expansion;
- optional UX polish.

### Campfire Review

Equivalent to GTD weekly review.

At review time:

1. clear Quest Inbox;
2. confirm Active Quest still matches owner priority;
3. move blocked work to Tavern;
4. remove completed quests from active queue;
5. reveal newly unblocked quests;
6. award achievements only from actual evidence;
7. choose the next quest with the shortest reliable path to project value.

## 3. Quest types

### Main Quest

Directly advances the current project objective.

Examples:

- connect L-shape to PAPER Robot;
- make multi-pattern Scanner exhaustive;
- validate PAPER Robot reliability.

### Boss Fight

A blocker that prevents trustworthy operation or invalidates results.

Examples:

- protection continuity loss;
- duplicate ownership;
- stale signal execution;
- reconciliation failure.

A Boss is complete only when root cause + fix + required verification are done.

### Side Quest

Useful but not on the critical path.

Examples:

- UI polish;
- diagnostic labels;
- non-blocking cleanup.

Side quests never preempt a Main Quest unless the owner explicitly changes
priority.

### Escort Quest

A task where an existing working subsystem must survive while another change is
made.

Examples:

- modify Box entry policy without breaking Wedge;
- change Telegram presentation without changing trading behavior.

Success condition includes preservation of the escorted subsystem.

### Exploration Quest

Bounded research with a concrete question.

Examples:

- inspect how mature engines handle reconnect recovery;
- compare focused-symbol monitoring architectures.

Exploration must end in a decision, plan or rejected option. Endless research
earns no XP.

### Raid

A coordinated multi-slice mission with several dependent stages.

Example:

```text
Raid: L-shape -> PAPER Robot
  1. admission contract
  2. durable candidate state
  3. entry/protection reuse
  4. Telegram Robot button
  5. focused acceptance
```

A Raid is used only when the slices are truly dependent. Do not turn ordinary
tasks into raids for theatrical effect.

## 4. XP system

XP expresses verified project progress. It is intentionally coarse.

- **10 XP — Scout:** useful verified finding that removes uncertainty.
- **25 XP — Quest step:** bounded implementation slice merged with required proof.
- **50 XP — Major quest:** user-visible or runtime capability completed.
- **100 XP — Boss defeated:** material reliability/safety blocker eliminated and verified.
- **150 XP — Raid cleared:** multi-stage capability completed end-to-end with acceptance.

No partial XP for work-in-progress unless it produced reusable verified
evidence.

No negative XP. Bugs are information, not punishment.

## 5. Levels

Total XP is project-level, not personal performance.

- Level 1 — Candle Goblin: 0–99 XP
- Level 2 — Pivot Hunter: 100–249 XP
- Level 3 — Wedge Ranger: 250–449 XP
- Level 4 — Breakout Tactician: 450–699 XP
- Level 5 — Robot Handler: 700–999 XP
- Level 6 — Risk Warden: 1000–1399 XP
- Level 7 — Market Cartographer: 1400–1899 XP
- Level 8 — Execution Architect: 1900–2499 XP
- Level 9 — Liquidity Dragon Tamer: 2500–3199 XP
- Level 10 — Keeper of the Green PnL: 3200+ XP

Ranks are humorous project milestones, not quality claims or trading guarantees.

## 6. Achievements

Achievements are permanent labels unlocked by evidence.

### Engineering achievements

**No More Ghost Signals**  
Eliminate a stale-signal path and verify it.

**One Symbol, Many Beasts**  
Scanner successfully returns multiple independent patterns for one symbol.

**Two Floors Cleared**  
One ticker completes all 5m and 1m detectors before the next ticker.

**The Watcher**  
FocusedPatternMonitor discovers a later independent structure after Full
Scanner has moved on.

**Same Engine, New Monster**  
A new pattern family reaches Robot by reusing the shared lifecycle rather than
building a duplicate engine.

**Fourfold Path**  
Ikigai Box executes its four owned entry parts through the shared Robot
lifecycle.

**No Doppelgängers**  
Duplicate Robot ownership is prevented by durable evidence.

**Phoenix Protocol**  
A restart/reconcile restores a valid Robot lifecycle without manual DB edits.

**Barrier Master**  
A reconnect boundary is handled without falsely invalidating pre-disconnect
evidence.

### Workflow achievements

**Zero Bureaucracy Combo**  
Three consecutive tasks completed without redundant test/doc repetition.

**Clean Handoff**  
A task survives chat/session transition using repository authority without the
owner having to reconstruct context.

**One Shot Acceptance**  
A complete owner-run acceptance pass succeeds without partial reruns.

**The Ruthless Backlog**  
A stale or superseded task is removed/closed instead of being repeated.

**Tiny Diff, Big Win**  
A production defect is solved with a deliberately small change surface.

### Trading-system achievements

**First Blood (PAPER)**  
First valid PAPER trade from a newly integrated pattern family.

**Chain Reaction**  
One market episode produces two separate valid sequential trades from different
structures, with independent candidates and protection.

**Flat Before Flip**  
An opposite secondary setup waits safely for flat, is revalidated and only then
enters.

**Guardian Online**  
Every open Robot position has proven full-position protection.

## 7. Bosses

A serious blocker may be given a boss name for communication, but the technical
reason remains explicit.

Format:

```text
BOSS: The Stale Generation Wraith
Technical blocker: pre-reconnect event retroactively rejected after owner-queue delay
HP: 3 evidence gates
  [x] root cause
  [x] code fix
  [x] Robot PAPER acceptance
Status: DEFEATED
```

Boss HP is the number of real evidence gates, never arbitrary story points.

## 8. Loot

Loot means a reusable asset produced by a quest:

- regression test;
- stable API/contract;
- reusable detector primitive;
- recovery path;
- operator control;
- documented invariant.

Loot is not a reward for creating files. It must reduce future work.

Example:

```text
Loot acquired:
- ordered disconnect barrier
- protection-continuity regression test
```

## 9. Combo system

Combos reward process quality, not speed.

### Precision Combo

Consecutive quests with:

- no unrelated edits;
- no repeated checks;
- no owner action that could have been automated;
- no regression outside scope.

### Reuse Combo

Consecutive features delivered by reusing shared infrastructure instead of
adding parallel mechanisms.

### Evidence Combo

Several decisions resolved from repository/runtime evidence without guessing.

A combo ends when a task legitimately requires a different path; there is no
penalty.

## 10. Quest card format

When useful, project status may be summarized as:

```text
🎯 ACTIVE QUEST
L-shape -> PAPER Robot

Type: Main Quest / Raid
Priority: #1
Objective: real L-shape Robot handoff + working Telegram Robot button
Boss: unsupported Robot admission for L-shape
Done when:
- L-shape produces durable Robot candidate
- shared Robot lifecycle accepts it
- STOP/TAKE rules remain L-shape-specific
- Telegram Robot button controls a real candidate
- required focused PAPER verification passes

Reward: 50 XP
Possible achievement: Same Engine, New Monster
```

Do not show a quest card on every reply. Use it at task start, meaningful
checkpoint, completion, owner request, or Campfire Review.

## 11. Current campaign

### Campaign: PAPER Robot — Pattern Guild

Current ordered quests:

1. **Raid: The L-shaped Door**
   L-shape -> PAPER Robot + real Telegram Robot button.
2. **Boss: The Crooked First Impulse**
   Correct Ikigai Box first-impulse segmentation; AIGENSYNUSDT 5m is the
   concrete defect.
3. **Side Quest: Dress the Position Card**
   Telegram position-card presentation refinement.
4. **Raid: Many Beasts, One Ticker** — deferred
   Multi-pattern 5m + 1m Scanner orchestration.
5. **Quest: The Watcher** — deferred
   Focused post-discovery pattern monitoring.

Owner priority always overrides campaign order.

## 12. Integration with existing project authority

- `DOCUMENTS/BACKLOG.md` remains the canonical task queue.
- This document owns game semantics only.
- ChangeRequests/specs own technical contracts.
- CI/tests/runtime evidence own completion proof.
- Telegram/Robot safety rules remain unchanged.
- The owner may rename quests/achievements at any time without changing
  implementation scope.

The game system must make work more enjoyable and easier to reason about. If a
mechanic starts creating bookkeeping, remove or simplify it.
