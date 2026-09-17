"""Pure safety tests for the Robot v0.1 PAPER flat-closure evidence predicate.

The positive case is the real 0GUSDT incident, distilled to the executions that
matter: one settled manual round trip, two Robot LIMIT entries, and the single
aggregate emergency SELL that flattened both.
"""

from decimal import Decimal
import unittest

from robot_flat_closure import (
    EMERGENCY_OUTCOME_CLOSED,
    EXIT_REASON_EMERGENCY_CLOSE,
    CandidateOwnership,
    prove_flat_closure,
)
from terminal.domain.models import (
    Category,
    Execution,
    ExecutionDedupKey,
    ExecutionId,
    Notional,
    OrderId,
    OrderSide,
    PositionKey,
    PositionSide,
    Price,
    Quantity,
    Symbol,
    TradingAccountId,
)
from terminal.persistence.sqlite_store import (
    PositionProjectionRecord,
    RobotTradeRecord,
)

ACCOUNT = TradingAccountId("paper")
SYMBOL = Symbol("0GUSDT")

TRADE_ID = "robot-trade-4ca4ac75045e1c25fcc023ef"
TRADE_CANDIDATE = "4ca4ac75045e1c25fcc023ef"
EMERGENCY_CANDIDATE = "a5e8157484267ae4468c5fe2"

TRADE_ORDER = "paper-limit-tw_0484879fd5ce496590f5a1c502525ab80"
EMERGENCY_ORDER = "paper-limit-tw_21681801a23f47f883602bf4ea3ea7c47"
CLOSING_ORDER = "paper-order-tw_3be8409a54774684b55c1373ca038a1ee"
MANUAL_ORDER = "paper-order-tw_d9512155b45e466d8a5f43899d9c03f06"

ENTRY_QUANTITY = Decimal("1268.3")
AVERAGE_ENTRY = Decimal("0.1965")
CLOSING_PRICE = Decimal("0.1969127050473186119873817035")
CLOSING_FEE = Decimal("0.2996223720000000000000000001")
CLOSING_QUANTITY = Decimal("2536.0")

CLOSING_AT_MS = 1789403591254
ATTEMPTED_AT_MS = 1789403589892
CLOSED_AT_MS = 1789403594827

EXPECTED_FEES = Decimal("0.1498466302869085173501577287")
EXPECTED_PNL_USDT = Decimal("0.5234338115141955835962145490")
EXPECTED_PNL_PCT = Decimal("0.1499019970942599593838546961")


def _execution(exec_id, order_id, side, price, quantity, timestamp_ms, fee="0.15"):
    return Execution(
        dedup_key=ExecutionDedupKey(ACCOUNT, Category.LINEAR, ExecutionId(exec_id)),
        order_id=OrderId(order_id),
        symbol=SYMBOL,
        side=side,
        price=Price(Decimal(price)),
        quantity=Quantity(Decimal(quantity)),
        fee=Decimal(fee),
        exchange_timestamp_ms=timestamp_ms,
    )


def _trade(**overrides):
    values = dict(
        trade_id=TRADE_ID,
        trading_account_id=ACCOUNT,
        candidate_id=TRADE_CANDIDATE,
        symbol=SYMBOL,
        direction="LONG",
        pattern="Falling Wedge",
        source_timeframe="1",
        signal_time_ms=1789398216145,
        entry_time_ms=1789400974838,
        entry_path="LIMIT",
        actual_wv=Decimal("1"),
        average_entry=AVERAGE_ENTRY,
        stop_price=Decimal("0.192570"),
        take_price=Decimal("0.203413633333333300"),
        exit_time_ms=None,
        exit_price=None,
        exit_reason=None,
        realized_pnl_usdt=None,
        realized_pnl_pct=None,
        fees_costs_usdt=None,
        version=1,
        created_at_ms=1789400974838,
        updated_at_ms=1789400974838,
        entry_quantity=ENTRY_QUANTITY,
        entry_position_version=11,
    )
    values.update(overrides)
    return RobotTradeRecord(**values)


def _position(**overrides):
    values = dict(
        position_key=PositionKey(ACCOUNT, Category.LINEAR, SYMBOL, 0),
        side=PositionSide.FLAT,
        quantity=Quantity(Decimal("0.0")),
        average_entry=None,
        realized_pnl=Decimal("48.25699999999999999999999996"),
        accumulated_fee=Decimal("2.129615928000000000000000000"),
        engaged_notional=Notional(Decimal("0")),
        sync_state="reconciliation_required",
        version=13,
        updated_at_ms=CLOSING_AT_MS,
    )
    values.update(overrides)
    return PositionProjectionRecord(**values)


