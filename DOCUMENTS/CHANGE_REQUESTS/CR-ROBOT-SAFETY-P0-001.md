# CR-ROBOT-SAFETY-P0-001 — Robot v0.1 P0 Safety Architecture (authority, ownership, first-fill, reconciliation)

<!-- CHANGE_REQUEST_METADATA_BEGIN -->
```json
{
  "schema_version": "1.0",
  "id": "CR-ROBOT-SAFETY-P0-001",
  "title": "Robot v0.1 P0 Safety Architecture: Robot safety authority separation, single owner per net symbol, Option A first-fill finality, and explicit reconcile_robot() exit from RECONCILIATION_REQUIRED",
  "governance_type": "DESIGN_TO_IMPLEMENTATION_CHANGE_REQUEST",
  "status": "APPROVED_NOT_IMPLEMENTED",
  "revision": "1.0",
  "lifecycle_stage": "CONTEXT",
  "objective": "Freeze and then implement the four P0 Robot v0.1 safety corrections reproduced in live PAPER runtime on 2026-09-14: (1) Robot safety authority must be independent of Workspace active-account selection without weakening operator command legality; (2) at most one active Robot exposure owner per (account, symbol, position_idx=0), with duplicate-owner ambiguity escalating to RECONCILIATION_REQUIRED instead of blind net-position closure; (3) Option A partial-fill finality with no Market top-up and event-driven first-fill protection; (4) an explicit reconcile_robot() command as the single evidence-based exit from RECONCILIATION_REQUIRED, landing PAUSED and never READY. This revision completes TASK/SPEC/CONTEXT documentation only; IMPLEMENT is not authorized.",
  "non_goals": [
    "Any production source, test, schema or runtime change in this revision (documentation only)",
    "Pyramiding, scaling in, or any second concurrent Robot lifecycle on one netted symbol",
    "Any change to STOP/TAKE calculation or priority",
    "Any change to Scanner geometry, pattern detection, sizing or wedge strategy",
    "LIVE trading paths, LIVE parity mutations, or LIVE account behavior",
    "Ownership-transfer/manual-takeover behavior (already deferred by AUTOPILOT_ROBOT_V0_1_TELEGRAM_ONLY_DECISION.md)",
    "Ownership or close-scope for manual (non-Robot) positions on the same PAPER account",
    "Retroactive repair of existing production data by direct SQLite writes",
    "A database-level uniqueness constraint for the single-owner invariant in P0"
  ],
  "approved_scope": [
    "P0.0 (this revision): freeze the corrected semantics in AUTOPILOT_ROBOT_V0_1_ROBOT_CONTROL_DECISION.md v1.6 Sections 7-10 and record the dependency-ordered implementation plan, file scope, acceptance criteria and regression-test contract here",
    "P0.1 (documented, not yet authorized): separate Robot safety authority from the Workspace-facing require_paper_mutations() gate at every Robot safety path, without introducing any blanket HTTP-level allow rule",
    "P0.2 (documented, not yet authorized): enforce at most one active Robot exposure owner per (account, symbol, position_idx=0) before entry submission and again immediately before final ownership commit",
    "P0.3 (documented, not yet authorized): Option A subtractive change in RobotBreakoutMonitor's tick path -- first authoritative non-zero fill is final, remainder cancelled, no Market top-up",
    "P0.4 (documented, not yet authorized): event-driven first-fill hook reusing the existing RobotProtectionCoverageManager feed and serialized owner-thread path",
    "P0.5 (documented, not yet authorized): reconcile_robot() command, runtime method and localhost route, legal only from (ROBOT_RUNNING, RECONCILIATION_REQUIRED), landing (ROBOT_RUNNING, PAUSED) on complete success",
    "P0.6 (documented, optional/deferrable): Telegram exposure of reconcile_robot() only while durable state is RECONCILIATION_REQUIRED"
  ],
  "prohibited_scope": [
    "Introducing any rule equivalent to 'a robot_runtime_state row exists implies a Robot mutation is allowed' at the HTTP layer or anywhere else",
    "Allowing removal of Workspace gating to make an otherwise-illegal Robot control command callable from an illegal durable state",
    "Automatically emergency-closing a netted symbol when ownership of the exposure being closed cannot be proven to belong solely to the requesting lifecycle",
    "Fabricating exit price, exit reason, realized PnL, fees, entry economics or historical execution to resolve a stale ledger row",
    "Landing on (ROBOT_RUNNING, READY) automatically at the end of reconciliation",
    "Submitting any Market order to complete a partial fill",
    "Schema migration in P0 unless later implementation analysis proves correctness is otherwise impossible",
    "Unrelated production, documentation, training/reference, or dirty-work changes"
  ],
  "authoritative_references": [
    "AGENTS.md",
    "DOCUMENTS/ASSISTANT_PROTOCOL.md",
    "DOCUMENTS/PROJECT_CONTRACTS.md#CONTRACT-CHANGE-REQUEST-001",
    "DOCUMENTS/PROJECT_CONTRACTS.md#CONTRACT-DEVELOPMENT-LIFECYCLE-001",
    "DOCUMENTS/PROJECT_RULES.md",
    "DOCUMENTS/GITHUB_FIRST_WORKFLOW.md",
    "DOCUMENTS/AUTOPILOT_ROBOT_V0_1_ROBOT_CONTROL_DECISION.md (v1.6, Sections 7-10)",
    "DOCUMENTS/AUTOPILOT_ROBOT_V0_1_RECOVERY_STATE_BATCH_DECISION.md (v1.3, Sections 3-10)",
    "DOCUMENTS/AUTOPILOT_ROBOT_V0_1_RESTART_FROM_STOPPED_DECISION.md",
    "DOCUMENTS/AUTOPILOT_ROBOT_V0_1_TELEGRAM_FEED_AND_SHORT_WEDGE_DECISION.md",
    "DOCUMENTS/CHANGE_REQUESTS/CR-PAPER-PROTECTION-LIFECYCLE-001.md",
    "DOCUMENTS/CHANGE_REQUESTS/CR-ROBOT-BREAKOUT-MONITOR-001.md",
    "DOCUMENTS/CHANGE_REQUESTS/CR-ROBOT-CONTROL-001.md"
  ],
  "context_scope_paths": [
    "terminal/runtime/paper_runtime.py",
    "terminal/runtime/paper_http_server.py",
    "terminal/application/robot_breakout_monitor.py",
    "terminal/application/robot_admission.py",
    "terminal/application/robot_control.py",
    "terminal/application/robot_recovery.py",
    "terminal/api/models.py",
    "robot_telegram_feed.py",
    "telegram_review.py"
  ],
  "context_test_paths": [
    "tests/test_robot_breakout_monitor.py",
    "tests/test_robot_admission.py",
    "tests/test_robot_control.py",
    "tests/test_robot_recovery_coordinator.py",
    "tests/test_terminal_paper_runtime.py",
    "tests/test_terminal_paper_http.py",
    "tests/test_terminal_account_switching.py",
    "tests/test_robot_paper_execution_threading.py",
    "tests/test_robot_telegram_feed.py",
    "tests/test_telegram_robot_control.py"
  ],
  "approved_decisions": [
    "OPTION A (owner-frozen): the first authoritative non-zero filled_quantity becomes the final trade size; the remaining entry LIMIT is cancelled; no Market top-up is ever submitted; STOP/TAKE are established immediately for the actual filled exposure; if protection for a uniquely owned exposure cannot be established, the existing fail-closed path applies",
    "Robot safety authority and operator command legality are two separate concepts. Safety authority is independent of Workspace active-account selection, must continue to function under PAUSED and RECONCILIATION_REQUIRED where applicable, and must never be blocked by require_paper_mutations() or a LIVE Workspace selection. Command legality keeps the explicit durable-state matrix for start/pause/resume/stop/close-all/reconcile, unchanged",
    "No blanket rule of the form 'robot_runtime_state row exists implies Robot mutation allowed' may be introduced; removing Workspace gating must not make an otherwise-illegal Robot control command callable from an illegal state",
    "At most one active Robot exposure owner per (account, symbol, position_idx=0) for PAPER one-way positions; the second lifecycle is prevented before entry submission and re-checked before final ownership commit; a blocked candidate stays APPROVED and recoverable and is never invalidated for losing the race",
    "CRITICAL: if a race produces real non-zero exposure for candidate B while candidate A already owns the same net symbol, the symbol must NOT be automatically emergency-full-closed, because the netted position would destroy candidate A's legitimate exposure. Required behavior: stop further risk-increasing mutations, preserve all evidence, escalate to or remain in RECONCILIATION_REQUIRED with a durable reason, and require reconciliation to determine safe disposition",
    "reconcile_robot() is legal only from (ROBOT_RUNNING, RECONCILIATION_REQUIRED); admission stays closed throughout; it reconciles authoritative position/order/protection truth against Robot ownership; finalizes/protects uniquely attributable exposure; emergency-closes only where ownership of the exposure being closed is proven; never triggers a blind net-position close on duplicate-owner ambiguity; closes a stale open robot_trades row only from complete authoritative exit evidence; never fabricates exit price, exit reason, realized PnL, fees or historical execution",
    "reconcile_robot() lands (ROBOT_RUNNING, PAUSED) on complete success and never READY automatically; the operator must explicitly resume_robot(). Any unresolved safety or evidence ambiguity leaves (ROBOT_RUNNING, RECONCILIATION_REQUIRED) with a durable reason and reports failure",
    "Event-driven first-fill acceptance wording claims no physically zero-time protection interval. Frozen invariant: once authoritative filled_quantity > 0 is observed by the serialized Robot owner-thread path, there is no intentional wait for another candle or periodic Robot tick; in the same processing pass the system begins remainder cancellation and ownership/protection finalization, or enters fail-closed handling. The 60s RobotBreakoutMonitor tick remains a watchdog/backstop, not the primary first-fill safety trigger",
    "0GUSDT-class historical repair does not preselect EMERGENCY_CLOSE or any other exit reason; the reason recorded must be the one proven evidence supports from the existing ROBOT_EXIT_REASONS set. If evidence is insufficient, nothing is synthesized, the row is left unresolved, and RECONCILIATION_REQUIRED is retained",
    "No schema migration in P0. All checks and repairs are expressed over existing robot_candidates/robot_trades/position_projections/paper_limit_orders state and existing valid (mode, recovery_status) pairs and ROBOT_EXIT_REASONS values. A database-level partial uniqueness constraint is explicitly rejected for P0 because it cannot express the pre-entry half of the single-owner invariant and would add migration risk to a live trading schema",
    "Implementation slice order is dependency-driven: P0.1 authority separation, P0.2 single-owner invariant, P0.3 Option A subtractive tick-path change, P0.4 event-driven first-fill hook, P0.5 explicit reconcile_robot(), P0.6 optional/deferrable Telegram exposure. P0.2 must precede P0.3 because Option A finalizes ownership far more eagerly and would otherwise create second owners faster"
  ],
  "unresolved_decisions": [
    "Whether authoritative execution evidence sufficient to close the existing production 0GUSDT stale robot_trades row actually exists; to be determined read-only during P0.5 CONTEXT, with 'leave unresolved and remain RECONCILIATION_REQUIRED' as the accepted outcome if it does not",
    "Whether P0.4's pre-entry market-data coverage set needs an explicit upper bound, to be decided from observed live subscription counts during P0.4 SPEC"
  ],
  "acceptance_criteria": [
    "Zero unintentional wait after authoritative first fill: from the owner-thread observation of filled_quantity > 0, the same processing pass begins remainder cancellation and ownership/protection finalization or fail-closed handling, with no path to protection that reads a closed candle or waits for the periodic tick",
    "No Market top-up after a partial fill: robot_market_confirmation.submit_confirmation_market() is unreachable from the Robot v0.1 entry lifecycle, entry_path written by that lifecycle is only LIMIT, and actual_wv equals the authoritatively observed filled fraction",
    "No Robot safety operation is blocked by Workspace active-account state: with a LIVE account selected, pause_robot(), stop_robot(), close_all_now(), reconcile_robot(), Robot-owned fill matching and protection dispatch all still function; require_paper_mutations() remains in force for Workspace-owned mutations only",
    "Operator command legality is unchanged by the authority separation: each control command is still rejected from every state outside its documented legal source state, and no blanket allow rule exists",
    "RECONCILIATION_REQUIRED is left only through reconcile_robot(), which lands (ROBOT_RUNNING, PAUSED) on complete success and never READY automatically",
    "Physical FLAT cannot remain indefinitely as an open Robot trade: after a successful reconcile_robot(), every non-exited robot_trades row has a non-flat authoritative position, or was closed from complete proven exit evidence, or reconciliation reported failure and retained RECONCILIATION_REQUIRED",
    "At most one active Robot exposure owner exists per (account, symbol, position_idx=0): no second entry LIMIT is submitted and no second robot_trades row is created while another Robot lifecycle owns that net symbol",
    "Duplicate-owner ambiguity never causes an automatic net-position close: the affected symbol stops risk-increasing mutations, evidence is preserved, and durable state is RECONCILIATION_REQUIRED with a reason naming the condition",
    "Already-OPEN candidates remain untouched by RobotBreakoutMonitor.tick(); INVALIDATED remains terminal; protection establishment, protection dispatch and the fail-closed emergency path remain unconditional on admission state except for the single narrow ownership exception in decision-document Section 10",
    "Full repository regression shows zero new failures against the documented pre-existing baseline"
  ],
  "verification_requirements": [
    "Regression reproducing the BSBUSDT/BSVUSDT class: a candidate in RETEST_DETECTED whose entry LIMIT is partially filled then cancelled, with a non-zero authoritative position projection, must produce a robot_trades row with STOP/TAKE sized to the filled quantity in one pass, with no closed candle available and no Market order submitted",
    "Regression for protection failure on that same path: build_protection_plan()/submit_initial_protection() failure for a uniquely owned exposure emergency-closes to FLAT and terminalizes the candidate, creating no robot_trades row",
    "Regression reproducing the pause_robot live_mutations_disabled bug: with a non-PAPER Workspace active account, pause_robot() reaches (ROBOT_RUNNING, PAUSED) and its synchronize bridge returns success; sibling cases cover close_all_now(), reconcile_robot() and the Robot localhost routes",
    "Regression proving command legality is unchanged after authority separation: each control command is still rejected from every illegal durable state with a non-PAPER Workspace account selected",
    "Regression reproducing the 0GUSDT stale robot_trades bug: an open robot_trades row with a FLAT authoritative position and complete proven exit evidence is closed by reconcile_robot() with the evidence-supported exit reason and lands (ROBOT_RUNNING, PAUSED); the negative case with insufficient evidence leaves the row untouched, synthesizes nothing and retains RECONCILIATION_REQUIRED",
    "Regression reproducing the duplicate candidate/net-symbol ownership bug: candidate B reaching RETEST_DETECTED on a symbol already owned by candidate A submits no entry LIMIT and stays APPROVED; and, in the raced variant where candidate B somehow has real non-zero exposure while candidate A already owns the same net symbol, the expected result is RECONCILIATION_REQUIRED with a durable reason and NO blind emergency full-close of the net position, with candidate A's trade, protection and evidence intact",
    "Regression for restart during the partial-fill/protection transition: interrupting between fill observation and ownership commit yields exactly one owner, protection established or fail-closed handling entered, no duplicate trade and no orphaned exposure",
    "Regression for reconcile_robot() legality across every durable state, admission staying closed during the pass, and resume_robot() being required afterwards",
    "Event-driven first-fill test asserting the finalize/protect sequence begins in the same owner-thread processing pass as the fill observation, without advancing the monitor's periodic clock",
    "Full repository regression compared against the documented pre-existing baseline, plus git diff --check, plus one protected task finish per slice"
  ],
  "risks": [
    "Option A materially reduces average position size (a 4% filled entry becomes a real 4% trade); downstream statistics, diary and PnL-percentage consumers must be reviewed before behavioral acceptance",
    "P0.4 increases MarketDataHub subscriptions by covering pre-entry symbols with a live Robot entry LIMIT; mitigated by scoping strictly to non-terminal limits and reusing the existing fail-closed coverage-health accounting",
    "Until P0.1 lands, production Robot safety commands remain blocked whenever the Workspace has a LIVE account selected, so the current RECONCILIATION_REQUIRED runtime cannot be reconciled through the normal bridge",
    "P0.2's fail-closed ownership check could, if scoped too broadly, block a legitimate new candidate on a symbol whose prior trade is genuinely closed; the probe must key on non-exited trades and live pre-entry lifecycles only",
    "P0.5 operates on real production state whose evidence completeness is not yet proven; an incomplete-evidence outcome must be an accepted, reportable result rather than a reason to synthesize history",
    "Section 10's narrow exception weakens the otherwise-unconditional emergency-close reflex; it must be implemented as a proof-of-ownership precondition only, never as a general suppression of fail-closed behavior"
  ],
  "residual_risks": [],
  "mission_outcome": [],
  "rollback_boundaries": [
    "Each slice lands as its own protected task and independently revertible change; no slice depends on another slice's data migration because no migration exists",
    "Rollback of P0.1 restores the generic require_paper_mutations() gate on Robot routes and runtime methods without touching durable Robot state",
    "Rollback of P0.2/P0.3/P0.4 restores prior RobotBreakoutMonitor entry-lifecycle behavior without schema or durable-state changes",
    "Rollback of P0.5 removes reconcile_robot() and returns RECONCILIATION_REQUIRED to its previous terminal-in-practice status, leaving all durable rows untouched",
    "No slice rewrites historical trade economics, so rollback never has to restore fabricated data"
  ],
  "implementation_phases": [
    {"id": "TASK", "status": "COMPLETED"},
    {"id": "SPEC", "status": "COMPLETED"},
    {"id": "CONTEXT", "status": "COMPLETED"},
    {"id": "IMPLEMENT", "status": "NOT_AUTHORIZED"},
    {"id": "VERIFY", "status": "PENDING"},
    {"id": "RECORD", "status": "PENDING"}
  ],
  "current_phase": "CONTEXT",
  "current_checkpoint": "P0_0_GOVERNANCE_FROZEN_IMPLEMENT_NOT_AUTHORIZED",
  "implementation_status": "DOCUMENTED_NOT_IMPLEMENTED",
  "next_phase": "IMPLEMENT",
  "next_phase_authorization": "EXPLICIT_USER_AUTHORIZATION_REQUIRED_PER_SLICE_STARTING_WITH_P0_1",
  "related_commits": [
    {"phase": "BASELINE", "commit": "52907b591014f1f4b94dcefc64fea6ea2863e1b8"}
  ],
  "repository_sync": {
    "branch": "main",
    "local_head": "52907b591014f1f4b94dcefc64fea6ea2863e1b8",
    "status": "DOCS_ONLY_UNCOMMITTED_AT_TIME_OF_WRITING"
  },
  "amendment_history": [
    {"revision": "1.0", "reason": "P0.0 governance: TASK/SPEC/CONTEXT formalization of the four P0 Robot v0.1 safety corrections reproduced in live PAPER runtime on 2026-09-14, following an architecture review the owner approved with mandatory corrections (Option A partial-fill finality; separation of Robot safety authority from operator command legality with no blanket allow rule; single owner per net symbol with an explicit prohibition on blind net-position closure under duplicate-owner ambiguity; reconcile_robot() as the single evidence-based exit from RECONCILIATION_REQUIRED landing PAUSED; event-driven first-fill wording that claims no physically zero-time interval; evidence-only stale-trade repair with no preselected exit reason; no schema migration in P0). Semantics frozen in AUTOPILOT_ROBOT_V0_1_ROBOT_CONTROL_DECISION.md v1.6 Sections 7-10. IMPLEMENT not authorized.", "date": "2026-09-14"}
  ],
  "related_work": [
    {
      "relationship": "EXTENDS_WITHOUT_REOPENING",
      "reason": "CR-ROBOT-CONTROL-001 owns the six operator control commands and is already at lifecycle_stage RECORD. reconcile_robot() is a seventh command in that family, but the other three P0 defects (authority separation, single-owner invariant, Option A entry finality) sit outside that CR's objective and approved_scope, spanning robot_breakout_monitor.py, robot_admission.py, paper_runtime.py and paper_http_server.py. This CR therefore carries the whole P0 architecture rather than reopening a RECORD-stage CR, and cites CR-ROBOT-CONTROL-001 as authority for the unchanged command-legality matrix.",
      "date": "2026-09-14"
    },
    {
      "relationship": "NARROW_EXCEPTION_TO",
      "reason": "CR-PAPER-PROTECTION-LIFECYCLE-001 establishes the fail-closed emergency-close path for an unprotectable fill. Decision-document Section 10 adds one narrow, explicitly stated exception: the emergency close is withheld when ownership of the exposure to be closed cannot be proven to belong solely to the requesting lifecycle, because the PAPER position is netted and closing it would destroy another lifecycle's legitimate exposure. In that case the condition escalates to RECONCILIATION_REQUIRED with evidence preserved. No other part of that CR's contract is modified.",
      "date": "2026-09-14"
    }
  ]
}
```
<!-- CHANGE_REQUEST_METADATA_END -->

