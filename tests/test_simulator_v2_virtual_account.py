"""SIMULATION-only receipt accounting; no network, Paper or exchange imports."""
import unittest
from decimal import Decimal

from research.simulator_v2.virtual_account import (
    VirtualAccount, VirtualFill,
)

D = Decimal


def receipt(
    fill_id, time_ms, side, quantity, price, fee="0",
    *, symbol="BTCUSDT", run_id="test", namespace="SIMULATION",
):
    return VirtualFill(
        simulation_run_id=run_id, symbol=symbol, fill_id=fill_id,
        virtual_time_ms=time_ms, side=side, quantity=D(quantity),
        price=D(price), fee=D(fee), namespace=namespace,
    )


class VirtualAccountTests(unittest.TestCase):
    def account(self):
        return VirtualAccount(
            simulation_run_id="test", symbol="BTCUSDT",
            initial_balance=D("1000"),
        )

    def test_open_long_mark_and_partial_close_include_fees(self):
        account = self.account()
        account.append(receipt("buy1", 100, "BUY", "2", "100", "1"))
        opened = account.snapshot(as_of_ms=100, mark_price=D("110"))
        self.assertEqual(opened.balance, D("999"))
        self.assertEqual(opened.average_entry, D("100"))
        self.assertEqual(opened.position_quantity, D("2"))
        self.assertEqual(opened.unrealized_pnl, D("20"))
        self.assertEqual(opened.equity, D("1019"))
        self.assertEqual(opened.total_net_pnl, D("19"))

        account.append(receipt("sell1", 200, "SELL", "1", "110", "1"))
        partly_closed = account.snapshot(as_of_ms=200, mark_price=D("110"))
        self.assertEqual(partly_closed.position_quantity, D("1"))
        self.assertEqual(partly_closed.realized_gross_pnl, D("10"))
        self.assertEqual(partly_closed.fees, D("2"))
        self.assertEqual(partly_closed.realized_net_pnl, D("8"))
        self.assertEqual(partly_closed.balance, D("1008"))
        self.assertEqual(partly_closed.unrealized_pnl, D("10"))
        self.assertEqual(partly_closed.equity, D("1018"))

        account.append(receipt("sell2", 300, "SELL", "1", "105", "0.5"))
        closed = account.snapshot(as_of_ms=300)
        self.assertEqual(closed.position_quantity, D("0"))
        self.assertIsNone(closed.average_entry)
        self.assertEqual(closed.balance, D("1012.5"))
        self.assertEqual(closed.equity, closed.balance)
        self.assertEqual(closed.total_net_pnl, D("12.5"))

    def test_short_average_entry_and_cover(self):
        account = self.account()
        account.append(receipt("s1", 100, "SELL", "1", "100"))
        account.append(receipt("s2", 200, "SELL", "1", "120"))
        mid = account.snapshot(as_of_ms=200, mark_price=D("90"))
        self.assertEqual(mid.position_quantity, D("-2"))
        self.assertEqual(mid.average_entry, D("110"))
        self.assertEqual(mid.unrealized_pnl, D("40"))
        account.append(receipt("b1", 300, "BUY", "2", "90", "1"))
        final = account.snapshot(as_of_ms=300)
        self.assertEqual(final.realized_gross_pnl, D("40"))
        self.assertEqual(final.balance, D("1039"))
        self.assertEqual(final.fees, D("1"))

    def test_rewind_never_reapplies_receipts(self):
        account = self.account()
        account.append(receipt("a", 100, "BUY", "1", "100", "1"))
        account.append(receipt("b", 200, "SELL", "1", "110", "1"))
        original = account.fills
        earlier = account.snapshot(as_of_ms=100, mark_price=D("101"))
        later = account.snapshot(as_of_ms=200)
        again = account.snapshot(as_of_ms=100, mark_price=D("101"))
        self.assertEqual(earlier, again)
        self.assertEqual(later.balance, D("1008"))
        self.assertEqual(account.fills, original)
        self.assertEqual(later.to_payload()["namespace"], "SIMULATION")

    def test_reject_cross_account_market_and_duplicate_receipts(self):
        account = self.account()
        with self.assertRaises(ValueError):
            account.append(receipt("x", 100, "BUY", "1", "100", symbol="ETHUSDT"))
        with self.assertRaises(ValueError):
            account.append(receipt("x", 100, "BUY", "1", "100", run_id="other"))
        with self.assertRaises(ValueError):
            receipt("x", 100, "BUY", "1", "100", namespace="PAPER")
        account.append(receipt("x", 100, "BUY", "1", "100"))
        with self.assertRaises(ValueError):
            account.append(receipt("x", 200, "BUY", "1", "101"))
        self.assertEqual(len(account.fills), 1)

    def test_reject_reverse_stale_overspend_without_partial_mutation(self):
        account = self.account()
        account.append(receipt("x", 100, "BUY", "1", "100", "1"))
        frozen = account.fills
        with self.assertRaises(ValueError):
            account.append(receipt("rev", 200, "SELL", "2", "110"))
        with self.assertRaises(ValueError):
            account.append(receipt("stale", 99, "BUY", "1", "100"))
        with self.assertRaises(ValueError):
            account.append(receipt("badfee", 200, "BUY", "1", "100", "1200"))
        self.assertEqual(account.fills, frozen)

    def test_no_position_mark_is_optional_but_open_needs_explicit_mark(self):
        account = self.account()
        self.assertEqual(account.snapshot(as_of_ms=0).equity, D("1000"))
        account.append(receipt("x", 100, "BUY", "1", "100"))
        with self.assertRaises(ValueError):
            account.snapshot(as_of_ms=100)
        self.assertEqual(account.snapshot(as_of_ms=110, mark_price=D("103")).equity,
                         D("1003"))

    def test_negative_price_quantity_and_fee_are_rejected(self):
        for qty, price, fee in [
            ("0", "100", "0"), ("1", "0", "0"),
            ("1", "100", "-1"), ("NaN", "100", "0"),
        ]:
            with self.subTest(qty=qty, price=price, fee=fee):
                with self.assertRaises(ValueError):
                    receipt("x", 100, "BUY", qty, price, fee)

    def test_balance_does_not_mean_free_margin_and_no_trading(self):
        account = self.account()
        self.assertFalse(hasattr(account, "submit_order"))
        self.assertFalse(hasattr(account, "cancel_order"))
        self.assertFalse(hasattr(account, "api"))
        account.append(receipt("x", 100, "BUY", "10", "1000"))
        self.assertEqual(account.snapshot(as_of_ms=100, mark_price=D("1000")).balance,
                         D("1000"))


if __name__ == "__main__":
    unittest.main()
