"""MIRROR RETEST trading overlay for the existing PAPER Robot (IKIGAI_BOX entries). OFF by default.

MIRROR is not a second execution engine. It only decides, for an existing Robot Box attempt, whether the attempt belongs
to an active MIRROR RETEST campaign and, if so, how the *existing* Box exit machinery is parameterised:

* owner rules (``DOCUMENTS/RETEST_BOX_CHAIN_IMPLEMENTATION_PLAN.md`` §2/§2a/§5): an attempt is a Box entry in the campaign
  direction (back toward a naked-broken Wedge boundary) while the campaign is active; 25 % of each filled slot exits at the
  standard Box TAKE (an ordinary Box-owned EXIT LIMIT, smaller quantity); after that partial TAKE the remainder STOP moves
  to the whole-trade net break-even (``retest_campaign.net_break_even_remainder_stop``, only tighter, protection kept);
  the remainder is closed by an ordinary Box-owned EXIT MARKET (slot 0, the existing emergency/manual close mechanism)
  at the first proven retest; risk of all attempts is bounded by the campaign ``R0`` (``retest_campaign.entry_gate``),
  which is frozen at the first attempt and never restored by profit. No reversal, no new entry signal is created here.
* Admission, ownership, fills, STOP protection, Net PnL and recovery stay with the existing Robot/Box code.
* Every behaviour change is derived from the candidate's durable ``robot_state.execution["mirror"]``; the policy object
  (network candles, account risk) is only needed to attach a campaign and to advance the retest.

Campaign sources: the frozen boundaries of the symbol's Wedge Robot candidates and the live Scanner MIRROR candidates
(``mirror_scanner``: fresh, confident naked breakout of a still untested level of any source -- Wedge / Triangle,
HORN, L-shape, Ikigai Box, swing zone). Either way the Robot replays the boundary itself on closed 5m candles; a Scanner
candidate only names the level and must agree with that replay (direction; same breakout candle on 5m).

Enable: ``BYBITSCANNER_MIRROR_RETEST_ROBOT=1`` (anything else = off, the Box Robot is unchanged).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import ROUND_FLOOR, Decimal
import hashlib
import os
import uuid
from typing import Any, Callable, Iterable, Mapping, Sequence

from geometry.naked_retest import (
    CAMPAIGN_LONG,
    CAMPAIGN_SHORT,
    EVENT_DATA_GAP,
    PHASE_CAMPAIGN_ACTIVE,
    PHASE_RETEST_PROVEN,
    TERMINAL_PHASES,
    Boundary,
    initialize_state,
    process_closed_candle,
)
from mirror_retest_observer import boundaries_from_candidate_snapshot
from retest_calibration import fine_resolver
from retest_account_risk import AccountRiskLimit, DECISION_DENY as RISK_DENY, DECISION_OK as RISK_OK, DECISION_WAIT as RISK_WAIT
from retest_campaign import (
    DECISION_ALLOW,
    GateResult,
    PARTIAL_TAKE_FRACTION,
    STOP_NET_BREAK_EVEN,
    entry_gate,
    freeze_campaign_r0,
    net_break_even_remainder_stop,
    open_campaign_budget,
)
from terminal.api.models import ClientActionId, MarketCommandRequest, VolumeRequest, VolumeUnit
from terminal.application.command_identity import CommandIdentityFactory
from terminal.application.ikigai_box_catchup import BoxCatchupMarketPlan
from terminal.domain.models import OrderId, OrderSide
from terminal.market_data.models import BookHealth, NormalizedOrderBook
from terminal.persistence.sqlite_store import BoxOwnedPaperLimitSpec

ENV_FLAG = "BYBITSCANNER_MIRROR_RETEST_ROBOT"
PAPER_TEST_ENV = "BYBITSCANNER_PAPER_TEST"
PAPER_TEST_BUDGET_ENV = "BYBITSCANNER_PAPER_TEST_R0_USDT"
STRATEGY_ID = "MIRROR_RETEST"
WEDGE_PATTERNS = frozenset({"Rising Wedge", "Falling Wedge"})
COARSE_MS = 300_000
FRESH_LAG_MS = 2 * COARSE_MS          # the replay must reach the latest closed 5m candle (or the one before)
MAX_SOURCE_CALLS = 3                  # bounded catch-up per boundary (each call <= 3000 closed 5m candles)
MAX_WEDGES = 5                        # most recent Wedge candidates of the symbol examined per attachment
MAX_SCANNER_LEVELS = 5                # most recent Scanner MIRROR candidates examined per attachment
SCANNER_TIMEFRAMES = ("5", "1")
SCANNER_SOURCE = "MIRROR_SCANNER"

ATTACHED = "ATTACHED"
NOT_ATTACHED = "NOT_ATTACHED"        # not a MIRROR attempt: the plain Box proceeds unchanged
BLOCKED = "BLOCKED"                  # a MIRROR attempt that failed R0 / its gate / its terms: it must not trade
DEFERRED = "DEFERRED"                # transient attachment uncertainty: do not persist, retry without any order
# Only these mean "this Box attempt is not a MIRROR attempt"; any other refusal after a campaign was found blocks.
PLAIN_BOX_REASONS = frozenset({"no_active_campaign", "direction_mismatch", "boundary_not_beyond_box_take"})
EXIT_REASON_RETEST = "MIRROR_RETEST"
PAPER_FEE_RATE = Decimal("0.0006")    # documented PAPER per-side fee (robot_l_shape.PAPER_ROBOT_FEE_RATE)
STOP_SLIPPAGE_FRACTION = Decimal("0.005")   # documented 0.5 % adverse-move ceiling (robot_late_admission)


class MirrorRobotError(RuntimeError):
    """A durable MIRROR record cannot be trusted; the caller fails closed."""


class _FineUnavailable(Exception):
    """1m proof could not be read: hold the candle, never decide UNPROVEN from missing data."""


def mirror_robot_enabled(environ: Mapping[str, str] | None = None) -> bool:
    return (os.environ if environ is None else environ).get(ENV_FLAG, "").strip() == "1"


@dataclass(frozen=True)
class MirrorRobotPolicy:
    """Inputs only MIRROR needs. ``candles`` is a ``mirror_retest_live_sources.BybitClosedKlineSource``-like object
    (``closed_candles(candidate_id, symbol, after_close_ms)`` and ``fine_candles(symbol, coarse)``)."""

    candles: Any
    account_risk_limit_usdt: Callable[[int], Decimal | AccountRiskLimit | None]
    quantity_step: Callable[[str], Decimal]
    fee_rate: Decimal = PAPER_FEE_RATE
    stop_slippage_fraction: Decimal = STOP_SLIPPAGE_FRACTION
    # Scanner MIRROR candidates as campaign sources (``mirror_scanner`` evidence root; None = its default root).
    scanner_levels: bool = True
    scanner_root: Any = None
    # USDT value of 1 working volume (standalone MIRROR entries are 1-WV LIMITs); None = unknown -> DEFERRED.
    one_wv_usdt: Callable[[], Decimal | None] | None = None
    paper_test: bool = False
    # In-process replay cache: boundary_id -> (state proven so far, data_blocked). Closed candles never change, so a
    # cached state is only extended by newer closed candles; a restart simply replays again.
    boundary_states: dict = field(default_factory=dict)


# --- durable values -------------------------------------------------------------------------------------

def boundary_to_dict(boundary: Boundary) -> dict[str, Any]:
    return {"boundary_id": boundary.boundary_id, "anchor_time_ms": boundary.anchor_time_ms,
            "anchor_price": boundary.anchor_price, "slope_per_ms": boundary.slope_per_ms,
            "as_of_time_ms": boundary.as_of_time_ms}


def boundary_from_dict(raw: Mapping[str, Any]) -> Boundary:
    try:
        return Boundary(str(raw["boundary_id"]), int(raw["anchor_time_ms"]), float(raw["anchor_price"]),
                        float(raw["slope_per_ms"]), int(raw["as_of_time_ms"]))
    except (KeyError, TypeError, ValueError) as exc:
        raise MirrorRobotError("durable MIRROR boundary is malformed") from exc


def mirror_record(execution: Mapping[str, Any] | None) -> Mapping[str, Any] | None:
    raw = (execution or {}).get("mirror")
    return raw if isinstance(raw, Mapping) else None


def is_attached(execution: Mapping[str, Any] | None) -> bool:
    raw = mirror_record(execution)
    return raw is not None and raw.get("decision") == ATTACHED


def retest_exit_requested(execution: Mapping[str, Any] | None) -> bool:
    raw = mirror_record(execution)
    return raw is not None and isinstance(raw.get("exit"), Mapping)


def _decimal(value: Any, field: str) -> Decimal:
    try:
        number = value if isinstance(value, Decimal) else Decimal(str(value))
    except Exception as exc:
        raise MirrorRobotError(f"{field} must be decimal") from exc
    if not number.is_finite():
        raise MirrorRobotError(f"{field} must be finite")
    return number


# --- campaign replay ------------------------------------------------------------------------------------

def _resolver(policy: MirrorRobotPolicy, symbol: str, boundary: Boundary, breakout_direction: str):
    def resolve(coarse: Mapping[str, Any], tolerance: float) -> str | None:
        try:
            fine = policy.candles.fine_candles(symbol, coarse)
        except Exception as exc:
            raise _FineUnavailable() from exc           # retry this candle later; no verdict from missing data
        return fine_resolver(boundary, breakout_direction, fine)(coarse, tolerance)
    return resolve


def advance_boundary(policy: MirrorRobotPolicy, candidate_ref: str, symbol: str, boundary: Boundary,
                     state: Mapping[str, Any] | None, *, now_ms: int | None = None) -> tuple[dict[str, Any], bool]:
    """Feed every new closed 5m candle into ``geometry.naked_retest``. Returns ``(state, data_blocked)``.

    With ``now_ms`` no request is made while the next 5m candle after the cursor cannot have closed yet.
    """

    current = dict(state) if state is not None else initialize_state(boundary)[0]
    for _ in range(MAX_SOURCE_CALLS):
        cursor = current.get("cursor_close_time_ms")
        if cursor is not None and now_ms is not None and now_ms < int(cursor) + COARSE_MS:
            break                                        # nothing new can be closed yet: no network call
        if cursor is None:
            cursor = boundary.as_of_time_ms - boundary.as_of_time_ms % COARSE_MS
        candles = policy.candles.closed_candles(candidate_ref, symbol, int(cursor))
        if not candles:
            break
        progressed = False
        for candle in candles:
            resolver = None
            if current.get("phase") == PHASE_CAMPAIGN_ACTIVE:
                resolver = _resolver(policy, symbol, boundary, current["breakout"]["direction"])
            try:
                new_state, event = process_closed_candle(boundary, current, candle, ambiguity_resolver=resolver)
            except _FineUnavailable:
                return current, True        # unproven 1m candle: hold cursor and defer new attachment
            if event == EVENT_DATA_GAP:
                return new_state, True
            progressed = progressed or new_state.get("cursor_close_time_ms") != current.get("cursor_close_time_ms")
            current = new_state
            if current["phase"] in TERMINAL_PHASES:
                return current, False
        if not progressed:
            break
    return current, bool(current.get("data_blocked"))


def scanner_level_sources(symbol: str, *, root: Any = None) -> list[dict[str, Any]]:
    """Live Scanner MIRROR candidates of ``symbol``: a fresh naked breakout of a level that is still untested.

    Read-only over ``mirror_scanner``'s durable state. An unreadable state file is not "no campaign": it raises, so the
    attachment defers without orders (the Scanner itself never overwrites such a file).
    """

    from mirror_levels.levels import LevelRegistry, MirrorLevelError
    from mirror_levels.tracker import STATUS_UNTESTED
    from mirror_scanner import LIFECYCLE_TRACKING, MirrorStateError, load_state, state_path

    sources = []
    for timeframe in SCANNER_TIMEFRAMES:
        if not state_path(symbol, timeframe, root).exists():
            continue
        try:
            state = load_state(symbol, timeframe, root)
            registry = LevelRegistry.from_dict(state["registry"])
        except (MirrorStateError, MirrorLevelError, KeyError, TypeError, ValueError) as exc:
            raise MirrorRobotError(f"MIRROR Scanner state unreadable: {symbol} {timeframe}m") from exc
        for level_id, record in sorted(state["records"].items()):
            if (not isinstance(record, Mapping) or record.get("candidate") is not True
                    or record.get("lifecycle") != LIFECYCLE_TRACKING or record.get("status") != STATUS_UNTESTED):
                continue                                 # stale / weak / duplicate / retested / gap: never a source
            level = registry.levels.get(level_id)
            breakout = (record.get("naked_retest") or {}).get("breakout")
            if (level is None or level.symbol != symbol or not isinstance(breakout, Mapping)
                    or breakout.get("campaign_direction") not in {CAMPAIGN_LONG, CAMPAIGN_SHORT}):
                continue
            sources.append({"level_id": level_id, "timeframe": timeframe, "boundary": level.boundary,
                            "pattern": level.pattern, "source": level.source,
                            "breakout_open_ms": int(breakout["open_time_ms"]),
                            "breakout_close_ms": int(breakout["close_time_ms"]),
                            "campaign_direction": breakout["campaign_direction"]})
    sources.sort(key=lambda item: (-item["breakout_close_ms"], item["level_id"]))
    return sources[:MAX_SCANNER_LEVELS]                  # bounded network work per attachment


def _replay_active(policy: MirrorRobotPolicy, ref: str, symbol: str, boundary: Boundary, *, direction: str,
                   now_ms: int) -> tuple[dict[str, Any] | None, bool]:
    """``(active state in direction | None, unresolved)`` from the Robot's own closed-5m replay of one boundary."""

    cached = policy.boundary_states.get(boundary.boundary_id)
    if cached is not None and cached[0].get("phase") in TERMINAL_PHASES:
        return None, False                               # a finished campaign never reopens (rule 5)
    state, blocked = advance_boundary(policy, ref, symbol, boundary, None if cached is None else cached[0],
                                      now_ms=now_ms)
    policy.boundary_states[boundary.boundary_id] = (state, blocked)
    if blocked:
        return None, True                                # incomplete candle or 1m proof is not "no campaign"
    if state.get("phase") != PHASE_CAMPAIGN_ACTIVE or state["breakout"]["campaign_direction"] != direction:
        return None, False
    if int(state.get("cursor_close_time_ms") or 0) < now_ms - now_ms % COARSE_MS - FRESH_LAG_MS:
        return None, True                                # cannot prove active status from stale replay
    return state, False


