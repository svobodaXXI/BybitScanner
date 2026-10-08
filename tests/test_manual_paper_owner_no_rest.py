"""P0-B final: manual PAPER Market / full-close / close_all make zero network
calls on the serialized owner thread.

Before: the HTTP handlers queued runtime.market()/full_close()/close_all() onto
the owner, which executed through TradingApplication -> PaperMarketExecutor ->
LiveOrderBookProvider.get_book(): a synchronous Bybit REST request (10 s
timeout) per symbol whenever the Workspace was not streaming it (close_all:
one per open position, serialized).

After: the HTTP handler thread reads the execution book (streamed first,
REST only there; close_all reads its symbols in parallel) and hands it to the
owner as immutable evidence. The owner uses the current streamed book, else
that evidence, never the provider; the book is validated (symbol, freshness)
before any command is persisted.

These tests drive the real HTTP handlers against a real SerializedPaperRuntime;
REST calls are attributed by thread name.
"""

from __future__ import annotations

from dataclasses import replace
from decimal import Decimal
from http.server import ThreadingHTTPServer
import json
from pathlib import Path
import tempfile
import threading
import time
import unittest
import urllib.error
import urllib.request

from terminal.api.models import VolumeUnit
from terminal.domain.models import Category, PositionKey, PositionSide, Symbol, TradingAccountId
from terminal.runtime.paper_http_server import (
    LiveOrderBookProvider, PaperHttpHandler, PublicOrderBookBuffer, SerializedPaperRuntime,
)
from terminal.runtime.paper_runtime import PaperRuntime
from tests.test_robot_protection_close_no_rest import _Context, _Hub, _SlowRestSession, _stream
from tests.test_terminal_paper_runtime import _instrument


ACCOUNT = TradingAccountId("paper")
OWNER_THREAD = "paper-runtime-owner"
SYMBOLS = ("BTCUSDT", "ETHUSDT", "SOLUSDT")
VOLUME_UNIT = VolumeUnit.USDT.value


def _market_body(symbol: str, action_id: str) -> dict:
    return {
        "client_action_id": action_id, "symbol": symbol, "side": "Buy",
        "volume": {"unit": VOLUME_UNIT, "amount": "321"},
        "sizing_reference_price": "64250", "slippage_type": "Percent", "slippage_value": "0.5",
    }


class _Fixture:
    """Real HTTP server over a real owner. Workspace shows ONGUSDT; REST answers
    after ``rest_delay_s`` with bid 64249.5 / ask 64250.5 for any symbol."""

    def __init__(self, temp: str, *, rest_delay_s: float = 2.0, stream_btc: bool = False,
                 rest_available: bool = True) -> None:
        self.session = _SlowRestSession(delay_s=0.0, bid="64249.5", ask="64250.5")
        self.btc = PublicOrderBookBuffer("BTCUSDT")
        workspace = PublicOrderBookBuffer("ONGUSDT")
        _stream(workspace, bid="0.2", ask="0.21")
        self.provider = LiveOrderBookProvider(
            workspace, rest_session=self.session if rest_available else None,
            hub=_Hub(_Context("BTCUSDT", self.btc)) if stream_btc else None,
        )
        primary = _instrument()
        holder: dict[str, PaperRuntime] = {}

        def factory() -> PaperRuntime:
            holder["owner"] = PaperRuntime(
                Path(temp) / "paper.sqlite3", book_provider=self.provider,
                instrument_snapshot=primary,
                instrument_provider=lambda symbol: replace(primary, symbol=symbol),
            )
            return holder["owner"]

        self.serialized = SerializedPaperRuntime(factory)
        self.owner = holder["owner"]
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), PaperHttpHandler)
        self.server.runtime = self.serialized
        self._thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self._thread.start()
        self.rest_delay_s = rest_delay_s

    def post(self, path: str, body: dict) -> tuple[dict, float]:
        request = urllib.request.Request(
            f"http://127.0.0.1:{self.server.server_port}{path}",
            data=json.dumps(body).encode("utf-8"),
            headers={"Content-Type": "application/json"}, method="POST",
        )
        started = time.perf_counter()
        try:
            payload = json.load(urllib.request.urlopen(request, timeout=60))
        except urllib.error.HTTPError as error:
            payload = json.load(error)
        return payload, (time.perf_counter() - started) * 1000

    def open_position(self, symbol: str, action_id: str) -> None:
        """Setup entry with fast REST (not the measured operation)."""
        delay, self.session.delay_s = self.session.delay_s, 0.0
        payload, _ = self.post("/api/market", _market_body(symbol, action_id))
        assert payload["status"] == "completed", payload
        self.session.delay_s = delay
        self.session.calls.clear()

    def arm(self) -> None:
        self.session.delay_s = self.rest_delay_s

    def owner_rest_calls(self) -> list:
        return [call for call in self.session.calls if call[0] == OWNER_THREAD]

    def slowest_owner_ms(self) -> float:
        return float(self.serialized.protection_ingress_metrics()["slowest_task_ms"])

    def executions(self):
        return self.serialized.call(lambda owner: [
            (item.side.value, item.price.value, item.quantity.value)
            for item in owner.store.load_executions()
        ])

    def side(self, symbol: str):
        key = PositionKey(ACCOUNT, Category.LINEAR, Symbol(symbol), 0)
        position = self.serialized.call(lambda owner: owner.store.get_position_projection(key))
        return None if position is None else position.side

    def command_count(self) -> int:
        return self.serialized.call(lambda owner: owner.store._connection.execute(
            "SELECT COUNT(*) FROM trading_commands").fetchone()[0])

    def close(self) -> None:
        self.server.shutdown()
        self._thread.join(timeout=5)
        self.server.server_close()
        self.serialized.close()


