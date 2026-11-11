"""Original confirmed Ikigai Box Scanner on closed M1 and M5 in SIMULATION.

A single detector is reused at both timeframes. The original formation
identity is scoped by run + symbol + source timeframe + original A/B.
No WATCH, order submission, Robot approval, or PAPER access.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

import pandas as pd

from geometry.ikigai_box import IkigaiBoxFormation, detect_ikigai_box
from research.historical_market_replay import Candle
from research.simulator_v2.timeline import MinuteFrame, SimulationEvent, StageFact

M1 = 60_000
M5 = 300_000
TF_MS = {"1m": M1, "5m": M5}
BoxTimeframe = Literal["1m", "5m"]


@dataclass(frozen=True)
class IkigaiScannerConfig:
    window_bars: int = 300
    timeframes: tuple[BoxTimeframe, ...] = ("1m", "5m")

    def __post_init__(self):
        if type(self.window_bars) is not int or not 50 <= self.window_bars <= 5000:
            raise ValueError("Ikigai lookback must contain 50..5000 candles")
        if (not isinstance(self.timeframes, tuple) or not self.timeframes
                or len(set(self.timeframes)) != len(self.timeframes)
                or any(tf not in TF_MS for tf in self.timeframes)):
            raise ValueError("Ikigai requires unique supported 1m/5m timeframes")


@dataclass(frozen=True)
class IkigaiObservation:
    simulation_run_id: str
    symbol: str
    timeframe: BoxTimeframe
    available_at_ms: int
    formation_id: str
    formation: IkigaiBoxFormation
    source_a_ms: int
    source_b_ms: int


class ReadOnlyIkigaiScanner:
    def __init__(self, config: IkigaiScannerConfig):
        if not isinstance(config, IkigaiScannerConfig):
            raise TypeError("explicit Ikigai config required")
        self.config = config
        self._bars: dict[str, tuple[Candle, ...]] = {
            tf: () for tf in config.timeframes
        }
        self._pending: dict[str, tuple[tuple[Candle, ...], IkigaiObservation | None]] = {}
        self._identity: tuple[str, str] | None = None
        self._seen: set[tuple[str, str]] = set()
        self._observations: list[IkigaiObservation] = []

    @property
    def observations(self) -> tuple[IkigaiObservation, ...]:
        if self._pending:
            raise RuntimeError("uncommitted Ikigai observations")
        return tuple(self._observations)

    @property
    def staged_observation(self) -> IkigaiObservation | None:
        candidates = [entry[1] for entry in self._pending.values()
                      if entry[1] is not None]
        return candidates[0] if len(candidates) == 1 else None

    def observe_staged(
        self, frame: MinuteFrame, _events: tuple[SimulationEvent, ...],
    ) -> tuple[StageFact, ...]:
        if self._pending:
            raise RuntimeError("previous Ikigai step uncommitted")
        identity = frame.simulation_run_id, frame.symbol
        if self._identity is not None and self._identity != identity:
            raise ValueError("cross-run Ikigai Scanner reuse")
        pending: dict[str, tuple[tuple[Candle, ...], IkigaiObservation | None]] = {}
        for tf in self.config.timeframes:
            bar = frame.minute if tf == "1m" else frame.newly_closed_5m
            if bar is None:
                continue
            interval = TF_MS[tf]
            if (bar.interval_ms != interval or bar.start_ms % interval
                    or bar.end_ms != frame.virtual_time_ms):
                raise ValueError("Ikigai requires a completed UTC " + tf)
            prior = self._bars[tf]
            if prior and prior[-1].end_ms != bar.start_ms:
                raise ValueError("gap in Ikigai " + tf)
            bars = (prior + (bar,))[-self.config.window_bars:]
            observed = None
            if len(bars) >= 32:
                closed = pd.DataFrame((
                    dict(open=float(c.open), high=float(c.high),
                         low=float(c.low), close=float(c.close))
                    for c in bars
                ))
                # ORIGINAL detector. No recalc on any future candle.
                formation = detect_ikigai_box(closed)
                if formation is not None:
                    a = bars[formation.anchor_start_index].start_ms
                    b = bars[formation.anchor_end_index].start_ms
                    fid = f"{tf}:{formation.direction}:{a}:{b}"
                    if (tf, fid) not in self._seen:
                        observed = IkigaiObservation(
                            frame.simulation_run_id, frame.symbol, tf,
                            frame.virtual_time_ms, fid, formation, a, b,
                        )
            pending[tf] = (bars, observed)
        self._pending = pending
        return ()  # Observations are NOT admission or trades.

    def commit_after_m1(self, frame: MinuteFrame) -> None:
        if not self._pending:
            return
        identity = frame.simulation_run_id, frame.symbol
        if self._identity is not None and self._identity != identity:
            raise ValueError("cross-run Ikigai commit")
        for tf, (bars, observed) in self._pending.items():
            if bars[-1].end_ms != frame.virtual_time_ms:
                raise ValueError("uncommitted " + tf + " Box signal")
            self._bars[tf] = bars
            if observed is not None:
                self._seen.add((tf, observed.formation_id))
                self._observations.append(observed)
        self._identity = identity
        self._pending = {}

    def discard_failed_m1(self) -> None:
        self._pending = {}
