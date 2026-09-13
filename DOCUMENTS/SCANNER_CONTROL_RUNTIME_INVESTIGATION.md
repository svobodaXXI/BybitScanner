# Scanner Control Runtime — Investigation Record

**Status:** RECORDED
**Date:** 2026-09-12
**Scope:** Trading Workspace / Unified Menu / Scanner lifecycle control
**Related decision:** `DOCUMENTS/SCANNER_CONTROL_RUNTIME_DECISION.md`

---

## 1. Investigation objective

Determine whether the existing BybitScanner architecture already contains an authoritative Scanner lifecycle runtime that can safely back the Trading Workspace Unified Menu.

Required UI behavior:

- `Запустить сканер`
- `Остановить сканер` / pause semantics
- `Продолжить сканер`
- state derived from authoritative runtime state rather than frontend click history.

---

## 2. Current Scanner execution model

The current root Scanner entrypoint is:

`main.py`

Its execution path was inspected and is currently structured as a scan-run flow:

`main()`
> symbol discovery
> `MAX_SYMBOLS` limiting
> sequential `analyze_symbol(symbol)`
> diary processing
> signal preparation/admission/notification
> scan completion.

The inspected `main.py` does not currently expose a durable lifecycle API equivalent to the Robot runtime.

No authoritative Scanner control contract was found for:

- `start_scanner`
- `pause_scanner`
- `resume_scanner`

Therefore the existing Scanner must not be represented in the UI as though these lifecycle operations already exist.

---

## 3. Existing runtime architecture

The current `terminal/runtime/` area contains the established Paper/Trading runtime infrastructure, including:

- `paper_context.py`
- `paper_http_server.py`
- `paper_runtime.py`

The current HTTP server routes runtime commands through the existing serialized runtime boundary.

The current runtime architecture therefore provides a suitable architectural pattern for introducing Scanner control, but no equivalent Scanner lifecycle runtime was found during this investigation.

---

## 4. Existing API / projection boundary

The current API layer contains:

- `terminal/api/models.py`
- `terminal/api/projections.py`
- `terminal/api/rest.py`
- `terminal/api/websocket.py`

`TerminalSnapshot` currently represents authoritative Trading Terminal state, including account, connectivity, reconciliation, positions, orders, executions, protection, cleanup, capabilities and related runtime information.

The inspected snapshot contract does not currently contain an authoritative Scanner lifecycle projection.

The WebSocket presentation protocol is snapshot-first and therefore is compatible with adding an authoritative Scanner projection later.

---

## 5. Robot runtime comparison

The Robot subsystem already has a durable runtime model and persisted authoritative state.

The accepted Robot control contract defines lifecycle commands such as:

- `start_robot()`
- `pause_robot()`
- `resume_robot()`
- `close_all_now()`
- `stop_robot()`

Robot runtime state is persisted and includes lifecycle/readiness/reconciliation states.

This establishes the correct architectural precedent:

`durable runtime state > authoritative projection > command boundary > UI`

Scanner currently does not have the equivalent lifecycle boundary.

---

## 6. Scanner / Robot relationship

The investigation confirmed that Scanner is already a meaningful producer in the broader architecture.

Scanner-related work includes the geometry cursor and Robot recovery integration.

However:

**Scanner candidate production is not the same thing as Scanner lifecycle control.**

Scanner lifecycle must remain an independent runtime domain.

Scanner commands must not implicitly:

- start Robot;
- pause Robot;
- stop Robot;
- alter Robot readiness;
- alter Robot admission semantics;
- submit or mutate trading orders.

Robot admission remains governed by the authoritative Robot runtime.

---

## 7. Frontend findings

The inspected frontend architecture includes:

- `App.tsx`
- `WorkspaceHeader.tsx`
- `ModePanel.tsx`
- `ModePanelLegacy.tsx`
- existing `OpenPositionsOverlay`.

`App.tsx` already owns authoritative application-level projections and passes workspace controls downward.

`WorkspaceHeader.tsx` currently handles symbol/timeframe controls and does not provide a global Scanner lifecycle state.

