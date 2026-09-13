# CR-ROBOT-BREAKOUT-MONITOR-001 — Wire Robot v0.1 Breakout/Retest Lifecycle to Approved Candidates

<!-- CHANGE_REQUEST_METADATA_BEGIN -->
```json
{
  "schema_version": "1.0",
  "id": "CR-ROBOT-BREAKOUT-MONITOR-001",
  "title": "Wire Robot v0.1 Breakout/Retest Lifecycle to Approved Candidates via a Reusable RobotBreakoutMonitor Coordinator",
  "governance_type": "DESIGN_TO_IMPLEMENTATION_CHANGE_REQUEST",
  "status": "CLOSED",
  "revision": "1.3",
  "lifecycle_stage": "RECORD",
  "objective": "Introduce a mode-agnostic RobotBreakoutMonitor coordinator, modeled on the existing terminal/application/robot_recovery.py:RobotRecoveryCoordinator pattern, that drives each durable APPROVED Robot candidate through the already-implemented and already-tested robot_state_machine.py / robot_entry_limit.py / robot_partial_fill.py / robot_market_confirmation.py / robot_protection.py pipeline on every new closed 1m candle, so that APPROVED candidates can actually reach robot_trades instead of stalling forever.",
  "non_goals": [
    "Change Scanner behavior, main.py, pattern/geometry detection, or the Scanner-side Telegram handoff (notification.py, robot_candidate_store.py)",
    "Change entry/pattern strategy logic inside robot_state_machine.py, robot_entry_limit.py, robot_partial_fill.py, robot_market_confirmation.py or robot_protection.py -- this CR delivers already-approved, already-tested logic to a real caller, it does not redesign that logic",
    "Implement live_runtime.py or any live-exchange execution path -- only reserve a dependency-injection boundary shaped so a future live implementation can reuse the same coordinator without duplicating coordination code",
    "Introduce a new OS process, a new HTTP bridge/endpoint, or any transport outside the existing paper_runtime.py process",
    "LIMIT re-pricing/top-up (robot_partial_fill.py's topup_due()/build_topup_limit()) -- the wait/adverse-move/Market-completion cycle is wired, but re-pricing the resting remainder at a fresh boundary every 5 candles is not; a candidate whose LIMIT never fills at all today just keeps resting at its original price",
    "A fresh Market-entry path for a candidate whose LIMIT never receives ANY fill (robot_market_confirmation.py's own evaluate_confirmation() gate) -- only the partial-fill MARKET_COMPLETE bridge is wired in this revision; a zero-fill LIMIT has no automated fallback yet",
    "Automated resolution for a partially-filled position stuck at APEX_REACHED or persistently BLOCKED_AMBIGUOUS/BLOCKED_POOR_RR -- these decisions are correctly surfaced but left as-is (no forced close, no invalidation); an operator would need to intervene manually today"
  ],
  "approved_scope": [
    "CONTEXT-stage research recorded in revision 1.0: enumerate every location that reads or writes Robot candidate state, and the existing Robot execution-command surface those pure modules already hand commands to",
    "CONTEXT-stage research recorded in revision 1.0: enumerate existing live/near-live multi-symbol market-data mechanisms in the repository and their gaps relative to a per-symbol closed-1m-candle feed",
    "CONTEXT-stage research recorded in revision 1.0: identify the existing test patterns (fake clock, fake providers, real temp-file SQLiteStore) that a RobotBreakoutMonitor test suite would follow",
    "IMPLEMENTED in revision 1.1: terminal/application/robot_breakout_monitor.py -- lazy robot_state initialization, WAITING_BREAKOUT -> WAITING_RETEST -> RETEST_DETECTED / EXPIRED_AT_APEX progression, and the initial retest LIMIT submission",
    "IMPLEMENTED in revision 1.1: scanner_geometry_cursor.py:latest_scanner_closed_candle(), the default PAPER closed-1m-candle provider",
    "IMPLEMENTED in revision 1.1: paper_runtime.py wiring (instantiate/start after recovery, stop in close())",
    "IMPLEMENTED in this revision (1.2), using the user's four exact data-source resolutions: poll SQLiteStore.get_paper_limit() each tick once RETEST_DETECTED; on full fill (remainder=0) call robot_protection.build_protection_plan()/submit_initial_protection() then create_robot_trade() with entry_path='LIMIT'; on a genuine partial fill, cancel the resting remainder (see context_findings -- a fifth piece the four decisions did not by themselves cover), then evaluate_partial_completion() each tick using average_entry from SQLiteStore.get_position_projection() and stop/take computed via robot_protection.structural_stop()/frozen_take_90(); once MARKET_COMPLETE, bridge into robot_market_confirmation.build_confirmation_market()/submit_confirmation_market() and, once COMPLETED, call create_robot_trade() with entry_path='MIXED'",
    "IMPLEMENTED in this revision (1.2): ActionExecutor is now one unified Protocol (create_limit, cancel_limit, market, create_stop/amend_stop/create_take/amend_take, full_close) -- PaperRuntime already satisfies all of it as a single object, replacing revision 1.1's limit-only 'limit_submitter' parameter (renamed action_executor)",
    "IMPLEMENTED in this revision (1.2): tests/test_robot_breakout_monitor.py rewritten/expanded to cover the full LIMIT and MIXED (partial-fill-to-market) paths through to a created, protected robot_trades row, using a fake ActionExecutor that applies fills directly against the store (bypassing the pretrade guard/execution engine, which have their own dedicated coverage)"
  ],
  "prohibited_scope": [
    "main.py, notification.py, robot_candidate_store.py (Scanner-side handoff envelope) without new evidence and approved amendment",
    "Internal decision logic of robot_state_machine.py, robot_entry_limit.py, robot_partial_fill.py, robot_market_confirmation.py, robot_protection.py -- only their existing public call boundary may be invoked",
    "terminal/application/robot_admission.py and terminal/application/robot_control.py admission/control semantics (CR-ROBOT-CONTROL-001 territory) beyond reading robot_runtime_state to gate the monitor's activity",
    "live_runtime.py implementation or any live-exchange order submission",
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
    "wedge/potential.py",
    "geometry/touches.py",
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
    "robot_state_machine.py, robot_entry_limit.py, robot_partial_fill.py, robot_protection.py and robot_market_confirmation.py are fully implemented and individually tested but had zero live callers before revision 1.1; the full production admission path (main.py -> notification.py -> Telegram approve -> telegram_review.py -> robot_admission.py:admit_robot_candidate() -> SQLiteStore.create_robot_candidate()) inserts an APPROVED candidate with robot_state_json=NULL and nothing progressed it further -- exactly the gap DOCUMENTS/ROBOT_V0_1_LOCAL_PAPER_RUN_2026-09-12.md recorded (2 APPROVED, 0 robot_trades)",
    "CORRECTED DURING IMPLEMENT: the user's description of structural_extreme as 'upper_line/lower_line points' does not match the real exported schema. geometry/candidate.py sets line['points'] to an INTEGER COUNT (len(candidate_points)), not a list -- the real per-touch price data lives at a DIFFERENT, sibling path: signal_snapshot['geometry']['touches']['lower_touch_points'] / ['upper_touch_points'] (geometry/touches.py:analyze_touches(), each item shaped {index, price, predicted, distance, score, touch_tolerance, violation_tolerance, classification, counted}). RobotBreakoutMonitor._structural_extreme() reads this corrected path, and additionally filters to counted=True points before taking min/max -- an outlier/violation wick that never counted as a genuine touch should not define the structural stop; this filter was not itemized in the user's decision but follows directly from what 'the point the boundary was built on' means and is recorded here as a resolved implementation detail",
    "VERIFIED: wedge/potential.py:calculate_potential_move() confirms geometry['pair_metrics']['reference_price'] and ['start_width'] exist exactly as the user described, with the same Falling-Wedge-UP / Rising-Wedge-DOWN sign convention RobotBreakoutMonitor._frozen_prices() reuses (target = reference +/- abs(start_width))",
    "VERIFIED: terminal/persistence/sqlite_store.py:get_paper_limit()/PaperLimitOrderRecord.filled_quantity and .status exist exactly as the user described; the CHECK constraint (terminal/persistence/schema.py) limits status to {'open','partially_filled','filled','cancelled'} -- order_authoritatively_inactive is status in {'filled','cancelled'}",
    "DISCOVERED DURING IMPLEMENT (unit-conversion gap the four decisions did not address): PaperLimitOrderRecord.filled_quantity/quantity are raw base-asset quantities, NOT the 0..1 'WV' fraction robot_partial_fill.py/robot_market_confirmation.py expect as filled_wv. Because the original LIMIT is always sized as exactly 1 WV (robot_entry_limit.py requests VolumeRequest(WORKING_VOLUME, Decimal('1'))), order.quantity IS that 1-WV baseline, so filled_wv = order.filled_quantity / order.quantity correctly recovers the 0..1 fraction. This conversion is implemented in RobotBreakoutMonitor and was not explicit in the user's 'filled_quantity ... directly' phrasing",
    "DISCOVERED DURING IMPLEMENT (a fifth necessary piece beyond the four decisions): robot_partial_fill.evaluate_partial_completion() only ever returns MARKET_COMPLETE when order_authoritatively_inactive is already True -- reading its logic order, an ACTIVE (open/partially_filled) resting LIMIT always forces BLOCKED_AMBIGUOUS regardless of elapsed wait time. Neither robot_partial_fill.py nor any other of the five pure modules provides a 'cancel the resting remainder' function -- this is orchestration only this coordinator can own. RobotBreakoutMonitor therefore cancels the resting LIMIT (idempotent, digest-based client_action_id, mirroring PaperRuntime.robot_close_all()'s existing pattern for Robot-owned actions outside the five pure modules) as soon as a genuine partial fill is observed and still active, before ever evaluating completion",
    "DISCOVERED DURING IMPLEMENT: robot_partial_fill.py has no Market-order-building function of its own -- DECISION_MARKET_COMPLETE is a bare decision with no companion 'build the market order' call. The actual Market-order construction/submission machinery (MarketCommandRequest, build_confirmation_market(), submit_confirmation_market()) lives in robot_market_confirmation.py and is gated on its OWN ConfirmationDecision.action == DECISION_MARKET_ENTRY, a different string constant than robot_partial_fill.DECISION_MARKET_COMPLETE. RobotBreakoutMonitor bridges the two by constructing a robot_market_confirmation.ConfirmationDecision(action=DECISION_MARKET_ENTRY, missing_wv=<from the partial-fill decision>, ...) itself and passing it into build_confirmation_market()/submit_confirmation_market() -- this calls only the existing public functions of both modules with coordinator-built input, it does not duplicate or reimplement either module's decision logic",
    "ACCEPTED SIMPLIFICATION (flagged, not silently assumed): after a completed Market top-up, the total actual_wv passed to create_robot_trade() is computed as filled_wv_before + decision.missing_wv (capped at 1), not independently re-verified against the post-fill position size via a fresh WV/raw-quantity re-conversion -- doing so would require importing the account-equity-dependent working_volume_usdt sizing logic this coordinator does not otherwise need. The Market command result's own CommandResultStatus is still checked (must be COMPLETED) before this assumption is relied on; residual risk if PAPER book depth allows only a further partial Market fill",
    "PaperRuntime already exposes every method the full chain needs on one object -- create_limit, cancel_limit, market, create_stop, amend_stop, create_take, amend_take, full_close -- so ActionExecutor (renamed from revision 1.1's limit-only 'limit_submitter') is a single unified dependency, matching the CR's original 'execute action' concept exactly rather than three separate injected callables",
    "REMOVED FROM REVISION 1.1: the 'idempotently resubmit the LIMIT every tick while RETEST_DETECTED' behavior is replaced by 'submit once, capture the real order_id, then poll get_paper_limit() using that id' -- now that fill-state polling exists, blind resubmission every tick is unnecessary and would only add confusing duplicate-submission noise next to the polling path",
    "terminal/application/*.py's no-network/no-mutation layering guard (tests/test_terminal_execution_engine.py:test_no_mutation_or_network_api_is_exposed) still passes with the expanded module -- confirmed by direct re-run, not just by absence of new top-level imports of config/scanner/main/requests/pybit/websocket"
  ],
  "approved_decisions": [
    "A new, reusable RobotBreakoutMonitor class is introduced, not bound to PAPER, following the existing terminal/application/robot_recovery.py:RobotRecoveryCoordinator pattern: it accepts a SQLiteStore, a trading_account_id, and dependency functions rather than a concrete PaperRuntime",
    "This follows the Freqtrade precedent of one shared coordination/strategy loop serving both dry-run and live, with only the execution layer differing between modes -- not duplicating the full cycle per mode",
    "The loop is embedded into paper_runtime.py as another background coordinator, next to the existing RobotRecoveryCoordinator (self._robot_recovery) -- not a separate OS process and not a new HTTP bridge",
    "Cadence is tied to TIMEFRAME (currently \"1\", i.e. once per new closed 1m candle), not to the Scanner's own scan cycle",
    "Multi-symbol live closed-1m-candle transport is REST-poll via bybit_api.get_candles() (through analyzer.candles.load_candles()), not extending MarketDataHub -- chosen specifically to avoid coupling this candidate-lifecycle dependency to the Trading Workspace market-data layer, which is independently evolving under the active CR-TRADING-WORKSPACE-001",
    "The 'get next closed candle' dependency is pull-based: RobotBreakoutMonitor calls the injected provider synchronously on its own tick, exactly matching RobotRecoveryCoordinator's existing Callable-provider style -- not push/callback-based",
    "No batching: the provider is invoked once per symbol, sequentially, on every tick, with no separate batch-fetch infrastructure -- the expected number of concurrently active Robot candidates is small enough that per-symbol REST calls are acceptable",
    "RobotBreakoutMonitor's periodic tick reuses the same background-thread idiom already used by terminal/market_data/hub.py:MarketDataHub -- a daemon threading.Thread plus a threading.Event stop flag -- and is started/stopped by PaperRuntime.__init__ itself (via .start()/.close()), not by a separate process-bootstrap mechanism",
    "RobotBreakoutMonitor's thread starts strictly after RobotRecoveryCoordinator.recover() completes inside PaperRuntime.__init__; the existing expected_revision optimistic-concurrency check in save_robot_candidate_state() is accepted as sufficient race protection for Robot v0.1, with no additional lock introduced",
    "filled_wv and order_authoritatively_inactive are sourced from SQLiteStore.get_paper_limit(order_id, trading_account_id)'s filled_quantity and status fields directly, with status in {'filled','cancelled'} meaning order_authoritatively_inactive=True; filled_quantity is converted to the 0..1 WV fraction by dividing by the order's own quantity (see context_findings)",
    "average_entry is sourced from SQLiteStore.get_position_projection(key).average_entry directly. structural_extreme is the most extreme counted touch point (geometry.touches.lower_touch_points for LONG, .upper_touch_points for SHORT) of the frozen signal_snapshot's boundary line the entry pattern was built on. rr is pure arithmetic (robot_market_confirmation.risk_reward_ratio over entry/stop/take), requiring no new data source",
    "frozen_signal_reference_price = signal_snapshot['geometry']['pair_metrics']['reference_price']; frozen_scanner_target_price = reference_price +/- pair_metrics['start_width'] (sign by direction, the same formula already used by wedge/potential.py:calculate_potential_move) -- both already present in the existing signal_snapshot, no new Scanner field needed",
    "create_robot_trade() is called in the same tick that either get_paper_limit() confirms FILLED (remainder=0) or a Market top-up via the robot_partial_fill/robot_market_confirmation bridge completes, immediately after robot_protection places STOP/TAKE"
  ],
  "unresolved_decisions": [],
  "acceptance_criteria": [
    "A durable APPROVED Robot candidate with no robot_state is lazily initialized by RobotBreakoutMonitor and advances through WAITING_BREAKOUT -> WAITING_RETEST -> RETEST_DETECTED (or EXPIRED_AT_APEX) exactly as robot_state_machine.py already defines, without any change to that module's decision logic",
    "Once RETEST_DETECTED, RobotBreakoutMonitor submits exactly one initial retest LIMIT via robot_entry_limit.py's existing build/submit functions and then polls it via SQLiteStore.get_paper_limit()",
    "A LIMIT that reaches full fill (remainder=0) results in robot_protection placing STOP/TAKE and create_robot_trade() being called with entry_path='LIMIT' in the same tick",
    "A genuine partial fill causes the resting remainder to be cancelled, then evaluated tick-by-tick via robot_partial_fill.evaluate_partial_completion(); once it returns MARKET_COMPLETE, a Market order for the missing volume is submitted via the robot_market_confirmation bridge, and on confirmed completion robot_protection places STOP/TAKE and create_robot_trade() is called with entry_path='MIXED'",
    "RobotBreakoutMonitor accepts its market-data and execution dependencies purely as constructor parameters (one unified ActionExecutor Protocol) and contains no PAPER-specific or live-specific branching itself",
    "paper_runtime.py instantiates RobotBreakoutMonitor with PAPER-bound dependencies alongside the existing RobotRecoveryCoordinator, started only after recovery completes, without introducing a new OS process or HTTP endpoint",
    "No existing PaperRuntime-constructing test makes a real network call as a result of this change",
    "Existing focused tests for the five pure Robot modules, RobotRecoveryCoordinator/paper_runtime wiring, and the terminal/application/* no-network/no-mutation layering guard continue to pass unmodified",
    "tests/test_robot_breakout_monitor.py exercises both the full-LIMIT-fill and partial-fill-to-Market-completion paths end to end against a real temp-file SQLiteStore, asserting the created robot_trades row's entry_path, actual_wv, average_entry, stop_price and take_price"
  ],
  "verification_results": [
    "Durable governance gate PASS (python -m tools.project_sync.governance.change_request)",
    "tests/test_robot_breakout_monitor.py: 10 of 10 PASS",
    "Combined focused Robot/paper-runtime/persistence/layering-guard suite: 151 of 151 PASS",
    "Full repository suite: 882 passed, 8 pre-existing failures confirmed unrelated (reproduced identically against the pre-CR baseline by stashing this CR's changes)",
    "terminal/application/*.py no-network/no-mutation layering guard (test_no_mutation_or_network_api_is_exposed): PASS"
  ],
  "acceptance_state": "SATISFIED_FOR_APPROVED_SCOPE_WITH_DOCUMENTED_RESIDUAL_GAPS_DEFERRED",
  "mission_outcome": [
    "RobotBreakoutMonitor implemented and wired into paper_runtime.py, structurally mirroring RobotRecoveryCoordinator",
    "A durable APPROVED Robot candidate now advances WAITING_BREAKOUT -> WAITING_RETEST -> RETEST_DETECTED -> initial LIMIT -> (full fill or cancel+partial-fill+Market completion) -> protection -> create_robot_trade, closing the wiring gap DOCUMENTS/ROBOT_V0_1_LOCAL_PAPER_RUN_2026-09-12.md recorded",
    "All nine architecture/data-source decisions across revisions 1.0-1.2 were resolved by the user and implemented without modifying any of the five pure Robot modules' internal decision logic",
    "Known residual gaps (LIMIT re-pricing, zero-fill fresh-entry fallback, automated resolution of a stuck partial fill) are explicitly out of this CR's approved scope and documented as candidates for a future follow-up CR, not silently dropped",
    "Full regression (882 passed) and the terminal/application/* no-network/no-mutation layering guard confirmed passing; a real-environment local paper run remains the next, separate verification step outside this CR's unit/integration-test scope"
  ],
  "verification_requirements": [
    "Focused tests/test_robot_breakout_monitor.py suite passing (10 tests: lazy init, LIMIT-submission timing, apex expiry, full-LIMIT-fill trade creation, partial-fill wait-then-market-complete trade creation, unavailable-candle tolerance, concurrent-writer safety, two-symbol independence, thread start/close safety, structural_extreme/frozen_prices for SHORT)",
    "Full existing Robot regression suite passing unmodified: tests/test_robot_state_machine.py, tests/test_robot_entry_limit.py, tests/test_robot_partial_fill.py, tests/test_robot_market_confirmation.py, tests/test_robot_protection.py, tests/test_robot_recovery_coordinator.py, tests/test_robot_runtime_wiring.py, tests/test_robot_admission.py, tests/test_scanner_geometry_cursor.py, tests/test_terminal_persistence.py, tests/test_terminal_paper_runtime.py, tests/test_terminal_execution_engine.py (including the no-network/no-mutation layering guard)",
    "Full repository test suite run: 882 passed, 8 pre-existing failures confirmed unrelated (reproduced identically by stashing this CR's changes and re-running against the unmodified baseline -- schema-migration/task-harness/telegram tests, none touching Robot code)",
    "Standalone durable ChangeRequest governance validation for this CR file",
    "Artifact-free compile, git diff --check and scoped allowlist review",
    "A repeated local paper run demonstrating an APPROVED candidate actually reaching robot_trades remains a separate, real-environment verification step beyond this unit/integration-test pass"
  ],
  "risks": [
    "REST-polling every APPROVED candidate's symbol once per 1m tick could approach Bybit rate limits at scale -- accepted for v0.1 given the expected small number of concurrently active candidates",
    "Two writers now touch robot_candidates state (RobotRecoveryCoordinator's one-shot recovery pass and the new periodic RobotBreakoutMonitor); the existing expected_revision optimistic-concurrency check is the accepted safeguard, with RobotBreakoutMonitor starting strictly after recovery completes each process start",
    "The 'assume full Market fill' simplification (see context_findings) means actual_wv on a MIXED trade is computed, not independently re-verified against post-fill position size; a thin-book partial Market fill would currently be recorded as if it fully completed",
    "No automated resolution exists yet for a partial fill stuck at APEX_REACHED or persistently BLOCKED_AMBIGUOUS/BLOCKED_POOR_RR, or for a LIMIT that never receives any fill at all (no re-pricing, no confirmation-based fresh entry) -- these candidates simply stop advancing and need manual operator attention",
    "The cancel-then-evaluate sequencing for partial fills is new orchestration with no precedent in the five pure modules; it is covered by tests/test_robot_breakout_monitor.py's partial-fill scenario but has no separate dedicated unit-level test of its own",
    "This is the coordinator's first exercise of robot_partial_fill.py, robot_market_confirmation.py and robot_protection.py composed together against real durable state; prior to this revision each was tested only in total isolation"
  ],
  "rollback_boundaries": [
    "RobotBreakoutMonitor (terminal/application/robot_breakout_monitor.py) plus its instantiation/teardown in terminal/runtime/paper_runtime.py plus the new scanner_geometry_cursor.latest_scanner_closed_candle() function and tests/test_robot_breakout_monitor.py form one independently revertible unit",
    "Rollback restores the previous (breakout/retest/initial-LIMIT-only, or fully non-functional) state without touching robot_candidates/robot_trades schema or any of the five existing tested pure modules"
  ],
  "implementation_phases": [
    {"id": "TASK", "status": "COMPLETED"},
    {"id": "SPEC", "status": "COMPLETED_HUMAN_APPROVED"},
    {"id": "CONTEXT", "status": "COMPLETED"},
    {"id": "IMPLEMENT", "status": "IMPLEMENTED_VERIFIED"},
    {"id": "VERIFY", "status": "IMPLEMENTED_VERIFIED"},
    {"id": "RECORD", "status": "COMPLETED_HUMAN_APPROVED"},
    {"id": "MISSION_CLOSE", "status": "COMPLETED"},
    {"id": "NO_NEXT_PHASE", "status": "NOT_APPLICABLE"}
  ],
  "current_phase": "MISSION_CLOSE",
  "current_checkpoint": "MISSION_CLOSE_COMPLETED",
  "implementation_status": "IMPLEMENTED_VERIFIED",
  "next_phase": "NO_NEXT_PHASE",
  "next_phase_authorization": "NOT_APPLICABLE",
  "related_commits": [
    {"phase": "BASELINE", "commit": "95418d75672e9057b294422ae2a66025559defdd"},
    {"phase": "REVISION_1_0_CHECKPOINT", "commit": "1cdddbf7ce90d3dc0aa9dc4b64d17ba5f0aa3c9c"},
    {"phase": "REVISION_1_1_CHECKPOINT", "commit": "1dbec876be71b98272cfab20d4e5d54de222d85d"},
    {"phase": "REVISION_1_2_CHECKPOINT", "commit": "a769cafd5c81e77d6709e90d08146f0f78a96be6"}
  ],
  "repository_sync": {
    "branch": "robot-v0-1-admission-gate",
    "baseline_local_head": "95418d75672e9057b294422ae2a66025559defdd",
    "local_head": "a769cafd5c81e77d6709e90d08146f0f78a96be6",
    "origin_branch": "a769cafd5c81e77d6709e90d08146f0f78a96be6",
    "status": "SYNCHRONIZED"
  },
  "amendment_history": [
    {"revision": "1.0", "reason": "Human-authorized durable CR opened recording the Robot v0.1 breakout/retest lifecycle wiring gap finding and the RobotBreakoutMonitor architecture decision approved in chat; CONTEXT-stage research on candidate-state read/write locations, multi-symbol live-candle retrieval options and applicable test patterns recorded in the same revision; IMPLEMENT explicitly not authorized pending separate human confirmation", "date": "2026-09-12"},
    {"revision": "1.1", "reason": "Human-authorized: the five unresolved live-candle-transport, threading and concurrency decisions resolved and recorded as approved_decisions with the user's exact choices; IMPLEMENT authorized and executed for the breakout/retest/initial-LIMIT portion (RobotBreakoutMonitor, scanner_geometry_cursor.latest_scanner_closed_candle(), paper_runtime.py wiring, focused test suite); partial-fill/confirmation/protection wiring and create_robot_trade() explicitly deferred to a follow-up revision pending newly discovered data-sourcing decisions this revision does not cover", "date": "2026-09-12"},
    {"revision": "1.2", "reason": "Human-authorized: the four remaining data-sourcing unresolved_decisions resolved and recorded as approved_decisions with the user's exact sources/formulas; IMPLEMENT continued and completed for the full chain to create_robot_trade() (partial fill, Market confirmation bridge, protection, trade creation) in the same pass, including one additional necessary piece discovered during implementation (cancelling the resting LIMIT remainder before Market completion can be evaluated) and one corrected field path (structural_extreme reads geometry.touches.*_touch_points, not upper_line/lower_line.points which is an integer count). Full existing suite plus the expanded focused suite verified passing", "date": "2026-09-12"},
    {"revision": "1.3", "reason": "Human-authorized: revision 1.2 approved as-is with no further code changes. Lifecycle formally updated to VERIFY/RECORD/MISSION_CLOSE reflecting the test runs already completed and pushed in commit a769caf (10/10 focused, 151/151 combined, 882 passed full-suite with 8 pre-existing unrelated failures). CR closed for its approved scope; residual gaps (LIMIT re-pricing, zero-fill fresh-entry fallback, stuck-partial resolution) remain explicitly documented as out of scope for a possible future follow-up CR", "date": "2026-09-12"}
  ]
}
```
<!-- CHANGE_REQUEST_METADATA_END -->

