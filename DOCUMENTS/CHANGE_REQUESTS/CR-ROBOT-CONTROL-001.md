# CR-ROBOT-CONTROL-001 — Robot v0.1 Admission-Gate Operator Control Commands and Telegram Toggle Surface

<!-- CHANGE_REQUEST_METADATA_BEGIN -->
```json
{
  "schema_version": "1.0",
  "id": "CR-ROBOT-CONTROL-001",
  "title": "Robot v0.1 Admission-Gate Operator Control Commands and Telegram Toggle Surface",
  "governance_type": "DESIGN_TO_IMPLEMENTATION_CHANGE_REQUEST",
  "status": "OPEN",
  "revision": "1.2",
  "lifecycle_stage": "RECORD",
  "objective": "Implement the six Robot v0.1 admission-gate operator control commands (start_robot, pause_robot, resume_robot, close_all_now, stop_robot) exactly per DOCUMENTS/AUTOPILOT_ROBOT_V0_1_ROBOT_CONTROL_DECISION.md v1.2, add the durable schema representation for the paused state, and expose all six through a Telegram control surface where pause/resume is a single toggle button (not two independent buttons), reusing existing shared execution/recovery/persistence capabilities without duplicating them.",
  "non_goals": [
    "Any path out of RECONCILIATION_REQUIRED (remains separately unresolved per AUTOPILOT_ROBOT_V0_1_ROBOT_CONTROL_DECISION.md)",
    "Any change to STOP/TAKE calculation, priority, or the existing emergency-close/protection contract (robot_protection.py)",
    "Ownership-transfer/manual-takeover behavior (already deferred by AUTOPILOT_ROBOT_V0_1_TELEGRAM_ONLY_DECISION.md)",
    "Ownership/close-scope for manual (non-Robot) positions on the same PAPER account",
    "Any Trading Workspace/Terminal UI control surface for Robot v0.1 (Telegram remains the only surface per AUTOPILOT_ROBOT_V0_1_TELEGRAM_ONLY_DECISION.md)",
    "New pattern-detection/Geometry work, or advancing Slices 2-6 of AUTOPILOT_ROBOT_V0_1_IMPLEMENTATION_SLICES.md",
    "Changing PaperRuntime.close_all()'s existing account-wide (non-Robot-scoped) behavior or signature",
    "Introducing python-telegram-bot/aiogram or any framework migration away from the existing custom getUpdates long-poll design in telegram_review.py"
  ],
  "approved_scope": [
    "Implement start_robot(), pause_robot(), resume_robot(), close_all_now(), stop_robot() as new application-layer functions in a new terminal/application/robot_control.py, reusing RobotRecoveryCoordinator, SQLiteStore.update_robot_runtime_state(), and the existing shared full_close() execution path exactly per AUTOPILOT_ROBOT_V0_1_ROBOT_CONTROL_DECISION.md v1.2 Sections 1, 2, 4, 5 and 6",
    "Add recovery_status value PAUSED, valid only under mode=ROBOT_RUNNING, to the robot_runtime_state schema (SCHEMA_VERSION 15 -> 16), via a rebuild-table migration following the existing v6/v7/v9 CHECK-constraint-change pattern in terminal/persistence/schema.py, plus matching updates to ROBOT_RECOVERY_STATUSES and ROBOT_RUNTIME_STATE_PAIRS in terminal/persistence/sqlite_store.py",
    "Extend RobotRecoveryCoordinator.recover() (terminal/application/robot_recovery.py) so that a backend restart while mode=ROBOT_RUNNING/recovery_status=PAUSED returns to PAUSED after reconciliation completes successfully, instead of silently reverting to READY (see Rationale)",
    "Add a Robot-owned-only close-all helper (new function, not a reuse or modification of PaperRuntime.close_all()'s existing account-wide behavior) that close_all_now() uses to Market-close every open Robot-owned position via the existing shared full_close() path, filtering strictly by robot_candidates/robot_trades OPEN status for the account",
    "Add a Telegram inline-keyboard control surface (robot_telegram_feed.py: new keyboard builder) with Start, one combined Pause/Resume toggle button (single callback_data + label pair that flips with current durable admission state, per v1.2 Rationale), Close All, and Stop, rendered from live durable state on every callback so a rejected transition is never offered",
    "Wire the control surface into telegram_review.py's existing callback dispatch (_process_callback / new _parse_* helper(s)) and existing chat-id authorization check; post an explicit confirmation or rejection-reason message back to the operator for every command outcome",
    "Add a lightweight one-tap inline confirmation step before close_all_now() executes (see Rationale) — Start/Pause/Resume/Stop remain single-tap since none of them force a Market close",
    "New test module tests/test_robot_control.py covering the full legality matrix for all five state-transition functions across every durable state (ROBOT_STOPPED/ROBOT_STOPPED, ROBOT_STOPPED/RECONCILIATION_REQUIRED, ROBOT_RUNNING/READY, ROBOT_RUNNING/PAUSED, ROBOT_RUNNING/RECONCILIATION_REQUIRED), the v16 schema migration/CHECK constraints, and the pause-preserved-across-restart behavior",
    "Focused regression additions to tests/test_terminal_persistence.py for the new CHECK constraint pair and migration"
  ],
  "prohibited_scope": [
    "geometry/, wedge/, signal/quality.py — unrelated to this CR",
    "Any change to STOP/TAKE lifecycle logic or robot_protection.py's emergency-close contract",
    "Any change to PaperRuntime.close_all()'s existing behavior, signature, or callers",
    "Any change to manual/non-Robot position handling or accounting",
    "Any attempt to add a path out of RECONCILIATION_REQUIRED",
    "Adopting a Telegram bot framework in place of the existing custom long-poll design",
    "Unrelated production, documentation, training/reference, or dirty-work changes"
  ],
  "authoritative_references": [
    "DOCUMENTS/AUTOPILOT_ROBOT_V0_1_ROBOT_CONTROL_DECISION.md (v1.2, ACCEPTED DESIGN)",
    "DOCUMENTS/AUTOPILOT_ROBOT_V0_1_RESTART_FROM_STOPPED_DECISION.md",
    "DOCUMENTS/AUTOPILOT_ROBOT_V0_1_RECOVERY_STATE_BATCH_DECISION.md",
    "DOCUMENTS/AUTOPILOT_ROBOT_V0_1_TELEGRAM_ONLY_DECISION.md",
    "DOCUMENTS/AUTOPILOT_ROBOT_V0_1_MANAGEMENT_SIMPLIFICATION_DECISION.md",
    "DOCUMENTS/AUTOPILOT_ROBOT_V0_1_IMPLEMENTATION_SLICES.md (Slice 7, Telegram Robot minimum UX)",
    "DOCUMENTS/PROJECT_CONTRACTS.md#CONTRACT-CHANGE-REQUEST-001",
    "AGENTS.md#Task-and-change-routing"
  ],
  "context_scope_paths": [
    "terminal/application/robot_control.py",
    "terminal/application/robot_recovery.py",
    "terminal/application/robot_admission.py",
    "terminal/persistence/schema.py",
    "terminal/persistence/sqlite_store.py",
    "terminal/runtime/paper_runtime.py",
    "robot_protection.py",
    "telegram_review.py",
    "robot_telegram_feed.py",
    "config.py",
    "terminal/runtime/paper_http_server.py"
  ],
  "context_test_paths": [
    "tests/test_robot_control.py",
    "tests/test_robot_admission.py",
    "tests/test_robot_recovery_coordinator.py",
    "tests/test_robot_runtime_wiring.py",
    "tests/test_robot_telegram_feed.py",
    "tests/test_telegram_robot_control.py",
    "tests/test_telegram_robot_handoff.py",
    "tests/test_terminal_paper_runtime.py",
    "tests/test_terminal_execution_engine.py",
    "tests/test_terminal_persistence.py"
  ],
  "external_reference_inspiration": [
    "Freqtrade's stop/stopbuy vs forceexit/emergencysell command separation, already cited in AUTOPILOT_ROBOT_V0_1_ROBOT_CONTROL_DECISION.md v1.1 Rationale (design inspiration only, not vendored)"
  ],
  "approved_decisions": [
    "All six command semantics (legality preconditions, rejection behavior, effects) are exactly as specified in AUTOPILOT_ROBOT_V0_1_ROBOT_CONTROL_DECISION.md v1.2 Sections 1-6; this CR adds no new command semantics",
    "recovery_status gains a PAUSED value (valid only under mode=ROBOT_RUNNING) rather than adding a new mode value, per the user's recommendation in chat, analogous to the existing READY/RECONCILING/RECONCILIATION_REQUIRED values",
    "close_all_now() uses a new Robot-owned-only close path rather than PaperRuntime.close_all(), because that existing method closes every open position on the account and close_all_now() must act exclusively on Robot-owned positions per v1.2 Section 4 Scope",
    "pause_robot() and resume_robot() are exposed in Telegram as one toggle button (single callback_data + label pair driven by live durable state), not two independently visible buttons, per v1.2 Rationale",
    "close_all_now() gets one lightweight inline confirmation tap before executing, because it is the one command in this set that forces an immediate Market close of a live (PAPER) position; start_robot/pause_robot/resume_robot/stop_robot remain single-tap because none of them can force a close"
  ],
  "unresolved_decisions": [],
  "resolved_decisions": [
    "Restart-preservation gap closed: AUTOPILOT_ROBOT_V0_1_ROBOT_CONTROL_DECISION.md v1.2's Rationale for the PAUSED recommendation says the recovery pipeline 'runs only at explicit backend start, not periodically in background, so PAUSED will not be accidentally overwritten' -- true for periodic background jobs, but code inspection of RobotRecoveryCoordinator.recover() (terminal/application/robot_recovery.py:99-134) found it unconditionally drives mode=ROBOT_RUNNING through RECONCILING to READY on every backend start regardless of the recovery_status value found at that start, which would silently un-pause the robot across a backend restart if left unmodified. Resolved by explicit CR authorization (this document, approved_scope) rather than by re-opening the schema-representation question: recover() is extended to detect an existing PAUSED value before reconciling and to land back on PAUSED (not READY) after a successful reconciliation pass, so an operator's pause survives a backend restart exactly as a durable admission gate should.",
    "Telegram callback_data naming and keyboard placement are implementation details resolved directly during IMPLEMENT (not itemized here) since AUTOPILOT_ROBOT_V0_1_ROBOT_CONTROL_DECISION.md's own Explicit non-goals defers 'the concrete Telegram implementation (button/keyboard update mechanics, callback wiring)'",
    "close_all_now() execution-reachability gap (surfaced in revision 1.1) resolved by explicit user approval in chat: a new POST /api/robot/close-all-now route on terminal/runtime/paper_http_server.py, backed by a new PaperRuntime.robot_close_all() method (Robot-owned-symbols-only, unlike the existing account-wide PaperRuntime.close_all()), using the same trust model as the two existing routes (localhost-only, require_paper_mutations() gate, no additional operator-token authentication) -- see approved_scope and IMPLEMENTATION_RECORD for what was actually built",
    "terminal/application/robot_control.py's close_all_now() takes its HTTP transport (http_post) as a required parameter rather than importing requests directly: a full regression run surfaced that tests/test_terminal_execution_engine.py's test_no_mutation_or_network_api_is_exposed asserts nothing under terminal/application/*.py imports requests/pybit/websocket/config/scanner/main, enforcing that application-layer code stays free of network clients. The actual requests.post call was moved into telegram_review.py (which already depends on requests) as _post_robot_close_all_now(), passed into close_all_now(http_post=...) by the caller -- this was caught and fixed before the CR's own regression check would have passed uncaught, not shipped as a known gap"
  ],
  "acceptance_criteria": [
    "All five state-transition functions enforce exactly the legality matrix in AUTOPILOT_ROBOT_V0_1_ROBOT_CONTROL_DECISION.md v1.2 (correct preconditions, explicit rejection error otherwise), verified by tests covering every durable state",
    "resume_robot() is legal only from (ROBOT_RUNNING, PAUSED); rejected with an explicit error from RECONCILIATION_REQUIRED and every other state, symmetric to start_robot()",
    "pause_robot()/resume_robot() never affect an already-open Robot position; STOP/TAKE lifecycle code is untouched",
    "close_all_now() acts exclusively on Robot-owned open positions, verified against a fixture containing both a Robot-owned position and a manual position on the same account; the manual position is never touched",
    "A failed close_all_now() attempt lands the runtime in (ROBOT_RUNNING, RECONCILIATION_REQUIRED) regardless of whether it was called from READY or PAUSED",
    "stop_robot() v1.1 never itself initiates a position close; rejected with an explicit error naming pause_robot()+close_all_now() when a Robot-owned position is open",
    "A backend restart while mode=ROBOT_RUNNING/recovery_status=PAUSED returns to PAUSED after successful reconciliation, not READY",
    "Telegram pause/resume is exactly one button whose label and callback_data reflect current durable state; the keyboard is re-rendered from live state on every relevant callback so a rejected transition is structurally unreachable through that button",
    "close_all_now() requires one explicit confirmation tap in Telegram before executing; start_robot/pause_robot/resume_robot/stop_robot remain single-tap",
    "Existing tests/test_robot_admission.py, tests/test_robot_recovery_coordinator.py, tests/test_robot_runtime_wiring.py pass unmodified",
    "Full repository regression shows zero new failures/errors against the pre-existing baseline already documented in CR-SCANNER-GEOMETRY-002 (2 pre-existing FAIL, 19 pre-existing terminal/diary ERROR, unrelated to this change)"
  ],
  "verification_requirements": [
    "New tests/test_robot_control.py: full state x command legality matrix, close_all_now Robot-only scoping, close_all_now failure -> RECONCILIATION_REQUIRED, stop_robot rejection when a position is open",
    "Schema/migration regression in tests/test_terminal_persistence.py for the v16 CHECK constraint and rebuild migration, including a fresh-DB create and an upgrade-from-v15 path",
    "Restart-preserves-PAUSED regression in tests/test_robot_recovery_coordinator.py or the new test module",
    "Full repository regression (python -B -m unittest discover -s tests) compared against the pre-existing baseline",
    "Manual Telegram smoke: start from ROBOT_STOPPED, pause, confirm button flips to resume label/action, resume, close_all_now confirmation flow, stop after no position is open"
  ],
  "verification_results": [
    "New tests/test_robot_control.py (29 tests): full legality matrix for start_robot/pause_robot/resume_robot/stop_robot/close_all_now across every durable state combination, close_all_now's http_post injection (custom backend_url, backend-unreachable wrapped as RobotControlRejected, backend rejection propagated)",
    "tests/test_robot_recovery_coordinator.py (+4 tests): restart while (ROBOT_RUNNING, PAUSED) lands back on PAUSED both with and without a surviving open trade; new RobotRecoveryCoordinator.start() reaches (ROBOT_RUNNING, READY) from a never-initialized store and correctly recovers a surviving APPROVED candidate",
    "tests/test_terminal_persistence.py (+1 test): a real pre-v16 database (old CHECK constraint, no PAUSED, an existing (ROBOT_RUNNING, READY) row) is reopened through SQLiteStore, exercising the actual v15->v16 rebuild-table migration -- confirms the existing row's data is preserved, (ROBOT_RUNNING, PAUSED) is now accepted, and (ROBOT_STOPPED, PAUSED) is still correctly rejected",
    "tests/test_terminal_paper_runtime.py (+2 tests, pytest-style): PaperRuntime.robot_close_all() closes only the Robot-owned symbol (a real Market position opened via runtime.api.market, then a robot_candidates/robot_trades OPEN row attached) and leaves a manual position on a second symbol untouched; a full_close() result patched to REJECTED lands robot_runtime_state in (ROBOT_RUNNING, RECONCILIATION_REQUIRED)",
    "tests/test_robot_telegram_feed.py (+6 tests) and new tests/test_telegram_robot_control.py (+11 tests): control-keyboard rendering per durable state (stopped offers only Start; running/READY offers Pause+CloseAll+Stop; running/PAUSED toggles to Resume+CloseAll+Stop; RECONCILIATION_REQUIRED offers no buttons), the robot:cmd:* callback parser including close_all/close_all_confirm/close_all_cancel, the close_all confirmation keyboard, and telegram_review.py dispatch for all five commands including the close_all two-step confirm/cancel flow (a bare close_all tap never executes; only close_all_confirm does; close_all_cancel answers without executing)",
    "tests/test_terminal_execution_engine.py::test_no_mutation_or_network_api_is_exposed: this boundary test caught a real regression mid-IMPLEMENT (terminal/application/robot_control.py originally imported requests directly for close_all_now()'s default transport) before it was committed; fixed by making http_post a required parameter with no default, moving the actual requests.post call into telegram_review.py's new _post_robot_close_all_now(). Passes after the fix.",
    "Full repository regression using the project's own venv (venv/Scripts/python.exe, matching start_paper_backend.bat -- the earlier python -B -m unittest discover run used a bare system Python missing pytest, which made 19 pytest-style modules fail to import and produced a less accurate baseline): 729 tests, 2 failures (test_task_harness, test_telegram_delivery) / 6 errors (test_terminal_live_account_reconciliation x2, test_terminal_live_limit_acceptance x3, test_terminal_paper_stop::test_schema_v9_migration), all confirmed pre-existing and unrelated to this change -- the v9_migration error in particular was independently reproduced against the pre-CR baseline commit via git stash (fails identically with or without this CR's changes, in a v9->v10->v11 migration path this CR never touches). Zero new failures or errors."
  ],
  "review_result": {
    "verdict": "NOT_YET_REVIEWED",
    "blocking_findings": [],
    "important_findings": [],
    "minor_non_blocking_findings": []
  },
  "acceptance_state": "IMPLEMENTED_VERIFIED_PENDING_COMMIT_AUTHORIZATION",
  "risks": [
    "SQLite CHECK-constraint rebuild migration (v16) on robot_runtime_state risks data loss/corruption if the create/copy/drop/rename sequence is interrupted mid-migration; must follow the exact tested v6/v7/v9 pattern and be covered by a dedicated migration test",
    "Overloading recovery_status with an operator-intent value (PAUSED) alongside recovery-lifecycle values (RECONCILING/READY/RECONCILIATION_REQUIRED) mixes two different concerns in one column; a future recovery-pipeline change that does not know about PAUSED could silently re-introduce the restart-clobber gap this CR closes",
    "A Robot-owned-only close-all path duplicates some position-iteration logic already present in PaperRuntime.close_all(); risk of behavioral drift between the two if one is changed later without the other",
    "Telegram single-toggle button requires the keyboard to always be rendered from live durable state; a stale cached keyboard could show a label/action that no longer matches reality",
    "close_all_now() is financially consequential even in PAPER mode; insufficient confirmation UX could let an operator trigger an unintended Market close via a mis-tap"
  ],
  "residual_risks": [],
  "mission_outcome": [],
  "rollback_boundaries": [
    "Implementation lands as one or more scoped, independently revertible commits after verification",
    "Rollback restores the pre-CR robot_runtime_state schema (v15, no PAUSED value) and removes the five command functions and the Telegram control keyboard, without affecting robot_admission.py's existing gate check, robot_recovery.py's pre-CR recover() behavior, or any non-Robot execution path"
  ],
  "implementation_phases": [
    {"id": "TASK", "status": "COMPLETED"},
    {"id": "SPEC", "status": "COMPLETED"},
    {"id": "CONTEXT", "status": "COMPLETED"},
    {"id": "IMPLEMENT", "status": "COMPLETED"},
    {"id": "VERIFY", "status": "COMPLETED"},
    {"id": "RECORD", "status": "IN_PROGRESS"}
  ],
  "current_phase": "RECORD",
  "current_checkpoint": "ALL_FIVE_COMMANDS_IMPLEMENTED_VERIFIED_UNCOMMITTED",
  "implementation_status": "IMPLEMENTED_VERIFIED_PENDING_COMMIT_AUTHORIZATION",
  "next_phase": "RECORD_COMPLETE",
  "next_phase_authorization": "COMMIT_AUTHORIZATION_REQUIRED_PER_ASSISTANT_PROTOCOL_7.2",
  "related_commits": [
    {"phase": "BASELINE", "commit": "0bbbaab17289933ac71442aad3c4f92546a52034"},
    {"phase": "CR_DRAFT", "commit": "1132314"},
    {"phase": "IMPLEMENT", "commit": "UNCOMMITTED_AT_TIME_OF_WRITING"}
  ],
  "repository_sync": {
    "branch": "robot-v0-1-admission-gate",
    "local_head": "1132314",
    "status": "FEATURE_BRANCH_AHEAD_OF_MAIN / IMPLEMENT_AND_VERIFY_COMPLETE_LOCALLY_UNCOMMITTED_AT_TIME_OF_WRITING"
  },
  "amendment_history": [
    {"revision": "1.0", "reason": "Initial TASK/SPEC/CONTEXT formalization of AUTOPILOT_ROBOT_V0_1_ROBOT_CONTROL_DECISION.md v1.2 into a durable ChangeRequest per CONTRACT-CHANGE-REQUEST-001 (substantial, risky, multi-session, schema-changing work), following explicit user authorization in chat to implement all six commands. Records the codebase exploration (state machine location, Telegram dispatch pattern, schema, shared close-execution path, test conventions) and one technical correction to the user's own PAUSED-in-recovery_status recommendation (restart-preservation fix in RobotRecoveryCoordinator.recover()). Awaiting explicit approval of this revision before IMPLEMENT begins.", "date": "2026-09-11"},
    {"revision": "1.1", "reason": "User approved revision 1.0 as-is in chat; IMPLEMENT started. Delivered and verified: schema v16 migration (robot_runtime_state gains PAUSED, rebuild-table pattern, existing-row data preserved); RobotRecoveryCoordinator refactored (new start() method for the explicit ROBOT_STOPPED->ROBOT_RUNNING operator action, shared _reconcile_running() helper, restart-while-PAUSED now lands back on PAUSED per the CR's own restart-preservation fix); new terminal/application/robot_control.py with start_robot/pause_robot/resume_robot/stop_robot as pure robot_runtime_state transitions (start_robot corrected during test-writing to require the fully clean (ROBOT_STOPPED, ROBOT_STOPPED) pair, not just mode==ROBOT_STOPPED, matching the decision doc's RECONCILIATION_REQUIRED carve-out); Telegram wiring in telegram_review.py (robot:cmd:* dispatch, reused chat-id authorization) and robot_telegram_feed.py (build_robot_control_keyboard, single pause/resume toggle button per state). 41 new tests added, full repository regression re-run twice with the pre-existing 2-FAIL/19-ERROR baseline unchanged. Also records a second, deeper architecture finding from a targeted investigation: close_all_now() cannot follow the same direct-SQLiteStore pattern as the other four commands because telegram_review.py and the live PaperRuntime (owned by terminal/runtime/paper_http_server.py, a separate OS process) share no memory or import path -- the only existing bridge is that server's unauthenticated localhost REST API. This is a material scope/mechanism change beyond what revision 1.0 approved (a new file, terminal/runtime/paper_http_server.py, and a new HTTP-bridge design), so close_all_now() is deliberately not implemented in this revision; see unresolved_decisions for the proposed resolution awaiting explicit approval.", "date": "2026-09-11"},
    {"revision": "1.2", "reason": "User approved the revision 1.1 close_all_now() HTTP-bridge design as-is in chat (new POST /api/robot/close-all-now route, same trust model as /api/full-close and /api/close-all). IMPLEMENT completed: PaperRuntime.robot_close_all() (terminal/runtime/paper_runtime.py) added as a Robot-owned-symbols-only sibling to the existing account-wide close_all(), marking (ROBOT_RUNNING, RECONCILIATION_REQUIRED) on any unconfirmed close; the new route wired into paper_http_server.py's do_POST (added to the existing mutation_paths require_paper_mutations() gate); close_all_now() added to terminal/application/robot_control.py as an HTTP-bridging function; Telegram two-step confirm/cancel flow added to telegram_review.py (_request_close_all_confirmation / _confirm_close_all_now) and the withheld Close All button restored to robot_telegram_feed.py's build_robot_control_keyboard() plus a new build_robot_close_all_confirmation_keyboard(). One real regression was caught and fixed before commit: close_all_now() originally imported requests directly, which tests/test_terminal_execution_engine.py's test_no_mutation_or_network_api_is_exposed correctly flagged as a terminal/application/ network-import boundary violation -- fixed by making http_post a required parameter supplied by the caller instead of a module-level requests import. 20 more tests added (test_robot_control.py close_all_now cases, test_terminal_paper_runtime.py's two robot_close_all() cases, test_robot_telegram_feed.py and test_telegram_robot_control.py's close_all-family cases). Full regression re-run using the project's own venv (venv/Scripts/python.exe, matching start_paper_backend.bat) rather than a bare system Python missing pytest: 729 tests, 2 pre-existing failures / 6 pre-existing errors, all independently confirmed unrelated to this change (one, a v9->v10->v11 migration test, was reproduced identically against the pre-CR baseline commit via git stash). All six commands from AUTOPILOT_ROBOT_V0_1_ROBOT_CONTROL_DECISION.md v1.2 are now implemented and verified. RECORD in progress pending explicit commit authorization per ASSISTANT_PROTOCOL.md 7.2 git safety rules.", "date": "2026-09-11"}
  ]
}
```
<!-- CHANGE_REQUEST_METADATA_END -->

