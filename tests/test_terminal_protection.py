import tempfile
import unittest
from dataclasses import replace
from decimal import Decimal
from pathlib import Path

from terminal.application.execution_engine import ExecutionEngine
from terminal.application.models import ProtectionEvidence, ProtectionState
from terminal.application.protection import ManualProtectionIntent, validate_manual_protection
from terminal.application.trading_application import TradingApplication
from terminal.application.trading_application import ApplicationMutationsDisabled
from terminal.domain.models import Category, OrderSide, PositionKey, Symbol, TradingAccountId
from terminal.domain.states import ConnectivityState
from terminal.persistence.sqlite_store import SQLiteStore
from tests.test_terminal_reconciliation import position_event
from tests.test_terminal_trading_application import Adapter, Guard, admitted, instrument


ACCOUNT = TradingAccountId("account-1")
KEY = PositionKey(ACCOUNT, Category.LINEAR, Symbol("BTCUSDT"), 0)


class ProtectionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.store = SQLiteStore.open(Path(self.temp.name) / "db.sqlite3")
        self.adapter = Adapter()
        self.engine = ExecutionEngine(self.store)
        self.app = TradingApplication(
            Guard(admitted()), self.store, self.adapter, self.engine,
            mutations_enabled=True, clock_ms=lambda: 3000,
        )

    def tearDown(self):
        self.store.close()
        self.temp.cleanup()

    def intent(self, tp=Decimal("120"), sl=Decimal("80"), connectivity=ConnectivityState.ONLINE):
        return ManualProtectionIntent(
            KEY, OrderSide.BUY, position_event(), instrument(), tp, sl,
            connectivity=connectivity,
        )

    def test_manual_full_protection_ack_is_pending_until_bybit_evidence(self):
        result = self.app.set_protection(self.intent())
        self.assertIs(result.state, ProtectionState.PENDING_CONFIRMATION)
        call = self.adapter.calls[-1]
        self.assertEqual(call[0].value, "protection")
        projection = self.engine.ingest_protection_evidence(ProtectionEvidence(
            KEY, Decimal("120"), Decimal("80"), None, 4000,
        ))
        self.assertEqual(projection.status, ProtectionState.CONFIRMED_ACTIVE.value)
        self.assertIsNone(projection.pending_command_id)
        self.assertEqual(self.store.load_executions(), ())

    def test_explicit_cancel_confirms_no_protection_only_from_exchange_fact(self):
        result = self.app.set_protection(self.intent(tp=None, sl=None))
        self.assertIs(result.state, ProtectionState.PENDING_CONFIRMATION)
        projection = self.engine.ingest_protection_evidence(
            ProtectionEvidence(KEY, None, None, None, 4000)
        )
        self.assertEqual(projection.status, ProtectionState.NO_PROTECTION_CONFIGURED.value)

    def test_unknown_or_rejected_outcome_is_truthful_and_not_retried(self):
        from terminal.exchange.bybit_v5_mutation_adapter import MutationDisposition

        self.adapter.disposition = MutationDisposition.UNKNOWN
        result = self.app.set_protection(self.intent())
        self.assertIs(result.state, ProtectionState.UNKNOWN)
        self.assertEqual(len(self.adapter.calls), 1)

        with self.assertRaisesRegex(ValueError, "reconciliation"):
            self.app.set_protection(self.intent(tp=Decimal("130"), sl=Decimal("70")))
        self.assertEqual(len(self.adapter.calls), 1)

    def test_deterministic_reject_is_failed_unprotected(self):
        from terminal.exchange.bybit_v5_mutation_adapter import MutationDisposition

        self.adapter.disposition = MutationDisposition.REJECTED
        rejected = self.app.set_protection(self.intent())
        self.assertIs(rejected.state, ProtectionState.FAILED_UNPROTECTED)
        self.assertIsNone(rejected.projection.pending_command_id)
        self.assertEqual(len(self.adapter.calls), 1)

    def test_offline_and_non_normalized_protection_fail_before_network(self):
        with self.assertRaisesRegex(ValueError, "ONLINE"):
            self.app.set_protection(self.intent(connectivity=ConnectivityState.OFFLINE))
        with self.assertRaisesRegex(ValueError, "tick"):
            validate_manual_protection(self.intent(tp=Decimal("120.1")))
        self.assertEqual(self.adapter.calls, [])

    def test_exchange_facts_without_intent_do_not_invent_protection(self):
        projection = self.engine.ingest_protection_evidence(
            ProtectionEvidence(KEY, None, None, None, 5000)
        )
        self.assertEqual(projection.status, ProtectionState.NO_PROTECTION_CONFIGURED.value)
        active = self.engine.ingest_protection_evidence(
            ProtectionEvidence(KEY, Decimal("120"), None, None, 6000)
        )
        self.assertEqual(active.status, ProtectionState.CONFIRMED_ACTIVE.value)

    def test_application_kill_switch_precedes_protection_persistence_and_network(self):
        self.app.mutations_enabled = False
        with self.assertRaises(ApplicationMutationsDisabled):
            self.app.set_protection(self.intent())
        self.assertEqual(self.adapter.calls, [])
        self.assertEqual(self.store.load_unfinished_commands(), ())


if __name__ == "__main__":
    unittest.main()
