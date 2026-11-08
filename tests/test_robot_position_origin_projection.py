from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import patch

from terminal.runtime.paper_http_server import _robot_position_markers


def test_selected_robot_position_exposes_exact_trade_origin_with_markers():
    trade = SimpleNamespace(trade_id="robot-btc", candidate_id="candidate-btc")
    runtime = SimpleNamespace(store=SimpleNamespace(
        get_open_robot_trade_for_symbol=lambda account, symbol: trade
    ))
    view = SimpleNamespace(
        is_open=True, is_robot=True, trade=trade, quantity=Decimal("1"),
        markers=(), pattern="Falling Wedge",
        signal_snapshot={"scanner_source_timeframe": "1"}, chart_candle_minutes=1,
        mirror_campaign=True, mirror_level_source="pattern_boundary",
        mirror_pattern="Falling Wedge", reentry_attempt_index=2,
    )
    with patch("robot_position_view.load_position_view", return_value=view) as read:
        result = _robot_position_markers(runtime, "BTCUSDT", "robot-btc", 1000)
    assert result["ok"] is True
    assert result["origin"] == {
        "pattern": "Falling Wedge",
        "candidate_id": "candidate-btc",
        "signal_timeframe_minutes": 1,
        "mirror_campaign": True,
        "mirror_level_source": "pattern_boundary",
        "mirror_pattern": "Falling Wedge",
        "reentry_attempt_index": 2,
    }
    assert result["markers"] == []
    read.assert_called_once()
    with patch("robot_position_view.load_position_view") as read_wrong:
        invalid = _robot_position_markers(runtime, "BTCUSDT", "another-trade", 1000)
    assert invalid == {"ok": False, "error": "unproven_robot_position"}
    read_wrong.assert_not_called()
