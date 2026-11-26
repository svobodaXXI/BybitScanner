"""Private, non-executing Box host and ingress receipt audit.

Internal building block for a separately authorized owner observation, not an
HTTP or GitHub diagnostic endpoint. Call with the existing serialized PAPER
owner store and protected MarketDataHub witness. No trade authorization.
"""
from __future__ import annotations

import json
import os
import tempfile
from dataclasses import asdict, dataclass, field
from pathlib import Path
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
    if len(frames) < 2 or not prints:
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
    last_received = None
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
            last_received = received
        except (AttributeError, TypeError):
            return PrivateBoxReceiptEvidence("UNKNOWN", **host)
    # A historically coherent but now stale tape is not a current host receipt.
    if (prior is None or last_received is None
            or observed_at_ms - prior[4] > max_quote_age_ms
            or observed_at_ms - last_received > max_quote_age_ms):
        return PrivateBoxReceiptEvidence("UNKNOWN", **host)
    # Raw receipt fragments do not prove a gap-free publicTrade stream or fill.
    return PrivateBoxReceiptEvidence("RECEIPTS_OBSERVED_UNATTESTED", **host,
                                     observed_book_frames=len(frames),
                                     observed_prints=len(eligible))


class PrivateBoxCapture:
    """One optional Box witness; called by the existing Robot lifecycle.

    No scheduler, network subscription, file IO or trading authority. The
    caller supplies the exact durable Robot readiness and canonical store.
    A changed host/revision must obtain a fresh vendor snapshot.
    """

    def __init__(self, hub) -> None:
        self._hub = hub
        self._owner = object()
        self._host: PrivateBoxReceiptEvidence | None = None
        self._witness = None

    def close(self) -> None:
        host = self._host
        if host is not None:
            self._hub.end_protected_research_capture(
                host.symbol, owner_token=self._owner,
            )
        self._host = None
        self._witness = None

    def sync(self, get_candidate, candidate_ids, *, robot_ready: bool,
             observed_at_ms: int) -> PrivateBoxReceiptEvidence:
        """Attach only to an already protected exact APPROVED Box host."""
        if robot_ready is not True:
            self.close()
            return PrivateBoxReceiptEvidence("UNKNOWN")
        try:
            ids = sorted(set(candidate_ids))
            # Preserve the current exact witness rather than discard a
            # usable tape when a lexically earlier candidate arrives.
            if self._host is not None and self._host.candidate_id in ids:
                ids.remove(self._host.candidate_id)
                ids.insert(0, self._host.candidate_id)
            first_valid = None
            for candidate_id in ids:
                host = inspect_private_box_receipts(
                    get_candidate, lambda _symbol: None,
                    candidate_id=candidate_id, observed_at_ms=observed_at_ms,
                )
                if host.status != "NO_RECEIPT":
                    continue
                if first_valid is None:
                    first_valid = host
                if host != self._host:
                    self.close()
                self._host = host
                self._witness = self._hub.begin_protected_research_capture(
                    host.symbol, owner_token=self._owner,
                )
                if self._witness is not None:
                    return host
                # An approved candidate without an existing protected
                # context must not starve other eligible candidates.
                self.close()
            self.close()
            return first_valid or PrivateBoxReceiptEvidence("NO_PROVEN_HOST")
        except Exception:
            self.close()
            return PrivateBoxReceiptEvidence("UNKNOWN")

    def observe(self, get_candidate, *, robot_ready: bool,
                observed_at_ms: int, save=None, observation_clock=None) -> PrivateBoxReceiptEvidence:
        """Read only our exact witness; never accept a replacement host."""
        if robot_ready is not True:
            self.close()
            return PrivateBoxReceiptEvidence("UNKNOWN")
        host = self._host
        witness = self._witness
        if host is None or witness is None:
            return PrivateBoxReceiptEvidence("NO_RECEIPT")
        try:
            current = inspect_private_box_receipts(
                get_candidate, lambda _symbol: None,
                candidate_id=host.candidate_id, observed_at_ms=observed_at_ms,
            )
            if current != host:
                self.close()
                return PrivateBoxReceiptEvidence("UNKNOWN")
            detached = self._hub.private_protected_research_snapshot(
                host.symbol, expected_witness=witness,
            )
            # Timestamp the completed detached read, not its start: ingress
            # may advance while copying. Future receipts remain rejected.
            if observation_clock is not None:
                observed_at_ms = observation_clock()
            result = inspect_private_box_receipts(
                get_candidate, lambda symbol: detached if symbol == host.symbol else None,
                candidate_id=host.candidate_id, observed_at_ms=observed_at_ms,
            )
            # Never persist a different revision that raced host selection.
            current = inspect_private_box_receipts(
                get_candidate, lambda _symbol: None,
                candidate_id=host.candidate_id, observed_at_ms=observed_at_ms,
            )
            if (current != host
                    or result.candidate_id != host.candidate_id
                    or result.state_revision != host.state_revision
                    or result.snapshot_sha256 != host.snapshot_sha256):
                self.close()
                return PrivateBoxReceiptEvidence("UNKNOWN")
            if save is not None and result.status == "RECEIPTS_OBSERVED_UNATTESTED":
                # Pass the SAME detached source used for validation, never
                # a second snapshot or a different candidate's older prints.
                book, trades = detached["book"], detached["trades"]
                save(result, {
                    "book": book,
                    "trades": {**trades, "prints": tuple(
                        item for item in trades["prints"]
                        if type(getattr(item, "received_at_ms", None)) is int
                        and item.received_at_ms >= host.approved_at_ms
                    )},
                })
            return result
        except Exception:
            self.close()
            return PrivateBoxReceiptEvidence("UNKNOWN")


def save_first_private_box_receipt(path: Path, result: PrivateBoxReceiptEvidence,
                                   detached: dict, *, allow_write) -> bool:
    """Retain ONE bounded owner-private sample, never overwrite prior evidence.

    This is a local diagnostic file, not a journal or public reporting path.
    A later owner-controlled export is separate. No completeness claim.
    """
    if (result.status != "RECEIPTS_OBSERVED_UNATTESTED"
            or result.source_complete or result.trading_authorized
            or path.exists() or not allow_write()):
        return False
    book, trades = detached["book"], detached["trades"]
    payload = json.dumps({
        "schema": "PAPER_BOX_PRIVATE_RECEIPT_V1",
        "host": asdict(result),
        "book": book,
        "trades": {**trades, "prints": [asdict(p) for p in trades["prints"]]},
        "source_complete": False,
        "trading_authorized": False,
    }, default=str, separators=(",", ":")).encode("utf-8")
    if len(payload) > 8 * 1024 * 1024:
        return False
    temporary = None
    try:
        # NamedTemporaryFile has owner-only permissions. Same-directory link
        # atomically publishes the finished file WITHOUT replacing a sample.
        with tempfile.NamedTemporaryFile(dir=path.parent, delete=False) as output:
            temporary = Path(output.name)
            output.write(payload)
        if not allow_write():
            return False
        try:
            os.link(temporary, path)
        except FileExistsError:
            return False
        return True
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
