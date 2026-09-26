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

### Owner one-pass rule — 2026-09-26

A manual Scanner start authorizes **one complete scan pass only**. Natural
completion returns the authoritative state to `STOPPED`; the runtime must
not automatically begin a second universe traversal.

`pause_scanner` is cooperative and preserves the current in-memory traversal
cursor. The current symbol/timeframe may finish, then the pass blocks before
the next unit. `resume_scanner` continues that same pass from the preserved
cursor; it does not start again from the first ticker.

`stop_scanner` is a distinct command, legal from RUNNING or PAUSED. It aborts
the current pass at the next cooperative checkpoint and leaves the Scanner
`STOPPED`. Robot/PAPER backend state is unaffected.

### Restart recovery — 2026-09-26

The pause cursor is intentionally in-memory only. Therefore a new backend
process cannot truthfully resume an interrupted PAUSED/RUNNING pass from its
old ticker/timeframe position. On ScannerControlRuntime startup, any persisted
`SCANNER_RUNNING` or `SCANNER_PAUSED` left by a previous process is stale and
must be recovered to `SCANNER_STOPPED` before owner commands are accepted.
The next owner start then begins one new pass. This is distinct from
same-process `PAUSED -> resume`, which continues the existing in-memory pass.


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

## 5. Telegram Scanner controls

Scanner controls shall reflect authoritative state and expose **two distinct
owner actions**, because pause and stop have different runtime semantics.

Dynamic command:

- `RUNNING` -> `⏸ Пауза сканера`;
- `PAUSED` -> `▶ Продолжить сканер`;
- `STOPPED` -> `▶ Запустить сканер`.

Separate command:

- `⏹ Остановить сканер` is always the explicit hard-stop action and moves an
  active or paused pass toward `STOPPED` at the next cooperative checkpoint.

The displayed action is a projection of runtime state, not a locally toggled
UI flag. Pause must preserve the current traversal cursor; continue must resume
that same pass rather than start a fresh pass from the first ticker.

The Telegram commands Menu button is part of the owner control surface.
Monitoring shall periodically verify that the owner's chat menu button is still
of type `commands` and restore it when it has disappeared or been replaced.
This self-heal changes presentation only; it must not infer or mutate Scanner
or Robot runtime state.

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


## 12. 2026-09-26 runtime discovery and acceptance gate

Observed production-like owner runtime evidence supersedes the earlier
assumption that pause was sufficient for “stop”:

- RUNNING caused repeated full-universe traversals; the owner observed a third
  pass.
- PAUSED did not interrupt the already executing `run_scan_pass()`; Telegram
  signals could continue from that in-flight pass.
- invoking the same toggle while PAUSED resumed Scanner, which made the old
  single-command UX ambiguous.
- the Telegram Menu button was observed to disappear intermittently.

Required acceptance after implementation:

1. start one pass, pause between safe units, and observe no progress while
   paused;
2. continue and prove the same traversal resumes rather than restarting at the
   first ticker;
3. stop and prove the in-flight pass exits at the next safe checkpoint and
   durable mode becomes STOPPED;
4. run one uninterrupted complete pass and prove no second pass starts;
5. verify Telegram exposes the dynamic pause/continue/start command plus the
   separate stop command;
6. verify the commands Menu button is restored if absent;
7. verify Scanner commands do not alter Robot runtime/admission state.

Draft implementation authority: PR #249. Do not call this accepted from CI
that does not directly execute the Scanner-control and Telegram-menu tests.
