# Runtime Intent Reconciler — One-Action Owner UX Plan

Status: **PLANNED / P0 / NOT IMPLEMENTED**  
Date: 2026-09-27  
Owner intent: one owner action expresses the desired runtime outcome; BybitScanner must inspect, prepare, reconcile and verify the required PAPER components automatically instead of asking the owner to perform preparatory state transitions.

## 1. Problem statement

The current canonical launcher is readiness-gated but not intent-driven.

Observed owner evidence on 2026-09-27:

1. the canonical safe-stop correctly left durable Robot state at
   `ROBOT_STOPPED / ROBOT_STOPPED`;
2. backend and Telegram remained alive by design;
3. the owner later used the normal desktop `Запуск робота` shortcut;
4. `start_robot_runtime.bat` reused the healthy backend and Telegram worker,
   then required `robot_admission_ready == true`;
5. because a safely stopped Robot is intentionally not admission-ready, the
   launcher exited before Scanner start;
6. restoring the intended runtime therefore required a separate Telegram
   `Робот -> ▶ Старт` action and then another launcher action.

That is safe but poor orchestration. A state that is a normal, recoverable
starting point for the requested action is being treated as a terminal
readiness failure.

The permanent UX rule is therefore:

> **The owner states intent once. The runtime prepares itself.**

The owner must not have to remember or manually perform prerequisite checks,
Robot STOPPED -> START transitions, PAUSED -> RESUME transitions, backend or
Telegram startup, safe canonical reconciliation, or Scanner state routing
before the requested outcome can begin.

## 2. Design principles

The implementation borrows mature orchestration principles without importing
Docker, Kubernetes, systemd or another runtime platform into this Windows
prototype.

### 2.1 Desired state, not imperative preparation

Use the controller/reconciliation pattern:

```text
owner intent
  -> observe authoritative actual state
  -> calculate safe delta
  -> apply canonical transitions
  -> re-observe
  -> succeed only when desired state is proven
```

The UI/launcher does not ask “is everything already ready?”. It asks “can the
requested desired state be reached safely from the current state?”.

### 2.2 Idempotent ensure semantics

Repeating the same intent must converge to the same final state:

- already READY -> no-op;
- STOPPED -> start;
- PAUSED -> resume when the intent requires RUNNING;
- missing dependency -> start it once and wait for bounded readiness;
- concurrent/double-click intent -> serialize/reuse rather than create a
  duplicate backend, Telegram worker or Scanner owner.

### 2.3 Separate liveness, startup readiness and intent readiness

A live process, a fully initialized dependency and a component that already
matches the requested state are different facts.

Do not use one boolean such as `robot_admission_ready` as both:

- a proof that Robot is already accepting candidates; and
- a verdict on whether a START intent can safely make it accept candidates.

A safely stopped Robot is **repairable for START**, not “broken”.

### 2.4 Automatic repair only through canonical fail-closed transitions

Automatic preparation may reuse existing authoritative transitions. It must
never invent state or bypass safety.

Allowed examples:

- canonical backend start/reuse;
- Telegram singleton start/reuse + READY wait;
- `ROBOT_STOPPED / ROBOT_STOPPED -> start_robot()`;
- `ROBOT_RUNNING / PAUSED -> resume_robot()`;
- Scanner STOPPED -> start;
- Scanner PAUSED -> resume;
- explicit canonical Robot reconciliation when the existing reconcile path can
  itself prove the state safe;
- bounded retry/backoff for transient dependency readiness.

Forbidden examples:

- editing SQLite state directly;
- clearing `RECONCILIATION_REQUIRED` without the canonical reconcile path;
- ignoring wrong PAPER database identity;
- proceeding with ambiguous order/position/protection ownership;
- creating a second Telegram getUpdates consumer;
- creating a second Scanner owner;
- enabling LIVE mutations;
- changing strategy/risk parameters to make startup pass.

## 3. Owner-facing intents

The orchestration contract is expressed as a small stable intent vocabulary.

### `SCANNER`

Desired outcome:

- canonical PAPER backend ready;
- canonical Telegram worker ready on the same DB authority;
- production Scanner acceptance config proven;
- Scanner one-pass runtime RUNNING;
- Robot state is **not changed merely to run Scanner**.

Normal convergence:

```text
backend absent      -> start + bounded READY wait
backend canonical   -> reuse
Telegram absent     -> start singleton + bounded READY wait
Scanner STOPPED     -> start one pass
Scanner PAUSED      -> resume same in-memory pass
Scanner RUNNING     -> no-op
```

