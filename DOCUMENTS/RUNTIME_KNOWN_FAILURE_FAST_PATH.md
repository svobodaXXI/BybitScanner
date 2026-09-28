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

## 2026-09-28 legacy full-stop incident — CLOSED

### Final owner evidence

The canonical desktop stop path is now owner-verified on a clean cycle from
main `d3504c695c5793dde6c41cf952276535d56a324a` (PR #322):

- fresh canonical owner start reached Robot `ROBOT_RUNNING / READY` and Scanner
  RUNNING;
- one click on desktop `Остановить робота` closed the stop window, PAPER
  backend window and Telegram monitoring window without further owner input;
- a read-only post-stop host snapshot proved no listeners on
  `127.0.0.1:8765` or `127.0.0.1:8766`;
- no `terminal.runtime.paper_http_server`, `telegram_monitoring.py` or new
  `stop_robot_runtime.bat` process remained;
- five historical stop-shells left by the old failure-visible `pause`
  behavior were separately identity-checked and terminated once; the clean
  #322 cycle did not recreate them.

This closes the **canonical shutdown incident**, not RVL-R6 as a whole. The
Robot Stability owner gate still requires sustained real multi-symbol traffic,
healthy protection with no `ingress_overflow`, queue drain, and a normal
reconcile/restart that does not recreate the original incident.

### Investigation path that must not be repeated

The incident took multiple distinct blockers in sequence. Preserve this order
for provenance, but use the compact fast path below for any recurrence.

1. **#310 — orphan ENTRY_PENDING retirement safety**
   - added the migration-only stale-arm retirement bridge;
   - required durable no-work proof, exact process ownership and a SQLite writer
     barrier before exact-PID termination.

2. **#311 — canonical Windows `cmd.exe /c` ancestry**
   - recognized the real canonical backend/Telegram launcher shape instead of
     treating it as unprovable ownership.

3. **#312 — stale-arm `ingress_overflow`**
   - allowed only the exact stale temporary `ENTRY_PENDING` shape with
     `ingress_overflow`; all other unhealthy reasons remained fail-closed.

4. **#313 / #314 — desktop shortcut authority**
   - removed untracked local wrappers from the critical owner path;
   - made shortcut repair compatible with Windows PowerShell 5.1.

5. **#315 — saturated owner-queue shutdown path**
   - avoided enqueuing Scanner control behind a provably saturated legacy owner
     queue;
   - preserved Robot STOPPED, durable quiescence, writer barrier and exact PID
     ownership gates.

6. **#316 — persistent stop diagnostics**
   - introduced `%TEMP%\BybitScanner-stop-last.log`;
   - this was decisive for later blockers;
   - the original version deliberately kept failures visible with `pause`,
     which left old idle cmd shells after repeated failed attempts.

7. **#317 — transient legacy health re-proof**
   - retried only read-only health proof for transport timeout or exact
     `paper_runtime_unavailable`; mutations remained single-attempt.

8. **#318 / #319 — correct Robot-scoped PAPER quiescence**
   - inert APPROVED candidates are not by themselves active Robot ownership;
   - full stop no longer requires the entire PAPER account to be flat;
   - unrelated/manual PAPER exposure may persist, while Robot-owned or
     ambiguous pending exposure still blocks fail-closed.

9. **#320 — overflow is an entry trigger, not a final invariant**
   - once the proven legacy-starvation path is selected, queue recovery is not
     a reason to abort shutdown;
   - the stable invariant is exact temporary ENTRY_PENDING coverage shape plus
     durable/process ownership proof.

10. **#322 — live listener can never equal ABSENT**
    - decisive false-success evidence: the persisted log said
      `PAPER backend: absent` and `Runtime STOPPED`, while a read-only host
      snapshot still showed listener PID 700 on 8765 and exact backend chain
      `15028 -> 13476 -> 700`;
    - root cause: an unreachable `/api/health` request was incorrectly treated
      as proof that the process did not exist;
    - #322 added exact localhost listener presence proof and fail-closed
      ownership handling, and removed the launcher `pause` so future failures
      do not leak idle stop shells.

Final successful stop log from the pre-fix backend showed:

```text
[STOP] PAPER backend: present
[STOP] Telegram monitoring: absent
[STOP] Scanner STOPPED confirmed
[STOP] retiring stale entry protection coverage
[STOP] legacy backend identity re-proof delayed (transport unavailable); retrying read-only probe attempt 2
[STOP] legacy backend identity re-proof delayed (transport unavailable); retrying read-only probe attempt 3
[STOP] legacy backend identity re-proof delayed (transport unavailable); retrying read-only probe attempt 4
Runtime STOPPED.
steps=scanner:stop,protection:legacy-entry-proof,backend:legacy-terminate
[STOP BAT] EXIT_CODE=0
```

### Fast path if stop ever appears broken again

Use this exact order; do not restart the two-day investigation tree.

1. Read `%TEMP%\BybitScanner-stop-last.log` once.
2. Read-only check listeners 8765/8766 and exact runtime process ownership.
3. Never infer success or failure from console-window presence alone.
4. If log says backend `absent` but 8765 has a listener, treat that as a
   contradiction and a stop defect; listener evidence wins over HTTP timeout.
5. If backend is present, preserve exact DB/process ownership and durable
   Robot-scoped quiescence; never use account-wide flattening or broad
   kill-by-name.
6. Historical idle `stop_robot_runtime.bat` cmd shells with no Python child are
   launcher residue, not proof that the runtime is still alive.
7. A clean pass requires: one owner stop action, exit 0, 8765/8766 gone, backend
   and Telegram processes gone, and no newly leaked stop shell.

Do not reopen #310-#322 individually unless new evidence contradicts one of
these recorded invariants.

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
