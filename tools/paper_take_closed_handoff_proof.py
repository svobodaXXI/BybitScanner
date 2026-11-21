"""Read-only proof for an already-FLAT legacy Robot APPROVED + PAPER TAKE.

This is a release *precondition*, not a close, candidate repair, admission
grant, or authority to signal a process.  Proof uses the installed PAPER
ledger and independent HTTP identity snapshots inside a single transaction.
Unknown facts fail closed.  The actual reconciliation belongs to the newer
PAPER owner after an explicitly authorized, separately protected handoff.
"""
from __future__ import annotations

from decimal import Decimal, InvalidOperation
from pathlib import Path
import sqlite3
from collections.abc import Mapping

from tools.flat_paper_recovery_gate import FlatRecoveryBlocked, _require


PROOF_LABEL = "ONE_APPROVED_PAPER_TAKE_FLAT_IMMUTABLE_V1"


def prove_take_closed_approved(
    conn: sqlite3.Connection, *, expected_identity: str, expected_build_sha: str,
    backend: dict, scanner: dict, autopilot: dict, protection: dict,
) -> str:
    """Prove one exact legacy TAKE-closed owner; never mutate SQLite or trade."""
    from terminal.application.robot_late_admission_market import restore_late_admission_market_plan
    from terminal.domain.models import Category, PositionKey, PositionSide, OrderSide, Symbol, TradingAccountId
    from terminal.persistence.sqlite_store import SQLiteStore

    _require(conn.in_transaction
             and tuple(conn.execute("PRAGMA query_only").fetchone()) == (1,),
             "take_closed_requires_readonly_snapshot")
    _require(
        backend.get("ok") is True
        and backend.get("component") == "paper_backend"
        and backend.get("mode") == "paper"
        and backend.get("paper_live_safe") is True
        and backend.get("database_identity") == expected_identity
        and backend.get("build_sha") == expected_build_sha
        and isinstance(backend.get("process_instance_id"), str)
        and bool(backend["process_instance_id"].strip()),
        "take_closed_backend_identity_unproven",
    )
    _require(scanner.get("mode") == "SCANNER_STOPPED"
             and scanner.get("worker_quiescent") is not False
             and autopilot.get("mode") == "OFF",
             "take_closed_admission_not_frozen")
    _require(protection.get("healthy") is True
             and protection.get("unhealthy_symbols") == {}
             and protection.get("covered_symbols") == []
             and protection.get("armed_symbols") == []
             and protection.get("coverage_roles") == {},
             "take_closed_protection_not_quiescent")
    ingress = protection.get("ingress")
    if ingress is not None:
        _require(isinstance(ingress, dict)
                 and type(ingress.get("current_pending")) is int
                 and ingress["current_pending"] == 0,
                 "take_closed_ingress_not_quiescent")
    _require(tuple(conn.execute("PRAGMA quick_check").fetchone()) == ("ok",),
             "take_closed_database_integrity_unproven")
    _require(conn.execute("PRAGMA foreign_key_check").fetchone() is None,
             "take_closed_database_foreign_key_conflict")

    runtime = conn.execute(
        "SELECT mode,recovery_status FROM robot_runtime_state "
        "WHERE trading_account_id='paper'"
    ).fetchall()
    scanner_rows = conn.execute(
        "SELECT mode FROM scanner_runtime_state WHERE trading_account_id='paper'"
    ).fetchall()
    autopilot_rows = conn.execute(
        "SELECT mode FROM robot_autopilot_state WHERE trading_account_id='paper'"
    ).fetchall()
    _require(len(runtime) == 1 and tuple(runtime[0]) ==
             ("ROBOT_RUNNING", "RECONCILIATION_REQUIRED")
             and len(scanner_rows) == 1 and tuple(scanner_rows[0]) == ("SCANNER_STOPPED",)
             and len(autopilot_rows) == 1 and tuple(autopilot_rows[0]) == ("OFF",),
             "take_closed_durable_admission_unproven")

    positions = conn.execute(
        "SELECT symbol,side,quantity,sync_state FROM position_projections "
        "WHERE trading_account_id='paper'"
    ).fetchall()
    _require(bool(positions), "take_closed_positions_missing")
    for symbol, side, raw, sync in positions:
        try:
            amount = Decimal(str(raw))
        except (InvalidOperation, ValueError, TypeError) as exc:
            raise FlatRecoveryBlocked("take_closed_position_invalid") from exc
        _require(bool(symbol) and side == "Flat" and amount.is_finite()
                 and amount == 0 and sync in ("synced", "synchronized"),
                 "take_closed_account_not_flat")

    # Prove EVERY active candidate, without a fixed count. Exactly one
    # immutable TAKE-closed owner may cross the exceptional handoff. Every
    # other owner must be independently proven never traded by the existing
    # durable ledger predicate. Unknown evidence blocks the WHOLE release;
    # neither admission nor a candidate status is changed here.
    active = conn.execute(
        "SELECT candidate_id,symbol,status,approved_at_ms "
        "FROM robot_candidates WHERE trading_account_id='paper' "
        "AND (status IS NULL OR status NOT IN "
        "('BOX_PLAN_ONLY','CLOSED','EXPIRED','INVALIDATED'))"
    ).fetchall()
    _require(bool(active)
             and all(status == "APPROVED"
                     and isinstance(cid, str) and bool(cid)
                     and isinstance(name, str) and bool(name)
                     and type(approved) is int and approved > 0
                     for cid, name, status, approved in active),
             "take_closed_owner_set_unproven")

    conn.row_factory = sqlite3.Row
    store = SQLiteStore(conn, Path("/readonly-take-closed-proof"), 5000)
    account = TradingAccountId("paper")
    candidates = []
    for owner_id, owner_symbol, _, owner_approved in active:
        record = store.get_robot_candidate(owner_id)
        _require(record is not None
                 and record.trading_account_id == account
                 and record.symbol.value == owner_symbol
                 and record.status == "APPROVED"
                 and record.approved_at_ms == owner_approved,
                 "take_closed_active_owner_identity_unproven")
        candidates.append(record)

    def _is_legacy_take_owner(record) -> bool:
        state = record.robot_state
        execution = state.get("execution") if isinstance(state, Mapping) else None
        return (isinstance(execution, Mapping)
                and execution.get("entry_mode") == "LATE_ADMISSION_MARKET"
                and execution.get("emergency_close_pending") is True)

    take_owners = [record for record in candidates if _is_legacy_take_owner(record)]
    _require(len(take_owners) == 1, "take_closed_original_owner_not_unique")
    candidate = take_owners[0]
    cid, name, approved = (
        candidate.candidate_id, candidate.symbol.value, candidate.approved_at_ms
    )
    _require(sum(item[0] == name for item in positions) == 1,
             "take_closed_symbol_projection_ambiguous")

    for other in candidates:
        if other.candidate_id == cid:
            continue
        other_state = other.robot_state
        other_execution = (other_state.get("execution")
                           if isinstance(other_state, Mapping) else None)
        _require(
            other.symbol != candidate.symbol
            and (other_execution is None
                 or (isinstance(other_execution, Mapping)
                     and other_execution.get("emergency_close_pending") is not True
                     and other_execution.get("emergency_close_intent") is None
                     and other_execution.get("emergency_close_outcome") is None
                     and other_execution.get("protected_postfill_recovery") is None))
            and store.prove_approved_candidate_never_traded(other),
            "take_closed_other_owner_not_proven_never_traded",
        )
    for table, condition in (
        ("robot_trades", "exit_time_ms IS NULL"),
        ("paper_limit_orders", "status IS NULL OR status NOT IN ('filled','cancelled')"),
        ("trading_commands", "current_state IS NULL OR current_state NOT IN "
         "('filled','cancelled','amended','rejected','failed','owner_attested_closed')"),
        ("paper_protection_obligations", "status IS NULL OR status != 'RESOLVED'"),
        ("reconciliation_checkpoints", "completed_at_ms IS NULL"),
    ):
        _require(conn.execute(
            f"SELECT 1 FROM {table} WHERE trading_account_id='paper' "
            f"AND ({condition}) LIMIT 1"
        ).fetchone() is None, "take_closed_unfinished_" + table)
    _require(conn.execute(
        "SELECT 1 FROM robot_trades WHERE trading_account_id='paper' "
        "AND candidate_id=? LIMIT 1", (cid,),
    ).fetchone() is None, "take_closed_duplicate_trade")

    symbol = Symbol(name)
    position = store.get_position_projection(PositionKey(account, Category.LINEAR, symbol, 0))
    _require(candidate is not None and candidate.trading_account_id == account
             and candidate.status == "APPROVED" and candidate.symbol == symbol
             and candidate.approved_at_ms == approved
             and position is not None and position.side is PositionSide.FLAT
             and position.quantity.value == 0 and position.version == 2
             and store.get_protection_projection(
                 PositionKey(account, Category.LINEAR, symbol, 0)) is None,
             "take_closed_candidate_or_flat_projection_unproven")
    state = candidate.robot_state
    execution = state.get("execution") if isinstance(state, Mapping) else None
    _require(isinstance(execution, Mapping)
             and state.get("phase") == "RETEST_DETECTED"
             and state.get("direction") in ("LONG", "SHORT")
             and candidate.signal_snapshot.get("pattern") in ("Rising Wedge", "Falling Wedge")
             and execution.get("entry_mode") == "LATE_ADMISSION_MARKET"
             and execution.get("emergency_close_pending") is True
             and execution.get("emergency_close_intent") is None
             and execution.get("emergency_close_outcome") is None
             and "emergency_closed_at_ms" not in execution
             and "post_fill_policy_exception" not in execution
             and isinstance(execution.get("late_market_intent"), Mapping)
             and isinstance(execution.get("protection_failure"), str)
             and execution["protection_failure"].startswith("POST_FILL_NET_RR_BELOW_2 rr="),
             "take_closed_legacy_intent_unproven")
    try:
        persisted_rr = Decimal(execution["protection_failure"].split(" rr=", 1)[1])
        planned_qty = Decimal(str(execution["late_market_intent"]["normalized_quantity"]))
        market = restore_late_admission_market_plan(execution["late_market_intent"])
    except (InvalidOperation, TypeError, ValueError, KeyError, IndexError, AttributeError) as exc:
        raise FlatRecoveryBlocked("take_closed_market_identity_unproven") from exc
    direction = state["direction"]
    expected_entry = OrderSide.SELL if direction == "SHORT" else OrderSide.BUY
    expected_exit = OrderSide.BUY if direction == "SHORT" else OrderSide.SELL
    _require(persisted_rr.is_finite() and Decimal("0") < persisted_rr < Decimal("2")
             and planned_qty.is_finite() and planned_qty > 0
             and market.candidate_id == cid
             and market.request.symbol == name
             and market.direction == direction
             and market.request.side is expected_entry,
             "take_closed_frozen_plan_mismatch")

    command = store.get_command(market.identity.command_id)
    _require(command is not None and command.trading_account_id == account
             and command.symbol == symbol and command.category is Category.LINEAR
             and command.position_idx == 0
             and command.command_kind == "create_market"
             and command.current_state.value == "filled"
             and command.side is expected_entry
             and command.exchange_order_id is not None
             and command.order_link_id == market.identity.order_link_id
             and approved <= command.created_at_ms
             and type(execution.get("emergency_close_attempted_at_ms")) is int
             and command.updated_at_ms <= execution["emergency_close_attempted_at_ms"],
             "take_closed_original_market_command_unproven")
    commands = store.load_commands_for_symbol_since(account, symbol, approved)
    _require(len(commands) == 1 and commands[0].command_id == command.command_id
             and not store.load_active_robot_entry_orders(account, symbol)
             and not store.load_active_paper_limits(account, symbol)
             and not store.load_open_robot_trades(account)
             and not store.load_unresolved_paper_protection_obligations(account),
             "take_closed_foreign_or_pending_work")

    fills = store.load_executions_for_symbol(account, symbol)
    _require(len(fills) == 2, "take_closed_exactly_two_fills_required")
    entry, closing = fills
    owned = store.load_executions_for_order(account, command.exchange_order_id)
    suffix = closing.order_id.value.removeprefix("paper-take-order-")
    _require(
        len(owned) == 1 and owned[0] == entry
        and entry.order_id == command.exchange_order_id
        and entry.side is expected_entry and closing.side is expected_exit
        and entry.symbol == closing.symbol == symbol
        and entry.dedup_key.trading_account_id == account
        and closing.dedup_key.trading_account_id == account
        and entry.dedup_key.category is Category.LINEAR
        and closing.dedup_key.category is Category.LINEAR
        and entry.quantity.value == closing.quantity.value == planned_qty
        and entry.price.value > 0 and closing.price.value > 0
        and entry.fee.is_finite() and closing.fee.is_finite()
        and entry.fee >= 0 and closing.fee >= 0
        and approved <= entry.exchange_timestamp_ms < closing.exchange_timestamp_ms
        and position.updated_at_ms == closing.exchange_timestamp_ms
        and closing.order_id.value == "paper-take-order-" + suffix
        and len(suffix) == 64 and all(ch in "0123456789abcdef" for ch in suffix)
        and closing.dedup_key.exec_id.value == "paper-take-exec-" + suffix,
        "take_closed_immutable_entry_take_lineage_unproven",
    )
    return PROOF_LABEL