## Why this CR exists

On 2026-09-14 a live PAPER runtime session reproduced four distinct Robot v0.1 safety defects in sequence. Each was observed, not inferred:

1. **`pause_robot()` could not execute its own safety reconciliation.** Its synchronous bridge to `POST /api/robot/synchronize-pending-entries` returned `{"ok": false, "error": "live_mutations_disabled"}` because the Workspace UI had a LIVE Bybit account selected. The fail-closed contract behaved correctly — durable state escalated to `RECONCILIATION_REQUIRED` with a recorded reason rather than reporting a false success — but the underlying coupling is wrong: a Workspace presentation choice must never be able to block Robot safety work on the PAPER account.

2. **Two Robot lifecycles owned one netted symbol (0GUSDT).** The second lifecycle's protection submission failed with `PAPER STOP already exists`, the fail-closed path emergency-closed the **net** position, and the first lifecycle — legitimately open and correctly protected — was left with a stale open `robot_trades` row while its exposure had already been flattened by someone else's emergency close.

3. **Real partial-fill exposure sat unprotected for an extended period (BSBUSDT, BSVUSDT).** Both had authoritatively filled quantity with no `robot_trades` row and no protection record of any kind, waiting on a Market top-up decision that could not complete. Protection was established only once admission moved to `RECONCILIATION_REQUIRED` and the blocked-admission branch happened to take over.

