"""Pure, fail-closed REST/WS L1000 identity alignment for Box/Wedge research.

No network calls, subscriptions, orderbook mutation, orders or Robot advice.
Even exact u/seq/cts overlap is NOT independent proof of missing-message
absence or publicTrade source completeness. Any uncertain segment is UNKNOWN.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation


MAX_FRAMES = 1024
DEPTH = 1000


@dataclass(frozen=True, slots=True)
class RestWsResearchAnchor:
    symbol: str
    update_id: int
    cross_sequence: int
    engine_cts_ms: int
    rest_available_at_ms: int
    ws_match_received_at_ms: int
    baseline_bids: tuple[tuple[Decimal, Decimal], ...]
    baseline_asks: tuple[tuple[Decimal, Decimal], ...]
    following_deltas: tuple[tuple[int, dict], ...]
    identity_match_only: bool = field(default=True, init=False)
    source_complete: bool = field(default=False, init=False)
    trading_authorized: bool = field(default=False, init=False)


def _valid_side(raw: object, *, descending: bool) -> tuple | None:
    if not isinstance(raw, list) or not 1 <= len(raw) <= DEPTH:
        return None
    result = []
    previous = None
    for level in raw:
        if (not isinstance(level, list) or len(level) != 2
                or any(isinstance(x, bool) or not isinstance(x, (str, int, float))
                       for x in level)):
            return None
        try:
            price, size = (Decimal(str(level[0])), Decimal(str(level[1])))
        except (InvalidOperation, ValueError, TypeError):
            return None
        if (not price.is_finite() or not size.is_finite()
                or price <= 0 or size <= 0):
            return None
        if previous is not None and (
            price >= previous if descending else price <= previous
        ):
            return None
        result.append((price, size))
        previous = price
    return tuple(result)


def _vendor_id(frame: dict) -> tuple[int, int, int, int] | None:
    if not isinstance(frame, dict):
        return None
    data = frame.get("data")
    if not isinstance(data, dict):
        return None
    update_id = data.get("u")
    sequence = data.get("seq")
    # Bybit documents cts on the top level, but preserve compatibility
    # with older verified raw captures that included it in data.
    cts = frame.get("cts", data.get("cts"))
    ts = frame.get("ts")
    if (any(type(x) is not int or x <= 0 for x in
            (update_id, sequence, cts, ts))
            or cts > ts):
        return None
    return (update_id, sequence, cts, ts)


def align_rest_to_observed_l1000(
    rest_response: object,
    ws_frames: tuple[tuple[int, dict], ...],
    *,
    symbol: str,
    host_known_at_ms: int,
    rest_requested_at_ms: int,
    rest_received_at_ms: int,
    decision_ms: int,
    max_quote_age_ms: int = 2000,
) -> RestWsResearchAnchor | None:
    """Require exact REST snapshot update to occur in ALREADY observed WS.

    It is incorrect to declare REST u+1 to be an observed frame: the matching
    update must be present with same u/seq/cts, after the immutable host was
    knowable and before REST receipt. Subsequent raw deltas must be strictly
    consecutive in update ID; missing/duplicate/backward/late frames fail
    closed rather than generate reconstructed liquidity or fill assertions.
    A caller must independently prove generation, transport, REST provenance,
    and complete publicTrade before using even descriptive observations.
    """
    if (not isinstance(symbol, str) or not symbol.isalnum()
            or not symbol.endswith("USDT")
            or any(type(x) is not int for x in (
                host_known_at_ms, rest_requested_at_ms, rest_received_at_ms,
                decision_ms, max_quote_age_ms,
            )) or not 0 <= host_known_at_ms <= rest_requested_at_ms
            < rest_received_at_ms <= decision_ms
            or not 0 < max_quote_age_ms <= 10_000
            or not isinstance(ws_frames, tuple)
            or not 3 <= len(ws_frames) <= MAX_FRAMES
            or not isinstance(rest_response, dict)
            or type(rest_response.get("retCode")) is not int
            or rest_response["retCode"] != 0):
        return None
    result = rest_response.get("result")
    if not isinstance(result, dict) or result.get("s") != symbol:
        return None
    u, seq, cts, ts = (
        result.get("u"), result.get("seq"),
        result.get("cts"), result.get("ts"),
    )
    if (any(type(x) is not int or x <= 0 for x in (u, seq, cts, ts))
            or cts > ts or not host_known_at_ms <= cts <= ts <= rest_received_at_ms
            or rest_received_at_ms - ts > max_quote_age_ms):
        return None
    bids = _valid_side(result.get("b"), descending=True)
    asks = _valid_side(result.get("a"), descending=False)
    if not bids or not asks or bids[0][0] >= asks[0][0]:
        return None
    match = -1
    previous_received = host_known_at_ms
    for i, row in enumerate(ws_frames):
        if (not isinstance(row, tuple) or len(row) != 2
                or type(row[0]) is not int
                or not previous_received <= row[0] <= decision_ms):
            return None
        previous_received = row[0]
        frame = row[1]
        if (not isinstance(frame, dict)
                or frame.get("type") != "delta"
                or frame.get("topic") != f"orderbook.{DEPTH}.{symbol}"
                or not isinstance(frame.get("data"), dict)
                or frame["data"].get("s") != symbol):
            return None
        identity = _vendor_id(frame)
        if identity is None:
            return None
        _, _, frame_cts, frame_ts = identity
        if frame_cts < host_known_at_ms or frame_ts > row[0]:
            return None
        if identity[:3] == (u, seq, cts):
            if match != -1:
                return None
            match = i
    if (match < 0 or match + 2 >= len(ws_frames)
            or ws_frames[match][0] > rest_received_at_ms
            or abs(ws_frames[match][1]["ts"] - ts) > max_quote_age_ms):
        return None
    prior_u, prior_seq, prior_cts, prior_ts = u, seq, cts, ts
    prior_receipt = ws_frames[match][0]
    for received, frame in ws_frames[match + 1:]:
        ident = _vendor_id(frame)
        if ident is None:
            return None
        next_u, next_seq, next_cts, next_ts = ident
        if (next_u != prior_u + 1
                or next_seq <= prior_seq or next_cts < prior_cts
                or next_ts < prior_ts
                or next_ts > received
                or received - prior_receipt > max_quote_age_ms):
            return None
        prior_u, prior_seq, prior_cts, prior_ts = ident
        prior_receipt = received
    return RestWsResearchAnchor(
        symbol, u, seq, cts, rest_received_at_ms,
        ws_frames[match][0], bids, asks, ws_frames[match + 1:],
    )
