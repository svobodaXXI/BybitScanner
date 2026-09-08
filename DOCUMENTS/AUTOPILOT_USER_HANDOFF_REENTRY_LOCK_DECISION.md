# AUTOPILOT User Handoff Re-entry Lock Decision

Date: 2026-09-08
Status: ACTIVE / DESIGN-ONLY
Implementation authorization: NONE

## Decision

When the user selects `Взять управление текущей сделкой`, ownership of that already-open AUTOPILOT position is transferred from the robot to the user without closing or reopening the position.

After this handoff, AUTOPILOT must not enter the same ticker again while the handed-off user-controlled position remains open.

The re-entry lock is ticker-scoped and remains active until the user fully closes the handed-off position.

Once the handed-off position is fully closed, the ticker becomes eligible for future AUTOPILOT entries again, subject to all ordinary strategy and risk-engine gates.

## Safety invariant

There must never be simultaneous robot re-entry on the same ticker while the user is still managing the handed-off open position.

The handoff must therefore establish explicit user ownership and a corresponding AUTOPILOT re-entry lock that survives UI navigation and backend/runtime restarts until authoritative position state confirms the user-controlled position is fully closed.
