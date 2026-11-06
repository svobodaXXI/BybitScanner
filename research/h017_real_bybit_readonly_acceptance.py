"""One-off H-017 real Bybit read-only market-history acceptance.

Runs in isolated GitHub Actions. Aggregates official public Bybit archived
trade prints into closed 5m OHLCV; no credentials, PAPER, fake data or disk writes.
The 7 visible UTC days have 72h of earlier closed-candle geometry warmup.
"""
from __future__ import annotations

import argparse
import csv
import gzip
import hashlib
import io
import json
from bisect import bisect_right
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from urllib.request import Request, urlopen

from research.local_replay_viewer.server import load_public_history
from research.h017_blue_execution_scenario import simulate_blue_open_scenario

SYMBOL = "GRASSUSDT"
START = "2026-07-29"
END = "2026-08-05"
EXPECTED_VISIBLE_BARS = 7 * 24 * 12
M5 = 300_000
ARCHIVE_ROOT = "https://public.bybit.com/trading/"
MAX_COMPRESSED_DAY = 24_000_000
MAX_TRADES_PER_DAY = 750_000


def archived_trade_klines(*, start: str = START, end: str = END):
    """Fetch official Bybit linear trades and rebuild only time-complete M5 bars.

    Historical trade prices are NOT the v5 kline endpoint. The test report
    preserves this distinction, never passing the archive as authenticated
    Bybit candle API data. Missing minutes or invalid archives fail closed.
    """
    day = datetime.strptime(start, "%Y-%m-%d").replace(
        tzinfo=timezone.utc,
    ) - timedelta(hours=72)
    stop = datetime.strptime(end, "%Y-%m-%d").replace(tzinfo=timezone.utc)
    archive_hashes = {}
    by_bucket = {}
    global_sequence = 0
    while day < stop:
        stamp = day.strftime("%Y-%m-%d")
        url = ARCHIVE_ROOT + SYMBOL + "/" + SYMBOL + stamp + ".csv.gz"
        request = Request(url, headers={"User-Agent": "H017-ReadOnly-ArchiveResearch/1.0"},
                          method="GET")
        with urlopen(request, timeout=25) as response:
            payload = response.read(MAX_COMPRESSED_DAY + 1)
        if not payload or len(payload) > MAX_COMPRESSED_DAY:
            raise ValueError("missing or oversized official Bybit trade archive " + stamp)
        archive_hashes[stamp] = hashlib.sha256(payload).hexdigest()
        first_ms = int(day.timestamp() * 1000)
        last_ms = first_ms + 86_400_000
        rows = 0
        with gzip.GzipFile(fileobj=io.BytesIO(payload)) as compressed:
            with io.TextIOWrapper(compressed, encoding="utf-8", newline="") as stream:
                reader = csv.DictReader(stream)
                if not {"timestamp", "symbol", "size", "price"}.issubset(reader.fieldnames or []):
                    raise ValueError("unknown Bybit trade archive schema " + stamp)
                for item in reader:
                    rows += 1
                    if rows > MAX_TRADES_PER_DAY or item["symbol"] != SYMBOL:
                        raise ValueError("oversized or foreign trade archive " + stamp)
                    timestamp = Decimal(item["timestamp"])
                    price, size = Decimal(item["price"]), Decimal(item["size"])
                    time_ms = int(timestamp * 1000)
                    if (not timestamp.is_finite() or not price.is_finite() or
                        not size.is_finite() or price <= 0 or size <= 0 or
                        not first_ms <= time_ms < last_ms):
                        raise ValueError("invalid/out-of-day Bybit trade " + stamp)
                    bucket = time_ms // M5 * M5
                    key = (time_ms, global_sequence)
                    global_sequence += 1
                    agg = by_bucket.get(bucket)
                    if agg is None:
                        by_bucket[bucket] = {
                            "first": key, "last": key, "open": price,
                            "close": price, "high": price, "low": price, "volume": size,
                        }
                    else:
                        if key < agg["first"]:
                            agg["first"], agg["open"] = key, price
                        if key > agg["last"]:
                            agg["last"], agg["close"] = key, price
                        agg["high"] = max(agg["high"], price)
                        agg["low"] = min(agg["low"], price)
                        agg["volume"] += size
        if rows == 0:
            raise ValueError("official Bybit archive has no trades " + stamp)
        day += timedelta(days=1)

    first_ms = int((datetime.strptime(start, "%Y-%m-%d").replace(
        tzinfo=timezone.utc) - timedelta(hours=72)).timestamp() * 1000)
    end_ms = int(stop.timestamp() * 1000)
    times = list(range(first_ms, end_ms, M5))
    if len(by_bucket) != len(times) or set(by_bucket) != set(times):
        raise ValueError("official trade archive has missing 5m bars; no synthetic filling")
    normalized = [
        {"time": str(t), "open": str(by_bucket[t]["open"]),
         "high": str(by_bucket[t]["high"]), "low": str(by_bucket[t]["low"]),
         "close": str(by_bucket[t]["close"]), "volume": str(by_bucket[t]["volume"])}
        for t in times
    ]

    def fetch_public_derived(symbol: str, interval: str, limit: int, *, end_ms: int):
        if symbol != SYMBOL or interval != "5" or not 1 <= limit <= 1000:
            raise ValueError("unexpected derived archive fetch request")
        idx = bisect_right(times, end_ms)
        return list(reversed(normalized[max(0, idx - limit):idx]))

    return fetch_public_derived, archive_hashes


