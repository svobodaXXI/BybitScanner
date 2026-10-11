"""SwordCounter S1: read-only Bybit V5 open-positions module.

No network, no API keys: every HTTP call goes through a fake session that only
implements ``get`` (a ``post``/``delete`` call would fail with AttributeError).
"""

import hashlib
import hmac
import io
import json
import logging
import re
import unittest
from decimal import Decimal
from pathlib import Path
from unittest import mock
from urllib.parse import parse_qsl, urlsplit

import requests

from tools.SwordCounter import bybit_positions as bp
from tools.SwordCounter.bybit_positions import (
    BybitApiError, BybitCredentialsError, BybitPositionsError, BybitResponseError,
    BybitTransportError, Credentials, OpenPosition, fetch_open_positions,
)

SECRET = "TOPSECRET-sentinel-value-0123456789abcdef"
KEY = "KEY-sentinel-ABCDEF123456"
NOW_MS = 1_700_000_000_123


def row(symbol="BTCUSDT", side="Buy", size="0.5", avg="60000", value="30000", idx=0, **extra):
    base = {
        "positionIdx": idx, "symbol": symbol, "side": side, "size": size, "avgPrice": avg,
        "positionValue": value, "positionStatus": "Normal", "leverage": "10",
        "markPrice": "60100", "positionIM": "3002.5", "positionIMByMp": "3002.5",
        "positionMM": "150.1", "positionBalance": "9999", "tradeMode": 0,
        "unrealisedPnl": "50", "updatedTime": "1700000000000", "seq": 1,
    }
    base.update(extra)
    return base


def page(rows, cursor="", ret_code=0, ret_msg="OK"):
    return {"retCode": ret_code, "retMsg": ret_msg,
            "result": {"category": "linear", "list": rows, "nextPageCursor": cursor},
            "retExtInfo": {}, "time": NOW_MS}


class FakeResponse:
    def __init__(self, payload=None, status=200, text=None):
        self.status_code = status
        self._payload = payload
        self.text = text if text is not None else json.dumps(payload)

    def json(self):
        if self._payload is None:
            raise ValueError("not json")
        return self._payload


class FakeSession:
    """Only ``get`` exists on purpose: any mutating HTTP verb is an AttributeError."""

    def __init__(self, *responses):
        self.responses = list(responses)
        self.calls = []

    def get(self, url, headers=None, timeout=None):
        self.calls.append({"url": url, "headers": dict(headers or {}), "timeout": timeout})
        item = self.responses.pop(0)
        if isinstance(item, BaseException):
            raise item
        return item


def creds():
    return Credentials(api_key=KEY, api_secret=SECRET)


def fetch(session, **kwargs):
    kwargs.setdefault("settle_coins", ("USDT",))
    return fetch_open_positions(creds(), session=session, clock_ms=lambda: NOW_MS, **kwargs)


class RequestShapeTests(unittest.TestCase):
    def test_signed_get_follows_the_v5_authentication_rules(self):
        session = FakeSession(FakeResponse(page([row()])))
        fetch(session, recv_window_ms=5000)

        call = session.calls[0]
        parts = urlsplit(call["url"])
        self.assertEqual((parts.scheme, parts.netloc, parts.path),
                         ("https", "api.bybit.com", "/v5/position/list"))
        query = parts.query
        self.assertEqual(dict(parse_qsl(query)),
                         {"category": "linear", "settleCoin": "USDT", "limit": "200"})
        expected = hmac.new(SECRET.encode(), f"{NOW_MS}{KEY}5000{query}".encode(),
                            hashlib.sha256).hexdigest()
        headers = call["headers"]
        self.assertEqual(headers["X-BAPI-SIGN"], expected)
        self.assertEqual(headers["X-BAPI-API-KEY"], KEY)
        self.assertEqual(headers["X-BAPI-TIMESTAMP"], str(NOW_MS))
        self.assertEqual(headers["X-BAPI-RECV-WINDOW"], "5000")
        self.assertRegex(headers["X-BAPI-SIGN"], r"^[0-9a-f]{64}$")
        self.assertGreater(call["timeout"], 0)
        self.assertNotIn(SECRET, call["url"])

    def test_default_settle_coins_cover_usdt_and_usdc_linear(self):
        session = FakeSession(FakeResponse(page([row()])), FakeResponse(page([])))
        result = fetch_open_positions(creds(), session=session, clock_ms=lambda: NOW_MS)
        coins = [dict(parse_qsl(urlsplit(c["url"]).query))["settleCoin"] for c in session.calls]
        self.assertEqual(coins, ["USDT", "USDC"])
        self.assertEqual([p.symbol for p in result], ["BTCUSDT"])

    def test_the_module_is_read_only_by_construction(self):
        source = Path(bp.__file__).read_text(encoding="utf-8")
        for forbidden in ("/v5/order", "create-order", "amend", "cancel", "set-leverage",
                          ".post(", ".put(", ".delete("):
            self.assertNotIn(forbidden, source, forbidden)
        self.assertEqual(re.findall(r'"/v5/[a-z/\-]+"', source), ['"/v5/position/list"'])
        for banned in ("terminal.", "robot_", "paper_runtime", "sqlite3", "config"):
            self.assertNotRegex(source, rf"(?m)^\s*(from|import)\s+{re.escape(banned)}", banned)


