"""Focused event-time SIMULATION matching, never OHLC or real exchange claims."""
from __future__ import annotations

from decimal import Decimal as D
import unittest

from robot_entry_flow_evidence import TakerPrint
from research.historical_market_replay import Candle
from research.simulator_v2.historical_orderbook import BookState
from research.simulator_v2.cache import _checksum, _rows
from research.simulator_v2.history import HistoryChunk
from research.simulator_v2.report import run_verified_chunks
from research.simulator_v2.session import VirtualReplaySession
from research.simulator_v2.virtual_account import VirtualAccount
from research.simulator_v2.virtual_exchange import (
    LimitRequest, MarketRequest, ProtectedLimitRequest, VirtualExchange,
    L2PartialTakePolicy,
)


M = 60_000


def minute(start: int, *, low="1", high="200") -> Candle:
    return Candle(
        start_ms=start, interval_ms=M, open=D("100"), high=D(high),
        low=D(low), close=D("100"), volume=D("10"),
    )


def book(at: int, *, bid="99", ask="101", bid_size="10", ask_size="10") -> BookState:
    return BookState(
        symbol="ICNTUSDT", available_at_ms=at, engine_at_ms=at - 1,
        update_id=at, sequence=at,
        bids=((D(bid), D(bid_size)),), asks=((D(ask), D(ask_size)),),
    )


def print_at(at: int, side: str, price: str) -> TakerPrint:
    return TakerPrint("ICNTUSDT", f"trade_{at}", at, side, D(price), D("1"))


def venue() -> VirtualExchange:
    account = VirtualAccount(
        simulation_run_id="l2_replay", symbol="ICNTUSDT",
        initial_balance=D("1000"),
    )
    ex = VirtualExchange(account=account, execution_mode="HISTORICAL_L2")
    ex.on_closed_minute(minute(0))
    return ex


def submit(ex: VirtualExchange, *, side="BUY", entry="100", stop="99", take="103"):
    request = ProtectedLimitRequest(
        LimitRequest("order1", side, D("1"), D(entry)), D(stop), D(take),
    )
    ex.submit_protected_limit(request, submitted_at_ms=M)


def partial_venue(*, slip="0.005") -> VirtualExchange:
    account = VirtualAccount(
        simulation_run_id="l2_partial_replay", symbol="ICNTUSDT",
        initial_balance=D("1000"),
    )
    ex = VirtualExchange(
        account=account, execution_mode="HISTORICAL_L2",
        l2_partial_take_policy=L2PartialTakePolicy(
            potential_fraction=D("0.5"), quantity_fraction=D("0.25"),
            quantity_step=D("1"), tick_size=D("0.1"),
            stop_slippage_fraction=D(slip),
        ),
    )
    ex.on_closed_minute(minute(0))
    return ex


def submit_100(ex, *, side="BUY", stop="99", take="104"):
    ex.submit_protected_limit(
        ProtectedLimitRequest(
            LimitRequest("partial_order", side, D("100"), D("100")),
            D(stop), D(take),
        ),
        submitted_at_ms=M,
    )


