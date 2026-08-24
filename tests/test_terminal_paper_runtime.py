import tempfile
from decimal import Decimal
from pathlib import Path

from terminal.api.models import (
    ClientActionId,
    CommandResultStatus,
    FullCloseCommandRequest,
    MarketCommandRequest,
    VolumeRequest,
    VolumeUnit,
)
from terminal.domain.models import OrderSide
from terminal.runtime.paper_runtime import PaperRuntime


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


import unittest


def load_tests(loader, tests, pattern):
    return unittest.TestSuite(
        unittest.FunctionTestCase(test)
        for test in (
            test_composed_paper_runtime_market_buy_completes,
            test_full_close_uses_authoritative_remaining_quantity_and_flat_repeat_is_noop,
            test_full_close_closes_short_without_flipping_long,
        )
    )