class MarginFieldTests(unittest.TestCase):
    def test_occupied_margin_is_position_im_not_value_over_leverage(self):
        # value / leverage = 30000 / 10 = 3000, the API reports 3002.5: no derivation from leverage.
        session = FakeSession(FakeResponse(page([row(value="30000", leverage="10",
                                                     positionIM="3002.5", positionIMByMp="3002.5")])))
        (position,) = fetch(session)

        self.assertEqual(position.position_im, Decimal("3002.5"))
        self.assertEqual(position.occupied_margin, Decimal("3002.5"))
        self.assertNotEqual(position.occupied_margin, position.position_value / position.leverage)
        self.assertEqual(OpenPosition.MARGIN_FIELD, "positionIM")
        # The deprecated field is never the margin source.
        self.assertNotEqual(position.occupied_margin, Decimal("9999"))

    def test_missing_margin_is_unavailable_never_guessed(self):
        # Portfolio margin: leverage "" and positionIM "" -> no number is invented.
        session = FakeSession(FakeResponse(page([row(leverage="", positionIM="", positionIMByMp="",
                                                     positionMM="")])))
        (position,) = fetch(session)
        self.assertIsNone(position.leverage)
        self.assertIsNone(position.position_im)
        self.assertIsNone(position.occupied_margin)
        self.assertFalse(position.margin_available)

    def test_disagreeing_margin_fields_are_an_explicit_error(self):
        session = FakeSession(FakeResponse(page([row(positionIM="3002.5", positionIMByMp="1.0")])))
        with self.assertRaises(BybitResponseError):
            fetch(session)


