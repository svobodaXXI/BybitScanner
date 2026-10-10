"""Autopilot A8: owner authorization, PAPER_AUTO confirmation, pre-admission evidence.

Temporary DBs and fake runtimes only. PAPER_AUTO is never enabled on a working DB.
"""

import json
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer
from pathlib import Path

import robot_state_machine
from terminal.application.robot_autopilot import (
    OUTCOME_WAIT, REASON_CANDIDATE_FRESHNESS_UNKNOWN,
)
from terminal.application.robot_autopilot_shadow import (
    PAPER_AUTO_MODE, SOURCE_SCANNER, resolve_autopilot_evidence_target,
)
from terminal.runtime.closed_candle_cache import PreparedCatchupEvidence
from terminal.runtime.paper_http_server import PaperHttpHandler
from tests.test_robot_autopilot_shadow import ACCOUNT, _Db, _wedge

OWNER_TOKEN = "autopilot-owner-token-with-at-least-32-chars"
HEADER = "X-BybitScanner-Autopilot-Owner-Token"

SNAPSHOT = {
    "symbol": "ONGUSDT", "pattern": "Falling Wedge",
    "geometry": {"current_index": 10, "apex": {"index": 30},
                 "upper_line": {"slope": 0.1, "intercept": 10},
                 "lower_line": {"slope": -0.1, "intercept": 20}},
}


def _candle(index, *, high=105, low=95, close=100):
    return {"closed": True, "timeframe": "1", "geometry_index": index,
            "high": high, "low": low, "close": close}


class _Target:
    def __init__(self):
        self.calls = []

    def set_autopilot_mode(self, mode, *, confirm_paper_auto=False):
        self.calls.append((mode, confirm_paper_auto))
        return {"mode": str(mode).upper()}


class _Runtime:
    def __init__(self):
        self.target = _Target()

    def call(self, operation):
        return operation(self.target)


class OwnerAuthHttpTests(unittest.TestCase):
    def _serve(self, token=OWNER_TOKEN):
        server = ThreadingHTTPServer(("127.0.0.1", 0), PaperHttpHandler)
        server.runtime = _Runtime()
        server.autopilot_owner_token = token
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()

        def stop():
            server.shutdown()
            server.server_close()
            thread.join(timeout=2)

        self.addCleanup(stop)
        return server

    def _post(self, server, body, token=None):
        request = urllib.request.Request(
            f"http://127.0.0.1:{server.server_address[1]}/api/robot/autopilot",
            data=json.dumps(body).encode("utf-8"), method="POST",
            headers={"Content-Type": "application/json", **({HEADER: token} if token else {})},
        )
        try:
            with urllib.request.urlopen(request) as response:
                return response.status, json.loads(response.read())
        except urllib.error.HTTPError as error:
            return error.code, json.loads(error.read())

    def test_off_and_shadow_need_no_owner_token(self):
        server = self._serve()
        for mode in ("OFF", "SHADOW"):
            with self.subTest(mode=mode):
                status, _body = self._post(server, {"mode": mode})
                self.assertEqual(status, 200)
        self.assertEqual(server.runtime.target.calls, [("OFF", False), ("SHADOW", False)])

    def test_paper_auto_without_a_valid_owner_token_is_forbidden_before_anything_else(self):
        for label, token, supplied in (
            ("missing", OWNER_TOKEN, None),
            ("wrong", OWNER_TOKEN, "x" * 44),
            ("server token unset", "", OWNER_TOKEN),
            ("server token too short", "short-token", "short-token"),
        ):
            with self.subTest(label):
                server = self._serve(token)
                for body in ({"mode": "PAPER_AUTO", "confirm_paper_auto": True},
                             {"mode": "PAPER_AUTO"},
                             {"mode": "PAPER_AUTO", "confirm_paper_auto": "yes"}):
                    status, _ = self._post(server, body, supplied)
                    self.assertEqual(status, 403)
                self.assertEqual(server.runtime.target.calls, [])

    def test_confirmation_must_be_present_and_a_real_boolean(self):
        server = self._serve()
        for body, expected in (
            ({"mode": "PAPER_AUTO"}, 409),
            ({"mode": "PAPER_AUTO", "confirm_paper_auto": False}, 409),
            ({"mode": "PAPER_AUTO", "confirm_paper_auto": "true"}, 400),
            ({"mode": "PAPER_AUTO", "confirm_paper_auto": 1}, 400),
            ({"mode": "PAPER_AUTO", "confirm_paper_auto": None}, 400),
        ):
            with self.subTest(body=body):
                status, _ = self._post(server, body, OWNER_TOKEN)
                self.assertEqual(status, expected)
        self.assertEqual(server.runtime.target.calls, [])

        status, _ = self._post(server, {"mode": "PAPER_AUTO", "confirm_paper_auto": True},
                               OWNER_TOKEN)
        self.assertEqual(status, 200)
        self.assertEqual(server.runtime.target.calls, [("PAPER_AUTO", True)])

    def test_malformed_requests_stay_bad_requests(self):
        server = self._serve()
        for body in ({"mode": 1}, {"mode": "SHADOW", "extra": True}, {},
                     {"mode": "SHADOW", "confirm_paper_auto": "yes"}):
            with self.subTest(body=body):
                self.assertEqual(self._post(server, body, OWNER_TOKEN)[0], 400)
        self.assertEqual(server.runtime.target.calls, [])


