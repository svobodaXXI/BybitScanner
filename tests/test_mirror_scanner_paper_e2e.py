"""Scanner MIRROR candidate -> existing PAPER Robot: one full protected trade on an isolated temp PAPER DB.

Signal: the real ``mirror_scanner.observe_mirror_levels`` sees a 5m naked DOWN breakout of an untested horizontal
level at 110 (fresh, body >= 0.5 ATR) -> durable Scanner MIRROR candidate, LONG campaign back to 110.
Attempt: an IKIGAI_BOX LONG (P1 94 .. P4 91.6, TAKE 99.2, STOP 89.6) handed to the Robot through the ordinary Box
handoff while that campaign is active. The Robot replays the level itself, attaches the attempt (R0, campaign gate),
enters through Box ownership, protects with the Box STOP, takes 25 % at the Box TAKE, moves the remainder STOP to net
break-even and closes the remainder at the proven first retest. Fills carry the documented PAPER fee 0.06 % per side.
Fake executor/market only: no network, no runtime, no PAPER DB outside a temp dir.
"""

from decimal import Decimal
from pathlib import Path
import unittest
from unittest import mock

import pandas as pd

import mirror_retest_robot as mirror
import mirror_scanner as ms
from geometry.naked_retest import PHASE_CAMPAIGN_ACTIVE, PHASE_RETEST_PROVEN
from mirror_levels.levels import SOURCE_SWING_ZONE, horizontal_level
from terminal.domain.models import (
    Execution, ExecutionDedupKey, ExecutionId, Category, Notional, OrderSide, PositionSide, Price, Quantity, Symbol,
)
from terminal.persistence.sqlite_store import PositionProjectionUpdate
from tests import test_mirror_robot_box_cycle as cycle
from tests.test_robot_breakout_monitor import ACCOUNT_ID, SYMBOL

FIVE = cycle.FIVE
LEVEL_CONFIRMED = 3_000_000
BREAKOUT_OPEN = 6_000_000
NOW = 7_500_000
FEE_RATE = mirror.PAPER_FEE_RATE


class ScannerCandles(cycle.Candles):
    """Closed 5m history: range above 110, one naked DOWN candle through it, then quiet trade near 100."""

    def __init__(self, on_time=None):
        super().__init__(on_time)
        self.coarse = [cycle.candle(t, 112, 113, 111, 112) for t in range(0, BREAKOUT_OPEN, FIVE)]
        self.coarse.append(cycle.candle(BREAKOUT_OPEN, 111, 111.5, 104, 105))
        t = BREAKOUT_OPEN + FIVE
        while t + FIVE <= NOW:
            self.coarse.append(cycle.candle(t, 100, 101, 99, 100))
            t += FIVE
        self.now = NOW


def scanner_frame(candles, upto_close_ms):
    rows = [{"time": c["open_time_ms"], "open": c["open"], "high": c["high"], "low": c["low"], "close": c["close"]}
            for c in candles if c["close_time_ms"] <= upto_close_ms]
    last = rows[-1]
    rows.append({"time": last["time"] + FIVE, "open": last["close"], "high": last["close"], "low": last["close"],
                 "close": last["close"]})                                  # the Scanner's still-open candle
    return pd.DataFrame(rows)


