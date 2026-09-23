"""Local-only L-shape observer for Scanner-owned Bybit OHLC snapshots.

Enabled by BYBITSCANNER_L_SHAPE_OBSERVATIONS=1 in main. No fetching,
notification, signal memory or Robot admission. Detector defaults are unchanged.
"""

from pathlib import Path
import re

from geometry.l_shape import detect_l_shape
from geometry.l_shape_preview import render_l_shape_preview


def observe_l_shape(symbol, candles, *, timeframe, chart_dir="charts"):
    """Report and render a candidate using only the snapshot's closed prefix.

    Scanner's Bybit snapshot includes the newest possibly open candle; exclude
    it before detection and rendering. The filename preserves the decision bar
    and impulse origin, independently of existing pattern chart paths.
    """
    if candles is None or len(candles) < 2:
        return None
    symbol, timeframe = str(symbol), str(timeframe).strip()
    if not re.fullmatch(r"[A-Z0-9]+", symbol) or not timeframe.isdecimal():
        raise ValueError("invalid L-shape symbol or timeframe")
    closed = candles.iloc[:-1].copy().reset_index(drop=True)
    formation = detect_l_shape(closed)
    if formation is None:
        return None
    source_time = int(closed.iloc[formation.as_of_index]["time"])
    origin_time = int(closed.iloc[formation.start_index]["time"])
    chart = Path(chart_dir) / "l_shape" / (
        f"{symbol}_{timeframe}_{formation.direction}_{origin_time}_{source_time}.png"
    )
    # Report the candidate even if the subsequent renderer fails.
    print(
        f"{symbol:<15} L-SHAPE candidate {formation.direction} "
        f"source_candle_time_ms={source_time} start_time_ms={origin_time}"
    )
    chart.parent.mkdir(parents=True, exist_ok=True)
    render_l_shape_preview(
        closed, formation, chart, symbol=symbol, timeframe=timeframe,
    )
    print(f"{symbol:<15} L-SHAPE preview {chart}")
    return {
        "formation": formation,
        "source_candle_time_ms": source_time,
        "chart_path": str(chart),
    }