class FreshnessEvidenceTests(unittest.TestCase):
    def _runtime(self, temp):
        from tests.test_continuity_recovery_candidate_snapshot import _runtime

        runtime = _runtime(temp)
        runtime._robot_command_dispatcher = lambda operation: operation(runtime)
        return runtime

    def test_successful_empty_evidence_is_fresh_failure_waits_apex_rejects(self):
        with tempfile.TemporaryDirectory() as temp:
            runtime = self._runtime(temp)
            try:
                def broken(_symbol, _snapshot):
                    raise RuntimeError("evidence was never prepared")

                for evidence, expected in (
                    (lambda *_: (), True),                      # loaded fine, nothing new
                    (lambda *_: (_candle(12),), True),          # before the apex
                    (lambda *_: (_candle(30),), False),         # EXPIRED_AT_APEX
                    (broken, None),                             # load failure
                    (None, None),                               # no evidence source
                ):
                    with self.subTest(expected=expected):
                        runtime.robot_catchup_evidence = evidence
                        self.assertIs(
                            runtime._autopilot_candidate_fresh("ONGUSDT", dict(SNAPSHOT)),
                            expected)
                self.assertEqual(
                    robot_state_machine.PHASE_EXPIRED_AT_APEX,
                    robot_state_machine.replay_closed_candles(
                        dict(SNAPSHOT),
                        robot_state_machine.initialize_state({
                            "status": "APPROVED", "timeframe": "1",
                            "signal_snapshot": dict(SNAPSHOT)})[0],
                        (_candle(30),))[0]["phase"])
            finally:
                runtime.close()

    def test_prepared_empty_result_is_consumed_as_success_and_failed_load_leaves_none(self):
        calls = []

        def fetch(symbol, _snapshot):
            calls.append(symbol)
            if symbol == "BAD":
                raise RuntimeError("kline request failed")
            return ()

        evidence = PreparedCatchupEvidence(fetch)
        evidence.prepare([("ONGUSDT", SNAPSHOT), ("BAD", SNAPSHOT)])
        self.assertEqual(evidence("ONGUSDT", SNAPSHOT), ())
        with self.assertRaises(RuntimeError):
            evidence("BAD", SNAPSHOT)

    def test_evidence_target_exists_only_for_paper_auto(self):
        with tempfile.TemporaryDirectory() as temp:
            db = _Db(Path(temp), autopilot="OFF")
            try:
                _wedge(db.candidates, "w")

                def switch(mode, at_ms):
                    state = db.store.get_robot_autopilot_state(ACCOUNT)
                    db.store.update_robot_autopilot_state(
                        ACCOUNT, mode=mode, expected_version=state.version,
                        updated_at_ms=at_ms)

                def target():
                    return resolve_autopilot_evidence_target(
                        db.store, ACCOUNT, source=SOURCE_SCANNER, candidate_ref="w",
                        candidate_store_dir=db.candidates)

                self.assertIsNone(target())  # OFF
                switch("SHADOW", 2000)
                self.assertIsNone(target())
                switch(PAPER_AUTO_MODE, 3000)
                symbol, snapshot = target()
                self.assertEqual(symbol, "ONGUSDT")
                self.assertEqual(snapshot["pattern"], "Falling Wedge")
            finally:
                db.store.close()


