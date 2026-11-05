"""Autopilot PR-A: virtual SHADOW capital must not constrain physical PAPER_AUTO.

SHADOW ALLOW selections reserve virtual RO in the portfolio facts. They are audit
records of a rehearsal, never obligations, so PAPER_AUTO risk gates (aggregate
cap and one-controller-per-symbol) count only physical Robot/manual obligations.
SHADOW itself keeps counting both. Temporary databases only; no audit row is
changed or removed and no trading object is created by SHADOW.
"""

import json
import tempfile
import unittest
from decimal import Decimal
from pathlib import Path
from unittest import mock

from terminal.application.robot_autopilot import (
    OUTCOME_ALLOW, OUTCOME_WAIT, REASON_ELIGIBLE, REASON_PORTFOLIO_AGGREGATE_CAP,
    REASON_PORTFOLIO_DATA_UNAVAILABLE, REASON_SYMBOL_OWNED,
)
from terminal.application import robot_autopilot_shadow
from terminal.application.robot_autopilot_shadow import (
    PAPER_AUTO_MODE, SOURCE_SCANNER, admit_arrived_auto_candidate, admit_paper_auto_candidate,
)
from terminal.application.robot_portfolio import collect_portfolio_facts
from terminal.domain.models import Symbol
from tests.test_robot_autopilot_shadow import ACCOUNT, TRADING_TABLES, _Db, _wedge


# AUTOPILOT-DAILY-GATE-1: these fixtures use near-epoch clocks and injected fills that
# cannot prove a 00:00 MSK equity baseline. The daily-loss gate itself is covered by
# tests/test_robot_autopilot_daily_gate.py; here it is a proven, unblocked gate.
import unittest.mock as _daily_gate_mock  # noqa: E402

_OPEN_DAILY_GATE = _daily_gate_mock.patch(
    "terminal.application.robot_autopilot_shadow._daily_loss_gate",
    lambda *args, **kwargs: {"enabled": True, "latched": False, "data_available": True,
                             "business_date_msk": "fixture", "transition": None})


def setUpModule():
    _OPEN_DAILY_GATE.start()


def tearDownModule():
    _OPEN_DAILY_GATE.stop()

T_ENABLE = 1_000_000
T_ARRIVE = 2_000_000


def _healthy():
    return True


def _fresh(*_args):
    return True


