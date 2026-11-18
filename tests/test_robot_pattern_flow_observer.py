"""Passive same-candidate pattern flow observer: zero new Scanner/Robot actions."""
import os
import unittest
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import patch

from robot_entry_flow_evidence import ExistingPatternEntryScope, match_existing_pattern_flow
from terminal.market_data.pattern_flow_observer import (
    PatternFlowObserver, pattern_flow_enabled, PATTERN_FLOW_PAPER_OPT_IN,
    source_coverage_audit,
)
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
    def test_coverage_audit_proves_missing_source_without_auto_subscribing(self):
        observed, recent, previous, current = PatternFlowSourceTests.source()
        now = PatternFlowSourceTests.CLOSE + 5_000
        # A valid canonical candidate with no publicTrade subscription is
        # UNKNOWN, not a certified flow or an invitation to subscribe.
        absent = _candidate()
        absent.symbol = SimpleNamespace(value="ETHUSDT")
        with_source = _candidate()
        result = source_coverage_audit(
            (absent, with_source), (_Context(observed),), now_ms=now,
        )
        counts = result["counts"]
        self.assertEqual(counts["approved_exact_scope"], 2)
        self.assertEqual(counts["missing_subscription"], 1)
        self.assertEqual(counts["window_present_needs_rest_parity"], 1)
        self.assertEqual(counts["buffer_at_limit"], 0)
        self.assertFalse(result["source_complete"])
        self.assertFalse(result["trading_authorized"])
        # No raw IDs, trade prints, symbol names or order authority leak.
        self.assertNotIn("BTCUSDT", str(result))
        self.assertNotIn("ETHUSDT", str(result))

    def test_capacity_and_unready_are_distinct_from_complete_source(self):
        observed, *_ = PatternFlowSourceTests.source()
        clock = PatternFlowSourceTests.CLOSE + 5_000
        first = source_coverage_audit(
            (_candidate(),), (_Context(observed),), now_ms=clock,
        )
        self.assertEqual(
            first["counts"]["window_present_needs_rest_parity"], 1,
        )
        # Buffer capacity can mask the previous closed minute; never
        # treat a full 512-print buffer as complete 2-minute history.
        from terminal.market_data.impulse_observation import ObservedPrint
        filled = dict(observed)
        filled["prints"] = tuple(
            ObservedPrint(
                f"trade-{i}", PatternFlowSourceTests.CLOSE - 30_000,
                i, "Buy", Decimal("100"), Decimal("1"),
            ) for i in range(512)
        )
        saturated = source_coverage_audit(
            (_candidate(),), (_Context(filled),), now_ms=clock,
        )
        self.assertEqual(saturated["counts"]["buffer_at_limit"], 1)
        self.assertEqual(saturated["counts"]["missing_two_closed_minutes"], 1)
        self.assertEqual(saturated["counts"]["window_present_needs_rest_parity"], 0)
        unready = _Context(observed)
        unready.trades_subscription_state = "CONNECTING"
        diagnostic = source_coverage_audit(
            (_candidate(),), (unready,), now_ms=clock,
        )
        self.assertEqual(diagnostic["counts"]["unready_subscription"], 1)
        self.assertEqual(diagnostic["counts"]["buffer_at_limit"], 0)

    def test_approved_pattern_warms_one_passive_trade_only_context(self):
        from terminal.market_data.hub import MarketDataHub
        from tests.test_terminal_market_data_hub import _Registry, _context
        observed, recent, previous, current = PatternFlowSourceTests.source()
        hub = MarketDataHub(_Registry(), _context,
                            connection_factory=lambda *_a, **_k: None)
        record = _candidate()
        observer = PatternFlowObserver(
            hub, _REST(recent, previous, current), "unused",
            clock_ms=lambda: PatternFlowSourceTests.CLOSE + 5_000,
            get_candidates=lambda: (record,),
        )
        try:
            self.assertEqual(observer.once(), 0)
            self.assertEqual(hub.list_contexts(), ())
            self.assertEqual(len(hub.list_flow_contexts()), 1)
            flow = hub.list_flow_contexts()[0]
            self.assertEqual(flow.symbol, "BTCUSDT")
            self.assertEqual(flow.impulse_observation.snapshot()["buffer_capacity"], 1000)
            self.assertFalse(flow.trade_bootstrap_complete)
            self.assertEqual(observer.source_coverage()["counts"]["unready_subscription"], 1)
        finally:
            observer.close()
            self.assertEqual(hub.list_flow_contexts(), ())
            hub.close()

    def test_opt_in_is_explicit_and_default_off(self):
        with patch.dict(os.environ, {}, clear=True):
            self.assertFalse(pattern_flow_enabled())
        for value in ("", "0", "true", "yes", "2"):
            with self.subTest(value=value):
                self.assertFalse(pattern_flow_enabled({PATTERN_FLOW_PAPER_OPT_IN: value}))
        self.assertTrue(pattern_flow_enabled({PATTERN_FLOW_PAPER_OPT_IN: "1"}))

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

    def test_opt_in_certification_window_is_enabled_on_existing_candidate_only(self):
        from terminal.market_data.impulse_observation import PublicTradeObservation
        observed, recent, previous, current = PatternFlowSourceTests.source()
        real = PublicTradeObservation("BTCUSDT")
        # Observer must not create a subscriber or trade. Its read-only source
        # is already attached, so a real opt-in source can expand its buffer.
        context = _Context(observed)
        context.impulse_observation = real
        rest = _REST(recent, previous, current)
        observer = PatternFlowObserver(
            SimpleNamespace(list_contexts=lambda: (context,)), rest,
            "unused", clock_ms=lambda: PatternFlowSourceTests.CLOSE + 5_000,
            get_candidates=lambda: (_candidate(),),
        )
        self.assertEqual(real.snapshot()["buffer_capacity"], 512)
        self.assertEqual(observer.once(), 0)
        self.assertEqual(real.snapshot()["buffer_capacity"], 1000)
        self.assertEqual(real.snapshot()["observed_prints"], 0)
        self.assertEqual(rest.requests, [])
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

    def test_observer_covers_all_existing_pattern_entry_families(self):
        observed, recent, previous, current = PatternFlowSourceTests.source()
        patterns = (
            ("L-shape", "LONG", "RETEST_DETECTED", "l_shape"),
            ("MIRROR", "LONG", "RETEST_DETECTED", "mirror_entry"),
            ("Double Top", "SHORT", "RETEST_DETECTED", "neckline_entry"),
            ("Double Bottom", "LONG", "RETEST_DETECTED", "neckline_entry"),
            ("IKIGAI_BOX", "LONG", "BOX_ENTRY_READY", "identity"),
            ("Rising Wedge", "SHORT", "RETEST_DETECTED", None),
        )
        for pattern, direction, phase, terms_key in patterns:
            with self.subTest(pattern=pattern):
                record = _candidate(direction=direction, phase=phase)
                frozen = {"pattern": pattern}
                state = dict(record.robot_state)
                if terms_key:
                    frozen[terms_key] = {"direction": direction}
                if pattern == "IKIGAI_BOX":
                    frozen["source_box_candidate_id"] = "box-plan-1"
                    state["source_box_candidate_id"] = "box-plan-1"
                record = SimpleNamespace(
                    **{**vars(record), "signal_snapshot": frozen,
                       "robot_state": state}
                )
                rest = _REST(recent, previous, current)
                observer = PatternFlowObserver(
                    SimpleNamespace(list_contexts=lambda: (_Context(observed),)),
                    rest, "unused",
                    clock_ms=lambda: PatternFlowSourceTests.CLOSE + 5_000,
                    get_candidates=lambda: (record,),
                )
                self.assertEqual(observer.once(), 1)
                proof = observer.get(record)
                self.assertIsNotNone(proof)
                self.assertEqual(proof.candidate_id, record.candidate_id)
                self.assertEqual(len(rest.requests), 3)
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
