import tempfile
from dataclasses import replace
from decimal import Decimal
from pathlib import Path

from terminal.api.models import (
    ClientActionId,
    CloseAllCommandRequest,
    CommandResultStatus,
    FullCloseCommandRequest,
    LimitCommandRequest,
    MarketCommandRequest,
    VolumeRequest,
    VolumeUnit,
    PaperLimitCancelRequest,
    PaperLimitAmendRequest,
    TimeInForce,
)
from terminal.domain.models import Category, OrderSide, Price, Quantity, Symbol
from terminal.exchange.events import InstrumentSnapshot
from terminal.market_data.models import BookHealth, NormalizedOrderBook, PriceLevel
from terminal.runtime.paper_runtime import PaperRuntime
from terminal.persistence.sqlite_store import DuplicateIdentity


class StaticBookProvider:
    def get_book(self, symbol: Symbol) -> NormalizedOrderBook:
        return NormalizedOrderBook(
            symbol=symbol,
            bids=(PriceLevel(Price(Decimal("64249.5")), Quantity(Decimal("10"))),),
            asks=(PriceLevel(Price(Decimal("64250.5")), Quantity(Decimal("10"))),),
            health=BookHealth.READY,
            received_at_ms=int(__import__("time").time() * 1000),
            available_depth=1,
        )


class ToggleBookProvider(StaticBookProvider):
    unavailable_symbols: set[str]
    stale_symbols: set[str]

    def __init__(self) -> None:
        self.unavailable_symbols = set()
        self.stale_symbols = set()

    def get_book(self, symbol: Symbol) -> NormalizedOrderBook | None:
        if symbol.value in self.unavailable_symbols:
            return None
        book = super().get_book(symbol)
        if symbol.value in self.stale_symbols:
            return replace(book, received_at_ms=0)
        return book


def _instrument() -> InstrumentSnapshot:
    return InstrumentSnapshot(
        Category.LINEAR, "BTCUSDT", "LinearPerpetual", "Trading",
        "BTC", "USDT", "USDT", Decimal("0.5"), Decimal("1000000"),
        Decimal("0.5"), Decimal("0.001"), Decimal("100"), Decimal("50"),
        Decimal("0.001"), Decimal("5"),
    )


def _runtime(path: Path) -> PaperRuntime:
    primary = _instrument()
    return PaperRuntime(
        path,
        book_provider=StaticBookProvider(),
        instrument_snapshot=primary,
        instrument_provider=lambda symbol: replace(primary, symbol=symbol),
    )


def test_composed_paper_runtime_market_buy_completes():
    with tempfile.TemporaryDirectory() as temp:
        runtime = _runtime(Path(temp) / "paper.sqlite3")
        try:
            result = runtime.api.market(
                MarketCommandRequest(
                    ClientActionId("runtime-buy-1"),
                    "BTCUSDT",
                    OrderSide.BUY,
                    VolumeRequest(VolumeUnit.USDT, Decimal("321")),
                    Decimal("64250"),
                    "Percent",
                    Decimal("0.5"),
                )
            )

            assert result.status is CommandResultStatus.COMPLETED
            assert result.command_id is not None
            assert result.reconciliation_required is False
            assert len(runtime.store.load_executions()) == 1
        finally:
            runtime.close()


def test_full_close_uses_authoritative_remaining_quantity_and_flat_repeat_is_noop():
    with tempfile.TemporaryDirectory() as temp:
        runtime = _runtime(Path(temp) / "paper.sqlite3")
        try:
            opened = runtime.api.market(
                MarketCommandRequest(
                    ClientActionId("runtime-open-long"), "BTCUSDT", OrderSide.BUY,
                    VolumeRequest(VolumeUnit.USDT, Decimal("321")), Decimal("64250"),
                    "Percent", Decimal("0.5"),
                )
            )
            assert opened.status is CommandResultStatus.COMPLETED
            before_close = runtime.paper_state("BTCUSDT")
            assert before_close["position_side"] == "Long"
            assert before_close["average_entry"] is not None

            closed = runtime.api.full_close(
                FullCloseCommandRequest(ClientActionId("runtime-close-long"), "BTCUSDT")
            )
            assert closed.status is CommandResultStatus.COMPLETED
            state = runtime.paper_state("BTCUSDT")
            assert state["position_side"] == "Flat"
            assert state["average_entry"] is None
            assert state["position_quantity"] == "0"
            assert state["engaged_notional_usdt"] == "0"
            assert state["engaged_wv"] == "0.0"
            execution_count = len(runtime.store.load_executions())

            repeated = runtime.api.full_close(
                FullCloseCommandRequest(ClientActionId("runtime-close-flat"), "BTCUSDT")
            )
            assert repeated.status is CommandResultStatus.COMPLETED
            assert repeated.reason_code == "already_flat"
            assert len(runtime.store.load_executions()) == execution_count
        finally:
            runtime.close()


