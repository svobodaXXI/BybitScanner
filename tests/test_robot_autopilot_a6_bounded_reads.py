"""P0 RUN #3: an A6 SHADOW arrival reads bounded history with unchanged results. Temporary DBs only.

RUN #3 stalled the owner thread for 45 s: every arrival materialized the whole audit
table (multi-KB facts per row, one row per WAIT reevaluation) and every candidate
including frozen Box plans. The batch now reads the first/latest decision of each
idea plus every SHADOW ALLOW, and only the candidates the portfolio collector can
reach. These tests pin that the reduced read set yields the same decisions, facts
and audit sequence as the full one, and that no full history read remains.
"""

import json
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from terminal.application import robot_autopilot_shadow as shadow
from terminal.application.robot_autopilot import OUTCOME_ALLOW
from terminal.application.robot_portfolio import collect_portfolio_facts
from terminal.persistence import schema
from terminal.persistence import sqlite_store
from terminal.persistence.sqlite_store import SQLiteStore
from tests.test_robot_autopilot_shadow import ACCOUNT, _Db, _wedge

MINUTE = 60_000
T0 = 100 * MINUTE + 5_000  # 1m source candle bucket 100
IDEAS = 10
CANDLES = 6
HEADS_INDEX = "robot_auto_decisions_a6_heads"


def _build_history(root: Path) -> _Db:
    """WAIT ideas reevaluated over several closed candles, then an arrival with ALLOWs."""
    db = _Db(root)
    for index in range(IDEAS):
        ref = f"w{index:03d}"
        _wedge(db.candidates, ref, symbol=f"S{index:03d}USDT")
        db.observe(ref, now=T0 + index)  # health unknown -> WAIT
    for candle in range(1, CANDLES + 1):
        ref = f"a{candle}"
        _wedge(db.candidates, ref, symbol=f"A{candle}USDT")
        db.observe(ref, now=T0 + candle * MINUTE)
    _wedge(db.candidates, "allow-1", symbol="ALLOWUSDT")
    db.observe("allow-1", now=T0 + (CANDLES + 1) * MINUTE, health=lambda: True)
    return db


def _heads(store):
    return store.load_robot_auto_decision_heads(
        ACCOUNT, keep_mode=shadow.SHADOW_MODE, keep_outcome=OUTCOME_ALLOW)


def _row(decision):
    return (decision.decision_id, decision.candidate_ref, decision.outcome, decision.reason_code,
            decision.evaluated_at_ms, decision.facts_json)


class DecisionHeadsTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.db = _build_history(Path(self.tmp.name))
        self.addCleanup(lambda: self.db.store.close())
        self.store = self.db.store

    def test_heads_are_equivalent_for_every_a6_consumer(self):
        full = self.store.load_robot_auto_decisions(ACCOUNT)
        heads = _heads(self.store)
        self.assertLess(len(heads), len(full))  # history really is larger than the read set
        positions = {d.decision_id: i for i, d in enumerate(full)}
        self.assertEqual([positions[d.decision_id] for d in heads],
                         sorted(positions[d.decision_id] for d in heads))  # audit order kept
        ideas = {(d.candidate_ref, d.source_identity, d.mode) for d in full}
        for ref, identity, mode in ideas:  # latest decision per idea (dedupe / frozen facts)
            self.assertEqual(shadow._latest_decision(heads, ref, identity, mode),
                             shadow._latest_decision(full, ref, identity, mode))
        state = self.store.get_robot_autopilot_state(ACCOUNT)
        runtime = self.store.get_robot_runtime_state(ACCOUNT)
        for now in (T0 + MINUTE, T0 + (CANDLES + 2) * MINUTE, T0 + 50 * MINUTE):  # due order incl. ties
            self.assertEqual(shadow._due_wait_refs(heads, state, runtime, now),
                             shadow._due_wait_refs(full, state, runtime, now))
        allows = lambda rows: [d.decision_id for d in rows
                               if d.mode == shadow.SHADOW_MODE and d.outcome == OUTCOME_ALLOW]
        self.assertTrue(allows(full))
        self.assertEqual(allows(heads), allows(full))
        self.assertEqual(self.store.count_robot_auto_decisions(ACCOUNT), len(full))

    def test_portfolio_facts_equal_with_the_reduced_read_set(self):
        with self.store.autopilot_decision_transaction():
            full = collect_portfolio_facts(self.store, ACCOUNT)
            reduced = collect_portfolio_facts(
                self.store, ACCOUNT, auto_decisions=_heads(self.store),
                robot_candidates=self.store.load_robot_candidates_for_portfolio(
                    ACCOUNT, plan_only_status="BOX_PLAN_ONLY"))
        self.assertTrue(full["available"], full.get("data_error"))
        self.assertGreater(full["occupied_ro"], 0)  # SHADOW ALLOW reservations are counted
        self.assertEqual(reduced, full)

    def test_arrival_never_reads_the_full_history(self):
        full = self.store.load_robot_auto_decisions(ACCOUNT)
        groups = {(d.candidate_ref, d.source_identity, d.mode, d.policy_version) for d in full}
        allow_rows = sum(1 for d in full if d.outcome == OUTCOME_ALLOW)
        calls = {"load_robot_auto_decisions": 0, "load_robot_candidates": 0}
        loaded = []
        originals = {name: getattr(SQLiteStore, name) for name in calls}
        heads_original = SQLiteStore.load_robot_auto_decision_heads

        def counting(name):
            def wrapper(store, *args, **kwargs):
                calls[name] += 1
                return originals[name](store, *args, **kwargs)
            return wrapper

        def recording(store, *args, **kwargs):
            rows = heads_original(store, *args, **kwargs)
            loaded.append(len(rows))
            return rows

        _wedge(self.db.candidates, "late", symbol="LATEUSDT")
        with patch.object(SQLiteStore, "load_robot_auto_decisions", counting("load_robot_auto_decisions")), \
                patch.object(SQLiteStore, "load_robot_candidates", counting("load_robot_candidates")), \
                patch.object(SQLiteStore, "load_robot_auto_decision_heads", recording):
            self.db.observe("late", now=T0 + (CANDLES + 3) * MINUTE)
        self.assertEqual(calls, {"load_robot_auto_decisions": 0, "load_robot_candidates": 0})
        self.assertEqual(len(loaded), 1)
        self.assertLessEqual(loaded[0], 2 * len(groups) + allow_rows)  # bounded by ideas, not by history
        self.assertLess(loaded[0], len(full))

    def test_audit_sequence_counts_the_whole_audit(self):
        before = self.store.count_robot_auto_decisions(ACCOUNT)
        _wedge(self.db.candidates, "late", symbol="LATEUSDT")
        now = T0 + (CANDLES + 3) * MINUTE
        self.db.observe("late", now=now)
        written = sorted((d for d in self.store.load_robot_auto_decisions(ACCOUNT)
                          if d.evaluated_at_ms == now),
                         key=lambda d: json.loads(d.facts_json)["portfolio_facts"]["audit_sequence"])
        self.assertTrue(written)
        sequences = [json.loads(d.facts_json)["portfolio_facts"]["audit_sequence"] for d in written]
        self.assertEqual(sequences, list(range(before + 1, before + 1 + len(written))))


class ArrivalEquivalenceTests(unittest.TestCase):
    """The same arrival on identical histories writes byte-identical audit rows."""

    def test_reduced_and_full_read_sets_write_identical_decisions(self):
        results = []
        for reduced in (False, True):
            with tempfile.TemporaryDirectory() as tmp:
                db = _build_history(Path(tmp))
                try:
                    _wedge(db.candidates, "late", symbol="LATEUSDT")
                    now = T0 + (CANDLES + 3) * MINUTE
                    patches = [] if reduced else [
                        # Stable's batch: full audit and candidate tables.
                        patch.object(SQLiteStore, "load_robot_auto_decision_heads",
                                     lambda store, account, **_: store.load_robot_auto_decisions(account)),
                        patch.object(SQLiteStore, "load_robot_candidates_for_portfolio",
                                     lambda store, account, **_: store.load_robot_candidates(account)),
                    ]
                    for item in patches:
                        item.start()
                    try:
                        db.observe("late", now=now, health=lambda: True)
                    finally:
                        for item in patches:
                            item.stop()
                    results.append(sorted(_row(d) for d in db.decisions() if d.evaluated_at_ms == now))
                finally:
                    db.store.close()
        self.assertTrue(results[0])
        self.assertEqual(results[1], results[0])


