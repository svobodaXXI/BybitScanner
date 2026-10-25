"""Standalone MIRROR entry -> existing Autopilot / Admission / PAPER Robot, on an isolated temp PAPER DB.

Signal: the real ``mirror_scanner.observe_mirror_levels`` sees a 5m naked DOWN breakout of an untested horizontal
level at 110 (LONG campaign back to 110), then a bullish Engulfing below the level -> frozen entry terms
(reference = confirmation close, STOP = confirmation low + the Robot's one-tick buffer, TAKE = 110, net RR >= 2 with
fees and slippage) -> common Robot handoff (flag on) -> Autopilot SHADOW ALLOW -> PAPER_AUTO admission -> the shared
single-LIMIT lifecycle of the real ``PaperRuntime``: MIRROR campaign / R0 gate, ENTRY LIMIT, real PAPER fill, STOP /
TAKE protection, TAKE close, fees and Net PnL; restart afterwards executes nothing again.
Synthetic market inputs only: no network, no runtime outside the temp dir, no production DB.
"""

from dataclasses import replace
from decimal import Decimal
from pathlib import Path
import os
import tempfile
import threading
import time
import unittest
from unittest import mock

import pandas as pd

import mirror_retest_robot as mirror
import mirror_scanner as ms
import robot_candidate_store
import robot_l_shape
from geometry.naked_retest import PHASE_CAMPAIGN_ACTIVE
from mirror_levels.levels import SOURCE_SWING_ZONE, horizontal_level
from terminal.application.robot_admission import admit_robot_candidate
from terminal.application.robot_autopilot import OUTCOME_ALLOW
from terminal.application.robot_autopilot_shadow import (
    SOURCE_SCANNER, admit_paper_auto_candidate, observe_shadow_candidate,
)
from terminal.application.robot_control import start_robot
from terminal.application.trading_accounts import paper_account_manager
from terminal.domain.models import Category, OrderSide, PositionKey, Symbol, TradingAccountId
from terminal.persistence.sqlite_store import SQLiteStore
from terminal.runtime.paper_http_server import SerializedPaperRuntime, create_configured_paper_runtime
from tests.test_robot_paper_acceptance import (
    _MutableBookProvider, _event_book, _instrument, _start_robot_monitor, _wait_until,
)

ACCOUNT = TradingAccountId("paper")
SYMBOL = "ACCEPTUSDT"
FIVE, ONE = 300_000, 60_000
LEVEL = 110.0
FEE = Decimal("0.0006")
OPEN_DAILY_GATE = mock.patch(
    "terminal.application.robot_autopilot_shadow._daily_loss_gate",
    lambda *args, **kwargs: {"enabled": True, "latched": False, "data_available": True,
                             "business_date_msk": "fixture", "transition": None})


def candle(open_ms, o, h, low, c):
    return {"open_time_ms": open_ms, "close_time_ms": open_ms + FIVE, "open": o, "high": h, "low": low, "close": c,
            "closed": True}


class Timeline:
    """Closed 5m history around the real clock (the Robot's campaign freshness uses wall time)."""

    def __init__(self):
        self.t = int(time.time() * 1000) // FIVE * FIVE            # latest closed 5m candle closes here
        start = self.t - 40 * FIVE
        self.breakout_open = self.t - 6 * FIVE
        self.coarse = [candle(o, 112, 113, 111, 112) for o in range(start, self.breakout_open, FIVE)]
        self.coarse += [
            candle(self.breakout_open, 111, 111.5, 104, 105),            # naked DOWN through 110
            candle(self.t - 5 * FIVE, 104.5, 105.0, 104.2, 104.6),
            candle(self.t - 4 * FIVE, 104.6, 104.8, 103.9, 104.0),       # bearish
            candle(self.t - 3 * FIVE, 103.95, 105.2, 103.9, 105.0),      # bullish Engulfing = confirmation
            candle(self.t - 2 * FIVE, 105.0, 105.4, 104.8, 105.2),
            candle(self.t - FIVE, 105.2, 105.5, 105.0, 105.3),
        ]
        self.confirmation = self.coarse[-3]
        self.level_confirmed = start + 10 * FIVE

    def frame(self, upto_close_ms):
        rows = [{"time": c["open_time_ms"], "open": c["open"], "high": c["high"], "low": c["low"],
                 "close": c["close"]} for c in self.coarse if c["close_time_ms"] <= upto_close_ms]
        last = rows[-1]
        rows.append({"time": last["time"] + FIVE, "open": last["close"], "high": last["close"],
                     "low": last["close"], "close": last["close"]})
        return pd.DataFrame(rows)

    # ``BybitClosedKlineSource``-like for the Robot's own campaign replay.
    def closed_candles(self, candidate_id, symbol, after_close_ms):
        now = int(time.time() * 1000)
        return [c for c in self.coarse if after_close_ms < c["close_time_ms"] <= now]

    def fine_candles(self, symbol, coarse):
        return [candle(coarse["open_time_ms"] + i * ONE, coarse["open"], coarse["high"], coarse["low"],
                       coarse["close"]) | {"close_time_ms": coarse["open_time_ms"] + (i + 1) * ONE}
                for i in range(5)]


