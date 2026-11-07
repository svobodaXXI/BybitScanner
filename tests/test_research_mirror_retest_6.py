from decimal import Decimal as D

import pytest

from geometry.naked_retest import Boundary
from tools.research_mirror_retest_6 import (
    AMBIGUOUS,
    CLOSED,
    FEE,
    FILLED_NONE,
    NOT_EVALUABLE,
    OPEN_AT_END,
    Trade,
    favourable_line_value,
    infer_tick,
    simulate,
)

MINUTE = 60_000


def bar(i, o, h, l, c):
    return {"open_time_ms": i * MINUTE, "close_time_ms": (i + 1) * MINUTE,
            "open": o, "high": h, "low": l, "close": c, "closed": True}


def long_trade(fraction=D(1), retest=None, entries=((D("100"), D("1")),)):
    return Trade("LONG", list(entries), D("95"), D("110"), 0, fraction, D("0.01"), retest)


def test_touch_is_not_a_fill_and_trade_through_is():
    assert simulate(long_trade(), [bar(0, 101, 102, 100, 101)])["status"] == FILLED_NONE
    result = simulate(long_trade(), [bar(0, 101, 102, 99.9, 101), bar(1, 101, 110.5, 100.5, 110)])
    assert (result["status"], result["exit"]) == (CLOSED, "TAKE")
    assert float(result["pnl"]) == pytest.approx(float(D(10) - FEE * (D(100) + D(110))))


def test_take_in_the_fill_candle_is_not_assumed():
    result = simulate(long_trade(), [bar(0, 101, 111, 99, 105)])
    assert result["status"] == OPEN_AT_END


def test_fill_then_stop_in_one_candle_is_a_stop_by_path_order():
    result = simulate(long_trade(), [bar(0, 101, 101, 94, 95)])
    assert (result["status"], result["exit"]) == (CLOSED, "STOP")


def test_stop_and_take_in_one_later_candle_is_ambiguous_with_bounds():
    result = simulate(long_trade(), [bar(0, 101, 101, 99, 100), bar(1, 100, 111, 94, 100)])
    assert result["status"] == AMBIGUOUS
    assert result["pnl_pessimistic"] < 0 < result["pnl_optimistic"]


def test_mirror_partial_take_moves_stop_to_net_break_even_and_retest_closes_rest():
    retest = {"time_ms": 3 * MINUTE, "price": 112.0}
    candles = [bar(0, 101, 101, 99, 100), bar(1, 100, 110.5, 100, 110), bar(2, 110, 111, 108, 109),
               bar(3, 112, 112, 112, 112)]
    trade = long_trade(D("0.25"), retest)
    result = simulate(trade, candles)
    assert (result["status"], result["exit"], result["partial_take"]) == (CLOSED, "RETEST", True)
    assert trade.events[0]["be_stop"] == "NET_BREAK_EVEN_STOP"
    expected = D("0.25") * 10 + D("0.75") * 12 - FEE * (D(100) + D("0.25") * 110 + D("0.75") * 112)
    assert float(result["pnl"]) == pytest.approx(float(expected))


def test_mirror_break_even_stop_keeps_net_pnl_non_negative():
    candles = [bar(0, 101, 101, 99, 100), bar(1, 100, 110.5, 100, 110), bar(2, 110, 110, 90, 91)]
    result = simulate(long_trade(D("0.25")), candles)
    assert result["exit"] == "BREAK_EVEN_STOP" and result["pnl"] >= 0


def test_retest_before_any_fill_cancels_the_entries():
    retest = {"time_ms": MINUTE, "price": 120.0}
    result = simulate(long_trade(D("0.25"), retest), [bar(0, 101, 102, 100.5, 101), bar(1, 101, 102, 99, 100)])
    assert (result["status"], result["reason"]) == (FILLED_NONE, "retest_before_fill")


def test_grid_fill_after_partial_take_is_not_evaluable():
    entries = ((D("100"), D("1")), (D("98"), D("1")))
    candles = [bar(0, 101, 101, 99.5, 100), bar(1, 100, 110.5, 100, 110), bar(2, 110, 110, 97, 98)]
    result = simulate(long_trade(D("0.25"), entries=entries), candles)
    assert result["status"] == NOT_EVALUABLE


def test_infer_tick_and_conservative_line_target():
    assert infer_tick([["0", "1.2340", "1.25", "1.2", "1.231"]]) == D("0.001")
    rising = Boundary("b", 0, 100.0, 1.0 / MINUTE, 0)
    assert favourable_line_value(rising, "LONG", MINUTE) == D("101.0")
    assert favourable_line_value(rising, "SHORT", MINUTE) is None
