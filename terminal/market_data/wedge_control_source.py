"""Bridge existing publicTrade facts to the detector's dynamic wedge primitive.

No subscription, IO, order calls or signal mutation. Only an owner-supplied
contiguous source-TF candle prefix with receipt evidence is accepted. The
open bar must be the state at this print, never a later chart snapshot.
This is an adapter contract, not a running market subscription.
"""
from dataclasses import dataclass
import math

from geometry.control_anchor import ConfirmedAnchor, observe_trade
from geometry.control_boundary import BoundarySelection, select_strict_boundary
from geometry.triangle_boundaries import PIVOT_RIGHT, local_alternation_pivots
from signal_geometry_producer import TIMEFRAME_MS
from signal_geometry_snapshot import validate_snapshot
from terminal.market_data.impulse_observation import ObservedPrint


@dataclass(frozen=True)
class WedgeControlObservation:
    state: object
    request: object = None
    boundary: BoundarySelection | None = None
    status: str = "NO_REBUILD"


def observe_wedge_print(state, trade, frame, *, timeframe, episode_start,
                        opposite_line, closed_known_at_ms, prefix_as_of_trade_id,
                        breakout_observed, source_valid):
    """Use one observed execution and its causal source-TF candle prefix.

    closed_known_at_ms records the actual local visibility of each closed
    bar, not just its exchange close time. Open-bar OHLC is supplied by the
    existing owner as of the exact print. Pivot confirmation uses CLOSED
    bars only, with the existing local alternation-aware detector. A caller
    cannot certify continuity from cross-sequence numbers alone.
    """
    bad = WedgeControlObservation(state, status="EVIDENCE_UNAVAILABLE")
    if source_valid is not True or not isinstance(trade, ObservedPrint):
        return bad
    try:
        interval = TIMEFRAME_MS[str(timeframe)]
        receipt = trade.received_at_ms
        if (type(receipt) is not int or receipt < trade.timestamp_ms
                or prefix_as_of_trade_id != trade.trade_id
                or type(episode_start) is not int
                or not 0 <= episode_start < len(frame)-1):
            return bad
        times = [int(v) for v in frame["time"]]
        if (any(t < 0 or t % interval for t in times)
                or any(b-a != interval for a,b in zip(times,times[1:]))
                or not times[-1] <= trade.timestamp_ms < times[-1]+interval
                or len(closed_known_at_ms) != len(times)-1):
            return bad
        if any(type(k) is not int or not t+interval <= k <= receipt
               for t,k in zip(times[:-1], closed_known_at_ms)):
            return bad
        for row in frame[["open","high","low","close"]].itertuples(index=False, name=None):
            o,h,l,c = map(float,row)
            if not all(math.isfinite(v) and v > 0 for v in (o,h,l,c)) or not l <= min(o,c) <= max(o,c) <= h:
                return bad
        if float(frame.iloc[-1].close) != float(trade.price):
            return bad

        # No current/open candle may be used as right confirmation.
        closed = frame.iloc[:-1]
        highs,lows = local_alternation_pivots(closed, len(closed)-1)
        points = highs if state.family == "falling" else lows
        anchors = []
        for point in points:
            i = point["index"]
            if i < episode_start:
                continue
            # Actual receipt of the confirming right-window and all earlier
            # evidence, conservatively including the local prefix.
            known = max(closed_known_at_ms[:i+PIVOT_RIGHT+1])
            anchors.append(ConfirmedAnchor(i, str(point["price"]), times[i], known))
        next_state, request = observe_trade(
            state, trade_id=trade.trade_id, timestamp_ms=trade.timestamp_ms,
            sequence=trade.sequence, price=trade.price,
            breakout_observed=breakout_observed, confirmed_anchors=anchors,
            source_valid=True,
        )
        if request is None:
            return WedgeControlObservation(next_state)
        boundary = select_strict_boundary(
            request, anchors, frame, episode_start=episode_start,
            current_index=len(frame)-1, opposite_line=opposite_line,
        )
        return WedgeControlObservation(next_state, request, boundary, boundary.status)
    except (KeyError, TypeError, ValueError, AttributeError, IndexError, OverflowError):
        return bad


