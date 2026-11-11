"""Isolated REAL Robot coordinator bindings for a single virtual account.

This is the *dependency boundary*, not a second trading engine. The original
RobotBreakoutMonitor is reused with (1) a new disposable private SQLite
owned by one SIMULATION run, (2) the verified closed-M1 clock/feed and
(3) a fail-closed action port until the native multi-order virtual exchange
is fully integrated. Never connect PAPER/MAIN credentials, stores or clients.

The original Robot coordinator's persistence has PAPER-only Box guards.
This adapter does NOT bypass/relax them or claim Box is executable today.
"""
from __future__ import annotations

from decimal import Decimal
import hashlib
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace

from research.simulator_v2.session import VirtualReplaySession
from research.simulator_v2.ikigai_observer import IkigaiObservation
from research.simulator_v2.ikigai_plan_preview import BoxSimulationPreview, BoxSimulationRiskTerms
from research.simulator_v2.virtual_account import VirtualFill
from research.simulator_v2.virtual_exchange import (
    LimitRequest, MarketRequest, RobotLimitRequest, RobotStopRequest,
)
from terminal.api.models import (
    CommandResult, CommandResultStatus, PaperLimitMutationResult,
    PaperStopMutationResult,
)
from terminal.application.ikigai_box_plan_persistence import persist_ikigai_box_plan
from terminal.application.robot_breakout_monitor import RobotBreakoutMonitor
from terminal.domain.models import (
    Category, Execution, ExecutionDedupKey, ExecutionId, Notional, OrderId,
    OrderSide, PositionKey, PositionSide, Price, Quantity, Symbol,
    TradingAccountId,
)
from terminal.market_data.models import BookHealth, NormalizedOrderBook, PriceLevel
from terminal.persistence.sqlite_store import PositionProjectionUpdate, SQLiteStore


class SimulationExecutionNotConnected(RuntimeError):
    """Native Robot command cannot be executed until virtual ports are proven."""


class _BlockedExecutionPort:
    """Same native ActionExecutor method names, but NO real or fake mutation."""

    @staticmethod
    def _block(_request):
        raise SimulationExecutionNotConnected(
            "SIMULATION Robot exchange integration is not verified"
        )

    create_limit = _block
    amend_limit = _block
    cancel_limit = _block
    create_stop = _block
    amend_stop = _block
    create_take = _block
    amend_take = _block
    full_close = _block


class IsolatedSimulationRobot:
    """Binds the original coordinator to one run-scoped SIMULATION account.

    No process thread is started and no external path/executor can be injected.
    All SQLite state resides in a freshly created private temporary directory.
    When the context closes, only that owned temporary directory is cleaned.
    """

    def __init__(self, session: VirtualReplaySession, *, tick_size: Decimal):
        if not isinstance(session, VirtualReplaySession):
            raise TypeError("original virtual SIMULATION session required")
        if session.wedge_robot is not None:
            raise ValueError(
                "do not run independent Wedge Robot replay in parallel with native Robot"
            )
        if not isinstance(tick_size, Decimal) or not tick_size.is_finite() or tick_size <= 0:
            raise ValueError("explicit positive SIMULATION tick size required")
        if session.account.simulation_run_id != session.timeline.simulation_run_id:
            raise ValueError("SIMULATION account and timeline identity disagree")
        if session.account.symbol != session.timeline.symbol:
            raise ValueError("SIMULATION symbol identity disagree")

        self.session = session
        self.account_id = TradingAccountId(
            "simulation:" + session.account.simulation_run_id
        )
        self._tick_size = tick_size
        self._closed = False
        self._temporary = TemporaryDirectory(prefix="bybitscanner-simulation-robot-")
        self._store_path = Path(self._temporary.name) / "robot.sqlite3"
        self._store = None
        self._monitor = None
        try:
            self._store = SQLiteStore.open(self._store_path)
            self._store.initialize_robot_runtime_state(self.account_id, updated_at_ms=0)
            # Deliberately STOPPED. No admission, no PAPER executor, no network.
            self._monitor = RobotBreakoutMonitor(
                lambda: SQLiteStore.open(self._store_path),
                self.account_id,
                get_closed_candle=self.closed_m1_for_robot,
                action_executor=_BlockedExecutionPort(),
                tick_size_provider=self._native_tick_size,
                clock_ms=self.virtual_clock_ms,
                arm_entry_coverage=lambda _symbol: False,
                release_entry_coverage=lambda _symbol: None,
                incident_dir=Path(self._temporary.name) / "incidents",
            )
        except Exception:
            if self._monitor is not None:
                self._monitor.close()
            if self._store is not None:
                self._store.close()
            self._temporary.cleanup()
            raise

    def _require_open(self) -> None:
        if self._closed:
            raise RuntimeError("SIMULATION Robot sandbox is closed")

    def _native_tick_size(self, symbol: str) -> Decimal:
        self._require_open()
        if symbol != self.session.account.symbol:
            raise ValueError("cross-symbol SIMULATION Robot request")
        return self._tick_size

    def virtual_clock_ms(self) -> int:
        self._require_open()
        value = self.session.virtual_time_ms
        if value is None:
            raise RuntimeError("SIMULATION has no completed M1")
        return value

    def closed_m1_for_robot(self, symbol: str) -> dict[str, object] | None:
        self._require_open()
        if symbol != self.session.account.symbol:
            raise ValueError("cross-symbol Robot market feed")
        candle = self.session.last_committed_minute
        if candle is None:
            return None
        if candle.end_ms != self.session.virtual_time_ms:
            raise RuntimeError("SIMULATION source clock diverged")
        return {
            "time_ms": candle.end_ms,
            "high": float(candle.high), "low": float(candle.low),
            "close": float(candle.close),
        }

    def tick(self) -> tuple[str, ...]:
        """Advance only the actual native Robot. No auto-thread or order IO."""
        self._require_open()
        self.virtual_clock_ms()
        return self._monitor.tick()

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        try:
            if self._monitor is not None:
                self._monitor.close()
        finally:
            try:
                if self._store is not None:
                    self._store.close()
            finally:
                self._temporary.cleanup()

    def __enter__(self):
        self._require_open()
        return self

    def __exit__(self, _type, _value, _tb):
        self.close()


