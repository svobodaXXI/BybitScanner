import unittest
from types import SimpleNamespace
from unittest.mock import patch
import workspace_owner_launcher as launcher


class WorkspaceOwnerLauncherTests(unittest.TestCase):
    @patch.object(launcher, "os", SimpleNamespace(name="nt"))
    @patch.object(launcher.subprocess, "Popen")
    @patch.object(launcher.Path, "is_file", return_value=True)
    def test_only_valid_target_reaches_launcher(self, file, popen):
        launcher.request_owner_workspace_open("EDITOR", "BTCUSDT", "5m")
        args = popen.call_args.args[0]
        self.assertIn("-Mode", args)
        self.assertIn("EDITOR", args)
        self.assertIn("BTCUSDT", args)
        self.assertIn("5m", args)

    @patch.object(launcher, "os", SimpleNamespace(name="nt"))
    @patch.object(launcher.subprocess, "Popen")
    @patch.object(launcher.Path, "is_file", return_value=True)
    def test_exact_signal_identity_is_forwarded(self, file, popen):
        launcher.request_owner_workspace_open("EDITOR", "BTCUSDT", "5m", "signal:123")
        args = popen.call_args.args[0]
        self.assertEqual(args[args.index("-SignalId") + 1], "signal:123")

    @patch.object(launcher.subprocess, "Popen")
    def test_bad_callback_never_launches(self, popen):
        for mode, symbol, timeframe in (
            ("ROBOT", "BTCUSDT", "5m"), ("EDITOR", "BTC;del", "5m"),
            ("EDITOR", "BTCUSDT", "1w")):
            with self.assertRaises(ValueError):
                launcher.request_owner_workspace_open(mode, symbol, timeframe)
        for signal_id in ("bad/id", "", "a" * 129):
            with self.assertRaises(ValueError):
                launcher.request_owner_workspace_open("EDITOR", "BTCUSDT", "5m", signal_id)
        popen.assert_not_called()


if __name__ == "__main__":
    unittest.main()
