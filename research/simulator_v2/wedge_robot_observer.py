"""Pure SIMULATION lifecycle observer reusing the actual Wedge Robot decision code.

Uses EXACT original robot_state_machine.initialize_state/process_closed_candle
and robot_entry_limit.build_initial_retest_limit. Both are pure. The latter
produces a LIMIT *plan only*; never calls the production submitter.

The virtual exchange models GTC LIMIT, but this adapter never submits an
order without fully proven sizing, protection, order ownership and admission.
It stages lifecycle and optional risk *preview* until a common M1 commit.
"""
from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from decimal import Decimal
import hashlib
from typing import Any

from robot_state_machine import (
    EVENT_BREAKOUT, EVENT_EXPIRED_AT_APEX, EVENT_RETEST,
    PHASE_EXPIRED_AT_APEX, PHASE_RETEST_DETECTED,
    initialize_state, process_closed_candle,
)
from robot_entry_limit import InitialRetestLimitPlan, build_initial_retest_limit
from research.simulator_v2.timeline import MINUTE_MS, MinuteFrame, SimulationEvent, StageFact
from research.simulator_v2.wedge_observer import ReadOnlyWedgeScanner, WedgeObservation
from research.simulator_v2.wedge_risk_preflight import (
    FrozenWedgeRiskEvidence, SimWedgeRiskSettings,
    UnsubmittedProtectedWedgePreview, WedgePreflightBlocked,
    preview_protected_wedge_limit,
)

WEDGE_PATTERNS = frozenset({"Falling Wedge", "Rising Wedge"})


@dataclass(frozen=True)
class SimWedgeRobotConfig:
    selected_patterns: frozenset[str]
    tick_size: Decimal

    def __post_init__(self) -> None:
        if (
            not isinstance(self.selected_patterns, frozenset)
            or not self.selected_patterns
            or not self.selected_patterns <= WEDGE_PATTERNS
        ):
            raise ValueError("select one or both supported wedge patterns explicitly")
        if (
            not isinstance(self.tick_size, Decimal)
            or not self.tick_size.is_finite()
            or self.tick_size <= 0
        ):
            raise ValueError("explicit valid instrument tick_size is required")


@dataclass(frozen=True)
class SimRobotDecision:
    candidate_id: str
    symbol: str
    simulation_run_id: str
    pattern: str
    virtual_time_ms: int
    event: str
    phase: str


@dataclass(frozen=True)
class _ActiveWedge:
    candidate: dict[str, Any]
    state: dict[str, Any]
    source_candle_start_ms: int
    frozen_risk: FrozenWedgeRiskEvidence | None = None


