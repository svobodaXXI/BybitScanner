"""Focused tests for the MIRROR-INTEGRATION-5 trial helpers (offline, no network)."""

import pytest

from geometry.naked_retest import Boundary
from mirror_retest_live_sources import KLINE_URL
from tools.research_mirror_integration_5 import FIVE, Recorder, owner_rule_breakout, signature

T = 1_700_000_100_000 - 1_700_000_100_000 % FIVE


def row(open_, close, *, high=None, low=None):
    high = high if high is not None else max(open_, close)
    low = low if low is not None else min(open_, close)
    return [str(T), str(open_), str(high), str(low), str(close), "1", "1"]


LEVEL = Boundary.horizontal("b:upper", 100.0, as_of_time_ms=T - FIVE)


@pytest.mark.parametrize("candle,expected", [
    (row(99, 101), True),                    # UP: opens below, closes above
    (row(101, 99), True),                    # DOWN mirror
    (row(100, 101), False),                  # opens on the level: equality does not qualify
    (row(99, 100), False),                   # closes on the level
    (row(99, 99.5, high=101), False),        # wick-only crossing
    (row(101, 102), False),                  # already opened beyond the level
    (row(99, 98, low=97), False),            # never reaches the level
])
def test_owner_rule_is_strict_and_symmetric(candle, expected):
    assert owner_rule_breakout(LEVEL, candle, T + FIVE) is expected


def test_owner_rule_uses_the_sloped_line_at_the_candle_own_times():
    sloped = Boundary("s:upper", T, 100.0, 1.0 / FIVE, T - FIVE)       # +1 per 5 minutes
    assert owner_rule_breakout(sloped, row(99.5, 101.5), T + FIVE) is True    # line 100 -> 101
    assert owner_rule_breakout(sloped, row(99.5, 100.9), T + FIVE) is False   # does not clear 101


class FakeSession:
    def __init__(self, payload):
        self.payload, self.calls = payload, []

    def get(self, url, params=None, timeout=None):
        self.calls.append((url, params))
        outer = self

        class Response:
            def raise_for_status(self):
                return None

            def json(self):
                return outer.payload

        return Response()


def test_recorder_allows_only_the_public_kline_endpoint():
    recorder = Recorder(FakeSession({}), pause_s=0)
    with pytest.raises(RuntimeError):
        recorder("https://api.bybit.com/v5/order/create", params={})
    with pytest.raises(RuntimeError):
        recorder("http://127.0.0.1:8765/api/robot/protection-health", params={})


def test_recorder_keeps_raw_rows_and_the_exchange_time_of_first_delivery():
    payload = {"retCode": 0, "time": T + 2 * FIVE, "result": {"list": [row(99, 101)]}}
    recorder = Recorder(FakeSession(payload), pause_s=0)
    recorder(KLINE_URL, params={"symbol": "X", "interval": "5"})
    payload["time"] = T + 9 * FIVE
    recorder(KLINE_URL, params={"symbol": "X", "interval": "5"})

    assert recorder.rows[("X", "5")][T][1] == "99"
    assert recorder.delivered[("X", "5", T)] == T + 2 * FIVE          # first delivery is kept
    assert recorder.exchange_ms == T + 9 * FIVE and recorder.urls == {KLINE_URL}


def test_recorder_fault_hook_simulates_an_outage_and_counts_nothing_as_data():
    def outage(number):
        raise ConnectionError("injected")

    recorder = Recorder(FakeSession({"time": 1, "result": {"list": [row(1, 2)]}}), pause_s=0, fault=outage)
    with pytest.raises(ConnectionError):
        recorder(KLINE_URL, params={"symbol": "X", "interval": "5"})
    assert recorder.rows == {} and recorder.calls == 1


def test_signature_compares_only_observations_up_to_the_ceiling():
    lines = [{"observation_id": "a", "event": "E", "decision": "WAIT", "candle_close_time_ms": 10},
             {"observation_id": "b", "event": "E", "decision": "WAIT", "candle_close_time_ms": 99}]
    assert signature(lines, 50) == [("a", "E", "WAIT")]
