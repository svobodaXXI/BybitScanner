"""Passive same-candidate pattern flow observer: zero new Scanner/Robot actions."""
import os
import unittest
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import patch

from robot_entry_flow_evidence import (
    ExistingPatternEntryScope, existing_pattern_entry_scope,
    match_existing_pattern_flow,
)
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
    def test_open_wedge_certifies_source_only_fade_on_same_candidate(self):
        """Open trade gets completed source facts, not a fresh trade signal."""
        observed, recent, previous, current = PatternFlowSourceTests.fading_source()
        host = _candidate()
        host.status = "OPEN"
        host.robot_state["pattern"] = "Falling Wedge"
        context = _Context(observed)
        rest = _REST(recent, previous, current)
        observer = PatternFlowObserver(
            SimpleNamespace(list_contexts=lambda: (context,)),
            rest, "unused",
            clock_ms=lambda: PatternFlowSourceTests.CLOSE + 5_000,
            get_candidates=lambda: (host,),
        )
        try:
            self.assertEqual(observer.once(), 1)
            evidence = observer.get(host)
            self.assertIsNotNone(evidence)
            self.assertEqual(evidence.candidate_id, host.candidate_id)
            self.assertEqual(evidence.state_revision, host.state_revision)
            self.assertEqual(evidence.direction, "LONG")
            self.assertTrue(evidence.source_complete)
            self.assertFalse(evidence.transition.buy_wave_accelerating)
            self.assertEqual(len(rest.requests), 3)
            host.status = "INVALIDATED"
            self.assertEqual(observer.once(), 0)
        finally:
            observer.close()

    def test_early_preview_observes_subminute_wave_without_entry_authority(self):
        from terminal.market_data.impulse_observation import PublicTradeObservation
        now = 1_800_030
        source = PublicTradeObservation("BTCUSDT")
        for i, (age, side, price, size) in enumerate((
            (27_000, "Sell", "100", "1"),
            (23_000, "Sell", "99", "1"),
            (14_000, "Buy", "99", "1"),
            (1_000, "Buy", "102", "3"),
        )):
            event_ms = now - age
            self.assertTrue(source.observe({
                "topic": "publicTrade.BTCUSDT",
                "data": [{
                    "i": f"early-{i}", "s": "BTCUSDT", "T": event_ms,
                    "seq": i + 1, "S": side, "p": price, "v": size,
                }],
            }, received_at_ms=event_ms + 25))
        context = _Context({})
        context.impulse_observation = source
        rest = _REST(None, None, None)
        observer = PatternFlowObserver(
            SimpleNamespace(list_contexts=lambda: (context,)), rest, "unused",
            clock_ms=lambda: now, get_candidates=lambda: (_candidate(),),
        )
        try:
            preview = observer.early_preview(_candidate())
            self.assertIsNotNone(preview)
            self.assertEqual(preview.candidate_id, "pattern-1")
            self.assertEqual(preview.state_revision, 4)
            self.assertEqual(preview.known_at_ms, now)
            self.assertEqual(preview.transport_generation, 0)
            self.assertEqual(preview.transition.known_at_ms, now)
            self.assertTrue(preview.transition.buy_wave_accelerating)
            self.assertTrue(preview.gap_or_truncation)
            self.assertEqual(len(preview.window_sha256), 64)
            self.assertFalse(preview.source_complete)
            self.assertFalse(preview.trading_authorized)
            self.assertEqual(rest.requests, [])
            self.assertFalse(match_existing_pattern_flow(
                ExistingPatternEntryScope(
                    "pattern-1", "BTCUSDT", "Falling Wedge", "LONG", 4,
                    "APPROVED", "RETEST_DETECTED",
                ), preview, now_ms=now,
            ))
            # No modification of the closed-M1 certified cache or entry gate.
            self.assertIsNone(observer.get(_candidate()))
            # Sub-minute flow is observable while an approved Wedge or
            # L-shape is still waiting; this never upgrades entry eligibility.
            for pattern, phase, direction, frozen in (
                ("Falling Wedge", "WAITING_BREAKOUT", "LONG",
                 {"pattern": "Falling Wedge"}),
                ("Falling Wedge", "WAITING_RETEST", "LONG",
                 {"pattern": "Falling Wedge"}),
                ("Rising Wedge", "WAITING_BREAKOUT", "SHORT",
                 {"pattern": "Rising Wedge"}),
                ("Rising Wedge", "WAITING_RETEST", "SHORT",
                 {"pattern": "Rising Wedge"}),
                ("L-shape", "L_SHAPE_WAITING_RETEST", "LONG",
                 {"pattern": "L-shape", "l_shape": {"direction": "LONG"}}),
            ):
                with self.subTest(pattern=pattern, phase=phase):
                    host = _candidate(direction=direction, phase=phase)
                    host.signal_snapshot = frozen
                    self.assertIsNone(existing_pattern_entry_scope(host))
                    early = observer.early_preview(host)
                    self.assertIsNotNone(early)
                    self.assertEqual((early.candidate_id, early.state_revision),
                                     ("pattern-1", 4))
                    self.assertEqual(early.direction, direction)
                    self.assertEqual(early.known_at_ms, now)
                    self.assertFalse(early.source_complete)
                    self.assertFalse(early.trading_authorized)
                    self.assertIsNone(observer.get(host))
                    self.assertFalse(match_existing_pattern_flow(
                        ExistingPatternEntryScope(
                            host.candidate_id, "BTCUSDT", pattern, direction,
                            host.state_revision, "APPROVED", phase,
                        ), early, now_ms=now,
                    ))
            self.assertEqual(rest.requests, [])
            source.mark_gap()
            self.assertIsNone(observer.early_preview(_candidate()))
        finally:
            observer.close()

    def test_early_preview_rejects_missing_receipts_stale_source_and_nonhost(self):
        from terminal.market_data.impulse_observation import PublicTradeObservation
        now = 1_800_030
        source = PublicTradeObservation("BTCUSDT")
        context = _Context({})
        context.impulse_observation = source
        clock = [now]
        observer = PatternFlowObserver(
            SimpleNamespace(list_contexts=lambda: (context,)),
            _REST(None, None, None), "unused",
            clock_ms=lambda: clock[0], get_candidates=lambda: (_candidate(),),
        )
        try:
            for i, age in enumerate((23_000, 1_000)):
                self.assertTrue(source.observe({
                    "topic": "publicTrade.BTCUSDT",
                    "data": [{
                        "i": f"early-{i}", "s": "BTCUSDT", "T": now - age,
                        "seq": i + 1, "S": "Buy", "p": "100", "v": "1",
                    }],
                }))  # receipt missing: event timestamp is not causal proof
            self.assertIsNone(observer.early_preview(_candidate()))
            source.mark_gap()
            for i, age in enumerate((23_000, 1_000)):
                event_ms = now - age
                self.assertTrue(source.observe({
                    "topic": "publicTrade.BTCUSDT",
                    "data": [{
                        "i": f"again-{i}", "s": "BTCUSDT", "T": event_ms,
                        "seq": i + 1, "S": "Buy", "p": "100", "v": "1",
                    }],
                }, received_at_ms=event_ms + 20))
            self.assertIsNotNone(observer.early_preview(_candidate()))
            for bad in (
                SimpleNamespace(**{**vars(_candidate()), "status": "OPEN"}),
                SimpleNamespace(**{**vars(_candidate()),
                    "signal_snapshot": {"pattern": "Double Top"}}),
                SimpleNamespace(**{**vars(_candidate()),
                    "robot_state": {"direction": "SHORT", "phase": "RETEST_DETECTED"}}),
                SimpleNamespace(**{**vars(_candidate()),
                    "robot_state": {"direction": "LONG", "phase": "EXPIRED_AT_APEX"}}),
                # Valid warm-up phase is still not enough without frozen
                # direction and exact supported host-pattern identity.
                _candidate(direction="SHORT", phase="WAITING_BREAKOUT"),
                SimpleNamespace(**{**vars(_candidate(phase="WAITING_RETEST")),
                    "signal_snapshot": {"pattern": "Rising Wedge"}}),
                SimpleNamespace(**{**vars(_candidate(phase="L_SHAPE_WAITING_RETEST")),
                    "signal_snapshot": {"pattern": "L-shape"}}),
                SimpleNamespace(**{**vars(_candidate(phase="L_SHAPE_WAITING_RETEST")),
                    "signal_snapshot": {"pattern": "L-shape",
                                        "l_shape": {"direction": "SHORT"}}}),
                SimpleNamespace(**{**vars(_candidate(phase="WAITING_RETEST")),
                    "signal_snapshot": {"pattern": "MIRROR",
                                        "mirror_entry": {"direction": "LONG"}}}),
            ):
                self.assertIsNone(observer.early_preview(bad))
            context.trade_bootstrap_complete = False
            self.assertIsNone(observer.early_preview(_candidate()))
            context.trade_bootstrap_complete = True
            clock[0] += 6_100
            self.assertIsNone(observer.early_preview(_candidate()))
        finally:
            observer.close()

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

    def test_wedge_and_l_shape_warm_before_retest_without_rest_or_orders(self):
        """Warm historical prints at canonical WAITING states, not just at entry."""
        from terminal.market_data.hub import MarketDataHub
        from tests.test_terminal_market_data_hub import _Registry, _context
        observed, recent, previous, current = PatternFlowSourceTests.source()
        phases = (
            ("Falling Wedge", "WAITING_BREAKOUT"),
            ("Rising Wedge", "WAITING_RETEST"),
            ("L-shape", "L_SHAPE_WAITING_RETEST"),
        )
        for pattern, phase in phases:
            with self.subTest(pattern=pattern, phase=phase):
                hub = MarketDataHub(_Registry(), _context,
                                    connection_factory=lambda *_a, **_k: None)
                record = _candidate(phase=phase)
                record.signal_snapshot = {"pattern": pattern}
                rest = _REST(recent, previous, current)
                observer = PatternFlowObserver(
                    hub, rest, "unused",
                    clock_ms=lambda: PatternFlowSourceTests.CLOSE + 5_000,
                    get_candidates=lambda: (record,),
                )
                try:
                    self.assertEqual(observer.once(), 0)
                    self.assertEqual(hub.list_contexts(), ())
                    self.assertEqual(len(hub.list_flow_contexts()), 1)
                    self.assertEqual(hub.list_flow_contexts()[0].symbol, "BTCUSDT")
                    self.assertEqual(rest.requests, [])
                    self.assertIsNone(observer.get(record))
                finally:
                    observer.close()
                    self.assertEqual(hub.list_flow_contexts(), ())
                    hub.close()

    def test_unknown_or_terminal_patterns_never_warm_trade_subscription(self):
        from terminal.market_data.hub import MarketDataHub
        from tests.test_terminal_market_data_hub import _Registry, _context
        observed, recent, previous, current = PatternFlowSourceTests.source()
        for pattern, phase in (
            ("IMPULSE_FLOW", "WAITING_RETEST"),
            ("L-shape", "WAITING_RETEST"),
            ("Falling Wedge", "EXPIRED_AT_APEX"),
            ("IKIGAI_BOX", "BOX_PLAN_ONLY"),
            # Legacy APPROVED standalone DT/DB cannot consume a flow topic
            # after #1153 made both reversal patterns auxiliary-only.
            ("Double Top", "RETEST_DETECTED"),
            ("Double Bottom", "RETEST_DETECTED"),
        ):
            with self.subTest(pattern=pattern, phase=phase):
                hub = MarketDataHub(_Registry(), _context,
                                    connection_factory=lambda *_a, **_k: None)
                record = _candidate(phase=phase)
                record.signal_snapshot = {"pattern": pattern}
                rest = _REST(recent, previous, current)
                observer = PatternFlowObserver(
                    hub, rest, "unused",
                    clock_ms=lambda: PatternFlowSourceTests.CLOSE + 5_000,
                    get_candidates=lambda: (record,),
                )
                try:
                    self.assertEqual(observer.once(), 0)
                    self.assertEqual(hub.list_flow_contexts(), ())
                    self.assertEqual(rest.requests, [])
                finally:
                    observer.close()
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

    def test_proven_wedge_breakout_certifies_early_before_original_retest(self):
        """Real source parity runs on a frozen host in WAITING_RETEST.

        Pure research timing uses already cached evidence, no second REST
        request, no order authority, and no fabricated Box breakout.
        """
        observed, recent, previous, current = PatternFlowSourceTests.source()
        host = _candidate(phase="WAITING_RETEST")
        host.signal_snapshot = {
            "pattern": "Falling Wedge",
            "geometry": {
                "upper_line": {"slope": -1, "intercept": 200},
                "lower_line": {"slope": -0.5, "intercept": 145},
                "apex": {"index": 110, "valid_intersection": True},
                "current_index": 100,
            },
            "scanner_geometry_cursor": {
                "version": "1.0", "timeframe": "1",
                "geometry_index": 100,
                "source_candle_time_ms": PatternFlowSourceTests.CLOSE - 120_000,
            },
        }
        host.robot_state = {
            "state_version": "1.0", "pattern": "Falling Wedge",
            "phase": "WAITING_RETEST", "direction": "LONG",
            "geometry_cursor": 101, "breakout_index": 101,
            "retest_index": None,
        }
        self.assertIsNone(existing_pattern_entry_scope(host))
        rest = _REST(recent, previous, current)
        ctx = _Context(observed)
        observer = PatternFlowObserver(
            SimpleNamespace(list_contexts=lambda: (ctx,)),
            rest, "unused",
            clock_ms=lambda: PatternFlowSourceTests.CLOSE + 5_000,
            get_candidates=lambda: (host,),
        )
        try:
            self.assertEqual(observer.once(), 1)
            receipt = observer.get(host)
            self.assertIsNotNone(receipt)
            self.assertEqual(receipt.source_kind, "BYBIT_TRIPLE_CLOSED_M1_CERTIFIED")
            decision = observer.research_timing(host)
            self.assertEqual(decision.outcome, "IMPULSE_ENTRY_RESEARCH")
            self.assertFalse(decision.trading_authorized)
            self.assertEqual(len(rest.requests), 3)
            # A missing/mutated frozen breakout must never reuse the receipt.
            host.robot_state["breakout_index"] = 100
            self.assertIsNone(observer.research_timing(host))
        finally:
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
                # The real Hub keeps a stable source object through every
                # list_contexts call. Do not synthesize a fresh observer for
                # each read: source-identity matching must reject replacements.
                context = _Context(observed)
                observer = PatternFlowObserver(
                    SimpleNamespace(list_contexts=lambda: (context,)),
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

    def test_cached_certificate_dies_on_reconnect_or_source_replacement(self):
        from terminal.market_data.impulse_observation import PublicTradeObservation
        observed, recent, previous, current = PatternFlowSourceTests.source()
        clock = lambda: PatternFlowSourceTests.CLOSE + 5_000
        live = PublicTradeObservation("BTCUSDT")
        live.enable_certification_buffer()
        # Test via a live observer source, so generation changes are observable.
        prints = observed["prints"]
        for item in prints:
            self.assertTrue(live.observe({
                "topic": "publicTrade.BTCUSDT", "data": [{
                    "i": item.trade_id, "s": "BTCUSDT", "T": item.timestamp_ms,
                    "seq": item.sequence, "S": item.side,
                    "p": str(item.price), "v": str(item.quantity),
                }],
            }, received_at_ms=item.received_at_ms))
        context = _Context(observed)
        context.impulse_observation = live
        hub = SimpleNamespace(list_contexts=lambda: (context,))
        observer = PatternFlowObserver(
            hub, _REST(recent, previous, current), "unused",
            clock_ms=clock, get_candidates=lambda: (_candidate(),),
        )
        try:
            self.assertEqual(observer.once(), 1)
            self.assertIsNotNone(observer.get(_candidate()))
            live.mark_gap()
            self.assertIsNone(observer.get(_candidate()))
            # Replacement with the same symbol and even the same generation
            # must not resurrect a certificate from the previous object.
            replacement = PublicTradeObservation("BTCUSDT")
            replacement.enable_certification_buffer()
            context.impulse_observation = replacement
            self.assertIsNone(observer.get(_candidate()))
        finally:
            observer.close()

    def test_warmed_ws_prints_certify_only_after_canonical_retest(self):
        from terminal.market_data.hub import MarketDataHub
        from tests.test_terminal_market_data_hub import _Registry, _context
        observed, recent, previous, current = PatternFlowSourceTests.source()
        hub = MarketDataHub(_Registry(), _context,
                            connection_factory=lambda *_a, **_k: None)
        candidate = _candidate(phase="WAITING_BREAKOUT")
        record = [candidate]
        rest = _REST(recent, previous, current)
        observer = PatternFlowObserver(
            hub, rest, "unused",
            clock_ms=lambda: PatternFlowSourceTests.CLOSE + 5_000,
            get_candidates=lambda: tuple(record),
        )
        try:
            self.assertEqual(observer.once(), 0)
            self.assertEqual(len(hub.list_flow_contexts()), 1)
            self.assertEqual(rest.requests, [])
            hub._dispatch({
                "op": "subscribe", "req_id": "flow:BTCUSDT", "success": True,
            })
            for item in observed["prints"]:
                raw = {
                    "topic": "publicTrade.BTCUSDT",
                    "data": [{
                        "i": item.trade_id, "s": "BTCUSDT",
                        "T": item.timestamp_ms, "seq": item.sequence,
                        "S": item.side, "p": str(item.price),
                        "v": str(item.quantity),
                    }],
                }
                with patch("terminal.market_data.hub.time.time",
                           return_value=item.received_at_ms / 1000):
                    hub._dispatch(raw)
            self.assertEqual(observer.once(), 0)
            self.assertEqual(rest.requests, [])
            record[0] = SimpleNamespace(
                **{**vars(candidate),
                   "state_revision": candidate.state_revision + 1,
                   "robot_state": {**candidate.robot_state,
                                   "phase": "RETEST_DETECTED"}}
            )
            self.assertEqual(observer.once(), 1)
            proof = observer.get(record[0])
            self.assertIsNotNone(proof)
            self.assertEqual(proof.candidate_id, candidate.candidate_id)
            self.assertEqual(proof.state_revision, candidate.state_revision + 1)
            self.assertEqual(len(rest.requests), 3)
            self.assertEqual(hub.list_contexts(), ())  # still no orderbook
            hub.list_flow_contexts()[0].impulse_observation.mark_gap()
            self.assertIsNone(observer.get(record[0]))
        finally:
            observer.close()
            hub.close()

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