class _SimulationActionExecutor:
    """Native Robot command port backed only by the run-private SQLite ledger."""

    def __init__(self, owner: "ConnectedSimulationRobot") -> None:
        self.owner = owner

    def create_limit(self, _request):
        raise SimulationExecutionNotConnected("non-Box LIMIT is outside this Box adapter")

    amend_limit = create_limit

    def cancel_limit(self, request):
        order, changed = self.owner._store.cancel_paper_limit(
            client_action_id=request.client_action_id.value,
            request_fingerprint=hashlib.sha256(
                f"simulation-cancel\0{request.order_id}".encode()
            ).hexdigest(),
            order_id=OrderId(request.order_id),
            trading_account_id=self.owner.account_id,
            updated_at_ms=self.owner.virtual_clock_ms(),
        )
        return PaperLimitMutationResult(
            request.client_action_id.value, CommandResultStatus.COMPLETED,
            "cancelled" if changed else "already_absent", order.order_id.value,
        )

    def _protection(self, leg: str, operation: str, request):
        key = PositionKey(
            self.owner.account_id, Category.LINEAR,
            Symbol(self.owner.session.account.symbol), 0,
        )
        self.owner._store.mutate_paper_protection_leg(
            client_action_id=request.client_action_id.value,
            request_fingerprint=hashlib.sha256(
                f"simulation-{leg}-{operation}\0{request.trigger_price}".encode()
            ).hexdigest(),
            operation=operation, position_key=key, leg=leg,
            trigger=request.trigger_price,
            updated_at_ms=self.owner.virtual_clock_ms(),
        )
        return PaperStopMutationResult(
            request.client_action_id.value, CommandResultStatus.COMPLETED,
            "created" if operation == "create" else "amended",
        )

    def create_stop(self, request):
        return self._protection("stop", "create", request)

    def amend_stop(self, request):
        return self._protection("stop", "amend", request)

    def create_take(self, request):
        return self._protection("take", "create", request)

    def amend_take(self, request):
        return self._protection("take", "amend", request)

    def full_close(self, _request):
        raise SimulationExecutionNotConnected(
            "native fail-closed emergency close is not a historical fill"
        )


