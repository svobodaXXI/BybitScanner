from pathlib import Path
import unittest

from tests.runtime_replay import RuntimeReplayFixture, run_runtime_replay


FIXTURE = (
    Path(__file__).resolve().parent
    / "fixtures"
    / "runtime_replays"
    / "smoke_ordered_entry_pending_v1.json"
)


class RuntimeReplayContractTests(unittest.TestCase):
    def test_smoke_fixture_is_deterministic_and_preserves_fifo(self):
        fixture = RuntimeReplayFixture.load(FIXTURE)

        first = run_runtime_replay(fixture)
        second = run_runtime_replay(fixture)

        expected = tuple(event.event_id for event in fixture.events)
        self.assertEqual(first.processed_event_ids, expected)
        self.assertEqual(second.processed_event_ids, expected)
        self.assertEqual(first.overflow_event_ids, ())
        self.assertEqual(second.overflow_event_ids, ())
        self.assertEqual(first.event_errors, ())
        self.assertEqual(second.event_errors, ())
        self.assertEqual(first.continuity_loss, None)
        self.assertEqual(second.continuity_loss, None)

        # Timing values are intentionally not compared: scheduling is not a
        # correctness oracle. The stable contract is the metric surface plus
        # deterministic event order and final drained state.
        self.assertEqual(first.metric_keys, second.metric_keys)
        self.assertEqual(first.metrics["capacity"], 64)
        self.assertEqual(second.metrics["capacity"], 64)
        self.assertEqual(first.metrics["current_pending"], 0)
        self.assertEqual(second.metrics["current_pending"], 0)
        self.assertGreaterEqual(first.metrics["high_watermark"], 1)
        self.assertGreaterEqual(second.metrics["high_watermark"], 1)
        self.assertLessEqual(first.metrics["high_watermark"], len(fixture.events))
        self.assertLessEqual(second.metrics["high_watermark"], len(fixture.events))
        self.assertEqual(first.metrics["last_symbol"], "2ZUSDT")
        self.assertEqual(first.metrics["last_role"], "ENTRY_PENDING")
        self.assertIsNone(first.metrics["last_overflow_symbol"])


if __name__ == "__main__":
    unittest.main()
