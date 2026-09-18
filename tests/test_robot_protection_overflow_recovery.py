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


@dataclass
class _Context:
    reconnect_count: int = 7


class _Owner:
    def __init__(self, durable_loss=None) -> None:
        self.fences = []
        self.recoveries = []
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


class _Runtime:
    def __init__(self, owner: _Owner) -> None:
        self.owner = owner

    def call(self, operation, timeout=15.0):
        return operation(self.owner)

    def enqueue(self, operation):
        operation(self.owner)


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