4. **`RECONCILIATION_REQUIRED` had no exit.** Every control command rejects from it by design, and the owning decision document listed any exit path as an explicit unresolved non-goal, leaving the runtime durably stuck.

Defect 2 is the root cause of the stale ledger row, not an independent bug: fixing the ownership invariant prevents recurrence, and reconciliation repairs what already exists.

## Frozen semantics (authority: AUTOPILOT_ROBOT_V0_1_ROBOT_CONTROL_DECISION.md v1.6)

This CR does not restate the semantics; it points at their owning document and records the plan to implement them. Section 7 now carries Option A and the event-driven observation wording, Section 8 defines `reconcile_robot()`, Section 9 separates Robot safety authority from operator command legality, and Section 10 defines the single-owner invariant including the prohibition on blind net-position closure.

## Implementation slices (dependency ordered)

**P0.1 — Robot authority separation.** Introduce a Robot-specific authority check for Robot safety paths and stop routing them through the Workspace-facing `require_paper_mutations()` gate: `robot_synchronize_pending_entries()`, `robot_close_all()`, the two `/api/robot/*` routes currently in `mutation_paths`, and Robot-owned fill matching which today returns zero whenever the Workspace active account is not PAPER. Operator command legality is untouched. No blanket allow rule is introduced. Unblocks every later slice, since none of them can run while a LIVE Workspace selection can veto Robot safety work.

