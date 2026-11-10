"""Pure local STOP/TAKE M1 model: pessimistic ordering, atomic fees, no IO."""
import unittest
from decimal import Decimal as D

from research.simulator_v2.timeline import MINUTE_MS, StepBlocked
from research.simulator_v2.virtual_account import VirtualAccount
from research.simulator_v2.virtual_exchange import (
    LimitRequest, MarketRequest, ProtectedLimitRequest, VirtualExchange,
)
from research.simulator_v2.session import VirtualReplaySession
from tests.test_simulator_v2_virtual_limit import bar


def exchange(balance="1000"):
    return VirtualExchange(
        account=VirtualAccount(
            simulation_run_id="safeexit", symbol="BTCUSDT",
            initial_balance=D(balance),
        ),
    )


def request(side="BUY", limit="100", stop="99", take="104", order_id="bracket"):
    return ProtectedLimitRequest(
        entry=LimitRequest(order_id, side, D("1"), D(limit)),
        stop_price=D(stop), take_price=D(take),
    )


class ProtectedM1Tests(unittest.TestCase):
    def test_long_and_short_take_after_entry_with_actual_fee_and_pnl(self):
        for side, stop, take, entry_high, entry_low, exit_high, exit_low, pnl in (
            ("BUY", "99", "104", "101", "99.5", "105", "99.5", D("4")),
            ("SELL", "101", "96", "100.5", "99", "100.5", "95", D("4")),
        ):
            with self.subTest(side=side):
                ex = exchange()
                ex.on_closed_minute(bar(0, opening="100", high="101", low="99"))
                ex.submit_protected_limit(
                    request(side, stop=stop, take=take), submitted_at_ms=MINUTE_MS,
                )
                ex.on_closed_minute(bar(
                    1, opening="100", high=entry_high, low=entry_low,
                ))
                self.assertEqual(len(ex.account.fills), 1)
                self.assertIsNotNone(ex.active_protection)
                self.assertIsNone(ex.pending)
                ex.on_closed_minute(bar(
                    2, opening="100", high=exit_high, low=exit_low,
                ))
                self.assertEqual(len(ex.account.fills), 2)
                self.assertIsNone(ex.active_protection)
                self.assertEqual(ex.account.fills[1].price, D(take))
                self.assertEqual(ex.account.fills[1].fee, D(take) * D("0.0006"))
                state = ex.account.snapshot(as_of_ms=3 * MINUTE_MS)
                self.assertEqual(state.position_quantity, 0)
                self.assertEqual(state.realized_gross_pnl, pnl)
                self.assertEqual(state.realized_net_pnl, pnl - D("100") * D("0.0006") - D(take) * D("0.0006"))
                self.assertEqual(ex.events[-1].kind, "TAKE_FILLED")

    def test_stop_wins_both_levels_same_bar_after_position_open(self):
        for side, stop, take in (("BUY", "99", "104"), ("SELL", "101", "96")):
            with self.subTest(side=side):
                ex = exchange()
                ex.on_closed_minute(bar(0, opening="100", high="101", low="99"))
                ex.submit_protected_limit(
                    request(side, stop=stop, take=take), submitted_at_ms=MINUTE_MS,
                )
                ex.on_closed_minute(bar(
                    1, opening="100", high="100.5", low="99.5",
                ))
                ex.on_closed_minute(bar(
                    2, opening="100", high="105", low="95",
                ))
                self.assertEqual(ex.events[-1].kind, "STOP_FILLED")
                self.assertEqual(ex.account.fills[-1].price, D(stop))
                self.assertEqual(ex.account.snapshot(as_of_ms=3 * MINUTE_MS).position_quantity, 0)

    def test_stop_same_entry_candle_is_two_atomic_receipts_never_fake_take(self):
        session = VirtualReplaySession(
            simulation_run_id="entry_stop", symbol="BTCUSDT",
            initial_balance=D("1000"),
        )
        session.step(bar(0, opening="100", high="101", low="99"))
        session.exchange.submit_protected_limit(
            request(), submitted_at_ms=MINUTE_MS,
        )
        state = session.step(bar(1, opening="100", high="106", low="98"))
        self.assertEqual(state.applied_fills, 2)
        self.assertEqual(state.position_quantity, 0)
        self.assertEqual(state.realized_gross_pnl, D("-1"))
        self.assertEqual([e.kind for e in session.events if e.source == "EXCHANGE"],
                         ["VIRTUAL_LIMIT_FILLED", "VIRTUAL_STOP_FILLED"])
        self.assertEqual([e.kind for e in session.exchange.events][-2:],
                         ["FILLED", "STOP_FILLED"])
        self.assertEqual(session.exchange.active_protection, None)
        self.assertEqual(session.exchange.last_minute_fills, session.account.fills)

    def test_entry_candle_take_only_is_deferred_as_order_cannot_be_proven(self):
        ex = exchange()
        ex.on_closed_minute(bar(0, opening="100", high="101", low="99"))
        ex.submit_protected_limit(
            request(), submitted_at_ms=MINUTE_MS,
        )
        ex.on_closed_minute(bar(
            1, opening="101", high="105", low="99.5",
        ))
        self.assertEqual(len(ex.account.fills), 1)
        self.assertIsNotNone(ex.active_protection)
        # If NEXT candle crosses TAKE, order can then be evaluated causally.
        ex.on_closed_minute(bar(2, opening="101", high="105", low="100"))
        self.assertEqual(ex.events[-1].kind, "TAKE_FILLED")
        self.assertEqual(len(ex.account.fills), 2)

    def test_stop_gap_uses_worse_open_not_optimistic_stop_price(self):
        for side, stop, opening in (("BUY", "99", "97"), ("SELL", "101", "103")):
            with self.subTest(side=side):
                ex = exchange()
                ex.on_closed_minute(bar(0, opening="100", high="101", low="99"))
                ex.submit_protected_limit(
                    request(side, stop=stop, take="104" if side=="BUY" else "96"),
                    submitted_at_ms=MINUTE_MS,
                )
                ex.on_closed_minute(bar(1, opening="100", high="100.5", low="99.5"))
                ex.on_closed_minute(bar(
                    2, opening=opening,
                    high=max(D(opening),D("105")),
                    low=min(D(opening),D("95")),
                    closing=opening,
                ))
                self.assertEqual(ex.account.fills[-1].price, D(opening))
                self.assertEqual(ex.events[-1].kind, "STOP_FILLED")

    def test_ambiguous_entry_and_stop_batch_rolls_back_completely_on_insufficient_balance(self):
        ex = exchange(balance="1")
        ex.on_closed_minute(bar(0, opening="100", high="101", low="99"))
        order = request(stop="90")
        ex.submit_protected_limit(order, submitted_at_ms=MINUTE_MS)
        old_events = ex.events
        with self.assertRaisesRegex(ValueError, "balance below zero"):
            ex.on_closed_minute(bar(1, opening="100", high="106", low="89"))
        self.assertEqual(ex.account.fills, ())
        self.assertEqual(ex.events, old_events)
        self.assertEqual(ex.virtual_time_ms, MINUTE_MS)
        self.assertEqual(ex.pending, order.entry)
        self.assertIsNone(ex.active_protection)
        ex.cancel_pending(order.entry.order_id, cancelled_at_ms=MINUTE_MS)
        ex.on_closed_minute(bar(1, opening="100", high="106", low="89"))
        self.assertEqual(ex.account.fills, ())

    def test_guards_protected_identity_both_sides_amend_and_new_entry_while_open(self):
        for stop,take in (("101","104"),("99","98"),("0","104")):
            with self.subTest(stop=stop,take=take):
                with self.assertRaises(ValueError):
                    request(stop=stop,take=take)
        ex = exchange()
        ex.on_closed_minute(bar(0, opening="100", high="101", low="99"))
        order = request()
        ex.submit_protected_limit(order, submitted_at_ms=MINUTE_MS)
        with self.assertRaisesRegex(ValueError, "reprice"):
            ex.amend_limit(
                LimitRequest("bracket","BUY",D("1"),D("101")),
                amended_at_ms=MINUTE_MS,
            )
        ex.on_closed_minute(bar(1,opening="100",high="100.5",low="99.5"))
        with self.assertRaisesRegex(ValueError,"protected position"):
            ex.submit(
                MarketRequest("overlap","BUY",D("1")),
                submitted_at_ms=2*MINUTE_MS,
            )
        with self.assertRaisesRegex(ValueError,"protected position"):
            ex.submit_protected_limit(
                request(order_id="other"), submitted_at_ms=2*MINUTE_MS,
            )

    def test_existing_unprotected_position_cannot_be_overlaid_by_protected_entry(self):
        ex = exchange()
        ex.on_closed_minute(bar(0, opening="100", high="101", low="99"))
        ex.submit(MarketRequest("oldopen", "BUY", D("1")), submitted_at_ms=MINUTE_MS)
        ex.on_closed_minute(bar(1, opening="100", high="101", low="99"))
        self.assertEqual(
            ex.account.snapshot(as_of_ms=2*MINUTE_MS, mark_price=D("100")).position_quantity,
            D("1"),
        )
        with self.assertRaisesRegex(ValueError, "position is open"):
            ex.submit_protected_limit(request(), submitted_at_ms=2*MINUTE_MS)
        self.assertIsNone(ex.pending)
        self.assertIsNone(ex.active_protection)
        self.assertEqual(len(ex.account.fills), 1)

    def test_protected_stop_failure_pauses_one_virtual_minute_without_false_exit(self):
        session = VirtualReplaySession(
            simulation_run_id="staged_stop", symbol="BTCUSDT",
            initial_balance=D("0.2"),
        )
        session.step(bar(0, opening="100", high="101", low="99"))
        order = request(stop="99", take="104")
        session.exchange.submit_protected_limit(order, submitted_at_ms=MINUTE_MS)
        session.step(bar(1, opening="100", high="100.5", low="99.5"))
        before = session.account.fills
        # Worse gap close would make the unlevered ledger negative.
        with self.assertRaises(StepBlocked):
            session.step(bar(2, opening="90", high="101", low="89", closing="90"))
        self.assertEqual(session.virtual_time_ms, 2*MINUTE_MS)
        self.assertEqual(session.account.fills, before)
        self.assertIsNotNone(session.exchange.active_protection)
        self.assertFalse(any(e.kind=="VIRTUAL_STOP_FILLED" for e in session.events))


if __name__ == "__main__":
    unittest.main()