def find_active_campaign(policy: MirrorRobotPolicy, wedge_records: Iterable[Any], *, symbol: str,
                         direction: str, now_ms: int,
                         scanner_sources: Sequence[Mapping[str, Any]] = (),
                         breakout_close_ms: int | None = None) -> dict[str, Any] | None:
    """The most recent ACTIVE campaign in ``direction`` on ``symbol``, replayed only from durable inputs.

    One naked breakout seen through several sources (a Wedge line and the Scanner level of the same line) is one
    campaign: equal breakout candles collapse onto the Wedge source, else the smallest boundary id, so every attempt
    of that breakout shares one ``campaign_id`` and one R0 budget. ``breakout_close_ms`` restricts the answer to the
    campaign of that one breakout candle (a standalone attempt belongs to its own level's breakout only).
    """

    found: list[dict[str, Any]] = []
    unresolved = False
    eligible = [record for record in wedge_records
                if isinstance(getattr(record, "signal_snapshot", None), Mapping)
                and record.signal_snapshot.get("pattern") in WEDGE_PATTERNS
                and isinstance(getattr(record, "approved_at_ms", None), int) and record.approved_at_ms <= now_ms]
    eligible.sort(key=lambda record: record.approved_at_ms, reverse=True)
    for record in eligible[:MAX_WEDGES]:                 # bounded network work per attachment
        snapshot, approved = record.signal_snapshot, record.approved_at_ms
        boundaries = boundaries_from_candidate_snapshot(
            candidate_id=record.candidate_id, created_at_ms=approved, signal_snapshot=snapshot)
        for boundary in boundaries or ():
            state, blocked = _replay_active(policy, record.candidate_id, symbol, boundary,
                                            direction=direction, now_ms=now_ms)
            unresolved = unresolved or blocked
            if state is not None:
                found.append({"boundary": boundary, "state": state, "parent_candidate_id": record.candidate_id})
    for source in scanner_sources:
        if source.get("campaign_direction") != direction or source["boundary"].as_of_time_ms > now_ms:
            continue
        state, blocked = _replay_active(policy, f"mirror-level:{source['level_id']}", symbol, source["boundary"],
                                        direction=direction, now_ms=now_ms)
        unresolved = unresolved or blocked
        if state is None:
            continue
        if source.get("timeframe") == "5" and int(state["breakout"]["open_time_ms"]) != source["breakout_open_ms"]:
            continue                                     # the Robot's replay does not confirm the Scanner breakout
        found.append({"boundary": source["boundary"], "state": state, "parent_candidate_id": None,
                      "source": SCANNER_SOURCE, "mirror_level_id": source["level_id"],
                      "mirror_timeframe": source.get("timeframe"), "mirror_pattern": source.get("pattern"),
                      "mirror_level_source": source.get("source")})
    if not found:
        if unresolved:
            raise MirrorRobotError("MIRROR campaign evidence is incomplete")
        return None
    for item in found:
        item["breakout_close_ms"] = int(item["state"]["breakout"]["close_time_ms"])
    if breakout_close_ms is not None:
        found = [item for item in found if item["breakout_close_ms"] == int(breakout_close_ms)]
        if not found:
            return None
    found.sort(key=lambda item: (-item["breakout_close_ms"], item["parent_candidate_id"] is None,
                                 item["boundary"].boundary_id))
    best = found[0]
    return {**best, "campaign_id": f"{best['boundary'].boundary_id}@{best['breakout_close_ms']}",
            "campaign_direction": direction}


