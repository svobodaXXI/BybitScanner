"""End-to-end acceptance for legacy protection recovery Slice B.

The test uses the real SerializedPaperRuntime, real PaperMarketExecutor,
existing Robot reconciliation coordinator, existing protection-obligation
stable identities, and existing Robot trade finalizer.  Only deterministic
market input is synthetic.
"""

from __future__ import annotations

import tempfile
import time
import unittest
from decimal import Decimal
from pathlib import Path

from terminal.application.trading_accounts import paper_account_manager
from terminal.domain.models import (
    Category,
    Execution,
    ExecutionDedupKey,
    ExecutionId,
    Notional,
    OrderId,
    OrderSide,
    PositionKey,
    PositionSide,
    Price,
    Quantity,
    Symbol,
    TradingAccountId,
)
from terminal.exchange.events import InstrumentSnapshot
from terminal.market_data.models import BookHealth, NormalizedOrderBook, PriceLevel
from terminal.persistence.legacy_protection_recovery import attest_legacy_robot_entry
from terminal.persistence.sqlite_store import PositionProjectionUpdate
from terminal.runtime.paper_http_server import SerializedPaperRuntime, create_configured_paper_runtime


ACCOUNT = TradingAccountId("paper")
SYMBOL_TEXT = "LEGACYUSDT"
SYMBOL = Symbol(SYMBOL_TEXT)
POSITION_KEY = PositionKey(ACCOUNT, Category.LINEAR, SYMBOL, 0)
CANDIDATE_ID = "legacy-reconcile-candidate"
TRADE_ID = "legacy-reconcile-trade"
ENTRY_ORDER_ID = "legacy-reconcile-entry-order"
ACTION_ID = "legacy-reconcile-attest-action"


def _instrument() -> InstrumentSnapshot:
    return InstrumentSnapshot(
        Category.LINEAR,
        SYMBOL_TEXT,
        "LinearPerpetual",
        "Trading",
        "LEGACY",
        "USDT",
        "USDT",
        Decimal("0.1"),
        Decimal("1000000"),
        Decimal("0.1"),
        Decimal("0.001"),
        Decimal("100"),
        Decimal("50"),
        Decimal("0.001"),
        Decimal("5"),
    )


class _FreshBookProvider:
    def get_book(self, symbol: Symbol) -> NormalizedOrderBook | None:
        if symbol != SYMBOL:
            return None
        now_ms = int(time.time() * 1000)
        return NormalizedOrderBook(
            symbol=SYMBOL,
            bids=(PriceLevel(Price(Decimal("97")), Quantity(Decimal("1000"))),),
            asks=(PriceLevel(Price(Decimal("97.1")), Quantity(Decimal("1000"))),),
            health=BookHealth.READY,
            received_at_ms=now_ms,
            available_depth=1,
            source_generation=1,
            source_sequence=1,
            source_update_id=1,
            source_event_at_ms=now_ms,
            source_matching_engine_cts_ms=None,
        )

    def get_current_book_update(self, symbol: Symbol):
        return None


def _runtime_factory(database_path: Path):
    instrument = _instrument()
    return create_configured_paper_runtime(
        database_path,
        book_provider=_FreshBookProvider(),
        instrument_snapshot=instrument,
        instrument_provider=lambda symbol: InstrumentSnapshot(
            instrument.category,
            symbol,
            instrument.contract_type,
            instrument.status,
            instrument.base_coin,
            instrument.quote_coin,
            instrument.settle_coin,
            instrument.min_price,
            instrument.max_price,
            instrument.tick_size,
            instrument.min_order_quantity,
            instrument.max_order_quantity,
            instrument.max_market_order_quantity,
            instrument.quantity_step,
            instrument.min_notional_value,
        ),
        account_manager=paper_account_manager(),
        robot_tick_interval_s=60.0,
    )