def verify_archived_hourly_wick_geometry(document):
    """Independently verify H1 line anchors and every known wick between them.

    Uses only CLOSED public-trade-derived H1 OHLC, including the hidden 72h
    context. Checks the geometry as *originally published*; a later break
    beyond the second anchor is not retroactively erased or retouched.
    """
    from research.historical_candle_feed import ClosedHigherTimeframeFeed
    from research.historical_market_replay import Candle

    original = document["context_1h"]
    first_visible = document["events"][0]["candle"]["start_ms"]
    if (not original or original[0]["start_ms"] != first_visible - 72 * 3_600_000
            or original[-1]["end_ms"] != first_visible
            or len(original) != 72):
        raise AssertionError("real Bybit run lacks exactly 72 closed H1 warmup bars")
    by_hour = {}
    for hour in original:
        if (hour["start_ms"] in by_hour or
                hour["end_ms"] != hour["start_ms"] + 3_600_000):
            raise AssertionError("invalid original H1 warmup history")
        by_hour[hour["start_ms"]] = hour
    feed = ClosedHigherTimeframeFeed()
    for event in document["events"]:
        c = event["candle"]
        _, _, new_hour, _ = feed.observe_closed_five_minute(
            Candle(c["start_ms"], M5, c["open"], c["high"],
                   c["low"], c["close"], c["volume"])
        )
        if new_hour is not None:
            if new_hour.start_ms in by_hour:
                raise AssertionError("visible H1 overlaps hidden H1 context")
            by_hour[new_hour.start_ms] = {
                "start_ms": new_hour.start_ms, "end_ms": new_hour.end_ms,
                "high": str(new_hour.high), "low": str(new_hour.low),
            }
    counts = {"MAIN_1H": 0, "TARGET_1H": 0}
    for line in document["geometry"]:
        kind = line["kind"]
        if kind not in counts:
            continue
        a = by_hour.get(line["from_ms"])
        b = by_hour.get(line["to_ms"])
        if a is None or b is None or line["from_ms"] >= line["to_ms"]:
            raise AssertionError("hourly anchor not a closed archived H1 candle")
        lower = (kind == "MAIN_1H") == (line["side"] == "BULL")
        wick = "low" if lower else "high"
        first_price, second_price = Decimal(line["from_price"]), Decimal(line["to_price"])
        if first_price != Decimal(a[wick]) or second_price != Decimal(b[wick]):
            raise AssertionError("H1 line anchor is not an actual archived wick")
        start, stop = line["from_ms"], line["to_ms"]
        for at in range(start + 3_600_000, stop + 1, 3_600_000):
            bar = by_hour.get(at)
            if bar is None:
                raise AssertionError("missing closed H1 within trendline anchor span")
            level = first_price + (second_price - first_price) * (
                Decimal(at - start) / Decimal(stop - start))
            price = Decimal(bar[wick])
            if lower and price < level or not lower and price > level:
                raise AssertionError("H1 wick protrudes beyond frozen yellow geometry")
        if line["available_at_ms"] < b["end_ms"]:
            raise AssertionError("hourly line published before its second wick closed")
        counts[kind] += 1
    return counts


