"""Verified, opt-in frozen MIRROR/L-shape/Wedge/Box reentry facts.

Only a caller in canonical Robot Admission may turn the pure evidence into
an attempt reservation. No second order or financial journal is introduced.
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
import hashlib
import json
from typing import Mapping, Any

import robot_l_shape
import robot_state_machine
from scanner_geometry_cursor import CURSOR_VERSION
from terminal.application.robot_reentry_thesis import verified_same_thesis
from terminal.application.robot_admission import RobotReentryAdmissionRequest
from terminal.application.robot_portfolio import RO_USDT
from terminal.domain.models import TradingAccountId, Symbol
from terminal.persistence.sqlite_store import SQLiteStore, PersistenceError


# Conservative adverse execution allowance ON TOP of the already charged
# two-sided PAPER maker/taker fee; this is a risk reservation, not fill PnL.
REENTRY_ADVERSE_SLIPPAGE_FRACTION = Decimal("0.002")
CAMPAIGN_MAX_TRADES = 3


@dataclass(frozen=True, slots=True)
class ProvenPatternEntry:
    pattern: str
    direction: str
    confirmed_at_ms: int
    risk_reservation_usdt: Decimal


def proven_pattern_entry(
    snapshot: Mapping[str, Any], *,
    now_ms: int,
) -> ProvenPatternEntry | None:
    """Only existing, independently confirmed closed pattern evidence counts."""
    if type(now_ms) is not int or now_ms < 0:
        return None
    if not isinstance(snapshot, Mapping):
        return None
    pattern = str(snapshot.get("pattern", "")).strip()
    if pattern == "IKIGAI_BOX":
        # This is the immutable *canonical Box plan*, never a mutable scanner
        # observation. The source reader verifies its hash and BOX_PLAN_ONLY
        # state; the owning admission validates it again before handoff.
        identity, plan = snapshot.get("identity"), snapshot.get("plan")
        if not isinstance(identity, Mapping) or not isinstance(plan, Mapping):
            return None
        timeframe = str(identity.get("timeframe", ""))
        if not timeframe.isdecimal() or int(timeframe) not in (1, 5):
            return None
        interval = int(timeframe) * 60_000
        decision = snapshot.get("decision_time_ms")
        direction = str(identity.get("direction", ""))
        if (type(decision) is not int or decision <= 0
                or decision % interval != 0
                or direction not in {"LONG", "SHORT"}
                or plan.get("direction") != direction
                or snapshot.get("environment") != "PAPER"
                or snapshot.get("execution_authorized") is not False
                or snapshot.get("contract_version") != 1
                or snapshot.get("attempt") != 1
                or decision + interval > now_ms):
            return None
        try:
            full = plan["full_position"]
            risk_full = Decimal(str(full["net_stop_loss"]))
            risk_partial = Decimal(str(plan["partial_fill_loss_upper_bound"]))
            qty = Decimal(str(full["quantity"]))
            avg = Decimal(str(full["average_entry"]))
            minimum_rr = Decimal(str(plan["minimum_partial_fill_rr"]))
            if (not all(v.is_finite() and v > 0 for v in (
                risk_full, risk_partial, qty, avg, minimum_rr
            )) or risk_partial < risk_full):
                return None
            # Box net_stop_loss already accounts for planned fees. Reserve
            # additional adverse slippage on the frozen entire position,
            # not a flat 250-USDT RO which can understate multi-grid risk.
            risk = risk_partial + qty * avg * REENTRY_ADVERSE_SLIPPAGE_FRACTION
            if not risk.is_finite():
                return None
            return ProvenPatternEntry(
                pattern=pattern, direction=direction,
                confirmed_at_ms=decision + interval,
                risk_reservation_usdt=risk,
            )
        except (KeyError, ValueError, TypeError, ArithmeticError):
            return None
    if pattern in {"Falling Wedge", "Rising Wedge"}:
        # The frozen 1m Scanner cursor identifies an actual source candle;
        # the Wedge Robot owns later breakout/retest/entry and STOP/TAKE.
        # Never use an envelope arrival timestamp as candle confirmation.
        cursor = snapshot.get("scanner_geometry_cursor")
        source_tf = str(snapshot.get("scanner_source_timeframe") or "1")
        if source_tf not in {"1", "5"}:
            return None
        geometry = snapshot.get("robot_geometry") if source_tf == "5" else (
            snapshot.get("robot_geometry") or snapshot.get("geometry")
        )
        if not isinstance(cursor, Mapping) or not isinstance(geometry, Mapping):
            return None
        if source_tf == "5" and (
            geometry.get("robot_coordinate_timeframe") != "1"
            or geometry.get("scanner_source_timeframe") != "5"
            or snapshot.get("robot_handoff_ready") is not True
        ):
            return None
        stamp = cursor.get("source_candle_time_ms")
        index = cursor.get("geometry_index")
        if (cursor.get("version") != CURSOR_VERSION or cursor.get("timeframe") != "1"
                or type(stamp) is not int or stamp <= 0 or stamp % 60_000 != 0
                or type(index) is not int or index < 0
                or geometry.get("current_index") != index):
            return None
        confirmation = stamp + 60_000
        if confirmation > now_ms:
            return None
        try:
            robot_state_machine.initialize_state({
                "candidate_id": "reentry-wedge-proof",
                "status": "APPROVED", "timeframe": "1",
                "signal_snapshot": dict(snapshot),
            })
        except (ValueError, TypeError, robot_state_machine.RobotStateMachineError):
            return None
        return ProvenPatternEntry(
            pattern=pattern,
            direction="LONG" if pattern == "Falling Wedge" else "SHORT",
            confirmed_at_ms=confirmation,
            risk_reservation_usdt=Decimal(RO_USDT) * (
                Decimal("0.015") + Decimal("2") * robot_l_shape.PAPER_ROBOT_FEE_RATE
                + REENTRY_ADVERSE_SLIPPAGE_FRACTION
            ),
        )
    if snapshot.get("robot_handoff_ready") is not True:
        return None
    if not robot_l_shape.is_l_shape_snapshot(snapshot):
        return None
    try:
        terms = robot_l_shape.frozen_terms(snapshot)
        # For MIRROR, initialize_state verifies that the NEXT candle closed
        # exactly one source-TF later with a supported Nison formation.
        if robot_l_shape.is_mirror_snapshot(snapshot):
            robot_l_shape.initialize_state({
                "candidate_id": "reentry-proof", "status": "APPROVED",
                "signal_snapshot": dict(snapshot),
            })
            confirmation = snapshot["mirror_entry"]["confirmation"]
            confirmed_at = int(confirmation["close_time_ms"])
        else:
            # L-shape's breakout_time_ms identifies the open of the frozen
            # breakout candle, confirmed only after its complete TF duration.
            confirmed_at = terms.breakout_time_ms + int(terms.source_timeframe) * 60_000
        if confirmed_at > now_ms or confirmed_at <= 0:
            return None
        entry = terms.reference
        stop = terms.stop
        # RO=250 USDT per canonical Robot capital unit; reserve the maximum
        # planned geometric stop loss plus fees and adverse fill allowance.
        base = Decimal(RO_USDT)
        # Shared non-Box Robot admission enforces its 1.5% maximum STOP
        # distance. Reserve that worst permitted geometry rather than the
        # unbuffered MIRROR STOP (the actual Robot adds one instrument tick).
        distance = max(abs(entry - stop) / entry, Decimal("0.015"))
        risk = base * (
            distance + Decimal("2") * robot_l_shape.PAPER_ROBOT_FEE_RATE
            + REENTRY_ADVERSE_SLIPPAGE_FRACTION
        )
        if not risk.is_finite() or risk <= 0:
            return None
        return ProvenPatternEntry(
            pattern=str(snapshot["pattern"]), direction=terms.direction,
            confirmed_at_ms=confirmed_at, risk_reservation_usdt=risk,
        )
    except (ValueError, TypeError, KeyError, robot_l_shape.RobotLShapeError):
        return None


def automatic_reentry_proposal(
    store: SQLiteStore, account: TradingAccountId, *,
    candidate_id: str,
    symbol: Symbol,
    snapshot: Mapping[str, Any],
    now_ms: int,
) -> RobotReentryAdmissionRequest | None:
    """Select one unambiguous existing STOP campaign, or register a first.

    This opt-in adapter is only called INSIDE the existing Robot admission
    transaction, after normal PAPER_AUTO policy ALLOW. It does not use
    symbol-only matching: both direction and the uniquely outstanding
    *durable* stopped campaign must agree; multiple campaigns fail closed.
    An older TAKE, cancellation or unresolved attempt never grants a retry.
    """
    if not store.in_robot_admission_transaction():
        raise PersistenceError("automatic reentry requires Robot admission transaction")
    evidence = proven_pattern_entry(snapshot, now_ms=now_ms)
    if evidence is None or not candidate_id:
        return None
    declared_symbol = (snapshot.get("identity") or {}).get("symbol") if (
        evidence.pattern == "IKIGAI_BOX" and isinstance(snapshot.get("identity"), Mapping)
    ) else snapshot.get("symbol")
    if symbol.value != str(declared_symbol):
        return None
    matches = store._connection.execute(
        """SELECT campaign_id, frozen_thesis_sha256 FROM robot_reentry_campaigns
           WHERE trading_account_id=? AND symbol=? AND direction=?
           ORDER BY created_at_ms DESC""",
        (account.value, symbol.value, evidence.direction),
    ).fetchall()
    # Only the latest campaign is eligible. Older campaigns can exist after
    # independently completed TAKE closures; they are historical Diary rows.
    if matches:
        parent = matches[0]
        rows = store._connection.execute(
            """SELECT a.candidate_id, a.attempt_index,
                      t.exit_reason, t.exit_time_ms, o.exec_id
               FROM robot_reentry_attempts a
               LEFT JOIN robot_trades t ON t.candidate_id=a.candidate_id
                                      AND t.trading_account_id=a.trading_account_id
               LEFT JOIN paper_protection_obligations o ON o.trade_id=t.trade_id
               WHERE a.trading_account_id=? AND a.campaign_id=?
               ORDER BY a.attempt_index""",
            (account.value, parent["campaign_id"]),
        ).fetchall()
        if not rows:
            raise PersistenceError("campaign has no original attempt")
        last = rows[-1]
        if last["exit_time_ms"] is None or evidence.confirmed_at_ms <= int(last["exit_time_ms"]):
            raise PersistenceError("new pattern was not confirmed after previous close")
        if last["exit_reason"] == "STOP":
            if last["exec_id"] is None:
                raise PersistenceError("STOP protection execution not proven")
            previous = store.get_robot_candidate(last["candidate_id"])
            if (previous is None
                    or previous.trading_account_id != account
                    or previous.symbol != symbol
                    or not verified_same_thesis(
                        previous_candidate_id=previous.candidate_id,
                        previous_snapshot_sha256=previous.snapshot_sha256,
                        previous_snapshot=previous.signal_snapshot,
                        new_snapshot=snapshot,
                        direction=evidence.direction,
                    )):
                raise PersistenceError("cross-pattern frozen thesis lineage unproven")
            if len(rows) >= CAMPAIGN_MAX_TRADES:
                raise PersistenceError("STOP reentry campaign exhausted")
            return RobotReentryAdmissionRequest(
                campaign_id=parent["campaign_id"], direction=evidence.direction,
                frozen_thesis_sha256=parent["frozen_thesis_sha256"],
                reserved_risk_usdt=evidence.risk_reservation_usdt,
                previous_stop_exec_id=last["exec_id"],
                confirmed_at_ms=evidence.confirmed_at_ms,
                strategy_confirmation_proven=True,
            )
        # A verified TAKE closes the old directional campaign; a later new
        # formation starts a NEW independently frozen thesis and risk budget.
        if last["exit_reason"] != "TAKE":
            raise PersistenceError("previous campaign is not safely terminal")
    else:
        # A pre-v26 Wedge/Box STOP is NOT implicitly a fresh first attempt:
        # without durable lineage it could bypass the owner's 1+2 cap.
        prior = store._connection.execute(
            """SELECT exit_reason FROM robot_trades
               WHERE trading_account_id=? AND symbol=? AND direction=?
                 AND exit_time_ms IS NOT NULL
               ORDER BY exit_time_ms DESC LIMIT 1""",
            (account.value, symbol.value, evidence.direction),
        ).fetchone()
        if prior is not None and prior["exit_reason"] == "STOP":
            raise PersistenceError("unlinked prior STOP requires canonical lineage proof")
    # New independent idea only when the last campaign closed at TAKE or no
    # unlinked STOP exists. Freeze the budget for all three allowed attempts.
    origin = json.dumps(
        [account.value, symbol.value, evidence.direction, candidate_id],
        separators=(",", ":"), ensure_ascii=False,
    )
    digest = hashlib.sha256(origin.encode("utf-8")).hexdigest()
    return RobotReentryAdmissionRequest(
        campaign_id="reentry-" + digest,
        direction=evidence.direction,
        frozen_thesis_sha256=digest,
        reserved_risk_usdt=evidence.risk_reservation_usdt,
        original_risk_budget_usdt=evidence.risk_reservation_usdt * CAMPAIGN_MAX_TRADES,
        strategy_confirmation_proven=True,
    )