**P0.2 — Single-owner invariant.** Add an ownership probe and fail-closed checks before first entry-LIMIT submission and immediately before `create_robot_trade()`, plus an advisory rejection at candidate admission. Must precede P0.3: Option A commits ownership far more eagerly, so shipping it first would manufacture second owners faster.

**P0.3 — Option A in the tick path.** Subtractive change: make the existing "cancel remainder, finalize for the actual filled fraction" branch unconditional on admission state, and delete the Market-completion block. Net deletion; no new policy is written.

**P0.4 — Event-driven first fill.** Extend the existing `robot_protection_coverage_symbols()` set with pre-entry symbols that have a live Robot entry LIMIT, and evaluate first fill in the same serialized owner-thread callback that already performs protection-crossing evaluation. Reuses the existing independent per-symbol feed; adds no thread, no price source and no subsystem.

**P0.5 — `reconcile_robot()`.** Command, runtime method and localhost route, reusing `RobotRecoveryCoordinator`, the pure restart-recovery policy, one `robot_synchronize_pending_entries()` pass under corrected Option A semantics, and the existing evidence-based trade-closure path. Last, because it must reconcile against corrected rules.

**P0.6 — Telegram exposure (optional, deferrable).** Surface `reconcile_robot()` only while durable state is `RECONCILIATION_REQUIRED`. Not required for safety.

