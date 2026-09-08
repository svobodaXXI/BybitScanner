# BybitScanner — Robot v0.1 recovery/state batch decision

Version: 1.3
Date: 2026-09-08
Status: ACCEPTED DESIGN / PAPER PROTOTYPE
Implementation authorization: NONE

## Scope

This decision batches Robot v0.1 lifecycle, recovery, and post-entry protection semantics that follow the already accepted fail-closed, reuse-first architecture.

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
- market data;
- instrument metadata and order normalization;
- ownership/control state where already defined by the common trading architecture.

Robot must not create a separate price feed or protection execution/reconciliation path for this recovery policy.

### 6. Filled entry with STOP not yet proven

Once a Robot entry is authoritatively `FILLED`, the intended STOP remains mandatory, but Robot v0.1 may temporarily hold the position while the shared execution/protection state is being safely resolved.

The maximum interval in which the robot-owned position may remain open without an authoritative proven STOP is **5 seconds** from the point at which the filled entry requires protection.

During that interval:
- an ambiguous STOP result is reconciled before any further mutation;
- blind STOP retry is forbidden;
- Robot uses the common authoritative protection/execution/reconciliation capability rather than a Robot-specific repair path.

If the correct STOP becomes authoritative within the allowed window, normal position management may continue.

### 7. Early emergency exit before the 5-second deadline

The 5-second interval is a maximum recovery window, not a mandatory waiting period.

If, while STOP is still not authoritative, the shared authoritative market price reaches or crosses the already calculated intended STOP level, Robot must immediately initiate `EMERGENCY MARKET CLOSE` rather than wait for the remaining recovery time.

Direction semantics:
- LONG: emergency condition when authoritative market price is at or below intended STOP;
- SHORT: emergency condition when authoritative market price is at or above intended STOP.

This comparison uses the existing shared authoritative market-data source. Robot does not own a second price source.

### 8. STOP recovery deadline

If 5 seconds expire and the required STOP still cannot be authoritatively proven, Robot must initiate `EMERGENCY MARKET CLOSE` through the common PAPER execution path.

After an emergency close request:
- ambiguity remains fail-closed and enters reconciliation;
- no blind close resend is allowed;
- Robot does not declare the position safely closed from command acceptance alone;
- the lifecycle remains recovery/reconciliation constrained until the shared authoritative PAPER position state confirms `FLAT`.

### 9. TAKE failure with authoritative STOP

Failure or ambiguity of TAKE does not by itself require emergency liquidation when the correct STOP is already authoritative.

In that case:
- the position may remain open under the authoritative STOP;
- TAKE recovery/reconciliation uses only the common protection lifecycle;
- blind TAKE retry is forbidden;
- Robot must not weaken, remove, or replace the proven STOP merely to repair TAKE.

STOP protection therefore has higher safety priority than TAKE restoration in the post-entry recovery sequence.

### 10. Terminal disposition after protection emergency close

Once a post-entry STOP-protection failure has caused emergency liquidation and the shared authoritative PAPER state confirms `FLAT`, that exact robot trading idea is terminally closed as `CLOSED_EMERGENCY_PROTECTION_FAILURE`.

For that exact immutable signal/pattern instance:
- no re-entry is permitted;
- a later breakout event cannot reactivate it;
- repeated delivery/approval of the same pattern instance remains idempotently ignored;
- the robot may continue operating on unrelated valid ideas if all common risk/state gates remain satisfied.

A later trade on the same symbol is permitted only from a genuinely new signal/pattern instance under the normal admission rules.

### 11. No emergency timeout for TAKE-only recovery

When the intended STOP is already authoritative, Robot v0.1 does not impose a separate emergency-close timeout solely because TAKE is missing, ambiguous, or still being reconciled.

The position may remain open under the proven STOP until one of the normal lifecycle outcomes occurs, including:
- TAKE becomes safely authoritative through the common lifecycle;
- STOP closes the position;
- the user closes the position through an already-authorized common control path;
- another already-defined common close/emergency rule closes the position.

Robot must not invent a TAKE-only market-liquidation timer or a second recovery mechanism.

### 12. Loss of an already-proven STOP

If a STOP was authoritative for an open robot-owned position and later becomes absent, invalid, cancelled, stale, ambiguous, or otherwise cannot be authoritatively proven, the position immediately re-enters the same `STOP_NOT_PROVEN` safety contract.

There is no softer recovery branch merely because the STOP had previously existed.