def verify_archived_prior_timeline(doc):
    """Closed-H1 audit of emitted purple levels, never trade evidence."""
    from research.historical_candle_feed import ClosedHigherTimeframeFeed
    from research.historical_market_replay import Candle

    hour_ms = 3_600_000
    hours = {bar["start_ms"]: bar for bar in doc.get("context_1h", [])}
    stream = ClosedHigherTimeframeFeed()
    closes = set()
    for event in doc["events"]:
        c = event["candle"]
        closes.add(event["time_ms"])
        _, _, h1, _ = stream.observe_closed_five_minute(
            Candle(c["start_ms"], M5, c["open"], c["high"], c["low"], c["close"], c["volume"])
        )
        if h1 is not None:
            if h1.start_ms in hours:
                raise AssertionError("overlapping H1 prior evidence")
            hours[h1.start_ms] = {
                "start_ms": h1.start_ms, "end_ms": h1.end_ms,
                "high": str(h1.high), "low": str(h1.low),
            }
    lines = [x for x in doc["geometry"] if x["kind"] == "MAIN_1H"]
    updates = doc.get("hourly_prior_updates", [])
    if lines and not updates:
        raise AssertionError("confirmed yellow lines lack purple-prior events")
    last = None
    transfers = 0
    for item in updates:
        at, known, side, price = (
            item["at_ms"], item["available_at_ms"], item["side"], Decimal(item["price"])
        )
        candidates = [x for x in lines if
                      x["side"] == side and x["to_ms"] == at and
                      Decimal(x["to_price"]) == price and x["available_at_ms"] <= known]
        wick = "low" if side == "BULL" else "high"
        candle = hours.get(at)
        if (item["kind"] != "H1_PRIOR_CONFIRMED" or not candidates or
                known not in closes or at >= known or
                (last is not None and known <= last[0]) or
                candle is None or candle["end_ms"] > known or
                Decimal(candle[wick]) != price):
            raise AssertionError("prior has no closed H1 wick or valid publication time")
        line = candidates[-1]
        movement = (side, line["from_ms"], line["from_price"])
        if last is not None and last[1] == movement:
            old_touch, old_price = last[2], last[3]
            before = [x for x in hours.values()
                      if line["from_ms"] <= x["start_ms"] < at]
            extreme = (max(Decimal(x["high"]) for x in before) if side == "BULL"
                       else min(Decimal(x["low"]) for x in before)) if before else None
            newer = extreme is not None and any(
                x["start_ms"] > at and x["end_ms"] <= known and
                (Decimal(x["high"]) > extreme if side == "BULL"
                 else Decimal(x["low"]) < extreme) for x in hours.values()
            )
            if (at <= old_touch or known % hour_ms != 0 or not newer or
                    (side == "BULL" and price <= old_price) or
                    (side == "BEAR" and price >= old_price)):
                raise AssertionError("prior moved without a later CLOSED H1 extreme")
            transfers += 1
        last = (known, movement, at, price)
    return {
        "events": len(updates), "transfers_verified": transfers,
        "initial_publications": len(updates) - transfers,
        "timeline": [
            {"side": x["side"], "at_ms": x["at_ms"],
             "available_at_ms": x["available_at_ms"], "price": x["price"]}
            for x in updates[:12]
        ],
        "timeline_truncated": len(updates) > 12,
    }


