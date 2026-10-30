"""MIRROR observation charts must show source geometry without future candles."""

from types import SimpleNamespace

import pytest

from mirror_scanner import _frozen_event_chart, mirror_source_token


class Level:
    def __init__(self, level_id, origin, side="upper", decision=None):
        self.level_id = level_id
        self.provenance = {"parent_formation_id": origin, "decision_index": decision}
        self.side = side
        self.source = "PATTERN_BOUNDARY"
        self.pattern = "Rising Wedge"
        self.confirmed_at_ms = 600_000

    def to_dict(self):
        return {
            "level_id": self.level_id,
            "side": self.side,
            "boundary": {
                "anchor_time_ms": 0,
                "anchor_price": 1.0 if self.side == "upper" else 0.9,
                "slope_per_ms": 0,
            },
        }


def test_snapshot_contains_only_exact_source_boundaries():
    registry = SimpleNamespace(levels={
        "selected": Level("selected", "formation-1"),
        "other-side": Level("other-side", "formation-1", "lower"),
        "unrelated": Level("unrelated", "formation-2"),
    })
    rows = [
        {"open_time_ms": i * 300_000, "close_time_ms": (i + 1) * 300_000,
         "open": 0.95, "high": 1.02,
         "low": 0.88, "close": 0.97}
        for i in range(125)
    ]
    record = {
        "sources": [{"parent_formation_id": "formation-1"}],
        "naked_retest": {"breakout": {"open_time_ms": 124 * 300_000}},
    }
    snapshot = _frozen_event_chart("TESTUSDT", "5", rows, registry, "selected", record, "breakout")
    assert len(snapshot["candles"]) == 120
    assert snapshot["candles"][0]["open_time_ms"] == 5 * 300_000
    assert {level["level_id"] for level in snapshot["levels"]} == {"selected", "other-side"}
    assert sum(bool(level["selected"]) for level in snapshot["levels"]) == 1
    assert snapshot["event_open_time_ms"] == 124 * 300_000
    assert mirror_source_token("TESTUSDT", "5", "selected") != mirror_source_token(
        "TESTUSDT", "5", "unrelated")


def test_boundary_pair_without_formation_id_requires_same_engine_decision():
    registry = SimpleNamespace(levels={
        "selected": Level("selected", None, decision=12),
        "paired": Level("paired", None, side="lower", decision=12),
        "other-decision": Level("other-decision", None, decision=11),
    })
    rows = [{"open_time_ms": i * 300_000, "close_time_ms": (i + 1) * 300_000,
             "open": 0.95, "high": 1.02, "low": 0.88, "close": 0.97} for i in range(4)]
    snapshot = _frozen_event_chart(
        "TESTUSDT", "5", rows, registry, "selected",
        {"sources": [{"parent_formation_id": None}],
         "naked_retest": {"breakout": {"open_time_ms": 3 * 300_000}}},
        "breakout",
    )
    assert {item["level_id"] for item in snapshot["levels"]} == {"selected", "paired"}


def test_delayed_event_does_not_include_future_candles_or_levels():
    selected = Level("selected", "formation-1")
    late = Level("late", "formation-1", side="lower")
    late.confirmed_at_ms = 10 * 300_000
    registry = SimpleNamespace(levels={"selected": selected, "late": late})
    rows = [{"open_time_ms": i * 300_000, "close_time_ms": (i + 1) * 300_000,
             "open": 0.95, "high": 1.02, "low": 0.88, "close": 0.97}
            for i in range(20)]
    event_index = 3
    snapshot = _frozen_event_chart(
        "TESTUSDT", "5", rows, registry, "selected",
        {"sources": [{"parent_formation_id": "formation-1"}],
         "naked_retest": {"breakout": {"open_time_ms": event_index * 300_000}}},
        "breakout",
    )
    assert len(snapshot["candles"]) == 4
    assert snapshot["candles"][-1]["open_time_ms"] == event_index * 300_000
    assert [level["level_id"] for level in snapshot["levels"]] == ["selected"]


def test_frozen_chart_renders_without_market_data(tmp_path):
    pytest.importorskip("matplotlib")
    from mirror_event_chart import render_mirror_chart

    target = tmp_path / "mirror.png"
    render_mirror_chart({
        "symbol": "TESTUSDT",
        "timeframe": "5",
        "candles": [
            {"open_time_ms": i * 300_000, "close_time_ms": (i + 1) * 300_000,
         "open": 0.95, "high": 1.02,
             "low": 0.88, "close": 0.97}
            for i in range(8)
        ],
        "levels": [Level("ray", None).to_dict() | {"selected": True}],
        "event_open_time_ms": 6 * 300_000,
    }, target)
    assert target.read_bytes().startswith(b"\x89PNG\r\n\x1a\n")


def test_chart_refuses_missing_evidence(tmp_path):
    pytest.importorskip("matplotlib")
    from mirror_event_chart import render_mirror_chart
    with pytest.raises(ValueError, match="missing MIRROR event candles"):
        render_mirror_chart({"levels": [{"boundary": {}}]}, tmp_path / "bad.png")