class _Case(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.db = _Db(Path(self.tmp.name))  # durable mode starts as SHADOW
        self.addCleanup(lambda: self.db.store.close())
        self.shadow_refs = []

    # -- virtual capital -------------------------------------------------
    def shadow_allow(self, count, symbols=None):
        for index in range(count):
            ref = f"shadow-{index}"
            symbol = symbols[index] if symbols else f"SH{index}USDT"
            _wedge(self.db.candidates, ref, symbol=symbol)
            observed = self.db.observe(ref, health=_healthy, now=5000 + index)
            self.assertEqual(observed.result.outcome, OUTCOME_ALLOW, (index, observed.result))
            self.shadow_refs.append(ref)

    # -- physical capital ------------------------------------------------
    def physical_ideas(self, count, start=0):
        for index in range(start, start + count):
            self.db.store.create_robot_candidate(
                candidate_id=f"phys-{index}", trading_account_id=ACCOUNT,
                symbol=Symbol(f"PH{index}USDT"), status="APPROVED",
                signal_snapshot={"pattern": "Falling Wedge", "slot": index},
                approved_at_ms=2000 + index, updated_at_ms=2000 + index,
            )

    def manual_limit(self, symbol="MANLIMUSDT"):
        self.db.store._connection.execute(
            "INSERT INTO paper_limit_orders VALUES (?, ?, 'paper', ?, 'Buy', '2.5', '100', '0', "
            "'GTC', 'open', 1, 1)", ("manual-limit-1", "link-manual-limit-1", symbol))

    def manual_position(self, symbol="MANPOSUSDT"):
        self.db.store._connection.execute(
            "INSERT INTO position_projections VALUES ('paper','linear',?,0,'Long','100','2.5',"
            "'0','0','250','synced',1,1)", (symbol,))

    # -- PAPER_AUTO ------------------------------------------------------
    def enable_paper_auto(self):
        state = self.db.store.get_robot_autopilot_state(ACCOUNT)
        self.db.store.update_robot_autopilot_state(
            ACCOUNT, mode=PAPER_AUTO_MODE, expected_version=state.version,
            updated_at_ms=T_ENABLE)

    def arrive(self, ref, symbol, now=T_ARRIVE):
        _wedge(self.db.candidates, ref, symbol=symbol)
        return admit_arrived_auto_candidate(
            self.db.store, ACCOUNT, source=SOURCE_SCANNER, candidate_ref=ref,
            protection_healthy=_healthy, candidate_fresh=_fresh,
            candidate_store_dir=self.db.candidates, clock_ms=lambda: now)

    def audit(self):
        return tuple(self.db.store.load_robot_auto_decisions(ACCOUNT))

    def facts_of(self, admission):
        return json.loads(admission.decision.facts_json)["portfolio_facts"]

    def assertOutcome(self, admission, outcome, reason):
        self.assertEqual((admission.result.outcome, admission.result.reason_code), (outcome, reason),
                         admission.result)


class SeparationTests(_Case):
    def test_nineteen_shadow_ro_do_not_block_paper_auto_through_the_cap(self):
        self.shadow_allow(19)
        self.assertEqual(collect_portfolio_facts(self.db.store, ACCOUNT)["occupied_ro"], 19)
        history = self.audit()
        self.enable_paper_auto()

        admitted = self.arrive("real-1", "REAL1USDT")

        self.assertOutcome(admitted, OUTCOME_ALLOW, REASON_ELIGIBLE)
        self.assertTrue(admitted.candidate_created)
        self.assertEqual(self.db.store.get_robot_candidate("real-1").status, "APPROVED")
        facts = self.facts_of(admitted)
        self.assertEqual((facts["occupied_ro"], facts["occupied_usdt"]), (0, 0))
        self.assertEqual(facts["owned_symbols"], [])
        self.assertEqual(facts["isolated_shadow_ro"], 19)
        # Nothing virtual was removed or rewritten: the 19 reservations and the audit remain.
        self.assertEqual(self.audit()[:len(history)], history)
        after = collect_portfolio_facts(self.db.store, ACCOUNT)
        self.assertEqual(after["occupied_ro"], 20)
        self.assertEqual(sum(1 for r in after["reservations"] if r["identity"].startswith("shadow:")), 19)

    def test_a_shadow_reservation_on_the_same_symbol_does_not_own_the_symbol(self):
        self.shadow_allow(1, symbols=["SAMEUSDT"])
        self.enable_paper_auto()

        admitted = self.arrive("real-same", "SAMEUSDT")

        self.assertOutcome(admitted, OUTCOME_ALLOW, REASON_ELIGIBLE)
        self.assertEqual(self.facts_of(admitted)["owned_symbols"], [])
        self.assertEqual(self.db.store.get_robot_candidate("real-same").status, "APPROVED")


class PhysicalCapitalStillBlocksTests(_Case):
    def test_physical_robot_obligations_still_enforce_the_cap_with_shadow_noise(self):
        self.shadow_allow(19)
        self.physical_ideas(18)
        self.enable_paper_auto()

        nineteenth = self.arrive("real-19", "REAL19USDT")
        twentieth = self.arrive("real-20", "REAL20USDT", now=T_ARRIVE + 1)

        self.assertOutcome(nineteenth, OUTCOME_ALLOW, REASON_ELIGIBLE)
        self.assertEqual(self.facts_of(nineteenth)["occupied_ro"], 18)
        self.assertOutcome(twentieth, OUTCOME_WAIT, REASON_PORTFOLIO_AGGREGATE_CAP)
        self.assertEqual(self.facts_of(twentieth)["occupied_ro"], 19)
        self.assertIsNone(self.db.store.get_robot_candidate("real-20"))

    def test_physical_symbol_ownership_still_blocks(self):
        self.shadow_allow(1)
        self.physical_ideas(1)
        self.enable_paper_auto()
        blocked = self.arrive("real-owned", "PH0USDT")
        self.assertOutcome(blocked, OUTCOME_WAIT, REASON_SYMBOL_OWNED)
        self.assertIsNone(self.db.store.get_robot_candidate("real-owned"))

    def test_manual_working_limit_and_manual_position_still_count_and_own(self):
        self.shadow_allow(19)
        self.manual_limit("MANLIMUSDT")
        self.manual_position("MANPOSUSDT")
        self.physical_ideas(17)  # 17 ideas + 1 limit + 1 position = 19 physical RO
        self.enable_paper_auto()

        by_limit = self.arrive("real-limit", "MANLIMUSDT")
        by_position = self.arrive("real-position", "MANPOSUSDT", now=T_ARRIVE + 1)
        by_cap = self.arrive("real-cap", "CAPUSDT", now=T_ARRIVE + 2)

        self.assertOutcome(by_limit, OUTCOME_WAIT, REASON_SYMBOL_OWNED)
        self.assertOutcome(by_position, OUTCOME_WAIT, REASON_SYMBOL_OWNED)
        self.assertOutcome(by_cap, OUTCOME_WAIT, REASON_PORTFOLIO_AGGREGATE_CAP)
        self.assertEqual(self.facts_of(by_cap)["occupied_ro"], 19)
        self.assertEqual(self.facts_of(by_cap)["isolated_shadow_ro"], 19)

    def test_unavailable_portfolio_data_still_fails_closed(self):
        self.shadow_allow(2)
        self.enable_paper_auto()
        self.db.store._connection.execute(
            "INSERT INTO trading_commands VALUES ('cmd-stuck','link-stuck','paper','linear','STUCKUSDT',"
            "0,'create_market','Buy','250',NULL,'1','terminal_manual','manual','submitting',2,NULL,1,2)")
        blocked = self.arrive("real-blocked", "FREEUSDT")
        self.assertOutcome(blocked, OUTCOME_WAIT, REASON_PORTFOLIO_DATA_UNAVAILABLE)
        self.assertIsNone(self.db.store.get_robot_candidate("real-blocked"))


class FreshFactsReadReuseTests(_Case):
    """FIX-1: reuse only rows read inside the current admission transaction."""

    def test_fresh_facts_equal_full_collector_including_ambiguous_commands(self):
        self.shadow_allow(2)
        self.physical_ideas(2)
        self.manual_limit()
        self.manual_position()
        self.enable_paper_auto()
        _wedge(self.db.candidates, "fresh", symbol="FREEUSDT")
        store = self.db.store
        for ambiguous in (False, True):
            with self.subTest(ambiguous=ambiguous):
                if ambiguous:
                    store._connection.execute(
                        "INSERT INTO trading_commands VALUES ('cmd-stuck','link-stuck','paper',"
                        "'linear','STUCKUSDT',0,'create_market','Buy','250',NULL,'1',"
                        "'terminal_manual','manual','submitting',2,NULL,1,2)")
                with store.autopilot_decision_transaction():
                    candidate = robot_autopilot_shadow._resolve_candidate(
                        store, ACCOUNT, source=SOURCE_SCANNER, candidate_ref="fresh",
                        candidate_store_dir=self.db.candidates)
                    decisions = store.load_robot_auto_decisions(ACCOUNT)
                    kwargs = dict(mode=PAPER_AUTO_MODE, candidate=candidate, decisions=decisions,
                                  protection_healthy=_healthy, candidate_fresh=_fresh,
                                  now_ms=T_ARRIVE)
                    with mock.patch.object(
                        robot_autopilot_shadow, "collect_portfolio_facts",
                        side_effect=lambda s, a, **_: collect_portfolio_facts(s, a),
                    ):
                        before = robot_autopilot_shadow._fresh_facts(store, ACCOUNT, **kwargs)
                    with mock.patch.object(store, "load_robot_auto_decisions",
                                           side_effect=AssertionError("repeated decisions read")), \
                         mock.patch.object(store, "load_robot_candidates",
                                           side_effect=AssertionError("full candidate read")), \
                         mock.patch.object(store, "load_robot_candidates_for_portfolio",
                                           wraps=store.load_robot_candidates_for_portfolio) as views:
                        after = robot_autopilot_shadow._fresh_facts(store, ACCOUNT, **kwargs)
                    views.assert_called_once_with(ACCOUNT, plan_only_status="BOX_PLAN_ONLY")
                    self.assertEqual(after, before)
                    self.assertEqual(after.portfolio_facts["audit_sequence"], len(decisions) + 1)
                    self.assertEqual(after.portfolio_facts["available"], not ambiguous)
                    if ambiguous:
                        result = robot_autopilot_shadow.evaluate_auto_admission(after)
                        self.assertEqual((result.outcome, result.reason_code),
                                         (OUTCOME_WAIT, REASON_PORTFOLIO_DATA_UNAVAILABLE))

    def test_arrival_loads_bounded_decisions_once_and_never_loads_full_candidates(self):
        self.shadow_allow(2)
        self.enable_paper_auto()
        store = self.db.store
        with mock.patch.object(store, "load_robot_auto_decisions",
                               side_effect=AssertionError("full decision read")), \
             mock.patch.object(store, "load_robot_auto_decisions_for_admission",
                               wraps=store.load_robot_auto_decisions_for_admission) as decisions, \
             mock.patch.object(store, "load_robot_candidates",
                               side_effect=AssertionError("full candidate read")), \
             mock.patch.object(store, "load_robot_candidates_for_portfolio",
                               wraps=store.load_robot_candidates_for_portfolio) as views:
            admitted = self.arrive("fresh", "FREEUSDT")
        self.assertOutcome(admitted, OUTCOME_ALLOW, REASON_ELIGIBLE)
        self.assertEqual(decisions.call_count, 1)
        views.assert_called_once_with(ACCOUNT, plan_only_status="BOX_PLAN_ONLY")
        self.assertEqual(self.facts_of(admitted)["audit_sequence"], 3)


class ShadowBehaviorUnchangedTests(_Case):
    def test_shadow_still_counts_virtual_ro_and_hits_the_cap(self):
        self.shadow_allow(19)
        _wedge(self.db.candidates, "shadow-over", symbol="OVERUSDT")
        over = self.db.observe("shadow-over", health=_healthy, now=9000)
        self.assertOutcome(over, OUTCOME_WAIT, REASON_PORTFOLIO_AGGREGATE_CAP)
        facts = json.loads(over.decision.facts_json)["portfolio_facts"]
        self.assertEqual(facts["occupied_ro"], 19)
        self.assertNotIn("isolated_shadow_ro", facts)

    def test_shadow_still_treats_a_virtual_symbol_as_owned(self):
        self.shadow_allow(1, symbols=["SAMEUSDT"])
        _wedge(self.db.candidates, "shadow-again", symbol="SAMEUSDT")
        again = self.db.observe("shadow-again", health=_healthy, now=9000)
        self.assertOutcome(again, OUTCOME_WAIT, REASON_SYMBOL_OWNED)

    def test_the_collector_keeps_reporting_virtual_reservations(self):
        self.shadow_allow(3)
        facts = collect_portfolio_facts(self.db.store, ACCOUNT)
        self.assertEqual([r["identity"] for r in facts["reservations"]],
                         [f"shadow:shadow-{i}" for i in range(3)])
        self.assertEqual(facts["occupied_ro"], 3)
        self.assertEqual(self.db.footprint()[:len(TRADING_TABLES)], (0,) * len(TRADING_TABLES))


class S3ConversionTests(_Case):
    def convert(self, allow, now=T_ARRIVE):
        return admit_paper_auto_candidate(
            self.db.store, ACCOUNT, allow_decision_id=allow.decision.decision_id,
            source=SOURCE_SCANNER, protection_healthy=_healthy, candidate_fresh=_fresh,
            candidate_store_dir=self.db.candidates, clock_ms=lambda: now)

    def test_conversion_still_spends_its_own_ro_once_and_ignores_other_virtual_ro(self):
        _wedge(self.db.candidates, "convert-me", symbol="CONVUSDT")
        allow = self.db.observe("convert-me", health=_healthy, now=4000)
        self.shadow_allow(18)
        self.enable_paper_auto()

        converted = self.convert(allow)

        self.assertOutcome(converted, OUTCOME_ALLOW, REASON_ELIGIBLE)
        self.assertTrue(converted.candidate_created)
        self.assertEqual(converted.candidate.candidate_id, "convert-me")
        self.assertEqual(self.facts_of(converted)["occupied_ro"], 0)
        after = collect_portfolio_facts(self.db.store, ACCOUNT)
        self.assertEqual(after["occupied_ro"], 19)  # 18 virtual + 1 physical, own not doubled

    def test_conversion_still_fails_closed_without_exactly_one_matching_reservation(self):
        _wedge(self.db.candidates, "convert-lost", symbol="LOSTUSDT")
        allow = self.db.observe("convert-lost", health=_healthy, now=4000)
        self.shadow_allow(2)
        self.enable_paper_auto()

        real_collect = robot_autopilot_shadow.collect_portfolio_facts

        def without_own(store, account, **kwargs):
            # A consistent collector answer in which the matching reservation is missing.
            facts = real_collect(store, account, **kwargs)
            kept = [row for row in facts["reservations"] if row["identity"] != "shadow:convert-lost"]
            facts.update(
                reservations=kept,
                occupied_ro=sum(row["ro"] for row in kept),
                owned_symbols=sorted({row["symbol"] for row in kept}),
            )
            return facts

        with mock.patch.object(robot_autopilot_shadow, "collect_portfolio_facts", without_own):
            blocked = self.convert(allow)

        self.assertOutcome(blocked, OUTCOME_WAIT, REASON_PORTFOLIO_DATA_UNAVAILABLE)
        self.assertIsNone(self.db.store.get_robot_candidate("convert-lost"))


if __name__ == "__main__":
    unittest.main()
