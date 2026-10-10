"""Real two-connection S3 contention; temporary SQLite and candidate files only."""

from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import patch

from terminal.application.robot_admission import admit_robot_candidate
from terminal.application.robot_autopilot_shadow import (
    SOURCE_SCANNER, admit_paper_auto_candidate, observe_shadow_candidate,
)
from terminal.application.robot_portfolio import collect_portfolio_facts
from terminal.domain.models import Symbol
from terminal.persistence.sqlite_store import SQLiteStore
from tests.test_robot_autopilot_shadow import ACCOUNT, TRADING_TABLES, _Db, _wedge


class AdmissionConcurrencyTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.path = self.root / "paper.sqlite3"
        self.db = _Db(self.root)
        self.addCleanup(self.db.store.close)

    def reserve(self, count):
        for index in range(count):
            self.db.store.create_robot_candidate(
                candidate_id=f"reserved-{index}", trading_account_id=ACCOUNT,
                symbol=Symbol(f"R{index}USDT"), status="APPROVED",
                signal_snapshot={"slot": index}, approved_at_ms=2000, updated_at_ms=2000,
            )

    def enable_auto(self):
        state = self.db.store.get_robot_autopilot_state(ACCOUNT)
        self.db.store.update_robot_autopilot_state(
            ACCOUNT, mode="PAPER_AUTO", expected_version=state.version,
            updated_at_ms=6000,
        )

    def auto(self, store, decision):
        return admit_paper_auto_candidate(
            store, ACCOUNT, allow_decision_id=decision.decision_id,
            source=SOURCE_SCANNER, protection_healthy=lambda: True,
            candidate_store_dir=self.db.candidates, clock_ms=lambda: 7000,
        )

    def race(self, first, second):
        """Hold first after BEGIN until second actually attempts BEGIN IMMEDIATE.

        Only connection acquisition is routed to pre-opened thread-owned stores
        so setup/migrations do not become the contended operation. Every query,
        transaction, policy, admission, audit and JSON write is production code.
        """
        ready = threading.Barrier(2)
        locked = threading.Event()
        attempted = threading.Event()
        local = threading.local()
        original_open = SQLiteStore.open
        trace = []
        errors = []
        connections = []

        def worker(index, operation):
            with original_open(self.path) as store:
                local.store = store
                connections.append(store._connection)
                begun = False
                held = False

                def observe(sql):
                    nonlocal begun, held
                    statement = sql.strip().upper()
                    if statement == "BEGIN IMMEDIATE":
                        begun = True
                        trace.append((index, "BEGIN"))
                        if index == 1:
                            attempted.set()
                    elif begun and statement.startswith("SELECT"):
                        trace.append((index, "READ"))
                        if index == 0 and not held:
                            held = True
                            locked.set()
                            if not attempted.wait(5):
                                errors.append("second connection never attempted BEGIN")
                    elif statement == "COMMIT":
                        trace.append((index, "COMMIT"))
                        begun = False

                store._connection.set_trace_callback(observe)
                ready.wait(timeout=10)
                if index == 1 and not locked.wait(5):
                    raise AssertionError("first connection never acquired its transaction")
                return operation(store)

        with patch.object(SQLiteStore, "open", side_effect=lambda *a, **k: local.store):
            with ThreadPoolExecutor(max_workers=2) as pool:
                futures = [pool.submit(worker, 0, first), pool.submit(worker, 1, second)]
                results = [future.result(timeout=20) for future in futures]
        self.assertFalse(errors, errors)
        self.assertIsNot(connections[0], connections[1])
        self.assertLess(trace.index((1, "BEGIN")), trace.index((0, "COMMIT")), trace)
        self.assertLess(trace.index((0, "COMMIT")), trace.index((1, "READ")), trace)
        return results

    def assert_capital_and_no_orders(self, occupied):
        facts = collect_portfolio_facts(self.db.store, ACCOUNT)
        self.assertTrue(facts["available"], facts)
        self.assertEqual(facts["occupied_ro"], occupied)
        for table in TRADING_TABLES:
            self.assertEqual(self.db.store._connection.execute(
                f"SELECT COUNT(*) FROM {table}"
            ).fetchone()[0], 0, table)

    def test_last_ro_reservation_then_canonical_admission(self):
        self.reserve(18)
        for index in range(2):
            _wedge(self.db.candidates, f"candidate-{index}", symbol=f"NEW{index}USDT")

        def selection(index):
            return lambda store: observe_shadow_candidate(
                store, ACCOUNT, source=SOURCE_SCANNER, candidate_ref=f"candidate-{index}",
                protection_healthy=lambda: True, candidate_store_dir=self.db.candidates,
                clock_ms=lambda: 5000,
            )

        winner, loser = self.race(selection(0), selection(1))
        self.assertEqual(winner.result.outcome, "ALLOW")
        self.assertEqual((loser.result.outcome, loser.result.reason_code),
                         ("WAIT", "PORTFOLIO_AGGREGATE_CAP"))
        self.assert_capital_and_no_orders(19)
        self.enable_auto()
        # Two simultaneous S3 deliveries of the winner must convert that RO once.
        first, second = self.race(
            lambda store: self.auto(store, winner.decision),
            lambda store: self.auto(store, winner.decision),
        )
        self.assertTrue(first.candidate_created)
        self.assertFalse(second.candidate_created)
        self.assertEqual(first.decision, second.decision)
        self.assertEqual(first.candidate.candidate_id, "candidate-0")
        self.assertIsNone(self.db.store.get_robot_candidate("candidate-1"))
        self.assertEqual(len(self.db.store.load_robot_candidates(ACCOUNT)), 19)
        self.assert_capital_and_no_orders(19)

    def same_candidate(self, manual_first):
        self.reserve(18)
        _wedge(self.db.candidates, "shared")
        allowed = self.db.observe("shared", health=lambda: True)
        self.assertEqual(allowed.result.outcome, "ALLOW")
        self.enable_auto()

        def manual(store):
            return admit_robot_candidate(
                "shared", database_path=self.path, store_dir=self.db.candidates,
                clock_ms=lambda: 7000,
            )

        def auto(store):
            return self.auto(store, allowed.decision)

        results = self.race(manual, auto) if manual_first else self.race(auto, manual)
        manual_result, auto_result = results if manual_first else results[::-1]
        self.assertEqual(int(manual_result[1]) + int(auto_result.candidate_created), 1)
        self.assertEqual(manual_result[0].candidate_id, "shared")
        if manual_first:
            self.assertEqual((auto_result.result.outcome, auto_result.result.reason_code),
                             ("WAIT", "ALREADY_ADMITTED"))
        else:
            self.assertEqual(auto_result.result.outcome, "ALLOW")
            self.assertEqual(auto_result.candidate.candidate_id, "shared")
        self.assertEqual(len(self.db.store.load_robot_candidates(ACCOUNT)), 19)
        self.assertEqual(len([d for d in self.db.decisions() if d.mode == "PAPER_AUTO"]), 1)
        self.assert_capital_and_no_orders(19)

    def test_manual_wins_same_candidate_race(self):
        self.same_candidate(manual_first=True)

    def test_auto_wins_same_candidate_race(self):
        self.same_candidate(manual_first=False)


if __name__ == "__main__":
    unittest.main()
