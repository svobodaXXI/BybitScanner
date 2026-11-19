"""Contract tests for causal entry-flow overlay of EXISTING Robot candidates.

These tests deliberately do not grant order authority or construct
standalone IMPULSE_FLOW Scanner candidates.
"""
import unittest
from dataclasses import replace
from decimal import Decimal

from robot_entry_flow_evidence import (
    CandidateBoundFlowEvidence,
    ExistingPatternEntryScope,
    FlowTransition, PatternEntryArgument,
    match_existing_pattern_flow, existing_pattern_entry_scope,
    summarize_pattern_entry_arguments,
)


def scope():
    return ExistingPatternEntryScope(
        candidate_id="wedge-verified-123",
        symbol="BTCUSDT",
        pattern="Falling Wedge",
        direction="LONG",
        state_revision=9,
        status="APPROVED",
        phase="RETEST_DETECTED",
    )


def transition(*, known_at_ms=180_010, buy=True, sell=False):
    return FlowTransition(
        known_at_ms=known_at_ms,
        current_delta_fraction=Decimal("0.45"),
        current_price_change_bps=Decimal("11"),
        buy_wave_accelerating=buy,
        sell_wave_accelerating=sell,
        sell_impact_fading=False,
        buy_impact_fading=False,
        bid_refill_observed=None,
        ask_refill_observed=None,
        sell_absorption_candidate=None,
        buy_absorption_candidate=None,
    )


def certificate():
    return CandidateBoundFlowEvidence(
        candidate_id="wedge-verified-123",
        symbol="BTCUSDT",
        direction="LONG",
        state_revision=9,
        source_kind="BYBIT_TRIPLE_CLOSED_M1_CERTIFIED",
        closed_at_ms=180_000,
        decision_ms=180_010,
        print_facts_sha256="a" * 64,
        source_complete=True,
        receipt_cutoff_proven=True,
        transport_generation_proven=True,
        transition=transition(),
    )


