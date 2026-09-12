"""Durable Robot v0.1 breakout/retest lifecycle monitor over APPROVED candidates.

Mode-agnostic coordinator, structurally mirroring
``terminal.application.robot_recovery.RobotRecoveryCoordinator``: it accepts a
``SQLiteStore``, a ``trading_account_id`` and dependency-injected functions
rather than a concrete PaperRuntime, so a future live implementation can
reuse it with live-bound dependencies instead of a duplicated cycle. It never
refits geometry, never invents entry/pattern strategy, and only advances the
existing ``robot_state_machine`` lifecycle and submits the existing
``robot_entry_limit`` initial retest LIMIT -- it does not implement partial
fill top-up, Market confirmation, protection or ``create_robot_trade``.
"""

from __future__ import annotations

import threading
from decimal import Decimal
from typing import Callable, Mapping

import robot_entry_limit
import robot_state_machine
from scanner_geometry_cursor import ScannerGeometryCursorError, project_latest_geometry_index
from terminal.domain.models import TradingAccountId
from terminal.persistence.sqlite_store import (
    ConcurrentUpdate,
    RobotCandidateRecord,
    SQLiteStore,
)

DEFAULT_TICK_INTERVAL_S = 60.0


class RobotBreakoutMonitorError(RuntimeError):
    """Raised when the breakout/retest monitor cannot safely advance a candidate."""


class RobotBreakoutMonitor:
    """Advance durable APPROVED Robot candidates through breakout/retest on each closed 1m candle."""

    def __init__(
        self,
        store: SQLiteStore,
        trading_account_id: TradingAccountId,
        *,
        get_closed_candle: Callable[[str], Mapping[str, object] | None],
        limit_submitter: robot_entry_limit.PaperLimitSubmitter,
        tick_size_provider: Callable[[str], Decimal],
        clock_ms: Callable[[], int],
        tick_interval_s: float = DEFAULT_TICK_INTERVAL_S,
    ) -> None:
        self._store = store
        self._account_id = trading_account_id
        self._get_closed_candle = get_closed_candle
        self._limit_submitter = limit_submitter
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
            except Exception:
                pass

    def tick(self) -> tuple[str, ...]:
        """Advance every durable APPROVED candidate by at most one closed candle.

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
            except Exception:
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
            # No new candle is needed to retry: idempotently (re)submitted every
            # tick while RETEST_DETECTED holds, including after a previous
            # submission attempt failed. robot_entry_limit's client_action_id is
            # deterministic per (candidate_id, retest_index) and create_limit()
            # dedupes on it, so a repeat submission is always safe.
            self._submit_initial_retest_limit(record, record.robot_state)
            return False
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
        if new_state.get("phase") == robot_state_machine.PHASE_RETEST_DETECTED:
            self._submit_initial_retest_limit(record, new_state)
        return True

    def _submit_initial_retest_limit(
        self, record: RobotCandidateRecord, state: Mapping[str, object],
    ) -> None:
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
        robot_entry_limit.submit_initial_retest_limit(self._limit_submitter, plan)

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
