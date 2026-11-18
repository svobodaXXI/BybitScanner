"""Passive same-candidate pattern flow observer: zero new Scanner/Robot actions."""
import unittest
from decimal import Decimal
from types import SimpleNamespace

from robot_entry_flow_evidence import ExistingPatternEntryScope, match_existing_pattern_flow
from terminal.market_data.pattern_flow_observer import PatternFlowObserver
from tests.test_robot_pattern_flow_source import PatternFlowSourceTests


class _REST:
    verify = True

    def __init__(self, recent, previous, current):
        self.recent, self.previous, self.current = recent, previous, current
        self.requests = []

    def get(self, url, *, params, timeout, allow_redirects):
        self.requests.append((url, params))
        if url.endswith("/recent-trade"):
            response = self.recent
        elif params["start"] == PatternFlowSourceTests.CLOSE - 120_000:
            response = self.previous
        else:
            response = self.current
        return SimpleNamespace(
            status_code=200,
            raise_for_status=lambda: None,
            json=lambda: response,
        )

    def close(self):
        pass


class _Context:
    symbol = "BTCUSDT"
    generation = 0  # Hub context field is NOT the publicTrade observation generation
    trades_subscription_state = "SUBSCRIBED"
    trade_bootstrap_complete = True

    def __init__(self, observed):
        self.impulse_observation = SimpleNamespace(snapshot=lambda: observed)


def _candidate(direction="LONG", phase="RETEST_DETECTED"):
    return SimpleNamespace(
        candidate_id="pattern-1",
        state_revision=4,
        symbol=SimpleNamespace(value="BTCUSDT"),
        status="APPROVED",
        signal_snapshot={"pattern": "Falling Wedge"},
        robot_state={"direction": direction, "phase": phase},
    )


class ObserverTests(unittest.TestCase):
    def test_certified_tape_is_bound_to_existing_candidate_no_signal_or_order(self):
        observed, recent, previous, current = PatternFlowSourceTests.source()
        ctx = _Context(observed)
        rest = _REST(recent, previous, current)
        clock = lambda: PatternFlowSourceTests.CLOSE + 5_000
        observer = PatternFlowObserver(
            SimpleNamespace(list_contexts=lambda: (ctx,)), rest, "unused",
            clock_ms=clock, get_candidates=lambda: (_candidate(),),
        )
        self.assertEqual(observer.once(), 1)
        receipt = observer.get(_candidate())
        self.assertIsNotNone(receipt)
        self.assertEqual(receipt.candidate_id, "pattern-1")
        self.assertEqual(len(rest.requests), 3)
        self.assertEqual(observer.once(), 0)
        self.assertEqual(len(rest.requests), 3)
        scope = ExistingPatternEntryScope(
            "pattern-1", "BTCUSDT", "Falling Wedge", "LONG", 4,
            "APPROVED", "RETEST_DETECTED",
        )
        self.assertTrue(match_existing_pattern_flow(scope, receipt, now_ms=clock()))
        observer.close()

    def test_no_existing_candidate_or_no_subscription_means_zero_rest(self):
        observed, recent, previous, current = PatternFlowSourceTests.source()
        rest = _REST(recent, previous, current)
        observer = PatternFlowObserver(
            SimpleNamespace(list_contexts=lambda: (_Context(observed),)),
            rest, "unused", clock_ms=lambda: PatternFlowSourceTests.CLOSE + 5_000,
            get_candidates=lambda: (),
        )
        self.assertEqual(observer.once(), 0)
        self.assertEqual(rest.requests, [])
        observer.close()

        bad = _Context(observed)
        bad.trades_subscription_state = "DEGRADED"
        rest = _REST(recent, previous, current)
        observer = PatternFlowObserver(
            SimpleNamespace(list_contexts=lambda: (bad,)), rest, "unused",
            clock_ms=lambda: PatternFlowSourceTests.CLOSE + 5_000,
            get_candidates=lambda: (_candidate(),),
        )
        self.assertEqual(observer.once(), 0)
        self.assertEqual(rest.requests, [])
        observer.close()

    def test_stale_or_revised_evidence_not_accepted_for_entry(self):
        observed, recent, previous, current = PatternFlowSourceTests.source()
        ctx = _Context(observed)
        clock_time = [PatternFlowSourceTests.CLOSE + 5_000]
        observer = PatternFlowObserver(
            SimpleNamespace(list_contexts=lambda: (ctx,)),
            _REST(recent, previous, current), "unused",
            clock_ms=lambda: clock_time[0],
            get_candidates=lambda: (_candidate(),),
        )
        self.assertEqual(observer.once(), 1)
        evidence = observer.get(_candidate())
        scope = ExistingPatternEntryScope(
            "pattern-1", "BTCUSDT", "Falling Wedge", "LONG", 5,
            "APPROVED", "RETEST_DETECTED",
        )
        self.assertFalse(match_existing_pattern_flow(scope, evidence, now_ms=clock_time[0]))
        clock_time[0] = PatternFlowSourceTests.CLOSE + 120_001
        self.assertIsNone(observer.get(_candidate()))
        observer.close()


if __name__ == "__main__":
    unittest.main()