def _set_reconciliation_required(owner, *, reason: str):
    state = owner.store.get_robot_runtime_state(ACCOUNT)
    if state is None:
        state = owner.store.initialize_robot_runtime_state(
            ACCOUNT, updated_at_ms=int(time.time() * 1000),
        )
    now_ms = max(int(time.time() * 1000), state.updated_at_ms)
    if state.mode == "ROBOT_STOPPED":
        state = owner.store.update_robot_runtime_state(
            ACCOUNT,
            mode="ROBOT_RUNNING",
            recovery_status="READY",
            reason=None,
            expected_version=state.version,
            updated_at_ms=now_ms,
        )
        now_ms = max(int(time.time() * 1000), state.updated_at_ms)
    if state.recovery_status == "PAUSED":
        return owner.store.update_robot_runtime_state(
            ACCOUNT,
            mode="ROBOT_RUNNING",
            recovery_status="RECONCILIATION_REQUIRED",
            reason=reason,
            expected_version=state.version,
            updated_at_ms=now_ms,
        )
    if state.recovery_status == "READY":
        return owner.store.update_robot_runtime_state(
            ACCOUNT,
            mode="ROBOT_RUNNING",
            recovery_status="RECONCILIATION_REQUIRED",
            reason=reason,
            expected_version=state.version,
            updated_at_ms=now_ms,
        )
    if state.recovery_status == "RECONCILIATION_REQUIRED":
        return state
    raise AssertionError(f"unexpected runtime state: {(state.mode, state.recovery_status)}")


def _seed_legacy_trigger(owner):
    base = int(time.time() * 1000) - 10_000
    _set_reconciliation_required(owner, reason="legacy acceptance seed")

    candidate, _ = owner.store.create_robot_candidate(
        candidate_id=CANDIDATE_ID,
        trading_account_id=ACCOUNT,
        symbol=SYMBOL,
        status="APPROVED",
        signal_snapshot={"symbol": SYMBOL_TEXT, "pattern": "Falling Wedge"},
        approved_at_ms=base,
        updated_at_ms=base,
    )
    candidate = owner.store.save_robot_candidate_state(
        CANDIDATE_ID,
        status="APPROVED",
        robot_state={
            "direction": "LONG",
            "execution": {"limit_order_id": ENTRY_ORDER_ID},
        },
        expected_revision=candidate.state_revision,
        updated_at_ms=base + 100,
    )

    entry = Execution(
        dedup_key=ExecutionDedupKey(ACCOUNT, Category.LINEAR, ExecutionId("legacy-entry-exec")),
        order_id=OrderId(ENTRY_ORDER_ID),
        symbol=SYMBOL,
        side=OrderSide.BUY,
        price=Price(Decimal("100")),
        quantity=Quantity(Decimal("2")),
        fee=Decimal("0"),
        exchange_timestamp_ms=base + 200,
    )
    owner.store.apply_execution_once(
        entry,
        PositionProjectionUpdate(
            position_key=POSITION_KEY,
            side=PositionSide.LONG,
            quantity=Quantity(Decimal("2")),
            average_entry=Price(Decimal("100")),
            realized_pnl=Decimal("0"),
            accumulated_fee=Decimal("0"),
            engaged_notional=Notional(Decimal("200")),
            sync_state="ready",
            expected_version=None,
            updated_at_ms=base + 200,
        ),
    )
    position = owner.store.get_position_projection(POSITION_KEY)

    owner.store.create_robot_trade(
        trade_id=TRADE_ID,
        trading_account_id=ACCOUNT,
        candidate_id=CANDIDATE_ID,
        symbol=SYMBOL,
        direction="LONG",
        pattern="Falling Wedge",
        source_timeframe="1",
        signal_time_ms=base,
        entry_time_ms=base + 300,
        entry_path="LIMIT",
        actual_wv=Decimal("1"),
        average_entry=Decimal("100"),
        stop_price=Decimal("98"),
        take_price=Decimal("106"),
        entry_quantity=Decimal("2"),
        entry_position_version=position.version,
        created_at_ms=base + 300,
    )
    with owner.store._transaction():
        owner.store._connection.execute(
            "UPDATE robot_trades SET entry_quantity=NULL, entry_position_version=NULL WHERE trade_id=?",
            (TRADE_ID,),
        )

    obligation, _ = owner.store.latch_paper_protection_obligation(
        trade_id=TRADE_ID,
        protection_version=1,
        winning_leg="STOP",
        trigger_price=Decimal("98"),
        observed_exit_price=Decimal("97.5"),
        observed_quantity=Decimal("2"),
        market_event_id="legacy-trigger-event",
        source_received_at_ms=base + 400,
        source_generation=1,
        source_sequence=2,
        source_update_id=3,
        source_event_at_ms=base + 390,
        source_matching_engine_cts_ms=base + 380,
        observed_bid_price=Decimal("97.5"),
        observed_ask_price=Decimal("97.6"),
        latched_at_ms=base + 400,
    )
    result = attest_legacy_robot_entry(
        owner.store,
        trade_id=TRADE_ID,
        obligation_id=obligation.obligation_id,
        client_action_id=ACTION_ID,
        authorized_at_ms=base + 500,
    )
    if not result.created:
        raise AssertionError("legacy attestation fixture was not created")
    return obligation


