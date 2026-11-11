"""Read-only ORIGINAL confirmed Ikigai Box detector on SIMULATION closed M5.

No WATCH signals, PAPER planning, Robot admission, or executable orders.
Scanner observations publish only after the shared M1 step commits.
"""
from __future__ import annotations

from dataclasses import dataclass
import pandas as pd

from geometry.ikigai_box import IkigaiBoxFormation, detect_ikigai_box
from research.historical_market_replay import Candle
from research.simulator_v2.timeline import MinuteFrame, SimulationEvent, StageFact

M5 = 300_000


@dataclass(frozen=True)
class IkigaiScannerConfig:
    window_bars: int = 300

    def __post_init__(self):
        if type(self.window_bars) is not int or not 50 <= self.window_bars <= 5000:
            raise ValueError("Ikigai M5 window must contain 50..5000 bars")


@dataclass(frozen=True)
class IkigaiObservation:
    simulation_run_id: str
    symbol: str
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
        self._bars: tuple[Candle, ...] = ()
        self._pending: tuple[tuple[Candle, ...], IkigaiObservation | None] | None = None
        self._identity: tuple[str, str] | None = None
        self._seen: set[str] = set()
        self._observations: list[IkigaiObservation] = []

    @property
    def observations(self) -> tuple[IkigaiObservation, ...]:
        if self._pending is not None:
            raise RuntimeError("uncommitted Ikigai observation")
        return tuple(self._observations)

    @property
    def staged_observation(self) -> IkigaiObservation | None:
        return self._pending[1] if self._pending else None

    def observe_staged(
        self, frame: MinuteFrame, _events: tuple[SimulationEvent, ...],
    ) -> tuple[StageFact, ...]:
        if self._pending is not None:
            raise RuntimeError("previous Ikigai M5 not committed")
        bar = frame.newly_closed_5m
        if bar is None:
            return ()
        if bar.interval_ms != M5 or bar.start_ms % M5 or bar.end_ms != frame.virtual_time_ms:
            raise ValueError("Ikigai requires completed UTC M5")
        identity = frame.simulation_run_id, frame.symbol
        if self._identity is not None and identity != self._identity:
            raise ValueError("cross-run Ikigai Scanner reuse")
        if self._bars and self._bars[-1].end_ms != bar.start_ms:
            raise ValueError("gap in Ikigai M5")
        bars = (self._bars + (bar,))[-self.config.window_bars:]
        observed = None
        if len(bars) >= 32:
            frame_data = pd.DataFrame((
                dict(open=float(b.open), high=float(b.high),
                     low=float(b.low), close=float(b.close))
                for b in bars
            ))
            formation = detect_ikigai_box(frame_data)
            if formation is not None:
                a = bars[formation.anchor_start_index].start_ms
                b = bars[formation.anchor_end_index].start_ms
                fid = f"{formation.direction}:{a}:{b}"
                if fid not in self._seen:
                    observed = IkigaiObservation(
                        frame.simulation_run_id, frame.symbol,
                        frame.virtual_time_ms, fid, formation, a, b,
                    )
        self._pending = bars, observed
        return ()  # No false approved Robot candidate from mere observation.

    def commit_after_m1(self, frame: MinuteFrame) -> None:
        if self._pending is None:
            return
        bars, observed = self._pending
        identity = frame.simulation_run_id, frame.symbol
        if self._identity is not None and self._identity != identity:
            raise ValueError("cross-run Ikigai commit")
        if bars[-1].end_ms != frame.virtual_time_ms:
            raise ValueError("Ikigai observation not at committed M5 close")
        self._identity = identity
        self._bars = bars
        if observed is not None:
            self._seen.add(observed.formation_id)
            self._observations.append(observed)
        self._pending = None

    def discard_failed_m1(self) -> None:
        self._pending = None
