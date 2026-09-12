# CR-ROBOT-BREAKOUT-MONITOR-001 — Wire Robot v0.1 Breakout/Retest Lifecycle to Approved Candidates

<!-- CHANGE_REQUEST_METADATA_BEGIN -->
```json
{
  "schema_version": "1.0",
  "id": "CR-ROBOT-BREAKOUT-MONITOR-001",
  "title": "Wire Robot v0.1 Breakout/Retest Lifecycle to Approved Candidates via a Reusable RobotBreakoutMonitor Coordinator",
  "governance_type": "DESIGN_TO_IMPLEMENTATION_CHANGE_REQUEST",
  "status": "IN_PROGRESS",
  "revision": "1.1",
  "lifecycle_stage": "IMPLEMENT",
  "objective": "Introduce a mode-agnostic RobotBreakoutMonitor coordinator, modeled on the existing terminal/application/robot_recovery.py:RobotRecoveryCoordinator pattern, that drives each durable APPROVED Robot candidate through the already-implemented and already-tested robot_state_machine.py / robot_entry_limit.py / robot_partial_fill.py / robot_market_confirmation.py / robot_protection.py pipeline on every new closed 1m candle, so that APPROVED candidates can actually reach robot_trades instead of stalling forever.",
  "non_goals": [
    "Change Scanner behavior, main.py, pattern/geometry detection, or the Scanner-side Telegram handoff (notification.py, robot_candidate_store.py)",
    "Change entry/pattern strategy logic inside robot_state_machine.py, robot_entry_limit.py, robot_partial_fill.py, robot_market_confirmation.py or robot_protection.py -- this CR delivers already-approved, already-tested logic to a real caller, it does not redesign that logic",
    "Implement live_runtime.py or any live-exchange execution path -- only reserve a dependency-injection boundary shaped so a future live implementation can reuse the same coordinator without duplicating coordination code",
    "Introduce a new OS process, a new HTTP bridge/endpoint, or any transport outside the existing paper_runtime.py process",
    "Implement robot_partial_fill.py top-up/completion wiring, robot_market_confirmation.py Market-entry wiring, robot_protection.py STOP/TAKE wiring, or the resulting create_robot_trade() call -- discovered during this revision's IMPLEMENT pass to need additional data-sourcing decisions (see context_findings and unresolved_decisions) that the five decisions this revision resolves do not cover; deferred to a follow-up revision"
  ],
  "approved_scope": [
    "CONTEXT-stage research recorded in revision 1.0: enumerate every location that reads or writes Robot candidate state, and the existing Robot execution-command surface those pure modules already hand commands to",
    "CONTEXT-stage research recorded in revision 1.0: enumerate existing live/near-live multi-symbol market-data mechanisms in the repository and their gaps relative to a per-symbol closed-1m-candle feed",
    "CONTEXT-stage research recorded in revision 1.0: identify the existing test patterns (fake clock, fake providers, real temp-file SQLiteStore) that a RobotBreakoutMonitor test suite would follow",
    "Architecture decision recorded in revision 1.0 (approved in chat): a new RobotBreakoutMonitor class, independent of PAPER, constructed with explicit dependency-injected callables for `next closed candle for symbol` and `execute action`, following the RobotRecoveryCoordinator(store, trading_account_id, ...) constructor shape",
    "IMPLEMENTED in this revision (1.1): terminal/application/robot_breakout_monitor.py -- RobotBreakoutMonitor lazily initializes robot_state via robot_state_machine.initialize_state() for a freshly admitted APPROVED candidate, advances WAITING_BREAKOUT -> WAITING_RETEST -> RETEST_DETECTED / EXPIRED_AT_APEX via robot_state_machine.process_closed_candle() on each tick, persists via save_robot_candidate_state() respecting optimistic concurrency, and submits the initial retest LIMIT via robot_entry_limit.build_initial_retest_limit()/submit_initial_retest_limit() once RETEST_DETECTED is reached, idempotently retried every tick thereafter",
    "IMPLEMENTED in this revision (1.1): scanner_geometry_cursor.py gains latest_scanner_closed_candle(symbol), the default PAPER closed-1m-candle provider, reusing analyzer.candles.load_candles()/bybit_api.get_candles() exactly like the existing latest_scanner_closed_candle_time_ms(), returning None (not raising) on any unavailable/invalid evidence so the periodic tick simply retries next cycle",
    "IMPLEMENTED in this revision (1.1): terminal/runtime/paper_runtime.py instantiates RobotBreakoutMonitor with PAPER-bound dependencies (self as the LIMIT submitter, the instrument provider's tick_size, the default closed-candle provider unless overridden) immediately after self._robot_recovery.recover() completes, starts its background thread, and stops it in PaperRuntime.close()",
    "IMPLEMENTED in this revision (1.1): tests/test_robot_breakout_monitor.py -- a focused coordinator test suite driving .tick() directly against a real temp-file SQLiteStore with a fake scripted closed-candle feed and a fake recording LIMIT submitter"
  ],
  "prohibited_scope": [
    "main.py, notification.py, robot_candidate_store.py (Scanner-side handoff envelope) without new evidence and approved amendment",
    "Internal decision logic of robot_state_machine.py, robot_entry_limit.py, robot_partial_fill.py, robot_market_confirmation.py, robot_protection.py -- only their existing public call boundary may be invoked",
    "terminal/application/robot_admission.py and terminal/application/robot_control.py admission/control semantics (CR-ROBOT-CONTROL-001 territory) beyond reading robot_runtime_state to gate the monitor's activity",
    "live_runtime.py implementation or any live-exchange order submission",
    "robot_partial_fill.py, robot_market_confirmation.py and robot_protection.py wiring, and any create_robot_trade() call, until the additional data-sourcing decisions recorded under unresolved_decisions are made and approved in a follow-up revision",
    "Unrelated production, documentation, training/reference, or dirty-work changes"
  ],
  "authoritative_references": [
    "DOCUMENTS/CHANGE_REQUESTS/CR-ROBOT-CONTROL-001.md (governing structural pattern for this CR)",
    "terminal/application/robot_recovery.py (RobotRecoveryCoordinator -- structural precedent for RobotBreakoutMonitor)",
    "DOCUMENTS/ROBOT_RUN_INDEX.md",
    "DOCUMENTS/ROBOT_V0_1_LOCAL_PAPER_RUN_2026-09-12.md (evidence: 2 APPROVED candidates, 0 robot_trades)",
    "DOCUMENTS/PROJECT_CONTRACTS.md#CONTRACT-CHANGE-REQUEST-001",
    "DOCUMENTS/PROJECT_CONTRACTS.md#CONTRACT-DEVELOPMENT-LIFECYCLE-001",
    "AGENTS.md#Task-and-change-routing"
  ],
  "context_scope_paths": [
    "robot_state_machine.py",
    "robot_entry_limit.py",
    "robot_partial_fill.py",
    "robot_market_confirmation.py",
    "robot_protection.py",
    "robot_candidate_store.py",
    "scanner_geometry_cursor.py",
    "analyzer/candles.py",
    "terminal/application/robot_admission.py",
    "terminal/application/robot_recovery.py",
    "terminal/application/robot_control.py",
    "terminal/application/robot_breakout_monitor.py",
    "terminal/persistence/sqlite_store.py",
    "terminal/runtime/paper_runtime.py",
    "terminal/runtime/paper_http_server.py",
    "terminal/market_data/hub.py",
    "terminal/market_data/models.py",
    "bybit_api.py",
    "telegram_review.py",
    "notification.py",
    "main.py"
  ],
  "context_test_paths": [
    "tests/test_robot_state_machine.py",
    "tests/test_robot_entry_limit.py",
    "tests/test_robot_partial_fill.py",
    "tests/test_robot_market_confirmation.py",
    "tests/test_robot_protection.py",
    "tests/test_robot_recovery_coordinator.py",
    "tests/test_robot_runtime_wiring.py",
    "tests/test_robot_admission.py",
    "tests/test_robot_breakout_monitor.py",
    "tests/test_scanner_geometry_cursor.py",
    "tests/test_terminal_paper_runtime.py",
    "tests/test_terminal_persistence.py",
    "tests/test_terminal_execution_engine.py"
  ],
  "external_reference_inspiration": [
    "Freqtrade: one shared worker loop/coordination code serves both dry-run (paper) and live, with dry-run/live differences isolated to the order-execution layer rather than duplicating the whole cycle -- cited by the user as the precedent this architecture follows (design inspiration only, not vendored)"
  ],
  "context_findings": [
    "robot_state_machine.py, robot_entry_limit.py, robot_partial_fill.py, robot_protection.py and robot_market_confirmation.py are fully implemented and individually tested but have zero live callers: grep across the repository confirms the only importers of robot_state_machine.py are the other robot_*.py modules and tests; main.py has zero mentions of 'robot' (case-insensitive) even on this branch; telegram_review.py and terminal/runtime/paper_runtime.py never imported robot_state_machine, robot_entry_limit, robot_partial_fill, robot_protection or robot_market_confirmation before this revision",
    "The full production admission path that DOES exist and run today: main.py -> notification.py (calls robot_candidate_store.create_signal_snapshot, writing an AVAILABLE JSON handoff record) -> operator taps Approve in Telegram -> telegram_review.py's callback handler calls terminal/application/robot_admission.py:admit_robot_candidate() -> which checks robot_runtime_state is ROBOT_RUNNING+READY, then calls SQLiteStore.create_robot_candidate(status='APPROVED', ...). That insertion is the ONLY thing that ever happened to the 2 APPROVED candidates recorded in DOCUMENTS/ROBOT_V0_1_LOCAL_PAPER_RUN_2026-09-12.md",
    "Candidate state read/write surface is entirely owned by terminal/persistence/sqlite_store.py: create_robot_candidate() (insert, APPROVED only, robot_state_json always NULL), get_robot_candidate()/load_robot_candidates() (read), save_robot_candidate_state(status, robot_state, expected_revision, updated_at_ms) (optimistic-concurrency update, enforced against ROBOT_CANDIDATE_TRANSITIONS = {'APPROVED': {'APPROVED','EXPIRED','INVALIDATED'}, ...}), and create_robot_trade() (which also flips the owning candidate to status='OPEN')",
    "robot_state_machine.initialize_state()/process_closed_candle() read status/timeframe/signal_snapshot from a plain 'candidate payload' mapping the caller builds, not from a RobotCandidateRecord directly -- mirrors RobotRecoveryCoordinator._candidate_payload(); RobotBreakoutMonitor._candidate_payload() replicates this",
    "create_robot_candidate() always inserts robot_state_json=NULL, and robot_restart_recovery.reconcile_restart() raises RobotRestartError if an APPROVED candidate's robot_state is still absent when recovery runs. Nothing before this revision ever called robot_state_machine.initialize_state() to produce that first state -- this was itself part of the wiring gap. RobotBreakoutMonitor now performs this lazy first-tick initialization, so a freshly admitted candidate is no longer a restart-recovery hazard once the monitor has ticked at least once before any restart",
    "PaperRuntime.create_limit() is already idempotent by client_action_id (via store.create_paper_limit() returning a 'duplicate_action' result on repeat), and robot_entry_limit.py's client_action_id is deterministic per (candidate_id, retest_index) -- so RobotBreakoutMonitor safely re-attempts the initial retest LIMIT submission on every tick while phase remains RETEST_DETECTED without needing its own separate submitted-once bookkeeping; verified by tests/test_robot_breakout_monitor.py",
    "terminal/application/*.py must not import config/scanner/main/requests/pybit/websocket (enforced by tests/test_terminal_execution_engine.py:test_no_mutation_or_network_api_is_exposed, confirmed still passing). RobotBreakoutMonitor therefore takes get_closed_candle purely as an injected callable and never imports analyzer/bybit_api itself; the real PAPER implementation (scanner_geometry_cursor.latest_scanner_closed_candle(), which lazily imports analyzer.candles only inside the function body, matching the existing latest_scanner_closed_candle_time_ms() idiom) is wired in by terminal/runtime/paper_runtime.py instead",
    "Starting RobotBreakoutMonitor's background thread unconditionally in PaperRuntime.__init__ is only test-safe because the tick loop waits a full tick_interval_s (default 60s, matching TIMEFRAME) BEFORE its first tick rather than ticking immediately on start. Every existing PaperRuntime-constructing test (tests/test_robot_runtime_wiring.py, tests/test_terminal_paper_runtime.py, tests/test_robot_breakout_monitor.py's own thread-lifecycle test) constructs and closes well within that window, so none of them reach a real get_closed_candle call -- confirmed by the full existing suite running in ~2 seconds unchanged after this wiring landed",
    "DISCOVERED DURING IMPLEMENT: reaching a real robot_trades row requires robot_partial_fill.py (fill/top-up policy), robot_market_confirmation.py (Market-entry confirmation) and robot_protection.py (STOP/TAKE planning) in addition to robot_entry_limit.py, and each needs inputs no existing code currently sources: filled_wv/order_authoritatively_inactive (live PAPER order-fill introspection -- no query API for this was found), average_entry/structural_extreme/rr (a live position/order query plus a swing-high/low computation, neither designed), and frozen_signal_reference_price/frozen_scanner_target_price (robot_protection.py:frozen_take_90 needs a Scanner target-price field not yet confirmed to exist in the real signal_snapshot schema produced by analyzer/core.py -- only 'pattern' and 'geometry' were confirmed present via the isolated modules' own test fixtures). These are NOT covered by the five decisions this revision resolves and are NOT invented here; this revision implements only the well-specified breakout/retest-to-initial-LIMIT portion of the chain"
  ],
  "approved_decisions": [
    "A new, reusable RobotBreakoutMonitor class is introduced, not bound to PAPER, following the existing terminal/application/robot_recovery.py:RobotRecoveryCoordinator pattern: it accepts a SQLiteStore, a trading_account_id, and dependency functions rather than a concrete PaperRuntime",
    "Dependencies are passed explicitly as constructor parameters with simple, explicit boundaries for future reuse: a 'get the next closed 1m candle for a symbol' function and an 'execute action' surface (LIMIT submission today; cancel/confirm-fill/protection reserved for the follow-up revision) -- paper_runtime.py instantiates the class with PAPER implementations of these dependencies; a future live_runtime.py can instantiate the same class with live implementations without duplicating coordination code",
    "This follows the Freqtrade precedent of one shared coordination/strategy loop serving both dry-run and live, with only the execution layer differing between modes -- not duplicating the full cycle per mode",
    "The loop is embedded into paper_runtime.py as another background coordinator, next to the existing RobotRecoveryCoordinator (self._robot_recovery) -- not a separate OS process and not a new HTTP bridge",
    "Cadence is tied to TIMEFRAME (currently \"1\", i.e. once per new closed 1m candle), not to the Scanner's own scan cycle",
    "Multi-symbol live closed-1m-candle transport is REST-poll via bybit_api.get_candles() (through analyzer.candles.load_candles()), not extending MarketDataHub -- chosen specifically to avoid coupling this candidate-lifecycle dependency to the Trading Workspace market-data layer, which is independently evolving under the active CR-TRADING-WORKSPACE-001",
    "The 'get next closed candle' dependency is pull-based: RobotBreakoutMonitor calls the injected provider synchronously on its own tick, exactly matching RobotRecoveryCoordinator's existing Callable-provider style -- not push/callback-based",
    "No batching: the provider is invoked once per symbol, sequentially, on every tick, with no separate batch-fetch infrastructure -- the expected number of concurrently active Robot candidates is small enough that per-symbol REST calls are acceptable",
    "RobotBreakoutMonitor's periodic tick reuses the same background-thread idiom already used by terminal/market_data/hub.py:MarketDataHub -- a daemon threading.Thread plus a threading.Event stop flag -- and is started/stopped by PaperRuntime.__init__ itself (via .start()/.close()), not by a separate process-bootstrap mechanism",
    "RobotBreakoutMonitor's thread starts strictly after RobotRecoveryCoordinator.recover() completes inside PaperRuntime.__init__; the existing expected_revision optimistic-concurrency check in save_robot_candidate_state() is accepted as sufficient race protection for Robot v0.1, with no additional lock introduced"
  ],
  "unresolved_decisions": [
    "Source of filled_wv and order_authoritatively_inactive for robot_partial_fill.py's evaluate_partial_completion() -- requires querying live PAPER order/fill state; no query API for this was identified during this revision",
    "Source of average_entry, structural_extreme (swing high/low) and rr for robot_market_confirmation.py/robot_protection.py -- requires a live position/order query and a swing-price computation, neither designed",
    "Whether frozen_signal_reference_price and frozen_scanner_target_price (needed by robot_protection.py:frozen_take_90) already exist as fields inside the real Scanner signal_snapshot payload produced by analyzer/core.py, or need a new Scanner-side field -- not yet confirmed against the real output schema",
    "Exact point at which create_robot_trade() should be called (which entry_path, which fill event triggers it) once the above inputs are sourced"
  ],
  "acceptance_criteria": [
    "A durable APPROVED Robot candidate with no robot_state is lazily initialized by RobotBreakoutMonitor and advances through WAITING_BREAKOUT -> WAITING_RETEST -> RETEST_DETECTED (or EXPIRED_AT_APEX) exactly as robot_state_machine.py already defines, without any change to that module's decision logic",
    "Once RETEST_DETECTED, RobotBreakoutMonitor submits exactly one initial retest LIMIT via robot_entry_limit.py's existing build/submit functions, safely re-attempted (idempotent) on later ticks",
    "RobotBreakoutMonitor accepts its market-data and execution dependencies purely as constructor parameters and contains no PAPER-specific or live-specific branching itself",
    "paper_runtime.py instantiates RobotBreakoutMonitor with PAPER-bound dependencies alongside the existing RobotRecoveryCoordinator, started only after recovery completes, without introducing a new OS process or HTTP endpoint",
    "No existing PaperRuntime-constructing test makes a real network call as a result of this change",
    "Existing focused tests for the five pure Robot modules and for RobotRecoveryCoordinator/paper_runtime wiring continue to pass unmodified",
    "A new focused test suite drives RobotBreakoutMonitor.tick() directly with a fake scripted closed-candle sequence and a fake LIMIT submitter against a real temp-file SQLiteStore, verifying state transitions, optimistic-concurrency safety and the initial retest LIMIT submission",
    "(Deferred to a follow-up revision, NOT this one) reaching a robot_trades row requires robot_partial_fill.py/robot_market_confirmation.py/robot_protection.py wiring, which needs the additional data-sourcing decisions recorded under unresolved_decisions"
  ],
  "verification_requirements": [
    "Focused tests/test_robot_breakout_monitor.py suite passing",
    "Full existing Robot regression suite passing unmodified: tests/test_robot_state_machine.py, tests/test_robot_entry_limit.py, tests/test_robot_partial_fill.py, tests/test_robot_market_confirmation.py, tests/test_robot_protection.py, tests/test_robot_recovery_coordinator.py, tests/test_robot_runtime_wiring.py, tests/test_robot_admission.py, tests/test_scanner_geometry_cursor.py, tests/test_terminal_persistence.py, tests/test_terminal_paper_runtime.py, tests/test_terminal_execution_engine.py (including the no-network/no-mutation layering guard)",
    "Standalone durable ChangeRequest governance validation for this CR file",
    "Artifact-free compile, git diff --check and scoped allowlist review",
    "(Deferred) A repeated local paper run demonstrating an APPROVED candidate reaching robot_trades remains pending the follow-up revision that wires partial-fill/confirmation/protection"
  ],
  "risks": [
    "REST-polling every APPROVED candidate's symbol once per 1m tick could approach Bybit rate limits at scale -- accepted for v0.1 given the expected small number of concurrently active candidates",
    "Two writers now touch robot_candidates state (RobotRecoveryCoordinator's one-shot recovery pass and the new periodic RobotBreakoutMonitor); the existing expected_revision optimistic-concurrency check is the accepted safeguard, with RobotBreakoutMonitor starting strictly after recovery completes each process start",
    "A candidate admitted mid-way through an in-progress 1m bar could be picked up on a partial candle if the tick/candle-boundary alignment is not carefully defined -- not specifically re-verified in this revision beyond the existing conservative 'second-newest kline' evidence pattern",
    "The five pure Robot modules have only ever been exercised in isolation before this revision; tests/test_robot_breakout_monitor.py adds the first integration-level coverage, but only for the breakout/retest/initial-LIMIT portion -- partial-fill/confirmation/protection composition remains untested end-to-end",
    "This revision intentionally stops at initial LIMIT submission: an approved candidate can now reach RETEST_DETECTED and have a resting LIMIT, but still cannot reach robot_trades until the follow-up revision resolves the data-sourcing gaps above -- avoid mistaking a resting LIMIT for the original wiring gap being fully closed"
  ],
  "rollback_boundaries": [
    "RobotBreakoutMonitor (terminal/application/robot_breakout_monitor.py) plus its instantiation/teardown in terminal/runtime/paper_runtime.py plus the new scanner_geometry_cursor.latest_scanner_closed_candle() function and tests/test_robot_breakout_monitor.py form one independently revertible unit",
    "Rollback restores the current non-functional state without touching robot_candidates/robot_trades schema or any of the five existing tested pure modules"
  ],
  "implementation_phases": [
    {"id": "TASK", "status": "COMPLETED"},
    {"id": "SPEC", "status": "COMPLETED_HUMAN_APPROVED"},
    {"id": "CONTEXT", "status": "COMPLETED"},
    {"id": "IMPLEMENT", "status": "IN_PROGRESS_BREAKOUT_RETEST_LIMIT_COMPLETE_PARTIAL_FILL_CONFIRMATION_PROTECTION_PENDING"},
    {"id": "VERIFY", "status": "NOT_STARTED_NOT_AUTHORIZED"},
    {"id": "RECORD", "status": "NOT_STARTED_NOT_AUTHORIZED"}
  ],
  "current_phase": "IMPLEMENT",
  "current_checkpoint": "BREAKOUT_RETEST_LIMIT_IMPLEMENTED_TESTS_PASSING_PARTIAL_FILL_CONFIRMATION_PROTECTION_PENDING_FOLLOWUP",
  "implementation_status": "IMPLEMENT_PARTIAL_BREAKOUT_RETEST_LIMIT_COMPLETE",
  "next_phase": "VERIFY",
  "next_phase_authorization": "APPROVED",
  "related_commits": [
    {"phase": "BASELINE", "commit": "95418d75672e9057b294422ae2a66025559defdd"},
    {"phase": "REVISION_1_0_CHECKPOINT", "commit": "1cdddbf7ce90d3dc0aa9dc4b64d17ba5f0aa3c9c"}
  ],
  "repository_sync": {
    "branch": "robot-v0-1-admission-gate",
    "baseline_local_head": "95418d75672e9057b294422ae2a66025559defdd",
    "status": "PENDING_CHECKPOINT_COMMIT"
  },
  "amendment_history": [
    {"revision": "1.0", "reason": "Human-authorized durable CR opened recording the Robot v0.1 breakout/retest lifecycle wiring gap finding and the RobotBreakoutMonitor architecture decision approved in chat; CONTEXT-stage research on candidate-state read/write locations, multi-symbol live-candle retrieval options and applicable test patterns recorded in the same revision; IMPLEMENT explicitly not authorized pending separate human confirmation", "date": "2026-09-12"},
    {"revision": "1.1", "reason": "Human-authorized: the five unresolved live-candle-transport, threading and concurrency decisions resolved and recorded as approved_decisions with the user's exact choices; IMPLEMENT authorized and executed for the breakout/retest/initial-LIMIT portion (RobotBreakoutMonitor, scanner_geometry_cursor.latest_scanner_closed_candle(), paper_runtime.py wiring, focused test suite); partial-fill/confirmation/protection wiring and create_robot_trade() explicitly deferred to a follow-up revision pending newly discovered data-sourcing decisions this revision does not cover", "date": "2026-09-12"}
  ]
}
```
<!-- CHANGE_REQUEST_METADATA_END -->

