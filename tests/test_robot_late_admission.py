import unittest
from decimal import Decimal

import robot_state_machine
from terminal.application.robot_admission_catchup import LATE_ADMISSION_MARKET
from terminal.application.robot_late_admission import (
    DECISION_APEX_REACHED,
    DECISION_BLOCKED_ADMISSION,
    DECISION_BLOCKED_BOOK_STALE,
    DECISION_BLOCKED_BOOK_UNAVAILABLE,
    DECISION_BLOCKED_INSUFFICIENT_LIQUIDITY,
    DECISION_BLOCKED_OWNERSHIP,
    DECISION_MARKET_ENTRY,
    DECISION_SKIPPED_EXCESS_SLIPPAGE,
    DECISION_SKIPPED_LOW_REWARD,
    DECISION_SKIPPED_POOR_RR,
    DECISION_SKIPPED_STOP_BEYOND_LIMIT,
    RobotLateAdmissionError,
    evaluate_late_admission,
)
from terminal.domain.models import OrderSide, Price, Quantity, Symbol
from terminal.market_data.models import BookHealth, NormalizedOrderBook, PriceLevel
from terminal.paper.matching import match_market_order


SYMBOL = Symbol("TESTUSDT")


def _snapshot(*, pattern="Falling Wedge", apex_index=130):
    return {
        "symbol": SYMBOL.value,
        "pattern": pattern,
        "geometry": {
            "upper_line": {"slope": -1.0, "intercept": 200.0},
            "lower_line": {"slope": -0.5, "intercept": 145.0},
            "apex": {"index": apex_index, "price": 90.0, "valid_intersection": True},
            "current_index": 100,
        },
    }


def _state(*, direction=robot_state_machine.DIRECTION_LONG):
    return {
        "state_version": robot_state_machine.STATE_VERSION,
        "phase": robot_state_machine.PHASE_RETEST_DETECTED,
        "pattern": "Falling Wedge" if direction == robot_state_machine.DIRECTION_LONG else "Rising Wedge",
        "direction": direction,
        "geometry_cursor": 103,
        "breakout_index": 102,
        "retest_index": 103,
        "last_event": robot_state_machine.EVENT_RETEST,
        "execution": {"entry_mode": LATE_ADMISSION_MARKET},
    }


def _levels(items):
    return tuple(
        PriceLevel(Price(Decimal(str(price))), Quantity(Decimal(str(quantity))))
        for price, quantity in items
    )


def _book(*, bids=((99, 10),), asks=((100, 10),), health=BookHealth.READY, received_at_ms=1_000):
    return NormalizedOrderBook(
        symbol=SYMBOL,
        bids=_levels(bids),
        asks=_levels(asks),
        health=health,
        received_at_ms=received_at_ms,
        available_depth=max(len(bids), len(asks)),
    )


def _evaluate(
    *,
    snapshot=None,
    state=None,
    book=None,
    quantity=Decimal("1"),
    current_geometry_index=104,
    now_ms=1_500,
    max_book_age_ms=1_000,
    structural_extreme=Decimal("98.6"),  # STOP 98.5: exactly 1.5% below the 100 VWAP
    tick_size=Decimal("0.1"),
    frozen_signal_reference_price=Decimal("94"),
    frozen_scanner_target_price=Decimal("104"),
    admission_ready=True,
    ownership_clear=True,
):
    return evaluate_late_admission(
        snapshot or _snapshot(),
        state or _state(),
        _book() if book is None else book,
        quantity=Quantity(quantity),
        current_geometry_index=current_geometry_index,
        now_ms=now_ms,
        max_book_age_ms=max_book_age_ms,
        structural_extreme=structural_extreme,
        tick_size=tick_size,
        frozen_signal_reference_price=frozen_signal_reference_price,
        frozen_scanner_target_price=frozen_scanner_target_price,
        admission_ready=admission_ready,
        ownership_clear=ownership_clear,
    )