def test_full_close_closes_short_without_flipping_long():
    with tempfile.TemporaryDirectory() as temp:
        runtime = _runtime(Path(temp) / "paper.sqlite3")
        try:
            opened = runtime.api.market(
                MarketCommandRequest(
                    ClientActionId("runtime-open-short"), "BTCUSDT", OrderSide.SELL,
                    VolumeRequest(VolumeUnit.USDT, Decimal("321")), Decimal("64250"),
                    "Percent", Decimal("0.5"),
                )
            )
            assert opened.status is CommandResultStatus.COMPLETED
            assert runtime.paper_state("BTCUSDT")["position_side"] == "Short"
            closed = runtime.api.full_close(
                FullCloseCommandRequest(ClientActionId("runtime-close-short"), "BTCUSDT")
            )
            assert closed.status is CommandResultStatus.COMPLETED
            assert runtime.paper_state("BTCUSDT")["position_side"] == "Flat"
        finally:
            runtime.close()


def test_paper_limit_create_is_durable_idempotent_and_cancel_is_safe():
    with tempfile.TemporaryDirectory() as temp:
        runtime = _runtime(Path(temp) / "paper.sqlite3")
        try:
            request = LimitCommandRequest(
                ClientActionId("limit-buy-1"), "BTCUSDT", OrderSide.BUY,
                VolumeRequest(VolumeUnit.USDT, Decimal("321")),
                Decimal("64000"), Decimal("64000"), TimeInForce.GTC,
            )
            created = runtime.create_limit(request)
            duplicate = runtime.create_limit(request)
            assert created.status is CommandResultStatus.COMPLETED
            assert duplicate.order_id == created.order_id
            assert duplicate.reason_code == "duplicate_action"
            try:
                runtime.create_limit(LimitCommandRequest(
                    ClientActionId("limit-buy-1"), "BTCUSDT", OrderSide.SELL,
                    VolumeRequest(VolumeUnit.USDT, Decimal("321")),
                    Decimal("64000"), Decimal("64000"), TimeInForce.GTC,
                ))
            except DuplicateIdentity:
                pass
            else:
                raise AssertionError("conflicting duplicate client action must fail closed")
            active = runtime.paper_state("BTCUSDT")["active_limit_orders"]
            assert len(active) == 1
            assert active[0]["side"] == "Buy"
            assert active[0]["time_in_force"] == "GTC"

            cancelled = runtime.cancel_limit(PaperLimitCancelRequest(
                ClientActionId("limit-cancel-1"), "BTCUSDT", created.order_id,
            ))
            repeated = runtime.cancel_limit(PaperLimitCancelRequest(
                ClientActionId("limit-cancel-2"), "BTCUSDT", created.order_id,
            ))
            assert cancelled.status is CommandResultStatus.COMPLETED
            assert repeated.status is CommandResultStatus.COMPLETED
            assert repeated.reason_code == "already_absent"
            assert runtime.paper_state("BTCUSDT")["active_limit_orders"] == []
        finally:
            runtime.close()


def test_paper_sell_limit_uses_shared_sizing_and_gtc():
    with tempfile.TemporaryDirectory() as temp:
        runtime = _runtime(Path(temp) / "paper.sqlite3")
        try:
            result = runtime.create_limit(LimitCommandRequest(
                ClientActionId("limit-sell-1"), "BTCUSDT", OrderSide.SELL,
                VolumeRequest(VolumeUnit.USDT, Decimal("321")),
                Decimal("65000"), Decimal("65000"), TimeInForce.GTC,
            ))
            assert result.status is CommandResultStatus.COMPLETED
            active = runtime.paper_state("BTCUSDT")["active_limit_orders"]
            assert active[0]["side"] == "Sell"
            assert active[0]["quantity"] == "0.004"
            assert active[0]["time_in_force"] == "GTC"
        finally:
            runtime.close()


