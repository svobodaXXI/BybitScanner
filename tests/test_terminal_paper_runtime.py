import tempfile
from decimal import Decimal
from pathlib import Path

from terminal.api.models import (
    ClientActionId,
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
from terminal.domain.models import OrderSide, Symbol
from terminal.runtime.paper_runtime import PaperRuntime
from terminal.persistence.sqlite_store import DuplicateIdentity


def test_composed_paper_runtime_market_buy_completes():
    with tempfile.TemporaryDirectory() as temp:
        runtime = PaperRuntime(Path(temp) / "paper.sqlite3")
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
        runtime = PaperRuntime(Path(temp) / "paper.sqlite3")
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

            closed = runtime.api.full_close(
                FullCloseCommandRequest(ClientActionId("runtime-close-long"), "BTCUSDT")
            )
            assert closed.status is CommandResultStatus.COMPLETED
            state = runtime.paper_state("BTCUSDT")
            assert state["position_side"] == "Flat"
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
        runtime = PaperRuntime(Path(temp) / "paper.sqlite3")
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
        runtime = PaperRuntime(Path(temp) / "paper.sqlite3")
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
        runtime = PaperRuntime(Path(temp) / "paper.sqlite3")
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
        runtime = PaperRuntime(Path(temp) / "paper.sqlite3")
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
        runtime = PaperRuntime(Path(temp) / "paper.sqlite3")
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


import unittest


def load_tests(loader, tests, pattern):
    return unittest.TestSuite(
        unittest.FunctionTestCase(test)
        for test in (
            test_composed_paper_runtime_market_buy_completes,
            test_full_close_uses_authoritative_remaining_quantity_and_flat_repeat_is_noop,
            test_full_close_closes_short_without_flipping_long,
            test_paper_limit_create_is_durable_idempotent_and_cancel_is_safe,
            test_paper_sell_limit_uses_shared_sizing_and_gtc,
            test_paper_limit_amend_reprices_in_place_and_is_durable_idempotent,
            test_paper_limit_amend_missing_or_inactive_fails_closed,
        )
    )
