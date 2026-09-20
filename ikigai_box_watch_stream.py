"""Opt-in, process-local closed-candle WATCH cursor for Scanner observations.

A cold start or data gap only bootstraps geometry; it never emits historical
WATCH cards. No PAPER/Robot DB, orders, or background process is touched.
WATCHs may be delivered only on a newly closed candle with exact continuity.
"""
from dataclasses import replace

from geometry.ikigai_box import detect_ikigai_box_watches
from ikigai_box_scanner import send_ikigai_box_watch_observation


_WATCH_CURSORS = {}


def _frame(candles, timeframe):
    if candles is None or not str(timeframe).isdecimal() or len(candles) < 2:
        return None
    closed = candles.iloc[:-1].reset_index(drop=True)
    if not all(name in closed.columns for name in
               ("time", "open", "high", "low", "close")):
        return None
    try:
        times = [int(value) for value in closed["time"]]
        duration = int(timeframe) * 60_000
    except (TypeError, ValueError, OverflowError):
        return None
    if duration <= 0 or any(
        right - left != duration
        for left, right in zip(times, times[1:])
    ):
        return None
    return closed, times


def _bootstrap(key, frame, times):
    watches = detect_ikigai_box_watches(frame)
    last = frame.iloc[-1]
    _WATCH_CURSORS[key] = {
        "time": times[-1],
        "last_ohlc": tuple(float(last[col]) for col in
                           ("open", "high", "low", "close")),
        "end_index": len(frame) - 1,
        "watches": watches,
        "pending": None,
    }


def _shift(previous, offset):
    translated = []
    for watch in previous:
        fields = {
            "as_of_index": watch.as_of_index + offset,
            "anchor_start_index": watch.anchor_start_index + offset,
            "anchor_end_index": watch.anchor_end_index + offset,
            "box_start_index": watch.box_start_index + offset,
            "box_end_index": watch.box_end_index + offset,
            "first_box_exit_index": (
                None if watch.first_box_exit_index is None
                else watch.first_box_exit_index + offset
            ),
        }
        if fields["anchor_start_index"] < 0:
            # A frozen setup that scrolled out of the 200-candle window
            # cannot be safely reconstructed or sent.
            continue
        translated.append(replace(watch, **fields))
    return tuple(translated)


def process_ikigai_box_watches(
    symbol, candles, *, timeframe, test_mode=False,
):
    """Send at most one new, not-yet-touched WATCH per symbol/closed candle.

    Explicit caller opt-in is enforced in main.run_scan_pass. On restart,
    skipped candles or changed historical OHLC, bootstrap without emitting.
    Repeated scan passes within the same candle never advance state.
    """
    key = (str(symbol), str(timeframe))
    validated = _frame(candles, timeframe)
    if validated is None:
        _WATCH_CURSORS.pop(key, None)
        return False
    frame, times = validated
    old = _WATCH_CURSORS.get(key)
    if old is None:
        _bootstrap(key, frame, times)
        return False
    if old["time"] == times[-1]:
        pending = old["pending"]
        if pending is None:
            return False
        # Retry a failed Telegram delivery using the SAME closed frame.
        sent = send_ikigai_box_watch_observation(
            symbol, candles, pending, timeframe=timeframe,
            test_mode=test_mode,
        )
        if sent:
            old["pending"] = None
        return sent

    if (
        len(times) < 2
        or old["time"] != times[-2]
        or times[-1] - old["time"] != int(timeframe) * 60_000
    ):
        _bootstrap(key, frame, times)
        return False

    last = frame.iloc[-2]
    prior_ohlc = tuple(float(last[col]) for col in
                       ("open", "high", "low", "close"))
    if prior_ohlc != old["last_ohlc"]:
        _bootstrap(key, frame, times)
        return False

    offset = len(frame) - 2 - old["end_index"]
    previous = _shift(old["watches"], offset)
    current = detect_ikigai_box_watches(
        frame, previous_watches=previous,
    )
    prev_by_anchor = {item.anchor_identity: item for item in previous}
    candidates = []
    now = len(frame) - 1
    for watch in current:
        old_watch = prev_by_anchor.get(watch.anchor_identity)
        first_ready = (
            old_watch is None and watch.phase == "BOX_READY"
            and watch.box_end_index == now
        )
        first_break = (
            watch.phase == "BOX_BREAK_OBSERVED"
            and watch.first_box_exit_index == now
            and (old_watch is None or old_watch.phase == "BOX_READY")
        )
        if first_ready or first_break:
            candidates.append(watch)
    pending_identity = (
        old["pending"].anchor_identity
        if old["pending"] is not None else None
    )
    if pending_identity is not None:
        candidate = next((
            item for item in current
            if item.anchor_identity == pending_identity
        ), None)
    else:
        # Cap notification volume: no multi-card burst per symbol/pass.
        candidate = max(
            candidates,
            key=lambda item: (
                item.anchor_end_index, item.anchor_start_index,
            ),
            default=None,
        )

    last = frame.iloc[-1]
    _WATCH_CURSORS[key] = {
        "time": times[-1],
        "last_ohlc": tuple(float(last[col]) for col in
                           ("open", "high", "low", "close")),
        "end_index": now,
        "watches": current,
        "pending": candidate,
    }
    if candidate is None:
        return False
    sent = send_ikigai_box_watch_observation(
        symbol, candles, candidate, timeframe=timeframe,
        test_mode=test_mode,
    )
    if sent:
        _WATCH_CURSORS[key]["pending"] = None
    return sent