class L2PartialTakeAndBERegressionTests(unittest.TestCase):
    def test_long_partial_then_next_book_be_then_stop_remainder(self):
        ex = partial_venue()
        submit_100(ex)
        entry = ex.on_historical_book(book(
            M + 10, bid="99.9", ask="100", ask_size="200",
        ))
        self.assertEqual(entry.quantity, D("100"))
        self.assertEqual(entry.fee, D("6"))
        partial = ex.on_historical_book(book(
            M + 20, bid="102.1", ask="102.2", bid_size="200",
        ))
        self.assertEqual(partial.quantity, D("25"))
        self.assertEqual(partial.price, D("102.0"))
        self.assertEqual(partial.fee, D("1.53000"))
        self.assertEqual(ex.account.snapshot(
            as_of_ms=M+20, mark_price=D("102.1"),
        ).position_quantity, D("75"))
        self.assertEqual(ex.l2_be_stop_amendments, 0)
        ex.on_historical_book(book(
            M + 30, bid="102.5", ask="102.6", bid_size="200",
        ))
        self.assertEqual(ex.l2_be_stop_amendments, 1)
        self.assertGreater(ex._l2_current_stop(ex.active_protection), D("100"))
        ex.on_historical_book(book(
            M + 40, bid="100.0", ask="100.2", bid_size="200",
        ))
        stop = ex.on_historical_trade(print_at(M + 50, "Sell", "100.0"))
        self.assertEqual(stop.quantity, D("75"))
        self.assertEqual(stop.price, D("100.0"))
        self.assertEqual(ex.account.snapshot(as_of_ms=M+50).position_quantity, 0)
        self.assertEqual([e.kind for e in ex.events][-3:], [
            "PARTIAL_TAKE_FILLED", "STOP_AMENDED_BE", "STOP_FILLED",
        ])
        self.assertEqual(ex.account.snapshot(as_of_ms=M+50).realized_net_pnl,
                         D("37.9700000"))

    def test_short_partial_and_be_stop_only_tightens(self):
        ex = partial_venue(slip="0")
        submit_100(ex, side="SELL", stop="101", take="96")
        entry = ex.on_historical_book(book(
            M+10, bid="100", ask="100.1", bid_size="200",
        ))
        self.assertEqual(entry.side, "SELL")
        partial = ex.on_historical_book(book(
            M+20, bid="97.8", ask="97.9", ask_size="200",
        ))
        self.assertEqual(partial.quantity, D("25"))
        self.assertEqual(partial.side, "BUY")
        self.assertEqual(partial.price, D("98.0"))
        ex.on_historical_book(book(
            M+30, bid="97.4", ask="97.5", ask_size="200",
        ))
        self.assertEqual(ex.l2_be_stop_amendments, 1)
        current = ex._l2_current_stop(ex.active_protection)
        self.assertLess(current, D("101"))
        self.assertGreater(current, D("97.5"))
        ex.on_historical_book(book(
            M+40, bid="100.6", ask="100.8", ask_size="200",
        ))
        close = ex.on_historical_trade(print_at(M+50, "Buy", "100.8"))
        self.assertEqual(close.quantity, D("75"))
        self.assertEqual(ex.account.snapshot(as_of_ms=M+40).position_quantity, 0)

    def test_partial_market_book_needs_full_depth_and_stop_stays(self):
        ex = partial_venue()
        submit_100(ex)
        ex.on_historical_book(book(M+10, bid="99", ask="100", ask_size="200"))
        self.assertIsNone(ex.on_historical_book(book(
            M+20, bid="102.1", ask="102.2", bid_size="5",
        )))
        self.assertEqual(ex.l2_partial_take_fills, 0)
        self.assertEqual(ex.l2_partial_depth_unproven_count, 1)
        self.assertEqual(ex.account.snapshot(
            as_of_ms=M+20, mark_price=D("102.1"),
        ).position_quantity, D("100"))
        stopbook = book(M+30, bid="98.9", ask="99.0", bid_size="200")
        ex.on_historical_book(stopbook)
        stop = ex.on_historical_trade(print_at(M+40, "Sell", "98.9"))
        self.assertEqual(stop.quantity, D("100"))
        self.assertEqual(ex.l2_be_stop_amendments, 0)

    def test_same_ms_partial_book_and_taker_is_fail_closed(self):
        ex = partial_venue()
        submit_100(ex)
        ex.on_historical_book(book(M+10, bid="99", ask="100", ask_size="200"))
        with self.assertRaisesRegex(ValueError, "partial TAKE chronology"):
            ex.on_historical_same_ms_inert_bucket(
                books=(book(M+20, bid="102.1", ask="102.2", bid_size="200"),),
                trades=(print_at(M+20, "Buy", "101"),),
            )
        self.assertEqual(len(ex.account.fills), 1)
        self.assertEqual(ex.l2_partial_take_fills, 0)

    def test_old_l2_and_ohlc_cannot_silently_enable_partial(self):
        ex = venue()
        submit_100(ex)
        ex.on_historical_book(book(M+10, bid="99", ask="100", ask_size="200"))
        ex.on_historical_book(book(M+20, bid="102.1", ask="102.2", bid_size="200"))
        self.assertEqual(len(ex.account.fills), 1)
        self.assertEqual(ex.l2_partial_take_fills, 0)
        with self.assertRaisesRegex(ValueError, "HISTORICAL_L2 only"):
            VirtualExchange(
                account=ex.account, execution_mode="OHLC_M1",
                l2_partial_take_policy=L2PartialTakePolicy(
                    D("0.5"), D("0.25"), D("1"), D("0.1"),
                ),
            )