## File scope per slice

| Slice | Production | Tests |
| --- | --- | --- |
| P0.1 | `terminal/runtime/paper_runtime.py`, `terminal/runtime/paper_http_server.py` | `tests/test_terminal_paper_runtime.py`, `tests/test_terminal_paper_http.py`, `tests/test_terminal_account_switching.py` |
| P0.2 | `terminal/application/robot_breakout_monitor.py`, `terminal/application/robot_admission.py` | `tests/test_robot_breakout_monitor.py`, `tests/test_robot_admission.py` |
| P0.3 | `terminal/application/robot_breakout_monitor.py` | `tests/test_robot_breakout_monitor.py` |
| P0.4 | `terminal/runtime/paper_runtime.py`, `terminal/runtime/paper_http_server.py` | `tests/test_terminal_paper_runtime.py`, `tests/test_robot_paper_execution_threading.py` |
| P0.5 | `terminal/application/robot_control.py`, `terminal/application/robot_recovery.py`, `terminal/runtime/paper_runtime.py`, `terminal/runtime/paper_http_server.py`, `terminal/api/models.py` | `tests/test_robot_control.py`, `tests/test_robot_recovery_coordinator.py`, `tests/test_terminal_paper_runtime.py` |
| P0.6 | `robot_telegram_feed.py`, `telegram_review.py` | `tests/test_robot_telegram_feed.py`, `tests/test_telegram_robot_control.py` |

