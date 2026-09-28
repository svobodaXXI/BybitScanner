from pathlib import Path
import unittest

from tests.runtime_replay import (
    RuntimeReplayFixture,
    run_manager_stall_replay,
    run_runtime_replay,
)


FIXTURE = (
    Path(__file__).resolve().parent
    / "fixtures"
    / "runtime_replays"
    / "smoke_ordered_entry_pending_v1.json"
)
OVERFLOW_FIXTURE = FIXTURE.with_name("entry_pending_overflow_20260927_v1.json")
INCIDENT_SYMBOLS = ("2ZUSDT", "ARBUSDT", "ARIAUSDT", "ARKUSDT", "CFGUSDT")


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


class RuntimeReplayEntryPendingOverflowTests(unittest.TestCase):
    """RVL-R2 RED: pre-LIMIT candidates under a bounded reconcile stall, via the manager.

    Lifecycle state: five APPROVED / RETEST_DETECTED candidates, NO limit_order_id, no
    resting LIMIT -- nothing a book event could fill. The production path under test is
    RobotProtectionCoverageManager (role discovery -> hub subscription -> _on_update)
    -> SerializedPaperRuntime.enqueue -> process_robot_market_event, with the
    production robot_reconcile() owner call stalled at its five per-candidate lookups.

    The fixture is RECONSTRUCTED from the 2026-09-27 incident envelope (not a raw
    capture). RECONSTRUCTED ASSUMPTION: 13 stream events per lookup is the smallest whole
    stall for which one reconcile spans capacity + 1 events (5 x 13 = 65); at the
    orderbook.1000 cadence (~25 events/s for five symbols) that is ~2.6 s, inside the
    recorded pre-#293 reconcile (9065 ms) and above the post-#293 ~1.4 s. Saved evidence
    does not prove the post-#293 64/64 came from reconcile alone.
    """

    CAPACITY = 64
    STALL_EVENTS_PER_LOOKUP = 13

    def test_pre_limit_traffic_during_bounded_reconcile_stall_never_enters_protection_ingress(self):
        fixture = RuntimeReplayFixture.load(OVERFLOW_FIXTURE)
        ids = tuple(event.event_id for event in fixture.events)
        self.assertIn("RECONSTRUCTED", fixture.name.upper())
        self.assertEqual(sorted({event.symbol for event in fixture.events}), list(INCIDENT_SYMBOLS))

        result = run_manager_stall_replay(
            fixture,
            stall_events_per_lookup=self.STALL_EVENTS_PER_LOOKUP,
            protection_ingress_capacity=self.CAPACITY,
        )

        # Replay invariants, valid now and after a lifecycle fix: the incident's
        # lifecycle state, the bounded stall itself, and event accounting.
        self.assertTrue(result.seeded_pre_limit)
        step = self.STALL_EVENTS_PER_LOOKUP
        span = len(INCIDENT_SYMBOLS) * step
        self.assertEqual(
            result.stall_event_ids, tuple(ids[start:start + step] for start in range(0, span, step)),
        )
        self.assertEqual(result.lookup_threads, ("paper-runtime-owner",) * len(INCIDENT_SYMBOLS))
        self.assertGreater(len(ids), span)
        self.assertEqual(set(result.unsubscribed_event_ids) | set(result.delivered_event_ids), set(ids))
        self.assertFalse(set(result.unsubscribed_event_ids) & set(result.delivered_event_ids))
        self.assertEqual(result.processed_event_ids, result.admitted_event_ids)
        self.assertEqual(result.event_errors, ())
        self.assertEqual(result.final_health["ingress"]["current_pending"], 0)

        health = result.health_after_producer
        evidence = (
            f"roles={dict(result.covered_roles)} delivered={len(result.delivered_event_ids)} "
            f"unsubscribed={len(result.unsubscribed_event_ids)} "
            f"admitted={len(result.admitted_event_ids)} overflow={result.overflow_event_ids} "
            f"suppressed_after_unhealthy={len(result.suppressed_event_ids)} "
            f"fence_overflows={result.fence_overflows} "
            f"pending_at_stall_release={result.pending_at_stall_release}/{self.CAPACITY} "
            f"high_watermark={health['ingress']['high_watermark']} "
            f"unhealthy={dict(health['unhealthy_symbols'])} "
            f"reconcile={result.reconcile_outcome}"
        )
        # Target contract (RED on current code): events of symbols that have no
        # fill-capable resting LIMIT are not protection-critical, so none of them may
        # enter protection ingress, overflow it, or turn any symbol unhealthy. This is
        # NOT "all 80 events processed": they should not belong to protection ingress.
        self.assertEqual(result.admitted_event_ids + result.overflow_event_ids, (), evidence)
        self.assertEqual(health["unhealthy_symbols"], {}, evidence)
        self.assertTrue(health["healthy"], evidence)


if __name__ == "__main__":
    unittest.main()
