# BybitScanner — Robot v0.1 post-entry management simplification decision

Version: 1.0
Date: 2026-09-08
Status: ACCEPTED DESIGN / PAPER PROTOTYPE
Implementation authorization: NONE

## Scope

This decision intentionally simplifies Robot v0.1 PAPER post-entry management so the prototype can be launched quickly and the entry logic can be evaluated without additional management layers.

All previously accepted entry, partial-fill, top-up, STOP, TAKE, ownership, recovery, and fail-closed execution decisions remain in force unless explicitly contradicted here.

## 1. Core post-entry rule

Once a Robot v0.1 PAPER position is open and its accepted protective orders are established, normal strategy management has exactly two price boundaries:

- STOP;
- TAKE.

The position remains open until one of those boundaries closes it, except for already accepted manual takeover or emergency/safety behavior.

Conceptually:

```text
POSITION_OPEN
  -> STOP hit -> CLOSED_BY_STOP
  -> TAKE hit -> CLOSED_BY_TAKE
```

## 2. Explicitly excluded from Robot v0.1 PAPER

The prototype does not add any of the following normal strategy-management layers:

- trailing STOP;
- automatic break-even move;
- time-stop;
- profit-percentage-based STOP movement;
- R-multiple-based STOP movement;
- discretionary post-entry structural exit;
- dynamic partial profit-taking;
- dynamic TAKE movement;
- adaptive runner logic;
- volatility-based exit;
- additional post-entry confirmation requirements.

These may be researched later, but they are outside Robot v0.1 PAPER and must not delay the prototype.

## 3. STOP

STOP is established according to the already accepted branch-specific Robot v0.1 entry rules.

After entry, normal strategy management does not move STOP merely because price becomes profitable, reaches a particular R multiple, or traverses part of the distance to TAKE.

Previously accepted safety constraints remain valid: later fills/top-ups may never require widening STOP to increase risk. Any protection recovery/emergency behavior remains governed by the existing recovery contract and is not a trading-management feature.

## 4. TAKE

Robot v0.1 PAPER TAKE remains the already accepted fixed target derived from 90% realization of the scanner-provided pattern potential in the immutable signal snapshot.

Normal post-entry management does not move this target.

## 5. No normal time exit

There is no normal strategy time-stop in Robot v0.1 PAPER. A position that reaches neither STOP nor TAKE remains open under its fixed protection/target until one of the already accepted terminal events occurs.

## 6. Terminal exceptions that remain valid

This simplification does not remove previously accepted non-strategy safety/ownership exits, including:

- explicit manual takeover by the user;
- explicit emergency close;
- protection-failure emergency behavior;
- account/order-state ambiguity and reconciliation safeguards;
- Robot stop / account-wide emergency behavior already specified elsewhere.

These are operational safety/ownership controls, not normal trade-management rules.

## 7. Prototype objective

Robot v0.1 PAPER should test a simple trading hypothesis:

```text
approved wedge signal
-> accepted entry logic
-> fixed STOP
-> fixed TAKE
-> observe outcome
```

Do not add new management sophistication unless a later explicit strategy decision authorizes it.

# END_OF_DOCUMENT
