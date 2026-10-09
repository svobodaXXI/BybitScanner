"""A3 focused acceptance: disposable SQLite databases, no services/orders submitted."""
import json
import sqlite3
import tempfile
import threading
import unittest
from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal
from pathlib import Path
from unittest.mock import patch

from terminal.application.robot_autopilot_shadow import observe_shadow_candidate, SOURCE_SCANNER
from terminal.application.robot_portfolio import collect_portfolio_facts
from terminal.domain.models import OrderId, OrderSide, Symbol
from terminal.persistence.sqlite_store import SQLiteStore
from terminal.persistence.schema import SCHEMA_STATEMENTS, SCHEMA_V25_MIGRATION_STATEMENTS
from tests.test_robot_autopilot_shadow import _Db, _wedge, _l_shape, ACCOUNT


class PortfolioTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.db = _Db(self.root)
        self.store = self.db.store
        self.addCleanup(self.store.close)

    def facts(self):
        with self.store.autopilot_decision_transaction():
            return collect_portfolio_facts(self.store, ACCOUNT)

    def candidate(self, ref, symbol, execution=None):
        self.store.create_robot_candidate(candidate_id=ref, trading_account_id=ACCOUNT,
            symbol=Symbol(symbol), status="APPROVED", signal_snapshot={"id": ref},
            approved_at_ms=1, updated_at_ms=1)
        if execution is not None:
            self.store._connection.execute("UPDATE robot_candidates SET robot_state_json=?, state_revision=1 WHERE candidate_id=?",
                                           (json.dumps({"execution": execution}), ref))

    def limit(self, ref, symbol="MANUSDT", quantity="125"):
        self.store.create_paper_limit(client_action_id=ref, request_fingerprint=ref,
            order_id=OrderId(ref), order_link_id=ref, trading_account_id=ACCOUNT,
            symbol=Symbol(symbol), side=OrderSide.BUY, price=Decimal(1),
            quantity=Decimal(quantity), created_at_ms=1)

    def fill(self, ref, quantity, symbol="MANUSDT", stamp=1, side="Buy"):
        self.store._connection.execute("INSERT INTO executions VALUES ('paper','linear',?,?,?,?,?,?,?,?)",
            (f"exec-{ref}-{stamp}", ref, symbol, side, '1', str(quantity), '0', stamp))

    def position(self, quantity, symbol="MANUSDT", side="Long", sync="synced"):
        self.store._connection.execute("INSERT OR REPLACE INTO position_projections VALUES ('paper','linear',?,0,?,?,?,'0','0',?,?,1,10)",
            (symbol, side, str(quantity), '1', str(quantity), sync))

    def command(self, ref, symbol, *, state="submitting", updated_at_ms=5,
                kind="create_market", exchange_order_id=None):
        self.store._connection.execute(
            """INSERT INTO trading_commands (
                command_id, order_link_id, trading_account_id, category, symbol, position_idx,
                command_kind, side, requested_notional, normalized_price, normalized_quantity,
                origin, controller, current_state, version, exchange_order_id,
                created_at_ms, updated_at_ms
            ) VALUES (?, ?, 'paper', 'linear', ?, 0, ?, 'Buy', '250', NULL, '1',
                      'terminal_manual', 'manual', ?, 2, ?, ?, ?)""",
            (ref, "link-" + ref, symbol, kind, state, exchange_order_id,
             updated_at_ms - 1, updated_at_ms),
        )

    def observe(self, ref="next", symbol="NEWUSDT"):
        _wedge(self.db.candidates, ref, symbol=symbol)
        return self.db.observe(ref, health=lambda: True)

    def test_boundary_zero_18_19_20_and_audited_allow(self):
        for count in (0, 18, 19, 20):
            with self.subTest(count=count), tempfile.TemporaryDirectory() as directory:
                db = _Db(Path(directory))
                try:
                    for i in range(count):
                        db.store.create_robot_candidate(candidate_id=f"r-{i}", trading_account_id=ACCOUNT,
                            symbol=Symbol(f"S{i}USDT"), status="APPROVED", signal_snapshot={"i": i},
                            approved_at_ms=1, updated_at_ms=1)
                    _wedge(db.candidates, "new", symbol="NEWUSDT")
                    observed = db.observe("new", health=lambda: True)
                    self.assertEqual(observed.result.outcome, "ALLOW" if count < 19 else "WAIT")
                    self.assertEqual(observed.result.reason_code, "ELIGIBLE" if count < 19 else "PORTFOLIO_AGGREGATE_CAP")
                    facts = json.loads(observed.decision.facts_json)["portfolio_facts"]
                    self.assertEqual((facts["occupied_ro"], facts["occupied_usdt"]), (count, count * 250))
                    self.assertEqual(set(facts["deferred_controls"].values()), {"NOT_EVALUATED"})
                    if count == 18:
                        self.assertEqual(collect_portfolio_facts(db.store, ACCOUNT)["occupied_ro"], 19)
                        print("A3 proof: 18 RO + SHADOW ALLOW = 19 RO / 4750 USDT; reason=ELIGIBLE")
                finally:
                    db.store.close()

    def test_two_small_manual_limits_reserve_two_ro(self):
        self.limit("a"); self.limit("b")
        self.assertEqual(self.facts()["occupied_ro"], 2)
        self.assertEqual(self.observe(symbol="MANUSDT").result.reason_code, "SYMBOL_OWNED")

    def test_partial_manual_limit_and_position_share_one_reserve(self):
        self.limit("a")
        self.fill("a", 50)
        self.position(50)
        self.store._connection.execute("UPDATE paper_limit_orders SET filled_quantity='50',status='partially_filled'")
        facts = self.facts()
        self.assertTrue(facts["available"])
        self.assertEqual(facts["occupied_ro"], 1)
        self.assertEqual(facts["reservations"][0]["identity"], "manual-order:a")

    def test_box_four_parts_and_partial_fills_are_one_ro(self):
        self.candidate("box", "BOXUSDT")
        self.store._connection.execute("INSERT INTO box_attempt_ownership VALUES ('box','paper','BOXUSDT',1,1,0,0,?)", ("0" * 64,))
        for i in range(4):
            ref = f"slot-{i}"
            self.limit(ref, "BOXUSDT", "62.5")
            self.store._connection.execute("INSERT INTO box_order_ownership VALUES ('paper',?,'box','ENTRY',?)", (ref, i + 1))
        self.fill("slot-0", 20, "BOXUSDT")
        self.fill("slot-1", 20, "BOXUSDT")
        self.position(40, "BOXUSDT")
        self.store._connection.execute("UPDATE paper_limit_orders SET filled_quantity='20',status='partially_filled' WHERE order_id IN ('slot-0','slot-1')")
        self.assertEqual(self.facts()["occupied_ro"], 1)

    def test_robot_limit_filled_and_pending_share_candidate(self):
        self.candidate("w", "MANUSDT", {"limit_order_id": "a"})
        self.limit("a"); self.fill("a", 50); self.position(50)
        self.store._connection.execute("UPDATE paper_limit_orders SET filled_quantity='50',status='partially_filled'")
        self.assertEqual(self.facts()["occupied_ro"], 1)

    def test_manual_position_without_orders_counts_and_blocks_symbol(self):
        self.position(100)
        self.assertEqual(self.facts()["occupied_ro"], 1)
        self.assertEqual(self.observe(symbol="MANUSDT").result.reason_code, "SYMBOL_OWNED")

    def test_large_manual_snapshot_rounds_up_notional(self):
        self.position(251)
        self.assertEqual(self.facts()["occupied_ro"], 2)

    def test_unproven_overlap_waits_instead_of_double_counting(self):
        self.limit("a"); self.position(50)
        self.assertFalse(self.facts()["available"])
        self.assertEqual(self.observe().result.reason_code, "PORTFOLIO_DATA_UNAVAILABLE")

    def test_partial_reduction_of_multiple_manual_ideas_is_unknown(self):
        self.fill("a", 100, stamp=1); self.fill("b", 100, stamp=2)
        self.fill("close", 50, stamp=3, side="Sell"); self.position(150)
        self.assertFalse(self.facts()["available"])

    def test_full_closure_releases_previous_ambiguous_manual_lots(self):
        self.fill("a", 100, stamp=1); self.fill("b", 100, stamp=2)
        self.fill("close", 50, stamp=3, side="Sell")
        self.fill("close", 150, stamp=4, side="Sell")
        self.position(0, side="Flat")
        self.assertEqual(self.facts()["occupied_ro"], 0)

    def test_historical_flat_unreconciled_projection_is_zero_exposure(self):
        self.position(0, side="Flat", sync="reconciliation_required")
        facts = self.facts()
        self.assertTrue(facts["available"])
        self.assertEqual(facts["occupied_ro"], 0)
        self.assertEqual(
            facts["historical_flat_records"],
            [{"symbol": "MANUSDT", "sync_state": "reconciliation_required", "version": 1,
              "updated_at_ms": 10, "proof": "flat_zero_quantity_zero_engaged_notional"}],
        )

    def test_later_synced_flat_snapshot_supersedes_stale_market_submission(self):
        self.command("stale-celo", "CELOUSDT", updated_at_ms=5)
        self.position(0, symbol="CELOUSDT", side="Flat", sync="synced")
        facts = self.facts()
        self.assertTrue(facts["available"])
        self.assertEqual(facts["occupied_ro"], 0)
        self.assertEqual(facts["superseded_commands"][0]["command_id"], "stale-celo")
        self.assertEqual(
            facts["superseded_commands"][0]["proof"],
            "later_synced_flat_zero_exposure",
        )

    def test_unresolved_market_submission_without_later_snapshot_waits(self):
        self.command("stale-og", "OGUSDT", updated_at_ms=5)
        observed = self.observe()
        self.assertEqual(observed.result.reason_code, "PORTFOLIO_DATA_UNAVAILABLE")
        audited = json.loads(observed.decision.facts_json)["portfolio_facts"]
        self.assertEqual(
            audited["data_error"],
            "unfinished command lacks a later authoritative flat snapshot: OGUSDT (1)",
        )
        self.assertEqual(audited["unresolved_commands"][0]["command_id"], "stale-og")

    def test_synced_flat_does_not_supersede_other_unfinished_command_classes(self):
        self.command("unknown", "CELOUSDT", state="unknown", updated_at_ms=5)
        self.position(0, symbol="CELOUSDT", side="Flat", sync="synced")
        self.assertEqual(self.observe().result.reason_code, "PORTFOLIO_DATA_UNAVAILABLE")

    def test_terminal_shadow_does_not_guess_unknown_manual_overlap(self):
        self.observe("selected", "MANUSDT")
        self.candidate("selected", "MANUSDT")
        self.store._connection.execute("UPDATE robot_candidates SET status='INVALIDATED'")
        self.position(50)
        self.assertFalse(self.facts()["available"])

    def test_missing_fill_evidence_and_unreconciled_projection_wait(self):
        self.limit("a")
        self.store._connection.execute("UPDATE paper_limit_orders SET filled_quantity='50',status='partially_filled'")
        self.assertEqual(self.observe().result.reason_code, "PORTFOLIO_DATA_UNAVAILABLE")

    def test_missing_account_waits(self):
        self.store._connection.execute("DELETE FROM paper_accounts")
        self.assertEqual(self.observe().result.reason_code, "PORTFOLIO_DATA_UNAVAILABLE")

    def test_failed_collector_read_waits(self):
        with patch.object(self.store, "load_paper_portfolio_rows", side_effect=sqlite3.OperationalError("offline")):
            self.assertEqual(self.observe().result.reason_code, "PORTFOLIO_DATA_UNAVAILABLE")

    def test_repeat_returns_original_facts_and_pattern_contention_waits(self):
        first = self.observe("w", "SAMEUSDT")
        again = self.db.observe("w", health=lambda: False, now=9999)
        self.assertFalse(again.created)
        self.assertEqual(first.facts, again.facts)
        self.assertEqual(first.result, again.result)
        _l_shape(self.db.candidates, "l", symbol="SAMEUSDT")
        self.assertEqual(self.db.observe("l", health=lambda: True).result.reason_code, "SYMBOL_OWNED")
        self.assertEqual(self.facts()["occupied_ro"], 1)

    def test_restart_and_off_do_not_release_virtual_reserve(self):
        self.observe("first")
        state = self.store.get_robot_autopilot_state(ACCOUNT)
        self.store.update_robot_autopilot_state(ACCOUNT, mode="OFF", expected_version=state.version, updated_at_ms=2000)
        with SQLiteStore.open(self.root / "paper.sqlite3") as reopened:
            self.assertEqual(collect_portfolio_facts(reopened, ACCOUNT)["occupied_ro"], 1)

    def test_nineteen_shadow_allows_exhaust_capacity_without_guessing_release(self):
        trading_tables = ("paper_limit_orders", "executions", "trading_commands", "robot_trades")
        before = {
            table: self.store._connection.execute(f"SELECT * FROM {table}").fetchall()
            for table in trading_tables
        }
        outcomes = []
        for index in range(20):
            observed = self.observe(f"shadow-{index}", f"SHADOW{index}USDT")
            outcomes.append((observed.result.outcome, observed.result.reason_code))
        self.assertEqual(outcomes[:19], [("ALLOW", "ELIGIBLE")] * 19)
        self.assertEqual(outcomes[19], ("WAIT", "PORTFOLIO_AGGREGATE_CAP"))
        facts = self.facts()
        self.assertEqual((facts["occupied_ro"], facts["occupied_usdt"]), (19, 4750))
        self.assertEqual(
            len([r for r in facts["reservations"] if r["identity"].startswith("shadow:")]),
            19,
        )
        after = {
            table: self.store._connection.execute(f"SELECT * FROM {table}").fetchall()
            for table in trading_tables
        }
        self.assertEqual(before, after)

    def test_real_handoff_replaces_virtual_and_terminal_flat_releases(self):
        self.observe("selected", "SELUSDT")
        self.candidate("selected", "SELUSDT")
        self.assertEqual(self.facts()["occupied_ro"], 1)
        self.store._connection.execute("UPDATE robot_candidates SET status='INVALIDATED' WHERE candidate_id='selected'")
        self.assertEqual(self.facts()["occupied_ro"], 0)

    def test_terminal_candidate_with_working_order_keeps_reservation(self):
        self.observe("selected", "MANUSDT")
        self.candidate("selected", "MANUSDT", {"limit_order_id": "a"}); self.limit("a")
        self.store._connection.execute("UPDATE robot_candidates SET status='INVALIDATED' WHERE candidate_id='selected'")
        self.assertEqual(self.facts()["occupied_ro"], 1)

    def test_parallel_same_symbol_and_last_slot_are_serialized(self):
        for same_symbol in (True, False):
            with self.subTest(same_symbol=same_symbol), tempfile.TemporaryDirectory() as directory:
                db = _Db(Path(directory))
                for i in range(18):
                    db.store.create_robot_candidate(candidate_id=f"r-{i}", trading_account_id=ACCOUNT,
                        symbol=Symbol(f"S{i}USDT"), status="APPROVED", signal_snapshot={"i": i}, approved_at_ms=1, updated_at_ms=1)
                for i in range(2):
                    _wedge(db.candidates, f"w-{i}", symbol="NEWUSDT" if same_symbol else f"NEW{i}USDT")
                db.store.close()
                barrier = threading.Barrier(2)
                def run(index):
                    with SQLiteStore.open(Path(directory) / "paper.sqlite3") as store:
                        barrier.wait(timeout=10)
                        return observe_shadow_candidate(store, ACCOUNT, source=SOURCE_SCANNER,
                            candidate_ref=f"w-{index}", protection_healthy=lambda: True,
                            candidate_store_dir=db.candidates, clock_ms=lambda: 5000).result
                with ThreadPoolExecutor(max_workers=2) as pool:
                    results = list(pool.map(run, (0, 1)))
                self.assertEqual(sorted(r.outcome for r in results), ["ALLOW", "WAIT"])
                self.assertIn("SYMBOL_OWNED" if same_symbol else "PORTFOLIO_AGGREGATE_CAP", [r.reason_code for r in results])

    def test_off_and_paper_auto_skip_collector_callbacks_and_writes(self):
        for mode in ("OFF", "PAPER_AUTO"):
            state = self.store.get_robot_autopilot_state(ACCOUNT)
            self.store.update_robot_autopilot_state(ACCOUNT, mode=mode, expected_version=state.version, updated_at_ms=2000)
            before = self.store._connection.total_changes
            with patch.object(self.store, "load_paper_portfolio_rows", side_effect=AssertionError("collector called")):
                self.assertIsNone(observe_shadow_candidate(self.store, ACCOUNT, source=SOURCE_SCANNER,
                    candidate_ref="missing", protection_healthy=lambda: self.fail("callback called")))
            self.assertEqual(self.store._connection.total_changes, before)

    def test_allow_changes_only_audit(self):
        tables = [r[0] for r in self.store._connection.execute("SELECT name FROM sqlite_master WHERE type='table'") if r[0] != "robot_auto_decisions"]
        before = {t: self.store._connection.execute(f'SELECT * FROM {t}').fetchall() for t in tables}
        self.assertEqual(self.observe().result.outcome, "ALLOW")
        after = {t: self.store._connection.execute(f'SELECT * FROM {t}').fetchall() for t in tables}
        self.assertEqual(before, after)

    def test_v24_additive_migration_preserves_rows_and_immutable_triggers(self):
        path = self.root / 'legacy.sqlite3'
        connection = sqlite3.connect(path)
        for statement in SCHEMA_STATEMENTS[:-len(SCHEMA_V25_MIGRATION_STATEMENTS)]:
            connection.execute(statement)
        connection.execute("PRAGMA user_version=24")
        connection.execute("INSERT INTO robot_autopilot_state VALUES ('paper','SHADOW',NULL,1,1)")
        connection.execute("INSERT INTO robot_auto_decisions VALUES ('old','paper','c','Wedge','XUSDT','1','src',NULL,'SHADOW','old','WAIT','PORTFOLIO_POLICY_UNSET',1,NULL)")
        connection.commit(); connection.close()
        with SQLiteStore.open(path) as migrated:
            record = migrated.get_robot_auto_decision('old')
            self.assertEqual(record.facts_json, '{}')
            self.assertEqual(record.reason_code, 'PORTFOLIO_POLICY_UNSET')
            self.assertEqual(migrated.settings().schema_version, 25)
            for sql in ("UPDATE robot_auto_decisions SET facts_json='{\"x\":1}'", "DELETE FROM robot_auto_decisions"):
                with self.assertRaises(sqlite3.IntegrityError):
                    migrated._connection.execute(sql)


if __name__ == '__main__':
    unittest.main()
