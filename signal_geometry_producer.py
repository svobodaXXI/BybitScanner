"""Convert real Geometry Engine v2 two-anchor lines to frozen signal coordinates.

No line fitting, interpolation or chart-PNG reverse engineering.
Only use the very same OHLC dataframe returned by the Scanner analysis.
"""
import time
from signal_geometry_snapshot import validate_snapshot

TIMEFRAME_MS = {"1": 60000, "5": 300000, "15": 900000,
                "60": 3600000, "D": 86400000}

def build_wedge_geometry_snapshot(signal_id, symbol, timeframe, geometry, candles, *, now_ms=None):
    if not isinstance(geometry, dict) or not hasattr(candles, "itertuples"):
        return None
    try:
        tf_ms = TIMEFRAME_MS[str(timeframe)]
        now = int(now_ms if now_ms is not None else time.time() * 1000)
        rows = []
        for row in candles.itertuples(index=False):
            rows.append({
                "open_time_ms": int(row.time),
                "open": float(row.open), "high": float(row.high),
                "low": float(row.low), "close": float(row.close),
            })
        # Bybit kline returns the still-forming candle last. Keep closed candles
        # only; an anchor on a dropped candle fails the index check below.
        while rows and rows[-1]["open_time_ms"] + tf_ms > now:
            rows.pop()
        if not rows:
            return None
        boundaries = []
        for kind in ("upper", "lower"):
            line = geometry.get(kind + "_line")
            if not isinstance(line, dict) or line.get("model") != "anchor":
                return None  # Regression line has no proven two source anchors.
            a, z = line.get("anchor_index"), line.get("second_index")
            if type(a) is not int or type(z) is not int or not 0 <= a < z < len(rows):
                return None
            boundaries.append({
                "boundary_id": kind, "kind": "ray",
                "anchors": [
                    {"bar_open_time_ms": rows[index]["open_time_ms"], "price": line[field]}
                    for index, field in ((a, "anchor_price"), (z, "second_price"))
                ],
            })
        payload = {
            "schema_version": 1, "signal_id": str(signal_id),
            "symbol": str(symbol), "timeframe": str(timeframe),
            "bars": rows, "boundaries": boundaries,
        }
        validate_snapshot(payload, candidate_id=str(signal_id),
                          symbol=str(symbol), timeframe=str(timeframe))
        return payload
    except (KeyError, ValueError, TypeError, OverflowError, AttributeError):
        return None

def build_box_geometry_snapshot(signal_id, symbol, timeframe, formation, candles):
    """Frozen FIRST-impulse/Fibonacci geometry for Box Telegram Editor.

    Uses the detector's actual A/B wick prices and source-time closed candles;
    no reconstruction from current market bars, PNG, or Robot trading plan.
    """
    if formation is None or not hasattr(candles, "itertuples"):
        return None
    try:
        end = int(formation.as_of_index)
        a, b = int(formation.anchor_start_index), int(formation.anchor_end_index)
        if not 0 <= a < b <= end or end >= len(candles):
            return None
        rows = [{
            "open_time_ms": int(row.time),
            "open": float(row.open), "high": float(row.high),
            "low": float(row.low), "close": float(row.close),
        } for row in candles.iloc[:end + 1].itertuples(index=False)]
        times = [bar["open_time_ms"] for bar in rows]
        boundaries = [{
            "boundary_id": "box_first_impulse", "kind": "segment",
            "anchors": [
                {"bar_open_time_ms": times[a], "price": float(formation.anchor_start_price)},
                {"bar_open_time_ms": times[b], "price": float(formation.anchor_end_price)},
            ],
        }]
        for name, price in (
            ("box_fibonacci_1_0", formation.fibonacci_1_0),
            ("box_fibonacci_1_618", formation.fibonacci_1_618),
            ("box_fibonacci_2_618", formation.fibonacci_2_618),
        ):
            boundaries.append({
                "boundary_id": name, "kind": "horizontal-ray",
                "anchors": [{"bar_open_time_ms": times[b], "price": float(price)}],
            })
        payload = {
            "schema_version": 1, "signal_id": str(signal_id),
            "symbol": str(symbol), "timeframe": str(timeframe),
            "bars": rows, "boundaries": boundaries,
        }
        validate_snapshot(payload, candidate_id=str(signal_id),
                          symbol=str(symbol), timeframe=str(timeframe))
        return payload
    except (ValueError, TypeError, OverflowError, AttributeError, IndexError):
        return None
