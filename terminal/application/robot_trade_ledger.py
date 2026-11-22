"""Pure durable OPEN Robot candidate ↔ trade correlation.

PAPER net positions cannot be assigned to a stale, duplicate, or mismatched
Robot ledger entry. This read-only predicate is shared by Close-All preflight
and explicit Robot reconciliation; it never claims an execution or FLAT proof.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from typing import Iterable, Mapping, Protocol
from decimal import Decimal

import robot_protection
from terminal.domain.models import CommandId, OrderId, OrderSide, PositionSide


class _RobotLedgerRow(Protocol):
    candidate_id: str
    symbol: object


class _RobotTradeLedgerRow(_RobotLedgerRow, Protocol):
    trade_id: str


@dataclass(frozen=True, slots=True)
class RobotOpenTradeLedgerProof:
    invalid_candidate_ids: tuple[str, ...]
    invalid_trade_ids: tuple[str, ...]
    orphan_trade_ids: tuple[str, ...]

    @property
    def valid(self) -> bool:
        return not self.invalid_candidate_ids and not self.invalid_trade_ids


def prove_robot_open_trade_ledger(
    candidates: Iterable[_RobotLedgerRow],
    trades: Iterable[_RobotTradeLedgerRow],
) -> RobotOpenTradeLedgerProof:
    """Require one-to-one candidate/trade IDs and matching symbol.

    A duplicate candidate id, duplicate trade owner, or multiple candidates
    on the same net symbol fails closed. Missing/truncated rows are not
    interpreted as a closed trade.
    """
    candidate_rows = tuple(candidates)
    trade_rows = tuple(trades)
    candidate_counts = Counter(item.candidate_id for item in candidate_rows)
    trade_counts = Counter(item.candidate_id for item in trade_rows)
    symbol_counts = Counter(item.symbol for item in candidate_rows)
    by_candidate = {item.candidate_id: item for item in candidate_rows}
    invalid_candidates = set()
    invalid_trades = set()
    orphans = set()

    for candidate in candidate_rows:
        if (
            candidate_counts[candidate.candidate_id] != 1
            or trade_counts[candidate.candidate_id] != 1
            or symbol_counts[candidate.symbol] != 1
        ):
            invalid_candidates.add(candidate.candidate_id)

    for trade in trade_rows:
        candidate = by_candidate.get(trade.candidate_id)
        if candidate is None:
            orphans.add(trade.trade_id)
            invalid_trades.add(trade.trade_id)
        elif (
            trade_counts[trade.candidate_id] != 1
            or candidate_counts[trade.candidate_id] != 1
            or candidate.symbol != trade.symbol
            or symbol_counts[candidate.symbol] != 1
        ):
            invalid_trades.add(trade.trade_id)
            invalid_candidates.add(trade.candidate_id)

    return RobotOpenTradeLedgerProof(
        tuple(sorted(invalid_candidates)),
        tuple(sorted(invalid_trades)),
        tuple(sorted(orphans)),
    )


def attest_wedge_partial(store, trade, *, remaining_quantity: Decimal, position=None):

    """Exact one-trade reduction lineage for STOP/TAKE and final PnL.

    Called ONLY for a Wedge carrying a durable partial intent. The entry
    orders, filled reduce-only command, exit order, quantity, direction,
    prices and fees must all be independently recoverable from PAPER.
    A pending/foreign/ambiguous partial cannot authorize STOP dispatch or
    close financial finalization.
    """
    from terminal.application.robot_breakout_monitor import robot_entry_order_ids

    if (trade.pattern not in ("Falling Wedge", "Rising Wedge")
            or trade.entry_quantity is None or trade.entry_quantity <= 0
            or not isinstance(remaining_quantity, Decimal)
            or not remaining_quantity.is_finite()
            or not Decimal(0) < remaining_quantity < trade.entry_quantity):
        raise RuntimeError("Wedge partial remainder not proven")
    candidate = store.get_robot_candidate(trade.candidate_id)
    if (candidate is None or candidate.status != "OPEN"
            or candidate.trading_account_id != trade.trading_account_id
            or candidate.symbol != trade.symbol
            or candidate.signal_snapshot.get("pattern") != trade.pattern
            or not isinstance(candidate.robot_state, Mapping)):
        raise RuntimeError("Wedge partial candidate owner not proven")
    state = candidate.robot_state
    execution = state.get("execution") or {}
    if not isinstance(execution, Mapping):
        raise RuntimeError("Wedge partial execution state invalid")
    intent = execution.get("wedge_be_partial_intent")
    if not isinstance(intent, Mapping):
        raise RuntimeError("Wedge partial intent missing")
    robot_protection.restore_wedge_be_partial_intent(
        intent, account_id=trade.trading_account_id.value,
        trade_id=trade.trade_id, candidate_id=trade.candidate_id,
        symbol=trade.symbol.value, direction=trade.direction,
        original_quantity=trade.entry_quantity,
        remaining_quantity=trade.entry_quantity,
    )
    command = store.get_command(CommandId(intent["command_id"]))
    exit_side = OrderSide.SELL if trade.direction == "LONG" else OrderSide.BUY
    if (
        command is None or command.current_state.value != "filled"
        or command.trading_account_id != trade.trading_account_id
        or command.symbol != trade.symbol
        or command.order_link_id != intent["order_link_id"]
        or command.command_kind != "create_market"
        or command.side is not exit_side
        or command.normalized_quantity is None
        or command.normalized_quantity.value != Decimal(intent["partial_quantity"])
    ):
        raise RuntimeError("Wedge reduce-only partial command not confirmed")
    entry_orders = robot_entry_order_ids(
        store, trade.trading_account_id, candidate, execution,
        entry_path=trade.entry_path,
    )
    if not entry_orders:
        raise RuntimeError("Wedge entry order identity unproven")
    entry_fills = tuple(
        fill for order_id in entry_orders
        for fill in store.load_executions_for_order(
            trade.trading_account_id, order_id,
        )
    )
    exit_id = OrderId("paper-order-" + str(intent["order_link_id"]))
    partial_fills = store.load_executions_for_order(
        trade.trading_account_id, exit_id,
    )
    facts = robot_protection.summarize_attested_robot_partial(
        trade.direction, trading_account_id=trade.trading_account_id,
        symbol=trade.symbol,
        entry_order_ids=tuple(order_id.value for order_id in entry_orders),
        partial_order_id=exit_id.value,
        entry_executions=entry_fills, partial_executions=partial_fills,
        actual_remaining_quantity=remaining_quantity,
    )
    if (facts.original_quantity != trade.entry_quantity
            or facts.average_entry != trade.average_entry
            or facts.closed_quantity != Decimal(intent["partial_quantity"])
            or facts.latest_partial_fill_ms <= int(intent["trigger_candle_end_ms"])):
        raise RuntimeError("Wedge partial fills contradict durable trade/intent")
    if position is not None:
        # Every applied PAPER fill advances the position projection exactly
        # once. No unrelated fill or position rewrite may be hidden by a
        # matching remaining quantity or average.
        if (
            trade.trading_account_id.value != "paper"
            or command.exchange_order_id != exit_id
            or trade.entry_position_version is None
            or position.version != trade.entry_position_version + len(partial_fills)
            or position.sync_state not in ("synced", "synchronized")
            or position.quantity.value != remaining_quantity
            or position.average_entry is None
            or position.average_entry.value != trade.average_entry
            or position.side is not (
                PositionSide.LONG if trade.direction == "LONG" else PositionSide.SHORT
            )
        ):
            raise RuntimeError("Wedge partial position lineage not proven")
    return facts


def prove_wedge_partial_remainder(store, trade, position, protection):
    """Read-only restart proof: original entry, one filled partial, armed remainder."""
    from terminal.application.robot_admission import active_robot_owner_candidate_ids

    if position is None or protection is None:
        raise RuntimeError("Wedge partial position/protection unavailable")
    facts = attest_wedge_partial(
        store, trade, remaining_quantity=position.quantity.value, position=position,
    )
    if (protection.status != "confirmed_active"
            or protection.pending_command_id is not None
            or protection.stop_loss is None
            or not protection.stop_loss.is_finite()
            or protection.stop_loss <= 0
            or protection.take_profit != trade.take_price
            or store.load_active_paper_limits(trade.trading_account_id, trade.symbol)
            or store.load_unresolved_paper_protection_obligations(trade.trading_account_id)
            or any(cmd.trading_account_id == trade.trading_account_id
                   and cmd.symbol == trade.symbol for cmd in store.load_unfinished_commands())
            or active_robot_owner_candidate_ids(
                store, trade.trading_account_id, trade.symbol,
                excluding_candidate_id=trade.candidate_id,
            )):
        raise RuntimeError("Wedge partial protection or exclusive ownership not proven")

    candidate = store.get_robot_candidate(trade.candidate_id)
    execution = candidate.robot_state["execution"]
    partial_intent = execution["wedge_be_partial_intent"]
    stop_intent = execution.get("wedge_be_stop_intent")
    if stop_intent is None:
        if protection.stop_loss != trade.stop_price:
            raise RuntimeError("Wedge partial STOP changed without durable intent")
    else:
        if (not isinstance(stop_intent, Mapping)
                or stop_intent.get("partial_command_id") != partial_intent["command_id"]
                or not isinstance(stop_intent.get("client_action_id"), str)
                or not stop_intent["client_action_id"]):
            raise RuntimeError("Wedge partial STOP intent not proven")
        target = Decimal(str(stop_intent.get("stop_price")))
        if not target.is_finite() or target != protection.stop_loss:
            raise RuntimeError("Wedge partial STOP outcome not confirmed")
    if not (
        trade.stop_price <= protection.stop_loss < trade.take_price
        if trade.direction == "LONG"
        else trade.take_price < protection.stop_loss <= trade.stop_price
    ):
        raise RuntimeError("Wedge partial STOP loosens or crosses protection")
    return facts