## Recovery summary

`robot_state_machine.py` and its four execution-policy siblings (`robot_entry_limit.py`,
`robot_partial_fill.py`, `robot_market_confirmation.py`, `robot_protection.py`) were complete and
individually tested but had zero live callers. The only thing that ever happened to an approved candidate
was admission into the `robot_candidates` SQLite table via `admit_robot_candidate()`.
`DOCUMENTS/ROBOT_V0_1_LOCAL_PAPER_RUN_2026-09-12.md` recorded exactly this: 2 candidates reached
`APPROVED`, 0 reached `robot_trades`.

Revision 1.1 resolves the five plumbing decisions the user gave (REST-poll transport via
`bybit_api.get_candles()`, pull-based per-symbol calls, no batching, MarketDataHub's daemon-thread idiom
started/stopped by `PaperRuntime.__init__`, and the existing `expected_revision` optimistic-concurrency
check as sufficient race protection) and implements them:

- **`terminal/application/robot_breakout_monitor.py`** (new) — `RobotBreakoutMonitor`, structurally
  mirroring `RobotRecoveryCoordinator`. It lazily initializes `robot_state` for a freshly admitted
  candidate, advances `WAITING_BREAKOUT -> WAITING_RETEST -> RETEST_DETECTED` / `EXPIRED_AT_APEX` via
  `robot_state_machine.process_closed_candle()` on each tick, persists via `save_robot_candidate_state()`,
  and submits the initial retest LIMIT via `robot_entry_limit.py` once `RETEST_DETECTED` is reached
  (idempotently retried every tick thereafter, relying on `create_limit()`'s existing
  `client_action_id`-based dedup).
