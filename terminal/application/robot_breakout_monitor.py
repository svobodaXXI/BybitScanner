"""Durable Robot v0.1 breakout/retest lifecycle monitor over APPROVED candidates.

Mode-agnostic coordinator, structurally mirroring
``terminal.application.robot_recovery.RobotRecoveryCoordinator``: it accepts a
``trading_account_id`` and dependency-injected functions rather than a
concrete PaperRuntime, so a future live implementation can reuse it with
live-bound dependencies instead of a duplicated cycle. It never refits
geometry and never invents entry/pattern/protection strategy: it only calls
the existing public functions of robot_state_machine.py, robot_entry_limit.py,
robot_partial_fill.py, robot_market_confirmation.py and robot_protection.py,
in the order CR-ROBOT-BREAKOUT-MONITOR-001 approved, driving each APPROVED
candidate all the way to ``create_robot_trade``.

POST-CLOSURE FIX (see DOCUMENTS/ROBOT_RUN_INDEX.md): SQLiteStore binds to its
opening thread and rejects every call from any other thread. This coordinator
therefore never accepts a pre-opened SQLiteStore -- it takes a store_factory
and opens its own connection lazily, from whichever thread first calls into
it, cached per-thread. The real background thread opens and owns its own
connection; a caller driving .tick() synchronously (e.g. tests) gets its own
separate connection on the calling thread.
"""

from __future__ import annotations

import hashlib
import threading
from decimal import Decimal
from typing import Callable, Mapping, Protocol

import robot_entry_limit
import robot_market_confirmation
import robot_partial_fill
import robot_protection
import robot_state_machine
from scanner_geometry_cursor import ScannerGeometryCursorError, project_latest_geometry_index
from terminal.api.models import ClientActionId, CommandResultStatus, PaperLimitCancelRequest
from terminal.application.robot_admission import active_robot_owner_candidate_ids
from terminal.domain.models import Category, PositionKey, Symbol, TradingAccountId
from terminal.persistence.sqlite_store import (
    ConcurrentUpdate,
    RobotCandidateRecord,
    SQLiteStore,
)

DEFAULT_TICK_INTERVAL_S = 60.0

# Matches the existing PaperRuntime.full_close() emergency-close tolerance
# (terminal/api/rest.py) -- reused rather than inventing a new number.
MARKET_SLIPPAGE_TYPE = "Percent"
MARKET_SLIPPAGE_VALUE = Decimal("0.5")

INACTIVE_LIMIT_STATUSES = {"filled", "cancelled"}


class ActionExecutor(Protocol):
    """Unified execution port. PaperRuntime already satisfies this today; a
    future live_runtime.py can satisfy it with live-bound implementations
    without duplicating this coordinator's cycle."""

    def create_limit(self, request): ...
    def cancel_limit(self, request): ...
    def market(self, request): ...
    def create_stop(self, request): ...
    def amend_stop(self, request): ...
    def create_take(self, request): ...
    def amend_take(self, request): ...
    def full_close(self, request): ...


class RobotBreakoutMonitorError(RuntimeError):
    """Raised when the breakout/retest monitor cannot safely advance a candidate."""


def _cancel_partial_remainder_action_id(candidate_id: str) -> ClientActionId:
    # No existing robot_*.py module owns "cancel the resting LIMIT before a
    # partial-fill Market completion" -- it is orchestration this coordinator
    # owns directly, mirroring the digest-based ClientActionId construction
    # PaperRuntime.robot_close_all() already uses for a similar Robot-owned
    # action outside the five pure modules.
    digest = hashlib.sha256(
        f"{candidate_id}\0cancel-partial-remainder".encode("utf-8")
    ).hexdigest()[:32]
    return ClientActionId(f"robot-cancel-partial-{digest}")


def _cancel_blocked_entry_action_id(candidate_id: str) -> ClientActionId:
    # Distinct action id from _cancel_partial_remainder_action_id above: this
    # one cancels a still-fully-resting (zero-fill) entry LIMIT because the
    # durable admission gate (robot_runtime_state) no longer permits new
    # entry risk for this candidate, not because a partial fill is being
    # topped up via Market. Same PaperLimitCancelRequest/cancel_limit
    # sanctioned path either way -- no new execution primitive.
    digest = hashlib.sha256(
        f"{candidate_id}\0cancel-blocked-entry".encode("utf-8")
    ).hexdigest()[:32]
    return ClientActionId(f"robot-cancel-blocked-{digest}")


