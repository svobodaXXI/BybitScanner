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



class PostBreakoutImpulsePriorityResearchTests(unittest.TestCase):
    """Earlier-than-retest hypothesis only; ZERO order permissions."""

    @staticmethod
    def _host(pattern="Falling Wedge", phase="WAITING_RETEST", direction="LONG"):
        from types import SimpleNamespace

        snapshot = {"pattern": pattern}
        state = {"phase": phase, "direction": direction,
                 "pattern": pattern, "state_version": "1.0"}
        if pattern in ("Falling Wedge", "Rising Wedge"):
            snapshot["geometry"] = {
                "upper_line": {"slope": -1.0, "intercept": 200.0},
                "lower_line": {"slope": -0.5, "intercept": 145.0},
                "apex": {"index": 110, "price": 90.0,
                         "valid_intersection": True},
                "current_index": 100,
            }
            snapshot["scanner_geometry_cursor"] = {
                "version": "1.0", "timeframe": "1",
                "geometry_index": 100, "source_candle_time_ms": 60_000,
            }
            state.update({
                "geometry_cursor": 102 if phase == "RETEST_DETECTED" else 101,
                "breakout_index": 101,
                "retest_index": 102 if phase == "RETEST_DETECTED" else None,
            })
        elif pattern in ("L-shape", "MIRROR"):
            term = "l_shape" if pattern == "L-shape" else "mirror_entry"
            stop, target = ("96", "110") if direction == "LONG" else ("104", "90")
            snapshot[term] = {
                "direction": direction, "source_timeframe": "1",
                "breakout_time_ms": 120_000,
                "reference": "100", "target": target, "stop": stop,
                "structural_stop": stop, "stop_kind": "STRUCTURAL",
                "potential_percent": "10", "reward_risk": "2.5",
            }
            if pattern == "MIRROR":
                # Owner-approved post-#1193 origin; no legacy HORN/Box or
                # wrong-side breakout may count as a MIRROR flow host.
                snapshot[term].update({
                    "level_id": "lvl-impulse-mirror-fixture",
                    "level_source": "pattern_boundary",
                    "level_pattern": (
                        "Rising Wedge" if direction == "LONG"
                        else "Falling Wedge"
                    ),
                    "level_side": (
                        "lower" if direction == "LONG" else "upper"
                    ),
                    "level_breakout_direction": (
                        "DOWN" if direction == "LONG" else "UP"
                    ),
                })
                snapshot[term]["confirmation"] = {
                    "close_time_ms": 180_000, "timeframe": "1",
                    "kind": "ENGULFING",
                }
            state.update({
                "last_candle_time_ms": (
                    180_000 if phase == "RETEST_DETECTED" else 120_000
                ),
                "breakout_time_ms": 120_000,
                "retest_time_ms": (
                    180_000 if phase == "RETEST_DETECTED" else None
                ),
            })
        elif pattern == "IKIGAI_BOX":
            snapshot["identity"] = {"direction": direction}
            snapshot["source_box_candidate_id"] = "box-parent-1"
            state["source_box_candidate_id"] = "box-parent-1"
        return SimpleNamespace(
            candidate_id="wedge-verified-123", state_revision=9,
            symbol=SimpleNamespace(value="BTCUSDT"),
            status="APPROVED", signal_snapshot=snapshot, robot_state=state,
        )

    @staticmethod
    def _observe(host, receipt=None, *, breakout=180_000, now=180_100):
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
            host, None, breakout_known_at_ms=180_000, decision_ms=180_100,
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
        self.assertIsNone(self._observe(host, breakout=180_001))
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


    def test_breakout_time_must_match_durable_wedge_index(self):
        from robot_entry_flow_evidence import canonical_host_breakout_known_at_ms

        host = self._host()
        self.assertEqual(canonical_host_breakout_known_at_ms(host), 180_000)
        for bad in (0, 119_999, 180_001):
            self.assertIsNone(self._observe(host, breakout=bad))
        host.robot_state["breakout_index"] = 100
        self.assertIsNone(canonical_host_breakout_known_at_ms(host))
        self.assertIsNone(self._observe(host))

    def test_wedge_anchor_apex_and_retest_integrity_fail_closed(self):
        for mutation in (
            lambda h: h.signal_snapshot["scanner_geometry_cursor"].update(
                source_candle_time_ms=60_001),
            lambda h: h.robot_state.update(breakout_index=109),
            lambda h: h.robot_state.update(geometry_cursor=100),
            lambda h: h.robot_state.update(state_version="forged"),
            lambda h: h.signal_snapshot["geometry"]["apex"].update(index=101),
            lambda h: h.signal_snapshot["geometry"].pop("upper_line"),
        ):
            with self.subTest(mutation=mutation):
                host = self._host()
                mutation(host)
                self.assertIsNone(self._observe(host))
        retested = self._host(phase="RETEST_DETECTED")
        retested.robot_state["retest_index"] = 101
        self.assertIsNone(self._observe(retested))

    def test_lshape_and_mirror_frozen_breakout_consistency(self):
        from robot_entry_flow_evidence import canonical_host_breakout_known_at_ms

        for pattern, phase in (
            ("L-shape", "L_SHAPE_WAITING_RETEST"),
            ("MIRROR", "RETEST_DETECTED"),
        ):
            with self.subTest(pattern=pattern):
                host = self._host(pattern, phase)
                self.assertEqual(canonical_host_breakout_known_at_ms(host), 180_000)
                host.robot_state["breakout_time_ms"] = 60_000
                self.assertIsNone(canonical_host_breakout_known_at_ms(host))
        mirror = self._host("MIRROR", "RETEST_DETECTED")
        mirror.signal_snapshot["mirror_entry"]["confirmation"]["kind"] = "UNKNOWN"
        self.assertIsNone(self._observe(mirror))

    def test_box_has_no_proven_frozen_breakout_adapter_yet(self):
        from robot_entry_flow_evidence import canonical_host_breakout_known_at_ms

        box = self._host("IKIGAI_BOX", "BOX_ENTRY_READY")
        self.assertIsNone(canonical_host_breakout_known_at_ms(box))
        self.assertIsNone(self._observe(box))
        # No fallback to a guessed breakout time or a different host family.
        self.assertIsNone(self._observe(box, breakout=180_000))


