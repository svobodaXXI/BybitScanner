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
        CREATE TABLE position_projections (trading_account_id TEXT, symbol TEXT, side TEXT, quantity TEXT, sync_state TEXT);
        CREATE TABLE robot_trades (
            trade_id TEXT, trading_account_id TEXT, symbol TEXT, pattern TEXT,
            exit_reason TEXT, exit_time_ms INTEGER, exit_price TEXT
        );
        CREATE TABLE robot_candidates (trading_account_id TEXT, symbol TEXT, status TEXT);
        CREATE TABLE paper_limit_orders (trading_account_id TEXT, status TEXT);
        CREATE TABLE trading_commands (trading_account_id TEXT, current_state TEXT);
        CREATE TABLE reconciliation_checkpoints (
            trading_account_id TEXT, completed_at_ms INTEGER
        );
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
        INSERT INTO position_projections VALUES ('paper','BUSDT','Flat','0','synced');
        INSERT INTO position_projections VALUES ('paper','VIRTUALUSDT','Flat','0','synced');
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

    def test_only_exact_incident_roles_can_replace_empty_coverage(self):
        conn, payload = fixture()
        payload["protection"].update(
            covered_symbols=["BUSDT", "AUSDT", "KMNOUSDT"],
            coverage_roles={
                "BUSDT": "OBLIGATION",
                "AUSDT": "ENTRY_PENDING",
                "KMNOUSDT": "ENTRY_PENDING",
            },
            armed_symbols=["AUSDT", "KMNOUSDT"],
        )
        self.assertEqual(prove_flat_recovery(conn, **payload),
                         "FLAT_RECOVERY_EVIDENCE_PROVEN_ONLY")
        self.assertEqual(conn.execute(
            "SELECT status FROM paper_protection_obligations"
        ).fetchone(), ("DISPATCHING",))

    def test_approved_armed_entry_candidate_is_not_stale(self):
        conn, payload = fixture()
        payload["protection"].update(
            covered_symbols=["BUSDT", "AUSDT", "KMNOUSDT"],
            coverage_roles={"BUSDT": "OBLIGATION", "AUSDT": "ENTRY_PENDING",
                            "KMNOUSDT": "ENTRY_PENDING"},
            armed_symbols=["AUSDT", "KMNOUSDT"],
        )
        conn.execute(
            "INSERT INTO robot_candidates VALUES ('paper','AUSDT','APPROVED')"
        )
        assert_blocked(self, conn, payload)

    def test_wrong_incident_role_or_extra_cover_blocks(self):
        changes = (
            ("coverage_roles", {
                "BUSDT": "EXPOSURE", "AUSDT": "ENTRY_PENDING",
                "KMNOUSDT": "ENTRY_PENDING"}),
            ("armed_symbols", ["AUSDT"]),
            ("armed_symbols", ["AUSDT", "KMNOUSDT", "NEWUSDT"]),
            ("covered_symbols", ["BUSDT", "AUSDT", "KMNOUSDT", "NEWUSDT"]),
            ("covered_symbols", ["BUSDT", "AUSDT"]),
        )
        for field, value in changes:
            with self.subTest(field=field, value=value):
                conn, payload = fixture()
                payload["protection"].update(
                    covered_symbols=["BUSDT", "AUSDT", "KMNOUSDT"],
                    coverage_roles={
                        "BUSDT": "OBLIGATION",
                        "AUSDT": "ENTRY_PENDING",
                        "KMNOUSDT": "ENTRY_PENDING",
                    },
                    armed_symbols=["AUSDT", "KMNOUSDT"],
                )
                payload["protection"][field] = value
                assert_blocked(self, conn, payload)

    def test_incident_roles_do_not_override_active_entry_or_exposure(self):
        for statement in (
            "INSERT INTO trading_commands VALUES ('paper','submitting')",
            "INSERT INTO paper_limit_orders VALUES ('paper','open')",
            "INSERT INTO robot_candidates VALUES ('paper','KMNOUSDT','OPEN')",
            "UPDATE position_projections SET side='Short',quantity='2' WHERE symbol='BUSDT'",
        ):
            with self.subTest(statement=statement):
                conn, payload = fixture()
                payload["protection"].update(
                    covered_symbols=["BUSDT", "AUSDT", "KMNOUSDT"],
                    coverage_roles={
                        "BUSDT": "OBLIGATION",
                        "AUSDT": "ENTRY_PENDING",
                        "KMNOUSDT": "ENTRY_PENDING",
                    },
                    armed_symbols=["AUSDT", "KMNOUSDT"],
                )
                conn.execute(statement)
                assert_blocked(self, conn, payload)

    def test_open_position_blocks_even_if_apis_report_healthy(self):
        conn, payload = fixture()
        conn.execute("UPDATE position_projections SET side='Short',quantity='422' "
                     "WHERE symbol='VIRTUALUSDT'")
        assert_blocked(self, conn, payload)

    def test_missing_virtual_flat_projection_blocks(self):
        conn, payload = fixture()
        conn.execute("DELETE FROM position_projections WHERE symbol='VIRTUALUSDT'")
        assert_blocked(self, conn, payload)

    def test_missing_busdt_flat_projection_blocks(self):
        conn, payload = fixture()
        conn.execute("DELETE FROM position_projections WHERE symbol='BUSDT'")
        assert_blocked(self, conn, payload)

    def test_unfinished_paper_reconciliation_blocks_historical_handoff(self):
        conn, payload = fixture()
        conn.execute(
            "INSERT INTO reconciliation_checkpoints VALUES ('other',NULL)"
        )
        # Other account's unfinished work must not affect the PAPER gate.
        self.assertEqual(
            prove_flat_recovery(conn, **payload),
            "FLAT_RECOVERY_EVIDENCE_PROVEN_ONLY",
        )
        conn.execute(
            "INSERT INTO reconciliation_checkpoints VALUES ('paper',NULL)"
        )
        before = conn.total_changes
        with self.assertRaisesRegex(
            FlatRecoveryBlocked, "unfinished_reconciliation_checkpoint",
        ):
            prove_flat_recovery(conn, **payload)
        self.assertEqual(conn.total_changes, before)
        conn.execute(
            "UPDATE reconciliation_checkpoints SET completed_at_ms=100 "
            "WHERE trading_account_id='paper'"
        )
        self.assertEqual(
            prove_flat_recovery(conn, **payload),
            "FLAT_RECOVERY_EVIDENCE_PROVEN_ONLY",
        )
        conn.close()

    def test_flat_projection_must_be_durably_synchronized(self):
        for status in (None, "", "unknown", "stale", "pending"):
            with self.subTest(sync_state=status):
                conn, payload = fixture()
                conn.execute(
                    "UPDATE position_projections SET sync_state=? "
                    "WHERE symbol='BUSDT'", (status,),
                )
                before = conn.total_changes
                assert_blocked(self, conn, payload)
                self.assertEqual(conn.total_changes, before)
                conn.close()
        # Both canonical synchronized markers remain valid, never used to
        # infer exposure from an untrusted projection.
        conn, payload = fixture()
        conn.execute(
            "UPDATE position_projections SET sync_state='synchronized' "
            "WHERE symbol='VIRTUALUSDT'"
        )
        self.assertEqual(
            prove_flat_recovery(conn, **payload),
            "FLAT_RECOVERY_EVIDENCE_PROVEN_ONLY",
        )
        conn.close()

    def test_null_and_unknown_durable_work_never_proves_flat(self):
        # SQLite three-valued logic: NOT IN and != silently exclude NULL.
        # This historical exception must refuse any unclassified work, not
        # only explicitly OPEN candidates or known pending commands.
        statements = (
            "INSERT INTO robot_candidates VALUES ('paper','NEWUSDT',NULL)",
            "INSERT INTO robot_candidates VALUES ('paper','NEWUSDT','APPROVED')",
            "INSERT INTO robot_candidates VALUES ('paper','NEWUSDT','UNKNOWN')",
            "INSERT INTO paper_limit_orders VALUES ('paper',NULL)",
            "INSERT INTO trading_commands VALUES ('paper',NULL)",
            "INSERT INTO paper_protection_obligations VALUES "
            "('paper','OTHERUSDT','unknown','STOP',NULL,'order','exec','1')",
        )
        for statement in statements:
            with self.subTest(statement=statement):
                conn, payload = fixture()
                conn.execute(statement)
                before = conn.total_changes
                assert_blocked(self, conn, payload)
                self.assertEqual(conn.total_changes, before)
                conn.close()

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
            ("robot_candidates", ("paper","NEWUSDT","OPEN")),
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

    def test_busdt_stop_requires_finite_positive_economics(self):
        # Matching infinities are equal as Decimal values, but can never
        # attest an immutable PAPER fill or a safe recovery handoff.
        cases = (
            ("obligation-and-fill-quantity-infinity",
             "UPDATE paper_protection_obligations SET observed_quantity='Infinity'",
             "UPDATE executions SET quantity='Infinity'"),
            ("trade-and-fill-price-infinity",
             "UPDATE robot_trades SET exit_price='Infinity'",
             "UPDATE executions SET price='Infinity'"),
            ("negative-quantities",
             "UPDATE paper_protection_obligations SET observed_quantity='-487'",
             "UPDATE executions SET quantity='-487'"),
            ("zero-prices",
             "UPDATE robot_trades SET exit_price='0'",
             "UPDATE executions SET price='0'"),
            ("malformed-quantity",
             "UPDATE paper_protection_obligations SET observed_quantity='not-a-number'",
             None),
            ("missing-execution-price",
             "UPDATE executions SET price=NULL",
             None),
        )
        for name, first, second in cases:
            with self.subTest(case=name):
                conn, payload = fixture()
                conn.execute(first)
                if second is not None:
                    conn.execute(second)
                before = conn.total_changes
                with self.assertRaisesRegex(
                    FlatRecoveryBlocked, "busdt_historical_stop_evidence_unproven",
                ):
                    prove_flat_recovery(conn, **payload)
                self.assertEqual(conn.total_changes, before)
                conn.close()

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
