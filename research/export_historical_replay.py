"""Read-only Bybit OHLCV -> standalone SIMULATION viewer JSON.

Market-only export deliberately produces NO trades or fabricated strategy signals.
Account credentials, PAPER database, Robot and order endpoints are never used.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import re
import secrets

from research.historical_candle_feed import (
    ClosedHigherTimeframeFeed, FIVE_MINUTES_MS, load_closed_five_minute_history,
    replay_with_closed_context,
)
from research.h017_blue_open_preview import blue_open_risk_preview
from research.h017_local_risk import H017LocalRiskPolicy
from research.causal_trend_geometry import main_line_contact

SIMULATION_OUTPUT = Path(__file__).resolve().parent / "simulation_runs"
MAX_BARS = 50_000
RUN_ID_RE = re.compile(r"^[A-Za-z0-9_-]{1,100}$")
SYMBOL_RE = re.compile(r"^[A-Z0-9]{3,30}$")


def build_market_only_document(
    *, symbol: str, start_ms: int, end_ms: int, run_id: str, fetch_candles,
    geometry_warmup_bars: int = 0,
) -> dict[str, object]:
    """Pure conversion with injected public-market fetch, no filesystem effects."""
    if not SYMBOL_RE.fullmatch(symbol):
        raise ValueError("invalid Bybit symbol")
    if not RUN_ID_RE.fullmatch(run_id):
        raise ValueError("invalid SIMULATION run ID")
    if end_ms <= start_ms or (end_ms - start_ms) // FIVE_MINUTES_MS > MAX_BARS:
        raise ValueError("history range exceeds 50000 5m bars or is empty")
    if (end_ms - start_ms) % FIVE_MINUTES_MS:
        raise ValueError("history boundaries must align to 5m")
    if type(geometry_warmup_bars) is not int or not 0 <= geometry_warmup_bars <= 864:
        raise ValueError("geometry warmup must be 0..864 closed 5m bars")
    # A bar whose start is in the future must never become a completed candle.
    now_ms = int(datetime.now(timezone.utc).timestamp() * 1000)
    if end_ms > (now_ms // FIVE_MINUTES_MS) * FIVE_MINUTES_MS:
        raise ValueError("future/forming candles are not valid history")
    preload_start_ms = max(0, start_ms - geometry_warmup_bars * FIVE_MINUTES_MS)
    all_candles = load_closed_five_minute_history(
        symbol=symbol, start_ms=preload_start_ms, end_ms=end_ms,
        fetch_candles=fetch_candles,
    )
    preload_count = (start_ms - preload_start_ms) // FIVE_MINUTES_MS
    warmup_candles = all_candles[:preload_count]
    candles = all_candles[preload_count:]
    # Closed H1 evidence used during hidden warmup, never a visible replay bar.
    # The viewer needs it to compare prior H1 extremes when the immutable
    # first trendline wick predates the seven-day display window.
    context = ClosedHigherTimeframeFeed()
    context_1h = []
    for earlier in warmup_candles:
        _, _, newly_closed_hour, _ = context.observe_closed_five_minute(earlier)
        if newly_closed_hour is not None:
            context_1h.append({
                "start_ms": newly_closed_hour.start_ms,
                "end_ms": newly_closed_hour.end_ms,
                "open": str(newly_closed_hour.open),
                "high": str(newly_closed_hour.high),
                "low": str(newly_closed_hour.low),
                "close": str(newly_closed_hour.close),
                "volume": str(newly_closed_hour.volume),
            })
    events = []
    geometry: list[dict[str, object]] = []
    observations: list[dict[str, object]] = []
    blue_risk_previews: list[dict[str, object]] = []
    blue_retirements: list[dict[str, object]] = []
    hourly_prior_updates: list[dict[str, object]] = []
    hourly_prior_breaks: list[dict[str, object]] = []
    last_prior_identity: tuple[str, int, object] | None = None
    risk_policy = H017LocalRiskPolicy()
    previous_trend = None
    previous_blue = None
    dmi_points: list[dict[str, object]] = []
    pending_contact: tuple[int, int, str, object] | None = None
    versions: dict[str, tuple[int, int, int]] = {}
    # The exported publication time can differ from CausalLine.available_at_ms
    # when an unchanged M5 correction is republished under a revised H1 trend.
    published_at: dict[str, int] = {}

    def collect_lines(view) -> None:
        def collect(kind: str, line, side: str, trend_version: int, pivots,
                    envelope_status: str | None = None) -> None:
            if pivots is None or len(pivots) != 4:
                raise ValueError("a published line must retain four source pivots")
            if any(point.confirmed_at_ms > view.five_minute.signal_time_ms for point in pivots):
                raise ValueError("source pivot belongs to the future")
            identity = (line.first.at_ms, line.second.at_ms, trend_version)
            if versions.get(kind) == identity:
                return
            if line.available_at_ms > view.five_minute.signal_time_ms:
                raise ValueError("future geometry in simulated market archive")
            versions[kind] = identity
            published_at[kind] = view.five_minute.signal_time_ms
            geometry.append({
                "kind": kind, "side": side,
                "available_at_ms": view.five_minute.signal_time_ms,
                "from_ms": line.first.at_ms, "to_ms": line.second.at_ms,
                "from_price": str(line.first.price), "to_price": str(line.second.price),
                "trend_version": trend_version,
                # These are structural confirmed extrema. A wick-envelope
                # fitting point may differ but must never replace their identity.
                "source_pivots": [
                    {"kind": point.kind, "at_ms": point.at_ms,
                     "confirmed_at_ms": point.confirmed_at_ms,
                     "price": str(point.price)}
                    for point in pivots
                ],
                "classification": "UNVALIDATED_GEOMETRY_ONLY",
                **({"envelope_status": envelope_status}
                   if envelope_status is not None else {}),
            })

        trend = view.hourly_trend
        if trend is not None:
            collect("MAIN_1H", trend.main, trend.side,
                    trend.available_at_ms, trend.pivot_sequence,
                    trend.envelope_status)
            collect("TARGET_1H", trend.target, trend.side,
                    trend.available_at_ms, trend.pivot_sequence,
                    trend.envelope_status)
            if view.reference_5m is not None:
                collect("REFERENCE_5M", view.reference_5m, trend.side,
                        trend.available_at_ms, view.reference_5m_pivots)
            if view.acceleration_5m is not None:
                collect("ACCELERATION_5M", view.acceleration_5m, trend.side,
                        trend.available_at_ms, view.acceleration_5m_pivots)

    def collect_main_line_observations(view) -> None:
        nonlocal pending_contact
        bar = view.five_minute.bar
        trend = view.hourly_trend
        # An H1 line discovered at THIS candle's close was not known at open.
        if trend is None or trend.available_at_ms > bar.start_ms:
            pending_contact = None
            return
        at_close = trend.main.value_at(bar.end_ms)
        # A follow-through is only the immediately following closed 5m bar.
        # Its existence does not turn a touch into an approved trade trigger.
        if pending_contact is not None:
            time_ms, version, side, prior_close = pending_contact
            if time_ms == bar.start_ms and version == trend.available_at_ms and side == trend.side:
                moving_away = (bar.close > prior_close and bar.close > at_close) if side == "BULL" else (
                    bar.close < prior_close and bar.close < at_close
                )
                if moving_away:
                    observations.append({
                        "kind": "MAIN_1H_REACTION", "side": side, "time_ms": bar.end_ms,
                        "touch_time_ms": time_ms, "price": str(bar.close),
                        "line_price": str(at_close), "trend_version": version,
                        "classification": "UNVALIDATED_GEOMETRY_ONLY",
                    })
        contact_at = main_line_contact(trend, bar)
        if contact_at is None:
            pending_contact = None
            return
        observations.append({
            "kind": "MAIN_1H_TOUCH", "side": trend.side, "time_ms": bar.end_ms,
            "price": str(bar.close), "line_price": str(contact_at),
            "trend_version": trend.available_at_ms,
            "classification": "UNVALIDATED_GEOMETRY_ONLY",
        })
        pending_contact = (bar.end_ms, trend.available_at_ms, trend.side, bar.close)

    def collect_context(view) -> None:
        nonlocal previous_trend, previous_blue, last_prior_identity
        # Only geometry known at the PRIOR close may qualify this bar OPEN.
        preview = blue_open_risk_preview(
            bar=view.five_minute.bar, known_trend=previous_trend,
            known_blue=previous_blue, policy=risk_policy,
        )
        if preview is not None:
            blue_risk_previews.append(preview)
        snapshot = view.dmi_5m
        # The 5m candle and its DMI snapshot become visible at the same close.
        if snapshot is None or snapshot.time_ms != view.five_minute.signal_time_ms:
            raise ValueError("DMI snapshot does not match last closed five-minute bar")
        dmi_points.append({
            "time_ms": snapshot.time_ms,
            "plus_di": str(snapshot.plus_di) if snapshot.plus_di is not None else None,
            "minus_di": str(snapshot.minus_di) if snapshot.minus_di is not None else None,
            "adx": str(snapshot.adx) if snapshot.adx is not None else None,
            "crossings": [
                {"time_ms": cross.time_ms, "side": cross.side,
                 "direction": cross.direction, "comparator": cross.comparator}
                for cross in snapshot.crossings
            ],
        })
        collect_lines(view)
        # The strategy's frozen confirmed prior is authoritative. Export its
        # changes once, rather than independently refitting purple levels from
        # yellow geometry in the browser. A warmup prior first becomes visible
        # on the FIRST displayed M5 close, not during hidden history.
        prior = view.hourly_prior_price
        touch = view.hourly_prior_touch_ms
        trend = view.hourly_trend
        if prior is not None and touch is not None and trend is not None:
            identity = (trend.side, touch, prior)
            if identity != last_prior_identity:
                if touch >= view.five_minute.signal_time_ms:
                    raise ValueError("future hourly prior touch")
                hourly_prior_updates.append({
                    "kind": "H1_PRIOR_CONFIRMED", "side": trend.side,
                    "at_ms": touch, "price": str(prior),
                    "available_at_ms": view.five_minute.signal_time_ms,
                    "trend_version": trend.available_at_ms,
                    "classification": "UNVALIDATED_GEOMETRY_ONLY",
                })
                last_prior_identity = identity
        else:
            last_prior_identity = None
        break_event = getattr(view, "hourly_prior_break", None)
        if break_event is not None:
            # Never attribute a warmup-only break to an unpublished prior.
            if any(
                level["trend_version"] == break_event["trend_version"] and
                level["at_ms"] == break_event["prior_at_ms"] and
                level["price"] == str(break_event["prior_price"])
                for level in hourly_prior_updates
            ):
                hourly_prior_breaks.append({
                    "kind": "PRIOR_CLOSE_NEXT_OPEN",
                    **{key: str(value) if key == "prior_price" else value
                       for key, value in break_event.items()},
                })
        collect_main_line_observations(view)
        # The old frozen correction remains active through later M5 pivots.
        # The first known M5 OPEN on the H1 trend side of that line retires
        # it at this CLOSED M5, without revising earlier chart history.
        if (previous_blue is not None and view.reference_5m is None and
                previous_trend is not None and view.hourly_trend is not None and
                previous_trend.side == view.hourly_trend.side and
                previous_trend.main.first.at_ms == view.hourly_trend.main.first.at_ms):
            bar = view.five_minute.bar
            level = previous_blue.value_at(bar.start_ms)
            beyond = ((previous_trend.side == "BULL" and bar.open > level) or
                      (previous_trend.side == "BEAR" and bar.open < level))
            # A correction may have existed only during the pre-history
            # warmup, then broken on the FIRST displayed M5. The current
            # archive has no such prior line, so it must not invent a
            # retirement referencing a non-exported geometry version.
            published = versions.get("REFERENCE_5M") == (
                previous_blue.first.at_ms,
                previous_blue.second.at_ms,
                previous_trend.available_at_ms,
            )
            if beyond and published:
                blue_retirements.append({
                    "kind": "REFERENCE_5M_OPEN_BREAK",
                    "time_ms": bar.end_ms, "open_ms": bar.start_ms,
                    # Point to the exact EXPORTED blue version, not its
                    # original first-confirmation time (which may predate a
                    # same-movement H1 revision).
                    "blue_available_at_ms": published_at["REFERENCE_5M"],
                    "trend_version": previous_trend.available_at_ms,
                })
        previous_trend = view.hourly_trend
        previous_blue = view.reference_5m

    result = replay_with_closed_context(
        simulation_run_id=run_id,
        candles=candles,
        geometry_warmup_candles=warmup_candles,
        on_closed_context=collect_context,
        on_visual_event=lambda event: events.append(event.to_payload()),
    )
    if result.trades or result.open_position or len(events) != len(candles):
        raise ValueError("market-only replay unexpectedly produced trading state")
    if len(dmi_points) != len(candles):
        raise ValueError("market-only DMI timeline does not match completed candles")
    return {
        "source": "SIMULATION", "simulation_run_id": run_id,
        "mode": "MARKET_ONLY", "market_data_source": "BYBIT_PUBLIC_KLINE",
        "symbol": symbol, "timeframe": "5m",
        "from_ms": start_ms, "until_ms": end_ms,
        "events": events,
        "geometry": geometry,
        "hourly_prior_updates": hourly_prior_updates,
        "hourly_prior_breaks": hourly_prior_breaks,
        "reference_5m_retirements": blue_retirements,
        "observations": observations,
        "h017_blue_risk_previews": blue_risk_previews,
        "geometry_warmup_hours": len(warmup_candles) // 12,
        "context_1h": context_1h,
        "dmi_5m": {
            "source": "SIMULATION", "timeframe": "5m",
            "di_length": 14, "adx_smoothing": 14,
            "points": dmi_points,
        },
    }


def write_run_document(document: dict[str, object], root: Path = SIMULATION_OUTPUT) -> Path:
    """Write only new SIMULATION files to the dedicated output root.

    No caller-controlled output filename/path and no replacement of previous
    runs. An existing symlinked output directory is rejected.
    """
    run_id = document.get("simulation_run_id")
    if document.get("source") != "SIMULATION" or not isinstance(run_id, str) or not RUN_ID_RE.fullmatch(run_id):
        raise ValueError("refusing non-SIMULATION output")
    if root.is_symlink():
        raise ValueError("simulation output cannot be a symlink")
    root.mkdir(exist_ok=True)
    if root.is_symlink() or not root.is_dir():
        raise ValueError("simulation output is not a safe directory")
    target = root / f"{run_id}.json"
    payload = json.dumps(document, ensure_ascii=False, separators=(",", ":"), allow_nan=False)
    # Exclusive open: never overwrite a previous run or any existing PAPER file.
    with target.open("x", encoding="utf-8") as handle:
        handle.write(payload)
        handle.write("\n")
    return target


def parse_date_utc(value: str) -> int:
    parsed = datetime.strptime(value, "%Y-%m-%d").replace(tzinfo=timezone.utc)
    return int(parsed.timestamp() * 1000)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Export historical Bybit 5m candles for offline SIMULATION viewer; no trades",
    )
    parser.add_argument("--symbol", required=True, help="Bybit linear symbol, e.g. BTCUSDT")
    parser.add_argument("--start", required=True, help="UTC day inclusive: YYYY-MM-DD")
    parser.add_argument("--end", required=True, help="UTC day exclusive: YYYY-MM-DD")
    parser.add_argument("--run-id", help="Safe unique research run identifier")
    args = parser.parse_args()
    run_id = args.run_id or ("market_" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S") + "_" + secrets.token_hex(4))
    # Import solely the repository's existing PUBLIC GET kline wrapper at actual
    # execution time; no order/account credentials and no runtime startup.
    from bybit_api import get_candles
    document = build_market_only_document(
        symbol=args.symbol, start_ms=parse_date_utc(args.start),
        end_ms=parse_date_utc(args.end), run_id=run_id,
        fetch_candles=get_candles,
    )
    output = write_run_document(document)
    print(f"SIMULATION MARKET_ONLY: {len(document['events'])} closed candles; file={output}")
    print("Open terminal/frontend/replay.html via the standalone frontend dev/preview server, then select this JSON.")


if __name__ == "__main__":
    main()