# --- attachment (entry gate) -------------------------------------------------------------------------------

def _floor(value: Decimal, step: Decimal) -> Decimal:
    return (value / step).to_integral_value(rounding=ROUND_FLOOR) * step


def _campaign_budget(policy: MirrorRobotPolicy, campaign: Mapping[str, Any],
                     prior_attempts: Sequence[Mapping[str, Any]], *, worst_case: Decimal, potential: Decimal,
                     now_ms: int) -> dict[str, Any]:
    """One R0 per campaign (frozen at its first attempt, never restored) and the §5 gate for a new attempt.

    Shared by Box-overlay and standalone attempts, so one breakout never spends two budgets.
    """

    def defer(reason: str) -> dict[str, Any]:
        return {"decision": DEFERRED, "reason": reason}

    def no(reason: str) -> dict[str, Any]:
        return {"decision": BLOCKED, "reason": reason}

    r0 = next((Decimal(str(a["mirror"]["r0_usdt"])) for a in prior_attempts
               if isinstance(a.get("mirror"), Mapping) and a["mirror"].get("r0_usdt") is not None), None)
    if r0 is None:
        # The PAPER runtime supplies a structured account-risk verdict. Keep WAIT retriable,
        # but reject a proven daily-loss latch or exhausted risk headroom.
        account_risk = policy.account_risk_limit_usdt(now_ms)
        if isinstance(account_risk, AccountRiskLimit):
            if account_risk.decision == RISK_WAIT:
                return defer(f"r0_wait:{account_risk.reason}")
            if account_risk.decision == RISK_DENY:
                return no(f"r0_denied:{account_risk.reason}")
            if account_risk.decision != RISK_OK:
                return defer("r0_unavailable")
            account_limit = account_risk.limit_usdt
        else:
            account_limit = account_risk               # injected test/legacy policy
        if account_limit is None:
            return defer("r0_unavailable")
        frozen = freeze_campaign_r0(idea_potential_net_usdt=potential,
                                    account_risk_limit_usdt=account_limit)
        if frozen is None:
            return no("r0_invalid")
        r0 = Decimal(str(frozen))
    realized_losses = Decimal(0)
    live_worst = Decimal(0)
    for attempt in prior_attempts:
        if attempt.get("closed"):
            net = attempt.get("net_pnl_usdt")
            if net is None:
                return defer("prior_attempt_result_unknown")
            realized_losses += max(Decimal(0), -Decimal(str(net)))
        else:
            live_worst += Decimal(str(attempt["mirror"]["worst_case_usdt"]))
    if policy.paper_test:
        # PAPER-only test policy: preserve active campaign and proven data,
        # but do not reject test attempts because of campaign financial loss.
        state = campaign["state"]
        if state.get("phase") != PHASE_CAMPAIGN_ACTIVE:
            return no("campaign_not_active")
        if state.get("data_blocked"):
            return defer("campaign_data_unreliable")
        gate = GateResult(DECISION_ALLOW, "paper_test_financial_policy", open_campaign_budget(r0))
        return {"decision": ATTACHED, "reason": gate.reason, "r0": r0, "gate": gate}
    gate = entry_gate(open_campaign_budget(r0), campaign_phase=campaign["state"]["phase"], data_reliable=True,
                      realized_loss_costs_usdt=realized_losses, live_pending_worst_case_usdt=live_worst,
                      new_attempt_worst_case_usdt=worst_case, remaining_net_reward_usdt=potential)
    if gate.decision == RISK_WAIT:
        return defer(f"campaign_gate_wait:{gate.reason}")
    if gate.decision != DECISION_ALLOW:
        return no(f"campaign_gate_{gate.decision.lower()}:{gate.reason}")
    return {"decision": ATTACHED, "reason": gate.reason, "r0": r0, "gate": gate}


