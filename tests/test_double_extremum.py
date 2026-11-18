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


def test_confirmed_double_top_keeps_historical_state_but_never_proves_new_reentry():
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
    # Legacy frozen state remains readable for protected historical trades,
    # but cannot authorize another independent DT order/reentry.
    assert proven_pattern_entry(frozen, now_ms=confirmation) is None
    assert proven_pattern_entry(frozen, now_ms=confirmation - 1) is None
    import pytest
    with pytest.raises(robot_l_shape.RobotLShapeError, match="cannot submit standalone"):
        robot_l_shape.build_initial_retest_limit({
            "candidate_id": "double-top", "status": "APPROVED",
            "signal_snapshot": frozen,
        }, state, tick_size=Decimal("0.1"))
    # A wick penetrating the neck without the candle body's close is rejected.
    bad = [dict(c) for c in bars]
    bad[-1]["close"] = "95.5"
    assert frozen_neckline_snapshot("LABUSDT", "1", bad) is None


def test_double_bottom_confirmation_cannot_create_new_stop_reentry(prepared):
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
    assert proposed is None


def test_neckline_signal_is_not_independently_executable_even_when_fresh():
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
    assert proven_pattern_entry(valid, now_ms=confirmed_at) is None

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


def _confirmed_auxiliary_top():
    from geometry.double_extremum import build_auxiliary_reversal_evidence
    bars = [
        bar(100, 98, 99), bar(104, 99, 103), bar(110, 102, 108),
        bar(105, 100, 102), bar(103, 95, 98), bar(105, 99, 103),
        bar(109.8, 102, 107), bar(106, 98, 101), bar(103, 94, 94.5),
    ]
    for i, candle in enumerate(bars):
        candle["time"] = 3_000_000 + i * 60_000
    closed_at = bars[-1]["time"] + 60_000
    return bars, closed_at, build_auxiliary_reversal_evidence(
        "LABUSDT", "1", bars, now_ms=closed_at,
    )


def test_auxiliary_double_reversal_has_causal_exact_identity_and_expiry():
    from geometry.double_extremum import build_auxiliary_reversal_evidence
    bars, closed_at, evidence = _confirmed_auxiliary_top()
    assert evidence is not None
    assert evidence["version"] == 1
    assert evidence["kind"] == "DOUBLE_REVERSAL_AUXILIARY"
    assert evidence["pattern"] == "Double Top"
    assert evidence["direction"] == "SHORT"
    assert evidence["confirmed_at_ms"] == closed_at
    assert evidence["expires_at_ms"] == closed_at + 120_000
    assert evidence["source_id"].startswith("double-reversal:")
    assert "robot_handoff_ready" not in evidence
    assert "neckline_entry" not in evidence
    assert build_auxiliary_reversal_evidence("LABUSDT", "1", bars, now_ms=closed_at) == evidence
    assert build_auxiliary_reversal_evidence("LABUSDT", "1", bars, now_ms=closed_at - 1) is None
    assert build_auxiliary_reversal_evidence("LABUSDT", "1", bars, now_ms=closed_at + 120_000) is None
    late = [dict(v) for v in bars]
    late[-1]["time"] += 60_000  # missing candle: no causal source
    assert build_auxiliary_reversal_evidence("LABUSDT", "1", late, now_ms=closed_at + 60_000) is None
    modified = [dict(v) for v in bars]
    modified[0]["high"] = "100.1"
    another = build_auxiliary_reversal_evidence("LABUSDT", "1", modified, now_ms=closed_at)
    assert another is not None and another["source_id"] != evidence["source_id"]