def _evidence(owner, obligation_id: str):
    trade = owner.store.get_robot_trade(TRADE_ID)
    candidate = owner.store.get_robot_candidate(CANDIDATE_ID)
    obligation = owner.store.get_paper_protection_obligation(obligation_id)
    position = owner.store.get_position_projection(POSITION_KEY)
    executions = owner.store.load_executions()
    stable_close = tuple(
        item
        for item in executions
        if item.dedup_key.exec_id == obligation.exec_id
    )
    runtime = owner.store.get_robot_runtime_state(ACCOUNT)
    return trade, candidate, obligation, position, executions, stable_close, runtime


class LegacyProtectionReconciliationAcceptanceTests(unittest.TestCase):
    def test_attested_legacy_obligation_reconciles_exactly_once_across_repeat_and_restart(self):
        with tempfile.TemporaryDirectory() as temp:
            database_path = Path(temp) / "paper.sqlite3"
            runtime = SerializedPaperRuntime(lambda: _runtime_factory(database_path))
            try:
                obligation = runtime.call(_seed_legacy_trigger)
                before = runtime.call(lambda owner: _evidence(owner, obligation.obligation_id))
                self.assertEqual(len(before[4]), 1)
                self.assertEqual(before[2].status, "TRIGGERED")
                self.assertEqual(before[3].side, PositionSide.LONG)
                self.assertEqual(before[3].quantity.value, Decimal("2"))
                self.assertEqual(before[6].recovery_status, "RECONCILIATION_REQUIRED")

                first = runtime.call(lambda owner: owner.robot_reconcile())
                self.assertTrue(first.success)
                self.assertEqual(first.mode, "ROBOT_RUNNING")
                self.assertEqual(first.recovery_status, "PAUSED")
                self.assertEqual(first.closed_trade_ids, (TRADE_ID,))
                self.assertEqual(first.unresolved_trade_ids, ())
                self.assertEqual(first.unresolved_obligation_ids, ())

                after_first = runtime.call(lambda owner: _evidence(owner, obligation.obligation_id))
                trade, candidate, resolved, position, executions, stable_close, state = after_first
                self.assertEqual(candidate.status, "CLOSED")
                self.assertIsNotNone(trade.exit_time_ms)
                self.assertEqual(trade.exit_reason, "STOP")
                self.assertEqual(trade.exit_price, Decimal("97"))
                self.assertIsNotNone(trade.realized_pnl_usdt)
                self.assertIsNotNone(trade.realized_pnl_pct)
                self.assertEqual(resolved.status, "RESOLVED")
                self.assertEqual(position.side, PositionSide.FLAT)
                self.assertEqual(position.quantity.value, Decimal("0"))
                self.assertEqual(len(executions), 2)
                self.assertEqual(len(stable_close), 1)
                self.assertEqual(stable_close[0].order_id, obligation.order_id)
                self.assertEqual(stable_close[0].side, OrderSide.SELL)
                self.assertEqual(stable_close[0].quantity.value, Decimal("2"))
                self.assertEqual(state.recovery_status, "PAUSED")

                runtime.call(lambda owner: _set_reconciliation_required(
                    owner, reason="repeat reconciliation acceptance",
                ))
                repeated = runtime.call(lambda owner: owner.robot_reconcile())
                self.assertTrue(repeated.success)
                self.assertEqual(repeated.recovery_status, "PAUSED")
                after_repeat = runtime.call(lambda owner: _evidence(owner, obligation.obligation_id))
                self.assertEqual(after_repeat[:6], after_first[:6])

                runtime.close()
                runtime = SerializedPaperRuntime(lambda: _runtime_factory(database_path))
                restarted = runtime.call(lambda owner: _evidence(owner, obligation.obligation_id))
                self.assertEqual(restarted[:6], after_first[:6])
                self.assertEqual(restarted[6].recovery_status, "PAUSED")

                runtime.call(lambda owner: _set_reconciliation_required(
                    owner, reason="post-restart reconciliation acceptance",
                ))
                after_restart_reconcile = runtime.call(lambda owner: owner.robot_reconcile())
                self.assertTrue(after_restart_reconcile.success)
                self.assertEqual(after_restart_reconcile.recovery_status, "PAUSED")
                final = runtime.call(lambda owner: _evidence(owner, obligation.obligation_id))
                self.assertEqual(final[:6], after_first[:6])
            finally:
                runtime.close()


if __name__ == "__main__":
    unittest.main()
