"""Isolated Simulator 2.0 clock tests: no Scanner/Robot/PAPER runtime needed."""
import unittest
from decimal import Decimal

from research.historical_market_replay import Candle
from research.simulator_v2.timeline import (
    IsolatedTimeline, StageFact, StepBlocked, MINUTE_MS,
)

D = Decimal


def bar(index, *, high="101", low="99", close="100", volume="2"):
    return Candle(
        start_ms=index * MINUTE_MS, interval_ms=MINUTE_MS,
        open=D("100"), high=D(high), low=D(low),
        close=D(close), volume=D(volume),
    )


class IsolatedTimelineTests(unittest.TestCase):
    def test_only_completed_m5_and_h1_are_published(self):
        runner = IsolatedTimeline(simulation_run_id="a", symbol="BTCUSDT")
        frames = [runner.step(bar(i)) for i in range(60)]
        self.assertTrue(all(f.newly_closed_5m is None for f in frames[:4]))
        self.assertEqual(frames[4].newly_closed_5m.start_ms, 0)
        self.assertEqual(frames[4].newly_closed_5m.interval_ms, 5 * MINUTE_MS)
        self.assertTrue(all(f.newly_closed_1h is None for f in frames[:59]))
        self.assertEqual(frames[59].newly_closed_1h.start_ms, 0)
        self.assertEqual(frames[59].newly_closed_1h.end_ms, 60 * MINUTE_MS)
        self.assertEqual(runner.processed_minutes, 60)
        self.assertEqual(sum(e.kind == "M5_CLOSED" for e in runner.events), 12)
        self.assertEqual(sum(e.kind == "H1_CLOSED" for e in runner.events), 1)

    def test_aggregation_uses_shared_candle_and_exact_ohlcv(self):
        runner = IsolatedTimeline(simulation_run_id="ohlc", symbol="ETHUSDT")
        bars = [bar(0, high="102", low="98", volume="1"),
                bar(1, high="103", low="98", volume="2"),
                bar(2, high="110", low="90", volume="3"),
                bar(3, high="104", low="98", volume="4"),
                bar(4, high="105", low="97", close="104", volume="5")]
        frame = None
        for b in bars:
            frame = runner.step(b)
        result = frame.newly_closed_5m
        self.assertEqual(result.open, D("100"))
        self.assertEqual(result.high, D("110"))
        self.assertEqual(result.low, D("90"))
        self.assertEqual(result.close, D("104"))
        self.assertEqual(result.volume, D("15"))

    def test_incomplete_first_bucket_not_fabricated(self):
        runner = IsolatedTimeline(simulation_run_id="partial", symbol="BTCUSDT")
        frames = [runner.step(bar(i)) for i in range(2, 10)]
        self.assertTrue(all(f.newly_closed_5m is None for f in frames[:3]))
        self.assertEqual(frames[-1].newly_closed_5m.start_ms, 5 * MINUTE_MS)

    def test_pipeline_order_and_precommit_visibility(self):
        trace = []
        runner = None

        def scanner(frame, staged):
            trace.append(("SCANNER", tuple(e.kind for e in staged)))
            self.assertEqual(runner.events, ())
            return (StageFact("EXACT_SCANNER_FACT", "signal-a"),)

        def robot(frame, staged):
            trace.append(("ROBOT", tuple(e.kind for e in staged)))
            self.assertEqual(staged[-1].kind, "EXACT_SCANNER_FACT")
            return (StageFact("EXACT_ROBOT_DECISION", "candidate-a"),)

        def exchange(frame, staged):
            trace.append(("EXCHANGE", tuple(e.kind for e in staged)))
            self.assertEqual(staged[-1].kind, "EXACT_ROBOT_DECISION")
            return (StageFact("EXACT_EXCHANGE_RECEIPT", "order-a"),)

        runner = IsolatedTimeline(
            simulation_run_id="order", symbol="BTCUSDT",
            scanner=scanner, robot=robot, exchange=exchange,
        )
        runner.step(bar(0))
        self.assertEqual([t[0] for t in trace], ["SCANNER", "ROBOT", "EXCHANGE"])
        self.assertEqual([e.source for e in runner.events],
                         ["MARKET", "SCANNER", "ROBOT", "EXCHANGE"])
        self.assertEqual(
            [e.sequence for e in runner.events], [1, 2, 3, 4]
        )
        self.assertTrue(all(e.virtual_time_ms == MINUTE_MS for e in runner.events))

    def test_failed_stage_does_not_advance_clock_or_journal(self):
        attempts = []

        def scanner(frame, staged):
            attempts.append(frame.virtual_time_ms)
            return (StageFact("SCANNER_FACT"),)

        def robot(frame, staged):
            raise RuntimeError("not settled")

        runner = IsolatedTimeline(
            simulation_run_id="fail", symbol="BTCUSDT",
            scanner=scanner, robot=robot,
        )
        with self.assertRaises(StepBlocked):
            runner.step(bar(0))
        self.assertEqual(runner.events, ())
        self.assertIsNone(runner.virtual_time_ms)
        self.assertEqual(runner.paused_stage, "ROBOT")
        with self.assertRaises(StepBlocked):
            runner.step(bar(1))
        self.assertEqual(attempts, [MINUTE_MS])
        runner.resume()
        with self.assertRaises(StepBlocked):
            runner.step(bar(0))
        self.assertEqual(attempts, [MINUTE_MS, MINUTE_MS])

    def test_failed_second_minute_preserves_first_and_rewind(self):
        def scanner(frame, staged):
            if frame.virtual_time_ms == 2 * MINUTE_MS:
                raise RuntimeError("invalid")
            return (StageFact("S", "one"),)

        runner = IsolatedTimeline(
            simulation_run_id="rewind", symbol="BTCUSDT", scanner=scanner,
        )
        runner.step(bar(0))
        first = runner.events
        with self.assertRaises(StepBlocked):
            runner.step(bar(1))
        self.assertEqual(first, runner.events)
        self.assertEqual(runner.virtual_time_ms, MINUTE_MS)
        self.assertEqual(runner.events_at(MINUTE_MS), first)
        self.assertEqual(runner.events_at(0), ())
        with self.assertRaises(ValueError):
            runner.events_at(2 * MINUTE_MS)

    def test_rejects_holes_duplicates_and_bad_run_identity(self):
        runner = IsolatedTimeline(simulation_run_id="a", symbol="BTCUSDT")
        runner.step(bar(0))
        with self.assertRaises(ValueError):
            runner.step(bar(0))
        with self.assertRaises(ValueError):
            runner.step(bar(2))
        self.assertEqual(runner.processed_minutes, 1)
        with self.assertRaises(ValueError):
            IsolatedTimeline(simulation_run_id="../paper", symbol="BTCUSDT")
        with self.assertRaises(ValueError):
            IsolatedTimeline(simulation_run_id="okay", symbol="BTCUSD")

    def test_reproducible_journal_and_no_invented_trading(self):
        def play():
            timeline = IsolatedTimeline(simulation_run_id="same", symbol="BTCUSDT")
            for i in range(65):
                timeline.step(bar(i))
            return tuple(e.to_payload() for e in timeline.events)

        first = play()
        self.assertEqual(first, play())
        self.assertEqual(
            {e["source"] for e in first}, {"MARKET"}
        )
        self.assertEqual(
            {e["namespace"] for e in first}, {"SIMULATION"}
        )
        self.assertTrue(all(e["kind"] in {"M1_CLOSED", "M5_CLOSED", "H1_CLOSED"} for e in first))


if __name__ == "__main__":
    unittest.main()
