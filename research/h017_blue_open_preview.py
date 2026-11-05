"""H-017: causal, non-trading preview of the owner's BLUE M5 opening trigger.

Only the previously closed 5m context is allowed. A qualifying OPEN and
projected hourly 2-4 target are assessed by the existing 200-USDT/20-slot
risk policy. This is NOT a trade entry, fill, backtest or authorization.
"""
from __future__ import annotations

from research.causal_trend_geometry import CausalLine, TrendCandidate
from research.h017_local_risk import H017LocalRiskPolicy
from research.historical_market_replay import Candle


def blue_open_risk_preview(
    *,
    bar: Candle,
    known_trend: TrendCandidate | None,
    known_blue: CausalLine | None,
    policy: H017LocalRiskPolicy,
) -> dict[str, object] | None:
    """Evaluate only an opening already beyond the confirmed blue signal line.

    `bar.high/low/close` are deliberately never accessed. The caller publishes
    the preview only at bar.end_ms alongside the closed candle to preserve the
    existing MARKET_ONLY viewer's time-cursor contract.
    """
    if (
        known_trend is None or known_blue is None
        or known_trend.available_at_ms > bar.start_ms
        or known_blue.available_at_ms > bar.start_ms
    ):
        return None
    # The blue line must be the known opposite-direction correction slope,
    # not an arbitrary line or one fitted to the forming candle.
    side = known_trend.side
    if (side == "BULL" and (known_blue.first.kind != "HIGH" or known_blue.second.kind != "HIGH")) or (
        side == "BEAR" and (known_blue.first.kind != "LOW" or known_blue.second.kind != "LOW")
    ):
        return None
    at_open = known_blue.value_at(bar.start_ms)
    if (side == "BULL" and bar.open <= at_open) or (
        side == "BEAR" and bar.open >= at_open
    ):
        return None
    target_at_open = known_trend.target.value_at(bar.start_ms)
    if target_at_open <= 0:
        # No fabricated target or extrapolated negative order price.
        return None
    direction = "LONG" if side == "BULL" else "SHORT"
    # No tick-size metadata is supplied in the public candle contract:
    # the existing policy correctly falls back to its 0.7% fixed stop.
    intent = policy.proposal(
        side=direction, expected_entry=bar.open, target=target_at_open,
    )
    preview: dict[str, object] = {
        "source": "SIMULATION",
        "kind": "BLUE_5M_OPEN",
        "classification": "UNVALIDATED_GEOMETRY_ONLY",
        "time_ms": bar.end_ms,
        "open_ms": bar.start_ms,
        "trend_version": known_trend.available_at_ms,
        "blue_available_at_ms": known_blue.available_at_ms,
        "side": direction,
        "entry_price": str(bar.open),
        "blue_price": str(at_open),
        "target_price": str(target_at_open),
        "risk_status": "RISK_PASS" if intent is not None else "RISK_BELOW_1R",
    }
    if intent is not None:
        preview.update({
            "stop_price": str(intent.stop),
            "quantity": str(intent.quantity),
        })
    return preview
