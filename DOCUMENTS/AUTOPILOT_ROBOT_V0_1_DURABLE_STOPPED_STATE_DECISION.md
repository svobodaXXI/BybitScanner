# BybitScanner — Robot v0.1 Durable STOPPED State Decision

Version: 1.0
Date: 2026-09-08
Status: ACCEPTED DESIGN / PAPER PROTOTYPE
Implementation authorization: NONE

## Decision

`ROBOT_STOPPED` is a durable robot-runtime state. It survives process restarts, scanner restarts, and PC restarts.

After the user confirms `Остановить робота` and the shared PAPER account state is confirmed `FLAT`:

- persist `ROBOT_STOPPED`;
- reject new signal approvals while stopped;
- do not restore prior `WAITING_BREAKOUT` candidates after restart;
- do not auto-enable Robot because the scanner/runtime process restarted;
- re-enable Robot only through an explicit user action such as `Запустить робота`;
- after re-enable, only new approvals may create new candidates; previously stopped/cleared candidates do not revive.

If stop/close processing is ambiguous or reconciliation is incomplete, Robot remains fail-closed and must not transition to active trading until authoritative shared state is reconciled.

## Ownership / reuse boundary

Robot owns only its durable orchestration mode (`RUNNING` / `ROBOT_STOPPED`) and candidate lifecycle policy.

It must not create a second account-position, protection, execution, or reconciliation source of truth. Account-wide close and `FLAT` confirmation continue to use the existing common PAPER execution/state/protection mechanisms.

## Rationale

A process restart is an infrastructure event and must not silently cancel an explicit user emergency-stop intent. Durable `ROBOT_STOPPED` therefore preserves user authority across restarts and prevents accidental automatic resumption.

# END_OF_DOCUMENT
