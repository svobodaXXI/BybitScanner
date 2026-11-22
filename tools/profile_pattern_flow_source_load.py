"""Offline synthetic source-load profile on the installed MarketDataHub code path.

No network, external WS, REST, VPS, DB, order, Robot thread or trading action.
Uses actual MarketDataHub._dispatch, PublicOrderBookBuffer, PublicTradeBuffer,
PublicTradeKlineBuffer and PublicTradeObservation, but NOT a production ingress
rate, 1000-level changing live orderbooks, SQLite owner callback or VPS CPU.

Report CPU and wall as *local CI runner samples*, never a safe subscription
budget. A second symbol implies BOTH extra publicTrade and orderbook topics.
"""
from __future__ import annotations

import json
import statistics
import time
from decimal import Decimal
from types import SimpleNamespace

from terminal.market_data.hub import MarketDataHub, SymbolContext
from terminal.runtime.paper_http_server import (
    PublicOrderBookBuffer, PublicTradeBuffer, PublicTradeKlineBuffer,
)


SYMBOLS = ("ONGUSDT", "BTCUSDT")
START_MS = 9_000_000
FRAMES_PER_SYMBOL = 160
REPETITIONS = 3


class _Registry:
    def get(self, symbol):
        value = str(symbol).strip().upper()
        if value not in SYMBOLS:
            raise LookupError(value)
        return SimpleNamespace(symbol=value, tick_size=Decimal("0.01"))


def _context(symbol, tick_size):
    book = PublicOrderBookBuffer(symbol, depth=1000)
    trade_klines = PublicTradeKlineBuffer(symbol, tick_size=tick_size)
    trades = PublicTradeBuffer(
        symbol, tick_size=tick_size, aggregation_window_ms=50,
        book_descriptor_provider=book.latest_descriptor,
        raw_trade_consumer=trade_klines.add_trades,
    )
    # Native kline REST workers are intentionally not started: this is a
    # bounded offline lower-bound observation, not a full VPS load emulation.
    return SymbolContext(symbol, book, trades, {"15s": trade_klines})


def _book(symbol, *, seq, snapshot=False):
    return {
        "topic": f"orderbook.1000.{symbol}",
        "type": "snapshot" if snapshot else "delta",
        "ts": START_MS + seq,
        "data": {
            "s": symbol, "u": seq, "seq": seq,
            "b": [["100", str(1 + (seq % 3))]],
            "a": [["101", str(1 + (seq % 2))]],
        },
    }