@dataclass(frozen=True)
class WedgePrintPrefix:
    """Exact frozen closed bars plus an observed open-bar prefix."""
    frame: object
    closed_known_at_ms: tuple[int, ...]
    as_of_trade_id: str


def build_wedge_print_prefix(snapshot, *, candidate_id, symbol, timeframe,
                             closed_known_at_ms, current_prints, trade,
                             observed_from_ms, source_valid,
                             closed_extension=(), extension_known_at_ms=()):
    """Use the existing immutable signal archive as the closed-bar seed.

    Later source-TF bars may extend the seed only via the same owner's
    contiguous, already-closed OHLC and actual receipt evidence.
    No fabricated gaps, later OHLC, or REST call is allowed here.
    The caller must establish observed_from_ms and source_valid from its
    actual market owner; a publicTrade cross-sequence alone proves neither
    continuity nor the absence of dropped prints. This is an observed
    prefix, not an assertion of exchange-complete OHLC.
    """
    if source_valid is not True or not isinstance(trade, ObservedPrint):
        return None
    try:
        import pandas as pd
        validate_snapshot(snapshot, candidate_id=candidate_id,
                          symbol=symbol, timeframe=timeframe)
        interval = TIMEFRAME_MS[str(timeframe)]
        seed = snapshot["bars"]
        if (not isinstance(closed_extension, (tuple, list))
                or len(closed_known_at_ms) != len(seed)
                or len(extension_known_at_ms) != len(closed_extension)):
            return None
        bars = [*seed, *closed_extension]
        # Reuse the existing source snapshot validation, including bar
        # bounds, OHLC integrity and original identity. Never mutate it.
        validate_snapshot({**snapshot, "bars": bars},
                          candidate_id=candidate_id, symbol=symbol, timeframe=timeframe)
        known_at_ms = (*closed_known_at_ms, *extension_known_at_ms)
        times = [b["open_time_ms"] for b in bars]
        if (any(t < 0 or t % interval for t in times)
                or any(b-a != interval for a,b in zip(times,times[1:]))):
            return None
        start = times[-1]+interval
        receipt = trade.received_at_ms
        if (type(receipt) is not int or receipt < trade.timestamp_ms
                or not start <= trade.timestamp_ms < start+interval
                or type(observed_from_ms) is not int
                or not 0 <= observed_from_ms <= start
                or any(type(k) is not int or not t+interval <= k <= receipt
                       for t,k in zip(times, known_at_ms))):
            return None

        # Process only the ordered prefix ending at the exact target print.
        # Later prints already in the shared buffer must not alter this bar.
        prices = []
        previous = None
        seen = {}
        found = False
        for item in current_prints:
            if not isinstance(item, ObservedPrint):
                return None
            if item.trade_id in seen:
                if seen[item.trade_id] != item:
                    return None
                continue
            at, known = item.timestamp_ms, item.received_at_ms
            if (type(known) is not int or not at <= known <= receipt
                    or not start <= at < start+interval
                    or (previous is not None and
                        (at < previous.timestamp_ms or
                         item.sequence < previous.sequence or
                         known < previous.received_at_ms))):
                return None
            price = float(item.price)
            if not math.isfinite(price) or price <= 0:
                return None
            seen[item.trade_id] = item
            prices.append(price)
            previous = item
            if item.trade_id == trade.trade_id:
                if item != trade or known != receipt:
                    return None
                found = True
                break
        if not found:
            return None
        rows = [{"time": b["open_time_ms"], **{k:b[k] for k in
                 ("open","high","low","close")}} for b in bars]
        rows.append({"time":start, "open":prices[0], "high":max(prices),
                     "low":min(prices), "close":prices[-1]})
        return WedgePrintPrefix(pd.DataFrame(rows), known_at_ms,
                                trade.trade_id)
    except (KeyError, TypeError, ValueError, AttributeError, IndexError, OverflowError):
        return None