def _trade_candidate(**overrides):
    values = dict(
        candidate_id=TRADE_CANDIDATE,
        status="OPEN",
        limit_order_id=TRADE_ORDER,
        emergency_attempted_at_ms=None,
        emergency_closed_at_ms=None,
        emergency_outcome=None,
        has_open_trade=True,
    )
    values.update(overrides)
    return CandidateOwnership(**values)


def _emergency_candidate(**overrides):
    values = dict(
        candidate_id=EMERGENCY_CANDIDATE,
        status="INVALIDATED",
        limit_order_id=EMERGENCY_ORDER,
        emergency_attempted_at_ms=ATTEMPTED_AT_MS,
        emergency_closed_at_ms=CLOSED_AT_MS,
        emergency_outcome=EMERGENCY_OUTCOME_CLOSED,
        has_open_trade=False,
    )
    values.update(overrides)
    return CandidateOwnership(**values)


def _settled_manual_round_trip():
    """A manual buy/sell pair that nets flat before the Robot lot opens."""

    return [
        _execution(
            "paper-exec-manual-buy", MANUAL_ORDER, OrderSide.BUY,
            "0.1867", "1339.8", 1788157067487,
        ),
        _execution(
            "paper-stop-exec-manual-sell", "paper-stop-order-796399f4", OrderSide.SELL,
            "0.1950275638154948499776085983", "1339.8", 1788158306687,
        ),
    ]


def _robot_entries():
    return [
        _execution(
            "paper-limit-961f9d95", TRADE_ORDER, OrderSide.BUY,
            "0.1965", "1268.3", 1789400971937,
        ),
        _execution(
            "paper-limit-80619678", EMERGENCY_ORDER, OrderSide.BUY,
            "0.1971", "1267.7", 1789403587548,
        ),
    ]


def _closing(**overrides):
    values = dict(
        exec_id="paper-exec-tw_3be8409a",
        order_id=CLOSING_ORDER,
        side=OrderSide.SELL,
        price=str(CLOSING_PRICE),
        quantity=str(CLOSING_QUANTITY),
        timestamp_ms=CLOSING_AT_MS,
        fee=str(CLOSING_FEE),
    )
    values.update(overrides)
    return _execution(**values)


def _executions():
    return [*_settled_manual_round_trip(), *_robot_entries(), _closing()]


def _prove(**overrides):
    values = dict(
        trade=_trade(),
        position=_position(),
        executions=_executions(),
        candidates=[_trade_candidate(), _emergency_candidate()],
        open_trade_candidate_ids=frozenset({TRADE_CANDIDATE}),
        has_unresolved_obligation=False,
    )
    values.update(overrides)
    return prove_flat_closure(**values)


