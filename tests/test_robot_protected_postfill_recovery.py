"""Exact orphan-Market recovery exercises only scratch PAPER state.

The canonical owner must prove the original command, fill and full-position
protection; no test directly repairs production DB or dispatches a close.
"""
from decimal import Decimal
from pathlib import Path
import tempfile
import time

import robot_protection
from terminal.application.robot_breakout_monitor import RobotBreakoutMonitor
from terminal.application.robot_admission_catchup import LATE_ADMISSION_MARKET
from terminal.application.robot_late_admission_market import (
    build_late_admission_market_plan,
    durable_late_admission_market_intent,
)
from terminal.api.models import CommandResultStatus, ClientActionId, MarketCommandRequest, VolumeRequest, VolumeUnit
from terminal.domain.models import Category, OrderSide, PositionKey, Symbol, TradingAccountId
from terminal.runtime.paper_runtime import _DirectRobotActionExecutor
from tests.test_robot_breakout_monitor import _snapshot
from tests.test_terminal_paper_runtime import _runtime, _set_admission, StaticBookProvider


ACCOUNT = TradingAccountId("paper")
SYMBOL = Symbol("BTCUSDT")
CID = "legacy-protected-low-rr"


def _orphan_fixture(path: Path, *, take_enabled=True):
    runtime = _runtime(path)
    store = runtime.store
    approved = int(time.time() * 1000) - 10_000
    snapshot = _snapshot(
        symbol=SYMBOL.value, pattern="Falling Wedge",
        lower_touch_prices=(64100.0, 64120.0),
        reference_price=64200.0, start_width=250.0,
    )
    candidate, _ = store.create_robot_candidate(
        candidate_id=CID, trading_account_id=ACCOUNT, symbol=SYMBOL,
        status="APPROVED", signal_snapshot=snapshot,
        approved_at_ms=approved, updated_at_ms=approved,
    )
    state = {
        "phase": "RETEST_DETECTED",
        "direction": "LONG",
        "execution": {"entry_mode": LATE_ADMISSION_MARKET},
    }
    book = StaticBookProvider().get_book(SYMBOL)
    payload = {
        "candidate_id": CID, "status": "APPROVED",
        "timeframe": "1", "signal_snapshot": snapshot,
    }
    plan = build_late_admission_market_plan(payload, state, book)
    preflight = runtime.api.market_preflight(plan.request, identity=plan.identity)
    assert preflight.admitted and preflight.normalized_quantity is not None
    tick = runtime._instrument_provider(SYMBOL.value).tick_size
    stop = robot_protection.build_protection_plan(
        payload, state, average_entry=book.asks[0].price.value,
        structural_extreme=Decimal("64100"), tick_size=tick,
        frozen_signal_reference_price=Decimal("64200"),
        frozen_scanner_target_price=Decimal("64450"),
    )
    intent = durable_late_admission_market_intent(
        plan, normalized_quantity=preflight.normalized_quantity,
        current_geometry_index=100,
        projected_vwap=book.asks[0].price.value,
        stop_price=stop.stop_price, take_price=stop.take_price,
        expected_reward=Decimal("1"), rr=Decimal("2.1"),
        adverse_slippage=Decimal("0.01"), persisted_at_ms=approved + 1,
    )
    state["execution"]["late_market_intent"] = intent
    store.save_robot_candidate_state(
        CID, status="APPROVED", robot_state=state,
        expected_revision=candidate.state_revision, updated_at_ms=approved + 1,
    )
    submitted = runtime.api.market(plan.request, identity=plan.identity)
    assert submitted.status is CommandResultStatus.COMPLETED
    position = store.get_position_projection(PositionKey(ACCOUNT, Category.LINEAR, SYMBOL, 0))
    assert position is not None and position.average_entry is not None
    expected = robot_protection.build_protection_plan(
        payload, state, average_entry=position.average_entry.value,
        structural_extreme=Decimal("64100"), tick_size=tick,
        frozen_signal_reference_price=Decimal("64200"),
        frozen_scanner_target_price=Decimal("64450"),
    )
    executor = _DirectRobotActionExecutor(runtime)
    assert executor.create_stop(expected.stop_request).status is CommandResultStatus.COMPLETED
    if take_enabled:
        assert executor.create_take(expected.take_request).status is CommandResultStatus.COMPLETED
    order = store.get_command(plan.identity.command_id)
    assert order is not None and order.exchange_order_id is not None
    fills = store.load_executions_for_order(ACCOUNT, order.exchange_order_id)
    assert len(fills) == 1
    rr = robot_protection.post_fill_net_rr(
        "LONG", average_entry=position.average_entry.value,
        quantity=position.quantity.value, entry_fee=fills[0].fee,
        stop_price=expected.stop_price, take_price=expected.take_price,
    )
    assert Decimal("0") < rr < Decimal("2")
    old = store.get_robot_candidate(CID)
    oldstate = dict(old.robot_state)
    execution = dict(oldstate["execution"])
    execution["protection_failure"] = f"POST_FILL_NET_RR_BELOW_2 rr={rr}"
    execution["emergency_close_pending"] = True
    attempted = max(int(time.time() * 1000), order.updated_at_ms + 1)
    execution["emergency_close_attempted_at_ms"] = attempted
    oldstate["execution"] = execution
    store.save_robot_candidate_state(
        CID, status="APPROVED", robot_state=oldstate,
        expected_revision=old.state_revision, updated_at_ms=attempted,
    )
    _set_admission(runtime, mode="ROBOT_RUNNING", recovery_status="RECONCILIATION_REQUIRED")
    return runtime


