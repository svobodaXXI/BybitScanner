# Scanner Control Runtime — Architectural Decision

**Status:** ACCEPTED  
**Scope:** Trading Workspace / Unified Menu  
**Date:** 2026-09-12

## 1. Decision

The Trading Workspace Unified Menu shall control Scanner only through an
authoritative Scanner Control Runtime.

The frontend shall not create or maintain an independent Scanner-running
state based on user clicks.

The existing Scanner analysis and scan logic remain unchanged by this
decision. The control layer is an orchestration/runtime boundary around the
existing Scanner execution.

## 2. Current architectural gap

The current Scanner execution is a scan-run flow rather than a durable,
long-lived control runtime:

`main()` → symbol discovery → sequential analysis → scan completion

It does not currently expose an authoritative lifecycle contract equivalent
to the Robot runtime.

Therefore the Unified Menu must not pretend that a Scanner start/pause
control already exists.

Adding a frontend toggle without an authoritative runtime would create a
false state model and violate the project's authoritative-state and
fail-closed principles.

## 3. Scanner lifecycle

The Scanner Control Runtime shall expose these authoritative states:

- `STOPPED`
- `RUNNING`
- `PAUSED`

Required lifecycle commands:

- `start_scanner`
- `pause_scanner`
- `resume_scanner`

Expected transitions:

`STOPPED --start--> RUNNING`

`RUNNING --pause--> PAUSED`

`PAUSED --resume--> RUNNING`

Invalid transitions shall be rejected by the runtime rather than simulated
by the frontend.

## 4. Unified Menu responsibility

The Unified Menu is a presentation and command surface.

It shall:

1. Read the current authoritative Scanner projection.
2. Display the corresponding Scanner action.
3. Dispatch the appropriate Scanner command.
4. Wait for authoritative state refresh.
5. Re-render from the refreshed state.

It shall not:

- maintain `scannerRunning` as a source of truth;
- infer Scanner state from the last click;
- assume a command succeeded merely because it was dispatched;
- directly manipulate Scanner internals;
- duplicate Scanner lifecycle logic.

## 5. Dynamic menu action

The Scanner menu item shall reflect authoritative state.

For `RUNNING`:

`Остановить сканер` / pause semantics according to the accepted Scanner
control contract.

For `PAUSED`:

`Продолжить сканер`.

For `STOPPED`:

`Запустить сканер`.

The displayed action is therefore a projection of runtime state, not a
locally toggled UI flag.

## 6. State flow

The canonical flow is:

`Scanner Control Runtime`
→ `authoritative Scanner state`
→ `application/UI projection`
→ `WorkspaceMenu`
→ `Scanner command`
→ `runtime mutation`
→ `authoritative refresh`
→ `WorkspaceMenu`

The prohibited flow is:

`click`
→ `setLocalState(...)`
→ `assume Scanner state`

## 7. Scanner/Robot separation

Scanner and Robot remain independent runtime domains.

Scanner lifecycle commands must not implicitly start, pause, stop, or alter
Robot runtime state.

Robot status displayed by the Unified Menu shall continue to come from the
authoritative Robot runtime state.

Scanner candidate production and Robot admission remain separate concerns.

## 8. Reuse and scope control

This decision does not authorize:

- rewriting Scanner analysis;
- rewriting symbol discovery;
- rewriting signal admission;
- introducing a second Scanner implementation;
- duplicating Scanner logic in React;
- introducing unrelated global frontend state;
- changing Robot execution semantics;
- changing trading order mechanics.

The implementation shall introduce the smallest control/runtime boundary
required to make Scanner lifecycle authoritative.

## 9. Fail-closed behavior

If the current Scanner state cannot be authoritatively determined, the UI
must not invent a state or silently toggle its local representation.

The command layer remains responsible for validating lifecycle transitions.

A failed or rejected command must result in an authoritative refresh rather
than a presumed state change.

## 10. Implementation order

Implementation shall proceed in this order:

1. Define the Scanner Control Runtime boundary.
2. Connect the existing Scanner execution to that boundary without rewriting
   its analysis logic.
3. Expose authoritative Scanner state to the application/UI projection.
4. Expose lifecycle commands through the existing command boundary.
5. Replace `Open Workspace` with the Unified Menu.
6. Connect the menu to Scanner commands and authoritative state.
7. Reuse the existing `OpenPositionsOverlay`.
8. Verify state transitions and UI behavior from runtime state.

## 11. Acceptance principle

The Unified Menu is considered correctly integrated only when its Scanner
label and behavior remain correct after state changes originating outside
the immediate click flow, including runtime refresh/restart scenarios.

The authoritative runtime state, not the frontend interaction history, is
the source of truth.