def test_auxiliary_is_host_context_for_wedge_box_lshape_mirror_but_never_a_trade():
    from geometry.double_extremum import attach_auxiliary_reversal
    _, closed_at, reversal = _confirmed_auxiliary_top()
    assert reversal is not None
    hosts = [
        {"symbol": "LABUSDT", "pattern": "Rising Wedge", "timeframe": "1"},
        {"pattern": "IKIGAI_BOX", "identity": {
            "symbol": "LABUSDT", "timeframe": "1", "direction": "SHORT",
        }},
        {"symbol": "LABUSDT", "timeframe": "1", "pattern": "L-shape",
         "l_shape": {"direction": "SHORT"}},
        {"symbol": "LABUSDT", "timeframe": "1", "pattern": "MIRROR",
         "mirror_entry": {"direction": "SHORT"}},
    ]
    for host in hosts:
        attached = attach_auxiliary_reversal(host, reversal, now_ms=closed_at)
        assert attached is not host
        assert "auxiliary_reversal" not in host
        assert attached["auxiliary_reversal"] == reversal
        assert attached["pattern"] == host["pattern"]
        assert "robot_handoff_ready" not in attached
        assert "candidate_id" not in attached
    for host in [
        {"symbol": "LABUSDT", "pattern": "Falling Wedge", "timeframe": "1"},  # opposite
        {"symbol": "OTHERUSDT", "pattern": "Rising Wedge", "timeframe": "1"},
        {"symbol": "LABUSDT", "pattern": "Rising Wedge", "timeframe": "5"},
        {"symbol": "LABUSDT", "pattern": "Double Top", "timeframe": "1"},
    ]:
        assert "auxiliary_reversal" not in attach_auxiliary_reversal(
            host, reversal, now_ms=closed_at,
        )
    assert "auxiliary_reversal" not in attach_auxiliary_reversal(
        hosts[0], reversal, now_ms=closed_at + 120_000,
    )
    tampered = dict(reversal, source_id="double-reversal:" + "x" * 64)
    assert "auxiliary_reversal" not in attach_auxiliary_reversal(
        hosts[0], tampered, now_ms=closed_at,
    )


def test_legacy_double_snapshot_is_observational_not_robot_ready():
    from geometry.double_extremum import frozen_neckline_snapshot
    from pattern_robot_integration import is_robot_executable_signal
    bars, _, _ = _confirmed_auxiliary_top()
    # Keep the original legacy fee-aware RR threshold in this historical
    # frozen-terms fixture; the auxiliary detector itself has no RR gate.
    bars[-1]["high"] = "96.5"
    legacy = frozen_neckline_snapshot("LABUSDT", "1", bars)
    assert legacy is not None
    assert legacy["pattern"] == "Double Top"
    assert legacy["scanner_observational_only"] is True
    assert legacy["robot_handoff_ready"] is False
    assert is_robot_executable_signal(legacy, timeframe="1") is False


def test_legacy_approved_double_candidate_cannot_reach_monitor_order_submission():
    from types import SimpleNamespace
    from unittest.mock import patch
    from terminal.application.robot_breakout_monitor import RobotBreakoutMonitor
    from terminal.domain.models import Symbol

    monitor = object.__new__(RobotBreakoutMonitor)
    for pattern in ("Double Top", "Double Bottom"):
        candidate = SimpleNamespace(
            candidate_id="historical-approved",
            symbol=Symbol("LABUSDT"),
            status="APPROVED",
            signal_snapshot={"pattern": pattern, "robot_handoff_ready": True},
            robot_state={"phase": "RETEST_DETECTED", "execution": {}},
        )
        # No market candle, order adapter or runtime admission call may occur.
        with patch.object(
            RobotBreakoutMonitor, "_invalidate_pre_entry_candidate",
        ) as invalidate, patch.object(
            RobotBreakoutMonitor, "_paper_candidate_is_inert", return_value=True,
        ) as inert:
            assert monitor._advance_l_shape_retest_detected(candidate) is True
        inert.assert_called_once_with(candidate)
        invalidate.assert_called_once_with(
            candidate, reason="Double Top/Bottom is auxiliary-only",
        )


def test_legacy_double_without_order_preserves_ambiguous_exposure():
    from types import SimpleNamespace
    from unittest.mock import patch
    from terminal.application.robot_breakout_monitor import RobotBreakoutMonitor
    from terminal.domain.models import Symbol

    monitor = object.__new__(RobotBreakoutMonitor)
    for pattern in ("Double Top", "Double Bottom"):
        candidate = SimpleNamespace(
            candidate_id="legacy", symbol=Symbol("LABUSDT"), status="APPROVED",
            signal_snapshot={"pattern": pattern},
            robot_state={"phase": "RETEST_DETECTED", "execution": {}},
        )
        with patch.object(
            RobotBreakoutMonitor, "_paper_candidate_is_inert", return_value=False,
        ), patch.object(
            RobotBreakoutMonitor, "_invalidate_pre_entry_candidate",
        ) as invalidated:
            assert monitor._advance_l_shape_retest_detected(candidate) is False
        invalidated.assert_not_called()


