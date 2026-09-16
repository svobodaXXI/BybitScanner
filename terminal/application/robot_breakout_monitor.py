"""Durable Robot v0.1 breakout/retest lifecycle monitor over APPROVED candidates.

Mode-agnostic coordinator, structurally mirroring
``terminal.application.robot_recovery.RobotRecoveryCoordinator``: it accepts a
``trading_account_id`` and dependency-injected functions rather than a
concrete PaperRuntime, so a future live implementation can reuse it with
live-bound dependencies instead of a duplicated cycle. It never refits
geometry and never invents entry/pattern/protection strategy: it only calls
the existing public functions of robot_state_machine.py, robot_entry_limit.py,
robot_protection.py,
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
import robot_protection
import robot_state_machine
from scanner_geometry_cursor import (
    ScannerGeometryCursorError,
    latest_scanner_closed_candle,
    load_scanner_catchup_closed_candles,
    project_latest_geometry_index,
)
from terminal.api.models import ClientActionId, CommandResultStatus, MarketCommandRequest, PaperLimitCancelRequest
from terminal.application.command_identity import CommandIdentityCandidate
from terminal.application.robot_admission import active_robot_owner_candidate_ids
from terminal.application.robot_admission_catchup import (
    LATE_ADMISSION_MARKET,
    replay_admission_catchup,
)
from terminal.application.robot_late_admission import (
    DECISION_APEX_REACHED as LATE_DECISION_APEX_REACHED,
    DECISION_MARKET_ENTRY as LATE_DECISION_MARKET_ENTRY,
    build_late_admission_market,
    evaluate_late_admission,
)
from terminal.domain.models import Category, PositionKey, Quantity, Symbol, TradingAccountId
from terminal.market_data.models import NormalizedOrderBook
from terminal.persistence.sqlite_store import (
    ConcurrentUpdate,
    RobotCandidateRecord,
    SQLiteStore,
)

DEFAULT_TICK_INTERVAL_S = 60.0
DEFAULT_LATE_MARKET_MAX_BOOK_AGE_MS = 1000

INACTIVE_LIMIT_STATUSES = {"filled", "cancelled"}


class ActionExecutor(Protocol):
    """Unified execution port. PaperRuntime already satisfies this today; a
    future live_runtime.py can satisfy it with live-bound implementations
    without duplicating this coordinator's cycle."""

    def create_limit(self, request): ...
    def cancel_limit(self, request): ...
    def create_stop(self, request): ...
    def amend_stop(self, request): ...
    def create_take(self, request): ...
    def amend_take(self, request): ...
    def full_close(self, request): ...


class RobotBreakoutMonitorError(RuntimeError):
    """Raised when the breakout/retest monitor cannot safely advance a candidate."""


def _cancel_partial_remainder_action_id(candidate_id: str) -> ClientActionId:
    digest = hashlib.sha256(
        f"{candidate_id}\0cancel-partial-remainder".encode("utf-8")
    ).hexdigest()[:32]
    return ClientActionId(f"robot-cancel-partial-{digest}")


