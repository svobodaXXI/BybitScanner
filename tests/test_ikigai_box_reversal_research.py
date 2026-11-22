"""Focused synthetic sequence tests; no actual source or execution claim."""
from dataclasses import replace
from decimal import Decimal as D
from types import SimpleNamespace as NS
import unittest

from robot_entry_flow_evidence import FlowWindow
from terminal.market_data.ikigai_box_reversal_research import (
    BoxFlowObservation, observe_box_reversal_flow,
)


def case(direction="LONG", book=True):
    digest = "a" * 64
    source = "box-plan-123"
    candidate = NS(
        candidate_id="box-robot-123", state_revision=1, snapshot_sha256=digest,
        symbol=NS(value="BTCUSDT"), trading_account_id=NS(value="paper"),
        status="APPROVED", approved_at_ms=1000,
        signal_snapshot=dict(
            identity=dict(direction=direction, symbol="BTCUSDT"),
            decision_time_ms=1000, pattern="IKIGAI_BOX", environment="PAPER",
            execution_authorized=False, source_box_candidate_id=source,
            plan=dict(direction=direction),
        ),
        robot_state=dict(phase="BOX_ENTRY_READY", source_box_candidate_id=source),
    )
    prices = ("94", "92", "91.9", "92.5") if direction == "LONG" else (
        "106", "108", "108.1", "107.5")
    vols = [(10, 100), (10, 120), (150, 10)]
    if direction == "SHORT":
        vols = [(sell, buy) for buy, sell in vols]
    windows = []
    for i, (buy, sell) in enumerate(vols):
        refill = {}
        if book and i == 1:
            refill = dict(book_valid=True)
            refill["bid_refill_ratio" if direction == "LONG" else "ask_refill_ratio"] = D("0.5")
        win = FlowWindow(
            1000 + i * 1000, 2000 + i * 1000,
            D(prices[i]), D(prices[i + 1]), D(buy), D(sell), **refill,
        )
        windows.append(BoxFlowObservation(
            candidate.candidate_id, 1, digest, "BTCUSDT", 0, win.end_ms, win))
    return candidate, tuple(windows)


def observe(record, windows, **kwargs):
    return observe_box_reversal_flow(
        record, windows, **({"decision_ms": 4000, "max_source_age_ms": 100} | kwargs))


class BoxReversalFlowResearchTests(unittest.TestCase):
    def test_mirrored_handoff_is_research_only(self):
        for direction in ("LONG", "SHORT"):
            with self.subTest(direction=direction):
                record, windows = case(direction)
                result = observe(record, windows)
                self.assertEqual(result.status, "HANDOFF_CANDIDATE")
                self.assertEqual(result.direction, direction)
                self.assertTrue(result.opposing_impact_fading)
                self.assertTrue(result.absorption_candidate)
                self.assertTrue(result.initiative_flip_observed)
                self.assertFalse(result.source_complete)
                self.assertFalse(result.trading_authorized)

    def test_missing_book_does_not_prove_absorption(self):
        record, windows = case(book=False)
        result = observe(record, windows)
        self.assertEqual(result.status, "EXHAUSTION_OBSERVED")
        self.assertIsNone(result.absorption_candidate)
        self.assertTrue(result.initiative_flip_observed)

    def test_refill_without_fade_and_fade_without_flip(self):
        record, (a, b, c) = case()
        no_fade = replace(b, window=replace(b.window, sell_notional_usdt=D("20")))
        result = observe(record, (a, no_fade, c))
        self.assertEqual(result.status, "WAIT_EXHAUSTION")
        self.assertFalse(result.absorption_candidate)
        no_flip = replace(c, window=replace(c.window, buy_notional_usdt=D("5"),
                                            sell_notional_usdt=D("150")))
        result = observe(record, (a, b, no_flip))
        self.assertEqual(result.status, "ABSORPTION_CANDIDATE")
        self.assertFalse(result.initiative_flip_observed)

    def test_reject_future_stale_foreign_or_discontinuous_evidence(self):
        record, (a, b, c) = case()
        for bad in (
            replace(b, candidate_id="foreign"), replace(b, symbol="ETHUSDT"),
            replace(b, state_revision=2), replace(b, snapshot_sha256="b"*64),
            replace(b, generation=1), replace(b, available_at_ms=4001),
            replace(b, available_at_ms=2999),
            replace(b, window=replace(b.window, start_ms=2001)),
            replace(b, window=replace(b.window, price_source="MID")),
            replace(b, window=replace(b.window, buy_notional_usdt=D(0),
                                      sell_notional_usdt=D(0))),
        ):
            with self.subTest(bad=bad):
                self.assertIsNone(observe(record, (a, bad, c)))
        self.assertIsNone(observe(record, (a, b, c), decision_ms=4101))
        self.assertIsNone(observe(record, (a, b, c), decision_ms=3999))
        self.assertIsNone(observe(record, (a, b)))

    def test_only_original_confirmed_paper_box(self):
        record, windows = case()
        for key, bad in (
            ("status", "OPEN"), ("candidate_id", "other"),
            ("trading_account_id", NS(value="live")),
            ("robot_state", dict(phase="WAITING_BREAKOUT", source_box_candidate_id="box-plan-123")),
            ("approved_at_ms", 4001),
        ):
            with self.subTest(key=key):
                altered = NS(**(vars(record) | {key: bad}))
                self.assertIsNone(observe(altered, windows))
        for key, bad in (
            ("pattern", "Rising Wedge"), ("decision_time_ms", 1001),
            ("execution_authorized", True),
        ):
            altered = NS(**(vars(record) | {"signal_snapshot": record.signal_snapshot | {key: bad}}))
            self.assertIsNone(observe(altered, windows))


if __name__ == "__main__":
    unittest.main()
