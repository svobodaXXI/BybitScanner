"""SwordCounter S2: working-volume ("swords") count from Bybit positionValue. Offline, no keys."""

import re
import unittest
from decimal import Decimal
from pathlib import Path

from tools.SwordCounter import swords as sw
from tools.SwordCounter.bybit_positions import (
    BybitApiError, BybitCredentialsError, BybitResponseError, BybitTransportError, OpenPosition,
)
from tools.SwordCounter.swords import (
    STATUS_NO_CONNECTION, STATUS_OK, STATUS_UNAVAILABLE, SwordSettings, count_swords,
    count_swords_from_api,
)


def pos(symbol="BTCUSDT", value="5", coin="USDT", idx=0, side="Buy", im="0.1"):
    return OpenPosition(
        symbol=symbol, side=side, position_idx=idx, settle_coin=coin, size=Decimal("1"),
        avg_price=Decimal("100"), position_value=None if value is None else Decimal(value), position_status="Normal",
        mark_price=Decimal("100"), position_im=Decimal(im),
        position_mm=Decimal("1"), leverage=Decimal("10"), unrealised_pnl=Decimal("0"),
        updated_time_ms=1,
    )


DEFAULT = SwordSettings()


class DefaultsAndSettingsTests(unittest.TestCase):
    def test_defaults_are_twenty_swords_of_five_usdt(self):
        self.assertEqual((DEFAULT.total_swords, DEFAULT.sword_size_usdt), (20, Decimal("5")))

    def test_both_parameters_are_configurable(self):
        s = SwordSettings(total_swords=10, sword_size_usdt=Decimal("2.5"))
        r = count_swords([pos(value="6")], s)
        self.assertEqual((r.used_swords, r.free_swords, r.total_swords, r.sword_size_usdt),
                         (3, 7, 10, Decimal("2.5")))
        self.assertEqual(SwordSettings(sword_size_usdt="7.5").sword_size_usdt, Decimal("7.5"))
        self.assertEqual(SwordSettings(sword_size_usdt=4).sword_size_usdt, Decimal("4"))

    def test_invalid_settings_are_rejected(self):
        for kwargs in ({"total_swords": 0}, {"total_swords": -1}, {"total_swords": 1.5},
                       {"total_swords": True}, {"total_swords": "20"}, {"total_swords": 20.0},
                       {"sword_size_usdt": 0}, {"sword_size_usdt": Decimal("0")},
                       {"sword_size_usdt": Decimal("-5")}, {"sword_size_usdt": 5.0},
                       {"sword_size_usdt": True}, {"sword_size_usdt": "abc"},
                       {"sword_size_usdt": Decimal("NaN")}, {"sword_size_usdt": Decimal("Infinity")},
                       {"sword_size_usdt": None}):
            with self.subTest(kwargs=kwargs), self.assertRaises(ValueError):
                SwordSettings(**kwargs)


