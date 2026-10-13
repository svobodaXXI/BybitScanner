"""TG-METASCALP-2: owner Telegram button opens a NEW MetaScalp order book.

All HTTP goes through a mocked urlopen; no MetaScalp, Telegram or exchange call.
"""
import io
import json
import socket
import sys
import types
import unittest
import urllib.error
from pathlib import Path
from unittest.mock import patch

import metascalp_bridge

# config.py is local and secret-bearing; this test owns only the import-time surface
# it needs (same pattern as test_telegram_delivery / test_telegram_monitoring).
_previous_config = sys.modules.get("config")
_config_stub = types.ModuleType("config")
_config_stub.TELEGRAM_TOKEN = "test-token"
_config_stub.TELEGRAM_CHAT_ID = "1"
_config_stub.TELEGRAM_CHAT_IDS = ("1",)
_config_stub.TELEGRAM_ENABLED = True
_config_stub.TELEGRAM_TEST_MODE = False
sys.modules["config"] = _config_stub
try:
    import notification
    import telegram_monitoring
finally:
    if _previous_config is None:
        sys.modules.pop("config", None)
    else:
        sys.modules["config"] = _previous_config

ROOT = Path(__file__).resolve().parents[1]
BYBIT_PERP = {"Id": 20, "Exchange": "Bybit", "ExchangeId": 6, "Market": "USDT Perpetual",
              "MarketType": 5, "State": 2, "ViewMode": False, "DemoMode": False}


