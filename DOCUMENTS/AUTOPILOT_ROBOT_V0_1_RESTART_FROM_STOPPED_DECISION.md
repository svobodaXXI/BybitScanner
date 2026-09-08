# BybitScanner — Robot v0.1 restart-from-stopped decision

Version: 1.0
Date: 2026-09-08
Status: ACCEPTED DESIGN / PAPER PROTOTYPE
Implementation authorization: NONE

## Decision

After Robot v0.1 has reached durable `ROBOT_STOPPED`, the explicit user action `Запустить робота` only re-enables the robot runtime and transitions it to a ready/running state for future approvals.

Accepted semantics:

1. `ROBOT_STOPPED` is not cleared by process or PC restart; it is cleared only by an explicit user start action.
2. Starting the robot does not restore or reactivate any candidate that was cancelled/cleared by the prior stop operation.
3. Previously stopped `WAITING_BREAKOUT` candidates remain terminal and must not re-enter the active candidate set.
4. The robot must not scan historical signals and must not auto-adopt old scanner signals merely because they would still satisfy age or geometry conditions.
5. Existing manual PAPER positions remain manual and must not become robot-owned as a side effect of robot start.
6. New robot activity begins only from a new explicit approval of a concrete scanner signal snapshot through the existing `Робот` handoff flow.
7. If authoritative PAPER account/position/protection state is not ready, is ambiguous, or is reconciling, start remains fail-closed: the robot must not admit new automated entries until the shared authoritative state is usable.

Conceptually:

```text
ROBOT_STOPPED
  -- explicit user Start -->
RUNNING / READY
  -- new signal approval -->
WAITING_BREAKOUT
```

There is no transition from old stopped candidates back into `WAITING_BREAKOUT`.

## Reuse / ownership boundary

This decision changes only Robot orchestration state. It does not create any alternate trading engine or duplicate source of truth.

The robot continues to reuse authoritative project capabilities for:
- account readiness;
- PAPER position state;
- protection state;
- execution;
- reconciliation;
- ownership/controller state.

## Rationale

Emergency stop must terminate the prior automation intent completely. Re-enabling the robot later should mean “accept new work from now on”, not “resume every old signal that used to be approved”. This avoids delayed or surprising entries after a stop/restart cycle and keeps user intent explicit and deterministic.

# END_OF_DOCUMENT
