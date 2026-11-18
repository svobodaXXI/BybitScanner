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
    FlowTransition,
    match_existing_pattern_flow, existing_pattern_entry_scope,
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
            ("Double Top", "SHORT", "RETEST_DETECTED", "neckline_entry"),
            ("Double Bottom", "LONG", "RETEST_DETECTED", "neckline_entry"),
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


if __name__ == "__main__":
    unittest.main()
