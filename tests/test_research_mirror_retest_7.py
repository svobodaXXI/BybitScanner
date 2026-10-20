import sqlite3
from decimal import Decimal as D
from pathlib import Path

import pytest

import tools.research_mirror_retest_6 as replay
from tools.research_mirror_retest_7 import (
    adverse_fraction,
    measure_stop_slippage,
    open_copy_readonly,
    quantile,
)

MINUTE = 60_000


def bar(i, o, h, l, c):
    return {"open_time_ms": i * MINUTE, "close_time_ms": (i + 1) * MINUTE,
            "open": o, "high": h, "low": l, "close": c, "closed": True}


def stop_trade():
    return replay.Trade("LONG", [(D("100"), D("1"))], D("95"), D("110"), 0, D(1), D("0.01"), None)


@pytest.fixture(autouse=True)
def reset_slippage():
    yield
    replay.STOP_SLIPPAGE = D(0)


def test_adverse_fraction_is_direction_aware_and_signed():
    assert adverse_fraction("LONG", D("100"), D("99")) == D("0.01")
    assert adverse_fraction("LONG", D("100"), D("101")) == D("-0.01")
    assert adverse_fraction("SHORT", D("100"), D("101")) == D("0.01")
    assert adverse_fraction("SHORT", D("100"), D("99")) == D("-0.01")
    with pytest.raises(ValueError):
        adverse_fraction("FLAT", D("100"), D("99"))
    with pytest.raises(ValueError):
        adverse_fraction("LONG", D("0"), D("99"))


def test_quantile_interpolates_and_rejects_empty():
    assert quantile([1.0, 2.0, 3.0, 4.0], 0.5) == 2.5
    assert quantile([5.0], 0.9) == 5.0
    assert quantile([0.0, 10.0], 0.75) == 7.5
    with pytest.raises(ValueError):
        quantile([], 0.5)


def test_zero_slippage_reproduces_the_stop_fill_at_the_stop_price():
    candles = [bar(0, D("100"), D("101"), D("99"), D("100")), bar(1, D("100"), D("100"), D("94"), D("95"))]
    baseline = replay.simulate(stop_trade(), candles)
    assert baseline["exit"] == "STOP"
    assert baseline["pnl"] == D("-5") - replay.FEE * (D("100") + D("95"))


def test_positive_slippage_makes_long_and_short_stop_exits_worse():
    long_candles = [bar(0, D("100"), D("101"), D("99"), D("100")), bar(1, D("100"), D("100"), D("94"), D("95"))]
    base_long = replay.simulate(stop_trade(), long_candles)["pnl"]
    replay.STOP_SLIPPAGE = D("0.01")
    assert replay.simulate(stop_trade(), long_candles)["pnl"] < base_long

    short = replay.Trade("SHORT", [(D("100"), D("1"))], D("105"), D("90"), 0, D(1), D("0.01"), None)
    short_candles = [bar(0, D("100"), D("101"), D("99"), D("100")), bar(1, D("100"), D("106"), D("100"), D("105"))]
    replay.STOP_SLIPPAGE = D(0)
    base_short = replay.simulate(short, short_candles)["pnl"]
    replay.STOP_SLIPPAGE = D("0.01")
    assert replay.simulate(short, short_candles)["pnl"] < base_short


def test_limit_take_exit_is_never_slipped():
    candles = [bar(0, D("100"), D("101"), D("99"), D("100")), bar(1, D("100"), D("111"), D("100"), D("110"))]
    base = replay.simulate(stop_trade(), candles)
    replay.STOP_SLIPPAGE = D("0.05")
    assert replay.simulate(stop_trade(), candles)["pnl"] == base["pnl"]
    assert base["exit"] == "TAKE"


def test_measurement_uses_only_stop_exits_and_reports_other_reasons(tmp_path: Path):
    path = tmp_path / "copy.sqlite3"
    with sqlite3.connect(path) as connection:
        connection.execute(
            "create table robot_trades (trade_id text, symbol text, direction text, stop_price text, "
            "exit_price text, entry_time_ms integer, exit_time_ms integer, exit_reason text)")
        connection.executemany("insert into robot_trades values (?,?,?,?,?,?,?,?)", [
            ("a", "X", "LONG", "100", "99", 0, 60_000, "STOP"),
            ("b", "Y", "SHORT", "100", "99.5", 0, 120_000, "STOP"),
            ("c", "Z", "LONG", "100", "110", 0, 60_000, "TAKE"),
            ("d", "W", "LONG", "100", "90", 0, 60_000, "EMERGENCY_CLOSE"),
        ])
    with open_copy_readonly(path) as connection:
        measured = measure_stop_slippage(connection)

    stats = measured["stats"]
    assert stats["n_stop_exits"] == 2
    assert stats["adverse_fraction"]["max"] == pytest.approx(0.01)
    assert stats["adverse_fraction"]["min"] == pytest.approx(-0.005)
    assert stats["better_than_stop"] == 1
    assert stats["other_exit_reasons"] == {"EMERGENCY_CLOSE": 1, "STOP": 2, "TAKE": 1}
    assert [item["trade_id"] for item in measured["samples"]] == ["a", "b"]


def test_read_only_open_cannot_write_and_live_db_is_refused(tmp_path: Path):
    path = tmp_path / "copy.sqlite3"
    sqlite3.connect(path).execute("create table t (x)").connection.close()
    with open_copy_readonly(path) as connection, pytest.raises(sqlite3.OperationalError):
        connection.execute("insert into t values (1)")

    live = tmp_path / "BybitScanner" / "paper_runtime.sqlite3"
    live.parent.mkdir()
    live.write_bytes(b"")
    with pytest.raises(SystemExit):
        open_copy_readonly(live)
    with pytest.raises(SystemExit):
        open_copy_readonly(tmp_path / "missing.sqlite3")