class CandidateReadSetTests(unittest.TestCase):
    """Only Box plans nothing refers to are left out; order is unchanged."""

    def test_unreferenced_box_plans_are_the_only_rows_left_out(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = SQLiteStore.open(Path(tmp) / "paper.sqlite3")
            try:
                c = store._connection
                rows = [  # (id, status, approved_at_ms, snapshot)
                    ("robot-a", "APPROVED", 10, {"id": "a", "source_box_candidate_id": "plan-src"}),
                    ("plan-src", "BOX_PLAN_ONLY", None, {"id": "src"}),
                    ("plan-owned", "BOX_PLAN_ONLY", None, {"id": "owned"}),
                    ("plan-free-1", "BOX_PLAN_ONLY", None, {"id": "free-1"}),
                    ("plan-free-2", "BOX_PLAN_ONLY", None, {"id": "free-2"}),
                    ("closed-1", "CLOSED", 5, {"id": "closed"}),
                ]
                for index, (ref, status, approved, snapshot) in enumerate(rows):
                    c.execute("INSERT INTO robot_candidates VALUES (?,?,?,?,?,?,NULL,0,?,?)",
                              (ref, ACCOUNT.value, "BOXUSDT", status, json.dumps(snapshot),
                               f"{index:064x}", approved, 20))
                c.execute("INSERT INTO box_attempt_ownership VALUES ('plan-owned','paper','BOXUSDT',1,1,0,0,?)",
                          ("0" * 64,))
                c.execute("INSERT INTO box_order_ownership VALUES ('paper','slot-1','plan-owned','ENTRY',1)")
                # Forged plans are not canonical Box contracts; only identity and order matter here.
                with patch.object(sqlite_store, "_robot_candidate_from_row", lambda row: row["candidate_id"]):
                    full = list(store.load_robot_candidates(ACCOUNT))
                    reduced = list(store.load_robot_candidates_for_portfolio(
                        ACCOUNT, plan_only_status="BOX_PLAN_ONLY"))
                self.assertEqual(reduced, [ref for ref in full if not ref.startswith("plan-free")])
                self.assertIn("plan-src", reduced)    # handoff source
                self.assertIn("plan-owned", reduced)  # owns a Box order
            finally:
                store.close()


class DecisionReadIndexTests(unittest.TestCase):
    def test_open_creates_the_covering_index_once_without_a_version_bump(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "paper.sqlite3"
            SQLiteStore.open(path).close()
            statements: list[str] = []
            original = sqlite3.connect

            def recording(*args, **kwargs):
                connection = original(*args, **kwargs)
                connection.set_trace_callback(statements.append)
                return connection

            with patch.object(sqlite_store.sqlite3, "connect", recording):
                SQLiteStore.open(path).close()
            self.assertFalse([s for s in statements if "CREATE INDEX" in s.upper()])
            raw = original(path)
            try:
                version = raw.execute("PRAGMA user_version").fetchone()[0]
                names = {row[0] for row in raw.execute("SELECT name FROM sqlite_master WHERE type='index'")}
            finally:
                raw.close()
            self.assertEqual(version, schema.SCHEMA_VERSION)
            self.assertIn(HEADS_INDEX, names)

    def test_heads_are_found_through_the_covering_index(self):
        with tempfile.TemporaryDirectory() as tmp:
            db = _build_history(Path(tmp))
            try:
                statements: list[str] = []
                db.store._connection.set_trace_callback(statements.append)
                _heads(db.store)
                db.store._connection.set_trace_callback(None)
                sql = next(s for s in statements if "ROW_NUMBER" in s)
                plan = " | ".join(row[3] for row in db.store._connection.execute("EXPLAIN QUERY PLAN " + sql))
                self.assertIn(f"COVERING INDEX {HEADS_INDEX}", plan)
                self.assertNotIn("SCAN robot_auto_decisions", plan)
            finally:
                db.store.close()


if __name__ == "__main__":
    unittest.main()
