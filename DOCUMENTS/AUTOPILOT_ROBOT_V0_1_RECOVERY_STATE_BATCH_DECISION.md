# BybitScanner — Robot v0.1 recovery/state batch decision

Version: 1.1
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

STOP_NOT_PROVEN
  -- safe reconciliation/recovery, < 5 s ----------------> STOP_PROVEN
  -- intended STOP crossed before deadline --------------> EMERGENCY_MARKET_CLOSE
  -- STOP still not proven at 5 s ------------------------> EMERGENCY_MARKET_CLOSE

EMERGENCY_MARKET_CLOSE
  -> shared execution/reconciliation
  -> confirmed authoritative FLAT

STOP_PROVEN + TAKE_NOT_PROVEN
  -> position may remain open
  -> safe TAKE reconciliation/recovery
```

Old stopped candidates never revive through these transitions.

# END_OF_DOCUMENT
