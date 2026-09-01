import ast
import unittest
from decimal import Decimal
from pathlib import Path

from terminal.domain.models import PositionSide, TradingAccountId
from terminal.exchange.bybit_v5_adapter import (
    AuthenticationError,
    BybitCredentials,
    BybitV5ReadAdapter,
    RateLimitError,
    TransportTimeout,
    UnsupportedPayload,
)
from terminal.exchange.events import (
    ExecutionEvent,
    NormalizedOrderStatus,
    NormalizedOrderType,
    OrderEvent,
    PositionEvent,
    StreamLifecycleKind,
)
from terminal.exchange.normalization import (
    IncompatiblePositionMode,
    PayloadNormalizationError,
    normalize_execution,
    normalize_execution_message,
    normalize_order,
    normalize_position,
)


ACCOUNT = TradingAccountId("terminal-account")


def order_payload(**overrides):
    payload = {
        "category": "linear",
        "symbol": "BTCUSDT",
        "orderId": "order-1",
        "orderLinkId": "terminal-command-1",
        "positionIdx": 0,
        "side": "Buy",
        "orderType": "Limit",
        "price": "65000.125000000000000001",
        "qty": "0.010000000000000001",
        "cumExecQty": "0",
        "leavesQty": "0.010000000000000001",
        "avgPrice": "",
        "orderStatus": "New",
        "reduceOnly": False,
        "closeOnTrigger": False,
        "stopOrderType": "",
        "triggerPrice": "",
        "takeProfit": "",
        "stopLoss": "",
        "tpslMode": "",
        "createdTime": "1000",
        "updatedTime": "1001",
    }
    payload.update(overrides)
    return payload


def execution_payload(**overrides):
    payload = {
        "category": "linear",
        "symbol": "BTCUSDT",
        "execId": "exec-1",
        "orderId": "order-1",
        "orderLinkId": "terminal-command-1",
        "side": "Buy",
        "execPrice": "65000.125000000000000001",
        "execQty": "0.001234567890123456",
        "execFee": "-0.000000000000000001",
        "execValue": "80.246913573024683912",
        "isMaker": True,
        "execTime": "2000",
        "seq": 99,
    }
    payload.update(overrides)
    return payload


def position_payload(**overrides):
    payload = {
        "category": "linear",
        "symbol": "BTCUSDT",
        "positionIdx": 0,
        "side": "Buy",
        "size": "0.001234567890123456",
        "avgPrice": "65000.125000000000000001",
        "markPrice": "65100.000000000000000001",
        "positionValue": "80.246913573024683912",
        "unrealisedPnl": "0.123456789012345678",
        "curRealisedPnl": "-0.000000000000000001",
        "cumRealisedPnl": "10.000000000000000001",
        "positionStatus": "Normal",
        "takeProfit": "70000.1",
        "stopLoss": "60000.1",
        "trailingStop": "",
        "seq": 100,
        "updatedTime": "3000",
    }
    payload.update(overrides)
    return payload


def instrument_payload():
    return {
        "category": "linear",
        "symbol": "BTCUSDT",
        "contractType": "LinearPerpetual",
        "status": "Trading",
        "baseCoin": "BTC",
        "quoteCoin": "USDT",
        "settleCoin": "USDT",
        "priceFilter": {
            "minPrice": "0.01",
            "maxPrice": "1999999.99",
            "tickSize": "0.010000000000000001",
        },
        "lotSizeFilter": {
            "minOrderQty": "0.001",
            "maxOrderQty": "100.000000000000000001",
            "maxMktOrderQty": "50.000000000000000001",
            "qtyStep": "0.001000000000000001",
            "minNotionalValue": "5.000000000000000001",
        },
    }


def response(items, *, cursor=""):
    return {
        "retCode": 0,
        "retMsg": "OK",
        "result": {
            "category": "linear",
            "list": items,
            "nextPageCursor": cursor,
        },
    }


