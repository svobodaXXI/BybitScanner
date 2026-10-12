"""P0 A6 variant B: SHADOW is computed off the owner thread; the owner only checks and commits.

RUN #3 stalled the owner for 45 s inside one SHADOW arrival. Variant B reads a WAL snapshot
on the calling thread (own read-only connection, no write lock), evaluates there with the
unchanged A6 code, then asks the owner for short commits of at most two audit rows. The owner
verifies Autopilot/Robot runtime versions and the audit tail, and never computes. Anything
else (OFF, STOP, other writers, lock, expiry) fails closed: the chunk writes nothing and the
attempt is recomputed or dropped; the owner never runs the heavy path. Temporary DBs only.
"""

import json
import queue
import sqlite3
import tempfile
import threading
import time
import unittest
from pathlib import Path

from terminal.application import robot_autopilot_shadow as shadow
from terminal.application.robot_autopilot import OUTCOME_ALLOW
from terminal.persistence import sqlite_store
from terminal.persistence.sqlite_store import (
    DuplicateIdentity, RobotAutoDecisionRecord, ShadowCommitBusy, ShadowCommitStale, SQLiteStore,
)
from terminal.domain.models import Symbol
from tests.test_robot_autopilot_shadow import ACCOUNT, _Db, _wedge

MINUTE = 60_000
T0 = 100 * MINUTE + 5_000
IDEAS = 12
NOW = T0 + 9 * MINUTE


def build_history(root: Path) -> _Db:
    """IDEAS WAIT ideas, later closed candles and an ALLOW, so due WAITs and ALLOW rows exist."""
    db = _Db(root)
    for index in range(IDEAS):
        ref = f"w{index:03d}"
        _wedge(db.candidates, ref, symbol=f"S{index:03d}USDT")
        db.observe(ref, now=T0 + index)
    _wedge(db.candidates, "allow-1", symbol="ALLOWUSDT")
    db.observe("allow-1", now=T0 + 2 * MINUTE, health=lambda: True)
    return db


class OwnerLoop:
    """The test's owner thread: the main thread serves submitted callables one at a time."""

    def __init__(self):
        self.tasks: queue.Queue = queue.Queue()

    def submit(self, fn):
        done, box = threading.Event(), {}
        self.tasks.put((fn, done, box))
        if not done.wait(60):
            raise TimeoutError("owner did not answer")
        if "error" in box:
            raise box["error"]
        return box["result"]

    def serve(self, until: threading.Event):
        while not until.is_set() or not self.tasks.empty():
            try:
                fn, done, box = self.tasks.get(timeout=0.02)
            except queue.Empty:
                continue
            try:
                box["result"] = fn()
            except BaseException as error:
                box["error"] = error
            done.set()


def run_caller(owner: OwnerLoop, fn):
    """Run ``fn`` on a separate caller thread while this thread acts as the owner."""
    out, finished = {}, threading.Event()

    def target():
        try:
            out["result"] = fn()
        except BaseException as error:
            out["error"] = error
        finally:
            finished.set()

    thread = threading.Thread(target=target, name="test-caller")
    thread.start()
    owner.serve(finished)
    thread.join()
    if "error" in out:
        raise out["error"]
    return out["result"]


