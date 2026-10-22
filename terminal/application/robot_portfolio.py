"""Read-only PAPER capital facts for SHADOW, never a trading allocator.

One Robot idea = one full RO. Manual working LIMITs are independent obligations.
Fill identity merges the filled and pending portions; ambiguous reductions are
unknown, never assigned to a convenient lot. Unresolved SHADOW selections stay
reserved across restart/OFF until a linked real idea proves terminal and flat, or
a durable source-terminal event of the same signal identity (A3-R3b sidecar store)
proves it ended while no physical obligation remains on its symbol.
"""
from __future__ import annotations

from decimal import Decimal, ROUND_CEILING
import sqlite3
from typing import Iterable

from terminal.domain.models import TradingAccountId
from terminal.persistence.sqlite_store import (
    PersistenceError, RobotAutoDecisionRecord, RobotCandidateRecord, SQLiteStore,
)
from terminal.persistence.source_terminal_events import (
    SourceTerminalEventError, load_terminal_identities, source_terminal_events_path,
)

RO_USDT = 250
CAP_RO = 19
DEFERRED = ("per_asset_2_ro", "correlation", "cluster", "direction", "daily_loss")


class Unavailable(ValueError):
    pass


def _number(value):
    number = Decimal(str(value))
    if not number.is_finite() or number < 0:
        raise Unavailable("invalid monetary/quantity fact")
    return number