class StopCampaignRenewalResearchTests(unittest.TestCase):
    """Research only: a STOP campaign cannot reuse pre-STOP flow as renewal."""

    @staticmethod
    def _proposal(**overrides):
        from terminal.application.robot_admission import RobotReentryAdmissionRequest

        values = dict(
            campaign_id="canonical-campaign-1", direction="LONG",
            frozen_thesis_sha256="a" * 64,
            reserved_risk_usdt=Decimal("3"),
            previous_stop_exec_id="durable-stop-exec-1",
            confirmed_at_ms=60_000,
            strategy_confirmation_proven=True,
        )
        values.update(overrides)
        return RobotReentryAdmissionRequest(**values)

    @staticmethod
    def _observe(proposal=None, proof=None, *, stopped=30_000, host=None):
        from terminal.application.robot_reentry_adapter import (
            observe_post_stop_campaign_renewal,
        )

        return observe_post_stop_campaign_renewal(
            proposal if proposal is not None
            else StopCampaignRenewalResearchTests._proposal(),
            host if host is not None
            else PostBreakoutImpulsePriorityResearchTests._host(),
            certificate() if proof is None else proof,
            previous_stop_at_ms=stopped,
            breakout_known_at_ms=180_000,
            decision_ms=180_100,
        )

    def test_fresh_long_and_short_impulse_is_only_a_nontrading_hypothesis(self):
        long = self._observe()
        self.assertEqual(long.outcome, "REENTRY_IMPULSE_RESEARCH")
        self.assertFalse(long.trading_authorized)
        self.assertEqual(long.candidate_id, "wedge-verified-123")

        short_host = PostBreakoutImpulsePriorityResearchTests._host(
            "Rising Wedge", "WAITING_RETEST", "SHORT",
        )
        short_flow = replace(
            certificate(), direction="SHORT",
            transition=replace(
                transition(buy=False, sell=True),
                current_delta_fraction=Decimal("-0.45"),
                current_price_change_bps=Decimal("-11"),
            ),
        )
        short = self._observe(
            self._proposal(direction="SHORT"), short_flow, host=short_host,
        )
        self.assertEqual(short.outcome, "REENTRY_IMPULSE_RESEARCH")
        self.assertFalse(short.trading_authorized)

    def test_both_closed_minutes_must_follow_stop_and_new_pattern(self):
        # A valid certificate can be fresh but still contain old pre-STOP data.
        later_pattern = self._proposal(confirmed_at_ms=120_000)
        decision = self._observe(later_pattern, stopped=90_000)
        self.assertEqual(decision.outcome, "WAIT_SOURCE")
        self.assertEqual(
            decision.reason, "RENEWED_FLOW_WINDOWS_NOT_POST_STOP_AND_PATTERN",
        )
        self.assertFalse(decision.trading_authorized)
        self.assertIsNone(self._observe(stopped=60_000))
        self.assertIsNone(self._observe(self._proposal(confirmed_at_ms=90_000), stopped=100_000))

    def test_missing_or_uncertain_tape_cannot_propose_renewal(self):
        from terminal.application.robot_reentry_adapter import (
            observe_post_stop_campaign_renewal,
        )
        host = PostBreakoutImpulsePriorityResearchTests._host()
        absent = observe_post_stop_campaign_renewal(
            self._proposal(), host, None, previous_stop_at_ms=30_000,
            breakout_known_at_ms=180_000, decision_ms=180_100,
        )
        self.assertEqual(absent.outcome, "WAIT_SOURCE")
        for change in (
            {"source_complete": False},
            {"receipt_cutoff_proven": False},
            {"transport_generation_proven": False},
            {"candidate_id": "unrelated-candidate"},
            {"state_revision": 8},
        ):
            with self.subTest(change=change):
                result = self._observe(proof=replace(certificate(), **change))
                self.assertEqual(result.outcome, "WAIT_SOURCE")
                self.assertFalse(result.trading_authorized)
        not_accelerating = replace(
            certificate(), transition=transition(buy=False, sell=True),
        )
        self.assertEqual(
            self._observe(proof=not_accelerating).outcome, "WAIT_DIRECTION",
        )

    def test_no_stop_no_campaign_link_wrong_direction_or_old_host(self):
        from terminal.application.robot_admission import RobotReentryAdmissionRequest

        self.assertIsNone(self._observe(
            self._proposal(previous_stop_exec_id=None, original_risk_budget_usdt=Decimal("9")),
        ))
        self.assertIsNone(self._observe(
            self._proposal(strategy_confirmation_proven=False),
        ))
        self.assertIsNone(self._observe(self._proposal(direction="SHORT")))
        self.assertIsNone(self._observe(
            self._proposal(campaign_id=""),
        ))
        host = PostBreakoutImpulsePriorityResearchTests._host()
        host.status = "CLOSED"
        self.assertIsNone(self._observe(host=host))
        host = PostBreakoutImpulsePriorityResearchTests._host(
            "Double Bottom", "RETEST_DETECTED",
        )
        self.assertIsNone(self._observe(host=host))