def test_legacy_double_standing_limit_cancel_before_match():
    from types import SimpleNamespace
    from unittest.mock import Mock, patch
    from terminal.application.robot_breakout_monitor import RobotBreakoutMonitor
    from terminal.api.models import CommandResultStatus
    from terminal.domain.models import TradingAccountId, Symbol

    def order(status, qty):
        return SimpleNamespace(
            status=status, quantity=Decimal("1"), filled_quantity=Decimal(qty),
        )

    for pattern in ("Double Top", "Double Bottom"):
        candidate = SimpleNamespace(
            candidate_id="legacy", symbol=Symbol("LABUSDT"), status="APPROVED",
            signal_snapshot={"pattern": pattern},
            robot_state={
                "phase": "RETEST_DETECTED",
                "execution": {"limit_order_id": "legacy-limit"},
            },
        )
        monitor = object.__new__(RobotBreakoutMonitor)
        monitor._account_id = TradingAccountId("paper")
        monitor._match_resting_orders = Mock()
        cancelled = Mock(return_value=SimpleNamespace(status=CommandResultStatus.COMPLETED))
        monitor._action_executor = SimpleNamespace(cancel_limit=cancelled)
        store = Mock()
        store.get_paper_limit.side_effect = [
            order("open", "0"), order("cancelled", "0"),
        ]
        with patch.object(
            RobotBreakoutMonitor, "_store", return_value=store,
        ), patch.object(
            RobotBreakoutMonitor, "_cancelled_legacy_double_is_inert", return_value=True,
        ) as proof, patch.object(
            RobotBreakoutMonitor, "_invalidate_pre_entry_candidate",
        ) as invalidate, patch.object(
            RobotBreakoutMonitor, "_confirm_entry_admission",
        ) as confirm:
            assert monitor._advance_l_shape_retest_detected(candidate) is True
        proof.assert_called_once_with(candidate, "legacy-limit")
        cancelled.assert_called_once()
        assert cancelled.call_args.args[0].order_id == "legacy-limit"
        invalidate.assert_called_once_with(
            candidate, reason="Double Top/Bottom legacy LIMIT cancelled without fill",
        )
        confirm.assert_not_called()
        monitor._match_resting_orders.assert_not_called()


def test_cancelled_double_without_proven_flat_does_not_invalidate_or_match():
    from types import SimpleNamespace
    from unittest.mock import Mock, patch
    from terminal.application.robot_breakout_monitor import RobotBreakoutMonitor
    from terminal.api.models import CommandResultStatus
    from terminal.domain.models import TradingAccountId, Symbol

    for pattern in ("Double Top", "Double Bottom"):
        candidate = SimpleNamespace(
            candidate_id="legacy", symbol=Symbol("LABUSDT"), status="APPROVED",
            signal_snapshot={"pattern": pattern},
            robot_state={
                "phase": "RETEST_DETECTED",
                "execution": {"limit_order_id": "legacy-limit"},
            },
        )
        monitor = object.__new__(RobotBreakoutMonitor)
        monitor._account_id = TradingAccountId("paper")
        monitor._match_resting_orders = Mock()
        cancel = Mock(return_value=SimpleNamespace(status=CommandResultStatus.COMPLETED))
        monitor._action_executor = SimpleNamespace(cancel_limit=cancel)
        store = Mock()
        store.get_paper_limit.side_effect = [
            SimpleNamespace(status="open", quantity=Decimal("1"),
                            filled_quantity=Decimal("0")),
            SimpleNamespace(status="cancelled", quantity=Decimal("1"),
                            filled_quantity=Decimal("0")),
        ]
        with patch.object(
            RobotBreakoutMonitor, "_store", return_value=store,
        ), patch.object(
            RobotBreakoutMonitor, "_cancelled_legacy_double_is_inert", return_value=False,
        ) as proof, patch.object(
            RobotBreakoutMonitor, "_invalidate_pre_entry_candidate",
        ) as invalidated, patch.object(
            RobotBreakoutMonitor, "_confirm_entry_admission",
        ) as confirm:
            assert monitor._advance_l_shape_retest_detected(candidate) is False
        cancel.assert_called_once()
        proof.assert_called_once_with(candidate, "legacy-limit")
        confirm.assert_not_called()
        invalidated.assert_not_called()
        monitor._match_resting_orders.assert_not_called()