def plan_attachment(policy: MirrorRobotPolicy, *, box_snapshot: Mapping[str, Any], symbol: str,
                    campaign: Mapping[str, Any] | None, prior_attempts: Sequence[Mapping[str, Any]],
                    now_ms: int) -> dict[str, Any]:
    """Decide once, before any Box order exists, whether this Box attempt is a MIRROR attempt.

    ``prior_attempts``: ``{"mirror": <durable record>, "closed": bool, "net_pnl_usdt": Decimal | None}`` of earlier
    attempts of the same campaign. Unknown R0/gate evidence defers without orders; proven denial blocks.
    """

    def no(reason: str) -> dict[str, Any]:
        plain = campaign is None or reason in PLAIN_BOX_REASONS
        out = {"strategy_id": STRATEGY_ID, "decision": NOT_ATTACHED if plain else BLOCKED, "reason": reason,
               "decided_at_ms": now_ms}
        if campaign is not None:
            out["campaign_id"] = campaign["campaign_id"]
            if campaign.get("parent_candidate_id") is not None:
                out["parent_candidate_id"] = campaign["parent_candidate_id"]
        return out

    def defer(reason: str) -> dict[str, Any]:
        out = {"strategy_id": STRATEGY_ID, "decision": DEFERRED, "reason": reason,
               "decided_at_ms": now_ms, "campaign_id": campaign["campaign_id"]}
        if campaign.get("parent_candidate_id") is not None:
            out["parent_candidate_id"] = campaign["parent_candidate_id"]
        return out

    if campaign is None:
        return no("no_active_campaign")
    plan = box_snapshot.get("plan") or {}
    direction = str(plan.get("direction", "")).upper()
    if direction != campaign["campaign_direction"]:
        return no("direction_mismatch")
    try:
        quantities = [_decimal(q, "slot quantity") for q in plan["limit_quantities"]]
        take = _decimal(plan["take_price"], "Box TAKE")
        full = plan["full_position"]
        average = _decimal(full["average_entry"], "Box average entry")
        worst_case = _decimal(full["net_stop_loss"], "Box net stop loss")
        step = _decimal(policy.quantity_step(symbol), "quantity step")
    except (KeyError, TypeError, MirrorRobotError):
        return no("box_terms_unavailable")
    if len(quantities) != 4 or step <= 0 or worst_case < 0:
        return no("box_terms_unavailable")
    boundary: Boundary = campaign["boundary"]
    target = Decimal(str(boundary.price_at(now_ms)))
    beyond = target > take if direction == CAMPAIGN_LONG else target < take
    if not beyond:
        return no("boundary_not_beyond_box_take")

    partial = [_floor(q * Decimal(str(PARTIAL_TAKE_FRACTION)), step) for q in quantities]
    if not any(p > 0 for p in partial):
        return no("partial_take_below_quantity_step")
    total, partial_total = sum(quantities), sum(partial)
    remainder = total - partial_total
    sign = Decimal(1) if direction == CAMPAIGN_LONG else Decimal(-1)
    gross = partial_total * (take - average) * sign + remainder * (target - average) * sign
    fees = policy.fee_rate * (total * average + partial_total * take + remainder * target)
    potential = gross - fees

    if potential <= 0:
        return no("net_potential_nonpositive")
    budget = _campaign_budget(policy, campaign, prior_attempts, worst_case=worst_case, potential=potential,
                              now_ms=now_ms)
    if budget["decision"] == DEFERRED:
        return defer(budget["reason"])
    if budget["decision"] != ATTACHED:
        return no(budget["reason"])
    r0, gate = budget["r0"], budget["gate"]
    return {
        "strategy_id": STRATEGY_ID, "decision": ATTACHED, "reason": gate.reason, "decided_at_ms": now_ms,
        "campaign_id": campaign["campaign_id"], "campaign_direction": direction,
        "boundary": boundary_to_dict(boundary), "state": campaign["state"],
        "partial_quantities": [str(p) for p in partial], "target_at_attach": str(target),
        "r0_usdt": str(r0), "worst_case_usdt": str(worst_case), "remaining_net_reward_usdt": str(potential),
        "budget_cap_usdt": str(gate.budget.cap_usdt),
        **({"parent_candidate_id": campaign["parent_candidate_id"]}
           if campaign.get("parent_candidate_id") is not None else {}),
        **({key: campaign[key] for key in ("source", "mirror_level_id", "mirror_timeframe", "mirror_pattern",
                                           "mirror_level_source") if campaign.get(key) is not None}),
    }