class PatternEntryFlowOverlayTests(unittest.TestCase):
    def test_matching_existing_wedge_receipt_is_only_descriptive(self):
        self.assertTrue(match_existing_pattern_flow(
            scope(), certificate(), now_ms=181_000,
        ))

    def test_absent_receipt_never_authorizes_entry(self):
        self.assertFalse(match_existing_pattern_flow(
            scope(), None, now_ms=181_000,
        ))

    def test_different_owner_revision_symbol_or_direction_is_rejected(self):
        original = certificate()
        for update in (
            {"candidate_id": "other"},
            {"state_revision": 8},
            {"symbol": "ETHUSDT"},
            {"direction": "SHORT"},
        ):
            with self.subTest(update=update):
                self.assertFalse(match_existing_pattern_flow(
                    scope(), replace(original, **update), now_ms=181_000,
                ))

    def test_standalone_or_unapproved_pattern_is_rejected(self):
        for update in (
            {"pattern": "IMPULSE_FLOW"},
            {"pattern": "IKIGAI_BOX"},  # Box requires BOX_ENTRY_READY
            {"status": "AVAILABLE"},
            {"phase": "WAITING_BREAKOUT"},
            {"state_revision": -1},
        ):
            with self.subTest(update=update):
                self.assertFalse(match_existing_pattern_flow(
                    replace(scope(), **update), certificate(), now_ms=181_000,
                ))

    def test_all_existing_pattern_families_use_frozen_candidate_identity(self):
        from types import SimpleNamespace

        families = (
            ("Falling Wedge", "LONG", "RETEST_DETECTED", None),
            ("Rising Wedge", "SHORT", "RETEST_DETECTED", None),
            ("L-shape", "LONG", "RETEST_DETECTED", "l_shape"),
            ("MIRROR", "SHORT", "RETEST_DETECTED", "mirror_entry"),
            ("IKIGAI_BOX", "LONG", "BOX_ENTRY_READY", "identity"),
        )
        for pattern, direction, phase, terms_key in families:
            with self.subTest(pattern=pattern):
                snap = {"pattern": pattern}
                state = {"phase": phase, "direction": direction}
                if terms_key:
                    snap[terms_key] = {"direction": direction}
                if pattern == "IKIGAI_BOX":
                    snap["source_box_candidate_id"] = "box-plan-1"
                    state["source_box_candidate_id"] = "box-plan-1"
                record = SimpleNamespace(
                    candidate_id="exact-1", symbol=SimpleNamespace(value="BTCUSDT"),
                    status="APPROVED", state_revision=4,
                    signal_snapshot=snap, robot_state=state,
                )
                chosen = existing_pattern_entry_scope(record)
                self.assertIsNotNone(chosen)
                self.assertEqual((chosen.pattern, chosen.direction, chosen.phase),
                                 (pattern, direction, phase))
                proof = certificate()
                proof = replace(proof, candidate_id="exact-1", state_revision=4,
                                direction=direction,
                                transition=transition(
                                    buy=(direction == "LONG"),
                                    sell=(direction == "SHORT"),
                                ))
                self.assertTrue(match_existing_pattern_flow(
                    chosen, proof, now_ms=181_000,
                ))
                self.assertFalse(match_existing_pattern_flow(
                    chosen, replace(proof, state_revision=3), now_ms=181_000,
                ))
                self.assertIsNone(existing_pattern_entry_scope(SimpleNamespace(
                    **{**vars(record), "robot_state": {**state, "direction":
                         ("SHORT" if direction == "LONG" else "LONG")}}
                )))
                if pattern == "IKIGAI_BOX":
                    self.assertIsNone(existing_pattern_entry_scope(SimpleNamespace(
                        **{**vars(record), "status": "BOX_PLAN_ONLY"}
                    )))
                else:
                    self.assertIsNone(existing_pattern_entry_scope(SimpleNamespace(
                        **{**vars(record), "robot_state": {**state, "phase": "WAITING_RETEST"}}
                    )))

    def test_auxiliary_double_extrema_never_authorize_flow_or_standalone_scope(self):
        from types import SimpleNamespace

        for pattern, direction in (("Double Top", "SHORT"), ("Double Bottom", "LONG")):
            with self.subTest(pattern=pattern):
                candidate = SimpleNamespace(
                    candidate_id="legacy-double",
                    symbol=SimpleNamespace(value="BTCUSDT"),
                    status="APPROVED",
                    state_revision=7,
                    signal_snapshot={
                        "pattern": pattern,
                        "robot_handoff_ready": True,
                        "neckline_entry": {"direction": direction},
                        "auxiliary_reversal": {"kind": "DOUBLE_REVERSAL_AUXILIARY"},
                    },
                    robot_state={"phase": "RETEST_DETECTED", "direction": direction},
                )
                self.assertIsNone(existing_pattern_entry_scope(candidate))
                forged_scope = ExistingPatternEntryScope(
                    "legacy-double", "BTCUSDT", pattern, direction,
                    7, "APPROVED", "RETEST_DETECTED",
                )
                receipt = replace(
                    certificate(), candidate_id="legacy-double",
                    state_revision=7, direction=direction,
                    transition=transition(
                        buy=(direction == "LONG"), sell=(direction == "SHORT"),
                    ),
                )
                self.assertFalse(match_existing_pattern_flow(
                    forged_scope, receipt, now_ms=181_000,
                ))

    def test_missing_or_forged_source_proof_rejected(self):
        original = certificate()
        for update in (
            {"source_kind": "WS_ONLY"},
            {"source_complete": False},
            {"receipt_cutoff_proven": False},
            {"transport_generation_proven": False},
            {"print_facts_sha256": ""},
            {"print_facts_sha256": "z" * 64},
        ):
            with self.subTest(update=update):
                self.assertFalse(match_existing_pattern_flow(
                    scope(), replace(original, **update), now_ms=181_000,
                ))

    def test_stale_future_and_backdated_receipts_rejected(self):
        original = certificate()
        cases = (
            (original, 179_999),
            (original, 300_001),
            (replace(original, decision_ms=240_001,
                     transition=transition(known_at_ms=240_001)), 240_002),
            (replace(original, closed_at_ms=180_001), 181_000),
            (replace(original, transition=transition(known_at_ms=190_000)), 181_000),
        )
        for receipt, now in cases:
            with self.subTest(now=now, close=receipt.closed_at_ms):
                self.assertFalse(match_existing_pattern_flow(
                    scope(), receipt, now_ms=now,
                ))

    def test_directional_wave_must_match_frozen_pattern_direction(self):
        self.assertFalse(match_existing_pattern_flow(
            scope(), replace(certificate(), transition=transition(buy=False, sell=True)),
            now_ms=181_000,
        ))
        short_scope = replace(scope(), direction="SHORT", pattern="Rising Wedge")
        short_receipt = replace(
            certificate(), direction="SHORT",
            transition=transition(buy=False, sell=True),
        )
        self.assertTrue(match_existing_pattern_flow(
            short_scope, short_receipt, now_ms=181_000,
        ))



