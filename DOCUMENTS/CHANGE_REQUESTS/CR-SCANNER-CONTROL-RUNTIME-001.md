# CR-SCANNER-CONTROL-RUNTIME-001 — Authoritative Scanner Control Runtime for the Trading Workspace Unified Menu

<!-- CHANGE_REQUEST_METADATA_BEGIN -->
```json
{
  "schema_version": "1.0",
  "id": "CR-SCANNER-CONTROL-RUNTIME-001",
  "title": "Authoritative Scanner Control Runtime (ScannerControlRuntime) for the Trading Workspace Unified Menu",
  "governance_type": "DESIGN_TO_IMPLEMENTATION_CHANGE_REQUEST",
  "status": "IN_PROGRESS",
  "revision": "1.0",
  "lifecycle_stage": "CONTEXT",
  "objective": "Give the Trading Workspace Unified Menu an authoritative Scanner lifecycle (STOPPED/RUNNING/PAUSED) to control, exactly as DOCUMENTS/SCANNER_CONTROL_RUNTIME_DECISION.md (ACCEPTED) already specifies, by extracting main.py's single scan pass into a reusable throttled function and introducing a ScannerControlRuntime coordinator inside terminal/runtime/paper_runtime.py that owns and drives it, alongside the existing RobotRecoveryCoordinator/RobotBreakoutMonitor coordinators.",
  "non_goals": [
    "Rewrite Scanner analysis, symbol discovery, or signal admission -- per DOCUMENTS/SCANNER_CONTROL_RUNTIME_DECISION.md section 8 and DOCUMENTS/SCANNER_CONTROL_RUNTIME_INVESTIGATION.md section 11, this is a minimal orchestration/runtime boundary around the existing Scanner execution, not a Scanner rewrite",
    "Introduce a second Scanner implementation, or duplicate Scanner lifecycle logic in React (Decision doc section 8/Investigation section 11)",
    "Change Robot execution semantics, Robot admission, or trading order mechanics -- Scanner and Robot remain independent runtime domains (Decision doc section 7, Investigation section 6): Scanner lifecycle commands must not implicitly start/pause/stop/alter Robot readiness or admission",
    "Resolve the GIL/shared-process-and-thread-pool contention risk between the Scanner scan pass and RobotBreakoutMonitor's tick (see risks) -- recorded as an accepted, non-blocking risk for this CR, not a solved question",
    "Authorize IMPLEMENT for this CR -- this revision formalizes the already-ACCEPTED design and closes the one open investigation item (section 12) into a durable, scoped, git-governed ChangeRequest; a further explicit human approval is required before writing ScannerControlRuntime, the new HTTP routes, or any frontend change"
  ],
  "approved_scope": [
    "CONTEXT-stage verification recorded in this revision: DOCUMENTS/SCANNER_CONTROL_RUNTIME_INVESTIGATION.md section 12 ('important unresolved implementation point' -- verify all current main.py launch paths) is now closed. A repository-wide search confirms main.py is invoked only by start_scanner.bat and start_robot.bat (both simply open a PowerShell window and run `python main.py`); no scheduler, systemd/Windows service, cron, or Telegram-triggered launch path exists. This was the one blocking precondition Investigation section 13 named before choosing a Scanner runtime ownership model",
    "Future IMPLEMENT phase (separately authorized), per the user's approved architecture: extract main.py's current single scan-pass body into a reusable, throttled, repeatable function/method (mirroring Freqtrade's Worker._process_running() pattern -- a throttled repeatable call rather than a one-shot script), preserving all existing analysis/admission/notification behavior unchanged",
    "Future IMPLEMENT phase: introduce ScannerControlRuntime inside terminal/runtime/paper_runtime.py, structurally following the existing RobotRecoveryCoordinator/RobotBreakoutMonitor coordinator pattern, exposing STOPPED/RUNNING/PAUSED state and start_scanner/pause_scanner/resume_scanner commands; invalid transitions are rejected by the runtime, never emulated by the frontend (Decision doc sections 3 and 9)",
    "Future IMPLEMENT phase: ScannerControlRuntime opens its OWN SQLiteStore.open() connection from inside its own background thread at the start of that thread's run, rather than accepting a store instance opened by the constructing (main) thread -- see context_findings for why this is load-bearing, not stylistic",
    "Future IMPLEMENT phase: four new HTTP routes on the existing terminal/runtime/paper_http_server.py -- /api/scanner/start, /api/scanner/pause, /api/scanner/resume, /api/scanner/status -- using the same trust model already used by every other PAPER-mutating route on that server (127.0.0.1-only bind, dispatch by exact path, no additional operator token), precedented by the existing /api/close-all route",
    "Future IMPLEMENT phase: Unified Menu frontend (terminal/frontend/src/app/App.tsx, WorkspaceHeader.tsx, ModePanelLegacy.tsx) reads the authoritative Scanner projection, dispatches the corresponding command, waits for authoritative refresh, and re-renders -- no local scannerRunning state, no inference from the last click (Decision doc sections 4 and 6)"
  ],
  "prohibited_scope": [
    "Scanner analysis, symbol discovery, signal admission, pattern/geometry/wedge detection logic -- unchanged by this CR",
    "terminal/application/robot_recovery.py, terminal/application/robot_breakout_monitor.py or any Robot admission/execution semantics -- Scanner and Robot remain independent runtime domains; Scanner commands must not implicitly touch Robot runtime state",
    "Any new Scanner lifecycle logic duplicated into React -- the frontend is a projection/command surface only",
    "Any resolution of the GIL/thread-pool contention risk between Scanner and RobotBreakoutMonitor beyond recording it as a known, accepted risk",
    "Writing ScannerControlRuntime code, the new HTTP routes, or any frontend change, until a separate human approval authorizes IMPLEMENT for this CR",
    "Unrelated production, documentation, training/reference, or dirty-work changes"
  ],
  "authoritative_references": [
    "DOCUMENTS/SCANNER_CONTROL_RUNTIME_DECISION.md (ACCEPTED -- governing architectural decision; sections 1-11 apply directly and are not restated here)",
    "DOCUMENTS/SCANNER_CONTROL_RUNTIME_INVESTIGATION.md (RECORDED -- governing investigation; section 12 is the item this revision closes)",
    "DOCUMENTS/CHANGE_REQUESTS/CR-ROBOT-CONTROL-001.md (governing structural CR pattern this document follows)",
    "DOCUMENTS/CHANGE_REQUESTS/CR-ROBOT-BREAKOUT-MONITOR-001.md (sibling coordinator precedent and the source of the SQLiteStore thread-ownership lesson this CR must not repeat)",
    "terminal/application/robot_recovery.py, terminal/application/robot_breakout_monitor.py (coordinator structural precedent)",
    "terminal/runtime/paper_http_server.py (existing PAPER-mutating route trust model precedent, e.g. /api/close-all)",
    "DOCUMENTS/PROJECT_CONTRACTS.md#CONTRACT-CHANGE-REQUEST-001",
    "DOCUMENTS/PROJECT_CONTRACTS.md#CONTRACT-DEVELOPMENT-LIFECYCLE-001",
    "AGENTS.md#Task-and-change-routing"
  ],
  "context_scope_paths": [
    "main.py",
    "analyzer/__init__.py",
    "bybit_api.py",
    "notification.py",
    "signal_adapter.py",
    "signal_memory.py",
    "terminal/runtime/paper_runtime.py",
    "terminal/runtime/paper_http_server.py",
    "terminal/application/robot_recovery.py",
    "terminal/application/robot_breakout_monitor.py",
    "terminal/persistence/sqlite_store.py",
    "terminal/api/models.py",
    "terminal/api/projections.py",
    "terminal/api/rest.py",
    "terminal/api/websocket.py",
    "terminal/frontend/src/app/App.tsx",
    "terminal/frontend/src/components/WorkspaceHeader.tsx",
    "terminal/frontend/src/components/ModePanel.tsx",
    "terminal/frontend/src/components/ModePanelLegacy.tsx",
    "start_scanner.bat",
    "start_robot.bat",
    "stop_robot.bat",
    "start_paper_backend.bat"
  ],
  "context_test_paths": [
    "tests/test_terminal_paper_http.py",
    "tests/test_terminal_market_data_hub.py",
    "tests/test_terminal_workspace_stream.py",
    "terminal/frontend/src/app/App.test.tsx",
    "terminal/frontend/src/components/WorkspaceHeader.test.tsx",
    "terminal/frontend/src/components/ModePanel.test.tsx"
  ],
  "external_reference_inspiration": [
    "Freqtrade: Worker._process_running() is a throttled, repeatable unit of work driven by an owning coordinator loop, not a one-shot script -- cited by the user as the precedent for extracting main.py's scan pass into a reusable function (design inspiration only, not vendored)"
  ],
  "context_findings": [
    "CLOSED Investigation section 12: repository-wide search (grep for 'main.py' across *.bat/*.ps1/*.yml/*.yaml/*.service/*.xml/*.sh/*.cfg/*.ini) found exactly two files that invoke it -- start_scanner.bat (runs `python telegram_review.py` then `python main.py`, each in its own PowerShell window) and start_robot.bat (additionally starts start_paper_backend.bat first, then the same two). No scheduler, Windows service, cron, or Telegram-triggered launch path exists. main.py is a single, manually-launched scan-pass script with no competing ownership model to reconcile",
    "main.py's current structure (verified by direct read) is exactly the 'scan-run flow' the Investigation document describes: build symbol list -> optional MAX_SYMBOLS truncation -> sequential analyze_symbol() per symbol with try/except-per-symbol isolation -> Trading Diary observation (best-effort, non-blocking) -> signal admission/notification -> a single 'scan finished' Telegram message with elapsed time. There is no loop, throttle, or lifecycle state anywhere in it -- confirming it must be extracted into a callable unit before any control runtime can throttle/repeat it",
    "CRITICAL LESSON FROM CR-ROBOT-BREAKOUT-MONITOR-001, VERIFIED DURING THIS CR'S OWN CONTEXT PASS: terminal/persistence/sqlite_store.py's SQLiteStore records `self._owner_thread = threading.get_ident()` at construction and every public method calls `_assert_owner()`, raising `PersistenceError('SQLiteStore must be used by its owning writer thread')` if called from any other thread. RobotBreakoutMonitor (already implemented and CLOSED on the robot-v0-1-admission-gate branch) accepts a SQLiteStore instance opened by PaperRuntime.__init__'s thread and stores it directly for use from its OWN background thread's tick() calls -- re-inspecting that already-merged code during this CR's own verification pass confirms the store is still accepted pre-opened, not re-opened inside the background thread. This means any real tick executed after the background thread's interval actually elapses would raise PersistenceError against every store call. This was not caught by that CR's own test suite because every test there calls .tick() synchronously from the main test thread; the one thread-lifecycle test starts and closes the monitor well within one tick interval, so the real background thread never actually calls tick() in any existing test. This is recorded here as a verified, currently-unresolved defect in already-closed work -- not something this CR fixes (out of scope: it lives on a different branch/CR), but the exact failure mode ScannerControlRuntime's own design must not repeat",
    "terminal/runtime/paper_http_server.py's existing trust model (verified): the server binds only to HOST='127.0.0.1' (ThreadingHTTPServer((HOST, port), ...)); mutation routes such as /api/close-all are gated only by `runtime.require_paper_mutations()` -- no separate operator/bearer token exists on this server. This is the exact precedent the four new /api/scanner/* routes should follow",
    "No /api/robot/* routes exist anywhere in terminal/runtime/paper_http_server.py on this branch (main) -- that HTTP surface is part of CR-ROBOT-CONTROL-001's work on the separate robot-v0-1-admission-gate branch, not yet merged here. /api/close-all remains the correct, present-on-this-branch trust-model precedent to cite",
    "terminal/frontend/src/app/App.tsx, WorkspaceHeader.tsx, ModePanel.tsx and ModePanelLegacy.tsx all exist on this branch with existing dedicated test files (App.test.tsx, WorkspaceHeader.test.tsx, ModePanel.test.tsx), confirming the Investigation document's file-path findings and giving the future IMPLEMENT phase existing test scaffolding to extend rather than create from scratch",
    "tests/test_terminal_paper_http.py is the existing focused test module for terminal/runtime/paper_http_server.py's HTTP route behavior and is the natural home for the four new /api/scanner/* route tests"
  ],
  "approved_decisions": [
    "main.py's single scan-pass body is extracted into a reusable, throttled, repeatable function/method, mirroring Freqtrade's Worker._process_running() pattern, rather than remaining a one-shot script -- existing analysis/admission/notification behavior is preserved unchanged, only the entry-point shape changes",
    "A new ScannerControlRuntime coordinator lives inside terminal/runtime/paper_runtime.py, following the exact same structural pattern already established by RobotRecoveryCoordinator/RobotBreakoutMonitor. States are STOPPED/RUNNING/PAUSED; commands are start_scanner/pause_scanner/resume_scanner; invalid transitions are rejected by the runtime itself, never emulated by the frontend (Decision doc sections 3 and 9)",
    "CRITICAL, to prevent repeating the CR-ROBOT-BREAKOUT-MONITOR-001 defect verified in context_findings: ScannerControlRuntime must call SQLiteStore.open() itself, from inside its own background thread, at the start of that thread's run -- it must NOT accept a pre-opened SQLiteStore instance from the constructing (main) thread. SQLiteStore enforces owning-thread-only access on every call; a store opened by any other thread will fail every real durable operation once the background thread actually runs",
    "Four new HTTP routes on the existing terminal/runtime/paper_http_server.py -- /api/scanner/start, /api/scanner/pause, /api/scanner/resume, /api/scanner/status -- using the exact same trust model as every existing PAPER-mutating route on that server (127.0.0.1-only bind, no additional operator token), precedented by /api/close-all",
    "The Unified Menu frontend (App.tsx/WorkspaceHeader.tsx/ModePanelLegacy.tsx) reads the authoritative Scanner projection, dispatches commands, and waits for authoritative refresh before re-rendering -- it holds no local scannerRunning state and never infers Scanner state from the last click (Decision doc sections 4 and 6)"
  ],
  "unresolved_decisions": [],
  "acceptance_criteria": [
    "(Gates the future IMPLEMENT phase, not this revision.) main.py's scan-pass logic is callable as a throttled, repeatable unit without any change to its analysis/admission/notification behavior",
    "ScannerControlRuntime enforces exactly STOPPED->RUNNING->PAUSED->RUNNING transitions (start/pause/resume) and rejects any invalid transition without frontend involvement",
    "ScannerControlRuntime opens its own SQLiteStore.open() connection from inside its own background thread; no SQLiteStore instance crosses a thread boundary into or out of it",
    "A real, unmocked test exercises ScannerControlRuntime's actual background thread executing past at least one real tick interval (not only synchronous direct calls), specifically to catch the class of defect recorded in context_findings",
    "/api/scanner/start, /api/scanner/pause, /api/scanner/resume and /api/scanner/status behave consistently with the existing /api/close-all trust model (127.0.0.1-only, require_paper_mutations()-equivalent gate, no additional token)",
    "Scanner lifecycle commands never start, pause, stop, or alter Robot runtime state, admission readiness, or trading order mechanics",
    "The Unified Menu displays the correct action label (Запустить/Остановить/Продолжить сканер) purely as a projection of authoritative runtime state, verified to remain correct after a state change originating outside the immediate click flow (runtime refresh/restart scenarios), per Decision doc section 11's acceptance principle"
  ],
  "verification_requirements": [
    "(Applies to the future IMPLEMENT/VERIFY phase.) Focused ScannerControlRuntime coordinator tests, including a real-background-thread tick test per acceptance_criteria",
    "New tests/test_terminal_paper_http.py coverage for the four /api/scanner/* routes",
    "Existing Robot regression suite (RobotRecoveryCoordinator, RobotBreakoutMonitor once available on this branch, terminal/application/* layering guard) passes unmodified",
    "Existing frontend test suite (App.test.tsx, WorkspaceHeader.test.tsx, ModePanel.test.tsx) passes unmodified, plus new coverage for the Unified Menu's Scanner projection/command flow",
    "Standalone durable ChangeRequest governance validation for this CR file",
    "Artifact-free compile, git diff --check and scoped allowlist review"
  ],
  "risks": [
    "Scanner and RobotBreakoutMonitor will run inside the same process/thread pool once both exist on the same branch: a long scan pass could theoretically hold the GIL long enough to slightly delay the Robot monitor's tick. Not blocking for this CR's scope, and not resolved here -- recorded as a known, accepted risk for future measurement, not a solved question",
    "ScannerControlRuntime is the second coordinator (after RobotBreakoutMonitor) to own a background thread inside PaperRuntime; repeating the SQLiteStore thread-ownership mistake would be a second occurrence of the same class of defect -- the approved_decisions/acceptance_criteria above exist specifically to prevent that",
    "main.py's extraction into a reusable function touches the single existing production Scanner entry point; any behavioral drift during extraction (even unintentional) would affect the only operational Scanner launch path since section 12 confirms there is no redundant path to fall back on",
    "The Unified Menu replacing 'Open Workspace' is a visible frontend change; Decision doc section 11's acceptance principle (correct behavior after out-of-band state changes, not just after a click) is the concrete bar future VERIFY work must clear"
  ],
  "rollback_boundaries": [
    "This revision (1.0) changes only this ChangeRequest document -- no production code is touched, so there is nothing to roll back yet",
    "The future IMPLEMENT phase must land ScannerControlRuntime, the main.py extraction, the four HTTP routes and the frontend wiring as independently revertible units where practical; rollback restores the current scan-run-script behavior without touching Robot runtime state or schema"
  ],
  "implementation_phases": [
    {"id": "TASK", "status": "COMPLETED"},
    {"id": "SPEC", "status": "COMPLETED_HUMAN_APPROVED"},
    {"id": "CONTEXT", "status": "COMPLETED"},
    {"id": "IMPLEMENT", "status": "NOT_STARTED_NOT_AUTHORIZED"},
    {"id": "VERIFY", "status": "NOT_STARTED_NOT_AUTHORIZED"},
    {"id": "RECORD", "status": "NOT_STARTED_NOT_AUTHORIZED"}
  ],
  "current_phase": "CONTEXT",
  "current_checkpoint": "LAUNCH_PATH_VERIFICATION_AND_THREAD_OWNERSHIP_LESSON_RECORDED_IMPLEMENT_PENDING_APPROVAL",
  "implementation_status": "IMPLEMENTATION_NOT_STARTED_NOT_AUTHORIZED",
  "next_phase": "IMPLEMENT",
  "next_phase_authorization": "NOT_AUTHORIZED_PENDING_HUMAN_APPROVAL_OF_THIS_CR",
  "related_commits": [
    {"phase": "BASELINE", "commit": "8306e653e6a59ab8414d334a192f4e28cfa54fab"}
  ],
  "repository_sync": {
    "branch": "main",
    "baseline_local_head": "8306e653e6a59ab8414d334a192f4e28cfa54fab",
    "status": "PENDING_CHECKPOINT_COMMIT"
  },
  "amendment_history": [
    {"revision": "1.0", "reason": "Human-authorized durable CR opened formalizing the already-ACCEPTED DOCUMENTS/SCANNER_CONTROL_RUNTIME_DECISION.md and RECORDED DOCUMENTS/SCANNER_CONTROL_RUNTIME_INVESTIGATION.md into a scoped, git-governed ChangeRequest, following the CR-ROBOT-CONTROL-001/CR-ROBOT-BREAKOUT-MONITOR-001 pattern. Investigation section 12 (verify all main.py launch paths) closed by direct repository verification. The five architecture decisions approved in chat recorded as approved_decisions, including the critical SQLiteStore thread-ownership requirement discovered as a live, currently-unresolved defect while re-verifying CR-ROBOT-BREAKOUT-MONITOR-001's already-closed work. IMPLEMENT explicitly not authorized pending separate human confirmation", "date": "2026-09-12"}
  ]
}
```
<!-- CHANGE_REQUEST_METADATA_END -->

