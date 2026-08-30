import tempfile
import time
import unittest
from dataclasses import replace
from decimal import Decimal
from pathlib import Path

from terminal.api.models import (
    ClientActionId,
    FullCloseCommandRequest,
    MarketCommandRequest,
    PaperStopDeleteRequest,
    PaperStopMutationRequest,
    VolumeRequest,
    VolumeUnit,
)
from terminal.domain.models import OrderSide, Price, Quantity, Symbol
from terminal.market_data.models import BookHealth, NormalizedOrderBook, PriceLevel
from terminal.runtime.paper_runtime import PaperRuntime
from tests.test_terminal_paper_runtime import _instrument


class MutableBookProvider:
    def __init__(self) -> None:
        self.update_id = "BTCUSDT:1"
        self.bid = Decimal("64249.5")
        self.ask = Decimal("64250.5")

    def get_book(self, symbol: Symbol) -> NormalizedOrderBook:
        return NormalizedOrderBook(
            symbol=symbol,
            bids=(PriceLevel(Price(self.bid), Quantity(Decimal("10"))),),
            asks=(PriceLevel(Price(self.ask), Quantity(Decimal("10"))),),
            health=BookHealth.READY,
            received_at_ms=int(time.time() * 1000),
            available_depth=1,
        )

    def get_current_book_update(self, symbol: Symbol):
        return self.update_id, self.get_book(symbol)

    def move(self, *, update_id: str, bid: str, ask: str) -> None:
        self.update_id = update_id
        self.bid = Decimal(bid)
        self.ask = Decimal(ask)


class PaperStopTriggerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.book = MutableBookProvider()
        self.runtime = PaperRuntime(
            Path(self.temp.name) / "paper.sqlite3",
            book_provider=self.book,
            instrument_snapshot=_instrument(),
        )

    def tearDown(self):
        self.runtime.close()
        self.temp.cleanup()

    def open_position(self, side: OrderSide, action_id: str, amount: str = "321") -> None:
        self.runtime.api.market(MarketCommandRequest(
            ClientActionId(action_id), "BTCUSDT", side,
            VolumeRequest(VolumeUnit.USDT, Decimal(amount)), Decimal("64250"),
            "Percent", Decimal("0.5"),
        ))

    def create_stop(self, action_id: str, price: str) -> None:
        self.runtime.create_stop(PaperStopMutationRequest(
            ClientActionId(action_id), "BTCUSDT", Decimal(price),
        ))

    def test_long_stop_closes_current_quantity_and_clears_all_protection_atomically(self):
        self.open_position(OrderSide.BUY, "long-open")
        self.create_stop("long-stop", "64000")
        key = self.runtime._context.context_for("BTCUSDT").pretrade.position_key
        current = self.runtime.store.get_protection_projection(key)
        self.runtime.store.upsert_protection_projection(
            replace(current, take_profit=Decimal("65000")),
            expected_version=current.version,
        )
        before = self.runtime.paper_state("BTCUSDT")
        expected_quantity = Decimal(before["position_quantity"])
        execution_count = len(self.runtime.store.load_executions())

        self.book.move(update_id="BTCUSDT:2", bid="63999.5", ask="64000.5")
        applied = self.runtime.process_orderbook_update("BTCUSDT:2")
        after = self.runtime.paper_state("BTCUSDT")

        self.assertEqual(applied, 1)
        self.assertEqual(len(self.runtime.store.load_executions()), execution_count + 1)
        self.assertEqual(self.runtime.store.load_executions()[-1].quantity.value, expected_quantity)
        self.assertEqual(after["position_side"], "Flat")
        self.assertEqual(after["position_quantity"], "0")
        self.assertIsNone(after["protection"]["stop_loss"])
        self.assertIsNone(after["protection"]["take_profit"])
        self.assertEqual(after["state_revision"], before["state_revision"] + 1)

        self.assertEqual(self.runtime.process_orderbook_update("BTCUSDT:2"), 0)
        self.book.move(update_id="BTCUSDT:3", bid="63900", ask="63900.5")
        self.assertEqual(self.runtime.process_orderbook_update("BTCUSDT:3"), 0)
        self.assertEqual(len(self.runtime.store.load_executions()), execution_count + 1)

    def test_short_stop_closes_without_reversing(self):
        self.open_position(OrderSide.SELL, "short-open")
        self.create_stop("short-stop", "64500")
        before = self.runtime.paper_state("BTCUSDT")
        expected_quantity = Decimal(before["position_quantity"])

        self.book.move(update_id="BTCUSDT:4", bid="64500", ask="64500.5")
        self.assertEqual(self.runtime.process_orderbook_update("BTCUSDT:4"), 1)
        after = self.runtime.paper_state("BTCUSDT")

        self.assertEqual(self.runtime.store.load_executions()[-1].side, OrderSide.BUY)
        self.assertEqual(self.runtime.store.load_executions()[-1].quantity.value, expected_quantity)
        self.assertEqual(after["position_side"], "Flat")
        self.assertEqual(after["position_quantity"], "0")

    def test_stop_uses_remaining_authoritative_quantity_after_partial_close(self):
        self.open_position(OrderSide.BUY, "partial-open")
        self.create_stop("partial-stop", "64000")
        self.open_position(OrderSide.SELL, "partial-close", amount="100")
        before = self.runtime.paper_state("BTCUSDT")
        remaining = Decimal(before["position_quantity"])
        self.assertGreater(remaining, 0)

        self.book.move(update_id="BTCUSDT:5", bid="63999.5", ask="64000.5")
        self.runtime.process_orderbook_update("BTCUSDT:5")

        stop_execution = self.runtime.store.load_executions()[-1]
        self.assertEqual(stop_execution.side, OrderSide.SELL)
        self.assertEqual(stop_execution.quantity.value, remaining)
        self.assertEqual(self.runtime.paper_state("BTCUSDT")["position_side"], "Flat")

    def test_manual_close_wins_before_trigger_and_stale_stop_never_executes(self):
        self.open_position(OrderSide.BUY, "race-open")
        self.create_stop("race-stop", "64000")
        self.runtime.api.full_close(FullCloseCommandRequest(
            ClientActionId("race-manual-close"), "BTCUSDT",
        ))
        executions_after_close = len(self.runtime.store.load_executions())
        state_after_close = self.runtime.paper_state("BTCUSDT")
        self.assertIsNone(state_after_close["protection"]["stop_loss"])

        self.book.move(update_id="BTCUSDT:6", bid="63999.5", ask="64000.5")
        self.assertEqual(self.runtime.process_orderbook_update("BTCUSDT:6"), 0)
        self.assertEqual(len(self.runtime.store.load_executions()), executions_after_close)
        self.assertEqual(self.runtime.paper_state("BTCUSDT")["position_side"], "Flat")

    def test_stale_stop_on_flat_is_cleaned_without_execution(self):
        key = self.runtime._context.context_for("BTCUSDT").pretrade.position_key
        self.runtime.store.mutate_paper_stop(
            client_action_id="seed-stale-stop",
            request_fingerprint="seed-stale-stop",
            operation="create",
            position_key=key,
            stop_loss=Decimal("64000"),
            updated_at_ms=1,
        )
        before_revision = self.runtime.paper_state("BTCUSDT")["state_revision"]

        self.book.move(update_id="BTCUSDT:7", bid="63999.5", ask="64000.5")
        self.assertEqual(self.runtime.process_orderbook_update("BTCUSDT:7"), 0)
        state = self.runtime.paper_state("BTCUSDT")

        self.assertEqual(self.runtime.store.load_executions(), ())
        self.assertIsNone(state["protection"]["stop_loss"])
        self.assertEqual(state["state_revision"], before_revision + 1)

    def test_delete_serialized_before_book_update_prevents_trigger(self):
        self.open_position(OrderSide.BUY, "delete-race-open")
        self.create_stop("delete-race-stop", "64000")
        self.runtime.delete_stop(PaperStopDeleteRequest(
            ClientActionId("delete-race-delete"), "BTCUSDT",
        ))
        before = len(self.runtime.store.load_executions())

        self.book.move(update_id="BTCUSDT:8", bid="63999.5", ask="64000.5")
        self.assertEqual(self.runtime.process_orderbook_update("BTCUSDT:8"), 0)
        self.assertEqual(len(self.runtime.store.load_executions()), before)


if __name__ == "__main__":
    unittest.main()
