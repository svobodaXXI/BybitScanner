# CR-ROBOT-BREAKOUT-MONITOR-001 — Wire Robot v0.1 Breakout/Retest Lifecycle to Approved Candidates

<!-- CHANGE_REQUEST_METADATA_BEGIN -->
```json
{
  "schema_version": "1.0",
  "id": "CR-ROBOT-BREAKOUT-MONITOR-001",
  "title": "Wire Robot v0.1 Breakout/Retest Lifecycle to Approved Candidates via a Reusable RobotBreakoutMonitor Coordinator",
  "governance_type": "DESIGN_TO_IMPLEMENTATION_CHANGE_REQUEST",
  "status": "IN_PROGRESS",
  "revision": "1.0",
  "lifecycle_stage": "CONTEXT",
  "objective": "Introduce a mode-agnostic RobotBreakoutMonitor coordinator, modeled on the existing terminal/application/robot_recovery.py:RobotRecoveryCoordinator pattern, that drives each durable APPROVED Robot candidate through the already-implemented and already-tested robot_state_machine.py / robot_entry_limit.py / robot_partial_fill.py / robot_market_confirmation.py / robot_protection.py pipeline on every new closed 1m candle, so that APPROVED candidates can actually reach robot_trades instead of stalling forever.",
  "non_goals": [
    "Change Scanner behavior, main.py, pattern/geometry detection, or the Scanner-side Telegram handoff (notification.py, robot_candidate_store.py)",
    "Change entry/pattern strategy logic inside robot_state_machine.py, robot_entry_limit.py, robot_partial_fill.py, robot_market_confirmation.py or robot_protection.py -- this CR delivers already-approved, already-tested logic to a real caller, it does not redesign that logic",
    "Implement live_runtime.py or any live-exchange execution path -- only reserve a dependency-injection boundary shaped so a future live implementation can reuse the same coordinator without duplicating coordination code",
    "Introduce a new OS process, a new HTTP bridge/endpoint, or any transport outside the existing paper_runtime.py process",
    "Resolve HOW multi-symbol live 1m candles are obtained beyond recording the current options as unresolved (see unresolved_decisions) -- no live-candle transport is selected or implemented by this revision",
    "Authorize IMPLEMENT for this CR -- this revision covers TASK/SPEC/CONTEXT only; a further explicit human approval is required before writing RobotBreakoutMonitor or wiring it into paper_runtime.py"
  ],
  "approved_scope": [
    "CONTEXT-stage research recorded in this revision: enumerate every location that reads or writes Robot candidate state, and the existing Robot execution-command surface those pure modules already hand commands to",
    "CONTEXT-stage research recorded in this revision: enumerate existing live/near-live multi-symbol market-data mechanisms in the repository and their gaps relative to a per-symbol closed-1m-candle feed",
    "CONTEXT-stage research recorded in this revision: identify the existing test patterns (fake clock, fake providers, real temp-file SQLiteStore) that a RobotBreakoutMonitor test suite would follow",
    "Architecture decision recorded in this revision (approved in chat, not yet implemented): a new RobotBreakoutMonitor class, independent of PAPER, constructed with explicit dependency-injected callables for `next closed candle for symbol` and `execute action` (open LIMIT, cancel, confirm fill, invoke protection), following the RobotRecoveryCoordinator(store, trading_account_id, ...) constructor shape",
    "Future IMPLEMENT phase (separately authorized): paper_runtime.py instantiates RobotBreakoutMonitor with PAPER-bound implementations of those dependencies and runs it as an additional background coordinator next to the existing self._robot_recovery, on a cadence tied to TIMEFRAME (currently \"1\")"
  ],
  "prohibited_scope": [
    "main.py, notification.py, robot_candidate_store.py (Scanner-side handoff envelope) without new evidence and approved amendment",
    "Internal decision logic of robot_state_machine.py, robot_entry_limit.py, robot_partial_fill.py, robot_market_confirmation.py, robot_protection.py -- only their existing public call boundary may be invoked",
    "terminal/application/robot_admission.py and terminal/application/robot_control.py admission/control semantics (CR-ROBOT-CONTROL-001 territory) beyond reading robot_runtime_state to gate the monitor's activity",
    "live_runtime.py implementation or any live-exchange order submission",
    "Writing RobotBreakoutMonitor code, editing paper_runtime.py, or any other IMPLEMENT-phase change, until a separate human approval authorizes IMPLEMENT for this CR",
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
    "terminal/application/robot_admission.py",
    "terminal/application/robot_recovery.py",
    "terminal/application/robot_control.py",
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
    "tests/test_terminal_paper_runtime.py",
    "tests/test_terminal_persistence.py"
  ],
  "external_reference_inspiration": [
    "Freqtrade: one shared worker loop/coordination code serves both dry-run (paper) and live, with dry-run/live differences isolated to the order-execution layer rather than duplicating the whole cycle -- cited by the user as the precedent this architecture follows (design inspiration only, not vendored)"
  ],
  "context_findings": [
    "robot_state_machine.py, robot_entry_limit.py, robot_partial_fill.py, robot_protection.py and robot_market_confirmation.py are fully implemented and individually tested (tests/test_robot_state_machine.py, tests/test_robot_entry_limit.py, tests/test_robot_partial_fill.py, tests/test_robot_market_confirmation.py, tests/test_robot_protection.py) but have zero live callers: grep across the repository confirms the only importers of robot_state_machine.py are the other robot_*.py modules and tests; main.py has zero mentions of 'robot' (case-insensitive) even on this branch; telegram_review.py and terminal/runtime/paper_runtime.py never import robot_state_machine, robot_entry_limit, robot_partial_fill, robot_protection or robot_market_confirmation",
    "The full production admission path that DOES exist and run today: main.py -> notification.py (calls robot_candidate_store.create_signal_snapshot, writing an AVAILABLE JSON handoff record with a robot_candidate_id) -> operator taps Approve in Telegram -> telegram_review.py's callback handler (line ~463) calls terminal/application/robot_admission.py:admit_robot_candidate() -> which checks robot_runtime_state is ROBOT_RUNNING+READY via SQLiteStore, then calls SQLiteStore.create_robot_candidate(status='APPROVED', ...), inserting a row into the robot_candidates SQLite table (terminal/persistence/sqlite_store.py) -- and then updates the legacy JSON record as a secondary, non-authoritative approval marker via robot_candidate_store.approve_candidate()",
    "That admit_robot_candidate() insertion into robot_candidates is the ONLY thing that has ever happened to the 2 APPROVED candidates recorded in DOCUMENTS/ROBOT_V0_1_LOCAL_PAPER_RUN_2026-09-12.md. Nothing after admission reads that APPROVED row to progress it: terminal/application/robot_recovery.py:RobotRecoveryCoordinator only touches APPROVED candidates once, synchronously, inside recover() at PaperRuntime construction (terminal/runtime/paper_runtime.py:360-366), purely for restart reconciliation (did an approved candidate expire at apex while the process was down) -- it never runs periodically and never advances a live candidate through the breakout/retest state machine during normal operation",
    "Candidate state read/write surface is entirely owned by terminal/persistence/sqlite_store.py: create_robot_candidate() (insert, APPROVED only), get_robot_candidate()/load_robot_candidates() (read), save_robot_candidate_state(status, robot_state, expected_revision, updated_at_ms) (optimistic-concurrency state update, enforced against ROBOT_CANDIDATE_TRANSITIONS), and create_robot_trade()/get_robot_trade()/the exit-fill UPDATE path (terminal/persistence/sqlite_store.py:3403-3600), where create_robot_trade() also flips the owning candidate to status='OPEN' and the exit path flips it to 'CLOSED'. A RobotBreakoutMonitor would read via load_robot_candidates(status='APPROVED') and write via save_robot_candidate_state() (during WAITING_BREAKOUT/WAITING_RETEST/RETEST_DETECTED/EXPIRED_AT_APEX transitions) and eventually create_robot_trade() once robot_entry_limit/robot_market_confirmation approve an actual entry",
    "The four execution-policy modules already hand fully-built commands to existing shared PaperRuntime capabilities rather than executing anything themselves: robot_entry_limit.py hands a LIMIT command to PaperRuntime.create_limit(); robot_partial_fill.py's top-up/completion decisions and robot_market_confirmation.py's Market-entry decisions likewise route through shared Terminal execution (create_limit/cancel_limit/amend_limit/full_close); robot_protection.py plans STOP/TAKE but leaves the mutation to the shared PAPER protection capability. This is the same 'coordination code decides, shared execution layer acts' split RobotRecoveryCoordinator already follows, and is the natural 'execute action' dependency surface for RobotBreakoutMonitor's PAPER binding",
    "No existing periodic background-tick mechanism exists inside PaperRuntime today: grep for Thread/threading/schedule/Timer/asyncio inside terminal/runtime/paper_runtime.py returns nothing. RobotRecoveryCoordinator.recover() is a one-shot call at construction, not a loop. The nearest local precedent for an owned background loop is terminal/market_data/hub.py:MarketDataHub, which starts its own daemon threading.Thread plus a threading.Event stop flag in start()/close(); terminal/runtime/paper_http_server.py uses the same daemon-thread-plus-stop-Event idiom in several places. Whichever of these idioms RobotBreakoutMonitor's periodic tick reuses, and who constructs/starts/stops it (PaperRuntime.__init__ itself, or the process bootstrap that also starts paper_http_server.py), is not yet decided -- see unresolved_decisions",
    "No existing multi-symbol live 1m-candle feed exists anywhere in the repository. bybit_api.py:get_candles(symbol, interval, limit) is a REST call for one symbol at a time (used today by main.py's sequential scanner loop over historical candles, not for a live per-tick feed). terminal/market_data/hub.py:MarketDataHub maintains one persistent WS connection per Terminal session and already generalizes to multiple symbols via SymbolContext, but it subscribes only to 'orderbook.{depth}.{symbol}' and 'publicTrade.{symbol}' topics (hub.py:_topics); SymbolContext.public_klines is a declared dict field with no producer anywhere -- no 'kline.*' WS topic is subscribed and no kline buffer implementation exists. There is therefore no ready-made 'next closed 1m candle, many symbols at once' primitive to inject as-is; three unresolved options are recorded below",
    "Existing coordinator-level test precedent (tests/test_robot_recovery_coordinator.py, tests/test_robot_runtime_wiring.py) constructs a real SQLiteStore against a temp-file database, injects a deterministic fake clock callable and fake book/instrument/geometry-index providers through the constructor, and asserts on resulting durable state -- no real network, no real time, no mocking of the store itself. This is the directly reusable pattern for testing RobotBreakoutMonitor: inject a fake scripted per-symbol closed-candle sequence and a fake action-recording executor, drive the coordinator's tick against a real temp-file SQLiteStore, and assert on resulting robot_candidates/robot_trades rows"
  ],
  "approved_decisions": [
    "A new, reusable RobotBreakoutMonitor class is introduced, not bound to PAPER, following the existing terminal/application/robot_recovery.py:RobotRecoveryCoordinator pattern: it accepts a SQLiteStore, a trading_account_id, and dependency functions rather than a concrete PaperRuntime",
    "Dependencies are passed explicitly as constructor parameters with simple, explicit boundaries for future reuse: a 'get the next closed 1m candle for a symbol' function and an 'execute action' function (open LIMIT, cancel, confirm fill, invoke protection) -- paper_runtime.py instantiates the class with PAPER implementations of these dependencies today; a future live_runtime.py can instantiate the same class with live implementations without duplicating coordination code",
    "This follows the Freqtrade precedent of one shared coordination/strategy loop serving both dry-run and live, with only the execution layer differing between modes -- not duplicating the full cycle per mode",
    "The loop is embedded into paper_runtime.py as another background coordinator, next to the existing RobotRecoveryCoordinator (self._robot_recovery) -- not a separate OS process and not a new HTTP bridge",
    "Cadence is tied to TIMEFRAME (currently \"1\", i.e. once per new closed 1m candle), not to the Scanner's own scan cycle"
  ],
  "unresolved_decisions": [
    "Multi-symbol live closed-1m-candle transport: (a) REST-poll bybit_api.get_candles() per APPROVED-candidate symbol once per TIMEFRAME tick, reusing the existing single-symbol REST call the scanner already uses; (b) extend terminal/market_data/hub.py:MarketDataHub with a new 'kline.{interval}.{symbol}' WS subscription and populate the already-declared but empty SymbolContext.public_klines buffer; (c) derive synthetic closed-1m OHLC bars from the already-subscribed 'publicTrade.{symbol}' stream. No evidence-based choice, prototype, or approval exists yet",
    "Whether the 'get next closed candle' dependency is pull-based (RobotBreakoutMonitor calls a provider synchronously on its own tick, matching RobotRecoveryCoordinator's existing Callable-provider style) or push-based (a feed calls back into the monitor as each candle closes) -- affects the exact injected function signature",
    "Whether one tick batch-fetches every APPROVED candidate's symbol together (fewer REST calls, simpler rate-limit accounting) or the injected provider is invoked once per symbol independently -- affects the dependency's exact signature (single-symbol call vs. multi-symbol batch call)",
    "Which existing background-thread idiom (MarketDataHub's own daemon Thread + threading.Event stop flag, vs. some other mechanism) RobotBreakoutMonitor's periodic tick reuses, and who owns starting/stopping it (PaperRuntime.__init__ itself vs. the process bootstrap that already starts paper_http_server.py) -- today PaperRuntime has no background-tick mechanism of its own to hook into",
    "Concurrency discipline between RobotRecoveryCoordinator (which already mutates robot_candidates rows during recover(), e.g. EXPIRED_AT_APEX) and the new periodic RobotBreakoutMonitor writer: save_robot_candidate_state() already enforces optimistic concurrency via expected_revision, but the exact sequencing guarantee needed between a one-shot recovery pass and a periodic live pass is not yet specified"
  ],
  "acceptance_criteria": [
    "(Gates the future IMPLEMENT phase, not this revision.) A durable APPROVED Robot candidate can reach a robot_trades row through RobotBreakoutMonitor without any change to robot_state_machine.py, robot_entry_limit.py, robot_partial_fill.py, robot_market_confirmation.py or robot_protection.py's existing tested decision logic",
    "RobotBreakoutMonitor accepts its market-data and execution dependencies purely as constructor parameters and contains no PAPER-specific or live-specific branching itself",
    "paper_runtime.py instantiates RobotBreakoutMonitor with PAPER-bound dependencies alongside the existing RobotRecoveryCoordinator, without introducing a new OS process or HTTP endpoint",
    "The monitor's tick cadence is driven by TIMEFRAME, not by the Scanner's scan cycle",
    "Existing focused tests for the five pure Robot modules and for RobotRecoveryCoordinator/paper_runtime wiring continue to pass unmodified",
    "A new focused test suite drives RobotBreakoutMonitor with a fake scripted closed-candle sequence and a fake action-recording executor against a real temp-file SQLiteStore, verifying candidate-state transitions and eventual robot_trades creation without any real network or real timer"
  ],
  "verification_requirements": [
    "(Applies to the future IMPLEMENT/VERIFY phase.) Focused RobotBreakoutMonitor unit/coordinator tests plus full existing Robot regression suite (tests/test_robot_state_machine.py, tests/test_robot_entry_limit.py, tests/test_robot_partial_fill.py, tests/test_robot_market_confirmation.py, tests/test_robot_protection.py, tests/test_robot_recovery_coordinator.py, tests/test_robot_runtime_wiring.py, tests/test_robot_admission.py, tests/test_terminal_persistence.py)",
    "Standalone durable ChangeRequest governance validation for this CR file",
    "Artifact-free compile, git diff --check and scoped allowlist review",
    "A repeated local paper run demonstrating an APPROVED candidate actually reaching robot_trades, as the direct counter-evidence to DOCUMENTS/ROBOT_V0_1_LOCAL_PAPER_RUN_2026-09-12.md"
  ],
  "risks": [
    "REST-polling every APPROVED candidate's symbol once per 1m tick could approach Bybit rate limits at scale if option (a) in unresolved_decisions is eventually chosen without batching",
    "Two writers now touch robot_candidates state (RobotRecoveryCoordinator's one-shot recovery pass and the new periodic RobotBreakoutMonitor) -- optimistic-concurrency protection already exists (expected_revision) but the required sequencing/ordering guarantee between the two has not been specified",
    "A candidate admitted mid-way through an in-progress 1m bar could be picked up on a partial candle if the tick/candle-boundary alignment is not carefully defined",
    "The five pure Robot modules have only ever been exercised in isolation; their real end-to-end composition across a live sequence of closed candles has zero existing integration-level coverage today",
    "Choosing to extend MarketDataHub for kline data would couple a Robot dependency to the Trading Workspace market-data layer, which is independently evolving under the active CR-TRADING-WORKSPACE-001 -- needs explicit scoping if chosen"
  ],
  "rollback_boundaries": [
    "This revision (1.0) changes only this ChangeRequest document -- no production code is touched, so there is nothing to roll back yet",
    "The future IMPLEMENT phase must land RobotBreakoutMonitor and its paper_runtime.py instantiation as one independently revertible change; rollback restores the current (non-functional) state without touching robot_candidates/robot_trades schema or any of the five existing tested pure modules"
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
  "current_checkpoint": "CANDIDATE_STATE_LIVE_CANDLE_AND_TEST_CONTEXT_RECORDED_IMPLEMENT_PENDING_APPROVAL",
  "implementation_status": "IMPLEMENTATION_NOT_STARTED_NOT_AUTHORIZED",
  "next_phase": "IMPLEMENT",
  "next_phase_authorization": "NOT_AUTHORIZED_PENDING_HUMAN_APPROVAL_OF_THIS_CR",
  "related_commits": [
    {"phase": "BASELINE", "commit": "95418d75672e9057b294422ae2a66025559defdd"}
  ],
  "repository_sync": {
    "branch": "robot-v0-1-admission-gate",
    "baseline_local_head": "95418d75672e9057b294422ae2a66025559defdd",
    "status": "PENDING_CHECKPOINT_COMMIT"
  },
  "amendment_history": [
    {"revision": "1.0", "reason": "Human-authorized durable CR opened recording the Robot v0.1 breakout/retest lifecycle wiring gap finding and the RobotBreakoutMonitor architecture decision approved in chat; CONTEXT-stage research on candidate-state read/write locations, multi-symbol live-candle retrieval options and applicable test patterns recorded in the same revision; IMPLEMENT explicitly not authorized pending separate human confirmation", "date": "2026-09-12"}
  ]
}
```
<!-- CHANGE_REQUEST_METADATA_END -->

