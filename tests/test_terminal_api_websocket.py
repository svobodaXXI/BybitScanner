import unittest
from dataclasses import replace

from terminal.api.models import (
    EventType, PresentationChannel, ServiceHealth, SubscriptionOperation,
    SubscriptionRequest,
)
from terminal.api.projections import SnapshotFacts, build_terminal_snapshot
from terminal.api.websocket import (
    EventDisposition, PresentationCursor, PresentationStreamSession, SubscriptionService,
)
from terminal.application.models import TrustState
from terminal.domain.models import Category, PositionKey, Symbol, TradingAccountId
from terminal.domain.states import ConnectivityState
from tests.test_terminal_api_projections import capability
from tests.test_terminal_reconciliation import position_event
from tests.test_terminal_trading_application import instrument


KEY = PositionKey(TradingAccountId("account-1"), Category.LINEAR, Symbol("BTCUSDT"), 0)


class SnapshotFactory:
    def __init__(self):
        self.calls = []

    def __call__(self, symbol, stream_id, snapshot_id):
        self.calls.append((symbol, stream_id, snapshot_id))
        key = replace(KEY, symbol=Symbol(symbol))
        position = replace(position_event(), position_key=key)
        facts = SnapshotFacts(
            snapshot_id, stream_id, key, ServiceHealth.HEALTHY, ConnectivityState.ONLINE,
            TrustState.CONVERGED, len(self.calls), position, (), (), (), None, None, (),
            replace(instrument(), symbol=symbol), (), (), capability(),
        )
        return build_terminal_snapshot(facts)


