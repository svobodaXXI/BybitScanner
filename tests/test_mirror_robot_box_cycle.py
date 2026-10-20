"""MIRROR RETEST inside the existing PAPER Robot: full Box trade cycle on a real SQLiteStore.

Campaign: a Wedge lower line at 110 is broken DOWN by a naked candle -> LONG campaign back to 110.
Attempt: an IKIGAI_BOX LONG (P1 94 .. P4 91.6, TAKE 99.2, STOP 89.6) entered while the campaign is active.
Expected: 25 % of the filled slot exits at the Box TAKE, the remainder STOP moves to net break-even, the remainder is
closed by a Box-owned EXIT MARKET at the proven retest, the trade closes as MIRROR_RETEST with the whole-trade Net PnL.
Fake executor/market only: no network, no runtime, no PAPER DB outside a temp dir.
"""

from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace
import tempfile
import unittest

import mirror_retest_robot as mirror
from geometry.naked_retest import PHASE_CAMPAIGN_ACTIVE, PHASE_RETEST_PROVEN
from scanner_geometry_cursor import build_scanner_geometry_cursor_anchor
from terminal.api.models import CommandResult, CommandResultStatus
from terminal.application.robot_breakout_monitor import RobotBreakoutMonitor
from terminal.domain.models import (
    Category, Execution, ExecutionDedupKey, ExecutionId, Notional, OrderId, OrderSide, PositionKey,
    PositionSide, Price, Quantity, Symbol,
)
from terminal.market_data.models import BookHealth, NormalizedOrderBook, PriceLevel
from terminal.persistence.sqlite_store import PositionProjectionUpdate, SQLiteStore
from tests.test_box_plan_persistence import snapshot as box_snapshot
from tests.test_robot_breakout_monitor import ACCOUNT_ID, SYMBOL, _Clock, _FakeActionExecutor, _ScriptedCandleFeed

FIVE, ONE = 300_000, 60_000
WEDGE_AS_OF = 1_000_000
BREAKOUT_OPEN = 1_500_000
NOW = 3_000_000
KEY = PositionKey(ACCOUNT_ID, Category.LINEAR, Symbol(SYMBOL), 0)


def book(price):
    value = Decimal(str(price))
    return NormalizedOrderBook(
        symbol=Symbol(SYMBOL),
        bids=(PriceLevel(Price(value - Decimal("0.1")), Quantity(Decimal("100"))),),
        asks=(PriceLevel(Price(value), Quantity(Decimal("100"))),),
        health=BookHealth.READY, received_at_ms=4_000, available_depth=1)


def candle(open_ms, o, h, low, c):
    return {"open_time_ms": open_ms, "close_time_ms": open_ms + FIVE, "open": o, "high": h, "low": low, "close": c,
            "closed": True}


def wedge_snapshot(level=110.0):
    line_low = {"slope": 0.0, "intercept": level}
    line_high = {"slope": 0.0, "intercept": level + 20}
    return {
        "pattern": "Falling Wedge", "symbol": SYMBOL, "timeframe": "5", "scanner_formation_id": "f-mirror",
        "robot_geometry": {"robot_coordinate_timeframe": "1", "upper_line": line_high, "lower_line": line_low},
        "scanner_geometry_cursor": build_scanner_geometry_cursor_anchor(
            geometry_index=0, source_candle_time_ms=WEDGE_AS_OF, timeframe="1"),
    }


