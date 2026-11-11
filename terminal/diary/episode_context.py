"""Optional read-only, exact-ID D2 context for a selected PAPER trade episode.

No guessed signal matches by symbol/time. D2's setup-instance link is the
ONLY supported join. D2 events are research decision observations, NOT the
complete Robot runtime journal. Feature/risk snapshot references are NOT
signal geometry. Never create, migrate or write a D2/PAPER database here.
"""
from __future__ import annotations

import sqlite3
from contextlib import closing
from pathlib import Path

from .decision_models import DecisionEventKind, SetupInstanceId
from .decision_store import DiaryDecisionStore, DiaryLinkageError, SCHEMA_VERSION
from .models import TradeEpisodeId


def _unproven(status: str) -> dict[str, object]:
    return {
        "status": status,
        "source": "TRADING_DIARY_D2",
        "geometry_status": "NOT_EXPORTED",
        "decision_scope": "D2_OBSERVATIONS_NOT_ROBOT_RUNTIME_LOG",
    }


def project_episode_d2_context_read_only(
    db_path: str | Path | None, *, trade_episode_id: str,
    account_id: str, symbol: str, side: str, opening_controller: str,
) -> dict[str, object]:
    """Read a pre-existing D2 link using SQLite read-only and an atomic D2 view.

    This independent D2 snapshot is NOT atomic with the PAPER executions
    snapshot; returned identities must match the selected episode explicitly.
    """
    if account_id != "paper" or side not in {"LONG", "SHORT"}:
        raise ValueError("unsupported_d2_episode_scope")
    if opening_controller not in {"ROBOT", "MANUAL"}:
        raise ValueError("unproven_opening_controller")
    if db_path is None:
        return _unproven("D2_STORE_ABSENT")
    path = Path(db_path)
    if not path.exists():
        return _unproven("D2_STORE_ABSENT")
    if not path.is_file():
        return _unproven("EVIDENCE_UNAVAILABLE")
    try:
        # The regular DiaryDecisionStore.open() initializes schemas and enters
        # a writer transaction. It is intentionally NOT used for this GET.
        with closing(sqlite3.connect(path.resolve().as_uri() + "?mode=ro", uri=True, timeout=0.5)) as connection:
            connection.row_factory = sqlite3.Row
            connection.execute("PRAGMA query_only=ON")
            connection.execute("BEGIN")
            version = int(connection.execute("PRAGMA user_version").fetchone()[0])
            if version != SCHEMA_VERSION:
                return _unproven("EVIDENCE_UNAVAILABLE")
            # Reuse the canonical D2 typed readers. Do NOT call their writer open.
            store = DiaryDecisionStore(connection, path)
            link = store.get_trade_episode_link(TradeEpisodeId(trade_episode_id))
            if link is None:
                return _unproven("NO_EXACT_EPISODE_LINK")
            setup = store.get_setup_instance(link.setup_instance_id)
            plan = store.get_order_plan(link.order_plan_id)
            if (setup is None or plan is None
                    or plan.setup_instance_id != link.setup_instance_id
                    or plan.trading_account_id.value != account_id
                    or setup.symbol.value != symbol or plan.symbol.value != symbol
                    or setup.direction.value.upper() != side or plan.side.value.upper() != side
                    or setup.origin.value.upper() != (
                        "ROBOT" if opening_controller == "ROBOT" else "TERMINAL_MANUAL"
                    )
                    or not (setup.created_at_ms <= plan.created_at_ms <= link.linked_at_ms)):
                return _unproven("CONFLICTING_D2_LINK")
            events = store.load_decision_events(setup.setup_instance_id)
            if not 2 <= len(events) <= 1000:
                return _unproven("INCOMPLETE_D2_DECISIONS")
            for event in events:
                DiaryDecisionStore._validate_event_against_setup(event, setup)
                if event.occurred_at_ms < setup.created_at_ms:
                    return _unproven("CONFLICTING_D2_LINK")
            event_by_id = {event.decision_event_id: event for event in events}
            strategy = event_by_id.get(plan.strategy_decision_event_id)
            risk = event_by_id.get(plan.risk_decision_event_id)
            if (strategy is None or risk is None or
                    strategy.kind is not DecisionEventKind.STRATEGY or
                    risk.kind is not DecisionEventKind.RISK or
                    strategy.occurred_at_ms > risk.occurred_at_ms or
                    risk.occurred_at_ms > plan.created_at_ms):
                return _unproven("CONFLICTING_D2_LINK")
            text_values = [
                setup.setup_instance_id.value, setup.setup_id, setup.pattern,
                setup.timeframe, setup.entry_mode, setup.strategy_version,
                *(e.reason_code for e in events),
                *(e.previous_state or "" for e in events),
                *(e.next_state for e in events),
            ]
            if any(len(value) > 256 for value in text_values):
                return _unproven("EVIDENCE_UNAVAILABLE")

            return {
                "status": "EXACT_D2_LINK",
                "source": "TRADING_DIARY_D2",
                "consistency": "INDEPENDENT_READ_SNAPSHOT_NOT_ATOMIC_WITH_PAPER",
                "geometry_status": "NOT_EXPORTED",
                "decision_scope": "D2_OBSERVATIONS_NOT_ROBOT_RUNTIME_LOG",
                "setup": {
                    "setup_instance_id": setup.setup_instance_id.value,
                    "setup_id": setup.setup_id,
                    "symbol": setup.symbol.value,
                    "direction": setup.direction.value.upper(),
                    "timeframe": setup.timeframe,
                    "pattern": setup.pattern,
                    "strategy_version": setup.strategy_version,
                    "entry_mode": setup.entry_mode,
                    "origin": setup.origin.value.upper(),
                    "created_at_ms": setup.created_at_ms,
                    "has_feature_snapshot_ref": any(e.feature_snapshot_ref for e in events),
                },
                "order_plan_id": plan.order_plan_id.value,
                "linked_at_ms": link.linked_at_ms,
                "decisions": [
                    {
                        "decision_event_id": e.decision_event_id.value,
                        "kind": e.kind.value,
                        "previous_state": e.previous_state,
                        "next_state": e.next_state,
                        "reason_code": e.reason_code,
                        "controller": e.controller.value.upper(),
                        "origin": e.origin.value.upper(),
                        "occurred_at_ms": e.occurred_at_ms,
                    }
                    for e in events
                ],
            }
    except (sqlite3.Error, OSError, ValueError, TypeError, DiaryLinkageError):
        # An optional observational store must not turn corrupt evidence into
        # apparently proven context, nor suppress proven execution facts.
        return _unproven("EVIDENCE_UNAVAILABLE")


