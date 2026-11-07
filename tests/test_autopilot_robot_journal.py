"""Read-only Robot journal: canonical ledger provenance, never Diary/manual guesses."""
import unittest
from decimal import Decimal
from types import SimpleNamespace

from terminal.domain.models import Symbol
from terminal.runtime.paper_http_server import _robot_journal


class RobotJournalTests(unittest.TestCase):
    def test_emits_recorded_signal_entry_exit_for_one_symbol_in_order(self):
        now = 1_800_000_000_000
        rows = [
            SimpleNamespace(
                trade_id="robot-btc", symbol=Symbol("BTCUSDT"), pattern="Falling Wedge",
                signal_time_ms=now - 3000, entry_time_ms=now - 2000,
                entry_quantity=Decimal("2"), average_entry=Decimal("101"),
                direction="LONG", exit_time_ms=now - 1000,
                exit_price=Decimal("105"), exit_reason="TAKE",
            ),
            SimpleNamespace(
                trade_id="robot-eth", symbol=Symbol("ETHUSDT"), pattern="Double Top",
                signal_time_ms=now - 2000, entry_time_ms=now - 1000,
                entry_quantity=Decimal("1"), average_entry=Decimal("20"),
                direction="SHORT", exit_time_ms=None, exit_price=None, exit_reason=None,
            ),
        ]
        class Store:
            def load_robot_trades_with_events_since(self, account, since):
                assert account.value == "paper"
                assert since == now - 7 * 24 * 60 * 60 * 1000
                return rows
        result = _robot_journal(SimpleNamespace(store=Store()), "BTCUSDT", now)
        self.assertEqual(result["source"], "robot_trades")
        self.assertEqual(result["symbol"], "BTCUSDT")
        self.assertEqual(
            [event["kind"] for event in result["events"]],
            ["SIGNAL_RECORDED", "POSITION_OPENED", "POSITION_CLOSED"],
        )
        self.assertEqual(result["events"][1]["price"], "101")
        self.assertEqual(result["events"][2]["reason"], "TAKE")
        self.assertTrue(all(event["trade_id"] == "robot-btc" for event in result["events"]))

    def test_missing_fill_evidence_never_creates_an_entry_or_exit(self):
        now = 1_800_000_000_000
        trade = SimpleNamespace(
            trade_id="robot-unknown", symbol=Symbol("BTCUSDT"), pattern="Mirror",
            signal_time_ms=now - 1000, entry_time_ms=now - 500,
            entry_quantity=None, average_entry=Decimal("10"),
            direction="LONG", exit_time_ms=None, exit_price=None, exit_reason=None,
        )
        store = SimpleNamespace(load_robot_trades_with_events_since=lambda account, since: (trade,))
        events = _robot_journal(SimpleNamespace(store=store), "BTCUSDT", now)["events"]
        self.assertEqual([event["kind"] for event in events], ["SIGNAL_RECORDED"])


if __name__ == "__main__":
    unittest.main()
