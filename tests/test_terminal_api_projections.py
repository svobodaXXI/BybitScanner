import unittest
from dataclasses import replace
from decimal import Decimal

from terminal.api.models import ServiceHealth, to_primitive
from terminal.api.projections import (
    CapabilitySettingsProjection, OrderClassification, PresentationOrigin, SnapshotFacts,
    build_terminal_snapshot,
)
from terminal.application.cleanup import CleanupStatus
from terminal.application.models import FlatCause, ProtectionState, TrustState
from terminal.domain.models import (
    Category, CommandId, Controller, Execution, ExecutionDedupKey, ExecutionId, Notional,
    OrderId, OrderSide, Origin, PositionKey, PositionSide, Price, Quantity, Symbol,
    TradingAccountId,
)
from terminal.domain.states import CommandState, ConnectivityState
from terminal.persistence.sqlite_store import (
    CleanupItemRecord, CleanupRunRecord, CommandRecord, ProtectionProjectionRecord,
)
from tests.test_terminal_reconciliation import order_event, position_event
from tests.test_terminal_trading_application import instrument


ACCOUNT = TradingAccountId("account-1")
KEY = PositionKey(ACCOUNT, Category.LINEAR, Symbol("BTCUSDT"), 0)


def capability(enabled=True):
    return CapabilitySettingsProjection(
        None, None, None, None, None, enabled, "testnet", False,
    )


def command(kind="create_limit", state=CommandState.OPEN, exchange_order="internal"):
    return CommandRecord(
        CommandId(f"cmd-{kind}"), f"link-{kind}", ACCOUNT, Category.LINEAR,
        Symbol("BTCUSDT"), 0, kind, OrderSide.BUY, Notional(Decimal("100")),
        Price(Decimal("100")), Quantity(Decimal("1")), Origin.TERMINAL_MANUAL,
        Controller.MANUAL, state, 1, OrderId(exchange_order), 1, 2,
    )


def facts(**changes):
    base = SnapshotFacts(
        "snapshot-1", "stream-1", KEY, ServiceHealth.HEALTHY,
        ConnectivityState.ONLINE, TrustState.CONVERGED, 4,
        position_event(side=PositionSide.FLAT, size="0"), (), (), (), None, None, (),
        instrument(), (), (), capability(),
    )
    return replace(base, **changes)


class TerminalApiProjectionTests(unittest.TestCase):
    def test_flat_and_open_position_snapshots_preserve_factual_fields(self):
        flat = build_terminal_snapshot(facts())
        self.assertEqual(flat.snapshot_id, "snapshot-1")
        self.assertEqual(flat.position.side, PositionSide.FLAT.value)
        self.assertIsNone(flat.position.average_entry)

        position = replace(
            position_event(), position_value=Decimal("210"), mark_price=Decimal("105"),
            unrealized_pnl=Decimal("10"), current_realized_pnl=Decimal("2"),
            cumulative_realized_pnl=Decimal("7"),
        )
        opened = build_terminal_snapshot(facts(position=position))
        self.assertEqual(opened.position.position_value, Decimal("210"))
        self.assertEqual(opened.position.unrealized_pnl, Decimal("10"))

    def test_internal_external_partial_limit_and_pending_states(self):
        internal = replace(
            order_event(order_id="internal", link="terminal-link", qty="3", leaves="2"),
            price=Decimal("100"),
        )
        external = replace(
            order_event(order_id="external", link="foreign-link", qty="1", leaves="1"),
            price=Decimal("101"),
        )
        cancel = command("cancel", CommandState.CANCEL_PENDING, "internal")
        amend = command("amend", CommandState.AMENDED, "internal")
        snapshot = build_terminal_snapshot(facts(
            active_orders=(internal, external), commands=(cancel, amend),
        ))
        first, second = snapshot.active_orders
        self.assertEqual(first.remaining_notional, Decimal("200"))
        self.assertTrue(first.pending_cancel)
        self.assertFalse(first.pending_amend)  # confirmed AMENDED remains an active order update
        self.assertIs(first.origin, PresentationOrigin.TERMINAL_MANUAL)
        self.assertIs(second.origin, PresentationOrigin.EXTERNAL_UNKNOWN)
        self.assertTrue(second.external)
        self.assertIs(first.classification, OrderClassification.ORDINARY_LIMIT)
        self.assertEqual(snapshot.chart_orders[0].entity_id, "internal")

    def test_cleanup_protection_unknown_and_reopened_warning(self):
        run = CleanupRunRecord(
            "cleanup-1", KEY, FlatCause.MARKET.value, 4, 100,
            CleanupStatus.REOPENED.value, 1, 100, 101,
        )
        items = (
            CleanupItemRecord("cleanup-1", OrderId("a"), None, CommandId("ca"), "la",
                              "cancelled", 1, 100, 101),
            CleanupItemRecord("cleanup-1", OrderId("b"), None, CommandId("cb"), "lb",
                              "unknown", 1, 100, 101),
        )
        protection = ProtectionProjectionRecord(
            KEY, ProtectionState.FAILED_UNPROTECTED.value, None, None, None, None,
            2, 100, 101,
        )
        snapshot = build_terminal_snapshot(facts(
            position=position_event(), cleanup_run=run, cleanup_items=items,
            protection=protection, trust_state=TrustState.RECONCILING,
        ))
        self.assertEqual(snapshot.cleanup.cancelled_count, 1)
        self.assertEqual(snapshot.cleanup.unknown_count, 1)
        self.assertTrue(snapshot.position.reopened_after_cleanup)
        self.assertIn("unprotected", " ".join(snapshot.warnings))
        self.assertEqual(snapshot.trading_readiness, "reconciling")

    def test_execution_filter_decimal_strings_and_unavailable_settings(self):
        execution = Execution(
            ExecutionDedupKey(ACCOUNT, Category.LINEAR, ExecutionId("exec-1")),
            OrderId("order-1"), Symbol("BTCUSDT"), OrderSide.BUY,
            Price(Decimal("100.5")), Quantity(Decimal("0.25")), Decimal("0.01"), 10,
        )
        snapshot = build_terminal_snapshot(facts(executions=(execution,), capability=capability(False)))
        encoded = to_primitive(snapshot)
        self.assertEqual(encoded["executions"][0]["price"], "100.5")
        self.assertIsNone(encoded["capability"]["one_wv_usdt"])
        self.assertEqual(encoded["trading_readiness"], "disabled")
        self.assertEqual(encoded["service_health"], "healthy")


if __name__ == "__main__":
    unittest.main()