## Recovery summary

Revision 1.1 wired the breakout/retest lifecycle up to the initial retest LIMIT submission and left the
remaining chain (partial fill, Market confirmation, protection, `create_robot_trade()`) explicitly
deferred, because reaching a real `robot_trades` row needed data sources the original five decisions
didn't cover: where `filled_wv`/order-inactive status come from, where `average_entry`/`structural_extreme`/`rr`
come from, whether the frozen reference/target prices already exist in the signal snapshot, and exactly
when `create_robot_trade()` should fire.

Revision 1.2 resolves all four with the user's exact answers and implements the complete chain in the same
pass:

- **Full LIMIT fill** — `SQLiteStore.get_paper_limit()` confirms `remainder=0` → `average_entry` from
  `get_position_projection()` → `robot_protection.build_protection_plan()`/`submit_initial_protection()`
  places STOP/TAKE → `create_robot_trade(entry_path='LIMIT')`, same tick.
- **Partial fill** — on first genuine partial fill, the resting remainder is **cancelled** (a necessary
  fifth piece the four decisions didn't cover: `robot_partial_fill.evaluate_partial_completion()` only ever
  returns `MARKET_COMPLETE` once the order is authoritatively inactive, and no existing module owns
  "cancel the remainder" — this coordinator does, idempotently). Each subsequent tick recomputes
  `stop_price` (`structural_stop`/`tighten_stop`, never widening) and `take_price` (`frozen_take_90`) and
  calls `evaluate_partial_completion()`. Once it returns `MARKET_COMPLETE`, the decision is bridged into
  `robot_market_confirmation.build_confirmation_market()`/`submit_confirmation_market()` (constructing the
  `ConfirmationDecision` input themselves rather than modifying either module), and on a `COMPLETED` result,
  protection is placed and `create_robot_trade(entry_path='MIXED')` is called.