class FakeHTTP:
    def __init__(self):
        self.calls = []
        self.responses = {}

    def _call(self, method, kwargs):
        self.calls.append((method, kwargs))
        value = self.responses[method]
        if callable(value):
            return value(kwargs)
        return value

    def get_open_orders(self, **kwargs):
        return self._call("get_open_orders", kwargs)

    def get_order_history(self, **kwargs):
        return self._call("get_order_history", kwargs)

    def get_positions(self, **kwargs):
        return self._call("get_positions", kwargs)

    def get_executions(self, **kwargs):
        return self._call("get_executions", kwargs)

    def get_instruments_info(self, **kwargs):
        return self._call("get_instruments_info", kwargs)

    def get_wallet_balance(self, **kwargs):
        return self._call("get_wallet_balance", kwargs)


class FakeWebSocket:
    def __init__(self):
        self.callbacks = {}
        self.connected = True
        self.exited = False

    def subscribe(self, topic, callback):
        self.callbacks[topic] = callback

    def is_connected(self):
        return self.connected

    def exit(self):
        self.connected = False
        self.exited = True


class BybitNormalizationTests(unittest.TestCase):
    def test_account_wide_reads_use_usdt_linear_scope_and_normalize_wallet(self):
        http = FakeHTTP()
        http.responses = {
            "get_open_orders": response([order_payload()]),
            "get_positions": response([position_payload(), position_payload(symbol="ETHUSDT", size="0", side="")]),
            "get_wallet_balance": {
                "retCode": 0, "retMsg": "OK", "time": 4321,
                "result": {"list": [{
                    "accountType": "UNIFIED", "totalWalletBalance": "99.75",
                    "totalEquity": "101.25", "totalMarginBalance": "91.5",
                    "totalAvailableBalance": "80.5", "accountIMRate": "0.12",
                    "totalInitialMargin": "11", "totalPerpUPL": "-8.25",
                    "coin": [{
                        "coin": "USDT", "walletBalance": "12.34", "equity": "10.5",
                        "availableToWithdraw": "", "availableToBorrow": "", "locked": "0",
                        "unrealisedPnl": "-1.84", "spotBorrow": "0", "borrowAmount": "0",
                        "usdValue": "10.5",
                    }],
                }]},
            },
        }
        factory_calls = []
        adapter = BybitV5ReadAdapter(
            ACCOUNT, BybitCredentials("key", "secret"), testnet=True,
            http_factory=lambda **kwargs: factory_calls.append(kwargs) or http,
        )
        self.assertEqual(len(adapter.list_all_active_orders()), 1)
        self.assertEqual(len(adapter.list_open_positions()), 1)
        wallet = adapter.get_wallet_snapshot()
        self.assertEqual(wallet.wallet_balance_usdt, Decimal("99.75"))
        self.assertEqual(wallet.total_equity_usdt, Decimal("101.25"))
        self.assertEqual(wallet.available_balance_usdt, Decimal("101.25"))
        self.assertNotEqual(wallet.wallet_balance_usdt, Decimal("12.34"))
        self.assertEqual(wallet.balance_provenance["account.totalAvailableBalance"], "80.5")
        self.assertEqual(wallet.balance_provenance["account.totalEquity"], "101.25")
        self.assertEqual(wallet.balance_provenance["USDT.equity"], "10.5")
        self.assertEqual(wallet.exchange_time_ms, 4321)
        self.assertEqual(factory_calls[0]["timeout"], 10)
        self.assertFalse(factory_calls[0]["force_retry"])
        self.assertFalse(factory_calls[0]["log_requests"])
        self.assertEqual(http.calls[0][1]["settleCoin"], "USDT")
        self.assertEqual(http.calls[1][1]["settleCoin"], "USDT")

    def test_ordinary_and_partially_filled_limit_normalization(self):
        ordinary = normalize_order(order_payload(), ACCOUNT)
        partial = normalize_order(
            order_payload(
                orderStatus="PartiallyFilled",
                cumExecQty="0.004",
                leavesQty="0.006000000000000001",
                avgPrice="64999.99",
            ),
            ACCOUNT,
        )
        self.assertIs(ordinary.order_type, NormalizedOrderType.LIMIT)
        self.assertIs(ordinary.status, NormalizedOrderStatus.OPEN)
        self.assertIs(partial.status, NormalizedOrderStatus.PARTIALLY_FILLED_OPEN)
        self.assertEqual(partial.cumulative_filled_quantity, Decimal("0.004"))
        self.assertEqual(partial.leaves_quantity, Decimal("0.006000000000000001"))

    def test_conditional_tpsl_order_preserves_protection_semantics(self):
        event = normalize_order(
            order_payload(
                orderStatus="Untriggered",
                stopOrderType="StopLoss",
                triggerPrice="60000.100000000000000001",
                takeProfit="70000.1",
                stopLoss="60000.1",
                tpslMode="Full",
                reduceOnly=True,
                closeOnTrigger=True,
            ),
            ACCOUNT,
        )
        self.assertIs(event.status, NormalizedOrderStatus.PENDING_TRIGGER)
        self.assertEqual(event.stop_order_type, "StopLoss")
        self.assertEqual(event.trigger_price, Decimal("60000.100000000000000001"))
        self.assertTrue(event.reduce_only)
        self.assertTrue(event.close_on_trigger)

    def test_external_empty_and_foreign_order_link_ids_are_preserved_as_facts(self):
        empty = normalize_order(order_payload(orderLinkId=""), ACCOUNT)
        foreign = normalize_order(order_payload(orderLinkId="metascalp-42"), ACCOUNT)
        self.assertIsNone(empty.order_link_id)
        self.assertEqual(foreign.order_link_id, "metascalp-42")
        self.assertFalse(hasattr(foreign, "origin"))

    def test_unknown_order_enum_is_deterministic_and_raw_value_is_retained(self):
        event = normalize_order(
            order_payload(orderType="FutureType", orderStatus="FutureStatus"), ACCOUNT
        )
        self.assertIs(event.order_type, NormalizedOrderType.UNKNOWN)
        self.assertIs(event.status, NormalizedOrderStatus.UNKNOWN)
        self.assertEqual(event.raw_order_type, "FutureType")
        self.assertEqual(event.raw_status, "FutureStatus")

    def test_final_order_empty_leaves_quantity_normalizes_to_zero(self):
        event = normalize_order(
            order_payload(orderStatus="Filled", leavesQty="", cumExecQty="0.01"),
            ACCOUNT,
        )
        self.assertIs(event.status, NormalizedOrderStatus.FILLED)
        self.assertEqual(event.leaves_quantity, Decimal("0"))

    def test_execution_decimal_and_dedup_identity_are_stable_for_rest_and_ws(self):
        raw = execution_payload()
        rest = normalize_execution(raw, ACCOUNT)
        websocket = normalize_execution_message(
            {"topic": "execution.linear", "data": [raw]}, ACCOUNT
        )[0]
        self.assertEqual(rest.dedup_identity, websocket.dedup_identity)
        self.assertEqual(rest.execution_price, Decimal("65000.125000000000000001"))
        self.assertEqual(rest.execution_quantity, Decimal("0.001234567890123456"))
        self.assertEqual(rest.execution_fee, Decimal("-0.000000000000000001"))
        self.assertEqual(rest.execution_value, Decimal("80.246913573024683912"))

    def test_multiple_ws_executions_become_separate_events(self):
        events = normalize_execution_message(
            {
                "topic": "execution.linear",
                "data": [execution_payload(), execution_payload(execId="exec-2")],
            },
            ACCOUNT,
        )
        self.assertEqual(len(events), 2)
        self.assertNotEqual(events[0].dedup_identity, events[1].dedup_identity)

    def test_open_and_flat_position_normalization(self):
        opened = normalize_position(position_payload(), ACCOUNT)
        flat = normalize_position(
            position_payload(
                side="",
                size="0",
                avgPrice="",
                markPrice="",
                positionValue="0",
                unrealisedPnl="0",
                curRealisedPnl="0",
                takeProfit="",
                stopLoss="",
            ),
            ACCOUNT,
        )
        self.assertIs(opened.side, PositionSide.LONG)
        self.assertEqual(opened.position_key.position_idx, 0)
        self.assertEqual(opened.average_entry, Decimal("65000.125000000000000001"))
        self.assertIs(flat.side, PositionSide.FLAT)
        self.assertEqual(flat.size, Decimal("0"))
        self.assertIsNone(flat.average_entry)

    def test_nonzero_position_idx_fails_closed(self):
        with self.assertRaises(IncompatiblePositionMode):
            normalize_position(position_payload(positionIdx=1), ACCOUNT)

    def test_order_and_position_events_are_not_execution_evidence(self):
        self.assertNotIsInstance(normalize_order(order_payload(), ACCOUNT), ExecutionEvent)
        self.assertNotIsInstance(normalize_position(position_payload(), ACCOUNT), ExecutionEvent)
        self.assertIsInstance(normalize_order(order_payload(), ACCOUNT), OrderEvent)
        self.assertIsInstance(normalize_position(position_payload(), ACCOUNT), PositionEvent)

    def test_missing_or_non_decimal_required_field_fails_closed(self):
        missing = order_payload()
        del missing["orderId"]
        with self.assertRaises(PayloadNormalizationError):
            normalize_order(missing, ACCOUNT)
        with self.assertRaises(PayloadNormalizationError):
            normalize_execution(execution_payload(execPrice=1.2), ACCOUNT)


