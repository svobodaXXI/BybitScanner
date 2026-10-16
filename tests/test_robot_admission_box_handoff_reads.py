"""FIX-4: exact source/lineage reads in the canonical Box handoff, FIX-3 equivalence and races."""
import tempfile
import unittest
from contextlib import ExitStack
from pathlib import Path
from unittest.mock import patch

from terminal.application import robot_admission as admission
from terminal.application import robot_autopilot_shadow as shadow
from terminal.domain.models import Symbol, TradingAccountId
from terminal.persistence.sqlite_store import SQLiteStore, SchemaError
from tests.test_robot_autopilot_shadow import ACCOUNT, _Db
from tests.test_robot_autopilot_bounded_admission import footprint
from tests.test_robot_autopilot_box_candidate_reads import NOW, arrive, plan
from tests import test_robot_autopilot_concurrency as concurrency

# FIX-3 reference: the handoff derived both reads from the whole candidate table.
FIX3_READS = {
    "load_robot_candidates_by_id_prefix": lambda self, account, prefix: tuple(
        r for r in self.load_robot_candidates(account) if r.candidate_id.startswith(prefix)),
    "load_robot_candidates_for_box_source": lambda self, account, ref: self.load_robot_candidates(account),
}


def reads(full):
    """FIX-3 reference reads, or FIX-4 reads with any whole-table read failing the test."""
    stack = ExitStack()
    if full:
        for name, fn in FIX3_READS.items():
            stack.enter_context(patch.object(SQLiteStore, name, fn))
    else:
        stack.enter_context(patch.object(SQLiteStore, "load_robot_candidates",
                                         side_effect=AssertionError("full candidate read")))
    return stack


def link(store, name, source, status="APPROVED", *, account=ACCOUNT, symbol="BTCUSDT"):
    store.create_robot_candidate(
        candidate_id=name, trading_account_id=account, symbol=Symbol(symbol), status="APPROVED",
        signal_snapshot={"id": name, "source_box_candidate_id": source.candidate_id},
        approved_at_ms=4000, updated_at_ms=4000)
    if status != "APPROVED":
        store._connection.execute("UPDATE robot_candidates SET status=? WHERE candidate_id=?",
                                  (status, name))


def tap(db, source, **kwargs):
    """Owner tap: admit_robot_candidate opens and owns its store and transaction."""
    return admission.admit_robot_candidate(
        admission.box_plan_admission_handle(source.candidate_id),
        database_path=db.store.path, clock_ms=lambda: NOW, **kwargs)


def outcome(call):
    try:
        record, created = call()
    except Exception as error:  # the class and message are part of the contract
        return ("raised", type(error).__name__, str(error))
    return ("returned", record, created)


def _ambiguous_prefix(db, source):
    db.store.create_robot_candidate(
        candidate_id=admission._box_plan_source_prefix(
            admission.box_plan_admission_handle(source.candidate_id)) + "-other",
        trading_account_id=ACCOUNT, symbol=Symbol("BTCUSDT"), status="APPROVED",
        signal_snapshot={"id": "prefix-collision"}, approved_at_ms=4000, updated_at_ms=4000)


def _foreign_prefix(db, source):
    db.store.create_robot_candidate(
        candidate_id=admission._box_plan_source_prefix(
            admission.box_plan_admission_handle(source.candidate_id)) + "-foreign",
        trading_account_id=TradingAccountId("foreign"), symbol=Symbol("BTCUSDT"), status="APPROVED",
        signal_snapshot={"id": "foreign-prefix"}, approved_at_ms=4000, updated_at_ms=4000)


def _same_symbol_owner(db, source):
    other = db.plans[7]
    link(db.store, "box-robot-owner", other, "OPEN")


def _robot_stopped(db, source):
    state = db.store.get_robot_runtime_state(ACCOUNT)
    db.store.update_robot_runtime_state(ACCOUNT, mode="ROBOT_STOPPED", recovery_status="ROBOT_STOPPED",
                                        reason=None, expected_version=state.version, updated_at_ms=1002)


TAP_SCENARIOS = {
    "new": lambda db, source: None,
    "linked_active": lambda db, source: link(db.store, "linked", source),
    "linked_terminal": lambda db, source: link(db.store, "linked", source, "INVALIDATED"),
    "linked_closed_cross_symbol": lambda db, source: link(db.store, "linked", source, "CLOSED",
                                                          symbol="OTHERUSDT"),
    "two_linked": lambda db, source: (link(db.store, "linked-a", source),
                                      link(db.store, "linked-b", source, "EXPIRED")),
    "foreign_linked_ignored": lambda db, source: link(db.store, "foreign-link", source,
                                                      account=TradingAccountId("foreign")),
    "ambiguous_prefix": _ambiguous_prefix,
    "foreign_prefix_ignored": _foreign_prefix,
    "same_symbol_owner": _same_symbol_owner,
    "robot_not_ready": _robot_stopped,
}


