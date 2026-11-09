"""Focused, network-free evidence for isolated manual MAIN order lifecycle."""
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace

import pytest

from terminal.application.manual_main_trading import (
    ManualMainTradeBlocked, ManualMainTradeLedger, ManualMainTrader,
)


ACCOUNT = "bybit-main-one"
BASE = {
    "confirmed": True, "account_id": ACCOUNT, "session_generation": 3,
    "client_action_id": "test-action-0001", "symbol": "BTCUSDT",
}
MARKET = {
    **BASE, "side": "Buy",
    "volume": {"unit": "usdt", "amount": "10"},
    "sizing_reference_price": "100",
}


class FakeValidator:
    def validate(self, _creds):
        return SimpleNamespace(environment="MAINNET", read_only=False)


class FakeAccounts:
    def __init__(self):
        self.stored = SimpleNamespace(
            environment="MAINNET", read_only=False, api_key="test", api_secret="test")
        self._validator = FakeValidator()
        self.snapshot = {
            "status": "READY", "refresh_generation": 3,
            "positions": [{"symbol": "BTCUSDT", "side": "Long", "size": "0.2"}],
            "orders": [{"account_id": ACCOUNT, "symbol": "BTCUSDT",
                        "order_id": "order-exchange-1", "quantity": "0.2",
                        "status": "open"}],
        }

    def _lookup(self, account):
        if account != ACCOUNT:
            raise LookupError("account_unknown")
        return self.stored

    def summary(self, account):
        self._lookup(account)
        return self.snapshot


class FakeBybit:
    def __init__(self, *, fail=False, response=None):
        self.calls = []
        self.fail = fail
        self.response = response or {"retCode": 0, "result": {"orderId": "exchange-1"}}

    def get_instruments_info(self, **kwargs):
        return {"retCode": 0, "result": {"list": [{
            "symbol": kwargs["symbol"],
            "lotSizeFilter": {"qtyStep": "0.01", "minOrderQty": "0.01"},
        }]}}

    def get_tickers(self, **kwargs):
        return {"retCode": 0, "result": {"list": [{
            "symbol": kwargs["symbol"], "markPrice": "100",
        }]}}

    def get_positions(self, **kwargs):
        return {"retCode": 0, "result": {"list": [{
            "symbol": kwargs["symbol"], "side": "Buy", "size": "0.2",
            "positionIdx": 0,
        }]}}

    def place_order(self, **kwargs):
        self.calls.append(("place", kwargs))
        if self.fail:
            raise TimeoutError("exchange status unknown")
        return self.response

    def amend_order(self, **kwargs):
        self.calls.append(("amend", kwargs))
        return self.response

    def cancel_order(self, **kwargs):
        self.calls.append(("cancel", kwargs))
        return self.response

    def set_trading_stop(self, **kwargs):
        self.calls.append(("stop", kwargs))
        return self.response


@pytest.fixture
def setup(tmp_path: Path):
    ledger = ManualMainTradeLedger(tmp_path / "actions.sqlite3")
    accounts = FakeAccounts()
    api = FakeBybit()
    trader = ManualMainTrader(
        accounts, ledger, enabled=True, max_notional=Decimal("100"),
        http_factory=lambda **kwargs: api,
    )
    try:
        yield trader, accounts, api, ledger
    finally:
        ledger.close()


def test_market_ack_uses_real_symbol_lot_and_no_duplicate_execution(setup):
    trader, _, api, _ = setup
    result = trader.submit("market", MARKET)
    assert result["status"] == "accepted_pending"
    assert result["order_id"] == "exchange-1"
    assert len(api.calls) == 1
    assert Decimal(api.calls[0][1]["qty"]) == Decimal("0.10")
    assert trader.submit("market", MARKET) == result
    assert len(api.calls) == 1
    with pytest.raises(ManualMainTradeBlocked, match="client_action_conflict"):
        trader.submit("market", {**MARKET, "side": "Sell"})


def test_exchange_timeout_is_fenced_without_retry_across_restart(tmp_path):
    path = tmp_path / "actions.sqlite3"
    accounts = FakeAccounts()
    api = FakeBybit(fail=True)
    first = ManualMainTradeLedger(path)
    trader = ManualMainTrader(accounts, first, enabled=True,
                              max_notional=Decimal("100"),
                              http_factory=lambda **kwargs: api)
    result = trader.submit("market", MARKET)
    assert result["status"] == "unknown"
    assert result["reconciliation_required"] is True
    first.close()
    second = ManualMainTradeLedger(path)
    try:
        restarted = ManualMainTrader(
            accounts, second, enabled=True, max_notional=Decimal("100"),
            http_factory=lambda **kwargs: api)
        assert restarted.submit("market", MARKET)["status"] == "unknown"
        with pytest.raises(ManualMainTradeBlocked, match="main_reconciliation_required"):
            restarted.submit("market", {**MARKET, "client_action_id": "test-action-0002"})
        assert len(api.calls) == 1
    finally:
        second.close()


def test_missing_owner_confirmation_or_permission_never_trades(setup):
    trader, accounts, api, _ = setup
    with pytest.raises(ManualMainTradeBlocked, match="owner_confirmation_required"):
        trader.submit("market", {**MARKET, "confirmed": False})
    accounts.stored.read_only = True
    with pytest.raises(ManualMainTradeBlocked, match="credentials_not_authorized"):
        trader.submit("market", MARKET)
    assert api.calls == []


def test_session_and_notional_gates_precede_any_exchange_call(setup):
    trader, _, api, _ = setup
    with pytest.raises(ManualMainTradeBlocked, match="stale_main_account_authority"):
        trader.submit("market", {**MARKET, "session_generation": 2})
    with pytest.raises(ManualMainTradeBlocked, match="manual_main_notional_ceiling"):
        trader.submit("market", {**MARKET, "volume": {"unit": "usdt", "amount": "1000"}})
    assert api.calls == []


def test_full_close_uses_exchange_verified_reduce_only_order(setup):
    trader, _, api, _ = setup
    result = trader.submit("full-close", BASE)
    assert result["status"] == "accepted_pending"
    assert len(api.calls) == 1
    order = api.calls[0][1]
    assert order["reduceOnly"] is True
    assert order["side"] == "Sell"
    assert order["qty"] == "0.2"
    assert order["positionIdx"] == 0


def test_disabled_gateway_never_issues_commands(setup):
    _, accounts, api, ledger = setup
    trader = ManualMainTrader(accounts, ledger, enabled=False,
                              max_notional=Decimal("100"),
                              http_factory=lambda **kwargs: api)
    with pytest.raises(ManualMainTradeBlocked, match="manual_main_live_disabled"):
        trader.submit("market", MARKET)
    assert api.calls == []


def test_stop_take_and_cancel_send_only_account_scoped_mutations(setup):
    trader, _, api, _ = setup
    stop = {**BASE, "stop_loss": "99", "take_profit": None}
    assert trader.submit("stop", stop)["status"] == "accepted_pending"
    assert api.calls[0][0] == "stop"
    assert api.calls[0][1]["stopLoss"] == "99"
    assert "takeProfit" not in api.calls[0][1]
    cancel = {**BASE, "client_action_id": "test-action-0002",
              "order_id": "order-exchange-1"}
    assert trader.submit("limit/cancel", cancel)["status"] == "accepted_pending"
    assert api.calls[1][0] == "cancel"
