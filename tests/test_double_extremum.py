from decimal import Decimal

from geometry.double_extremum import detect_confirmed_double_extremum


def bar(h, l, c):
    return {"high": str(h), "low": str(l), "close": str(c)}


def test_confirmed_double_top_only_last_close_crosses_neckline():
    candles = [
        bar(100, 98, 99), bar(104, 99, 103), bar(110, 102, 108),
        bar(105, 100, 102), bar(103, 95, 98), bar(105, 99, 103),
        bar(109.8, 102, 107), bar(106, 98, 101), bar(103, 94, 94.5),
    ]
    found = detect_confirmed_double_extremum(candles)
    assert found is not None
    assert found.pattern == "Double Top"
    assert found.direction == "SHORT"
    assert found.neckline == Decimal("95")
    assert found.stop == Decimal("110")
    assert found.confirmed_index == len(candles) - 1
    # No candle may be claimed confirmed if its body has not closed.
    assert detect_confirmed_double_extremum(candles[:-1]) is None
    shadow = [dict(c) for c in candles]
    shadow[-1]["close"] = "96"
    assert detect_confirmed_double_extremum(shadow) is None


def test_confirmed_double_bottom_long_and_wick_only_rejected():
    candles = [
        bar(102, 98, 100), bar(101, 94, 96), bar(98, 90, 92),
        bar(101, 95, 99), bar(106, 99, 104), bar(102, 97, 99),
        bar(99, 90.2, 92), bar(104, 96, 100), bar(107, 98, 106.5),
    ]
    found = detect_confirmed_double_extremum(candles)
    assert found is not None
    assert found.pattern == "Double Bottom"
    assert found.neckline == Decimal("106")
    assert found.stop == Decimal("90")
    wick = [dict(c) for c in candles]
    wick[-1]["close"] = "105"
    assert detect_confirmed_double_extremum(wick) is None


def test_unequal_extrema_or_old_confirmation_rejected():
    candles = [
        bar(100, 98, 99), bar(104, 99, 103), bar(110, 102, 108),
        bar(105, 100, 102), bar(103, 95, 98), bar(105, 99, 103),
        bar(120, 102, 107), bar(106, 98, 101), bar(103, 94, 94.5),
    ]
    assert detect_confirmed_double_extremum(candles) is None
    candles[6] = bar(109.8, 102, 107)
    candles.append(bar(100, 92, 93))
    assert detect_confirmed_double_extremum(candles) is None