class ConnectedSimulationRobot:
    """Actual Box Robot coordinator on one private ledger and one exchange.

    This adapter owns no Box prices, sizing, STOP/TAKE policy or lifecycle
    transitions.  It translates the coordinator's durable orders to the
    shared ``VirtualExchange`` and translates its receipts back to the same
    coordinator ledger.
    """

    def __init__(
        self, session: VirtualReplaySession, *, tick_size: Decimal,
        terms: BoxSimulationRiskTerms,
    ) -> None:
        if not isinstance(session, VirtualReplaySession) or session.ikigai_scanner is None:
            raise TypeError("native Ikigai Scanner SIMULATION session required")
        if not isinstance(terms, BoxSimulationRiskTerms) or terms.tick_size != tick_size:
            raise ValueError("one explicit Box SIMULATION instrument profile required")
        self.session = session
        self.terms = terms
        self.account_id = TradingAccountId("simulation:" + session.account.simulation_run_id)
        self._tick_size = tick_size
        self._closed = False
        self._source_candidate_id: str | None = None
        self._source_candidate_ids: list[str] = []
        self._completed_market_ids: set[str] = set()
        self._temporary = TemporaryDirectory(prefix="bybitscanner-simulation-box-")
        self._store_path = Path(self._temporary.name) / "simulation.sqlite3"
        self._store = SQLiteStore.open(
            self._store_path, allow_simulation_box_accounts=True,
        )
        runtime = self._store.initialize_robot_runtime_state(
            self.account_id, updated_at_ms=0,
        )
        self._store.update_robot_runtime_state(
            self.account_id, mode="ROBOT_RUNNING", recovery_status="READY",
            reason=None, expected_version=runtime.version, updated_at_ms=0,
        )
        self._executor = _SimulationActionExecutor(self)
        self._monitor = RobotBreakoutMonitor(
            lambda: SQLiteStore.open(
                self._store_path, allow_simulation_box_accounts=True,
            ), self.account_id,
            get_closed_candle=self.closed_m1_for_robot,
            action_executor=self._executor,
            tick_size_provider=lambda symbol: self._tick_size_for(symbol),
            clock_ms=self.virtual_clock_ms,
            get_market_book=self.market_book,
            market_preflight=self.market_preflight,
            submit_market=self.submit_market,
            arm_entry_coverage=lambda symbol: symbol == self.session.account.symbol,
            release_entry_coverage=lambda _symbol: None,
            incident_dir=Path(self._temporary.name) / "incidents",
        )

    def _require_open(self) -> None:
        if self._closed:
            raise RuntimeError("SIMULATION Robot adapter is closed")

    @property
    def can_admit(self) -> bool:
        """Whether the native one-symbol owner has completed its campaign."""
        self._require_open()
        if self._source_candidate_id is None:
            return True
        symbol = Symbol(self.session.account.symbol)
        if self._store.get_open_robot_trade_for_symbol(self.account_id, symbol) is not None:
            return False
        snapshot = self.session.account.snapshot(
            as_of_ms=self.virtual_clock_ms(), mark_price=self.session.last_committed_minute.close,
        )
        return (
            snapshot.position_quantity == 0
            and not self.session.exchange.robot_limits
            and not self.session.exchange.robot_markets
            and self.session.exchange.robot_stop is None
        )

    def ownership_roles(self) -> dict[str, str]:
        """All durable order roles across sequential campaigns in this run."""
        roles: dict[str, str] = {}
        for candidate_id in self._source_candidate_ids:
            roles.update({
                item.order_id.value: item.role
                for item in self._store.load_box_order_ownership(candidate_id)
            })
        return roles

    def virtual_clock_ms(self) -> int:
        self._require_open()
        if self.session.virtual_time_ms is None:
            raise RuntimeError("SIMULATION has no completed M1")
        return self.session.virtual_time_ms

    def _tick_size_for(self, symbol: str) -> Decimal:
        if symbol != self.session.account.symbol:
            raise ValueError("cross-symbol SIMULATION Robot request")
        return self._tick_size

    def closed_m1_for_robot(self, symbol: str):
        self._tick_size_for(symbol)
        candle = self.session.last_committed_minute
        if candle is None:
            return None
        return {
            "time_ms": candle.end_ms, "high": float(candle.high),
            "low": float(candle.low), "close": float(candle.close),
        }

    def market_book(self, symbol: str) -> NormalizedOrderBook | None:
        self._tick_size_for(symbol)
        candle = self.session.last_committed_minute
        if candle is None:
            return None
        quantity = Quantity(Decimal("1000000000000"))
        price = Price(candle.close)
        return NormalizedOrderBook(
            symbol=Symbol(symbol), bids=(PriceLevel(price, quantity),),
            asks=(PriceLevel(price, quantity),), health=BookHealth.READY,
            received_at_ms=candle.end_ms, available_depth=1,
        )

    @staticmethod
    def market_preflight(request, _identity):
        return SimpleNamespace(
            admitted=True,
            normalized_quantity=request.volume.amount / request.sizing_reference_price,
        )

    def _market_order_id(self, command_id: str) -> str:
        for candidate in self._store.load_robot_candidates_by_status(
            self.account_id, ("APPROVED", "OPEN"),
        ):
            catchup = (candidate.robot_state or {}).get("execution", {}).get("box_catchup", {})
            for item in catchup.get("market_intents", ()):
                if item.get("command_id") == command_id:
                    return str(item["order_id"])
        raise RuntimeError("native Box MARKET identity is unavailable")

    def submit_market(self, request, identity):
        order_id = self._market_order_id(identity.command_id.value)
        if order_id in self._completed_market_ids:
            return CommandResult(
                request.client_action_id.value, CommandResultStatus.COMPLETED,
                "completed", "historical next-open fill committed",
            )
        quantity = request.volume.amount / request.sizing_reference_price
        self.session.exchange.submit_robot_market(
            MarketRequest(order_id, request.side.value, quantity),
            submitted_at_ms=self.virtual_clock_ms(),
        )
        return CommandResult(
            request.client_action_id.value, CommandResultStatus.ACCEPTED_PENDING,
            "accepted_pending", "awaiting next closed historical M1",
        )

    def admit(self, observation: IkigaiObservation) -> BoxSimulationPreview:
        self._require_open()
        if not self.can_admit:
            raise ValueError("native symbol owner already has an active Box campaign")
        preview = self.session.preview_ikigai_grid(observation, self.terms)
        formation = observation.formation
        source, _ = persist_ikigai_box_plan(
            self._store, preview.plan, planner_version="SIMULATOR_NATIVE_REUSE_V1",
            identity={
                "venue": "bybit", "market": "linear",
                "symbol": observation.symbol,
                "timeframe": observation.timeframe.removesuffix("m"),
                "direction": formation.direction,
                "a_time_ms": observation.source_a_ms,
                "b_time_ms": observation.source_b_ms,
            },
            decision_time_ms=observation.available_at_ms,
            anchor_a_price=Decimal(str(formation.anchor_start_price)),
            anchor_b_price=Decimal(str(formation.anchor_end_price)),
            frozen_f2618=Decimal(str(formation.fibonacci_2_618)),
            working_quantity=self.terms.working_quantity,
            tick_size=self.terms.tick_size,
            entry_fee_rate=self.terms.entry_fee_rate,
            target_fee_rate=self.terms.exit_fee_rate,
            stop_fee_rate=self.terms.exit_fee_rate,
            structural_stop=None, created_at_ms=observation.available_at_ms,
            trading_account_id=self.account_id,
        )
        self._source_candidate_id = source.candidate_id
        if source.candidate_id not in self._source_candidate_ids:
            self._source_candidate_ids.append(source.candidate_id)
        self._store.handoff_box_plan_to_robot_for_account(
            source.candidate_id, trading_account_id=self.account_id,
            symbol=source.symbol, expected_snapshot_sha256=source.snapshot_sha256,
            approved_at_ms=observation.available_at_ms,
        )
        self._drive_robot()
        self._synchronize_exchange()
        return preview

    def _drive_robot(self) -> None:
        def fingerprint():
            candidates = self._store.load_robot_candidates(self.account_id)
            limits = self._store.load_active_paper_limits(
                self.account_id, Symbol(self.session.account.symbol),
            )
            key = PositionKey(
                self.account_id, Category.LINEAR,
                Symbol(self.session.account.symbol), 0,
            )
            position = self._store.get_position_projection(key)
            protection = self._store.get_protection_projection(key)
            return (
                tuple((item.candidate_id, item.status, item.state_revision)
                      for item in candidates),
                tuple((item.order_id.value, item.status, item.filled_quantity)
                      for item in limits),
                position.version if position else None,
                protection.version if protection else None,
                len(self.session.exchange.events),
            )
        for _ in range(16):
            before = fingerprint()
            advanced = self._monitor.tick()
            if not advanced or fingerprint() == before:
                return
        raise RuntimeError("native Robot did not settle within bounded tick budget")

    def _apply_fill(
        self, fill: VirtualFill, order_id: str, *, execution_id: ExecutionId | None = None,
    ) -> None:
        key = PositionKey(
            self.account_id, Category.LINEAR, Symbol(fill.symbol), 0,
        )
        current = self._store.get_position_projection(key)
        prior_signed = Decimal(0)
        prior_average = None
        realized = accumulated_fee = Decimal(0)
        expected_version = None
        if current is not None:
            prior_signed = current.quantity.value * (
                Decimal(1) if current.side is PositionSide.LONG
                else Decimal(-1) if current.side is PositionSide.SHORT else Decimal(0)
            )
            prior_average = current.average_entry.value if current.average_entry else None
            realized = current.realized_pnl
            accumulated_fee = current.accumulated_fee
            expected_version = current.version
        signed = fill.quantity if fill.side == "BUY" else -fill.quantity
        if not prior_signed or prior_signed * signed > 0:
            next_signed = prior_signed + signed
            average = (
                (prior_average or Decimal(0)) * abs(prior_signed)
                + fill.price * fill.quantity
            ) / abs(next_signed)
        else:
            if fill.quantity > abs(prior_signed):
                raise ValueError("native Robot receipt would reverse SIMULATION position")
            direction = Decimal(1) if prior_signed > 0 else Decimal(-1)
            realized += (fill.price - prior_average) * fill.quantity * direction
            next_signed = prior_signed + signed
            average = prior_average if next_signed else None
        accumulated_fee += fill.fee
        side = (
            PositionSide.LONG if next_signed > 0 else
            PositionSide.SHORT if next_signed < 0 else PositionSide.FLAT
        )
        execution = Execution(
            ExecutionDedupKey(
                self.account_id, Category.LINEAR,
                execution_id or ExecutionId(
                    "simulation-" + hashlib.sha256(fill.fill_id.encode()).hexdigest()
                ),
            ),
            OrderId(order_id), Symbol(fill.symbol),
            OrderSide.BUY if fill.side == "BUY" else OrderSide.SELL,
            Price(fill.price), Quantity(fill.quantity), fill.fee,
            fill.virtual_time_ms,
        )
        projection = PositionProjectionUpdate(
            key, side, Quantity(abs(next_signed)),
            Price(average) if average is not None else None,
            realized, accumulated_fee,
            Notional(abs(next_signed) * (average or Decimal(0))),
            "synced", expected_version, fill.virtual_time_ms,
        )
        limit = self._store.get_paper_limit(order_id, self.account_id)
        if limit is None:
            self._store.apply_execution_once(execution, projection)
            self._completed_market_ids.add(order_id)
        else:
            self._store.apply_paper_limit_execution_once(
                OrderId(order_id), execution, projection,
                updated_at_ms=fill.virtual_time_ms,
            )

    def _apply_stop_fill(self, fill: VirtualFill) -> None:
        """Use the production Box protection finalizer on virtual evidence."""
        from terminal.runtime.paper_runtime import PaperRuntime

        symbol = Symbol(self.session.account.symbol)
        trade = self._store.get_open_robot_trade_for_symbol(self.account_id, symbol)
        key = PositionKey(self.account_id, Category.LINEAR, symbol, 0)
        protection = self._store.get_protection_projection(key)
        position = self._store.get_position_projection(key)
        if (trade is None or protection is None or protection.stop_loss is None
                or position is None or position.side is PositionSide.FLAT
                or self._source_candidate_id is None):
            raise SimulationExecutionNotConnected(
                "native Robot STOP lacks durable trade/protection ownership"
            )
        minute = self.session.last_committed_minute
        if minute is None:
            raise SimulationExecutionNotConnected("STOP lacks closed historical M1")
        sequence = minute.end_ms // 60_000
        obligation, _ = self._store.latch_paper_protection_obligation(
            trade_id=trade.trade_id, protection_version=protection.version,
            winning_leg="STOP", trigger_price=protection.stop_loss,
            observed_exit_price=fill.price, observed_quantity=fill.quantity,
            market_event_id=(
                f"simulation:{self.session.account.simulation_run_id}:{minute.end_ms}"
            ),
            source_received_at_ms=minute.end_ms,
            source_generation=0, source_sequence=sequence,
            source_update_id=sequence, source_event_at_ms=minute.end_ms,
            source_matching_engine_cts_ms=None,
            observed_bid_price=fill.price, observed_ask_price=fill.price,
            latched_at_ms=minute.end_ms,
        )
        self._store.reserve_box_order_identity(
            self._source_candidate_id, order_id=obligation.order_id,
            role="EXIT", slot=0,
        )
        for owner in self._store.load_box_order_ownership(self._source_candidate_id):
            if owner.order_id == obligation.order_id:
                continue
            limit = self._store.get_paper_limit(owner.order_id.value, self.account_id)
            if limit is None or limit.status in {"filled", "cancelled"}:
                continue
            digest = hashlib.sha256(
                f"{self._source_candidate_id}\0simulation-stop-cancel\0{owner.order_id.value}".encode()
            ).hexdigest()[:32]
            self._store.cancel_paper_limit(
                client_action_id=f"box-close-cancel-{digest}",
                request_fingerprint=hashlib.sha256(
                    f"{symbol.value}\0{owner.order_id.value}".encode()
                ).hexdigest(),
                order_id=owner.order_id, trading_account_id=self.account_id,
                updated_at_ms=minute.end_ms,
            )
        obligation = self._store.transition_paper_protection_obligation(
            obligation.obligation_id, expected_status="TRIGGERED",
            next_status="DISPATCHING", expected_version=obligation.version,
            updated_at_ms=minute.end_ms,
        )
        self._apply_fill(
            fill, obligation.order_id.value, execution_id=obligation.exec_id,
        )
        execution = self._store.get_execution(ExecutionDedupKey(
            self.account_id, Category.LINEAR, obligation.exec_id,
        ))
        if execution is None:
            raise SimulationExecutionNotConnected("virtual STOP execution was not durable")
        # The finalizer is the same production evidence gate used by PAPER;
        # only its store dependency is needed for the Box branch.
        PaperRuntime._finalize_paper_protection_obligation(
            SimpleNamespace(store=self._store), obligation, trade, execution,
            now_ms=minute.end_ms,
        )

    def after_committed_minute(self) -> None:
        """Return this minute's exchange receipts to the native Robot once."""
        self._require_open()
        fills = self.session.exchange.last_minute_fills
        events = self.session.exchange.last_minute_order_events
        if len(fills) != len(events):
            raise RuntimeError("SIMULATION exchange receipt mismatch")
        if fills:
            for fill, event in zip(fills, events):
                if event.kind == "STOP_FILLED":
                    self._apply_stop_fill(fill)
                else:
                    self._apply_fill(fill, event.order_id)
            if not any(event.kind == "STOP_FILLED" for event in events):
                self._monitor.process_authoritative_fill(self.session.account.symbol)
        self._drive_robot()
        self._synchronize_exchange()

    def _synchronize_exchange(self) -> None:
        if self._source_candidate_id is None:
            return
        ownership = self._store.load_box_order_ownership(self._source_candidate_id)
        roles = {item.order_id.value: item.role for item in ownership}
        active = self._store.load_active_paper_limits(
            self.account_id, Symbol(self.session.account.symbol),
        )
        requests = tuple(RobotLimitRequest(
            LimitRequest(
                order.order_id.value, order.side.name,
                order.quantity - order.filled_quantity, order.price,
            ),
            reduce_only=roles.get(order.order_id.value) == "EXIT",
        ) for order in active)
        self.session.exchange.synchronize_robot_limits(
            requests, synchronized_at_ms=self.virtual_clock_ms(),
        )
        key = PositionKey(
            self.account_id, Category.LINEAR,
            Symbol(self.session.account.symbol), 0,
        )
        projection = self._store.get_position_projection(key)
        protection = self._store.get_protection_projection(key)
        stop = None
        if (projection is not None and projection.side is not PositionSide.FLAT
                and protection is not None and protection.stop_loss is not None):
            digest = hashlib.sha256(self._source_candidate_id.encode()).hexdigest()[:32]
            stop = RobotStopRequest(
                "boxstop_" + digest, projection.side.name, protection.stop_loss,
            )
        self.session.exchange.synchronize_robot_stop(
            stop, synchronized_at_ms=self.virtual_clock_ms(),
        )

    def close(self) -> None:
        if self._closed:
            return
        self._monitor.close()
        self._store.close()
        self._temporary.cleanup()
        self._closed = True

    def __enter__(self):
        self._require_open()
        return self

    def __exit__(self, _type, _value, _tb):
        self.close()