class ProveFlatClosurePositiveTests(unittest.TestCase):
    def test_zero_g_incident_produces_exact_evidence(self):
        evidence = _prove()

        self.assertIsNotNone(evidence)
        self.assertEqual(evidence.trade_id, TRADE_ID)
        self.assertEqual(evidence.candidate_id, TRADE_CANDIDATE)
        self.assertEqual(evidence.closing_exec_id, "paper-exec-tw_3be8409a")
        self.assertEqual(evidence.closing_order_id, CLOSING_ORDER)
        self.assertEqual(evidence.closing_quantity, CLOSING_QUANTITY)
        self.assertEqual(evidence.exit_time_ms, CLOSING_AT_MS)
        self.assertEqual(evidence.exit_price, CLOSING_PRICE)
        self.assertEqual(evidence.exit_reason, EXIT_REASON_EMERGENCY_CLOSE)
        self.assertEqual(evidence.fees_costs_usdt, EXPECTED_FEES)
        self.assertEqual(evidence.realized_pnl_usdt, EXPECTED_PNL_USDT)
        self.assertEqual(evidence.realized_pnl_pct, EXPECTED_PNL_PCT)

    def test_open_lot_and_emergency_attribution_are_reported(self):
        evidence = _prove()

        self.assertEqual(
            [(item.candidate_id, item.quantity) for item in evidence.open_lot],
            [(TRADE_CANDIDATE, Decimal("1268.3")),
             (EMERGENCY_CANDIDATE, Decimal("1267.7"))],
        )
        self.assertEqual(evidence.emergency.candidate_id, EMERGENCY_CANDIDATE)
        self.assertEqual(evidence.emergency.attempted_at_ms, ATTEMPTED_AT_MS)
        self.assertEqual(evidence.emergency.closed_at_ms, CLOSED_AT_MS)
        self.assertEqual(evidence.emergency.outcome, EMERGENCY_OUTCOME_CLOSED)
        self.assertEqual(evidence.emergency.lot_quantity, Decimal("1267.7"))

    def test_partial_fills_aggregate_to_the_attested_entry_quantity(self):
        partials = [
            _execution("paper-limit-part-1", TRADE_ORDER, OrderSide.BUY,
                       "0.1965", "700.0", 1789400971937),
            _execution("paper-limit-part-2", TRADE_ORDER, OrderSide.BUY,
                       "0.1965", "568.3", 1789400971938),
            _execution("paper-limit-part-3", EMERGENCY_ORDER, OrderSide.BUY,
                       "0.1971", "600.0", 1789403587548),
            _execution("paper-limit-part-4", EMERGENCY_ORDER, OrderSide.BUY,
                       "0.1971", "667.7", 1789403587549),
        ]
        executions = [*_settled_manual_round_trip(), *partials, _closing()]

        evidence = _prove(executions=executions)

        self.assertIsNotNone(evidence)
        self.assertEqual(len(evidence.open_lot), 4)
        self.assertEqual(evidence.realized_pnl_usdt, EXPECTED_PNL_USDT)
        self.assertEqual(evidence.emergency.lot_quantity, Decimal("1267.7"))

    def test_short_mirror_reverses_sides_and_pnl_sign(self):
        trade = _trade(direction="SHORT")
        executions = [
            _execution("paper-exec-manual-sell", MANUAL_ORDER, OrderSide.SELL,
                       "0.1867", "1339.8", 1788157067487),
            _execution("paper-exec-manual-buy", "paper-stop-order-796399f4", OrderSide.BUY,
                       "0.1950275638154948499776085983", "1339.8", 1788158306687),
            _execution("paper-limit-961f9d95", TRADE_ORDER, OrderSide.SELL,
                       "0.1965", "1268.3", 1789400971937),
            _execution("paper-limit-80619678", EMERGENCY_ORDER, OrderSide.SELL,
                       "0.1971", "1267.7", 1789403587548),
            _closing(side=OrderSide.BUY),
        ]

        evidence = _prove(trade=trade, executions=executions)

        self.assertIsNotNone(evidence)
        self.assertEqual(evidence.fees_costs_usdt, EXPECTED_FEES)
        self.assertEqual(evidence.realized_pnl_usdt, -EXPECTED_PNL_USDT)
        self.assertEqual(
            evidence.realized_pnl_pct,
            (-EXPECTED_PNL_USDT - EXPECTED_FEES) / (ENTRY_QUANTITY * AVERAGE_ENTRY) * 100,
        )


