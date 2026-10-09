> **Current owner Wedge RR decision (2026-10-09):** minimum executable RR for Falling/Rising Wedge is **1.5:1**, not 2:1. See `DOCUMENTS/WEDGE_ROBOT_RR_OWNER_DECISION_20261009.md`. PR #440 was closed unmerged; Box and L-shape remain governed by their own thresholds.

# BybitScanner — Unified Signal / Robot Integration Standard

Status: ACTIVE  
Owner rule: 2026-09-27  
Purpose: one owner-facing trading workflow for every Scanner pattern.

## 1. Product goal

The Scanner and Robot are one product surface:

```text
detect opportunity
→ deliver one understandable Telegram signal
→ owner or Robot accepts the opportunity
→ one execution/protection/position lifecycle
→ one monitoring/history/recovery surface
```

Pattern implementations may differ internally, but the owner must not have to
learn a different operational workflow for Wedge, Ikigai Box, L-shape,
Triangle or future patterns.

## 2. Platform-level behavior — MUST be shared

The following are common infrastructure and MUST NOT be reimplemented per
pattern:

- Telegram signal shell and command/menu behavior;
- durable Robot candidate persistence and admission;
- candidate ownership / duplicate prevention;
- Robot pause / resume / stop;
- order ownership and execution bookkeeping;
- protection ownership and fail-closed safety;
- open-position projection and position cards;
- lifecycle notifications for candidate acceptance, position open and position close;
- monitoring, restart and reconciliation;
- owner-facing history/statistics plumbing;
- the desktop runtime composition/readiness path.

A new pattern must reuse these surfaces through the common integration
contract. A second execution engine, second Telegram control path or
pattern-specific copy of shared lifecycle behavior is forbidden.

## 3. Unified Telegram signal UX

All normal Scanner signals use the same owner-facing structure where the data
exists:

1. symbol;
2. source timeframe;
3. direction;
4. pattern name;
5. potential / quality information that is meaningful for that pattern;
6. chart;
7. one TradingView action with the canonical shared label;
8. Robot admission action only when this exact signal has a durable executable
   Robot candidate;
9. common review actions.

The same label MUST always mean the same action.

### Robot button invariant

`🤖 Робот` means exactly:

> admit / accept this exact signal as a Robot candidate.

It MUST NOT sometimes mean "show Robot status".

If a signal is not Robot-capable yet:

- do not show a deceptive `🤖 Робот` admission button;
- Robot status remains available through the common Robot status surface;
- if a status button is ever shown inline, it must be explicitly labelled
  `🤖 Статус робота`.

### Candidate feedback invariant

A Robot admission tap must produce one unambiguous owner result using the
shared wording family:

- candidate accepted;
- candidate already accepted;
- candidate rejected with bounded reason;
- candidate unavailable/stale;
- candidate persistence/admission failure.

No pattern gets its own silent or differently-shaped admission workflow unless
the strategy itself requires additional owner input.

## 4. Persistent owner control surface

The Telegram Menu button is a permanent owner control surface.

- It must remain available after Scanner pause/resume/start/stop.
- It must remain available after Robot control callbacks.
- It must remain available after candidate/review/position callbacks.
- Dynamic command descriptions may change, but the Menu surface itself must
  not disappear and require the owner to leave/re-enter the bot.

The `/scanner` command is one state-aware toggle:

- RUNNING → `⏸ Пауза сканера`;
- PAUSED → `▶ Продолжить сканер`;
- STOPPED → `▶ Запустить сканер`.

Pause/resume must preserve the same Scanner traversal according to the
ScannerControlRuntime contract; stop terminates it.

## 5. Common Robot lifecycle

Every Robot-capable pattern enters the same platform lifecycle:

```text
Scanner signal
→ immutable/durable candidate snapshot
→ owner/automatic admission according to current authority
→ execution ownership
→ entry order(s)
→ protection
→ open position
→ lifecycle events
→ exit
→ durable closed trade/history
→ restart/reconcile continuity
```

Common infrastructure owns the states and safety around that lifecycle.

## 6. Pattern Strategy Adapter contract

Pattern-specific code supplies only strategy-specific facts and rules.

An adapter must define, as applicable:

- stable pattern identifier and display label;
- direction / side semantics;
- immutable evidence required from the Scanner signal;
- whether the signal is executable now;
- entry plan;
- number/type/price of entry orders;
- STOP plan;
- TAKE / exit plan;
- invalidation conditions;
- pattern-specific re-entry or continuation rules;
- any strategy-specific lifecycle transition that cannot be expressed by the
  common platform states.

The adapter MUST NOT own Telegram menu plumbing, generic candidate persistence,
generic position notifications, generic protection/recovery or a parallel
execution engine.

Wedge is the existing reference implementation, not the architectural owner of
shared platform behavior. Shared code that currently lives behind
wedge-specific assumptions must be extracted to the common platform boundary
before additional pattern integrations duplicate it.

## 7. Integration Definition of Done for a new Robot-capable pattern

A pattern is not considered Robot-integrated until all applicable gates are
proven through the common path:

- ordinary Scanner signal reaches the normal Telegram feed;
- signal presentation follows the shared format;
- a durable candidate is created only when executable;
- `🤖 Робот` refers to that real candidate;
- acceptance/rejection feedback is delivered;
- candidate appears in common monitoring;
- entry uses the common execution owner;
- full-position protection is proven;
- open-position card uses the common position surface;
- open/close lifecycle notifications use the common notification surface;
- Robot and Scanner controls remain functional;
- restart/reconcile preserves ownership and lifecycle;
- mandatory owner-run full Scanner/PAPER acceptance is completed under the
  existing acceptance rules.

Pattern-specific tests verify strategy rules. Shared UX/lifecycle behavior
should be verified primarily once at the platform contract boundary, plus a
small adapter-conformance matrix, instead of being copied into one test suite
per pattern.

## 8. Current migration direction

1. Keep Wedge behavior working while extracting common platform contracts.
2. Ikigai Box and L-shape must connect through the same adapter boundary,
   preserving their own trading rules.
3. Triangle and future patterns use the same integration path.
4. Do not add one-off Telegram/Robot fixes to an individual pattern when the
   requirement is platform-level.

## 9. Known acceptance findings — 2026-09-27

- The state-aware Scanner Pause/Resume command works, but the visible Telegram
  Menu button can disappear in the already-open chat; draft PR #271 addresses
  the common menu persistence boundary.
- An Ikigai Box signal displayed a `🤖 Робот` control that acted as Robot
  status rather than candidate admission because Box is not yet part of the
  current Robot state-machine supported-pattern set. This is a UX contract
  violation and evidence for the common adapter migration.
- These findings must be fixed at the shared boundary, not separately for each
  pattern.

## 10. Safety

This standard does not authorize LIVE trading, new risk parameters or runtime
starts by agents. Existing PAPER/LIVE authority, fail-closed rules, manual
owner runtime ownership and acceptance requirements remain unchanged.