class RobotBreakoutMonitor:
    """Advance durable APPROVED Robot candidates through breakout/retest on each closed 1m candle."""

    def __init__(
        self,
        store_factory: Callable[[], SQLiteStore],
        trading_account_id: TradingAccountId,
        *,
        get_closed_candle: Callable[[str], Mapping[str, object] | None],
        action_executor: ActionExecutor,
        tick_size_provider: Callable[[str], Decimal],
        clock_ms: Callable[[], int],
        tick_interval_s: float = DEFAULT_TICK_INTERVAL_S,
        match_resting_orders: Callable[[str], object] | None = None,
    ) -> None:
        self._store_factory = store_factory
        self._local = threading.local()
        self._account_id = trading_account_id
        self._get_closed_candle = get_closed_candle
        self._action_executor = action_executor
        self._tick_size_provider = tick_size_provider
        self._clock_ms = clock_ms
        self._tick_interval_s = tick_interval_s
        # Optional: attempt PAPER fill/protection matching for this candidate's
        # own symbol before re-reading order state below. Independent of which
        # symbol the Workspace UI currently displays -- see
        # PaperRuntime.robot_match_symbol(). None in tests that fake fills
        # directly through the store.
        self._match_resting_orders = match_resting_orders
        self._stop = threading.Event()
        self._thread = threading.Thread(
            target=self._run, name="robot-breakout-monitor", daemon=True,
        )
        self._started = False

    def _store(self) -> SQLiteStore:
        store = getattr(self._local, "store", None)
        if store is None:
            store = self._store_factory()
            self._local.store = store
        return store

    def start(self) -> None:
        if self._started:
            return
        self._started = True
        self._thread.start()

    def close(self) -> None:
        self._stop.set()
        if self._started and self._thread is not threading.current_thread():
            self._thread.join(timeout=5)
        # Close whatever store THIS (calling) thread opened for itself -- the
        # background thread closes its own in _run()'s finally block, since
        # only the owning thread may touch a SQLiteStore connection.
        self._close_local_store()

    def _close_local_store(self) -> None:
        store = getattr(self._local, "store", None)
        if store is not None:
            store.close()
            self._local.store = None

    def _run(self) -> None:
        try:
            # Wait a full interval BEFORE the first tick (never tick immediately
            # on start): a short-lived caller that starts and closes this
            # monitor well within one interval -- as every existing
            # PaperRuntime-constructing test does -- never reaches a real
            # get_closed_candle call.
            while not self._stop.wait(self._tick_interval_s):
                try:
                    self.tick()
                except Exception as error:
                    print(
                        "[ROBOT BREAKOUT MONITOR LOOP ERROR] "
                        f"error={error}"
                    )
        finally:
            self._close_local_store()

    def tick(self) -> tuple[str, ...]:
        """Advance every durable APPROVED candidate by at most one step.

        Returns the ids of candidates whose durable state actually changed.
        One candidate's failure never blocks the others.
        """

        advanced: list[str] = []
        for record in self._store().load_robot_candidates(self._account_id):
            if record.status != "APPROVED":
                continue
            try:
                if self._advance_one(record):
                    advanced.append(record.candidate_id)
            except Exception as error:
                print(
                    "[ROBOT CANDIDATE ERROR] "
                    f"candidate_id={record.candidate_id} error={error}"
                )
                self._record_execution_error(record, error)
                continue
        return tuple(advanced)

    def _record_execution_error(self, record: RobotCandidateRecord, error: Exception) -> None:
        # Best-effort diagnostics only: never let a failure to record the
        # failure itself mask the original error or block other candidates.
        if record.robot_state is None:
            return
        try:
            execution = dict(record.robot_state.get("execution") or {})
            execution["last_execution_error"] = str(error)
            execution["last_attempt_at_ms"] = self._now_ms()
            execution["attempt_count"] = int(execution.get("attempt_count", 0) or 0) + 1
            self._persist_execution(record, execution)
        except Exception:
            pass

    def _advance_one(self, record: RobotCandidateRecord) -> bool:
        if record.robot_state is None:
            state, _event = robot_state_machine.initialize_state(
                self._candidate_payload(record),
            )
            self._persist_state(record, state)
            return True

        phase = record.robot_state.get("phase")
        if phase == robot_state_machine.PHASE_RETEST_DETECTED:
            return self._advance_retest_detected(record)
        if phase == robot_state_machine.PHASE_EXPIRED_AT_APEX:
            return False

        candle = self._get_closed_candle(record.symbol.value)
        if candle is None:
            return False

        try:
            geometry_index = project_latest_geometry_index(
                record.signal_snapshot,
                latest_closed_candle_time_ms=int(candle["time_ms"]),
            )
        except ScannerGeometryCursorError:
            return False

        state_candle = {
            "closed": True,
            "timeframe": "1",
            "geometry_index": geometry_index,
            "high": candle["high"],
            "low": candle["low"],
            "close": candle["close"],
        }
        new_state, event = robot_state_machine.process_closed_candle(
            record.signal_snapshot, record.robot_state, state_candle,
        )
        if event in (
            robot_state_machine.EVENT_IGNORED_STALE,
            robot_state_machine.EVENT_TERMINAL,
        ):
            return False

        # A freshly detected RETEST is persisted here and picked up by
        # _advance_retest_detected() on the NEXT tick (via a freshly loaded,
        # correctly revisioned record) rather than being chased in the same
        # call -- this keeps state_revision bookkeeping in one place.
        self._persist_state(record, new_state)
        return True

    def _advance_retest_detected(self, record: RobotCandidateRecord) -> bool:
        execution = dict(record.robot_state.get("execution") or {})

        if "limit_order_id" not in execution:
            # RETEST_DETECTED is deliberately terminal for
            # robot_state_machine.process_closed_candle()/resume_without_replay()
            # (see _TERMINAL_PHASES there) -- once retest is detected, nothing
            # else re-validates the frozen apex on later ticks. A candidate can
            # sit in this phase for an arbitrarily long time (the
            # live_mutations_disabled bug, a process restart, any other
            # downtime) before its first entry order is ever submitted, so
            # re-check freshness against the SAME frozen apex here, once,
            # immediately before that first submission -- fail closed rather
            # than submit into an already-expired setup.
            candle = self._get_closed_candle(record.symbol.value)
            if candle is None:
                return False
            try:
                geometry_index = project_latest_geometry_index(
                    record.signal_snapshot,
                    latest_closed_candle_time_ms=int(candle["time_ms"]),
                )
            except ScannerGeometryCursorError:
                return False
            apex_index = int(record.signal_snapshot["geometry"]["apex"]["index"])
            if geometry_index >= apex_index:
                expired_state = dict(record.robot_state)
                expired_state["phase"] = robot_state_machine.PHASE_EXPIRED_AT_APEX
                expired_state["last_event"] = robot_state_machine.EVENT_EXPIRED_AT_APEX
                expired_state["geometry_cursor"] = geometry_index
                self._persist_state(record, expired_state)
                return True

            new_entry_admitted, terminal_stop = self._read_admission_gate()
            if not new_entry_admitted:
                # No exposure exists yet for this candidate (no entry order
                # has ever been submitted) -- PAUSE/RECONCILIATION_REQUIRED
                # simply withhold the submission and leave the candidate
                # APPROVED (recoverable once admission is restored). Only a
                # durable ROBOT_STOPPED gives this pending pre-entry intent
                # its terminal disposition, per
                # AUTOPILOT_ROBOT_V0_1_RESTART_FROM_STOPPED_DECISION.md
                # ("previously stopped candidates remain terminal and must
                # not re-enter the active candidate set").
                if terminal_stop:
                    self._invalidate_pre_entry_candidate(
                        record, reason="ROBOT_STOPPED before entry order submission",
                    )
                    return True
                return False

            # P0.2 final pre-submission ownership check. A different
            # pending-partial or OPEN lifecycle already owns this net symbol,
            # so keep this candidate APPROVED/recoverable and submit no risk.
            if self._active_other_owner_candidate_ids(record):
                return False

            result = self._submit_initial_retest_limit(record, record.robot_state)
            order_id = getattr(result, "order_id", None)
            if not order_id:
                return False
            execution["limit_order_id"] = order_id
            self._persist_execution(record, execution)
            return True

        if self._match_resting_orders is not None:
            self._match_resting_orders(record.symbol.value)

        order = self._store().get_paper_limit(execution["limit_order_id"], self._account_id)
        if order is None or order.quantity <= 0:
            return False

        filled_fraction = min(order.filled_quantity / order.quantity, Decimal("1"))
        inactive = order.status in INACTIVE_LIMIT_STATUSES

        try:
            remainder = robot_partial_fill.missing_wv(filled_fraction)
        except robot_partial_fill.RobotPartialFillError:
            return False

        if remainder <= 0:
            average_entry = self._average_entry(record.symbol)
            if average_entry is None:
                return False
            self._finalize_trade(
                record, execution, entry_path="LIMIT",
                actual_wv=filled_fraction, average_entry=average_entry,
            )
            return True

        new_entry_admitted, terminal_stop = self._read_admission_gate()

        if filled_fraction <= 0:
            if new_entry_admitted:
                return False
            # A working, still-fully-unfilled entry LIMIT exists but the
            # admission gate no longer permits new entry risk -- cancel it
            # through the same sanctioned execution path used everywhere
            # else in this module (idempotent by deterministic action id,
            # safe to repeat every tick until confirmed cancelled or it
            # fills first). No exposure exists yet, so ROBOT_STOPPED can
            # safely give this candidate its terminal disposition now;
            # PAUSED/RECONCILIATION_REQUIRED instead leave it APPROVED and
            # recoverable.
            if not inactive:
                self._action_executor.cancel_limit(PaperLimitCancelRequest(
                    _cancel_blocked_entry_action_id(record.candidate_id),
                    record.symbol.value, execution["limit_order_id"],
                ))
            if terminal_stop:
                self._invalidate_pre_entry_candidate(
                    record, reason="ROBOT_STOPPED with unfilled resting entry LIMIT",
                )
            return True

        if not new_entry_admitted:
            # Real partial exposure exists here, with the admission gate
            # blocking further completion. This must never depend on
            # get_closed_candle()/RobotBreakoutMonitor's own periodic
            # tick_interval_s cadence for STOP safety --
            # AUTOPILOT_ROBOT_V0_1_RECOVERY_STATE_BATCH_DECISION.md Section
            # 6's 5-second STOP-not-proven window is a maximum recovery
            # deadline, not a retry interval, and every input
            # structural_extreme/frozen_prices/structural_stop/tighten_stop
            # needs -- record.signal_snapshot, average_entry from the
            # authoritative position projection, tick_size -- is already
            # frozen/durable and requires no new closed candle at all.
            # Cancel any still-live resting remainder first (same sanctioned
            # path used everywhere else in this module), then attempt
            # protection immediately. If that attempt itself fails,
            # _finalize_trade()'s own existing fail-closed path
            # (_fail_closed_unprotected_fill) emergency-closes right away --
            # tighter than the 5-second maximum, not a new timer, and no
            # second protection engine.
            if not inactive:
                self._action_executor.cancel_limit(PaperLimitCancelRequest(
                    _cancel_partial_remainder_action_id(record.candidate_id),
                    record.symbol.value, execution["limit_order_id"],
                ))
                refreshed = self._store().get_paper_limit(execution["limit_order_id"], self._account_id)
                if refreshed is not None:
                    order = refreshed
                    filled_fraction = min(order.filled_quantity / order.quantity, Decimal("1"))
                    inactive = order.status in INACTIVE_LIMIT_STATUSES
            average_entry = self._average_entry(record.symbol)
            if average_entry is None:
                return True
            # Reload first: an earlier _persist_execution() elsewhere this
            # tick (or a prior tick) may have already advanced this
            # candidate's durable state_revision past what the in-hand
            # `record` carries -- see the identical hazard/fix on the
            # MARKET_COMPLETE-blocked path below.
            fresh_record = self._store().get_robot_candidate(record.candidate_id) or record
            self._finalize_trade(
                fresh_record, execution, entry_path="LIMIT",
                actual_wv=filled_fraction, average_entry=average_entry,
            )
            return True

        candle = self._get_closed_candle(record.symbol.value)
        if candle is None:
            return False
        try:
            geometry_index = project_latest_geometry_index(
                record.signal_snapshot,
                latest_closed_candle_time_ms=int(candle["time_ms"]),
            )
        except ScannerGeometryCursorError:
            return False

        average_entry = self._average_entry(record.symbol)
        if average_entry is None:
            return False

        direction = record.robot_state["direction"]
        if execution.get("first_partial_at_ms") is None:
            execution["first_partial_at_ms"] = self._now_ms()
            execution["first_partial_price"] = str(average_entry)

        if not inactive:
            # evaluate_partial_completion() only ever considers Market
            # completion once the resting remainder is authoritatively no
            # longer live (order_authoritatively_inactive) -- cancel it here;
            # idempotent by client_action_id, safe to re-attempt every tick
            # until confirmed cancelled or it fills first.
            self._action_executor.cancel_limit(PaperLimitCancelRequest(
                _cancel_partial_remainder_action_id(record.candidate_id),
                record.symbol.value, execution["limit_order_id"],
            ))
            refreshed = self._store().get_paper_limit(execution["limit_order_id"], self._account_id)
            if refreshed is not None:
                order = refreshed
                filled_fraction = min(order.filled_quantity / order.quantity, Decimal("1"))
                inactive = order.status in INACTIVE_LIMIT_STATUSES

        structural_extreme = self._structural_extreme(record.signal_snapshot, direction)
        tick_size = self._tick_size_provider(record.symbol.value)
        proposed_stop = robot_protection.structural_stop(
            direction, average_entry=average_entry,
            structural_extreme=structural_extreme, tick_size=tick_size,
        )
        existing_stop = (
            Decimal(execution["stop_price"]) if execution.get("stop_price") else None
        )
        stop_price = robot_protection.tighten_stop(
            direction, existing_stop=existing_stop, proposed_stop=proposed_stop,
        )
        execution["stop_price"] = str(stop_price)

        reference_price, target_price = self._frozen_prices(record.signal_snapshot, direction)
        take_price = robot_protection.frozen_take_90(
            direction, frozen_signal_reference_price=reference_price,
            frozen_scanner_target_price=target_price,
        )
        rr = robot_market_confirmation.risk_reward_ratio(
            direction, entry_price=average_entry, stop_price=stop_price, take_price=take_price,
        )

        apex_index = int(record.signal_snapshot["geometry"]["apex"]["index"])
        snapshot_pf = robot_partial_fill.PartialFillSnapshot(
            direction=direction,
            filled_wv=filled_fraction,
            first_partial_at_ms=execution["first_partial_at_ms"],
            first_partial_price=Decimal(execution["first_partial_price"]),
            order_authoritatively_inactive=inactive,
        )
        decision = robot_partial_fill.evaluate_partial_completion(
            snapshot_pf, now_ms=self._now_ms(),
            current_price=Decimal(str(candle["close"])), rr=rr,
            before_apex=geometry_index < apex_index,
        )

        self._persist_execution(record, execution)

        if decision.action != robot_partial_fill.DECISION_MARKET_COMPLETE:
            return True

        # new_entry_admitted is guaranteed True here: the blocked case
        # (PAUSE/STOP/RECONCILIATION_REQUIRED) already returned above,
        # before ever reaching get_closed_candle() -- see that branch for
        # why a blocked partial fill is finalized immediately from frozen
        # data instead of being decided here.

        # Bridge robot_partial_fill's MARKET_COMPLETE decision into
        # robot_market_confirmation's Market-order builder: only their public
        # build/submit functions are called, using a ConfirmationDecision
        # value this coordinator constructs (orchestration, not new policy).
        reward = robot_market_confirmation.expected_reward_ratio(
            direction, entry_price=average_entry, take_price=take_price,
        )
        boundary_side = "upper" if direction == robot_state_machine.DIRECTION_LONG else "lower"
        boundary = robot_state_machine.boundary_price(
            record.signal_snapshot, side=boundary_side, geometry_index=geometry_index,
        )
        bridge_decision = robot_market_confirmation.ConfirmationDecision(
            robot_market_confirmation.DECISION_MARKET_ENTRY,
            decision.missing_wv, boundary, reward, rr,
        )
        payload = self._candidate_payload(record)
        plan = robot_market_confirmation.build_confirmation_market(
            payload, record.robot_state, bridge_decision,
            geometry_index=geometry_index, sizing_reference_price=average_entry,
            slippage_type=MARKET_SLIPPAGE_TYPE, slippage_value=MARKET_SLIPPAGE_VALUE,
        )
        result = robot_market_confirmation.submit_confirmation_market(
            self._action_executor, plan,
        )
        if getattr(result, "status", None) != CommandResultStatus.COMPLETED:
            return True

        final_average_entry = self._average_entry(record.symbol)
        if final_average_entry is None:
            return True
        final_actual_wv = min(filled_fraction + decision.missing_wv, Decimal("1"))
        # Same stale-state_revision hazard as the blocked-admission finalize
        # call above: _persist_execution() earlier in this tick already
        # advanced the durable revision past what this in-hand `record`
        # carries. Reload before finalizing so a genuine fail-closed
        # emergency-close/invalidate here can't silently lose its terminal
        # status write to a spurious ConcurrentUpdate.
        fresh_record = self._store().get_robot_candidate(record.candidate_id) or record
        self._finalize_trade(
            fresh_record, execution, entry_path="MIXED",
            actual_wv=final_actual_wv, average_entry=final_average_entry,
        )
        return True

    def _finalize_trade(
        self,
        record: RobotCandidateRecord,
        execution: Mapping[str, object],
        *,
        entry_path: str,
        actual_wv: Decimal,
        average_entry: Decimal,
    ) -> None:
        direction = record.robot_state["direction"]
        # Everything from here through submit_initial_protection() runs after
        # a real fill already exists: any ordinary operational failure in
        # this whole region (geometry/tick-size/frozen-price derivation,
        # plan validation, or submission) must fail closed rather than
        # silently leave the fill unprotected for a bare retry next tick.
        # Deliberately Exception, not BaseException: SystemExit/
        # KeyboardInterrupt must still propagate.
        try:
            structural_extreme = self._structural_extreme(record.signal_snapshot, direction)
            tick_size = self._tick_size_provider(record.symbol.value)
            reference_price, target_price = self._frozen_prices(record.signal_snapshot, direction)
            existing_stop = (
                Decimal(execution["stop_price"]) if execution.get("stop_price") else None
            )
            payload = self._candidate_payload(record)
            plan = robot_protection.build_protection_plan(
                payload, record.robot_state,
                average_entry=average_entry, structural_extreme=structural_extreme,
                tick_size=tick_size, frozen_signal_reference_price=reference_price,
                frozen_scanner_target_price=target_price, existing_stop=existing_stop,
            )
        except Exception as error:
            self._fail_closed_unprotected_fill(record, error)
            return

        # Owner-frozen D2.3 ownership attestation (CR-PAPER-PROTECTION-LIFECYCLE-001):
        # prove the Robot's own entry quantity and the position's version
        # watermark from the authoritative confirmed position projection --
        # the same durable evidence average_entry above was already read
        # from -- BEFORE any protection side effect. No protection may be
        # submitted before ownership can be proven. create_robot_trade()
        # stays last: candidate remains APPROVED and RobotBreakoutMonitor.tick()
        # keeps retrying this same _finalize_trade() call (via the persisted
        # entry execution state) until it durably commits, which is what
        # makes protection's own idempotent resubmission safe to retry here.
        position_key = PositionKey(self._account_id, Category.LINEAR, record.symbol, 0)
        entry_projection = self._store().get_position_projection(position_key)
        if entry_projection is None or entry_projection.quantity.value <= 0:
            return
        entry_quantity = entry_projection.quantity.value
        entry_position_version = entry_projection.version

        # A fill now exists. If another lifecycle already owns this net
        # symbol, ownership is ambiguous: do not submit conflicting protection
        # and never blind-close the net position. Preserve evidence and
        # require reconciliation.
        duplicate_owners = self._active_other_owner_candidate_ids(record)
        if duplicate_owners:
            self._escalate_duplicate_ownership(record, duplicate_owners)
            return

        try:
            stop_result, take_result = robot_protection.submit_initial_protection(
                self._action_executor, plan,
            )
            if (
                getattr(stop_result, "status", None) != CommandResultStatus.COMPLETED
                or getattr(take_result, "status", None) != CommandResultStatus.COMPLETED
            ):
                raise RobotBreakoutMonitorError("initial protection submission did not complete")
        except Exception as error:
            self._fail_closed_unprotected_fill(record, error)
            return

        # Re-check immediately before final ownership commit. This closes the
        # race between the pre-protection probe and create_robot_trade().
        duplicate_owners = self._active_other_owner_candidate_ids(record)
        if duplicate_owners:
            self._escalate_duplicate_ownership(record, duplicate_owners)
            return

        now_ms = self._now_ms()
        self._store().create_robot_trade(
            trade_id=f"robot-trade-{record.candidate_id}",
            trading_account_id=self._account_id,
            candidate_id=record.candidate_id,
            symbol=record.symbol,
            direction=direction,
            pattern=str(record.signal_snapshot.get("pattern", "")),
            source_timeframe="1",
            signal_time_ms=record.approved_at_ms,
            entry_time_ms=now_ms,
            entry_path=entry_path,
            actual_wv=actual_wv,
            average_entry=average_entry,
            stop_price=plan.stop_price,
            take_price=plan.take_price,
            entry_quantity=entry_quantity,
            entry_position_version=entry_position_version,
            created_at_ms=now_ms,
        )

    def _active_other_owner_candidate_ids(
        self, record: RobotCandidateRecord,
    ) -> tuple[str, ...]:
        return active_robot_owner_candidate_ids(
            self._store(), self._account_id, record.symbol,
            excluding_candidate_id=record.candidate_id,
        )

    def _escalate_duplicate_ownership(
        self, record: RobotCandidateRecord, owner_candidate_ids: tuple[str, ...],
    ) -> None:
        reason = (
            "DUPLICATE_ROBOT_OWNER "
            f"symbol={record.symbol.value} candidate_id={record.candidate_id} "
            f"owner_candidate_ids={','.join(owner_candidate_ids)}"
        )
        for _attempt in range(2):
            runtime = self._store().get_robot_runtime_state(self._account_id)
            if runtime is None:
                raise RobotBreakoutMonitorError(
                    "Robot runtime state is unavailable during duplicate ownership escalation"
                )
            if (
                runtime.mode == "ROBOT_RUNNING"
                and runtime.recovery_status == "RECONCILIATION_REQUIRED"
                and runtime.reason == reason
            ):
                return
            try:
                self._store().update_robot_runtime_state(
                    self._account_id,
                    mode="ROBOT_RUNNING",
                    recovery_status="RECONCILIATION_REQUIRED",
                    reason=reason,
                    expected_version=runtime.version,
                    updated_at_ms=self._now_ms(),
                )
                return
            except ConcurrentUpdate:
                continue
        raise RobotBreakoutMonitorError(
            "Robot runtime state changed during duplicate ownership escalation"
        )

    def _average_entry(self, symbol: Symbol) -> Decimal | None:
        key = PositionKey(self._account_id, Category.LINEAR, symbol, 0)
        projection = self._store().get_position_projection(key)
        if projection is None or projection.average_entry is None:
            return None
        return projection.average_entry.value

    @staticmethod
    def _structural_extreme(signal_snapshot: Mapping[str, object], direction: str) -> Decimal:
        touches = signal_snapshot.get("geometry", {}).get("touches") or {}
        key = (
            "lower_touch_points"
            if direction == robot_state_machine.DIRECTION_LONG
            else "upper_touch_points"
        )
        points = [
            point for point in (touches.get(key) or [])
            if isinstance(point, Mapping) and point.get("counted")
        ]
        if not points:
            raise RobotBreakoutMonitorError(
                f"no counted {key} available to compute structural_extreme"
            )
        prices = [Decimal(str(point["price"])) for point in points]
        return min(prices) if direction == robot_state_machine.DIRECTION_LONG else max(prices)

    @staticmethod
    def _frozen_prices(
        signal_snapshot: Mapping[str, object], direction: str,
    ) -> tuple[Decimal, Decimal]:
        pair_metrics = signal_snapshot.get("geometry", {}).get("pair_metrics") or {}
        reference_price = pair_metrics.get("reference_price")
        start_width = pair_metrics.get("start_width")
        if reference_price is None or start_width is None:
            raise RobotBreakoutMonitorError(
                "signal snapshot pair_metrics is missing reference_price/start_width"
            )
        reference = Decimal(str(reference_price))
        width = Decimal(str(start_width)).copy_abs()
        target = (
            reference + width
            if direction == robot_state_machine.DIRECTION_LONG
            else reference - width
        )
        return reference, target

    def _submit_initial_retest_limit(
        self, record: RobotCandidateRecord, state: Mapping[str, object],
    ):
        payload = {
            "candidate_id": record.candidate_id,
            "status": record.status,
            "timeframe": "1",
            "signal_snapshot": record.signal_snapshot,
        }
        tick_size = self._tick_size_provider(record.symbol.value)
        plan = robot_entry_limit.build_initial_retest_limit(
            payload, state, tick_size=tick_size,
        )
        return robot_entry_limit.submit_initial_retest_limit(self._action_executor, plan)

    def _read_admission_gate(self) -> tuple[bool, bool]:
        """Read the authoritative durable robot_runtime_state and derive the
        two admission facts this coordinator's risk-increasing pre-entry
        submission call sites need: whether a NEW entry order may be
        submitted right now, and whether durable mode has reached the
        terminal ROBOT_STOPPED state.

        This is the exact same admission condition
        ``robot_admission.admit_robot_candidate()`` already gates brand-new
        candidate admission on (``mode == ROBOT_RUNNING and recovery_status
        == READY``) -- reused here, not reintroduced as a second state
        machine, because RobotBreakoutMonitor is the sole owner of
        already-admitted APPROVED candidates and must apply the identical
        admission boundary to any further order it submits on their behalf.
        Every other phase-transition/bookkeeping path in this class (state
        machine advancement, apex-expiry detection, already-filled
        protection/finalize, emergency close) is deliberately left
        unconditional on this gate: it governs only NEW entry risk.
        """
        state = self._store().get_robot_runtime_state(self._account_id)
        if state is None:
            # Durable runtime state not yet initialized: fail closed on new
            # entry risk, but do not treat this as a terminal ROBOT_STOPPED
            # disposition -- that would risk prematurely invalidating a
            # candidate during a startup race rather than simply waiting.
            return False, False
        new_entry_admitted = (
            state.mode == "ROBOT_RUNNING" and state.recovery_status == "READY"
        )
        terminal_stop = state.mode == "ROBOT_STOPPED"
        return new_entry_admitted, terminal_stop

    def _invalidate_pre_entry_candidate(
        self, record: RobotCandidateRecord, *, reason: str,
    ) -> None:
        """Give a pending pre-entry Robot candidate its explicit durable
        terminal disposition once durable mode has reached ROBOT_STOPPED,
        per AUTOPILOT_ROBOT_V0_1_RESTART_FROM_STOPPED_DECISION.md
        ("previously stopped candidates remain terminal and must not
        re-enter the active candidate set"). Reuses the existing terminal
        INVALIDATED status and save_robot_candidate_state() path already
        established by _fail_closed_unprotected_fill() -- no new candidate
        status or transition is introduced.

        Only ever called when no fill/exposure exists yet for this
        candidate (a zero-fill resting entry LIMIT, or none submitted at
        all): a candidate that already has a partial fill is deliberately
        never invalidated here, since that would orphan a live position
        with no robot_trade/protection ownership record.
        """
        execution = dict(record.robot_state.get("execution") or {})
        execution["stopped_without_entry_at_ms"] = self._now_ms()
        execution["stopped_without_entry_reason"] = reason
        new_state = dict(record.robot_state)
        new_state["execution"] = execution
        try:
            self._store().save_robot_candidate_state(
                record.candidate_id,
                status="INVALIDATED",
                robot_state=new_state,
                expected_revision=record.state_revision,
                updated_at_ms=self._now_ms(),
            )
        except ConcurrentUpdate:
            # Another writer already advanced this candidate first; no
            # exposure exists in this path, so nothing further to reconcile.
            pass

    def _fail_closed_unprotected_fill(
        self, record: RobotCandidateRecord, error: Exception,
    ) -> None:
        """A Robot entry already filled into a real authoritative position, but
        initial STOP/TAKE protection could not be derived, built, validated,
        or submitted for it (CR-PAPER-PROTECTION-LIFECYCLE-001
        post-BATUSDT-defect fix). Never leave a filled position open and
        unprotected waiting for the next tick without at least attempting a
        close: submit the same sanctioned PAPER full-close path
        ``submit_emergency_close()`` already uses elsewhere, using
        ``emergency_close_request()``'s deterministic action id so a close
        retried across ticks is idempotent, exactly like
        ``protection_recovery()``'s own emergency close.

        The candidate is invalidated -- and only then -- once FLAT is itself
        authoritatively confirmed: an ambiguous, rejected, unavailable, or
        otherwise incomplete close (or one that completes but the position
        somehow reads back still non-flat) leaves the candidate APPROVED, so
        RobotBreakoutMonitor's existing per-tick retry (already relied on
        elsewhere in _finalize_trade for the ownership-attestation gate)
        keeps attempting/reconciling the close instead of prematurely
        terminalizing a position that may still be open. No robot_trade is
        ever created here; this candidate never proved out a protected entry.
        """
        duplicate_owners = self._active_other_owner_candidate_ids(record)
        if duplicate_owners:
            # Section 10 narrow exception: a full-close would destroy another
            # legitimate owner of the same net position. Preserve evidence,
            # escalate, and deliberately do not close.
            execution = dict(record.robot_state.get("execution") or {})
            execution["protection_failure"] = str(error)
            execution["duplicate_owner_candidate_ids"] = list(duplicate_owners)
            execution["duplicate_ownership_detected_at_ms"] = self._now_ms()
            self._persist_execution(record, execution)
            self._escalate_duplicate_ownership(record, duplicate_owners)
            return

        request = robot_protection.emergency_close_request(record.candidate_id, record.symbol.value)
        execution = dict(record.robot_state.get("execution") or {})
        execution["protection_failure"] = str(error)
        execution["emergency_close_attempted_at_ms"] = self._now_ms()

        try:
            result = self._action_executor.full_close(request)
        except Exception as close_error:
            execution["emergency_close_pending"] = True
            execution["emergency_close_error"] = str(close_error)
            self._persist_execution(record, execution)
            return

        authoritative_flat = False
        completed = getattr(result, "status", None) == CommandResultStatus.COMPLETED
        if completed:
            position_key = PositionKey(self._account_id, Category.LINEAR, record.symbol, 0)
            projection = self._store().get_position_projection(position_key)
            authoritative_flat = projection is None or projection.quantity.value <= 0

        if not (completed and authoritative_flat):
            execution["emergency_close_pending"] = True
            self._persist_execution(record, execution)
            return

        execution.pop("emergency_close_pending", None)
        execution.pop("emergency_close_error", None)
        execution["emergency_close_outcome"] = robot_protection.RECOVERY_CLOSED
        execution["emergency_closed_at_ms"] = self._now_ms()
        new_state = dict(record.robot_state)
        new_state["execution"] = execution
        try:
            self._store().save_robot_candidate_state(
                record.candidate_id,
                status="INVALIDATED",
                robot_state=new_state,
                expected_revision=record.state_revision,
                updated_at_ms=self._now_ms(),
            )
        except ConcurrentUpdate:
            # Another writer already advanced this candidate first; the
            # emergency close above already ran and is idempotent by
            # deterministic action id if retried on a later tick.
            pass

    def _persist_execution(
        self, record: RobotCandidateRecord, execution: Mapping[str, object],
    ) -> None:
        new_state = dict(record.robot_state)
        new_state["execution"] = dict(execution)
        self._persist_state(record, new_state)

    def _persist_state(
        self, record: RobotCandidateRecord, new_state: Mapping[str, object],
    ) -> None:
        status = (
            "EXPIRED"
            if new_state.get("phase") == robot_state_machine.PHASE_EXPIRED_AT_APEX
            else "APPROVED"
        )
        try:
            self._store().save_robot_candidate_state(
                record.candidate_id,
                status=status,
                robot_state=dict(new_state),
                expected_revision=record.state_revision,
                updated_at_ms=self._now_ms(),
            )
        except ConcurrentUpdate:
            # Another writer already advanced this candidate first; skip it
            # for this tick rather than overwrite a newer durable state.
            pass

    @staticmethod
    def _candidate_payload(record: RobotCandidateRecord) -> dict[str, object]:
        return {
            "candidate_id": record.candidate_id,
            "status": record.status,
            "timeframe": "1",
            "symbol": record.symbol.value,
            "signal_snapshot": dict(record.signal_snapshot),
        }

    def _now_ms(self) -> int:
        value = self._clock_ms()
        if not isinstance(value, int) or isinstance(value, bool) or value < 0:
            raise RobotBreakoutMonitorError(
                "Robot breakout monitor clock returned invalid timestamp"
            )
        return value