class ProveFlatClosureFailClosedTests(unittest.TestCase):
    def test_missing_wrong_or_multiple_emergency_marker_fails_closed(self):
        cases = {
            "no marker at all": [
                _trade_candidate(),
                _emergency_candidate(
                    emergency_attempted_at_ms=None,
                    emergency_closed_at_ms=None,
                    emergency_outcome=None,
                ),
            ],
            "partially written marker": [
                _trade_candidate(),
                _emergency_candidate(emergency_closed_at_ms=None),
            ],
            "foreign outcome": [
                _trade_candidate(),
                _emergency_candidate(emergency_outcome="CLOSED_BY_SOMETHING_ELSE"),
            ],
            "two marked candidates": [
                _trade_candidate(
                    emergency_attempted_at_ms=ATTEMPTED_AT_MS,
                    emergency_closed_at_ms=CLOSED_AT_MS,
                    emergency_outcome=EMERGENCY_OUTCOME_CLOSED,
                ),
                _emergency_candidate(),
            ],
            "marker on the stale trade's own candidate": [
                _trade_candidate(
                    emergency_attempted_at_ms=ATTEMPTED_AT_MS,
                    emergency_closed_at_ms=CLOSED_AT_MS,
                    emergency_outcome=EMERGENCY_OUTCOME_CLOSED,
                ),
                _emergency_candidate(
                    emergency_attempted_at_ms=None,
                    emergency_closed_at_ms=None,
                    emergency_outcome=None,
                ),
            ],
            "marker candidate not INVALIDATED": [
                _trade_candidate(),
                _emergency_candidate(status="CLOSED"),
            ],
        }
        for name, candidates in cases.items():
            with self.subTest(name):
                self.assertIsNone(_prove(candidates=candidates))

    def test_closing_outside_the_emergency_timestamp_envelope_fails_closed(self):
        cases = {
            "marker closes before it was attempted": _emergency_candidate(
                emergency_attempted_at_ms=CLOSED_AT_MS + 1,
            ),
            "closing execution precedes the attempt": _emergency_candidate(
                emergency_attempted_at_ms=CLOSING_AT_MS + 1,
                emergency_closed_at_ms=CLOSING_AT_MS + 2,
            ),
            "closing execution follows the close": _emergency_candidate(
                emergency_attempted_at_ms=CLOSING_AT_MS - 2,
                emergency_closed_at_ms=CLOSING_AT_MS - 1,
            ),
        }
        for name, candidate in cases.items():
            with self.subTest(name):
                self.assertIsNone(_prove(candidates=[_trade_candidate(), candidate]))

    def test_emergency_candidate_fill_outside_the_lot_fails_closed(self):
        # The emergency marker sits on a third candidate whose own entry is not
        # part of the reconstructed open lot.
        bystander = CandidateOwnership(
            candidate_id="bystander-candidate",
            status="INVALIDATED",
            limit_order_id=EMERGENCY_ORDER,
            emergency_attempted_at_ms=None,
            emergency_closed_at_ms=None,
            emergency_outcome=None,
            has_open_trade=False,
        )
        elsewhere = _emergency_candidate(
            limit_order_id="paper-limit-tw_not_in_this_lot",
        )

        self.assertIsNone(
            _prove(candidates=[_trade_candidate(), bystander, elsewhere])
        )

    def test_unattributed_manual_contribution_fails_closed(self):
        manual_top_up = _execution(
            "paper-exec-manual-topup", "paper-order-tw_manual_market", OrderSide.BUY,
            "0.1968", "1267.7", 1789403587548,
        )
        executions = [
            *_settled_manual_round_trip(),
            _robot_entries()[0],
            manual_top_up,
            _closing(),
        ]

        self.assertIsNone(_prove(executions=executions))

    def test_ambiguous_lot_shape_fails_closed(self):
        intermediate_exit = [
            *_settled_manual_round_trip(),
            *_robot_entries(),
            _execution("paper-exec-partial-exit", "paper-order-tw_partial", OrderSide.SELL,
                       "0.1970", "500.0", 1789403590000),
            _closing(quantity="2036.0"),
        ]
        quantity_mismatch = [
            *_settled_manual_round_trip(),
            *_robot_entries(),
            _closing(quantity="2500.0"),
        ]

        with self.subTest("intermediate closing-side execution"):
            self.assertIsNone(_prove(executions=intermediate_exit))
        with self.subTest("closing quantity does not match the lot"):
            self.assertIsNone(_prove(executions=quantity_mismatch))
        with self.subTest("trade fills do not aggregate to entry_quantity"):
            self.assertIsNone(_prove(trade=_trade(entry_quantity=Decimal("1000.0"))))

    def test_competing_or_inconsistent_ownership_fails_closed(self):
        with self.subTest("a second Robot trade is still open on the symbol"):
            self.assertIsNone(_prove(
                candidates=[_trade_candidate(),
                            _emergency_candidate(has_open_trade=True)],
                open_trade_candidate_ids=frozenset(
                    {TRADE_CANDIDATE, EMERGENCY_CANDIDATE}
                ),
            ))
        with self.subTest("caller ownership views disagree"):
            self.assertIsNone(_prove(
                candidates=[_trade_candidate(),
                            _emergency_candidate(has_open_trade=True)],
            ))
        with self.subTest("one entry order claimed by two candidates"):
            self.assertIsNone(_prove(candidates=[
                _trade_candidate(),
                _emergency_candidate(),
                CandidateOwnership(
                    candidate_id="duplicate-owner",
                    status="EXPIRED",
                    limit_order_id=TRADE_ORDER,
                    emergency_attempted_at_ms=None,
                    emergency_closed_at_ms=None,
                    emergency_outcome=None,
                    has_open_trade=False,
                ),
            ]))

    def test_position_and_obligation_preconditions_fail_closed(self):
        cases = {
            "position still open": dict(position=_position(
                side=PositionSide.LONG, quantity=Quantity(Decimal("1268.3")),
            )),
            "position not bound to the closing execution": dict(
                position=_position(updated_at_ms=CLOSING_AT_MS - 1),
            ),
            "position version did not advance": dict(position=_position(version=11)),
            "missing position projection": dict(position=None),
            "unresolved protection obligation": dict(has_unresolved_obligation=True),
            "trade lacks the ownership attestation": dict(
                trade=_trade(entry_quantity=None),
            ),
            "trade already terminalized": dict(
                trade=_trade(exit_time_ms=CLOSING_AT_MS, exit_price=CLOSING_PRICE,
                             exit_reason=EXIT_REASON_EMERGENCY_CLOSE,
                             realized_pnl_usdt=EXPECTED_PNL_USDT,
                             realized_pnl_pct=EXPECTED_PNL_PCT),
            ),
        }
        for name, overrides in cases.items():
            with self.subTest(name):
                self.assertIsNone(_prove(**overrides))


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
