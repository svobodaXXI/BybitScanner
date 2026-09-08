# Robot v0.1 All Positions UI Decision

Status: ACTIVE / DESIGN-ONLY
Date: 2026-09-08
Implementation authorization: NONE

## Accepted decision

The Telegram Scanner bot `Robot` section includes an `All positions` control.

Opening `All positions` shows all current PAPER positions for the active PAPER account, using the existing authoritative PAPER account/position state rather than a robot-specific duplicate store.

From this view the user can:
- select a position;
- close the selected position;
- close all positions;
- navigate between positions and inspect their primary state.

Selecting another position changes only UI selection state. The position source of truth remains the existing PAPER account state.

After a position is selected, the `Robot` feed posts or refreshes a full position-status card for that selected position with the previously accepted information where applicable:
- symbol;
- pattern/source metadata;
- direction;
- volume;
- entry;
- STOP;
- TAKE;
- lifecycle/status;
- PnL;
- fees;
- funding;
- chart/visual state.

For positions not created by the robot, robot-only fields such as pattern metadata may be absent or explicitly identified as manual/non-robot origin rather than fabricated.

`Close all positions` must use the same common PAPER account-wide market-close capability used by Robot v0.1 emergency stop; it must not implement a second bulk-close lifecycle.

# END_OF_DOCUMENT