class _RobotCandle:
    def __init__(self):
        self._lock = threading.Lock()
        self.value = None

    def set(self, value):
        with self._lock:
            self.value = value

    def __call__(self, symbol):
        with self._lock:
            return self.value if symbol == SYMBOL else None


class MirrorStandaloneHarness(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.db = self.root / "paper.sqlite3"
        self.candidates = self.root / "candidates"
        self.mirror_root = self.root / "mirror_levels"
        self.timeline = Timeline()
        self.level = horizontal_level(symbol=SYMBOL, timeframe="5", source=SOURCE_SWING_ZONE, pattern=None,
                                      side="lower", price=LEVEL, anchor_time_ms=self.timeline.level_confirmed - FIVE,
                                      confirmed_at_ms=self.timeline.level_confirmed)
        for patcher in (
            mock.patch.dict(os.environ, {robot_l_shape.MIRROR_STANDALONE_ENV: "1"}),
            mock.patch.object(robot_candidate_store, "DEFAULT_STORE_DIR", self.candidates),
            OPEN_DAILY_GATE,
        ):
            patcher.start()
            self.addCleanup(patcher.stop)

    def scan(self, upto_close_ms, fine=None):
        with mock.patch.object(ms, "collect_levels", lambda *a, **k: [self.level]):
            return ms.observe_mirror_levels(SYMBOL, self.timeline.frame(upto_close_ms), timeframe="5",
                                            fine_candles=fine, root=self.mirror_root, now_ms=upto_close_ms)

    def state(self):
        return ms.load_state(SYMBOL, "5", self.mirror_root)


class MirrorStandalonePaperE2E(MirrorStandaloneHarness):
    def runtime(self, robot_candle, book):
        instrument = _instrument()

        def policy_factory(**kwargs):
            real = mirror.build_runtime_policy(**kwargs, environ={mirror.ENV_FLAG: "1"})
            return replace(real, candles=self.timeline, account_risk_limit_usdt=lambda now: Decimal("1000"),
                           scanner_root=self.mirror_root)

        with mock.patch("terminal.runtime.paper_runtime.build_mirror_robot_policy", policy_factory):
            return SerializedPaperRuntime(lambda: create_configured_paper_runtime(
                self.db, book_provider=book, instrument_snapshot=instrument,
                instrument_provider=lambda symbol: replace(instrument, symbol=symbol),
                account_manager=paper_account_manager(), robot_closed_candle_provider=robot_candle,
                robot_tick_interval_s=0.02,
            )), instrument

    def test_pin_bar_full_paper_lifecycle_via_existing_robot(self):
        tl = self.timeline
        # Same reference, STOP and TAKE as the Engulfing E2E; only the confirming
        # shape changes. This proves the Pin Bar signal traverses the real
        # admission, R0, matcher, protection, restart and fee-inclusive close.
        tl.coarse[-3] = candle(tl.t - 3 * FIVE, 104.9, 105.1, 103.9, 105.0)
        self.assertTrue(ms._pin_bar(tl.coarse[-3], "LONG"))
        self.assertFalse(ms._engulfing(tl.coarse[-4], tl.coarse[-3], "LONG"))
        self.test_mirror_signal_to_closed_paper_trade_with_fees_net_pnl_and_no_repeat_after_restart()
        self.assertEqual(self.state()["standalone_entries"][0]["terms"]["confirmation"]["kind"],
                         ms.CONFIRMATION_PIN_BAR)

    def test_mirror_signal_to_closed_paper_trade_with_fees_net_pnl_and_no_repeat_after_restart(self):
        tl, report = self.timeline, {}
        # 1. MIRROR breakout (fresh), then the bullish Engulfing confirmation on 5m.
        self.assertEqual(self.scan(tl.breakout_open + 2 * FIVE)["new_candidates"], 1)
        summary = self.scan(tl.t)
        self.assertEqual(len(summary["standalone_handoffs"]), 1, summary)
        candidate_ref = summary["standalone_handoffs"][0]
        entry = self.state()["standalone_entries"][0]
        terms = entry["terms"]
        self.assertEqual((entry["handoff"], terms["direction"], terms["source_timeframe"]), ("HANDED", "LONG", "5"))
        self.assertEqual((terms["reference"], terms["stop"], terms["target"]), ("105.0", "103.9", "110.0"))
        self.assertGreaterEqual(Decimal(terms["reward_risk"]), 2)
        report["signal"] = {"level": LEVEL, "breakout": "5m 111 -> 105 (naked DOWN)",
                            "confirmation": terms["confirmation"], "frozen": {k: terms[k] for k in (
                                "reference", "stop", "target", "reward_risk")}}

        robot_candle, book = _RobotCandle(), _MutableBookProvider()
        book.set(SYMBOL, bid=Decimal("105.3"), ask=Decimal("105.4"))
        runtime, instrument = self.runtime(robot_candle, book)
        try:
            started = start_robot(database_path=self.db)
            self.assertEqual((started.mode, started.recovery_status), ("ROBOT_RUNNING", "READY"))

            # 2. Autopilot SHADOW ALLOW -> PAPER_AUTO admission (the existing first-eligible path).
            store = SQLiteStore.open(self.db)
            try:
                autopilot = store.get_robot_autopilot_state(ACCOUNT)
                store.update_robot_autopilot_state(ACCOUNT, mode="SHADOW", expected_version=autopilot.version,
                                                   updated_at_ms=int(time.time() * 1000))
                observed = observe_shadow_candidate(
                    store, ACCOUNT, source=SOURCE_SCANNER, candidate_ref=candidate_ref,
                    protection_healthy=lambda: True, candidate_store_dir=self.candidates,
                    clock_ms=lambda: int(time.time() * 1000))
                self.assertEqual(observed.result.outcome, OUTCOME_ALLOW, observed.result)
                autopilot = store.get_robot_autopilot_state(ACCOUNT)
                store.update_robot_autopilot_state(ACCOUNT, mode="PAPER_AUTO", expected_version=autopilot.version,
                                                   updated_at_ms=int(time.time() * 1000))
                admitted = admit_paper_auto_candidate(
                    store, ACCOUNT, allow_decision_id=observed.decision.decision_id, source=SOURCE_SCANNER,
                    protection_healthy=lambda: True, candidate_fresh=lambda *_: True,
                    candidate_store_dir=self.candidates, clock_ms=lambda: int(time.time() * 1000))
                self.assertEqual(admitted.result.outcome, OUTCOME_ALLOW, admitted.result)
                record = store.get_robot_candidate(admitted.decision.resulting_candidate_id or candidate_ref)
            finally:
                store.close()
            self.assertEqual((record.status, record.robot_state["phase"], record.robot_state["pattern"]),
                             ("APPROVED", robot_l_shape.PHASE_WAITING_RETEST, "MIRROR"))
            candidate_id = record.candidate_id
            report["admission"] = {"autopilot": "SHADOW ALLOW -> PAPER_AUTO ALLOW", "candidate": candidate_id}

            # 3. Entry: price returns to the confirmation close -> MIRROR campaign / R0 gate -> 1-WV LIMIT.
            _start_robot_monitor(runtime)

            def candidate():
                return runtime.call(lambda owner: owner.store.get_robot_candidate(candidate_id))

            robot_candle.set({"time_ms": tl.t - 2 * FIVE, "high": 105.3, "low": 104.95, "close": 105.1})
            attached = _wait_until(lambda: mirror.mirror_record((candidate().robot_state or {}).get("execution")))
            self.assertEqual(attached["decision"], mirror.ATTACHED, attached)
            self.assertEqual((attached["mode"], attached["source"], attached["mirror_level_id"]),
                             ("STANDALONE", mirror.SCANNER_SOURCE, self.level.level_id))
            self.assertEqual(attached["campaign_id"], f"{self.level.level_id}@{tl.breakout_open + FIVE}")
            self.assertEqual(attached["state"]["phase"], PHASE_CAMPAIGN_ACTIVE)
            self.assertEqual(attached["one_wv_usdt"], "250")                   # floor(5 % x 5000 PAPER equity)
            report["r0_gate"] = {k: attached[k] for k in ("campaign_id", "r0_usdt", "worst_case_usdt",
                                                           "remaining_net_reward_usdt")}

            def limit():
                order_id = (candidate().robot_state.get("execution") or {}).get("limit_order_id")
                return runtime.call(lambda owner: owner.store.get_paper_limit(order_id, ACCOUNT)) if order_id else None

            order = _wait_until(limit)
            tick = instrument.tick_size
            self.assertEqual((order.side, order.price), (OrderSide.BUY, Decimal("105.0") + 2 * tick))

            # 4. Fill through the real PAPER matcher.
            book.set(SYMBOL, bid=order.price - tick, ask=order.price)
            key = PositionKey(ACCOUNT, Category.LINEAR, Symbol(SYMBOL), 0)
            trade = _wait_until(lambda: runtime.call(
                lambda owner: owner.store.get_open_robot_trade_for_symbol(ACCOUNT, Symbol(SYMBOL))))
            self.assertEqual((trade.pattern, trade.direction, trade.entry_path), ("MIRROR", "LONG", "LIMIT"))

            def protection():
                projection = runtime.call(lambda owner: owner.store.get_protection_projection(key))
                return projection if projection and projection.stop_loss and projection.take_profit else None

            prot = _wait_until(protection)
            self.assertEqual(prot.stop_loss, Decimal("103.9") - tick)            # beyond the confirmation low
            self.assertEqual(prot.take_profit, Decimal("110.0"))                # 100 % at the MIRROR level
            report["entry"] = {"side": "BUY", "qty": str(trade.entry_quantity), "avg": str(trade.average_entry),
                               "stop": str(prot.stop_loss), "take": str(prot.take_profit)}

            # Restart with the position open: recovery keeps ownership, nothing is entered twice.
            runtime.close()
            runtime, _ = self.runtime(robot_candle, book)
            _start_robot_monitor(runtime)
            time.sleep(0.3)
            fills = runtime.call(lambda owner: owner.store.load_executions_for_symbol(ACCOUNT, Symbol(SYMBOL)))
            self.assertEqual(len(fills), 1)

            # 5. TAKE at the first retest of 110 -> close, fees, Net PnL.
            exit_bid = prot.take_profit + tick
            book.set(SYMBOL, bid=exit_bid, ask=exit_bid + tick)
            crossing = _event_book(SYMBOL, bid=exit_bid, ask=exit_bid + tick)
            runtime.call(lambda owner: owner.process_robot_market_event(
                SYMBOL, crossing, event_id="mirror-take", received_at_ms=crossing.received_at_ms))
            closed = _wait_until(lambda: (lambda t: t if t and t.exit_time_ms else None)(
                runtime.call(lambda owner: owner.store.get_robot_trade(trade.trade_id))))
            self.assertEqual(closed.exit_reason, "TAKE")
            fills = runtime.call(lambda owner: owner.store.load_executions_for_symbol(ACCOUNT, Symbol(SYMBOL)))
            fees = sum((f.fee for f in fills), Decimal(0))
            self.assertEqual(fees, sum((f.price.value * f.quantity.value * FEE for f in fills), Decimal(0)))
            # PR #615 merged: a non-Box close must attribute both entry and exit fees.
            self.assertEqual(closed.fees_costs_usdt, fees)
            net = closed.realized_pnl_usdt - fees
            self.assertGreater(net, 0)
            self.assertEqual(candidate().status, "CLOSED")
            report["close"] = {"exit_reason": closed.exit_reason, "exit_price": str(closed.exit_price),
                               "fills": [(f.side.value, str(f.price.value), str(f.quantity.value), str(f.fee))
                                         for f in fills],
                               "realized_pnl_usdt": str(closed.realized_pnl_usdt),
                               "fees_all_fills_usdt": str(fees),
                               "trade_fees_costs_usdt": str(closed.fees_costs_usdt), "net_pnl_usdt": str(net)}

            # 6. Restart after the close: no new order or execution; the level is now retested for the Scanner.
            runtime.close()
            runtime, _ = self.runtime(robot_candle, book)
            _start_robot_monitor(runtime)
            time.sleep(0.3)
            after = runtime.call(lambda owner: owner.store.load_executions_for_symbol(ACCOUNT, Symbol(SYMBOL)))
            self.assertEqual(len(after), len(fills))
            self.assertEqual(candidate().status, "CLOSED")
        finally:
            runtime.close()
        print("\nMIRROR STANDALONE PAPER E2E", report)


class MirrorStandaloneRules(MirrorStandaloneHarness):
    def test_pin_bar_shape_is_directional_and_rejects_bad_ohlc(self):
        long_bar = {"open": 104.8, "high": 105.1, "low": 103.0, "close": 105.0, "closed": True}
        short_bar = {"open": 104.8, "high": 106.6, "low": 104.5, "close": 104.6, "closed": True}
        self.assertTrue(ms._pin_bar(long_bar, "LONG"))
        self.assertFalse(ms._pin_bar(long_bar, "SHORT"))
        self.assertTrue(ms._pin_bar(short_bar, "SHORT"))
        self.assertFalse(ms._pin_bar(short_bar, "LONG"))
        self.assertFalse(ms._pin_bar(long_bar | {"closed": False}, "LONG"))
        self.assertFalse(ms._pin_bar(long_bar | {"low": 105.2}, "LONG"))
        self.assertFalse(ms._pin_bar(long_bar | {"high": 104.9}, "LONG"))
        self.assertFalse(ms._pin_bar(long_bar | {"close": float("nan")}, "LONG"))
        self.assertFalse(ms._pin_bar(long_bar | {"low": 0}, "LONG"))
        self.assertFalse(ms._pin_bar({"open": 10, "high": 10, "low": 10, "close": 10}, "LONG"))
        self.assertFalse(ms._pin_bar(long_bar, "SIDEWAYS"))
        self.assertFalse(ms._pin_bar({"open": 104.8}, "LONG"))

    def test_5m_pin_bar_routes_through_existing_mirror_handoff_once(self):
        tl = self.timeline
        # No Engulfing: current opens above previous close. Long lower-wick rejection.
        tl.coarse[-3] = candle(tl.t - 3 * FIVE, 104.9, 105.1, 103.9, 105.0)
        self.assertFalse(ms._engulfing(tl.coarse[-4], tl.coarse[-3], "LONG"))
        self.scan(tl.breakout_open + 2 * FIVE)
        first = self.scan(tl.t)
        self.assertEqual(len(first["standalone_handoffs"]), 1)
        entries = self.state()["standalone_entries"]
        self.assertEqual(len(entries), 1)
        self.assertEqual(entries[0]["terms"]["confirmation"]["kind"], ms.CONFIRMATION_PIN_BAR)
        self.assertEqual(entries[0]["terms"]["source_timeframe"], "5")
        self.assertGreaterEqual(Decimal(entries[0]["terms"]["reward_risk"]), Decimal("2"))
        self.assertEqual(self.scan(tl.t)["standalone_handoffs"], [])
        self.assertEqual(len(self.state()["standalone_entries"]), 1)

    def test_short_pin_bar_routes_through_same_scanner_and_handoff(self):
        tl = self.timeline
        # Mirror all prices about 100: a downward naked breakout with a LONG
        # lower-wick Pin Bar becomes an upward breakout with a SHORT upper wick.
        tl.coarse[-3] = candle(tl.t - 3 * FIVE, 104.9, 105.1, 103.9, 105.0)
        tl.coarse = [candle(r["open_time_ms"], 200 - r["open"], 200 - r["low"],
                            200 - r["high"], 200 - r["close"]) for r in tl.coarse]
        self.level = horizontal_level(
            symbol=SYMBOL, timeframe="5", source=SOURCE_SWING_ZONE, pattern=None,
            side="upper", price=90.0,
            anchor_time_ms=tl.level_confirmed - FIVE,
            confirmed_at_ms=tl.level_confirmed,
        )
        self.assertTrue(ms._pin_bar(tl.coarse[-3], "SHORT"))
        self.assertFalse(ms._engulfing(tl.coarse[-4], tl.coarse[-3], "SHORT"))
        self.assertEqual(self.scan(tl.breakout_open + 2 * FIVE)["new_candidates"], 1)
        result = self.scan(tl.t)
        self.assertEqual(len(result["standalone_handoffs"]), 1)
        entries = self.state()["standalone_entries"]
        self.assertEqual(len(entries), 1)
        terms = entries[0]["terms"]
        self.assertEqual((terms["direction"], terms["confirmation"]["kind"],
                          terms["source_timeframe"]), ("SHORT", ms.CONFIRMATION_PIN_BAR, "5"))
        self.assertEqual((terms["reference"], terms["stop"], terms["target"]),
                         ("95.0", "96.1", "90.0"))
        self.assertGreaterEqual(Decimal(terms["reward_risk"]), 2)
        self.assertEqual(self.scan(tl.t)["standalone_handoffs"], [])

    def test_engulfing_takes_priority_when_the_same_candle_is_also_pin_bar(self):
        tl = self.timeline
        tl.coarse[-4] = candle(tl.t - 4 * FIVE, 104.5, 104.8, 103.9, 104.3)
        tl.coarse[-3] = candle(tl.t - 3 * FIVE, 104.2, 104.7, 103.1, 104.6)
        self.assertTrue(ms._engulfing(tl.coarse[-4], tl.coarse[-3], "LONG"))
        self.assertTrue(ms._pin_bar(tl.coarse[-3], "LONG"))
        self.scan(tl.breakout_open + 2 * FIVE)
        self.scan(tl.t)
        entries = self.state()["standalone_entries"]
        self.assertEqual(len(entries), 1)
        self.assertEqual(entries[0]["terms"]["confirmation"]["kind"], ms.CONFIRMATION_ENGULFING)

    def test_1m_pin_bar_requires_only_its_own_closed_candle(self):
        tl = self.timeline
        tl.coarse[-3] = candle(tl.t - 3 * FIVE, 104.1, 105.2, 103.9, 105.0)
        base = tl.t - 4 * FIVE
        fine = [
            candle(base, 104.6, 104.7, 104.1, 104.2) | {"close_time_ms": base + ONE},
            candle(base + ONE, 104.8, 105.0, 103.9, 104.9) | {"close_time_ms": base + 2 * ONE},
        ]
        future = candle(tl.t, 104.8, 105.0, 103.3, 104.9) | {"close_time_ms": tl.t + ONE}
        self.scan(tl.breakout_open + 2 * FIVE)
        self.scan(tl.t, fine=fine + [future])
        entries = self.state()["standalone_entries"]
        self.assertEqual(len(entries), 1)
        self.assertEqual(entries[0]["terms"]["confirmation"]["kind"], ms.CONFIRMATION_PIN_BAR)
        self.assertEqual(entries[0]["terms"]["source_timeframe"], "1")
        self.assertEqual(entries[0]["terms"]["confirmation"]["close_time_ms"], base + 2 * ONE)

    def test_flag_off_journals_the_confirmation_but_never_hands_off_or_admits(self):
        with mock.patch.dict(os.environ, {robot_l_shape.MIRROR_STANDALONE_ENV: "0"}):
            self.scan(self.timeline.breakout_open + 2 * FIVE)
            summary = self.scan(self.timeline.t)
            self.assertEqual(summary["standalone_handoffs"], [])
            self.assertEqual(self.state()["standalone_entries"][0]["handoff"], "OFF")
            self.assertFalse(self.candidates.exists() and any(self.candidates.iterdir()))
            snapshot = ms._standalone_snapshot(SYMBOL, self.state()["standalone_entries"][0]["terms"])
            robot_candidate_store.create_signal_snapshot(snapshot, timeframe="5", store_dir=self.candidates,
                                                         candidate_id="forced")
            with self.assertRaisesRegex(Exception, "MIRROR standalone Robot is not enabled"):
                admit_robot_candidate("forced", database_path=self.root / "x.sqlite3", store_dir=self.candidates)
        # Turning the flag on later never trades an old confirmation.
        self.assertEqual(self.scan(self.timeline.t)["standalone_handoffs"], [])

    def test_confirmation_without_engulfing_or_with_poor_rr_never_becomes_an_entry(self):
        tl = self.timeline
        tl.coarse[-3] = candle(tl.t - 3 * FIVE, 104.1, 105.2, 103.9, 105.0)   # opens above prior close: no Engulfing
        self.scan(tl.breakout_open + 2 * FIVE)
        self.assertEqual(self.scan(tl.t)["standalone_handoffs"], [])
        self.assertEqual(self.state().get("standalone_entries"), [])
        tl.coarse[-3] = candle(tl.t - 3 * FIVE, 103.95, 105.2, 101.0, 105.0)   # Engulfing, STOP far: RR < 2
        self.mirror_root = self.root / "mirror_rr"
        self.scan(tl.breakout_open + 2 * FIVE)
        self.scan(tl.t)
        self.assertEqual(self.state()["standalone_entries"], [])
        rejected = [r for r in self._events() if r["event"] == "mirror_entry_confirmation"]
        self.assertTrue(rejected and rejected[0]["rejection"].startswith("entry_net_rr_below_2"))

    def test_1m_confirmation_counts_independently_and_never_reads_beyond_the_tracked_candle(self):
        tl = self.timeline
        tl.coarse[-3] = candle(tl.t - 3 * FIVE, 104.1, 105.2, 103.9, 105.0)   # no 5m Engulfing
        base = tl.t - 4 * FIVE
        fine = [candle(base + i * ONE, *ohlc) | {"close_time_ms": base + (i + 1) * ONE} for i, ohlc in enumerate((
            (104.4, 104.5, 104.2, 104.3), (104.3, 104.35, 104.0, 104.05),       # bearish
            (104.0, 104.9, 103.98, 104.8),                                       # bullish Engulfing on 1m
        ))]
        late = candle(tl.t, 104.9, 104.95, 104.5, 104.6) | {"close_time_ms": tl.t + ONE}
        late_engulf = candle(tl.t + ONE, 104.5, 105.4, 104.4, 105.3) | {"close_time_ms": tl.t + 2 * ONE}
        self.scan(tl.breakout_open + 2 * FIVE)
        self.scan(tl.t, fine=fine + [late, late_engulf])
        entries = self.state()["standalone_entries"]
        self.assertEqual([e["terms"]["source_timeframe"] for e in entries], ["1"])
        self.assertEqual(entries[0]["terms"]["confirmation"]["close_time_ms"], base + 3 * ONE)

    def test_no_confirmation_after_the_first_retest(self):
        tl = self.timeline
        self.scan(tl.breakout_open + 2 * FIVE)
        tl.coarse[-4] = candle(tl.t - 4 * FIVE, 104.6, 110.2, 103.9, 104.0)   # touches 110 before the Engulfing
        self.scan(tl.t)
        self.assertEqual(self.state()["records"][self.level.level_id]["status"], "RETESTED")
        self.assertEqual(self.state()["standalone_entries"], [])

    def test_handoff_is_at_most_once_even_after_a_crash_between_marking_and_handoff(self):
        self.scan(self.timeline.breakout_open + 2 * FIVE)
        with mock.patch("pattern_robot_integration.prepare_robot_handoff",
                        side_effect=RuntimeError("crash during handoff")):
            with self.assertRaises(RuntimeError):
                self.scan(self.timeline.t)
        self.assertEqual(self.state()["standalone_entries"][0]["handoff"], "SENT")
        self.assertEqual(self.scan(self.timeline.t)["standalone_handoffs"], [])
        self.assertFalse(self.candidates.exists() and any(self.candidates.iterdir()))

    def _events(self):
        import json
        return [json.loads(line) for line in (self.mirror_root / "events.jsonl").read_text(encoding="utf-8")
                .splitlines() if line.strip()]


class MirrorStandaloneBudget(unittest.TestCase):
    """One campaign, one R0: standalone and Box-overlay attempts share the budget; no entry without a campaign."""

    def policy(self, wv="250"):
        return mirror.MirrorRobotPolicy(candles=None, account_risk_limit_usdt=lambda now: Decimal("1000"),
                                        quantity_step=lambda s: Decimal("0.1"), one_wv_usdt=lambda: Decimal(wv))

    def campaign(self):
        from geometry.naked_retest import Boundary
        return {"campaign_id": "lvl@1", "campaign_direction": "LONG", "boundary": Boundary.horizontal(
            "lvl", 110.0, as_of_time_ms=0), "state": {"phase": PHASE_CAMPAIGN_ACTIVE}, "parent_candidate_id": None}

    def plan(self, prior=(), campaign="default", wv="250"):
        return mirror.plan_standalone_attachment(
            self.policy(wv), direction="LONG", entry_price=Decimal("105.02"), stop_price=Decimal("103.89"),
            target_price=Decimal("110"), campaign=self.campaign() if campaign == "default" else campaign,
            prior_attempts=prior, now_ms=1)

    def test_no_campaign_after_retest_never_attaches(self):
        self.assertEqual(self.plan(campaign=None)["decision"], mirror.BLOCKED)
        self.assertEqual(self.plan(campaign=None)["reason"], "no_active_campaign")

    def test_first_attempt_freezes_r0_and_later_attempts_reuse_it(self):
        first = self.plan()
        self.assertEqual(first["decision"], mirror.ATTACHED)
        r0 = Decimal(first["r0_usdt"])
        self.assertAlmostEqual(float(r0), float(Decimal(first["remaining_net_reward_usdt"]) / 2), places=9)
        # While the first attempt is live its worst case already fills the budget: no parallel second R0.
        concurrent = self.plan(prior=[{"mirror": first, "closed": False, "net_pnl_usdt": None}])
        self.assertEqual(concurrent["decision"], mirror.BLOCKED)
        self.assertTrue(concurrent["reason"].startswith("campaign_gate_"))
        # After it ended without loss, the next attempt reuses the same frozen R0 (never a fresh budget).
        second = self.plan(prior=[{"mirror": first, "closed": True, "net_pnl_usdt": Decimal("0")}])
        self.assertEqual(second["decision"], mirror.ATTACHED)
        self.assertEqual(Decimal(second["r0_usdt"]), r0)

    def test_box_overlay_loss_in_the_same_campaign_consumes_the_standalone_budget(self):
        first = self.plan()
        box_attempt = {"strategy_id": mirror.STRATEGY_ID, "decision": mirror.ATTACHED, "campaign_id": "lvl@1",
                       "r0_usdt": first["r0_usdt"], "worst_case_usdt": "5"}
        exhausted = self.plan(prior=[{"mirror": box_attempt, "closed": True, "net_pnl_usdt": Decimal("-1000")}])
        self.assertEqual(exhausted["decision"], mirror.BLOCKED)
        self.assertTrue(exhausted["reason"].startswith("campaign_gate_"))

    def test_unknown_working_volume_defers_without_an_order(self):
        policy = replace(self.policy(), one_wv_usdt=lambda: None)
        out = mirror.plan_standalone_attachment(
            policy, direction="LONG", entry_price=Decimal("105.02"), stop_price=Decimal("103.89"),
            target_price=Decimal("110"), campaign=self.campaign(), prior_attempts=(), now_ms=1)
        self.assertEqual(out["decision"], mirror.DEFERRED)


if __name__ == "__main__":
    unittest.main()
