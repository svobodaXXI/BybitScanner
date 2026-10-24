"""CR-PAPER-PROTECTION-LIFECYCLE-001 21.2: a Wedge/L-shape STOP/TAKE close records entry + exit fees.

#608 PAPER run 24.10.2026: Wedge/L-shape ``robot_trades.fees_costs_usdt`` held only the exit
fee, while Box closes already recorded the whole lifecycle. Only the candidate's own entry
order identities are correlated; unproven correlation keeps the exit-only total.
Temporary SQLite only.
"""
from decimal import Decimal
from pathlib import Path
import tempfile

from terminal.domain.models import Symbol, TradingAccountId
from tests.test_terminal_paper_runtime import (
    MutableBookProvider, _crossing_book, _entry_book, _open_robot_position_with_confirmed_protection,
    _runtime_with_provider,
)

ACCOUNT = TradingAccountId("paper")


def _open(runtime, *, link_entry=True, entry_quantity_override=None):
    _open_robot_position_with_confirmed_protection(
        runtime, symbol="BTCUSDT", entry_price=Decimal("64250.5"),
        stop_price=Decimal("64000"), take_price=Decimal("64600"),
        trade_id="trade-fee-1", candidate_id="candidate-fee-1",
    )
    entry_fills = runtime.store.load_executions_for_symbol(ACCOUNT, Symbol("BTCUSDT"))
    assert len(entry_fills) == 1
    entry = entry_fills[0]
    if link_entry:
        candidate = runtime.store.get_robot_candidate("candidate-fee-1")
        runtime.store.save_robot_candidate_state(
            "candidate-fee-1", status=candidate.status,
            robot_state={"phase": "RETEST_DETECTED", "direction": "LONG",
                         "execution": {"limit_order_id": entry.order_id.value}},
            expected_revision=candidate.state_revision, updated_at_ms=1600,
        )
    if entry_quantity_override is not None:
        runtime.store._connection.execute(
            "UPDATE robot_trades SET entry_quantity=? WHERE trade_id='trade-fee-1'",
            (str(entry_quantity_override(entry.quantity.value)),),
        )
    return entry


def _stop(runtime, provider):
    close_book = _crossing_book("BTCUSDT", bid="63990", ask="63995")
    provider.set_book("BTCUSDT", close_book)
    obligation = runtime.evaluate_robot_protection_crossing(
        "BTCUSDT", close_book, event_id="evt-stop", received_at_ms=5000,
    )
    assert obligation is not None and obligation.status == "RESOLVED"
    exit_fill = [fill for fill in runtime.store.load_executions_for_symbol(ACCOUNT, Symbol("BTCUSDT"))
                 if fill.side.value == "Sell"]
    assert len(exit_fill) == 1
    return runtime.store.get_robot_trade("trade-fee-1"), exit_fill[0]


def _with_runtime(test):
    with tempfile.TemporaryDirectory() as temp:
        provider = MutableBookProvider("BTCUSDT", _entry_book())
        runtime = _runtime_with_provider(Path(temp) / "paper.sqlite3", provider)
        try:
            test(runtime, provider)
        finally:
            runtime.close()


def test_stop_close_records_entry_and_exit_fees_and_fee_inclusive_pct():
    def run(runtime, provider):
        entry = _open(runtime)
        trade, exit_fill = _stop(runtime, provider)
        assert entry.fee > 0 and exit_fill.fee > 0
        assert trade.fees_costs_usdt == entry.fee + exit_fill.fee
        notional = trade.entry_quantity * trade.average_entry
        assert trade.realized_pnl_pct == (
            (trade.realized_pnl_usdt - entry.fee - exit_fill.fee) / notional * 100
        )
    _with_runtime(run)


def test_unlinked_entry_keeps_the_previous_exit_only_total():
    def run(runtime, provider):
        _open(runtime, link_entry=False)
        trade, exit_fill = _stop(runtime, provider)
        assert trade.fees_costs_usdt == exit_fill.fee
        assert trade.exit_reason == "STOP"
    _with_runtime(run)


def test_entry_fills_not_matching_the_attested_quantity_are_not_attributed():
    def run(runtime, provider):
        _open(runtime, entry_quantity_override=lambda quantity: quantity * 2)
        assert runtime._robot_entry_fees(runtime.store.get_robot_trade("trade-fee-1")) is None
    _with_runtime(run)
