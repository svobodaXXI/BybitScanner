"""Exact PAPER owner->device relay proof, no database mutation or live trading."""
from http.server import ThreadingHTTPServer
from threading import Thread
from unittest import TestCase
from unittest.mock import patch
from urllib.error import HTTPError
from urllib.request import Request, urlopen
import json

from terminal.diary.simulator_launch_relay import SimulatorLaunchRelay
from terminal.diary.ticker_finrez import EpisodeFactsSourceChanged, EpisodeFactsNotFound
from terminal.runtime import paper_http_server as http


class ExactPaperBridgeTests(TestCase):
    EPISODE = "te_" + "a" * 24
    OWNER_ORIGIN = "https://statistics.example.test"
    SECRET = "S" * 64

    def setUp(self):
        self.source_calls = []
        self.relay = SimulatorLaunchRelay(
            origin=self.OWNER_ORIGIN, devices={"owner-pc": self.SECRET},
        )
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), http.PaperHttpHandler)
        self.server.simulator_launch_relay = self.relay
        self.server.diary_source_db_path = "/unopened-PAPER-source"
        self.server.diary_setup_store_path = "/unopened-D2-source"
        self.worker = Thread(target=self.server.serve_forever, daemon=True)
        self.worker.start()
        self.patches = [
            patch.object(http, "load_paper_source_snapshot", side_effect=self._snapshot),
            patch.object(http, "project_paper_closed_episode_facts", side_effect=self._facts),
            patch.object(http, "project_episode_d2_context_read_only", side_effect=self._d2),
            patch.object(http, "attach_verified_original_geometry",
                         side_effect=lambda d2, **_: d2),
        ]
        for p in self.patches: p.start()

    def tearDown(self):
        for p in reversed(self.patches): p.stop()
        self.server.shutdown()
        self.server.server_close()
        self.worker.join(timeout=3)

    def _snapshot(self, path):
        self.source_calls.append(("load", path))
        return "snapshot"

    def _facts(self, snapshot, *, account_id, owner, trade_episode_id,
               source_revision, now_ms):
        self.source_calls.append(("project", account_id, owner, trade_episode_id, source_revision))
        assert snapshot == "snapshot" and now_ms > 0
        if source_revision == 8:
            raise EpisodeFactsSourceChanged("stale")
        if trade_episode_id != self.EPISODE:
            raise EpisodeFactsNotFound("foreign")
        return {
            "schema": "BYBITSCANNER_CLOSED_EPISODE_FACTS_V1",
            "namespace": "PAPER_READ_ONLY", "source": "PAPER_EXECUTIONS_ATTRIBUTED",
            "account_id": "paper", "owner": "ROBOT", "source_revision": source_revision,
            "trade_episode_id": self.EPISODE, "symbol": "BTCUSDT",
            "side": "LONG", "opened_at_ms": 1793999999000,
            "closed_at_ms": 1794000001000,
            "replay_evidence": "EXECUTION_FACTS_ONLY_NO_DECISIONS_OR_CANDLES",
            "execution_allocations": [{
                "execution_id": "fill-1", "execution_price": "123.456789",
                "controller": "ROBOT", "occurred_at_ms": 1794000000123,
            }],
        }

    def _d2(self, store, *, trade_episode_id, account_id, symbol, side, opening_controller):
        self.source_calls.append(("d2", trade_episode_id))
        assert store == "/unopened-D2-source" and account_id == "paper"
        assert opening_controller == "ROBOT"
        return {"status": "NO_EXACT_EPISODE_LINK", "source": "TRADING_DIARY_D2",
                "geometry_status": "NOT_EXPORTED",
                "decision_scope": "D2_OBSERVATIONS_NOT_ROBOT_RUNTIME_LOG"}

    def call(self, route, *, payload=None, origin="", token=""):
        url = f"http://127.0.0.1:{self.server.server_address[1]}/api/diary/simulator-bridge/{route}"
        headers = {}
        if origin:
            headers.update({"Origin": origin, "Sec-Fetch-Site": "same-origin"})
        if token:
            headers["X-BybitScanner-Simulator-Device-Token"] = token
        if payload is not None:
            headers["Content-Type"] = "application/json"
        req = Request(url, data=json.dumps(payload).encode() if payload is not None else None,
                      headers=headers)
        try:
            with urlopen(req, timeout=2) as response:
                return response.status, json.load(response)
        except HTTPError as error:
            return error.code, json.load(error)

    def test_authorized_one_case_matches_revision_and_device_no_any_episode_lookup(self):
        self.assertEqual(self.call("poll?device_id=owner-pc&viewer_running=1",
                                   token=self.SECRET)[1]["state"], "IDLE")
        payload = {
            "episode_id": self.EPISODE, "account_id": "paper",
            "owner": "ROBOT", "source_revision": 9,
        }
        for change, status in [
            ({"account_id":"main"}, 403),
            ({"source_revision":8}, 409),
            ({"source_revision":0}, 400),
            ({"owner":"UNKNOWN"}, 400),
            ({"episode_id":"te_" + "b"*24}, 404),
            ({"source_revision":"9"}, 400),
        ]:
            code, _ = self.call("request", origin=self.OWNER_ORIGIN,
                                payload={**payload, **change})
            self.assertEqual(code, status)
        count = len(self.source_calls)
        for origin in ("https://attacker.example", ""):
            code, _ = self.call("request", origin=origin, payload=payload)
            self.assertEqual(code, 403)
        self.assertEqual(len(self.source_calls), count)
        code, queued = self.call("request", origin=self.OWNER_ORIGIN, payload=payload)
        self.assertEqual(code, 200)
        self.assertEqual(queued["state"], "QUEUED")
        self.assertNotIn("episode_facts", queued) # Browser never receives device payload.
        code, _ = self.call("poll?device_id=owner-pc&viewer_running=1",
                            token="wrong")
        self.assertEqual(code, 403)
        code, delivery = self.call("poll?device_id=owner-pc&viewer_running=1",
                                   token=self.SECRET)
        self.assertEqual(code, 200)
        self.assertEqual(delivery["request_id"], queued["request_id"])
        facts = delivery["episode_facts"]
        self.assertEqual((facts["account_id"], facts["owner"], facts["source_revision"],
                          facts["trade_episode_id"]),
                         ("paper", "ROBOT", 9, self.EPISODE))
        self.assertEqual(facts["execution_allocations"][0]["execution_price"], "123.456789")
        self.assertEqual(facts["setup_context"]["status"], "NO_EXACT_EPISODE_LINK")
        self.assertEqual(self.call("ack", payload={
            "device_id": "owner-pc", "request_id": queued["request_id"], "launched": True,
        }, token=self.SECRET)[1]["state"], "LAUNCHED")
        self.assertEqual(self.call("poll?device_id=owner-pc&viewer_running=1",
                                   token=self.SECRET)[1]["state"], "IDLE")
        self.assertEqual(self.relay._requests[queued["request_id"]].episode_facts, None)

    def test_legacy_locator_remains_data_free(self):
        self.call("poll?device_id=owner-pc&viewer_running=0", token=self.SECRET)
        code, queued = self.call("request", origin=self.OWNER_ORIGIN,
                                  payload={"episode_id": self.EPISODE})
        self.assertEqual(code, 200)
        delivered = self.call("poll?device_id=owner-pc&viewer_running=0",
                              token=self.SECRET)[1]
        self.assertEqual(delivered["episode_id"], self.EPISODE)
        self.assertNotIn("episode_facts", delivered)
        self.assertEqual(self.source_calls, [])
