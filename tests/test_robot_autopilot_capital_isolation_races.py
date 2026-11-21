"""A3-RESERVE-1: SHADOW/PAPER_AUTO capital separation under races, repeats and restart.

Owner decision (2026-10-15): virtual SHADOW ALLOW reservations never block
PAPER_AUTO. The separation itself is #469 (``_physical_capital_only``); these
tests pin the remaining guarantees with a SHADOW portfolio saturated at 19 RO:
two different PAPER_AUTO arrivals racing for the last physical RO on two real
SQLite connections, a repeated arrival, and a store reopen. Temporary databases
and candidate files only; every policy, transaction and admission is production
code.
"""

import json
from pathlib import Path
import tempfile
import unittest
import unittest.mock as _daily_gate_mock

from terminal.application.robot_autopilot import (
    OUTCOME_ALLOW, OUTCOME_WAIT, REASON_ELIGIBLE, REASON_PORTFOLIO_AGGREGATE_CAP,
)
from terminal.application.robot_autopilot_shadow import (
    PAPER_AUTO_MODE, SOURCE_SCANNER, admit_arrived_auto_candidate,
)
from terminal.application.robot_portfolio import collect_portfolio_facts
from terminal.domain.models import Symbol
from terminal.persistence.sqlite_store import SQLiteStore
import tests.test_robot_autopilot_concurrency as concurrency
from tests.test_robot_autopilot_shadow import ACCOUNT, TRADING_TABLES, _Db, _wedge


# AUTOPILOT-DAILY-GATE-1: near-epoch fixture clocks cannot prove a 00:00 MSK
# baseline; the gate is covered by tests/test_robot_autopilot_daily_gate.py.
_OPEN_DAILY_GATE = _daily_gate_mock.patch(
    "terminal.application.robot_autopilot_shadow._daily_loss_gate",
    lambda *args, **kwargs: {"enabled": True, "latched": False, "data_available": True,
                             "business_date_msk": "fixture", "transition": None})


def setUpModule():
    _OPEN_DAILY_GATE.start()


def tearDownModule():
    _OPEN_DAILY_GATE.stop()


T_ARRIVE = 2_000_000


class SaturatedShadowPaperAutoTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.path = self.root / "paper.sqlite3"
        self.db = _Db(self.root)
        self.addCleanup(lambda: self.db.store.close())

    # Real two-connection contention, reused rather than duplicated.
    race = concurrency.AdmissionConcurrencyTests.race

    def saturate_shadow(self):
        for index in range(19):
            ref = f"shadow-{index}"
            _wedge(self.db.candidates, ref, symbol=f"SH{index}USDT")
            observed = self.db.observe(ref, health=lambda: True, now=5000 + index)
            self.assertEqual(observed.result.outcome, OUTCOME_ALLOW, (index, observed.result))
        self.assertEqual(collect_portfolio_facts(self.db.store, ACCOUNT)["occupied_ro"], 19)
        return tuple(self.db.decisions())

    def physical_ideas(self, count):
        for index in range(count):
            self.db.store.create_robot_candidate(
                candidate_id=f"phys-{index}", trading_account_id=ACCOUNT,
                symbol=Symbol(f"PH{index}USDT"), status="APPROVED",
                signal_snapshot={"pattern": "Falling Wedge", "slot": index},
                approved_at_ms=2000 + index, updated_at_ms=2000 + index,
            )

    def enable_paper_auto(self):
        state = self.db.store.get_robot_autopilot_state(ACCOUNT)
        self.db.store.update_robot_autopilot_state(
            ACCOUNT, mode=PAPER_AUTO_MODE, expected_version=state.version, updated_at_ms=6000)

    def arrive(self, store, ref, now=T_ARRIVE):
        return admit_arrived_auto_candidate(
            store, ACCOUNT, source=SOURCE_SCANNER, candidate_ref=ref,
            protection_healthy=lambda: True, candidate_fresh=lambda *_: True,
            candidate_store_dir=self.db.candidates, clock_ms=lambda: now)

    def assertOutcome(self, admission, outcome, reason):
        self.assertEqual((admission.result.outcome, admission.result.reason_code),
                         (outcome, reason), admission.result)

    def portfolio(self, admission):
        return json.loads(admission.decision.facts_json)["portfolio_facts"]

    def assert_shadow_history_intact(self, history, store=None):
        store = store or self.db.store
        self.assertEqual(tuple(store.load_robot_auto_decisions(ACCOUNT))[:len(history)], history)
        facts = collect_portfolio_facts(store, ACCOUNT)
        self.assertEqual(sum(1 for row in facts["reservations"]
                             if row["identity"].startswith("shadow:")), 19)

    def assert_no_orders(self, store=None):
        connection = (store or self.db.store)._connection
        for table in TRADING_TABLES:
            self.assertEqual(connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0],
                             0, table)

    def test_two_arrivals_race_for_the_last_physical_ro_under_saturated_shadow(self):
        history = self.saturate_shadow()
        self.physical_ideas(18)
        self.enable_paper_auto()
        _wedge(self.db.candidates, "real-a", symbol="REALAUSDT")
        _wedge(self.db.candidates, "real-b", symbol="REALBUSDT")

        first, second = self.race(
            lambda store: self.arrive(store, "real-a"),
            lambda store: self.arrive(store, "real-b", now=T_ARRIVE + 1),
        )

        # The serialized winner takes the last physical RO; virtual RO counted for neither.
        self.assertOutcome(first, OUTCOME_ALLOW, REASON_ELIGIBLE)
        self.assertTrue(first.candidate_created)
        self.assertEqual(self.portfolio(first)["occupied_ro"], 18)
        self.assertEqual(self.portfolio(first)["isolated_shadow_ro"], 19)
        self.assertOutcome(second, OUTCOME_WAIT, REASON_PORTFOLIO_AGGREGATE_CAP)
        self.assertFalse(second.candidate_created)
        self.assertEqual(self.portfolio(second)["occupied_ro"], 19)
        self.assertEqual(self.portfolio(second)["isolated_shadow_ro"], 19)
        self.assertEqual(self.db.store.get_robot_candidate("real-a").status, "APPROVED")
        self.assertIsNone(self.db.store.get_robot_candidate("real-b"))
        physical = [row for row in collect_portfolio_facts(self.db.store, ACCOUNT)["reservations"]
                    if not row["identity"].startswith("shadow:")]
        self.assertEqual(len(physical), 19)
        self.assert_shadow_history_intact(history)
        self.assert_no_orders()

    def test_repeated_arrival_never_spends_a_second_physical_ro(self):
        history = self.saturate_shadow()
        self.physical_ideas(18)
        self.enable_paper_auto()
        _wedge(self.db.candidates, "real-once", symbol="ONCEUSDT")

        admitted = self.arrive(self.db.store, "real-once")
        repeated = self.arrive(self.db.store, "real-once", now=T_ARRIVE + 1)

        self.assertOutcome(admitted, OUTCOME_ALLOW, REASON_ELIGIBLE)
        self.assertTrue(admitted.candidate_created)
        self.assertOutcome(repeated, OUTCOME_ALLOW, REASON_ELIGIBLE)
        self.assertFalse(repeated.decision_created)
        self.assertFalse(repeated.candidate_created)
        self.assertEqual(repeated.decision, admitted.decision)
        self.assertEqual(len([d for d in self.db.decisions() if d.mode == PAPER_AUTO_MODE]), 1)
        physical = [row for row in collect_portfolio_facts(self.db.store, ACCOUNT)["reservations"]
                    if not row["identity"].startswith("shadow:")]
        self.assertEqual(len(physical), 19)
        self.assert_shadow_history_intact(history)
        self.assert_no_orders()

    def test_restart_keeps_physical_only_counting_and_the_cap(self):
        history = self.saturate_shadow()
        self.physical_ideas(18)
        self.enable_paper_auto()
        _wedge(self.db.candidates, "after-restart-1", symbol="RESTART1USDT")
        _wedge(self.db.candidates, "after-restart-2", symbol="RESTART2USDT")
        self.db.store.close()

        with SQLiteStore.open(self.path) as reopened:
            self.assertEqual(reopened.get_robot_autopilot_state(ACCOUNT).mode, PAPER_AUTO_MODE)
            nineteenth = self.arrive(reopened, "after-restart-1")
        with SQLiteStore.open(self.path) as reopened:
            twentieth = self.arrive(reopened, "after-restart-2", now=T_ARRIVE + 1)
            self.assert_shadow_history_intact(history, reopened)
            self.assert_no_orders(reopened)
            self.assertIsNone(reopened.get_robot_candidate("after-restart-2"))

        self.assertOutcome(nineteenth, OUTCOME_ALLOW, REASON_ELIGIBLE)
        self.assertEqual(self.portfolio(nineteenth)["occupied_ro"], 18)
        self.assertOutcome(twentieth, OUTCOME_WAIT, REASON_PORTFOLIO_AGGREGATE_CAP)
        self.assertEqual(self.portfolio(twentieth)["occupied_ro"], 19)
        self.assertEqual(self.portfolio(twentieth)["isolated_shadow_ro"], 19)
        self.db.store = SQLiteStore.open(self.path)  # the cleanup closes a live store


if __name__ == "__main__":
    unittest.main()
