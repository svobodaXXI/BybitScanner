"""Owner-attested closure of four stale LIVE Limit commands; temporary databases only."""

import hashlib
import sqlite3
import tempfile
import unittest
from pathlib import Path

from terminal.application.legacy_live_limit_owner_attestation import (
    ALLOWED_LEGACY_LIVE_COMMANDS, ATTESTATION_REASON, LIVE_ACCOUNT_ID, SYMBOL,
    LegacyLiveAttestationError, attest_legacy_live_limit_commands,
    prove_legacy_live_limit_command,
)
from terminal.domain.models import CommandId
from terminal.domain.states import (
    COMMAND_TRANSITIONS, CommandState, InvalidStateTransition, transition_command,
)
from terminal.persistence.schema import SCHEMA_VERSION
from terminal.persistence.sqlite_store import SQLiteStore
from tools import attest_legacy_live_limit_commands as tool

IDS = tuple(ALLOWED_LEGACY_LIVE_COMMANDS)
NOW = 2_000_000_000_000
ORIGINAL_HISTORY = (
    (None, "admitted", "durable LIVE Limit acceptance ownership"),
    ("admitted", "submitting", "LIVE Limit adapter dispatch durably started"),
    ("submitting", "acknowledged", "exchange accepted mutation request"),
    ("acknowledged", "open", "normalized exchange evidence resolved command"),
)
OTHER_LIVE = "cmd_other_live_open_0000000000000000"