class PreAdmissionPreparationTests(unittest.TestCase):
    def _runtime(self, temp):
        from tests.test_continuity_recovery_candidate_snapshot import _runtime

        runtime = _runtime(temp)
        self.in_owner = False

        def dispatch(operation):
            self.in_owner = True
            try:
                return operation(runtime)
            finally:
                self.in_owner = False

        runtime._robot_command_dispatcher = dispatch
        runtime.bind_autopilot_protection_health(lambda: True)
        return runtime

    def _box(self, runtime):
        from tests.test_terminal_paper_runtime import _CONFIRMED_BOX_FORMATION

        return runtime._dispatch_ikigai_box_plan_preparation(
            "BTCUSDT", "5", _CONFIRMED_BOX_FORMATION)

    def test_evidence_is_prepared_off_the_owner_before_admission_in_paper_auto(self):
        with tempfile.TemporaryDirectory() as temp:
            runtime = self._runtime(temp)
            try:
                fetched = []

                def fetch(symbol, _snapshot):
                    self.assertFalse(self.in_owner, "REST evidence fetched on the owner")
                    fetched.append(symbol)
                    return ()

                runtime.robot_catchup_evidence = PreparedCatchupEvidence(fetch)
                runtime.set_autopilot_mode("PAPER_AUTO", confirm_paper_auto=True)
                self._box(runtime)
                self.assertEqual(fetched, ["BTCUSDT"])
            finally:
                runtime.close()

    def test_off_and_shadow_never_fetch_evidence(self):
        for mode in ("OFF", "SHADOW"):
            with self.subTest(mode=mode), tempfile.TemporaryDirectory() as temp:
                runtime = self._runtime(temp)
                try:
                    fetched = []
                    runtime.robot_catchup_evidence = PreparedCatchupEvidence(
                        lambda symbol, _snapshot: fetched.append(symbol) or ())
                    runtime.set_autopilot_mode(mode)
                    self._box(runtime)
                    self.assertEqual(fetched, [])
                finally:
                    runtime.close()

    def test_failed_evidence_load_waits_and_admits_nothing(self):
        with tempfile.TemporaryDirectory() as temp:
            runtime = self._runtime(temp)
            try:
                def fetch(_symbol, _snapshot):
                    raise RuntimeError("kline request failed")

                runtime.robot_catchup_evidence = PreparedCatchupEvidence(fetch)
                runtime.set_autopilot_mode("PAPER_AUTO", confirm_paper_auto=True)
                source_id = self._box(runtime)

                decisions = runtime.store.load_robot_auto_decisions(ACCOUNT)
                self.assertEqual([(d.outcome, d.reason_code) for d in decisions],
                                 [(OUTCOME_WAIT, REASON_CANDIDATE_FRESHNESS_UNKNOWN)])
                self.assertEqual(runtime.store.get_robot_candidate(source_id).status,
                                 "BOX_PLAN_ONLY")
            finally:
                runtime.close()

    def test_preparation_failure_never_breaks_the_scanner_pass(self):
        with tempfile.TemporaryDirectory() as temp:
            runtime = self._runtime(temp)
            try:
                class Exploding:
                    def prepare(self, _targets):
                        raise RuntimeError("boom")

                    def __call__(self, *_):
                        raise RuntimeError("never prepared")

                runtime.robot_catchup_evidence = Exploding()
                runtime.set_autopilot_mode("PAPER_AUTO", confirm_paper_auto=True)
                self.assertIsNotNone(self._box(runtime))  # plan still frozen
            finally:
                runtime.close()


if __name__ == "__main__":
    unittest.main()
