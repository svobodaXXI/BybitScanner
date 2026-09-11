# CR-ROBOT-CONTROL-001 — Robot v0.1 Admission-Gate Operator Control Commands and Telegram Toggle Surface

<!-- CHANGE_REQUEST_METADATA_BEGIN -->
```json
{
  "schema_version": "1.0",
  "id": "CR-ROBOT-CONTROL-001",
  "title": "Robot v0.1 Admission-Gate Operator Control Commands and Telegram Toggle Surface",
  "governance_type": "DESIGN_TO_IMPLEMENTATION_CHANGE_REQUEST",
  "status": "OPEN",
  "revision": "1.0",
  "lifecycle_stage": "IMPLEMENT",
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
    "config.py"
  ],
  "context_test_paths": [
    "tests/test_robot_control.py",
    "tests/test_robot_admission.py",
    "tests/test_robot_recovery_coordinator.py",
    "tests/test_robot_runtime_wiring.py",
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
    "Telegram callback_data naming and keyboard placement are implementation details resolved directly during IMPLEMENT (not itemized here) since AUTOPILOT_ROBOT_V0_1_ROBOT_CONTROL_DECISION.md's own Explicit non-goals defers 'the concrete Telegram implementation (button/keyboard update mechanics, callback wiring)'"
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
  "verification_results": [],
  "review_result": {
    "verdict": "NOT_YET_REVIEWED",
    "blocking_findings": [],
    "important_findings": [],
    "minor_non_blocking_findings": []
  },
  "acceptance_state": "NOT_STARTED",
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
    {"id": "IMPLEMENT", "status": "NOT_STARTED"},
    {"id": "VERIFY", "status": "NOT_STARTED"},
    {"id": "RECORD", "status": "NOT_STARTED"}
  ],
  "current_phase": "IMPLEMENT",
  "current_checkpoint": "CONTEXT_COMPLETE_PENDING_CR_APPROVAL",
  "implementation_status": "NOT_STARTED_PENDING_CR_APPROVAL",
  "next_phase": "IMPLEMENT",
  "next_phase_authorization": "CR_APPROVAL_REQUIRED_BEFORE_IMPLEMENT_PER_CONTRACT_CHANGE_REQUEST_001",
  "related_commits": [
    {"phase": "BASELINE", "commit": "0bbbaab17289933ac71442aad3c4f92546a52034"}
  ],
  "repository_sync": {
    "branch": "robot-v0-1-admission-gate",
    "local_head": "0bbbaab",
    "status": "FEATURE_BRANCH_AHEAD_OF_MAIN / CR_DRAFTED_NOT_YET_APPROVED"
  },
  "amendment_history": [
    {"revision": "1.0", "reason": "Initial TASK/SPEC/CONTEXT formalization of AUTOPILOT_ROBOT_V0_1_ROBOT_CONTROL_DECISION.md v1.2 into a durable ChangeRequest per CONTRACT-CHANGE-REQUEST-001 (substantial, risky, multi-session, schema-changing work), following explicit user authorization in chat to implement all six commands. Records the codebase exploration (state machine location, Telegram dispatch pattern, schema, shared close-execution path, test conventions) and one technical correction to the user's own PAUSED-in-recovery_status recommendation (restart-preservation fix in RobotRecoveryCoordinator.recover()). Awaiting explicit approval of this revision before IMPLEMENT begins.", "date": "2026-09-11"}
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
semantics in full; CONTEXT is complete per the codebase exploration summarized in `context_scope_paths`. IMPLEMENT
has not started and requires explicit approval of this CR revision first, per the contract cited above.

# END_OF_DOCUMENT