## Recovery summary

`DOCUMENTS/AUTOPILOT_ROBOT_V0_1_ROBOT_CONTROL_DECISION.md` (v1.2, ACCEPTED DESIGN) fully specifies six Robot v0.1
admission-gate operator commands — `start_robot()`, `pause_robot()`, `resume_robot()`, `close_all_now()`,
`stop_robot()` — but explicitly states `Implementation authorization: NONE` and that it "does not authorize
implementation of the Telegram commands/buttons." No durable ChangeRequest previously governed this work: none
of the five existing files under `DOCUMENTS/CHANGE_REQUESTS/` reference it, and none of the 17
`AUTOPILOT_ROBOT_V0_1_*.md` decision documents cite a governing CR id. Per
`DOCUMENTS/PROJECT_CONTRACTS.md#CONTRACT-CHANGE-REQUEST-001`, "durable ChangeRequest is mandatory for
substantial, risky, architectural or multi-session work" and "implementation requires an approved request
revision when a durable request is mandatory" — this work (a schema migration on a live trading state machine,
five new state-transition functions, and a new Telegram control surface) meets that bar.

None of the five command functions exist in the codebase yet; this is greenfield work on top of the existing
admission-gate infrastructure (`terminal/application/robot_admission.py`, `terminal/application/robot_recovery.py`,
`terminal/persistence/sqlite_store.py`'s `robot_runtime_state` table). The user proposed, in chat, adding a
`PAUSED` value to `recovery_status` (not `mode`) as the schema representation for the paused state introduced by
`ROBOT_CONTROL_DECISION.md` Section 2, reasoning that the recovery pipeline runs only at explicit backend start
and therefore would not accidentally clobber `PAUSED`, and left the final representation choice to this
assistant. Code inspection of `RobotRecoveryCoordinator.recover()` confirmed the "runs only at backend start, not
periodically" premise, but also found a real gap the recommendation's own reasoning does not cover: `recover()`
unconditionally drives `mode=ROBOT_RUNNING` through `RECONCILING` to `READY` on every backend start, with no
check for a pre-existing `PAUSED` value — so a backend restart while paused would silently un-pause the robot.
This CR accepts the `recovery_status=PAUSED` representation but adds a restart-preservation fix to `recover()`
as part of the same change, so pause remains a genuinely durable operator decision. See `resolved_decisions`
above.

TASK and SPEC are considered complete because `ROBOT_CONTROL_DECISION.md` v1.2 already specifies command-level
semantics in full; CONTEXT is complete per the codebase exploration summarized in `context_scope_paths`. The
user approved revision 1.0 as-is in chat and IMPLEMENT began; see `IMPLEMENTATION_RECORD` below for what has
been delivered and for the second architecture gap this revision surfaces.

## IMPLEMENTATION_RECORD (revision 1.1)

### What was built and verified

- `terminal/persistence/schema.py` — new `SCHEMA_V16_MIGRATION_STATEMENTS` (`SCHEMA_VERSION` 15 -> 16): rebuilds
  `robot_runtime_state` under a CHECK constraint that adds `PAUSED` to `recovery_status`, valid only paired with
  `mode='ROBOT_RUNNING'`, following the same create/copy/drop/rename pattern already used for CHECK-constraint
  changes at v6/v7/v9. `terminal/persistence/sqlite_store.py` — `SQLiteStore._migrate_v15_to_v16`, wired into the
  version-detection chain (a `version == 15` branch, and `_migrate_v14_to_v15` now chains into it, matching the
  existing v13->v14->v15 chaining pattern); `ROBOT_RECOVERY_STATUSES` and `ROBOT_RUNTIME_STATE_PAIRS` extended
  with `PAUSED` / `("ROBOT_RUNNING", "PAUSED")`.
- `terminal/application/robot_recovery.py` — refactored `RobotRecoveryCoordinator`: the running-branch body of
  `recover()` is extracted into `_reconcile_running()`, which now accepts a `was_paused` flag and lands on
  `PAUSED` (not `READY`) after a successful reconciliation when the runtime started `PAUSED` — this is the
  restart-preservation fix described in `resolved_decisions`. A new public `start()` method reuses
  `_reconcile_running()` for the explicit `Запустить робота` action (`AUTOPILOT_ROBOT_V0_1_RESTART_FROM_STOPPED_DECISION.md`):
  unlike `recover()`, which must never lift durable `ROBOT_STOPPED` on its own, `start()` is the one path that
  actively reconciles into `ROBOT_RUNNING`; it is the caller's job (`robot_control.start_robot()`) to reject the
  call outright when durable mode is not already `ROBOT_STOPPED`.
- `terminal/application/robot_control.py` (new) — `start_robot()`, `pause_robot()`, `resume_robot()`,
  `stop_robot()`, each opening its own `SQLiteStore` connection exactly like
  `robot_admission.admit_robot_candidate()` (no live `PaperRuntime` needed, since none of the four execute an
  order). `RobotControlRejected(PersistenceError)` is raised for every illegal source state. While writing the
  legality-matrix tests, `start_robot()`'s precondition was corrected from `mode != ROBOT_STOPPED` to
  `mode != ROBOT_STOPPED or recovery_status != ROBOT_STOPPED` — the decision doc's Section 1 phrasing ("legal
  only from `ROBOT_STOPPED`... rejected including from `RECONCILIATION_REQUIRED`") means the fully clean
  `(ROBOT_STOPPED, ROBOT_STOPPED)` pair specifically, not any state where `mode` happens to equal
  `ROBOT_STOPPED` — `(ROBOT_STOPPED, RECONCILIATION_REQUIRED)` is a real, valid durable pair that must still be
  rejected.
- `robot_telegram_feed.py` — `build_robot_control_keyboard(mode, recovery_status)`: renders no buttons under
  `RECONCILIATION_REQUIRED`, a single Start button under `ROBOT_STOPPED`, and otherwise one Pause/Resume toggle
  button (label and `callback_data` both flip with `recovery_status`) plus Stop — implementing the CR's own
  Rationale addition that pause/resume must never be two independently visible buttons. `parse_robot_control_callback`
  parses `robot:cmd:<start|pause|resume|stop>`; `close_all` is deliberately excluded from the accepted-command set
  and the button is withheld from the keyboard until the gap below is resolved, rather than shipping a control
  that cannot execute.
- `telegram_review.py` — `_process_callback()` extended with a third parse branch (`robot:cmd:*`) alongside the
  existing `review:*` and `robot:approve:*` branches, reusing the existing single-owner chat-id authorization
  check unchanged. `_call_robot_control_command(command)` dispatches by name (an if/elif chain, not a dict of
  functions captured at import time) specifically so tests can patch `telegram_review.pause_robot` etc. the same
  way existing tests already patch `admit_robot_candidate`. `_run_robot_control_command()` answers the callback
  with a success message, the `RobotControlRejected` reason, or a generic error — never lets an exception escape
  the long-poll loop.
- Tests: `tests/test_robot_control.py` (22, new), `tests/test_robot_recovery_coordinator.py` (+4: restart-while-
  PAUSED with and without an open trade, `start()` from a never-initialized store, `start()` recovering a
  surviving `APPROVED` candidate), `tests/test_terminal_persistence.py` (+1: a real pre-v16 database — old CHECK
  constraint, no `PAUSED`, an existing `(ROBOT_RUNNING, READY)` row — reopened through `SQLiteStore` to exercise
  the actual rebuild migration, confirming data preservation and the new/old CHECK boundaries), `tests/test_robot_telegram_feed.py`
  (+5: keyboard/parser), `tests/test_telegram_robot_control.py` (+7, new: dispatch, rejection handling,
  non-owner rejection).

### Verification

- Targeted runs (`tests.test_robot_control`, `tests.test_robot_recovery_coordinator`, `tests.test_robot_admission`,
  `tests.test_terminal_persistence`, `tests.test_robot_telegram_feed`, `tests.test_telegram_robot_control`,
  `tests.test_telegram_robot_handoff`, `tests.test_telegram_review_authorization`): all pass.
- Full repository regression (`python -B -m unittest discover -s tests`), run twice (once after the four commands
  and schema/recovery work, once after the Telegram wiring): 675 tests total, 2 failures / 19 errors, identical
  to the pre-existing baseline documented in `CR-SCANNER-GEOMETRY-002` (`test_task_harness`,
  `test_telegram_delivery`, and 19 terminal/diary/live-limit/paper-http loader errors — all pre-existing,
  unrelated to this change). Zero new failures or errors in either run.

### close_all_now() (revision 1.2) — the gap revision 1.1 surfaced, now closed

A targeted investigation (prompted by needing to know how `close_all_now()` would actually execute a Market
close) found that `telegram_review.py` and the live `PaperRuntime` instance run as two completely separate OS
processes with no shared memory or import path — confirmed by the process launch scripts
(`start_paper_backend.bat` runs `python -m terminal.runtime.paper_http_server`; `start_scanner.bat` separately
spawns `python telegram_review.py` and `python main.py` in their own PowerShell windows). The only existing
bridge from an external process into the live `PaperRuntime` is that server's unauthenticated
`127.0.0.1:8765` REST API (`POST /api/full-close` for one symbol, `POST /api/close-all` for the whole account —
confirmed account-wide, not Robot-scoped). This was a different, and larger, mechanism than `start_robot()`/
`pause_robot()`/`resume_robot()`/`stop_robot()` needed, and required touching a file
(`terminal/runtime/paper_http_server.py`) that was not in revision 1.0's `context_scope_paths` — a material
scope change per `CONTRACT-CHANGE-REQUEST-001`, not something to decide unilaterally mid-IMPLEMENT. The user
approved the proposed resolution in chat; it is now built:

- `terminal/runtime/paper_runtime.py` — new `PaperRuntime.robot_close_all(request)`: filters
  `store.load_robot_candidates(account)` to `status == "OPEN"` symbols only (deduplicated, sorted), Market-closes
  each via the existing `self.api.full_close(...)` path exactly like `close_all()` already does per-symbol, and —
  unlike `close_all()` — if any close's `CommandResultStatus` is not `COMPLETED`, updates `robot_runtime_state` to
  `(ROBOT_RUNNING, RECONCILIATION_REQUIRED)` before returning. `close_all()` itself is untouched (per
  `prohibited_scope`).
- `terminal/runtime/paper_http_server.py` — new `POST /api/robot/close-all-now` route immediately after
  `/api/close-all`, added to the existing `mutation_paths` set so it goes through the same
  `require_paper_mutations()` 409 gate; calls `runtime.robot_close_all(request)` through the same
  `SerializedPaperRuntime.call(...)` actor hop as every other mutation route. No new authentication was added —
  same trust model as `/api/full-close`/`/api/close-all` (bound to `127.0.0.1`, no operator token), per the
  user's explicit approval.
- `terminal/application/robot_control.py` — new `close_all_now(*, http_post, database_path=None, clock_ms=None,
  backend_url=None)`: validates legality the same way as the other four commands (a direct `SQLiteStore` read,
  rejecting everything except `(ROBOT_RUNNING, READY)`/`(ROBOT_RUNNING, PAUSED)`), then calls the caller-supplied
  `http_post(url, payload)` against `{backend_url or DEFAULT_PAPER_BACKEND_URL}/api/robot/close-all-now`, wrapping
  any transport exception (backend not running, connection refused, etc.) as `RobotControlRejected` rather than
  letting it propagate raw. `http_post` has **no default** and **no `requests` import in this module** — see the
  regression below for why.
- `telegram_review.py` — `_post_robot_close_all_now(url, payload)` (the actual `requests.post`, living here
  instead of in `terminal/application/`), `_request_close_all_confirmation()` (answers the callback and sends a
  new message with `build_robot_close_all_confirmation_keyboard()`), `_confirm_close_all_now()` (the real
  `close_all_now()` call). `_run_robot_control_command()` branches on `close_all`/`close_all_confirm`/
  `close_all_cancel` before falling through to the plain four-command path.
- `robot_telegram_feed.py` — the previously-withheld Close All button is restored to
  `build_robot_control_keyboard()` (shown whenever `mode == ROBOT_RUNNING`, i.e. both `READY` and `PAUSED`,
  matching `close_all_now()`'s legality); new `build_robot_close_all_confirmation_keyboard()`; `close_all`,
  `close_all_confirm`, `close_all_cancel` added to `ROBOT_CONTROL_COMMANDS`.

**Regression caught and fixed before commit:** `close_all_now()` originally imported `requests` directly inside
`terminal/application/robot_control.py` (with a `_post_json` default helper). The full regression run then
failed `tests/test_terminal_execution_engine.py::test_no_mutation_or_network_api_is_exposed`, which asserts via
`ast`-parsing every file under `terminal/application/*.py` that none of them import `requests`/`pybit`/
`websocket`/`config`/`scanner`/`main` — an architecture boundary keeping the application layer free of network
clients. Fixed by making `http_post` a required parameter with no default and moving the real `requests.post`
call into `telegram_review.py`'s `_post_robot_close_all_now()`, which the caller passes in. Re-run after the fix:
passes, and the fix cost no test rewrites in `tests/test_robot_control.py` since every test there already passed
`http_post=` explicitly.

### Final verification (revision 1.2)

- Targeted runs (all the revision 1.1 modules plus `tests.test_terminal_paper_runtime` and
  `tests.test_terminal_execution_engine`): all pass.
- Full repository regression, switched to the project's own `venv/Scripts/python.exe` (matching
  `start_paper_backend.bat`) instead of a bare system Python that was silently missing `pytest` and skipping 19
  pytest-style modules: **729 tests, 2 failures / 6 errors**, all independently confirmed pre-existing and
  unrelated to this change (`test_task_harness`, `test_telegram_delivery`, two
  `test_terminal_live_account_reconciliation` cases, three `test_terminal_live_limit_acceptance` schema-migration
  cases, and `test_terminal_paper_stop::test_schema_v9_migration` — the last one reproduced identically against
  the pre-CR baseline commit `1132314` via `git stash`, in a v9->v10->v11 migration path this CR never touches).
  Zero new failures or errors.

All six commands from `AUTOPILOT_ROBOT_V0_1_ROBOT_CONTROL_DECISION.md` v1.2 (`start_robot`, `pause_robot`,
`resume_robot`, `close_all_now`, `stop_robot`, plus the Telegram pause/resume toggle) are implemented and
verified. RECORD is in progress: this document update is part of it, and the change is implemented and verified
but not yet committed, pending explicit commit authorization per `ASSISTANT_PROTOCOL.md` 7.2 git safety rules.

# END_OF_DOCUMENT