class TerminalWebSocketContractTests(unittest.TestCase):
    def setUp(self):
        self.factory = SnapshotFactory()
        self.service = SubscriptionService(self.factory)

    def subscribe(self, symbol="BTCUSDT"):
        return self.service.handle(SubscriptionRequest(
            SubscriptionOperation.SUBSCRIBE, symbol,
            (PresentationChannel.ORDERS, PresentationChannel.POSITION),
        ))

    def test_subscribe_unsubscribe_all_and_symbol_switch_require_fresh_snapshot(self):
        first = self.subscribe()
        first_session = self.service.session
        self.assertTrue(first.fresh_snapshot_required)
        again = self.subscribe()
        self.assertFalse(again.fresh_snapshot_required)
        switched = self.subscribe("ETHUSDT")
        self.assertTrue(switched.fresh_snapshot_required)
        self.assertNotEqual(first_session.stream_id, self.service.session.stream_id)
        self.assertEqual(len(self.factory.calls), 2)

        removed = self.service.handle(SubscriptionRequest(
            SubscriptionOperation.UNSUBSCRIBE, "ETHUSDT",
        ))
        self.assertTrue(removed.accepted)
        self.assertIsNone(self.service.session)
        self.subscribe()
        self.service.handle(SubscriptionRequest(SubscriptionOperation.UNSUBSCRIBE_ALL))
        self.assertIsNone(self.service.session)

    def test_ping_pong_and_heartbeat_do_not_claim_trading_readiness(self):
        pong = self.service.handle(SubscriptionRequest(
            SubscriptionOperation.PING, nonce="n-1",
        ))
        self.assertEqual(pong.operation, SubscriptionOperation.PONG)
        self.assertEqual(pong.nonce, "n-1")
        self.subscribe()
        heartbeat = self.service.session.heartbeat()
        self.assertEqual(heartbeat.event_type, EventType.HEARTBEAT)
        self.assertTrue(heartbeat.payload["service_alive"])
        self.assertFalse(heartbeat.payload["trading_ready"])

    def test_snapshot_first_and_event_sequence_progression(self):
        self.subscribe()
        session = self.service.session
        initial = session.initial_snapshot_event()
        updated = session.emit(
            EventType.ORDER_UPDATED, "order-1", 2, {"status": "cancelled"},
            reconciliation_generation=session.snapshot.reconciliation_generation,
        )
        removed = session.emit(
            EventType.ORDER_REMOVED, "order-1", 2, {"derived": True},
            reconciliation_generation=session.snapshot.reconciliation_generation,
        )
        self.assertEqual(initial.event_type, EventType.SNAPSHOT_REPLACED)
        self.assertEqual((initial.event_sequence, updated.event_sequence, removed.event_sequence), (1, 2, 3))
        self.assertEqual(updated.payload["status"], "cancelled")

    def test_order_removal_is_derived_only_after_final_lifecycle_update(self):
        self.subscribe()
        session = self.service.session
        with self.assertRaisesRegex(ValueError, "preceding final"):
            session.emit(
                EventType.ORDER_REMOVED, "order-1", 1, {"derived": True},
                reconciliation_generation=session.snapshot.reconciliation_generation,
            )
        session.emit(
            EventType.ORDER_UPDATED, "order-1", 1, {"status": "filled"},
            reconciliation_generation=session.snapshot.reconciliation_generation,
        )
        removed = session.emit(
            EventType.ORDER_REMOVED, "order-1", 1, {"derived": True},
            reconciliation_generation=session.snapshot.reconciliation_generation,
        )
        self.assertEqual(removed.event_type, EventType.ORDER_REMOVED)

    def test_events_are_filtered_by_subscribed_channel_and_symbol(self):
        session = PresentationStreamSession(
            "BTCUSDT", (PresentationChannel.ORDERS,), self.factory,
        )
        with self.assertRaisesRegex(ValueError, "channel"):
            session.emit(
                EventType.EXECUTION_RECORDED, "exec-1", 1, {"symbol": "BTCUSDT"},
                reconciliation_generation=1,
            )
        with self.assertRaisesRegex(ValueError, "symbol"):
            session.emit(
                EventType.ORDER_ADDED, "order-1", 1, {"symbol": "ETHUSDT"},
                reconciliation_generation=1,
            )
        execution_session = PresentationStreamSession(
            "BTCUSDT", (PresentationChannel.EXECUTIONS,), self.factory,
        )
        execution = execution_session.emit(
            EventType.EXECUTION_RECORDED, "exec-1", 1, {"symbol": "BTCUSDT"},
            reconciliation_generation=1,
        )
        self.assertEqual(execution.event_type, EventType.EXECUTION_RECORDED)

    def test_cursor_rejects_wrong_ids_stale_versions_and_detects_gaps(self):
        self.subscribe()
        session = self.service.session
        cursor = PresentationCursor(session.snapshot)
        first = session.initial_snapshot_event()
        self.assertEqual(cursor.apply(first), EventDisposition.APPLY)
        self.assertEqual(cursor.apply(first), EventDisposition.IGNORE_STALE)

        second = session.emit(
            EventType.POSITION_CHANGED, "position", 5, {},
            reconciliation_generation=session.snapshot.reconciliation_generation,
        )
        self.assertEqual(cursor.apply(second), EventDisposition.APPLY)
        stale_entity = replace(second, event_sequence=3, entity_version=4)
        self.assertEqual(cursor.apply(stale_entity), EventDisposition.IGNORE_STALE)
        gap = replace(second, event_sequence=5, entity_version=6)
        self.assertEqual(cursor.apply(gap), EventDisposition.FRESH_SNAPSHOT_REQUIRED)
        self.assertEqual(cursor.apply(replace(second, stream_id="other", event_sequence=3)),
                         EventDisposition.IGNORE_STALE)
        self.assertEqual(cursor.apply(replace(second, snapshot_id="other", event_sequence=3)),
                         EventDisposition.IGNORE_STALE)
        self.assertEqual(cursor.apply(replace(
            second, event_sequence=3,
            reconciliation_generation=session.snapshot.reconciliation_generation - 1,
        )), EventDisposition.IGNORE_STALE)

    def test_reconnect_always_creates_new_stream_and_snapshot(self):
        one = PresentationStreamSession(
            "BTCUSDT", (PresentationChannel.ORDERS,), self.factory,
        )
        two = PresentationStreamSession(
            "BTCUSDT", (PresentationChannel.ORDERS,), self.factory,
        )
        self.assertNotEqual(one.stream_id, two.stream_id)
        self.assertNotEqual(one.snapshot_id, two.snapshot_id)


if __name__ == "__main__":
    unittest.main()