class Candles:
    """``BybitClosedKlineSource``-like: closed 5m candles up to ``now`` and complete 1m proof on request."""

    def __init__(self):
        self.coarse = [candle(1_200_000, 112, 113, 111, 112),
                       candle(BREAKOUT_OPEN, 111, 111.5, 104, 105)]          # naked DOWN through 110
        t = BREAKOUT_OPEN + FIVE
        while t + FIVE <= NOW:
            self.coarse.append(candle(t, 100, 101, 99, 100))
            t += FIVE
        self.now = NOW
        self.fine_calls = 0

    def closed_candles(self, candidate_id, symbol, after_close_ms):
        return [c for c in self.coarse if c["close_time_ms"] > after_close_ms and c["close_time_ms"] <= self.now]

    def fine_candles(self, symbol, coarse):
        self.fine_calls += 1
        return [candle(coarse["open_time_ms"] + i * ONE, coarse["open"], coarse["high"], coarse["low"],
                       coarse["close"]) | {"close_time_ms": coarse["open_time_ms"] + (i + 1) * ONE}
                for i in range(5)]

    def add(self, o, h, low, c):
        t = self.coarse[-1]["close_time_ms"]
        self.coarse.append(candle(t, o, h, low, c))
        self.now = t + FIVE


class MirrorBoxCycleTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.db = Path(self.tmp.name) / "paper.sqlite3"
        self.store = SQLiteStore.open(self.db)
        self.addCleanup(self.store.close)
        self.store.initialize_robot_runtime_state(ACCOUNT_ID, updated_at_ms=1)
        self.store.update_robot_runtime_state(ACCOUNT_ID, mode="ROBOT_RUNNING", recovery_status="READY",
                                              reason=None, expected_version=1, updated_at_ms=1)
        self.clock = _Clock(NOW)
        self.executor = _FakeActionExecutor(self.store, ACCOUNT_ID, self.clock)
        self.candles = Candles()
        self.risk_limit = Decimal("1000")
        self.book = book("93.5")
        self.market_submissions = []
        self.fail_next_submit = False

    # --- harness -----------------------------------------------------------------------------------

    def policy(self):
        return mirror.MirrorRobotPolicy(candles=self.candles, account_risk_limit_usdt=lambda now: self.risk_limit,
                                        quantity_step=lambda symbol: Decimal("0.1"))

    def monitor(self, *, with_policy=True):
        monitor = RobotBreakoutMonitor(
            lambda: SQLiteStore.open(self.db), ACCOUNT_ID, get_closed_candle=_ScriptedCandleFeed(),
            action_executor=self.executor, tick_size_provider=lambda symbol: Decimal("0.01"),
            clock_ms=self.clock, arm_entry_coverage=lambda symbol: True, release_entry_coverage=lambda s: None,
            incident_dir=Path(self.tmp.name) / "incidents", mirror_policy=self.policy() if with_policy else None)
        monitor._get_market_book = lambda symbol: self.book
        monitor._market_preflight = lambda request, identity: SimpleNamespace(
            admitted=True, normalized_quantity=request.volume.amount / request.sizing_reference_price)
        monitor._submit_market = self.submit_market
        self.addCleanup(monitor.close)
        return monitor

    def submit_market(self, request, identity):
        if self.fail_next_submit:
            self.fail_next_submit = False
            raise RuntimeError("simulated crash before the market reached the engine")
        if identity.command_id.value not in {c for c, _ in self.market_submissions}:
            self.market_submissions.append((identity.command_id.value, request.side))
            quantity = request.volume.amount / request.sizing_reference_price
            self.fill(OrderId(f"paper-order-{identity.order_link_id}"), request.side, quantity,
                      request.sizing_reference_price)
        return CommandResult(request.client_action_id.value, CommandResultStatus.COMPLETED, "completed", "filled")

    def fill(self, order_id, side, quantity, price, *, resting=False):
        """Apply one fill with correct increase/reduce position economics (fee 0, like the shared fake)."""
        current = self.store.get_position_projection(KEY)
        qty = current.quantity.value if current else Decimal(0)
        avg = current.average_entry.value if current and current.average_entry else None
        realized = current.realized_pnl if current else Decimal(0)
        increasing = qty == 0 or (side == OrderSide.BUY) == (current.side == PositionSide.LONG)
        if increasing:
            new_qty = qty + quantity
            new_avg = ((avg or Decimal(0)) * qty + price * quantity) / new_qty
            new_side = PositionSide.LONG if side == OrderSide.BUY else PositionSide.SHORT
        else:
            sign = Decimal(1) if current.side == PositionSide.LONG else Decimal(-1)
            realized = realized + (price - avg) * quantity * sign
            new_qty = qty - quantity
            new_avg = avg if new_qty else None
            new_side = current.side if new_qty else PositionSide.FLAT
        self.executor._exec_counter += 1
        execution = Execution(ExecutionDedupKey(ACCOUNT_ID, Category.LINEAR, ExecutionId(f"x{self.executor._exec_counter}")),
                              order_id, Symbol(SYMBOL), side, Price(price), Quantity(quantity), Decimal("0"), self.clock())
        update = PositionProjectionUpdate(
            KEY, new_side, Quantity(new_qty), Price(new_avg) if new_avg is not None else None, realized, Decimal("0"),
            Notional(new_qty * new_avg if new_avg is not None else Decimal(0)), "synced",
            current.version if current else None, self.clock())
        if resting:
            self.store.apply_paper_limit_execution_once(order_id, execution, update, updated_at_ms=self.clock())
        else:
            self.store.apply_execution_once(execution, update)

    def add_wedge(self, level=110.0):
        wedge = self.store.create_robot_candidate(
            candidate_id="wedge-1", trading_account_id=ACCOUNT_ID, symbol=Symbol(SYMBOL), status="APPROVED",
            signal_snapshot=wedge_snapshot(level), approved_at_ms=WEDGE_AS_OF, updated_at_ms=WEDGE_AS_OF)
        wedge = wedge[0] if isinstance(wedge, tuple) else wedge
        self.store.save_robot_candidate_state(wedge.candidate_id, status="EXPIRED", robot_state={"phase": "DONE"},
                                              expected_revision=wedge.state_revision, updated_at_ms=WEDGE_AS_OF + 1)

    def add_box(self):
        data = box_snapshot()
        data["identity"]["symbol"] = SYMBOL
        source, _ = self.store.save_box_plan_only(snapshot=data, created_at_ms=3001)
        candidate, _ = self.store.handoff_box_plan_to_robot(
            source.candidate_id, symbol=source.symbol, expected_snapshot_sha256=source.snapshot_sha256,
            approved_at_ms=3002)
        return source, candidate

    def execution(self, candidate):
        return self.store.get_robot_candidate(candidate.candidate_id).robot_state.get("execution") or {}

    def owned(self, source, role, slot):
        return next((o for o in self.store.load_box_order_ownership(source.candidate_id)
                     if o.role == role and o.slot == slot), None)

    def open_first_slot(self, monitor, candidate):
        """attach -> catch-up plan -> ownership -> P1 MARKET fill + STOP + EXIT."""
        for _ in range(4):
            self.assertEqual(monitor.tick(), (candidate.candidate_id,))

    # --- the full cycle --------------------------------------------------------------------------

    def test_full_mirror_cycle_partial_take_break_even_retest_close_and_net_pnl(self):
        self.add_wedge()
        source, candidate = self.add_box()
        monitor = self.monitor()

        self.assertEqual(monitor.tick(), (candidate.candidate_id,))           # attach decision only
        attached = self.execution(candidate)["mirror"]
        self.assertEqual(attached["decision"], mirror.ATTACHED, attached)
        self.assertEqual(attached["campaign_direction"], "LONG")
        self.assertEqual(attached["state"]["phase"], PHASE_CAMPAIGN_ACTIVE)
        self.assertEqual(attached["partial_quantities"], ["0.5"] * 4)
        self.assertEqual(Decimal(attached["r0_usdt"]), Decimal("57.51976"))   # min(1000, 0.5 x 115.03952)
        self.assertIsNone(self.store.get_robot_trade(f"robot-trade-{candidate.candidate_id}"))

        for _ in range(3):                                                    # plan, ownership, P1 MARKET
            self.assertEqual(monitor.tick(), (candidate.candidate_id,))
        trade = self.store.get_robot_trade(f"robot-trade-{candidate.candidate_id}")
        self.assertEqual((trade.entry_quantity, trade.average_entry), (Decimal("2"), Decimal("93.5")))
        partial_exit = self.owned(source, "EXIT", 1)
        order = self.store.get_paper_limit(partial_exit.order_id.value, ACCOUNT_ID)
        self.assertEqual((order.price, order.quantity, order.side), (Decimal("99.2"), Decimal("0.5"), OrderSide.SELL))
        self.assertTrue(partial_exit.order_id.value.startswith("paper-box-mirror-exit-"))
        stop0 = self.store.get_protection_projection(KEY).stop_loss
        self.assertEqual(stop0, Decimal("90.65"))

        # 25 % at the Box TAKE fills; price now near the TAKE.
        self.book = book("99")
        self.fill(partial_exit.order_id, OrderSide.SELL, Decimal("0.5"), Decimal("99.2"), resting=True)
        monitor.process_authoritative_fill(SYMBOL)
        be = self.store.get_protection_projection(KEY).stop_loss
        self.assertEqual(be, Decimal("92.15"))                                 # whole-trade net >= 0 incl. fees/slippage
        self.assertEqual(self.execution(candidate)["mirror"]["be_stop"], "92.15")
        for slot in (2, 3, 4):                                                 # setup realized: no new entries
            entry = self.owned(source, "ENTRY", slot)
            self.assertEqual(self.store.get_paper_limit(entry.order_id.value, ACCOUNT_ID).status, "cancelled")
        self.assertIsNone(self.store.get_robot_trade(trade.trade_id).exit_reason)

        # Quiet candle: nothing; then the first touch of 110 is the retest.
        self.candles.add(100, 104, 99, 103)
        monitor.tick()
        self.assertEqual(self.execution(candidate)["mirror"]["state"]["phase"], PHASE_CAMPAIGN_ACTIVE)
        self.book = book("110")
        self.candles.add(104, 110.5, 103, 109)
        self.assertEqual(monitor.tick(), (candidate.candidate_id,))           # retest proven -> exit requested
        record = self.execution(candidate)["mirror"]
        self.assertEqual(record["state"]["phase"], PHASE_RETEST_PROVEN)
        self.assertEqual(record["exit"]["reason"], "MIRROR_RETEST")
        self.assertEqual(monitor.tick(), (candidate.candidate_id,))           # Box-owned EXIT MARKET slot 0
        self.assertEqual(len(self.market_submissions), 2)                      # P1 entry + remainder close
        self.assertEqual(self.market_submissions[-1][1], OrderSide.SELL)
        self.assertIsNotNone(self.owned(source, "EXIT", 0))

        closed = self.store.get_robot_trade(trade.trade_id)
        self.assertEqual(closed.exit_reason, "TAKE")                          # schema reason; MIRROR identity below
        self.assertEqual(self.execution(candidate)["mirror"]["exit"]["reason"], "MIRROR_RETEST")
        # 0.5 x (99.2 - 93.5) + 1.5 x (109.9 - 93.5) = 2.85 + 24.6
        self.assertEqual(closed.realized_pnl_usdt, Decimal("27.45"))
        self.assertEqual(self.store.get_robot_candidate(candidate.candidate_id).status, "CLOSED")
        self.assertEqual(self.store.get_position_projection(KEY).quantity.value, Decimal("0"))

        # Restart after completion: a fresh monitor does nothing more.
        restarted = self.monitor()
        restarted.tick()
        self.assertEqual(len(self.market_submissions), 2)
        self.assertEqual(len(self.store.load_box_order_ownership(source.candidate_id)), 6)   # 4 ENTRY + EXIT1 + EXIT0

    def test_restart_between_retest_and_close_closes_exactly_once(self):
        self.add_wedge()
        source, candidate = self.add_box()
        monitor = self.monitor()
        self.open_first_slot(monitor, candidate)
        self.book = book("110")
        self.candles.add(104, 110.5, 103, 109)
        monitor.tick()                                                         # exit requested and persisted
        self.fail_next_submit = True
        with self.assertRaises(RuntimeError):
            monitor._advance_mirror_box(self.store.get_robot_candidate(candidate.candidate_id))
        intent = self.execution(candidate)["mirror"]["close_intent"]           # durable before the crash
        self.assertEqual(intent["slot"], 0)

        restarted = self.monitor()                                             # crash/restart
        restarted.tick()
        restarted.tick()
        closes = [side for _, side in self.market_submissions if side == OrderSide.SELL]
        self.assertEqual(len(closes), 1)
        trade = self.store.get_robot_trade(f"robot-trade-{candidate.candidate_id}")
        self.assertEqual(trade.exit_reason, "TAKE")
        self.assertEqual(self.store.get_position_projection(KEY).quantity.value, Decimal("0"))

    def test_the_mirror_state_survives_a_restart_and_is_not_reattached(self):
        self.add_wedge()
        source, candidate = self.add_box()
        self.open_first_slot(self.monitor(), candidate)
        decided = self.execution(candidate)["mirror"]["decided_at_ms"]
        restarted = self.monitor()
        restarted.tick()
        self.assertEqual(self.execution(candidate)["mirror"]["decided_at_ms"], decided)
        self.assertEqual(len(self.market_submissions), 1)                      # P1 was not re-sent

    def test_owner_path_monitor_without_policy_keeps_the_mirror_exits(self):
        self.add_wedge()
        source, candidate = self.add_box()
        self.open_first_slot(self.monitor(), candidate)
        plain = self.monitor(with_policy=False)                                # like process_authoritative_fill's monitor
        plain.process_authoritative_fill(SYMBOL)
        exits = [o for o in self.store.load_box_order_ownership(source.candidate_id) if o.role == "EXIT"]
        self.assertEqual([(o.slot, self.store.get_paper_limit(o.order_id.value, ACCOUNT_ID).quantity) for o in exits],
                         [(1, Decimal("0.5"))])

    # --- MIRROR off / not applicable: the Box Robot is unchanged ---------------------------------------

    def test_without_policy_the_box_trades_exactly_as_before(self):
        self.add_wedge()
        source, candidate = self.add_box()
        monitor = self.monitor(with_policy=False)
        for _ in range(3):
            self.assertEqual(monitor.tick(), (candidate.candidate_id,))
        self.assertNotIn("mirror", self.execution(candidate))
        order = self.store.get_paper_limit(self.owned(source, "EXIT", 1).order_id.value, ACCOUNT_ID)
        self.assertEqual((order.price, order.quantity), (Decimal("99.2"), Decimal("2")))

    def test_no_campaign_means_a_plain_box_attempt(self):
        source, candidate = self.add_box()                                     # no Wedge on the symbol
        monitor = self.monitor()
        for _ in range(4):
            monitor.tick()
        record = self.execution(candidate)["mirror"]
        self.assertEqual((record["decision"], record["reason"]), (mirror.NOT_ATTACHED, "no_active_campaign"))
        order = self.store.get_paper_limit(self.owned(source, "EXIT", 1).order_id.value, ACCOUNT_ID)
        self.assertEqual(order.quantity, Decimal("2"))

    def test_unknown_account_risk_or_exhausted_budget_never_attaches(self):
        self.add_wedge()
        self.risk_limit = None
        source, candidate = self.add_box()
        self.monitor().tick()
        self.assertEqual(self.execution(candidate)["mirror"]["reason"], "r0_unavailable")

    def test_boundary_not_beyond_the_box_take_never_attaches(self):
        self.add_wedge(level=98.0)                                             # line below the Box TAKE 99.2
        self.candles.coarse[1] = candle(BREAKOUT_OPEN, 99, 99.5, 95, 96)
        for c in self.candles.coarse[2:]:
            c.update(open=96, high=97, low=95, close=96)
        source, candidate = self.add_box()
        self.monitor().tick()
        self.assertEqual(self.execution(candidate)["mirror"]["reason"], "boundary_not_beyond_box_take")

    def test_a_data_gap_blocks_the_campaign_and_never_closes(self):
        self.add_wedge()
        source, candidate = self.add_box()
        monitor = self.monitor()
        self.open_first_slot(monitor, candidate)
        t = self.candles.coarse[-1]["close_time_ms"] + FIVE                    # one 5m candle missing
        self.candles.coarse.append(candle(t, 104, 110.5, 103, 109))
        self.candles.now = t + FIVE
        monitor.tick()
        record = self.execution(candidate)["mirror"]
        self.assertTrue(record["data_blocked"])
        self.assertNotIn("exit", record)
        self.assertEqual(len(self.market_submissions), 1)

    def test_retest_before_any_fill_ends_the_attempt_without_trading(self):
        self.add_wedge()
        source, candidate = self.add_box()
        self.book = book("95")                                                 # no slot crossed: all four rest
        monitor = self.monitor()
        for _ in range(3):
            monitor.tick()
        self.assertEqual(len(self.market_submissions), 0)
        self.candles.add(104, 110.5, 103, 109)
        monitor.tick()                                                         # retest proven
        monitor.tick()                                                         # nothing filled: end the attempt
        self.assertEqual(self.store.get_robot_candidate(candidate.candidate_id).status, "INVALIDATED")
        for slot in (1, 2, 3, 4):
            entry = self.owned(source, "ENTRY", slot)
            self.assertEqual(self.store.get_paper_limit(entry.order_id.value, ACCOUNT_ID).status, "cancelled")
        self.assertEqual(len(self.market_submissions), 0)


