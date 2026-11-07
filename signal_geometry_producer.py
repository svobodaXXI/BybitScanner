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