def test_exact_protected_legacy_entry_reconciles_to_paused_without_market_retry():
    with tempfile.TemporaryDirectory() as temp:
        runtime = _orphan_fixture(Path(temp) / "paper.sqlite3")
        try:
            store = runtime.store
            before = store.load_executions_for_symbol(ACCOUNT, SYMBOL)
            before_commands = store.load_commands_for_symbol_since(ACCOUNT, SYMBOL, 0)
            assert len(before) == len(before_commands) == 1
            result = runtime.robot_reconcile()
            assert result.success is True
            assert result.recovery_status == "PAUSED"
            assert runtime.robot_admission_ready() is False
            candidate = store.get_robot_candidate(CID)
            assert candidate.status == "OPEN"
            execution = candidate.robot_state["execution"]
            assert "emergency_close_pending" not in execution
            assert execution["post_fill_policy_exception"]["reason"] == "POST_FILL_NET_RR_BELOW_2"
            assert execution["protected_postfill_recovery"]["entry_command_id"] == before_commands[0].command_id.value
            trade = store.get_robot_trade("robot-trade-" + CID)
            assert trade is not None and trade.exit_time_ms is None
            assert trade.entry_quantity == store.get_position_projection(
                PositionKey(ACCOUNT, Category.LINEAR, SYMBOL, 0),
            ).quantity.value
            assert store.robot_account_quarantines(ACCOUNT) == {}
            assert store.load_executions_for_symbol(ACCOUNT, SYMBOL) == before
            assert store.load_commands_for_symbol_since(ACCOUNT, SYMBOL, 0) == before_commands
        finally:
            runtime.close()


def test_unconfirmed_take_retains_required_and_no_trade():
    with tempfile.TemporaryDirectory() as temp:
        runtime = _orphan_fixture(Path(temp) / "paper.sqlite3", take_enabled=False)
        try:
            before = runtime.store.load_executions_for_symbol(ACCOUNT, SYMBOL)
            result = runtime.robot_reconcile()
            assert result.success is False
            assert result.recovery_status == "RECONCILIATION_REQUIRED"
            assert runtime.store.get_robot_trade("robot-trade-" + CID) is None
            assert runtime.store.get_robot_candidate(CID).robot_state["execution"]["emergency_close_pending"] is True
            assert runtime.store.load_executions_for_symbol(ACCOUNT, SYMBOL) == before
        finally:
            runtime.close()


def test_extra_market_command_retains_required_without_replay():
    with tempfile.TemporaryDirectory() as temp:
        runtime = _orphan_fixture(Path(temp) / "paper.sqlite3")
        try:
            extra = runtime.api.market(MarketCommandRequest(
                ClientActionId("foreign-after-entry"), SYMBOL.value, OrderSide.BUY,
                VolumeRequest(VolumeUnit.WORKING_VOLUME, Decimal("1")), Decimal("64250.5"),
                "Percent", Decimal("0.5"),
            ))
            assert extra.status is CommandResultStatus.COMPLETED
            before = runtime.store.load_executions_for_symbol(ACCOUNT, SYMBOL)
            result = runtime.robot_reconcile()
            assert result.success is False
            assert runtime.store.get_robot_trade("robot-trade-" + CID) is None
            assert runtime.store.get_robot_candidate(CID).status == "APPROVED"
            assert runtime.store.load_executions_for_symbol(ACCOUNT, SYMBOL) == before
        finally:
            runtime.close()


def test_cas_failure_rolls_back_trade_and_pending_marker():
    with tempfile.TemporaryDirectory() as temp:
        runtime = _orphan_fixture(Path(temp) / "paper.sqlite3")
        try:
            store = runtime.store
            record = store.get_robot_candidate(CID)
            state = dict(record.robot_state)
            execution = dict(state["execution"])
            execution.pop("emergency_close_pending")
            execution["protected_postfill_recovery"] = {"proof": "test"}
            state["execution"] = execution
            pos = store.get_position_projection(PositionKey(ACCOUNT, Category.LINEAR, SYMBOL, 0))
            from terminal.persistence.sqlite_store import ConcurrentUpdate
            import pytest
            with pytest.raises(ConcurrentUpdate):
                store.create_robot_trade(
                    trade_id="robot-trade-" + CID, trading_account_id=ACCOUNT,
                    candidate_id=CID, symbol=SYMBOL, direction="LONG",
                    pattern="Falling Wedge", source_timeframe="1",
                    signal_time_ms=record.approved_at_ms,
                    entry_time_ms=record.approved_at_ms + 1,
                    entry_path="MARKET", actual_wv=Decimal("1"),
                    average_entry=pos.average_entry.value,
                    stop_price=Decimal("64099.5"), take_price=Decimal("64272"),
                    entry_quantity=pos.quantity.value, entry_position_version=pos.version,
                    created_at_ms=max(int(time.time()*1000), record.updated_at_ms),
                    recovery_state=state,
                    recovery_expected_revision=record.state_revision - 1,
                )
            assert store.get_robot_trade("robot-trade-" + CID) is None
            assert store.get_robot_candidate(CID).robot_state["execution"]["emergency_close_pending"] is True
        finally:
            runtime.close()