def _prints(symbol, *, frame, batch):
    stamp = START_MS + frame * (120_000 // FRAMES_PER_SYMBOL)
    return {
        "topic": f"publicTrade.{symbol}",
        "data": [
            {
                "i": f"{symbol}-{frame}-{offset}",
                "s": symbol,
                "T": stamp + offset,
                "seq": frame * batch + offset + 1,
                "S": "Buy" if offset % 2 == 0 else "Sell",
                "p": "100.50", "v": "0.10",
            }
            for offset in range(batch)
        ],
    }


def measure(*, symbols, batch):
    """One deterministic burst, using real in-process source logic only."""
    hub = MarketDataHub(_Registry(), _context, connection_factory=lambda *_a, **_k: None)
    observed_protection_book_calls = [0]
    try:
        contexts = {symbol: hub.subscribe(symbol) for symbol in symbols}
        contexts["ONGUSDT"].add_update_listener(
            "existing-protection",
            lambda _event_id: observed_protection_book_calls.__setitem__(
                0, observed_protection_book_calls[0] + 1
            ),
        )
        for sym in symbols:
            hub._dispatch(_book(sym, seq=1, snapshot=True))

        begin_wall = time.perf_counter_ns()
        begin_cpu = time.thread_time_ns()
        for i in range(FRAMES_PER_SYMBOL):
            for sym in symbols:
                hub._dispatch(_book(sym, seq=i + 2))
                hub._dispatch(_prints(sym, frame=i, batch=batch))
        cpu_ms = (time.thread_time_ns() - begin_cpu) / 1_000_000
        wall_ms = (time.perf_counter_ns() - begin_wall) / 1_000_000

        snapshots = {sym: contexts[sym].impulse_observation.snapshot()
                     for sym in symbols}
        total = FRAMES_PER_SYMBOL * batch
        assert observed_protection_book_calls[0] == FRAMES_PER_SYMBOL + 1, (
            "extra unowned symbol unexpectedly altered existing protection-book deliveries"
        )
        for sym, snap in snapshots.items():
            assert snap["observed_prints"] == min(total, 512), sym
            assert snap["invalid_frames"] == 0, sym
            assert snap["order_authority"] is False, sym
            assert snap["continuity"] == "UNPROVEN", sym
        oldest = snapshots[symbols[-1]]["prints"][0].timestamp_ms
        return {
            "cpu_ms": round(cpu_ms, 3),
            "wall_ms": round(wall_ms, 3),
            "source_prints_per_symbol": total,
            "retained_prints_per_symbol": snapshots[symbols[-1]]["observed_prints"],
            "previous_closed_minute_retained": oldest < START_MS + 60_000,
            "existing_book_owner_callback_count": observed_protection_book_calls[0],
        }
    finally:
        hub.close()


def profile():
    """Repeat paired 1/2-source bursts and print runner-local paired medians."""
    outputs = []
    for batch in (2, 8):
        baseline, extra = [], []
        # Alternate order to reduce systematic host thermal/cache bias.
        for index in range(REPETITIONS):
            if index % 2:
                b = measure(symbols=SYMBOLS, batch=batch)
                a = measure(symbols=SYMBOLS[:1], batch=batch)
            else:
                a = measure(symbols=SYMBOLS[:1], batch=batch)
                b = measure(symbols=SYMBOLS, batch=batch)
            baseline.append(a)
            extra.append(b)
        a_cpu = statistics.median(row["cpu_ms"] for row in baseline)
        b_cpu = statistics.median(row["cpu_ms"] for row in extra)
        a_wall = statistics.median(row["wall_ms"] for row in baseline)
        b_wall = statistics.median(row["wall_ms"] for row in extra)
        assert all(row["existing_book_owner_callback_count"]
                   == FRAMES_PER_SYMBOL + 1 for row in baseline + extra)
        assert all(row["previous_closed_minute_retained"] == (batch == 2)
                   for row in baseline + extra)
        outputs.append({
            "batch_trades_per_frame": batch,
            "synthetic_trades_per_symbol_per_two_minutes": FRAMES_PER_SYMBOL * batch,
            "baseline_one_symbol_cpu_ms_median": a_cpu,
            "plus_one_symbol_cpu_ms_median": b_cpu,
            "additional_source_cpu_ms_median_difference": round(b_cpu - a_cpu, 3),
            "baseline_one_symbol_wall_ms_median": a_wall,
            "plus_one_symbol_wall_ms_median": b_wall,
            "protected_book_callback_count_unchanged": FRAMES_PER_SYMBOL + 1,
            "prior_minute_retained": batch == 2,
            "raw_print_buffer_limit": 512,
        })
    return {
        "schema": "offline_pattern_flow_source_cost_v1",
        "source": "INSTALLED_SHA_EQUIVALENT_HUB_AND_TRADE_OBSERVATION",
        "synthetic": True,
        "market_data_socket_connections": 0,
        "subscriptions_created_on_vps": 0,
        "trading_authorized": False,
        "safe_subscription_count_proven": False,
        "cannot_establish": [
            "production_market_event_arrival_rate",
            "1000_level_orderbook_burst_cost",
            "owner_sqlite_protection_queue_service_rate",
            "live_bybit_transport_completeness_or_slippage",
        ],
        "pairs": outputs,
    }


if __name__ == "__main__":
    print("PATTERN_FLOW_SOURCE_OFFLINE_PROFILE=" + json.dumps(
        profile(), sort_keys=True, separators=(",", ":"),
    ))
