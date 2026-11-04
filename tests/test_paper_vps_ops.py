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

    def test_diagnostic_upgrade_preserves_original_ssh_credentials(self):
        script = Path("tools/upgrade_paper_vps_diagnostics.ps1").read_text()
        self.assertIn("fe3290e74323fdf368fd01a788fb0fdadb4f3171", script)
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