def plan_standalone_attachment(policy: MirrorRobotPolicy, *, direction: str, entry_price: Any, stop_price: Any,
                               target_price: Any, campaign: Mapping[str, Any] | None,
                               prior_attempts: Sequence[Mapping[str, Any]], now_ms: int) -> dict[str, Any]:
    """Decide, before any order exists, whether a standalone MIRROR entry (one 1-WV LIMIT) may trade.

    Requires the live campaign of its own level (none after the first retest -> never an entry), the campaign
    direction, a known 1 WV and the same single campaign R0 / §5 gate as the Box overlay. Worst case and potential
    are in USDT at 1 WV with the PAPER fee on both sides and the documented adverse slippage on the exit leg.
    Anything but ATTACHED / DEFERRED means: no order, the candidate is retired.
    """

    def no(reason: str) -> dict[str, Any]:
        out = {"strategy_id": STRATEGY_ID, "decision": BLOCKED, "mode": "STANDALONE", "reason": reason,
               "decided_at_ms": now_ms}
        if campaign is not None:
            out["campaign_id"] = campaign["campaign_id"]
        return out

    def defer(reason: str) -> dict[str, Any]:
        out = {"strategy_id": STRATEGY_ID, "decision": DEFERRED, "mode": "STANDALONE", "reason": reason,
               "decided_at_ms": now_ms}
        if campaign is not None:
            out["campaign_id"] = campaign["campaign_id"]
        return out

    if campaign is None:
        return no("no_active_campaign")
    if direction != campaign["campaign_direction"]:
        return no("direction_mismatch")
    try:
        entry = _decimal(entry_price, "entry price")
        stop = _decimal(stop_price, "stop price")
        target = _decimal(target_price, "target price")
    except MirrorRobotError:
        return no("entry_terms_unavailable")
    sign = Decimal(1) if direction == CAMPAIGN_LONG else Decimal(-1)
    if entry <= 0 or (entry - stop) * sign <= 0 or (target - entry) * sign <= 0:
        return no("entry_terms_invalid")
    one_wv = policy.one_wv_usdt() if policy.one_wv_usdt is not None else None
    if one_wv is None:
        return defer("one_wv_unavailable")
    one_wv = _decimal(one_wv, "1 WV")
    if one_wv <= 0:
        return no("one_wv_invalid")
    quantity = one_wv / entry
    fee, slip = policy.fee_rate, policy.stop_slippage_fraction
    worst_case = quantity * ((entry - stop) * sign + fee * (entry + stop) + slip * stop)
    potential = quantity * ((target - entry) * sign - fee * (entry + target) - slip * target)
    if potential <= 0:
        return no("net_potential_nonpositive")
    budget = _campaign_budget(policy, campaign, prior_attempts, worst_case=worst_case, potential=potential,
                              now_ms=now_ms)
    if budget["decision"] == DEFERRED:
        return defer(budget["reason"])
    if budget["decision"] != ATTACHED:
        return no(budget["reason"])
    boundary: Boundary = campaign["boundary"]
    return {
        "strategy_id": STRATEGY_ID, "decision": ATTACHED, "mode": "STANDALONE", "reason": budget["reason"],
        "decided_at_ms": now_ms, "campaign_id": campaign["campaign_id"], "campaign_direction": direction,
        "boundary": boundary_to_dict(boundary), "state": campaign["state"],
        "entry_price": str(entry), "stop_price": str(stop), "target_price": str(target),
        "one_wv_usdt": str(one_wv), "r0_usdt": str(budget["r0"]), "worst_case_usdt": str(worst_case),
        "remaining_net_reward_usdt": str(potential), "budget_cap_usdt": str(budget["gate"].budget.cap_usdt),
        **({"parent_candidate_id": campaign["parent_candidate_id"]}
           if campaign.get("parent_candidate_id") is not None else {}),
        **({key: campaign[key] for key in ("source", "mirror_level_id", "mirror_timeframe", "mirror_pattern",
                                           "mirror_level_source") if campaign.get(key) is not None}),
    }