## Recovery summary

`robot_state_machine.py` and its four execution-policy siblings (`robot_entry_limit.py`,
`robot_partial_fill.py`, `robot_market_confirmation.py`, `robot_protection.py`) are complete and
individually tested, but nothing in the live-running code (`main.py`, `telegram_review.py`,
`terminal/runtime/paper_runtime.py`) ever calls them. The only thing that currently happens to an
approved candidate is admission into the `robot_candidates` SQLite table via
`terminal/application/robot_admission.py:admit_robot_candidate()`, called from `telegram_review.py`'s
Telegram approve callback. `terminal/application/robot_recovery.py:RobotRecoveryCoordinator` touches
`APPROVED` candidates only once, synchronously, during `PaperRuntime.__init__` — a restart-reconciliation
pass, not a live per-candle loop. `DOCUMENTS/ROBOT_V0_1_LOCAL_PAPER_RUN_2026-09-12.md` recorded exactly
this: 2 candidates reached `APPROVED`, 0 reached `robot_trades`.

The approved architecture (agreed in chat) is a new `RobotBreakoutMonitor` coordinator, structurally
mirroring `RobotRecoveryCoordinator` — constructed with a `SQLiteStore`, a `trading_account_id`, and
explicit dependency-injected functions for "get the next closed 1m candle for a symbol" and "execute
action" — instantiated with PAPER bindings inside `paper_runtime.py` alongside the existing
`self._robot_recovery`, ticking on TIMEFRAME rather than the Scanner's own cycle. This follows the same
dry-run/live coordination-vs-execution split Freqtrade uses, so a future `live_runtime.py` can reuse the
same coordinator with live bindings instead of a duplicated cycle. `live_runtime.py` itself, the Scanner,
and the existing pure modules' decision logic are explicitly out of scope for this CR.

