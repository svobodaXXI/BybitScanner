"""A3-R4 focused tests: Wedge source-terminal EXPIRED producer.

Synthetic frozen geometry in 1m index space (anchor index 10, apex index 20):
upper = 130 - i, lower = 90 + i. A Falling Wedge (LONG) breaks out on close > upper.
Temporary PAPER DB, candidate store and sidecar only; the candle loader is a stub.
"""
from pathlib import Path
import tempfile
import unittest
from unittest import mock

import pandas as pd

from robot_candidate_store import create_signal_snapshot
from terminal.application.robot_admission import candidate_snapshot_sha256
from terminal.application.robot_portfolio import collect_portfolio_facts
from terminal.application.wedge_source_terminal_producer import (
    BOX_RULE, MAX_KLINE_LIMIT, MAX_RANGE_PAGES, RULE, TAKE_RULE, FetchRotation, RangeLoadError,
    box_plan_terms, evaluate_box_first_grid_exit, evaluate_wedge_apex_expiry,
    evaluate_wedge_take_after_apex, load_closed_1m_range, producer_pass_lock,
    run_wedge_terminal_producer_once, wedge_retest_take,
)
from terminal.domain.models import OrderId, OrderSide, Symbol
from terminal.persistence.source_terminal_events import (
    append_source_terminal_event, load_terminal_identities, source_terminal_events_path,
)
from terminal.persistence.sqlite_store import RobotAutoDecisionRecord
from tests.runtime_replay import _box_plan_snapshot
from tests.test_robot_autopilot_shadow import _Db, ACCOUNT
from decimal import Decimal

T0 = 1_791_000_000_000  # anchor candle open time (multiple of one minute)
MIN = 60_000


def _snapshot(*, apex=20.0, cursor_index=10, pattern="Falling Wedge", cursor=True):
    snapshot = {
        "symbol": "WEDGEUSDT", "pattern": pattern,
        "robot_geometry": {
            "current_index": 10, "apex": {"index": apex, "valid_intersection": True},
            "upper_line": {"slope": -1.0, "intercept": 130.0},
            "lower_line": {"slope": 1.0, "intercept": 90.0},
        },
    }
    if cursor:
        snapshot["scanner_geometry_cursor"] = {
            "version": "1.0", "timeframe": "1", "geometry_index": cursor_index, "source_candle_time_ms": T0,
        }
    return snapshot


def _frame(closes, *, skip=(), forming=True):
    """Rows for minutes 1..len(closes) after the anchor, plus one still-forming row."""
    rows = [{"time": T0 + k * MIN, "high": close + 0.5, "low": close - 0.5, "close": close}
            for k, close in enumerate(closes, start=1) if k not in skip]
    if forming:
        rows.append({"time": T0 + (len(closes) + 1) * MIN, "high": 100.5, "low": 99.5, "close": 100.0})
    return pd.DataFrame(rows)


QUIET = [100.0] * 10  # indices 11..20: never above the upper boundary
BREAKOUT_NO_RETEST = [100.0] * 4 + [126.0] * 6  # breakout at 15, lows never back to upper


