import io
import unittest
from contextlib import redirect_stdout
from unittest.mock import patch

from terminal.market_data.workspace_errors import WorkspaceErrorDetails
from tools.dev.workspace_doctor import DoctorFailure, diagnose, main


class _Client:
    request_id = "doctor-test"

    def __init__(self, *, supported=True, ready=True, stream_ready=True) -> None:
        self.supported = supported
        self.ready = ready
        self.stream_ready = stream_ready
        self.calls = []
        self.generation = 7

    def get_json(self, path):
        self.calls.append(("GET", path))
        if path == "/api/instruments":
            return {"instruments": [{"symbol": "OGUSDT"}] if self.supported else []}
        return {"workspace": {
            "requested_symbol": "OGUSDT", "active_symbol": "OGUSDT",
            "active_generation": self.generation, "switch_state": "READY",
            "pending_symbol": None, "last_error": None,
            "readiness": {"ready": self.ready},
        }}

    def post_json(self, path, payload):
        self.calls.append(("POST", path, payload))
        return {"symbol": "OGUSDT", "generation": self.generation}

    def open_workspace_stream(self, symbol, interval):
        self.calls.append(("STREAM", symbol, interval))
        if not self.stream_ready:
            raise DoctorFailure(WorkspaceErrorDetails(
                "upstream_market_data_failure", "workspace_stream", symbol,
                symbol, True, "stream unavailable", self.request_id,
            ))
        return {
            "kind": "workspace_snapshot", "state": "READY", "symbol": symbol,
            "workspace_generation": self.generation,
        }


class WorkspaceDoctorTests(unittest.TestCase):
    def test_supported_ready_path_is_compact_and_non_mutating_after_activation(self):
        client = _Client()
        report = diagnose("ogusdt", "5", client)
        self.assertEqual(report.exit_code, 0)
        self.assertEqual(report.render().splitlines(), [
            "STATUS PASS",
            "INSTRUMENT PASS symbol=OGUSDT",
            "SWITCH PASS active_symbol=OGUSDT generation=7",
            "READINESS PASS book=true trades=true candles=true",
            "STREAM PASS kind=workspace_snapshot generation=7",
            "STATE PASS switch_state=READY active_symbol=OGUSDT generation=7",
        ])
        self.assertEqual(client.calls, [
            ("GET", "/api/instruments"),
            ("POST", "/api/workspace/symbol", {"symbol": "OGUSDT"}),
            ("GET", "/api/workspace/state"),
            ("STREAM", "OGUSDT", "5"),
            ("GET", "/api/workspace/state"),
        ])

    def test_unsupported_symbol_fails_semantically_before_activation(self):
        client = _Client(supported=False)
        report = diagnose("BADUSDT", "5", client)
        self.assertEqual(report.exit_code, 1)
        self.assertIn("INSTRUMENT FAIL", report.render())
        self.assertIn('code="unsupported_instrument"', report.render())
        self.assertIn('stage="instrument_lookup"', report.render())
        self.assertEqual(client.calls, [("GET", "/api/instruments")])

    def test_classifies_not_ready_and_stream_unavailable(self):
        not_ready = diagnose("OGUSDT", "5", _Client(ready=False))
        self.assertEqual(not_ready.exit_code, 1)
        self.assertIn("READINESS FAIL", not_ready.render())
        self.assertIn('code="candidate_not_ready"', not_ready.render())

        stream = diagnose("OGUSDT", "5", _Client(stream_ready=False))
        self.assertEqual(stream.exit_code, 1)
        self.assertIn("STREAM FAIL", stream.render())
        self.assertIn('stage="workspace_stream"', stream.render())

    def test_main_has_deterministic_exit_code_and_compact_output(self):
        client = _Client()
        with patch(
            "tools.dev.workspace_doctor.WorkspaceDoctorClient",
            return_value=client,
        ):
            output = io.StringIO()
            with redirect_stdout(output):
                exit_code = main(["--symbol", "OGUSDT", "--interval", "5"])
            self.assertEqual(exit_code, 0)
            self.assertEqual(output.getvalue().count("\n"), 6)

            output = io.StringIO()
            with redirect_stdout(output):
                exit_code = main(["--symbol", "OGUSDT", "--interval", "bad"])
            self.assertEqual(exit_code, 1)
            self.assertTrue(output.getvalue().startswith("STATUS FAIL\nINPUT FAIL\n"))


if __name__ == "__main__":
    unittest.main()
