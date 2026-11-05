"""H-017 ONLY: fixed-capital, 20-slot, offline research risk proposal.

This module never calls exchange/account APIs, creates orders, or writes PAPER.
Geometry/entry timing comes from the owner's separate strategy definitions.
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation

from typing import Callable, Sequence

from research.historical_market_replay import (
    Candle, ClosedBarView, EntryIntent, ReplayResult, ReplayVisualEvent, Side,
    replay_candles,
)


def _positive(value: object, label: str) -> Decimal:
    try:
        number = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise ValueError(f"invalid {label}") from exc
    if not number.is_finite() or number <= 0:
        raise ValueError(f"invalid {label}")
    return number


@dataclass(frozen=True)
class H017LocalRiskPolicy:
    """200 USDT, 20 independent 10-USDT budget slots, no leverage.

    Stop distances refer to *entry price*, not to account equity. The optional
    structural stop is ONE KNOWN price tick beyond an already-known extremum.
    Missing/invalid geometry falls back to exactly 0.7%, never an invented tick.
    """

    initial_cash: Decimal = Decimal("200")
    max_open_positions: int = 20
    max_stop_fraction: Decimal = Decimal("0.007")
    minimum_reward_risk: Decimal = Decimal("1")

    def __post_init__(self) -> None:
        object.__setattr__(self, "initial_cash", _positive(self.initial_cash, "initial_cash"))
        object.__setattr__(self, "max_stop_fraction", _positive(self.max_stop_fraction, "max_stop_fraction"))
        object.__setattr__(self, "minimum_reward_risk", _positive(self.minimum_reward_risk, "minimum_reward_risk"))
        if type(self.max_open_positions) is not int or self.max_open_positions <= 0:
            raise ValueError("invalid slot count")
        if self.max_stop_fraction >= 1:
            raise ValueError("stop fraction cannot be 100% or more")

    @property
    def slot_budget(self) -> Decimal:
        return self.initial_cash / Decimal(self.max_open_positions)

    def proposal(
        self, *, side: Side, expected_entry: object, target: object,
        confirmed_extreme: object | None = None,
        tick_size: object | None = None,
    ) -> EntryIntent | None:
        """Candidate only. Not an authorization to trade or a candle trigger.

        `target` is the already-known structural price objective from H-017;
        absent/invalid objectives must not be replaced with synthetic TAKEs.
        Quantities are decimal *upper bounds* for next-open sizing in the replay.
        """
        if side not in ("LONG", "SHORT"):
            raise ValueError("invalid side")
        entry = _positive(expected_entry, "entry")
        take = _positive(target, "target")
        stop = entry * (1 - self.max_stop_fraction if side == "LONG"
                        else 1 + self.max_stop_fraction)
        if confirmed_extreme is not None and tick_size is not None:
            extreme = _positive(confirmed_extreme, "confirmed_extreme")
            tick = _positive(tick_size, "tick_size")
            structural = extreme - tick if side == "LONG" else extreme + tick
            if structural > 0:
                distance = ((entry - structural) / entry if side == "LONG"
                            else (structural - entry) / entry)
                # Strictly less than 0.7%: at exactly 0.7%, use the fixed stop.
                if Decimal(0) < distance < self.max_stop_fraction:
                    stop = structural
        risk = entry - stop if side == "LONG" else stop - entry
        reward = take - entry if side == "LONG" else entry - take
        if risk <= 0 or reward < self.minimum_reward_risk * risk:
            return None
        return EntryIntent(
            side=side, quantity=self.slot_budget / entry,
            stop=stop, take=take,
        )

    def replay(
        self, *, simulation_run_id: str, candles: Sequence[Candle],
        on_closed_bar: Callable[[ClosedBarView], EntryIntent | None],
        taker_fee_rate: Decimal = Decimal("0.0006"),
        adverse_slippage_rate: Decimal = Decimal("0"),
        on_visual_event: Callable[[ReplayVisualEvent], None] | None = None,
    ) -> ReplayResult:
        """Activate the H-017 risk policy only for a local SIMULATION run.

        The external strategy must provide its approved geometry/entry timing;
        this wrapper adds NO signal rules and never touches real accounts.
        """
        return replay_candles(
            simulation_run_id=simulation_run_id, candles=candles,
            on_closed_bar=on_closed_bar, initial_cash=self.initial_cash,
            taker_fee_rate=taker_fee_rate,
            adverse_slippage_rate=adverse_slippage_rate,
            on_visual_event=on_visual_event,
            max_open_positions=self.max_open_positions,
            position_slot_budget=self.slot_budget,
            minimum_reward_risk=self.minimum_reward_risk,
            maximum_stop_fraction=self.max_stop_fraction,
        )
