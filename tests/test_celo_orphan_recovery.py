"""CELO recovery on temporary databases only; never opens the owner PAPER DB."""
import sqlite3
from contextlib import closing
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from tests.test_paper_orphan_market_commands import _Fixture, PAPER
from terminal.application.celo_orphan_recovery import (
    ALLOWED_ORPHAN_COMMANDS, REQUESTS, OrphanEvidenceError,
    fail_orphan_paper_market_commands,
)
from terminal.domain.models import CommandId, OrderId
from terminal.domain.states import CommandState
from tools import reconcile_celo_orphans as tool

IDS = tuple(ALLOWED_ORPHAN_COMMANDS)
NOW = 2_000_000_000_000


class CeloRecoveryTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.f = _Fixture(Path(self.tmp.name))
        self.addCleanup(self.f.store.close)
        self.s = self.f.store
        self.c = self.s._connection
        for cid, (_, link) in ALLOWED_ORPHAN_COMMANDS.items():
            quantity, created = REQUESTS[cid]
            self.f.submitting(cid, at_ms=created, symbol='CELOUSDT', link=link)
            self.c.execute('UPDATE trading_commands SET normalized_quantity=? WHERE command_id=?', (quantity, cid))
        self.s.initialize_robot_runtime_state(PAPER, updated_at_ms=1)
        self.s.initialize_scanner_runtime_state(PAPER, updated_at_ms=1)
        self.s.initialize_robot_autopilot_state(PAPER, updated_at_ms=1)
        for i, side in enumerate(('Buy', 'Sell')):
            cid, link = 'foreign-'+str(i), 'foreign-link-'+str(i)
            self.f.submitting(cid, at_ms=100, symbol='CELOUSDT', link=link)
            self.s.transition_command_state(CommandId(cid), CommandState.SUBMITTING, CommandState.ACKNOWLEDGED,
                expected_version=2, reason='ack', occurred_at_ms=150)
            self.s.transition_command_state(CommandId(cid), CommandState.ACKNOWLEDGED, CommandState.FILLED,
                expected_version=3, reason='simulator fill', occurred_at_ms=200,
                exchange_order_id=OrderId('paper-order-'+link))
            self.c.execute("INSERT INTO executions VALUES ('paper','linear',?,?,'CELOUSDT',?,'1','2','0',200)",
                           ('paper-exec-'+link, 'paper-order-'+link, side))
        self.c.execute("INSERT INTO position_projections VALUES ('paper','linear','CELOUSDT',0,'Flat','0',NULL,'0','0','0','synced',2,200)")

    def snapshot(self):
        return tuple(self.c.iterdump())

    def apply(self):
        return fail_orphan_paper_market_commands(self.s, IDS, occurred_at_ms=NOW)

    def refused(self):
        before = self.snapshot()
        with self.assertRaises(OrphanEvidenceError): self.apply()
        self.assertEqual(before, self.snapshot())

    def test_success_preserves_foreign_history_and_all_other_tables(self):
        tables = [r[0] for r in self.c.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT IN ('trading_commands','command_state_history','sqlite_sequence')")]
        before = {t: self.c.execute('SELECT * FROM '+t).fetchall() for t in tables}
        foreign = self.c.execute("SELECT * FROM trading_commands WHERE command_id LIKE 'foreign-%'").fetchall()
        history = self.c.execute("SELECT * FROM command_state_history WHERE command_id LIKE 'foreign-%'").fetchall()
        self.assertEqual([r.current_state for r in self.apply()], [CommandState.FAILED]*3)
        self.assertEqual(before, {t: self.c.execute('SELECT * FROM '+t).fetchall() for t in tables})
        self.assertEqual(foreign, self.c.execute("SELECT * FROM trading_commands WHERE command_id LIKE 'foreign-%'").fetchall())
        self.assertEqual(history, self.c.execute("SELECT * FROM command_state_history WHERE command_id LIKE 'foreign-%'").fetchall())

    def test_repeat_is_exactly_idempotent(self):
        self.apply(); before = self.snapshot(); self.apply()
        self.assertEqual(before, self.snapshot())

    def test_related_execution_in_any_account_blocks_all_three(self):
        link = ALLOWED_ORPHAN_COMMANDS[IDS[-1]][1]
        self.c.execute("INSERT INTO executions VALUES ('other','linear',?,'other-order','OTHER','Buy','1','1','0',200)", ('paper-exec-'+link,))
        self.refused()

    def test_related_order_even_cancelled_is_not_assumed_safe(self):
        link = ALLOWED_ORPHAN_COMMANDS[IDS[0]][1]
        self.c.execute("INSERT INTO paper_limit_orders VALUES ('other-order',?,'paper','CELOUSDT','Buy','1','1','0','GTC','cancelled',1,2)", (link,))
        self.refused()

    def test_uncertainty_refuses_without_writes(self):
        mutations = [
            "DELETE FROM position_projections",
            "UPDATE position_projections SET sync_state='stale'",
            "UPDATE position_projections SET quantity='1'",
            "DELETE FROM executions WHERE side='Sell'",
            "UPDATE trading_commands SET current_state='submitting' WHERE command_id='foreign-0'",
            "UPDATE trading_commands SET normalized_quantity='1' WHERE command_id='"+IDS[0]+"'",
            "UPDATE command_state_history SET reason='unknown' WHERE command_id='"+IDS[1]+"'",
            "UPDATE robot_autopilot_state SET mode='PAPER_AUTO'",
            "INSERT INTO paper_limit_orders VALUES ('open','open-link','paper','CELOUSDT','Buy','1','1','0','GTC','open',1,2)",
        ]
        for sql in mutations:
            with self.subTest(sql=sql):
                self.c.execute('SAVEPOINT fixture')
                self.c.execute(sql)
                # Proof itself is read-only, so inspect without opening a nested transaction.
                from terminal.application.celo_orphan_recovery import prove_orphan_paper_market_command
                before = self.snapshot()
                with self.assertRaises(OrphanEvidenceError):
                    for cid in IDS: prove_orphan_paper_market_command(self.s, cid)
                self.assertEqual(before, self.snapshot())
                self.c.execute('ROLLBACK TO fixture'); self.c.execute('RELEASE fixture')

    def test_mid_write_failure_rolls_back_entire_group(self):
        original = self.s._transition_command_in_transaction
        calls = []
        def fail_second(*args):
            calls.append(1)
            if len(calls) == 2: raise RuntimeError('injected write failure')
            return original(*args)
        before = self.snapshot()
        with patch.object(self.s, '_transition_command_in_transaction', side_effect=fail_second):
            with self.assertRaisesRegex(RuntimeError, 'injected'): self.apply()
        self.assertEqual(before, self.snapshot())

    def test_partial_allowlist_refused(self):
        before = self.snapshot()
        with self.assertRaises(OrphanEvidenceError):
            fail_orphan_paper_market_commands(self.s, IDS[:1], occurred_at_ms=NOW)
        self.assertEqual(before, self.snapshot())

    def test_cli_dry_run_apply_repeat_and_runtime_guard(self):
        backup = Path(self.tmp.name)/'backup.sqlite3'
        with closing(sqlite3.connect(backup)) as dest:
            self.c.backup(dest)
        args = ['--database',str(self.f.path),'--backup',str(backup),'--backup-sha256',tool._sha256(backup)]
        before = self.snapshot()
        self.assertEqual(tool.main(args, probe_listening=lambda _:True, out=lambda _:None), tool.EXIT_BLOCKED)
        self.assertEqual(tool.main(args, probe_listening=lambda _:False, out=lambda _:None), tool.EXIT_OK)
        self.assertEqual(before, self.snapshot())
        for _ in range(2):
            self.assertEqual(tool.main(args+['--apply'], probe_listening=lambda _:False, out=lambda _:None, clock_ms=lambda:NOW), tool.EXIT_OK)
        self.assertTrue(all(self.s.get_command(CommandId(cid)).current_state is CommandState.FAILED for cid in IDS))
