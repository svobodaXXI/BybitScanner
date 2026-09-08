from pathlib import Path
from unittest.mock import patch

import main

from scanner_diary import record_scanner_diary_observation
from terminal.diary import DiaryDecisionStore


def _analysis(*, approved: bool, reason: str = "test", direction: str = "LONG"):
    return {
        "result": {
            "pattern": "Falling Wedge",
            "final_score": 75 if approved else 55,
            "quality": {"quality": "A Setup" if approved else "B Setup"},
            "confirmation": {
                "direction": direction,
                "confirmed": approved,
                "breakout": approved,
            },
            "signal": {
                "approved": approved,
                "reason": reason,
            },
        },
        "highs": [10, 20, 30],
        "lows": [15, 25, 35],
    }


def test_rejected_scanner_setup_is_recorded_once_as_skipped_denominator(tmp_path: Path):
    path = tmp_path / "diary.sqlite3"
    first = record_scanner_diary_observation(
        symbol="BTCUSDT",
        analysis_result=_analysis(approved=False, reason="score below minimum"),
        timeframe="5",
        scanner_mode="hunter",
        observed_at_ms=100,
        database_path=path,
    )
    repeated = record_scanner_diary_observation(
        symbol="BTCUSDT",
        analysis_result=_analysis(approved=False, reason="score below minimum"),
        timeframe="5",
        scanner_mode="hunter",
        observed_at_ms=200,
        database_path=path,
    )

    assert first.status == "RECORDED"
    assert repeated.status == "UNCHANGED"
    assert repeated.setup_instance_id == first.setup_instance_id
    assert repeated.decision_event_id == first.decision_event_id

    with DiaryDecisionStore.open(path) as store:
        events = store.load_setup_outcomes(first.setup_instance_id)
        assert len(events) == 1
        assert events[0].next_state == "SKIPPED"
        assert events[0].reason_code == "SCANNER_SCORE_BELOW_MINIMUM"
        assert events[0].feature_snapshot_ref.startswith("inline-json-sha256:")


def test_approved_scanner_setup_records_append_only_armed_strategy_decision(tmp_path: Path):
    path = tmp_path / "diary.sqlite3"
    result = record_scanner_diary_observation(
        symbol="ETHUSDT",
        analysis_result=_analysis(approved=True, reason="quality and score accepted"),
        timeframe="5",
        scanner_mode="hunter",
        observed_at_ms=123,
        database_path=path,
    )

    assert result.status == "RECORDED"
    with DiaryDecisionStore.open(path) as store:
        events = store.load_decision_events(result.setup_instance_id)
        assert len(events) == 1
        assert events[0].kind.value == "STRATEGY"
        assert events[0].next_state == "ARMED"
        assert events[0].feature_snapshot_ref.startswith("inline-json-sha256:")


def test_same_structure_with_changed_decision_snapshot_appends_new_event(tmp_path: Path):
    path = tmp_path / "diary.sqlite3"
    rejected = record_scanner_diary_observation(
        symbol="BTCUSDT",
        analysis_result=_analysis(approved=False, reason="score below minimum"),
        timeframe="5",
        scanner_mode="hunter",
        observed_at_ms=100,
        database_path=path,
    )
    approved = record_scanner_diary_observation(
        symbol="BTCUSDT",
        analysis_result=_analysis(approved=True, reason="quality and score accepted"),
        timeframe="5",
        scanner_mode="hunter",
        observed_at_ms=200,
        database_path=path,
    )

    assert rejected.setup_instance_id == approved.setup_instance_id
    assert rejected.decision_event_id != approved.decision_event_id
    with DiaryDecisionStore.open(path) as store:
        events = store.load_decision_events(rejected.setup_instance_id)
        assert [event.next_state for event in events] == ["SKIPPED", "ARMED"]


def test_unresolved_nondirectional_pattern_is_not_misclassified(tmp_path: Path):
    observation = _analysis(approved=False, direction="WAIT")
    observation["result"]["pattern"] = "Triangle Compression"
    path = tmp_path / "diary.sqlite3"

    result = record_scanner_diary_observation(
        symbol="BTCUSDT",
        analysis_result=observation,
        timeframe="5",
        scanner_mode="hunter",
        observed_at_ms=100,
        database_path=path,
    )

    assert result.status == "UNRESOLVED_DIRECTION"
    assert not path.exists()


def test_scanner_main_feeds_recognized_pattern_to_diary_without_owning_admission():
    analysis_result = _analysis(approved=False)
    with patch.object(main, "get_symbols", return_value=["BTCUSDT"]), \
            patch.object(main, "analyze_symbol", return_value=analysis_result), \
            patch.object(main, "record_scanner_diary_observation") as diary_mock, \
            patch.object(main, "send_signal", return_value=False), \
            patch.object(main, "send_message", return_value={"ok": True}), \
            patch.object(main.config, "TELEGRAM_TEST_MODE", False):
        main.main()

    diary_mock.assert_called_once()
    kwargs = diary_mock.call_args.kwargs
    assert kwargs["symbol"] == "BTCUSDT"
    assert kwargs["analysis_result"] is analysis_result