class BoxHandoffReadTests(unittest.TestCase):
    PLANS = 300

    def build(self, tmp):
        db = _Db(Path(tmp), autopilot="PAPER_AUTO")
        db.plans = [plan(db.store, index) for index in range(self.PLANS)]  # all on BTCUSDT
        return db

    def test_prefix_read_equals_full_read_filter(self):
        with tempfile.TemporaryDirectory() as tmp:
            db = self.build(tmp)
            try:
                _ambiguous_prefix(db, db.plans[3])
                _foreign_prefix(db, db.plans[3])
                full = db.store.load_robot_candidates(ACCOUNT)
                for source in (db.plans[0], db.plans[3], db.plans[-1]):
                    for prefix in (source.candidate_id, source.candidate_id[:49], "box-plan-", "box-"):
                        with self.subTest(prefix=prefix), reads(full=False):
                            self.assertEqual(
                                db.store.load_robot_candidates_by_id_prefix(ACCOUNT, prefix),
                                tuple(r for r in full if r.candidate_id.startswith(prefix)))
                with reads(full=False):
                    self.assertEqual(len(db.store.load_robot_candidates_by_id_prefix(
                        ACCOUNT, admission._box_plan_source_prefix(
                            admission.box_plan_admission_handle(db.plans[3].candidate_id)))), 2)
                    self.assertEqual(db.store.load_robot_candidates_by_id_prefix(ACCOUNT, "zzz"), ())
                    with self.assertRaises(ValueError):
                        db.store.load_robot_candidates_by_id_prefix(ACCOUNT, "")
                # The read is a primary-key range, never a visit of the whole account.
                statements = []
                db.store._connection.set_trace_callback(statements.append)
                try:
                    db.store.load_robot_candidates_by_id_prefix(ACCOUNT, db.plans[3].candidate_id[:49])
                finally:
                    db.store._connection.set_trace_callback(None)
                plan_rows = db.store._connection.execute(
                    "EXPLAIN QUERY PLAN " + statements[-1]).fetchall()
                self.assertTrue(any("USING PRIMARY KEY" in row[-1] for row in plan_rows), plan_rows)
                self.assertFalse(any("robot_candidates_account" in row[-1] for row in plan_rows),
                                 plan_rows)
            finally:
                db.store.close()

    def test_owner_tap_matches_fix3_for_every_scenario_and_repeat(self):
        kinds = {}
        for name, prepare in TAP_SCENARIOS.items():
            results = []
            for full in (True, False):
                with self.subTest(scenario=name, full=full), tempfile.TemporaryDirectory() as tmp:
                    db = self.build(tmp)
                    try:
                        source = db.plans[3]
                        prepare(db, source)
                        before = footprint(db.store)
                        with reads(full):
                            first = outcome(lambda: tap(db, source))
                            after = footprint(db.store)
                            repeated = outcome(lambda: tap(db, source))
                            stale = outcome(lambda: tap(db, source, expected_snapshot_sha256="0" * 64))
                        self.assertEqual(after, footprint(db.store))  # repeat writes nothing
                        if first[0] == "returned":
                            self.assertEqual(repeated, (first[0], first[1], False))
                            if first[2]:  # a new linked candidate never authorizes execution
                                self.assertFalse(first[1].robot_state["execution_authorized"])
                                self.assertEqual(first[1].signal_snapshot["plan"],
                                                 source.signal_snapshot["plan"])
                        else:
                            self.assertEqual(before, after)
                            self.assertEqual(repeated, first)
                        self.assertEqual(stale[0], "raised")
                        results.append((first, repeated, stale, before, after))
                    finally:
                        db.store.close()
            self.assertEqual(results[0], results[1], name)
            first = results[1][0]
            kinds[name] = first[0] if first[0] == "raised" else ("created" if first[2] else "existing")
        # The matrix really covers creation, idempotent return and each rejection.
        self.assertEqual(kinds, {
            "new": "created", "linked_active": "existing", "linked_terminal": "existing",
            "linked_closed_cross_symbol": "existing", "two_linked": "raised",
            "foreign_linked_ignored": "created", "ambiguous_prefix": "raised",
            "foreign_prefix_ignored": "created", "same_symbol_owner": "raised",
            "robot_not_ready": "raised"})

    def test_absent_source_rejected_without_writes(self):
        with tempfile.TemporaryDirectory() as tmp:
            db = self.build(tmp)
            try:
                before = footprint(db.store)
                with reads(full=False), self.assertRaises(admission.RobotAdmissionRejected):
                    admission.admit_robot_candidate("bp-" + "0" * 40, database_path=db.store.path,
                                                    clock_ms=lambda: NOW)
                self.assertEqual(before, footprint(db.store))
            finally:
                db.store.close()

    def test_paper_auto_admission_matches_fix3_with_no_full_candidate_read(self):
        for scenario in ("allow", "wait", "reject", "ambiguous", "linked", "terminal", "owner"):
            results = []
            for full in (True, False):
                with self.subTest(scenario=scenario, full=full), tempfile.TemporaryDirectory() as tmp:
                    db = self.build(tmp)
                    try:
                        source = db.plans[3]
                        if scenario == "linked":
                            link(db.store, "linked", source)
                        if scenario == "terminal":
                            link(db.store, "linked", source, "INVALIDATED")
                        if scenario == "owner":
                            _same_symbol_owner(db, source)
                        if scenario == "ambiguous":
                            db.store._connection.execute(
                                "INSERT INTO trading_commands VALUES ('stuck','stuck','paper',"
                                "'linear','STUCKUSDT',0,'create_market','Buy','250',NULL,'1',"
                                "'terminal_manual','manual','submitting',2,NULL,1,2)")
                        fresh = None if scenario == "wait" else scenario != "reject"
                        with reads(full):
                            first = arrive(db, source, fresh=fresh)
                            after = footprint(db.store)
                            repeated = arrive(db, source, fresh=fresh)
                        self.assertEqual(first.decision, repeated.decision)
                        self.assertFalse(repeated.decision_created)
                        self.assertEqual(after, footprint(db.store))
                        expected = {"allow": "ALLOW", "reject": "REJECT", "terminal": "REJECT"}
                        self.assertEqual(first.result.outcome, expected.get(scenario, "WAIT"))
                        if first.candidate is not None:
                            self.assertFalse(first.candidate.robot_state["execution_authorized"])
                            self.assertEqual(first.candidate.signal_snapshot["plan"],
                                             source.signal_snapshot["plan"])
                        results.append((first.result, first.decision, first.candidate,
                                        first.candidate_created, after))
                    finally:
                        db.store.close()
            self.assertEqual(results[0], results[1], scenario)

    def test_corrupt_linked_row_fails_closed_and_rolls_back_both_paths(self):
        with tempfile.TemporaryDirectory() as tmp:
            db = self.build(tmp)
            try:
                source = db.plans[3]
                link(db.store, "corrupt", source, "CLOSED")
                db.store._connection.execute(
                    "UPDATE robot_candidates SET snapshot_sha256=? WHERE candidate_id='corrupt'",
                    ("0" * 64,))
                before = footprint(db.store)
                with reads(full=False):
                    with self.assertRaises(SchemaError):
                        tap(db, source)
                    with self.assertRaises(SchemaError):
                        arrive(db, source)
                self.assertEqual(before, footprint(db.store))
            finally:
                db.store.close()

    def test_error_after_handoff_rolls_back_candidate_and_audit(self):
        with tempfile.TemporaryDirectory() as tmp:
            db = self.build(tmp)
            try:
                before = footprint(db.store)
                with reads(full=False), patch.object(
                        shadow, "record_auto_decision", side_effect=RuntimeError("audit failed")):
                    with self.assertRaises(RuntimeError):
                        arrive(db, db.plans[3])
                self.assertEqual(before, footprint(db.store))
                with reads(full=False):
                    admitted = arrive(db, db.plans[3])
                self.assertTrue(admitted.candidate_created)
            finally:
                db.store.close()


class BoxHandoffRaceTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name) / "paper.sqlite3"
        self.db = _Db(Path(self.tmp.name), autopilot="PAPER_AUTO")
        self.addCleanup(self.db.store.close)
        self.plans = [plan(self.db.store, index) for index in range(60)]
        self.source = self.plans[3]

    def test_two_connections_admit_one_plan_once(self):
        with reads(full=False):
            first, second = concurrency.AdmissionConcurrencyTests.race(
                self, lambda s: arrive(self.db, self.source, s),
                lambda s: arrive(self.db, self.source, s))
        self.assertTrue(first.candidate_created)
        self.assertFalse(second.candidate_created)
        self.assertEqual(first.decision, second.decision)
        self.assertEqual(self.db.store.count_robot_auto_decisions(ACCOUNT), 1)
        linked = self.db.store.load_robot_candidates_for_box_source(ACCOUNT, self.source.candidate_id)
        self.assertEqual(linked, (first.candidate,))

    def test_committed_prefix_collision_is_seen_and_admission_rolls_back(self):
        prefix = admission._box_plan_source_prefix(
            admission.box_plan_admission_handle(self.source.candidate_id))

        def collide(store):
            return store.create_robot_candidate(
                candidate_id=prefix + "-late", trading_account_id=ACCOUNT, symbol=Symbol("OTHERUSDT"),
                status="APPROVED", signal_snapshot={"id": "late"}, approved_at_ms=4000,
                updated_at_ms=4000)

        def admit(store):
            try:
                return arrive(self.db, self.source, store)
            except admission.RobotAdmissionRejected as error:
                return error

        with reads(full=False):
            before = footprint(self.db.store)
            _inserted, result = concurrency.AdmissionConcurrencyTests.race(self, collide, admit)
        self.assertIsInstance(result, admission.RobotAdmissionRejected)
        after = footprint(self.db.store)
        self.assertEqual(len(after["robot_candidates"]), len(before["robot_candidates"]) + 1)
        self.assertEqual(after["robot_auto_decisions"], before["robot_auto_decisions"])
        self.assertEqual(self.db.store.load_robot_candidates_for_box_source(
            ACCOUNT, self.source.candidate_id), ())


if __name__ == "__main__":
    unittest.main()
