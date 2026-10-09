"""Cached book-level normalization is value-identical to fresh construction.

No network or DB. Full 1000-level books per side are compared level by level,
including the exact Decimal string form, order, sequence and depth.
"""

import random
import unittest
from decimal import Decimal, InvalidOperation

import terminal.runtime.paper_http_server as server
from terminal.domain.models import Price, Quantity
from terminal.market_data.models import PriceLevel
from terminal.runtime.paper_http_server import (
    PublicOrderBookBuffer,
    _book_level,
    _normalized_book_from_snapshot,
)

SYMBOL = "BTCUSDT"


def _fresh(levels):
    return tuple(
        PriceLevel(Price(Decimal(level["price"])), Quantity(Decimal(level["size"])))
        for level in levels
    )


def _exact(levels):
    return [(str(level.price.value), str(level.quantity.value)) for level in levels]


def _buffer(seed):
    rnd = random.Random(seed)
    buffer = PublicOrderBookBuffer(SYMBOL, depth=1000)
    buffer.apply_message({"topic": f"orderbook.1000.{SYMBOL}", "type": "snapshot", "ts": 1, "data": {
        "s": SYMBOL, "u": 1, "seq": 1,
        "b": [[f"{65000 - i * 0.1:.1f}", f"{rnd.uniform(0.001, 5):.3f}"] for i in range(1000)],
        "a": [[f"{65000.1 + i * 0.1:.1f}", f"{rnd.uniform(0.001, 5):.3f}"] for i in range(1000)],
    }})
    return buffer, rnd


