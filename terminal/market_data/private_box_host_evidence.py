"""Private, non-executing Box host and ingress receipt audit.

Internal building block for a separately authorized owner observation, not an
HTTP or GitHub diagnostic endpoint. Call with the existing serialized PAPER
owner store and protected MarketDataHub witness. No trade authorization.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable

from terminal.market_data.research_l2_rest_anchor import _vendor_id


@dataclass(frozen=True, slots=True)
class PrivateBoxReceiptEvidence:
    status: str
    candidate_id: str | None = None
    symbol: str | None = None
    state_revision: int | None = None
    snapshot_sha256: str | None = None
    approved_at_ms: int | None = None
    observed_book_frames: int = 0
    observed_prints: int = 0
    source_complete: bool = field(default=False, init=False)
    trading_authorized: bool = field(default=False, init=False)


def inspect_private_box_receipts(
    get_candidate: Callable[[str], object],
    research_snapshot: Callable[[str], dict | None],
    *, candidate_id: str, observed_at_ms: int,
    max_quote_age_ms: int = 2000,
) -> PrivateBoxReceiptEvidence:
    """Only an existing immutable APPROVED PAPER Box and existing witness.

    get_candidate must be SQLiteStore.get_robot_candidate called on the owner
    thread. research_snapshot reads an already-opted-in protected MarketDataHub
    witness. Neither creates subscriptions or exports raw books and prints.
    """
    missing = PrivateBoxReceiptEvidence("NO_PROVEN_HOST")
    if (not isinstance(candidate_id, str)
            or not candidate_id.startswith("box-robot-")
            or not 10 <= len(candidate_id) <= 128
            or type(observed_at_ms) is not int or observed_at_ms < 0
            or type(max_quote_age_ms) is not int
            or not 0 < max_quote_age_ms <= 10_000):
        return missing
    try:
        record = get_candidate(candidate_id)
        if record is None:
            return missing
        snapshot = record.signal_snapshot
        state = record.robot_state
        identity = snapshot["identity"]
        source_id = snapshot["source_box_candidate_id"]
        approved = record.approved_at_ms
        symbol = record.symbol.value
        sha = record.snapshot_sha256
        revision = record.state_revision
        if (record.candidate_id != candidate_id
                or record.trading_account_id.value != "paper"
                or record.status != "APPROVED"
                or not isinstance(snapshot, dict) or not isinstance(state, dict)
                or state.get("phase") != "BOX_ENTRY_READY"
                or snapshot.get("pattern") != "IKIGAI_BOX"
                or snapshot.get("environment") != "PAPER"
                or snapshot.get("execution_authorized") is not False
                or not isinstance(identity, dict)
                or identity.get("symbol") != symbol
                or identity.get("direction") not in ("LONG", "SHORT")
                or snapshot.get("plan", {}).get("direction") != identity["direction"]
                or not isinstance(source_id, str)
                or not source_id.startswith("box-plan-")
                or candidate_id != "box-robot-" + source_id.removeprefix("box-plan-")
                or state.get("source_box_candidate_id") != source_id
                or type(approved) is not int or not 0 <= approved <= observed_at_ms
                or type(snapshot.get("decision_time_ms")) is not int
                or snapshot["decision_time_ms"] > approved
                or type(revision) is not int or revision < 1
                or not isinstance(sha, str) or len(sha) != 64
                or any(c not in "0123456789abcdef" for c in sha)):
            return missing
        source = get_candidate(source_id)
        source_snapshot = dict(snapshot)
        source_snapshot.pop("source_box_candidate_id")
        if (source is None or source.candidate_id != source_id
                or source.trading_account_id.value != "paper"
                or source.status != "BOX_PLAN_ONLY"
                or source.robot_state is not None
                or source.symbol.value != symbol
                or source.signal_snapshot != source_snapshot):
            return missing
    except (AttributeError, TypeError, KeyError, ValueError):
        return missing
    except Exception:
        return PrivateBoxReceiptEvidence("UNKNOWN")

    host = dict(candidate_id=candidate_id, symbol=symbol,
                state_revision=revision, snapshot_sha256=sha,
                approved_at_ms=approved)
    try:
        evidence = research_snapshot(symbol)
    except Exception:
        return PrivateBoxReceiptEvidence("UNKNOWN", **host)
    if evidence is None:
        return PrivateBoxReceiptEvidence("NO_RECEIPT", **host)
    if not isinstance(evidence, dict):
        return PrivateBoxReceiptEvidence("UNKNOWN", **host)
    book, trades = evidence.get("book"), evidence.get("trades")
    if not isinstance(book, dict) or not isinstance(trades, dict):
        return PrivateBoxReceiptEvidence("UNKNOWN", **host)
    frames, prints = book.get("frames"), trades.get("prints")
    if (book.get("symbol") != symbol or trades.get("symbol") != symbol
            or book.get("active") is not True or book.get("depth") != 1000
            or book.get("source_complete") is not False
            or book.get("trading_authorized") is not False
            or type(book.get("epoch")) is not int
            or type(trades.get("generation")) is not int
            or not isinstance(frames, tuple) or not isinstance(prints, tuple)
            or len(frames) > 1024 or len(prints) > 1000):
        return PrivateBoxReceiptEvidence("UNKNOWN", **host)
    if not frames or not prints:
        return PrivateBoxReceiptEvidence("NO_RECEIPT", **host)
    prior = None
    for index, entry in enumerate(frames):
        if not isinstance(entry, tuple) or len(entry) != 2:
            return PrivateBoxReceiptEvidence("UNKNOWN", **host)
        received, frame = entry
        if (type(received) is not int or not approved <= received <= observed_at_ms
                or not isinstance(frame, dict)
                or frame.get("type") != ("snapshot" if index == 0 else "delta")
                or frame.get("topic") != f"orderbook.1000.{symbol}"):
            return PrivateBoxReceiptEvidence("UNKNOWN", **host)
        data = frame.get("data")
        if not isinstance(data, dict) or data.get("s") != symbol:
            return PrivateBoxReceiptEvidence("UNKNOWN", **host)
        vendor_identity = _vendor_id(frame)  # Shared REST/WS source validator.
        if vendor_identity is None:
            return PrivateBoxReceiptEvidence("UNKNOWN", **host)
        u, seq, cts, ts = vendor_identity
        if (not approved <= cts <= ts <= received
                or received - ts > max_quote_age_ms):
            return PrivateBoxReceiptEvidence("UNKNOWN", **host)
        if prior is not None:
            pu, ps, pc, pt, pr = prior
            if (u != pu + 1 or seq <= ps or cts < pc or ts < pt
                    or received < pr or received - pr > max_quote_age_ms):
                return PrivateBoxReceiptEvidence("UNKNOWN", **host)
        prior = (u, seq, cts, ts, received)
    # Never attribute earlier prints retained by the shared observer to the host.
    eligible = tuple(item for item in prints
                     if type(getattr(item, "received_at_ms", None)) is int
                     and getattr(item, "received_at_ms") >= approved)
    if not eligible:
        return PrivateBoxReceiptEvidence("NO_RECEIPT", **host)
    seen = set()
    last = None
    for item in eligible:
        try:
            received = item.received_at_ms
            stamp, seq, trade_id = item.timestamp_ms, item.sequence, item.trade_id
            if (type(received) is not int
                    or not approved <= stamp <= received <= observed_at_ms
                    or not isinstance(trade_id, str) or not trade_id
                    or type(seq) is not int or seq < 0 or trade_id in seen
                    or (last is not None and (stamp < last[0] or seq < last[1]))):
                return PrivateBoxReceiptEvidence("UNKNOWN", **host)
            seen.add(trade_id)
            last = stamp, seq
        except (AttributeError, TypeError):
            return PrivateBoxReceiptEvidence("UNKNOWN", **host)
    # Raw receipt fragments do not prove a gap-free publicTrade stream or fill.
    return PrivateBoxReceiptEvidence("RECEIPTS_OBSERVED_UNATTESTED", **host,
                                     observed_book_frames=len(frames),
                                     observed_prints=len(eligible))