def test_cancelled_double_proof_requires_no_order_fills_trade_or_residual_exposure():
    from types import SimpleNamespace
    from unittest.mock import Mock, patch
    from terminal.application.robot_breakout_monitor import RobotBreakoutMonitor
    from terminal.application.robot_recovery import RobotRecoveryCoordinator
    from terminal.domain.models import TradingAccountId, Symbol

    monitor = object.__new__(RobotBreakoutMonitor)
    monitor._account_id = TradingAccountId("paper")
    monitor._clock_ms = lambda: 1111
    candidate = SimpleNamespace(
        candidate_id="legacy", symbol=Symbol("LABUSDT"), status="APPROVED",
        signal_snapshot={"pattern": "Double Top"},
    )
    store = Mock()
    store.get_robot_trade.return_value = None
    store.load_executions_for_order.return_value = ()
    with patch.object(
        RobotBreakoutMonitor, "_store", return_value=store,
    ), patch.object(
        RobotRecoveryCoordinator, "_candidate_is_inert", return_value=True,
    ) as canonical:
        assert monitor._cancelled_legacy_double_is_inert(candidate, "legacy-limit") is True
    store.get_robot_trade.assert_called_once_with("robot-trade-legacy")
    account, order_id = store.load_executions_for_order.call_args.args
    assert account == monitor._account_id and order_id.value == "legacy-limit"
    canonical.assert_called_once_with(candidate)

    # A fill recorded in the immutable execution ledger overrides a cancelled
    # order row that still (incorrectly) says filled_quantity == 0.
    store.load_executions_for_order.return_value = (object(),)
    with patch.object(
        RobotBreakoutMonitor, "_store", return_value=store,
    ), patch.object(
        RobotRecoveryCoordinator, "_candidate_is_inert",
        side_effect=AssertionError("must not inspect inertness after proven fill"),
    ):
        assert monitor._cancelled_legacy_double_is_inert(candidate, "legacy-limit") is False

    store.load_executions_for_order.return_value = ()
    store.get_robot_trade.return_value = object()
    with patch.object(RobotBreakoutMonitor, "_store", return_value=store):
        assert monitor._cancelled_legacy_double_is_inert(candidate, "legacy-limit") is False

    store.get_robot_trade.return_value = None
    with patch.object(
        RobotBreakoutMonitor, "_store", return_value=store,
    ), patch.object(
        RobotRecoveryCoordinator, "_candidate_is_inert", return_value=False,
    ):
        assert monitor._cancelled_legacy_double_is_inert(candidate, "legacy-limit") is False


def test_legacy_double_cancel_unknown_never_advances_or_invalidates():
    from types import SimpleNamespace
    from unittest.mock import Mock, patch
    from terminal.application.robot_breakout_monitor import RobotBreakoutMonitor
    from terminal.domain.models import TradingAccountId, Symbol

    monitor = object.__new__(RobotBreakoutMonitor)
    monitor._account_id = TradingAccountId("paper")
    monitor._match_resting_orders = Mock()
    monitor._action_executor = SimpleNamespace(
        cancel_limit=Mock(return_value=SimpleNamespace(status="UNPROVEN")),
    )
    store = Mock()
    store.get_paper_limit.return_value = SimpleNamespace(
        status="open", quantity=Decimal("1"), filled_quantity=Decimal("0"),
    )
    candidate = SimpleNamespace(
        candidate_id="legacy", symbol=Symbol("LABUSDT"), status="APPROVED",
        signal_snapshot={"pattern": "Double Bottom"},
        robot_state={"phase": "RETEST_DETECTED", "execution": {"limit_order_id": "legacy-limit"}},
    )
    with patch.object(
        RobotBreakoutMonitor, "_store", return_value=store,
    ), patch.object(
        RobotBreakoutMonitor, "_invalidate_pre_entry_candidate",
    ) as invalidated:
        assert monitor._advance_l_shape_retest_detected(candidate) is False
    invalidated.assert_not_called()
    monitor._match_resting_orders.assert_not_called()


