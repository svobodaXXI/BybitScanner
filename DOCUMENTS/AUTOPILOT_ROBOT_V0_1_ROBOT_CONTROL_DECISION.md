# BybitScanner — Robot v0.1 Robot Control Decision

Version: 1.2
Date: 2026-09-11
Status: ACCEPTED DESIGN
Implementation authorization: NONE

## Scope

`AUTOPILOT_ROBOT_V0_1_RESTART_FROM_STOPPED_DECISION.md` and `AUTOPILOT_ROBOT_V0_1_RECOVERY_STATE_BATCH_DECISION.md` already require that the first transition to active automation happen only through an explicit user action (`Запустить робота`), but neither document specifies the full set of operator control commands or their exact legality/effects. This decision records the accepted semantics of the Robot v0.1 lifecycle control commands: `start_robot()`, `pause_robot()`, `resume_robot()`, `close_all_now()`, and `stop_robot()`.

This is a design contract only. It does not authorize implementation of the Telegram commands/buttons that will invoke these operations; that remains a separate, later implementation task.

**Amendment (v1.0 → v1.1):** v1.0 defined only three commands and let a single `stop_robot()` call also trigger an immediate Market close of an open Robot-owned position (v1.0 Section 3). v1.1 splits that into two independent commands: a new explicit `close_all_now()` that forces an immediate Market close, and a redefined `stop_robot()` that only disengages admission when no position is open. The original v1.0 Section 3 text is preserved below for decision history and is superseded by Section 4 (`close_all_now()`) and Section 5 (`stop_robot()`, v1.1).

**Amendment (v1.1 → v1.2):** v1.1 left the paused state (Section 2) with no defined way back other than `stop_robot()` fully disengaging the robot. v1.2 adds `resume_robot()` (Section 6), the symmetric counterpart to `pause_robot()`: it is legal only from the paused state and returns admission to `READY`/`ROBOT_RUNNING`, mirroring the single-legal-source-state pattern already accepted for `start_robot()` (Section 1). No other section's behavior changes.

## 1. start_robot()

Legal only from durable state `ROBOT_STOPPED`.

From any other durable state, including `RECONCILIATION_REQUIRED`, `start_robot()` is rejected with an explicit error and produces no side effect on durable state.

Recovering out of `RECONCILIATION_REQUIRED` remains a separate, unresolved problem. It is explicitly out of scope for this decision. `start_robot()` must not attempt, guess, or shortcut that recovery, and must not treat rejection from `RECONCILIATION_REQUIRED` as an invitation to add a bypass.

Reaching `RUNNING`/`READY` after a legal `start_robot()` call continues to follow the already accepted recovery/reconciliation pipeline (`AUTOPILOT_ROBOT_V0_1_RESTART_FROM_STOPPED_DECISION.md`, `AUTOPILOT_ROBOT_V0_1_RECOVERY_STATE_BATCH_DECISION.md`): no old candidate is revived, no manual position is adopted, and any ambiguity in authoritative account state during that pipeline still fails closed into `RECONCILIATION_REQUIRED` rather than a forced `RUNNING`.

## 2. pause_robot()

Legal only from `ROBOT_RUNNING` (or its current durable equivalent, e.g. `RUNNING`/`READY`).

From `RECONCILIATION_REQUIRED`, `pause_robot()` is rejected with an explicit error.

Effect: admission of new candidates stops immediately. No new Scanner signal approval may create a new `WAITING_BREAKOUT` candidate while paused.

An already-open Robot position, if one exists at the moment of pausing, is unaffected by this command. It continues to be managed exclusively by the existing, unmodified STOP/TAKE lifecycle (`AUTOPILOT_ROBOT_V0_1_MANAGEMENT_SIMPLIFICATION_DECISION.md`). `pause_robot()` introduces no new closing logic, no new exit condition, and no change to STOP/TAKE calculation or priority.

Pause is a durable admission gate, not an account-flattening action. It does not itself request any close, cancel, or amend against an open position or a working entry/top-up order.

The exact durable representation of a paused state (a new `mode` value, a `recovery_status`/`reason` overlay on `ROBOT_RUNNING`, or another mechanism) is not specified here and is deferred until implementation authorization. This decision fixes only the accepted behavior above, not its schema encoding.

The reverse transition out of this paused state is `resume_robot()` (Section 6, v1.2 — new). `pause_robot()` itself is unchanged by that addition: it still only ever moves the robot into the paused state defined above.

