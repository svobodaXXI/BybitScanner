"""SIMULATION-only USDT linear-perpetual accounting projection.

Consumes explicit virtual execution receipts; it never creates orders, assumes
fills, calls Bybit, owns Robot strategy, or accesses PAPER/MAIN/testnet.
No leverage/collateral/free-margin/liquidation model is claimed here.
The entire fill history is immutable except for append; historical snapshots
are projections that never change the journal or replay an external command.
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
import re


IDENTITY = re.compile(r"^[A-Za-z0-9_-]{1,100}$")
SYMBOL = re.compile(r"^[A-Z0-9]{3,30}$")


def _money(value: Decimal, *, positive: bool = False) -> Decimal:
    if not isinstance(value, Decimal) or not value.is_finite():
        raise ValueError("finite Decimal amount is required")
    if positive and value <= 0:
        raise ValueError("positive Decimal amount is required")
    if not positive and value < 0:
        raise ValueError("negative amount is forbidden")
    return value


@dataclass(frozen=True)
class VirtualFill:
    """Receipt already produced by a future *isolated* simulated exchange."""
    simulation_run_id: str
    symbol: str
    fill_id: str
    virtual_time_ms: int
    side: str
    quantity: Decimal
    price: Decimal
    fee: Decimal
    namespace: str = "SIMULATION"

    def __post_init__(self) -> None:
        if self.namespace != "SIMULATION":
            raise ValueError("exchange-backed receipts are forbidden")
        if not IDENTITY.fullmatch(self.simulation_run_id):
            raise ValueError("unsafe run identity")
        if not IDENTITY.fullmatch(self.fill_id):
            raise ValueError("invalid virtual fill identity")
        if not SYMBOL.fullmatch(self.symbol) or not self.symbol.endswith("USDT"):
            raise ValueError("invalid simulated symbol")
        if type(self.virtual_time_ms) is not int or self.virtual_time_ms < 0:
            raise ValueError("invalid virtual execution timestamp")
        if self.side not in {"BUY", "SELL"}:
            raise ValueError("only BUY/SELL virtual receipts are supported")
        _money(self.quantity, positive=True)
        _money(self.price, positive=True)
        _money(self.fee)


@dataclass(frozen=True)
class VirtualAccountSnapshot:
    simulation_run_id: str
    symbol: str
    as_of_ms: int
    initial_balance: Decimal
    balance: Decimal
    position_quantity: Decimal  # positive LONG; negative SHORT
    average_entry: Decimal | None
    realized_gross_pnl: Decimal
    fees: Decimal
    unrealized_pnl: Decimal
    equity: Decimal
    applied_fills: int
    namespace: str = "SIMULATION"

    @property
    def realized_net_pnl(self) -> Decimal:
        return self.realized_gross_pnl - self.fees

    @property
    def total_net_pnl(self) -> Decimal:
        return self.realized_net_pnl + self.unrealized_pnl

    def to_payload(self) -> dict[str, object]:
        return {
            "namespace": self.namespace,
            "simulation_run_id": self.simulation_run_id,
            "symbol": self.symbol,
            "virtual_time_ms": self.as_of_ms,
            "initial_balance": str(self.initial_balance),
            "balance": str(self.balance),
            "position_quantity": str(self.position_quantity),
            "average_entry": str(self.average_entry) if self.average_entry is not None else None,
            "realized_gross_pnl": str(self.realized_gross_pnl),
            "fees": str(self.fees),
            "realized_net_pnl": str(self.realized_net_pnl),
            "unrealized_pnl": str(self.unrealized_pnl),
            "equity": str(self.equity),
            "total_net_pnl": str(self.total_net_pnl),
            "applied_fills": self.applied_fills,
        }


class VirtualAccount:
    """Single-symbol, one-way USDT-linear account; receipts only, no execution.

    With no margin/collateral model, `balance` means deposit plus closed gross
    PnL minus fees, NOT free purchasing power. Never infer order eligibility,
    leverage or liquidation from this projection.
    """

    def __init__(
        self, *, simulation_run_id: str, symbol: str, initial_balance: Decimal,
    ) -> None:
        if not IDENTITY.fullmatch(simulation_run_id):
            raise ValueError("unsafe SIMULATION run ID")
        if not SYMBOL.fullmatch(symbol) or not symbol.endswith("USDT"):
            raise ValueError("invalid symbol")
        _money(initial_balance, positive=True)
        self.simulation_run_id = simulation_run_id
        self.symbol = symbol
        self.initial_balance = initial_balance
        self._fills: list[VirtualFill] = []

    @property
    def fills(self) -> tuple[VirtualFill, ...]:
        return tuple(self._fills)

    def append(self, receipt: VirtualFill) -> None:
        """Validate candidate ledger atomically before one local append."""
        if not isinstance(receipt, VirtualFill):
            raise TypeError("only explicit VirtualFill receipts are allowed")
        if (
            receipt.namespace != "SIMULATION"
            or receipt.simulation_run_id != self.simulation_run_id
            or receipt.symbol != self.symbol
        ):
            raise ValueError("receipt does not belong to this virtual account")
        if any(fill.fill_id == receipt.fill_id for fill in self._fills):
            raise ValueError("duplicate virtual fill; refusing double accounting")
        if self._fills and receipt.virtual_time_ms < self._fills[-1].virtual_time_ms:
            raise ValueError("virtual receipts must arrive chronologically")
        # A rejected fill must not change prior accounting state.
        self._project(tuple(self._fills) + (receipt,), receipt.virtual_time_ms,
                      receipt.price)
        self._fills.append(receipt)

    def snapshot(
        self, *, as_of_ms: int, mark_price: Decimal | None = None,
    ) -> VirtualAccountSnapshot:
        """Rewind from immutable fills, never mutate a running strategy/ledger."""
        if type(as_of_ms) is not int or as_of_ms < 0:
            raise ValueError("invalid virtual cursor")
        # Later market marks are allowed without a trade; the caller must
        # explicitly supply the closed-market mark when a position is open.
        active = tuple(fill for fill in self._fills
                       if fill.virtual_time_ms <= as_of_ms)
        return self._project(active, as_of_ms, mark_price)

    def _project(
        self, fills: tuple[VirtualFill, ...], as_of_ms: int,
        mark_price: Decimal | None,
    ) -> VirtualAccountSnapshot:
        balance = self.initial_balance
        position = Decimal(0)
        average: Decimal | None = None
        gross = fees = Decimal(0)

        for fill in fills:
            signed = fill.quantity if fill.side == "BUY" else -fill.quantity
            if not position or position * signed > 0:
                new_position = position + signed
                current_value = (average or Decimal(0)) * abs(position)
                average = (current_value + fill.price * fill.quantity) / abs(new_position)
                position = new_position
            else:
                closing_qty = min(abs(position), fill.quantity)
                if fill.quantity > abs(position):
                    raise ValueError("implicit position reversal is forbidden")
                direction = Decimal(1) if position > 0 else Decimal(-1)
                realized = (fill.price - average) * closing_qty * direction
                gross += realized
                balance += realized
                position += signed
                if not position:
                    average = None
            balance -= fill.fee
            fees += fill.fee
            if balance < 0:
                raise ValueError("virtual balance below zero; margin model unimplemented")

        if position:
            if mark_price is None:
                raise ValueError("explicit market mark required for open position")
            _money(mark_price, positive=True)
            unrealized = (mark_price - average) * position
        else:
            if mark_price is not None:
                _money(mark_price, positive=True)
            unrealized = Decimal(0)
        equity = balance + unrealized
        return VirtualAccountSnapshot(
            self.simulation_run_id, self.symbol, as_of_ms, self.initial_balance,
            balance, position, average, gross, fees, unrealized, equity,
            len(fills),
        )
