# Robot v0.1 Emergency Stop Decision

Status: ACTIVE / DESIGN-ONLY
Date: 2026-09-08
Implementation authorization: NONE

## Scope

This decision applies only to the near-term PAPER Robot v0.1 Telegram prototype. It does not authorize LIVE behavior.

## Accepted controls

Robot v0.1 exposes two separate manual controls in the Telegram `Робот` surface:

1. `Закрыть позицию`
   - applies only to the selected robot-controlled PAPER position;
   - requires explicit confirmation;
   - routes through the existing common PAPER Market Close lifecycle;
   - successful completion records the robot trade as `CLOSED_MANUAL`.

2. `Остановить робота`
   - is an account-level emergency stop, not a simple strategy pause;
   - requires explicit confirmation with the exact user-facing meaning:
     `Остановить робота и закрыть все позиции по рынку?`;
   - confirmation choices are `Подтвердить` and `Отмена` (wording may be adapted cosmetically without changing semantics).

## Emergency-stop semantics

After the user confirms `Остановить робота`:

1. latch Robot state to `STOPPING` before issuing any exposure-increasing action;
2. reject new approvals and new robot entries while `STOPPING`;
3. close all currently open PAPER positions on the active PAPER account by Market Close through the existing common execution lifecycle;
4. "all positions on the account" is literal and includes non-robot/manual PAPER positions if any are open on other symbols;
5. cancel/clear remaining robot candidates and any remaining protection/order state that is no longer applicable after account flattening, using existing authoritative order/protection lifecycles rather than a robot-specific duplicate mechanism;
6. reconcile authoritative PAPER account state;
7. transition to `ROBOT_STOPPED` only after the account is confirmed FLAT and relevant robot/protection cleanup is reconciled.

If flattening or reconciliation is incomplete or ambiguous, Robot must remain fail-closed in `STOPPING`/error-reconciliation state and must not silently report `ROBOT_STOPPED`.

## Architecture constraints

- Telegram is presentation/control only and must not become the authoritative position state.
- Robot must reuse existing PAPER position, Market Close, STOP/TAKE, accounting and reconciliation capabilities.
- No separate `robot_close_all` position engine or duplicate position ledger is introduced.
- This emergency-stop command is intentionally distinct from future non-destructive pause/resume controls.

# END_OF_DOCUMENT