**SUPERSEDED BY v1.1 SECTION 3/4 BELOW.** The following Section 3 is preserved for decision history only. It no longer governs `stop_robot()` behavior. See Section 4 (`close_all_now()`) and Section 5 (`stop_robot()`, v1.1) below for the current accepted model.

## 3. stop_robot()

Legal only from `ROBOT_RUNNING` or from the paused state defined in Section 2.

From `RECONCILIATION_REQUIRED`, `stop_robot()` is rejected with an explicit error.

### 3.1 No open position

If no Robot-owned position is open at the moment `stop_robot()` is called, the robot transitions immediately to durable `ROBOT_STOPPED`.

### 3.2 Open position

If a Robot-owned position is open, `stop_robot()`:

- initiates an immediate Market close of that position through the existing shared PAPER execution path, without waiting for the existing STOP or TAKE levels to be reached;
- transitions the robot's own runtime mode to `ROBOT_STOPPED` immediately, without waiting for exchange/account confirmation that the close has completed.

Robot runtime mode (`ROBOT_STOPPED`) and the confirmed flat/closed state of that specific position are therefore two independent facts. `ROBOT_STOPPED` stops new admission immediately; it does not by itself assert that every previously open position is already flat.

### 3.3 Market close failure

If the Market close attempt cannot be authoritatively confirmed as filled (for example, the exchange is unreachable, the command result is ambiguous, or the close is rejected), that specific position is handed to `RECONCILIATION_REQUIRED` for manual resolution.

The robot's own runtime mode nonetheless remains `ROBOT_STOPPED`. `stop_robot()` never reverts runtime mode back toward `ROBOT_RUNNING` to retry the close; retry/repair of the close itself follows the existing fail-closed, no-blind-retry recovery contract (`AUTOPILOT_ROBOT_V0_1_RECOVERY_STATE_BATCH_DECISION.md`), not a new mechanism introduced here.

### 3.4 Relationship to the existing emergency/recovery contract

`AUTOPILOT_ROBOT_V0_1_RECOVERY_STATE_BATCH_DECISION.md` establishes that Robot "does not declare the position safely closed from command acceptance alone" for its protection-failure emergency path. Section 3.2 above does not weaken or contradict that: the *position's* closed/flat status still requires authoritative confirmation before it is treated as closed, exactly as before. What this decision adds is that the *robot's own admission gate* (`ROBOT_STOPPED`) does not wait on that confirmation. An explicit user stop must close admission immediately even while the underlying close is still being confirmed or, per Section 3.3, is still unresolved in `RECONCILIATION_REQUIRED`.

## 4. close_all_now() (v1.1 — new)

Legal from `ROBOT_RUNNING` and from the paused state defined in Section 2.

From `RECONCILIATION_REQUIRED`, `close_all_now()` is rejected with an explicit error.

Scope: `close_all_now()` acts exclusively on Robot-owned positions. Manual/non-robot positions open on the same PAPER account are not affected, checked, cancelled, or closed by this command.

Effect: immediately initiates a Market close of any open Robot-owned position through the existing shared PAPER execution path, without waiting for the existing STOP or TAKE levels to be reached.

`close_all_now()` does not by itself change the robot's admission mode. The robot remains in whichever state it was called from — `ROBOT_RUNNING` or paused — once the close has been initiated. Closing exposure and closing admission are independent actions; an operator who wants both must call `close_all_now()` and `pause_robot()`/`stop_robot()` separately, in either order.

If the Market close cannot be authoritatively confirmed as filled (for example, the exchange is unreachable, the command result is ambiguous, or the close is rejected), the affected position is handed to `RECONCILIATION_REQUIRED` for manual resolution, regardless of whether the robot was `ROBOT_RUNNING` or paused at the time of the call.

If no Robot-owned position is open when `close_all_now()` is called, the command is legal but a no-op with respect to execution: there is nothing to close, no order is sent, and admission mode is unchanged.

## 5. stop_robot() (v1.1 — replaces Section 3 above)

Legal only from `ROBOT_RUNNING` or from the paused state defined in Section 2, and only when no Robot-owned position is open at the moment of the call.

If a Robot-owned position is open, `stop_robot()` is rejected with an explicit error instructing the operator to call `pause_robot()` and then `close_all_now()` first. Under v1.1, `stop_robot()` never itself initiates a position close; forcing a close is exclusively the responsibility of `close_all_now()` (Section 4).

From `RECONCILIATION_REQUIRED`, `stop_robot()` is rejected with an explicit error, as in v1.0.

