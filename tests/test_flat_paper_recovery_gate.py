"""Fail-closed FLAT recovery evidence. In-memory SQL only; never touches VPS."""
import sqlite3
import unittest

from tools.flat_paper_recovery_gate import FlatRecoveryBlocked, prove_flat_recovery


IDENTITY = "e0cbafb1c172b65f2db3a2c7cef2636b4164a4b1a229bd183bd907e7984ff0ad"


def fixture():
    conn = sqlite3.connect(":memory:")
    conn.executescript("""
        CREATE TABLE robot_runtime_state (trading_account_id TEXT, mode TEXT, recovery_status TEXT);
        CREATE TABLE robot_autopilot_state (trading_account_id TEXT, mode TEXT);
        CREATE TABLE position_projections (trading_account_id TEXT, symbol TEXT, side TEXT, quantity TEXT);
        CREATE TABLE robot_trades (
            trade_id TEXT, trading_account_id TEXT, symbol TEXT, pattern TEXT,
            exit_reason TEXT, exit_time_ms INTEGER, exit_price TEXT
        );
        CREATE TABLE robot_candidates (trading_account_id TEXT, status TEXT);
        CREATE TABLE paper_limit_orders (trading_account_id TEXT, status TEXT);
        CREATE TABLE trading_commands (trading_account_id TEXT, current_state TEXT);
        CREATE TABLE paper_protection_obligations (
            trading_account_id TEXT, symbol TEXT, trade_id TEXT, winning_leg TEXT,
            status TEXT, order_id TEXT, exec_id TEXT, observed_quantity TEXT
        );
        CREATE TABLE executions (
            trading_account_id TEXT, category TEXT, exec_id TEXT, order_id TEXT,
            symbol TEXT, quantity TEXT, exchange_timestamp_ms INTEGER, price TEXT, side TEXT
        );
        INSERT INTO robot_runtime_state VALUES ('paper','ROBOT_RUNNING','RECONCILIATION_REQUIRED');
        INSERT INTO robot_autopilot_state VALUES ('paper','OFF');
        INSERT INTO position_projections VALUES ('paper','BUSDT','Flat','0');
        INSERT INTO position_projections VALUES ('paper','VIRTUALUSDT','Flat','0');
        INSERT INTO robot_trades VALUES
            ('box-busdt','paper','BUSDT','IKIGAI_BOX','TAKE',100,'0.1280451745');
        INSERT INTO paper_protection_obligations VALUES
            ('paper','BUSDT','box-busdt','STOP','DISPATCHING',
             'stop-order','stop-exec','487');
        INSERT INTO executions VALUES
            ('paper','linear','stop-exec','stop-order','BUSDT','487',100,
             '0.1280451745','Sell');
    """)
    payload = dict(
        expected_identity=IDENTITY,
        backend=dict(ok=True, component="paper_backend", mode="paper",
                     paper_live_safe=True, database_identity=IDENTITY),
        scanner=dict(mode="SCANNER_STOPPED"),
        autopilot=dict(mode="OFF"),
        protection=dict(healthy=True, covered_symbols=[], armed_symbols=[],
                        unhealthy_symbols={}),
    )
    return conn, payload


def assert_blocked(case, conn, payload):
    with case.assertRaises(FlatRecoveryBlocked):
        prove_flat_recovery(conn, **payload)