`ModePanelLegacy.tsx` contains existing utility controls and the reusable `OpenPositionsOverlay`.

The intended Unified Menu should therefore be an application/workspace command surface rather than a new router or duplicate overlay system.

---

## 8. Critical architectural finding

A frontend-only implementation such as:

`click > setLocalState(...) > assume Scanner is running`

would create a false state model.

It would fail if:

- the runtime rejected the command;
- the process stopped;
- the runtime restarted;
- state changed outside the current browser interaction;
- another control surface changed Scanner state;
- command execution became unavailable.

The authoritative model must instead be:

`Scanner Control Runtime`
> authoritative Scanner state
> application/UI projection
> Workspace Menu
> Scanner command
> runtime mutation
> authoritative refresh
> Workspace Menu.

---

## 9. Required Scanner lifecycle model

The accepted Scanner Control Runtime decision defines:

### States

- `STOPPED`
- `RUNNING`
- `PAUSED`

### Commands

- `start_scanner`
- `pause_scanner`
- `resume_scanner`

### Valid transitions

`STOPPED --start--> RUNNING`

`RUNNING --pause--> PAUSED`

`PAUSED --resume--> RUNNING`

Invalid transitions must be rejected by the runtime.

The UI must not emulate lifecycle transitions locally.

---

## 10. Fail-closed requirement

If authoritative Scanner state cannot be determined:

- the UI must not invent a state;
- the UI must not silently toggle its local state;
- command success must not be assumed;
- the authoritative state must be refreshed after command failure/rejection.

This is consistent with the existing project fail-closed and authoritative-state principles.

---

## 11. Scope boundary

The Scanner Control Runtime work must **not**:

- rewrite Scanner analysis;
- rewrite symbol discovery;
- rewrite signal admission;
- create a second Scanner implementation;
- move Scanner business logic into React;
- introduce unrelated global frontend state;
- change Robot execution semantics;
- change order execution mechanics.

The intended change is a minimal orchestration/runtime boundary around the existing Scanner execution.

---

## 12. Important unresolved implementation point

The inspected root `main.py` demonstrates the current Scanner execution flow, but this investigation does not yet establish that `main.py` is the only operational/production Scanner launch path.

Before implementation, the following must be checked:

1. all current callers of `main.py`;
2. deployment/systemd launch configuration;
3. scheduler or loop mechanisms;
4. Telegram-triggered Scanner execution paths;
5. any existing background process/service that may already own Scanner execution.

This check is required before choosing the concrete Scanner runtime ownership model.

---

## 13. Implementation consequence

The correct implementation order is:

1. verify all current Scanner launch/ownership paths;
2. define the minimal Scanner Control Runtime ownership boundary;
3. connect existing Scanner execution without rewriting analysis;
4. expose authoritative Scanner state;
5. expose lifecycle commands;
6. replace `Open Workspace` with Unified Menu;
7. connect Unified Menu to the authoritative Scanner projection/commands;
8. reuse `OpenPositionsOverlay`;
9. verify lifecycle behavior, restart behavior and fail-closed behavior.

The Unified Menu implementation must not begin before the authoritative Scanner control boundary exists.

---

## 14. Canonical documents

Scanner Control Runtime architectural decision:

`DOCUMENTS/SCANNER_CONTROL_RUNTIME_DECISION.md`

This investigation record:

`DOCUMENTS/SCANNER_CONTROL_RUNTIME_INVESTIGATION.md`

Trading Workspace acceptance authority:

`DOCUMENTS/ACCEPTANCE/CR-TRADING-WORKSPACE-001.md`

Project-wide current-state authority:

`DOCUMENTS/PROJECT_STATE.md`

---

## 15. Current conclusion

The investigation confirms an architectural gap rather than an existing missing UI hookup:

**The Trading Workspace needs a real Scanner Control Runtime before the Unified Menu can safely control Scanner.**

The correct next engineering task is therefore Scanner runtime ownership/implementation discovery, not React menu implementation.
