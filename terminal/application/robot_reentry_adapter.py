"""Trusted, opt-in reentry evidence from actual MIRROR/L-shape frozen terms.

Reuses the existing pattern adapter and Robot's 250-USDT PAPER risk unit.
No fabricated STOP, confirmation, strategy, or source pattern metadata.
Wedge and Box require separate verified entry-ready/financial adapters.
This module ONLY creates an admission proposal; no order submission.
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
import hashlib
import json
from typing import Mapping, Any

import robot_l_shape
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
    if evidence is None or not candidate_id or symbol.value != str(snapshot.get("symbol")):
        return None
    matches = store._connection.execute(
        """SELECT campaign_id, frozen_thesis_sha256 FROM robot_reentry_campaigns
           WHERE trading_account_id=? AND symbol=? AND direction=?
           ORDER BY created_at_ms DESC""",
        (account.value, symbol.value, evidence.direction),
    ).fetchall()
    if len(matches) > 1:
        raise PersistenceError("ambiguous active reentry campaign lineage")
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
        # Terminal TAKE ends the directional campaign. No new attempt is
        # attached and no risk budget is silently reset.
        if last["exit_reason"] == "TAKE":
            return None
        if (last["exit_reason"] != "STOP" or last["exit_time_ms"] is None
                or last["exec_id"] is None or
                evidence.confirmed_at_ms <= int(last["exit_time_ms"])):
            raise PersistenceError("new pattern is not confirmed after reconciled STOP")
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
    # New independent idea, no previous outstanding reentry campaign. Freeze
    # all possible STOP-risk across the initial attempt and two retries.
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
