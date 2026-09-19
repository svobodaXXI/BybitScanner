"""1m chart for one Robot position or closed Robot trade (read-only).

Pattern lines come only from the frozen candidate snapshot: the 1m
``robot_geometry`` lines are evaluated at the candle index produced by
``scanner_geometry_cursor.project_latest_geometry_index``; nothing is refit.
Horizontal levels show average entry, STOP and TAKE. Filled triangles are
executions (Buy up, Sell down); a hollow triangle is a resting limit order.
"""

from __future__ import annotations

import logging
import math
from pathlib import Path
from typing import Any, Mapping

import matplotlib as mpl

mpl.use("Agg")

import matplotlib.pyplot as plt  # noqa: E402
import matplotlib.transforms as mtransforms  # noqa: E402
import mplfinance as mpf  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

from robot_position_view import PositionView, format_price  # noqa: E402
from scanner_geometry_cursor import (  # noqa: E402
    ONE_MINUTE_MS, ScannerGeometryCursorError, project_latest_geometry_index,
)

mpl.rcParams["font.family"] = "DejaVu Sans"
logging.getLogger("matplotlib").setLevel(logging.ERROR)

CHARTS_DIR = Path(__file__).resolve().parent / "charts" / "robot"
MSK_OFFSET = pd.Timedelta(hours=3)
EXIT_DEDUP_MS = 2_000
BUY_COLOR = "#00a152"
SELL_COLOR = "#d50000"
ENTRY_COLOR = "#1e88e5"
STOP_COLOR = "#d50000"
TAKE_COLOR = "#00a152"
LINE_COLOR = "#ff9800"


class PositionChartError(RuntimeError):
    """Raised when a position chart cannot be rendered."""


def default_chart_path(symbol: str) -> Path:
    return CHARTS_DIR / f"{symbol}_position.png"


def _prepare_candles(candles_df) -> pd.DataFrame:
    if candles_df is None or len(candles_df) == 0:
        raise PositionChartError("no candles")
    df = candles_df.copy()
    df["time"] = pd.to_numeric(df["time"], errors="coerce")
    df = df.dropna(subset=["time", "open", "high", "low", "close"])
    if df.empty:
        raise PositionChartError("no candles")
    df["time"] = df["time"].astype("int64")
    df = df.sort_values("time").drop_duplicates("time").reset_index(drop=True)
    df.index = pd.to_datetime(df["time"], unit="ms") + MSK_OFFSET
    df.index.name = "Время (МСК)"
    return df


