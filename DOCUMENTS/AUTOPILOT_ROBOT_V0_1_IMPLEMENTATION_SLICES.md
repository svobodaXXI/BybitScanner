# BybitScanner — Robot v0.1 implementation slices

Version: 1.0
Date: 2026-09-08
Status: IMPLEMENTATION PLAN ONLY
Runtime implementation authorization: NONE

## Purpose

This document converts the already accepted Robot v0.1 PAPER scope into a minimal dependency-ordered implementation plan. It does not authorize runtime code changes.

The implementation must reuse existing Scanner, Terminal/PAPER execution, authoritative market data, sizing, order lifecycle, STOP/TAKE, position state, accounting, reconciliation and Telegram capabilities wherever they already exist. Robot adds orchestration/policy, not duplicate infrastructure.

## Slice 1 — Signal handoff and candidate persistence

Goal: accept an approved Scanner wedge signal into Robot as an immutable snapshot and persist the minimum candidate state.

Includes:
- `Робот` action from an eligible Scanner signal;
- idempotent handoff of one immutable signal/pattern instance;
- required fields for frozen geometry, timeframe, direction, scanner potential and signal identity;
- minimal Robot enabled/stopped gate;
- reject duplicate same-instance approval;
- durable candidate state needed for restart;
- no order placement yet.

Acceptance: approved signal can enter Robot once, survive restart when valid, and remain non-trading.

## Slice 2 — Breakout/retest state machine

Goal: advance an approved candidate using closed 1m market data through the accepted pre-entry lifecycle.

Includes:
- WAITING_BREAKOUT;
- qualifying breakout close using frozen geometry;
- WAITING_RETEST;
- retest detection using frozen boundary evaluated at current candle coordinate;
- apex expiry;
- no execution yet.

Acceptance: deterministic state transitions can be replayed from authoritative market data without creating orders.

## Slice 3 — Initial retest LIMIT entry

Goal: place and maintain the first PAPER entry LIMIT through shared execution.

Includes:
- initial retest LIMIT;
- current-coordinate frozen-boundary price;
- 5 closed-1m-candle reposition cadence;
- LONG/SHORT symmetric tick offsets;
- authoritative amend/cancel/reconciliation;
- no blind retry;
- no duplicate Robot order-state engine.

Acceptance: one candidate can maintain at most one authoritative entry LIMIT and never duplicate exposure because of ambiguous transport.

## Slice 4 — Partial fill completion and top-up

Goal: implement the already accepted fill-completion rules without adding new strategy behavior.

Includes:
- 10-second remainder wait after authoritative partial fill;
- Market completion only when adverse deterioration <= 0.5% and whole-position RR remains >= 1.0;
- authoritative cancellation of remainder before Market completion;
- reduced-size position when Market completion is not admissible;
- later LIMIT top-up toward, never above, 1 WV;
- same 5-candle reposition rule to apex;
- same partial-fill completion rule for later top-ups;
- STOP/TAKE/apex terminal effects on further top-up.

Acceptance: total Robot size for one idea never exceeds 1 WV and all exposure increases are blocked while state is ambiguous/reconciling.

## Slice 5 — Confirmation Market path

Goal: add the alternative confirmed-retest Market entry without racing the LIMIT path.

Includes:
- closed 1m confirmation after retest;
- authoritative LIMIT cancellation before Market fallback;
- RR >= 1.0 gate;
- minimum expected reward >= 1% gate;
- shared PAPER Market execution;
- underfill may use the same later top-up mechanism.

Acceptance: LIMIT and Market paths are mutually exclusive execution routes for the same immutable idea.

## Slice 6 — STOP/TAKE protection

Goal: make every filled Robot position immediately use the already accepted two-boundary prototype management.

Includes:
- aggressive LIMIT branch STOP from breakout-candle extreme +/- 1 tick, with accepted 2% fallback;
- confirmation Market branch STOP from completed retest extreme +/- 1 tick, with accepted 2% fallback;
- Robot v0.1 PAPER TAKE from frozen Scanner pattern potential at 90% realization;
- shared STOP/TAKE lifecycle and quantity synchronization;
- no trailing, break-even, time-stop or additional structural exit;
- existing protection recovery/emergency contract reused.

Acceptance: after entry, normal strategy management is only STOP or TAKE; protection failure follows the already accepted fail-closed recovery contract.

## Slice 7 — Telegram Robot minimum UX

Goal: expose enough information to operate and observe the PAPER prototype.

Includes:
- `Робот` menu entry;
- feed posts for signal accepted, position opened and position closed;
- `Все позиции`;
- `Под наблюдением`;
- current-state post with chart using reusable chart/rendering capabilities;
- selected-position close and already accepted emergency controls;
- no advanced diary UI.

Acceptance: the user can see candidate/trade state and basic result without opening development tooling.

## Slice 8 — Minimal trade record and restart closure

Goal: persist the minimum prototype result set and prove recovery end-to-end.

Includes baseline fields only:
- trade_id;
- symbol;
- direction;
- pattern;
- timeframe;
- signal time;
- entry time and entry type;
- actual WV;
- average entry;
- STOP;
- TAKE;
- exit time and price;
- exit reason;
- PnL USDT / PnL %;
- shared fees/costs when already available;
- source Scanner signal snapshot id/reference.

Also includes:
- restart recovery for waiting candidates permitted by accepted contracts;
- authoritative restoration/reconciliation of open Robot PAPER positions;
- durable ROBOT_STOPPED semantics;
- end-to-end PAPER acceptance from signal to CLOSED.

Acceptance: a complete PAPER trade survives restart/reconciliation and produces a minimal durable result record.

## Explicitly deferred from v0.1 launch

Do not block prototype launch on:
- LIVE execution;
- advanced trade diary;
- rich statistics/analytics;
- trailing/break-even/time-stop;
- dynamic post-entry management;
- new pattern families;
- APK/standalone mobile app;
- advanced chart/editor UX;
- strategy optimization;
- portfolio/correlation logic beyond already accepted Robot exposure cap;
- cosmetic polish not required for acceptance.

## Implementation rule

When runtime implementation is explicitly authorized, execute exactly one dependent slice at a time. Each slice must reuse existing authoritative capabilities first, have targeted tests/verification, and avoid unrelated changes.

# END_OF_DOCUMENT
