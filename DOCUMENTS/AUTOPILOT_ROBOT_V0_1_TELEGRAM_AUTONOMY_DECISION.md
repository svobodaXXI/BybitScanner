# AUTOPILOT Robot v0.1 — Telegram autonomy decision

Status: ACCEPTED DESIGN DECISION
Date: 2026-09-08

## Decision

1. `Все позиции` is a separate Telegram screen. The main `Робот` view does not embed the full positions list.
2. The only user approval for a scanner signal is pressing the `Робот` button next to that scanner signal.
3. After that approval, Robot v0.1 autonomously owns the signal lifecycle. There is no second confirmation immediately before entry.
4. For an approved Falling Wedge 1m candidate, the robot waits for the previously specified breakout condition and then automatically submits the PAPER entry through the common authoritative execution path, creates/synchronizes protection through existing common STOP/TAKE capabilities, and manages the trade until close or explicit manual intervention.
5. Telegram remains the control/presentation surface; it must not become a second source of truth for trade state.

## Lifecycle implication

`SCANNER_SIGNAL -> USER_PRESSES_ROBOT -> APPROVED -> WAITING_BREAKOUT -> ENTRY_PENDING -> OPEN -> EXIT_PENDING -> CLOSED`

No `WAITING_CONFIRMATION` / second-entry-confirmation state exists in Robot v0.1.

## UI implication

- Main `Робот` screen: currently selected candidate/position and its full status/details/actions.
- `Все позиции`: separate screen using the previously accepted ranking policy.