If the precondition is met (no open position, legal source state), `stop_robot()` transitions the robot immediately to durable `ROBOT_STOPPED`.

Because the no-open-position precondition is checked *before* the transition is accepted, rather than resolved as a side effect *of* the transition, this redefinition removes the v1.0 case where `ROBOT_STOPPED` could be asserted while a Market close was still unconfirmed (v1.0 Sections 3.2–3.3). Under v1.1, reaching `ROBOT_STOPPED` via `stop_robot()` always means no Robot-owned position was open at that moment; there is no longer a `stop_robot()` code path that both closes a position and disengages admission in one call.

## 6. resume_robot() (v1.2 — new)

Legal only from the paused state defined in Section 2.

From `RECONCILIATION_REQUIRED`, and from any other durable state (including `ROBOT_STOPPED` and unpaused `ROBOT_RUNNING`), `resume_robot()` is rejected with an explicit error and produces no side effect on durable state — symmetric to the single-legal-source-state rule already accepted for `start_robot()` (Section 1). In particular, `resume_robot()` is not a substitute for `start_robot()`: it never moves the robot out of `ROBOT_STOPPED`, and it never attempts, guesses, or shortcuts recovery out of `RECONCILIATION_REQUIRED`, for the same reasons given in Section 1.

Effect: admission of new candidates resumes immediately. The robot returns to `READY`/`ROBOT_RUNNING`, and Scanner signal approval may again create new `WAITING_BREAKOUT` candidates.

An already-open Robot position, if one exists at the moment of resuming, is unaffected by this command, for the same reason it was unaffected by `pause_robot()` (Section 2): it continued to be managed by the existing, unmodified STOP/TAKE lifecycle throughout the paused interval, and `resume_robot()` introduces no new admission logic beyond re-opening the gate that `pause_robot()` closed.

`resume_robot()` uses whatever durable representation of the paused state is eventually chosen for Section 2 (still deferred to implementation authorization); this decision fixes only that the transition is legal exclusively from that paused representation and lands back on the same `READY`/`ROBOT_RUNNING` durable value `pause_robot()` was called from.

## Durable state consistency

`close_all_now()` reuses existing valid `(mode, recovery_status)` combinations: a failed close while the robot is `ROBOT_RUNNING` lands in `(ROBOT_RUNNING, RECONCILIATION_REQUIRED)`, already valid in the existing Terminal SQLite Robot runtime schema. A failed close while paused lands in whatever durable slot eventually backs the paused-state encoding left open in Section 2; this decision introduces no combination beyond what Section 2 already deferred. On success or as a no-op, `close_all_now()` does not change `mode` at all.

`stop_robot()` v1.1 requires no new `(mode, recovery_status)` pair. Its precondition — no open Robot-owned position — is evaluated by reading existing authoritative position state before the call is accepted, not by encoding a new combination in `robot_runtime_state`. A successful call is a plain transition to `(*, ROBOT_STOPPED)`, the same durable target `stop_robot()` already reached in v1.0 Section 3.1.

The v1.0 mapping is preserved in Section 3 for decision history: `(ROBOT_STOPPED, ROBOT_STOPPED)` for the no-open-position case, and `(ROBOT_STOPPED, RECONCILIATION_REQUIRED)` for a failed forced close inside `stop_robot()` itself. That second combination no longer arises from `stop_robot()` under v1.1 — it now arises only from `close_all_now()` (this section, paragraph 1) — but the combination itself remains valid and unchanged in the schema.

`resume_robot()` (v1.2) likewise requires no new `(mode, recovery_status)` pair. It is a plain transition from whatever durable value backs the Section 2 paused state back to `(READY/ROBOT_RUNNING, *)` — the same durable target `pause_robot()` departed from — and it is legal only when that source value is not `RECONCILIATION_REQUIRED`, consistent with every other command in this decision.

## Reuse / ownership boundary

These commands change only Robot orchestration/admission state. None of them create a duplicate position store, protection store, accounting source, execution path, or reconciliation path.

The following remain authoritative shared capabilities, reused as-is:

- PAPER position/order/fill state;
- protection (STOP/TAKE) lifecycle;
- Market close execution;
- reconciliation;
- account state.

`pause_robot()`, `close_all_now()`, and `stop_robot()` must not invent a Robot-specific close, cancel, or reconciliation mechanism distinct from what the existing shared execution/protection/reconciliation capabilities already provide.

## Explicit non-goals for this decision