## Recovery summary

`DOCUMENTS/SCANNER_CONTROL_RUNTIME_DECISION.md` (ACCEPTED) and `DOCUMENTS/SCANNER_CONTROL_RUNTIME_INVESTIGATION.md`
(RECORDED) already establish the governing architecture: the Trading Workspace Unified Menu must control
Scanner only through an authoritative Scanner Control Runtime (`STOPPED`/`RUNNING`/`PAUSED`,
`start_scanner`/`pause_scanner`/`resume_scanner`), never through a locally-toggled frontend flag. Those
documents are not restated here — see them directly for the full rationale (sections 1-11 of the Decision,
sections 1-11 of the Investigation).

This CR formalizes that accepted design into a scoped, git-governed ChangeRequest and closes the one item
the Investigation left open: **section 12**, whether `main.py` has competing launch paths. It does not.
`start_scanner.bat` and `start_robot.bat` are the only two files anywhere in the repository that invoke it;
no scheduler, service, or Telegram-triggered path exists.

**The approved architecture** (agreed in chat): extract `main.py`'s single scan pass into a reusable,
throttled function (Freqtrade's `Worker._process_running()` precedent) driven by a new `ScannerControlRuntime`
coordinator inside `terminal/runtime/paper_runtime.py` — structurally the same pattern as the existing
`RobotRecoveryCoordinator`/`RobotBreakoutMonitor`. Four new HTTP routes on the existing
`paper_http_server.py` (`/api/scanner/start|pause|resume|status`) follow the same trust model as
`/api/close-all`. The Unified Menu frontend becomes a pure projection/command surface with no local
`scannerRunning` state.

**One critical requirement, discovered by re-verifying already-closed work rather than merely restating the
user's instruction:** while confirming the "lesson learned" this CR was asked to record, direct inspection of
`terminal/persistence/sqlite_store.py` and the already-merged `RobotBreakoutMonitor`
(`CR-ROBOT-BREAKOUT-MONITOR-001`, `robot-v0-1-admission-gate` branch) confirms this is not a hypothetical
risk — it is a **currently live, unresolved defect** in that closed CR's code: `SQLiteStore` binds to its
opening thread and raises on every call from any other thread, and `RobotBreakoutMonitor` still accepts a
store opened by `PaperRuntime.__init__`'s thread for use from its own background thread. No existing test
catches this because every test there calls `.tick()` synchronously; the one thread-lifecycle test never lets
the real background thread reach a real tick. `ScannerControlRuntime` must open its own `SQLiteStore`
connection from inside its own background thread from the start, and its future IMPLEMENT phase must include
a test that actually drives its background thread past a real tick interval — specifically to catch this
class of defect, which this CR's own sibling did not.

**IMPLEMENT is explicitly not authorized by this revision.** No `ScannerControlRuntime` code, HTTP route, or
frontend change has been written. A separate human approval is required before implementation begins.

## Amendment rule

Material scope, approved decision, risk, acceptance, lifecycle or implementation-authorization changes
require a new revision and explicit human approval.
