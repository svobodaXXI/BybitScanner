"""P0-B slice 3: pause/stop pending-entry synchronization never performs kline
I/O on the serialized PAPER owner thread.

Before: robot_synchronize_pending_entries() ran a one-shot RobotBreakoutMonitor
.tick() on the owner. For an APPROVED candidate without durable state, that
tick called load_scanner_catchup_closed_candles() (a Bybit kline request), and
the closed-candle cache fetched in place on a miss -- both on the owner.

After: the HTTP command boundary (SerializedPaperRuntime
.warm_robot_closed_candles) prepares closed candles and admission catch-up
evidence on its own thread; the owner tick only peeks the cache and consumes
prepared evidence. Without evidence the candidate stays uninitialized (no
state, no order, no exposure) exactly as a failed fetch always left it.
"""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path
import tempfile
import threading
import time
import unittest
from unittest.mock import patch

import robot_state_machine
from terminal.domain.models import Symbol, TradingAccountId
from terminal.runtime.closed_candle_cache import CachedClosedCandleProvider
from terminal.runtime.paper_http_server import SerializedPaperRuntime
from terminal.runtime.paper_runtime import PaperRuntime
from tests.test_robot_breakout_monitor_admission_catchup import SYMBOL, _candle, _snapshot
from tests.test_terminal_paper_runtime import StaticBookProvider, _instrument


ACCOUNT = TradingAccountId("paper")
OWNER_THREAD = "paper-runtime-owner"
CATCHUP = (
    _candle(101, high=96, low=94, close=95),
    _candle(102, high=97, low=95, close=96),
)


class _SlowLoaders:
    """Deterministic stand-ins for the Scanner kline loaders (2 s each)."""

    def __init__(self, delay_s: float) -> None:
        self.delay_s = delay_s
        self.calls: list[tuple[str, str]] = []
        self.available = True

    def closed(self, symbol):
        self.calls.append((threading.current_thread().name, "closed"))
        time.sleep(self.delay_s)
        return None  # no newer closed candle: only admission catch-up matters

    def catchup(self, symbol, signal_snapshot):
        self.calls.append((threading.current_thread().name, "catchup"))
        time.sleep(self.delay_s)
        if not self.available:
            raise RuntimeError("kline source unavailable")
        return CATCHUP

    def owner_calls(self):
        return [call for call in self.calls if call[0] == OWNER_THREAD]


class _Fixture:
    def __init__(self, temp: str, *, delay_s: float = 2.0) -> None:
        self.loaders = _SlowLoaders(delay_s)
        # One bound object: the runtime enables catch-up only when the cache's
        # fetch *is* the canonical Scanner closed-candle loader.
        closed = self.loaders.closed
        self._patches = [
            patch("terminal.runtime.paper_runtime.latest_scanner_closed_candle", closed),
            patch(
                "terminal.runtime.paper_runtime.load_scanner_catchup_closed_candles",
                self.loaders.catchup,
            ),
        ]
        for item in self._patches:
            item.start()
        primary = _instrument()
        holder: dict[str, PaperRuntime] = {}

        def factory() -> PaperRuntime:
            holder["owner"] = PaperRuntime(
                Path(temp) / "paper.sqlite3", book_provider=StaticBookProvider(),
                instrument_snapshot=primary,
                instrument_provider=lambda symbol: replace(primary, symbol=symbol),
                robot_closed_candle_provider=CachedClosedCandleProvider(closed),
            )
            return holder["owner"]

        self.serialized = SerializedPaperRuntime(factory)
        assert self.serialized.call(lambda owner: owner.robot_catchup_evidence) is not None
        self.serialized.call(lambda owner: owner.store.create_robot_candidate(
            candidate_id="candidate-1", trading_account_id=ACCOUNT, symbol=Symbol(SYMBOL),
            status="APPROVED", signal_snapshot=_snapshot(), approved_at_ms=1, updated_at_ms=1,
        ))
        self.owner_ms: list[float] = []

    def synchronize(self, *, warm: bool = True):
        """The HTTP pause/stop route: warm off-owner, then one owner call."""
        if warm:
            self.serialized.warm_robot_closed_candles()

        def run(owner):
            started = time.perf_counter()
            try:
                return owner.robot_synchronize_pending_entries()
            finally:
                self.owner_ms.append((time.perf_counter() - started) * 1000)

        return self.serialized.call(run, timeout=30)

    def candidate(self):
        return self.serialized.call(lambda owner: owner.store.get_robot_candidate("candidate-1"))

    def side_effects(self):
        return self.serialized.call(lambda owner: (
            owner.store._connection.execute("SELECT COUNT(*) FROM trading_commands").fetchone()[0],
            owner.store._connection.execute("SELECT COUNT(*) FROM paper_limit_orders").fetchone()[0],
            len(owner.store.load_executions()),
        ))

    def close(self) -> None:
        self.serialized.close()
        for item in self._patches:
            item.stop()


