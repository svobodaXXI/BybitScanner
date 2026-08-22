import tempfile
import unittest
import uuid
from decimal import Decimal
from pathlib import Path

from terminal.application.command_identity import CommandIdentityFactory
from terminal.application.execution_engine import ExecutionEngine
from terminal.application.pretrade_guard import (
    AdmittedPreTradeRequest, IntentClassification, OrderKind, PreTradeDecision,
    SlippageMetadata, SlippageToleranceType,
)
from terminal.application.trading_application import (
    AmendIntent, ApplicationMutationsDisabled, CancelIntent, TradingApplication,
)
from terminal.domain.models import Category, OrderId, OrderSide, TradingAccountId
from terminal.domain.states import CommandState
from terminal.exchange.bybit_v5_mutation_adapter import (
    MutationDisposition, MutationKind, MutationOutcome,
)
from terminal.exchange.events import (
    InstrumentSnapshot, NormalizedOrderStatus, NormalizedOrderType, OrderEvent,
)
from terminal.persistence.sqlite_store import SQLiteStore


ACCOUNT = TradingAccountId("account")


class Guard:
    def __init__(self, decision):
        self.decision = decision
        self.calls = 0

    def evaluate(self, intent, context):
        self.calls += 1
        return self.decision


class Adapter:
    def __init__(self, disposition=MutationDisposition.ACKNOWLEDGED):
        self.disposition = disposition
        self.calls = []

    def _outcome(self, kind, kwargs):
        self.calls.append((kind, kwargs))
        return MutationOutcome(
            kind, self.disposition, order_id=kwargs.get("order_id") or "exchange-1", reason="fake"
        )

    def create_market_order(self, **kwargs): return self._outcome(MutationKind.CREATE, kwargs)
    def create_limit_order(self, **kwargs): return self._outcome(MutationKind.CREATE, kwargs)
    def amend_order(self, **kwargs): return self._outcome(MutationKind.AMEND, kwargs)
    def cancel_order(self, **kwargs): return self._outcome(MutationKind.CANCEL, kwargs)
    def set_trading_stop(self, **kwargs): return self._outcome(MutationKind.PROTECTION, kwargs)


def admitted(kind=OrderKind.MARKET, side=OrderSide.BUY, qty="2", reduce_only=False):
    identity = CommandIdentityFactory(lambda: uuid.UUID(int=1)).create()
    request = AdmittedPreTradeRequest(
        identity=identity, trading_account_id=ACCOUNT, category=Category.LINEAR,
        symbol="BTCUSDT", position_idx=0, side=side, order_kind=kind,
        requested_notional=Decimal("200"), sizing_reference_price=Decimal("100"),
        raw_quantity=Decimal(qty), normalized_quantity=Decimal(qty),
        final_quantity=Decimal(qty),
        normalized_limit_price=Decimal("100") if kind is OrderKind.LIMIT else None,
        classification=IntentClassification.ENTRY, reduce_only=reduce_only,
        capped_at_flat=reduce_only,
        slippage=(SlippageMetadata(SlippageToleranceType.PERCENT, Decimal("0.5"))
                  if kind is OrderKind.MARKET else None),
    )
    return PreTradeDecision(True, None, "admitted", request)


def instrument():
    return InstrumentSnapshot(
        Category.LINEAR, "BTCUSDT", "LinearPerpetual", "Trading", "BTC", "USDT", "USDT",
        Decimal("1"), Decimal("1000000"), Decimal("0.5"), Decimal("0.001"),
        Decimal("100"), Decimal("50"), Decimal("0.001"), Decimal("5"),
    )


def order(filled="1", qty="3", price="100"):
    return OrderEvent(
        ACCOUNT, Category.LINEAR, "BTCUSDT", OrderId("active"), "existing", 0,
        OrderSide.BUY, NormalizedOrderType.LIMIT, "Limit", Decimal(price), Decimal(qty),
        Decimal(filled), Decimal(qty)-Decimal(filled), None,
        NormalizedOrderStatus.PARTIALLY_FILLED_OPEN, "PartiallyFilled", False, False,
        None, None, None, None, None, 1, 2000,
    )


class TradingApplicationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.store = SQLiteStore.open(Path(self.temp.name) / "db.sqlite3")
        self.adapter = Adapter()
        self.guard = Guard(admitted())
        self.app = TradingApplication(
            self.guard, self.store, self.adapter, ExecutionEngine(self.store),
            mutations_enabled=True, clock_ms=lambda: 1000,
        )

    def tearDown(self):
        self.store.close()
        self.temp.cleanup()

    def test_application_kill_switch_precedes_guard_persistence_and_network(self):
        self.app.mutations_enabled = False
        with self.assertRaises(ApplicationMutationsDisabled):
            self.app.submit(object(), object())
        self.assertEqual(self.guard.calls, 0)
        self.assertEqual(self.store.load_unfinished_commands(), ())
        self.assertEqual(self.adapter.calls, [])

    def test_persistence_before_create_and_exact_identity_mapping(self):
        result = self.app.submit(object(), object())
        self.assertEqual(len(self.adapter.calls), 1)
        payload = self.adapter.calls[0][1]
        persisted = self.store.get_command(result.command.command_id)
        self.assertEqual(payload["order_link_id"], persisted.order_link_id)
        self.assertEqual(payload["qty"], persisted.normalized_quantity.value)
        self.assertIs(result.command.current_state, CommandState.ACKNOWLEDGED)
        self.assertEqual(self.store.load_executions(), ())

    def test_repeated_same_identity_cannot_submit_twice(self):
        self.app.submit(object(), object())
        with self.assertRaises(Exception):
            self.app.submit(object(), object())
        self.assertEqual(len(self.adapter.calls), 1)

    def test_persistence_or_transition_failure_is_zero_network(self):
        original = self.store.persist_command_before_submit
        self.store.persist_command_before_submit = lambda record: (_ for _ in ()).throw(OSError("disk"))
        with self.assertRaises(OSError):
            self.app.submit(object(), object())
        self.assertEqual(self.adapter.calls, [])
        self.store.persist_command_before_submit = original

        self.store.transition_command_state = lambda *a, **k: (_ for _ in ()).throw(OSError("commit"))
        self.guard = Guard(admitted(side=OrderSide.SELL))
        self.app.guard = self.guard
        with self.assertRaises(OSError):
            self.app.submit(object(), object())
        self.assertEqual(self.adapter.calls, [])

    def test_market_capped_qty_reduce_only_and_limit_gtc_inputs(self):
        self.guard.decision = admitted(side=OrderSide.SELL, qty="0.75", reduce_only=True)
        self.app.submit(object(), object())
        payload = self.adapter.calls[-1][1]
        self.assertEqual(payload["qty"], Decimal("0.75"))
        self.assertTrue(payload["reduce_only"])
        self.assertNotIn("price", payload)

    def test_amend_final_total_validation_and_ack_then_confirmed_amended(self):
        intent = AmendIntent(
            ACCOUNT, "BTCUSDT", OrderSide.BUY, instrument(), order(), order_id="active",
            resulting_total_quantity=Decimal("2.5"), changed_price=Decimal("101.0"),
        )
        result = self.app.amend(intent)
        self.assertEqual(self.adapter.calls[-1][1]["qty"], Decimal("2.5"))
        self.assertIs(result.command.current_state, CommandState.ACKNOWLEDGED)
        evidence = order(filled="1", qty="2.5", price="101.0")
        resolved = self.app.execution_engine.resolve_command(
            result.command, order_evidence=(evidence,), execution_evidence=(), occurred_at_ms=1100,
        )
        self.assertIs(resolved.current_state, CommandState.AMENDED)
        self.assertEqual(self.store.load_executions(), ())
        with self.assertRaisesRegex(ValueError, "exceed"):
            self.app.amend(AmendIntent(
                ACCOUNT, "BTCUSDT", OrderSide.BUY, instrument(), order(), order_id="active",
                resulting_total_quantity=Decimal("1"),
            ))

    def test_cancel_specific_ack_is_pending_until_confirmed(self):
        result = self.app.cancel(CancelIntent(
            ACCOUNT, "BTCUSDT", OrderSide.BUY, order(), order_link_id="existing"
        ))
        self.assertIs(result.command.current_state, CommandState.CANCEL_PENDING)
        self.assertEqual(self.adapter.calls[-1][1]["order_link_id"], "existing")


if __name__ == "__main__":
    unittest.main()
