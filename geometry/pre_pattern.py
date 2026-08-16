"""
geometry.pre_pattern

??????????? ???????? ???? ????? ??????? ?????????????? ?????????.

?? ??????? ?????:
- ?? ?????? ?? Validation;
- ?? ?????? ?? Ranking;
- ?? ?????? anchors;
- ?????? ???????? pre-pattern context.
"""


def detect_pre_pattern_impulse(
    candles,
    start_index,
    lookback=20
):
    if (
        candles is None
        or start_index is None
        or start_index <= 0
    ):
        return None

    window_start = max(
        0,
        int(start_index) - int(lookback)
    )

    window_end = int(start_index)

    if window_end <= window_start:
        return None

    try:
        first_close = float(
            candles.iloc[window_start]["close"]
        )

        last_close = float(
            candles.iloc[window_end]["close"]
        )
    except Exception:
        return None

    if first_close <= 0:
        return None

    change_percent = (
        (last_close - first_close)
        / first_close
        * 100.0
    )

    if change_percent > 0:
        direction = "UP"
    elif change_percent < 0:
        direction = "DOWN"
    else:
        direction = "FLAT"

    return {
        "window_start": window_start,
        "window_end": window_end,
        "lookback": window_end - window_start,
        "first_close": first_close,
        "last_close": last_close,
        "change_percent": float(
            change_percent
        ),
        "direction": direction
    }
