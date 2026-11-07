"""Bounded public H1 screening for a REAL H-017 four-pivot reversal window.

Research-only *candidate selection*. No paper/live keys, server, account,
orders, trade simulation, or acceptance bypass. Official Bybit kline H1
prices shortlist windows; the separate public-trade-derived M5 archive and
Chromium proof alone can accept a window. Do not call this a verified reversal.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone, timedelta
from decimal import Decimal
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from research.causal_trend_geometry import (
    ConfirmedSwingStream, recent_hourly_trend, wick_tight_hourly_trend,
)
from research.historical_candle_feed import ONE_HOUR_MS
from research.historical_market_replay import Candle

SYMBOL = "GRASSUSDT"
START = "2026-07-01"
END = "2026-11-01"
MAX_PAGES = 6
DAY_MS = 86_400_000
PUBLIC_H1 = "https://api.bybit.com/v5/market/kline"


def millis(day: str) -> int:
    return int(datetime.strptime(day, "%Y-%m-%d").replace(tzinfo=timezone.utc).timestamp() * 1000)


def date_utc(ms: int) -> str:
    return datetime.fromtimestamp(ms / 1000, tz=timezone.utc).strftime("%Y-%m-%d")


def load_verified_public_h1() -> list[Candle]:
    first_ms, stop_ms = millis(START), millis(END)
    cutoff = stop_ms - 1
    rows: dict[int, Candle] = {}
    for _ in range(MAX_PAGES):
        url = PUBLIC_H1 + "?" + urlencode({
            "category": "linear", "symbol": SYMBOL, "interval": "60",
            "limit": "1000", "end": cutoff,
        })
        with urlopen(Request(url, headers={"User-Agent": "H017-ReadOnly-H1-Selection/1.0"},
                             method="GET"), timeout=15) as response:
            raw = response.read(2_000_001)
        if not raw or len(raw) > 2_000_000:
            raise ValueError("Bybit H1 public reply missing or oversized")
        payload = json.loads(raw)
        if payload.get("retCode") != 0:
            raise ValueError("official Bybit public H1 API rejected screening")
        items = payload.get("result", {}).get("list")
        if not isinstance(items, list) or not items:
            raise ValueError("Bybit returned no public H1 candles")
        starts = []
        for entry in items:
            if not isinstance(entry, list) or len(entry) < 6:
                raise ValueError("malformed official H1 candle")
            at = int(entry[0])
            if at % ONE_HOUR_MS or at + ONE_HOUR_MS > stop_ms:
                continue
            starts.append(at)
            if at < first_ms:
                continue
            if at in rows:
                continue
            rows[at] = Candle(
                at, ONE_HOUR_MS, Decimal(entry[1]), Decimal(entry[2]),
                Decimal(entry[3]), Decimal(entry[4]), Decimal(entry[5]),
            )
        if not starts:
            raise ValueError("Bybit H1 pagination returned no closed candles")
        oldest = min(starts)
        if oldest <= first_ms:
            break
        cutoff = oldest - 1
    result = [rows[x] for x in sorted(rows)]
    if not result or result[0].start_ms != first_ms or result[-1].end_ms != stop_ms:
        raise ValueError("bounded H1 market history is incomplete")
    if any(a.end_ms != b.start_ms for a, b in zip(result, result[1:])):
        raise ValueError("public H1 calendar gap; no fabricated bars allowed")
    return result


def screen(bars: list[Candle]) -> dict[str, object]:
    stream = ConfirmedSwingStream(timeframe_ms=ONE_HOUR_MS, wing=2)
    valid = []
    seen = set()
    four_count = 0
    envelope_count = 0
    for bar in bars:
        stream.observe_closed(bar)
        pivot_quad = stream.recent_pivots
        proposal = recent_hourly_trend(pivot_quad)
        if proposal is None:
            continue
        four_count += 1
        key = tuple((p.at_ms, p.price) for p in proposal.pivot_sequence)
        if key in seen:
            continue
        seen.add(key)
        envelope_count += 1
        fitted = wick_tight_hourly_trend(proposal, stream.bars)
        if fitted is None:
            continue
        valid.append(fitted)
    pairs = []
    used_windows = set()
    for newer in valid:
        for older in reversed(valid):
            if (older.side == newer.side or
                    older.available_at_ms >= newer.available_at_ms):
                continue
            # Keep both confirmed trend phases within a single visible 7d
            # replay, plus the normal 72h warmup for earlier H1 pivots.
            begin = millis(date_utc(max(millis(START), older.available_at_ms - DAY_MS)))
            end = begin + 7 * DAY_MS
            if newer.available_at_ms >= end or end > millis(END):
                continue
            key = (begin, end)
            if key in used_windows:
                continue
            used_windows.add(key)
            prior = older.main.second.price
            close_open = []
            for cur, following in zip(bars, bars[1:]):
                if not (older.available_at_ms < cur.end_ms < newer.available_at_ms):
                    continue
                beyond = (
                    cur.close < prior and following.open < prior
                    if older.side == "BULL"
                    else cur.close > prior and following.open > prior
                )
                if beyond:
                    close_open.append(cur.end_ms)
            pairs.append({
                "start": date_utc(begin), "end": date_utc(end),
                "old_side": older.side, "new_side": newer.side,
                "old_confirmed_ms": older.available_at_ms,
                "opposite_confirmed_ms": newer.available_at_ms,
                "possible_frozen_prior_breaks": len(close_open),
                "first_possible_break_ms": close_open[0] if close_open else None,
                "status": "PUBLIC_H1_SCREEN_ONLY_NOT_ACCEPTED",
            })
            break
    pairs.sort(key=lambda v: (-v["possible_frozen_prior_breaks"], v["start"]))
    return {
        "result": "PUBLIC_H1_SCREEN_NOT_FINAL_ACCEPTANCE", "symbol": SYMBOL,
        "range": [START, END], "hourly_bars": len(bars),
        "convergent_proposals_observed": four_count,
        "distinct_convergent_proposals": envelope_count,
        "wick_valid_proposals": len(valid),
        "possible_7_day_pairs": len(pairs),
        "candidate_windows": pairs[:12],
        "requires_trade_archive_and_browser_proof": True,
    }


if __name__ == "__main__":
    print(json.dumps(screen(load_verified_public_h1()), sort_keys=True), flush=True)