class MirrorPolicyUnitTests(unittest.TestCase):
    def test_flag_is_off_by_default_and_only_exact_1_enables(self):
        self.assertFalse(mirror.mirror_robot_enabled({}))
        for value in ("0", "true", "yes", " 2"):
            self.assertFalse(mirror.mirror_robot_enabled({mirror.ENV_FLAG: value}))
        self.assertTrue(mirror.mirror_robot_enabled({mirror.ENV_FLAG: "1"}))
        self.assertIsNone(mirror.build_runtime_policy(database_path="x", account_id=ACCOUNT_ID,
                                                      quantity_step=lambda s: Decimal("1"), environ={}))

    def test_prior_attempt_losses_consume_the_campaign_budget(self):
        boundary = mirror.boundary_from_dict({"boundary_id": "w:lower", "anchor_time_ms": 0, "anchor_price": 110.0,
                                              "slope_per_ms": 0.0, "as_of_time_ms": 0})
        campaign = {"campaign_id": "w:lower@1", "boundary": boundary, "campaign_direction": "LONG",
                    "state": {"phase": PHASE_CAMPAIGN_ACTIVE}, "breakout_close_ms": 1}
        policy = mirror.MirrorRobotPolicy(candles=None, account_risk_limit_usdt=lambda now: Decimal("1000"),
                                          quantity_step=lambda s: Decimal("0.1"))
        prior = [{"mirror": {"r0_usdt": "57.52", "worst_case_usdt": "25.6"}, "closed": True,
                  "net_pnl_usdt": Decimal("-40")}]
        decision = mirror.plan_attachment(policy, box_snapshot=box_snapshot(), symbol=SYMBOL, campaign=campaign,
                                          prior_attempts=prior, now_ms=NOW)
        self.assertEqual(decision["decision"], mirror.NOT_ATTACHED)            # 40 realized + 25.6 > 57.52
        self.assertIn("campaign_budget_exceeded", decision["reason"])
        profit = [{"mirror": {"r0_usdt": "57.52", "worst_case_usdt": "25.6"}, "closed": True,
                   "net_pnl_usdt": Decimal("500")}]
        allowed = mirror.plan_attachment(policy, box_snapshot=box_snapshot(), symbol=SYMBOL, campaign=campaign,
                                         prior_attempts=profit, now_ms=NOW)
        self.assertEqual(allowed["decision"], mirror.ATTACHED)
        self.assertEqual(allowed["r0_usdt"], "57.52")                          # frozen at the first attempt

    def test_profit_never_restores_budget_and_live_attempts_count_at_worst_case(self):
        boundary = mirror.boundary_from_dict({"boundary_id": "w:lower", "anchor_time_ms": 0, "anchor_price": 110.0,
                                              "slope_per_ms": 0.0, "as_of_time_ms": 0})
        campaign = {"campaign_id": "c", "boundary": boundary, "campaign_direction": "LONG",
                    "state": {"phase": PHASE_CAMPAIGN_ACTIVE}, "breakout_close_ms": 1}
        policy = mirror.MirrorRobotPolicy(candles=None, account_risk_limit_usdt=lambda now: Decimal("1000"),
                                          quantity_step=lambda s: Decimal("0.1"))
        live = [{"mirror": {"r0_usdt": "57.52", "worst_case_usdt": "25.6"}, "closed": False}] * 2
        decision = mirror.plan_attachment(policy, box_snapshot=box_snapshot(), symbol=SYMBOL, campaign=campaign,
                                          prior_attempts=live, now_ms=NOW)
        self.assertEqual(decision["decision"], mirror.NOT_ATTACHED)            # 3 x 25.6 > 57.52


