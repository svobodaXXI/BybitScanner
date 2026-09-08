from decimal import Decimal
from types import SimpleNamespace

from terminal.application.live_market_execution import LiveMarketMutationCoordinator
from terminal.domain.models import OrderSide, Price, Quantity, Symbol
from terminal.market_data.models import BookHealth, NormalizedOrderBook, PriceLevel


def _book(*, received_at_ms: int, bid: str = "0.05145", ask: str = "0.05148"):
    return NormalizedOrderBook(
        symbol=Symbol("NILUSDT"),
        bids=(PriceLevel(Price(Decimal(bid)), Quantity(Decimal("100"))),),
        asks=(PriceLevel(Price(Decimal(ask)), Quantity(Decimal("100"))),),
        health=BookHealth.READY,
        received_at_ms=received_at_ms,
        available_depth=1,
    )


def _coordinator(provider, *, now_ms: int = 2_000):
    coordinator = object.__new__(LiveMarketMutationCoordinator)
    coordinator._book_provider = provider
    coordinator._clock_ms = lambda: now_ms
    return coordinator


def _request(side=OrderSide.BUY):
    return SimpleNamespace(
        symbol="NILUSDT",
        side=side,
        sizing_reference_price=Decimal("0.05148"),
    )


class _Provider:
    def __init__(self, websocket_book, rest_book=None, *, rest_error=None):
        self.websocket_book = websocket_book
        self.rest_book = rest_book
        self.rest_error = rest_error
        self.rest_calls = 0

    def get_book(self, symbol):
        assert symbol == Symbol("NILUSDT")
        return self.websocket_book

    def _load_rest_book(self, symbol):
        assert symbol == Symbol("NILUSDT")
        self.rest_calls += 1
        if self.rest_error is not None:
            raise self.rest_error
        return self.rest_book


def test_fresh_websocket_book_is_used_without_rest_refresh():
    provider = _Provider(_book(received_at_ms=1_500))
    coordinator = _coordinator(provider)

    assert coordinator._fresh_reference_price(_request()) == Decimal("0.05148")
    assert provider.rest_calls == 0


def test_stale_websocket_book_reuses_existing_rest_fallback_for_buy_reference():
    provider = _Provider(
        _book(received_at_ms=500, ask="0.05140"),
        _book(received_at_ms=1_500, ask="0.05152"),
    )
    coordinator = _coordinator(provider)

    assert coordinator._fresh_reference_price(_request()) == Decimal("0.05152")
    assert provider.rest_calls == 1


def test_stale_websocket_book_reuses_existing_rest_fallback_for_sell_reference():
    provider = _Provider(
        _book(received_at_ms=500, bid="0.05130"),
        _book(received_at_ms=1_500, bid="0.05144"),
    )
    coordinator = _coordinator(provider)

    assert coordinator._fresh_reference_price(_request(OrderSide.SELL)) == Decimal("0.05144")
    assert provider.rest_calls == 1


def test_rest_refresh_failure_remains_fail_closed():
    provider = _Provider(_book(received_at_ms=500), rest_error=RuntimeError("offline"))
    coordinator = _coordinator(provider)

    assert coordinator._fresh_reference_price(_request()) is None
    assert provider.rest_calls == 1


def test_rest_refresh_that_is_also_stale_remains_fail_closed():
    provider = _Provider(
        _book(received_at_ms=500),
        _book(received_at_ms=900),
    )
    coordinator = _coordinator(provider)

    assert coordinator._fresh_reference_price(_request()) is None
    assert provider.rest_calls == 1