# --- exits ------------------------------------------------------------------------------------------------

def partial_exit_specs(source: Any, mirror: Mapping[str, Any], *, slots: Iterable[int],
                       created_at_ms: int) -> tuple[BoxOwnedPaperLimitSpec, ...]:
    """One Box-owned EXIT LIMIT per filled slot for its 25 % share, at the frozen Box TAKE."""

    plan = source.signal_snapshot["plan"]
    direction = str(plan["direction"]).upper()
    take = _decimal(plan["take_price"], "Box TAKE")
    partial = [_decimal(q, "partial quantity") for q in mirror["partial_quantities"]]
    side = OrderSide.SELL if direction == CAMPAIGN_LONG else OrderSide.BUY
    specs = []
    for slot in sorted(set(slots)):
        quantity = partial[slot - 1]
        if quantity <= 0:
            continue                                     # this slot is held whole to the retest
        digest = hashlib.sha256(f"box-mirror-partial-exit\0{source.candidate_id}\0{slot}".encode()).hexdigest()
        fingerprint = hashlib.sha256(
            f"{source.snapshot_sha256}\0MIRROR_EXIT\0{slot}\0{side.value}\0{take}\0{quantity}".encode()).hexdigest()
        specs.append(BoxOwnedPaperLimitSpec(
            slot=slot, client_action_id=f"box-mirror-exit-{digest}", request_fingerprint=fingerprint,
            order_id=OrderId(f"paper-box-mirror-exit-{digest}"), order_link_id=f"box-mirror-exit-{digest}",
            side=side, price=take, quantity=quantity, created_at_ms=created_at_ms))
    return tuple(specs)