class CountTests(unittest.TestCase):
    def test_empty_account_uses_no_swords(self):
        r = count_swords([], DEFAULT)
        self.assertEqual((r.status, r.occupied_margin_usdt, r.used_swords, r.free_swords, r.over_limit,
                          r.positions_count), (STATUS_OK, Decimal("0"), 0, 20, False, 0))

    def test_margin_is_summed_over_all_positions(self):
        r = count_swords([pos("A", "12.5"), pos("B", "7.25"), pos("C", "0.25")], DEFAULT)
        self.assertEqual(r.occupied_margin_usdt, Decimal("20.00"))
        self.assertEqual((r.used_swords, r.free_swords, r.positions_count), (4, 16, 3))

    def test_a_partial_sword_counts_as_a_whole_sword(self):
        for value, used in (("0.01", 1), ("4.99", 1), ("5", 1), ("5.0000001", 2), ("12.5", 3)):
            with self.subTest(value=value):
                self.assertEqual(count_swords([pos(value=value)], DEFAULT).used_swords, used)

    def test_exact_limit_boundary(self):
        r = count_swords([pos("A", "60"), pos("B", "40")], DEFAULT)
        self.assertEqual((r.occupied_margin_usdt, r.used_swords, r.free_swords, r.over_limit),
                         (Decimal("100"), 20, 0, False))

    def test_over_limit_is_shown_not_hidden(self):
        r = count_swords([pos("A", "100.01")], DEFAULT)
        self.assertEqual((r.status, r.used_swords, r.free_swords, r.over_limit), (STATUS_OK, 21, 0, True))
        big = count_swords([pos("A", "250")], DEFAULT)
        self.assertEqual((big.used_swords, big.free_swords, big.over_limit), (50, 0, True))

    def test_decimal_precision_beyond_float_is_exact(self):
        # 0.1 + 0.2 is exactly 0.3; a value a hair over a boundary still costs a sword.
        r = count_swords([pos("A", "0.1"), pos("B", "0.2"), pos("C", "4.7")], DEFAULT)
        self.assertEqual((r.occupied_margin_usdt, r.used_swords), (Decimal("5.0"), 1))
        hair = count_swords([pos(value="100.0000000000000000000000000000000001")], DEFAULT)
        self.assertEqual((hair.used_swords, hair.over_limit), (21, True))

    def test_metabroker_four_positions_5_4_5_5_use_four_swords(self):
        # Regression: positionIM (~1.9 USDT margin) gave 1 sword; the working volume is the
        # position value without dividing by leverage: 5 + 4 + 5 + 5 = 19 USDT -> 4 used, 16 free.
        positions = [pos("SENTUSDT", "5", im="0.1", side="Buy"), pos("VELVETUSDT", "4", im="0.8", side="Sell"),
                     pos("XNYUSDT", "5", im="1.0"), pos("LYNUSDT", "5", im="0.2")]
        r = count_swords(positions, DEFAULT)
        self.assertEqual((r.status, r.occupied_margin_usdt, r.used_swords, r.free_swords, r.over_limit),
                         (STATUS_OK, Decimal("19"), 4, 16, False))

    def test_leverage_and_margin_do_not_change_the_volume(self):
        low = count_swords([pos(value="19", im="19")], DEFAULT)
        high = count_swords([pos(value="19", im="0.19")], DEFAULT)
        self.assertEqual((low.used_swords, high.used_swords), (4, 4))

    def test_no_float_arithmetic_in_the_module(self):
        source = Path(sw.__file__).read_text(encoding="utf-8")
        self.assertNotRegex(source, r"\bfloat\(|math\.ceil|\bround\(")


class UnavailableTests(unittest.TestCase):
    def assertUnavailable(self, result):
        self.assertEqual(result.status, STATUS_UNAVAILABLE)
        self.assertEqual(result.status_label, "Недоступно")
        self.assertIsNone(result.occupied_margin_usdt)
        self.assertIsNone(result.used_swords)
        self.assertIsNone(result.free_swords)
        self.assertIsNone(result.over_limit)
        self.assertTrue(result.reason)

    def test_one_unknown_margin_makes_the_whole_result_unavailable(self):
        r = count_swords([pos("A", "10"), pos("B", None), pos("C", "3")], DEFAULT)
        self.assertUnavailable(r)
        self.assertEqual(r.unknown_margin_symbols, ("B",))
        self.assertEqual(r.positions_count, 3)

    def test_margin_in_another_settle_coin_is_not_mixed_into_usdt(self):
        self.assertUnavailable(count_swords([pos("A", "10"), pos("BTCPERP", "10", coin="USDC")], DEFAULT))

    def test_negative_margin_is_not_trusted(self):
        self.assertUnavailable(count_swords([pos(value="-1")], DEFAULT))


class ConnectionTests(unittest.TestCase):
    def test_api_errors_mean_no_connection_and_never_zero(self):
        for error in (BybitApiError("Bybit retCode 10003: API key is invalid.", ret_code=10003),
                      BybitApiError("Bybit HTTP status 403", http_status=403),
                      BybitTransportError("Bybit request failed: Timeout"),
                      BybitResponseError("Bybit reply is not valid JSON"),
                      BybitCredentialsError("keys missing")):
            with self.subTest(type(error).__name__):
                def failing():
                    raise error
                r = count_swords_from_api(failing, DEFAULT)
                self.assertEqual((r.status, r.status_label), (STATUS_NO_CONNECTION, "Нет соединения"))
                self.assertIsNone(r.occupied_margin_usdt)
                self.assertIsNone(r.used_swords)
                self.assertIsNone(r.free_swords)
                self.assertIsNone(r.positions_count)
                self.assertIn(type(error).__name__, r.reason)

    def test_programming_errors_are_not_disguised_as_no_connection(self):
        def broken():
            raise KeyError("bug")
        with self.assertRaises(KeyError):
            count_swords_from_api(broken, DEFAULT)

    def test_each_call_reads_positions_afresh(self):
        calls = []
        def fetch():
            calls.append(1)
            return (pos(value=str(5 * len(calls))),)
        first = count_swords_from_api(fetch, DEFAULT)
        second = count_swords_from_api(fetch, DEFAULT)
        self.assertEqual((first.used_swords, second.used_swords, len(calls)), (1, 2, 2))
        self.assertEqual(first.status_label, "Доступно")


if __name__ == "__main__":
    unittest.main()