def _geometry_index(snapshot: Mapping[str, Any], time_ms: int, source_time_ms: int) -> float:
    if time_ms >= source_time_ms:
        return float(project_latest_geometry_index(snapshot, latest_closed_candle_time_ms=time_ms))
    # Before the frozen anchor the same cursor steps back one index per minute.
    elapsed = source_time_ms - time_ms
    if elapsed % ONE_MINUTE_MS:
        raise ScannerGeometryCursorError("candle time is not aligned to the cursor")
    anchor_index = project_latest_geometry_index(snapshot, latest_closed_candle_time_ms=source_time_ms)
    return float(anchor_index - elapsed // ONE_MINUTE_MS)


def _line_start_index(geometry: Mapping[str, Any], line: Mapping[str, Any]) -> float:
    anchor = line.get("anchor_index")
    if anchor is None:
        return -math.inf
    # anchor_index stays in Scanner source-bar units; express it in the 1m cursor space.
    try:
        minutes = int(str(geometry.get("scanner_source_timeframe", "1")).strip())
        current = float(geometry.get("current_index"))
    except (TypeError, ValueError):
        return float(anchor)
    return current - (current - float(anchor)) * minutes


def _pattern_lines(view: PositionView, times: np.ndarray) -> list[np.ndarray]:
    snapshot = view.signal_snapshot
    if not isinstance(snapshot, Mapping):
        return []
    geometry = snapshot.get("robot_geometry")
    cursor = snapshot.get("scanner_geometry_cursor")
    if not isinstance(geometry, Mapping) or not isinstance(cursor, Mapping):
        return []
    try:
        source_time_ms = int(cursor["source_candle_time_ms"])
        indices = np.array([_geometry_index(snapshot, int(t), source_time_ms) for t in times])
        apex = geometry.get("apex")
        apex_index = float(apex["index"]) if isinstance(apex, Mapping) else math.inf
    except (ScannerGeometryCursorError, KeyError, TypeError, ValueError) as exc:
        print("[POSITION CHART] geometry skipped:", exc)
        return []

    lines = []
    for key in ("upper_line", "lower_line"):
        line = geometry.get(key)
        if not isinstance(line, Mapping):
            continue
        try:
            values = float(line["slope"]) * indices + float(line["intercept"])
        except (KeyError, TypeError, ValueError):
            continue
        values = values.astype(float)
        values[(indices < _line_start_index(geometry, line)) | (indices > apex_index)] = np.nan
        if np.isfinite(values).any():
            lines.append(values)
    return lines


def _candle_position(times: np.ndarray, time_ms: int) -> int | None:
    position = int(np.searchsorted(times, time_ms, side="right")) - 1
    if position < 0 or time_ms >= times[position] + ONE_MINUTE_MS:
        return None
    return position


def _draw_marker(ax, x: int, price: float, side: str, *, filled: bool) -> None:
    color = BUY_COLOR if side == "Buy" else SELL_COLOR
    ax.scatter(
        [x], [price],
        marker="^" if side == "Buy" else "v",
        s=140,
        facecolors=color if filled else "none",
        edgecolors="black" if filled else color,
        linewidths=0.8 if filled else 1.8,
        zorder=6,
    )


def _draw_level(ax, price: float, label: str, color: str, style: str) -> None:
    ax.axhline(price, color=color, linestyle=style, linewidth=1.2, zorder=4)
    transform = mtransforms.blended_transform_factory(ax.transAxes, ax.transData)
    ax.text(
        0.995, price, f"{label} {format_price(price)}",
        transform=transform, color=color, fontsize=9, va="bottom", ha="right",
        bbox={"facecolor": "white", "edgecolor": "none", "alpha": 0.8, "pad": 1},
        zorder=7,
    )


def render_position_chart(view: PositionView, candles_df, out_path: Path | str | None = None) -> Path:
    df = _prepare_candles(candles_df)
    times = df["time"].to_numpy(dtype="int64")
    out = Path(out_path) if out_path is not None else default_chart_path(view.symbol)
    out.parent.mkdir(parents=True, exist_ok=True)

    addplots = [
        mpf.make_addplot(values, color=LINE_COLOR, width=2)
        for values in _pattern_lines(view, times)
    ]
    title = f"{view.symbol} | {view.pattern or '—'} | {view.direction} | 1m"
    plot_kwargs = dict(
        type="candle", style="charles", title=title, volume=False, figsize=(12, 6),
        datetime_format="%H:%M", xrotation=0, ylabel="", returnfig=True,
    )
    if addplots:
        plot_kwargs["addplot"] = addplots
    fig, axes = mpf.plot(df[["open", "high", "low", "close"]], **plot_kwargs)
    try:
        ax = axes[0]
        ax.set_xlabel("Время (МСК)")

        levels = [
            (view.average_entry, "Вход", ENTRY_COLOR, "--"),
            (view.stop_price, "STOP", STOP_COLOR, "-"),
            (view.take_price, "TAKE", TAKE_COLOR, "-"),
        ]
        prices = [float(df["low"].min()), float(df["high"].max())]
        for price, label, color, style in levels:
            if price is not None:
                _draw_level(ax, float(price), label, color, style)
                prices.append(float(price))

        markers = [(m.time_ms, float(m.price), m.side, m.filled) for m in view.markers]
        if view.exit_time_ms is not None and view.exit_price is not None:
            exit_price = float(view.exit_price)
            # MARKET/MIXED windows already include the exit execution; do not draw it twice.
            already_drawn = any(
                filled and abs(time_ms - view.exit_time_ms) <= EXIT_DEDUP_MS
                and math.isclose(price, exit_price, rel_tol=1e-9)
                for time_ms, price, _, filled in markers
            )
            if not already_drawn:
                exit_side = "Sell" if view.direction == "LONG" else "Buy"
                markers.append((view.exit_time_ms, exit_price, exit_side, True))
        for time_ms, price, side, filled in markers:
            x = _candle_position(times, int(time_ms))
            if x is not None:
                _draw_marker(ax, x, price, side, filled=filled)
                prices.append(price)

        low, high = min(prices), max(prices)
        pad = (high - low) * 0.05 or abs(high) * 0.01 or 1.0
        ax.set_ylim(low - pad, high + pad)
        fig.savefig(out, dpi=100, bbox_inches="tight")
    finally:
        plt.close(fig)

    if not out.exists() or out.stat().st_size == 0:
        raise PositionChartError("chart file was not written")
    return out
