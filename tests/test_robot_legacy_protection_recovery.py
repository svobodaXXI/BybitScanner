import tempfile
import unittest
from dataclasses import replace
from decimal import Decimal
from pathlib import Path

from terminal.domain.models import (
    Category,
    Execution,
    ExecutionDedupKey,
    ExecutionId,
    Notional,
    OrderId,
    OrderSide,
    PositionKey,
    PositionSide,
    Price,
    Quantity,
    Symbol,
    TradingAccountId,
)
from terminal.persistence.legacy_protection_recovery import (
    LEGACY_ATTESTATION_SOURCE,
    LegacyProtectionRecoveryRejected,
    attest_legacy_robot_entry,
    prove_legacy_entry_attestation,
)
from terminal.persistence.sqlite_store import PositionProjectionUpdate, SQLiteStore


ACCOUNT = TradingAccountId("paper")
SYMBOL = Symbol("BTCUSDT")
POSITION_KEY = PositionKey(ACCOUNT, Category.LINEAR, SYMBOL, 0)
ENTRY_ORDER_ID = "legacy-entry-order"
TRADE_ID = "legacy-trade-1"
CANDIDATE_ID = "legacy-candidate-1"
ACTION_ID = "legacy-attest-action-1"


class LegacyProtectionRecoveryTests(unittest.TestCase):
    def setUp(self):
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.database_path = Path(self.temporary_directory.name) / "paper.sqlite3"

    def tearDown(self):
        self.temporary_directory.cleanup()

    def open_store(self):
        return SQLiteStore.open(self.database_path, busy_timeout_ms=2500)

    @staticmethod
    def entry_execution(
        *,
        exec_id: str = "legacy-entry-exec-1",
        order_id: str = ENTRY_ORDER_ID,
        side: OrderSide = OrderSide.BUY,
        price: str = "100",
        quantity: str = "2",
        timestamp_ms: int = 1200,
    ) -> Execution:
        return Execution(
            dedup_key=ExecutionDedupKey(ACCOUNT, Category.LINEAR, ExecutionId(exec_id)),
            order_id=OrderId(order_id),
            symbol=SYMBOL,
            side=side,
            price=Price(Decimal(price)),
            quantity=Quantity(Decimal(quantity)),
            fee=Decimal("0"),
            exchange_timestamp_ms=timestamp_ms,
        )

    @staticmethod
    def projection(*, quantity: str = "2", average_entry: str = "100") -> PositionProjectionUpdate:
        qty = Decimal(quantity)
        return PositionProjectionUpdate(
            position_key=POSITION_KEY,
            side=PositionSide.LONG if qty > 0 else PositionSide.FLAT,
            quantity=Quantity(qty),
            average_entry=Price(Decimal(average_entry)) if qty > 0 else None,
            realized_pnl=Decimal("0"),
            accumulated_fee=Decimal("0"),
            engaged_notional=Notional(qty * Decimal(average_entry) if qty > 0 else Decimal("0")),
            sync_state="ready",
            expected_version=None,
            updated_at_ms=1200,
        )

    def seed_legacy_trade(self, store: SQLiteStore):
        runtime = store.initialize_robot_runtime_state(ACCOUNT, updated_at_ms=900)
        runtime = store.update_robot_runtime_state(
            ACCOUNT,
            mode="ROBOT_RUNNING",
            recovery_status="READY",
            reason=None,
            expected_version=runtime.version,
            updated_at_ms=910,
        )
        runtime = store.update_robot_runtime_state(
            ACCOUNT,
            mode="ROBOT_RUNNING",
            recovery_status="RECONCILIATION_REQUIRED",
            reason="legacy protection recovery test",
            expected_version=runtime.version,
            updated_at_ms=920,
        )

        candidate, _ = store.create_robot_candidate(
            candidate_id=CANDIDATE_ID,
            trading_account_id=ACCOUNT,
            symbol=SYMBOL,
            status="APPROVED",
            signal_snapshot={"symbol": SYMBOL.value, "pattern": "Falling Wedge"},
            approved_at_ms=1000,
            updated_at_ms=1000,
        )
        candidate = store.save_robot_candidate_state(
            CANDIDATE_ID,
            status="APPROVED",
            robot_state={
                "direction": "LONG",
                "execution": {"limit_order_id": ENTRY_ORDER_ID},
            },
            expected_revision=candidate.state_revision,
            updated_at_ms=1100,
        )

        entry = self.entry_execution()
        store.apply_execution_once(entry, self.projection())
        position = store.get_position_projection(POSITION_KEY)
        self.assertIsNotNone(position)

        trade, _ = store.create_robot_trade(
            trade_id=TRADE_ID,
            trading_account_id=ACCOUNT,
            candidate_id=CANDIDATE_ID,
            symbol=SYMBOL,
            direction="LONG",
            pattern="Falling Wedge",
            source_timeframe="1",
            signal_time_ms=1000,
            entry_time_ms=1300,
            entry_path="LIMIT",
            actual_wv=Decimal("1"),
            average_entry=Decimal("100"),
            stop_price=Decimal("98"),
            take_price=Decimal("106"),
            entry_quantity=Decimal("2"),
            entry_position_version=position.version,
            created_at_ms=1300,
        )

        # Reproduce an authentic v17 -> v18 legacy row: both D2.3 columns are
        # nullable only for pre-attestation trades migrated into the new schema.
        with store._transaction():
            store._connection.execute(
                "UPDATE robot_trades SET entry_quantity=NULL, entry_position_version=NULL WHERE trade_id=?",
                (TRADE_ID,),
            )

        obligation, _ = store.latch_paper_protection_obligation(
            trade_id=TRADE_ID,
            protection_version=1,
            winning_leg="STOP",
            trigger_price=Decimal("98"),
            observed_exit_price=Decimal("97.5"),
            observed_quantity=Decimal("2"),
            market_event_id="book-event-1",
            source_received_at_ms=1350,
            source_generation=1,
            source_sequence=10,
            source_update_id=11,
            source_event_at_ms=1340,
            source_matching_engine_cts_ms=1330,
            observed_bid_price=Decimal("97.5"),
            observed_ask_price=Decimal("97.6"),
            latched_at_ms=1400,
        )

        return (
            runtime,
            store.get_robot_trade(TRADE_ID),
            store.get_robot_candidate(CANDIDATE_ID),
            obligation,
            store.get_position_projection(POSITION_KEY),
            store.load_executions(),
        )

    def test_pure_proof_reconstructs_exact_limit_entry(self):
        with self.open_store() as store:
            runtime, trade, candidate, obligation, position, executions = self.seed_legacy_trade(store)
            proof = prove_legacy_entry_attestation(
                runtime=runtime,
                trade=trade,
                candidate=candidate,
                obligation=obligation,
                position=position,
                executions=executions,
            )

            self.assertEqual(proof.trade_id, TRADE_ID)
            self.assertEqual(proof.obligation_id, obligation.obligation_id)
            self.assertEqual(proof.entry_order_id, ENTRY_ORDER_ID)
            self.assertEqual(proof.execution_ids, ("legacy-entry-exec-1",))
            self.assertEqual(proof.entry_quantity, Decimal("2"))
            self.assertEqual(proof.entry_position_version, position.version)
            self.assertEqual(proof.average_entry, Decimal("100"))

    def test_atomic_attestation_is_idempotent_and_has_no_market_side_effect(self):
        with self.open_store() as store:
            _runtime, _trade, _candidate, obligation, position, _executions = self.seed_legacy_trade(store)
            before_execs = store.load_executions()
            before_obligation = store.get_paper_protection_obligation(obligation.obligation_id)

            first = attest_legacy_robot_entry(
                store,
                trade_id=TRADE_ID,
                obligation_id=obligation.obligation_id,
                client_action_id=ACTION_ID,
                authorized_at_ms=1500,
            )
            self.assertTrue(first.created)
            self.assertEqual(first.trade.entry_quantity, Decimal("2"))
            self.assertEqual(first.trade.entry_position_version, position.version)
            self.assertEqual(first.trade.version, 2)
            self.assertEqual(first.candidate.state_revision, 2)

            audit = first.candidate.robot_state["execution"]["legacy_entry_attestation"]
            self.assertEqual(audit["source"], LEGACY_ATTESTATION_SOURCE)
            self.assertEqual(audit["client_action_id"], ACTION_ID)
            self.assertEqual(audit["trade_id"], TRADE_ID)
            self.assertEqual(audit["obligation_id"], obligation.obligation_id)
            self.assertEqual(audit["entry_order_id"], ENTRY_ORDER_ID)
            self.assertEqual(audit["execution_ids"], ["legacy-entry-exec-1"])
            self.assertEqual(audit["entry_quantity"], "2")
            self.assertEqual(audit["entry_position_version"], position.version)
            self.assertEqual(audit["authorized_at_ms"], 1500)

            self.assertEqual(store.load_executions(), before_execs)
            self.assertEqual(
                store.get_paper_protection_obligation(obligation.obligation_id),
                before_obligation,
            )
            self.assertEqual(store.get_position_projection(POSITION_KEY), position)

            repeated = attest_legacy_robot_entry(
                store,
                trade_id=TRADE_ID,
                obligation_id=obligation.obligation_id,
                client_action_id=ACTION_ID,
                authorized_at_ms=1600,
            )
            self.assertFalse(repeated.created)
            self.assertEqual(repeated.trade.version, first.trade.version)
            self.assertEqual(repeated.candidate.state_revision, first.candidate.state_revision)
            self.assertEqual(
                repeated.candidate.robot_state["execution"]["legacy_entry_attestation"],
                audit,
            )
            self.assertEqual(store.load_executions(), before_execs)

    def test_failed_proof_persists_neither_trade_fields_nor_audit(self):
        with self.open_store() as store:
            _runtime, _trade, _candidate, obligation, _position, _executions = self.seed_legacy_trade(store)
            with store._transaction():
                store._connection.execute(
                    "UPDATE paper_protection_obligations SET observed_quantity='3' WHERE obligation_id=?",
                    (obligation.obligation_id,),
                )

            with self.assertRaisesRegex(
                LegacyProtectionRecoveryRejected,
                "triggered obligation quantity",
            ):
                attest_legacy_robot_entry(
                    store,
                    trade_id=TRADE_ID,
                    obligation_id=obligation.obligation_id,
                    client_action_id=ACTION_ID,
                    authorized_at_ms=1500,
                )

            trade = store.get_robot_trade(TRADE_ID)
            candidate = store.get_robot_candidate(CANDIDATE_ID)
            self.assertIsNone(trade.entry_quantity)
            self.assertIsNone(trade.entry_position_version)
            self.assertNotIn(
                "legacy_entry_attestation",
                candidate.robot_state.get("execution", {}),
            )

    def test_partial_or_modern_attestation_is_not_recoverable(self):
        for mode in ("partial", "modern"):
            with self.subTest(mode=mode), self.open_store() as store:
                _runtime, _trade, _candidate, obligation, _position, _executions = self.seed_legacy_trade(store)
                with store._transaction():
                    if mode == "partial":
                        store._connection.execute(
                            "UPDATE robot_trades SET entry_quantity='2', entry_position_version=NULL WHERE trade_id=?",
                            (TRADE_ID,),
                        )
                    else:
                        store._connection.execute(
                            "UPDATE robot_trades SET entry_quantity='2', entry_position_version=1 WHERE trade_id=?",
                            (TRADE_ID,),
                        )

                expected = "partial canonical" if mode == "partial" else "already exists"
                with self.assertRaisesRegex(LegacyProtectionRecoveryRejected, expected):
                    attest_legacy_robot_entry(
                        store,
                        trade_id=TRADE_ID,
                        obligation_id=obligation.obligation_id,
                        client_action_id=ACTION_ID,
                        authorized_at_ms=1500,
                    )
            # Each subtest needs an independent SQLite file.
            self.tearDown()
            self.setUp()

    def test_client_action_id_cannot_be_reused_for_another_target(self):
        with self.open_store() as store:
            _runtime, _trade, _candidate, obligation, _position, _executions = self.seed_legacy_trade(store)
            other, _ = store.create_robot_candidate(
                candidate_id="other-candidate",
                trading_account_id=ACCOUNT,
                symbol=Symbol("ETHUSDT"),
                status="APPROVED",
                signal_snapshot={"symbol": "ETHUSDT", "pattern": "Falling Wedge"},
                approved_at_ms=1450,
                updated_at_ms=1450,
            )
            store.save_robot_candidate_state(
                other.candidate_id,
                status="APPROVED",
                robot_state={
                    "execution": {
                        "legacy_entry_attestation": {
                            "source": LEGACY_ATTESTATION_SOURCE,
                            "client_action_id": ACTION_ID,
                            "trade_id": "other-trade",
                            "obligation_id": "other-obligation",
                        }
                    }
                },
                expected_revision=other.state_revision,
                updated_at_ms=1460,
            )

            with self.assertRaisesRegex(LegacyProtectionRecoveryRejected, "client_action_id conflicts"):
                attest_legacy_robot_entry(
                    store,
                    trade_id=TRADE_ID,
                    obligation_id=obligation.obligation_id,
                    client_action_id=ACTION_ID,
                    authorized_at_ms=1500,
                )

            trade = store.get_robot_trade(TRADE_ID)
            self.assertIsNone(trade.entry_quantity)
            self.assertIsNone(trade.entry_position_version)

    def test_pure_proof_rejects_pre_entry_nonflat_and_any_post_entry_foreign_execution(self):
        with self.open_store() as store:
            runtime, trade, candidate, obligation, position, executions = self.seed_legacy_trade(store)

            pre_entry_nonflat = self.entry_execution(
                exec_id="old-manual-buy",
                order_id="old-manual-order",
                quantity="1",
                timestamp_ms=1100,
            )
            with self.assertRaisesRegex(LegacyProtectionRecoveryRejected, "FLAT immediately before"):
                prove_legacy_entry_attestation(
                    runtime=runtime,
                    trade=trade,
                    candidate=candidate,
                    obligation=obligation,
                    position=position,
                    executions=(pre_entry_nonflat, *executions),
                )

            post_entry_foreign = self.entry_execution(
                exec_id="manual-after-entry",
                order_id="manual-after-entry-order",
                side=OrderSide.SELL,
                quantity="1",
                timestamp_ms=1250,
            )
            with self.assertRaisesRegex(LegacyProtectionRecoveryRejected, "unidentified/manual execution"):
                prove_legacy_entry_attestation(
                    runtime=runtime,
                    trade=trade,
                    candidate=candidate,
                    obligation=obligation,
                    position=position,
                    executions=(*executions, post_entry_foreign),
                )

    def test_pure_proof_rejects_state_economics_and_close_execution_mismatches(self):
        with self.open_store() as store:
            runtime, trade, candidate, obligation, position, executions = self.seed_legacy_trade(store)

            cases = (
                (
                    "runtime",
                    dict(runtime=replace(runtime, recovery_status="PAUSED")),
                    "RECONCILIATION_REQUIRED",
                ),
                (
                    "candidate lifecycle",
                    dict(candidate=replace(candidate, status="CLOSED")),
                    "candidate scope/lifecycle",
                ),
                (
                    "obligation lifecycle",
                    dict(obligation=replace(obligation, status="DISPATCHING")),
                    "exactly TRIGGERED",
                ),
                (
                    "position quantity",
                    dict(position=replace(position, quantity=Quantity(Decimal("3")))),
                    "current position quantity",
                ),
                (
                    "position average",
                    dict(position=replace(position, average_entry=Price(Decimal("101")))),
                    "current position average entry",
                ),
                (
                    "obligation quantity",
                    dict(obligation=replace(obligation, observed_quantity=Decimal("3"))),
                    "triggered obligation quantity",
                ),
                (
                    "trade vwap",
                    dict(trade=replace(trade, average_entry=Decimal("101"))),
                    "entry VWAP",
                ),
            )
            base = dict(
                runtime=runtime,
                trade=trade,
                candidate=candidate,
                obligation=obligation,
                position=position,
                executions=executions,
            )
            for name, override, message in cases:
                with self.subTest(name=name):
                    arguments = dict(base)
                    arguments.update(override)
                    with self.assertRaisesRegex(LegacyProtectionRecoveryRejected, message):
                        prove_legacy_entry_attestation(**arguments)

            stable_close = Execution(
                dedup_key=ExecutionDedupKey(
                    ACCOUNT,
                    Category.LINEAR,
                    obligation.exec_id,
                ),
                order_id=obligation.order_id,
                symbol=SYMBOL,
                side=OrderSide.SELL,
                price=Price(Decimal("97")),
                quantity=Quantity(Decimal("2")),
                fee=Decimal("0"),
                exchange_timestamp_ms=1450,
            )
            with self.assertRaisesRegex(LegacyProtectionRecoveryRejected, "close execution already exists"):
                prove_legacy_entry_attestation(
                    runtime=runtime,
                    trade=trade,
                    candidate=candidate,
                    obligation=obligation,
                    position=position,
                    executions=(*executions, stable_close),
                )


if __name__ == "__main__":
    unittest.main()
