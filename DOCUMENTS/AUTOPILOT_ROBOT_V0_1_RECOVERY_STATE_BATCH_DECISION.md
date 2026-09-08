# BybitScanner — Robot v0.1 recovery/state batch decision

Version: 1.0
Date: 2026-09-08
Status: ACCEPTED DESIGN / PAPER PROTOTYPE
Implementation authorization: NONE

## Scope

This decision batches minor Robot v0.1 lifecycle/recovery semantics that follow the already accepted fail-closed, reuse-first architecture.

## Accepted decisions

### 1. First-run state

If no durable Robot runtime state exists yet, Robot starts in `ROBOT_STOPPED`.

The first transition to active automation requires an explicit user action through `Запустить робота`.

### 2. Restart from `ROBOT_STOPPED`

`Запустить робота` only attempts the transition to `RUNNING/READY`.

It does not:
- revive old `WAITING_BREAKOUT` candidates;
- scan historical signals and auto-approve them;
- adopt manual PAPER positions as robot-owned;
- recreate prior automation intent.

New robot work can begin only from a new explicit approval of a specific signal snapshot.

### 3. Reconciliation gate before restart

If the authoritative PAPER account state still contains position/protection evidence that conflicts with the completed `ROBOT_STOPPED` state, restart is fail-closed.

Robot remains inactive with a reconciliation-required state/reason until the shared authoritative PAPER state confirms the account state needed for safe restart, including confirmed `FLAT` for robot-owned exposure expected to have been closed by emergency stop.

Robot must not automatically take such surviving exposure back under automation ownership.

### 4. Ambiguity handling

At startup, restart, or recovery, any ambiguity in authoritative position, protection, execution, ownership, or reconciliation state blocks new approvals and entries.

No robot-specific repair path, guessed state reconstruction, blind retry, or second trading/state engine is introduced.

### 5. Ownership / reuse boundary

Robot owns only orchestration/lifecycle decisions around whether automation may be active.

The following remain authoritative shared capabilities:
- PAPER position state;
- protection state;
- execution lifecycle;
- reconciliation;
- account state;
- sizing;
- ownership/control state where already defined by the common trading architecture.

## Resulting state contract

Conceptually:

```text
NO_DURABLE_STATE
  -> ROBOT_STOPPED

ROBOT_STOPPED
  -- explicit user start + authoritative state safe/ready --> RUNNING/READY
  -- ambiguous/conflicting authoritative state ----------> RECONCILIATION_REQUIRED

RECONCILIATION_REQUIRED
  -- confirmed safe authoritative state -----------------> eligible for explicit start
```

Old stopped candidates never revive through these transitions.

# END_OF_DOCUMENT
