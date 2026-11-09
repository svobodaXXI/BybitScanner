"""M1 causal feed and real source Scanner -> Robot evidence regressions."""
from __future__ import annotations

from decimal import Decimal

import pytest

from research.machine_time_source_feed import (
    CausalMinuteFeed, M1_MS, M5_MS, H1_MS, original_neckline_proofs,
)


def row(t: int, h: str = "101", l: str = "99", c: str = "100") -> dict:
    return {
        "time": t, "open": c, "high": h,
        "low": l, "close": c, "volume": "10",
    }


def test_m1_stream_releases_only_closed_m5_h1_at_utc_bucket_boundaries():
    feed = CausalMinuteFeed("BTCUSDT")
    snapshots = [feed.observe_closed_m1(row(i * M1_MS)) for i in range(61)]
    assert all(s.newly_closed_m5 is None for s in snapshots[:4])
    assert snapshots[4].newly_closed_m5 is not None
    assert snapshots[4].newly_closed_m5.start_ms == 0
    assert snapshots[4].newly_closed_m5.end_ms == M5_MS
    assert snapshots[4].newly_closed_m5.volume == Decimal("50")
    assert snapshots[59].newly_closed_h1 is not None
    assert snapshots[59].newly_closed_h1.end_ms == H1_MS
    assert all(s.newly_closed_h1 is None for s in snapshots[:59])
    assert len(snapshots[3].m1_history) == 4
    assert len(snapshots[3].m5_history) == 0
    assert len(snapshots[4].m5_history) == 1
    assert len(snapshots[4].h1_history) == 0
    assert len(snapshots[59].h1_history) == 1
    assert len(snapshots[60].m5_history) == 12
    assert len(snapshots[60].h1_history) == 1
    with pytest.raises(IndexError):
        _ = snapshots[3].m1_history[4]


def test_no_partial_h1_when_history_starts_mid_hour():
    feed = CausalMinuteFeed("BTCUSDT")
    steps = [feed.observe_closed_m1(row(3_000_000 + i * M1_MS)) for i in range(70)]
    assert all(s.newly_closed_h1 is None for s in steps[:69])
    assert steps[69].newly_closed_h1 is not None
    assert steps[69].newly_closed_h1.start_ms == H1_MS
    assert steps[69].newly_closed_h1.end_ms == 2 * H1_MS


def test_gap_duplicate_bad_ohlc_and_wrong_symbol_fail_closed():
    with pytest.raises(ValueError):
        CausalMinuteFeed("BTCUSDT/PAPER")
    feed = CausalMinuteFeed("BTCUSDT")
    old = feed.observe_closed_m1(row(0))
    for invalid in (
        row(0), row(2 * M1_MS),
        row(M1_MS, h="90", l="99"),
        row(M1_MS, h="NaN"),
    ):
        with pytest.raises(ValueError):
            feed.observe_closed_m1(invalid)
    assert len(old.m1_history) == 1
    next_step = feed.observe_closed_m1(row(M1_MS))
    assert len(next_step.m1_history) == 2


def _confirmed_double_top_bars():
    # Existing test_double_extremum fixture; no replay geometry is invented.
    return [
        ("100", "98", "99"),
        ("104", "99", "103"),
        ("110", "102", "108"),
        ("105", "100", "102"),
        ("103", "95", "98"),
        ("105", "99", "103"),
        ("109.8", "102", "107"),
        ("106", "98", "101"),
        ("96.5", "94", "94.5"),
    ]


def _run_original_proofs(bars):
    feed = CausalMinuteFeed("LABUSDT")
    observations = []
    for i, (h, l, c) in enumerate(bars):
        step = feed.observe_closed_m1(row(3_000_000 + i * M1_MS, h, l, c))
        observations.append(original_neckline_proofs(step, source_window=100))
    return observations


def test_actual_scanner_frozen_snapshot_is_verified_by_actual_robot_code():
    observations = _run_original_proofs(_confirmed_double_top_bars())
    assert all(not proof for proof in observations[:-1])
    assert len(observations[-1]) == 1
    item = observations[-1][0]
    assert item.pattern == "Double Top"
    assert item.timeframe == "1"
    assert item.confirmed_at_ms == 3_000_000 + 9 * M1_MS
    assert item.frozen_snapshot["robot_handoff_ready"] is True
    assert item.frozen_snapshot["neckline_entry"]["stop"] == "96.5"
    assert item.robot_proof.pattern == "Double Top"
    assert item.robot_proof.direction == "SHORT"
    assert _run_original_proofs(_confirmed_double_top_bars()) == observations


def test_a_wick_without_body_close_cannot_become_robot_proof():
    candles = _confirmed_double_top_bars()
    candles[-1] = ("96.5", "94", "95.5")
    assert all(not proof for proof in _run_original_proofs(candles))


def test_source_window_is_explicit_not_new_implicit_pattern_strategy():
    step = CausalMinuteFeed("BTCUSDT").observe_closed_m1(row(0))
    with pytest.raises(ValueError):
        original_neckline_proofs(step, source_window=8)
    with pytest.raises(ValueError):
        original_neckline_proofs(step, source_window=True)
