"""Evidence-backed recovery for pre-D2.3 Robot entry attestations.

This module is deliberately PAPER/persistence-only.  It reconstructs the
canonical ``robot_trades.entry_quantity`` / ``entry_position_version`` pair
from immutable execution evidence and stores a compact audit record in the
existing candidate ``robot_state.execution`` envelope.  It never dispatches,
cancels, amends, or creates an order.

The write helper is a package-internal companion to :mod:`sqlite_store`: it
uses that store's single-writer transaction/connection so the canonical trade
fields and candidate audit record commit atomically without adding a second
schema or ownership model.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from decimal import Decimal
from typing import Mapping, Sequence

from terminal.domain.models import (
    Category,
    Execution,
    OrderSide,
    PositionKey,
    PositionSide,
)
from terminal.persistence.sqlite_store import (
    ConcurrentUpdate,
    PaperProtectionObligationRecord,
    PersistenceError,
    PositionProjectionRecord,
    RobotCandidateRecord,
    RobotRuntimeStateRecord,
    RobotTradeRecord,
    SQLiteStore,
)


LEGACY_ATTESTATION_SOURCE = "execution_ledger_reconstruction_v1"


class LegacyProtectionRecoveryRejected(PersistenceError):
    """Raised when legacy ownership evidence is incomplete or ambiguous."""


@dataclass(frozen=True, slots=True)
class LegacyEntryAttestationProof:
    trade_id: str
    obligation_id: str
    entry_order_id: str
    execution_ids: tuple[str, ...]
    entry_quantity: Decimal
    entry_position_version: int
    average_entry: Decimal


@dataclass(frozen=True, slots=True)
class LegacyEntryAttestationResult:
    trade: RobotTradeRecord
    candidate: RobotCandidateRecord
    created: bool


def _reject(reason: str) -> None:
    raise LegacyProtectionRecoveryRejected(reason)


def _signed_quantity(execution: Execution) -> Decimal:
    quantity = execution.quantity.value
    if quantity <= 0 or execution.price.value <= 0:
        _reject("execution ledger contains non-positive entry evidence")
    return quantity if execution.side is OrderSide.BUY else -quantity


def _candidate_entry_order_id(candidate: RobotCandidateRecord) -> str:
    state = candidate.robot_state
    if not isinstance(state, Mapping):
        _reject("legacy candidate lacks durable Robot state")
    execution = state.get("execution")
    if not isinstance(execution, Mapping):
        _reject("legacy candidate lacks durable execution state")
    order_id = execution.get("limit_order_id")
    if not isinstance(order_id, str) or not order_id.strip():
        _reject("legacy recovery supports only a proven durable LIMIT entry identity")
    return order_id.strip()


def _candidate_first_partial(candidate: RobotCandidateRecord) -> tuple[int, Decimal]:
    """Durable first-partial anchors, required only by the composite shape."""

    state = candidate.robot_state
    execution = state.get("execution") if isinstance(state, Mapping) else None
    if not isinstance(execution, Mapping):
        _reject("composite legacy candidate lacks durable execution state")
    at_ms = execution.get("first_partial_at_ms")
    price = execution.get("first_partial_price")
    if not isinstance(at_ms, int) or isinstance(at_ms, bool) or at_ms < 0:
        _reject("composite legacy recovery requires a durable first partial timestamp")
    if not isinstance(price, str) or not price.strip():
        _reject("composite legacy recovery requires a durable first partial price")
    try:
        parsed = Decimal(price)
    except Exception:
        _reject("durable first partial price is not a valid decimal")
    if parsed <= 0:
        _reject("durable first partial price is not positive")
    return at_ms, parsed


def _prove_composite_topup(
    *,
    trade: RobotTradeRecord,
    candidate: RobotCandidateRecord,
    scoped: Sequence[Execution],
    entry_executions: Sequence[Execution],
    entry_order_id: str,
    expected_side: OrderSide,
    position: PositionProjectionRecord,
) -> tuple[Execution, ...]:
    """Prove the exact Slice A2 shape: one LIMIT partial + one same-side top-up.

    Deliberately not a multi-leg abstraction.  The top-up carries Workspace
    order identity that a manual action would also carry, so ownership is
    locked by durable Robot-authored evidence instead: ``entry_path == "MIXED"``
    (written only by Robot's own trade finalizer), a ledger closed at exactly
    these two executions, ``entry_time_ms`` ordering, and the caller's exact
    VWAP equality against ``trade.average_entry``.  Because the ledger is
    closed, no other candidate/trade can own these executions.
    """

    if len(entry_executions) != 1:
        _reject("composite legacy recovery requires exactly one LIMIT partial execution")
    if len(scoped) != 2:
        _reject("composite legacy recovery requires exactly two executions in symbol history")

    limit_execution = entry_executions[0]
    top_ups = tuple(item for item in scoped if item.order_id.value != entry_order_id)
    if len(top_ups) != 1:
        _reject("composite legacy recovery requires exactly one subsequent top-up execution")
    top_up = top_ups[0]

    if top_up.side is not expected_side:
        _reject("composite top-up execution side does not match Robot direction")
    if top_up.quantity.value <= 0 or top_up.price.value <= 0:
        _reject("composite top-up contains non-positive execution evidence")
    if top_up.exchange_timestamp_ms <= limit_execution.exchange_timestamp_ms:
        _reject("composite top-up does not follow the proven LIMIT partial")
    if top_up.exchange_timestamp_ms > trade.entry_time_ms:
        _reject("composite top-up occurred after durable Robot entry finalization")
    if position.version != 2:
        _reject("composite legacy recovery requires exactly two position mutations")

    first_partial_at_ms, first_partial_price = _candidate_first_partial(candidate)
    if first_partial_price != limit_execution.price.value:
        _reject("durable first partial price does not match the proven LIMIT execution")
    if not (
        limit_execution.exchange_timestamp_ms <= first_partial_at_ms <= trade.entry_time_ms
    ):
        _reject("durable first partial timestamp is inconsistent with the proven entry")

    # Attribution lock: a LIMIT-only entry would have produced a LIMIT-only
    # durable average entry, so an equal value proves the top-up is not owned.
    if limit_execution.price.value == trade.average_entry:
        _reject("LIMIT-only VWAP already equals durable average entry; top-up is not Robot-owned")

    return (limit_execution, top_up)


def _legacy_audit(candidate: RobotCandidateRecord) -> Mapping[str, object] | None:
    state = candidate.robot_state
    if not isinstance(state, Mapping):
        return None
    execution = state.get("execution")
    if not isinstance(execution, Mapping):
        return None
    audit = execution.get("legacy_entry_attestation")
    return audit if isinstance(audit, Mapping) else None


def prove_legacy_entry_attestation(
    *,
    runtime: RobotRuntimeStateRecord,
    trade: RobotTradeRecord,
    candidate: RobotCandidateRecord,
    obligation: PaperProtectionObligationRecord,
    position: PositionProjectionRecord,
    executions: Sequence[Execution],
) -> LegacyEntryAttestationProof:
    """Pure/read-only proof of one pre-D2.3 Robot entry attestation.

    Two historical shapes are supported and no other may be generalized to:
    a single durable ``LIMIT`` entry, and the composite ``MIXED`` shape of one
    LIMIT partial plus exactly one same-side top-up over a ledger closed at
    exactly those two executions (see ``_prove_composite_topup``).

    No state is mutated here.  Ambiguity rejects recovery rather than trying
    to infer ownership from Working Volume, candles, or the current aggregate
    alone.
    """

    if runtime.mode != "ROBOT_RUNNING" or runtime.recovery_status != "RECONCILIATION_REQUIRED":
        _reject("legacy recovery is legal only in ROBOT_RUNNING/RECONCILIATION_REQUIRED")
    if trade.exit_time_ms is not None:
        _reject("legacy Robot trade is already closed")
    if trade.entry_quantity is not None or trade.entry_position_version is not None:
        _reject("legacy recovery requires both canonical entry attestations to be NULL")
    if trade.entry_path not in {"LIMIT", "MIXED"}:
        _reject("legacy recovery supports only durable LIMIT or composite MIXED entry identity")

    if (
        candidate.candidate_id != trade.candidate_id
        or candidate.trading_account_id != trade.trading_account_id
        or candidate.symbol != trade.symbol
        or candidate.status != "OPEN"
    ):
        _reject("legacy Robot candidate scope/lifecycle does not match the open trade")

    if (
        obligation.trade_id != trade.trade_id
        or obligation.trading_account_id != trade.trading_account_id
        or obligation.symbol != trade.symbol
        or obligation.status != "TRIGGERED"
    ):
        _reject("legacy protection obligation scope/lifecycle is not exactly TRIGGERED")

    expected_side = OrderSide.BUY if trade.direction == "LONG" else OrderSide.SELL
    expected_position_side = PositionSide.LONG if trade.direction == "LONG" else PositionSide.SHORT
    if trade.direction not in {"LONG", "SHORT"}:
        _reject("legacy Robot trade direction is unsupported")

    position_key = PositionKey(trade.trading_account_id, Category.LINEAR, trade.symbol, 0)
    if position.position_key != position_key:
        _reject("current position projection scope does not match legacy trade")
    if position.side is not expected_position_side or position.quantity.value <= 0:
        _reject("current position side/quantity does not match legacy Robot direction")
    if position.version < 1:
        _reject("current position version is not authoritative")
    if position.average_entry is None:
        _reject("current position lacks authoritative average entry")

    entry_order_id = _candidate_entry_order_id(candidate)
    scoped = tuple(
        item
        for item in executions
        if item.dedup_key.trading_account_id == trade.trading_account_id
        and item.dedup_key.category is Category.LINEAR
        and item.symbol == trade.symbol
    )
    if any(item.dedup_key.exec_id == obligation.exec_id for item in scoped):
        _reject("stable protection close execution already exists")

    entry_executions = tuple(item for item in scoped if item.order_id.value == entry_order_id)
    if not entry_executions:
        _reject("durable LIMIT entry has no immutable execution evidence")
    if any(item.side is not expected_side for item in entry_executions):
        _reject("durable LIMIT entry execution side does not match Robot direction")
    if any(item.quantity.value <= 0 or item.price.value <= 0 for item in entry_executions):
        _reject("durable LIMIT entry contains non-positive execution evidence")

    first_entry_at = min(item.exchange_timestamp_ms for item in entry_executions)
    if any(item.exchange_timestamp_ms > trade.entry_time_ms for item in entry_executions):
        _reject("entry execution occurred after durable Robot entry time")

    pre_entry_net = Decimal("0")
    for item in scoped:
        if item.exchange_timestamp_ms < first_entry_at:
            pre_entry_net += _signed_quantity(item)
    if pre_entry_net != 0:
        _reject("execution ledger does not prove FLAT immediately before Robot entry")

    if trade.entry_path == "LIMIT":
        for item in scoped:
            if (
                item.exchange_timestamp_ms >= first_entry_at
                and item.order_id.value != entry_order_id
            ):
                _reject("unidentified/manual execution exists after Robot entry began")
        proven_entry = entry_executions
    else:
        proven_entry = _prove_composite_topup(
            trade=trade,
            candidate=candidate,
            scoped=scoped,
            entry_executions=entry_executions,
            entry_order_id=entry_order_id,
            expected_side=expected_side,
            position=position,
        )

    ordered_entry = tuple(
        sorted(
            proven_entry,
            key=lambda item: (item.exchange_timestamp_ms, item.dedup_key.exec_id.value),
        )
    )
    entry_quantity = sum((item.quantity.value for item in ordered_entry), Decimal("0"))
    if entry_quantity <= 0:
        _reject("reconstructed Robot entry quantity is not positive")
    entry_notional = sum(
        (item.price.value * item.quantity.value for item in ordered_entry),
        Decimal("0"),
    )
    average_entry = entry_notional / entry_quantity

    if entry_quantity != position.quantity.value:
        _reject("reconstructed entry quantity does not match current position quantity")
    if entry_quantity != obligation.observed_quantity:
        _reject("reconstructed entry quantity does not match triggered obligation quantity")
    if average_entry != trade.average_entry:
        _reject("reconstructed entry VWAP does not match durable Robot average entry")
    if position.average_entry.value != trade.average_entry:
        _reject("current position average entry does not match durable Robot average entry")

    return LegacyEntryAttestationProof(
        trade_id=trade.trade_id,
        obligation_id=obligation.obligation_id,
        entry_order_id=entry_order_id,
        execution_ids=tuple(item.dedup_key.exec_id.value for item in ordered_entry),
        entry_quantity=entry_quantity,
        entry_position_version=position.version,
        average_entry=average_entry,
    )


def _audit_matches_existing(
    audit: Mapping[str, object] | None,
    *,
    client_action_id: str,
    trade: RobotTradeRecord,
    obligation_id: str,
) -> bool:
    if audit is None:
        return False
    return (
        audit.get("source") == LEGACY_ATTESTATION_SOURCE
        and audit.get("client_action_id") == client_action_id
        and audit.get("trade_id") == trade.trade_id
        and audit.get("obligation_id") == obligation_id
        and audit.get("entry_quantity") == str(trade.entry_quantity)
        and audit.get("entry_position_version") == trade.entry_position_version
    )


def attest_legacy_robot_entry(
    store: SQLiteStore,
    *,
    trade_id: str,
    obligation_id: str,
    client_action_id: str,
    authorized_at_ms: int,
) -> LegacyEntryAttestationResult:
    """Atomically persist one proven legacy canonical entry attestation.

    This function has no execution port and therefore cannot create a Market
    side effect.  Replaying the same durable client action is idempotent;
    conflicting reuse or any ownership ambiguity fails closed.
    """

    if not isinstance(trade_id, str) or not trade_id.strip():
        raise ValueError("trade_id must be non-empty")
    if not isinstance(obligation_id, str) or not obligation_id.strip():
        raise ValueError("obligation_id must be non-empty")
    if not isinstance(client_action_id, str) or not client_action_id.strip():
        raise ValueError("client_action_id must be non-empty")
    if not isinstance(authorized_at_ms, int) or isinstance(authorized_at_ms, bool) or authorized_at_ms < 0:
        raise ValueError("authorized_at_ms must be a non-negative integer")

    trade_id = trade_id.strip()
    obligation_id = obligation_id.strip()
    client_action_id = client_action_id.strip()
    store._assert_owner()  # package-internal single-writer boundary

    with store._transaction():  # canonical fields + audit commit or roll back together
        trade = store.get_robot_trade(trade_id)
        if trade is None:
            _reject("legacy Robot trade does not exist")
        candidate = store.get_robot_candidate(trade.candidate_id)
        if candidate is None:
            _reject("legacy Robot candidate does not exist")

        target_audit = _legacy_audit(candidate)
        for other in store.load_robot_candidates(trade.trading_account_id):
            audit = _legacy_audit(other)
            if audit is None or audit.get("client_action_id") != client_action_id:
                continue
            if (
                other.candidate_id != candidate.candidate_id
                or audit.get("trade_id") != trade_id
                or audit.get("obligation_id") != obligation_id
            ):
                _reject("legacy recovery client_action_id conflicts with another durable target")

        both_present = trade.entry_quantity is not None and trade.entry_position_version is not None
        exactly_one_present = (trade.entry_quantity is None) != (trade.entry_position_version is None)
        if both_present:
            if _audit_matches_existing(
                target_audit,
                client_action_id=client_action_id,
                trade=trade,
                obligation_id=obligation_id,
            ):
                return LegacyEntryAttestationResult(trade=trade, candidate=candidate, created=False)
            _reject("canonical entry attestation already exists without this legacy recovery action")
        if exactly_one_present:
            _reject("partial canonical entry attestation is not legacy-recovery eligible")

        runtime = store.get_robot_runtime_state(trade.trading_account_id)
        if runtime is None:
            _reject("Robot runtime state is unavailable")
        obligation = store.get_paper_protection_obligation_for_trade(trade_id)
        if obligation is None or obligation.obligation_id != obligation_id:
            _reject("target protection obligation does not match legacy Robot trade")
        position = store.get_position_projection(
            PositionKey(trade.trading_account_id, Category.LINEAR, trade.symbol, 0)
        )
        if position is None:
            _reject("current PAPER position projection is unavailable")

        proof = prove_legacy_entry_attestation(
            runtime=runtime,
            trade=trade,
            candidate=candidate,
            obligation=obligation,
            position=position,
            executions=store.load_executions(),
        )

        state = dict(candidate.robot_state or {})
        execution_state = dict(state.get("execution") or {})
        if "legacy_entry_attestation" in execution_state:
            _reject("candidate already contains conflicting legacy entry attestation metadata")
        execution_state["legacy_entry_attestation"] = {
            "source": LEGACY_ATTESTATION_SOURCE,
            "client_action_id": client_action_id,
            "trade_id": trade_id,
            "obligation_id": obligation_id,
            "entry_order_id": proof.entry_order_id,
            "execution_ids": list(proof.execution_ids),
            "entry_quantity": str(proof.entry_quantity),
            "entry_position_version": proof.entry_position_version,
            "average_entry": str(proof.average_entry),
            "authorized_at_ms": authorized_at_ms,
        }
        state["execution"] = execution_state
        state_json = json.dumps(
            state,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )

        trade_cursor = store._connection.execute(
            """UPDATE robot_trades
               SET entry_quantity=?, entry_position_version=?, version=version+1, updated_at_ms=?
               WHERE trade_id=? AND exit_time_ms IS NULL
                 AND entry_quantity IS NULL AND entry_position_version IS NULL
                 AND updated_at_ms<=?""",
            (
                str(proof.entry_quantity),
                proof.entry_position_version,
                authorized_at_ms,
                trade_id,
                authorized_at_ms,
            ),
        )
        if trade_cursor.rowcount != 1:
            raise ConcurrentUpdate("legacy Robot trade changed before attestation commit")

        candidate_cursor = store._connection.execute(
            """UPDATE robot_candidates
               SET robot_state_json=?, state_revision=state_revision+1, updated_at_ms=?
               WHERE candidate_id=? AND status='OPEN' AND state_revision=?
                 AND updated_at_ms<=?""",
            (
                state_json,
                authorized_at_ms,
                candidate.candidate_id,
                candidate.state_revision,
                authorized_at_ms,
            ),
        )
        if candidate_cursor.rowcount != 1:
            raise ConcurrentUpdate("legacy Robot candidate changed before attestation commit")

    persisted_trade = store.get_robot_trade(trade_id)
    persisted_candidate = store.get_robot_candidate(candidate.candidate_id)
    if persisted_trade is None or persisted_candidate is None:
        raise PersistenceError("legacy entry attestation disappeared after commit")
    return LegacyEntryAttestationResult(
        trade=persisted_trade,
        candidate=persisted_candidate,
        created=True,
    )