def retest_close_market_plan(source: Any, book: NormalizedOrderBook, *, quantity: Decimal) -> BoxCatchupMarketPlan:
    """The stable Box-owned EXIT MARKET (slot 0) that closes the MIRROR remainder at the proven retest."""

    direction = str(source.signal_snapshot["plan"]["direction"]).upper()
    quantity = _decimal(quantity, "remainder quantity")
    if quantity <= 0:
        raise MirrorRobotError("remainder quantity must be positive")
    if book.symbol != source.symbol or book.health is not BookHealth.READY:
        raise MirrorRobotError("authoritative READY book for the Box symbol is required")
    levels = book.bids if direction == CAMPAIGN_LONG else book.asks
    if not levels:
        raise MirrorRobotError("executable book side is empty")
    best = _decimal(levels[0].price.value, "best price")
    side = OrderSide.SELL if direction == CAMPAIGN_LONG else OrderSide.BUY
    digest = hashlib.sha256(f"box-mirror-retest-close\0{source.candidate_id}".encode()).hexdigest()[:32]
    identity = CommandIdentityFactory(lambda value=uuid.UUID(hex=digest): value).create()
    request = MarketCommandRequest(
        client_action_id=ClientActionId(f"box-market-{digest}"), symbol=source.symbol.value, side=side,
        volume=VolumeRequest(VolumeUnit.USDT, quantity * best), sizing_reference_price=best,
        slippage_type="Percent", slippage_value=Decimal("0.5"))
    return BoxCatchupMarketPlan(slot=0, quantity=quantity, best_price=best,
                                order_id=OrderId(f"paper-order-{identity.order_link_id}"),
                                request=request, identity=identity)