Each slice opens its own protected task with exactly these paths and finishes with its own PASS receipt. A slice that needs a path not listed here stops and requests a CR amendment rather than widening scope silently.

## Migration decision

**No schema migration in P0.** `(ROBOT_RUNNING, PAUSED)` and `(ROBOT_RUNNING, RECONCILIATION_REQUIRED)` are already valid v16 pairs; the exit reasons needed for evidence-based ledger repair already exist in `ROBOT_EXIT_REASONS`; `entry_path='LIMIT'` is already valid and `MIXED` merely stops being written by this lifecycle; the ownership invariant is expressible as queries over existing tables. A database-level partial uniqueness constraint was considered and rejected for P0: it cannot express the pre-entry half of the invariant — a partially filled candidate that has no trade row yet — so it would add rebuild-migration risk to a live trading schema without removing the need for the application-level checks. This decision is revisited only if implementation analysis proves correctness is otherwise impossible.

## Current runtime context at time of writing

Production PAPER runtime is `(ROBOT_RUNNING, RECONCILIATION_REQUIRED)` following the `pause_robot()` escalation described above. BSBUSDT and BSVUSDT are now protected with `robot_trades` rows and STOP/TAKE, having been finalized by the blocked-admission branch once admission closed. The 0GUSDT stale row remains open against a FLAT position and is the concrete P0.5 repair case. This CR authorizes no runtime action; recovery of that state is itself gated on P0.1 and P0.5.

# END_OF_DOCUMENT
