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
    RobotTakeRequest,
)
from terminal.api.models import (
    CommandResult, CommandResultStatus, PaperLimitMutationResult,
    PaperStopMutationResult,
)
from mirror_retest_robot import (
    ATTACHED, SCANNER_SOURCE, STRATEGY_ID, PAPER_FEE_RATE,
    STOP_SLIPPAGE_FRACTION, MirrorRobotPolicy, mirror_record,
)
from research.simulator_v2.mirror_candles import LocalMirrorClosedCandles
from research.simulator_v2.mirror_auto_scanner import LocalMirrorAutoScanner
import mirror_scanner
import robot_l_shape
from terminal.application.ikigai_box_plan_persistence import persist_ikigai_box_plan
from terminal.application.box_protection_finalizer import finalize_box_protection_obligation
from terminal.application.non_box_protection_finalizer import (
    finalize_non_box_protection_obligation,
)
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

    def create_limit(self, request):
        """Persist only the shared Robot's *attached* MIRROR 1-WV entry.

        Box still uses its native atomic grid path. This is the other native
        LIMIT port, not a strategy engine or a shortcut into PAPER execution.
        The original Robot must first freeze and attach the MIRROR campaign.
        """
        self.owner._require_open()
        source_id = self.owner._source_candidate_id
        record = (self.owner._store.get_robot_candidate(source_id)
                  if source_id is not None else None)
        if (record is None or record.trading_account_id != self.owner.account_id
                or record.symbol.value != self.owner.session.account.symbol
                or record.status != "APPROVED" or record.robot_state is None
                or not robot_l_shape.is_mirror_snapshot(record.signal_snapshot)):
            raise SimulationExecutionNotConnected(
                "native MIRROR LIMIT lacks a run-owned approved candidate"
            )
        execution = record.robot_state.get("execution")
        attached = mirror_record(execution)
        frozen = record.signal_snapshot.get("mirror_entry")
        if (not isinstance(attached, dict) or attached.get("decision") != ATTACHED
                or attached.get("mode") != "STANDALONE"
                or attached.get("strategy_id") != STRATEGY_ID
                or attached.get("source") != SCANNER_SOURCE
                or not isinstance(frozen, dict)
                or attached.get("mirror_level_id") != frozen.get("level_id")):
            raise SimulationExecutionNotConnected(
                "native MIRROR campaign attachment is not proven"
            )
        native_request = robot_l_shape.build_initial_retest_limit(
            {"candidate_id": record.candidate_id, "status": record.status,
             "signal_snapshot": record.signal_snapshot},
            record.robot_state, tick_size=self.owner._tick_size,
        ).request
        if request != native_request:
            raise SimulationExecutionNotConnected(
                "MIRROR LIMIT does not match the original Robot plan"
            )
        # The native policy has already frozen the 1-WV USDT amount and its
        # R0 decision. Apply the one instrument step from the local profile;
        # never silently enlarge a rounded quantity or fall back to a Box size.
        try:
            notional = Decimal(str(attached["one_wv_usdt"]))
            price = request.limit_price
            step = self.owner.terms.quantity_step
            quantity = (notional / price // step) * step
        except (ValueError, TypeError, KeyError, ArithmeticError) as exc:
            raise SimulationExecutionNotConnected("MIRROR virtual sizing unavailable") from exc
        if (notional <= 0 or not notional.is_finite() or not quantity.is_finite()
                or quantity < self.owner.terms.minimum_quantity
                or quantity * price > self.owner.terms.maximum_notional_usdt):
            raise SimulationExecutionNotConnected("MIRROR virtual size outside instrument limits")
        digest = hashlib.sha256(
            f"{self.owner.account_id.value}\\0{request.client_action_id.value}".encode()
        ).hexdigest()[:32]
        order_id = OrderId("simulation-limit-" + digest)
        fingerprint = hashlib.sha256(
            f"{request.symbol}\\0{request.side.value}\\0{price}\\0{quantity}".encode()
        ).hexdigest()
        order, created = self.owner._store.create_paper_limit(
            client_action_id=request.client_action_id.value,
            request_fingerprint=fingerprint,
            order_id=order_id, order_link_id=order_id.value,
            trading_account_id=self.owner.account_id,
            symbol=Symbol(request.symbol), side=request.side,
            price=price, quantity=quantity,
            created_at_ms=self.owner.virtual_clock_ms(), robot_entry=True,
        )
        return PaperLimitMutationResult(
            request.client_action_id.value, CommandResultStatus.COMPLETED,
            "created" if created else "already_exists", order.order_id.value,
        )

    def amend_limit(self, _request):
        raise SimulationExecutionNotConnected(
            "native non-Box LIMIT amendment has no verified virtual adapter"
        )

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
        mirror_working_volume_usdt: Decimal | None = None,
        mirror_risk_limit_usdt: Decimal | None = None,
        mirror_auto_scan: bool = False,
        mirror_one_filled_trade_per_campaign: bool = False,
        mirror_research_skip_ambiguous: bool = False,
    ) -> None:
        if type(mirror_research_skip_ambiguous) is not bool:
            raise TypeError("research-only ambiguous event gate must be boolean")
        if mirror_research_skip_ambiguous and not mirror_auto_scan:
            raise ValueError("research-only ambiguity filter requires automatic local replay")
        if type(mirror_one_filled_trade_per_campaign) is not bool:
            raise TypeError("experimental MIRROR one-fill gate requires a boolean")
        if mirror_one_filled_trade_per_campaign and not mirror_auto_scan:
            raise ValueError("experimental MIRROR gate requires automatic local replay")
        if type(mirror_auto_scan) is not bool:
            raise TypeError("local MIRROR auto scan requires an explicit boolean")
        enabled_mirror = (
            mirror_working_volume_usdt is not None
            or mirror_risk_limit_usdt is not None
        )
        if not isinstance(session, VirtualReplaySession):
            raise TypeError("original SIMULATION session required")
        if mirror_auto_scan and not enabled_mirror:
            raise ValueError("automatic MIRROR needs a complete isolated risk profile")
        if session.ikigai_scanner is None and not enabled_mirror:
            raise TypeError("native Ikigai Scanner or explicit MIRROR profile required")
        if not isinstance(terms, BoxSimulationRiskTerms) or terms.tick_size != tick_size:
            raise ValueError("one explicit SIMULATION instrument profile required")
        if enabled_mirror:
            if (not isinstance(mirror_working_volume_usdt, Decimal)
                    or not mirror_working_volume_usdt.is_finite()
                    or mirror_working_volume_usdt <= 0
                    or mirror_working_volume_usdt > terms.maximum_notional_usdt
                    or not isinstance(mirror_risk_limit_usdt, Decimal)
                    or not mirror_risk_limit_usdt.is_finite()
                    or mirror_risk_limit_usdt <= 0
                    or mirror_risk_limit_usdt > session.account.initial_balance):
                raise ValueError("explicit bounded local MIRROR WV and risk limit required")
        if session.wedge_robot is not None:
            raise ValueError("duplicate research Wedge Robot cannot own native simulation")
        self.session = session
        self.terms = terms
        self.account_id = TradingAccountId("simulation:" + session.account.simulation_run_id)
        self._tick_size = tick_size
        self._closed = False
        self._source_candidate_id: str | None = None
        self._source_candidate_ids: list[str] = []
        self._mirror_one_fill_experiment = mirror_one_filled_trade_per_campaign
        self._mirror_consumed_campaigns: set[tuple[str, int]] = set()
        self._mirror_experiment_suppressed: list[str] = []
        self._mirror_research_skip_ambiguous = mirror_research_skip_ambiguous
        self._mirror_ambiguous_research_events: list[tuple[int, tuple[str, ...]]] = []
        # Scanner eligibility is many-to-many: one closed reversal may be
        # evidence for every independently authorized MIRROR level. Recording
        # each candidate never confers Robot ownership or order permission.
        self._mirror_confirmation_events: list[tuple[int, tuple[str, ...]]] = []
        self._completed_market_ids: set[str] = set()
        self._temporary = TemporaryDirectory(prefix="bybitscanner-simulation-box-")
        self._store_path = Path(self._temporary.name) / "simulation.sqlite3"
        self._mirror_root = Path(self._temporary.name) / "mirror_levels"
        self._mirror_source = (
            LocalMirrorClosedCandles(session.account.symbol)
            if enabled_mirror else None
        )
        self._mirror_policy = (
            MirrorRobotPolicy(
                candles=self._mirror_source,
                account_risk_limit_usdt=lambda _now: mirror_risk_limit_usdt,
                quantity_step=lambda symbol: self._quantity_step_for(symbol),
                fee_rate=max(PAPER_FEE_RATE, session.exchange.taker_fee_rate,
                             session.exchange.maker_fee_rate),
                stop_slippage_fraction=STOP_SLIPPAGE_FRACTION,
                scanner_root=self._mirror_root,
                one_wv_usdt=lambda: mirror_working_volume_usdt,
            ) if enabled_mirror else None
        )
        self._auto_mirror_scanner = (
            LocalMirrorAutoScanner(self._mirror_source, root=self._mirror_root)
            if mirror_auto_scan else None
        )
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
            mirror_policy=self._mirror_policy,
            mirror_standalone_enabled=(lambda: True) if enabled_mirror else None,
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
        source = self._store.get_robot_candidate(self._source_candidate_id)
        if (source is not None
                and robot_l_shape.is_mirror_snapshot(source.signal_snapshot)
                and source.status in ("APPROVED", "OPEN")):
            return False
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
            and self.session.exchange.robot_take is None
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

    def _quantity_step_for(self, symbol: str) -> Decimal:
        self._tick_size_for(symbol)
        return self.terms.quantity_step

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

    @staticmethod
    def _mirror_campaign_key(frozen: dict) -> tuple[str, int]:
        """Frozen source level + historical breakout, never wall-clock or price."""
        level = frozen.get("level_id")
        breakout = frozen.get("level_breakout_close_ms")
        if not isinstance(level, str) or not level or type(breakout) is not int:
            raise SimulationExecutionNotConnected(
                "MIRROR campaign identity is missing from frozen confirmation"
            )
        return level, breakout

    def _mark_mirror_filled_campaign(self) -> None:
        """Use the native *durable fill/trade*, not a mere submitted signal."""
        if not self._mirror_one_fill_experiment:
            return
        candidate_id = self._source_candidate_id
        if candidate_id is None:
            return
        candidate = self._store.get_robot_candidate(candidate_id)
        if candidate is None or not robot_l_shape.is_mirror_snapshot(candidate.signal_snapshot):
            return
        trade = self._store.get_robot_trade("robot-trade-" + candidate_id)
        if trade is None or trade.entry_quantity is None or trade.entry_quantity <= 0:
            return  # Unfilled signal does not consume the experiment's slot.
        frozen = candidate.signal_snapshot.get("mirror_entry")
        if not isinstance(frozen, dict):
            raise SimulationExecutionNotConnected("filled MIRROR lacks frozen source")
        self._mirror_consumed_campaigns.add(self._mirror_campaign_key(frozen))

    @property
    def mirror_experiment_suppressed(self) -> tuple[str, ...]:
        return tuple(self._mirror_experiment_suppressed)

    @property
    def mirror_ambiguous_research_events(self) -> tuple[tuple[int, tuple[str, ...]], ...]:
        return tuple(self._mirror_ambiguous_research_events)

    @property
    def mirror_confirmation_events(self) -> tuple[tuple[int, tuple[str, ...]], ...]:
        """All independently authorized level confirmations, including collisions."""
        return tuple(self._mirror_confirmation_events)

    def admit_mirror(self, source_state: dict, *, entry_id: str) -> str:
        """Admit one exact native Scanner confirmation to the private Robot.

        The Scanner's original source/reversal gate is reused verbatim.
        The independently replayed *committed* M5 campaign remains mandatory
        for native Robot R0 attachment and LIMIT submission. No PAPER path.
        """
        self._require_open()
        if self._mirror_source is None or self._mirror_policy is None:
            raise SimulationExecutionNotConnected(
                "local MIRROR profile was not explicitly selected"
            )
        if not self.can_admit:
            raise SimulationExecutionNotConnected("existing native Robot owner is active")
        if (not isinstance(source_state, dict)
                or source_state.get("timeframe") != "5"
                or source_state.get("symbol") != self.session.account.symbol
                or not isinstance(entry_id, str)):
            raise ValueError("local MIRROR source identity mismatch")
        entries = [
            x for x in source_state.get("standalone_entries", ())
            if isinstance(x, dict) and x.get("entry_id") == entry_id
        ]
        if len(entries) != 1:
            raise ValueError("exact native MIRROR confirmation is absent or ambiguous")
        snapshot = mirror_scanner.verified_standalone_snapshot(
            self.session.account.symbol, source_state, entries[0],
        )
        if snapshot is None:
            raise ValueError("native MIRROR source or confirmation was revoked")
        if (self._mirror_one_fill_experiment
                and self._mirror_campaign_key(snapshot["mirror_entry"])
                in self._mirror_consumed_campaigns):
            raise SimulationExecutionNotConnected(
                "experimental MIRROR campaign already has an attested entry fill"
            )
        close_ms = snapshot["mirror_entry"]["confirmation"]["close_time_ms"]
        if close_ms != self.virtual_clock_ms():
            raise ValueError("MIRROR admission requires its exact committed close")
        # A bounded feed without the level's original M5 is not a reliable
        # replay. Never manufacture a new active campaign from later candles.
        from mirror_levels.levels import LevelRegistry
        level = LevelRegistry.from_dict(source_state["registry"]).levels[
            snapshot["mirror_entry"]["level_id"]
        ]
        first_cursor = level.confirmed_at_ms - level.confirmed_at_ms % 300_000
        if not self._mirror_source.closed_candles(
            entry_id, self.session.account.symbol, first_cursor,
        ):
            raise ValueError("MIRROR source history is not yet proven")
        digest = hashlib.sha256(
            f"{self.account_id.value}\\0{entry_id}".encode()
        ).hexdigest()[:32]
        candidate_id = "simulation-mirror-" + digest
        if self._store.get_robot_candidate(candidate_id) is not None:
            raise ValueError("duplicate local MIRROR candidate")
        # The local private Scanner state is the same format the native
        # MIRROR policy reads. It never uses the production Scanner state.
        mirror_scanner.save_state(source_state, root=self._mirror_root)
        self._store.create_robot_candidate(
            candidate_id=candidate_id, trading_account_id=self.account_id,
            symbol=Symbol(self.session.account.symbol), status="APPROVED",
            signal_snapshot=snapshot, approved_at_ms=close_ms,
            updated_at_ms=close_ms,
        )
        self._source_candidate_id = candidate_id
        self._source_candidate_ids.append(candidate_id)
        self._drive_robot()
        self._synchronize_exchange()
        return candidate_id

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

    def _apply_protection_fill(self, fill: VirtualFill, winning_leg: str) -> None:
        """Finalize STOP/TAKE through the same durable native Robot proof."""
        if winning_leg not in {"STOP", "TAKE"}:
            raise SimulationExecutionNotConnected("invalid native protective leg")

        symbol = Symbol(self.session.account.symbol)
        trade = self._store.get_open_robot_trade_for_symbol(self.account_id, symbol)
        key = PositionKey(self.account_id, Category.LINEAR, symbol, 0)
        protection = self._store.get_protection_projection(key)
        position = self._store.get_position_projection(key)
        trigger = (
            protection.stop_loss if winning_leg == "STOP"
            else protection.take_profit
        ) if protection is not None else None
        if (trade is None or protection is None or trigger is None
                or position is None or position.side is PositionSide.FLAT
                or self._source_candidate_id is None
                or trade.pattern not in {"IKIGAI_BOX", "MIRROR"}
                or (trade.pattern == "MIRROR" and (
                    trade.candidate_id != self._source_candidate_id
                    or trade.entry_quantity != fill.quantity
                    or position.quantity.value != fill.quantity
                ))):

            raise SimulationExecutionNotConnected(
                "native Robot STOP lacks durable trade/protection ownership"
            )
        minute = self.session.last_committed_minute
        if minute is None:
            raise SimulationExecutionNotConnected("STOP lacks closed historical M1")
        sequence = minute.end_ms // 60_000
        obligation, _ = self._store.latch_paper_protection_obligation(
            trade_id=trade.trade_id, protection_version=protection.version,
            winning_leg=winning_leg, trigger_price=trigger,
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
        if trade.pattern == "IKIGAI_BOX":
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
        if trade.pattern == "IKIGAI_BOX":
            resolved = finalize_box_protection_obligation(
                self._store, obligation, trade, now_ms=minute.end_ms,
            )
        else:
            resolved = finalize_non_box_protection_obligation(
                self._store, obligation, trade, execution,
                now_ms=minute.end_ms, require_entry_fees=True,
            )
            if resolved.status == "RESOLVED":
                self._store.clear_paper_protection_for_flat(key)
        if resolved.status != "RESOLVED":
            raise SimulationExecutionNotConnected(
                "native Robot protection close lacks complete durable economics"
            )

    def after_committed_minute(self) -> None:
        """Return this minute's exchange receipts to the native Robot once."""
        self._require_open()
        if self._mirror_source is not None:
            minute = self.session.last_committed_minute
            if minute is None:
                raise SimulationExecutionNotConnected(
                    "MIRROR source lacks a committed M1"
                )
            self._mirror_source.append_committed(
                minute, committed_time_ms=self.virtual_clock_ms(),
            )
        fills = self.session.exchange.last_minute_fills
        events = self.session.exchange.last_minute_order_events
        if len(fills) != len(events):
            raise RuntimeError("SIMULATION exchange receipt mismatch")
        new_entry_fill = bool(fills) and not any(
            event.kind in {"STOP_FILLED", "TAKE_FILLED"} for event in events
        )
        if fills:
            for fill, event in zip(fills, events):
                if event.kind in {"STOP_FILLED", "TAKE_FILLED"}:
                    self._apply_protection_fill(fill, event.order_type)
                else:
                    self._apply_fill(fill, event.order_id)
            if new_entry_fill:
                self._monitor.process_authoritative_fill(self.session.account.symbol)
        self._drive_robot()
        if new_entry_fill:
            # Native Robot may attest an entry only during this drive.
            self._mark_mirror_filled_campaign()
        self._synchronize_exchange()
        if self._auto_mirror_scanner is not None:
            discovered = self._auto_mirror_scanner.observe_committed(
                now_ms=self.virtual_clock_ms(),
            )
            if discovered:
                # Do not collapse, rank or discard confirmed Scanner evidence
                # merely because multiple levels share one closed candle.
                self._mirror_confirmation_events.append(
                    (self.virtual_clock_ms(), tuple(discovered)),
                )
            if len(discovered) > 1:
                if not self._mirror_research_skip_ambiguous:
                    raise SimulationExecutionNotConnected(
                        "simultaneous native MIRROR confirmations have no proven priority"
                    )
                # Research-only execution deferral (NOT signal rejection):
                # every eligible level remains counted above; none is
                # silently prioritized for a single-owner virtual account.
                # Both compared trading variants defer the exact same group.
                self._mirror_ambiguous_research_events.append(
                    (self.virtual_clock_ms(), tuple(discovered)),
                )
                return
            if discovered and self.can_admit:
                source_state = mirror_scanner.load_state(
                    self.session.account.symbol, "5", self._mirror_root,
                )
                entry_id = discovered[0]
                if self._mirror_one_fill_experiment:
                    entries = source_state.get("standalone_entries") or ()
                    matching = [x for x in entries if x.get("entry_id") == entry_id]
                    if len(matching) != 1 or not isinstance(matching[0].get("terms"), dict):
                        raise SimulationExecutionNotConnected(
                            "experimental MIRROR candidate identity is ambiguous"
                        )
                    campaign = self._mirror_campaign_key(matching[0]["terms"])
                    if campaign in self._mirror_consumed_campaigns:
                        self._mirror_experiment_suppressed.append(entry_id)
                        return
                self.admit_mirror(source_state, entry_id=entry_id)

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
        take = None
        if (projection is not None and projection.side is not PositionSide.FLAT
                and protection is not None and protection.take_profit is not None):
            digest = hashlib.sha256(self._source_candidate_id.encode()).hexdigest()[:32]
            take = RobotTakeRequest(
                "robottake_" + digest, projection.side.name, protection.take_profit,
            )
        self.session.exchange.synchronize_robot_take(
            take, synchronized_at_ms=self.virtual_clock_ms(),
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
