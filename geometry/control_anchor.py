"""Source-time control-anchor trigger for an existing local wedge episode.

Pure geometry observation. No network, orders, admission, candidate mutation
or journal writes. The existing market owner must supply ordered trade facts,
a proved episode, breakout observation and confirmed same-side pivots.
A request is not a successful geometry revision. The caller must validate
the rebuilt geometry before publishing a revision.
"""
from __future__ import annotations

from dataclasses import dataclass, replace
from decimal import Decimal, InvalidOperation


@dataclass(frozen=True)
class ConfirmedAnchor:
    index: int
    price: str
    pivot_at_ms: int
    known_at_ms: int


@dataclass(frozen=True)
class RebuildRequest:
    episode_id: str
    family: str
    old_extreme: str
    new_extreme: str
    trade_id: str
    timestamp_ms: int
    sequence: int
    control_anchor: ConfirmedAnchor | None


@dataclass(frozen=True)
class ControlAnchorState:
    episode_id: str
    family: str
    extreme: str
    # Breakout is an observational fact from the geometry owner, not a
    # Robot phase or a permission to submit orders.
    breakout_seen: bool = False
    timestamp_ms: int = -1
    sequence: int = -1
    trade_ids: tuple[str, ...] = ()


def _price(value):
    try:
        p = Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError) as exc:
        raise ValueError("invalid price") from exc
    if not p.is_finite() or p <= 0:
        raise ValueError("invalid price")
    return p


def _nonnegative_int(value):
    return type(value) is int and value >= 0


def initialize_control_anchor(episode_id, family, extreme):
    if not isinstance(episode_id, str) or not episode_id:
        raise ValueError("episode identity required")
    if family not in ("falling", "rising"):
        raise ValueError("unsupported wedge family")
    return ControlAnchorState(episode_id, family, str(_price(extreme)))


def observe_trade(state, *, trade_id, timestamp_ms, sequence, price,
                  breakout_observed, confirmed_anchors, source_valid):
    """Return next observation state and, if necessary, a rebuild request.

    A falling wedge tracks LOW and consumes confirmed HIGHs; rising mirrors
    this. The caller supplies ONLY pivots of the relevant side within the
    owned episode and an observation-valid source. Confirmation timestamps
    must precede the new trade; no right-confirmation of the new extreme.
    Equal prices do not trigger. Preserve the latest observed extreme even
    if the geometry builder cannot supply a new valid line. A failed request
    must be reported separately, not published as a successful revision.

    Exchange sequences can repeat. Deduplicate IDs at the current source
    cursor and reject backward timestamps or sequences. A gap is not repaired
    by this function: the existing market owner must establish new evidence.
    Persist the returned state and request atomically before consuming the
    next observation in any future runtime integration.
    """
    if source_valid is not True:
        return state, None
    if not isinstance(state, ControlAnchorState):
        raise ValueError("invalid control anchor state")
    if (not isinstance(trade_id, str) or not trade_id
            or not _nonnegative_int(timestamp_ms)
            or not _nonnegative_int(sequence)
            or type(breakout_observed) is not bool):
        raise ValueError("invalid source event")
    if timestamp_ms < state.timestamp_ms or sequence < state.sequence:
        return state, None
    same_cursor = timestamp_ms == state.timestamp_ms and sequence == state.sequence
    if same_cursor and trade_id in state.trade_ids:
        return state, None
    p = _price(price)
    old = _price(state.extreme)
    ids = state.trade_ids + (trade_id,) if same_cursor else (trade_id,)
    seen = state.breakout_seen or breakout_observed
    new = replace(state, timestamp_ms=timestamp_ms, sequence=sequence,
                  trade_ids=ids, breakout_seen=seen)
    more_extreme = p < old if state.family == "falling" else p > old
    if not more_extreme:
        return new, None
    new = replace(new, extreme=str(p))
    # Before the break the episode's opposite extreme is still maintained,
    # but a rebuild of the broken boundary is not requested.
    if not seen:
        return new, None

    anchors = []
    for a in confirmed_anchors:
        if not isinstance(a, ConfirmedAnchor):
            raise ValueError("invalid confirmed anchor")
        if (not _nonnegative_int(a.index)
                or not _nonnegative_int(a.pivot_at_ms)
                or not _nonnegative_int(a.known_at_ms)
                or a.pivot_at_ms > a.known_at_ms):
            raise ValueError("invalid pivot chronology")
        _price(a.price)
        if a.known_at_ms < timestamp_ms:
            anchors.append(a)
    anchor = max(anchors, key=lambda a: (a.pivot_at_ms, a.index), default=None)
    return new, RebuildRequest(
        state.episode_id, state.family, str(old), str(p),
        trade_id, timestamp_ms, sequence, anchor,
    )
