"""Owner-authorized reconciliation of two orphaned PAPER Market commands (OGUSDT).

Temporary databases only. The commands are created exactly like the manual
PAPER Market path does (ADMITTED -> SUBMITTING) and the real simulator is used
both to orphan a command (stale book: no fill) and to fill one (fresh book).
"""

import hashlib
import json
import sqlite3
import tempfile
import unittest
from decimal import Decimal
from pathlib import Path

from terminal.application.execution_engine import ExecutionEngine
from terminal.application.paper_orphan_market_commands import (
    ALLOWED_ORPHAN_COMMANDS, FAILED_REASON, OrphanEvidenceError,
    fail_orphan_paper_market_commands, prove_orphan_paper_market_command,
)
from terminal.application.robot_portfolio import collect_portfolio_facts
from terminal.domain.models import (
    Category, CommandId, Controller, ExecutionId, Notional, OrderId, OrderSide, Origin,
    Price, Quantity, Symbol, TradingAccountId,
)
from terminal.domain.states import CommandState
from terminal.market_data.models import BookHealth, NormalizedOrderBook, PriceLevel
from terminal.paper.executor import PaperBookStale, PaperMarketExecutor
from terminal.persistence.sqlite_store import CommandRecord, SQLiteStore
from tools import reconcile_paper_orphan_market_commands as tool

PAPER = TradingAccountId("paper")
FIRST = "cmd_b5ce5acd36b7489daf23a7632afa3fd2"
SECOND = "cmd_3ebfeec0374e4f589c96c2dd5599e035"
LINKS = {FIRST: "tw_b5ce5acd36b7489daf23a7632afa3fd2d",
         SECOND: "tw_3ebfeec0374e4f589c96c2dd5599e035b"}
T_FIRST, T_SECOND = 1788100079745, 1788100082106


def _book(received_at_ms):
    return NormalizedOrderBook(
        symbol=Symbol("OGUSDT"),
        bids=(PriceLevel(Price(Decimal("2.88")), Quantity(Decimal("1000"))),),
        asks=(PriceLevel(Price(Decimal("2.89")), Quantity(Decimal("1000"))),),
        health=BookHealth.READY, received_at_ms=received_at_ms, available_depth=1,
    )


class _Books:
    def __init__(self, book):
        self.book = book

    def get_book(self, symbol):
        return self.book if self.book.symbol == symbol else None


class _Fixture:
    def __init__(self, root: Path):
        self.path = root / "paper.sqlite3"
        self.store = SQLiteStore.open(self.path)
        self.store.initialize_paper_account(PAPER, Decimal("5000"), updated_at_ms=1)

    def submitting(self, command_id, *, at_ms, account=PAPER, symbol="OGUSDT", link=None,
                   kind="create_market"):
        """Same durable steps as TradingApplication._persist_submitting."""
        record = CommandRecord(
            command_id=CommandId(command_id), order_link_id=link or LINKS[command_id],
            trading_account_id=account, category=Category.LINEAR, symbol=Symbol(symbol),
            position_idx=0, command_kind=kind, side=OrderSide.BUY,
            requested_notional=Notional(Decimal("250")), normalized_price=None,
            normalized_quantity=Quantity(Decimal("86.5")),
            origin=Origin.TERMINAL_MANUAL, controller=Controller.MANUAL,
            current_state=CommandState.ADMITTED, version=1, exchange_order_id=None,
            created_at_ms=at_ms, updated_at_ms=at_ms,
        )
        eligibility = self.store.persist_command_before_submit(record)
        return self.store.transition_command_state(
            eligibility.command_id, CommandState.ADMITTED, CommandState.SUBMITTING,
            expected_version=eligibility.committed_version,
            reason="single mutation attempt durably started", occurred_at_ms=at_ms + 5,
        )

    def simulate(self, command_id, *, fresh):
        """Run the real PAPER Market simulator for the command's identity."""
        link = LINKS[command_id]
        executor = PaperMarketExecutor(
            _Books(_book(10_000)), ExecutionEngine(self.store), max_book_age_ms=500,
            fee_rate=Decimal("0.0006"), clock_ms=lambda: 10_100 if fresh else 20_000,
        )
        return executor.execute(
            trading_account_id=PAPER, symbol=Symbol("OGUSDT"), side=OrderSide.BUY,
            quantity=Quantity(Decimal("86.5")), order_link_id=link,
            order_id=OrderId(f"paper-order-{link}"), exec_id=ExecutionId(f"paper-exec-{link}"),
        )

    def both_orphaned(self):
        for command_id, at_ms in ((FIRST, T_FIRST), (SECOND, T_SECOND)):
            self.submitting(command_id, at_ms=at_ms)
            with self.test.assertRaises(PaperBookStale):
                self.simulate(command_id, fresh=False)

    def footprint(self):
        c = self.store._connection
        return tuple(c.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0] for t in (
            "trading_commands", "command_state_history", "executions",
            "position_projections", "paper_limit_orders", "paper_state_revisions"))

    def states(self):
        return {cid: self.store.get_command(CommandId(cid)).current_state
                for cid in (FIRST, SECOND) if self.store.get_command(CommandId(cid))}


class OrphanProofTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.f = _Fixture(Path(self.tmp.name))
        self.f.test = self
        self.addCleanup(self.f.store.close)

    def assertRefused(self, *ids, match=None):
        before = self.f.footprint()
        with self.assertRaises(OrphanEvidenceError) as raised:
            fail_orphan_paper_market_commands(self.f.store, ids or (FIRST, SECOND),
                                              occurred_at_ms=2_000_000_000_000)
        if match:
            self.assertIn(match, str(raised.exception))
        self.assertEqual(self.f.footprint(), before, "a refused reconciliation wrote state")
        return raised.exception

    def test_allowlist_is_exactly_the_two_ogusdt_commands(self):
        self.assertEqual(ALLOWED_ORPHAN_COMMANDS, {
            FIRST: ("OGUSDT", LINKS[FIRST]), SECOND: ("OGUSDT", LINKS[SECOND])})

    def test_proved_orphans_fail_with_exact_audit_and_unblock_the_portfolio(self):
        self.f.both_orphaned()
        self.assertEqual(collect_portfolio_facts(self.f.store, PAPER)["available"], False)
        executions_before = self.f.store.load_executions()

        results = fail_orphan_paper_market_commands(
            self.f.store, (FIRST, SECOND), occurred_at_ms=2_000_000_000_000)

        self.assertEqual([r.current_state for r in results], [CommandState.FAILED] * 2)
        self.assertEqual([r.version for r in results], [3, 3])
        for command_id in (FIRST, SECOND):
            history = self.f.store.load_command_history(CommandId(command_id))
            self.assertEqual(
                [(h.previous_state, h.next_state) for h in history],
                [(None, CommandState.ADMITTED), (CommandState.ADMITTED, CommandState.SUBMITTING),
                 (CommandState.SUBMITTING, CommandState.FAILED)])
            self.assertEqual(history[-1].reason, FAILED_REASON)
        # Trading history is untouched: no execution, position, order or revision appears.
        self.assertEqual(self.f.store.load_executions(), executions_before)
        self.assertEqual(self.f.footprint()[2:], (0, 0, 0, 0))
        facts = collect_portfolio_facts(self.f.store, PAPER)
        self.assertTrue(facts["available"], facts.get("data_error"))
        self.assertNotIn("unresolved_commands", facts)

    def test_rerun_is_idempotent_only_for_this_exact_reconciliation(self):
        self.f.both_orphaned()
        fail_orphan_paper_market_commands(self.f.store, (FIRST, SECOND), occurred_at_ms=2_000_000_000_000)
        before = self.f.footprint()
        again = fail_orphan_paper_market_commands(
            self.f.store, (FIRST, SECOND), occurred_at_ms=2_000_000_000_100)
        self.assertEqual([r.current_state for r in again], [CommandState.FAILED] * 2)
        self.assertEqual(self.f.footprint(), before)

    def test_a_command_the_simulator_filled_is_refused(self):
        self.f.submitting(FIRST, at_ms=T_FIRST)
        filled = self.f.simulate(FIRST, fresh=True)
        # Deterministic identity and atomic projection of the real simulator.
        self.assertEqual(filled.exec_id.value, f"paper-exec-{LINKS[FIRST]}")
        self.assertEqual(filled.order_id.value, f"paper-order-{LINKS[FIRST]}")
        position = self.f.store.load_paper_portfolio_rows(PAPER)["position_projections"]
        self.assertEqual([(p["symbol"], p["sync_state"]) for p in position], [("OGUSDT", "synced")])
        self.assertRefused(FIRST, match="execution")

    def test_any_paper_trace_on_the_symbol_is_refused(self):
        traces = {
            "execution": "INSERT INTO executions VALUES ('paper','linear','other-exec',"
                         "'other-order','OGUSDT','Buy','2.89','1','0.001',5)",
            "order": "INSERT INTO paper_limit_orders VALUES ('o-1','l-1','paper','OGUSDT','Buy',"
                     "'2.80','1','0','GTC','cancelled',1,2)",
            "position": "INSERT INTO position_projections VALUES ('paper','linear','OGUSDT',0,"
                        "'Flat','0','0','0','0','0','synced',1,9999999999999)",
            "revision": "INSERT INTO paper_state_revisions VALUES ('paper','OGUSDT',1)",
        }
        for label, insert in traces.items():
            with self.subTest(label), tempfile.TemporaryDirectory() as temp:
                f = _Fixture(Path(temp))
                f.test = self
                try:
                    f.both_orphaned()
                    f.store._connection.execute(insert)
                    before = f.footprint()
                    with self.assertRaises(OrphanEvidenceError) as raised:
                        fail_orphan_paper_market_commands(
                            f.store, (FIRST, SECOND), occurred_at_ms=2_000_000_000_000)
                    self.assertIn(label, str(raised.exception))
                    self.assertEqual(f.footprint(), before)
                    self.assertEqual(set(f.states().values()), {CommandState.SUBMITTING})
                finally:
                    f.store.close()

    def test_the_deterministic_identity_in_any_account_is_refused(self):
        self.f.both_orphaned()
        self.f.store._connection.execute(
            "INSERT INTO executions VALUES ('bybit-x','linear',?,?,'BTCUSDT','Buy','1','1','0',5)",
            (f"paper-exec-{LINKS[SECOND]}", "unrelated"))
        self.assertRefused(match="execution")

    def test_ambiguous_history_or_state_is_refused(self):
        self.f.both_orphaned()
        c = self.f.store._connection
        for label, mutate, restore in (
            ("history", lambda: c.execute(
                "INSERT INTO command_state_history (command_id, previous_state, next_state, reason,"
                " occurred_at_ms) VALUES (?, 'submitting', 'submitting', 'duplicate', 1)", (FIRST,)),
             lambda: c.execute("DELETE FROM command_state_history WHERE reason='duplicate'")),
            ("exchange_order_id", lambda: c.execute(
                "UPDATE trading_commands SET exchange_order_id='x' WHERE command_id=?", (FIRST,)),
             lambda: c.execute(
                "UPDATE trading_commands SET exchange_order_id=NULL WHERE command_id=?", (FIRST,))),
            ("state", lambda: c.execute(
                "UPDATE trading_commands SET current_state='unknown' WHERE command_id=?", (FIRST,)),
             lambda: c.execute(
                "UPDATE trading_commands SET current_state='submitting' WHERE command_id=?", (FIRST,))),
            ("version", lambda: c.execute(
                "UPDATE trading_commands SET version=5 WHERE command_id=?", (FIRST,)),
             lambda: c.execute("UPDATE trading_commands SET version=2 WHERE command_id=?", (FIRST,))),
            ("other unfinished command", lambda: self.f.submitting(
                "cmd_other", at_ms=T_SECOND + 1, link="tw_other"),
             lambda: (c.execute("DELETE FROM command_state_history WHERE command_id='cmd_other'"),
                      c.execute("DELETE FROM trading_commands WHERE command_id='cmd_other'"))),
        ):
            with self.subTest(label):
                mutate()
                try:
                    self.assertRefused(match=label)
                finally:
                    restore()
        # Restored fixture is provable again: the refusals above were not sticky.
        prove_orphan_paper_market_command(self.f.store, FIRST)

    def test_account_symbol_identity_and_kind_must_match_the_allowlist(self):
        cases = (
            ("account", dict(account=TradingAccountId("bybit-9e55e9b1839a41b4b492a54a25b26295"))),
            ("symbol", dict(symbol="CELOUSDT")),
            ("order_link_id", dict(link="tw_b5ce5acd36b7489daf23a7632afa3fd2X")),
            ("kind", dict(kind="create_limit")),
        )
        for label, overrides in cases:
            with self.subTest(label), tempfile.TemporaryDirectory() as temp:
                f = _Fixture(Path(temp))
                try:
                    f.submitting(FIRST, at_ms=T_FIRST, **overrides)
                    with self.assertRaises(OrphanEvidenceError) as raised:
                        prove_orphan_paper_market_command(f.store, FIRST)
                    self.assertIn(label, str(raised.exception))
                finally:
                    f.store.close()

    def test_unknown_missing_or_duplicate_ids_are_refused(self):
        self.f.both_orphaned()
        self.assertRefused(FIRST, "cmd_d2d1c17dd4ed41e5a2fd5859a3648a28", match="allowlist")
        self.assertRefused(FIRST, FIRST, match="duplicate")
        with self.assertRaises(OrphanEvidenceError):
            fail_orphan_paper_market_commands(self.f.store, (), occurred_at_ms=1)

    def test_nothing_is_written_unless_every_command_is_proven(self):
        self.f.both_orphaned()
        self.f.store._connection.execute(
            "UPDATE trading_commands SET exchange_order_id='x' WHERE command_id=?", (SECOND,))
        self.assertRefused(match="exchange_order_id")
        self.assertEqual(self.f.states(), {FIRST: CommandState.SUBMITTING,
                                            SECOND: CommandState.SUBMITTING})

    def test_a_failed_command_with_any_other_history_is_refused(self):
        self.f.both_orphaned()
        self.f.store.transition_command_state(
            CommandId(FIRST), CommandState.SUBMITTING, CommandState.FAILED, expected_version=2,
            reason="some other failure", occurred_at_ms=T_FIRST + 100)
        self.assertRefused(match="history")


