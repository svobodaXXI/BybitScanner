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
from dataclasses import dataclass
from decimal import Decimal
from typing import Callable, Mapping, Protocol

import robot_entry_limit
import robot_protection
import robot_state_machine
from robot_market_confirmation import risk_reward_ratio
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
    evaluate_late_admission,
)
from terminal.application.robot_late_admission_market import (
    build_late_admission_market_plan,
    durable_late_admission_market_intent,
    restore_late_admission_market_plan,
)
from terminal.domain.models import (
    Category, CommandId, OrderId, OrderSide, PositionKey, PositionSide, Quantity,
    Symbol, TradingAccountId,
)
from terminal.market_data.models import NormalizedOrderBook
from terminal.persistence.sqlite_store import (
    ConcurrentUpdate,
    RobotCandidateRecord,
    SQLiteStore,
)

DEFAULT_TICK_INTERVAL_S = 60.0
DEFAULT_LATE_MARKET_MAX_BOOK_AGE_MS = 1000

INACTIVE_LIMIT_STATUSES = {"filled", "cancelled"}
PHASE_INVALIDATED_UNSUPPORTED_PATTERN = "INVALIDATED_UNSUPPORTED_PATTERN"
ENTRY_RR_SKIP_POOR_RR = "SKIPPED_POOR_RR"  # same name as the late-admission decision
ENTRY_RR_SKIP_UNAVAILABLE = "SKIPPED_RR_UNAVAILABLE"


class ActionExecutor(Protocol):
    """Unified execution port. PaperRuntime already satisfies this today; a
    future live_runtime.py can satisfy it with live-bound implementations
    without duplicating this coordinator's cycle."""

    def create_limit(self, request): ...
    def amend_limit(self, request): ...
    def cancel_limit(self, request): ...
    def create_stop(self, request): ...
    def amend_stop(self, request): ...
    def create_take(self, request): ...
    def amend_take(self, request): ...
    def full_close(self, request): ...


class RobotBreakoutMonitorError(RuntimeError):
    """Raised when the breakout/retest monitor cannot safely advance a candidate."""


@dataclass(frozen=True, slots=True)
class _EntryEvidence:
    order_id: OrderId
    quantity: Decimal
    average_entry: Decimal
    position_version: int


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


def _cancel_apex_entry_action_id(candidate_id: str) -> ClientActionId:
    digest = hashlib.sha256(
        f"{candidate_id}\0cancel-entry-at-apex".encode("utf-8")
    ).hexdigest()[:32]
    return ClientActionId(f"robot-cancel-apex-{digest}")


