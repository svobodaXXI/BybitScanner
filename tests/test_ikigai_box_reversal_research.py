"""Focused synthetic sequence tests; no actual source or execution claim."""
from dataclasses import replace
from decimal import Decimal as D
from types import SimpleNamespace as NS
import unittest

from robot_entry_flow_evidence import FlowWindow
from terminal.market_data.sustained_absorption import (
    AbsorptionObservation, RecoveryWindow,
)
from terminal.market_data.ikigai_box_reversal_research import (
    BoxFlowObservation, BoxBoundAbsorption, observe_box_reversal_flow,
    BoxSecondLegExtreme, preview_box_reversal_handoff,
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



def stable_band(record, windows, *, adverse=False, min_depth="60",
                second_recovery="25"):
    """Two completed halves of the original fade window; diagnostic only."""
    fade = windows[1].window
    half = (fade.start_ms + fade.end_ms) // 2
    metric = AbsorptionObservation(
        "BTCUSDT", record.signal_snapshot["identity"]["direction"], 0,
        fade.end_ms, tuple(map(D, ("91", "92", "93", "94", "95"))),
        D("100"), D(min_depth), D("80"), adverse,
        (
            RecoveryWindow(fade.start_ms, half, D("100"), D("60"), D("25")),
            RecoveryWindow(half, fade.end_ms, D("100"), D("60"),
                           D(second_recovery)),
        ),
    )
    return BoxBoundAbsorption(
        record.candidate_id, record.state_revision,
        record.snapshot_sha256, "BTCUSDT", 0, fade.end_ms, metric,
    )


def observe(record, windows, **kwargs):
    return observe_box_reversal_flow(
        record, windows, **({"decision_ms": 4000, "max_source_age_ms": 100} | kwargs))


class BoxReversalFlowResearchTests(unittest.TestCase):
    def test_mirrored_handoff_is_research_only(self):
        for direction in ("LONG", "SHORT"):
            with self.subTest(direction=direction):
                record, windows = case(direction)
                result = observe(record, windows, fixed_band=stable_band(record, windows))
                self.assertEqual(result.status, "HANDOFF_CANDIDATE")
                self.assertEqual(result.direction, direction)
                self.assertTrue(result.opposing_impact_fading)
                self.assertTrue(result.absorption_candidate)
                self.assertTrue(result.sustained_absorption_observed)
                self.assertTrue(result.initiative_flip_observed)
                self.assertFalse(result.source_complete)
                self.assertFalse(result.trading_authorized)

    def test_refill_ratio_alone_never_promotes_handoff(self):
        record, windows = case()
        result = observe(record, windows)
        self.assertEqual(result.status, "WAIT_SUSTAINED_ABSORPTION")
        self.assertTrue(result.absorption_candidate)
        self.assertFalse(result.sustained_absorption_observed)
        self.assertFalse(result.trading_authorized)

    def test_fixed_band_break_zero_depth_and_churn_do_not_promote(self):
        record, windows = case()
        for band in (
            stable_band(record, windows, adverse=True),
            stable_band(record, windows, min_depth="0"),
            stable_band(record, windows, second_recovery="0"),
        ):
            result = observe(record, windows, fixed_band=band)
            self.assertEqual(result.status, "WAIT_SUSTAINED_ABSORPTION")
            self.assertFalse(result.sustained_absorption_observed)

    def test_fixed_band_wrong_identity_time_or_future_is_rejected(self):
        record, windows = case()
        good = stable_band(record, windows)
        for bad in (
            replace(good, candidate_id="other"),
            replace(good, state_revision=4),
            replace(good, snapshot_sha256="b"*64),
            replace(good, symbol="ETHUSDT"),
            replace(good, generation=2),
            replace(good, available_at_ms=4001),
            replace(good, observation=replace(good.observation, direction="SHORT")),
            replace(good, observation=replace(good.observation, generation=2)),
            replace(good, observation=replace(good.observation, decision_ms=2999)),
            replace(good, observation=replace(good.observation,
                                            windows=(good.observation.windows[0],))),
        ):
            with self.subTest(bad=bad):
                self.assertIsNone(observe(record, windows, fixed_band=bad))

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
        result = observe(record, (a, b, no_flip),
                         fixed_band=stable_band(record, (a,b,no_flip)))
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

    def test_preapproval_flow_cannot_be_attributed_to_approved_box(self):
        # A historical Box snapshot can carry the OPEN time of its final
        # candle, earlier than the approval that created the Robot host.
        # Completed trade windows from that interval are not proof of
        # post-approval observation, even when their receipt is later.
        for direction in ("LONG", "SHORT"):
            with self.subTest(direction=direction):
                record, windows = case(direction)
                self.assertIsNotNone(observe(record, windows))
                for approved_at_ms in (1001, 2001):
                    late = NS(**(vars(record) | {"approved_at_ms": approved_at_ms}))
                    self.assertIsNone(observe(late, windows))

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



class BoxReversalHandoffPreviewTests(unittest.TestCase):
    def _case(self, direction="LONG", book=True):
        from terminal.paper.ikigai_box_plan import plan_approved_first_ikigai_box

        record, windows = case(direction, book=book)
        plan = plan_approved_first_ikigai_box(
            direction=direction, working_quantity=D("8"), frozen_f1=D("100"),
            frozen_f1618=D("92" if direction == "LONG" else "108"),
            tick_size=D("0.01"), entry_fee_rate=D("0"), target_fee_rate=D("0"),
            stop_fee_rate=D("0"),
        )
        record.signal_snapshot["identity"]["b_time_ms"] = 500
        record.signal_snapshot["plan"].update(
            environment="PAPER", execution_authorized=False,
            limit_prices=list(map(str, plan.limit_prices)),
            limit_quantities=list(map(str, plan.limit_quantities)),
            frozen_f1=str(plan.frozen_f1), frozen_f1618=str(plan.frozen_f1618),
            take_price=str(plan.take_price), stop_price=str(plan.stop_price),
        )
        record.signal_snapshot["inputs"] = dict(
            tick_size="0.01", entry_fee_rate="0.001",
            target_fee_rate="0.001", stop_fee_rate="0.001",
        )
        extreme = BoxSecondLegExtreme(
            record.candidate_id, 1, record.snapshot_sha256, "BTCUSDT", 0,
            2999, 3000, D("91.9" if direction == "LONG" else "108.1"),
        )
        return record, windows, plan, extreme

    def _preview(self, args, **overrides):
        if "fixed_band" not in overrides and args[1][1].window.book_valid:
            overrides["fixed_band"] = stable_band(args[0], args[1])
        return preview_box_reversal_handoff(*args, **(dict(
            decision_ms=4000, max_source_age_ms=100, quantity=D("2"),
            qty_step=D("1"), stop_buffer_ticks=10,
            adverse_entry_per_unit=D("0.1"), adverse_target_per_unit=D("0.1"),
            adverse_stop_per_unit=D("0.1"), additional_cost_allowance_usdt=D("0.1"),
            maximum_allowed_loss_usdt=D("3"),
        ) | overrides))

    def test_mirrored_handoff_binds_benchmark_stop_and_target(self):
        for direction, entry, stop, take in (
            ("LONG", "92.5", "91.8", "99.2"),
            ("SHORT", "107.5", "108.2", "100.8"),
        ):
            with self.subTest(direction=direction):
                args = self._case(direction)
                result = self._preview(args)
                self.assertEqual(result.status, "HYPOTHETICAL_ECONOMICS_OK")
                self.assertEqual(result.economics.assumed_entry, D(entry))
                self.assertEqual(result.economics.structural_stop, D(stop))
                self.assertEqual(result.economics.frozen_take, D(take))
                self.assertFalse(result.source_complete)
                self.assertFalse(result.trading_authorized)
                self.assertFalse(result.economics.execution_authorized)
                rejected = self._preview(args, maximum_allowed_loss_usdt=D("1"))
                self.assertEqual(rejected.status, "RISK_BUDGET_EXCEEDED")
                self.assertFalse(rejected.economics.allowed)

    def test_missing_fixed_band_has_no_hypothetical_economics(self):
        args = self._case()
        result = self._preview(args, fixed_band=None)
        self.assertEqual(result.status, "WAIT_HANDOFF")
        self.assertIsNone(result.economics)

    def test_missing_absorption_has_no_economics(self):
        result = self._preview(self._case(book=False))
        self.assertEqual(result.status, "WAIT_HANDOFF")
        self.assertIsNone(result.economics)

    def test_reject_foreign_or_future_extreme_and_unfrozen_plan(self):
        record, windows, plan, extreme = self._case()
        for bad in (
            replace(extreme, candidate_id="foreign"),
            replace(extreme, state_revision=2),
            replace(extreme, symbol="ETHUSDT"),
            replace(extreme, snapshot_sha256="b"*64),
            replace(extreme, generation=1),
            replace(extreme, available_at_ms=4001),
            replace(extreme, event_ms=499),
            replace(extreme, event_ms=4001),
            replace(extreme, price=D("92")),
        ):
            with self.subTest(bad=bad):
                self.assertIsNone(self._preview((record, windows, plan, bad)))
        for bad_plan in (
            replace(plan, take_price=D("100")),
            replace(plan, limit_quantities=(D("3"),)*4),
            replace(plan, stop_price=D("89")),
        ):
            self.assertIsNone(self._preview((record, windows, bad_plan, extreme)))
        self.assertIsNone(self._preview((record, windows, plan, extreme),
                                        decision_ms=4101))

    def test_spent_target_and_invalid_frozen_terms_return_none(self):
        record, (a,b,c), plan, extreme = self._case()
        spent = replace(c, window=replace(c.window, end_price=plan.take_price))
        self.assertIsNone(self._preview((record, (a,b,spent), plan, extreme)))
        record.signal_snapshot["inputs"]["entry_fee_rate"] = "NaN"
        self.assertIsNone(self._preview((record, (a,b,c), plan, extreme)))


if __name__ == "__main__":
    unittest.main()
