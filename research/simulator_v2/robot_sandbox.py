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
from pathlib import Path
from tempfile import TemporaryDirectory

from research.simulator_v2.session import VirtualReplaySession
from terminal.application.robot_breakout_monitor import RobotBreakoutMonitor
from terminal.domain.models import TradingAccountId
from terminal.persistence.sqlite_store import SQLiteStore


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
