"""Legacy FLAT PAPER rows left ``reconciliation_required`` before 9f64db3.

Until 2026-09-18 every simulator-owned PAPER fill stored its projection as
``reconciliation_required``. A symbol that later returned to a clean FLAT kept
that label, which made ``begin_box_attempt_ownership`` reject it forever.
A Box may use such a row only when the row proves itself clean; nothing is
rewritten. Temporary SQLite only: no runtime, network or real PAPER DB.
"""
from decimal import Decimal as D
from pathlib import Path
import tempfile
import unittest

import tests.test_robot_breakout_monitor as monitor_fixtures
from terminal.application.robot_breakout_monitor import RobotBreakoutMonitor
from terminal.domain.models import (
    Category, Execution, ExecutionDedupKey, ExecutionId, Notional, OrderId, OrderSide,
    PositionKey, PositionSide, Price, Quantity, Symbol, TradingAccountId,
)
from terminal.paper.box_ownership import BoxOwnershipError
from terminal.persistence.sqlite_store import (
    BoxOwnedPaperLimitSpec, PersistenceError, PositionProjectionUpdate, SQLiteStore,
)
from tests.test_box_plan_persistence import snapshot, trade_args

ACCOUNT = TradingAccountId("paper")
SYMBOL = Symbol("BTCUSDT")
KEY = PositionKey(ACCOUNT, Category.LINEAR, SYMBOL, 0)
LEGACY = "reconciliation_required"
GATE = "Box ownership requires reconciled FLAT position and journal"


def plan_snapshot(symbol="BTCUSDT"):
    data = snapshot()
    data["identity"]["symbol"] = symbol
    return data


def seed_round_trip(store, symbol, sync_state, *, key=None, row_updated_at=200, flat=True):
    """Buy then sell the same quantity: the row the legacy PAPER simulator left behind."""
    key = key or PositionKey(ACCOUNT, Category.LINEAR, Symbol(symbol), 0)
    legs = [(OrderSide.BUY, PositionSide.LONG, D("5"), D("90"), 100)]
    if flat:
        legs.append((OrderSide.SELL, PositionSide.FLAT, D("0"), None, row_updated_at))
    for number, (side, position_side, remaining, average, at) in enumerate(legs, start=1):
        current = store.get_position_projection(key)
        execution = Execution(
            ExecutionDedupKey(ACCOUNT, Category.LINEAR, ExecutionId(f"{symbol}-legacy-{number}")),
            OrderId(f"{symbol}-legacy-order-{number}"), Symbol(symbol), side,
            Price(D("90")), Quantity(D("5")), D(0), 100 * number,
        )
        store.apply_execution_once(execution, PositionProjectionUpdate(
            key, position_side, Quantity(remaining), Price(average) if average else None,
            D(0), D(0), Notional(remaining * (average or D(0))), sync_state,
            current.version if current else None, at,
        ))


class LegacyFlatBaselineTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.store = SQLiteStore.open(Path(self.tmp.name) / "paper.sqlite3")
        self.addCleanup(self.store.close)
        self.plan, _ = self.store.save_box_plan_only(snapshot=plan_snapshot(), created_at_ms=3001)

    def baseline(self):
        return self.store._connection.execute(
            "SELECT baseline_position_version, baseline_time_ms, baseline_execution_count "
            "FROM box_attempt_ownership WHERE candidate_id=?", (self.plan.candidate_id,),
        ).fetchone()

    def assertRejected(self):
        with self.assertRaises(PersistenceError) as caught:
            self.store.begin_box_attempt_ownership(self.plan.candidate_id)
        self.assertEqual(str(caught.exception), GATE)
        self.assertIsNone(self.baseline())

    def raw(self, sql, params=()):
        with self.store._transaction():
            self.store._connection.execute(sql, params)

    # --- accepted ---------------------------------------------------------

    def test_provably_clean_legacy_flat_row_is_accepted_without_rewriting_it(self):
        seed_round_trip(self.store, "BTCUSDT", LEGACY)
        before = self.store.get_position_projection(KEY)
        self.assertTrue(self.store.begin_box_attempt_ownership(self.plan.candidate_id))
        self.assertEqual(tuple(self.baseline()), (2, 200, 2))
        self.assertEqual(self.store.get_position_projection(KEY), before)
        self.assertEqual(before.sync_state, LEGACY)

    def test_ordinary_synced_flat_row_is_still_accepted(self):
        seed_round_trip(self.store, "BTCUSDT", "synced")
        self.assertTrue(self.store.begin_box_attempt_ownership(self.plan.candidate_id))
        self.assertEqual(tuple(self.baseline()), (2, 200, 2))

    def test_legacy_baseline_proves_zero_exposure_and_reserves_identities(self):
        seed_round_trip(self.store, "BTCUSDT", LEGACY)
        self.assertTrue(self.store.begin_box_attempt_ownership(self.plan.candidate_id))
        proof = self.store.prove_box_owned_position(self.plan.candidate_id)
        self.assertEqual((proof.entry_quantity, proof.remaining_quantity, proof.position_version),
                         (D(0), D(0), 2))
        self.assertTrue(self.store.reserve_box_order_identity(
            self.plan.candidate_id, order_id=OrderId("entry-1"), role="ENTRY", slot=1))

    def test_legacy_baseline_proves_an_owned_fill_that_rewrites_the_row_as_synced(self):
        seed_round_trip(self.store, "BTCUSDT", LEGACY)
        self.assertTrue(self.store.begin_box_attempt_ownership(self.plan.candidate_id))
        limits = tuple(
            BoxOwnedPaperLimitSpec(
                slot=slot, client_action_id=f"limit-{slot}", request_fingerprint=f"limit-fp-{slot}",
                order_id=OrderId(f"limit-order-{slot}"), order_link_id=f"limit-link-{slot}",
                side=OrderSide.BUY, price=D(price), quantity=D("2"), created_at_ms=5000 + slot,
            )
            for slot, price in ((1, "94.0"), (2, "93.2"), (3, "92.4"), (4, "91.6"))
        )
        self.store.create_box_mixed_entry_ownership(
            self.plan.candidate_id, trading_account_id=ACCOUNT, symbol=SYMBOL,
            market_orders=(), limit_orders=limits,
        )
        current = self.store.get_position_projection(KEY)
        execution = Execution(
            ExecutionDedupKey(ACCOUNT, Category.LINEAR, ExecutionId("owned-fill-1")),
            OrderId("limit-order-1"), SYMBOL, OrderSide.BUY, Price(D("94.0")),
            Quantity(D("2")), D(0), 6000,
        )
        self.store.apply_paper_limit_execution_once(
            OrderId("limit-order-1"), execution,
            PositionProjectionUpdate(
                KEY, PositionSide.LONG, Quantity(D("2")), Price(D("94.0")), D(0), D(0),
                Notional(D("188.0")), "synced", current.version, 6000,
            ),
            updated_at_ms=6000,
        )
        proof = self.store.prove_box_owned_position(self.plan.candidate_id)
        self.assertEqual((proof.entry_by_slot[0], proof.remaining_quantity, proof.position_version),
                         (D("2"), D("2"), 3))

    # --- rejected: the row or the symbol is not provably clean ---------------

    def test_non_flat_legacy_position_is_rejected(self):
        # The CELOUSDT shape: Long, quantity left over, net execution not zero.
        seed_round_trip(self.store, "BTCUSDT", LEGACY, flat=False)
        self.assertRejected()

    def test_flat_row_with_non_zero_journal_net_is_rejected(self):
        seed_round_trip(self.store, "BTCUSDT", LEGACY)
        self.raw("DELETE FROM executions WHERE exec_id=?", ("BTCUSDT-legacy-2",))
        self.assertRejected()

    def test_flat_row_with_an_average_entry_is_rejected(self):
        seed_round_trip(self.store, "BTCUSDT", LEGACY)
        self.raw("UPDATE position_projections SET average_entry='90' WHERE symbol='BTCUSDT'")
        self.assertRejected()

    def test_late_fill_after_the_row_was_last_written_is_rejected(self):
        seed_round_trip(self.store, "BTCUSDT", LEGACY, row_updated_at=150)
        self.assertRejected()

    def test_version_that_does_not_match_the_journal_is_rejected(self):
        seed_round_trip(self.store, "BTCUSDT", LEGACY)
        self.raw("UPDATE position_projections SET version=version+1 WHERE symbol='BTCUSDT'")
        self.assertRejected()

    def test_unknown_sync_state_is_rejected(self):
        seed_round_trip(self.store, "BTCUSDT", "something_else")
        self.assertRejected()

    def test_row_at_time_zero_is_rejected(self):
        seed_round_trip(self.store, "BTCUSDT", LEGACY)
        self.raw("UPDATE position_projections SET updated_at_ms=0 WHERE symbol='BTCUSDT'")
        self.assertRejected()

    def test_in_flight_command_blocks_the_legacy_exception_but_terminal_ones_do_not(self):
        seed_round_trip(self.store, "BTCUSDT", LEGACY)
        insert = (
            "INSERT INTO trading_commands (command_id, order_link_id, trading_account_id, category, "
            "symbol, position_idx, command_kind, side, requested_notional, origin, controller, "
            "current_state, version, created_at_ms, updated_at_ms) "
            "VALUES (?, ?, 'paper', 'linear', 'BTCUSDT', 0, 'create_market', 'Buy', '250', "
            "'terminal_manual', 'manual', ?, 1, 1, 1)"
        )
        for number, state in enumerate((
            "local_intent", "admitted", "submitting", "acknowledged", "open", "partially_filled",
            "cancel_pending", "amended", "unknown", "reconciling",
        )):
            with self.subTest(state=state):
                self.raw(insert, (f"cmd-{number}", f"link-{number}", state))
                self.assertRejected()
                self.raw("DELETE FROM trading_commands WHERE command_id=?", (f"cmd-{number}",))
        for number, state in enumerate(("filled", "cancelled", "rejected", "failed"), start=100):
            self.raw(insert, (f"cmd-{number}", f"link-{number}", state))
        self.assertTrue(self.store.begin_box_attempt_ownership(self.plan.candidate_id))

    def test_working_paper_limit_is_rejected(self):
        seed_round_trip(self.store, "BTCUSDT", LEGACY)
        self.store.create_paper_limit(
            client_action_id="foreign-limit", request_fingerprint="foreign-limit-fp",
            order_id=OrderId("foreign-limit-order"), order_link_id="foreign-limit-link",
            trading_account_id=ACCOUNT, symbol=SYMBOL, side=OrderSide.BUY,
            price=D("80"), quantity=D("1"), created_at_ms=300,
        )
        self.assertRejected()

    def test_protection_projection_is_rejected(self):
        seed_round_trip(self.store, "BTCUSDT", LEGACY)
        self.raw(
            "INSERT INTO protection_projections VALUES "
            "('paper', 'linear', 'BTCUSDT', 0, 'confirmed_active', NULL, '89', NULL, NULL, 1, 1, 1)"
        )
        self.assertRejected()

    def _robot_candidate_and_trade(self, *, open_trade):
        self.store.create_robot_candidate(
            candidate_id="legacy-owner", trading_account_id=ACCOUNT, symbol=SYMBOL,
            status="APPROVED", signal_snapshot={"symbol": "BTCUSDT", "pattern": "Falling Wedge"},
            approved_at_ms=1, updated_at_ms=1,
        )
        self.store.create_robot_trade(**trade_args("legacy-owner"))
        if not open_trade:
            self.store.close_robot_trade(
                "trade-1", exit_time_ms=500, exit_price=D("89.6"), exit_reason="STOP",
                realized_pnl_usdt=D("-1"), realized_pnl_pct=D("-1"), fees_costs_usdt=D("0"),
                updated_at_ms=500,
            )

    def test_open_robot_trade_is_rejected(self):
        seed_round_trip(self.store, "BTCUSDT", LEGACY)
        self._robot_candidate_and_trade(open_trade=True)
        self.assertRejected()

    def test_open_robot_candidate_is_rejected(self):
        seed_round_trip(self.store, "BTCUSDT", LEGACY)
        self.store.create_robot_candidate(
            candidate_id="legacy-open", trading_account_id=ACCOUNT, symbol=SYMBOL,
            status="APPROVED", signal_snapshot={"symbol": "BTCUSDT", "pattern": "Falling Wedge"},
            approved_at_ms=10, updated_at_ms=10,
        )
        self.raw("UPDATE robot_candidates SET status='OPEN' WHERE candidate_id='legacy-open'")
        self.assertRejected()

    def test_unresolved_protection_obligation_is_rejected_even_for_a_closed_trade(self):
        seed_round_trip(self.store, "BTCUSDT", LEGACY)
        self._robot_candidate_and_trade(open_trade=False)
        self.raw(
            "INSERT INTO paper_protection_obligations (obligation_id, trade_id, trading_account_id, "
            "symbol, protection_version, winning_leg, trigger_price, observed_exit_price, "
            "observed_quantity, market_event_id, source_received_at_ms, latched_at_ms, order_id, "
            "exec_id, status, version, updated_at_ms) VALUES ('ob-1', 'trade-1', 'paper', 'BTCUSDT', "
            "1, 'STOP', '89.6', '89.6', '8', 'ev', 1, 2, 'ob-order', 'ob-exec', 'TRIGGERED', 1, 2)"
        )
        self.assertRejected()

    def test_resolved_history_does_not_block(self):
        seed_round_trip(self.store, "BTCUSDT", LEGACY)
        self._robot_candidate_and_trade(open_trade=False)
        self.assertTrue(self.store.begin_box_attempt_ownership(self.plan.candidate_id))

    # --- the proof keeps rejecting any later change ----------------------------

    def _begin_on_legacy(self):
        seed_round_trip(self.store, "BTCUSDT", LEGACY)
        self.assertTrue(self.store.begin_box_attempt_ownership(self.plan.candidate_id))

    def test_proof_rejects_a_foreign_mutation_after_the_legacy_baseline(self):
        self._begin_on_legacy()
        self.raw("UPDATE position_projections SET version=version+1 WHERE symbol='BTCUSDT'")
        with self.assertRaises(BoxOwnershipError):
            self.store.prove_box_owned_position(self.plan.candidate_id)

    def test_proof_rejects_a_foreign_fill_while_the_row_is_still_legacy(self):
        self._begin_on_legacy()
        execution = Execution(
            ExecutionDedupKey(ACCOUNT, Category.LINEAR, ExecutionId("foreign-fill")),
            OrderId("foreign-order"), SYMBOL, OrderSide.BUY, Price(D("90")), Quantity(D("1")), D(0), 900,
        )
        current = self.store.get_position_projection(KEY)
        self.store.apply_execution_once(execution, PositionProjectionUpdate(
            KEY, PositionSide.LONG, Quantity(D("1")), Price(D("90")), D(0), D(0),
            Notional(D("90")), LEGACY, current.version, 900,
        ))
        with self.assertRaises(BoxOwnershipError):
            self.store.prove_box_owned_position(self.plan.candidate_id)

    def test_proof_rejects_a_row_that_stopped_being_flat_while_still_legacy(self):
        self._begin_on_legacy()
        self.raw("UPDATE position_projections SET side='Long', quantity='1', average_entry='90' "
                 "WHERE symbol='BTCUSDT'")
        with self.assertRaises(BoxOwnershipError):
            self.store.prove_box_owned_position(self.plan.candidate_id)


