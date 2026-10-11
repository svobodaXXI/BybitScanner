"""P0: A6 due-WAIT reevaluation is bounded per arrival. Temporary DBs only.

One arrival may reevaluate at most a small batch of due WAITs, oldest first, from
one consistent read set (audit, candidates, PAPER portfolio) inside one decision
transaction, with virtual RO reservations advanced after each SHADOW ALLOW. Due
WAITs beyond the batch stay due for the next arrival: nothing is skipped, nothing
is written twice and nothing becomes a trading object.
"""

import tempfile
import unittest
from pathlib import Path

from robot_candidate_store import load_candidate
from terminal.application import robot_autopilot_shadow as shadow
from terminal.application.robot_autopilot import (
    OUTCOME_ALLOW, OUTCOME_WAIT, REASON_ELIGIBLE, REASON_PORTFOLIO_AGGREGATE_CAP,
    REASON_PROTECTION_HEALTH_UNKNOWN, REASON_ROBOT_NOT_READY, REASON_SYMBOL_OWNED,
)
from terminal.application.robot_portfolio import collect_portfolio_facts
from terminal.persistence.sqlite_store import SQLiteStore
from tests.test_robot_autopilot_shadow import ACCOUNT, _Db, _wedge

MINUTE = 60_000
T0 = 100 * MINUTE + 5_000  # 1m source candle bucket 100
T1 = T0 + MINUTE
T2 = T0 + 2 * MINUTE
LIMIT = 8


class _Counting:
    """Count heavy whole-table reads made through the store during one arrival."""

    NAMES = ("load_robot_candidates", "load_robot_auto_decisions", "load_paper_portfolio_rows")

    def __init__(self, test):
        self.calls = dict.fromkeys(self.NAMES, 0)
        for name in self.NAMES:
            original = getattr(SQLiteStore, name)

            def counted(store, *args, _name=name, _original=original, **kwargs):
                self.calls[_name] += 1
                return _original(store, *args, **kwargs)

            setattr(SQLiteStore, name, counted)
            test.addCleanup(setattr, SQLiteStore, name, original)


class BoundedDueWaitBatchTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.db = _Db(Path(self.tmp.name))
        self.addCleanup(lambda: self.db.store.close())

    def seed_waits(self, count, *, symbols=None, health=None):
        """`count` WAITs recorded one by one inside candle T0, in arrival order."""
        refs = []
        for index in range(count):
            ref = f"w{index:03d}"
            symbol = symbols[index] if symbols else f"S{index:03d}USDT"
            _wedge(self.db.candidates, ref, symbol=symbol)
            observation = self.db.observe(ref, health=health, now=T0 + index)
            self.assertEqual(observation.result.outcome, OUTCOME_WAIT)
            refs.append(ref)
        return refs

    def arrive(self, ref, *, now, health=None, symbol=None):
        _wedge(self.db.candidates, ref, symbol=symbol or "ARRIVALUSDT")
        return self.db.observe(ref, health=health, now=now)

    def evaluated_at(self, now):
        return [d for d in self.db.decisions() if d.evaluated_at_ms == now]

    def test_480_due_waits_one_arrival_reevaluates_at_most_the_oldest_batch(self):
        refs = self.seed_waits(480)
        before = self.db.footprint()
        self.arrive("arrival-1", now=T1)
        at_t1 = self.evaluated_at(T1)
        # The batch, then the arrival itself; everything else stays due.
        self.assertEqual(sorted(d.candidate_ref for d in at_t1 if d.candidate_ref != "arrival-1"),
                         refs[:LIMIT])
        self.assertEqual(len(at_t1), LIMIT + 1)
        due_left = shadow._due_wait_refs(
            self.db.store.load_robot_auto_decisions(ACCOUNT),
            self.db.store.get_robot_autopilot_state(ACCOUNT),
            self.db.store.get_robot_runtime_state(ACCOUNT), T1,
        )
        self.assertEqual([ref for ref, _ in due_left], refs[LIMIT:])
        self.assertEqual(self.db.footprint(), before)

    def test_queue_advances_oldest_first_without_skips_duplicates_or_starvation(self):
        refs = self.seed_waits(40)
        order = []
        for n in range(6):  # 40 / 8 = 5 arrivals drain the candle; the 6th finds nothing
            seen = {d.decision_id for d in self.db.decisions()}
            self.arrive(f"a1-{n}", now=T1)
            new = [d for d in self.db.decisions()
                   if d.decision_id not in seen and d.candidate_ref.startswith("w")]
            order.extend(sorted(d.candidate_ref for d in new))
        self.assertEqual(order, refs)  # each WAIT exactly once, in arrival order
        # The next closed candle starts over from the oldest evaluation, still bounded.
        self.arrive("a2-0", now=T2)
        self.assertEqual(sorted(d.candidate_ref for d in self.evaluated_at(T2)
                                if d.candidate_ref.startswith("w")), refs[:LIMIT])

    def test_repeated_arrival_at_the_same_clock_is_idempotent(self):
        self.seed_waits(12)
        first = self.arrive("arrival-1", now=T1)
        second = self.db.observe("arrival-1", now=T1)
        self.assertEqual(second.decision, first.decision)
        self.assertFalse(second.created)
        ids = [d.decision_id for d in self.db.decisions()]
        self.assertEqual(len(ids), len(set(ids)))
        self.assertEqual(len(self.evaluated_at(T1)), 12 + 1)  # 8 + 4 more, then the arrival
        third = self.db.observe("arrival-1", now=T1)
        self.assertFalse(third.created)
        self.assertEqual(len(self.evaluated_at(T1)), 13)

    def test_one_consistent_read_set_per_arrival(self):
        self.seed_waits(40)
        counting = _Counting(self)
        self.arrive("arrival-1", now=T1)
        self.assertEqual(counting.calls, {"load_robot_candidates": 1,
                                          "load_robot_auto_decisions": 1,
                                          "load_paper_portfolio_rows": 1})

    def test_ro_is_spent_sequentially_with_increasing_audit_sequence(self):
        self.seed_waits(24)  # health unknown at T0
        for n in range(4):
            self.arrive(f"arrival-{n}", now=T1, health=lambda: True, symbol=f"A{n}USDT")
        batch = sorted(self.evaluated_at(T1), key=_sequence)
        sequences = [_sequence(d) for d in batch]
        self.assertEqual(sequences, list(range(sequences[0], sequences[0] + len(batch))))
        allowed = 0
        for decision in batch:
            facts = _portfolio(decision)
            self.assertEqual(facts["occupied_ro"], allowed)  # every earlier ALLOW reserved 1 RO
            if decision.outcome == OUTCOME_ALLOW:
                allowed += 1
            else:
                self.assertEqual(decision.reason_code, REASON_PORTFOLIO_AGGREGATE_CAP)
        self.assertEqual(allowed, 19)
        self.assertEqual(len(batch), 24 + 4)
        # arrival-2 closed the batch that spent the 19th RO incrementally in memory;
        # its recorded portfolio equals a fresh full collection of the final state.
        fresh = collect_portfolio_facts(self.db.store, ACCOUNT)
        self.assertEqual(fresh["occupied_ro"], 19)
        closing = _portfolio(next(d for d in batch if d.candidate_ref == "arrival-2"))
        closing.pop("audit_sequence")
        self.assertEqual(closing, fresh)

    def test_same_symbol_inside_one_batch_sees_the_earlier_virtual_reservation(self):
        self.seed_waits(2, symbols=["DUPUSDT", "DUPUSDT"])
        self.arrive("arrival-1", now=T1, health=lambda: True)
        outcomes = {d.candidate_ref: (d.outcome, d.reason_code) for d in self.evaluated_at(T1)}
        self.assertEqual(outcomes["w000"], (OUTCOME_ALLOW, REASON_ELIGIBLE))
        self.assertEqual(outcomes["w001"], (OUTCOME_WAIT, REASON_SYMBOL_OWNED))

    def test_risk_gates_are_read_fresh_for_every_arrival_and_candidate(self):
        self.seed_waits(16)
        calls = []

        def health():
            calls.append(1)
            return True

        self.arrive("arrival-1", now=T1, health=health)
        self.assertEqual(len(calls), LIMIT + 1)  # never cached across candidates
        store = self.db.store
        runtime = store.get_robot_runtime_state(ACCOUNT)
        store.update_robot_runtime_state(ACCOUNT, mode="ROBOT_STOPPED",
                                         recovery_status="ROBOT_STOPPED", reason=None,
                                         expected_version=runtime.version, updated_at_ms=T1 + 10)
        self.arrive("arrival-2", now=T1 + 20, health=health)
        later = self.evaluated_at(T1 + 20)
        self.assertEqual(len(later), LIMIT + 1)
        self.assertTrue(all(d.reason_code == REASON_ROBOT_NOT_READY for d in later))

    def test_time_budget_ends_the_batch_between_candidates(self):
        refs = self.seed_waits(12)
        ticks = iter(range(0, 10_000, 5))  # 5 s per reading: over budget after the first WAIT
        original = shadow._monotonic
        shadow._monotonic = lambda: float(next(ticks))
        self.addCleanup(setattr, shadow, "_monotonic", original)
        self.arrive("arrival-1", now=T1)
        at_t1 = self.evaluated_at(T1)
        self.assertEqual(sorted(d.candidate_ref for d in at_t1), sorted([refs[0], "arrival-1"]))
        for decision in at_t1:  # complete audit rows only
            self.assertTrue(decision.facts_json)
        shadow._monotonic = original
        self.arrive("arrival-2", now=T1)
        self.assertEqual(sorted(d.candidate_ref for d in self.evaluated_at(T1)
                                if d.candidate_ref.startswith("w")), refs[:1 + LIMIT])

    def test_a_broken_old_wait_never_blocks_the_batch_or_the_arrival(self):
        refs = self.seed_waits(4)
        (self.db.candidates / f"{refs[0]}.json").unlink()
        self.arrive("arrival-1", now=T1)
        evaluated = sorted(d.candidate_ref for d in self.evaluated_at(T1))
        self.assertEqual(evaluated, sorted([*refs[1:], "arrival-1"]))

    def test_trading_footprint_and_candidate_files_are_unchanged(self):
        refs = self.seed_waits(20)
        before = self.db.footprint()
        for n in range(3):
            self.arrive(f"arrival-{n}", now=T1, health=lambda: True, symbol=f"A{n}USDT")
        self.assertEqual(self.db.footprint(), before)
        for ref in refs:
            self.assertEqual(load_candidate(ref, store_dir=self.db.candidates)["status"], "AVAILABLE")


def _facts(decision):
    import json
    return json.loads(decision.facts_json)


def _portfolio(decision):
    return dict(_facts(decision)["portfolio_facts"])


def _sequence(decision):
    return _facts(decision)["portfolio_facts"]["audit_sequence"]


if __name__ == "__main__":
    unittest.main()
