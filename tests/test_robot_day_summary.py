"""Read-only PAPER Robot day accounting: no Diary/manual trade mixing."""
from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from types import SimpleNamespace
from unittest import TestCase

from terminal.runtime.paper_http_server import _robot_day_summary


def trade(exit_ms, gross="3.125", fees="0.625", quantity="10"):
    return SimpleNamespace(
        exit_time_ms=exit_ms,
        realized_pnl_usdt=Decimal(gross) if gross is not None else None,
        fees_costs_usdt=Decimal(fees) if fees is not None else None,
        entry_quantity=Decimal(quantity) if quantity is not None else None,
    )


class RobotDaySummaryTests(TestCase):
    @classmethod
    def setUpClass(cls):
        cls.now_ms = int(datetime(2026, 10, 19, 12, tzinfo=timezone.utc).timestamp() * 1000)
        cls.day_start_ms = int(datetime(2026, 10, 18, 21, tzinfo=timezone.utc).timestamp() * 1000)

    def project(self, rows):
        seen = []

        class Store:
            def load_robot_trades_with_events_since(self, account, since_ms):
                seen.append((account.value, since_ms))
                return rows

        summary = _robot_day_summary(SimpleNamespace(store=Store()), self.now_ms)
        self.assertEqual(seen, [("paper", self.day_start_ms)])
        self.assertEqual(summary["source"], "robot_trades")
        self.assertEqual(summary["account_id"], "paper")
        self.assertEqual(summary["day_start_ms"], self.day_start_ms)
        return summary

    def test_closed_only_and_fee_aware_net_at_msk_midnight(self):
        summary = self.project([
            trade(self.day_start_ms, gross="2.50", fees="0.25"),
            trade(self.now_ms, gross="-1.125", fees="0.125"),
            trade(self.day_start_ms - 1, gross="999", fees="0"),
            trade(self.now_ms + 1, gross="999", fees="0"),
            trade(None, gross="999", fees="0"),
        ])
        self.assertEqual(summary["closed_trades"], 2)
        self.assertEqual(summary["trades_without_pnl"], 0)
        self.assertEqual(Decimal(summary["net_pnl_usdt"]), Decimal("1.000"))

    def test_incomplete_close_never_fabricates_net_or_hides_trade_count(self):
        summary = self.project([
            trade(self.day_start_ms + 1),
            trade(self.day_start_ms + 2, fees=None),
            trade(self.day_start_ms + 3, quantity=None),
            trade(self.day_start_ms + 4, fees="-1"),
        ])
        self.assertEqual(summary["closed_trades"], 4)
        self.assertEqual(summary["trades_without_pnl"], 3)
        self.assertIsNone(summary["net_pnl_usdt"])

    def test_empty_day_is_a_proven_zero_not_missing(self):
        summary = self.project([trade(self.day_start_ms - 1)])
        self.assertEqual(summary["closed_trades"], 0)
        self.assertEqual(summary["trades_without_pnl"], 0)
        self.assertEqual(summary["net_pnl_usdt"], "0")
