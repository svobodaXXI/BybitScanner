"""AUTOPILOT-EQUITY-1B: read-only daily equity facts of the PAPER account (PAPER-equity v1).

Owner-approved model (no admission wiring here; the daily-loss gate comes later):

* Funding: the PAPER simulator never applies funding, so its contribution is zero by
  definition of the simulator. This is NOT a LIVE assumption.
* Day: business day starts at 00:00 Moscow time (MSK, fixed UTC+3).
* Baseline: equity at 00:00 MSK, rebuilt from the immutable ``executions`` journal
  only when that replay proves every position FLAT at the boundary. A position open
  at the boundary makes the whole day DATA_UNAVAILABLE; no later equity is substituted.
* Current: deposit + realized PnL - fees of the full replay, plus unrealized PnL of
  open positions at caller-supplied fresh mark prices (an explicit input; nothing is
  fetched here). A missing, stale or invalid mark for an open position is unavailable.
* External transfers are unsupported in PAPER: the account row must still be its
  single initial-deposit version. Any accounting contradiction is unavailable.

Replay uses the exact runtime projection arithmetic (``execution_engine``) and must
reproduce every stored ``position_projections`` row of the account; otherwise the
journal is not a proof of history. Tied execution timestamps of one symbol cannot
prove fill order and fail closed, as in ``robot_flat_closure``.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
from typing import Any, Iterable, Mapping

from terminal.application.execution_engine import (
    _average_after_fill, _realized_pnl, _signed_quantity,
)
from terminal.domain.models import OrderSide, PositionSide, TradingAccountId

MSK = timezone(timedelta(hours=3), "MSK")
DAY_MS = 86_400_000
FUNDING_MODEL = "PAPER_SIMULATOR_NO_FUNDING"

ACCOUNT_UNAVAILABLE = "ACCOUNT_UNAVAILABLE"
EXTERNAL_TRANSFER_UNSUPPORTED = "EXTERNAL_TRANSFER_UNSUPPORTED"
ACCOUNT_CREATED_AFTER_DAY_START = "ACCOUNT_CREATED_AFTER_DAY_START"
EXECUTION_DATA_INVALID = "EXECUTION_DATA_INVALID"
EXECUTION_AFTER_AS_OF = "EXECUTION_AFTER_AS_OF"
EXECUTION_ORDER_AMBIGUOUS = "EXECUTION_ORDER_AMBIGUOUS"
PROJECTION_MISMATCH = "PROJECTION_MISMATCH"
POSITION_OPEN_AT_DAY_START = "POSITION_OPEN_AT_DAY_START"
MARK_PRICE_MISSING = "MARK_PRICE_MISSING"
MARK_PRICE_STALE = "MARK_PRICE_STALE"
MARK_PRICE_INVALID = "MARK_PRICE_INVALID"
BASELINE_NOT_POSITIVE = "BASELINE_NOT_POSITIVE"
READ_FAILED = "READ_FAILED"


@dataclass(frozen=True, slots=True)
class MarkPrice:
    """A mark price observed by the running runtime; supplied by the caller."""

    price: Decimal
    observed_at_ms: int


@dataclass(frozen=True, slots=True)
class PaperDailyEquityFacts:
    trading_account_id: str
    business_date_msk: str
    day_start_ms: int
    as_of_ms: int
    baseline_equity_usdt: Decimal | None
    current_adjusted_equity_usdt: Decimal | None
    daily_change_usdt: Decimal | None
    daily_change_pct: Decimal | None
    data_available: bool
    unavailability_reason: str | None
    funding_model: str = FUNDING_MODEL


class _Unavailable(Exception):
    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


@dataclass(slots=True)
class _Lot:
    signed: Decimal = Decimal(0)
    average: Decimal | None = None
    realized: Decimal = Decimal(0)
    fees: Decimal = Decimal(0)


def msk_day_start_ms(as_of_ms: int) -> tuple[str, int]:
    """(ISO business date, epoch ms of its 00:00 MSK) containing ``as_of_ms``."""
    moment = datetime.fromtimestamp(as_of_ms / 1000, tz=MSK)
    start = datetime(moment.year, moment.month, moment.day, tzinfo=MSK)
    return start.date().isoformat(), int(start.timestamp()) * 1000


def _decimal(value: Any) -> Decimal:
    try:
        result = Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError):
        raise _Unavailable(EXECUTION_DATA_INVALID) from None
    if not result.is_finite():
        raise _Unavailable(EXECUTION_DATA_INVALID)
    return result


def _apply(lot: _Lot, side: str, price: Decimal, quantity: Decimal, fee: Decimal) -> None:
    fill = quantity if side == OrderSide.BUY.value else -quantity
    result = lot.signed + fill
    lot.realized += _realized_pnl(lot.signed, lot.average, fill, price)
    lot.average = _average_after_fill(lot.signed, lot.average, fill, price, result)
    lot.signed = result
    lot.fees += fee


def _replay(executions: Iterable[Mapping[str, Any]], account: str, as_of_ms: int,
            day_start_ms: int) -> tuple[dict[str, _Lot], dict[str, _Lot]]:
    """Full replay and the replay of executions strictly before ``day_start_ms``."""
    by_symbol: dict[str, list[tuple[int, str, Decimal, Decimal, Decimal]]] = {}
    for row in executions:
        if (row.get("trading_account_id") != account or row.get("category") != "linear"
                or row.get("side") not in (OrderSide.BUY.value, OrderSide.SELL.value)
                or not isinstance(row.get("symbol"), str) or not row["symbol"]):
            raise _Unavailable(EXECUTION_DATA_INVALID)
        stamp = row.get("exchange_timestamp_ms")
        if type(stamp) is not int or stamp < 0:
            raise _Unavailable(EXECUTION_DATA_INVALID)
        if stamp > as_of_ms:
            raise _Unavailable(EXECUTION_AFTER_AS_OF)
        price, quantity, fee = (_decimal(row.get(k)) for k in ("price", "quantity", "fee"))
        if price <= 0 or quantity <= 0:
            raise _Unavailable(EXECUTION_DATA_INVALID)
        by_symbol.setdefault(row["symbol"], []).append((stamp, row["side"], price, quantity, fee))
    full: dict[str, _Lot] = {}
    at_start: dict[str, _Lot] = {}
    for symbol, fills in by_symbol.items():
        fills.sort(key=lambda item: item[0])
        if any(a[0] == b[0] for a, b in zip(fills, fills[1:])):
            raise _Unavailable(EXECUTION_ORDER_AMBIGUOUS)
        lot, start = _Lot(), _Lot()
        for stamp, side, price, quantity, fee in fills:
            _apply(lot, side, price, quantity, fee)
            if stamp < day_start_ms:
                _apply(start, side, price, quantity, fee)
        full[symbol], at_start[symbol] = lot, start
    return full, at_start


def _check_projections(projections: Iterable[Mapping[str, Any]], full: Mapping[str, _Lot],
                       account: str) -> None:
    """Every stored position row must equal the replay; a replayed lot needs its row."""
    seen = set()
    for row in projections:
        symbol = row.get("symbol")
        if (row.get("trading_account_id") != account or row.get("category") != "linear"
                or row.get("position_idx") != 0 or symbol in seen):
            raise _Unavailable(PROJECTION_MISMATCH)
        seen.add(symbol)
        lot = full.get(symbol, _Lot())
        try:
            side = PositionSide(row.get("side"))
        except ValueError:
            raise _Unavailable(PROJECTION_MISMATCH) from None
        average = row.get("average_entry")
        if (_signed_quantity(side, _decimal(row.get("quantity"))) != lot.signed
                or (None if average is None else _decimal(average)) != lot.average
                or _decimal(row.get("realized_pnl")) != lot.realized
                or _decimal(row.get("accumulated_fee")) != lot.fees):
            raise _Unavailable(PROJECTION_MISMATCH)
    if any(symbol not in seen for symbol in full):
        raise _Unavailable(PROJECTION_MISMATCH)


def compute_paper_daily_equity(
    account: Mapping[str, Any] | None,
    executions: Iterable[Mapping[str, Any]],
    projections: Iterable[Mapping[str, Any]],
    *,
    trading_account_id: str,
    as_of_ms: int,
    marks: Mapping[str, MarkPrice],
    max_mark_age_ms: int,
) -> PaperDailyEquityFacts:
    """Pure PAPER-equity v1 facts from one consistent snapshot of account rows."""
    business_date, day_start_ms = msk_day_start_ms(as_of_ms)

    def unavailable(reason: str) -> PaperDailyEquityFacts:
        return PaperDailyEquityFacts(trading_account_id, business_date, day_start_ms, as_of_ms,
                                     None, None, None, None, False, reason)

    try:
        if (account is None or trading_account_id != "paper"
                or account.get("trading_account_id") != trading_account_id):
            raise _Unavailable(ACCOUNT_UNAVAILABLE)
        deposit = _decimal(account.get("initial_deposit_usdt"))
        if (deposit <= 0 or account.get("version") != 1
                or _decimal(account.get("equity_usdt")) != deposit):
            raise _Unavailable(EXTERNAL_TRANSFER_UNSUPPORTED)
        created_ms = account.get("updated_at_ms")
        if type(created_ms) is not int or created_ms > as_of_ms:
            raise _Unavailable(ACCOUNT_UNAVAILABLE)
        if created_ms >= day_start_ms:
            raise _Unavailable(ACCOUNT_CREATED_AFTER_DAY_START)
        full, at_start = _replay(executions, trading_account_id, as_of_ms, day_start_ms)
        _check_projections(projections, full, trading_account_id)
        if any(lot.signed != 0 for lot in at_start.values()):
            raise _Unavailable(POSITION_OPEN_AT_DAY_START)
        baseline = deposit + sum((lot.realized - lot.fees for lot in at_start.values()), Decimal(0))
        if baseline <= 0:
            raise _Unavailable(BASELINE_NOT_POSITIVE)
        unrealized = Decimal(0)
        for symbol, lot in full.items():
            if lot.signed == 0:
                continue
            mark = marks.get(symbol)
            if mark is None:
                raise _Unavailable(MARK_PRICE_MISSING)
            if (not isinstance(mark.price, Decimal) or not mark.price.is_finite()
                    or mark.price <= 0 or type(mark.observed_at_ms) is not int
                    or mark.observed_at_ms > as_of_ms or lot.average is None):
                raise _Unavailable(MARK_PRICE_INVALID)
            if as_of_ms - mark.observed_at_ms > max_mark_age_ms:
                raise _Unavailable(MARK_PRICE_STALE)
            unrealized += lot.signed * (mark.price - lot.average)
        current = deposit + sum((lot.realized - lot.fees for lot in full.values()),
                                Decimal(0)) + unrealized
        change = current - baseline
        return PaperDailyEquityFacts(
            trading_account_id, business_date, day_start_ms, as_of_ms, baseline, current,
            change, change / baseline * Decimal(100), True, None)
    except _Unavailable as error:
        return unavailable(error.reason)


def collect_paper_daily_equity_facts(
    store, account: TradingAccountId, *, as_of_ms: int,
    marks: Mapping[str, MarkPrice], max_mark_age_ms: int,
) -> PaperDailyEquityFacts:
    """Read the account, its executions and position rows in ONE read snapshot.

    ``store`` is a reader (``SQLiteStore.open_reader``) owned by the calling thread;
    nothing is written. ``marks`` come from the running runtime; nothing is fetched.
    """
    _require_inputs(as_of_ms, max_mark_age_ms)
    try:
        with store.read_snapshot():
            return paper_daily_equity_facts_in_transaction(
                store, account, as_of_ms=as_of_ms, marks=marks, max_mark_age_ms=max_mark_age_ms)
    except Exception:
        return _read_failed(account, as_of_ms)


def paper_daily_equity_facts_in_transaction(
    store, account: TradingAccountId, *, as_of_ms: int,
    marks: Mapping[str, MarkPrice], max_mark_age_ms: int,
) -> PaperDailyEquityFacts:
    """Same facts from the caller's already open transaction (e.g. the admission one).

    The caller's BEGIN IMMEDIATE snapshot makes the rows consistent with every other
    admission fact; a read error is READ_FAILED, never an implicit pass.
    """
    _require_inputs(as_of_ms, max_mark_age_ms)
    try:
        record = store.get_paper_account(account)
        rows = store.load_paper_portfolio_rows(account) if account.value == "paper" else None
    except Exception:
        return _read_failed(account, as_of_ms)
    account_row = None if record is None else {
        "trading_account_id": record.trading_account_id.value,
        "initial_deposit_usdt": record.initial_deposit_usdt,
        "equity_usdt": record.equity_usdt,
        "version": record.version,
        "updated_at_ms": record.updated_at_ms,
    }
    return compute_paper_daily_equity(
        account_row, rows["executions"] if rows else (), rows["position_projections"] if rows else (),
        trading_account_id=account.value, as_of_ms=as_of_ms, marks=marks,
        max_mark_age_ms=max_mark_age_ms)


def _require_inputs(as_of_ms: int, max_mark_age_ms: int) -> None:
    if type(max_mark_age_ms) is not int or max_mark_age_ms < 0 or type(as_of_ms) is not int:
        raise ValueError("explicit integer as_of_ms and non-negative max_mark_age_ms are required")


def _read_failed(account: TradingAccountId, as_of_ms: int) -> PaperDailyEquityFacts:
    business_date, day_start_ms = msk_day_start_ms(as_of_ms)
    return PaperDailyEquityFacts(account.value, business_date, day_start_ms, as_of_ms,
                                 None, None, None, None, False, READ_FAILED)