class ManualMarketTests(unittest.TestCase):
    def test_unstreamed_market_fills_on_off_owner_evidence_with_zero_owner_rest(self):
        with tempfile.TemporaryDirectory() as temp:
            fixture = _Fixture(temp)
            try:
                fixture.arm()
                payload, _ = fixture.post("/api/market", _market_body("BTCUSDT", "m-1"))
                self.assertEqual(payload["status"], "completed")
                self.assertEqual(fixture.owner_rest_calls(), [])
                self.assertEqual(len(fixture.session.calls), 1)  # read once, off the owner
                self.assertLess(fixture.slowest_owner_ms(), 1000)
                [(side, price, _qty)] = fixture.executions()
                self.assertEqual((side, price), ("Buy", Decimal("64250.5")))
            finally:
                fixture.close()

    def test_streamed_book_takes_precedence_over_evidence(self):
        with tempfile.TemporaryDirectory() as temp:
            fixture = _Fixture(temp, stream_btc=True)
            try:
                _stream(fixture.btc, bid="64299.5", ask="64300.5")
                payload, _ = fixture.post("/api/market", _market_body("BTCUSDT", "m-2"))
                self.assertEqual(payload["status"], "completed")
                self.assertEqual(fixture.session.calls, [])
                self.assertEqual(fixture.executions()[0][1], Decimal("64300.5"))
            finally:
                fixture.close()

    def test_missing_evidence_persists_nothing_and_fills_nothing(self):
        with tempfile.TemporaryDirectory() as temp:
            fixture = _Fixture(temp, rest_available=False)
            try:
                payload, _ = fixture.post("/api/market", _market_body("BTCUSDT", "m-3"))
                self.assertNotEqual(payload["status"], "completed")
                self.assertEqual(fixture.executions(), [])
                self.assertEqual(fixture.command_count(), 0)
                self.assertIsNone(fixture.side("BTCUSDT"))
            finally:
                fixture.close()

    def test_manual_market_identity_semantics_are_unchanged(self):
        # Manual Market has never deduplicated on client_action_id (each submit
        # gets a fresh canonical command identity); this slice must not change that.
        with tempfile.TemporaryDirectory() as temp:
            fixture = _Fixture(temp, stream_btc=True)
            try:
                _stream(fixture.btc, bid="64299.5", ask="64300.5")
                fixture.post("/api/market", _market_body("BTCUSDT", "m-4"))
                _stream(fixture.btc, bid="64299.5", ask="64300.5")
                fixture.post("/api/market", _market_body("BTCUSDT", "m-4"))
                self.assertEqual(len(fixture.executions()), 2)
                self.assertEqual(fixture.command_count(), 2)
                self.assertEqual(fixture.session.calls, [])
            finally:
                fixture.close()


class ManualFullCloseTests(unittest.TestCase):
    def test_full_close_uses_off_owner_evidence_and_cannot_reverse(self):
        with tempfile.TemporaryDirectory() as temp:
            fixture = _Fixture(temp)
            try:
                fixture.open_position("BTCUSDT", "open-btc")
                fixture.arm()
                payload, _ = fixture.post(
                    "/api/full-close", {"client_action_id": "fc-1", "symbol": "BTCUSDT"},
                )
                self.assertEqual(payload["status"], "completed")
                self.assertEqual(fixture.owner_rest_calls(), [])
                self.assertEqual(len(fixture.session.calls), 1)
                self.assertLess(fixture.slowest_owner_ms(), 1000)
                entry, close = fixture.executions()
                self.assertEqual((close[0], close[1]), ("Sell", Decimal("64249.5")))
                self.assertEqual(close[2], entry[2])
                self.assertEqual(fixture.side("BTCUSDT"), PositionSide.FLAT)

                # Repeat on a flat position: no-op, never a reversal.
                again, _ = fixture.post(
                    "/api/full-close", {"client_action_id": "fc-2", "symbol": "BTCUSDT"},
                )
                self.assertEqual(again["status"], "completed")
                self.assertEqual(len(fixture.executions()), 2)
                self.assertEqual(fixture.side("BTCUSDT"), PositionSide.FLAT)
            finally:
                fixture.close()

    def test_full_close_without_evidence_fails_closed(self):
        with tempfile.TemporaryDirectory() as temp:
            fixture = _Fixture(temp)
            try:
                fixture.open_position("BTCUSDT", "open-btc")
                fixture.provider._rest_session = None  # REST gone, no stream
                payload, _ = fixture.post(
                    "/api/full-close", {"client_action_id": "fc-3", "symbol": "BTCUSDT"},
                )
                self.assertNotEqual(payload["status"], "completed")
                self.assertEqual(len(fixture.executions()), 1)
                self.assertEqual(fixture.side("BTCUSDT"), PositionSide.LONG)
                self.assertEqual(fixture.command_count(), 1)
            finally:
                fixture.close()