class UnifiedPatternEntryArgumentsTests(unittest.TestCase):
    """All auxiliary evidence stays on one canonical host; no new orders."""

    @staticmethod
    def _host(pattern="Falling Wedge", direction="LONG"):
        from types import SimpleNamespace
        phases = {
            "Falling Wedge": "RETEST_DETECTED",
            "Rising Wedge": "RETEST_DETECTED",
            "L-shape": "RETEST_DETECTED",
            "MIRROR": "RETEST_DETECTED",
            "IKIGAI_BOX": "BOX_ENTRY_READY",
        }
        snap = {"pattern": pattern}
        state = {"direction": direction, "phase": phases.get(pattern, "RETEST_DETECTED")}
        terms = {"L-shape": "l_shape", "MIRROR": "mirror_entry",
                 "IKIGAI_BOX": "identity"}.get(pattern)
        if terms:
            snap[terms] = {"direction": direction}
        if pattern == "IKIGAI_BOX":
            snap["source_box_candidate_id"] = "box-original-1"
            state["source_box_candidate_id"] = "box-original-1"
        return SimpleNamespace(
            candidate_id="host-1",
            symbol=SimpleNamespace(value="BTCUSDT"),
            state_revision=7, status="APPROVED",
            signal_snapshot=snap, robot_state=state,
        )

    @staticmethod
    def _factor(kind="TAKER_PRESSURE", outcome="SUPPORT", **overrides):
        values = dict(
            kind=kind, candidate_id="host-1", state_revision=7,
            symbol="BTCUSDT", direction="LONG", outcome=outcome,
            source_id="verified-example-1", event_at_ms=180_000,
            available_at_ms=180_009,
        )
        values.update(overrides)
        return PatternEntryArgument(**values)

    def test_each_optional_factor_can_support_same_approved_pattern(self):
        host = self._host()
        kinds = (
            "TAKER_PRESSURE", "OPPOSING_PRESSURE_FADE", "LIQUIDATION",
            "OPEN_INTEREST", "DMI_CROSS", "DMI_PRECURSOR",
            "REVERSAL_CANDLE", "DOUBLE_EXTREMUM",
        )
        for kind in kinds:
            with self.subTest(kind=kind):
                result = summarize_pattern_entry_arguments(
                    host, (self._factor(kind),), decision_ms=180_010,
                )
                self.assertEqual(result.candidate_id, "host-1")
                self.assertEqual(len(result.supporting_groups), 1)
                self.assertFalse(result.trading_authorized)
                self.assertIn("UNKNOWN", dict(result.group_outcomes).values())

    def test_correlated_factors_do_not_create_extra_votes(self):
        result = summarize_pattern_entry_arguments(self._host(), (
            self._factor("TAKER_PRESSURE"),
            self._factor("OPPOSING_PRESSURE_FADE"),
            self._factor("DMI_CROSS"),
            self._factor("DMI_PRECURSOR"),
            self._factor("OPEN_INTEREST", outcome="CONTRADICT"),
            self._factor("REVERSAL_CANDLE", outcome="SUPPORT"),
            self._factor("DOUBLE_EXTREMUM", outcome="CONTRADICT"),
        ), decision_ms=180_010)
        votes = dict(result.group_outcomes)
        self.assertEqual(votes["EXECUTED_FLOW"], "SUPPORT")
        self.assertEqual(votes["DMI"], "SUPPORT")
        self.assertEqual(votes["OPEN_INTEREST"], "CONTRADICT")
        self.assertEqual(votes["PRICE_REVERSAL"], "CONFLICT")
        self.assertEqual(votes["LIQUIDATIONS"], "UNKNOWN")
        self.assertEqual(len(result.supporting_groups), 2)
        self.assertFalse(result.trading_authorized)

    def test_wrong_host_stale_future_and_unsupported_kind_do_not_count(self):
        result = summarize_pattern_entry_arguments(self._host(), (
            self._factor(candidate_id="other"),
            self._factor(state_revision=8),
            self._factor(symbol="ETHUSDT"),
            self._factor(direction="SHORT"),
            self._factor(available_at_ms=180_011),
            self._factor(event_at_ms=180_012),
            self._factor(source_id=""),
            self._factor(kind="IMPULSE_FLOW"),
            self._factor(outcome="ALLOW_ORDER"),
        ), decision_ms=180_010)
        self.assertTrue(all(v == "UNKNOWN" for _, v in result.group_outcomes))
        self.assertEqual(result.supporting_groups, ())
        self.assertFalse(result.trading_authorized)

    def test_no_standalone_auxiliary_or_unapproved_signal(self):
        from types import SimpleNamespace
        for pattern in ("IMPULSE_FLOW", "Double Top", "Double Bottom"):
            host = self._host()
            host.signal_snapshot = {"pattern": pattern}
            self.assertIsNone(summarize_pattern_entry_arguments(
                host, (self._factor(),), decision_ms=180_010,
            ))
        not_approved = self._host()
        not_approved.status = "AVAILABLE"
        self.assertIsNone(summarize_pattern_entry_arguments(
            not_approved, (self._factor(),), decision_ms=180_010,
        ))
        early = self._host()
        early.robot_state["phase"] = "WAITING_BREAKOUT"
        self.assertIsNone(summarize_pattern_entry_arguments(
            early, (self._factor(),), decision_ms=180_010,
        ))
        box_plan = self._host("IKIGAI_BOX")
        box_plan.status = "BOX_PLAN_ONLY"
        self.assertIsNone(summarize_pattern_entry_arguments(
            box_plan, (self._factor(),), decision_ms=180_010,
        ))

    def test_every_existing_host_family_keeps_its_own_candidate_and_direction(self):
        for pattern, direction in (
            ("Falling Wedge", "LONG"), ("Rising Wedge", "SHORT"),
            ("L-shape", "LONG"), ("MIRROR", "SHORT"),
            ("IKIGAI_BOX", "LONG"),
        ):
            with self.subTest(pattern=pattern):
                host = self._host(pattern, direction)
                factor = self._factor(direction=direction)
                result = summarize_pattern_entry_arguments(
                    host, (factor,), decision_ms=180_010,
                )
                self.assertEqual((result.pattern, result.candidate_id,
                                  result.direction), (pattern, "host-1", direction))
                self.assertEqual(result.supporting_groups, ("EXECUTED_FLOW",))
                self.assertFalse(result.trading_authorized)
                mismatched = self._factor(
                    direction=("SHORT" if direction == "LONG" else "LONG")
                )
                result = summarize_pattern_entry_arguments(
                    host, (mismatched,), decision_ms=180_010,
                )
                self.assertEqual(result.supporting_groups, ())