def _cancel_blocked_entry_action_id(candidate_id: str) -> ClientActionId:
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
        get_admission_catchup_candles: Callable[
            [str, Mapping[str, object]], tuple[Mapping[str, object], ...]
        ] | None = None,
        get_market_book: Callable[[str], NormalizedOrderBook | None] | None = None,
        market_preflight: Callable[[MarketCommandRequest, CommandIdentityCandidate], object] | None = None,
        submit_market: Callable[[MarketCommandRequest, CommandIdentityCandidate], object] | None = None,
        late_market_max_book_age_ms: int = DEFAULT_LATE_MARKET_MAX_BOOK_AGE_MS,
    ) -> None:
        self._store_factory = store_factory
        self._local = threading.local()
        self._account_id = trading_account_id
        self._get_closed_candle = get_closed_candle
        if (
            get_admission_catchup_candles is None
            and get_closed_candle is latest_scanner_closed_candle
        ):
            get_admission_catchup_candles = load_scanner_catchup_closed_candles
        self._get_admission_catchup_candles = get_admission_catchup_candles
        self._action_executor = action_executor
        self._tick_size_provider = tick_size_provider
        self._clock_ms = clock_ms
        self._tick_interval_s = tick_interval_s
        self._match_resting_orders = match_resting_orders
        self._get_market_book = get_market_book
        self._market_preflight = market_preflight
        self._submit_market = submit_market
        self._late_market_max_book_age_ms = late_market_max_book_age_ms
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
        self._close_local_store()

    def _close_local_store(self) -> None:
        store = getattr(self._local, "store", None)
        if store is not None:
            store.close()
            self._local.store = None

    def _run(self) -> None:
        try:
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
        """Advance every durable APPROVED candidate by at most one step."""
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

    def process_authoritative_fill(self, symbol: str) -> tuple[str, ...]:
        normalized = symbol.strip().upper()
        if not normalized:
            raise ValueError("symbol must be non-empty")

        advanced: list[str] = []
        for record in self._store().load_robot_candidates(self._account_id):
            if (
                record.status != "APPROVED"
                or record.symbol.value != normalized
                or record.robot_state is None
                or record.robot_state.get("phase") != robot_state_machine.PHASE_RETEST_DETECTED
            ):
                continue
            execution = record.robot_state.get("execution") or {}
            order_id = execution.get("limit_order_id")
            if not order_id:
                continue
            order = self._store().get_paper_limit(order_id, self._account_id)
            if order is None or order.quantity <= 0 or order.filled_quantity <= 0:
                continue
            try:
                if self._advance_retest_detected(record, match_resting_orders=False):
                    advanced.append(record.candidate_id)
            except Exception as error:
                print(
                    "[ROBOT CANDIDATE ERROR] "
                    f"candidate_id={record.candidate_id} error={error}"
                )
                self._record_execution_error(record, error)
        return tuple(advanced)

    def _record_execution_error(self, record: RobotCandidateRecord, error: Exception) -> None:
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
            if (
                state.get("phase") != robot_state_machine.PHASE_EXPIRED_AT_APEX
                and self._get_admission_catchup_candles is not None
            ):
                candles = self._get_admission_catchup_candles(
                    record.symbol.value,
                    record.signal_snapshot,
                )
                state, _events = replay_admission_catchup(
                    record.signal_snapshot,
                    state,
                    candles,
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

        self._persist_state(record, new_state)
        return True

    def _advance_retest_detected(
        self, record: RobotCandidateRecord, *, match_resting_orders: bool = True,
    ) -> bool:
        execution = dict(record.robot_state.get("execution") or {})

        if (
            execution.get("entry_mode") == LATE_ADMISSION_MARKET
            and "limit_order_id" not in execution
        ):
            return self._advance_late_admission(record, execution)

        if "limit_order_id" not in execution:
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
                if terminal_stop:
                    self._invalidate_pre_entry_candidate(
                        record, reason="ROBOT_STOPPED before entry order submission",
                    )
                    return True
                return False

            if self._active_other_owner_candidate_ids(record):
                return False

            result = self._submit_initial_retest_limit(record, record.robot_state)
            order_id = getattr(result, "order_id", None)
            if not order_id:
                return False
            execution["limit_order_id"] = order_id
            self._persist_execution(record, execution)
            return True

        if match_resting_orders and self._match_resting_orders is not None:
            self._match_resting_orders(record.symbol.value)

        order = self._store().get_paper_limit(execution["limit_order_id"], self._account_id)
        if order is None or order.quantity <= 0:
            return False

        filled_fraction = min(order.filled_quantity / order.quantity, Decimal("1"))
        inactive = order.status in INACTIVE_LIMIT_STATUSES

        if filled_fraction <= 0:
            new_entry_admitted, terminal_stop = self._read_admission_gate()
            if new_entry_admitted:
                return False
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

        if not inactive:
            self._action_executor.cancel_limit(PaperLimitCancelRequest(
                _cancel_partial_remainder_action_id(record.candidate_id),
                record.symbol.value, execution["limit_order_id"],
            ))
            refreshed = self._store().get_paper_limit(
                execution["limit_order_id"], self._account_id,
            )
            if refreshed is not None:
                order = refreshed
                filled_fraction = min(order.filled_quantity / order.quantity, Decimal("1"))

        if filled_fraction <= 0:
            return True

        average_entry = self._average_entry(record.symbol)
        if average_entry is None:
            return True

        fresh_record = self._store().get_robot_candidate(record.candidate_id) or record
        self._finalize_trade(
            fresh_record, execution, entry_path="LIMIT",
            actual_wv=filled_fraction, average_entry=average_entry,
        )
        return True

    def _advance_late_admission(
        self, record: RobotCandidateRecord, execution: dict[str, object],
    ) -> bool:
        intent = execution.get("late_market_intent")

        # A previously filled deterministic Market must be finalized/protected
        # even if new-entry admission has since been paused or stopped.
        average_entry = self._average_entry(record.symbol)
        if isinstance(intent, Mapping) and average_entry is not None:
            self._finalize_trade(
                record, execution, entry_path="MARKET",
                actual_wv=Decimal("1"), average_entry=average_entry,
            )
            return True

        # Runtime binding is a separate microslice. Until all three callbacks
        # exist, late admission remains fail-closed and ordinary LIMIT behavior
        # is unchanged.
        if (
            self._get_market_book is None
            or self._market_preflight is None
            or self._submit_market is None
        ):
            return False

        new_entry_admitted, terminal_stop = self._read_admission_gate()
        if not new_entry_admitted:
            if terminal_stop and not isinstance(intent, Mapping):
                self._invalidate_pre_entry_candidate(
                    record, reason="ROBOT_STOPPED before late Market submission",
                )
                return True
            return False
        if self._active_other_owner_candidate_ids(record):
            return False

        if isinstance(intent, Mapping):
            plan = self._late_market_plan_from_intent(record, intent)
            result = self._submit_market(plan.request, plan.identity)
            if getattr(result, "status", None) == CommandResultStatus.COMPLETED:
                average_entry = self._average_entry(record.symbol)
                if average_entry is not None:
                    fresh = self._store().get_robot_candidate(record.candidate_id) or record
                    fresh_execution = dict(fresh.robot_state.get("execution") or execution)
                    self._finalize_trade(
                        fresh, fresh_execution, entry_path="MARKET",
                        actual_wv=Decimal("1"), average_entry=average_entry,
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

        book = self._get_market_book(record.symbol.value)
        if book is None:
            return False
        direction = str(record.robot_state.get("direction", "")).strip().upper()
        levels = (
            book.asks
            if direction == robot_state_machine.DIRECTION_LONG
            else book.bids
        )
        if not levels:
            return False
        sizing_reference_price = levels[0].price.value
        plan = build_late_admission_market(
            self._candidate_payload(record),
            record.robot_state,
            sizing_reference_price=sizing_reference_price,
        )
        preflight = self._market_preflight(plan.request, plan.identity)
        if not getattr(preflight, "admitted", False):
            return False
        normalized_quantity = getattr(preflight, "normalized_quantity", None)
        if not isinstance(normalized_quantity, Decimal) or normalized_quantity <= 0:
            return False

        structural_extreme = self._structural_extreme(
            record.signal_snapshot, direction,
        )
        tick_size = self._tick_size_provider(record.symbol.value)
        reference_price, target_price = self._frozen_prices(
            record.signal_snapshot, direction,
        )
        decision = evaluate_late_admission(
            record.signal_snapshot,
            record.robot_state,
            book,
            quantity=Quantity(normalized_quantity),
            current_geometry_index=geometry_index,
            now_ms=self._now_ms(),
            max_book_age_ms=self._late_market_max_book_age_ms,
            structural_extreme=structural_extreme,
            tick_size=tick_size,
            frozen_signal_reference_price=reference_price,
            frozen_scanner_target_price=target_price,
            admission_ready=True,
            ownership_clear=True,
        )
        if decision.action == LATE_DECISION_APEX_REACHED:
            expired_state = dict(record.robot_state)
            expired_state["phase"] = robot_state_machine.PHASE_EXPIRED_AT_APEX
            expired_state["last_event"] = robot_state_machine.EVENT_EXPIRED_AT_APEX
            expired_state["geometry_cursor"] = geometry_index
            self._persist_state(record, expired_state)
            return True
        if decision.action != LATE_DECISION_MARKET_ENTRY:
            return False

        intent = {
            "client_action_id": plan.request.client_action_id.value,
            "command_id": plan.identity.command_id.value,
            "order_link_id": plan.identity.order_link_id,
            "sizing_reference_price": str(plan.request.sizing_reference_price),
            "slippage_type": plan.request.slippage_type,
            "slippage_value": str(plan.request.slippage_value),
            "normalized_quantity": str(normalized_quantity),
            "geometry_index": geometry_index,
            "projected_vwap": str(decision.projected_vwap),
            "stop_price": str(decision.stop_price),
            "take_price": str(decision.take_price),
            "expected_reward": str(decision.expected_reward),
            "rr": str(decision.rr),
            "adverse_slippage": str(decision.adverse_slippage),
        }
        durable_execution = dict(execution)
        durable_execution["late_market_intent"] = intent
        durable_state = dict(record.robot_state)
        durable_state["execution"] = durable_execution
        try:
            self._store().save_robot_candidate_state(
                record.candidate_id,
                status="APPROVED",
                robot_state=durable_state,
                expected_revision=record.state_revision,
                updated_at_ms=self._now_ms(),
            )
        except ConcurrentUpdate:
            # Strict boundary: if the intent did not durably commit exactly at
            # the expected revision, no Market side effect is permitted.
            return False

        # Re-read both risk gates after the durable intent commit and before
        # the first side effect. A pause/ownership race therefore withholds the
        # submit while preserving the already-authorized deterministic intent.
        fresh = self._store().get_robot_candidate(record.candidate_id)
        if fresh is None:
            return True
        new_entry_admitted, _terminal_stop = self._read_admission_gate()
        if not new_entry_admitted or self._active_other_owner_candidate_ids(fresh):
            return True

        result = self._submit_market(plan.request, plan.identity)
        if getattr(result, "status", None) == CommandResultStatus.COMPLETED:
            average_entry = self._average_entry(record.symbol)
            if average_entry is not None:
                fresh = self._store().get_robot_candidate(record.candidate_id) or fresh
                fresh_execution = dict(fresh.robot_state.get("execution") or durable_execution)
                self._finalize_trade(
                    fresh, fresh_execution, entry_path="MARKET",
                    actual_wv=Decimal("1"), average_entry=average_entry,
                )
        return True

    def _late_market_plan_from_intent(
        self, record: RobotCandidateRecord, intent: Mapping[str, object],
    ):
        try:
            reference = Decimal(str(intent["sizing_reference_price"]))
            slippage_value = Decimal(str(intent["slippage_value"]))
            slippage_type = str(intent["slippage_type"])
        except Exception as exc:
            raise RobotBreakoutMonitorError("durable late Market intent is invalid") from exc
        plan = build_late_admission_market(
            self._candidate_payload(record),
            record.robot_state,
            sizing_reference_price=reference,
            slippage_type=slippage_type,
            slippage_value=slippage_value,
        )
        if (
            plan.request.client_action_id.value != intent.get("client_action_id")
            or plan.identity.command_id.value != intent.get("command_id")
            or plan.identity.order_link_id != intent.get("order_link_id")
        ):
            raise RobotBreakoutMonitorError("durable late Market identity mismatch")
        return plan

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

        position_key = PositionKey(self._account_id, Category.LINEAR, record.symbol, 0)
        entry_projection = self._store().get_position_projection(position_key)
        if entry_projection is None or entry_projection.quantity.value <= 0:
            return
        entry_quantity = entry_projection.quantity.value
        entry_position_version = entry_projection.version

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
        state = self._store().get_robot_runtime_state(self._account_id)
        if state is None:
            return False, False
        new_entry_admitted = (
            state.mode == "ROBOT_RUNNING" and state.recovery_status == "READY"
        )
        terminal_stop = state.mode == "ROBOT_STOPPED"
        return new_entry_admitted, terminal_stop

    def _invalidate_pre_entry_candidate(
        self, record: RobotCandidateRecord, *, reason: str,
    ) -> None:
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
            pass

    def _fail_closed_unprotected_fill(
        self, record: RobotCandidateRecord, error: Exception,
    ) -> None:
        duplicate_owners = self._active_other_owner_candidate_ids(record)
        if duplicate_owners:
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