def attach_verified_original_geometry(
    setup_context: dict[str, object], *, symbol: str, opened_at_ms: int,
) -> dict[str, object]:
    """Optionally attach an EXACT archived detector snapshot, never refitted rays.

    D2 setup_id is accepted as the archived candidate id ONLY when the
    immutable Telegram source record independently agrees on that exact id,
    symbol, timeframe and pattern. Archive hashes prove intact source bytes,
    not causality of Robot decisions or a cryptographic signature.
    """
    if setup_context.get("status") != "EXACT_D2_LINK":
        return setup_context
    setup = setup_context.get("setup")
    if not isinstance(setup, dict) or setup.get("origin") != "ROBOT":
        return setup_context
    candidate_id = setup.get("setup_id")
    if (not isinstance(candidate_id, str) or not candidate_id
            or len(candidate_id) > 128
            or type(opened_at_ms) is not int or opened_at_ms <= 0):
        return setup_context

    # Reuse archive's existing original-image and canonical geometry checks.
    # Both only read files and never access live price, Robot, PAPER or MAIN.
    from signal_archive import load_frozen_signal_geometry, load_original_signal
    from signal_geometry_snapshot import validate_snapshot

    meta = load_original_signal([candidate_id])
    if meta is None:
        return setup_context
    if (meta.get("candidate_id") != candidate_id
            or meta.get("symbol") != symbol or setup.get("symbol") != symbol
            or meta.get("timeframe") != setup.get("timeframe")
            or meta.get("pattern") != setup.get("pattern")):
        return setup_context
    sent_ms = meta.get("sent_at_ms")
    if type(sent_ms) is not int or sent_ms < 0 or sent_ms > opened_at_ms:
        return setup_context

    frozen = load_frozen_signal_geometry(candidate_id)
    if frozen is None:
        return setup_context
    try:
        _, digest = validate_snapshot(
            frozen, candidate_id=candidate_id,
            symbol=symbol, timeframe=str(setup["timeframe"]),
        )
    except (ValueError, TypeError, KeyError):
        return setup_context
    if digest != meta.get("geometry_sha256"):
        return setup_context
    bars = frozen.get("bars")
    if (not isinstance(bars, list) or not bars
            or type(bars[-1].get("open_time_ms")) is not int
            or bars[-1]["open_time_ms"] > sent_ms):
        return setup_context

    # Export observational geometry as-is. Do not mix with corrected owner
    # geometry, simulated Scanner lines, nor inferred decision chronology.
    return {
        **setup_context,
        "geometry_status": "ORIGINAL_ARCHIVE_HASH_VERIFIED",
        "original_geometry": {
            "schema": "BYBITSCANNER_ARCHIVED_SIGNAL_GEOMETRY_V1",
            "source": "ORIGINAL_TELEGRAM_SIGNAL_ARCHIVE",
            "linkage_basis": "D2_SETUP_ID_EQUALS_ARCHIVED_CANDIDATE_ID",
            "integrity": "LOCAL_ARCHIVE_HASH_ONLY_NOT_CRYPTOGRAPHIC_PROOF",
            "signal_id": candidate_id,
            "sent_at_ms": sent_ms,
            "sha256": digest,
            "snapshot": frozen,
        },
    }
