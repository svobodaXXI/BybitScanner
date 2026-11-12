"""Native CLOSED-candle Scanner candidate bridge for frozen-level strategies.

Use geometry.l_shape and geometry.double_extremum, not rewritten detectors.
Never import production Scanner runtime, send Telegram, create candidates in
PAPER, or read any candle beyond the committed one-run virtual M1 frontier.
Only hand back exact original immutable snapshots; Robot/VirtualExchange
decide the next stage separately.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json

from geometry.double_extremum import frozen_neckline_snapshot
from research.historical_market_replay import Candle
from research.simulator_v2.timeline import MinuteFrame
from terminal.application.robot_admission import scanner_candidate_admission_error


_NATIVE_LEVEL_IDS = frozenset({"L_SHAPE", "DOUBLE_TOP", "DOUBLE_BOTTOM"})


@dataclass(frozen=True)
class FrozenLevelObservation:
    candidate_id: str
    pattern: str
    available_at_ms: int
    source_timeframe: str
    candidate: dict[str, object]


class NativeFrozenLevelScanner:
    """One symbol / one run / original 1m+5m Scanner detectors.

    The 5m source comes from IsolatedTimeline.newly_closed_5m; never locally
    resample 1m or allow a partial bar. The bounded history is exclusively
    causal and retained per original source timeframe.
    """

    def __init__(
        self, *, symbol: str, simulation_run_id: str,
        selected: frozenset[str], window_bars: int,
    ):
        if (not isinstance(selected, frozenset) or not selected
                or not selected <= _NATIVE_LEVEL_IDS):
            raise ValueError("only selected native frozen-level strategy IDs allowed")
        if type(window_bars) is not int or not 50 <= window_bars <= 5000:
            raise ValueError("verified local Scanner lookback must be 50..5000")
        if not isinstance(symbol, str) or not symbol.endswith("USDT"):
            raise ValueError("native local Scanner needs a single USDT symbol")
        if not isinstance(simulation_run_id, str) or not simulation_run_id:
            raise ValueError("native local Scanner needs explicit run identity")
        self.symbol = symbol
        self.simulation_run_id = simulation_run_id
        self.selected = selected
        self.window_bars = window_bars
        self._history: dict[str, list[Candle]] = {"1": [], "5": []}
        self._seen: set[str] = set()
        self._last_minute_close: int | None = None
        self._observations: list[FrozenLevelObservation] = []

    @property
    def observations(self) -> tuple[FrozenLevelObservation, ...]:
        return tuple(self._observations)

    @staticmethod
    def _rows(bars: list[Candle]) -> list[dict[str, object]]:
        return [
            dict(time=bar.start_ms, open=float(bar.open), high=float(bar.high),
                 low=float(bar.low), close=float(bar.close),
                 volume=float(bar.volume))
            for bar in bars
        ]

    def observe_closed(self, frame: MinuteFrame) -> tuple[FrozenLevelObservation, ...]:
        if (not isinstance(frame, MinuteFrame)
                or frame.symbol != self.symbol
                or frame.simulation_run_id != self.simulation_run_id
                or frame.minute.interval_ms != 60_000
                or frame.minute.end_ms != frame.virtual_time_ms
                or (self._last_minute_close is not None
                    and frame.minute.start_ms != self._last_minute_close)):
            raise ValueError("native level Scanner requires next committed M1 of same run")
        # Validate BOTH sources before changing the observer's minute cursor.
        sources = [("1", frame.minute)]
        if frame.newly_closed_5m is not None:
            bar = frame.newly_closed_5m
            if (bar.interval_ms != 300_000 or bar.start_ms % 300_000
                    or bar.end_ms != frame.virtual_time_ms):
                raise ValueError("only verified fully closed UTC M5 can enter native Scanner")
            sources.append(("5", bar))
        for tf, bar in sources:
            prior = self._history[tf]
            if prior and prior[-1].end_ms != bar.start_ms:
                raise ValueError("gap or overlap in native Scanner source timeframe")
        self._last_minute_close = frame.virtual_time_ms
        observations: list[FrozenLevelObservation] = []
        for tf, bar in sources:
            prior = self._history[tf]
            if prior and prior[-1].end_ms != bar.start_ms:
                raise ValueError("gap or overlap in native Scanner source timeframe")
            prior.append(bar)
            if len(prior) > self.window_bars:
                del prior[:-self.window_bars]
            if len(prior) < 9:
                continue
            rows = self._rows(prior)
            snapshots: list[dict[str, object]] = []
            if "L_SHAPE" in self.selected and len(prior) >= 32:
                # Original geometry, eligibility and Scanner handoff formatting;
                # do not invoke rendering, notification or production persistence.
                import pandas as pd
                from geometry.l_shape import detect_l_shape, l_shape_signal_plan
                from l_shape_scanner import _robot_signal_snapshot
                formation = detect_l_shape(pd.DataFrame(rows))
                if formation is not None:
                    plan = l_shape_signal_plan(formation)
                    if plan.eligible:
                        snapshots.append(_robot_signal_snapshot(
                            self.symbol, tf, {
                                "formation": formation,
                                "signal_plan": plan,
                                "extreme_time_ms": prior[formation.extreme_index].start_ms,
                                "source_candle_time_ms": bar.start_ms,
                            },
                        ))
            if "DOUBLE_TOP" in self.selected or "DOUBLE_BOTTOM" in self.selected:
                frozen = frozen_neckline_snapshot(self.symbol, tf, rows)
                if frozen is not None and (
                    (frozen["pattern"] == "Double Top" and "DOUBLE_TOP" in self.selected)
                    or (frozen["pattern"] == "Double Bottom" and "DOUBLE_BOTTOM" in self.selected)
                ):
                    snapshots.append(frozen)
            for snapshot in snapshots:
                # Deterministic run-local identity; a repeated Scanner view of the
                # same ORIGINAL immutable signal can never submit a second order.
                digest = hashlib.sha256(json.dumps(
                    snapshot, sort_keys=True, separators=(",", ":"), default=str,
                ).encode("utf-8")).hexdigest()[:32]
                candidate_id = "simlevel_" + digest
                if candidate_id in self._seen:
                    continue
                candidate = dict(
                    candidate_id=candidate_id, status="APPROVED",
                    symbol=self.symbol, timeframe=tf,
                    signal_snapshot=snapshot,
                )
                rejection = scanner_candidate_admission_error(candidate)
                if rejection is not None:
                    # Same production pure gate as the actual owner Admission.
                    continue
                observation = FrozenLevelObservation(
                    candidate_id=candidate_id,
                    pattern=str(snapshot["pattern"]),
                    available_at_ms=bar.end_ms,
                    source_timeframe=tf,
                    candidate=candidate,
                )
                self._seen.add(candidate_id)
                self._observations.append(observation)
                observations.append(observation)
        return tuple(observations)