class ManualCloseAllTests(unittest.TestCase):
    def _open_three(self, fixture: _Fixture) -> None:
        for symbol in SYMBOLS:
            fixture.open_position(symbol, f"open-{symbol}")

    def test_close_all_reads_symbols_in_parallel_off_owner(self):
        with tempfile.TemporaryDirectory() as temp:
            fixture = _Fixture(temp)
            try:
                self._open_three(fixture)
                fixture.arm()
                payload, wall_ms = fixture.post("/api/close-all", {"client_action_id": "ca-1"})
                self.assertEqual(
                    [item["status"] for item in payload["results"]], ["completed"] * 3,
                )
                self.assertEqual(fixture.owner_rest_calls(), [])
                self.assertEqual(len(fixture.session.calls), 3)
                self.assertLess(fixture.slowest_owner_ms(), 1000)
                # Three 2 s reads overlap (they used to serialize on the owner).
                self.assertLess(wall_ms, 5000)
                for symbol in SYMBOLS:
                    self.assertEqual(fixture.side(symbol), PositionSide.FLAT)
                closes = fixture.executions()[3:]
                self.assertEqual([item[0] for item in closes], ["Sell"] * 3)
                # Deterministic order: positions as listed by the store.
                self.assertEqual(
                    [item["symbol"] for item in payload["positions"]], [],
                )

                # Replay + new request after everything is flat: no-ops.
                for action in ("ca-1", "ca-2"):
                    again, _ = fixture.post("/api/close-all", {"client_action_id": action})
                    self.assertEqual(again["results"], [])
                self.assertEqual(len(fixture.executions()), 6)
            finally:
                fixture.close()

    def test_close_all_reports_unavailable_symbol_and_continues(self):
        with tempfile.TemporaryDirectory() as temp:
            fixture = _Fixture(temp)
            try:
                self._open_three(fixture)
                original = fixture.provider.get_book

                def flaky(symbol):
                    if symbol.value == "ETHUSDT":
                        return None  # no evidence for this one
                    return original(symbol)

                fixture.provider.get_book = flaky
                payload, _ = fixture.post("/api/close-all", {"client_action_id": "ca-3"})
                by_symbol = dict(zip(
                    fixture.serialized.call(lambda owner: owner.manual_open_symbols()) or SYMBOLS,
                    [None] * 3,
                ))
                statuses = sorted(item["status"] for item in payload["results"])
                self.assertEqual(statuses, ["completed", "completed", "unavailable"])
                self.assertEqual(fixture.side("ETHUSDT"), PositionSide.LONG)
                self.assertEqual(fixture.side("BTCUSDT"), PositionSide.FLAT)
                self.assertEqual(fixture.side("SOLUSDT"), PositionSide.FLAT)
                self.assertEqual([p["symbol"] for p in payload["positions"]], ["ETHUSDT"])
                del by_symbol
            finally:
                fixture.close()


class OwnerNetworkInventoryGuardTests(unittest.TestCase):
    """Static guard for the PAPER owner-thread zero-network invariant."""

    def test_every_paper_market_submit_site_hands_in_explicit_evidence(self):
        import re

        source = Path("terminal/runtime/paper_runtime.py").read_text(encoding="utf-8")
        sites = []
        for match in re.finditer(r"(?:self|runtime)\.(?:_robot_api|api)\.(?:market|full_close)\(", source):
            depth, index = 1, match.end()
            while depth:
                depth += {"(": 1, ")": -1}.get(source[index], 0)
                index += 1
            sites.append(source[match.start():index])
        # market, full_close, close_all, _robot_market, _robot_full_close,
        # late-admission submit, Box manual close, owner-thread Box emergency close.
        self.assertEqual(len(sites), 8, sites)
        for site in sites:
            self.assertIn("market_book=", site, site)

    def test_provider_get_book_on_owner_code_is_only_the_guarded_monitor_branch(self):
        source = Path("terminal/runtime/paper_runtime.py").read_text(encoding="utf-8")
        reads = [line.strip() for line in source.splitlines() if "_book_provider.get_book(" in line]
        # The monitor-thread branch of _dispatch_robot_market_book (guarded by
        # store.is_owned_by_current_thread()); everything else is streamed-only.
        self.assertEqual(reads, ["return self._book_provider.get_book(normalized)"])
        guard = source.index("if streamed is not None or self.store.is_owned_by_current_thread():")
        self.assertLess(guard, source.index("return self._book_provider.get_book(normalized)"))


if __name__ == "__main__":
    unittest.main()
