"""Verified local public M5 gap caching; no real Bybit, PAPER or VPS access."""
from datetime import datetime, timezone
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from research.historical_candle_feed import FIVE_MINUTES_MS
from research.local_replay_viewer.public_m5_cache import complete_history_fetch

STEP = FIVE_MINUTES_MS
START = int(datetime(2026, 1, 1, tzinfo=timezone.utc).timestamp() * 1000)


def row(index):
    return {
        "time": START + index * STEP, "open": "100",
        "high": "102", "low": "99", "close": "101", "volume": "1",
    }


class VerifiedCacheTests(unittest.TestCase):
    def test_complete_cache_reuses_without_network(self):
        calls = []
        def upstream(symbol, interval, limit, *, end_ms):
            calls.append(end_ms)
            return [row(i) for i in range(5) if row(i)["time"] <= end_ms][::-1][:limit]
        with TemporaryDirectory() as tmp:
            kwargs = dict(symbol="BTCUSDT", start_ms=START, end_ms=START+5*STEP,
                          directory=Path(tmp))
            first = complete_history_fetch(**kwargs, upstream_fetch=upstream)
            self.assertEqual([r["time"] for r in first("BTCUSDT", "5", 50,
                             end_ms=START+5*STEP-1)], [START+i*STEP for i in range(4, -1, -1)])
            self.assertEqual(len(calls), 1)
            second = complete_history_fetch(**kwargs,
                upstream_fetch=lambda *a, **k: self.fail("cached interval re-fetched"))
            self.assertEqual(len(second("BTCUSDT", "5", 5, end_ms=START+5*STEP-1)), 5)

    def test_partial_coverage_downloads_only_missing_span(self):
        fetched = []
        def upstream(symbol, interval, limit, *, end_ms):
            fetched.append(end_ms)
            return [row(i) for i in range(6) if row(i)["time"] <= end_ms][::-1][:limit]
        with TemporaryDirectory() as tmp:
            folder = Path(tmp)
            complete_history_fetch(symbol="BTCUSDT", start_ms=START, end_ms=START+2*STEP,
                                   directory=folder, upstream_fetch=upstream)
            fetched.clear()
            complete_history_fetch(symbol="BTCUSDT", start_ms=START, end_ms=START+6*STEP,
                                   directory=folder, upstream_fetch=upstream)
            self.assertEqual(fetched, [START+6*STEP-1])
            complete_history_fetch(symbol="BTCUSDT", start_ms=START, end_ms=START+6*STEP,
                 directory=folder, upstream_fetch=lambda *a, **k: self.fail("repeat fetch"))

    def test_unavailable_missing_candles_never_publish_completion(self):
        with TemporaryDirectory() as tmp:
            folder = Path(tmp)
            def incomplete(*args, **kwargs):
                return [row(0)]
            with self.assertRaisesRegex(ValueError, "missing|ended|pagination"):
                complete_history_fetch(symbol="BTCUSDT", start_ms=START,
                    end_ms=START+3*STEP, directory=folder, upstream_fetch=incomplete)
            self.assertEqual(list(folder.glob("*.json")), [])

    def test_wrong_cache_identity_fails_closed(self):
        with TemporaryDirectory() as tmp:
            folder = Path(tmp)
            day = START // 86_400_000
            (folder / f"BTCUSDT-{day}.json").write_text(
                json.dumps({"schema": "wrong", "symbol": "BTCUSDT", "day": day, "candles": []}))
            with self.assertRaisesRegex(ValueError, "identity"):
                complete_history_fetch(symbol="BTCUSDT", start_ms=START,
                    end_ms=START+STEP, directory=folder,
                    upstream_fetch=lambda *a, **k: self.fail("unsafe cache must not fetch"))

    def test_verified_public_json_is_reused_as_candles_only(self):
        events = []
        for i in range(3):
            candle = row(i)
            events.append({"source": "SIMULATION", "simulation_run_id": "source",
                "sequence": i+1, "kind": "CANDLE_CLOSED", "time_ms": candle["time"]+STEP,
                "candle": {"start_ms": candle["time"], "end_ms": candle["time"]+STEP,
                           **{k: candle[k] for k in ("open", "high", "low", "close", "volume")}}})
        with TemporaryDirectory() as tmp:
            folder = Path(tmp)
            report = folder / "real-h1-august.json"
            report.write_text(json.dumps({"source":"SIMULATION", "simulation_run_id":"source",
                "mode":"MARKET_ONLY", "market_data_source":"BYBIT_OFFICIAL_PUBLIC_TRADES_DERIVED_5M",
                "symbol":"BTCUSDT", "timeframe":"5m", "events":events}))
            fetch = complete_history_fetch(symbol="BTCUSDT", start_ms=START,
                end_ms=START+3*STEP, directory=folder / "cache", bundled_report=report,
                upstream_fetch=lambda *a, **k: self.fail("verified report must be reused"))
            self.assertEqual(len(fetch("BTCUSDT", "5", 5, end_ms=START+3*STEP-1)), 3)
            with self.assertRaises(AssertionError):
                complete_history_fetch(symbol="XRPUSDT", start_ms=START,
                    end_ms=START+3*STEP, directory=folder / "other-cache",
                    bundled_report=report,
                    upstream_fetch=lambda *a, **k: self.fail("ticker mismatch must fetch"))


if __name__ == "__main__":
    unittest.main()