class RobotLateAdmissionTests(unittest.TestCase):
    # RR boundary: structural STOP 99.0 (1% risk), take 97 + 0.9 * 5 = 101.5.
    def test_rr_exactly_one_point_five_is_viable(self):
        decision = _evaluate(
            structural_extreme=Decimal("99.1"),
            frozen_signal_reference_price=Decimal("97"),
            frozen_scanner_target_price=Decimal("102"),
        )

        self.assertEqual(decision.action, DECISION_MARKET_ENTRY)
        self.assertEqual(decision.projected_vwap, Decimal("100"))
        self.assertEqual(decision.stop_price, Decimal("99.0"))
        self.assertEqual(decision.take_price, Decimal("101.5"))
        self.assertEqual(decision.expected_reward, Decimal("0.015"))
        self.assertEqual(decision.rr, Decimal("1.5"))

    def test_rr_below_one_point_five_is_blocked(self):
        decision = _evaluate(
            book=_book(asks=((Decimal("100.1"), 10),)),
            structural_extreme=Decimal("99.1"),
            frozen_signal_reference_price=Decimal("97"),
            frozen_scanner_target_price=Decimal("102"),
        )

        self.assertEqual(decision.action, DECISION_SKIPPED_POOR_RR)
        self.assertLess(decision.rr, Decimal("1.5"))

    def test_structural_stop_at_limit_is_viable_and_beyond_is_skipped(self):
        at_limit = _evaluate()  # STOP 98.5, exactly 1.5%
        self.assertEqual(at_limit.action, DECISION_MARKET_ENTRY)
        self.assertEqual(at_limit.stop_price, Decimal("98.5"))
        self.assertEqual(at_limit.rr, Decimal("2"))

        for extreme in (Decimal("98.5"), Decimal("90"), Decimal("100.5")):
            with self.subTest(structural_extreme=extreme):
                # 98.4 (1.6%), 89.9 (far) and 100.4 (wrong side): no Market
                # entry, and no fallback STOP is offered for a new entry.
                decision = _evaluate(structural_extreme=extreme)
                self.assertEqual(decision.action, DECISION_SKIPPED_STOP_BEYOND_LIMIT)
                self.assertEqual(decision.projected_vwap, Decimal("100"))
                self.assertIsNone(decision.stop_price)
                self.assertIsNone(decision.rr)

    def test_expected_reward_exactly_one_percent_is_viable(self):
        decision = _evaluate(
            structural_extreme=Decimal("99.5"),
            frozen_signal_reference_price=Decimal("92"),
            frozen_scanner_target_price=Decimal("102"),
        )

        self.assertEqual(decision.action, DECISION_MARKET_ENTRY)
        self.assertEqual(decision.take_price, Decimal("101.0"))
        self.assertEqual(decision.expected_reward, Decimal("0.01"))
        self.assertGreater(decision.rr, Decimal("1.5"))

    def test_expected_reward_below_one_percent_is_blocked(self):
        decision = _evaluate(
            book=_book(asks=((Decimal("100.01"), 10),)),
            structural_extreme=Decimal("99.5"),
            frozen_signal_reference_price=Decimal("92"),
            frozen_scanner_target_price=Decimal("102"),
        )

        self.assertEqual(decision.action, DECISION_SKIPPED_LOW_REWARD)
        self.assertLess(decision.expected_reward, Decimal("0.01"))
        self.assertGreaterEqual(decision.rr, Decimal("1.5"))

    def test_adverse_slippage_exactly_half_percent_is_viable(self):
        book = _book(asks=((100, 1), (101, 1)))
        decision = _evaluate(
            book=book,
            quantity=Decimal("2"),
            structural_extreme=Decimal("100"),
            frozen_signal_reference_price=Decimal("100"),
            frozen_scanner_target_price=Decimal("110"),
        )

        self.assertEqual(decision.action, DECISION_MARKET_ENTRY)
        self.assertEqual(decision.projected_vwap, Decimal("100.5"))
        self.assertEqual(decision.best_price, Decimal("100"))
        self.assertEqual(decision.adverse_slippage, Decimal("0.005"))

    def test_adverse_slippage_above_half_percent_is_blocked(self):
        decision = _evaluate(
            book=_book(asks=((100, 1), (Decimal("101.02"), 1))),
            quantity=Decimal("2"),
            structural_extreme=Decimal("100"),
            frozen_signal_reference_price=Decimal("100"),
            frozen_scanner_target_price=Decimal("110"),
        )

        self.assertEqual(decision.action, DECISION_SKIPPED_EXCESS_SLIPPAGE)
        self.assertGreater(decision.adverse_slippage, Decimal("0.005"))

    def test_projected_vwap_is_exactly_shared_paper_matcher_vwap(self):
        book = _book(asks=((100, 1), (101, 2)))
        quantity = Quantity(Decimal("2"))
        expected = match_market_order(book, side=OrderSide.BUY, quantity=quantity)

        decision = evaluate_late_admission(
            _snapshot(), _state(), book,
            quantity=quantity,
            current_geometry_index=104,
            now_ms=1_500,
            max_book_age_ms=1_000,
            structural_extreme=Decimal("100"),
            tick_size=Decimal("0.1"),
            frozen_signal_reference_price=Decimal("100"),
            frozen_scanner_target_price=Decimal("110"),
            admission_ready=True,
            ownership_clear=True,
        )

        self.assertEqual(decision.projected_vwap, expected.vwap.value)

    def test_apex_admission_and_ownership_gates_fail_closed_before_market_preview(self):
        self.assertEqual(
            _evaluate(admission_ready=False).action,
            DECISION_BLOCKED_ADMISSION,
        )
        self.assertEqual(
            _evaluate(ownership_clear=False).action,
            DECISION_BLOCKED_OWNERSHIP,
        )
        self.assertEqual(
            _evaluate(current_geometry_index=130).action,
            DECISION_APEX_REACHED,
        )

    def test_book_health_and_freshness_fail_closed_with_executor_age_semantics(self):
        self.assertEqual(
            _evaluate(book=_book(health=BookHealth.DEGRADED)).action,
            DECISION_BLOCKED_BOOK_UNAVAILABLE,
        )
        accepted = _evaluate(book=_book(received_at_ms=1_000), now_ms=2_000, max_book_age_ms=1_000)
        self.assertEqual(accepted.action, DECISION_MARKET_ENTRY)
        self.assertEqual(
            _evaluate(book=_book(received_at_ms=999), now_ms=2_000, max_book_age_ms=1_000).action,
            DECISION_BLOCKED_BOOK_STALE,
        )
        self.assertEqual(
            _evaluate(book=_book(received_at_ms=2_001), now_ms=2_000, max_book_age_ms=1_000).action,
            DECISION_BLOCKED_BOOK_STALE,
        )

    def test_insufficient_depth_fails_closed(self):
        decision = _evaluate(book=_book(asks=((100, Decimal("0.5")),)))

        self.assertEqual(decision.action, DECISION_BLOCKED_INSUFFICIENT_LIQUIDITY)
        self.assertIsNone(decision.projected_vwap)

    def test_short_uses_bids_and_short_protection_math(self):
        snapshot = _snapshot(pattern="Rising Wedge")
        state = _state(direction=robot_state_machine.DIRECTION_SHORT)
        decision = _evaluate(
            snapshot=snapshot,
            state=state,
            book=_book(bids=((100, 10),), asks=((101, 10),)),
            structural_extreme=Decimal("100.9"),
            frozen_signal_reference_price=Decimal("103"),
            frozen_scanner_target_price=Decimal("98"),
        )

        self.assertEqual(decision.action, DECISION_MARKET_ENTRY)
        self.assertEqual(decision.best_price, Decimal("100"))
        self.assertEqual(decision.projected_vwap, Decimal("100"))
        self.assertEqual(decision.stop_price, Decimal("101.0"))
        self.assertEqual(decision.take_price, Decimal("98.5"))
        self.assertEqual(decision.rr, Decimal("1.5"))

    def test_short_structural_stop_beyond_limit_is_skipped(self):
        snapshot = _snapshot(pattern="Rising Wedge")
        state = _state(direction=robot_state_machine.DIRECTION_SHORT)
        for extreme, expected in (
            (Decimal("101.4"), DECISION_MARKET_ENTRY),               # STOP 101.5 (1.5%)
            (Decimal("101.5"), DECISION_SKIPPED_STOP_BEYOND_LIMIT),  # STOP 101.6
        ):
            with self.subTest(structural_extreme=extreme):
                decision = _evaluate(
                    snapshot=snapshot,
                    state=state,
                    book=_book(bids=((100, 10),), asks=((101, 10),)),
                    structural_extreme=extreme,
                    frozen_signal_reference_price=Decimal("106"),
                    frozen_scanner_target_price=Decimal("96"),
                )
                self.assertEqual(decision.action, expected)

    def test_only_catchup_marked_retest_is_accepted(self):
        ordinary = _state()
        ordinary["execution"] = {}

        with self.assertRaises(RobotLateAdmissionError):
            _evaluate(state=ordinary)


if __name__ == "__main__":
    unittest.main()