class _AdapterFixture:
    def setUp(self):
        self.http = FakeHTTP()
        self.socket = FakeWebSocket()
        self.http_factory_calls = []
        self.ws_factory_calls = []

        def http_factory(**kwargs):
            self.http_factory_calls.append(kwargs)
            return self.http

        def ws_factory(**kwargs):
            self.ws_factory_calls.append(kwargs)
            return self.socket

        self.adapter = BybitV5ReadAdapter(
            ACCOUNT,
            BybitCredentials("fake-key", "fake-secret"),
            testnet=True,
            http_factory=http_factory,
            websocket_factory=ws_factory,
        )


class BybitReadAdapterTests(_AdapterFixture, unittest.TestCase):

    def test_constructor_is_lazy_and_credentials_repr_is_redacted(self):
        self.assertEqual(self.http_factory_calls, [])
        self.assertEqual(self.ws_factory_calls, [])
        self.assertNotIn("fake-key", repr(BybitCredentials("fake-key", "fake-secret")))
        self.assertNotIn("fake-secret", repr(BybitCredentials("fake-key", "fake-secret")))

    def test_active_order_cursor_pagination_preserves_every_order(self):
        def paginated(kwargs):
            if "cursor" not in kwargs:
                return response([order_payload(orderId="order-1")], cursor="page-2")
            return response([order_payload(orderId="order-2", orderLinkId="")])

        self.http.responses["get_open_orders"] = paginated
        events = self.adapter.list_active_orders("btcusdt")
        self.assertEqual(tuple(item.order_id.value for item in events), ("order-1", "order-2"))
        self.assertEqual(self.http.calls[0][1]["openOnly"], 0)
        self.assertNotIn("orderFilter", self.http.calls[0][1])
        self.assertEqual(self.http.calls[1][1]["cursor"], "page-2")

    def test_order_history_and_execution_history_are_read_only_and_paginated(self):
        self.http.responses["get_order_history"] = response([order_payload()])
        self.http.responses["get_executions"] = response([execution_payload()])
        orders = self.adapter.list_order_history(
            "BTCUSDT", start_time_ms=0, end_time_ms=7 * 24 * 60 * 60 * 1000
        )
        executions = self.adapter.list_executions("BTCUSDT")
        self.assertEqual(len(orders), 1)
        self.assertEqual(len(executions), 1)
        with self.assertRaisesRegex(ValueError, "seven days"):
            self.adapter.list_executions(
                "BTCUSDT", start_time_ms=0, end_time_ms=7 * 24 * 60 * 60 * 1000 + 1
            )

    def test_position_and_instrument_reads_are_normalized(self):
        rest_position = position_payload()
        self.http.responses["get_positions"] = response([rest_position])
        self.http.responses["get_instruments_info"] = response([instrument_payload()])
        position = self.adapter.get_position("BTCUSDT")
        instrument = self.adapter.get_instrument("BTCUSDT")
        self.assertEqual(position.position_key.trading_account_id, ACCOUNT)
        self.assertEqual(instrument.tick_size, Decimal("0.010000000000000001"))
        self.assertEqual(
            instrument.max_market_order_quantity,
            Decimal("50.000000000000000001"),
        )

    def test_authentication_rate_limit_and_timeout_errors_are_normalized(self):
        self.http.responses["get_open_orders"] = {
            "retCode": 10003,
            "retMsg": "invalid key",
        }
        with self.assertRaises(AuthenticationError):
            self.adapter.list_active_orders("BTCUSDT")

        self.http.responses["get_open_orders"] = {
            "retCode": 10006,
            "retMsg": "too many visits",
        }
        with self.assertRaises(RateLimitError):
            self.adapter.list_active_orders("BTCUSDT")

        def timeout(_kwargs):
            raise TimeoutError("fake timeout")

        self.http.responses["get_open_orders"] = timeout
        with self.assertRaises(TransportTimeout):
            self.adapter.list_active_orders("BTCUSDT")

        class FakePybitError(Exception):
            status_code = 10006

        def sdk_rate_limit(_kwargs):
            raise FakePybitError("fake SDK error")

        self.http.responses["get_open_orders"] = sdk_rate_limit
        with self.assertRaises(RateLimitError):
            self.adapter.list_active_orders("BTCUSDT")

    def test_malformed_or_incompatible_response_fails_closed(self):
        self.http.responses["get_positions"] = response(
            [position_payload(positionIdx=1)]
        )
        with self.assertRaises(UnsupportedPayload):
            self.adapter.get_position("BTCUSDT")