The same rules apply:
- at most 5 seconds to safely re-establish/prove the intended STOP;
- no blind STOP retry;
- immediate emergency close if the intended STOP level is reached/crossed before recovery;
- emergency close at the 5-second deadline if STOP is still not proven;
- confirmed authoritative `FLAT` is required before the emergency lifecycle is complete.

### 13. Loss of authoritative market data while STOP is unproven

If an open robot-owned position has no proven STOP and the shared authoritative market-data state becomes unavailable, stale, ambiguous, or `UNKNOWN`, Robot must not consume the remaining STOP recovery window blind.

It must immediately initiate `EMERGENCY MARKET CLOSE` through the common PAPER execution path and reconcile until authoritative `FLAT` is confirmed.

No Robot-specific fallback price feed is permitted.

### 14. Account-wide gate during unresolved emergency exposure

While any robot-owned emergency close remains unresolved, ambiguous, `UNKNOWN`, or still under reconciliation, Robot must block **all new approvals and all new entries for the entire active PAPER account**.

This is an admission/risk gate only. It does not automatically liquidate other already-open robot positions that remain safely protected.

### 15. Other already-open robot positions during one-position emergency

A protection emergency on one position does not trigger account-wide emergency flatten by itself.

Other already-open robot positions:
- remain open if their authoritative state is healthy;
- keep their existing proven STOP/TAKE lifecycle;
- continue normal shared protection management;
- independently enter their own emergency path if their own protection/state becomes unsafe.

Robot therefore freezes new risk while preserving correctly protected existing exposure.

### 16. Reopening the account-wide admission gate

New Robot approvals/entries may resume only when all of the following are true:
- the affected emergency-close position is authoritatively `FLAT`;
- its emergency execution/reconciliation lifecycle is terminally resolved;
- the shared authoritative PAPER account state is no longer `UNKNOWN`/`RECONCILING` for the relevant safety domains;
- no residual robot-owned exposure or protection ambiguity requiring reconciliation remains;
- ordinary Robot admission/risk gates are otherwise satisfied.

A confirmed `FLAT` event alone is not enough if the common account state is still materially ambiguous.

### 17. Prolonged or unresolved emergency reconciliation

There is no timeout that permits Robot to resume new trading merely because reconciliation has taken too long.

If authoritative safety cannot be proven, Robot remains fail-closed. The durable condition is treated as `RECONCILIATION_REQUIRED` (or the common equivalent), with new approvals/entries blocked until authoritative safety is restored.

Restart must not bypass this gate or auto-resume Robot activity.

### 18. No blind emergency-close resend

Emergency close follows the existing shared execution/reconciliation ownership rules.

An ambiguous command result is reconciled rather than blindly repeated. A later close mutation is permitted only if authoritative reconciliation proves residual open quantity that still requires a new close command under the common execution lifecycle.

### 19. Recovery-block policy principle

For Robot v0.1, non-strategic recovery details in this protection-failure block default to the existing shared fail-closed/reuse-first architecture without requiring separate user confirmation.

User confirmation remains required only when a choice would materially change trading strategy, risk sizing, STOP/TAKE semantics, emergency liquidation scope, ownership/control, LIVE execution boundaries, or another decision with direct financial consequence.

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

ENTRY_FILLED
  -> establish/prove intended STOP through shared protection lifecycle

STOP_PROVEN
  -- STOP later becomes unproven -------------------------> STOP_NOT_PROVEN

STOP_NOT_PROVEN
  -- safe reconciliation/recovery, < 5 s ----------------> STOP_PROVEN
  -- intended STOP crossed before deadline --------------> EMERGENCY_MARKET_CLOSE
  -- market data authority lost --------------------------> EMERGENCY_MARKET_CLOSE
  -- STOP still not proven at 5 s ------------------------> EMERGENCY_MARKET_CLOSE

EMERGENCY_MARKET_CLOSE
  -> block all new Robot approvals/entries account-wide
  -> shared execution/reconciliation
  -> confirmed authoritative FLAT
  -> common account safety/reconciliation proven
  -> CLOSED_EMERGENCY_PROTECTION_FAILURE for affected idea
  -> ordinary Robot admission may resume

CLOSED_EMERGENCY_PROTECTION_FAILURE
  -> same immutable signal/pattern instance can never re-enter

STOP_PROVEN + TAKE_NOT_PROVEN
  -> position may remain open without a TAKE-only emergency timeout
  -> safe TAKE reconciliation/recovery through shared protection lifecycle
```

Old stopped candidates never revive through these transitions.

# END_OF_DOCUMENT