def break_even_stop(policy_fee_rate: Decimal, slippage_fraction: Decimal, *, direction: str, proof: Any,
                    current_stop: Decimal | None, mark: Decimal, tick: Decimal) -> Decimal | None:
    """Rule 12: tighter remainder STOP that keeps the whole trade's net PnL >= 0, or None (keep current)."""

    if proof.exit_quantity <= 0 or proof.remaining_quantity <= 0 or proof.average_exit is None:
        return None
    plan = net_break_even_remainder_stop(
        campaign_direction=direction, partial_take_confirmed=True,
        protection_preserved=current_stop is not None, current_stop_price=current_stop, mark_price=mark,
        entry_qty=proof.entry_quantity, entry_avg_price=proof.average_entry,
        entry_fees_usdt=proof.accumulated_fee, partial_qty=proof.exit_quantity,
        partial_avg_price=proof.average_exit, partial_fees_usdt=Decimal(0),
        funding_usdt=Decimal(0),                          # PAPER simulator: no funding (daily gate facts)
        remainder_exit_fee_rate=policy_fee_rate, slippage_price=mark * slippage_fraction, tick_size=tick)
    return plan.stop_price if plan.decision == STOP_NET_BREAK_EVEN else None


def tighter_stop(direction: str, a: Decimal, b: Decimal | None) -> Decimal:
    if b is None:
        return a
    return max(a, b) if direction == CAMPAIGN_LONG else min(a, b)


# --- runtime wiring ---------------------------------------------------------------------------------------

def build_runtime_policy(*, database_path: Any, account_id: Any,
                         quantity_step: Callable[[str], Decimal],
                         daily_marks: Callable[[], tuple[Mapping[str, Any], int]] | None = None,
                         environ: Mapping[str, str] | None = None) -> MirrorRobotPolicy | None:
    """The production policy, or None (the default) unless ``BYBITSCANNER_MIRROR_RETEST_ROBOT=1``.

    Candles: public closed klines (read-only). Account risk limit: the PAPER_AUTO daily-loss gate valued with the
    runtime's fresh marks (``daily_marks``, the provider Autopilot uses) minus committed worst cases
    (``retest_account_risk.account_risk_limit``); anything but OK means no R0 -> the MIRROR attempt is BLOCKED.
    """

    if not mirror_robot_enabled(environ):
        return None
    env = os.environ if environ is None else environ
    paper_test = env.get(PAPER_TEST_ENV, "").strip() == "1"
    paper_test_budget = env.get(PAPER_TEST_BUDGET_ENV) if paper_test else None
    from mirror_retest_live_sources import BybitClosedKlineSource

    def risk_limit(now_ms: int) -> AccountRiskLimit:
        from mirror_retest_sidecar import read_account_facts
        from retest_account_risk import DECISION_OK, account_risk_limit
        from terminal.persistence.sqlite_store import SQLiteStore

        reader = SQLiteStore.open_reader(database_path)
        try:
            with reader.read_snapshot():
                facts = read_account_facts(reader, account_id, now_ms=now_ms, daily_marks=daily_marks)
        finally:
            reader.close()
        limit = account_risk_limit(daily_gate=facts.daily_gate,
                                   committed_worst_case_usdt=facts.committed_worst_case_usdt,
                                   paper_test=paper_test,
                                   paper_test_budget_usdt=paper_test_budget)
        return limit   # Preserve WAIT vs DENY and source reason for attachment decision.

    def one_wv_usdt() -> Decimal | None:
        from terminal.domain.models import TradingAccountId
        from terminal.persistence.sqlite_store import SQLiteStore
        from terminal.runtime.paper_context import working_volume_usdt

        reader = SQLiteStore.open_reader(database_path)
        try:
            with reader.read_snapshot():
                account = reader.get_paper_account(
                    account_id if isinstance(account_id, TradingAccountId) else TradingAccountId(str(account_id)))
        finally:
            reader.close()
        return None if account is None else working_volume_usdt(account.equity_usdt)   # the PAPER 1-WV rule

    return MirrorRobotPolicy(candles=BybitClosedKlineSource(strict_availability=True),
                             account_risk_limit_usdt=risk_limit,
                             quantity_step=quantity_step, one_wv_usdt=one_wv_usdt,
                             paper_test=paper_test)