- the Telegram command/button surface that invokes these operations, including the concrete implementation of the pause/resume toggle button described in Rationale (separate implementation task);
- the exact durable schema representation of the paused state;
- any path out of `RECONCILIATION_REQUIRED` (remains a separate, unresolved problem);
- any change to STOP/TAKE calculation, priority, or the existing emergency-close contract;
- ownership-transfer/manual-takeover behavior (already deferred outside Robot v0.1 by `AUTOPILOT_ROBOT_V0_1_TELEGRAM_ONLY_DECISION.md`);
- automatically chaining `stop_robot()` into `close_all_now()` when a position is open — rejected in favor of two explicit operator actions; see Rationale;
- ownership/close-scope for manual positions on the same PAPER account — out of scope for this decision; `close_all_now()` does not touch them (see Section 4, Scope).

## Rationale

An operator needs a way to stop new risk immediately (`pause_robot()`) without necessarily forcing an existing, currently-protected position closed, and a separate, stronger way to flatten and fully disengage when that is the intent. Coupling `ROBOT_STOPPED` to a *confirmed* flat account would let a stuck or slow exchange confirmation block the operator from asserting "stop admitting new work now," which is the opposite of the fail-closed, user-authority-preserving intent already accepted for `ROBOT_STOPPED` elsewhere. Separating "admission is closed" from "this specific position is confirmed flat" keeps both guarantees: the operator's stop intent takes effect immediately, and the position's true state is never asserted without authoritative confirmation.

**v1.1 addition.** v1.0 let a single `stop_robot()` call also trigger a Market close of an open position (Section 3.2). Folding "stop admitting new work" and "force-close my exposure right now" into one command hides a financially consequential action — an immediate, unconditional Market close of a live position — inside a command whose name only promises to stop the robot. An operator who meant only to disengage automation could unintentionally force-close a position that was open, healthy, and already correctly protected under its existing STOP/TAKE.

Established open-source trading bots draw the same line rather than combining the two. Freqtrade, for example, keeps `stop`/`stopbuy` (halt new entries) separate from `forceexit`/`emergencysell` (immediately close a specific position or all positions) as distinct operator commands, precisely because forcing a position closed is a separate, higher-consequence decision from pausing new admission.

v1.1 applies the same separation: `close_all_now()` is the one command that may force an immediate Market close, and its name says so; `stop_robot()` v1.1 is restricted to the no-open-position case so it can never silently trigger a close as a side effect. An operator who wants both effects must call both commands explicitly — `pause_robot()` (or nothing, if already paused) then `close_all_now()`, and only then `stop_robot()` — rather than relying on one ambiguous command to infer that a forced close was also wanted.

**v1.2 addition.** `pause_robot()` closes new admission but, unlike `stop_robot()`, is not meant to be a one-way gate: an operator who paused to stop new risk temporarily needs a direct way back to `ROBOT_RUNNING` that does not re-run the full `start_robot()` recovery/reconciliation pipeline (Section 1), because nothing about pausing and resuming implies the account state needs to be re-verified from a stopped baseline — the robot was continuously running, with an unmodified STOP/TAKE lifecycle on any open position, throughout the paused interval. `resume_robot()` exists for exactly this: a lightweight, symmetric reversal of `pause_robot()`, legal only from the state `pause_robot()` produces, rejected everywhere else (including `RECONCILIATION_REQUIRED`) with the same fail-closed posture already accepted for `start_robot()`.

Because `pause_robot()` and `resume_robot()` are the only two legal transitions into and out of the paused state, and each is legal from exactly the state the other produces, they form a single operator-facing toggle rather than two independent actions with overlapping preconditions. The Telegram interface is expected to reflect this directly at the UI level: one button occupies the pause/resume slot, not two. While the robot is running (unpaused), that button reads "Пауза" and invokes `pause_robot()`; once paused, the same button visually becomes "▶ Старт" and invokes `resume_robot()` instead. The button's label and bound command flip together, driven by the robot's current admission state, so the operator is never shown a control whose action would be rejected — "Пауза" never appears while already paused, and "▶ Старт" (in this toggle slot) never appears while running. This mirrors the reasoning in the two paragraphs above: since `pause_robot()`/`resume_robot()` legality is already mutually exclusive and exhaustive over {running, paused}, presenting them as two permanently-visible buttons would only invite the operator to invoke the one call that is guaranteed to be rejected. As stated in Explicit non-goals, this paragraph fixes only the intended interface *behavior*; the concrete Telegram implementation (button/keyboard update mechanics, callback wiring) remains a separate, later implementation task, exactly as for every other command in this decision.

# END_OF_DOCUMENT
