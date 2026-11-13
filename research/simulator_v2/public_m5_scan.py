"""Original Scanner wedge / Ikigai Box on CLOSED public M5, observation only.

This path intentionally does NOT call Robot, trading, private APIs, PAPER
storage or VirtualExchange. A visible candidate is not an executable signal.
The server has already downloaded and validated immutable public M5; this
module reads that same document without re-fetching or future lookahead.
"""
from __future__ import annotations

from decimal import Decimal
import re

from research.historical_market_replay import Candle
from research.simulator_v2.wedge_observer import ReadOnlyWedgeScanner, WedgeScannerConfig

M5 = 300_000
MAX_PUBLIC_SCAN_BARS = 288
SELECTABLE = frozenset(("WEDGE_RISING", "WEDGE_FALLING", "IKIGAI_BOX"))
_RUN_RE = re.compile(r"^[a-zA-Z0-9_-]{1,100}$")
_SYMBOL_RE = re.compile(r"^[A-Z0-9]{3,30}USDT$")

# Explicit research preset, NOT inherited trading/production Scanner config.
WEDGE_RESEARCH_PRESET = WedgeScannerConfig(
    window_bars=300, mode="hunter", min_score=50,
)


def scan_public_closed_m5(
    document: dict[str, object], selected: tuple[str, ...],
) -> list[dict[str, object]]:
    if (not isinstance(selected, tuple) or len(selected) != len(set(selected))
            or not all(x in SELECTABLE for x in selected)):
        raise ValueError("only known local M5 research detectors can be selected")
    if not selected:
        return []
    if (document.get("mode") != "MARKET_ONLY"
            or document.get("market_data_source") != "BYBIT_PUBLIC_KLINE"
            or document.get("source") != "SIMULATION"
            or document.get("timeframe") != "5m"):
        raise ValueError("only independently verified public closed M5 permitted")
    symbol, run_id = document.get("symbol"), document.get("simulation_run_id")
    if (not isinstance(symbol, str) or not _SYMBOL_RE.fullmatch(symbol)
            or not isinstance(run_id, str) or not _RUN_RE.fullmatch(run_id)):
        raise ValueError("unscoped Scanner research")
    raw_events = document.get("events")
    if (not isinstance(raw_events, list) or not 1 <= len(raw_events) <= MAX_PUBLIC_SCAN_BARS):
        raise ValueError("Local Scanner M5 study supports at most one full UTC day")
    candles: list[Candle] = []
    previous = None
    for event in raw_events:
        if not isinstance(event, dict) or event.get("kind") != "CANDLE_CLOSED":
            raise ValueError("Scanner study requires candle-only history")
        raw = event.get("candle")
        if not isinstance(raw, dict) or type(raw.get("start_ms")) is not int or (
            type(raw.get("end_ms")) is not int
        ):
            raise ValueError("invalid closed M5 source time")
        bar = Candle(
            start_ms=raw["start_ms"], interval_ms=raw["end_ms"] - raw["start_ms"],
            open=Decimal(str(raw["open"])), high=Decimal(str(raw["high"])),
            low=Decimal(str(raw["low"])), close=Decimal(str(raw["close"])),
            volume=Decimal(str(raw["volume"])),
        )
        if (bar.interval_ms != M5 or bar.start_ms % M5 or
                bar.end_ms != event.get("time_ms") or
                (previous is not None and bar.start_ms != previous)):
            raise ValueError("Scanner study requires consecutive closed UTC M5")
        previous = bar.end_ms
        candles.append(bar)
    wedges = any(x.startswith("WEDGE_") for x in selected)
    box = "IKIGAI_BOX" in selected
    wedge_scanner = ReadOnlyWedgeScanner(WEDGE_RESEARCH_PRESET) if wedges else None
    if box:
        import pandas as pd
        from geometry.ikigai_box import detect_ikigai_box
    observed: list[dict[str, object]] = []
    seen: set[tuple[str, str]] = set()
    for count in range(1, len(candles) + 1):
        window = tuple(candles[max(0, count - 300):count])
        current = window[-1]
        if wedge_scanner and len(window) >= 50:
            result = wedge_scanner.evaluate_closed_m5_window(
                simulation_run_id=run_id, symbol=symbol,
                closed_at_ms=current.end_ms, bars=window,
            )
            if result is not None:
                category = ("WEDGE_FALLING" if result.pattern == "Falling Wedge"
                            else "WEDGE_RISING")
                source_id = result.formation_id
                if (category in selected and source_id is not None and
                        (category, source_id) not in seen):
                    seen.add((category, source_id))
                    observed.append({
                        "strategy": category, "timeframe": "5m",
                        "pattern": result.pattern, "signal_id": source_id,
                        "available_at_ms": current.end_ms,
                        "source_candle_start_ms": current.start_ms,
                        "close_price": float(current.close),
                        "status": "FILTER_APPROVED" if result.scanner_filter_approved
                                  else "FILTER_REJECTED",
                        "reason": result.scanner_filter_reason[:240],
                        "score": result.final_score,
                    })
        if box and len(window) >= 32:
            df = pd.DataFrame({
                key: [float(getattr(c, key)) for c in window]
                for key in ("open", "high", "low", "close")
            })
            formation = detect_ikigai_box(df)
            if formation is not None:
                a = window[formation.anchor_start_index].start_ms
                b = window[formation.anchor_end_index].start_ms
                identity = f"5m:{formation.direction}:{a}:{b}"
                if ("IKIGAI_BOX", identity) not in seen:
                    seen.add(("IKIGAI_BOX", identity))
                    observed.append({
                        "strategy": "IKIGAI_BOX", "timeframe": "5m",
                        "pattern": "Ikigai Box", "signal_id": identity,
                        "available_at_ms": current.end_ms,
                        "source_candle_start_ms": current.start_ms,
                        "close_price": float(current.close),
                        "status": "CONFIRMED_STRUCTURE_ONLY",
                        "reason": "No Robot Box order admission or risk authorization",
                        "side": formation.direction,
                        "box_start_ms": window[formation.box_start_index].start_ms,
                        "box_end_ms": window[formation.box_end_index].start_ms,
                        "box_low": formation.box_low,
                        "box_high": formation.box_high,
                    })
    if len(observed) > 512:
        raise ValueError("Scanner study exceeds bounded candidate count")
    return sorted(observed, key=lambda x: (x["available_at_ms"], x["strategy"], x["signal_id"]))