### `ROBOT`

Desired outcome:

- canonical PAPER backend ready;
- Telegram control/lifecycle worker ready;
- Robot durable state `ROBOT_RUNNING / READY`;
- protection readiness proven;
- Scanner state left unchanged.

Normal convergence:

```text
ROBOT_STOPPED / ROBOT_STOPPED -> canonical start
ROBOT_RUNNING / PAUSED        -> canonical resume
ROBOT_RUNNING / READY         -> no-op
RECONCILIATION_REQUIRED       -> canonical reconcile once;
                                 continue only if the result is proven safe
```

### `ALL`

Desired outcome:

- backend ready;
- Telegram ready;
- Robot `RUNNING / READY`;
- Robot protection healthy;
- Scanner one-pass RUNNING.

This is the canonical “prepare the full PAPER prototype and begin the pass”
intent.

### stop intents

Preserve independent control while also supporting one-action full stop:

- `STOP_SCANNER` — Scanner only;
- `STOP_ROBOT` — Robot safe-stop semantics, Scanner unchanged unless the
  authoritative Robot stop contract explicitly requires otherwise;
- `STOP_ALL` — stop Scanner first, then canonical safe Robot stop; leave
  backend/Telegram alive when that remains the safe reusable infrastructure
  contract.

## 4. Stable owner UX mapping

Do not replace the existing owner surfaces.

### Desktop

- `start_scanner.lnk -> C:\BybitScanner\start_scanner.bat`
  expresses **SCANNER**.
- `Запуск робота.lnk -> C:\BybitScanner\start_robot.bat`
  expresses **ALL** for the current full-prototype workflow.
- the existing stop shortcut expresses **STOP_ALL**.

The .lnk files remain stable. Only the scripts behind them evolve.

### Telegram

The same reconciler must back Telegram; Telegram must not maintain a second
copy of runtime preparation rules.

Required actions:

- Scanner action -> **SCANNER** / pause / stop as appropriate;
- Robot panel -> **ROBOT** start/resume/pause/stop;
- one explicit owner action **«▶ Всё»** (label may be finalized during the UI
  slice) -> **ALL**;
- one explicit **stop all** action may be exposed if it can reuse the same
  safe-stop contract without ambiguity.

A Telegram action and a desktop action that express the same intent must
converge through the same application contract.

## 5. Target architecture

Do not turn the batch files into a larger state machine.

Target:

```text
Desktop .lnk / Telegram
        |
        v
 RuntimeIntent request
        |
        +-----------------------+
        | bootstrap boundary    |
        | backend / Telegram    |
        +-----------------------+
                    |
                    v
          canonical PAPER backend
                    |
                    v
       RuntimeIntentReconciler
          observe -> plan -> apply
                    |
        +-----------+-----------+
        |                       |
      Robot                   Scanner
 existing control/          existing
 recovery paths        ScannerControlRuntime
```

### 5.1 Thin desktop bootstrapper

Introduce one tracked Python entrypoint, e.g.
`tools/runtime_intent.py`.

Responsibilities:

1. load the existing local runtime environment;
2. prove/reuse or start the canonical PAPER backend;
3. bounded-wait for backend startup readiness;
4. prove/reuse or start the canonical Telegram singleton when required by the
   intent;
5. send the requested intent to the canonical backend;
6. verify the returned final projection;
7. exit 0 only when the requested desired state is proven;
8. print one compact final success/blocker result.

The existing .bat files become thin compatibility wrappers around this
entrypoint. Do not duplicate state logic in PowerShell/batch.

### 5.2 One backend intent service

Add one application/runtime boundary, e.g.
`RuntimeIntentReconciler`, owned by the canonical backend.

Expose it through a localhost PAPER-only route, e.g.

```text
POST /api/runtime/intent
{
  "intent": "ALL"
}
```

The exact route/name may change during implementation, but there must be one
canonical control contract rather than separate launcher and Telegram
algorithms.

The backend-side reconciler:

1. reads authoritative Robot + Scanner + protection state;
2. classifies each mismatch as:
   - already satisfied;
   - safely repairable;
   - blocked / unsafe;
3. applies only canonical transitions;
4. re-reads authoritative state after every mutation;
5. returns one structured result.

Suggested response shape:

```json
{
  "ok": true,
  "intent": "ALL",
  "changed": ["robot:start", "scanner:start"],
  "final": {
    "robot": "READY",
    "scanner": "RUNNING",
    "protection": "HEALTHY"
  },
  "blocked_by": []
}
```

Do not expose secrets or raw credentials/config.

### 5.3 Structured runtime conditions

Add/read a compact runtime status projection rather than overloading generic
`/api/health`.

Minimum useful conditions:

- backend identity / PAPER DB identity;
- backend startup readiness;
- Telegram readiness + same DB identity;
- Robot mode;
- Robot recovery status;
- Robot protection health;
- Scanner mode;
- Scanner acceptance config;
- LIVE gates safe.

When useful, include machine-readable condition metadata such as:

```text
condition=ROBOT_STOPPED
repairable=true
canonical_action=START_ROBOT
```

versus:

```text
condition=ROBOT_OWNERSHIP_AMBIGUOUS
repairable=false
canonical_action=null
```

Presentation text belongs at the owner surface; the condition contract stays
stable and machine-readable.

## 6. Reconciliation policy

### 6.1 Robot

For an intent requiring Robot READY:

| Actual durable state | Reconciler action |
| --- | --- |
| STOPPED / STOPPED | `start_robot()` |
| RUNNING / PAUSED | `resume_robot()` |
| RUNNING / READY | no-op |
| RUNNING / RECONCILIATION_REQUIRED | call canonical reconciliation once; continue only from a proven legal result |
| STOPPED / RECONCILIATION_REQUIRED | fail closed; no shortcut |
| unknown/malformed | fail closed |

If canonical reconciliation lands in PAUSED and all evidence is healthy, a
RUNNING intent may then use the normal `resume_robot()` transition.

### 6.2 Scanner

For an intent requiring Scanner RUNNING:

| Actual state | Reconciler action |
| --- | --- |
| STOPPED | start |
| PAUSED in the same live coordinator | resume |
| RUNNING | no-op |
| unavailable/unknown | fail closed |

A fresh backend continues to recover stale persisted RUNNING/PAUSED to STOPPED
before intent reconciliation; never pretend to resume a lost in-memory cursor.

### 6.3 Protection

Protection health is a postcondition for Robot/ALL intent, not a reason to
manually prepare the owner workflow.

If protection is unhealthy:

1. use the existing canonical recovery/reconcile path when it is applicable;
2. re-check once;
3. if still unhealthy, stop the intent with one precise blocker;
4. never launch Scanner as part of ALL after Robot/protection failed its
   required final state.

SCANNER-only intent does not start Robot merely to satisfy Robot protection.

## 7. Transient upstream failures

The observed `Bybit kline request failed` messages demonstrate that upstream
data can fail independently of owner orchestration.

Use bounded retry/backoff at the owning market-data boundary for transient
failures. If repeated failures cross a defined threshold, expose a degraded
condition/circuit-breaker state rather than spinning indefinitely.

Important separation:

- a kline failure that is not a dependency of the requested intent must not
  falsely block runtime startup;
- a required market-data readiness failure must block the affected capability
  with a precise reason;
- do not hide persistent upstream failures by infinite retry.

The first implementation of RuntimeIntentReconciler does not need to redesign
all market-data retry policy; it must avoid conflating unrelated background
errors with intent readiness.

## 8. Concurrency and duplicate prevention

One-action UX must remain correct under double-clicks and concurrent Telegram
commands.

Required invariants:

1. only one canonical backend owns the PAPER DB/runtime;
2. only one Telegram getUpdates worker owns the bot;
3. only one ScannerControlRuntime owns a pass;
4. backend intent mutation is serialized;
5. repeated identical intent is idempotent;
6. a second caller observes/reuses the in-progress or resulting state rather
   than spawning duplicates;
7. stale completion from an earlier intent cannot overwrite a newer,
   conflicting owner command.

Use the existing port/singleton/serialized-owner mechanisms where possible;
add only the smallest intent-level serialization needed.

## 9. Implementation slices

### Slice A — freeze the intent contract

Add focused tests for the desired transition matrix before changing launch UX:

- ROBOT STOPPED -> ROBOT intent -> READY;
- ROBOT PAUSED -> ROBOT intent -> READY;
- ROBOT READY -> ROBOT intent -> no-op;
- Scanner STOPPED -> SCANNER intent -> RUNNING;
- Scanner PAUSED -> SCANNER intent -> RUNNING;
- Scanner RUNNING -> SCANNER intent -> no-op;
- ALL composes Robot then Scanner with required postconditions;
- SCANNER does not mutate Robot;
- ROBOT does not mutate Scanner;
- unsafe/unknown state fails closed.

