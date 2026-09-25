from __future__ import annotations

from dataclasses import dataclass
import unittest

from terminal.runtime.paper_http_server import RobotProtectionCoverageManager


SYMBOL = "KSMUSDT"


class _Response:
    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict:
        return {
            "retCode": 0,
            "result": {
                "s": SYMBOL,
                "b": [["4.270", "100"]],
                "a": [["4.271", "100"]],
                "ts": 1789725000000,
                "u": 10680001,
                "seq": 177600000001,
                "cts": 1789724999999,
            },
        }


class _Session:
    def __init__(self) -> None:
        self.calls = []

    def get(self, url, *, params, timeout):
        self.calls.append((url, params, timeout))
        return _Response()


class _BookSnapshot:
    def __init__(self, *, message_type="delta") -> None:
        self.message_type = message_type

    def snapshot(self):
        return {
            "state": "READY",
            "symbol": SYMBOL,
            "bids": [{"price": "4.270", "size": "100"}],
            "asks": [{"price": "4.271", "size": "100"}],
            "receivedAt": 1789725000001,
            "sequence": 177600000001,
            "updateId": 10680001,
            "timestamp": 1789725000000,
            "matchingEngineCts": 1789724999999,
            "messageType": self.message_type,
        }


@dataclass
class _Context:
    reconnect_count: int = 7
    public_orderbook: object | None = None


class _Owner:
    def __init__(self, durable_loss=None) -> None:
        self.fences = []
        self.recoveries = []
        self.processed = []
        self.durable_loss = durable_loss

    def robot_protection_coverage_symbols(self):
        return (SYMBOL,)

    def robot_protection_continuity_loss(self):
        return self.durable_loss

    def fence_robot_protection_continuity_loss(self, symbol, reason):
        self.fences.append((symbol, reason))
        return True

    def recover_robot_protection_continuity_loss(
        self, symbol, book, *, event_id, received_at_ms, reason,
    ):
        self.recoveries.append(
            (symbol, book, event_id, received_at_ms, reason)
        )
        return True

    def process_robot_market_event(
        self, symbol, book, *, event_id, received_at_ms,
    ):
        self.processed.append(
            (symbol, book, event_id, received_at_ms)
        )
        return 1


class _Runtime:
    def __init__(self, owner: _Owner) -> None:
        self.owner = owner

    def call(self, operation, timeout=15.0):
        return operation(self.owner)

    def enqueue(self, operation, **_kwargs):
        operation(self.owner)


class _QueuedRuntime(_Runtime):
    def __init__(self, owner: _Owner) -> None:
        super().__init__(owner)
        self.queued = []

    def enqueue(self, operation, **_kwargs):
        self.queued.append(operation)

    def run_next(self):
        return self.queued.pop(0)(self.owner)


class RobotProtectionOverflowRecoveryTests(unittest.TestCase):
    def test_restart_rehydrates_durable_continuity_loss_and_recovers(self):
        owner = _Owner((SYMBOL, "ingress_overflow"))
        runtime = _Runtime(owner)
        session = _Session()
        manager = RobotProtectionCoverageManager(
            object(), runtime, recovery_session=session,
        )
        manager._covered[SYMBOL] = _Context()

        self.assertTrue(manager.is_healthy())
        manager.resync()

        self.assertEqual(owner.fences, [(SYMBOL, "ingress_overflow")])
        self.assertEqual(len(owner.recoveries), 1)
        self.assertEqual(owner.recoveries[0][0], SYMBOL)
        self.assertEqual(owner.recoveries[0][4], "ingress_overflow")
        self.assertTrue(manager.is_healthy())
        self.assertEqual(len(session.calls), 1)

    def test_disconnect_barrier_preserves_pre_disconnect_event_fifo_order(self):
        owner = _Owner()
        runtime = _QueuedRuntime(owner)
        manager = RobotProtectionCoverageManager(object(), runtime)
        context = _Context(reconnect_count=0, public_orderbook=_BookSnapshot())
        manager._covered[SYMBOL] = context
        manager._roles[SYMBOL] = "OPEN_POSITION"

        manager._on_update(SYMBOL, f"{SYMBOL}:177600000001:10680001")
        context.reconnect_count = 1
        manager._on_disconnect(SYMBOL, 1, "OSError")

        self.assertEqual(len(runtime.queued), 2)
        runtime.run_next()
        self.assertEqual(len(owner.processed), 1)
        self.assertEqual(owner.processed[0][1].source_generation, 0)
        self.assertEqual(owner.fences, [])

        runtime.run_next()
        self.assertEqual(
            owner.fences,
            [(SYMBOL, "websocket_disconnect:OSError")],
        )
        self.assertEqual(
            manager.health()["unhealthy_symbols"],
            {SYMBOL: "websocket_disconnect:OSError"},
        )

    def test_disconnect_blocks_new_generation_delta_until_snapshot_recovery(self):
        owner = _Owner()
        runtime = _QueuedRuntime(owner)
        manager = RobotProtectionCoverageManager(object(), runtime)
        book = _BookSnapshot(message_type="delta")
        context = _Context(reconnect_count=1, public_orderbook=book)
        manager._covered[SYMBOL] = context
        manager._roles[SYMBOL] = "OPEN_POSITION"

        manager._on_disconnect(SYMBOL, 1, "OSError")
        manager._on_update(SYMBOL, f"{SYMBOL}:177600000001:10680001")
        self.assertEqual(len(runtime.queued), 1)

        book.message_type = "snapshot"
        manager._on_update(SYMBOL, f"{SYMBOL}:177600000001:10680001")
        self.assertEqual(len(runtime.queued), 2)

        runtime.run_next()
        self.assertEqual(
            owner.fences,
            [(SYMBOL, "websocket_disconnect:OSError")],
        )
        runtime.run_next()
        self.assertEqual(len(owner.recoveries), 1)
        self.assertEqual(owner.recoveries[0][4], "websocket_disconnect:OSError")

    def test_unhealthy_symbol_recovers_from_fresh_rest_snapshot_without_ws_snapshot(self):
        owner = _Owner()
        runtime = _Runtime(owner)
        session = _Session()
        manager = RobotProtectionCoverageManager(
            object(), runtime, recovery_session=session,
        )
        manager._covered[SYMBOL] = _Context()
        manager._unhealthy[SYMBOL] = "ingress_overflow"

        manager.resync()

        self.assertEqual(owner.fences, [(SYMBOL, "ingress_overflow")])
        self.assertEqual(len(owner.recoveries), 1)
        symbol, book, event_id, received_at_ms, reason = owner.recoveries[0]
        self.assertEqual(symbol, SYMBOL)
        self.assertEqual(reason, "ingress_overflow")
        self.assertEqual(event_id, f"{SYMBOL}:rest-recovery:177600000001:10680001")
        self.assertEqual(book.source_generation, 7)
        self.assertEqual(book.source_sequence, 177600000001)
        self.assertEqual(book.source_update_id, 10680001)
        self.assertEqual(book.source_event_at_ms, 1789725000000)
        self.assertEqual(book.source_matching_engine_cts_ms, 1789724999999)
        self.assertEqual(received_at_ms, book.received_at_ms)
        self.assertTrue(manager.is_healthy())
        self.assertEqual(len(session.calls), 1)
        url, params, timeout = session.calls[0]
        self.assertEqual(url, "https://api.bybit.com/v5/market/orderbook")
        self.assertEqual(
            params,
            {"category": "linear", "symbol": SYMBOL, "limit": 50},
        )
        self.assertEqual(timeout, 10)


if __name__ == "__main__":
    unittest.main()
