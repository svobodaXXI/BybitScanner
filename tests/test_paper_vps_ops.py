"""Offline only: never opens SSH, GitHub or VPS connections."""
import unittest
from pathlib import Path
from unittest import mock

from ci import paper_vps_ops as bridge

SHA = "13c46760c2b08cfa9627eac82a46b23a1824ca07"


def event(body, *, login="svobodaXXI", association="OWNER", issue=823,
          action="created", pull_request=False):
    data = {
        "action": action,
        "repository": {"full_name": "svobodaXXI/BybitScanner"},
        "issue": {"number": issue},
        "comment": {"user": {"login": login},
                    "author_association": association, "body": body},
    }
    if pull_request:
        data["issue"]["pull_request"] = {"url": "https://example.invalid"}
    return data


class OwnerBridgeTests(unittest.TestCase):
    def test_owner_bootstrap_shell_fragment_preserves_shared_system_paths(self):
        import subprocess
        script = (
            Path("tools/bootstrap_paper_vps_bridge.ps1")
            .read_text(encoding="utf-8")
        )
        shell = script.split("$setup = @'", 1)[1].split("'@", 1)[0]
        result = subprocess.run(
            ["sh", "-n"], input=shell, text=True, capture_output=True,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertNotIn(
            "install -d -o root -g root -m 0700 /usr/local/libexec", shell
        )
        self.assertIn(
            "test -z \"$(find /usr/local/libexec -maxdepth 0 -perm /022 -print)\"",
            shell,
        )
        self.assertIn("test -z \"$(find /root/.ssh -maxdepth 0 -perm /077 -print)\"", shell)
        self.assertNotIn("chmod 0600 /root/.ssh/authorized_keys", shell)

    def test_exact_owner_comment_matches_one_fixed_operation(self):
        self.assertEqual(
            bridge.parse_request(event("/paper-vps preflight " + SHA)),
            ("preflight", SHA),
        )
        self.assertEqual(
            bridge.parse_request(event("/paper-vps execute " + SHA)),
            ("execute", SHA),
        )

    def test_forged_wrong_scope_and_shell_payloads_cannot_dispatch(self):
        commands = [
            "/paper-vps execute " + SHA + "\nrm -rf /",
            "/paper-vps execute " + SHA + " --force",
            "/paper-vps execute refs/heads/main",
            "/paper-vps maintenance " + SHA,
            "/paper-vps execute " + SHA.upper(),
            " /paper-vps execute " + SHA,
        ]
        for command in commands:
            with self.subTest(command=command):
                with self.assertRaises(ValueError):
                    bridge.parse_request(event(command))
        for altered in (
            {"login": "other"},
            {"association": "COLLABORATOR"},
            {"issue": 822},
            {"action": "edited"},
            {"pull_request": True},
        ):
            with self.subTest(altered=altered):
                with self.assertRaises(ValueError):
                    bridge.parse_request(event("/paper-vps execute " + SHA, **altered))
        wrong_repo = event("/paper-vps execute " + SHA)
        wrong_repo["repository"]["full_name"] = "attacker/repo"
        with self.assertRaises(ValueError):
            bridge.parse_request(wrong_repo)

    def test_diagnose_is_fixed_owner_only_and_not_general_ssh(self):
        self.assertEqual(
            bridge.parse_request(event("/paper-vps diagnose " + SHA)),
            ("diagnose", SHA),
        )
        for bad in ("/paper-vps shell " + SHA,
                    "/paper-vps diagnose " + SHA + " --file=/etc/shadow",
                    "/paper-vps diagnose " + SHA + "; id"):
            with self.assertRaises(ValueError):
                bridge.parse_request(event(bad))

    def test_diagnose_does_not_stage_or_record_or_invoke_maintenance(self):
        output = {"kind": "PAPER_STOP_READ_ONLY", "db": {"available": False}}
        with (
            mock.patch.object(bridge.os, "geteuid", return_value=0),
            mock.patch("pathlib.Path.is_file", return_value=True),
            mock.patch.object(bridge, "_read_only_diag", return_value=output) as read,
            mock.patch.object(bridge, "_stage") as stage,
            mock.patch.object(bridge, "_record_one_shot") as marker,
            mock.patch.object(bridge, "_run") as run,
        ):
            self.assertEqual(bridge.remote("diagnose", SHA), 0)
            read.assert_called_once_with(SHA)
            stage.assert_not_called()
            marker.assert_not_called()
            run.assert_not_called()

    def test_reason_summary_does_not_expose_private_exception_text(self):
        reason = (
            "ROBOT_PROTECTION_COVERAGE_LOST symbol=ALICEUSDT "
            "reason=websocket_disconnect token=SECRET-NOT-FOR-ACTIONS"
        )
        summary = bridge._robot_reason_public_summary(reason)
        self.assertEqual(summary["kind"], "PROTECTION_COVERAGE_LOST")
        self.assertEqual(summary["symbol"], "ALICEUSDT")
        self.assertEqual(len(summary["fingerprint"]), 16)
        self.assertNotIn("SECRET", str(summary))
        self.assertEqual(
            bridge._robot_reason_public_summary("pause_robot could not reach backend")["kind"],
            "PENDING_ENTRY_SYNCHRONIZATION",
        )
        self.assertEqual(
            bridge._robot_reason_public_summary("https://private/path?token=SECRET")["kind"],
            "OTHER_REQUIRES_PRIVATE_REVIEW",
        )
        self.assertNotIn("SECRET", str(bridge._robot_reason_public_summary(
            "https://private/path?token=SECRET",
        )))

    def test_read_only_snapshot_keeps_reason_private_and_counts_obligations(self):
        import json
        import sqlite3
        import tempfile
        from types import SimpleNamespace

        now_ms = 1_794_988_800_000
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            database = root / "paper.sqlite3"
            env = root / "paper.env"
            env.write_text(f"BYBITSCANNER_PAPER_DB={database}", encoding="utf-8")
            with sqlite3.connect(database) as conn:
                conn.executescript("""
                    CREATE TABLE robot_runtime_state (
                        trading_account_id TEXT, mode TEXT, recovery_status TEXT,
                        reason TEXT, version INTEGER, updated_at_ms INTEGER);
                    CREATE TABLE robot_candidates (
                        trading_account_id TEXT, symbol TEXT, status TEXT,
                        state_revision INTEGER, robot_state_json TEXT);
                    CREATE TABLE scanner_runtime_state (
                        trading_account_id TEXT, mode TEXT);
                    CREATE TABLE robot_autopilot_state (
                        trading_account_id TEXT, mode TEXT);
                    CREATE TABLE paper_limit_orders (
                        trading_account_id TEXT, status TEXT);
                    CREATE TABLE robot_trades (
                        trade_id TEXT PRIMARY KEY,
                        trading_account_id TEXT, exit_time_ms INTEGER, exit_reason TEXT);
                    CREATE TABLE position_projections (
                        trading_account_id TEXT, side TEXT, quantity TEXT);
                    CREATE TABLE paper_protection_obligations (
                        trading_account_id TEXT, status TEXT);
                """)
                conn.execute(
                    "INSERT INTO robot_runtime_state VALUES (?,?,?,?,?,?)",
                    ("paper", "ROBOT_RUNNING", "RECONCILIATION_REQUIRED",
                     "ROBOT_PROTECTION_COVERAGE_LOST symbol=ALICEUSDT "
                     "reason=SECRET-SHOULD-NOT-LEAK", 19, now_ms - 5000),
                )
                conn.executemany("INSERT INTO robot_trades VALUES (?,?,?,?)", [
                    ("te_today", "paper", now_ms - 1000, "EMERGENCY_CLOSE"),
                    ("te_stop", "paper", now_ms - 2000, "STOP"),
                    ("te_old", "paper", now_ms - 80 * 60 * 60 * 1000, "TAKE"),
                    ("te_nov17", "paper", 1794870000000, "EMERGENCY_CLOSE"),
                    ("te_nov18", "paper", 1794960000000, "EMERGENCY_CLOSE"),
                ])
                conn.executemany("INSERT INTO position_projections VALUES (?,?,?)", [
                    ("paper", "LONG", "3.5"), ("paper", "FLAT", "0"),
                ])
                conn.execute(
                    "INSERT INTO paper_protection_obligations VALUES (?,?)",
                    ("paper", "DISPATCHING"),
                )
            incident_dir = root / "robot_incidents"
            incident_dir.mkdir()
            (incident_dir / "incident.json").write_text(json.dumps({
                "schema_version": 1, "timestamp_ms": 1794869999999,
                "incident_type": "ROBOT_PROTECTION_EMERGENCY_CLOSE",
                "reason_code": "MARKET_DATA_CONTINUITY_LOST",
                "trade_id": "te_nov17",
                "facts": {
                    "recovery_reason": "websocket_disconnect:SECRET-SHOULD-NOT-LEAK",
                    "continuity_fence_reason": "websocket_disconnect:SECRET-SHOULD-NOT-LEAK",
                    "continuity_fence_id": "continuity-fence-138",
                    "continuity_fence_symbol": "FAKEUSDT",
                    "intended_stop_crossed": False,
                },
            }), encoding="utf-8")
            (incident_dir / "fence.json").write_text(json.dumps({
                "schema_version": 1, "timestamp_ms": 1794869990000,
                "incident_type": "ROBOT_PROTECTION_CONTINUITY_FENCE",
                "reason_code": "MARKET_DATA_CONTINUITY_FENCE",
                "symbol": "FAKEUSDT",
                "facts": {
                    "fence_id": "continuity-fence-138",
                    "continuity_reason": "websocket_disconnect:SECRET-SHOULD-NOT-LEAK",
                    "ingress_capacity": 64,
                    "ingress_high_watermark": 64,
                    "ingress_max_queue_latency_ms": "2240.7",
                    "ingress_max_processing_ms": "1900.2",
                },
            }), encoding="utf-8")
            owner_dir = root / "owner_incidents"
            owner_dir.mkdir()
            for name, timestamp, stage, facts in (
                ("slow", 1794869987000, "OWNER_SLOW", {
                    "task_kind": "protection", "task_label": "SECRET-NEVER-PUBLISH",
                    "processing_ms": "812.5", "ingress_queue_latency_ms": "103.2",
                    "symbol": "SECRETUSDT",
                }),
                ("overflow", 1794869989000, "INGRESS_OVERFLOW", {
                    "capacity": 64, "pending": 64, "symbol": "SECRETUSDT",
                }),
                ("watermark", 1794869988000, "INGRESS_WATERMARK", {
                    "capacity": 64, "pending": 64,
                }),
                ("outside", 1794875000000, "OWNER_SLOW", {
                    "task_kind": "call", "processing_ms": "9999",
                }),
            ):
                (owner_dir / (name + ".json")).write_text(json.dumps({
                    "schema_version": 1, "timestamp_ms": timestamp,
                    "incident_type": "PAPER_OWNER_OBSERVABILITY",
                    "stage": stage, "reason_code": stage, "facts": facts,
                }), encoding="utf-8")
            with (
                mock.patch.object(bridge.time, "time", return_value=now_ms / 1000),
                mock.patch.object(bridge.urlrequest, "urlopen",
                                  side_effect=OSError("offline")) as http,
                mock.patch.object(bridge.subprocess, "run",
                                  return_value=SimpleNamespace(stdout="inactive")) as commands,
            ):
                snapshot = bridge._read_only_diag(
                    SHA, root=root, env_file=env, transactions=root,
                )
            self.assertEqual(snapshot["version"], 2)
            db = snapshot["db"]
            self.assertTrue(db["quick_check"])
            self.assertEqual(db["robot_reason"]["kind"], "PROTECTION_COVERAGE_LOST")
            self.assertEqual(db["robot_reason"]["symbol"], "ALICEUSDT")
            self.assertEqual(db["robot_state_version"], 19)
            self.assertEqual(db["robot_state_updated_at_ms"], now_ms - 5000)
            self.assertEqual(db["nonflat_position_projections"], 1)
            self.assertEqual(db["unresolved_protection_obligations"], 1)
            self.assertEqual(db["recent_exit_reasons_72h"],
                             {"EMERGENCY_CLOSE": 3, "STOP": 1})
            self.assertEqual(db["nov17_18_msk_exit_reasons"], {
                "2026-11-17": {"EMERGENCY_CLOSE": 1},
                "2026-11-18": {"EMERGENCY_CLOSE": 2, "STOP": 1},
            })
            self.assertEqual(db["nov17_18_emergency_incidents"], {
                "emergency_trades": 3,
                "journal_state": "COMPLETE_SCAN",
                "retained_files": 2,
                "unreadable_files": 0,
                "linked_emergency_trades": 1,
                "linked_continuity_loss_trades": 1,
                "incident_not_after_exit_trades": 1,
                "linked_stop_already_crossed_trades": 0,
                "recovery_trigger_classes": {"WEBSOCKET_DISCONNECT": 1},
                "fence_trigger_classes": {"WEBSOCKET_DISCONNECT": 1},
                "linked_original_fence_trades": 1,
                "fence_ingress_watermark_at_capacity_trades": 1,
                "fence_queue_latency_over_2s_trades": 1,
                "fence_processing_over_2s_trades": 0,
                "fence_max_queue_latency_ms": 2240.7,
                "fence_max_processing_ms": 1900.2,
                "owner_ingress_history": {
                    "journal_state": "COMPLETE_SCAN",
                    "retained_files": 4, "unreadable_files": 0,
                    "nov17_18_retained_records": 4,
                    "around_fence_write_records": 3,
                    "fence_windows_with_records": 1,
                    "fence_windows_checked": 1,
                    "around_fence_ingress_overflow_records": 1,
                    "around_fence_full_watermark_records": 1,
                    "around_fence_slow_task_records": 1,
                    "around_fence_slow_task_kinds": {"protection": 1},
                    "around_fence_max_slow_processing_ms": 812.5,
                    "around_fence_max_slow_queue_latency_ms": 103.2,
                    "possible_pruned_history": False,
                },
                "without_matching_incident_trades": 2,
            })
            self.assertNotIn("SECRET", json.dumps(snapshot))
            self.assertEqual(http.call_count, 4)
            self.assertEqual(commands.call_count, 3)

    def test_continuity_reason_class_only_allows_fixed_labels(self):
        self.assertEqual(bridge._continuity_reason_class("ingress_overflow"),
                         "INGRESS_OVERFLOW")
        self.assertEqual(bridge._continuity_reason_class(
            "websocket_disconnect:SECRET-SHOULD-NOT-LEAK"), "WEBSOCKET_DISCONNECT")
        self.assertEqual(bridge._continuity_reason_class(
            "unknown SECRET-SHOULD-NOT-LEAK"), "OTHER")
        self.assertEqual(bridge._continuity_reason_class(None), "UNAVAILABLE")

    def test_missing_owner_ingress_journal_is_not_a_negative_diagnosis(self):
        import tempfile
        with tempfile.TemporaryDirectory() as directory:
            result = bridge._nov17_18_owner_ingress_telemetry(
                Path(directory) / "paper.sqlite3", (1794869990000,), 1794988800000)
            self.assertEqual(result, {"journal_state": "MISSING_DIRECTORY"})

    def test_missing_incident_journal_never_claims_zero_incidents(self):
        import sqlite3
        import tempfile
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            with sqlite3.connect(":memory:") as conn:
                conn.execute("CREATE TABLE robot_trades "
                             "(trade_id TEXT, trading_account_id TEXT, "
                             "exit_time_ms INTEGER, exit_reason TEXT)")
                conn.execute("INSERT INTO robot_trades VALUES (?,?,?,?)",
                             ("te_missing", "paper", 1794870000000,
                              "EMERGENCY_CLOSE"))
                result = bridge._nov17_18_emergency_incidents(
                    conn, root / "paper.sqlite3", 1794988800000)
            self.assertEqual(result["emergency_trades"], 1)
            self.assertEqual(result["journal_state"], "MISSING_DIRECTORY")
            self.assertNotIn("linked_emergency_trades", result)

    def test_diagnostic_upgrade_preserves_original_ssh_credentials(self):
        script = Path("tools/upgrade_paper_vps_diagnostics.ps1").read_text()
        self.assertIn("b2ae206e685de274bd56370451dd41bb64b1584d", script)
        self.assertIn('test "$(sha256sum "$target" | cut -d \' \' -f1)" = "$old"', script)
        self.assertIn("DIAGNOSTICS_HANDLER_INSTALLED", script)
        for forbidden in ("authorized_keys", "gh secret set", "systemctl stop",
                          "systemctl restart", "sqlite3 ", "rm -rf"):
            self.assertNotIn(forbidden, script)

    def test_ssh_target_must_be_exact_root_hostname(self):
        self.assertEqual(bridge.validate_target("root@vps.example"), "root@vps.example")
        for item in ("", "user@host", "root@host;cmd", "root@host -oProxyCommand=x",
                     "root@../bad", "root@host\nexec", "root@host/path"):
            with self.subTest(target=item):
                with self.assertRaises(ValueError):
                    bridge.validate_target(item)

    def test_preflight_inspects_installed_root_not_git_staging(self):
        # Imported staging modules derive ROOT from their own file path.
        # Failing to override it verifies staging against itself instead
        # of the still-running /opt/BybitScanner release.
        self.assertIn(
            'inspect_staged_release(\n        sha, stage=stage, root=Path("/opt/BybitScanner"))',
            bridge.PREFLIGHT,
        )

    def test_preflight_never_invokes_coordinator_or_one_shot_marker(self):
        calls = []
        def run(argv, **kwargs):
            calls.append(argv)
            return "PREFLIGHT_PASS: synthetic"
        with (
            mock.patch.object(bridge.os, "geteuid", return_value=0),
            mock.patch("pathlib.Path.is_file", return_value=True),
            mock.patch.object(bridge, "_stage", return_value=Path("/synthetic-stage")),
            mock.patch.object(bridge, "_run", side_effect=run),
            mock.patch.object(bridge, "_record_one_shot") as record,
        ):
            self.assertEqual(bridge.remote("preflight", SHA), 0)
            record.assert_not_called()
        self.assertEqual(len(calls), 1)
        self.assertIn("tools.paper_two_orphan_proof", calls[0][2])
        self.assertNotIn("tools.paper_maintenance", str(calls))

    def test_execute_is_one_coordinator_after_pinned_proof_and_marker(self):
        calls = []
        def run(argv, **kwargs):
            calls.append(argv)
            if "tools.paper_maintenance" in argv:
                return "READY: exact synthetic PAPER acceptance"
            return "PREFLIGHT_PASS: synthetic"
        with (
            mock.patch.object(bridge.os, "geteuid", return_value=0),
            mock.patch("pathlib.Path.is_file", return_value=True),
            mock.patch.object(bridge, "_stage", return_value=Path("/synthetic-stage")),
            mock.patch.object(bridge, "_run", side_effect=run),
            mock.patch.object(bridge, "_record_one_shot") as record,
        ):
            self.assertEqual(bridge.remote("execute", SHA), 0)
            record.assert_called_once_with(SHA)
        self.assertEqual(len(calls), 2)
        self.assertEqual(calls[1][:4], [
            str(bridge.VENV), "-m", "tools.paper_maintenance", SHA,
        ])
        self.assertIn("--dual-orphan-handoff-20261103", calls[1])
        self.assertIn("--start-paper-after-editor", calls[1])

    def test_ambiguous_or_failed_preflight_never_records_or_executes(self):
        with (
            mock.patch.object(bridge.os, "geteuid", return_value=0),
            mock.patch("pathlib.Path.is_file", return_value=True),
            mock.patch.object(bridge, "_stage", return_value=Path("/synthetic-stage")),
            mock.patch.object(bridge, "_run", side_effect=RuntimeError("proof failed")) as run,
            mock.patch.object(bridge, "_record_one_shot") as record,
        ):
            self.assertEqual(bridge.remote("execute", SHA), 2)
            run.assert_called_once()
            record.assert_not_called()

    def test_duplicate_one_shot_marker_blocks_coordinator(self):
        calls = []
        def run(argv, **kwargs):
            calls.append(argv)
            return "PREFLIGHT_PASS: synthetic"
        with (
            mock.patch.object(bridge.os, "geteuid", return_value=0),
            mock.patch("pathlib.Path.is_file", return_value=True),
            mock.patch.object(bridge, "_stage", return_value=Path("/synthetic-stage")),
            mock.patch.object(bridge, "_run", side_effect=run),
            mock.patch.object(bridge, "_record_one_shot", side_effect=FileExistsError),
        ):
            self.assertEqual(bridge.remote("execute", SHA), 2)
        self.assertEqual(len(calls), 1)

    def test_forced_ssh_requires_root_owned_pinned_installed_script(self):
        import stat
        from types import SimpleNamespace

        pinned = str(bridge.PINNED_REMOTE)
        protected = SimpleNamespace(st_mode=stat.S_IFREG | 0o700, st_uid=0)
        with (
            mock.patch.object(bridge, "__file__", pinned),
            mock.patch("pathlib.Path.lstat", return_value=protected),
        ):
            self.assertEqual(
                bridge.authorized_remote_request("preflight " + SHA),
                ("preflight", SHA),
            )
            self.assertEqual(
                bridge.authorized_remote_request("execute " + SHA),
                ("execute", SHA),
            )
            self.assertEqual(
                bridge.authorized_remote_request("diagnose " + SHA),
                ("diagnose", SHA),
            )
            for command in (
                None, "", "execute " + SHA + " --force",
                "execute " + SHA + "\\nanything",
                "remote execute " + SHA,
                "bash -c id",
            ):
                with self.subTest(command=command):
                    with self.assertRaises(ValueError):
                        bridge.authorized_remote_request(command)

        # A source file in any checkout or injected via stdin is never
        # permitted to act as the privileged SSH command handler.
        with (
            mock.patch.object(bridge, "__file__", "/tmp/rogue.py"),
            mock.patch("pathlib.Path.lstat", return_value=protected),
        ):
            with self.assertRaises(ValueError):
                bridge.authorized_remote_request("execute " + SHA)
        for st_mode, st_uid in (
            (stat.S_IFREG | 0o755, 0),
            (stat.S_IFLNK | 0o700, 0),
            (stat.S_IFREG | 0o700, 1000),
        ):
            with (
                mock.patch.object(bridge, "__file__", pinned),
                mock.patch("pathlib.Path.lstat", return_value=SimpleNamespace(
                    st_mode=st_mode, st_uid=st_uid)),
            ):
                with self.assertRaises(ValueError):
                    bridge.authorized_remote_request("execute " + SHA)

    def test_ssh_entrypoint_cannot_be_called_as_unrestricted_remote(self):
        with mock.patch.object(bridge, "remote") as remote:
            self.assertEqual(bridge.main(["remote", "execute", SHA]), 2)
            remote.assert_not_called()
        with (
            mock.patch.object(
                bridge, "authorized_remote_request",
                return_value=("preflight", SHA),
            ) as attest,
            mock.patch.object(bridge, "remote", return_value=0) as remote,
            mock.patch.dict(bridge.os.environ, {
                "SSH_ORIGINAL_COMMAND": "preflight " + SHA,
            }),
        ):
            self.assertEqual(bridge.main(["forced"]), 0)
            attest.assert_called_once_with("preflight " + SHA)
            remote.assert_called_once_with("preflight", SHA)

    def test_invalid_target_never_prepares_stage(self):
        with mock.patch.object(bridge, "_stage") as stage:
            self.assertEqual(bridge.remote("execute", "not-a-sha"), 2)
            stage.assert_not_called()


if __name__ == "__main__":
    unittest.main()
