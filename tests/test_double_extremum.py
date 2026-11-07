from decimal import Decimal

from geometry.double_extremum import detect_confirmed_double_extremum
from tests.test_stop_reentry_reservation import prepared


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


def test_real_neckline_signal_proves_double_top_reentry_and_rejects_wick_only():
    import robot_l_shape
    from geometry.double_extremum import frozen_neckline_snapshot
    from terminal.application.robot_reentry_adapter import proven_pattern_entry
    bars = [
        bar(100, 98, 99), bar(104, 99, 103), bar(110, 102, 108),
        bar(105, 100, 102), bar(103, 95, 98), bar(105, 99, 103),
        bar(109.8, 102, 107), bar(106, 98, 101), bar(96.5, 94, 94.5),
    ]
    for i, candle in enumerate(bars):
        candle["time"] = 3_000_000 + i * 60_000
    frozen = frozen_neckline_snapshot("LABUSDT", "1", bars)
    assert frozen is not None
    assert frozen["pattern"] == "Double Top"
    assert frozen["neckline_entry"]["stop"] == "96.5"
    state, _ = robot_l_shape.initialize_state({
        "candidate_id": "double-top", "status": "APPROVED",
        "signal_snapshot": frozen,
    })
    assert state["phase"] == robot_l_shape.PHASE_RETEST_DETECTED
    confirmation = frozen["neckline_entry"]["confirmation"]["close_time_ms"]
    proof = proven_pattern_entry(frozen, now_ms=confirmation)
    assert proof is not None
    assert proof.pattern == "Double Top"
    assert proof.direction == "SHORT"
    assert proof.confirmed_at_ms == confirmation
    assert proven_pattern_entry(frozen, now_ms=confirmation - 1) is None
    # A wick penetrating the neck without the candle body's close is rejected.
    bad = [dict(c) for c in bars]
    bad[-1]["close"] = "95.5"
    assert frozen_neckline_snapshot("LABUSDT", "1", bad) is None


def test_double_bottom_new_closed_neckline_is_same_campaign_proposal_after_stop(prepared):
    from geometry.double_extremum import frozen_neckline_snapshot
    from terminal.application.robot_reentry_adapter import automatic_reentry_proposal
    from terminal.domain.models import TradingAccountId, Symbol

    store, _ = prepared
    candles = [
        bar(102, 98, 100), bar(101, 94, 96), bar(98, 90, 92),
        bar(101, 95, 99), bar(106, 99, 104), bar(102, 97, 99),
        bar(99, 90.2, 92), bar(104, 96, 100), bar(107, 105.5, 106.5),
    ]
    for i, row in enumerate(candles):
        row["time"] = 360_000 + i * 60_000
    new_snapshot = frozen_neckline_snapshot("LABUSDT", "1", candles)
    assert new_snapshot is not None
    with store.robot_admission_transaction():
        proposed = automatic_reentry_proposal(
            store, TradingAccountId("paper"), candidate_id="second",
            symbol=Symbol("LABUSDT"), snapshot=new_snapshot,
            now_ms=900_000,
        )
    assert proposed is not None
    assert proposed.previous_stop_exec_id == "stop-exec-1"
    assert proposed.confirmed_at_ms == 900_000
    assert proposed.strategy_confirmation_proven is True
    assert proposed.original_risk_budget_usdt is None


def test_neckline_retry_rejects_forged_and_stale_confirmation():
    from copy import deepcopy
    from geometry.double_extremum import frozen_neckline_snapshot
    from terminal.application.robot_reentry_adapter import proven_pattern_entry

    bars = [
        bar(102, 98, 100), bar(101, 94, 96), bar(98, 90, 92),
        bar(101, 95, 99), bar(106, 99, 104), bar(102, 97, 99),
        bar(99, 90.2, 92), bar(104, 96, 100), bar(107, 105.5, 106.5),
    ]
    for i, item in enumerate(bars):
        item["time"] = 360_000 + i * 60_000
    valid = frozen_neckline_snapshot("LABUSDT", "1", bars)
    assert valid is not None
    confirmed_at = valid["neckline_entry"]["confirmation"]["close_time_ms"]
    assert proven_pattern_entry(valid, now_ms=confirmed_at) is not None

    for tamper in ("future", "wrong_kind", "wrong_timeframe", "bad_close",
                   "bad_direction", "wrong_neckline", "no_handoff"):
        broken = deepcopy(valid)
        neckline = broken["neckline_entry"]
        confirmation = neckline["confirmation"]
        if tamper == "future":
            assert proven_pattern_entry(broken, now_ms=confirmed_at - 1) is None
            continue
        if tamper == "wrong_kind":
            confirmation["kind"] = "WICK_BREAK"
        elif tamper == "wrong_timeframe":
            confirmation["timeframe"] = "5"
        elif tamper == "bad_close":
            confirmation["close"] = "100"
        elif tamper == "bad_direction":
            neckline["direction"] = "SHORT"
        elif tamper == "wrong_neckline":
            neckline["neckline"] = "107"
        else:
            broken["robot_handoff_ready"] = False
        assert proven_pattern_entry(broken, now_ms=confirmed_at) is None, tamper
