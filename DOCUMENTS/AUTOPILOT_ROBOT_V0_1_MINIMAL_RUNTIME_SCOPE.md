# BybitScanner — Robot v0.1 minimal runtime scope

Version: 1.0
Date: 2026-09-08
Status: ACCEPTED DESIGN / PAPER PROTOTYPE SCOPE
Implementation authorization: NONE

## Purpose

Define the smallest useful Robot v0.1 PAPER runtime needed to validate the end-to-end strategy quickly, without expanding into secondary UX, analytics, advanced management, or LIVE behavior.

This document does not authorize implementation. It defines scope only.

## 1. Prototype objective

Robot v0.1 is successful when one approved scanner wedge signal can travel through the full PAPER lifecycle:

```text
scanner signal
-> user gives signal to Robot
-> Robot waits for breakout/retest
-> Robot opens PAPER position using accepted entry policy
-> Robot places STOP and TAKE
-> position closes by STOP or TAKE
-> basic result is saved and reported
```

The prototype is intentionally narrow. The first goal is to prove this loop reliably, not to build the final trading product.

## 2. Required v0.1 runtime capabilities

### 2.1 Signal handoff

- Existing scanner signal remains the source of pattern identity, frozen geometry, timeframe, and potential.
- User action `Робот` transfers one immutable approved signal snapshot to Robot.
- Repeat handoff of the same signal instance is idempotent.
- No new Robot geometry or pattern detector is introduced.

### 2.2 Candidate lifecycle

Minimal states/concepts only as needed to drive behavior:

- waiting for breakout;
- waiting for retest / working entry;
- position open;
- closed / skipped / expired;
- fail-closed reconciliation state when authoritative execution state is uncertain.

Exact enum names are an implementation detail.

### 2.3 Entry execution

Implement only the already accepted Robot v0.1 wedge-entry rules from the authoritative entry-strategy decision:

- Falling Wedge -> LONG;
- Rising Wedge -> SHORT;
- closed 1m breakout event;
- retest LIMIT path;
- LIMIT repositioning every 5 newly closed 1m candles up to apex;
- partial-fill handling with the accepted 10-second / 0.5% Market-completion rule;
- later top-up to no more than 1 WV when allowed;
- confirmation Market fallback;
- accepted RR/reward admission checks;
- same immutable wedge instance and frozen geometry throughout entry lifecycle.

Execution must reuse common PAPER sizing, order lifecycle, market data, instrument metadata, position state, and reconciliation.

### 2.4 Position size

- Intended Robot trade size: 1 WV.
- Aggregate Robot exposure cap: 19 WV.
- Robot does not create a separate sizing engine.

### 2.5 STOP

Only the already accepted branch-specific Robot v0.1 STOP rules are in scope.

- aggressive retest LIMIT branch: breakout-candle extreme +/- 1 tick, with accepted 2% fallback;
- confirmation Market branch: completed retest extreme +/- 1 tick, with accepted 2% fallback;
- later fills may never widen an existing accepted STOP;
- common protection lifecycle only.

### 2.6 TAKE

For Robot v0.1 PAPER:

- TAKE uses the scanner-provided immutable pattern potential;
- target is the accepted 90% realization of scanner potential;
- later fills/top-ups do not rewrite that target;
- no Robot-specific potential engine.

### 2.7 Post-entry management

Keep management deliberately minimal:

```text
POSITION OPEN
-> STOP active
-> TAKE active
-> STOP or TAKE closes the position
```

Out of scope for v0.1:

- trailing stop;
- automatic break-even;
- time-stop;
- dynamic structural exit;
- partial-profit ladder;
- runner logic;
- discretionary strategy management.

Manual takeover and emergency controls may use already accepted shared ownership/safety contracts but do not expand the strategy-management layer.

### 2.8 Persistence and restart

Minimum persistence is required because an open Robot PAPER position must not become ownerless after restart.

- open Robot-owned PAPER position is restored/reconciled from shared authoritative state;
- approved waiting candidate may restore only from its saved immutable snapshot when still valid under accepted recovery rules;
- no retroactive execution of missed offline breakout events;
- Robot stopped state remains durable;
- unresolved state is fail-closed.

Do not build a second account/position persistence subsystem if common runtime state already owns the information.

### 2.9 Basic Telegram Robot UX

Only the minimum previously accepted Telegram surface is needed:

- main menu entry `Робот`;
- feed-style Robot status posts;
- notification when signal is accepted for observation;
- notification when a position opens;
- notification when a position closes;
- basic current/open-position view using already accepted Robot UX contracts;
- STOP/TAKE and entry information in the trade post;
- chart rendering may reuse existing shared chart capability when available.

Do not build a new terminal UX or competitor-inspired interface for v0.1.

### 2.10 Basic trade record

Persist only the accepted minimal fields:

- trade_id;
- source signal snapshot id/reference;
- symbol;
- direction;
- pattern;
- timeframe;
- signal time;
- entry time;
- entry type;
- actual size in WV;
- authoritative average entry;
- STOP;
- TAKE;
- exit time;
- exit price;
- exit reason;
- PnL USDT;
- PnL percent;
- fees/costs when already available from shared accounting/execution.

No full trading-diary schema is required for launch.

## 3. Safety/runtime invariants that remain mandatory

Speed of prototype delivery does not remove the existing core safety invariants:

- PAPER only for Robot v0.1;
- no implicit LIVE authorization;
- no blind retry after ambiguous order action;
- no duplicate Robot order-state engine;
- authoritative reconciliation before exposure increase when state is uncertain;
- active STOP protection must follow accepted protection-recovery contract;
- STOP/TAKE terminal event prevents further entry/top-up for the same wedge instance;
- same idea never exceeds accepted 1 WV intended trade size;
- aggregate Robot exposure remains <= 19 WV.

These are infrastructure safety constraints, not additional trading-strategy bureaucracy.

## 4. Explicitly out of scope for first working prototype

Do not delay v0.1 for:

- LIVE execution;
- standalone Android APK;
- advanced diary UI;
- advanced statistics/dashboarding;
- strategy optimizer;
- ML/AI ranking;
- portfolio allocation engine beyond existing 19 WV cap;
- dynamic trailing/break-even management;
- advanced chart interaction;
- new scanner patterns;
- final mobile/desktop UX polish;
- competitor UX features;
- automated strategy research pipeline;
- complex notification preferences;
- production-grade multi-node deployment.

These may be added after the basic PAPER loop has produced real operating experience.

## 5. Recommended implementation order when runtime authorization is later granted

Implementation should be sliced by dependency, not attempted as one large rewrite:

1. immutable scanner-signal handoff + Robot candidate state;
2. breakout/retest observation using existing market data;
3. PAPER entry orchestration using shared order lifecycle;
4. STOP/TAKE attachment and protection verification;
5. close/outcome capture;
6. minimal Telegram status/reporting;
7. restart/reconciliation acceptance;
8. end-to-end PAPER acceptance on real scanner signals.

Each slice should reuse existing capabilities and avoid building final-product extras before the end-to-end loop works.

## 6. Prototype completion criterion

Robot v0.1 PAPER can be called functionally complete when repeated real scanner signals can reliably demonstrate:

```text
approve signal
-> observe
-> enter according to accepted strategy
-> protect with STOP + TAKE
-> close by one boundary
-> save basic result
-> report outcome
-> recover safely across restart/ambiguity
```

Everything beyond this is a later iteration unless a defect blocks this loop.

# END_OF_DOCUMENT
