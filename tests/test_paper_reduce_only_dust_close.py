"""Issue #450: PAPER-only reduce-only close of a position below min notional.

Guard tests cover the exemption boundary; the runtime test reproduces the
CELOUSDT dust through the normal ledger on a temporary PAPER DB and closes it
through the standard Full Close path. No network and no real DB.
"""

from __future__ import annotations

import tempfile
import time
from dataclasses import replace
from decimal import Decimal
from pathlib import Path

import pytest

from terminal.api.models import (
    ClientActionId, CommandResultStatus, FullCloseCommandRequest, MarketCommandRequest,
    VolumeRequest, VolumeUnit,
)
from terminal.application.pretrade_guard import (
    ExactQuantityIntent, IntentClassification, NotionalIntent, RejectionCode,
)
from terminal.domain.models import (
    Category, OrderSide, PositionKey, PositionSide, Price, Quantity, Symbol, TradingAccountId,
)
from terminal.market_data.models import BookHealth, NormalizedOrderBook, PriceLevel
from terminal.exchange.events import InstrumentSnapshot
from terminal.runtime.paper_runtime import PaperRuntime
from tests.test_terminal_pretrade_guard import (
    context, enabled_guard, instrument, limit, market,
)


def _dust_guard(enabled: bool = True):
    return replace(enabled_guard(), paper_reduce_only_below_min_notional=enabled)


def _exact(side, quantity, price="20000"):
    return market(side=side, volume=ExactQuantityIntent(Decimal(quantity)), price=Decimal(price))


DUST = context(position_side=PositionSide.LONG, confirmed_position_quantity=Decimal("0.0002"))
DUST_SHORT = context(position_side=PositionSide.SHORT, confirmed_position_quantity=Decimal("0.0002"))
# 0.0002 BTC @ 20000 = 4 USDT < 5 USDT min notional; min qty 0.001 lowered to 0.0001.
SMALL_MIN = {"instrument": instrument(min_order_quantity=Decimal("0.0001"), quantity_step=Decimal("0.0001"))}
DUST = replace(DUST, **SMALL_MIN)
DUST_SHORT = replace(DUST_SHORT, **SMALL_MIN)


@pytest.mark.parametrize("ctx, side", [(DUST, OrderSide.SELL), (DUST_SHORT, OrderSide.BUY)])
def test_paper_close_of_long_and_short_dust_is_admitted_reduce_only(ctx, side):
    decision = _dust_guard().evaluate(_exact(side, "0.0002"), ctx)
    assert decision.admitted, decision
    assert decision.request.classification is IntentClassification.CLOSE
    assert decision.request.reduce_only is True
    assert decision.request.final_quantity == Decimal("0.0002")


def test_partial_reduce_below_min_notional_is_admitted_and_never_flips():
    ctx = replace(DUST, confirmed_position_quantity=Decimal("0.0003"))
    partial = _dust_guard().evaluate(_exact(OrderSide.SELL, "0.0001"), ctx)
    assert partial.admitted and partial.request.classification is IntentClassification.REDUCE
    # An oversized opposite MARKET is capped at flat: closes, never reverses.
    oversized = _dust_guard().evaluate(
        market(side=OrderSide.SELL, volume=NotionalIntent(Decimal("100"))), ctx,
    )
    assert oversized.admitted
    assert oversized.request.classification is IntentClassification.CLOSE
    assert oversized.request.final_quantity == Decimal("0.0003")


def test_default_guard_still_blocks_min_notional_close_like_live():
    decision = enabled_guard().evaluate(_exact(OrderSide.SELL, "0.0002"), DUST)
    assert not decision.admitted
    assert decision.reason_code is RejectionCode.INSUFFICIENT_VOLUME


def test_new_or_increasing_exposure_below_min_notional_is_still_blocked():
    flat = replace(context(), **SMALL_MIN)
    for ctx, side in ((flat, OrderSide.BUY), (DUST, OrderSide.BUY)):
        decision = _dust_guard().evaluate(
            market(side=side, volume=NotionalIntent(Decimal("4"))), ctx,
        )
        assert not decision.admitted
        assert decision.reason_code is RejectionCode.INSUFFICIENT_VOLUME


def test_limit_reduce_below_min_notional_is_not_exempt():
    ctx = replace(DUST, instrument=replace(DUST.instrument, tick_size=Decimal("0.1")))
    decision = _dust_guard().evaluate(limit(OrderSide.SELL, "4", "20000"), ctx)
    assert not decision.admitted
    assert decision.reason_code is RejectionCode.INSUFFICIENT_VOLUME


