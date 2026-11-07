"""Frozen MIRROR event chart (presentation only, no market-data fetches)."""

from __future__ import annotations

from datetime import datetime, timezone
import math
from pathlib import Path
from typing import Mapping, Sequence


def _visible_event_candles(snapshot: Mapping) -> Sequence[Mapping]:
    """Show an older selected source anchor when its exact frozen OHLC exists.

    The 120-candle event window remains the fallback for legacy or truncated
    evidence. Never invent historical candles or extend a line from a guessed
    origin. The expanded history must share the exact event-window tail.
    """
    recent = snapshot.get("candles") or ()
    if not recent:
        return recent
    selected = [level for level in snapshot.get("levels", ())
                if level.get("selected") is True]
    if len(selected) != 1 or not selected[0].get("anchors"):
        return recent
    source_anchor = min(int(anchor[0]) for anchor in selected[0]["anchors"])
    if source_anchor >= int(recent[0]["open_time_ms"]):
        return recent
    history = snapshot.get("geometry_candles") or ()
    if not isinstance(history, list) or len(history) <= len(recent):
        return recent
    if source_anchor not in {int(bar["open_time_ms"]) for bar in history}:
        return recent  # Outside retained immutable evidence; no invented OHLC.
    fields = ("open_time_ms", "open", "high", "low", "close")
    if any(
        tuple(old[field] for field in fields) != tuple(new[field] for field in fields)
        for old, new in zip(history[-len(recent):], recent)
    ):
        raise ValueError("MIRROR frozen source context disagrees with event candles")
    return history


def render_mirror_chart(snapshot: Mapping, output_path: str | Path) -> None:
    """Draw only candles and geometry frozen when the MIRROR event occurred.

    Raises ValueError if the evidence is incomplete; callers must not substitute
    a newer symbol chart and misrepresent it as the event's source.
    """
    rows = _visible_event_candles(snapshot)
    if not rows:
        raise ValueError("missing MIRROR event candles")
    levels = snapshot.get("levels") or ()
    if not levels:
        raise ValueError("missing MIRROR source geometry")
    import matplotlib
    matplotlib.use("Agg")
    from matplotlib import pyplot as plt
    from matplotlib.patches import Rectangle

    # Prioritize vertical geometry readability over a wide, shallow chart.
    fig, ax = plt.subplots(figsize=(11, 7.2), dpi=130)
    try:
        fig.patch.set_facecolor("#111827")
        ax.set_facecolor("#111827")
        times = [int(r["open_time_ms"]) for r in rows]
        if times != sorted(set(times)):
            raise ValueError("non-monotonic MIRROR candles")
        for i, row in enumerate(rows):
            o, h, low, c = (float(row[k]) for k in ("open", "high", "low", "close"))
            if not all(math.isfinite(x) for x in (o, h, low, c)) or not low <= min(o, c) <= max(o, c) <= h:
                raise ValueError("invalid MIRROR OHLC")
            color = "#34d399" if c >= o else "#fb7185"
            ax.vlines(i, low, h, color=color, linewidth=0.9)
            ax.add_patch(Rectangle((i - 0.27, min(o, c)), 0.54, max(abs(c - o), (h - low) * 0.002),
                                   facecolor=color, edgecolor=color, linewidth=0.5))
        from mirror_scanner import mirror_subtype
        subtype = mirror_subtype(snapshot.get("source"), snapshot.get("pattern"),
                                 snapshot.get("event_kind", "breakout"),
                                 retest_confirmed=snapshot.get("retest_confirmed") is True)
        for level in levels:
            boundary = level["boundary"]
            anchor_t = int(boundary["anchor_time_ms"])
            anchor_p = float(boundary["anchor_price"])
            slope = float(boundary["slope_per_ms"])
            if not all(math.isfinite(v) for v in (anchor_p, slope)):
                raise ValueError("invalid MIRROR line")
            # A confirmed level starts at its actual anchor, never to the left.
            visible = [(i, anchor_p + slope * (t - anchor_t))
                       for i, t in enumerate(times) if t >= anchor_t]
            if not visible:
                continue
            selected = level.get("selected", False)
            color = "#fbbf24" if selected else "#60a5fa"
            ax.plot([x for x, _ in visible], [y for _, y in visible],
                    color=color, linewidth=1.9 if selected else 1.4,
                    linestyle="-" if selected else "--",
                    label=(subtype if selected else "Граница источника"))
            # Mark the actual extremum only when its candle is visible.
            # Otherwise the line continues from an off-chart historic anchor.
            if anchor_t in times:
                anchor_idx = times.index(anchor_t)
                ax.scatter([anchor_idx], [anchor_p],
                           color=color, s=20, zorder=5)
        event_t = snapshot.get("event_open_time_ms")
        if event_t is not None:
            event_idx = next((i for i, t in enumerate(times) if t >= int(event_t)), None)
            if event_idx is not None:
                event_name = ("Первый ретест" if snapshot.get("event_kind") == "first_retest"
                              else "Пробой")
                ax.axvline(event_idx, color="#e5e7eb", alpha=0.5, linestyle=":", label=event_name)
                ax.scatter([event_idx], [float(rows[event_idx]["close"])],
                           color="#ffffff", s=28, marker="o", zorder=6)
        # Keep the event candle around 75% of the horizontal span instead
        # of pinning it to the far right edge of the Telegram image.
        left = -0.8
        right = left + (len(rows) - 1 - left) / 0.75
        ax.set_xlim(left, right)
        ticks = sorted(set([0, len(rows) // 4, len(rows) // 2, 3 * len(rows) // 4, len(rows) - 1]))
        ax.set_xticks(ticks, [datetime.fromtimestamp(times[i] / 1000, timezone.utc).strftime("%d.%m %H:%M")
                              for i in ticks], rotation=20, ha="right")
        ax.tick_params(colors="#e5e7eb", labelsize=8)
        for spine in ax.spines.values():
            spine.set_color("#4b5563")
        ax.grid(alpha=0.12)
        title = f"MIRROR · {snapshot.get('symbol', '—')} · {snapshot.get('timeframe', '—')}m\n{subtype}"
        if snapshot.get("event_kind") == "breakout":
            close = snapshot.get("breakout_close")
            boundary = snapshot.get("breakout_boundary_at_close")
            if close is not None and boundary is not None:
                from mirror_scanner import _retest_potential_percent
                potential = _retest_potential_percent(boundary, close)
                if potential.is_finite() and float(close) > 0 and math.isfinite(float(boundary)):
                    title += (f"\nПробой: свеча закрыта за уровнем · Close {float(close):.8g}"
                              f" · до ретеста {potential:.2f}%")
        ax.set_title(title, color="white")
        ax.legend(loc="best", fontsize=8, facecolor="#1f2937", labelcolor="white")
        fig.tight_layout()
        fig.savefig(str(output_path), format="png", facecolor=fig.get_facecolor())
    finally:
        plt.close(fig)