class SynchronizePendingEntriesOwnerKlineTests(unittest.TestCase):
    def test_prepared_evidence_initializes_candidate_with_zero_owner_kline_calls(self):
        with tempfile.TemporaryDirectory() as temp:
            fixture = _Fixture(temp)
            try:
                response = fixture.synchronize()
                self.assertEqual(fixture.loaders.owner_calls(), [])
                self.assertIn(("MainThread", "catchup"), fixture.loaders.calls)
                self.assertLess(fixture.owner_ms[-1], 1000)
                record = fixture.candidate()
                # Same durable result the admission catch-up has always produced.
                self.assertEqual(record.state_revision, 1)
                self.assertEqual(record.robot_state["phase"], robot_state_machine.PHASE_WAITING_BREAKOUT)
                self.assertEqual(record.robot_state["geometry_cursor"], 102)
                self.assertEqual(response.unresolved_candidate_ids, ())
                self.assertEqual(response.still_pending_protection, ())
                self.assertEqual(fixture.side_effects(), (0, 0, 0))
            finally:
                fixture.close()

    def test_repeated_synchronize_is_idempotent(self):
        with tempfile.TemporaryDirectory() as temp:
            fixture = _Fixture(temp, delay_s=0.0)
            try:
                fixture.synchronize()
                first = fixture.candidate()
                fixture.loaders.calls.clear()
                second_response = fixture.synchronize()
                self.assertEqual(fixture.loaders.owner_calls(), [])
                # Durable state exists: no catch-up target, no second replay.
                self.assertNotIn(("MainThread", "catchup"), fixture.loaders.calls)
                self.assertEqual(fixture.candidate(), first)
                self.assertEqual(second_response.unresolved_candidate_ids, ())
                self.assertEqual(fixture.side_effects(), (0, 0, 0))
            finally:
                fixture.close()

    def test_unprepared_evidence_leaves_candidate_uninitialized_and_safe(self):
        with tempfile.TemporaryDirectory() as temp:
            fixture = _Fixture(temp)
            try:
                # Owner work queued without the off-owner warm step.
                response = fixture.synchronize(warm=False)
                self.assertEqual(fixture.loaders.calls, [])
                self.assertLess(fixture.owner_ms[-1], 1000)
                record = fixture.candidate()
                self.assertEqual((record.status, record.robot_state, record.state_revision),
                                 ("APPROVED", None, 0))
                self.assertEqual(response.unresolved_candidate_ids, ())
                self.assertEqual(fixture.side_effects(), (0, 0, 0))

                # A later synchronize with evidence resolves it exactly once.
                fixture.synchronize()
                self.assertEqual(fixture.candidate().state_revision, 1)
                self.assertEqual(fixture.loaders.owner_calls(), [])
            finally:
                fixture.close()

    def test_failed_off_owner_fetch_fabricates_no_initialization(self):
        with tempfile.TemporaryDirectory() as temp:
            fixture = _Fixture(temp, delay_s=0.0)
            fixture.loaders.available = False
            try:
                response = fixture.synchronize()
                self.assertEqual(fixture.loaders.owner_calls(), [])
                record = fixture.candidate()
                self.assertEqual((record.robot_state, record.state_revision), (None, 0))
                self.assertEqual(response.unresolved_candidate_ids, ())
                self.assertEqual(fixture.side_effects(), (0, 0, 0))
            finally:
                fixture.close()


class PreparedCatchupEvidenceTests(unittest.TestCase):
    def test_evidence_is_snapshot_bound_consumed_once_and_expires(self):
        from terminal.runtime.closed_candle_cache import PreparedCatchupEvidence

        now = [0.0]
        fetched = []
        evidence = PreparedCatchupEvidence(
            lambda symbol, snapshot: fetched.append(symbol) or CATCHUP,
            max_age_s=90.0, clock=lambda: now[0],
        )
        snapshot = _snapshot()
        with self.assertRaises(RuntimeError):
            evidence(SYMBOL, snapshot)  # nothing prepared: never fetches
        self.assertEqual(fetched, [])
        evidence.prepare([(SYMBOL, snapshot)])
        with self.assertRaises(RuntimeError):
            evidence(SYMBOL, _snapshot(apex_index=131))  # different snapshot
        self.assertEqual(evidence(SYMBOL, snapshot), CATCHUP)
        with self.assertRaises(RuntimeError):
            evidence(SYMBOL, snapshot)  # consumed once
        evidence.prepare([(SYMBOL, snapshot)])
        now[0] = 91.0
        with self.assertRaises(RuntimeError):
            evidence(SYMBOL, snapshot)  # stale
        self.assertEqual(fetched, [SYMBOL, SYMBOL])


if __name__ == "__main__":
    unittest.main()