class ParsingTests(unittest.TestCase):
    def test_open_positions_are_parsed_exactly_and_empty_rows_dropped(self):
        session = FakeSession(FakeResponse(page([
            row("BTCUSDT", "Buy", "0.5"),
            row("ETHUSDT", "Sell", "0", value="0", side_override=None),
            row("SOLUSDT", "", "0", avg="0", value="0"),
            row("XRPUSDT", "Sell", "100", avg="0.5", value="50", positionIM="5", positionIMByMp="5"),
        ])))
        positions = fetch(session)
        self.assertEqual([(p.symbol, p.side, p.size) for p in positions],
                         [("BTCUSDT", "Buy", Decimal("0.5")), ("XRPUSDT", "Sell", Decimal("100"))])
        first = positions[0]
        self.assertEqual((first.avg_price, first.position_value, first.mark_price, first.leverage),
                         (Decimal("60000"), Decimal("30000"), Decimal("60100"), Decimal("10")))
        self.assertEqual((first.position_idx, first.position_status, first.settle_coin),
                         (0, "Normal", "USDT"))

    def test_hedge_mode_keeps_both_legs_of_one_symbol(self):
        session = FakeSession(FakeResponse(page([row("BTCUSDT", "Buy", "1", idx=1),
                                                 row("BTCUSDT", "Sell", "2", idx=2)])))
        self.assertEqual([(p.position_idx, p.side) for p in fetch(session)], [(1, "Buy"), (2, "Sell")])

    def test_a_valid_empty_list_is_the_only_way_to_get_zero_positions(self):
        self.assertEqual(fetch(FakeSession(FakeResponse(page([])))), ())

    def test_pagination_follows_the_cursor_and_merges_pages(self):
        session = FakeSession(
            FakeResponse(page([row("AAAUSDT")], cursor="CUR1")),
            FakeResponse(page([row("BBBUSDT")], cursor="")),
        )
        positions = fetch(session)
        self.assertEqual([p.symbol for p in positions], ["AAAUSDT", "BBBUSDT"])
        self.assertEqual(dict(parse_qsl(urlsplit(session.calls[1]["url"]).query))["cursor"], "CUR1")

    def test_a_repeated_cursor_or_duplicate_key_is_an_error_not_a_loop(self):
        looping = FakeSession(FakeResponse(page([row("AAAUSDT")], cursor="SAME")),
                              FakeResponse(page([row("BBBUSDT")], cursor="SAME")))
        with self.assertRaises(BybitResponseError):
            fetch(looping)
        duplicate = FakeSession(FakeResponse(page([row("AAAUSDT"), row("AAAUSDT")])))
        with self.assertRaises(BybitResponseError):
            fetch(duplicate)

    def test_malformed_rows_are_errors_never_skipped(self):
        for label, bad in (
            ("size", row(size="abc")), ("side", row(side="Long")), ("avg", row(avg="")),
            ("value", row(value="x")), ("idx", row(idx="a")), ("symbol", row(symbol="")),
            ("negative size", row(size="-1")), ("nan", row(avg="NaN")),
        ):
            with self.subTest(label):
                with self.assertRaises(BybitResponseError):
                    fetch(FakeSession(FakeResponse(page([bad]))))


class ErrorsAreExplicitTests(unittest.TestCase):
    def assertRaisesNotEmpty(self, error_type, session):
        with self.assertRaises(error_type) as raised:
            result = fetch(session)
            self.fail(f"returned {result!r} instead of raising")
        return raised.exception

    def test_api_error_is_raised_with_code_and_message_never_zero_positions(self):
        error = self.assertRaisesNotEmpty(
            BybitApiError, FakeSession(FakeResponse(page([], ret_code=10003, ret_msg="API key is invalid."))))
        self.assertEqual((error.ret_code, error.ret_msg), (10003, "API key is invalid."))
        self.assertIsInstance(error, BybitPositionsError)

    def test_http_errors_timeouts_and_bad_json_are_distinct_explicit_errors(self):
        http = self.assertRaisesNotEmpty(BybitApiError, FakeSession(FakeResponse(None, status=403, text="blocked")))
        self.assertEqual(http.http_status, 403)
        self.assertRaisesNotEmpty(BybitTransportError, FakeSession(requests.Timeout("slow")))
        self.assertRaisesNotEmpty(BybitTransportError, FakeSession(requests.ConnectionError("down")))
        self.assertRaisesNotEmpty(BybitResponseError, FakeSession(FakeResponse(None, status=200, text="<html>")))

    def test_malformed_envelopes_are_errors(self):
        for label, payload in (
            ("no retCode", {"result": {"list": []}}),
            ("string retCode", {"retCode": "0", "retMsg": "OK", "result": {"list": []}}),
            ("no result", {"retCode": 0, "retMsg": "OK"}),
            ("no list", {"retCode": 0, "retMsg": "OK", "result": {}}),
            ("list not a list", {"retCode": 0, "retMsg": "OK", "result": {"list": {}}}),
            ("not an object", [1, 2]),
        ):
            with self.subTest(label):
                self.assertRaisesNotEmpty(BybitResponseError, FakeSession(FakeResponse(payload)))

    def test_a_failure_on_any_settle_coin_or_page_discards_everything(self):
        second_coin_fails = FakeSession(FakeResponse(page([row("AAAUSDT")])),
                                        FakeResponse(page([], ret_code=10016, ret_msg="Server error")))
        with self.assertRaises(BybitApiError):
            fetch_open_positions(creds(), session=second_coin_fails, clock_ms=lambda: NOW_MS)
        second_page_fails = FakeSession(FakeResponse(page([row("AAAUSDT")], cursor="C")),
                                        requests.Timeout("slow"))
        with self.assertRaises(BybitTransportError):
            fetch(second_page_fails)

    def test_invalid_parameters_are_rejected_before_any_request(self):
        session = FakeSession()
        for kwargs in ({"category": "spot"}, {"settle_coins": ()}, {"settle_coins": ("btc usdt",)},
                       {"recv_window_ms": 0}, {"recv_window_ms": 99999}, {"timeout_s": 0},
                       {"base_url": "http://api.bybit.com"}):
            with self.subTest(kwargs=kwargs), self.assertRaises(ValueError):
                fetch(session, **kwargs)
        self.assertEqual(session.calls, [])