def verify_archived_prior_break_timeline(doc):
    """Audit kernel-confirmed close/next OPEN breaks on archived CLOSED H1.

    Never infer a breakout from a wick or declare an opposite yellow line
    unless the kernel actually published its H1 pivots in the JSON geometry.
    """
    from research.historical_candle_feed import ClosedHigherTimeframeFeed
    from research.historical_market_replay import Candle

    hours = {bar["start_ms"]: bar for bar in doc["context_1h"]}
    stream = ClosedHigherTimeframeFeed()
    bars_by_start = {}
    for event in doc["events"]:
        c = event["candle"]
        bars_by_start[c["start_ms"]] = c
        _, _, h1, _ = stream.observe_closed_five_minute(
            Candle(c["start_ms"], M5, c["open"], c["high"],
                   c["low"], c["close"], c["volume"])
        )
        if h1 is not None:
            hours[h1.start_ms] = {
                "start_ms": h1.start_ms, "end_ms": h1.end_ms,
                "close": str(h1.close),
            }
    priors = doc.get("hourly_prior_updates", [])
    lines = [g for g in doc["geometry"] if g["kind"] == "MAIN_1H"]
    breaks = doc.get("hourly_prior_breaks", [])
    last_confirmed = -1
    outcomes = []
    for index, event in enumerate(breaks):
        at = event["confirmed_at_ms"]
        next_break_at = (breaks[index + 1]["confirmed_at_ms"]
                         if index + 1 < len(breaks) else float("inf"))
        close_at = event["hourly_close_ms"]
        first = bars_by_start.get(close_at)
        hour = hours.get(close_at - 3_600_000)
        frozen = next((p for p in reversed(priors)
                       if p["available_at_ms"] <= close_at - 3_600_000), None)
        previous_side = event["previous_side"]
        price = Decimal(event["prior_price"])
        close = Decimal(str(hour["close"])) if hour else None
        opening = Decimal(str(first["open"])) if first else None
        proven = (previous_side == "BULL" and
                  close is not None and opening is not None and
                  close < price and opening < price) or (
                  previous_side == "BEAR" and
                  close is not None and opening is not None and
                  close > price and opening > price)
        if (event["kind"] != "PRIOR_CLOSE_NEXT_OPEN" or
                at <= last_confirmed or close_at % 3_600_000 or
                event["next_hour_open_ms"] != close_at or
                at != close_at + M5 or first is None or
                first["end_ms"] != at or hour is None or
                hour["end_ms"] != close_at or frozen is None or
                Decimal(frozen["price"]) != price or
                frozen["side"] != previous_side or
                frozen["at_ms"] != event["prior_at_ms"] or
                frozen["trend_version"] != event["trend_version"] or
                event["new_side"] != ("BEAR" if previous_side == "BULL" else "BULL") or
                not proven):
            raise AssertionError("kernel breakout lacks CLOSED H1 and next OPEN evidence")
        # The opposite H1 line must be a separately published confirmed
        # geometry version, never synthesized at the moment of prior break.
        opposite = [g for g in lines if
                    g["side"] == event["new_side"] and
                    at <= g["available_at_ms"] < next_break_at]
        outcomes.append({
            "confirmed_at_ms": at, "previous_side": previous_side,
            "new_side": event["new_side"], "prior_price": event["prior_price"],
            "hourly_close_ms": close_at,
            "opposite_h1_first_published_ms": (
                opposite[0]["available_at_ms"] if opposite else None),
        })
        last_confirmed = at
    return {
        "confirmed_close_next_open_breaks": len(breaks),
        "breaks_with_later_published_opposite_h1": sum(
            item["opposite_h1_first_published_ms"] is not None for item in outcomes),
        "break_events": outcomes[:12],
        "truncated": len(outcomes) > 12,
    }


def retrospective_first_touch_study(bars, previews, dmi_points):
    """Independent, non-executable first-touch count on a bounded market sample.

    Each RISK_PASS preview is an overlapping hypothetical scenario, NOT a fill.
    Frozen target and stop prices are observed from its actual OPEN onward;
    when both touch within one M5, the order remains unknowable.
    A crossover may corroborate the OPEN only if it was visible on the
    immediately preceding fully closed candle (not that OPEN's own close).
    """
    by_open = {bar["start_ms"]: i for i, bar in enumerate(bars)}
    at_close = {point["time_ms"]: point for point in dmi_points}
    outcomes = ("TARGET_FIRST", "STOP_FIRST", "BOTH_SAME_M5", "UNRESOLVED")
    groups = {label: {status: 0 for status in outcomes} for label in (
        "DMI_PREVIOUS_CLOSE_ONE_OR_MORE", "DMI_PREVIOUS_CLOSE_ZERO",
        "DMI_UNAVAILABLE_OR_NOT_WARM",
    )}
    for p in previews:
        if p["risk_status"] != "RISK_PASS":
            continue
        start = by_open.get(p["open_ms"])
        if start is None or p["open_ms"] != p["time_ms"] - M5:
            raise AssertionError("candidate not aligned with closed M5")
        last = at_close.get(p["open_ms"])
        label = (
            "DMI_UNAVAILABLE_OR_NOT_WARM" if last is None or last["adx"] is None
            or "crossings" not in last else
            "DMI_PREVIOUS_CLOSE_ONE_OR_MORE" if last["crossings"] else
            "DMI_PREVIOUS_CLOSE_ZERO"
        )
        stop = Decimal(p["stop_price"])
        target = Decimal(p["target_price"])
        outcome = "UNRESOLVED"
        for bar in bars[start:]:
            high, low = Decimal(str(bar["high"])), Decimal(str(bar["low"]))
            if p["side"] == "LONG":
                target_hit, stop_hit = high >= target, low <= stop
            elif p["side"] == "SHORT":
                target_hit, stop_hit = low <= target, high >= stop
            else:
                raise AssertionError("unrecognized H-017 direction")
            if target_hit or stop_hit:
                outcome = ("BOTH_SAME_M5" if target_hit and stop_hit else
                           "TARGET_FIRST" if target_hit else "STOP_FIRST")
                break
        groups[label][outcome] += 1
    if sum(sum(counts.values()) for counts in groups.values()) != sum(
        p["risk_status"] == "RISK_PASS" for p in previews
    ):
        raise AssertionError("H-017 observational cohort totals do not match")
    return groups


