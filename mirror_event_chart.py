"""Frozen MIRROR event chart (presentation only, no market-data fetches)."""

from __future__ import annotations

from datetime import datetime, timezone
import math
from pathlib import Path
from typing import Mapping, Sequence


def render_mirror_chart(snapshot: Mapping, output_path: str | Path) -> None:
    """Draw only candles and geometry frozen when the MIRROR event occurred.

    Raises ValueError if the evidence is incomplete; callers must not substitute
    a newer symbol chart and misrepresent it as the event's source.
    """
    rows = snapshot.get("candles") or ()
    if not rows:
        raise ValueError("missing MIRROR event candles")
    levels = snapshot.get("levels") or ()
    if not levels:
        raise ValueError("missing MIRROR source geometry")
    import matplotlib
    matplotlib.use("Agg")
    from matplotlib import pyplot as plt
    from matplotlib.patches import Rectangle

    fig, ax = plt.subplots(figsize=(11, 5.4), dpi=130)
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
        ax.set_xlim(-0.8, len(rows) + 0.2)
        ticks = sorted(set([0, len(rows) // 4, len(rows) // 2, 3 * len(rows) // 4, len(rows) - 1]))
        ax.set_xticks(ticks, [datetime.fromtimestamp(times[i] / 1000, timezone.utc).strftime("%d.%m %H:%M")
                              for i in ticks], rotation=20, ha="right")
        ax.tick_params(colors="#e5e7eb", labelsize=8)
        for spine in ax.spines.values():
            spine.set_color("#4b5563")
        ax.grid(alpha=0.12)
        ax.set_title(f"MIRROR · {snapshot.get('symbol', '—')} · {snapshot.get('timeframe', '—')}m\n{subtype}",
                     color="white")
        ax.legend(loc="best", fontsize=8, facecolor="#1f2937", labelcolor="white")
        fig.tight_layout()
        fig.savefig(str(output_path), format="png", facecolor=fig.get_facecolor())
    finally:
        plt.close(fig)