- **`structural_extreme`** reads the *verified-correct* path `signal_snapshot.geometry.touches.{lower,upper}_touch_points`
  (filtered to `counted=True`), not `upper_line`/`lower_line.points`, which turned out to be an integer
  touch *count*, not point data — caught and corrected during implementation rather than shipped broken.
- **`ActionExecutor`** is now one unified Protocol (`create_limit`, `cancel_limit`, `market`,
  `create_stop`/`amend_stop`/`create_take`/`amend_take`, `full_close`); `PaperRuntime` already satisfies
  all of it as a single object, replacing revision 1.1's limit-only `limit_submitter` parameter.

`tests/test_robot_breakout_monitor.py` was expanded from 7 to 10 tests, now covering both the full-LIMIT
and partial-fill-to-Market-completion paths end to end — including asserted `stop_price`/`take_price`
values computed from a crafted `touches`/`pair_metrics` fixture — against a real temp-file `SQLiteStore`
with a fake `ActionExecutor` that applies fills directly (bypassing the pretrade guard/execution engine,
which already have dedicated coverage elsewhere). The full existing regression suite (882 tests) and the
`terminal/application/*` no-network/no-mutation layering guard pass unmodified; the 8 failures in a full
repository run are pre-existing and unrelated (reproduced identically against the pre-CR baseline).

**Known residual gaps, explicitly not invented behavior:** no LIMIT re-pricing/top-up
(`topup_due`/`build_topup_limit`), no fresh-entry fallback for a LIMIT that never fills at all
(`robot_market_confirmation.evaluate_confirmation()`'s own gate is unused), and no automated resolution for
a partial fill stuck at `APEX_REACHED` or persistently blocked — these candidates simply stop advancing and
would need manual operator attention today. None of these were covered by the four decisions this revision
resolves.

Revision 1.3 closes the mission after revision 1.2 was approved as-is (no further code changes). The
`VERIFY` and `RECORD` phases are recorded against the test runs already completed and pushed in commit
`a769caf` — 10/10 focused, 151/151 combined Robot/paper-runtime/persistence/layering-guard, and 882 passed
in a full repository run with 8 pre-existing failures confirmed unrelated. No later phase exists for this
CR; the documented residual gaps remain candidates for a separate future ChangeRequest, and a real-environment
local paper run is tracked separately (see `DOCUMENTS/ROBOT_RUN_INDEX.md`).

## Amendment rule

Material scope, approved decision, risk, acceptance, lifecycle or implementation-authorization changes
require a new revision and explicit human approval.