def collect_portfolio_facts(
    store: SQLiteStore, account: TradingAccountId, *,
    robot_candidates: Iterable[RobotCandidateRecord] | None = None,
    auto_decisions: Iterable[RobotAutoDecisionRecord] | None = None,
) -> dict:
    """Caller serializes this read with audit append. No PAPER writes or services.

    ``robot_candidates``/``auto_decisions`` may be rows the caller already read
    inside the same decision transaction; they are never a cache across transactions.
    """
    facts = {"available": False, "reference_capital_usdt": 5000,
             "ro_usdt": RO_USDT, "cap_ro": CAP_RO, "new_reserve_ro": 1,
             "deferred_controls": {name: "NOT_EVALUATED" for name in DEFERRED}}
    try:
        paper_account = store.get_paper_account(account)
        if account.value != "paper" or paper_account is None:
            raise Unavailable("PAPER account is unavailable")
        rows = store.load_paper_portfolio_rows(account)
        candidates = {c.candidate_id: c for c in (
            store.load_robot_candidates(account) if robot_candidates is None else robot_candidates)}
        trades = store.load_open_robot_trades(account)
        orders = {o["order_id"]: o for o in rows["paper_limit_orders"]}
        commands = {c["command_id"]: c for c in rows["trading_commands"]}
        projections = {p["symbol"]: p for p in rows["position_projections"]}
        working_limits = [
            order for order in orders.values()
            if order["status"] in {"open", "partially_filled"}
        ]
        working_limit_symbols = {order["symbol"] for order in working_limits}
        terminal_command_states = {"filled", "cancelled", "amended", "rejected", "failed"}
        superseded_commands = []
        unresolved_commands = []
        for command in commands.values():
            if command["current_state"] in terminal_command_states:
                continue
            projection = projections.get(command["symbol"])
            superseded_by_flat = (
                command["command_kind"] == "create_market"
                and command["current_state"] == "submitting"
                and command["exchange_order_id"] is None
                and projection is not None
                and projection["side"] == "Flat"
                and _number(projection["quantity"]) == 0
                and _number(projection["engaged_notional"]) == 0
                and projection["sync_state"] == "synced"
                and int(projection["updated_at_ms"]) > int(command["updated_at_ms"])
                and command["symbol"] not in working_limit_symbols
            )
            summary = {
                "command_id": command["command_id"],
                "symbol": command["symbol"],
                "kind": command["command_kind"],
                "state": command["current_state"],
                "updated_at_ms": command["updated_at_ms"],
            }
            if superseded_by_flat:
                summary["proof"] = "later_synced_flat_zero_exposure"
                summary["proof_updated_at_ms"] = projection["updated_at_ms"]
                superseded_commands.append(summary)
            else:
                unresolved_commands.append(summary)
        facts["superseded_commands"] = sorted(
            superseded_commands,
            key=lambda item: (item["symbol"], item["updated_at_ms"], item["command_id"]),
        )
        unresolved_symbols = {command["symbol"] for command in unresolved_commands}
        facts["historical_flat_records"] = [
            {"symbol": position["symbol"], "sync_state": position["sync_state"],
             "version": position["version"], "updated_at_ms": position["updated_at_ms"],
             "proof": "flat_zero_quantity_zero_engaged_notional"}
            for position in projections.values()
            if (position["side"] == "Flat" and _number(position["quantity"]) == 0
                and _number(position["engaged_notional"]) == 0
                and position["sync_state"] != "synced"
                and position["symbol"] not in working_limit_symbols
                and position["symbol"] not in unresolved_symbols)
        ]
        if unresolved_commands:
            facts["unresolved_commands"] = sorted(
                unresolved_commands,
                key=lambda item: (item["symbol"], item["updated_at_ms"], item["command_id"]),
            )
            counts = {}
            for command in unresolved_commands:
                counts[command["symbol"]] = counts.get(command["symbol"], 0) + 1
            detail = ", ".join(f"{symbol} ({counts[symbol]})" for symbol in sorted(counts))
            raise Unavailable(
                "unfinished command lacks a later authoritative flat snapshot: " + detail
            )
        owners = {}
        reservations = {}
        symbols = set()

        # A Box plan and its handed-off Robot candidate are one physical idea
        # only when both immutable snapshot lineage and Robot state agree.
        # Never canonicalize merely because two candidate IDs look alike.
        handoffs = {}
        ambiguous_handoffs = set()
        for robot in candidates.values():
            source_id = robot.signal_snapshot.get("source_box_candidate_id")
            if not source_id:
                continue
            source = candidates.get(source_id)
            state = robot.robot_state or {}
            snapshot = dict(robot.signal_snapshot)
            snapshot.pop("source_box_candidate_id", None)
            if (source is None or source.status != "BOX_PLAN_ONLY"
                    or source.symbol.value != robot.symbol.value
                    or state.get("source_box_candidate_id") != source_id
                    or snapshot != source.signal_snapshot):
                continue
            if source_id in handoffs:
                ambiguous_handoffs.add(source_id)
            else:
                handoffs[source_id] = robot.candidate_id

        def canonical_owner(candidate_id):
            if candidate_id in ambiguous_handoffs:
                raise Unavailable("order ownership is ambiguous")
            candidate_id = handoffs.get(candidate_id, candidate_id)
            child = candidates.get(candidate_id)
            state = (child.robot_state or {}) if child is not None else {}
            parent_id = state.get("mirror_parent_candidate_id")
            if not isinstance(parent_id, str) or not parent_id.strip():
                return candidate_id
            parent = candidates.get(parent_id)
            if (
                parent is None
                or child is None
                or child.signal_snapshot.get("pattern") != "IKIGAI_BOX"
                or child.robot_state.get("source_box_candidate_id")
                    != child.signal_snapshot.get("source_box_candidate_id")
                or parent.status != "APPROVED"
                or parent.symbol != child.symbol
                or parent.snapshot_sha256 != state.get("mirror_parent_snapshot_sha256")
                or str((parent.robot_state or {}).get("direction", "")).upper()
                    != str(state.get("mirror_parent_direction", "")).upper()
            ):
                # An invalid/stale link never releases capital fail-open.
                return candidate_id
            return parent_id

        def reserve(key, symbol, ro=1):
            previous = reservations.get(key)
            if previous is not None and previous["symbol"] != symbol:
                raise Unavailable("obligation identity crosses symbols")
            reservations[key] = {"identity": key, "symbol": symbol,
                                 "ro": max(ro, previous["ro"] if previous else 0)}
            symbols.add(symbol)

        def own(order_id, candidate_id):
            c = candidates.get(candidate_id)
            candidate_id = canonical_owner(candidate_id)
            if c is None or (order_id in owners and owners[order_id] != candidate_id):
                raise Unavailable("order ownership is ambiguous")
            order = orders.get(order_id)
            if order and order["symbol"] != c.symbol.value:
                raise Unavailable("order ownership crosses symbols")
            owners[order_id] = candidate_id

        for c in candidates.values():
            if c.status in {"APPROVED", "OPEN"}:
                reserve("robot:" + canonical_owner(c.candidate_id), c.symbol.value)
            execution = (c.robot_state or {}).get("execution") or {}
            ids = list(execution.get("limit_order_ids") or []) + list(execution.get("market_order_ids") or [])
            if execution.get("limit_order_id"):
                ids.append(execution["limit_order_id"])
            intent = execution.get("late_market_intent") or {}
            if intent:
                command = commands.get(intent.get("command_id"))
                if command and command["symbol"] != c.symbol.value:
                    raise Unavailable("market command crosses symbols")
                if command and command["exchange_order_id"]:
                    ids.append(command["exchange_order_id"])
            for order_id in ids:
                own(order_id, c.candidate_id)
        for ownership in rows["box_order_ownership"]:
            own(ownership["order_id"], ownership["candidate_id"])
        for trade in trades:
            if trade.candidate_id not in candidates:
                raise Unavailable("trade has no candidate")
            reserve("robot:" + canonical_owner(trade.candidate_id), trade.symbol.value)

        def identity(order_id):
            return "robot:" + owners[order_id] if order_id in owners else "manual-order:" + order_id

        executions = {}
        for fill in rows["executions"]:
            executions.setdefault(fill["symbol"], []).append(fill)
        pending_symbols = set()
        for order in orders.values():
            qty, filled = _number(order["quantity"]), _number(order["filled_quantity"])
            if filled > qty or qty <= 0:
                raise Unavailable("invalid LIMIT quantities")
            if order["status"] in {"open", "partially_filled"}:
                if filled >= qty:
                    raise Unavailable("working LIMIT has no remainder")
                reserve(identity(order["order_id"]), order["symbol"])
                pending_symbols.add(order["symbol"])
                proven_fills = sum((_number(f["quantity"]) for f in executions.get(order["symbol"], [])
                                    if f["order_id"] == order["order_id"]), Decimal(0))
                if proven_fills != filled:
                    raise Unavailable("LIMIT filled quantity lacks matching executions")

        for symbol in set(executions) | set(projections):
            projection = projections.get(symbol)
            projected = _number(projection["quantity"]) if projection else Decimal(0)
            if projection and projected == 0:
                if projection["side"] != "Flat" or _number(projection["engaged_notional"]) != 0:
                    raise Unavailable("zero position projection is internally inconsistent")
            elif projection and projection["sync_state"] != "synced":
                raise Unavailable("position is not reconciled")
            if projected and projection["side"] not in {"Long", "Short"}:
                raise Unavailable("position side is invalid")
            signed_projected = -projected if projection and projection["side"] == "Short" else projected
            history = sorted(executions.get(symbol, []), key=lambda f: (f["exchange_timestamp_ms"], f["exec_id"]))
            if not history:
                if projected:
                    if symbol in symbols or symbol in pending_symbols:
                        raise Unavailable("position overlap cannot be proven without fills")
                    notional = _number(projection["engaged_notional"])
                    if notional <= 0:
                        raise Unavailable("manual position notional is unavailable")
                    reserve("manual-position:" + symbol, symbol,
                            max(1, int((notional / RO_USDT).to_integral_value(rounding=ROUND_CEILING))))
                continue
            # Same-side fills at one timestamp commute (e.g. four Box slots).
            # Opposing fills at a tied timestamp have no proven chronology.
            sides_by_time = {}
            for fill in history:
                sides_by_time.setdefault(fill["exchange_timestamp_ms"], set()).add(fill["side"])
            if any(len(sides) > 1 for sides in sides_by_time.values()):
                raise Unavailable("fill chronology is ambiguous")
            net, lots, ambiguous_allocation = Decimal(0), {}, False
            for fill in history:
                qty = _number(fill["quantity"])
                if qty <= 0 or fill["side"] not in {"Buy", "Sell"}:
                    raise Unavailable("invalid execution")
                delta = qty if fill["side"] == "Buy" else -qty
                key = identity(fill["order_id"])
                if fill["order_id"] in owners and candidates[owners[fill["order_id"]]].symbol.value != symbol:
                    raise Unavailable("execution ownership crosses symbols")
                if net == 0 or net * delta > 0:
                    lots[key] = lots.get(key, Decimal(0)) + qty
                elif qty >= abs(net):
                    remainder = qty - abs(net)
                    lots = {key: remainder} if remainder else {}
                    ambiguous_allocation = False
                elif len(lots) == 1 and not ambiguous_allocation:
                    only = next(iter(lots))
                    lots[only] -= qty
                else:
                    ambiguous_allocation = True
                    lots = {}
                net += delta
            if ambiguous_allocation:
                raise Unavailable("partial reduction has ambiguous idea allocation")
            if net != signed_projected:
                raise Unavailable("fills and position projection disagree")
            for key in lots:
                reserve(key, symbol)

        facts["paper_account_version"] = paper_account.version
        facts["working_limits"] = [
            {name: order[name] for name in ("order_id", "symbol", "side", "price", "quantity",
                                           "filled_quantity", "status", "updated_at_ms")}
            for order in working_limits
        ]
        facts["positions"] = [
            {name: position[name] for name in ("symbol", "side", "quantity", "engaged_notional",
                                              "sync_state", "version", "updated_at_ms")}
            for position in projections.values() if _number(position["quantity"]) > 0
        ]
        facts["robot_ideas"] = [
            {"candidate_id": c.candidate_id, "symbol": c.symbol.value,
             "status": c.status, "revision": c.state_revision}
            for c in candidates.values() if "robot:" + c.candidate_id in reservations
        ]
        physical = set(reservations)
        physical_symbols = set(symbols)
        terminal_identities, facts["source_terminal_events"] = _source_terminal_identities(store, account)
        released = []
        for decision in (store.load_robot_auto_decisions(account)
                         if auto_decisions is None else auto_decisions):
            if decision.mode != "SHADOW" or decision.outcome != "ALLOW":
                continue
            linked = [c for c in candidates.values() if c.candidate_id == decision.candidate_ref
                      or c.signal_snapshot.get("source_box_candidate_id") == decision.candidate_ref]
            linked = [c for c in linked if c.status != "BOX_PLAN_ONLY"]
            if len(linked) > 1:
                raise Unavailable("SHADOW selection has ambiguous real handoff")
            if linked:
                c = linked[0]
                key = "robot:" + canonical_owner(c.candidate_id)
                if key in physical:
                    continue  # virtual selection became this same physical idea
                if c.status in {"CLOSED", "EXPIRED", "INVALIDATED"}:
                    if c.symbol.value in symbols:
                        raise Unavailable("terminal SHADOW handoff has unproven position overlap")
                    continue  # physical collector proved no remaining obligation
            if ((decision.candidate_ref, decision.snapshot_sha256) in terminal_identities
                    and decision.symbol.value not in physical_symbols):
                released.append({"candidate_ref": decision.candidate_ref,
                                 "snapshot_sha256": decision.snapshot_sha256,
                                 "symbol": decision.symbol.value})
                continue  # proven source-terminal event, no physical obligation on the symbol
            # No invented expiry or simulated fills; pure SHADOW has no proven release.
            reserve("shadow:" + decision.candidate_ref, decision.symbol.value)
        facts["released_shadow_reservations"] = sorted(
            released, key=lambda item: (item["candidate_ref"], item["snapshot_sha256"]))
        facts.update(available=True, occupied_ro=sum(r["ro"] for r in reservations.values()),
                     occupied_usdt=sum(r["ro"] for r in reservations.values()) * RO_USDT,
                     owned_symbols=sorted(symbols),
                     reservations=sorted(reservations.values(), key=lambda r: r["identity"]))
    except Unavailable as error:
        facts.update(available=False, data_error=str(error))
    except (PersistenceError, sqlite3.Error, ValueError, TypeError, KeyError, ArithmeticError, AttributeError):
        # Do not persist exception strings (paths/secrets) or pretend partial facts are complete.
        facts.update(available=False, data_error="PAPER portfolio facts are incomplete or inconsistent")
    return facts


def _source_terminal_identities(store: SQLiteStore, account: TradingAccountId):
    """All proven (candidate_ref, snapshot_sha256) of this account, or none at all.

    A missing, foreign, incomplete or inconsistent sidecar releases nothing: every
    virtual reservation is kept rather than a partially read subset released.
    """
    path = getattr(store, "path", None)
    if path is None:
        return frozenset(), "ABSENT"
    try:
        identities = load_terminal_identities(source_terminal_events_path(path), account.value)
    except SourceTerminalEventError:
        return frozenset(), "UNAVAILABLE"
    return (frozenset(), "ABSENT") if identities is None else (identities, "AVAILABLE")