def check(*, start: str = START, end: str = END,
          require_complete_reversal: bool = False) -> dict[str, object]:
    start_date = datetime.strptime(start, "%Y-%m-%d").replace(tzinfo=timezone.utc)
    end_date = datetime.strptime(end, "%Y-%m-%d").replace(tzinfo=timezone.utc)
    if end_date - start_date != timedelta(days=7) or end_date > datetime.now(timezone.utc):
        raise ValueError("read-only acceptance requires seven complete past UTC days")
    fetch, archive_hashes = archived_trade_klines(start=start, end=end)
    doc = load_public_history(symbol=SYMBOL, start=start, end=end,
                              fetch_candles=fetch)
    # Explicitly correct the in-memory archival provenance: this is NOT a
    # direct response from the public /v5/market/kline API and is not a
    # browser-import acceptance of its strictly versioned JSON format.
    doc["market_data_source"] = "BYBIT_OFFICIAL_PUBLIC_TRADES_DERIVED_5M"
    events = doc["events"]
    if (doc["source"], doc["mode"], doc["market_data_source"], doc["symbol"]) != (
        "SIMULATION", "MARKET_ONLY", "BYBIT_OFFICIAL_PUBLIC_TRADES_DERIVED_5M", SYMBOL
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
    verified_h1 = verify_archived_hourly_wick_geometry(doc)
    verified_priors = verify_archived_prior_timeline(doc)
    verified_breaks = verify_archived_prior_break_timeline(doc)
    if require_complete_reversal and not verified_breaks["breaks_with_later_published_opposite_h1"]:
        raise AssertionError(
            "no complete REAL H1 sequence: frozen prior -> close/next OPEN -> "
            "opposite confirmed 1--3/2--4 line before the next break"
        )
    # Hash the actual returned closed OHLCV bars, not mock fixtures or rendered pixels.
    canonical = json.dumps(bars, sort_keys=True, ensure_ascii=True, separators=(",", ":"))
    summary = {
        "result": "REAL_BYBIT_OFFICIAL_TRADE_ARCHIVE_CHECKED",
        "no_trading": True,
        "origin": ARCHIVE_ROOT + SYMBOL + "/",
        "archive_compressed_sha256_by_day": archive_hashes,
        "market_data_source": doc["market_data_source"],
        "symbol": SYMBOL,
        "start_utc_inclusive": start,
        "end_utc_exclusive": end,
        "warmup_hours": doc["geometry_warmup_hours"],
        "closed_m5_bars": len(bars),
        "bar_sha256": hashlib.sha256(canonical.encode()).hexdigest(),
        "hourly_main_lines": sum(x["kind"] == "MAIN_1H" for x in doc["geometry"]),
        "hourly_target_lines": sum(x["kind"] == "TARGET_1H" for x in doc["geometry"]),
        "closed_h1_wick_verified_lines": verified_h1,
        "closed_h1_prior_timeline": verified_priors,
        "closed_h1_prior_breaks": verified_breaks,
        "hourly_main_contacts": sum(x["kind"] == "MAIN_1H_TOUCH" for x in doc["observations"]),
        "hourly_main_reactions": sum(x["kind"] == "MAIN_1H_REACTION" for x in doc["observations"]),
        "blue_open_candidates": len(doc["h017_blue_risk_previews"]),
        "passes_1R": sum(x["risk_status"] == "RISK_PASS" for x in doc["h017_blue_risk_previews"]),
        "below_1R": sum(x["risk_status"] == "RISK_BELOW_1R" for x in doc["h017_blue_risk_previews"]),
        "first_touch_research_only": retrospective_first_touch_study(
            bars, doc["h017_blue_risk_previews"], doc["dmi_5m"]["points"]
        ),
        "simulated_fills": 0,
        "net_pnl": None,
        "geometry_owner_verified": False,
        "counterfactual_blue_open_only": {
            key: value for key, value in simulate_blue_open_scenario(doc).items()
            if key not in ("closed_simulated_trades", "open_simulated_positions")
        },
    }
    return summary


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Read-only public Bybit H1 historical acceptance")
    parser.add_argument("--start", default=START, help="UTC date inclusive")
    parser.add_argument("--end", default=END, help="UTC date exclusive, seven days later")
    parser.add_argument("--require-complete-reversal", action="store_true",
                        help="fail if no validated H1 close/OPEN/opposite-line sequence")
    args = parser.parse_args()
    print(json.dumps(check(
        start=args.start, end=args.end,
        require_complete_reversal=args.require_complete_reversal,
    ), ensure_ascii=False, sort_keys=True))
