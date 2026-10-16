"""FIX-3: exact Box lineage reads, full admission equivalence and real writer races."""
import copy
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from terminal.application import robot_autopilot_shadow as shadow
from terminal.domain.models import Symbol, TradingAccountId
from terminal.persistence.sqlite_store import SQLiteStore, SchemaError
from tests.test_box_plan_persistence import snapshot
from tests.test_robot_autopilot_shadow import ACCOUNT, _Db
from tests.test_robot_autopilot_bounded_admission import footprint
from tests import test_robot_autopilot_concurrency as concurrency

NOW = 1792116000000


def plan(store, index=0):
    data = snapshot()
    data["identity"]["a_time_ms"] += index
    return store.save_box_plan_only(snapshot=data, created_at_ms=3001)[0]


def arrive(db, source, store=None, fresh=True):
    return shadow.admit_arrived_auto_candidate(
        store or db.store, ACCOUNT, source=shadow.SOURCE_BOX_PLAN,
        candidate_ref=source.candidate_id, candidate_store_dir=db.candidates,
        clock_ms=lambda: NOW, protection_healthy=lambda: True,
        candidate_fresh=(None if fresh is None else lambda *_: fresh))


class BoxCandidateReadTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name) / "paper.sqlite3"
        self.db = _Db(Path(self.tmp.name), autopilot="PAPER_AUTO")
        self.addCleanup(self.db.store.close)
        self.source = plan(self.db.store)

    def linked(self, name, status="APPROVED", *, account=ACCOUNT, symbol="BTCUSDT", ref=None):
        store = self.db.store
        row, _ = store.create_robot_candidate(
            candidate_id=name, trading_account_id=account, symbol=Symbol(symbol),
            status="APPROVED", signal_snapshot={"id":name, "source_box_candidate_id":
                                               self.source.candidate_id if ref is None else ref},
            approved_at_ms=4000, updated_at_ms=4000)
        if status != "APPROVED":
            store._connection.execute("UPDATE robot_candidates SET status=? WHERE candidate_id=?",
                                      (status, name))
        return row

    def test_many_plans_keep_all_linked_statuses_symbols_and_account_isolation(self):
        store = self.db.store
        for index in range(1, 201):
            plan(store, index)
        with store.autopilot_decision_transaction():
            for status in ("APPROVED", "OPEN", "CLOSED", "EXPIRED", "INVALIDATED"):
                self.linked(status, status)
            self.linked("cross-symbol", symbol="OTHERUSDT")
            self.linked("foreign", account=TradingAccountId("foreign"))
            self.linked("unrelated", ref="another-source")
            full = store.load_robot_candidates(ACCOUNT)
            expected = tuple(r for r in full if r.status != "BOX_PLAN_ONLY"
                             and r.signal_snapshot.get("source_box_candidate_id") == self.source.candidate_id)
            with patch.object(store, "load_robot_candidates",
                              side_effect=AssertionError("full candidate read")):
                selected = store.load_robot_candidates_for_box_source(ACCOUNT, self.source.candidate_id)
                optimized = shadow._box_plan_candidate(store, self.source.candidate_id, ACCOUNT)
            original = shadow._box_plan_candidate(store, self.source.candidate_id, ACCOUNT, full)
        self.assertEqual(selected, expected)
        self.assertEqual(len(selected), 6)
        self.assertEqual(len(full), 208)
        self.assertEqual(optimized, original)
        self.assertTrue(optimized.invalidated)
        self.assertTrue(optimized.already_admitted)
        self.assertEqual(optimized.own_ids, {self.source.candidate_id, *(r.candidate_id for r in expected)})

    def test_absent_source_fails_before_lineage_read_or_audit(self):
        before = footprint(self.db.store)
        with patch.object(self.db.store, "load_robot_candidates_for_box_source",
                          side_effect=AssertionError("missing source must fail first")):
            with self.assertRaises(LookupError):
                shadow.admit_arrived_auto_candidate(
                    self.db.store, ACCOUNT, source=shadow.SOURCE_BOX_PLAN,
                    candidate_ref="missing", clock_ms=lambda: NOW)
        self.assertEqual(before, footprint(self.db.store))

    def test_corrupt_linked_snapshot_still_fails_closed_and_rolls_back(self):
        self.linked("corrupt")
        self.db.store._connection.execute(
            "UPDATE robot_candidates SET snapshot_sha256=? WHERE candidate_id='corrupt'", ("0" * 64,))
        before = footprint(self.db.store)
        for full in (False, True):
            with self.subTest(full=full), self.assertRaises(SchemaError):
                if full:
                    self.db.store.load_robot_candidates(ACCOUNT)
                else:
                    arrive(self.db, self.source)
        self.assertEqual(before, footprint(self.db.store))

    def test_full_admission_matches_fix2_including_repeat_and_protection_snapshot(self):
        for scenario in ("allow", "wait", "reject", "ambiguous", "linked", "terminal"):
            results = []
            for full in (True, False):
                with self.subTest(scenario=scenario, full=full), tempfile.TemporaryDirectory() as tmp:
                    db = _Db(Path(tmp), autopilot="PAPER_AUTO")
                    try:
                        source = plan(db.store)
                        for index in range(1, 41):
                            plan(db.store, index)
                        frozen = copy.deepcopy(source.signal_snapshot)
                        if scenario in ("linked", "terminal"):
                            target, _ = db.store.handoff_box_plan_to_robot(
                                source.candidate_id, symbol=source.symbol,
                                expected_snapshot_sha256=source.snapshot_sha256, approved_at_ms=4000)
                            if scenario == "terminal":
                                db.store.save_robot_candidate_state(
                                    target.candidate_id, status="INVALIDATED",
                                    robot_state={**target.robot_state, "phase":"INVALIDATED"},
                                    expected_revision=target.state_revision, updated_at_ms=5000)
                        if scenario == "ambiguous":
                            db.store._connection.execute(
                                "INSERT INTO trading_commands VALUES ('stuck','stuck','paper',"
                                "'linear','STUCKUSDT',0,'create_market','Buy','250',NULL,'1',"
                                "'terminal_manual','manual','submitting',2,NULL,1,2)")
                        loader = ((lambda account, ref: db.store.load_robot_candidates(account))
                                  if full else db.store.load_robot_candidates_for_box_source)
                        with patch.object(db.store, "load_robot_candidates_for_box_source", loader):
                            fresh = None if scenario == "wait" else scenario != "reject"
                            first = arrive(db, source, fresh=fresh)
                            after = footprint(db.store)
                            repeated = arrive(db, source, fresh=fresh)
                        self.assertEqual(first.decision, repeated.decision)
                        self.assertFalse(repeated.decision_created)
                        self.assertEqual(after, footprint(db.store))
                        self.assertEqual(db.store.get_robot_candidate(source.candidate_id).signal_snapshot, frozen)
                        expected = {"allow":"ALLOW", "reject":"REJECT", "terminal":"REJECT"}.get(scenario, "WAIT")
                        self.assertEqual(first.result.outcome, expected)
                        if first.candidate is not None:
                            self.assertEqual(first.candidate.signal_snapshot["plan"], frozen["plan"])
                            self.assertFalse(first.candidate.robot_state["execution_authorized"])
                        results.append((first.result, first.decision, after))
                    finally:
                        db.store.close()
            self.assertEqual(results[0], results[1], scenario)

    def test_concurrent_same_plan_admits_once(self):
        first, second = concurrency.AdmissionConcurrencyTests.race(
            self, lambda s: arrive(self.db, self.source, s),
            lambda s: arrive(self.db, self.source, s))
        self.assertTrue(first.candidate_created)
        self.assertFalse(second.candidate_created)
        self.assertEqual(first.decision, second.decision)
        self.assertEqual(self.db.store.count_robot_auto_decisions(ACCOUNT), 1)

    def test_concurrent_link_insert_is_seen_before_admission(self):
        def insert(store):
            return store.create_robot_candidate(
                candidate_id="late-link", trading_account_id=ACCOUNT, symbol=Symbol("OTHERUSDT"),
                status="APPROVED", signal_snapshot={"source_box_candidate_id":self.source.candidate_id},
                approved_at_ms=4000, updated_at_ms=4000)
        _inserted, admission = concurrency.AdmissionConcurrencyTests.race(
            self, insert, lambda s: arrive(self.db, self.source, s))
        self.assertEqual((admission.result.outcome, admission.result.reason_code),
                         ("WAIT", "ALREADY_ADMITTED"))
        self.assertFalse(admission.candidate_created)


if __name__ == "__main__":
    unittest.main()
