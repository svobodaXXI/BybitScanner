"""Trading Diary projection of Robot STOP reentry campaign attempts.

No second journal/database/financial engine: links are in canonical PAPER
SQLite, actual trade facts and PnL are read from existing Robot Statistics v1.
Observational only; never used by Robot Admission or order execution.
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from pathlib import Path
import sqlite3

from terminal.statistics.models import PnlBasis
from terminal.statistics.reader import RobotStatisticsReadError, RobotStatisticsReader


class ReentryDiaryReadError(RuntimeError):
    """Incomplete or contradictory campaign linkage; no inferred stats."""


@dataclass(frozen=True)
class ReentryDiaryAttempt:
    campaign_id: str
    attempt_index: int
    candidate_id: str
    reserved_at_ms: int
    reserved_risk_usdt: Decimal
    previous_stop_exec_id: str | None
    trade_id: str | None
    exit_time_ms: int | None
    pattern: str | None
    status: str
    exit_reason: str | None
    gross_pnl_usdt: Decimal | None
    fees_costs_usdt: Decimal | None
    known_net_pnl_usdt: Decimal | None


@dataclass(frozen=True)
class ReentryDiaryCampaign:
    campaign_id: str
    trading_account_id: str
    symbol: str
    direction: str
    frozen_thesis_sha256: str
    original_risk_budget_usdt: Decimal
    attempts: tuple[ReentryDiaryAttempt, ...]

    @property
    def filled_attempt_count(self) -> int:
        return sum(item.trade_id is not None for item in self.attempts)

    @property
    def known_net_pnl_usdt(self) -> Decimal | None:
        # Unknown costs are unknown, never zero. Pending and open attempts
        # also forbid reporting a finalized campaign total.
        if any(item.status != "CLOSED" or item.known_net_pnl_usdt is None
               for item in self.attempts):
            return None
        return sum((item.known_net_pnl_usdt for item in self.attempts), Decimal(0))


def _money(value: str, name: str, *, positive: bool = False) -> Decimal:
    try:
        result = Decimal(value)
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise ReentryDiaryReadError(f"{name} is invalid") from exc
    if not result.is_finite() or (positive and result <= 0) or (not positive and result < 0):
        raise ReentryDiaryReadError(f"{name} is invalid")
    return result


class ReentryDiaryReader:
    """Read campaign linkage; reuse RobotStatisticsReader for closed PnL."""

    def __init__(self, database_path: str | Path):
        self._path = Path(database_path)

    def load(self, *, trading_account_id: str = "paper") -> tuple[ReentryDiaryCampaign, ...]:
        if not isinstance(trading_account_id, str) or not trading_account_id.strip():
            raise ValueError("account id must be non-empty")
        if not self._path.is_file():
            raise ReentryDiaryReadError("PAPER database does not exist")
        # Canonical stats owns trade/fee parsing and reconciliation validation.
        try:
            trades = RobotStatisticsReader(self._path).load_completed_trades(
                trading_account_id=trading_account_id
            )
        except RobotStatisticsReadError as exc:
            raise ReentryDiaryReadError("Robot statistics facts unavailable") from exc
        completed = {trade.candidate_id: trade for trade in trades}
        connection = sqlite3.connect(self._path.resolve().as_uri() + "?mode=ro", uri=True)
        connection.row_factory = sqlite3.Row
        try:
            tables = {
                row[0] for row in connection.execute(
                    "SELECT name FROM sqlite_master WHERE type='table'"
                )
            }
            if not {"robot_reentry_campaigns", "robot_reentry_attempts"}.issubset(tables):
                raise ReentryDiaryReadError("reentry lineage schema unavailable")
            rows = connection.execute(
                """SELECT c.campaign_id, c.trading_account_id, c.symbol,
                          c.direction, c.first_candidate_id, c.frozen_thesis_sha256,
                          c.original_risk_budget_usdt, a.attempt_index,
                          a.candidate_id, a.reserved_risk_usdt,
                          a.previous_stop_exec_id, a.reserved_at_ms,
                          t.trade_id, t.exit_time_ms
                   FROM robot_reentry_campaigns c
                   LEFT JOIN robot_reentry_attempts a
                     ON a.trading_account_id=c.trading_account_id
                    AND a.campaign_id=c.campaign_id
                   LEFT JOIN robot_trades t
                     ON t.candidate_id=a.candidate_id
                    AND t.trading_account_id=a.trading_account_id
                   WHERE c.trading_account_id=?
                   ORDER BY c.created_at_ms,c.campaign_id,
                            a.attempt_index,a.reserved_at_ms,a.candidate_id""",
                (trading_account_id,),
            ).fetchall()
            groups: dict[str, tuple[sqlite3.Row, list[ReentryDiaryAttempt]]] = {}
            for row in rows:
                name = row["campaign_id"]
                if name not in groups:
                    groups[name] = (row, [])
                if row["candidate_id"] is None:
                    raise ReentryDiaryReadError("campaign has no initial attempt")
                index = int(row["attempt_index"])
                previous = groups[name][1][-1] if groups[name][1] else None
                if index != len(groups[name][1]) + 1 or index > 3:
                    raise ReentryDiaryReadError("non-contiguous or duplicate attempt indexes")
                if index == 1 and row["candidate_id"] != row["first_candidate_id"]:
                    raise ReentryDiaryReadError("first attempt contradicts campaign identity")
                if previous is not None:
                    if previous.status != "CLOSED" or previous.exit_reason != "STOP":
                        raise ReentryDiaryReadError("retry requires prior closed STOP")
                    if previous.exit_time_ms is None or int(row["reserved_at_ms"]) <= previous.exit_time_ms:
                        raise ReentryDiaryReadError("retry reservation must follow STOP close")
                trade = completed.get(row["candidate_id"])
                if row["trade_id"] is not None and row["exit_time_ms"] is not None and trade is None:
                    raise ReentryDiaryReadError("completed attempt has unproven Robot statistics")
                if trade is not None and trade.trade_id != row["trade_id"]:
                    raise ReentryDiaryReadError("campaign trade attribution conflicts")
                if trade is not None:
                    if (trade.symbol != row["symbol"]
                            or trade.direction != row["direction"]
                            or trade.trading_account_id != trading_account_id):
                        raise ReentryDiaryReadError("trade differs from campaign account/symbol/direction")
                    if trade.exit_time_ms < trade.entry_time_ms:
                        raise ReentryDiaryReadError("trade exit precedes entry")
                    # A multi-candle pattern may begin forming before STOP.
                    # Its confirmation is checked by the owning admission
                    # adapter; signal_time_ms is NOT necessarily that close.
                    # The Diary only proves non-overlapping observed trades.
                    if previous is not None and trade.entry_time_ms <= previous.exit_time_ms:
                        raise ReentryDiaryReadError("trade entry predates prior STOP")
                    status = "CLOSED"
                elif row["trade_id"] is not None:
                    status = "OPEN"
                else:
                    status = "RESERVED_OR_UNFILLED"
                groups[name][1].append(ReentryDiaryAttempt(
                    campaign_id=name,
                    attempt_index=int(row["attempt_index"]),
                    candidate_id=str(row["candidate_id"]),
                    reserved_at_ms=int(row["reserved_at_ms"]),
                    reserved_risk_usdt=_money(row["reserved_risk_usdt"], "reserved risk", positive=True),
                    previous_stop_exec_id=row["previous_stop_exec_id"],
                    trade_id=str(row["trade_id"]) if row["trade_id"] is not None else None,
                    exit_time_ms=trade.exit_time_ms if trade else None,
                    pattern=trade.pattern if trade else None,
                    status=status,
                    exit_reason=trade.exit_reason if trade else None,
                    gross_pnl_usdt=trade.realized_pnl_usdt if trade else None,
                    fees_costs_usdt=trade.fees_costs_usdt if trade else None,
                    known_net_pnl_usdt=trade.pnl_usdt(PnlBasis.KNOWN_COST_ADJUSTED) if trade else None,
                ))
            return tuple(
                ReentryDiaryCampaign(
                    campaign_id=name, trading_account_id=trading_account_id,
                    symbol=str(row["symbol"]), direction=str(row["direction"]),
                    frozen_thesis_sha256=str(row["frozen_thesis_sha256"]),
                    original_risk_budget_usdt=_money(
                        row["original_risk_budget_usdt"], "original risk budget", positive=True
                    ),
                    attempts=tuple(attempts),
                )
                for name, (row, attempts) in groups.items()
            )
        except sqlite3.Error as exc:
            raise ReentryDiaryReadError("reentry diary unavailable") from exc
        finally:
            connection.close()
