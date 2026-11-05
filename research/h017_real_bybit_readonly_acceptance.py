"""One-off H-017 real Bybit read-only market-history acceptance.

Runs in isolated GitHub Actions. Uses the existing public GET adapter, no
credentials, no orders, no PAPER state, no synthetic fallback, no disk writes.
The 7 visible UTC days have 72h of earlier closed-candle geometry warmup.
"""
from __future__ import annotations

import hashlib
import json
from decimal import Decimal

from research.local_replay_viewer.server import load_public_history, BYBIT_PUBLIC_KLINE

SYMBOL = "GRASSUSDT"
START = "2026-07-29"
END = "2026-08-05"
EXPECTED_VISIBLE_BARS = 7 * 24 * 12
M5 = 300_000


def check() -> dict[str, object]:
    doc = load_public_history(symbol=SYMBOL, start=START, end=END)
    events = doc["events"]
    if (doc["source"], doc["mode"], doc["market_data_source"], doc["symbol"]) != (
        "SIMULATION", "MARKET_ONLY", "BYBIT_PUBLIC_KLINE", SYMBOL
    ):
        raise AssertionError("wrong public-market research identity")
    if len(events) != EXPECTED_VISIBLE_BARS or doc["geometry_warmup_hours"] != 72:
        raise AssertionError("incomplete public history or warmup")
    bars = []
    expected_open = doc["from_ms"]
    for index, event in enumerate(events):
        if event["kind"] != "CANDLE_CLOSED" or event["time_ms"] != expected_open + M5:
            raise AssertionError(f"non-causal/partial market event at {index}")
        bar = event["candle"]
        if bar["start_ms"] != expected_open or bar["end_ms"] != expected_open + M5:
            raise AssertionError(f"broken public market 5m continuity at {index}")
        bars.append(bar)
        expected_open += M5
    if expected_open != doc["until_ms"]:
        raise AssertionError("unexpected UTC range")
    if doc.get("mode") != "MARKET_ONLY" or any(
        event["kind"] != "CANDLE_CLOSED" or "trade_id" in event for event in events
    ):
        raise AssertionError("fake trade state in read-only market replay")
    by_start = {bar["start_ms"]: bar for bar in bars}
    if len(by_start) != EXPECTED_VISIBLE_BARS:
        raise AssertionError("overlapping candles")
    for preview in doc["h017_blue_risk_previews"]:
        bar = by_start[preview["open_ms"]]
        if preview["time_ms"] != bar["end_ms"] or Decimal(preview["entry_price"]) != Decimal(bar["open"]):
            raise AssertionError("preview not tied to exact public candle OPEN")
        if preview["blue_available_at_ms"] > bar["start_ms"] or preview["trend_version"] > bar["start_ms"]:
            raise AssertionError("preview uses future geometry")
        entry = Decimal(preview["entry_price"])
        target = Decimal(preview["target_price"])
        side = preview["side"]
        reward = target-entry if side == "LONG" else entry-target
        risk = entry * Decimal("0.007")
        qualifies = reward >= risk
        if (preview["risk_status"] == "RISK_PASS") != qualifies:
            raise AssertionError("wrong H-017 gross reward/risk classification")
        if qualifies:
            stop = Decimal(preview["stop_price"])
            expected_stop = entry * (Decimal("0.993") if side == "LONG" else Decimal("1.007"))
            if stop != expected_stop or abs(Decimal(preview["quantity"]) * entry - Decimal("10")) > Decimal("1e-20"):
                raise AssertionError("unexpected H-017 0.7% stop or 10 USDT slot sizing")
        elif "stop_price" in preview or "quantity" in preview:
            raise AssertionError("rejected H-017 candidate contains execution fields")
    # Hash the actual returned closed OHLCV bars, not mock fixtures or rendered pixels.
    canonical = json.dumps(bars, sort_keys=True, ensure_ascii=True, separators=(",", ":"))
    summary = {
        "result": "REAL_BYBIT_PUBLIC_HISTORY_CHECKED",
        "no_trading": True,
        "origin": BYBIT_PUBLIC_KLINE,
        "symbol": SYMBOL,
        "start_utc_inclusive": START,
        "end_utc_exclusive": END,
        "warmup_hours": doc["geometry_warmup_hours"],
        "closed_m5_bars": len(bars),
        "bar_sha256": hashlib.sha256(canonical.encode()).hexdigest(),
        "hourly_main_lines": sum(x["kind"] == "MAIN_1H" for x in doc["geometry"]),
        "hourly_target_lines": sum(x["kind"] == "TARGET_1H" for x in doc["geometry"]),
        "hourly_main_contacts": sum(x["kind"] == "MAIN_1H_TOUCH" for x in doc["observations"]),
        "hourly_main_reactions": sum(x["kind"] == "MAIN_1H_REACTION" for x in doc["observations"]),
        "blue_open_candidates": len(doc["h017_blue_risk_previews"]),
        "passes_1R": sum(x["risk_status"] == "RISK_PASS" for x in doc["h017_blue_risk_previews"]),
        "below_1R": sum(x["risk_status"] == "RISK_BELOW_1R" for x in doc["h017_blue_risk_previews"]),
        "simulated_fills": 0,
        "net_pnl": None,
        "geometry_owner_verified": False,
    }
    return summary


if __name__ == "__main__":
    print(json.dumps(check(), ensure_ascii=False, sort_keys=True))
