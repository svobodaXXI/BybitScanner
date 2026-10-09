"""Read-only PAPER capital facts for SHADOW, never a trading allocator.

One Robot idea = one full RO. Manual working LIMITs are independent obligations.
Fill identity merges the filled and pending portions; ambiguous reductions are
unknown, never assigned to a convenient lot. Unresolved SHADOW selections stay
reserved across restart/OFF until a linked real idea proves terminal and flat.
"""
from __future__ import annotations

from decimal import Decimal, ROUND_CEILING
import sqlite3

from terminal.domain.models import TradingAccountId
from terminal.persistence.sqlite_store import SQLiteStore, PersistenceError

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


def collect_portfolio_facts(store: SQLiteStore, account: TradingAccountId) -> dict:
    """Caller serializes this read with audit append. No PAPER writes or services."""
    facts = {"available": False, "reference_capital_usdt": 5000,
             "ro_usdt": RO_USDT, "cap_ro": CAP_RO, "new_reserve_ro": 1,
             "deferred_controls": {name: "NOT_EVALUATED" for name in DEFERRED}}
    try:
        paper_account = store.get_paper_account(account)
        if account.value != "paper" or paper_account is None:
            raise Unavailable("PAPER account is unavailable")
        rows = store.load_paper_portfolio_rows(account)
        candidates = {c.candidate_id: c for c in store.load_robot_candidates(account)}
        trades = store.load_open_robot_trades(account)
        orders = {o["order_id"]: o for o in rows["paper_limit_orders"]}
        commands = {c["command_id"]: c for c in rows["trading_commands"]}
        if any(c["current_state"] not in {"filled", "cancelled", "amended", "rejected", "failed"}
               for c in commands.values()):
            raise Unavailable("unfinished command may carry unproven obligations")
        owners = {}
        reservations = {}
        symbols = set()

        def reserve(key, symbol, ro=1):
            previous = reservations.get(key)
            if previous is not None and previous["symbol"] != symbol:
                raise Unavailable("obligation identity crosses symbols")
            reservations[key] = {"identity": key, "symbol": symbol,
                                 "ro": max(ro, previous["ro"] if previous else 0)}
            symbols.add(symbol)

        def own(order_id, candidate_id):
            c = candidates.get(candidate_id)
            if c is None or (order_id in owners and owners[order_id] != candidate_id):
                raise Unavailable("order ownership is ambiguous")
            order = orders.get(order_id)
            if order and order["symbol"] != c.symbol.value:
                raise Unavailable("order ownership crosses symbols")
            owners[order_id] = candidate_id

        for c in candidates.values():
            if c.status in {"APPROVED", "OPEN"}:
                reserve("robot:" + c.candidate_id, c.symbol.value)
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
            reserve("robot:" + trade.candidate_id, trade.symbol.value)

        def identity(order_id):
            return "robot:" + owners[order_id] if order_id in owners else "manual-order:" + order_id

        executions = {}
        for fill in rows["executions"]:
            executions.setdefault(fill["symbol"], []).append(fill)
        projections = {p["symbol"]: p for p in rows["position_projections"]}
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
            if projection and projection["sync_state"] != "synced":
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
            for order in orders.values() if order["status"] in {"open", "partially_filled"}
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
        for decision in store.load_robot_auto_decisions(account):
            if decision.mode != "SHADOW" or decision.outcome != "ALLOW":
                continue
            linked = [c for c in candidates.values() if c.candidate_id == decision.candidate_ref
                      or c.signal_snapshot.get("source_box_candidate_id") == decision.candidate_ref]
            linked = [c for c in linked if c.status != "BOX_PLAN_ONLY"]
            if len(linked) > 1:
                raise Unavailable("SHADOW selection has ambiguous real handoff")
            if linked:
                c = linked[0]
                key = "robot:" + c.candidate_id
                if key in physical:
                    continue  # virtual selection became this same physical idea
                if c.status in {"CLOSED", "EXPIRED", "INVALIDATED"}:
                    if c.symbol.value in symbols:
                        raise Unavailable("terminal SHADOW handoff has unproven position overlap")
                    continue  # physical collector proved no remaining obligation
            # No invented expiry or simulated fills; pure SHADOW has no proven release.
            reserve("shadow:" + decision.candidate_ref, decision.symbol.value)
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