class ToolGuardTests(unittest.TestCase):
    """The CLI applies only to a stopped runtime with a verified pre-change backup."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        root = Path(self.tmp.name)
        f = _Fixture(root)
        f.test = self
        f.both_orphaned()
        f.store.close()
        self.db = f.path
        self.backup = root / "backup.sqlite3"
        source = sqlite3.connect(f"file:{self.db.as_posix()}?mode=ro", uri=True)
        target = sqlite3.connect(self.backup)
        source.backup(target)
        target.close()
        source.close()
        self.sha = hashlib.sha256(self.backup.read_bytes()).hexdigest()

    def run_tool(self, *extra, probe=lambda _url: False):
        out = []
        code = tool.main(["--database", str(self.db), "--backup", str(self.backup),
                          "--backup-sha256", self.sha, *extra],
                         probe_listening=probe, out=out.append)
        return code, "\n".join(out)

    def states(self):
        c = sqlite3.connect(f"file:{self.db.as_posix()}?mode=ro", uri=True)
        try:
            return dict(c.execute(
                "SELECT command_id, current_state FROM trading_commands").fetchall())
        finally:
            c.close()

    def test_dry_run_is_the_default_and_writes_nothing(self):
        code, text = self.run_tool()
        self.assertEqual(code, 0, text)
        self.assertIn("DRY-RUN", text)
        self.assertEqual(set(self.states().values()), {"submitting"})

    def test_apply_fails_both_commands_after_every_guard(self):
        code, text = self.run_tool("--apply")
        self.assertEqual(code, 0, text)
        self.assertEqual(self.states(), {FIRST: "failed", SECOND: "failed"})

    def test_a_running_backend_or_telegram_worker_blocks(self):
        for listening in (tool.DEFAULT_BACKEND_HEALTH, tool.DEFAULT_TELEGRAM_HEALTH):
            with self.subTest(listening):
                code, text = self.run_tool("--apply", probe=lambda url: url == listening)
                self.assertNotEqual(code, 0)
                self.assertIn("runtime", text)
                self.assertEqual(set(self.states().values()), {"submitting"})

    def test_backup_must_match_its_digest_and_the_pre_change_state(self):
        code = tool.main(["--database", str(self.db), "--backup", str(self.backup),
                          "--backup-sha256", "0" * 64, "--apply"],
                         probe_listening=lambda _url: False, out=lambda _l: None)
        self.assertNotEqual(code, 0)
        self.assertEqual(set(self.states().values()), {"submitting"})
        # A backup taken after the change no longer proves the pre-change state.
        self.assertEqual(self.run_tool("--apply")[0], 0)
        post = Path(self.tmp.name) / "post.sqlite3"
        source = sqlite3.connect(f"file:{self.db.as_posix()}?mode=ro", uri=True)
        target = sqlite3.connect(post)
        source.backup(target)
        target.close()
        source.close()
        code = tool.main(["--database", str(self.db), "--backup", str(post),
                          "--backup-sha256", hashlib.sha256(post.read_bytes()).hexdigest()],
                         probe_listening=lambda _url: False, out=lambda _l: None)
        self.assertNotEqual(code, 0)

    def test_a_database_on_another_schema_is_never_opened_or_migrated(self):
        c = sqlite3.connect(self.db)
        c.execute("PRAGMA user_version = 24")
        c.close()
        before = hashlib.sha256(self.db.read_bytes()).hexdigest()
        code, text = self.run_tool("--apply")
        self.assertNotEqual(code, 0)
        self.assertIn("schema", text)
        self.assertEqual(hashlib.sha256(self.db.read_bytes()).hexdigest(), before)


if __name__ == "__main__":
    unittest.main()