class MirrorScannerPaperE2E(unittest.TestCase):
    setUp_base = cycle.MirrorBoxCycleTests.setUp
    monitor = cycle.MirrorBoxCycleTests.monitor
    submit_market = cycle.MirrorBoxCycleTests.submit_market
    add_box = cycle.MirrorBoxCycleTests.add_box
    execution = cycle.MirrorBoxCycleTests.execution
    owned = cycle.MirrorBoxCycleTests.owned

    def setUp(self):
        self.setUp_base()
        self.clock.value = NOW
        self.candles = ScannerCandles(on_time=lambda now: setattr(self.clock, "value", now))
        self.root = Path(self.tmp.name) / "mirror_levels"
        self.level = horizontal_level(symbol=SYMBOL, timeframe="5", source=SOURCE_SWING_ZONE, pattern=None,
                                      side="lower", price=110.0, anchor_time_ms=0, confirmed_at_ms=LEVEL_CONFIRMED)
        self.fees = Decimal(0)

    def policy(self):
        return mirror.MirrorRobotPolicy(candles=self.candles, account_risk_limit_usdt=lambda now: self.risk_limit,
                                        quantity_step=lambda symbol: Decimal("0.1"), scanner_root=self.root)

    def fill(self, order_id, side, quantity, price, *, resting=False):
        """Shared fake fill economics plus the PAPER per-side fee on every leg."""
        fee = (price * quantity * FEE_RATE).quantize(Decimal("0.00000001"))
        self.fees += fee
        current = self.store.get_position_projection(cycle.KEY)
        qty = current.quantity.value if current else Decimal(0)
        avg = current.average_entry.value if current and current.average_entry else None
        realized = current.realized_pnl if current else Decimal(0)
        accumulated = (current.accumulated_fee if current else Decimal(0)) + fee
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
        execution = Execution(
            ExecutionDedupKey(ACCOUNT_ID, Category.LINEAR, ExecutionId(f"x{self.executor._exec_counter}")),
            order_id, Symbol(SYMBOL), side, Price(price), Quantity(quantity), fee, self.clock())
        update = PositionProjectionUpdate(
            cycle.KEY, new_side, Quantity(new_qty), Price(new_avg) if new_avg is not None else None, realized,
            accumulated, Notional(new_qty * new_avg if new_avg is not None else Decimal(0)), "synced",
            current.version if current else None, self.clock())
        if resting:
            self.store.apply_paper_limit_execution_once(order_id, execution, update, updated_at_ms=self.clock())
        else:
            self.store.apply_execution_once(execution, update)

    def scan(self, upto_close_ms):
        with mock.patch.object(ms, "collect_levels", lambda *a, **k: [self.level]):
            return ms.observe_mirror_levels(SYMBOL, scanner_frame(self.candles.coarse, upto_close_ms),
                                            timeframe="5", root=self.root, now_ms=upto_close_ms)

    # --- the end-to-end trade --------------------------------------------------------------------------------

    def test_scanner_mirror_signal_to_closed_paper_trade_with_fees_and_net_pnl(self):
        report = {}
        # 1. Signal: the Scanner pass right after the breakout candle closed.
        summary = self.scan(BREAKOUT_OPEN + 2 * FIVE)
        self.assertEqual(summary["new_candidates"], 1, summary)
        record = ms.load_state(SYMBOL, "5", self.root)["records"][self.level.level_id]
        self.assertTrue(record["candidate"])
        self.assertEqual(record["freshness"], "FRESH")
        self.assertEqual(record["naked_retest"]["breakout"]["campaign_direction"], "LONG")
        report["signal"] = {"level_id": self.level.level_id, "level": 110.0,
                            "breakout": record["naked_retest"]["breakout"],
                            "body_atr": record["breakout_evidence"]["body_atr"]}

        # 2. Candidate -> admission: an ordinary Box attempt in the campaign direction joins the MIRROR campaign.
        source, candidate = self.add_box()
        monitor = self.monitor()
        self.assertEqual(monitor.tick(), (candidate.candidate_id,))
        attached = self.execution(candidate)["mirror"]
        self.assertEqual(attached["decision"], mirror.ATTACHED, attached)
        self.assertEqual(attached["source"], mirror.SCANNER_SOURCE)
        self.assertEqual(attached["mirror_level_id"], self.level.level_id)
        self.assertNotIn("parent_candidate_id", attached)
        self.assertEqual(attached["campaign_id"], f"{self.level.level_id}@{BREAKOUT_OPEN + FIVE}")
        self.assertEqual(attached["state"]["phase"], PHASE_CAMPAIGN_ACTIVE)
        report["admission"] = {k: attached[k] for k in ("decision", "campaign_id", "r0_usdt", "worst_case_usdt",
                                                        "remaining_net_reward_usdt", "partial_quantities")}

        # 3. Entry + fill + STOP: P1 MARKET through Box ownership, Box STOP, 25 % EXIT LIMIT at the Box TAKE.
        for _ in range(3):
            self.assertEqual(monitor.tick(), (candidate.candidate_id,))
        trade = self.store.get_robot_trade(f"robot-trade-{candidate.candidate_id}")
        self.assertEqual((trade.entry_quantity, trade.average_entry), (Decimal("2"), Decimal("93.5")))
        stop0 = self.store.get_protection_projection(cycle.KEY).stop_loss
        self.assertIsNotNone(stop0)
        partial_exit = self.owned(source, "EXIT", 1)
        order = self.store.get_paper_limit(partial_exit.order_id.value, ACCOUNT_ID)
        self.assertEqual((order.price, order.quantity, order.side), (Decimal("99.2"), Decimal("0.5"), OrderSide.SELL))
        report["entry"] = {"side": "BUY", "qty": "2", "avg": "93.5", "stop": str(stop0),
                           "take_25pct": f"{order.quantity} @ {order.price}"}

        # 4. TAKE 25 %: partial EXIT fills, remainder STOP -> whole-trade net break-even.
        self.book = cycle.book("99")
        self.fill(partial_exit.order_id, OrderSide.SELL, Decimal("0.5"), Decimal("99.2"), resting=True)
        monitor.process_authoritative_fill(SYMBOL)
        be = self.store.get_protection_projection(cycle.KEY).stop_loss
        self.assertGreater(be, stop0)
        self.assertEqual(self.execution(candidate)["mirror"]["be_stop"], str(be))
        report["after_partial"] = {"be_stop": str(be)}

        # 5. First retest of 110 -> remainder closed by Box-owned EXIT MARKET slot 0.
        self.candles.add(100, 104, 99, 103)
        monitor.tick()
        self.assertEqual(self.execution(candidate)["mirror"]["state"]["phase"], PHASE_CAMPAIGN_ACTIVE)
        self.book = cycle.book("110")
        self.candles.add(104, 110.5, 103, 109)
        self.assertEqual(monitor.tick(), (candidate.candidate_id,))
        self.assertEqual(self.execution(candidate)["mirror"]["state"]["phase"], PHASE_RETEST_PROVEN)
        self.assertEqual(monitor.tick(), (candidate.candidate_id,))
        self.assertEqual(len(self.market_submissions), 2)

        # 6. Close + Net PnL.
        closed = self.store.get_robot_trade(trade.trade_id)
        self.assertEqual(closed.exit_reason, "TAKE")
        self.assertEqual(self.execution(candidate)["mirror"]["exit"]["reason"], "MIRROR_RETEST")
        self.assertEqual(self.store.get_robot_candidate(candidate.candidate_id).status, "CLOSED")
        self.assertEqual(self.store.get_position_projection(cycle.KEY).quantity.value, Decimal("0"))
        # 0.5 x (99.2 - 93.5) + 1.5 x (109.9 - 93.5)
        self.assertEqual(closed.realized_pnl_usdt, Decimal("27.45"))
        expected_fees = sum((p * q * FEE_RATE for p, q in (
            (Decimal("93.5"), Decimal("2")), (Decimal("99.2"), Decimal("0.5")), (Decimal("109.9"), Decimal("1.5")))),
            Decimal(0))
        self.assertEqual(closed.fees_costs_usdt, expected_fees)
        net = closed.realized_pnl_usdt - closed.fees_costs_usdt
        self.assertGreater(net, 0)
        report["close"] = {"exit_reason": closed.exit_reason, "mirror_exit": "MIRROR_RETEST",
                           "realized_pnl_usdt": str(closed.realized_pnl_usdt),
                           "fees_usdt": str(closed.fees_costs_usdt), "net_pnl_usdt": str(net)}

        # 7. The Scanner sees the same retest and ends the level; restart does nothing more.
        self.scan(self.candles.now)
        done = ms.load_state(SYMBOL, "5", self.root)["records"][self.level.level_id]
        self.assertEqual(done["lifecycle"], ms.LIFECYCLE_DONE)
        self.monitor().tick()
        self.assertEqual(len(self.market_submissions), 2)
        print("\nMIRROR->PAPER E2E", report)

    def test_retested_stale_or_rejected_scanner_levels_are_never_campaign_sources(self):
        self.scan(BREAKOUT_OPEN + 5 * FIVE)                                       # seen 4 candles late: stale
        record = ms.load_state(SYMBOL, "5", self.root)["records"][self.level.level_id]
        self.assertFalse(record["candidate"])
        self.assertEqual(mirror.scanner_level_sources(SYMBOL, root=self.root), [])
        source, candidate = self.add_box()
        monitor = self.monitor()
        monitor.tick()
        self.assertEqual(self.execution(candidate)["mirror"]["decision"], mirror.NOT_ATTACHED)

    def test_unreadable_scanner_state_defers_without_any_order(self):
        path = ms.state_path(SYMBOL, "5", self.root)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("{broken", encoding="utf-8")
        source, candidate = self.add_box()
        monitor = self.monitor()
        monitor.tick()
        execution = self.execution(candidate)
        self.assertNotEqual((execution.get("mirror") or {}).get("decision"), mirror.ATTACHED)
        self.assertEqual(self.store.load_box_order_ownership(source.candidate_id), ())
        self.assertIsNone(self.store.get_robot_trade(f"robot-trade-{candidate.candidate_id}"))

    def test_scanner_breakout_not_confirmed_by_robot_replay_is_not_a_campaign(self):
        self.scan(BREAKOUT_OPEN + 2 * FIVE)
        sources = mirror.scanner_level_sources(SYMBOL, root=self.root)
        self.assertEqual(len(sources), 1)
        forged = [dict(sources[0], breakout_open_ms=BREAKOUT_OPEN - FIVE)]
        self.assertIsNone(mirror.find_active_campaign(self.policy(), [], symbol=SYMBOL, direction="LONG",
                                                      now_ms=NOW, scanner_sources=forged))
        self.assertIsNone(mirror.find_active_campaign(self.policy(), [], symbol=SYMBOL, direction="SHORT",
                                                      now_ms=NOW, scanner_sources=sources))

    def test_one_breakout_seen_by_wedge_and_scanner_is_one_campaign(self):
        self.scan(BREAKOUT_OPEN + 2 * FIVE)
        sources = mirror.scanner_level_sources(SYMBOL, root=self.root)
        wedge = type("W", (), {"candidate_id": "wedge-1", "approved_at_ms": LEVEL_CONFIRMED,
                               "signal_snapshot": cycle.wedge_snapshot(110.0)})()
        with mock.patch.object(cycle, "WEDGE_AS_OF", LEVEL_CONFIRMED):
            wedge.signal_snapshot = cycle.wedge_snapshot(110.0)
        campaign = mirror.find_active_campaign(self.policy(), [wedge], symbol=SYMBOL, direction="LONG", now_ms=NOW,
                                               scanner_sources=sources)
        self.assertEqual(campaign["parent_candidate_id"], "wedge-1")             # Wedge wins the tie: one R0 budget
        self.assertNotIn("source", campaign)


if __name__ == "__main__":
    unittest.main()