def test_paper_limit_amend_reprices_in_place_and_is_durable_idempotent():
    with tempfile.TemporaryDirectory() as temp:
        runtime = _runtime(Path(temp) / "paper.sqlite3")
        try:
            created = runtime.create_limit(LimitCommandRequest(
                ClientActionId("limit-amend-create"), "BTCUSDT", OrderSide.BUY,
                VolumeRequest(VolumeUnit.USDT, Decimal("321")),
                Decimal("64000"), Decimal("64000"), TimeInForce.GTC,
            ))
            before = runtime.paper_state("BTCUSDT")["active_limit_orders"][0]
            request = PaperLimitAmendRequest(
                ClientActionId("limit-amend-1"), "BTCUSDT", created.order_id,
                Decimal("64100.24"),
            )
            amended = runtime.amend_limit(request)
            duplicate = runtime.amend_limit(request)
            after = runtime.paper_state("BTCUSDT")["active_limit_orders"][0]

            assert amended.reason_code == "amended"
            assert duplicate.reason_code == "duplicate_action"
            assert after["order_id"] == before["order_id"]
            assert after["side"] == before["side"]
            assert after["quantity"] == before["quantity"]
            assert after["time_in_force"] == "GTC"
            assert after["price"] == "64100.0"
            assert len(runtime.store.load_active_paper_limits(Symbol("BTCUSDT"))) == 1

            try:
                runtime.amend_limit(PaperLimitAmendRequest(
                    ClientActionId("limit-amend-1"), "BTCUSDT", created.order_id,
                    Decimal("63900"),
                ))
            except DuplicateIdentity:
                pass
            else:
                raise AssertionError("conflicting amend action identity must fail closed")
        finally:
            runtime.close()


def test_paper_limit_amend_missing_or_inactive_fails_closed():
    with tempfile.TemporaryDirectory() as temp:
        runtime = _runtime(Path(temp) / "paper.sqlite3")
        try:
            for order_id in ("missing",):
                try:
                    runtime.amend_limit(PaperLimitAmendRequest(
                        ClientActionId("amend-missing"), "BTCUSDT", order_id,
                        Decimal("64100"),
                    ))
                except ValueError:
                    pass
                else:
                    raise AssertionError("missing order amend must fail closed")

            created = runtime.create_limit(LimitCommandRequest(
                ClientActionId("inactive-create"), "BTCUSDT", OrderSide.SELL,
                VolumeRequest(VolumeUnit.USDT, Decimal("321")),
                Decimal("65000"), Decimal("65000"), TimeInForce.GTC,
            ))
            runtime.cancel_limit(PaperLimitCancelRequest(
                ClientActionId("inactive-cancel"), "BTCUSDT", created.order_id,
            ))
            try:
                runtime.amend_limit(PaperLimitAmendRequest(
                    ClientActionId("amend-inactive"), "BTCUSDT", created.order_id,
                    Decimal("65100"),
                ))
            except ValueError:
                pass
            else:
                raise AssertionError("inactive order amend must fail closed")
        finally:
            runtime.close()


def test_account_inventory_is_multi_symbol_and_close_is_symbol_scoped():
    with tempfile.TemporaryDirectory() as temp:
        runtime = _runtime(Path(temp) / "paper.sqlite3")
        try:
            for symbol, side, action in (
                ("BTCUSDT", OrderSide.BUY, "inventory-btc"),
                ("ETHUSDT", OrderSide.SELL, "inventory-eth"),
            ):
                result = runtime.api.market(MarketCommandRequest(
                    ClientActionId(action), symbol, side,
                    VolumeRequest(VolumeUnit.USDT, Decimal("321")), Decimal("64250"),
                    "Percent", Decimal("0.5"),
                ))
                assert result.status is CommandResultStatus.COMPLETED

            inventory = runtime.open_positions()
            assert inventory.account_id == "paper"
            assert [item.symbol for item in inventory.positions] == ["BTCUSDT", "ETHUSDT"]
            assert [item.position_side for item in inventory.positions] == ["Long", "Short"]

            closed = runtime.api.full_close(FullCloseCommandRequest(
                ClientActionId("inventory-close-btc"), "BTCUSDT",
            ))
            assert closed.status is CommandResultStatus.COMPLETED
            assert [item.symbol for item in runtime.open_positions().positions] == ["ETHUSDT"]
            assert runtime.paper_state("BTCUSDT")["position_side"] == "Flat"
            assert runtime.paper_state("ETHUSDT")["position_side"] == "Short"
        finally:
            runtime.close()