def test_legacy_double_cancel_race_preserves_actual_partial_fill():
    from types import SimpleNamespace
    from unittest.mock import Mock, patch
    from terminal.application.robot_breakout_monitor import RobotBreakoutMonitor
    from terminal.api.models import CommandResultStatus
    from terminal.domain.models import TradingAccountId, Symbol

    monitor = object.__new__(RobotBreakoutMonitor)
    monitor._account_id = TradingAccountId("paper")
    monitor._match_resting_orders = Mock()
    monitor._action_executor = SimpleNamespace(
        cancel_limit=Mock(return_value=SimpleNamespace(status=CommandResultStatus.COMPLETED)),
    )
    candidate = SimpleNamespace(
        candidate_id="legacy", symbol=Symbol("LABUSDT"), status="APPROVED",
        signal_snapshot={"pattern": "Double Top"},
        robot_state={"phase": "RETEST_DETECTED", "execution": {"limit_order_id": "legacy-limit"}},
    )
    store = Mock()
    store.get_paper_limit.side_effect = [
        SimpleNamespace(status="open", quantity=Decimal("1"), filled_quantity=Decimal("0")),
        SimpleNamespace(status="cancelled", quantity=Decimal("1"), filled_quantity=Decimal("0.25")),
    ]
    store.get_robot_candidate.return_value = None
    with patch.object(
        RobotBreakoutMonitor, "_store", return_value=store,
    ), patch.object(
        RobotBreakoutMonitor, "_invalidate_pre_entry_candidate",
    ) as invalidated, patch.object(
        RobotBreakoutMonitor, "_finalize_trade",
    ) as finalize:
        assert monitor._advance_l_shape_retest_detected(candidate) is True
    invalidated.assert_not_called()
    finalize.assert_called_once_with(
        candidate, {"limit_order_id": "legacy-limit"},
        entry_path="LIMIT", actual_wv=Decimal("0.25"),
    )
    monitor._match_resting_orders.assert_not_called()


def test_auxiliary_double_bottom_long_confirms_all_supported_hosts():
    from geometry.double_extremum import (
        attach_auxiliary_reversal, build_auxiliary_reversal_evidence,
    )
    candles = [
        bar(102, 98, 100), bar(101, 94, 96), bar(98, 90, 92),
        bar(101, 95, 99), bar(106, 99, 104), bar(102, 97, 99),
        bar(99, 90.2, 92), bar(104, 96, 100), bar(107, 98, 106.5),
    ]
    for i, candle in enumerate(candles):
        candle["time"] = 3_000_000 + i * 60_000
    closed_at = candles[-1]["time"] + 60_000
    reversal = build_auxiliary_reversal_evidence(
        "LABUSDT", "1", candles, now_ms=closed_at,
    )
    assert reversal is not None
    assert reversal["pattern"] == "Double Bottom"
    assert reversal["direction"] == "LONG"
    assert "robot_handoff_ready" not in reversal
    assert "candidate_id" not in reversal

    hosts = [
        {"pattern": "Falling Wedge", "symbol": "LABUSDT", "timeframe": "1"},
        {"pattern": "IKIGAI_BOX", "identity": {
            "symbol": "LABUSDT", "timeframe": "1", "direction": "LONG",
        }},
        {"pattern": "L-shape", "symbol": "LABUSDT", "timeframe": "1",
         "l_shape": {"direction": "LONG"}},
        {"pattern": "MIRROR", "symbol": "LABUSDT", "timeframe": "1",
         "mirror_entry": {"direction": "LONG"}},
    ]
    for host in hosts:
        linked = attach_auxiliary_reversal(host, reversal, now_ms=closed_at)
        assert linked["pattern"] == host["pattern"]
        assert linked["auxiliary_reversal"] == reversal
        assert "auxiliary_reversal" not in host
        assert "candidate_id" not in linked

    wrong = {"pattern": "Rising Wedge", "symbol": "LABUSDT", "timeframe": "1"}
    assert "auxiliary_reversal" not in attach_auxiliary_reversal(
        wrong, reversal, now_ms=closed_at,
    )
    assert "auxiliary_reversal" not in attach_auxiliary_reversal(
        hosts[0], reversal, now_ms=closed_at + 120_000,
    )
