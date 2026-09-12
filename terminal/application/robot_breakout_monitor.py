"""Durable Robot v0.1 breakout/retest lifecycle monitor over APPROVED candidates.

Mode-agnostic coordinator, structurally mirroring
``terminal.application.robot_recovery.RobotRecoveryCoordinator``: it accepts a
``SQLiteStore``, a ``trading_account_id`` and dependency-injected functions
rather than a concrete PaperRuntime, so a future live implementation can
reuse it with live-bound dependencies instead of a duplicated cycle. It never
refits geometry and never invents entry/pattern/protection strategy: it only
calls the existing public functions of robot_state_machine.py,
robot_entry_limit.py, robot_partial_fill.py, robot_market_confirmation.py and
robot_protection.py, in the order CR-ROBOT-BREAKOUT-MONITOR-001 approved,
driving each APPROVED candidate all the way to ``create_robot_trade``.
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

_INACTIVE_LIMIT_STATUSES = {"filled", "cancelled"}


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


class RobotBreakoutMonitor:
    """Advance durable APPROVED Robot candidates through breakout/retest on each closed 1m candle."""

    def __init__(
        self,
        store: SQLiteStore,
        trading_account_id: TradingAccountId,
        *,
        get_closed_candle: Callable[[str], Mapping[str, object] | None],
        action_executor: ActionExecutor,
        tick_size_provider: Callable[[str], Decimal],
        clock_ms: Callable[[], int],
        tick_interval_s: float = DEFAULT_TICK_INTERVAL_S,
    ) -> None:
        self._store = store
        self._account_id = trading_account_id
        self._get_closed_candle = get_closed_candle
        self._action_executor = action_executor
        self._tick_size_provider = tick_size_provider
        self._clock_ms = clock_ms
        self._tick_interval_s = tick_interval_s
        self._stop = threading.Event()
        self._thread = threading.Thread(
            target=self._run, name="robot-breakout-monitor", daemon=True,
        )
        self._started = False

    def start(self) -> None:
        if self._started:
            return
        self._started = True
        self._thread.start()

    def close(self) -> None:
        self._stop.set()
        if self._started and self._thread is not threading.current_thread():
            self._thread.join(timeout=5)

    def _run(self) -> None:
        # Wait a full interval BEFORE the first tick (never tick immediately on
        # start): a short-lived caller that starts and closes this monitor well
        # within one interval -- as every existing PaperRuntime-constructing
        # test does -- never reaches a real get_closed_candle call.
        while not self._stop.wait(self._tick_interval_s):
            try:
                self.tick()
            except Exception as error:
                print(
                    "[ROBOT BREAKOUT MONITOR LOOP ERROR] "
                    f"error={error}"
                )

    def tick(self) -> tuple[str, ...]:
        """Advance every durable APPROVED candidate by at most one step.

        Returns the ids of candidates whose durable state actually changed.
        One candidate's failure never blocks the others.
        """

        advanced: list[str] = []
        for record in self._store.load_robot_candidates(self._account_id):
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
                continue
        return tuple(advanced)

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
            result = self._submit_initial_retest_limit(record, record.robot_state)
            order_id = getattr(result, "order_id", None)
            if not order_id:
                return False
            execution["limit_order_id"] = order_id
            self._persist_execution(record, execution)
            return True

        order = self._store.get_paper_limit(execution["limit_order_id"], self._account_id)
        if order is None or order.quantity <= 0:
            return False

        filled_fraction = min(order.filled_quantity / order.quantity, Decimal("1"))
        inactive = order.status in _INACTIVE_LIMIT_STATUSES

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

        if filled_fraction <= 0:
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
            refreshed = self._store.get_paper_limit(execution["limit_order_id"], self._account_id)
            if refreshed is not None:
                order = refreshed
                filled_fraction = min(order.filled_quantity / order.quantity, Decimal("1"))
                inactive = order.status in _INACTIVE_LIMIT_STATUSES

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
        self._finalize_trade(
            record, execution, entry_path="MIXED",
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
        robot_protection.submit_initial_protection(self._action_executor, plan)

        now_ms = self._now_ms()
        self._store.create_robot_trade(
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
            created_at_ms=now_ms,
        )

    def _average_entry(self, symbol: Symbol) -> Decimal | None:
        key = PositionKey(self._account_id, Category.LINEAR, symbol, 0)
        projection = self._store.get_position_projection(key)
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
            self._store.save_robot_candidate_state(
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
