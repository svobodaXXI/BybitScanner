import sqlite3
from decimal import Decimal as D
from pathlib import Path

import pytest

from tools.research_mirror_retest_7 import open_copy_readonly
from tools.research_mirror_retest_8 import (
    CLASS_CLEAN_FAST,
    CLASS_HANDLING_DELAY,
    CLASS_STOP_MOVED,
    classify,
    handling_delay_ms,
    load_stop_exits,
    report,
)


def case(**overrides):
    values = dict(direction="LONG", recorded_stop=D("100"), trigger_price=D("100"),
                  exit_price=D("99"), delay_ms=500)
    values.update(overrides)
    return classify(**values)


def test_delay_is_event_to_receipt_plus_latch_to_exit_and_unknown_when_missing():
    assert handling_delay_ms(1_000, 1_400, 1_400, 1_900) == 900
    assert handling_delay_ms(2_000, 1_600, 1_600, 1_700) == 100   # negative receipt skew is not a delay
    assert handling_delay_ms(None, 1, 1, 2) is None
    assert handling_delay_ms(1, 2, None, 3) is None


def test_fast_unmoved_stop_is_clean_and_measures_trigger_to_exit():
    result = case()

    assert result["class"] == CLASS_CLEAN_FAST
    assert result["trigger_to_exit_adverse_fraction"] == pytest.approx(0.01)
    assert result["stop_vs_trigger_fraction"] == 0.0


def test_moved_stop_is_classified_before_delay():
    result = case(recorded_stop=D("100"), trigger_price=D("98"), delay_ms=60_000)

    assert result["class"] == CLASS_STOP_MOVED


def test_late_or_untimed_exit_is_handling_delay_not_clean():
    assert case(delay_ms=2_001)["class"] == CLASS_HANDLING_DELAY
    assert case(delay_ms=2_000)["class"] == CLASS_CLEAN_FAST
    assert case(delay_ms=None)["class"] == CLASS_HANDLING_DELAY


def test_short_direction_and_favourable_fill_are_signed_correctly():
    assert case(direction="SHORT", exit_price=D("101"))["trigger_to_exit_adverse_fraction"] == pytest.approx(0.01)
    assert case(exit_price=D("101"))["trigger_to_exit_adverse_fraction"] == pytest.approx(-0.01)


def test_load_and_report_join_obligations_and_split_classes(tmp_path: Path):
    path = tmp_path / "copy.sqlite3"
    with sqlite3.connect(path) as connection:
        connection.execute(
            "create table robot_trades (trade_id text, symbol text, direction text, stop_price text, "
            "exit_price text, exit_time_ms integer, exit_reason text)")
        connection.execute(
            "create table paper_protection_obligations (trade_id text, winning_leg text, trigger_price text, "
            "source_event_at_ms integer, source_received_at_ms integer, latched_at_ms integer)")
        connection.executemany("insert into robot_trades values (?,?,?,?,?,?,?)", [
            ("fast", "A", "LONG", "100", "99.9", 1_500, "STOP"),
            ("slow", "B", "LONG", "100", "95", 100_000, "STOP"),
            ("take", "C", "LONG", "100", "110", 1_500, "TAKE"),
        ])
        connection.executemany("insert into paper_protection_obligations values (?,?,?,?,?,?)", [
            ("fast", "STOP", "100", 1_000, 1_300, 1_300),
            ("slow", "STOP", "100", 1_000, 1_300, 1_300),
            ("take", "TAKE", "110", 1_000, 1_300, 1_300),
        ])
    with open_copy_readonly(path) as connection:
        items = load_stop_exits(connection)

    assert [item["trade_id"] for item in items] == ["fast", "slow"]
    summary = report(items)
    assert summary["n_stop_exits"] == 2
    assert summary["classes"][CLASS_CLEAN_FAST]["count"] == 1
    assert summary["classes"][CLASS_CLEAN_FAST]["adverse"]["max"] == pytest.approx(0.001)
    assert summary["classes"][CLASS_HANDLING_DELAY]["count"] == 1
    assert summary["classes"][CLASS_STOP_MOVED]["count"] == 0
    assert summary["delayed_count_by_threshold_ms"] == {"1000": 1, "2000": 1, "5000": 1}