class BookLevelCacheTests(unittest.TestCase):
    def setUp(self):
        server._BOOK_LEVEL_CACHE.clear()

    def test_every_level_of_every_event_matches_fresh_construction(self):
        buffer, rnd = _buffer(11)
        for update in range(2, 80):
            payload = buffer.snapshot()
            book = _normalized_book_from_snapshot(SYMBOL, payload, source_generation=3)
            self.assertEqual(len(book.bids), 1000)
            self.assertEqual(len(book.asks), 1000)
            self.assertEqual(book.bids, _fresh(payload["bids"]))
            self.assertEqual(book.asks, _fresh(payload["asks"]))
            self.assertEqual(_exact(book.bids), _exact(_fresh(payload["bids"])))
            self.assertEqual(_exact(book.asks), _exact(_fresh(payload["asks"])))
            self.assertEqual(book.source_sequence, payload["sequence"])
            self.assertEqual(book.source_update_id, update - 1)
            self.assertEqual(book.source_update_id, payload["updateId"])
            self.assertEqual(book.available_depth, 1000)
            self.assertEqual(book.source_generation, 3)
            side = rnd.choice(("b", "a"))
            prices = [l["price"] for l in payload["bids" if side == "b" else "asks"]]
            buffer.apply_message({"topic": f"orderbook.1000.{SYMBOL}", "type": "delta", "ts": update, "data": {
                "s": SYMBOL, "u": update, "seq": update, "b": [], "a": [],
                side: [[rnd.choice(prices), f"{rnd.uniform(0.001, 5):.3f}"] for _ in range(20)],
            }})

    def test_updates_deletions_and_snapshot_replacement_never_return_stale_levels(self):
        buffer, _ = _buffer(5)
        first = _normalized_book_from_snapshot(SYMBOL, buffer.snapshot())
        top_bid = buffer.snapshot()["bids"][0]["price"]
        top_ask = buffer.snapshot()["asks"][0]["price"]
        steps = [
            # size change of an existing level
            {"type": "delta", "data": {"b": [[top_bid, "9.999"]]}},
            # deletion of the best ask
            {"type": "delta", "data": {"a": [[top_ask, "0"]]}},
            # back to the original size (a key already cached)
            {"type": "delta", "data": {"b": [[top_bid, first.bids[0].quantity.value.__str__()]]}},
            # reconnect: a fresh full snapshot with different levels
            {"type": "snapshot", "data": {
                "b": [[f"{50000 - i * 0.5:.1f}", "2.000"] for i in range(1000)],
                "a": [[f"{50000.5 + i * 0.5:.1f}", "3.000"] for i in range(1000)]}},
        ]
        for update, step in enumerate(steps, start=2):
            data = {"s": SYMBOL, "u": update, "seq": update, "b": [], "a": [], **step["data"]}
            buffer.apply_message({"topic": f"orderbook.1000.{SYMBOL}", "type": step["type"],
                                  "ts": update, "data": data})
            payload = buffer.snapshot()
            book = _normalized_book_from_snapshot(SYMBOL, payload, source_generation=update)
            self.assertEqual(book.bids, _fresh(payload["bids"]))
            self.assertEqual(book.asks, _fresh(payload["asks"]))
            self.assertEqual(_exact(book.bids), _exact(_fresh(payload["bids"])))
            self.assertEqual((book.source_update_id, book.source_generation), (update, update))
        self.assertEqual(book.bids[0], PriceLevel(Price(Decimal("50000.0")), Quantity(Decimal("2.000"))))
        self.assertNotIn(top_ask, {str(level.price.value) for level in book.asks})

    def test_concurrent_use_stays_correct_and_bounded(self):
        import threading

        limit = server._BOOK_LEVEL_CACHE_LIMIT
        server._BOOK_LEVEL_CACHE_LIMIT = 500
        errors = []

        def worker(offset):
            try:
                for index in range(3000):
                    price, size = str(1000 + (index * 7 + offset) % 2500), f"{offset + 1}.{index % 13}"
                    level = _book_level(price, size)
                    if (str(level.price.value), str(level.quantity.value)) != (price, size):
                        errors.append((price, size))
                    if len(server._BOOK_LEVEL_CACHE) > 500 + 8:
                        errors.append(("unbounded", len(server._BOOK_LEVEL_CACHE)))
            except Exception as exc:  # pragma: no cover - reported below
                errors.append(exc)

        try:
            threads = [threading.Thread(target=worker, args=(i,)) for i in range(8)]
            for thread in threads:
                thread.start()
            for thread in threads:
                thread.join()
        finally:
            server._BOOK_LEVEL_CACHE_LIMIT = limit
        self.assertEqual(errors, [])

    def test_exact_decimal_text_is_preserved_between_equal_values(self):
        first = _book_level("100.10", "1.230")
        second = _book_level("100.1", "1.23")
        self.assertEqual(first, second)  # equal by value
        self.assertEqual((str(first.price.value), str(first.quantity.value)), ("100.10", "1.230"))
        self.assertEqual((str(second.price.value), str(second.quantity.value)), ("100.1", "1.23"))
        self.assertIs(_book_level("100.10", "1.230"), first)

    def test_invalid_levels_still_fail_every_time_and_are_never_cached(self):
        for _ in range(2):
            with self.assertRaises(ValueError):
                _book_level("100", "0")
            with self.assertRaises(InvalidOperation):
                _book_level("abc", "1")
        self.assertNotIn(("100", "0"), server._BOOK_LEVEL_CACHE)
        payload = _buffer(3)[0].snapshot()
        payload["bids"] = [*payload["bids"][:5], {"price": "1", "size": "0"}]
        self.assertIsNone(_normalized_book_from_snapshot(SYMBOL, payload))

    def test_non_string_input_takes_the_original_path(self):
        self.assertEqual(_book_level(Decimal("5"), Decimal("2")),
                         PriceLevel(Price(Decimal("5")), Quantity(Decimal("2"))))
        self.assertEqual(server._BOOK_LEVEL_CACHE, {})

    def test_cache_is_bounded(self):
        limit = server._BOOK_LEVEL_CACHE_LIMIT
        try:
            server._BOOK_LEVEL_CACHE_LIMIT = 10
            for index in range(25):
                _book_level(str(100 + index), "1")
                self.assertLessEqual(len(server._BOOK_LEVEL_CACHE), 10)
        finally:
            server._BOOK_LEVEL_CACHE_LIMIT = limit


if __name__ == "__main__":
    unittest.main()