class FlatRecoveryGateTests(unittest.TestCase):
    def test_exact_historical_stop_is_only_a_read_only_proof(self):
        conn, payload = fixture()
        before = conn.total_changes
        self.assertEqual(prove_flat_recovery(conn, **payload),
                         "FLAT_RECOVERY_EVIDENCE_PROVEN_ONLY")
        self.assertEqual(conn.total_changes, before)
        row = conn.execute(
            "SELECT status FROM paper_protection_obligations"
        ).fetchone()
        self.assertEqual(row, ("DISPATCHING",))
        conn.close()

    def test_open_position_blocks_even_if_apis_report_healthy(self):
        conn, payload = fixture()
        conn.execute("UPDATE position_projections SET side='Short',quantity='422' "
                     "WHERE symbol='VIRTUALUSDT'")
        assert_blocked(self, conn, payload)

    def test_missing_busdt_flat_projection_blocks(self):
        conn, payload = fixture()
        conn.execute("DELETE FROM position_projections WHERE symbol='BUSDT'")
        assert_blocked(self, conn, payload)

    def test_active_limit_and_unknown_limit_block(self):
        for status in ("open", "partially_filled", "unknown"):
            with self.subTest(status=status):
                conn, payload = fixture()
                conn.execute("INSERT INTO paper_limit_orders VALUES ('paper',?)", (status,))
                assert_blocked(self, conn, payload)

    def test_pending_market_and_unknown_command_block(self):
        for state in ("submitting", "unknown", "reconciling"):
            with self.subTest(state=state):
                conn, payload = fixture()
                conn.execute("INSERT INTO trading_commands VALUES ('paper',?)", (state,))
                assert_blocked(self, conn, payload)

    def test_open_robot_trade_or_candidate_blocks(self):
        for table, values in (
            ("robot_trades", ("pending","paper","NEWUSDT","WEDGE",None,None,None)),
            ("robot_candidates", ("paper","OPEN")),
        ):
            with self.subTest(table=table):
                conn, payload = fixture()
                conn.execute(
                    f"INSERT INTO {table} VALUES ({','.join('?' for _ in values)})",
                    values,
                )
                assert_blocked(self, conn, payload)

    def test_unresolved_obligation_must_be_exactly_busdt_stop(self):
        for column, value in (
            ("symbol","OTHERUSDT"), ("winning_leg","TAKE"),
            ("status","TRIGGERED"), ("exec_id","missing"),
        ):
            with self.subTest(column=column):
                conn, payload = fixture()
                conn.execute(f"UPDATE paper_protection_obligations SET {column}=?", (value,))
                assert_blocked(self, conn, payload)

    def test_competing_unresolved_obligation_blocks(self):
        conn, payload = fixture()
        conn.execute(
            "INSERT INTO paper_protection_obligations VALUES "
            "('paper','NEWUSDT','new','STOP','TRIGGERED','new-order','new-exec','1')"
        )
        assert_blocked(self, conn, payload)

    def test_stop_execution_cannot_be_misattributed(self):
        for column, value in (
            ("order_id", "wrong-order"), ("symbol", "OTHERUSDT"),
            ("quantity", "486"), ("side", "Buy"), ("price", "0.3"),
        ):
            with self.subTest(column=column):
                conn, payload = fixture()
                conn.execute(f"UPDATE executions SET {column}=?", (value,))
                assert_blocked(self, conn, payload)

    def test_any_active_mode_or_protection_fails(self):
        for name, field, value in (
            ("backend","paper_live_safe",False),
            ("backend","database_identity","other"),
            ("scanner","mode","SCANNER_RUNNING"),
            ("autopilot","mode","PAPER_AUTO"),
            ("protection","covered_symbols",["BUSDT"]),
            ("protection","armed_symbols",["VIRTUALUSDT"]),
            ("protection","healthy",False),
        ):
            with self.subTest(name=name, field=field):
                conn, payload = fixture()
                payload[name][field] = value
                assert_blocked(self, conn, payload)

    def test_durable_state_overrides_api_claim(self):
        for statement in (
            "UPDATE robot_autopilot_state SET mode='PAPER_AUTO'",
            "UPDATE robot_runtime_state SET recovery_status='READY'",
        ):
            with self.subTest(statement=statement):
                conn, payload = fixture()
                conn.execute(statement)
                assert_blocked(self, conn, payload)

    def test_partial_or_ambiguous_evidence_fails(self):
        conn, payload = fixture()
        conn.execute("UPDATE robot_trades SET exit_time_ms=NULL")
        assert_blocked(self, conn, payload)


if __name__ == "__main__":
    unittest.main()