class LegacyFlatBoxMonitorTests(unittest.TestCase):
    """The Box monitor must stop looping on the legacy sync_state error."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db_path = Path(self.tmp.name) / "terminal.db"
        self.store = SQLiteStore.open(self.db_path)
        self.store.initialize_robot_runtime_state(monitor_fixtures.ACCOUNT_ID, updated_at_ms=1)
        self.store.update_robot_runtime_state(
            monitor_fixtures.ACCOUNT_ID, mode="ROBOT_RUNNING", recovery_status="READY",
            reason=None, expected_version=1, updated_at_ms=1,
        )
        self.clock = monitor_fixtures._Clock()
        self.executor = monitor_fixtures._FakeActionExecutor(
            self.store, monitor_fixtures.ACCOUNT_ID, self.clock,
        )
        self.monitor = RobotBreakoutMonitor(
            lambda: SQLiteStore.open(self.db_path),
            monitor_fixtures.ACCOUNT_ID,
            get_closed_candle=monitor_fixtures._ScriptedCandleFeed(),
            action_executor=self.executor,
            tick_size_provider=lambda symbol: D("0.1"),
            clock_ms=self.clock,
            arm_entry_coverage=lambda symbol: True,
            release_entry_coverage=lambda symbol: None,
            incident_dir=Path(self.tmp.name) / "incidents",
        )

    def tearDown(self):
        # The monitor lazily opens its own connection on the test thread; close it
        # before the temp directory is removed or Windows keeps the file locked.
        self.monitor.close()
        self.store.close()
        self.tmp.cleanup()

    def _approved_box(self):
        data = plan_snapshot(monitor_fixtures.SYMBOL)
        source, _ = self.store.save_box_plan_only(snapshot=data, created_at_ms=3001)
        candidate, _ = self.store.handoff_box_plan_to_robot(
            source.candidate_id, symbol=source.symbol,
            expected_snapshot_sha256=source.snapshot_sha256, approved_at_ms=3002,
        )
        return source, candidate

    def _tick(self, times):
        self.clock.value = 4000
        book = monitor_fixtures._ready_book("93.5")
        self.monitor._get_market_book = lambda symbol: book
        for _ in range(times):
            self.monitor.tick()

    def test_legacy_flat_box_is_no_longer_stuck_on_the_sync_state_error(self):
        seed_round_trip(self.store, monitor_fixtures.SYMBOL, LEGACY)
        source, candidate = self._approved_box()
        self._tick(3)
        record = self.store.get_robot_candidate(candidate.candidate_id)
        execution = record.robot_state.get("execution") or {}
        self.assertNotIn("last_execution_error", execution)
        self.assertNotIn("attempt_count", execution)
        baseline = self.store._connection.execute(
            "SELECT baseline_position_version, baseline_execution_count FROM box_attempt_ownership "
            "WHERE candidate_id=?", (source.candidate_id,),
        ).fetchone()
        self.assertEqual(tuple(baseline), (2, 2))
        self.assertEqual(
            self.store.get_position_projection(
                PositionKey(ACCOUNT, Category.LINEAR, Symbol(monitor_fixtures.SYMBOL), 0)
            ).sync_state, LEGACY,
        )

    def test_non_flat_legacy_position_still_blocks_with_the_foreign_position_protection(self):
        seed_round_trip(self.store, monitor_fixtures.SYMBOL, LEGACY, flat=False)
        source, candidate = self._approved_box()
        self._tick(2)
        record = self.store.get_robot_candidate(candidate.candidate_id)
        self.assertEqual(record.status, "INVALIDATED")
        self.assertIn(
            "FOREIGN_POSITION_PRESENT_BEFORE_ROBOT_ENTRY",
            (record.robot_state.get("execution") or {}).get("stopped_without_entry_reason", ""),
        )
        self.assertIsNone(self.store._connection.execute(
            "SELECT 1 FROM box_attempt_ownership WHERE candidate_id=?", (source.candidate_id,),
        ).fetchone())


if __name__ == "__main__":
    unittest.main()