- **`scanner_geometry_cursor.py`** — new `latest_scanner_closed_candle(symbol)`, the default PAPER
  closed-candle provider, mirroring the existing `latest_scanner_closed_candle_time_ms()` but returning
  OHLC and never raising (returns `None` for a periodic caller to simply retry).
- **`terminal/runtime/paper_runtime.py`** — instantiates and starts `RobotBreakoutMonitor` immediately
  after `self._robot_recovery.recover()` completes, and stops it in `close()`.
- **`tests/test_robot_breakout_monitor.py`** (new) — drives `.tick()` directly against a real temp-file
  `SQLiteStore` with a fake scripted candle feed and a fake recording LIMIT submitter; covers lazy
  initialization, the full breakout-to-retest sequence and exactly-once (idempotent) LIMIT submission,
  apex expiry, an unavailable candle leaving state untouched, a simulated concurrent-writer race being
  absorbed without raising, two independent symbols, and that starting/closing the background thread
  within one tick interval never reaches the real candle provider.

**Discovered during IMPLEMENT, not previously known:** reaching a real `robot_trades` row needs
`robot_partial_fill.py`, `robot_market_confirmation.py` and `robot_protection.py` as well, and each of
those requires inputs nothing in the repository currently sources — live order/fill introspection
(`filled_wv`, `order_authoritatively_inactive`), a live position/order query plus a swing-price computation
(`average_entry`, `structural_extreme`, `rr`), and confirmation that `frozen_signal_reference_price` /
`frozen_scanner_target_price` actually exist in the real Scanner `signal_snapshot` schema. These are not
covered by the five decisions resolved in this revision and are not invented here. **This revision
therefore stops at the initial retest LIMIT submission; partial-fill, confirmation, protection and
`create_robot_trade()` remain explicitly deferred to a follow-up revision.**

The full existing test suite (Robot regression, `RobotRecoveryCoordinator`/`paper_runtime` wiring,
`SQLiteStore` persistence, and the `terminal/application/*` no-network/no-mutation layering guard) passes
unmodified alongside the new focused suite.

## Amendment rule

Material scope, approved decision, risk, acceptance, lifecycle or implementation-authorization changes
require a new revision and explicit human approval.
