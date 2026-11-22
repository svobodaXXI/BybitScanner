"""Focused guard tests: candle/flow confluence is research, not an order."""
import unittest
from decimal import Decimal
from types import SimpleNamespace

from robot_entry_flow_evidence import FlowTransition
from terminal.market_data.wedge_candle_exhaustion_research import (
    ClosedCandlePatternObservation, observe_wedge_candle_exhaustion,
)


class WedgeCandleExhaustionResearchTests(unittest.TestCase):
    @staticmethod
    def host(pattern="Falling Wedge", phase="WAITING_BREAKOUT"):
        direction = "LONG" if pattern == "Falling Wedge" else "SHORT"
        return SimpleNamespace(
            status="APPROVED", candidate_id="wedge-frozen-1",
            state_revision=3, symbol=SimpleNamespace(value="BTCUSDT"),
            signal_snapshot={"pattern": pattern},
            robot_state={"pattern": pattern, "direction": direction, "phase": phase},
        )

    @staticmethod
    def candle(name="BULLISH_ENGULFING", **overrides):
        values = dict(
            name=name, candidate_id="wedge-frozen-1", state_revision=3,
            symbol="BTCUSDT", source_id="closed-ohcl-replay-1",
            pattern_version="v1", event_group="same-price-event-1",
            closed_at_ms=60_000, available_at_ms=60_010,
        )
        values.update(overrides)
        return ClosedCandlePatternObservation(**values)

    @staticmethod
    def flow(*, long=True, fading=True, known_at=60_015):
        return FlowTransition(
            known_at_ms=known_at,
            current_delta_fraction=Decimal("-0.2") if long else Decimal("0.2"),
            current_price_change_bps=Decimal("-1") if long else Decimal("1"),
            buy_wave_accelerating=False, sell_wave_accelerating=False,
            sell_impact_fading=fading if long else False,
            buy_impact_fading=fading if not long else False,
            bid_refill_observed=None, ask_refill_observed=None,
            sell_absorption_candidate=None, buy_absorption_candidate=None,
        )

    def observe(self, *candles, host=None, flow=None, decision_ms=60_020):
        return observe_wedge_candle_exhaustion(
            self.host() if host is None else host,
            self.flow() if flow is None else flow,
            tuple(candles), decision_ms=decision_ms,
        )

    def test_long_fade_with_bullish_candle_is_descriptive_only(self):
        result = self.observe(self.candle())
        self.assertEqual(result.outcome, "FLOW_FADE_WITH_CANDLE_CONTEXT_RESEARCH")
        self.assertEqual(result.candle_event_outcomes, (
            ("same-price-event-1", "SUPPORT"),
        ))
        self.assertFalse(result.arc_geometry_attested)
        self.assertFalse(result.source_complete)
        self.assertFalse(result.trading_authorized)

    def test_short_fade_with_evening_star_and_hanging_man_one_event(self):
        host = self.host("Rising Wedge")
        result = self.observe(
            self.candle("EVENING_STAR"),
            self.candle("HANGING_MAN"),
            host=host, flow=self.flow(long=False),
        )
        self.assertEqual(result.direction, "SHORT")
        self.assertEqual(result.candle_event_outcomes, (
            ("same-price-event-1", "SUPPORT"),
        ))
        self.assertEqual(result.outcome, "FLOW_FADE_WITH_CANDLE_CONTEXT_RESEARCH")

    def test_doji_is_indecision_not_reversal_confirmation(self):
        result = self.observe(self.candle("DOJI"))
        self.assertEqual(result.outcome, "FLOW_FADE_WITH_INDECISION_RESEARCH")
        self.assertEqual(result.candle_event_outcomes[0][1], "INDECISION")
        self.assertFalse(result.trading_authorized)

    def test_conflicting_candle_does_not_become_bullish_support(self):
        result = self.observe(
            self.candle("BULLISH_ENGULFING"),
            self.candle("BEARISH_ENGULFING"),
        )
        self.assertEqual(result.candle_event_outcomes[0][1], "CONFLICT")
        self.assertEqual(result.outcome, "FLOW_FADE_ONLY_RESEARCH")

    def test_wrong_candidate_future_unversioned_and_unsupported_are_ignored(self):
        result = self.observe(
            self.candle(candidate_id="other"),
            self.candle(state_revision=4),
            self.candle(symbol="ETHUSDT"),
            self.candle(available_at_ms=60_021),
            self.candle(closed_at_ms=60_021),
            self.candle(pattern_version=""),
            self.candle(event_group=""),
            self.candle("TRIPLE_BOTTOM"),
        )
        self.assertEqual(result.candle_event_outcomes, ())
        self.assertEqual(result.outcome, "FLOW_FADE_ONLY_RESEARCH")

    def test_future_flow_cannot_prove_fade(self):
        result = self.observe(
            self.candle("HAMMER"), flow=self.flow(known_at=60_030),
        )
        self.assertIsNone(result.opposing_flow_fading)
        self.assertEqual(result.outcome, "CANDLE_CONTEXT_ONLY_RESEARCH")

    def test_not_a_wedge_prebreakout_approved_host(self):
        host = self.host(phase="RETEST_DETECTED")
        self.assertIsNone(self.observe(self.candle(), host=host))
        host = self.host()
        host.status = "OPEN"
        self.assertIsNone(self.observe(self.candle(), host=host))
        host = self.host("IKIGAI_BOX")
        self.assertIsNone(self.observe(self.candle(), host=host))


if __name__ == "__main__":
    unittest.main()