if __name__ == "__main__":
    unittest.main()


class MirrorFineProofTests(unittest.TestCase):
    """A sloped line makes a touch ambiguous at 5m; missing 1m data must hold, not end the campaign."""

    def test_missing_1m_proof_holds_the_candle_and_later_proves_the_retest(self):
        from geometry.naked_retest import Boundary
        boundary = Boundary("w:lower", 0, 110.0, 1.0 / FIVE, 0)               # +1 per 5 minutes

        class Source:
            def __init__(self):
                self.coarse = [candle(0, 111, 111.5, 104, 105)]                  # naked DOWN: 111 > 110, 105 < 111
                self.fine_ok = False

            def closed_candles(self, candidate_id, symbol, after_close_ms):
                return [c for c in self.coarse if c["close_time_ms"] > after_close_ms]

            def fine_candles(self, symbol, coarse):
                if not self.fine_ok:
                    raise RuntimeError("1m unavailable")
                return [{"open_time_ms": coarse["open_time_ms"] + i * ONE,
                         "close_time_ms": coarse["open_time_ms"] + (i + 1) * ONE,
                         "open": 110.5, "high": 111.6 if i == 2 else 110.8, "low": 110.3, "close": 110.8,
                         "closed": True} for i in range(5)]

        source = Source()
        policy = mirror.MirrorRobotPolicy(candles=source, account_risk_limit_usdt=lambda now: None,
                                          quantity_step=lambda s: Decimal("1"))
        state, blocked = mirror.advance_boundary(policy, "w", SYMBOL, boundary, None)
        self.assertEqual(state["phase"], PHASE_CAMPAIGN_ACTIVE)
        # line 111 -> 112 inside the next candle: open/close below it, high 111.6 -> AMBIGUOUS at 5m
        source.coarse.append(candle(FIVE, 110.5, 111.6, 110.3, 110.8))
        held, blocked = mirror.advance_boundary(policy, "w", SYMBOL, boundary, state)
        self.assertEqual(held, state)                                          # not UNPROVEN, not consumed
        source.fine_ok = True
        proven, _ = mirror.advance_boundary(policy, "w", SYMBOL, boundary, held)
        self.assertEqual(proven["phase"], PHASE_RETEST_PROVEN)
