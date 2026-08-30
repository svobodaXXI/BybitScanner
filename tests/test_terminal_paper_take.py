import tempfile
import unittest
from decimal import Decimal
from pathlib import Path

from terminal.api.models import ClientActionId, MarketCommandRequest, PaperStopDeleteRequest, PaperStopMutationRequest, VolumeRequest, VolumeUnit
from terminal.domain.models import OrderSide
from terminal.runtime.paper_runtime import PaperRuntime
from tests.test_terminal_paper_runtime import _instrument
from tests.test_terminal_paper_stop_trigger import MutableBookProvider


class PaperTakeTests(unittest.TestCase):
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

    def open(self, side: OrderSide, action: str):
        self.runtime.api.market(MarketCommandRequest(
            ClientActionId(action), "BTCUSDT", side,
            VolumeRequest(VolumeUnit.USDT, Decimal("321")), Decimal("64250"),
            "Percent", Decimal("0.5"),
        ))

    def take(self, action: str, price: str):
        return self.runtime.create_take(PaperStopMutationRequest(
            ClientActionId(action), "BTCUSDT", Decimal(price),
        ))

    def test_take_crud_coexists_with_stop(self):
        self.open(OrderSide.BUY, "open-coexist")
        self.runtime.create_stop(PaperStopMutationRequest(
            ClientActionId("stop-coexist"), "BTCUSDT", Decimal("64000"),
        ))
        request = PaperStopMutationRequest(
            ClientActionId("take-create"), "BTCUSDT", Decimal("65000.24"),
        )
        self.runtime.create_take(request)
        replay = self.runtime.create_take(request)
        created = self.runtime.paper_state("BTCUSDT")
        self.assertEqual(created["protection"]["stop_loss"], "64000")
        self.assertEqual(created["protection"]["take_profit"], "65000.5")
        self.assertEqual(created["protection"]["effective_quantity"], created["position_quantity"])
        self.assertEqual(replay.reason_code, "duplicate_action")

        self.runtime.amend_take(PaperStopMutationRequest(
            ClientActionId("take-amend"), "BTCUSDT", Decimal("65100.24"),
        ))
        self.assertEqual(self.runtime.paper_state("BTCUSDT")["protection"]["take_profit"], "65100.5")
        self.runtime.delete_take(PaperStopDeleteRequest(ClientActionId("take-delete"), "BTCUSDT"))
        deleted = self.runtime.paper_state("BTCUSDT")["protection"]
        self.assertIsNone(deleted["take_profit"])
        self.assertEqual(deleted["stop_loss"], "64000")

    def test_long_take_closes_current_quantity_once_and_clears_aggregate(self):
        self.open(OrderSide.BUY, "open-long-take")
        self.runtime.create_stop(PaperStopMutationRequest(
            ClientActionId("long-sibling-stop"), "BTCUSDT", Decimal("64000"),
        ))
        self.take("long-take", "65000")
        before = self.runtime.paper_state("BTCUSDT")
        expected = Decimal(before["position_quantity"])
        count = len(self.runtime.store.load_executions())

        self.book.move(update_id="BTCUSDT:take-long", bid="65000", ask="65000.5")
        self.assertEqual(self.runtime.process_orderbook_update("BTCUSDT:take-long"), 1)
        after = self.runtime.paper_state("BTCUSDT")
        execution = self.runtime.store.load_executions()[-1]
        self.assertEqual(execution.side, OrderSide.SELL)
        self.assertEqual(execution.quantity.value, expected)
        self.assertEqual(after["position_side"], "Flat")
        self.assertIsNone(after["protection"]["take_profit"])
        self.assertIsNone(after["protection"]["stop_loss"])
        self.assertEqual(after["state_revision"], before["state_revision"] + 1)
        self.assertEqual(len(self.runtime.store.load_executions()), count + 1)
        self.assertEqual(self.runtime.process_orderbook_update("BTCUSDT:take-long"), 0)

    def test_short_take_closes_without_reverse_exposure(self):
        self.open(OrderSide.SELL, "open-short-take")
        self.take("short-take", "63500")
        expected = Decimal(self.runtime.paper_state("BTCUSDT")["position_quantity"])
        self.book.move(update_id="BTCUSDT:take-short", bid="63499.5", ask="63500")
        self.assertEqual(self.runtime.process_orderbook_update("BTCUSDT:take-short"), 1)
        execution = self.runtime.store.load_executions()[-1]
        self.assertEqual(execution.side, OrderSide.BUY)
        self.assertEqual(execution.quantity.value, expected)
        self.assertEqual(self.runtime.paper_state("BTCUSDT")["position_side"], "Flat")


if __name__ == "__main__":
    unittest.main()
