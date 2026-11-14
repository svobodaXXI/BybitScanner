"""Optional read-only reuse of the EXISTING H-017 causal H1/M5 geometry.

This uses research.causal_trend_geometry.CausalGeometryFeed unchanged; it
does not reimplement detection or infer Scanner/Robot trading decisions.

The observer stages a COPY of its state before the virtual exchange stage.
It publishes the geometry projection only AFTER the complete M1 is committed.
A rejected virtual fill discards the staged geometry update, allowing retry
of exactly the same bar without duplicate pivots or future leakage.

This is a research projection, not production Scanner provenance. It emits
NO SCANNER/ROBOT journal facts, requests, or trading side effects.
"""
from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from decimal import Decimal

from research.causal_trend_geometry import CausalGeometryFeed, CausalLine, TrendCandidate
from research.simulator_v2.timeline import MinuteFrame, SimulationEvent, StageFact


@dataclass(frozen=True)
class ReusedGeometrySnapshot:
    """Geometry truly available after the indicated CLOSED historical M5."""

    virtual_time_ms: int
    h1_trend: TrendCandidate | None
    m5_correction: CausalLine | None
    confirmed_hourly_prior: Decimal | None
    confirmed_prior_break: tuple[tuple[str, str], ...]


class ReadOnlyReusedGeometry:
    """Single-writer staged projection; never an order/strategy producer."""

    def __init__(self) -> None:
        self._committed = CausalGeometryFeed()
        self._snapshots: list[ReusedGeometrySnapshot] = []
        self._pending: tuple[CausalGeometryFeed, ReusedGeometrySnapshot] | None = None

    @property
    def snapshots(self) -> tuple[ReusedGeometrySnapshot, ...]:
        return tuple(self._snapshots)

    def projection_at(self, virtual_time_ms: int) -> ReusedGeometrySnapshot | None:
        """Read-only rewind; does not mutate the authoritative geometry feed."""
        if type(virtual_time_ms) is not int or virtual_time_ms < 0:
            raise ValueError("invalid virtual projection cursor")
        if self._pending is not None:
            raise RuntimeError("cannot project an uncommitted geometry minute")
        return next(
            (item for item in reversed(self._snapshots)
             if item.virtual_time_ms <= virtual_time_ms),
            None,
        )

    def observe_staged(
        self, frame: MinuteFrame, _staged: tuple[SimulationEvent, ...],
    ) -> tuple[StageFact, ...]:
        """Pure relative to committed geometry; no production Scanner events."""
        if self._pending is not None:
            raise RuntimeError("uncommitted geometry state from previous M1")
        if frame.newly_closed_5m is None:
            return ()
        staged = deepcopy(self._committed)
        trend, correction = staged.observe_closed(
            frame.newly_closed_5m, frame.newly_closed_1h,
        )
        prior_break = staged.confirmed_hourly_prior_break
        snapshot = ReusedGeometrySnapshot(
            virtual_time_ms=frame.virtual_time_ms,
            h1_trend=trend, m5_correction=correction,
            confirmed_hourly_prior=staged.confirmed_hourly_prior,
            confirmed_prior_break=tuple(
                sorted((str(k), str(v)) for k, v in prior_break.items())
            ) if prior_break is not None else (),
        )
        if (
            (trend is not None and trend.available_at_ms > frame.virtual_time_ms)
            or (correction is not None and correction.available_at_ms > frame.virtual_time_ms)
        ):
            raise ValueError("research geometry attempted future exposure")
        self._pending = (staged, snapshot)
        return ()  # Never mislabel research geometry as a real Scanner fact.

    def commit_after_m1(self) -> None:
        """Called only after IsolatedTimeline and VirtualExchange both succeed."""
        if self._pending is not None:
            self._committed, snapshot = self._pending
            self._snapshots.append(snapshot)
            self._pending = None

    def discard_failed_m1(self) -> None:
        """Keep previous geometry intact when the virtual minute is blocked."""
        self._pending = None
