import unittest
from decimal import Decimal

from terminal.exchange.bybit_v5_adapter import BybitCredentials
from terminal.exchange.bybit_v5_mutation_adapter import (
    BybitEnvironment,
    BybitV5MutationAdapter,
    LiveAuthorizationRequired,
    MutationDisabled,
    MutationDisposition,
)


class FakeClient:
    def __init__(self, response=None, error=None):
        self.response = response or {"retCode": 0, "result": {"orderId": "o-1"}}
        self.error = error
        self.calls = []

    def _call(self, name, payload):
        self.calls.append((name, payload))
        if self.error:
            raise self.error
        return self.response

    def place_order(self, **payload):
        return self._call("place", payload)

    def amend_order(self, **payload):
        return self._call("amend", payload)

    def cancel_order(self, **payload):
        return self._call("cancel", payload)

    def set_trading_stop(self, **payload):
        return self._call("protection", payload)


class Factory:
    def __init__(self, client):
        self.client = client
        self.calls = []

    def __call__(self, **kwargs):
        self.calls.append(kwargs)
        return self.client


def adapter(client=None, **kwargs):
    client = client or FakeClient()
    factory = Factory(client)
    result = BybitV5MutationAdapter(
        BybitCredentials("fake-key", "fake-secret"),
        environment=kwargs.pop("environment", BybitEnvironment.TESTNET),
        mutations_enabled=kwargs.pop("mutations_enabled", True),
        http_factory=factory,
        **kwargs,
    )
    return result, client, factory


class MutationAdapterTests(unittest.TestCase):
    def test_adapter_kill_switch_is_lazy_and_zero_call(self):
        subject, client, factory = adapter(mutations_enabled=False)
        with self.assertRaises(MutationDisabled):
            subject.cancel_order(symbol="btcusdt", order_id="o")
        self.assertEqual(factory.calls, [])
        self.assertEqual(client.calls, [])

    def test_environment_is_explicit_and_mainnet_has_separate_authorization(self):
        with self.assertRaises(TypeError):
            BybitV5MutationAdapter(BybitCredentials("k", "s"), environment=None)  # type: ignore[arg-type]
        with self.assertRaises(LiveAuthorizationRequired):
            adapter(environment=BybitEnvironment.MAINNET)
        subject, _, factory = adapter(
            environment=BybitEnvironment.MAINNET, live_authorized=True
        )
        subject.cancel_order(symbol="BTCUSDT", order_id="o")
        self.assertFalse(factory.calls[0]["testnet"])
        self.assertFalse(factory.calls[0]["demo"])

    def test_pybit_internal_retry_path_is_structurally_disabled(self):
        subject, _, factory = adapter()
        subject.cancel_order(symbol="BTCUSDT", order_id="o")
        options = factory.calls[0]
        self.assertIs(options["force_retry"], False)
        self.assertEqual(options["retry_codes"], set())
        self.assertTrue(options["retry_codes"])
        self.assertEqual(options["max_retries"], 1)
        self.assertIs(options["log_requests"], False)

    def test_market_and_limit_exact_mapping(self):
        subject, client, _ = adapter()
        subject.create_market_order(
            symbol="btcusdt", side="Buy", qty=Decimal("0.0100"),
            order_link_id="link", reduce_only=True,
            slippage_tolerance_type="Percent", slippage_tolerance=Decimal("0.50"),
        )
        market = client.calls[-1][1]
        self.assertEqual(market["qty"], "0.0100")
        self.assertTrue(market["reduceOnly"])
        self.assertNotIn("price", market)
        subject.create_limit_order(
            symbol="ethusdt", side="Sell", qty=Decimal("2.00"),
            price=Decimal("3210.50"), order_link_id="link-2",
        )
        limit = client.calls[-1][1]
        self.assertEqual(limit["timeInForce"], "GTC")
        self.assertFalse(limit["reduceOnly"])
        self.assertNotIn("slippageTolerance", limit)

    def test_amend_and_cancel_specific_identity_mapping(self):
        subject, client, _ = adapter()
        subject.amend_order(
            symbol="BTCUSDT", order_id="o", qty=Decimal("2"), price=Decimal("100")
        )
        self.assertEqual(client.calls[-1][1]["qty"], "2")
        self.assertNotIn("orderLinkId", client.calls[-1][1])
        subject.cancel_order(symbol="BTCUSDT", order_link_id="external-link")
        self.assertEqual(client.calls[-1][1]["orderLinkId"], "external-link")
        self.assertFalse(hasattr(subject, "cancel_all_orders"))

    def test_full_position_protection_mapping_and_empty_result_ack(self):
        client = FakeClient({"retCode": 0, "result": {}})
        subject, _, factory = adapter(client)
        outcome = subject.set_trading_stop(
            symbol="btcusdt", take_profit=Decimal("120.0"),
            stop_loss=None, tp_trigger_by="MarkPrice", sl_trigger_by="LastPrice",
        )
        payload = client.calls[-1][1]
        self.assertEqual(payload["category"], "linear")
        self.assertEqual(payload["symbol"], "BTCUSDT")
        self.assertEqual(payload["tpslMode"], "Full")
        self.assertEqual(payload["positionIdx"], 0)
        self.assertEqual(payload["takeProfit"], "120.0")
        self.assertEqual(payload["stopLoss"], "0")
        self.assertIs(outcome.disposition, MutationDisposition.ACKNOWLEDGED)
        self.assertEqual(len(client.calls), 1)
        self.assertEqual(factory.calls[0]["max_retries"], 1)

    def test_deterministic_reject_and_ambiguous_conditions_do_not_retry(self):
        deterministic = FakeClient({"retCode": 110012, "retMsg": "margin", "result": {}})
        subject, _, _ = adapter(deterministic)
        outcome = subject.cancel_order(symbol="BTCUSDT", order_id="o")
        self.assertIs(outcome.disposition, MutationDisposition.REJECTED)
        self.assertEqual(len(deterministic.calls), 1)

        ambiguous = FakeClient(error=TimeoutError("contains fake-secret"))
        subject, _, _ = adapter(ambiguous)
        outcome = subject.cancel_order(symbol="BTCUSDT", order_id="o")
        self.assertIs(outcome.disposition, MutationDisposition.UNKNOWN)
        self.assertNotIn("fake-secret", outcome.reason)
        self.assertEqual(len(ambiguous.calls), 1)

    def test_malformed_success_is_unknown_and_credentials_are_redacted(self):
        client = FakeClient({"retCode": 0, "result": {}})
        subject, _, _ = adapter(client)
        outcome = subject.cancel_order(symbol="BTCUSDT", order_id="o")
        self.assertIs(outcome.disposition, MutationDisposition.UNKNOWN)
        self.assertNotIn("fake-key", repr(subject))
        self.assertNotIn("fake-secret", repr(subject))


if __name__ == "__main__":
    unittest.main()