class ReadOnlyWedgeRobot:
    """Read the Scanner's tentative closed M5 and advance the ORIGINAL Robot FSM.

    This is a read-only native-policy replay adapter, NOT a replacement for
    the production Robot coordinator, its durable admission, order ownership,
    partial-fill lifecycle, or PAPER protection. Virtual matching belongs to
    the SIMULATION exchange adapter; no alternative trading policy is allowed.

    The local selected-strategy auto-approval is explicitly SIMULATION-only;
    it does NOT call durable admission, bypass production gates, or claim that
    any actual PAPER candidate is APPROVED. That word appears only in the
    private input shape required by the existing pure Robot FSM.
    """

    def __init__(
        self, *, scanner: ReadOnlyWedgeScanner, config: SimWedgeRobotConfig,
        risk_settings: SimWedgeRiskSettings | None = None,
    ) -> None:
        if not isinstance(scanner, ReadOnlyWedgeScanner):
            raise TypeError("a read-only wedge Scanner stage is required")
        if not isinstance(config, SimWedgeRobotConfig):
            raise TypeError("explicit SIMULATION Robot configuration required")
        if risk_settings is not None and not isinstance(risk_settings, SimWedgeRiskSettings):
            raise TypeError("explicit SIMULATION risk settings required")
        if risk_settings is not None and risk_settings.tick_size != config.tick_size:
            raise ValueError("Wedge LIMIT tick and risk tick mismatch")
        self.scanner = scanner
        self.config = config
        self.risk_settings = risk_settings
        self._active: dict[str, _ActiveWedge] = {}
        self._seen: set[str] = set()
        self._decisions: list[SimRobotDecision] = []
        self._limit_plans: list[InitialRetestLimitPlan] = []
        self._risk_previews: list[UnsubmittedProtectedWedgePreview] = []
        self._pending: tuple[
            dict[str, _ActiveWedge], set[str],
            list[SimRobotDecision], list[InitialRetestLimitPlan],
            list[UnsubmittedProtectedWedgePreview],
        ] | None = None

    @property
    def decisions(self) -> tuple[SimRobotDecision, ...]:
        if self._pending is not None:
            raise RuntimeError("uncommitted SIMULATION Robot state")
        return tuple(self._decisions)

    @property
    def limit_plans(self) -> tuple[InitialRetestLimitPlan, ...]:
        """Deterministic plans, NEVER placed orders or fills."""
        if self._pending is not None:
            raise RuntimeError("uncommitted SIMULATION LIMIT plans")
        return tuple(self._limit_plans)

    @property
    def risk_previews(self) -> tuple[UnsubmittedProtectedWedgePreview, ...]:
        """Fee-aware STOP/TAKE/RR previews only, never submitted orders."""
        if self._pending is not None:
            raise RuntimeError("uncommitted SIMULATION risk preview")
        return tuple(self._risk_previews)

    @property
    def active_count(self) -> int:
        return len(self._active)

    @staticmethod
    def _id(observation: WedgeObservation) -> str:
        if not observation.formation_id:
            raise ValueError("no immutable formation identity")
        material = (
            f"{observation.simulation_run_id}\0{observation.symbol}\0"
            f"{observation.pattern}\0{observation.formation_id}"
        ).encode("utf-8")
        return "SIMWEDGE_" + hashlib.sha256(material).hexdigest()[:32]

    def observe_staged(
        self, frame: MinuteFrame, _staged: tuple[SimulationEvent, ...],
    ) -> tuple[StageFact, ...]:
        if self._pending is not None:
            raise RuntimeError("previous virtual Robot minute not committed")
        active = deepcopy(self._active)
        seen = set(self._seen)
        decisions: list[SimRobotDecision] = []
        limit_plans: list[InitialRetestLimitPlan] = []
        risk_previews: list[UnsubmittedProtectedWedgePreview] = []
        facts: list[StageFact] = []

        def record(cid: str, pattern: str, event: str, phase: str) -> None:
            decisions.append(SimRobotDecision(
                candidate_id=cid, symbol=frame.symbol,
                simulation_run_id=frame.simulation_run_id,
                pattern=pattern, virtual_time_ms=frame.virtual_time_ms,
                event=event, phase=phase,
            ))
            facts.append(StageFact(
                kind="SIM_WEDGE_" + event,
                entity_id=cid,
                details=(("pattern", pattern), ("phase", phase)),
            ))

        # Existing candidates are evaluated on THIS closed M1. A newly seen M5
        # formation below cannot see this minute's high/low or close as an
        # already-available future Robot candle: it starts NEXT M1.
        for cid, running in list(active.items()):
            candidate, state = running.candidate, running.state
            snapshot = candidate["signal_snapshot"]
            if snapshot["symbol"] != frame.symbol or (
                candidate["simulation_run_id"] != frame.simulation_run_id
            ):
                raise ValueError("cross-run Robot candidate rejected")
            delta = frame.minute.start_ms - running.source_candle_start_ms
            if delta < 0 or delta % MINUTE_MS:
                raise ValueError("Robot cursor is not a causal UTC M1 index")
            cursor = snapshot["robot_geometry"]["current_index"] + delta // MINUTE_MS
            state, event = process_closed_candle(
                snapshot, state, {
                    "timeframe": "1", "closed": True,
                    "geometry_index": cursor,
                    "high": float(frame.minute.high),
                    "low": float(frame.minute.low),
                    "close": float(frame.minute.close),
                },
            )
            pattern = snapshot["pattern"]
            if event in (EVENT_BREAKOUT, EVENT_RETEST, EVENT_EXPIRED_AT_APEX):
                record(cid, pattern, event, state["phase"])
            if event == EVENT_RETEST:
                # The existing real Wedge LIMIT planner determines entry
                # price and order direction. No submit() call is allowed.
                plan = build_initial_retest_limit(
                    candidate, state, tick_size=self.config.tick_size,
                )
                limit_plans.append(plan)
                if self.risk_settings is not None:
                    # The original Scanner evidence is bound to the same
                    # immutable formation, never reconstructed from future M1.
                    try:
                        preview = preview_protected_wedge_limit(
                            plan, evidence=running.frozen_risk,
                            settings=self.risk_settings,
                            retest_closed_at_ms=frame.virtual_time_ms,
                        )
                    except WedgePreflightBlocked as exc:
                        facts.append(StageFact(
                            kind="SIM_WEDGE_RISK_BLOCKED", entity_id=cid,
                            details=(("reason", str(exc)), ("note", "NOT_SUBMITTED")),
                        ))
                    else:
                        risk_previews.append(preview)
                        facts.append(StageFact(
                            kind="SIM_WEDGE_RISK_PREVIEW", entity_id=cid,
                            details=(
                                ("stop", str(preview.stop_price)),
                                ("take", str(preview.take_price)),
                                ("net_rr", str(preview.projected_net_rr)),
                                ("quantity", str(preview.request.quantity)),
                                ("note", "PREVIEW_ONLY_NOT_SUBMITTED"),
                            ),
                        ))
                facts.append(StageFact(
                    kind="SIM_WEDGE_LIMIT_PLANNED", entity_id=cid,
                    details=(
                        ("side", plan.request.side.value),
                        ("limit_price", str(plan.request.limit_price)),
                        ("note", "NOT_SUBMITTED"),
                    ),
                ))
            if state["phase"] in (PHASE_RETEST_DETECTED, PHASE_EXPIRED_AT_APEX):
                del active[cid]
            else:
                active[cid] = _ActiveWedge(
                    candidate, state, running.source_candle_start_ms, running.frozen_risk,
                )

        obs = self.scanner.staged_observation
        if obs is not None and obs.pattern in self.config.selected_patterns:
            if obs.symbol != frame.symbol or obs.simulation_run_id != frame.simulation_run_id:
                raise ValueError("Scanner observation crossed SIMULATION identity")
            if obs.available_at_ms != frame.virtual_time_ms or (
                obs.source_candle_start_ms + 300_000 != frame.virtual_time_ms
            ):
                raise ValueError("future or unclosed Scanner M5 observation")
            if (obs.scanner_filter_approved and obs.robot_geometry_ready
                    and obs.formation_id and obs.robot_geometry is not None):
                cid = self._id(obs)
                if cid not in seen:
                    snapshot = {
                        "symbol": obs.symbol,
                        "pattern": obs.pattern,
                        "robot_geometry": deepcopy(obs.robot_geometry),
                    }
                    candidate = {
                        "candidate_id": cid,
                        "status": "APPROVED",  # private FSM shape, SIMULATION only
                        "namespace": "SIMULATION",
                        "simulation_run_id": obs.simulation_run_id,
                        "timeframe": "1",
                        "signal_snapshot": snapshot,
                    }
                    state, event = initialize_state(candidate)
                    seen.add(cid)
                    record(cid, obs.pattern, event, state["phase"])
                    if state["phase"] != PHASE_EXPIRED_AT_APEX:
                        frozen_risk = None
                        if (obs.frozen_structural_extreme is not None
                                and obs.frozen_reference_price is not None
                                and obs.frozen_target_price is not None):
                            frozen_risk = FrozenWedgeRiskEvidence(
                                candidate_id=cid, symbol=obs.symbol, pattern=obs.pattern,
                                observed_at_ms=obs.available_at_ms,
                                structural_extreme=obs.frozen_structural_extreme,
                                frozen_signal_reference_price=obs.frozen_reference_price,
                                frozen_scanner_target_price=obs.frozen_target_price,
                            )
                        active[cid] = _ActiveWedge(
                            candidate, state, obs.source_candle_start_ms, frozen_risk,
                        )

        self._pending = active, seen, decisions, limit_plans, risk_previews
        return tuple(facts)

    def commit_after_m1(self) -> None:
        if self._pending is None:
            raise RuntimeError("missing staged Robot M1")
        active, seen, decisions, limit_plans, risk_previews = self._pending
        self._active = active
        self._seen = seen
        self._decisions.extend(decisions)
        self._limit_plans.extend(limit_plans)
        self._risk_previews.extend(risk_previews)
        self._pending = None

    def discard_failed_m1(self) -> None:
        self._pending = None