def _frozen_robot_apex_index(signal_snapshot: Mapping[str, object]) -> Decimal:
    geometry = signal_snapshot.get("robot_geometry")
    if geometry is None:
        geometry = signal_snapshot.get("geometry")
    apex = geometry.get("apex") if isinstance(geometry, Mapping) else None
    raw = apex.get("index") if isinstance(apex, Mapping) else None
    try:
        value = Decimal(str(raw))
    except Exception as exc:
        raise RobotBreakoutMonitorError("frozen Robot apex is invalid") from exc
    if not value.is_finite() or value < 0:
        raise RobotBreakoutMonitorError("frozen Robot apex is invalid")
    return value


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
        for record in self._store().load_robot_candidates_by_status(
            self._account_id, ("APPROVED",),
        ):
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
        symbol_value = Symbol(normalized)
        for record in self._store().load_robot_candidates_for_symbol(
            self._account_id, symbol_value,
        ):
            if (
                record.status != "APPROVED"
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
            try:
                state, _event = robot_state_machine.initialize_state(
                    self._candidate_payload(record),
                )
            except robot_state_machine.RobotStateMachineError as error:
                pattern = (record.signal_snapshot or {}).get("pattern")
                if robot_state_machine.is_supported_pattern(pattern):
                    raise
                self._invalidate_unsupported_pattern(record, error)
                return True
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
            apex_index = _frozen_robot_apex_index(record.signal_snapshot)
            if Decimal(geometry_index) >= apex_index:
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

            block_reason = self._pre_entry_block_reason(record)
            if block_reason is not None:
                self._invalidate_pre_entry_candidate(record, reason=block_reason)
                return True

            plan = self._build_initial_retest_limit_plan(record, record.robot_state)
            rr_skip = self._entry_rr_skip(record, plan)
            if rr_skip is not None:
                reason, details = rr_skip
                self._invalidate_pre_entry_candidate(record, reason=reason, details=details)
                return True
            result = robot_entry_limit.submit_initial_retest_limit(self._action_executor, plan)
            order_id = getattr(result, "order_id", None)
            if not order_id:
                return False
            execution["limit_order_id"] = order_id
            execution["last_limit_index"] = geometry_index
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
            block_reason = self._pre_entry_block_reason(
                record, allowed_limit_order_id=execution["limit_order_id"],
            )
            if block_reason is not None:
                if not inactive:
                    self._action_executor.cancel_limit(PaperLimitCancelRequest(
                        _cancel_blocked_entry_action_id(record.candidate_id),
                        record.symbol.value, execution["limit_order_id"],
                    ))
                self._invalidate_pre_entry_candidate(record, reason=block_reason)
                return True

            new_entry_admitted, terminal_stop = self._read_admission_gate()
            if not new_entry_admitted:
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

            if inactive:
                self._invalidate_pre_entry_candidate(
                    record,
                    reason="ENTRY_LIMIT_INACTIVE_BEFORE_FILL",
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

            apex_index = _frozen_robot_apex_index(record.signal_snapshot)
            if Decimal(geometry_index) >= apex_index:
                result = self._action_executor.cancel_limit(PaperLimitCancelRequest(
                    _cancel_apex_entry_action_id(record.candidate_id),
                    record.symbol.value,
                    execution["limit_order_id"],
                ))
                if getattr(result, "status", None) != CommandResultStatus.COMPLETED:
                    return False
                expired_state = dict(record.robot_state)
                expired_state["phase"] = robot_state_machine.PHASE_EXPIRED_AT_APEX
                expired_state["last_event"] = robot_state_machine.EVENT_EXPIRED_AT_APEX
                expired_state["geometry_cursor"] = geometry_index
                expired_execution = dict(execution)
                expired_execution["cancelled_at_apex_index"] = geometry_index
                expired_state["execution"] = expired_execution
                self._persist_state(record, expired_state)
                return True

            last_limit_index = int(
                execution.get(
                    "last_limit_index",
                    record.robot_state.get("retest_index"),
                )
            )
            if geometry_index < last_limit_index:
                return False
            if not robot_entry_limit.reprice_due(
                last_limit_index=last_limit_index,
                current_index=geometry_index,
            ):
                return False

            plan = robot_entry_limit.build_retest_limit_reprice(
                self._candidate_payload(record),
                record.robot_state,
                geometry_index=geometry_index,
                tick_size=self._tick_size_provider(record.symbol.value),
                order_id=execution["limit_order_id"],
            )
            # The reprice changes the prospective entry price. Do not amend a
            # previously admitted resting LIMIT to a price with poor or
            # uncomputable RR; keep monitoring the original proven order.
            if self._entry_rr_skip(
                record, plan, direction=str(record.robot_state["direction"]),
            ) is not None:
                return False
            result = robot_entry_limit.submit_retest_limit_reprice(
                self._action_executor, plan,
            )
            if getattr(result, "status", None) != CommandResultStatus.COMPLETED:
                return False
            execution["last_limit_index"] = geometry_index
            self._persist_execution(record, execution)
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

        fresh_record = self._store().get_robot_candidate(record.candidate_id) or record
        self._finalize_trade(
            fresh_record, execution, entry_path="LIMIT",
            actual_wv=filled_fraction,
        )
        return True

    def _advance_late_admission(
        self, record: RobotCandidateRecord, execution: dict[str, object],
    ) -> bool:
        intent = execution.get("late_market_intent")

        if isinstance(intent, Mapping):
            if self._finalize_trade(
                record, execution, entry_path="MARKET",
                actual_wv=Decimal("1"),
            ):
                return True

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

        block_reason = self._pre_entry_block_reason(record)
        if block_reason is not None:
            self._invalidate_pre_entry_candidate(record, reason=block_reason)
            return True

        if isinstance(intent, Mapping):
            plan = restore_late_admission_market_plan(intent)
            result = self._submit_market(plan.request, plan.identity)
            if getattr(result, "status", None) == CommandResultStatus.COMPLETED:
                fresh = self._store().get_robot_candidate(record.candidate_id) or record
                fresh_execution = dict(fresh.robot_state.get("execution") or execution)
                self._finalize_trade(
                    fresh, fresh_execution, entry_path="MARKET",
                    actual_wv=Decimal("1"),
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
        plan = build_late_admission_market_plan(
            self._candidate_payload(record), record.robot_state, book,
        )
        preflight = self._market_preflight(plan.request, plan.identity)
        if not getattr(preflight, "admitted", False):
            return False
        normalized_quantity = getattr(preflight, "normalized_quantity", None)
        if not isinstance(normalized_quantity, Decimal) or normalized_quantity <= 0:
            return False

        direction = str(record.robot_state.get("direction", "")).strip().upper()
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

        intent = durable_late_admission_market_intent(
            plan,
            normalized_quantity=normalized_quantity,
            current_geometry_index=geometry_index,
            projected_vwap=decision.projected_vwap,
            stop_price=decision.stop_price,
            take_price=decision.take_price,
            expected_reward=decision.expected_reward,
            rr=decision.rr,
            adverse_slippage=decision.adverse_slippage,
            persisted_at_ms=self._now_ms(),
        )
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
            return False

        fresh = self._store().get_robot_candidate(record.candidate_id)
        if fresh is None:
            return True
        new_entry_admitted, _terminal_stop = self._read_admission_gate()
        if not new_entry_admitted or self._active_other_owner_candidate_ids(fresh):
            return True
        block_reason = self._pre_entry_block_reason(fresh)
        if block_reason is not None:
            self._invalidate_pre_entry_candidate(fresh, reason=block_reason)
            return True

        result = self._submit_market(plan.request, plan.identity)
        if getattr(result, "status", None) == CommandResultStatus.COMPLETED:
            fresh = self._store().get_robot_candidate(record.candidate_id) or fresh
            fresh_execution = dict(fresh.robot_state.get("execution") or durable_execution)
            self._finalize_trade(
                fresh, fresh_execution, entry_path="MARKET",
                actual_wv=Decimal("1"),
            )
        return True

    def _finalize_trade(
        self,
        record: RobotCandidateRecord,
        execution: Mapping[str, object],
        *,
        entry_path: str,
        actual_wv: Decimal,
    ) -> bool:
        direction = record.robot_state["direction"]
        try:
            entry_evidence = self._prove_entry_evidence(
                record, execution, entry_path=entry_path,
            )
        except RobotBreakoutMonitorError as error:
            self._escalate_reconciliation(
                "ROBOT_ENTRY_OWNERSHIP_MISMATCH "
                f"symbol={record.symbol.value} candidate_id={record.candidate_id} "
                f"reason={error}"
            )
            return False
        if entry_evidence is None:
            return False

        average_entry = entry_evidence.average_entry
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
            return False

        entry_quantity = entry_evidence.quantity
        entry_position_version = entry_evidence.position_version

        duplicate_owners = self._active_other_owner_candidate_ids(record)
        if duplicate_owners:
            self._escalate_duplicate_ownership(record, duplicate_owners)
            return False

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
            return False

        duplicate_owners = self._active_other_owner_candidate_ids(record)
        if duplicate_owners:
            self._escalate_duplicate_ownership(record, duplicate_owners)
            return False

        try:
            confirmed_evidence = self._prove_entry_evidence(
                record, execution, entry_path=entry_path,
            )
        except RobotBreakoutMonitorError as error:
            self._escalate_reconciliation(
                "ROBOT_ENTRY_OWNERSHIP_MISMATCH "
                f"symbol={record.symbol.value} candidate_id={record.candidate_id} "
                f"reason={error}"
            )
            return False
        if confirmed_evidence != entry_evidence:
            self._escalate_reconciliation(
                "ROBOT_ENTRY_OWNERSHIP_CHANGED "
                f"symbol={record.symbol.value} candidate_id={record.candidate_id}"
            )
            return False

        now_ms = self._now_ms()
        self._store().create_robot_trade(
            trade_id=f"robot-trade-{record.candidate_id}",
            trading_account_id=self._account_id,
            candidate_id=record.candidate_id,
            symbol=record.symbol,
            direction=direction,
            pattern=str(record.signal_snapshot.get("pattern", "")),
            source_timeframe=str(
                record.signal_snapshot.get(
                    "scanner_source_timeframe",
                    record.signal_snapshot.get("timeframe", "1"),
                )
            ).strip() or "1",
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
        return True

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
        self._escalate_reconciliation(
            "DUPLICATE_ROBOT_OWNER "
            f"symbol={record.symbol.value} candidate_id={record.candidate_id} "
            f"owner_candidate_ids={','.join(owner_candidate_ids)}"
        )

    def _escalate_reconciliation(self, reason: str) -> None:
        for _attempt in range(2):
            runtime = self._store().get_robot_runtime_state(self._account_id)
            if runtime is None:
                raise RobotBreakoutMonitorError(
                    "Robot runtime state is unavailable during safety escalation"
                )
            if (
                runtime.mode == "ROBOT_RUNNING"
                and runtime.recovery_status == "RECONCILIATION_REQUIRED"
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
            "Robot runtime state changed during safety escalation"
        )

    def _pre_entry_block_reason(
        self,
        record: RobotCandidateRecord,
        *,
        allowed_limit_order_id: str | None = None,
    ) -> str | None:
        position_key = PositionKey(self._account_id, Category.LINEAR, record.symbol, 0)
        position = self._store().get_position_projection(position_key)
        if (
            position is not None
            and (
                position.side is not PositionSide.FLAT
                or position.quantity.value != 0
            )
        ):
            return (
                "FOREIGN_POSITION_PRESENT_BEFORE_ROBOT_ENTRY "
                f"symbol={record.symbol.value}"
            )

        foreign_orders = tuple(
            order.order_id.value
            for order in self._store().load_active_paper_limits(
                self._account_id, record.symbol,
            )
            if order.order_id.value != allowed_limit_order_id
        )
        if foreign_orders:
            return (
                "FOREIGN_WORKING_ORDER_PRESENT_BEFORE_ROBOT_ENTRY "
                f"symbol={record.symbol.value} order_ids={','.join(foreign_orders)}"
            )
        return None

    def _entry_order_id(
        self,
        record: RobotCandidateRecord,
        execution: Mapping[str, object],
        *,
        entry_path: str,
    ) -> OrderId | None:
        if entry_path == "LIMIT":
            raw_order_id = execution.get("limit_order_id")
            if not isinstance(raw_order_id, str) or not raw_order_id.strip():
                return None
            return OrderId(raw_order_id.strip())

        if entry_path != "MARKET":
            raise RobotBreakoutMonitorError(f"unsupported Robot entry path: {entry_path}")
        intent = execution.get("late_market_intent")
        if not isinstance(intent, Mapping):
            return None
        raw_command_id = intent.get("command_id")
        if not isinstance(raw_command_id, str) or not raw_command_id.strip():
            raise RobotBreakoutMonitorError("late Market intent lacks command identity")
        command = self._store().get_command(CommandId(raw_command_id.strip()))
        if command is None or command.exchange_order_id is None:
            return None
        if (
            command.trading_account_id != self._account_id
            or command.symbol != record.symbol
        ):
            raise RobotBreakoutMonitorError(
                "late Market command identity does not match Robot candidate scope"
            )
        return command.exchange_order_id

    def _prove_entry_evidence(
        self,
        record: RobotCandidateRecord,
        execution: Mapping[str, object],
        *,
        entry_path: str,
    ) -> _EntryEvidence | None:
        order_id = self._entry_order_id(record, execution, entry_path=entry_path)
        if order_id is None:
            return None

        fills = self._store().load_executions_for_order(self._account_id, order_id)
        if not fills:
            return None

        direction = str(record.robot_state.get("direction", "")).strip().upper()
        expected_side = (
            OrderSide.BUY
            if direction == robot_state_machine.DIRECTION_LONG
            else OrderSide.SELL
            if direction == robot_state_machine.DIRECTION_SHORT
            else None
        )
        if expected_side is None:
            raise RobotBreakoutMonitorError("Robot entry direction is invalid")
        if any(
            fill.symbol != record.symbol
            or fill.side is not expected_side
            or fill.quantity.value <= 0
            or fill.price.value <= 0
            for fill in fills
        ):
            raise RobotBreakoutMonitorError(
                "durable Robot entry executions do not match candidate scope/direction"
            )

        quantity = sum((fill.quantity.value for fill in fills), Decimal("0"))
        notional = sum(
            (fill.price.value * fill.quantity.value for fill in fills),
            Decimal("0"),
        )
        if quantity <= 0 or notional <= 0:
            raise RobotBreakoutMonitorError("durable Robot entry evidence is empty")
        average_entry = notional / quantity

        position_key = PositionKey(self._account_id, Category.LINEAR, record.symbol, 0)
        position = self._store().get_position_projection(position_key)
        expected_position_side = (
            PositionSide.LONG
            if expected_side is OrderSide.BUY
            else PositionSide.SHORT
        )
        if (
            position is None
            or position.side is not expected_position_side
            or position.quantity.value != quantity
            or position.average_entry is None
            or position.average_entry.value != average_entry
        ):
            raise RobotBreakoutMonitorError(
                "aggregate position does not equal the Robot-owned entry fills"
            )

        ordered = tuple(
            sorted(
                fills,
                key=lambda fill: (
                    fill.exchange_timestamp_ms,
                    fill.dedup_key.exec_id.value,
                ),
            )
        )
        first_at = ordered[0].exchange_timestamp_ms
        symbol_executions = self._store().load_executions_for_symbol(
            self._account_id, record.symbol,
        )
        pre_entry_net = Decimal("0")
        for item in symbol_executions:
            signed = (
                item.quantity.value
                if item.side is OrderSide.BUY
                else -item.quantity.value
            )
            if item.exchange_timestamp_ms < first_at:
                pre_entry_net += signed
                continue
            if item.order_id != order_id:
                raise RobotBreakoutMonitorError(
                    "foreign execution exists after Robot entry began"
                )
        if pre_entry_net != 0:
            raise RobotBreakoutMonitorError(
                "symbol was not FLAT immediately before Robot entry"
            )
        foreign_orders = tuple(
            item.order_id.value
            for item in self._store().load_active_paper_limits(
                self._account_id, record.symbol,
            )
            if item.order_id != order_id
        )
        if foreign_orders:
            raise RobotBreakoutMonitorError(
                "foreign working order exists on Robot-owned symbol"
            )

        return _EntryEvidence(
            order_id=order_id,
            quantity=quantity,
            average_entry=average_entry,
            position_version=position.version,
        )

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

    def _build_initial_retest_limit_plan(
        self, record: RobotCandidateRecord, state: Mapping[str, object],
    ):
        payload = {
            "candidate_id": record.candidate_id,
            "status": record.status,
            "timeframe": "1",
            "signal_snapshot": record.signal_snapshot,
        }
        tick_size = self._tick_size_provider(record.symbol.value)
        return robot_entry_limit.build_initial_retest_limit(
            payload, state, tick_size=tick_size,
        )

    def _entry_rr_skip(
        self, record: RobotCandidateRecord, plan, *,
        direction: str | None = None,
    ) -> tuple[str, dict[str, object]] | None:
        """Planned take/stop ratio for the retest LIMIT, before it is placed.

        Uses the same inputs as ``robot_protection.build_protection_plan`` after
        the fill (structural extreme and frozen prices from the snapshot), with
        the LIMIT price as the entry. Returns ``(reason, details)`` when the
        candidate must be skipped, ``None`` only when RR is computable and
        meets the threshold. Existing filled positions continue through their
        independent post-fill protection and emergency-close lifecycle.
        """
        threshold = robot_protection.min_entry_rr()
        details: dict[str, object] = {
            "entry_price": str(plan.request.limit_price), "min_rr": str(threshold),
        }
        try:
            direction = direction if direction is not None else plan.direction
            structural_extreme = self._structural_extreme(record.signal_snapshot, direction)
            tick_size = self._tick_size_provider(record.symbol.value)
            reference_price, target_price = self._frozen_prices(record.signal_snapshot, direction)
            stop_price = robot_protection.structural_stop(
                direction, average_entry=plan.request.limit_price,
                structural_extreme=structural_extreme, tick_size=tick_size,
            )
            take_price = robot_protection.frozen_take_90(
                direction, frozen_signal_reference_price=reference_price,
                frozen_scanner_target_price=target_price,
            )
            rr = risk_reward_ratio(
                direction, entry_price=plan.request.limit_price,
                stop_price=stop_price, take_price=take_price,
            )
        except Exception as error:
            print(
                "[ROBOT ENTRY RR UNAVAILABLE] "
                f"candidate_id={record.candidate_id} symbol={record.symbol.value} error={error}"
            )
            details["error"] = str(error)
            return ENTRY_RR_SKIP_UNAVAILABLE, details
        details.update(stop_price=str(stop_price), take_price=str(take_price), rr=str(rr))
        if rr <= 0 or rr < threshold:
            print(
                "[ROBOT ENTRY SKIPPED] "
                f"candidate_id={record.candidate_id} symbol={record.symbol.value} "
                f"reason={ENTRY_RR_SKIP_POOR_RR} rr={rr} min_rr={threshold}"
            )
            return ENTRY_RR_SKIP_POOR_RR, details
        return None

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
        details: Mapping[str, object] | None = None,
    ) -> None:
        execution = dict(record.robot_state.get("execution") or {})
        execution["stopped_without_entry_at_ms"] = self._now_ms()
        execution["stopped_without_entry_reason"] = reason
        if details:
            execution["entry_rr_filter"] = dict(details)
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

    def _invalidate_unsupported_pattern(
        self, record: RobotCandidateRecord, error: Exception,
    ) -> None:
        # An APPROVED candidate without robot_state would otherwise fail every
        # tick and block restart reconciliation; it never had an order.
        now_ms = self._now_ms()
        state = {
            "state_version": robot_state_machine.STATE_VERSION,
            "phase": PHASE_INVALIDATED_UNSUPPORTED_PATTERN,
            "pattern": (record.signal_snapshot or {}).get("pattern"),
            "invalidated_reason": str(error),
            "invalidated_at_ms": now_ms,
        }
        try:
            self._store().save_robot_candidate_state(
                record.candidate_id,
                status="INVALIDATED",
                robot_state=state,
                expected_revision=record.state_revision,
                updated_at_ms=now_ms,
            )
        except ConcurrentUpdate:
            return
        print(
            "[ROBOT CANDIDATE INVALIDATED] "
            f"candidate_id={record.candidate_id} reason={error}"
        )

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