class EvaluateApexExpiryTests(unittest.TestCase):
    def test_apex_without_breakout_is_proven(self):
        evidence = evaluate_wedge_apex_expiry(_snapshot(), _frame(QUIET))
        self.assertIsNotNone(evidence)
        self.assertEqual(evidence["rule"], RULE)
        self.assertEqual((evidence["first_index"], evidence["apex_candle_index"]), (11, 20))
        self.assertEqual((evidence["from_time_ms"], evidence["to_time_ms"]), (T0 + MIN, T0 + 10 * MIN))
        self.assertEqual(evidence["candles"], 10)

    def test_breakout_before_apex_is_not_expiry(self):
        closes = list(QUIET)
        closes[4] = 126.0  # index 15: close 126 > upper 115
        self.assertIsNone(evaluate_wedge_apex_expiry(_snapshot(), _frame(closes)))

    def test_unretested_breakout_expires_at_apex(self):
        # index 15 closes above upper 115 and every later low stays above the boundary.
        evidence = evaluate_wedge_apex_expiry(_snapshot(), _frame(BREAKOUT_NO_RETEST))
        self.assertIsNotNone(evidence)
        self.assertEqual((evidence["breakout_index"], evidence["apex_candle_index"]), (15, 20))
        self.assertIsNone(evaluate_wedge_apex_expiry(_snapshot(), _frame(QUIET))["breakout_index"])

    def test_missing_candle_is_not_expiry(self):
        self.assertIsNone(evaluate_wedge_apex_expiry(_snapshot(), _frame(QUIET, skip={5})))

    def test_apex_candle_still_forming_is_not_expiry(self):
        # Only indices 11..19 are closed; the index-20 row is the newest (forming) one.
        self.assertIsNone(evaluate_wedge_apex_expiry(_snapshot(), _frame(QUIET[:9])))

    def test_invalid_or_ambiguous_cursor_is_not_expiry(self):
        self.assertIsNone(evaluate_wedge_apex_expiry(_snapshot(cursor=False), _frame(QUIET)))
        self.assertIsNone(evaluate_wedge_apex_expiry(_snapshot(cursor_index=11), _frame(QUIET)))

    def test_unsupported_pattern_is_not_expiry(self):
        self.assertIsNone(evaluate_wedge_apex_expiry(_snapshot(pattern="L-shape"), _frame(QUIET)))