def test_min_quantity_and_step_still_apply_to_the_close():
    below_min = replace(DUST, instrument=replace(DUST.instrument, min_order_quantity=Decimal("0.001")))
    decision = _dust_guard().evaluate(_exact(OrderSide.SELL, "0.0002"), below_min)
    assert not decision.admitted and decision.reason_code is RejectionCode.INSUFFICIENT_VOLUME
    off_step = _dust_guard().evaluate(_exact(OrderSide.SELL, "0.00015"), DUST)
    assert not off_step.admitted


def test_close_after_flat_is_not_an_order():
    flat = replace(context(), **SMALL_MIN)
    decision = _dust_guard().evaluate(_exact(OrderSide.SELL, "0.0002"), flat)
    assert not decision.admitted


# --- full ledger scenario on a temporary PAPER DB (CELOUSDT-like) -------------

CELO = InstrumentSnapshot(
    Category.LINEAR, "CELOUSDT", "LinearPerpetual", "Trading",
    "CELO", "USDT", "USDT", Decimal("0.00001"), Decimal("1000"),
    Decimal("0.00001"), Decimal("0.1"), Decimal("260000"), Decimal("51000"),
    Decimal("0.1"), Decimal("5"),
)
ACCOUNT = TradingAccountId("paper")
KEY = PositionKey(ACCOUNT, Category.LINEAR, Symbol("CELOUSDT"), 0)


class _Book:
    def __init__(self):
        self.bid, self.ask = "0.07534", "0.07535"

    def get_book(self, symbol):
        return NormalizedOrderBook(
            symbol=symbol,
            bids=(PriceLevel(Price(Decimal(self.bid)), Quantity(Decimal("100000"))),),
            asks=(PriceLevel(Price(Decimal(self.ask)), Quantity(Decimal("100000"))),),
            health=BookHealth.READY, received_at_ms=int(time.time() * 1000), available_depth=1,
        )


def _market(runtime, action, side, usdt, price):
    return runtime.api.market(MarketCommandRequest(
        ClientActionId(action), "CELOUSDT", side,
        VolumeRequest(VolumeUnit.USDT, Decimal(usdt)), Decimal(price), "Percent", Decimal("0.5"),
    ))


def _counts(runtime):
    c = runtime.store._connection
    return tuple(c.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
                 for t in ("executions", "trading_commands"))


def test_celo_like_dust_closes_through_the_ledger_to_synced_flat_once():
    with tempfile.TemporaryDirectory() as temp:
        book = _Book()
        runtime = PaperRuntime(
            Path(temp) / "paper.sqlite3", book_provider=book,
            instrument_snapshot=CELO, instrument_provider=lambda symbol: replace(CELO, symbol=symbol),
        )
        try:
            assert _market(runtime, "buy", OrderSide.BUY, "250", "0.07535").status is CommandResultStatus.COMPLETED
            bought = runtime.store.get_position_projection(KEY).quantity.value
            book.bid, book.ask = "0.07522", "0.07523"
            sell_usdt = str(((bought - Decimal("1.3")) * Decimal("0.07522")).quantize(Decimal("0.00001")))
            assert _market(runtime, "sell", OrderSide.SELL, sell_usdt, "0.07522").status is CommandResultStatus.COMPLETED
            dust = runtime.store.get_position_projection(KEY)
            assert dust.side is PositionSide.LONG and Decimal("0") < dust.quantity.value * Decimal("0.07522") < 5
            pnl_before = dust.realized_pnl
            before = _counts(runtime)

            # The ordinary 5 USDT entry floor still applies on the same symbol.
            assert _market(runtime, "tiny-buy", OrderSide.BUY, "1", "0.07523").status is not CommandResultStatus.COMPLETED

            closed = runtime.api.full_close(FullCloseCommandRequest(ClientActionId("dust-close"), "CELOUSDT"))
            assert closed.status is CommandResultStatus.COMPLETED, closed
            flat = runtime.store.get_position_projection(KEY)
            assert (flat.side, flat.quantity.value, flat.sync_state) == (PositionSide.FLAT, Decimal("0"), "synced")
            assert flat.realized_pnl != pnl_before  # PnL realized through the ledger
            after = _counts(runtime)
            assert after[0] == before[0] + 1  # exactly one closing execution
            sells = [f for f in runtime.store.load_executions_for_symbol(ACCOUNT, Symbol("CELOUSDT"))
                     if f.side is OrderSide.SELL]
            assert sells[-1].quantity.value == dust.quantity.value

            again = runtime.api.full_close(FullCloseCommandRequest(ClientActionId("dust-close-2"), "CELOUSDT"))
            assert again.status is CommandResultStatus.COMPLETED
            assert _counts(runtime) == after  # no second execution or command
        finally:
            runtime.close()