class EventTimeMatchingTests(unittest.TestCase):
    def test_touch_is_not_fill_then_trade_through_and_stop_from_book(self):
        ex = venue()
        submit(ex)
        self.assertIsNone(ex.on_historical_book(book(M + 10)))
        self.assertIsNone(ex.on_historical_trade(print_at(M + 20, "Sell", "100")))
        self.assertIsNotNone(ex.pending)
        receipt = ex.on_historical_trade(print_at(M + 30, "Sell", "99.9"))
        self.assertEqual(receipt.virtual_time_ms, M + 30)
        self.assertEqual(receipt.price, D("100"))
        self.assertEqual(receipt.fee, D("0.02"))  # maker 0.02%
        self.assertIsNotNone(ex.active_protection)
        self.assertIsNone(ex.on_historical_book(book(M + 40, bid="98.8", ask="99.1")))
        close = ex.on_historical_trade(print_at(M + 50, "Sell", "98.9"))
        self.assertEqual(close.virtual_time_ms, M + 50)
        self.assertEqual(close.price, D("98.8"))  # marketable STOP slips to L2
        self.assertEqual([e.kind for e in ex.events][-2:], ["FILLED", "STOP_FILLED"])
        ex.on_closed_minute(minute(M, low="50", high="150"))
        self.assertEqual(ex.account.snapshot(as_of_ms=2*M).position_quantity, 0)

    def test_stop_triggers_on_trade_but_fills_only_after_fresh_l2_quote(self):
        ex = venue()
        submit(ex)
        ex.on_historical_book(book(M + 10, bid="99.9", ask="100"))
        self.assertIsNone(ex.on_historical_trade(print_at(M + 20, "Sell", "98.9")))
        self.assertTrue(ex.l2_stop_pending)
        self.assertIsNotNone(ex.active_protection)
        self.assertEqual(len(ex.account.fills), 1)
        self.assertIn("STOP_TRIGGER_DEFERRED", [e.kind for e in ex.events])
        self.assertIsNone(ex.on_historical_book(
            book(M + 30, bid="99", ask="99.1"),
        ))  # Still too optimistic relative to triggering print
        self.assertTrue(ex.l2_stop_pending)
        fill = ex.on_historical_book(book(M + 40, bid="98.8", ask="99.1"))
        self.assertEqual(fill.price, D("98.8"))
        self.assertEqual(fill.virtual_time_ms, M + 40)
        self.assertEqual(ex.l2_deferred_stop_count, 1)
        self.assertFalse(ex.l2_stop_pending)
        self.assertIsNone(ex.active_protection)
        self.assertEqual([e.kind for e in ex.events][-2:],
                         ["STOP_TRIGGER_DEFERRED", "STOP_FILLED"])
        self.assertEqual(ex.account.snapshot(as_of_ms=M + 40).position_quantity, 0)

    def test_deferred_stop_cannot_fill_from_late_or_insufficient_l2(self):
        ex = venue()
        submit(ex)
        ex.on_historical_book(book(M + 10, bid="99.9", ask="100"))
        ex.on_historical_trade(print_at(M + 20, "Sell", "98.9"))
        with self.assertRaisesRegex(ValueError, "executable depth"):
            ex.on_historical_book(book(
                M + 30, bid="98.8", ask="99.1", bid_size="0.1",
            ))
        self.assertTrue(ex.l2_stop_pending)
        self.assertEqual(len(ex.account.fills), 1)
        with self.assertRaisesRegex(ValueError, "within 250ms"):
            ex.on_historical_book(book(M + 300, bid="98.8", ask="99.1"))
        self.assertTrue(ex.l2_stop_pending)
        self.assertEqual(len(ex.account.fills), 1)
        self.assertIsNotNone(ex.active_protection)

    def test_deferred_short_stop_does_not_use_pre_trigger_good_ask(self):
        ex = venue()
        submit(ex, side="SELL", entry="100", stop="101", take="97")
        ex.on_historical_book(book(M + 10, bid="100", ask="100.1"))
        self.assertEqual(len(ex.account.fills), 1)
        self.assertIsNone(ex.on_historical_trade(print_at(M + 20, "Buy", "101.2")))
        self.assertTrue(ex.l2_stop_pending)
        fill = ex.on_historical_book(book(M + 40, bid="100.9", ask="101.3"))
        self.assertEqual(fill.price, D("101.3"))
        self.assertEqual(fill.side, "BUY")
        self.assertEqual(ex.account.snapshot(as_of_ms=M + 40).position_quantity, 0)

    def test_deferred_stop_tracks_worst_print_before_fill(self):
        ex = venue()
        submit(ex)
        ex.on_historical_book(book(M + 10, bid="99.9", ask="100"))
        ex.on_historical_trade(print_at(M + 20, "Sell", "98.9"))
        self.assertIsNone(ex.on_historical_trade(print_at(M + 30, "Sell", "98.5")))
        self.assertIsNone(ex.on_historical_book(book(M + 40, bid="98.8", ask="99.1")))
        self.assertTrue(ex.l2_stop_pending)
        fill = ex.on_historical_book(book(M + 50, bid="98.4", ask="99.1"))
        self.assertEqual(fill.price, D("98.4"))
        self.assertFalse(ex.l2_stop_pending)

    def test_historic_book_marketable_limit_and_trade_through_take(self):
        ex = venue()
        submit(ex)
        fill = ex.on_historical_book(book(M + 10, bid="99.9", ask="100"))
        self.assertEqual(fill.virtual_time_ms, M + 10)
        self.assertEqual(fill.price, D("100"))
        self.assertEqual(fill.fee, D("0.06"))  # taker 0.06%
        self.assertIsNone(ex.on_historical_trade(print_at(M + 20, "Buy", "103")))
        take = ex.on_historical_trade(print_at(M + 30, "Buy", "103.1"))
        self.assertEqual(take.price, D("103"))
        self.assertEqual(take.fee, D("0.0206"))
        self.assertEqual([e.kind for e in ex.events][-2:], ["FILLED", "TAKE_FILLED"])

    def test_m1_high_low_never_create_l2_fill(self):
        ex = venue()
        submit(ex)
        ex.on_closed_minute(minute(M, low="0.1", high="10000"))
        self.assertIsNotNone(ex.pending)
        self.assertEqual(len(ex.account.fills), 0)
        self.assertEqual([e.kind for e in ex.events], ["SUBMITTED"])

    def test_missing_book_depth_keeps_limit_pending_and_marks_uncertainty(self):
        ex = venue()
        submit(ex)
        self.assertIsNone(ex.on_historical_book(book(
            M + 10, bid="99", ask="99.9", ask_size="0.1",
        )))
        self.assertIsNotNone(ex.pending)
        self.assertEqual(ex.account.fills, ())
        self.assertEqual(ex.l2_unproven_entry_depth_count, 1)
        self.assertIn("DEPTH_UNPROVEN", [e.kind for e in ex.events])
        filled = ex.on_historical_book(book(
            M + 20, bid="99", ask="99.9", ask_size="2",
        ))
        self.assertIsNotNone(filled)
        self.assertEqual(filled.price, D("99.9"))
        self.assertEqual(ex.l2_unproven_entry_depth_count, 1)

    def test_stop_exit_still_fails_closed_on_insufficient_book_depth(self):
        ex = venue()
        submit(ex)
        ex.on_historical_book(book(M + 10, bid="99.9", ask="100"))
        self.assertEqual(len(ex.account.fills), 1)
        self.assertIsNotNone(ex.active_protection)
        ex.on_historical_book(book(
            M + 20, bid="98.8", ask="99.1", bid_size="0.1",
        ))
        with self.assertRaisesRegex(ValueError, "executable depth"):
            ex.on_historical_trade(print_at(M + 30, "Sell", "98.9"))
        self.assertIsNotNone(ex.active_protection)
        self.assertEqual(len(ex.account.fills), 1)

    def test_inert_cross_channel_tie_does_not_block_flat_replay(self):
        ex = venue()
        at = M + 10
        b = book(at)
        ex.on_historical_same_ms_inert_bucket(
            books=(b,), trades=(print_at(at, "Buy", "100"),),
        )
        self.assertEqual(ex._l2_book, b)
        self.assertEqual(ex.account.fills, ())
        self.assertIsNone(ex.on_historical_trade(print_at(at + 10, "Sell", "100")))

    def test_inert_cross_channel_tie_with_pending_untriggered_order(self):
        ex = venue()
        submit(ex)
        at = M + 10
        b = book(at, bid="99.0", ask="101.0")
        ex.on_historical_same_ms_inert_bucket(
            books=(b,), trades=(print_at(at, "Sell", "100"),),
        )
        self.assertEqual(ex._l2_book, b)
        self.assertIsNotNone(ex.pending)
        self.assertEqual(ex.account.fills, ())

    def test_actionable_book_tie_blocks_before_order_or_ledger_update(self):
        ex = venue()
        submit(ex)
        at = M + 10
        with self.assertRaisesRegex(ValueError, "marketable entry chronology"):
            ex.on_historical_same_ms_inert_bucket(
                books=(book(at, ask="100"),),
                trades=(print_at(at, "Sell", "100"),),
            )
        self.assertIsNone(ex._l2_book)
        self.assertIsNotNone(ex.pending)
        self.assertEqual(ex.account.fills, ())

    def test_actionable_trade_tie_with_stop_blocks_before_ledger_update(self):
        ex = venue()
        submit(ex)
        ex.on_historical_book(book(M + 10, bid="99.9", ask="100"))
        previous = ex._l2_book
        at = M + 20
        with self.assertRaisesRegex(ValueError, "protected exit chronology"):
            ex.on_historical_same_ms_inert_bucket(
                books=(book(at, bid="98.8", ask="99.1"),),
                trades=(print_at(at, "Sell", "98.9"),),
            )
        self.assertEqual(ex._l2_book, previous)
        self.assertEqual(len(ex.account.fills), 1)
        self.assertIsNotNone(ex.active_protection)

    def test_cross_channel_timestamp_tie_is_ambiguous(self):
        ex = venue()
        submit(ex)
        ex.on_historical_book(book(M + 10))
        with self.assertRaisesRegex(ValueError, "ambiguous"):
            ex.on_historical_trade(print_at(M + 10, "Sell", "99"))

    def test_same_ms_unordered_prints_no_false_block_or_touch_fill(self):
        ex = venue()
        submit(ex)
        ex.on_historical_book(book(M + 10))
        group = (
            TakerPrint("ICNTUSDT", "same_ms_one", M + 20, "Sell", D("100"), D("1")),
            TakerPrint("ICNTUSDT", "same_ms_two", M + 20, "Sell", D("100"), D("2")),
        )
        self.assertIsNone(ex.on_historical_trade_batch(group))
        self.assertIsNotNone(ex.pending)
        self.assertEqual(ex.account.fills, ())

    def test_same_ms_unambiguous_trade_through_is_one_fill(self):
        ex = venue()
        submit(ex)
        ex.on_historical_book(book(M + 10))
        group = (
            TakerPrint("ICNTUSDT", "same_ms_one", M + 20, "Sell", D("99.9"), D("2")),
            TakerPrint("ICNTUSDT", "same_ms_two", M + 20, "Sell", D("99.8"), D("1")),
        )
        filled = ex.on_historical_trade_batch(group)
        self.assertEqual(filled.price, D("100"))
        self.assertEqual(filled.virtual_time_ms, M + 20)
        self.assertEqual(len(ex.account.fills), 1)
        self.assertIsNotNone(ex.active_protection)

    def test_same_ms_entry_stop_is_ambiguous_and_leaves_ledger_unchanged(self):
        ex = venue()
        submit(ex)
        ex.on_historical_book(book(M + 10))
        group = (
            TakerPrint("ICNTUSDT", "same_ms_one", M + 20, "Sell", D("99.9"), D("2")),
            TakerPrint("ICNTUSDT", "same_ms_two", M + 20, "Sell", D("98.5"), D("1")),
        )
        with self.assertRaisesRegex(ValueError, "entry/exit order"):
            ex.on_historical_trade_batch(group)
        self.assertEqual(ex.account.fills, ())
        self.assertIsNotNone(ex.pending)

    def test_same_ms_stop_take_is_ambiguous_and_leaves_protection(self):
        ex = venue()
        submit(ex)
        ex.on_historical_book(book(M + 10, bid="99.9", ask="100"))
        self.assertIsNotNone(ex.active_protection)
        group = (
            TakerPrint("ICNTUSDT", "same_ms_stop", M + 20, "Sell", D("98.9"), D("1")),
            TakerPrint("ICNTUSDT", "same_ms_take", M + 20, "Buy", D("103.1"), D("1")),
        )
        with self.assertRaisesRegex(ValueError, "STOP/TAKE order"):
            ex.on_historical_trade_batch(group)
        self.assertEqual(len(ex.account.fills), 1)
        self.assertIsNotNone(ex.active_protection)

    def test_resting_limit_does_not_fill_from_book_touch(self):
        ex = venue()
        submit(ex)
        ex.on_historical_book(book(M + 10, bid="100", ask="100.1"))
        self.assertIsNotNone(ex.pending)
        self.assertEqual(ex.account.fills, ())

    def test_no_ohlc_market_fallback(self):
        ex = venue()
        ex.submit(MarketRequest("market1", "BUY", D("1")), submitted_at_ms=M)
        with self.assertRaisesRegex(ValueError, "OHLC MARKET"):
            ex.on_historical_book(book(M + 10))
        self.assertEqual(ex.account.fills, ())

    def test_runner_feeds_l2_before_committing_next_candle(self):
        session = VirtualReplaySession(
            simulation_run_id="l2_session", symbol="ICNTUSDT",
            initial_balance=D("1000"), execution_mode="HISTORICAL_L2",
        )
        candles = (minute(0), minute(M), minute(2*M))
        chunk = HistoryChunk(
            symbol="ICNTUSDT", start_ms=0, end_ms=3*M,
            source_id="TEST_ORIGINAL_M1", candles=candles,
            sha256=_checksum(_rows(candles)),
        )

        def on_close(active, candle):
            if candle.end_ms == M:
                active.exchange.submit_protected_limit(
                    ProtectedLimitRequest(
                        LimitRequest("order1", "BUY", D("1"), D("100")),
                        D("99"), D("103"),
                    ), submitted_at_ms=candle.end_ms,
                )

        def feed(active, candle):
            if candle.start_ms == M:
                active.exchange.on_historical_book(
                    book(M + 10, bid="99.9", ask="100")
                )
                active.exchange.on_historical_trade(print_at(M + 20, "Buy", "103.1"))

        report = run_verified_chunks(
            session, (chunk,), on_committed_m1=on_close,
            on_before_m1=feed,
        )
        self.assertEqual(report.virtual_fills, 2)
        self.assertEqual([fill.virtual_time_ms for fill in session.account.fills],
                         [M + 10, M + 20])
        self.assertEqual(report.final_position_quantity, 0)
        self.assertEqual([e.kind for e in session.exchange.events][-2:],
                         ["FILLED", "TAKE_FILLED"])

    def test_l2_runner_rejects_unverified_feed(self):
        session = VirtualReplaySession(
            simulation_run_id="l2_missing_feed", symbol="ICNTUSDT",
            initial_balance=D("1000"), execution_mode="HISTORICAL_L2",
        )
        candles = (minute(0),)
        chunk = HistoryChunk(
            symbol="ICNTUSDT", start_ms=0, end_ms=M,
            source_id="TEST_ORIGINAL_M1", candles=candles,
            sha256=_checksum(_rows(candles)),
        )
        with self.assertRaisesRegex(ValueError, "verified event feeder"):
            run_verified_chunks(session, (chunk,))


if __name__ == "__main__":
    unittest.main()