class PatternFlowOptInExecutionGateTests(unittest.TestCase):
    """First-release Wedge opt-in; other native entry routes stay unchanged."""

    @staticmethod
    def _monitor(observer, *, l_shape_enabled=False):
        from terminal.application.robot_breakout_monitor import RobotBreakoutMonitor

        monitor = object.__new__(RobotBreakoutMonitor)
        monitor._clock_ms = lambda: 181_000
        monitor._get_pattern_flow_evidence = observer
        monitor._impulse_l_shape_paper_enabled = l_shape_enabled
        return monitor

    @staticmethod
    def _record(pattern, direction, phase):
        from types import SimpleNamespace

        snap = {"pattern": pattern}
        state = {"phase": phase, "direction": direction}
        if pattern in ("L-shape", "MIRROR"):
            snap["l_shape" if pattern == "L-shape" else "mirror_entry"] = {
                "direction": direction,
            }
        if pattern == "IKIGAI_BOX":
            snap["identity"] = {"direction": direction}
            snap["source_box_candidate_id"] = "frozen-box-plan"
            state["source_box_candidate_id"] = "frozen-box-plan"
        return SimpleNamespace(
            candidate_id="pattern-original", symbol=SimpleNamespace(value="BTCUSDT"),
            signal_snapshot=snap, robot_state=state, status="APPROVED",
            state_revision=9,
        )

    @staticmethod
    def _families():
        return (
            ("Falling Wedge", "LONG", "RETEST_DETECTED"),
            ("Rising Wedge", "SHORT", "RETEST_DETECTED"),
            ("L-shape", "LONG", "RETEST_DETECTED"),
            ("MIRROR", "SHORT", "RETEST_DETECTED"),
            ("IKIGAI_BOX", "LONG", "BOX_ENTRY_READY"),
        )

    @staticmethod
    def _receipt(direction):
        proof = certificate()
        return replace(
            proof, candidate_id="pattern-original", direction=direction,
            transition=replace(
                transition(buy=direction == "LONG", sell=direction == "SHORT"),
                current_delta_fraction=Decimal(
                    "0.45" if direction == "LONG" else "-0.45",
                ),
                current_price_change_bps=Decimal(
                    "11" if direction == "LONG" else "-11",
                ),
            ),
        )

    def test_absent_observer_preserves_original_paper_entry_path(self):
        owner = self._monitor(None)
        for pattern, direction, phase in self._families():
            with self.subTest(pattern=pattern):
                self.assertTrue(owner._pattern_flow_allows_entry(
                    self._record(pattern, direction, phase),
                ))

    def test_optin_absent_or_erroring_source_blocks_only_enabled_families(self):
        for l_shape_enabled in (False, True):
            for pattern, direction, phase in self._families():
                for should_raise in (False, True):
                    calls = []
                    def observer(record):
                        calls.append(record)
                        if should_raise:
                            raise RuntimeError("source reconnecting")
                        return None
                    owner = self._monitor(observer, l_shape_enabled=l_shape_enabled)
                    record = self._record(pattern, direction, phase)
                    enabled = pattern in ("Falling Wedge", "Rising Wedge") or (
                        pattern == "L-shape" and l_shape_enabled
                    )
                    with self.subTest(pattern=pattern, l_shape_enabled=l_shape_enabled,
                                      should_raise=should_raise):
                        self.assertEqual(owner._pattern_flow_allows_entry(record), not enabled)
                        self.assertEqual(calls, [record] if enabled else [])

    def test_only_fresh_bound_same_direction_tape_allows_enabled_entry_gate(self):
        for pattern, direction, phase in self._families():
            if pattern not in ("Falling Wedge", "Rising Wedge", "L-shape"):
                continue
            with self.subTest(pattern=pattern):
                record = self._record(pattern, direction, phase)
                good = self._receipt(direction)
                self.assertTrue(
                    self._monitor(lambda _: good, l_shape_enabled=True)
                    ._pattern_flow_allows_entry(record),
                )
                for bad in (
                    replace(good, candidate_id="foreign"),
                    replace(good, state_revision=8),
                    replace(good, symbol="ETHUSDT"),
                    replace(good, direction="SHORT" if direction == "LONG" else "LONG"),
                    replace(good, source_complete=False),
                    replace(good, receipt_cutoff_proven=False),
                    replace(good, transport_generation_proven=False),
                    replace(good, closed_at_ms=60_000),
                ):
                    self.assertFalse(
                        self._monitor(lambda _, receipt=bad: receipt, l_shape_enabled=True)
                        ._pattern_flow_allows_entry(record),
                    )

    def test_auxiliary_reversal_has_no_independent_entry_scope(self):
        for pattern, direction in (("Double Top", "SHORT"), ("Double Bottom", "LONG")):
            self.assertIsNone(existing_pattern_entry_scope(
                self._record(pattern, direction, "RETEST_DETECTED"),
            ))


if __name__ == "__main__":
    unittest.main()
