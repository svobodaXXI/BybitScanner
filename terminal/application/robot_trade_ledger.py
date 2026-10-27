"""Pure durable OPEN Robot candidate ↔ trade correlation.

PAPER net positions cannot be assigned to a stale, duplicate, or mismatched
Robot ledger entry. This read-only predicate is shared by Close-All preflight
and explicit Robot reconciliation; it never claims an execution or FLAT proof.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from typing import Iterable, Protocol


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
