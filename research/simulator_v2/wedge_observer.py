"""Read-only reuse of the actual Scanner wedge computations on virtual CLOSED M5.

No Scanner process, config import, Bybit client, file writes, Telegram,
Robot candidate persistence, account reads or order calls. The existing
pivots -> wedge -> confirmation -> scoring -> quality -> filter functions
own ALL pattern mathematics and thresholds. Caller supplies Scanner settings;
they are never silently taken from live runtime configuration.

Observations are research projections, NOT persisted APPROVED Robot candidates.
Each M5 update is staged until the parent SIMULATION minute commits.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from research.historical_market_replay import Candle
from research.simulator_v2.timeline import MinuteFrame, SimulationEvent, StageFact


@dataclass(frozen=True)
class WedgeScannerConfig:
    """Exact parameters required to reproduce one Scanner observation window."""

    window_bars: int
    mode: str
    min_score: float

    def __post_init__(self) -> None:
        if type(self.window_bars) is not int or not 50 <= self.window_bars <= 5000:
            raise ValueError("explicit Scanner lookback must be between 50 and 5000 M5")
        if self.mode not in ("hunter", "sniper"):
            raise ValueError("explicit Scanner hunter/sniper mode required")
        if (isinstance(self.min_score, bool)
                or not isinstance(self.min_score, (int, float))
                or not 0 <= self.min_score <= 100):
            raise ValueError("explicit finite Scanner minimum score required")


@dataclass(frozen=True)
class WedgeObservation:
    """One observed wedge on exact closed M5. NOT a Robot order/admission."""

    simulation_run_id: str
    symbol: str
    source_candle_start_ms: int
    available_at_ms: int
    pattern: str
    formation_id: str | None
    final_score: float
    quality: str
    scanner_filter_approved: bool
    scanner_filter_reason: str
    robot_geometry_ready: bool
    # The original frozen projection can be passed to a FUTURE isolated
    # admission adapter; no admission or lifecycle happens in this observer.
    robot_geometry: dict[str, Any] | None


class ReadOnlyWedgeScanner:
    """Actual wedge analysis; strictly read-only and transactional per virtual M1."""

    def __init__(self, config: WedgeScannerConfig) -> None:
        if not isinstance(config, WedgeScannerConfig):
            raise TypeError("explicit wedge Scanner configuration required")
        self.config = config
        self._committed_bars: tuple[Candle, ...] = ()
        self._observations: list[WedgeObservation] = []
        self._pending: tuple[tuple[Candle, ...], WedgeObservation | None] | None = None
        self._identity: tuple[str, str] | None = None

    @property
    def observations(self) -> tuple[WedgeObservation, ...]:
        if self._pending is not None:
            raise RuntimeError("wedge observation is uncommitted")
        return tuple(self._observations)

    @property
    def closed_m5_count(self) -> int:
        return self._closed_count

    _closed_count: int = 0

    def observations_at(self, virtual_time_ms: int) -> tuple[WedgeObservation, ...]:
        if type(virtual_time_ms) is not int or virtual_time_ms < 0:
            raise ValueError("invalid virtual time")
        return tuple(item for item in self.observations
                     if item.available_at_ms <= virtual_time_ms)

    def _evaluate(
        self, *, frame: MinuteFrame, bars: tuple[Candle, ...],
    ) -> WedgeObservation | None:
        """The same pure computational functions used by analyzer.core."""
        import pandas as pd

        from pivots import find_pivots
        from wedge import analyze_wedge
        from confirmation import confirm_signal
        from analyzer.scoring import calculate_final_score
        from signal.quality import evaluate_quality
        from signal.filter import evaluate_signal
        from scanner_geometry_cursor import (
            ScannerGeometryCursorError, project_frozen_geometry_to_robot_1m,
        )

        df = pd.DataFrame([{
            "time": candle.start_ms,
            "open": float(candle.open),
            "high": float(candle.high),
            "low": float(candle.low),
            "close": float(candle.close),
            "volume": float(candle.volume),
        } for candle in bars])
        highs, lows = find_pivots(df)
        if len(highs) < 3 or len(lows) < 3:
            return None
        result = analyze_wedge(
            highs, lows, current_index=len(df) - 1, candles=df,
        )
        if result is None or result.get("pattern") not in (
            "Falling Wedge", "Rising Wedge",
        ):
            return None

        confirmation = confirm_signal(df, result)
        if confirmation is None:
            raise ValueError("wedge confirmation unexpectedly unavailable")
        score = calculate_final_score(result, confirmation)
        quality = evaluate_quality(
            result.get("pattern"), result.get("geometry"), confirmation, score,
            containment_violations=(
                (result.get("detection") or {}).get("features", {})
                .get("containment_violations")
            ),
        )
        decision = evaluate_signal(
            quality, score, confirmation,
            mode=self.config.mode, min_score=self.config.min_score,
        )
        geometry = result.get("geometry")
        formation_id: str | None = None
        robot_geometry: dict[str, Any] | None = None
        if isinstance(geometry, dict):
            try:
                upper = int(geometry["upper_line"]["anchor_index"])
                lower = int(geometry["lower_line"]["anchor_index"])
                if 0 <= upper < len(bars) and 0 <= lower < len(bars):
                    formation_id = (
                        f"{bars[upper].start_ms}:{bars[lower].start_ms}"
                    )
            except (KeyError, ValueError, TypeError, OverflowError):
                pass
            try:
                robot_geometry = project_frozen_geometry_to_robot_1m(
                    geometry, source_timeframe="5",
                )
            except (ScannerGeometryCursorError, KeyError, TypeError, ValueError, OverflowError):
                robot_geometry = None

        return WedgeObservation(
            simulation_run_id=frame.simulation_run_id,
            symbol=frame.symbol,
            source_candle_start_ms=bars[-1].start_ms,
            available_at_ms=frame.virtual_time_ms,
            pattern=result["pattern"],
            formation_id=formation_id,
            final_score=float(score),
            quality=str(quality.get("quality", "Invalid")),
            scanner_filter_approved=decision.get("approved") is True,
            scanner_filter_reason=str(decision.get("reason", "")),
            robot_geometry_ready=robot_geometry is not None and formation_id is not None,
            robot_geometry=robot_geometry,
        )

    def observe_staged(
        self, frame: MinuteFrame, _staged: tuple[SimulationEvent, ...],
    ) -> tuple[StageFact, ...]:
        if self._pending is not None:
            raise RuntimeError("previous wedge M5 has not committed")
        if frame.newly_closed_5m is None:
            return ()
        new = frame.newly_closed_5m
        if (new.end_ms != frame.virtual_time_ms or new.interval_ms != 300_000
                or new.start_ms % 300_000):
            raise ValueError("wedge observer requires an exact CLOSED UTC M5")
        identity = (frame.simulation_run_id, frame.symbol)
        if self._identity is not None and self._identity != identity:
            raise ValueError("wedge observer cannot mix symbols or runs")
        if self._committed_bars and new.start_ms != self._committed_bars[-1].end_ms:
            raise ValueError("gap in wedge history")
        bars = (self._committed_bars + (new,))[-self.config.window_bars:]
        observation = (
            self._evaluate(frame=frame, bars=bars) if len(bars) >= 50 else None
        )
        self._pending = bars, observation
        return ()  # Research facts are NOT disguised as production SCANNER events.

    def commit_after_m1(self, frame: MinuteFrame) -> None:
        if self._pending is not None:
            bars, observation = self._pending
            identity = (frame.simulation_run_id, frame.symbol)
            if self._identity is not None and self._identity != identity:
                raise ValueError("wedge commit identity changed")
            self._identity = identity
            self._committed_bars = bars
            self._closed_count += 1
            if observation is not None:
                self._observations.append(observation)
            self._pending = None

    def discard_failed_m1(self) -> None:
        self._pending = None