def _insert_live_command(connection, command_id, *, link, order_id, price, quantity, created_at_ms,
                         state="open", version=4, account=LIVE_ACCOUNT_ID, symbol=SYMBOL,
                         history=ORIGINAL_HISTORY):
    connection.execute(
        """INSERT INTO trading_commands VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (command_id, link, account, "linear", symbol, 0, "create_limit", "Buy", "5.2", price,
         quantity, "terminal_manual", "manual", state, version, order_id, created_at_ms,
         created_at_ms + 1000))
    for n, (previous, following, reason) in enumerate(history):
        connection.execute(
            "INSERT INTO command_state_history (command_id, previous_state, next_state, reason, occurred_at_ms) "
            "VALUES (?,?,?,?,?)", (command_id, previous, following, reason, created_at_ms + n))


def _insert_action(connection, command_id, spec, *, state="RESOLVED"):
    session = spec["session"]
    connection.execute(
        """INSERT OR IGNORE INTO live_limit_acceptance_sessions
           (acceptance_session_id, trading_account_id, environment, symbol, capability, state,
            max_create_count, aggregate_notional_ceiling, per_order_ceiling, reserved_count,
            reserved_notional, opened_at_ms, expires_at_ms, authorized_build_sha, database_identity,
            operator_authorization_reference, authorized_session_generation, updated_at_ms)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (session, LIVE_ACCOUNT_ID, "MAINNET", SYMBOL, "LIVE_LIMIT_CREATE", "EXHAUSTED", 1, "5.20",
         "5.20", 1, "5.20", 1, 2, "sha", "identity", "ref", 2, 1))
    connection.execute(
        """INSERT INTO live_limit_actions
           (acceptance_session_id, trading_account_id, environment, capability, session_generation,
            symbol, operation, client_action_id, request_fingerprint, command_id, order_link_id,
            exchange_order_id, dispatch_state, reconciliation_state, reserved_count, reserved_notional,
            build_sha, process_instance_id, process_started_at_ms, process_id, database_path,
            database_identity, schema_version, host_identity, created_at_ms, updated_at_ms)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (session, LIVE_ACCOUNT_ID, "MAINNET", "LIVE_LIMIT_CREATE", 2, SYMBOL, "CREATE",
         spec["client_action_id"], spec["fingerprint"], command_id, spec["order_link_id"],
         spec["exchange_order_id"], "ACKNOWLEDGED", state, 1, "5.20", "sha", "pi", 1, 1, "db",
         "identity", SCHEMA_VERSION, "host", 1, 2))


class _Case(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.addCleanup(self._close)
        self._build("paper.sqlite3")

    def _rebuild(self, name):
        self._close()
        self._build(name)

    def _build(self, name):
        self.path = Path(self.tmp.name) / name
        self.store = SQLiteStore.open(self.path)
        self.c = self.store._connection
        for command_id, spec in ALLOWED_LEGACY_LIVE_COMMANDS.items():
            _insert_live_command(
                self.c, command_id, link=spec["order_link_id"], order_id=spec["exchange_order_id"],
                price=spec["price"], quantity=spec["quantity"], created_at_ms=spec["created_at_ms"])
            _insert_action(self.c, command_id, spec)
        # unrelated LIVE command that must never be touched
        _insert_live_command(self.c, OTHER_LIVE, link="tw_other_live", order_id="other-exchange-order",
                             price="1", quantity="1", created_at_ms=1788000000000)

    def _close(self):
        try:
            self.store.close()
        except Exception:
            pass

    def snapshot(self, *, skip_commands=False):
        tables = [r[0] for r in self.c.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY 1")]
        result = {}
        for table in tables:
            if skip_commands and table in ("trading_commands", "command_state_history"):
                continue
            result[table] = tuple(tuple(r) for r in self.c.execute(f'SELECT * FROM "{table}" ORDER BY 1,2'))
        return result

    def state(self, command_id):
        row = self.c.execute("SELECT current_state, version FROM trading_commands WHERE command_id=?",
                             (command_id,)).fetchone()
        return row[0], row[1]

    def history(self, command_id):
        return tuple(tuple(r) for r in self.c.execute(
            "SELECT previous_state, next_state, reason FROM command_state_history WHERE command_id=? "
            "ORDER BY history_id", (command_id,)))


class AttestationTests(_Case):
    def test_all_four_are_proven_and_dry_proof_writes_nothing(self):
        before = self.snapshot()
        for command_id in IDS:
            proof = prove_legacy_live_limit_command(self.store, command_id)
            self.assertFalse(proof.already_attested)
            self.assertEqual(proof.version, 4)
        self.assertEqual(self.snapshot(), before)

    def test_attestation_closes_exactly_four_and_keeps_all_original_history(self):
        before = self.snapshot(skip_commands=True)
        other_before = (self.state(OTHER_LIVE), self.history(OTHER_LIVE))
        results = attest_legacy_live_limit_commands(self.store, IDS, occurred_at_ms=NOW)
        self.assertEqual({r.current_state for r in results}, {CommandState.OWNER_ATTESTED_CLOSED})
        for command_id in IDS:
            self.assertEqual(self.state(command_id), ("owner_attested_closed", 5))
            history = self.history(command_id)
            self.assertEqual(history[:4], ORIGINAL_HISTORY)
            self.assertEqual(history[4], ("open", "owner_attested_closed", ATTESTATION_REASON))
            self.assertEqual(len(history), 5)
        self.assertIn("owner's statement", ATTESTATION_REASON)
        self.assertIn("NOT exchange evidence", ATTESTATION_REASON)
        self.assertNotIn("cancelled by the exchange", ATTESTATION_REASON)
        # nothing else changed: no execution, order, action, session, projection ...
        self.assertEqual(self.snapshot(skip_commands=True), before)
        self.assertEqual((self.state(OTHER_LIVE), self.history(OTHER_LIVE)), other_before)

    def test_closed_commands_are_no_longer_unfinished_but_others_still_are(self):
        unfinished = {c.command_id.value for c in self.store.load_unfinished_commands()}
        self.assertTrue(set(IDS) <= unfinished)
        attest_legacy_live_limit_commands(self.store, IDS, occurred_at_ms=NOW)
        unfinished = {c.command_id.value for c in self.store.load_unfinished_commands()}
        self.assertTrue(unfinished.isdisjoint(IDS))
        self.assertIn(OTHER_LIVE, unfinished)
        self.assertEqual(self.store.get_command(CommandId(IDS[0])).current_state,
                         CommandState.OWNER_ATTESTED_CLOSED)

    def test_second_application_is_a_verified_no_op(self):
        attest_legacy_live_limit_commands(self.store, IDS, occurred_at_ms=NOW)
        after_first = self.snapshot()
        results = attest_legacy_live_limit_commands(self.store, IDS, occurred_at_ms=NOW + 10)
        self.assertTrue(all(r.version == 5 for r in results))
        self.assertEqual(self.snapshot(), after_first)
        for command_id in IDS:
            self.assertTrue(prove_legacy_live_limit_command(self.store, command_id).already_attested)

    def test_only_the_exact_four_ids_are_accepted(self):
        before = self.snapshot()
        for bad in (IDS[:3], IDS + (OTHER_LIVE,), IDS[:3] + (OTHER_LIVE,), (), (OTHER_LIVE,)):
            with self.assertRaises(LegacyLiveAttestationError):
                attest_legacy_live_limit_commands(self.store, bad, occurred_at_ms=NOW)
        with self.assertRaises(LegacyLiveAttestationError):
            prove_legacy_live_limit_command(self.store, OTHER_LIVE)
        self.assertEqual(self.snapshot(), before)

    def test_any_identity_mismatch_refuses_the_whole_group_atomically(self):
        mutations = {
            "price": "UPDATE trading_commands SET normalized_price='0.1' WHERE command_id=?",
            "quantity": "UPDATE trading_commands SET normalized_quantity='99' WHERE command_id=?",
            "account": "UPDATE trading_commands SET trading_account_id='paper' WHERE command_id=?",
            "symbol": "UPDATE trading_commands SET symbol='BTCUSDT' WHERE command_id=?",
            "exchange_order": "UPDATE trading_commands SET exchange_order_id='x' WHERE command_id=?",
            "created": "UPDATE trading_commands SET created_at_ms=1 WHERE command_id=?",
            "version": "UPDATE trading_commands SET version=9 WHERE command_id=?",
            "state": "UPDATE trading_commands SET current_state='cancelled' WHERE command_id=?",
        }
        for number, (name, sql) in enumerate(mutations.items()):
            with self.subTest(name):
                self._rebuild(f"mutation_{number}.sqlite3")
                self.c.execute(sql, (IDS[3],))
                before = self.snapshot()
                with self.assertRaises(LegacyLiveAttestationError):
                    attest_legacy_live_limit_commands(self.store, IDS, occurred_at_ms=NOW)
                self.assertEqual(self.snapshot(), before)
                self.assertEqual({self.state(i)[0] for i in IDS[:3]}, {"open"})

    def test_tampered_history_and_missing_or_unresolved_action_refuse(self):
        cases = {
            "history": "UPDATE command_state_history SET reason='edited' WHERE command_id=? AND next_state='open'",
            "fingerprint": "UPDATE live_limit_actions SET request_fingerprint='x' WHERE command_id=?",
            "unresolved": "UPDATE live_limit_actions SET reconciliation_state='REQUIRED' WHERE command_id=?",
            "dispatch": "UPDATE live_limit_actions SET dispatch_state='UNKNOWN' WHERE command_id=?",
            "no action": "DELETE FROM live_limit_actions WHERE command_id=?",
        }
        for number, (name, sql) in enumerate(cases.items()):
            with self.subTest(name):
                self._rebuild(f"tampered_{number}.sqlite3")
                self.c.execute(sql, (IDS[1],))
                before = self.snapshot()
                with self.assertRaises(LegacyLiveAttestationError):
                    attest_legacy_live_limit_commands(self.store, IDS, occurred_at_ms=NOW)
                self.assertEqual(self.snapshot(), before)
        with self.subTest("unresolved action of another command blocks everything"):
            self._rebuild("unresolved_other.sqlite3")
            self.c.execute("UPDATE live_limit_actions SET reconciliation_state='REQUIRED' WHERE command_id=?",
                           (IDS[0],))
            with self.assertRaises(LegacyLiveAttestationError):
                prove_legacy_live_limit_command(self.store, IDS[2])

    def test_a_real_execution_or_paper_trace_is_never_hidden(self):
        spec = ALLOWED_LEGACY_LIVE_COMMANDS[IDS[0]]
        self.c.execute(
            "INSERT INTO executions VALUES (?,?,?,?,?,?,?,?,?,?)",
            (LIVE_ACCOUNT_ID, "linear", "exec-1", spec["exchange_order_id"], SYMBOL, "Buy", "0.09513",
             "54", "0.001", 1788560000000))
        with self.assertRaises(LegacyLiveAttestationError):
            attest_legacy_live_limit_commands(self.store, IDS, occurred_at_ms=NOW)
        self.c.execute("DELETE FROM executions")
        self.c.execute(
            "INSERT INTO paper_limit_orders (order_id, order_link_id, trading_account_id, symbol, side, price, "
            "quantity, filled_quantity, time_in_force, status, created_at_ms, updated_at_ms) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
            (spec["exchange_order_id"], "x", "paper", SYMBOL, "Buy", "1", "1", "0", "GTC", "open", 1, 1))
        with self.assertRaises(LegacyLiveAttestationError):
            attest_legacy_live_limit_commands(self.store, IDS, occurred_at_ms=NOW)

    def test_timestamp_before_history_is_refused(self):
        with self.assertRaises(LegacyLiveAttestationError):
            attest_legacy_live_limit_commands(self.store, IDS, occurred_at_ms=1)
        self.assertEqual({self.state(i)[0] for i in IDS}, {"open"})


class StateMachineTests(unittest.TestCase):
    def test_new_state_is_terminal_and_reachable_only_from_open(self):
        self.assertEqual(COMMAND_TRANSITIONS[CommandState.OWNER_ATTESTED_CLOSED], frozenset())
        sources = {s for s, targets in COMMAND_TRANSITIONS.items()
                   if CommandState.OWNER_ATTESTED_CLOSED in targets}
        self.assertEqual(sources, {CommandState.OPEN})
        for state in (CommandState.ACKNOWLEDGED, CommandState.CANCELLED, CommandState.FILLED,
                      CommandState.RECONCILING, CommandState.SUBMITTING):
            with self.assertRaises(InvalidStateTransition):
                transition_command(state, CommandState.OWNER_ATTESTED_CLOSED)
        with self.assertRaises(InvalidStateTransition):
            transition_command(CommandState.OWNER_ATTESTED_CLOSED, CommandState.OPEN)


class ToolTests(_Case):
    def _backup(self):
        backup = Path(self.tmp.name) / "backup.sqlite3"
        source = sqlite3.connect(self.path)
        target = sqlite3.connect(backup)
        source.backup(target)
        target.close()
        source.close()
        return backup, hashlib.sha256(backup.read_bytes()).hexdigest()

    def _run(self, *extra, running=False, backup=None, sha=None):
        # the owner connection is closed so the tool can reopen the file like a real run
        self.store.close()
        if backup is None:
            backup, sha = self._backup()
        lines = []
        code = tool.main(
            ["--database", str(self.path), "--backup", str(backup), "--backup-sha256", sha, *extra],
            probe_listening=lambda url: running, out=lines.append, clock_ms=lambda: NOW)
        return code, lines

    def _states(self):
        c = sqlite3.connect(self.path)
        try:
            return {r[0]: (r[1], r[2]) for r in c.execute(
                "SELECT command_id, current_state, version FROM trading_commands")}
        finally:
            c.close()

    def test_dry_run_proves_and_writes_nothing(self):
        self.c.execute("PRAGMA wal_checkpoint(TRUNCATE)")
        code, lines = self._run()
        self.assertEqual(code, tool.EXIT_OK)
        self.assertEqual(sum(1 for line in lines if line.startswith("PROVEN")), 4)
        self.assertTrue(any(line.startswith("DRY-RUN") for line in lines))
        self.assertEqual({v for k, v in self._states().items() if k in IDS}, {("open", 4)})

    def test_apply_requires_the_exact_owner_statement(self):
        code, lines = self._run("--apply")
        self.assertEqual(code, tool.EXIT_USAGE)
        code, _ = self._run("--apply", "--owner-statement", "yes")
        self.assertEqual(code, tool.EXIT_USAGE)
        self.assertEqual({v for k, v in self._states().items() if k in IDS}, {("open", 4)})

    def test_apply_closes_four_is_idempotent_and_leaves_other_live_command_alone(self):
        code, lines = self._run("--apply", "--owner-statement", tool.OWNER_STATEMENT)
        self.assertEqual(code, tool.EXIT_OK, lines)
        states = self._states()
        self.assertEqual({states[i] for i in IDS}, {("owner_attested_closed", 5)})
        self.assertEqual(states[OTHER_LIVE], ("open", 4))
        # second apply: the backup no longer holds the pre-change state -> blocked, no change
        backup, sha = self._backup()
        code, lines = self._run("--apply", "--owner-statement", tool.OWNER_STATEMENT,
                                backup=backup, sha=sha)
        self.assertEqual(code, tool.EXIT_BLOCKED)
        self.assertEqual({self._states()[i] for i in IDS}, {("owner_attested_closed", 5)})

    def test_running_runtime_wrong_backup_hash_or_wrong_backup_block_before_any_write(self):
        code, lines = self._run(running=True)
        self.assertEqual(code, tool.EXIT_BLOCKED)
        self.assertIn("not fully stopped", lines[0])
        backup, _sha = self._backup()
        code, lines = self._run(backup=backup, sha="0" * 64)
        self.assertEqual(code, tool.EXIT_BLOCKED)
        self.assertIn("SHA-256", lines[0])
        code, _ = self._run("--apply", "--owner-statement", tool.OWNER_STATEMENT,
                            backup=self.path, sha=hashlib.sha256(self.path.read_bytes()).hexdigest())
        self.assertEqual(code, tool.EXIT_BLOCKED)
        self.assertEqual({v for k, v in self._states().items() if k in IDS}, {("open", 4)})


if __name__ == "__main__":
    unittest.main()