class BybitPrivateStreamTests(_AdapterFixture, unittest.TestCase):
    def test_private_subscriptions_are_explicit_and_normalized(self):
        orders = []
        executions = []
        positions = []
        lifecycle = []
        connected = self.adapter.start_private_streams(
            on_order=orders.append,
            on_execution=executions.append,
            on_position=positions.append,
            on_lifecycle=lifecycle.append,
        )
        self.assertEqual(
            set(self.socket.callbacks),
            {"order.linear", "execution.linear", "position.linear"},
        )
        self.assertIs(connected.kind, StreamLifecycleKind.CONNECTED_UNTRUSTED)
        self.assertEqual(lifecycle[0].kind, StreamLifecycleKind.BUFFERING)

        self.socket.callbacks["order.linear"](
            {"topic": "order.linear", "data": [order_payload()]}
        )
        self.socket.callbacks["execution.linear"](
            {
                "topic": "execution.linear",
                "data": [execution_payload(), execution_payload(execId="exec-2")],
            }
        )
        ws_position = position_payload()
        ws_position["entryPrice"] = ws_position.pop("avgPrice")
        self.socket.callbacks["position.linear"](
            {"topic": "position.linear", "data": [ws_position]}
        )
        self.assertEqual(len(orders), 1)
        self.assertEqual(len(executions), 2)
        self.assertEqual(len(positions), 1)

    def test_disconnect_and_bad_payload_require_reconciliation(self):
        lifecycle = []
        self.adapter.start_private_streams(
            on_order=lambda event: None,
            on_execution=lambda event: None,
            on_position=lambda event: None,
            on_lifecycle=lifecycle.append,
        )
        self.socket.callbacks["order.linear"]({"topic": "order.linear", "data": [{}]})
        self.assertIs(lifecycle[-1].kind, StreamLifecycleKind.RECONCILIATION_REQUIRED)
        self.socket.connected = False
        observed = self.adapter.observe_private_stream()
        self.assertIs(observed.kind, StreamLifecycleKind.DISCONNECTED)
        closed = self.adapter.close_private_streams()
        self.assertIs(closed.kind, StreamLifecycleKind.DISCONNECTED)


class BybitStructuralSafetyTests(unittest.TestCase):
    def test_adapter_exposes_no_trading_mutation_api(self):
        public_names = {name for name in dir(BybitV5ReadAdapter) if not name.startswith("_")}
        forbidden = {
            "place_order",
            "create_order",
            "amend_order",
            "cancel_order",
            "cancel_all_orders",
            "set_trading_stop",
            "switch_position_mode",
        }
        self.assertTrue(forbidden.isdisjoint(public_names), forbidden & public_names)

    def test_exchange_package_has_no_scanner_runtime_or_persistence_coupling(self):
        root = Path(__file__).parents[1] / "terminal" / "exchange"
        forbidden = {
            "config",
            "main",
            "scanner",
            "analyzer",
            "bybit_api",
            "notification",
            "telegram_bot",
            "sqlite3",
            "fastapi",
        }
        imported = set()
        for path in root.glob("*.py"):
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    imported.update(alias.name.split(".")[0] for alias in node.names)
                elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
                    imported.add(node.module.split(".")[0])
        self.assertTrue(forbidden.isdisjoint(imported), imported & forbidden)


if __name__ == "__main__":
    unittest.main()