This revision (1.0) is CONTEXT-stage only. It records: every location that reads or writes Robot candidate
state (`terminal/persistence/sqlite_store.py`'s `create_robot_candidate` / `load_robot_candidates` /
`save_robot_candidate_state` / `create_robot_trade`), the existing PAPER execution surface the four policy
modules already hand commands to (`create_limit` / `cancel_limit` / `amend_limit` / `full_close` /
protection mutation methods), the fact that **no** multi-symbol live 1m-candle feed exists anywhere in the
repository today (`bybit_api.get_candles()` is single-symbol REST; `MarketDataHub`'s `public_klines` field
is declared but has no producer), and the existing coordinator-test pattern
(`tests/test_robot_recovery_coordinator.py`) that a `RobotBreakoutMonitor` test suite would follow. Three
concrete unresolved options for the live-candle transport, and the lack of any existing periodic-tick
mechanism inside `PaperRuntime`, are recorded under `unresolved_decisions` rather than decided here.

**IMPLEMENT is explicitly not authorized by this revision.** No `RobotBreakoutMonitor` code has been
written and `paper_runtime.py` has not been touched. A separate human approval is required before
implementation begins.

## Amendment rule

Material scope, approved decision, risk, acceptance, lifecycle or implementation-authorization changes
require a new revision and explicit human approval.
