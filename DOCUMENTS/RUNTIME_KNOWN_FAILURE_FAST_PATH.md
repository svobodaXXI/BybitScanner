# BybitScanner — Runtime Known-Failure Fast Path

Status: ACTIVE  
Date: 2026-09-27  
Purpose: compact evidence-first runbook for recurring Scanner / PAPER Robot / Telegram / desktop-launch failures.  
Primary objective: minimize owner time. Known failure classes are diagnosed from repository authority and one bounded host snapshot before any exploratory sequence.

## Universal principle

**Known path before investigation.**

When a runtime symptom belongs to a previously documented class, the assistant must:

1. load the known path and current committed entrypoint first;
2. identify the smallest authoritative state that can decide the class;
3. obtain missing host-only evidence in one bounded read-only snapshot where possible;
4. apply the existing recovery/repair path if the signature matches;
5. broaden the investigation only when the evidence contradicts the known signature.

Do not rediscover launchers, routes, state machines, recovery transitions, process ownership rules, database authority or acceptance rules that are already documented and unchanged.

A repeated incident should normally cost the owner **at most one diagnostic round-trip before the known repair/recovery action**. If more is genuinely required, name the exact new unknown that prevents use of the fast path.

## Runtime decision order

For Scanner / Robot / Telegram / backend incidents, classify in this order:

1. **Entrypoint / launcher failure**
   - Read the current tracked launcher and helper first.
   - If Python reports repository-package import failure from a helper under a subdirectory, check script-vs-module invocation before inspecting Robot state.
   - Canonical Windows rule: repository helpers that import project packages run from repository root as modules when appropriate (`python -m ...`), not as direct subdirectory scripts that change `sys.path[0]`.

2. **Durable Robot recovery state**
   - Read `get_robot_runtime_status()` from the configured PAPER DB.
   - Never infer Robot authority from a process window.
   - `RECONCILIATION_REQUIRED` is a fail-closed latch, not permission to edit SQLite.
   - If current evidence may already be settled, inspect candidate/trade/executions/position projection read-only, then use the canonical reconciliation route.

3. **Canonical reconciliation**
   - Legal state: `ROBOT_RUNNING / RECONCILIATION_REQUIRED`.
   - Operator route: `POST /api/robot/reconcile`.
   - Success lands in `ROBOT_RUNNING / PAUSED` with unresolved candidate/trade/obligation sets empty and `reason=None`.
   - Do not hand-clear `recovery_status`.

4. **Canonical safe stop**
   - Legal Robot states: `ROBOT_RUNNING / READY` or `ROBOT_RUNNING / PAUSED`; reconciliation remains fail-closed when required.
   - Owner surface: desktop shortcut `Остановить робота` -> tracked `C:\BybitScanner\stop_robot_runtime.bat` directly.
   - Full-stop success means Scanner STOPPED, Robot `ROBOT_STOPPED / ROBOT_STOPPED`, Telegram monitoring gone, and PAPER backend gone.
   - Never put an untracked/local wrapper between the desktop shortcut and the tracked stop launcher.

5. **Process shape on Windows venv**
   - A venv `python.exe` parent with a base Python child can be one logical interpreter launch, not two independent workers.
   - Do not label it duplication from process count alone.
   - Prove duplication from independent parentage/ownership/listeners, not executable path difference.

6. **Protection ingress / owner-thread pressure**
   - Reuse current ingress diagnostics before adding instrumentation: pending, high-watermark, queue latency, processing latency, slowest owner task, symbol/role, candle-cache metrics.
   - A short burst immediately after crash/power-loss recovery is not by itself proof of a persistent runtime bottleneck.
   - Compare against a clean subsequent run before reopening architecture, unless overflow or sustained pressure repeats.

7. **Scanner lifecycle**
   - Durable mode is authoritative for start/pause/resume/stop routing.
   - One manual start -> at most one full pass.
   - Do not diagnose Scanner control from window presence alone.
   - Final Scanner visual acceptance remains one complete owner-manual universe pass with ordinary Telegram delivery.