class SecretsTests(unittest.TestCase):
    def test_credentials_come_from_the_environment_and_are_never_printed(self):
        env = {"SWORDCOUNTER_BYBIT_API_KEY": KEY, "SWORDCOUNTER_BYBIT_API_SECRET": SECRET}
        with mock.patch.dict("os.environ", env, clear=False):
            loaded = Credentials.from_env()
        self.assertEqual((loaded.api_key, loaded.api_secret), (KEY, SECRET))
        for text in (repr(loaded), str(loaded), f"{loaded}", repr([loaded])):
            self.assertNotIn(SECRET, text)
            self.assertNotIn(KEY, text)

    def test_missing_or_blank_credentials_name_the_variables_only(self):
        with mock.patch.dict("os.environ", {}, clear=True):
            with self.assertRaises(BybitCredentialsError) as raised:
                Credentials.from_env()
        self.assertIn("SWORDCOUNTER_BYBIT_API_KEY", str(raised.exception))
        self.assertIn("SWORDCOUNTER_BYBIT_API_SECRET", str(raised.exception))
        with self.assertRaises(BybitCredentialsError):
            Credentials(api_key=" ", api_secret=SECRET)

    def test_no_error_log_or_traceback_text_carries_the_secret(self):
        stream = io.StringIO()
        handler = logging.StreamHandler(stream)
        root = logging.getLogger()
        root.addHandler(handler)
        self.addCleanup(root.removeHandler, handler)
        captured = []
        for session in (
            FakeSession(FakeResponse(page([], ret_code=10003, ret_msg="API key is invalid."))),
            FakeSession(FakeResponse(None, status=500, text="oops")),
            FakeSession(requests.exceptions.ProxyError(f"proxy http://user:{SECRET}@proxy:8080 refused")),
            FakeSession(FakeResponse(page([row(size="abc")]))),
        ):
            try:
                fetch(session)
            except BybitPositionsError as error:
                captured += [str(error), repr(error), repr(error.__cause__), repr(error.__context__)]
        text = "\n".join(captured) + stream.getvalue()
        self.assertNotIn(SECRET, text)
        self.assertNotIn(KEY, text)
        self.assertNotIn("user:", text)


class RestartTests(unittest.TestCase):
    def test_every_call_reads_live_state_so_a_restart_recovers_the_positions(self):
        before = fetch(FakeSession(FakeResponse(page([row("AAAUSDT"), row("BBBUSDT")]))))
        # "Application restarted": nothing is cached or persisted, a new call reflects the exchange now.
        after = fetch(FakeSession(FakeResponse(page([row("BBBUSDT", size="2")]))))
        self.assertEqual([p.symbol for p in before], ["AAAUSDT", "BBBUSDT"])
        self.assertEqual([(p.symbol, p.size) for p in after], [("BBBUSDT", Decimal("2"))])
        source = Path(bp.__file__).read_text(encoding="utf-8")
        for persistence in ("open(", "write_text", "pickle", "shelve", "json.dump(", "sqlite3"):
            self.assertNotIn(persistence, source, persistence)


if __name__ == "__main__":
    unittest.main()