def test_account_inventory_projects_per_symbol_price_pnl_and_tick_size():
    with tempfile.TemporaryDirectory() as temp:
        primary = replace(_instrument(), tick_size=Decimal("0.10"))
        runtime = PaperRuntime(
            Path(temp) / "paper.sqlite3",
            book_provider=StaticBookProvider(),
            instrument_snapshot=primary,
            instrument_provider=lambda symbol: replace(
                primary, symbol=symbol,
                tick_size=Decimal("0.10") if symbol == "BTCUSDT" else Decimal("0.01"),
            ),
        )
        try:
            opened = runtime.api.market(MarketCommandRequest(
                ClientActionId("inventory-pnl-btc"), "BTCUSDT", OrderSide.BUY,
                VolumeRequest(VolumeUnit.USDT, Decimal("321")), Decimal("64250"),
                "Percent", Decimal("0.5"),
            ))
            assert opened.status is CommandResultStatus.COMPLETED
            item = runtime.open_positions().positions[0]
            assert item.current_price == Decimal("64250.0")
            assert item.unrealized_pnl is not None
            assert item.tick_size == Decimal("0.10")
        finally:
            runtime.close()


def test_account_inventory_fails_closed_when_symbol_price_is_unavailable():
    with tempfile.TemporaryDirectory() as temp:
        provider = ToggleBookProvider()
        runtime = PaperRuntime(
            Path(temp) / "paper.sqlite3",
            book_provider=provider,
            instrument_snapshot=_instrument(),
            instrument_provider=lambda symbol: replace(_instrument(), symbol=symbol),
        )
        try:
            runtime.api.market(MarketCommandRequest(
                ClientActionId("inventory-no-price-eth"), "ETHUSDT", OrderSide.BUY,
                VolumeRequest(VolumeUnit.USDT, Decimal("321")), Decimal("64250"),
                "Percent", Decimal("0.5"),
            ))
            provider.unavailable_symbols.add("ETHUSDT")
            item = runtime.open_positions().positions[0]
            assert item.symbol == "ETHUSDT"
            assert item.current_price is None
            assert item.unrealized_pnl is None
        finally:
            runtime.close()


def test_account_inventory_fails_closed_when_symbol_price_is_stale():
    with tempfile.TemporaryDirectory() as temp:
        provider = ToggleBookProvider()
        runtime = PaperRuntime(
            Path(temp) / "paper.sqlite3",
            book_provider=provider,
            instrument_snapshot=_instrument(),
        )
        try:
            runtime.api.market(MarketCommandRequest(
                ClientActionId("inventory-stale-price"), "BTCUSDT", OrderSide.BUY,
                VolumeRequest(VolumeUnit.USDT, Decimal("321")), Decimal("64250"),
                "Percent", Decimal("0.5"),
            ))
            provider.stale_symbols.add("BTCUSDT")
            item = runtime.open_positions().positions[0]
            assert item.current_price is None
            assert item.unrealized_pnl is None
        finally:
            runtime.close()


def test_close_all_uses_stable_children_and_does_not_duplicate_closes():
    with tempfile.TemporaryDirectory() as temp:
        runtime = _runtime(Path(temp) / "paper.sqlite3")
        try:
            for symbol, action in (("BTCUSDT", "bulk-open-btc"), ("ETHUSDT", "bulk-open-eth")):
                runtime.api.market(MarketCommandRequest(
                    ClientActionId(action), symbol, OrderSide.BUY,
                    VolumeRequest(VolumeUnit.USDT, Decimal("321")), Decimal("64250"),
                    "Percent", Decimal("0.5"),
                ))
            request = CloseAllCommandRequest(ClientActionId("bulk-close-1"))
            first = runtime.close_all(request)
            execution_count = len(runtime.store.load_executions())
            second = runtime.close_all(request)

            assert first.positions == ()
            assert second.positions == ()
            assert len(first.results) == 2
            assert len(runtime.store.load_executions()) == execution_count
            assert runtime.paper_state("BTCUSDT")["position_side"] == "Flat"
            assert runtime.paper_state("ETHUSDT")["position_side"] == "Flat"
        finally:
            runtime.close()


import unittest


def load_tests(loader, tests, pattern):
    return unittest.TestSuite(
        unittest.FunctionTestCase(test)
        for test in (
            test_composed_paper_runtime_market_buy_completes,
            test_full_close_uses_authoritative_remaining_quantity_and_flat_repeat_is_noop,
            test_full_close_closes_short_without_flipping_long,
            test_account_inventory_is_multi_symbol_and_close_is_symbol_scoped,
            test_account_inventory_projects_per_symbol_price_pnl_and_tick_size,
            test_account_inventory_fails_closed_when_symbol_price_is_unavailable,
            test_account_inventory_fails_closed_when_symbol_price_is_stale,
            test_close_all_uses_stable_children_and_does_not_duplicate_closes,
            test_paper_limit_create_is_durable_idempotent_and_cancel_is_safe,
            test_paper_sell_limit_uses_shared_sizing_and_gtc,
            test_paper_limit_amend_reprices_in_place_and_is_durable_idempotent,
            test_paper_limit_amend_missing_or_inactive_fails_closed,
        )
    )