## 2026-09-27 incident — closed path

Observed sequence after abrupt power loss and local migration to canonical desktop wrappers:

- canonical start successfully brought up PAPER backend and Telegram Monitoring;
- startup recovery showed protection queue pressure and closed prior exposure;
- Robot durable state was `ROBOT_RUNNING / RECONCILIATION_REQUIRED` with `ROBOT_ENTRY_OWNERSHIP_MISMATCH` for BLENDUSDT candidate `d31c60b4abeda16305c062bf`;
- read-only durable evidence later showed the candidate CLOSED, no open Robot trade, FLAT/synced position, and two exactly offsetting executions (SELL 581, BUY 581);
- canonical `POST /api/robot/reconcile` cleared the stale recovery latch and landed `ROBOT_RUNNING / PAUSED`;
- desktop safe-stop then exposed a separate launcher defect: `ModuleNotFoundError: No module named 'terminal'`;
- root cause: `stop_robot_runtime.bat` executed `tools\stop_robot_runtime.py` as a script, making `tools` the import root;
- PR #280 changed the launcher to `python -m tools.stop_robot_runtime` and added focused regression coverage; Robot PAPER acceptance #218 passed; merged as `adcd44e1580a1f7648abb79c20a84c6980859660`;
- owner reran the canonical stop path: exit 0, expected success text, final durable state `ROBOT_STOPPED / ROBOT_STOPPED` version 80; backend/Telegram intentionally remained running.

### Fast path if this class repeats

- Import error from canonical stop: inspect current `stop_robot_runtime.bat` first; verify module invocation. Do not investigate Robot ownership first.
- `RECONCILIATION_REQUIRED` with a now-flat/settled symbol: read durable evidence once, then call canonical reconciliation. Do not edit DB.
- Stop shortcut appears ineffective: first prove the shortcut's `TargetPath`. It must point directly to tracked `C:\BybitScanner\stop_robot_runtime.bat`; do not assume an untracked wrapper delegates correctly.
- If the direct tracked launcher runs but shutdown is blocked, use its exact stdout/stderr and current health/durable evidence; do not infer failure from window presence alone.
- venv/base-Python parent-child chain: treat as one logical launch unless independent ownership evidence proves otherwise.

## Maintenance rule

Whenever a new runtime failure is resolved and is reasonably repeatable:

- add only the stable symptom -> decisive evidence -> canonical recovery/repair path here;
- remove superseded diagnostic branches;
- link the code/PR checkpoint when useful;
- do not turn this document into an incident diary.

The goal is fewer owner round-trips, not more documentation.

## Repeated ingress overflow during canonical reconcile — 2026-09-27

A successful reconcile to PAUSED followed by renewed coverage loss is not a
stale-latch-only incident. Do not repeat reconcile/resume as the repair.
Observed: ENTRY_PENDING on 2ZUSDT/ARBUSDT/ARKUSDT, no orders/exposure;
capacity/high-watermark 64/64, max queue latency 9620.0137 ms,
max protection processing 666.6149 ms, slowest owner call
`BackendRuntimeIntentPorts.reconcile_robot.<locals>.<lambda>` 9065.2912 ms.
Trace: robot_reconcile -> RobotRecoveryCoordinator._latest_geometry_indices
-> default ScannerGeometryCursorProvider -> latest_scanner_closed_candle_time_ms
-> candle REST. This bypassed the warmed candle cache (owner cache misses = 0).
Recovery geometry must use the same pre-warmed closed-candle evidence; a
missing/stale cache entry fails recovery closed instead of performing owner REST.
Bootstrap recovery before subscriptions retains its original evidence path.
Do not enlarge ingress capacity, weaken continuity checks or infer a need to
remove pre-entry coverage solely because its LIMIT has not yet been created.
Patch/runtime acceptance remains separate: no runtime restart or recovery retry
is authorized by a successful developer test.