if __name__ == "__main__":
    unittest.main()


class PostBreakoutImpulsePriorityResearchTests(unittest.TestCase):
    """Earlier-than-retest hypothesis only; ZERO order permissions."""

    @staticmethod
    def _host(pattern="Falling Wedge", phase="WAITING_RETEST", direction="LONG"):
        from types import SimpleNamespace

        snapshot = {"pattern": pattern}
        state = {"phase": phase, "direction": direction}
        term = {"L-shape": "l_shape", "MIRROR": "mirror_entry",
                "IKIGAI_BOX": "identity"}.get(pattern)
        if term:
            snapshot[term] = {"direction": direction}
        if pattern == "IKIGAI_BOX":
            snapshot["source_box_candidate_id"] = "box-parent-1"
            state["source_box_candidate_id"] = "box-parent-1"
        return SimpleNamespace(
            candidate_id="wedge-verified-123", state_revision=9,
            symbol=SimpleNamespace(value="BTCUSDT"),
            status="APPROVED", signal_snapshot=snapshot, robot_state=state,
        )

    @staticmethod
    def _observe(host, receipt=None, *, breakout=179_000, now=180_100):
        from robot_entry_flow_evidence import observe_post_breakout_impulse_timing

        return observe_post_breakout_impulse_timing(
            host, certificate() if receipt is None else receipt,
            breakout_known_at_ms=breakout, decision_ms=now,
        )

    def test_wedge_prefers_verified_impulse_before_old_retest_gate(self):
        from robot_entry_flow_evidence import existing_pattern_entry_scope

        host = self._host()
        self.assertIsNone(existing_pattern_entry_scope(host))
        decision = self._observe(host)
        self.assertEqual(decision.outcome, "IMPULSE_ENTRY_RESEARCH")
        self.assertEqual(decision.candidate_id, host.candidate_id)
        self.assertFalse(decision.trading_authorized)

    def test_supported_hosts_preserve_frozen_direction(self):
        cases = (
            ("Rising Wedge", "WAITING_RETEST", "SHORT"),
            ("L-shape", "L_SHAPE_WAITING_RETEST", "LONG"),
            ("MIRROR", "RETEST_DETECTED", "LONG"),
            ("IKIGAI_BOX", "BOX_ENTRY_READY", "LONG"),
        )
        for pattern, phase, direction in cases:
            with self.subTest(pattern=pattern):
                host = self._host(pattern, phase, direction)
                proof = replace(
                    certificate(), direction=direction,
                    transition=replace(
                        transition(
                            buy=(direction == "LONG"),
                            sell=(direction == "SHORT"),
                        ),
                        current_delta_fraction=Decimal(
                            "0.45" if direction == "LONG" else "-0.45"
                        ),
                        current_price_change_bps=Decimal(
                            "11" if direction == "LONG" else "-11"
                        ),
                    ),
                )
                decision = self._observe(host, proof)
                self.assertEqual(decision.outcome, "IMPULSE_ENTRY_RESEARCH")
                self.assertFalse(decision.trading_authorized)

    def test_missing_and_unproven_source_are_not_early_entries(self):
        from robot_entry_flow_evidence import observe_post_breakout_impulse_timing

        host = self._host()
        missing = observe_post_breakout_impulse_timing(
            host, None, breakout_known_at_ms=179_000, decision_ms=180_100,
        )
        self.assertEqual(missing.outcome, "WAIT_SOURCE")
        self.assertFalse(missing.trading_authorized)
        for change in (
            {"candidate_id": "foreign"},
            {"state_revision": 8},
            {"symbol": "ETHUSDT"},
            {"direction": "SHORT"},
            {"source_complete": False},
            {"receipt_cutoff_proven": False},
            {"transport_generation_proven": False},
            {"source_kind": "WS_ONLY"},
            {"print_facts_sha256": "invalid"},
            {"decision_ms": 180_101},
        ):
            with self.subTest(change=change):
                proof = replace(certificate(), **change)
                self.assertEqual(self._observe(host, proof).outcome, "WAIT_SOURCE")

    def test_opposite_or_not_accelerating_wave_does_not_promote(self):
        host = self._host()
        proof = replace(
            certificate(),
            transition=transition(buy=False, sell=True),
        )
        result = self._observe(host, proof)
        self.assertEqual(result.outcome, "WAIT_DIRECTION")
        self.assertFalse(result.trading_authorized)

    def test_rejects_stale_future_or_prebreakout_receipts(self):
        host = self._host()
        self.assertIsNone(self._observe(host, breakout=180_101))
        self.assertEqual(self._observe(host, breakout=180_001).outcome, "WAIT_SOURCE")
        self.assertEqual(self._observe(host, now=301_000).outcome, "WAIT_SOURCE")
        self.assertEqual(
            self._observe(host, replace(certificate(), closed_at_ms=180_001)).outcome,
            "WAIT_SOURCE",
        )

    def test_no_unapproved_or_independent_impulse_pattern(self):
        for pattern, phase, direction in (
            ("IMPULSE_FLOW", "RETEST_DETECTED", "LONG"),
            ("Double Top", "RETEST_DETECTED", "SHORT"),
            ("Double Bottom", "RETEST_DETECTED", "LONG"),
            ("Falling Wedge", "WAITING_BREAKOUT", "LONG"),
        ):
            with self.subTest(pattern=pattern):
                self.assertIsNone(self._observe(self._host(pattern, phase, direction)))
        host = self._host()
        host.status = "AVAILABLE"
        self.assertIsNone(self._observe(host))

    def test_rejects_forged_host_terms_and_box_parent(self):
        for pattern, phase in (
            ("L-shape", "L_SHAPE_WAITING_RETEST"),
            ("MIRROR", "RETEST_DETECTED"),
            ("IKIGAI_BOX", "BOX_ENTRY_READY"),
        ):
            with self.subTest(pattern=pattern):
                host = self._host(pattern, phase)
                term = {"L-shape": "l_shape", "MIRROR": "mirror_entry",
                        "IKIGAI_BOX": "identity"}[pattern]
                host.signal_snapshot[term]["direction"] = "SHORT"
                self.assertIsNone(self._observe(host))
        box = self._host("IKIGAI_BOX", "BOX_ENTRY_READY")
        box.robot_state["source_box_candidate_id"] = "foreign-box"
        self.assertIsNone(self._observe(box))
