"""Measure bounded client projection payloads against live public market data."""

from __future__ import annotations

import argparse
import json
import statistics
import time

from terminal.market_data.client_projection import ClientMarketProjection
from terminal.market_data.hub import MarketDataHub
from terminal.market_data.instrument_registry import InstrumentRegistry
from terminal.runtime.paper_http_server import create_bybit_rest_session, create_symbol_context


def _bytes(event: dict) -> int:
    return len(json.dumps(event, separators=(",", ":")).encode("utf-8"))


def measure(symbols: tuple[str, ...], duration: float) -> dict[str, dict]:
    session = create_bybit_rest_session()
    instruments = InstrumentRegistry(session)
    instruments.refresh()
    hub = MarketDataHub(instruments, create_symbol_context)
    contexts = {symbol: hub.subscribe(symbol) for symbol in symbols}
    hub.start()
    try:
        deadline = time.monotonic() + 30
        while time.monotonic() < deadline:
            if all(
                context.public_orderbook.wait_until_ready(0.05)
                and context.public_klines["5"].snapshot().get("state") == "READY"
                for context in contexts.values()
            ):
                break
        else:
            raise TimeoutError("market projection measurement did not become ready")

        projections = {
            symbol: ClientMarketProjection(context, 1)
            for symbol, context in contexts.items()
        }
        results: dict[str, dict] = {}
        incremental: dict[str, dict[str, list[int]]] = {}
        for symbol, projection in projections.items():
            book = projection.book_event()
            trades = projection.trades_event()
            candles = projection.candles_event("5")
            results[symbol] = {
                "book_bootstrap_bytes": _bytes(book),
                "book_bootstrap_levels": len(book["bids"]) + len(book["asks"]),
                "trade_bootstrap_bytes": _bytes(trades),
                "trade_bootstrap_items": len(trades["trades"]),
                "candle_bootstrap_bytes": _bytes(candles),
                "candle_bootstrap_items": len(candles["candles"]),
            }
            incremental[symbol] = {"book": [], "trades": [], "candles": []}

        started = time.monotonic()
        while time.monotonic() - started < duration:
            for symbol, projection in projections.items():
                for kind, event in (
                    ("book", projection.book_event()),
                    ("trades", projection.trades_event()),
                    ("candles", projection.candles_event("5")),
                ):
                    if event is not None:
                        incremental[symbol][kind].append(_bytes(event))
            time.sleep(0.02)

        elapsed = time.monotonic() - started
        for symbol, by_kind in incremental.items():
            total = 0
            for kind, sizes in by_kind.items():
                total += sum(sizes)
                results[symbol][f"{kind}_events"] = len(sizes)
                results[symbol][f"{kind}_messages_per_second"] = len(sizes) / elapsed
                results[symbol][f"{kind}_median_bytes"] = statistics.median(sizes) if sizes else 0
                results[symbol][f"{kind}_bytes_per_second"] = sum(sizes) / elapsed
            results[symbol]["combined_incremental_bytes_per_second"] = total / elapsed
            results[symbol]["measurement_seconds"] = elapsed
        return results
    finally:
        hub.close()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--seconds", type=float, default=15.0)
    parser.add_argument("--symbol", action="append", dest="symbols")
    args = parser.parse_args()
    symbols = tuple(item.upper() for item in (args.symbols or ["BTCUSDT", "ONGUSDT"]))
    print(json.dumps(measure(symbols, args.seconds), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
