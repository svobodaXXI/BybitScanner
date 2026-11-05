"""One-off H-017 real Bybit read-only market-history acceptance.

Runs in isolated GitHub Actions. Aggregates official public Bybit archived
trade prints into closed 5m OHLCV; no credentials, PAPER, fake data or disk writes.
The 7 visible UTC days have 72h of earlier closed-candle geometry warmup.
"""
from __future__ import annotations

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

SYMBOL = "GRASSUSDT"
START = "2026-07-29"
END = "2026-08-05"
EXPECTED_VISIBLE_BARS = 7 * 24 * 12
M5 = 300_000
ARCHIVE_ROOT = "https://public.bybit.com/trading/"
MAX_COMPRESSED_DAY = 24_000_000
MAX_TRADES_PER_DAY = 750_000


def archived_trade_klines():
    """Fetch official Bybit linear trades and rebuild only time-complete M5 bars.

    Historical trade prices are NOT the v5 kline endpoint. The test report
    preserves this distinction, never passing the archive as authenticated
    Bybit candle API data. Missing minutes or invalid archives fail closed.
    """
    day = datetime.strptime(START, "%Y-%m-%d").replace(
        tzinfo=timezone.utc,
    ) - timedelta(hours=72)
    stop = datetime.strptime(END, "%Y-%m-%d").replace(tzinfo=timezone.utc)
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

    first_ms = int((datetime.strptime(START, "%Y-%m-%d").replace(
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


def check() -> dict[str, object]:
    fetch, archive_hashes = archived_trade_klines()
    doc = load_public_history(symbol=SYMBOL, start=START, end=END,
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
    # Hash the actual returned closed OHLCV bars, not mock fixtures or rendered pixels.
    canonical = json.dumps(bars, sort_keys=True, ensure_ascii=True, separators=(",", ":"))
    summary = {
        "result": "REAL_BYBIT_OFFICIAL_TRADE_ARCHIVE_CHECKED",
        "no_trading": True,
        "origin": ARCHIVE_ROOT + SYMBOL + "/",
        "archive_compressed_sha256_by_day": archive_hashes,
        "market_data_source": doc["market_data_source"],
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
        "first_touch_research_only": retrospective_first_touch_study(
            bars, doc["h017_blue_risk_previews"], doc["dmi_5m"]["points"]
        ),
        "simulated_fills": 0,
        "net_pnl": None,
        "geometry_owner_verified": False,
    }
    return summary


if __name__ == "__main__":
    print(json.dumps(check(), ensure_ascii=False, sort_keys=True))