class Fixture(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.db = build_history(Path(self.tmp.name))
        self.addCleanup(lambda: self.db.store.close())
        self.owner = OwnerLoop()
        self.chunks = []

    def observer(self, *, hook=None, health=None, now=NOW, lock_wait_ms=100, monotonic=time.monotonic,
                 attempts=None):
        def commit(chunk):
            self.chunks.append(chunk)
            if hook is not None:
                hook(chunk)
            return self.owner.submit(lambda: shadow.commit_shadow_chunk(
                self.db.store, chunk, protection_healthy=health, monotonic=monotonic,
                lock_wait_ms=lock_wait_ms))
        kwargs = {} if attempts is None else {"attempts": attempts}
        return shadow.ShadowDeferredObserver(
            self.db.store.path, ACCOUNT, commit, protection_healthy=health,
            candidate_store_dir=self.db.candidates, clock_ms=lambda: now, monotonic=monotonic, **kwargs)

    def arrive(self, ref="late", symbol="LATEUSDT"):
        _wedge(self.db.candidates, ref, symbol=symbol)

    def observe(self, observer, ref="late"):
        return run_caller(self.owner, lambda: observer.observe(shadow.SOURCE_SCANNER, ref))

    def rows(self, at=None):
        return [d for d in self.db.decisions() if at is None or d.evaluated_at_ms == at]


def _row(d):
    return (d.decision_id, d.candidate_ref, d.outcome, d.reason_code, d.evaluated_at_ms, d.facts_json)


class EquivalenceTests(Fixture):
    def test_deferred_commit_writes_exactly_the_owner_path_audit(self):
        self.arrive()
        self.db.observe("late", now=NOW, health=lambda: True)  # the current owner path
        expected = sorted(_row(d) for d in self.rows(NOW))
        self.assertGreater(len(expected), 2)
        with tempfile.TemporaryDirectory() as other:
            twin = build_history(Path(other))
            try:
                _wedge(twin.candidates, "late", symbol="LATEUSDT")
                owner = OwnerLoop()
                observer = shadow.ShadowDeferredObserver(
                    twin.store.path, ACCOUNT,
                    lambda chunk: owner.submit(lambda: shadow.commit_shadow_chunk(
                        twin.store, chunk, protection_healthy=lambda: True)),
                    protection_healthy=lambda: True, candidate_store_dir=twin.candidates,
                    clock_ms=lambda: NOW)
                result = run_caller(owner, lambda: observer.observe(shadow.SOURCE_SCANNER, "late"))
                got = sorted(_row(d) for d in twin.decisions() if d.evaluated_at_ms == NOW)
            finally:
                twin.store.close()
        self.assertEqual(result, shadow.DEFERRED_COMMITTED)
        self.assertEqual(got, expected)  # ids, outcomes, reasons and facts_json byte for byte

    def test_owner_never_reads_history_or_computes(self):
        self.arrive()
        heavy = ("load_robot_auto_decisions", "load_robot_auto_decision_heads", "load_robot_candidates",
                 "load_robot_candidates_for_portfolio", "load_paper_portfolio_rows",
                 "load_open_robot_trades", "get_robot_candidate")
        calls = []
        originals = {name: getattr(SQLiteStore, name) for name in heavy}
        owner_thread = threading.get_ident()

        def counting(name):
            def wrapper(store, *args, **kwargs):
                if threading.get_ident() == owner_thread and store is self.db.store:
                    calls.append(name)
                return originals[name](store, *args, **kwargs)
            return wrapper
        for name in heavy:
            setattr(SQLiteStore, name, counting(name))
            self.addCleanup(setattr, SQLiteStore, name, originals[name])
        before = threading.active_count()
        result = self.observe(self.observer(health=lambda: True))
        self.assertEqual(result, shadow.DEFERRED_COMMITTED)
        self.assertEqual(calls, [])
        self.assertEqual(threading.active_count(), before)  # no new thread

    def test_chunks_are_at_most_two_rows_in_audit_order_with_continuous_sequence(self):
        self.arrive()
        before = self.db.store.count_robot_auto_decisions(ACCOUNT)
        self.assertEqual(self.observe(self.observer(health=lambda: True)), shadow.DEFERRED_COMMITTED)
        sizes = [len(chunk.records) for chunk in self.chunks]
        self.assertTrue(sizes and max(sizes) <= 2, sizes)
        self.assertGreater(len(sizes), 2)  # a batch really needed several commits
        # audit_sequence is the insertion position: contiguous, in commit order (the rows of
        # one attempt share their time, so their read order inside it is by id)
        committed = [r for chunk in self.chunks for r in chunk.records]
        sequences = [json.loads(r.facts_json)["portfolio_facts"]["audit_sequence"] for r in committed]
        self.assertEqual(sequences, list(range(before + 1, before + 1 + len(committed))))
        self.assertEqual(self.db.store.count_robot_auto_decisions(ACCOUNT), before + len(committed))

    def test_repeat_arrival_is_idempotent(self):
        self.arrive()
        observer = self.observer(health=lambda: True)
        self.observe(observer)
        count = self.db.store.count_robot_auto_decisions(ACCOUNT)
        self.chunks.clear()
        self.assertEqual(self.observe(observer), shadow.DEFERRED_COMMITTED)
        self.assertEqual(self.db.store.count_robot_auto_decisions(ACCOUNT), count)


class FailClosedTests(Fixture):
    def owner_do(self, fn):
        return self.owner.submit(fn)

    def test_off_during_the_attempt_writes_nothing(self):
        self.arrive()
        done = []

        def hook(chunk):
            if not done:
                done.append(1)
                state = self.owner_do(lambda: self.db.store.get_robot_autopilot_state(ACCOUNT))
                self.owner_do(lambda: self.db.store.update_robot_autopilot_state(
                    ACCOUNT, mode="OFF", expected_version=state.version, updated_at_ms=NOW + 1))
        before = self.db.store.count_robot_auto_decisions(ACCOUNT)
        result = self.observe(self.observer(hook=hook, health=lambda: True))
        self.assertEqual(result, shadow.DEFERRED_HANDOVER)  # OFF: the existing owner entry decides (does nothing)
        self.assertEqual(self.db.store.count_robot_auto_decisions(ACCOUNT), before)

    def test_switch_to_paper_auto_hands_the_arrival_to_the_existing_owner_path(self):
        self.arrive()
        done = []

        def hook(chunk):
            if not done:
                done.append(1)
                state = self.owner_do(lambda: self.db.store.get_robot_autopilot_state(ACCOUNT))
                self.owner_do(lambda: self.db.store.update_robot_autopilot_state(
                    ACCOUNT, mode="PAPER_AUTO", expected_version=state.version, updated_at_ms=NOW + 1))
        before = self.db.store.count_robot_auto_decisions(ACCOUNT)
        self.assertEqual(self.observe(self.observer(hook=hook, health=lambda: True)), shadow.DEFERRED_HANDOVER)
        self.assertEqual(self.db.store.count_robot_auto_decisions(ACCOUNT), before)

    def test_robot_stop_during_the_attempt_never_records_a_stale_ready_decision(self):
        self.arrive()
        done = []

        def hook(chunk):
            if not done:
                done.append(1)
                runtime = self.owner_do(lambda: self.db.store.get_robot_runtime_state(ACCOUNT))
                self.owner_do(lambda: self.db.store.update_robot_runtime_state(
                    ACCOUNT, mode="ROBOT_STOPPED", recovery_status="ROBOT_STOPPED", reason=None,
                    expected_version=runtime.version, updated_at_ms=NOW))
        self.assertEqual(self.observe(self.observer(hook=hook, health=lambda: True)), shadow.DEFERRED_COMMITTED)
        rows = [d for d in self.rows() if d.evaluated_at_ms >= NOW]
        self.assertTrue(rows)
        for d in rows:
            facts = json.loads(d.facts_json)
            self.assertEqual(facts["robot_mode"], "ROBOT_STOPPED")  # recomputed on the new state
            self.assertEqual(d.reason_code, "ROBOT_NOT_READY")

    def test_foreign_audit_write_between_chunks_recomputes_without_duplicates_or_gaps(self):
        self.arrive()
        state = {"chunks": 0}

        def hook(chunk):
            state["chunks"] += 1
            if state["chunks"] == 2:  # after the first chunk is committed, someone else appends
                foreign = RobotAutoDecisionRecord(
                    decision_id="auto-foreign", trading_account_id=ACCOUNT, candidate_ref="foreign",
                    pattern="Wedge", symbol=Symbol("FOREIGNUSDT"), timeframe="1", source_identity="foreign:x",
                    snapshot_sha256=None, mode="SHADOW", policy_version=shadow.POLICY_VERSION,
                    outcome="WAIT", reason_code="ROBOT_NOT_READY", evaluated_at_ms=NOW + 5,
                    resulting_candidate_id=None, facts_json=json.dumps({"portfolio_facts": {}}))
                self.owner_do(lambda: self.db.store.append_robot_auto_decision(foreign))
        before = self.db.store.count_robot_auto_decisions(ACCOUNT)
        result = self.observe(self.observer(hook=hook, health=lambda: True))
        self.assertEqual(result, shadow.DEFERRED_COMMITTED)
        full = self.db.decisions()
        ids = [d.decision_id for d in full]
        self.assertEqual(len(ids), len(set(ids)))
        mine = [d for d in full if d.decision_id != "auto-foreign" and d.evaluated_at_ms >= NOW]
        sequences = sorted(json.loads(d.facts_json)["portfolio_facts"]["audit_sequence"] for d in mine)
        foreign_position = before + 2 + 1  # the first chunk (2 rows) was committed before it
        total = self.db.store.count_robot_auto_decisions(ACCOUNT)
        # no duplicate and no gap: only the foreign writer's own slot is missing
        self.assertEqual(sequences, [n for n in range(before + 1, total + 1) if n != foreign_position])
        self.assertGreater(len(full), before + 1)
        self.assertTrue(any(d.candidate_ref == "late" for d in mine))

    def test_expired_request_writes_nothing_and_the_owner_never_computes(self):
        self.arrive()
        clock = {"t": 1000.0}
        ticks = iter(range(10_000))
        before = self.db.store.count_robot_auto_decisions(ACCOUNT)
        # every owner-side reading is far beyond the chunk's expiry
        result = self.observe(self.observer(health=lambda: True, monotonic=lambda: next(ticks) * 100.0))
        self.assertEqual(result, shadow.DEFERRED_DROPPED)
        self.assertEqual(self.db.store.count_robot_auto_decisions(ACCOUNT), before)
        del clock

    def test_a_held_write_lock_is_a_bounded_refusal_not_a_wait(self):
        self.arrive()
        holder = sqlite3.connect(str(self.db.store.path), isolation_level=None)
        holder.execute("BEGIN IMMEDIATE")
        self.addCleanup(holder.close)
        before = self.db.store.count_robot_auto_decisions(ACCOUNT)
        started = time.monotonic()
        result = self.observe(self.observer(health=lambda: True, lock_wait_ms=50, attempts=2))
        elapsed = time.monotonic() - started
        self.assertEqual(result, shadow.DEFERRED_DROPPED)
        self.assertLess(elapsed, 5.0)  # the default busy timeout alone would be 5 s per chunk
        self.assertEqual(self.db.store.count_robot_auto_decisions(ACCOUNT), before)
        holder.execute("COMMIT")
        self.assertEqual(self.observe(self.observer(health=lambda: True)), shadow.DEFERRED_COMMITTED)

    def test_a_protection_change_before_the_commit_is_stale(self):
        self.arrive()
        flips = {"n": 0}

        def health():
            flips["n"] += 1
            return flips["n"] % 2 == 1  # alternates: the owner's re-read never matches the plan's value
        before = self.db.store.count_robot_auto_decisions(ACCOUNT)
        result = self.observe(self.observer(health=health, attempts=2))
        self.assertEqual(result, shadow.DEFERRED_DROPPED)
        self.assertEqual(self.db.store.count_robot_auto_decisions(ACCOUNT), before)

    def test_snapshot_does_not_hold_the_write_lock(self):
        self.arrive()
        outcome = {}

        def health():  # runs during the off-owner evaluation, inside the read snapshot
            if "write" not in outcome:
                writer = sqlite3.connect(str(self.db.store.path), isolation_level=None, timeout=0)
                try:
                    writer.execute("BEGIN IMMEDIATE")
                    writer.execute("CREATE TABLE IF NOT EXISTS probe (n INTEGER)")
                    writer.execute("INSERT INTO probe VALUES (1)")
                    writer.execute("COMMIT")
                    outcome["write"] = "ok"
                except sqlite3.OperationalError as error:
                    outcome["write"] = str(error)
                finally:
                    writer.close()
            return True
        self.assertEqual(self.observe(self.observer(health=health)), shadow.DEFERRED_COMMITTED)
        self.assertEqual(outcome["write"], "ok")


class ConcurrentCallerTests(Fixture):
    def test_two_callers_are_serialized_each_arrival_decided_once(self):
        self.arrive("late-a", "AAAUSDT")
        self.arrive("late-b", "BBBUSDT")
        observer = self.observer(health=lambda: True)
        results = {}
        threads = []
        finished = threading.Event()
        remaining = {"n": 2}

        def call(ref):
            results[ref] = observer.observe(shadow.SOURCE_SCANNER, ref)
            remaining["n"] -= 1
            if remaining["n"] == 0:
                finished.set()
        for ref in ("late-a", "late-b"):
            threads.append(threading.Thread(target=call, args=(ref,)))
        for thread in threads:
            thread.start()
        self.owner.serve(finished)
        for thread in threads:
            thread.join()
        self.assertEqual(set(results.values()), {shadow.DEFERRED_COMMITTED})
        full = self.db.decisions()
        for ref in ("late-a", "late-b"):
            self.assertEqual(len([d for d in full if d.candidate_ref == ref and d.evaluated_at_ms >= NOW]), 1)
        ids = [d.decision_id for d in full]
        self.assertEqual(len(ids), len(set(ids)))
        sequences = sorted(json.loads(d.facts_json)["portfolio_facts"]["audit_sequence"]
                           for d in full if d.evaluated_at_ms >= NOW)
        start = min(sequences)
        self.assertEqual(sequences, list(range(start, start + len(sequences))))  # unique and contiguous


class StoreContractTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.dbs = []

    def make(self, name):
        root = Path(self.tmp.name) / name
        root.mkdir()
        db = _Db(root)
        self.dbs.append(db)
        self.addCleanup(db.store.close)
        return db

    @staticmethod
    def record(**override):
        values = dict(
            decision_id="auto-x", trading_account_id=ACCOUNT, candidate_ref="ref-x", pattern="Wedge",
            symbol=Symbol("XUSDT"), timeframe="1", source_identity="ref-x:s", snapshot_sha256="a" * 64,
            mode="SHADOW", policy_version=shadow.POLICY_VERSION, outcome="WAIT", reason_code="ROBOT_NOT_READY",
            evaluated_at_ms=NOW, resulting_candidate_id=None, facts_json="{}")
        values.update(override)
        return RobotAutoDecisionRecord(**values)

    def commit(self, store, records, **kwargs):
        expected = store.shadow_commit_markers(ACCOUNT)
        return store.append_robot_auto_decisions_committed(records, expected=expected, lock_wait_ms=100, **kwargs)

    def test_both_writers_enforce_the_same_field_invariants(self):
        a, b = self.make("a"), self.make("b")
        invalid = [
            {"decision_id": " "}, {"candidate_ref": ""}, {"pattern": ""}, {"timeframe": " "},
            {"source_identity": ""}, {"policy_version": ""}, {"reason_code": ""}, {"outcome": "MAYBE"},
            {"evaluated_at_ms": -1}, {"snapshot_sha256": "xyz"}, {"snapshot_sha256": "A" * 64},
        ]
        for override in invalid:
            with self.subTest(override=override):
                record = self.record(**override)
                with self.assertRaises(ValueError) as old:
                    a.store.append_robot_auto_decision(record)
                with self.assertRaises(ValueError) as new:
                    self.commit(b.store, [record])
                self.assertEqual(str(old.exception), str(new.exception))
                self.assertEqual(b.store.count_robot_auto_decisions(ACCOUNT), 0)
        with self.assertRaises(ValueError):  # the fast writer is SHADOW-only: PAPER_AUTO stays on the old path
            self.commit(b.store, [self.record(mode="PAPER_AUTO")])
        with self.assertRaises(ValueError):
            self.commit(b.store, [self.record(decision_id=f"auto-{i}") for i in range(3)])  # at most two rows
        with self.assertRaises(ValueError):
            self.commit(b.store, [])

    def test_valid_rows_are_identical_to_the_standard_append(self):
        a, b = self.make("a"), self.make("b")
        records = [self.record(decision_id="auto-1", evaluated_at_ms=NOW),
                   self.record(decision_id="auto-2", candidate_ref="ref-y", source_identity="ref-y:s",
                               evaluated_at_ms=NOW + 1, outcome=OUTCOME_ALLOW, reason_code="ELIGIBLE")]
        for r in records:
            a.store.append_robot_auto_decision(r)
        self.assertEqual(self.commit(b.store, records), 2)
        self.assertEqual(b.decisions(), a.decisions())

    def test_identical_row_is_skipped_and_a_conflicting_id_aborts_the_whole_chunk(self):
        db = self.make("a")
        first = self.record(decision_id="auto-1")
        self.assertEqual(self.commit(db.store, [first]), 1)
        self.assertEqual(self.commit(db.store, [first]), 0)  # idempotent
        clash = self.record(decision_id="auto-1", outcome="REJECT")
        fresh = self.record(decision_id="auto-2", candidate_ref="ref-z", source_identity="ref-z:s")
        with self.assertRaises(DuplicateIdentity):
            self.commit(db.store, [fresh, clash])
        self.assertEqual([d.decision_id for d in db.decisions()], ["auto-1"])  # fresh rolled back too

    def test_chunk_checks_versions_and_tail_and_mode(self):
        db = self.make("a")
        store = db.store
        expected = store.shadow_commit_markers(ACCOUNT)
        store.append_robot_auto_decision(self.record(decision_id="auto-other", candidate_ref="o", source_identity="o:s"))
        with self.assertRaises(ShadowCommitStale):  # audit tail moved
            store.append_robot_auto_decisions_committed([self.record()], expected=expected, lock_wait_ms=100)
        expected = store.shadow_commit_markers(ACCOUNT)
        runtime = store.get_robot_runtime_state(ACCOUNT)
        store.update_robot_runtime_state(ACCOUNT, mode="ROBOT_STOPPED", recovery_status="ROBOT_STOPPED", reason=None,
                                         expected_version=runtime.version, updated_at_ms=NOW)
        with self.assertRaises(ShadowCommitStale):  # Robot runtime version moved
            store.append_robot_auto_decisions_committed([self.record()], expected=expected, lock_wait_ms=100)
        expected = store.shadow_commit_markers(ACCOUNT)
        state = store.get_robot_autopilot_state(ACCOUNT)
        store.update_robot_autopilot_state(ACCOUNT, mode="OFF", expected_version=state.version, updated_at_ms=NOW)
        with self.assertRaises(ShadowCommitStale):  # OFF
            store.append_robot_auto_decisions_committed([self.record()], expected=expected, lock_wait_ms=100)
        self.assertEqual([d.decision_id for d in db.decisions()], ["auto-other"])

    def test_commit_lock_wait_is_short_and_the_default_timeout_is_restored(self):
        db = self.make("a")
        store = db.store
        expected = store.shadow_commit_markers(ACCOUNT)
        holder = sqlite3.connect(str(store.path), isolation_level=None)
        holder.execute("BEGIN IMMEDIATE")
        started = time.monotonic()
        with self.assertRaises(ShadowCommitBusy):
            store.append_robot_auto_decisions_committed([self.record()], expected=expected, lock_wait_ms=50)
        self.assertLess(time.monotonic() - started, 2.0)
        holder.execute("COMMIT")
        holder.close()
        self.assertEqual(store._connection.execute("PRAGMA busy_timeout").fetchone()[0], 5000)

    def test_reader_is_read_only_and_sees_a_stable_snapshot(self):
        db = self.make("a")
        db.store.append_robot_auto_decision(self.record())
        reader = SQLiteStore.open_reader(db.store.path)
        try:
            with reader.read_snapshot():
                first = reader.count_robot_auto_decisions(ACCOUNT)
                db.store.append_robot_auto_decision(self.record(decision_id="auto-2", candidate_ref="r2",
                                                                source_identity="r2:s"))  # writer is not blocked
                self.assertEqual(reader.count_robot_auto_decisions(ACCOUNT), first)  # snapshot unchanged
            self.assertEqual(reader.count_robot_auto_decisions(ACCOUNT), first + 1)
            with self.assertRaises(sqlite3.OperationalError):
                reader._connection.execute("DELETE FROM robot_auto_decisions")
            with self.assertRaises(sqlite3.OperationalError):
                reader._connection.execute("CREATE TABLE nope (n INTEGER)")
        finally:
            reader.close()

    def test_full_markers_detect_every_input_of_the_facts(self):
        db = self.make("a")
        store, c = db.store, db.store._connection
        base = store.shadow_full_markers(ACCOUNT)
        self.assertEqual(store.shadow_full_markers(ACCOUNT), base)  # stable without writes
        oid = c.execute("SELECT order_id FROM paper_limit_orders LIMIT 1").fetchone()
        c.execute("BEGIN")
        mutations = {
            "paper account": "UPDATE paper_accounts SET version=version+1, updated_at_ms=updated_at_ms+1",
            "autopilot": "UPDATE robot_autopilot_state SET version=version+1, updated_at_ms=updated_at_ms+1",
            "runtime": "UPDATE robot_runtime_state SET version=version+1, updated_at_ms=updated_at_ms+1",
        }
        for label, sql in mutations.items():
            with self.subTest(label):
                c.execute("SAVEPOINT m")
                c.execute(sql)
                self.assertNotEqual(store.shadow_full_markers(ACCOUNT), base)
                c.execute("ROLLBACK TO m")
        c.execute("ROLLBACK")
        del oid

class CommitChunkTests(StoreContractTests):
    """``commit_shadow_chunk``: the owner-side bounded decision. Anything but COMMITTED writes nothing."""

    def chunk(self, store, *records, expires_at=1e12, protection=True):
        return shadow.ShadowChunk(ACCOUNT, tuple(records), store.shadow_commit_markers(ACCOUNT),
                                  expires_at, protection)

    def run_chunk(self, store, chunk, *, health=lambda: True, monotonic=lambda: 0.0, lock_wait_ms=100):
        return shadow.commit_shadow_chunk(store, chunk, protection_healthy=health, monotonic=monotonic,
                                          lock_wait_ms=lock_wait_ms)

    def test_committed_expired_stale_not_shadow_busy_conflict(self):
        db = self.make("a")
        store = db.store
        count = lambda: store.count_robot_auto_decisions(ACCOUNT)
        ok = self.record(decision_id="auto-1")
        self.assertEqual(self.run_chunk(store, self.chunk(store, ok)), "COMMITTED")
        self.assertEqual(count(), 1)
        fresh = self.record(decision_id="auto-2", candidate_ref="r2", source_identity="r2:s")
        self.assertEqual(self.run_chunk(store, self.chunk(store, fresh, expires_at=5.0), monotonic=lambda: 6.0),
                         "EXPIRED")  # an owner that dequeues the call late writes nothing
        self.assertEqual(self.run_chunk(store, self.chunk(store, fresh), health=lambda: False), "STALE")
        self.assertEqual(self.run_chunk(store, self.chunk(store, fresh, protection=None), health=lambda: True), "STALE")
        self.assertEqual(self.run_chunk(store, self.chunk(store, fresh, protection=shadow._MIXED)), "STALE")
        self.assertEqual(self.run_chunk(store, self.chunk(store, ok)), "CONFLICT")  # the row already exists
        clash = self.record(decision_id="auto-1", outcome="REJECT")
        self.assertEqual(self.run_chunk(store, self.chunk(store, clash)), "CONFLICT")
        holder = sqlite3.connect(str(store.path), isolation_level=None)
        holder.execute("BEGIN IMMEDIATE")
        try:
            self.assertEqual(self.run_chunk(store, self.chunk(store, fresh), lock_wait_ms=30), "BUSY")
        finally:
            holder.execute("COMMIT")
            holder.close()
        stale = self.chunk(store, fresh)
        state = store.get_robot_autopilot_state(ACCOUNT)
        store.update_robot_autopilot_state(ACCOUNT, mode="OFF", expected_version=state.version, updated_at_ms=NOW)
        self.assertEqual(self.run_chunk(store, stale), "NOT_SHADOW")
        self.assertEqual(count(), 1)  # only the first commit ever wrote

    def test_a_failure_inside_the_evaluation_is_contained_and_never_runs_the_owner_path(self):
        from unittest.mock import patch

        db = self.make("a")
        db.store.append_robot_auto_decision(self.record())
        owner_calls = []
        observer = shadow.ShadowDeferredObserver(
            db.store.path, ACCOUNT, lambda chunk: owner_calls.append(chunk) or "COMMITTED",
            candidate_store_dir=db.candidates)
        with patch.object(shadow, "plan_shadow_observation", side_effect=RuntimeError("boom")):
            self.assertEqual(observer.observe(shadow.SOURCE_SCANNER, "x"), shadow.DEFERRED_DROPPED)
        self.assertEqual(owner_calls, [])

    def test_a_non_shadow_mode_is_a_handover_without_any_owner_call(self):
        db = self.make("a")
        state = db.store.get_robot_autopilot_state(ACCOUNT)
        db.store.update_robot_autopilot_state(ACCOUNT, mode="OFF", expected_version=state.version, updated_at_ms=NOW)
        owner_calls = []
        observer = shadow.ShadowDeferredObserver(
            db.store.path, ACCOUNT, lambda chunk: owner_calls.append(chunk) or "COMMITTED",
            candidate_store_dir=db.candidates)
        self.assertEqual(observer.observe(shadow.SOURCE_SCANNER, "x"), shadow.DEFERRED_HANDOVER)
        self.assertEqual(owner_calls, [])


class DeferredMetricsTests(Fixture):
    """PR #477 P0: every arrival without a SHADOW decision is counted, per process."""

    def test_commit_and_exhausted_attempts_are_counted_with_the_last_reason(self):
        self.arrive()
        observer = self.observer(health=lambda: True)
        self.assertEqual(self.observe(observer), shadow.DEFERRED_COMMITTED)
        self.assertEqual((observer.metrics()["committed"], observer.metrics()["dropped"]), (1, 0))
        self.arrive("late-2", symbol="LATE2USDT")
        busy = shadow.ShadowDeferredObserver(
            self.db.store.path, ACCOUNT, lambda chunk: "BUSY", protection_healthy=lambda: True,
            candidate_store_dir=self.db.candidates, clock_ms=lambda: NOW + 1)
        self.assertEqual(busy.observe(shadow.SOURCE_SCANNER, "late-2"), shadow.DEFERRED_DROPPED)
        metrics = busy.metrics()
        self.assertEqual((metrics["committed"], metrics["dropped"]), (0, 1))
        self.assertEqual(metrics["last_drop"]["reason"], "ATTEMPTS_EXHAUSTED:BUSY")
        self.assertEqual(metrics["last_drop"]["candidate_ref"], "late-2")

    def test_an_evaluation_error_is_counted_as_dropped(self):
        from unittest.mock import patch

        observer = self.observer(health=lambda: True)
        with patch.object(shadow, "plan_shadow_observation", side_effect=RuntimeError("boom")):
            self.assertEqual(observer.observe(shadow.SOURCE_SCANNER, "x"), shadow.DEFERRED_DROPPED)
        metrics = observer.metrics()
        self.assertEqual((metrics["committed"], metrics["dropped"]), (0, 1))
        self.assertEqual(metrics["last_drop"]["reason"], "ERROR_RuntimeError")

    def test_a_handover_is_neither_committed_nor_dropped_by_the_observer(self):
        state = self.db.store.get_robot_autopilot_state(ACCOUNT)
        self.db.store.update_robot_autopilot_state(
            ACCOUNT, mode="OFF", expected_version=state.version, updated_at_ms=NOW)
        observer = self.observer(health=lambda: True)
        self.assertEqual(self.observe(observer), shadow.DEFERRED_HANDOVER)
        metrics = observer.metrics()
        self.assertEqual((metrics["committed"], metrics["dropped"], metrics["last_drop"]), (0, 0, None))

    def test_metrics_never_wait_for_a_running_evaluation(self):
        self.arrive()
        seen = []

        def hook(chunk):  # the evaluation lock is held here; a reader must not wait for it
            if not seen:
                reader = threading.Thread(target=lambda: seen.append(observer.metrics()))
                reader.start()
                reader.join(2.0)
                seen.append(reader.is_alive())
        observer = self.observer(hook=hook, health=lambda: True)
        self.assertEqual(self.observe(observer), shadow.DEFERRED_COMMITTED)
        self.assertEqual(seen[0]["committed"], 0)
        self.assertIs(seen[1], False)
        self.assertEqual(observer.metrics()["committed"], 1)

    def test_concurrent_drops_are_all_counted(self):
        observer = self.observer()
        threads = [threading.Thread(target=lambda i=i: [
            observer.record_drop(shadow.SOURCE_SCANNER, f"r{i}-{n}", "X") for n in range(200)])
            for i in range(8)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()
        self.assertEqual(observer.metrics()["dropped"], 1600)

    def test_a_new_process_starts_from_zero(self):
        observer = self.observer()
        observer.record_drop(shadow.SOURCE_SCANNER, "x", "X")
        fresh = self.observer()  # a restarted backend builds a new runtime and observer
        self.assertEqual((fresh.metrics()["committed"], fresh.metrics()["dropped"]), (0, 0))
        self.assertGreaterEqual(fresh.metrics()["observer_started_at_ms"],
                                observer.metrics()["observer_started_at_ms"])


class HandoverOwnerTests(Fixture):
    """PR #477 P0: a handover reaching the owner after OFF->SHADOW never evaluates there."""

    def runtime(self, observer):
        from terminal.runtime.paper_runtime import PaperRuntime

        runtime = PaperRuntime.__new__(PaperRuntime)
        runtime.store = self.db.store
        runtime._paper_account_id = ACCOUNT
        runtime._shadow_deferred = observer
        runtime._process_instance_id = "proc-1"
        runtime._autopilot_protection_health = lambda: True
        runtime._autopilot_candidate_fresh = lambda symbol, snapshot: True
        runtime._prepare_autopilot_evidence = lambda source, ref: None
        return runtime

    def set_mode(self, mode):
        state = self.db.store.get_robot_autopilot_state(ACCOUNT)
        self.db.store.update_robot_autopilot_state(
            ACCOUNT, mode=mode, expected_version=state.version, updated_at_ms=NOW)

    def patched(self):
        from unittest.mock import patch
        from terminal.runtime import paper_runtime

        heavy = patch.object(paper_runtime, "observe_shadow_candidate",
                             side_effect=AssertionError("heavy SHADOW evaluation on the owner"))
        auto = patch.object(paper_runtime, "admit_arrived_auto_candidate", return_value="AUTO")
        return heavy, auto

    def test_off_to_shadow_race_drops_on_the_owner_without_the_heavy_path(self):
        self.arrive()
        self.set_mode("OFF")
        observer = self.observer(health=lambda: True)
        runtime = self.runtime(observer)

        def dispatcher(operation):  # the operator's POST SHADOW lands before the owner runs
            self.set_mode("SHADOW")
            return operation(runtime)
        runtime._robot_command_dispatcher = dispatcher
        before = self.db.store.count_robot_auto_decisions(ACCOUNT)
        heavy, auto = self.patched()
        with heavy, auto as admit:
            runtime._observe_autopilot_with_prepared_evidence(shadow.SOURCE_SCANNER, "late")
        admit.assert_not_called()
        self.assertEqual(self.db.store.count_robot_auto_decisions(ACCOUNT), before)
        metrics = runtime.autopilot_shadow_deferred_metrics()
        self.assertEqual((metrics["committed"], metrics["dropped"]), (0, 1))
        self.assertEqual(metrics["last_drop"]["reason"], "HANDOVER_MODE_SHADOW")
        self.assertEqual(metrics["process_instance_id"], "proc-1")

    def test_handover_in_off_does_nothing_and_counts_nothing(self):
        self.set_mode("OFF")
        runtime = self.runtime(self.observer())
        runtime._robot_command_dispatcher = lambda operation: operation(runtime)
        heavy, auto = self.patched()
        with heavy, auto as admit:
            runtime._observe_autopilot_with_prepared_evidence(shadow.SOURCE_SCANNER, "x")
        admit.assert_not_called()
        self.assertEqual(runtime.autopilot_shadow_deferred_metrics()["dropped"], 0)

    def test_handover_in_paper_auto_keeps_the_unchanged_admission_path(self):
        self.set_mode("PAPER_AUTO")
        runtime = self.runtime(self.observer())
        runtime._robot_command_dispatcher = lambda operation: operation(runtime)
        heavy, auto = self.patched()
        with heavy, auto as admit:
            runtime._observe_autopilot_with_prepared_evidence(shadow.SOURCE_SCANNER, "x")
            self.assertEqual(runtime.observe_autopilot_candidate(shadow.SOURCE_SCANNER, "y"), "AUTO")
        self.assertEqual([c.kwargs["candidate_ref"] for c in admit.call_args_list], ["x", "y"])
        self.assertEqual(runtime.autopilot_shadow_deferred_metrics()["dropped"], 0)

    def test_protection_health_payload_carries_the_counters_off_the_owner(self):
        from terminal.runtime.paper_http_server import (
            RobotProtectionCoverageManager, SerializedPaperRuntime,
        )

        observer = self.observer()
        observer.record_drop(shadow.SOURCE_BOX_PLAN, "box-1", "HANDOVER_MODE_SHADOW")
        runtime = self.runtime(observer)

        class Owned:  # only what SerializedPaperRuntime picks up from the owned runtime
            autopilot_shadow_deferred_metrics = runtime.autopilot_shadow_deferred_metrics

            def close(self):
                pass
        serialized = SerializedPaperRuntime(Owned)
        self.addCleanup(serialized.close)
        blocked, release = threading.Event(), threading.Event()
        serialized._requests.put((lambda runtime: (blocked.set(), release.wait(5)), threading.Event(), {}))
        self.assertTrue(blocked.wait(5))  # the owner is busy: the counters must not wait for it
        try:
            manager = RobotProtectionCoverageManager(None, serialized, recovery_session=object())
            health = manager.health()
        finally:
            release.set()
        payload = health["autopilot_shadow_deferred"]
        self.assertEqual((payload["committed"], payload["dropped"]), (0, 1))
        self.assertEqual(payload["last_drop"]["reason"], "HANDOVER_MODE_SHADOW")
        self.assertEqual(payload["process_instance_id"], "proc-1")
        json.dumps(payload)  # served as JSON as is


if __name__ == "__main__":
    unittest.main()