### Slice B — backend RuntimeIntentReconciler

Implement the application service using existing control/recovery primitives.
Do not duplicate their transition legality.

Add one localhost PAPER route for intent + one compact status/conditions
projection if required.

### Slice C — desktop bootstrap consolidation

Implement `tools/runtime_intent.py`.

Move backend/Telegram bootstrap/reuse/wait logic out of
`start_robot_runtime.bat` into reusable Python orchestration.

Convert existing desktop-target .bat files to thin intent wrappers.

Preserve shortcut paths.

### Slice D — Telegram uses the same intent service

Replace direct Telegram START/RESUME preparation logic with calls to the same
backend intent contract where the command is an intent-level action.

Keep presentation in Telegram, state transition authority in the reconciler.

Add **ALL** as one explicit owner action.

### Slice E — stop intents through the same contract

Unify Scanner stop + Robot safe-stop composition under `STOP_ALL` while
preserving existing proven safe-stop behavior and fail-closed semantics.

Do not regress the already-fixed module invocation from PR #280.

### Slice F — compact final owner result

Normal success should require no diagnostic output from the owner.

Examples:

```text
READY: Backend · Telegram · Robot · Scanner
```

or:

```text
BLOCKED: Robot ownership is ambiguous for BLENDUSDT.
No unsafe state was changed.
```

Detailed diagnostics remain in logs/status surfaces for investigation.

## 10. Focused verification

Do not create a broad new campaign for each slice.

Required focused cases:

1. cold host-like bootstrap with no backend/Telegram;
2. warm backend + Telegram + Robot STOPPED (the exact 2026-09-27 failure);
3. Robot PAUSED;
4. Robot already READY;
5. Scanner STOPPED / PAUSED / RUNNING;
6. recoverable `RECONCILIATION_REQUIRED`;
7. reconciliation that remains unsafe -> one blocked result;
8. wrong PAPER DB identity -> fail closed;
9. protection unhealthy -> fail closed after canonical recovery attempt;
10. duplicate/double intent -> no duplicate owner/process;
11. SCANNER-only leaves Robot untouched;
12. ROBOT-only leaves Scanner untouched;
13. ALL converges to both desired states;
14. stop-all preserves the existing safe-stop invariants.

Run only focused changed-behavior tests plus the existing mandatory Robot PAPER
acceptance gate where the touched runtime boundary requires it.

## 11. Owner acceptance

The implementation is not accepted merely because unit/CI tests pass.

Final owner acceptance uses the permanent full Scanner rule and starts from a
real non-prepared state, preferably the exact safe-stop state that exposed the
gap:

```text
backend/Telegram may already be alive
Robot = ROBOT_STOPPED / ROBOT_STOPPED
Scanner = STOPPED
```

The owner performs **one action** through the canonical desktop surface.

Acceptance requires:

1. no preparatory Telegram Robot START;
2. no manual status query;
3. no terminal preflight;
4. backend/Telegram reused or prepared automatically;
5. Robot automatically reaches READY;
6. protection is proven healthy;
7. Scanner starts one complete eligible-universe pass;
8. normal Telegram delivery works for all integrated patterns;
9. Menu persistence and Scanner Pause/Continue remain correct;
10. Robot-capable signals can reach real candidate admission;
11. natural Scanner completion returns Scanner to STOPPED;
12. no second pass starts automatically;
13. no LIVE mutation gate is enabled.

The same convergence is then checked from the Telegram **ALL** action without
inventing a second orchestration path.

## 12. Non-goals

This plan does not authorize:

- Docker/Kubernetes/systemd adoption;
- a second Robot/Scanner state machine;
- LIVE trading;
- risk/strategy changes;
- automatic DB edits;
- weakening ownership/protection gates;
- infinite retries;
- broad process killing;
- replacing existing desktop shortcuts;
- removing independent Robot-only or Scanner-only controls.

## 13. Completion criterion

Done means the owner can request **SCANNER**, **ROBOT** or **ALL** once from the
supported desktop/Telegram surface and the system either:

1. automatically reaches and proves the requested safe desired state using
   canonical transitions; or
2. stops once with a precise non-repairable blocker after exhausting only the
   bounded canonical recovery path.

No normal start flow may require the owner to manually inspect readiness,
toggle prerequisite states, run intermediate commands, or repeat the original
start action.
