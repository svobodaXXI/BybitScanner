"""MIRROR-INTEGRATION-2: OBSERVE_ONLY path for MIRROR RETEST candidates.

    closed candle -> naked breakout / retest (geometry.naked_retest)
                  -> available facts: frozen R0 (retest_account_risk), campaign budget
                  -> research policy (mirror_retest_robot_bridge.observe_for_robot)
                  -> decision WAIT | BLOCK with every reason
                  -> immutable observation record (idempotent journal)

Nothing here is Robot admission: every record carries ``executable=False``,
``admission_allowed=False`` and ``mode=OBSERVE_ONLY``; a research-policy ALLOW
is reported as ``WAIT robot_execution_not_authorized``. No orders, no Robot or
Scanner imports, no PAPER DB. Account facts come from the caller; until the
shared read interface (``DOCUMENTS/research/mirror_retest_r0/CONTRACT.md``)
exists they are absent and every decision is ``WAIT``.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
import hashlib
import json
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

from geometry.naked_retest import (
    EVENT_DATA_GAP,
    EVENT_NAKED_BREAKOUT,
    EVENT_RETEST_PROVEN,
    EVENT_RETEST_UNPROVEN,
    PHASE_CAMPAIGN_ACTIVE,
    PHASE_WAITING_BREAKOUT,
    Boundary,
    initialize_state,
    process_closed_candle,
)
from mirror_retest_robot_bridge import MODE_OBSERVE_ONLY, STRATEGY_ID, observe_for_robot
from retest_account_risk import DECISION_OK, freeze_r0
from retest_calibration import fine_resolver
from retest_campaign import DECISION_ALLOW, DECISION_DENY, open_campaign_budget

DECISION_WAIT = "WAIT"
DECISION_BLOCK = "BLOCK"
OBSERVED_EVENTS = frozenset({EVENT_NAKED_BREAKOUT, EVENT_RETEST_PROVEN, EVENT_RETEST_UNPROVEN, EVENT_DATA_GAP})


@dataclass(frozen=True)
class AccountFacts:
    """Account inputs of R0; ``None`` means not supplied by an authoritative source (-> WAIT)."""

    daily_gate: Mapping[str, Any] | None = None
    committed_worst_case_usdt: Sequence[Any] | None = None


@dataclass(frozen=True)
class Observation:
    observation_id: str
    strategy_id: str
    boundary_id: str
    symbol: str
    candle_close_time_ms: int
    event: str
    phase: str
    campaign_direction: str | None
    decision: str
    reasons: tuple[str, ...]
    r0_decision: str | None
    r0_usdt: float | None
    research_policy: str | None
    exit_intent: str | None
    executable: bool = False
    admission_allowed: bool = False
    mode: str = MODE_OBSERVE_ONLY
    facts: dict = field(default_factory=dict)
    # Identity and time for read-only consumers (MIRROR-OBSERVATION-PROJECTION). All optional so
    # journals written before these fields existed stay valid; none enters ``observation_id``.
    candidate_ref: str | None = None      # Robot candidate id (exact key)
    pattern: str | None = None            # e.g. "Rising Wedge"
    timeframe: str | None = None          # candle timeframe of the candidate ("5")
    account_id: str | None = None         # PAPER account scope of the candidate
    recorded_at_ms: int | None = None     # wall clock when the sidecar produced the record


GEOMETRY_TIMEFRAME_MS = 60_000   # Scanner->Robot geometry is indexed on 1m candles (robot_coordinate_timeframe "1")


def boundaries_from_candidate_snapshot(
    *, candidate_id: str, created_at_ms: int, signal_snapshot: Mapping[str, Any],
) -> tuple[Boundary, Boundary] | None:
    """Frozen upper/lower boundaries of one Scanner->Robot Wedge candidate (RETEST-4 transform).

    Uses only the immutable ``signal_snapshot`` (``robot_geometry`` lines and the
    ``scanner_geometry_cursor``); ``as_of`` is the candidate creation time, so no
    line is applied before it was known. Anything missing or not on the 1m
    geometry grid returns None (no observation, never a guessed line).
    """

    geometry = signal_snapshot.get("robot_geometry") if isinstance(signal_snapshot, Mapping) else None
    cursor = signal_snapshot.get("scanner_geometry_cursor") if isinstance(signal_snapshot, Mapping) else None
    if not isinstance(geometry, Mapping) or not isinstance(cursor, Mapping):
        return None
    if str(geometry.get("robot_coordinate_timeframe")) != "1" or str(cursor.get("timeframe")) != "1":
        return None
    try:
        index = int(cursor["geometry_index"])
        cursor_time_ms = int(cursor["source_candle_time_ms"])
        lines = {side: (float(geometry[f"{side}_line"]["slope"]), float(geometry[f"{side}_line"]["intercept"]))
                 for side in ("upper", "lower")}
        return tuple(
            Boundary(f"{candidate_id}:{side}", cursor_time_ms, slope * index + intercept,
                     slope / GEOMETRY_TIMEFRAME_MS, int(created_at_ms))
            for side, (slope, intercept) in lines.items()
        )
    except (KeyError, TypeError, ValueError):
        return None


def _observation_id(boundary_id: str, event: str, close_ms: int) -> str:
    return hashlib.sha256(f"{STRATEGY_ID}\0{boundary_id}\0{event}\0{close_ms}".encode()).hexdigest()[:32]


def decide(
    *,
    state: Mapping[str, Any],
    boundary_id: str,
    idea_potential_net_usdt: Any,
    account: AccountFacts,
) -> tuple[str, tuple[str, ...], dict]:
    """WAIT/BLOCK with reasons for one observed state; never ALLOW."""

    phase = state["phase"]
    reasons: list[str] = []
    facts: dict[str, Any] = {"data_blocked": state.get("data_blocked") is True}
    if phase == PHASE_WAITING_BREAKOUT:
        # A data gap before any breakout: no campaign exists yet, nothing to block.
        return DECISION_WAIT, ("data_unreliable", "no_campaign", "observe_only"), facts
    if phase != PHASE_CAMPAIGN_ACTIVE:
        observed = observe_for_robot(boundary_id=boundary_id, state=state)
        facts["exit_intent"] = observed.exit_intent
        return DECISION_BLOCK, ("campaign_not_active:" + phase, "observe_only"), facts

    r0 = freeze_r0(
        idea_potential_net_usdt=idea_potential_net_usdt,
        daily_gate=account.daily_gate,
        committed_worst_case_usdt=account.committed_worst_case_usdt,
    )
    facts["r0"] = {"decision": r0.decision, "reason": r0.reason, "r0_usdt": r0.r0_usdt}
    if facts["data_blocked"]:
        reasons.append("data_unreliable")
    if r0.decision != DECISION_OK:
        reasons.append(f"r0_{r0.decision.lower()}:{r0.reason}")
    budget = open_campaign_budget(r0.r0_usdt) if r0.decision == DECISION_OK else None
    # New-attempt worst case, realized costs and remaining reward come from a real
    # attempt plan and fills; none exist in observation, so the policy cannot ALLOW.
    observed = observe_for_robot(
        boundary_id=boundary_id, state=state, budget=budget,
        data_reliable=not facts["data_blocked"],
    )
    facts["research_policy"] = {"decision": observed.risk_decision, "reason": observed.risk_reason}
    reasons.append(f"policy_{observed.risk_decision.lower()}:{observed.risk_reason}")
    if observed.risk_decision == DECISION_ALLOW:
        reasons.append("robot_execution_not_authorized")
    reasons.append("observe_only")
    hard_block = r0.decision == DECISION_DENY or observed.risk_decision == DECISION_DENY
    return (DECISION_BLOCK if hard_block else DECISION_WAIT), tuple(reasons), facts


def observe_closed_candle(
    boundary: Boundary,
    state: Mapping[str, Any] | None,
    candle: Mapping[str, Any],
    *,
    symbol: str,
    idea_potential_net_usdt: Any = None,
    account: AccountFacts = AccountFacts(),
    fine_candles: Sequence[Mapping[str, Any]] | None = None,
) -> tuple[dict[str, Any], Observation | None]:
    """Advance one closed candle; return the new state and an observation for material events.

    Retest contact is physical (tolerance 0): RETEST-5 found no ATR zone that passes
    its train gate, so no tolerance parameter is introduced here.
    """

    if state is None:
        state, _ = initialize_state(boundary)
    resolver = None
    if fine_candles is not None and state.get("breakout"):
        resolver = fine_resolver(boundary, state["breakout"]["direction"], fine_candles)
    new_state, event = process_closed_candle(boundary, state, candle, ambiguity_resolver=resolver)
    if event not in OBSERVED_EVENTS:
        return new_state, None
    decision, reasons, facts = decide(
        state=new_state, boundary_id=boundary.boundary_id,
        idea_potential_net_usdt=idea_potential_net_usdt, account=account,
    )
    breakout = new_state.get("breakout") or {}
    record = Observation(
        observation_id=_observation_id(boundary.boundary_id, event, int(candle["close_time_ms"])),
        strategy_id=STRATEGY_ID,
        boundary_id=boundary.boundary_id,
        symbol=symbol,
        candle_close_time_ms=int(candle["close_time_ms"]),
        event=event,
        phase=new_state["phase"],
        campaign_direction=breakout.get("campaign_direction"),
        decision=decision,
        reasons=reasons,
        r0_decision=(facts.get("r0") or {}).get("decision"),
        r0_usdt=(facts.get("r0") or {}).get("r0_usdt"),
        research_policy=(facts.get("research_policy") or {}).get("decision"),
        exit_intent=facts.get("exit_intent"),
        facts=facts,
    )
    return new_state, record


def observe_history(
    boundary: Boundary,
    candles: Iterable[Mapping[str, Any]],
    *,
    symbol: str,
    idea_potential_net_usdt: Any = None,
    account: AccountFacts = AccountFacts(),
    fine_candles: Sequence[Mapping[str, Any]] | None = None,
) -> tuple[dict[str, Any], list[Observation]]:
    """Replay closed candles in order (historical cases) and collect observations."""

    state: dict[str, Any] | None = None
    records: list[Observation] = []
    for candle in candles:
        state, record = observe_closed_candle(
            boundary, state, candle, symbol=symbol, idea_potential_net_usdt=idea_potential_net_usdt,
            account=account, fine_candles=fine_candles,
        )
        if record is not None:
            records.append(record)
        if state["phase"] not in (PHASE_WAITING_BREAKOUT, PHASE_CAMPAIGN_ACTIVE):
            break
    if state is None:
        state, _ = initialize_state(boundary)
    return state, records


class ObservationJournal:
    """Append-only JSONL journal of observations; idempotent by ``observation_id``.

    A research file, not a Robot/PAPER store: the shared durable sink is part of the
    contract still to be agreed.
    """

    def __init__(self, path: Path) -> None:
        self.path = Path(path)
        self._seen: set[str] = set()
        if self.path.exists():
            for line in self.path.read_text(encoding="utf-8").splitlines():
                if line.strip():
                    self._seen.add(json.loads(line)["observation_id"])

    def append(self, records: Iterable[Observation]) -> int:
        new = [record for record in records if record.observation_id not in self._seen]
        if not new:
            return 0
        for record in new:
            if record.executable or record.admission_allowed or record.mode != MODE_OBSERVE_ONLY:
                raise ValueError("only OBSERVE_ONLY, non-executable records may be journaled")
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8") as handle:
            for record in new:
                handle.write(json.dumps(asdict(record), sort_keys=True, default=str) + "\n")
                self._seen.add(record.observation_id)
        return len(new)