class _ProducerCase(unittest.TestCase):
    """Temporary PAPER DB, candidate store and sidecar; no test methods of its own."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.db = _Db(self.root)
        self.store = self.db.store
        self.addCleanup(self.store.close)
        self.sidecar = source_terminal_events_path(self.store.path)
        self.loads = []

    def allow(self, ref, *, snapshot=None, account=ACCOUNT):
        envelope = create_signal_snapshot(snapshot or _snapshot(), timeframe="5", store_dir=self.db.candidates,
                                          candidate_id=ref, created_at="2026-10-10T00:00:00+00:00")
        sha = candidate_snapshot_sha256(envelope["signal_snapshot"])
        self.store.append_robot_auto_decision(RobotAutoDecisionRecord(
            decision_id=f"d-{ref}", trading_account_id=account, candidate_ref=ref, pattern="Falling Wedge",
            symbol=Symbol("WEDGEUSDT"), timeframe="5", source_identity=f"{ref}:{sha}", snapshot_sha256=sha,
            mode="SHADOW", policy_version="test", outcome="ALLOW", reason_code="ELIGIBLE",
            evaluated_at_ms=T0 + MIN, resulting_candidate_id=None))
        return sha

    def loader(self, frame):
        """Range stub: the rows of ``frame`` inside [start_ms, end_ms]."""
        def load(symbol, start_ms, end_ms):
            self.loads.append((symbol, start_ms, end_ms))
            return frame[(frame["time"] >= start_ms) & (frame["time"] <= end_ms)].reset_index(drop=True)
        return load

    def run_once(self, frame, now_ms=T0 + 12 * MIN, **kwargs):
        return run_wedge_terminal_producer_once(
            self.store.path, ACCOUNT, candidate_store_dir=self.db.candidates,
            candle_range_loader=self.loader(frame), now_ms=now_ms, **kwargs)

    def facts(self):
        with self.store.autopilot_decision_transaction():
            return collect_portfolio_facts(self.store, ACCOUNT)


class ProducerRunTests(_ProducerCase):
    def test_proven_expiry_appends_matching_identity_and_releases(self):
        sha = self.allow("w1")
        self.assertEqual(self.facts()["occupied_ro"], 1)
        self.assertEqual(self.run_once(_frame(QUIET)), {"w1": "APPENDED"})
        self.assertEqual(load_terminal_identities(self.sidecar, "paper"), frozenset({("w1", sha)}))
        self.assertEqual(self.facts()["occupied_ro"], 0)

    def test_repeat_is_idempotent_and_skips_network(self):
        self.allow("w1")
        self.run_once(_frame(QUIET))
        self.loads.clear()
        self.assertEqual(self.run_once(_frame(QUIET)), {"w1": "ALREADY_TERMINAL"})
        self.assertEqual(self.loads, [])

    def test_breakout_or_gap_appends_nothing(self):
        self.allow("w1")
        closes = list(QUIET)
        closes[4] = 126.0
        self.assertEqual(self.run_once(_frame(closes)), {"w1": "NOT_PROVEN"})
        self.assertEqual(self.run_once(_frame(QUIET, skip={3})), {"w1": "NOT_PROVEN"})
        self.assertFalse(self.sidecar.exists())

    def test_not_due_before_apex_does_not_fetch(self):
        self.allow("w1")
        self.assertEqual(self.run_once(_frame(QUIET), now_ms=T0 + 10 * MIN), {"w1": "NOT_DUE"})
        self.assertEqual(self.loads, [])

    def test_old_signal_is_proven_from_its_own_anchor_range(self):
        sha = self.allow("w1")
        late = T0 + (MAX_KLINE_LIMIT * 3) * MIN  # far beyond one latest-candles request
        self.assertEqual(self.run_once(_frame(QUIET), now_ms=late), {"w1": "APPENDED"})
        self.assertEqual(self.loads, [("WEDGEUSDT", T0 + MIN, T0 + 11 * MIN)])  # anchor+1 .. apex+1
        self.assertEqual(load_terminal_identities(self.sidecar, "paper"), frozenset({("w1", sha)}))

    def test_apex_range_beyond_page_bound_is_kept_without_fetch(self):
        far_apex = 10 + MAX_KLINE_LIMIT * MAX_RANGE_PAGES + 5
        self.allow("w1", snapshot=_snapshot(apex=float(far_apex)))
        late = T0 + (far_apex + 5) * MIN
        self.assertEqual(self.run_once(_frame(QUIET), now_ms=late), {"w1": "OUT_OF_REACH"})
        self.assertEqual(self.loads, [])

    def test_fetch_budget_defers_the_rest_of_the_pass(self):
        self.allow("w1")
        self.allow("w2")
        self.assertEqual(self.run_once(_frame(QUIET), max_fetches=1), {"w1": "APPENDED", "w2": "DEFERRED"})
        self.assertEqual(len(self.loads), 1)

    def test_fetch_budget_rotates_so_no_pending_wedge_starves(self):
        # SHADOW RUN #5: 16 pending Wedges, budget 5, every fetched signal NOT_PROVEN.
        refs = [f"w{n:02d}" for n in range(16)]
        for ref in refs:
            self.allow(ref)
        closes = list(QUIET)
        closes[4] = 126.0  # breakout before the apex: NOT_PROVEN, never EXPIRED
        rotation, checked = FetchRotation(), []
        for _pass in range(4):  # ceil(16 / 5) passes
            self.loads.clear()
            results = self.run_once(_frame(closes), max_fetches=5, fetch_rotation=rotation)
            proven = [ref for ref, status in results.items() if status == "NOT_PROVEN"]
            self.assertEqual(len(proven), 5)
            self.assertEqual(len(self.loads), 5)
            self.assertEqual(set(results.values()), {"NOT_PROVEN", "DEFERRED"})
            checked.extend(proven)
        self.assertEqual(set(checked), set(refs))
        self.assertFalse(self.sidecar.exists())  # NOT_PROVEN appends nothing
        self.assertEqual(self.facts()["occupied_ro"], 16)  # every reservation is kept

    def test_without_rotation_the_same_signals_take_the_budget(self):
        # The pre-fix behaviour a one-off pass (CLI) keeps: no cross-pass memory.
        for n in range(16):
            self.allow(f"w{n:02d}")
        closes = list(QUIET)
        closes[4] = 126.0
        checked = set()
        for _pass in range(4):
            results = self.run_once(_frame(closes), max_fetches=5)
            checked |= {ref for ref, status in results.items() if status == "NOT_PROVEN"}
        self.assertEqual(len(checked), 5)

    def test_rotation_restarts_from_the_beginning_for_an_unknown_cursor(self):
        self.allow("w1")
        self.allow("w2")
        rotation = FetchRotation()
        rotation.last_fetched = ("gone", "0" * 64)
        self.assertEqual(self.run_once(_frame(QUIET), max_fetches=1, fetch_rotation=rotation),
                         {"w1": "APPENDED", "w2": "DEFERRED"})
        self.assertEqual(rotation.last_fetched[0], "w1")
        self.assertEqual(self.run_once(_frame(QUIET), max_fetches=1, fetch_rotation=rotation),
                         {"w2": "APPENDED", "w1": "ALREADY_TERMINAL"})

    def test_concurrent_pass_is_refused(self):
        self.allow("w1")
        with producer_pass_lock(self.sidecar) as acquired:
            self.assertTrue(acquired)
            self.assertEqual(self.run_once(_frame(QUIET)), {})
        self.assertEqual(self.loads, [])
        self.assertEqual(self.run_once(_frame(QUIET)), {"w1": "APPENDED"})


    def test_snapshot_identity_mismatch_appends_nothing(self):
        self.allow("w1")
        other = Path(self.db.candidates) / "w1.json"
        payload = other.read_text(encoding="utf-8").replace('"WEDGEUSDT"', '"OTHERUSDT"', 1)
        other.write_text(payload, encoding="utf-8")
        self.assertEqual(self.run_once(_frame(QUIET)), {"w1": "IDENTITY_MISMATCH"})
        self.assertFalse(self.sidecar.exists())

    def test_physical_obligation_blocks_the_event_and_keeps_reservation(self):
        self.allow("w1")
        self.store.create_paper_limit(client_action_id="o", request_fingerprint="o", order_id=OrderId("o"),
            order_link_id="o", trading_account_id=ACCOUNT, symbol=Symbol("WEDGEUSDT"), side=OrderSide.BUY,
            price=Decimal(1), quantity=Decimal(125), created_at_ms=1)
        self.assertEqual(self.run_once(_frame(QUIET)), {"w1": "OBLIGATION_PENDING"})
        self.assertFalse(self.sidecar.exists())
        facts = self.facts()
        self.assertIn("shadow:w1", [r["identity"] for r in facts["reservations"]])
        self.assertEqual(facts["released_shadow_reservations"], [])

    def test_unproven_obligations_append_nothing(self):
        self.allow("w1")
        with mock.patch("terminal.application.wedge_source_terminal_producer.collect_portfolio_facts",
                        side_effect=RuntimeError("collector unavailable")):
            self.assertEqual(self.run_once(_frame(QUIET)), {"w1": "OBLIGATIONS_UNPROVEN"})
        self.assertFalse(self.sidecar.exists())

    def test_unretested_breakout_is_appended_and_releases(self):
        sha = self.allow("w1")
        self.assertEqual(self.run_once(_frame(BREAKOUT_NO_RETEST)), {"w1": "APPENDED"})
        self.assertEqual(load_terminal_identities(self.sidecar, "paper"), frozenset({("w1", sha)}))
        facts = self.facts()
        self.assertEqual((facts["occupied_ro"], len(facts["released_shadow_reservations"])), (0, 1))

    def test_breakout_then_retest_stays_reserved(self):
        self.allow("w1")
        closes = list(QUIET)
        closes[4] = 126.0  # BREAKOUT at 15, the index-16 low touches the boundary: RETEST
        self.assertEqual(self.run_once(_frame(closes)), {"w1": "NOT_PROVEN"})
        self.assertFalse(self.sidecar.exists())
        self.assertEqual(self.facts()["occupied_ro"], 1)

    def test_unreadable_sidecar_stops_the_run(self):
        self.allow("w1")
        self.sidecar.write_bytes(b"not a database")
        self.assertEqual(self.run_once(_frame(QUIET)), {})
        self.assertEqual(self.loads, [])


RETESTED = list(QUIET)
RETESTED[4] = 126.0  # BREAKOUT at 15 (close > upper 115), the index-16 low touches upper 114: RETEST
# frozen_take_90: reference 100, start_width 20 -> LONG target 120, TAKE 100 + 20 * 0.9 = 118.
PAIR_METRICS = {"reference_price": 100.0, "start_width": 20.0}


def _take_snapshot(**kwargs):
    snapshot = _snapshot(**kwargs)
    snapshot["geometry"] = {"pair_metrics": dict(PAIR_METRICS)}
    return snapshot


class EvaluateRetestTakeTests(unittest.TestCase):
    """SHADOW-RESERVE-1: BREAKOUT -> RETEST, then the frozen TAKE strictly after the apex candle."""

    APEX_OPEN = T0 + 10 * MIN  # index 20

    def test_take_after_apex_is_proven(self):
        retest = wedge_retest_take(_take_snapshot(), _frame(RETESTED))
        self.assertEqual((retest["breakout_index"], retest["retest_index"]), (15, 16))
        self.assertEqual(retest["take_price"], Decimal("118.0"))
        post = _frame(RETESTED + [100.0, 118.0])  # index 22 high 118.5 >= TAKE 118
        evidence = evaluate_wedge_take_after_apex(retest, post[post["time"] > self.APEX_OPEN], self.APEX_OPEN)
        self.assertEqual((evidence["rule"], evidence["outcome"]), (TAKE_RULE, "TAKE_REACHED_AFTER_APEX"))
        self.assertEqual(evidence["take_candle_time_ms"], T0 + 12 * MIN)

    def test_take_only_before_or_at_the_apex_is_not_proven(self):
        closes = list(RETESTED)
        closes[7] = 119.0  # index 18 reaches TAKE before the apex: an entry could still follow
        retest = wedge_retest_take(_take_snapshot(), _frame(closes))
        post = _frame(closes + [100.0, 100.0])
        self.assertIsNone(evaluate_wedge_take_after_apex(retest, post[post["time"] > self.APEX_OPEN],
                                                         self.APEX_OPEN))
        self.assertIsNone(evaluate_wedge_take_after_apex(retest, post, self.APEX_OPEN))  # not after apex

    def test_forming_row_never_proves_the_take(self):
        retest = wedge_retest_take(_take_snapshot(), _frame(RETESTED))
        post = _frame(RETESTED + [100.0], forming=False)
        post.loc[len(post)] = {"time": T0 + 12 * MIN, "high": 130.0, "low": 99.0, "close": 120.0}
        self.assertIsNone(evaluate_wedge_take_after_apex(retest, post[post["time"] > self.APEX_OPEN],
                                                         self.APEX_OPEN))

    def test_no_retest_or_no_frozen_take_is_not_a_retest_proof(self):
        self.assertIsNone(wedge_retest_take(_take_snapshot(), _frame(QUIET)))
        self.assertIsNone(wedge_retest_take(_take_snapshot(), _frame(BREAKOUT_NO_RETEST)))
        self.assertIsNone(wedge_retest_take(_snapshot(), _frame(RETESTED)))  # no pair_metrics

    def test_short_wedge_take_is_symmetric(self):
        closes = list(QUIET)
        closes[4], closes[5] = 80.0, 106.0  # close 80 < lower 105: BREAKOUT; high 106.5 >= 106: RETEST
        snapshot = _take_snapshot(pattern="Rising Wedge")
        retest = wedge_retest_take(snapshot, _frame(closes))
        self.assertEqual((retest["direction"], retest["take_price"]), ("SHORT", Decimal("82.0")))
        post = _frame(closes + [81.0, 100.0])  # index 21 low 80.5 <= TAKE 82
        evidence = evaluate_wedge_take_after_apex(retest, post[post["time"] > self.APEX_OPEN], self.APEX_OPEN)
        self.assertEqual(evidence["take_candle_time_ms"], T0 + 11 * MIN)


class RetestTakeProducerTests(_ProducerCase):
    def test_retest_then_take_after_apex_appends_and_releases(self):
        sha = self.allow("w1", snapshot=_take_snapshot())
        self.assertEqual(self.facts()["occupied_ro"], 1)
        frame = _frame(RETESTED + [100.0, 118.0, 100.0])
        self.assertEqual(self.run_once(frame, now_ms=T0 + 14 * MIN), {"w1": "APPENDED"})
        self.assertEqual(self.loads, [("WEDGEUSDT", T0 + MIN, T0 + 11 * MIN),
                                      ("WEDGEUSDT", T0 + 11 * MIN, T0 + 14 * MIN)])
        self.assertEqual(load_terminal_identities(self.sidecar, "paper"), frozenset({("w1", sha)}))
        facts = self.facts()
        self.assertEqual((facts["occupied_ro"], len(facts["released_shadow_reservations"])), (0, 1))

    def test_retest_without_take_after_apex_stays_reserved(self):
        self.allow("w1", snapshot=_take_snapshot())
        self.assertEqual(self.run_once(_frame(RETESTED + [100.0, 100.0]), now_ms=T0 + 13 * MIN),
                         {"w1": "NOT_PROVEN"})
        self.assertFalse(self.sidecar.exists())
        self.assertEqual(self.facts()["occupied_ro"], 1)


def _box_snapshot():
    snapshot = _box_plan_snapshot("BOXUSDT")  # LONG: P1 94, TAKE 99.2, STOP 89.6
    snapshot["decision_time_ms"] = T0
    return snapshot


def _box_frame(bars, *, skip=()):
    """(high, low) rows for minutes 1..len(bars) after the decision minute, plus a forming row."""
    rows = [{"time": T0 + k * MIN, "high": high, "low": low, "close": (high + low) / 2}
            for k, (high, low) in enumerate(bars, start=1) if k not in skip]
    rows.append({"time": T0 + (len(bars) + 1) * MIN, "high": 100.5, "low": 99.5, "close": 100.0})
    return pd.DataFrame(rows)


ABOVE = (100.5, 99.5)  # above P1 94 (and above TAKE 99.2 before any entry)
ENTRY = (95.0, 93.9)  # low touches P1 94
TAKE_BAR = (99.5, 95.0)  # high reaches TAKE 99.2
STOP_BAR = (94.0, 89.5)  # low reaches STOP 89.6


class EvaluateBoxExitTests(unittest.TestCase):
    def setUp(self):
        self.terms = box_plan_terms(_box_snapshot())

    def test_terms_come_from_the_frozen_plan(self):
        self.assertEqual((self.terms.direction, self.terms.entry_price, self.terms.take_price,
                          self.terms.stop_price, self.terms.start_ms),
                         ("LONG", Decimal("94"), Decimal("99.2"), Decimal("89.6"), T0 + MIN))

    def test_entry_then_take_or_stop(self):
        take = evaluate_box_first_grid_exit(self.terms, _box_frame([ABOVE, ENTRY, TAKE_BAR]))
        self.assertEqual((take["rule"], take["outcome"]), (BOX_RULE, "TAKE_REACHED"))
        self.assertEqual((take["entry_candle_time_ms"], take["exit_candle_time_ms"]), (T0 + 2 * MIN, T0 + 3 * MIN))
        stop = evaluate_box_first_grid_exit(self.terms, _box_frame([ABOVE, ENTRY, STOP_BAR]))
        self.assertEqual(stop["outcome"], "STOP_REACHED")

    def test_no_entry_ambiguous_bar_or_gap_is_not_proven(self):
        self.assertIsNone(evaluate_box_first_grid_exit(self.terms, _box_frame([ABOVE] * 5)))
        self.assertIsNone(evaluate_box_first_grid_exit(self.terms, _box_frame([ABOVE, (99.5, 93.9)])))
        self.assertIsNone(evaluate_box_first_grid_exit(self.terms, _box_frame([ABOVE, ENTRY, TAKE_BAR], skip={2})))
        self.assertIsNone(evaluate_box_first_grid_exit(self.terms, _box_frame([ABOVE, ENTRY])))  # exit forming

    def test_ambiguous_entry_bar_is_settled_by_a_later_exit(self):
        evidence = evaluate_box_first_grid_exit(self.terms, _box_frame([ABOVE, (99.5, 93.9), TAKE_BAR]))
        self.assertEqual(evidence["exit_candle_time_ms"], T0 + 3 * MIN)

    def test_inconsistent_plan_has_no_terms(self):
        snapshot = _box_snapshot()
        snapshot["plan"]["stop_price"] = "95"  # STOP inside the grid
        self.assertIsNone(box_plan_terms(snapshot))
        self.assertIsNone(box_plan_terms({**_box_snapshot(), "pattern": "Falling Wedge"}))


class BoxProducerTests(_ProducerCase):
    def allow_box(self, *, decision_id="d-box", sha=None):
        source, _ = self.store.save_box_plan_only(snapshot=_box_snapshot(), created_at_ms=T0)
        ref, sha = source.candidate_id, sha or source.snapshot_sha256
        self.store.append_robot_auto_decision(RobotAutoDecisionRecord(
            decision_id=decision_id, trading_account_id=ACCOUNT, candidate_ref=ref, pattern="IKIGAI_BOX",
            symbol=Symbol("BOXUSDT"), timeframe="5", source_identity=f"{ref}:{sha}", snapshot_sha256=sha,
            mode="SHADOW", policy_version="test", outcome="ALLOW", reason_code="ELIGIBLE",
            evaluated_at_ms=T0 + MIN, resulting_candidate_id=None))
        return ref, sha

    def test_box_take_after_entry_appends_and_releases(self):
        ref, sha = self.allow_box()
        self.assertEqual(self.facts()["occupied_ro"], 1)
        self.assertEqual(self.run_once(_box_frame([ABOVE, ENTRY, TAKE_BAR]), now_ms=T0 + 5 * MIN),
                         {ref: "APPENDED"})
        self.assertEqual(self.loads, [("BOXUSDT", T0 + MIN, T0 + 5 * MIN)])
        self.assertEqual(load_terminal_identities(self.sidecar, "paper"), frozenset({(ref, sha)}))
        self.assertEqual(self.facts()["occupied_ro"], 0)

    def test_box_without_proven_exit_stays_reserved(self):
        ref, _sha = self.allow_box()
        self.assertEqual(self.run_once(_box_frame([ABOVE, ENTRY, ENTRY]), now_ms=T0 + 4 * MIN),
                         {ref: "NOT_PROVEN"})
        self.assertEqual(self.run_once(_box_frame([ABOVE] * 3), now_ms=T0 + 4 * MIN), {ref: "NOT_PROVEN"})
        self.assertFalse(self.sidecar.exists())
        self.assertEqual(self.facts()["occupied_ro"], 1)

    def test_repeat_and_restart_release_once_without_refetch(self):
        ref, _sha = self.allow_box()
        self.allow_box(decision_id="d-box-repeat")  # a repeated ALLOW of the same frozen plan
        self.assertEqual(self.facts()["occupied_ro"], 1)
        frame = _box_frame([ABOVE, ENTRY, STOP_BAR])
        self.assertEqual(self.run_once(frame, now_ms=T0 + 5 * MIN), {ref: "APPENDED"})
        self.loads.clear()
        for rotation in (None, FetchRotation()):  # same process, then a restarted worker
            self.assertEqual(self.run_once(frame, now_ms=T0 + 5 * MIN, fetch_rotation=rotation),
                             {ref: "ALREADY_TERMINAL"})
        self.assertEqual(self.loads, [])
        facts = self.facts()
        self.assertEqual(facts["occupied_ro"], 0)
        self.assertEqual({item["candidate_ref"] for item in facts["released_shadow_reservations"]}, {ref})

    def test_historical_reservation_is_proven_from_its_own_decision_window(self):
        ref, _sha = self.allow_box()
        late = T0 + 5 * MAX_KLINE_LIMIT * MIN  # far beyond the bounded window
        self.assertEqual(self.run_once(_box_frame([ABOVE, ENTRY, TAKE_BAR]), now_ms=late), {ref: "APPENDED"})
        self.assertEqual(self.loads, [("BOXUSDT", T0 + MIN, T0 + MAX_RANGE_PAGES * MAX_KLINE_LIMIT * MIN)])

    def test_box_identity_mismatch_or_missing_source_appends_nothing(self):
        ref, _sha = self.allow_box(sha="f" * 64)
        self.assertEqual(self.run_once(_box_frame([ABOVE, ENTRY, TAKE_BAR]), now_ms=T0 + 5 * MIN),
                         {ref: "IDENTITY_MISMATCH"})
        self.assertEqual(self.loads, [])
        self.assertFalse(self.sidecar.exists())

    def test_box_physical_obligation_keeps_the_reservation(self):
        ref, _sha = self.allow_box()
        self.store.create_paper_limit(client_action_id="o", request_fingerprint="o", order_id=OrderId("o"),
            order_link_id="o", trading_account_id=ACCOUNT, symbol=Symbol("BOXUSDT"), side=OrderSide.BUY,
            price=Decimal(1), quantity=Decimal(125), created_at_ms=1)
        self.assertEqual(self.run_once(_box_frame([ABOVE, ENTRY, TAKE_BAR]), now_ms=T0 + 5 * MIN),
                         {ref: "OBLIGATION_PENDING"})
        self.assertFalse(self.sidecar.exists())


class _FakeKlines:
    """Bybit V5 get_kline stub: newest-first rows inside [start, end], at most ``limit``."""

    def __init__(self, first_ms, count, fail=False):
        self.rows = [[str(first_ms + k * MIN), "100", "100.5", "99.5", "100", "1", "1"] for k in range(count)]
        self.calls = []
        self.fail = fail

    def __call__(self, **kwargs):
        self.calls.append(kwargs)
        if self.fail:
            return {"retCode": 10006, "retMsg": "rate limit"}
        inside = [r for r in self.rows if kwargs["start"] <= int(r[0]) <= kwargs["end"]]
        return {"retCode": 0, "result": {"list": list(reversed(inside))[: kwargs["limit"]]}}


class RangeLoaderTests(unittest.TestCase):
    def test_paginates_in_bounded_windows_and_returns_ascending_rows(self):
        klines = _FakeKlines(T0, 2500)
        frame = load_closed_1m_range("WEDGEUSDT", T0, T0 + 2499 * MIN, get_kline=klines)
        self.assertEqual(len(klines.calls), 3)
        self.assertTrue(all(call["limit"] == MAX_KLINE_LIMIT and call["interval"] == "1"
                            and call["category"] == "linear" for call in klines.calls))
        self.assertEqual(list(frame["time"]), [T0 + k * MIN for k in range(2500)])

    def test_api_error_or_page_bound_raises(self):
        with self.assertRaises(RangeLoadError):
            load_closed_1m_range("WEDGEUSDT", T0, T0 + 10 * MIN, get_kline=_FakeKlines(T0, 11, fail=True))
        too_long = T0 + (MAX_KLINE_LIMIT * MAX_RANGE_PAGES) * MIN
        klines = _FakeKlines(T0, 1)
        with self.assertRaises(RangeLoadError):
            load_closed_1m_range("WEDGEUSDT", T0, too_long, get_kline=klines)
        self.assertEqual(klines.calls, [])


if __name__ == "__main__":
    unittest.main()
