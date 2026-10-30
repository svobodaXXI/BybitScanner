"""Telegram failure should not erase a normal Scanner signal before its chart arrives."""

from unittest.mock import patch

import signal_memory


def _signal():
    return {"symbol": "TESTUSDT", "timeframe": "5", "pattern": "Falling Wedge",
            "formation_id": "formation-123", "score": 95, "direction": "SHORT"}


def test_failed_delivery_retries_same_signal_after_cooldown(tmp_path, monkeypatch):
    monkeypatch.setattr(signal_memory, "MEMORY_FILE", str(tmp_path / "signal-memory.json"))
    signal = _signal()
    with patch.object(signal_memory.time, "time", return_value=1000):
        assert signal_memory.update_signal(signal) == "NEW"
        signal_memory.record_telegram_delivery(signal, False)
        assert signal_memory.update_signal(signal) == "STABLE"
    with patch.object(signal_memory.time, "time", return_value=1299):
        assert signal_memory.update_signal(signal) == "STABLE"
    with patch.object(signal_memory.time, "time", return_value=1300):
        assert signal_memory.update_signal(signal) == "NEW"
        signal_memory.record_telegram_delivery(signal, True)
        assert signal_memory.update_signal(signal) == "STABLE"


def test_preexisting_stable_signals_are_not_replayed(tmp_path, monkeypatch):
    monkeypatch.setattr(signal_memory, "MEMORY_FILE", str(tmp_path / "signal-memory.json"))
    assert signal_memory.update_signal(_signal()) == "NEW"
    assert signal_memory.update_signal(_signal()) == "STABLE"


def test_retry_identity_is_exact_timeframe_and_formation(tmp_path, monkeypatch):
    monkeypatch.setattr(signal_memory, "MEMORY_FILE", str(tmp_path / "signal-memory.json"))
    signal = _signal()
    other = {**signal, "formation_id": "formation-other"}
    assert signal_memory.update_signal(signal) == "NEW"
    signal_memory.record_telegram_delivery(signal, False)
    assert signal_memory.update_signal(other) == "NEW"
    assert signal_memory.update_signal(other) == "STABLE"