class _Response(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


class FakeMetaScalp:
    """Routes mocked urlopen calls; records every request."""

    def __init__(self, port=17845, connections=(BYBIT_PERP,), tickers=("SOLUSDT", "DOGEUSDT"),
                 combo=None):
        self.port, self.connections, self.tickers, self.combo = port, list(connections), tickers, combo
        self.calls = []

    def __call__(self, request, timeout=None):
        url = request if isinstance(request, str) else request.full_url
        method = "GET" if isinstance(request, str) else request.get_method()
        body = None if isinstance(request, str) else request.data
        self.calls.append((method, url, body, timeout))
        prefix = f"http://127.0.0.1:{self.port}"
        if not url.startswith(prefix + "/"):
            raise urllib.error.URLError(ConnectionRefusedError())
        path = url[len(prefix):]
        if method == "GET" and path == "/ping":
            return _Response(b'{"app":"MetaScalp","version":"1.0.250"}')
        if method == "GET" and path == "/api/connections":
            return _Response(json.dumps({"connections": self.connections}).encode())
        if method == "GET" and path == "/api/connections/20/tickers":
            return _Response(json.dumps({"tickers": [{"Name": t} for t in self.tickers]}).encode())
        if method == "POST" and path == "/api/combo":
            if self.combo is not None:
                raise self.combo
            return _Response(b'{"status":"ok"}')
        raise AssertionError(f"unexpected MetaScalp call {method} {path}")

    def posts(self):
        return [call for call in self.calls if call[0] == "POST"]


def _open(fake, symbol="SOLUSDT"):
    with patch.object(metascalp_bridge.urllib.request, "urlopen", side_effect=fake):
        return metascalp_bridge.open_order_book(symbol)


class OpenOrderBookTest(unittest.TestCase):
    def test_success_posts_exactly_one_combo_for_the_symbol(self):
        fake = FakeMetaScalp(port=17847)
        self.assertEqual(_open(fake), "MetaScalp: открыт стакан SOLUSDT")
        (post,) = fake.posts()
        self.assertEqual(post[1], "http://127.0.0.1:17847/api/combo")
        self.assertEqual(json.loads(post[2]), {"Ticker": "SOLUSDT"})
        self.assertEqual(post[3], metascalp_bridge.COMBO_TIMEOUT_SECONDS)
        for method, url, _, _ in fake.calls:
            self.assertTrue(url.startswith("http://127.0.0.1:1784") or url.startswith("http://127.0.0.1:1785"))
            self.assertIn(url.split(":", 2)[2].split("/", 1)[1],
                          ("ping", "api/connections", "api/connections/20/tickers", "api/combo"))

    def test_refusals_never_post(self):
        cases = {
            "не запущен": FakeMetaScalp(port=18000),
            "ровно одно": FakeMetaScalp(connections=()),
            "ровно одно ": FakeMetaScalp(connections=(BYBIT_PERP, dict(BYBIT_PERP, Id=21))),
            "не Bybit USDT Perpetual": FakeMetaScalp(connections=(dict(BYBIT_PERP, MarketType=1),)),
            "не Bybit USDT Perpetual ": FakeMetaScalp(connections=(dict(BYBIT_PERP, ExchangeId=1),)),
            "Connected": FakeMetaScalp(connections=(dict(BYBIT_PERP, State=1),)),
            "нет в Bybit": FakeMetaScalp(tickers=("BTCUSDT",)),
        }
        for expected, fake in cases.items():
            with self.subTest(expected=expected):
                with self.assertRaises(metascalp_bridge.MetaScalpError) as raised:
                    _open(fake)
                self.assertIn(expected.strip(), str(raised.exception))
                self.assertEqual(fake.posts(), [])

    def test_invalid_symbol_makes_no_call(self):
        fake = FakeMetaScalp()
        for symbol in ("solusdt", "SOLUSDC", "SOL/USDT", "", "BYBIT:SOLUSDT.p"):
            with self.subTest(symbol=symbol), self.assertRaises(metascalp_bridge.MetaScalpError):
                _open(fake, symbol)
        self.assertEqual(fake.calls, [])

    def test_post_timeout_or_rejection_is_reported_once_without_retry(self):
        for error, expected in (
            (socket.timeout("timed out"), "не ответил"),
            (urllib.error.HTTPError("u", 400, "bad", {}, None), "HTTP 400"),
        ):
            with self.subTest(expected=expected):
                fake = FakeMetaScalp(combo=error)
                with self.assertRaises(metascalp_bridge.MetaScalpError) as raised:
                    _open(fake)
                self.assertIn(expected, str(raised.exception))
                self.assertEqual(len(fake.posts()), 1)

    def test_bridge_has_no_trading_or_existing_panel_routes(self):
        source = (ROOT / "metascalp_bridge.py").read_text(encoding="utf-8")
        code = source.split('"""', 2)[2]  # skip the module docstring
        for forbidden in ("/orders", "positions", "change-ticker", "/api/ui", "link-number",
                          "cancel", "close", "leverage"):
            self.assertNotIn(forbidden, code)
        self.assertEqual(code.count('method="POST"'), 1)


class SignalButtonTest(unittest.TestCase):
    def _texts(self, keyboard):
        return [(b["text"], b.get("callback_data")) for row in keyboard["inline_keyboard"] for b in row]

    def test_owner_card_has_metascalp_button_for_signal_symbol(self):
        owner = notification.build_tradingview_keyboard("SOLUSDT", "5", include_review_actions=True)
        self.assertEqual(owner["inline_keyboard"][0][1], {"text": "📊 MetaScalp", "callback_data": "ms:open:SOLUSDT"})
        self.assertEqual(owner["inline_keyboard"][0][0]["text"], "📈 Open TradingView")

    def test_friend_card_and_invalid_symbol_have_no_button(self):
        friend = notification.build_tradingview_keyboard("SOLUSDT", "5", include_review_actions=False)
        odd = notification.build_tradingview_keyboard("SOL-PERP", "5", include_review_actions=True)
        self.assertNotIn("📊 MetaScalp", [t for t, _ in self._texts(friend) + self._texts(odd)])

    def test_all_signal_senders_use_the_common_card_builder(self):
        # Wedge/Triangle (notification.send_signal), L-shape and Ikigai Box cards all come
        # from build_tradingview_keyboard with the owner flag, so new patterns inherit it.
        for module in ("notification.py", "l_shape_scanner.py", "ikigai_box_scanner.py"):
            source = (ROOT / module).read_text(encoding="utf-8")
            with self.subTest(module=module):
                self.assertIn("build_tradingview_keyboard(", source)
                self.assertIn("include_review_actions=", source)

    def test_robot_button_is_kept(self):
        owner = notification.build_tradingview_keyboard(
            "SOLUSDT", "5", include_review_actions=True, robot_candidate_id="cand-1")
        self.assertIn(("🤖 Робот", "robot:approve:cand-1"), self._texts(owner))


class CallbackTest(unittest.TestCase):
    def _query(self, user_id="1", data="ms:open:SOLUSDT", markup_data="ms:open:SOLUSDT"):
        return {"id": "cb", "from": {"id": user_id}, "data": data,
                "message": {"chat": {"id": -100},
                            "reply_markup": {"inline_keyboard": [[{"text": "📊 MetaScalp",
                                                                   "callback_data": markup_data}]]}}}

    def _run(self, query, result="MetaScalp: открыт стакан SOLUSDT"):
        with patch.object(telegram_monitoring, "_owner_id", return_value="1"), \
                patch.object(telegram_monitoring, "_answer_callback") as answer, \
                patch.object(metascalp_bridge, "open_order_book", return_value=result) as opener:
            handled = telegram_monitoring._process_metascalp_callback(query)
        return handled, answer, opener

    def test_owner_tap_opens_order_book_and_answers(self):
        handled, answer, opener = self._run(self._query())
        self.assertTrue(handled)
        opener.assert_called_once_with("SOLUSDT")
        answer.assert_called_once_with("cb", "MetaScalp: открыт стакан SOLUSDT")

    def test_non_owner_is_refused_without_call(self):
        handled, answer, opener = self._run(self._query(user_id="2"))
        self.assertTrue(handled)
        opener.assert_not_called()
        answer.assert_called_once_with("cb", "Недостаточно прав")

    def test_symbol_must_come_from_the_signal_button(self):
        for query in (self._query(data="ms:open:DOGEUSDT"), self._query(data="ms:open:bad")):
            with self.subTest(data=query["data"]):
                handled, answer, opener = self._run(query)
                self.assertTrue(handled)
                opener.assert_not_called()
                answer.assert_called_once_with("cb", "Некорректный тикер сигнала")

    def test_metascalp_failure_is_reported_to_telegram(self):
        with patch.object(telegram_monitoring, "_owner_id", return_value="1"), \
                patch.object(telegram_monitoring, "_answer_callback") as answer, \
                patch.object(metascalp_bridge, "open_order_book",
                             side_effect=metascalp_bridge.MetaScalpError("MetaScalp не запущен")):
            telegram_monitoring._process_metascalp_callback(self._query())
        answer.assert_called_once_with("cb", "MetaScalp не запущен")

    def test_other_callbacks_are_not_claimed(self):
        self.assertFalse(telegram_monitoring._process_metascalp_callback({"data": "robot:view:feed"}))


if __name__ == "__main__":
    unittest.main()
