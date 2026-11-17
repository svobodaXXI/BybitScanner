"""Offline exact-ID PAPER handoff: no raw DB, arbitrary URLs, or forged fills."""
from __future__ import annotations

import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from research.local_replay_viewer import launch_bridge_agent as agent
from research.local_replay_viewer.paper_episode_local_store import load_episode


EPISODE = "te_" + "a" * 24
REQUEST = "b" * 32
CONFIG = {"origin": "https://example.test", "device_id": "owner-laptop", "token": "A" * 64}


class ReplyOpener:
    def __init__(self, replies):
        self.replies = list(replies)
        self.requests = []

    def open(self, request, timeout):
        self.requests.append((request, timeout))
        reply = self.replies.pop(0)
        raw = reply if isinstance(reply, bytes) else json.dumps(reply).encode()
        data = io.BytesIO(raw)
        data.status = 200
        return data


class ExactDeliveryTests(unittest.TestCase):
    def setUp(self):
        self.facts = {
            "ok": True, "schema": "BYBITSCANNER_CLOSED_EPISODE_FACTS_V1",
            "namespace": "PAPER_READ_ONLY", "source": "PAPER_EXECUTIONS_ATTRIBUTED",
            "account_id": "paper", "owner": "ROBOT", "source_revision": 9,
            "trade_episode_id": EPISODE,
            "replay_evidence": "EXECUTION_FACTS_ONLY_NO_DECISIONS_OR_CANDLES",
            "execution_allocations": [{"execution_id": "real-execution", "occurred_at_ms": 1700000000123}],
        }

    def test_scoped_owner_request_stores_exact_bytes_before_browser_launch(self):
        poll = {"ok": True, "state": "OPEN_EPISODE",
                "request_id": REQUEST, "episode_id": EPISODE,
                "owner": "ROBOT", "source_revision": 9}
        opener = ReplyOpener([poll, {"ok": True, "state": "LAUNCHED"}])
        exact = json.dumps(self.facts, separators=(",", ":")).encode()
        events = []
        with tempfile.TemporaryDirectory() as root, \
             patch.object(agent, "HERE", Path(root)), \
             patch.object(agent, "viewer_is_running", return_value=False), \
             patch.object(agent, "_verified_facts", return_value=exact) as reader:
            def launch(episode):
                self.assertEqual(load_episode(Path(root) / "paper-episode-facts", episode), exact)
                events.append(episode)
            outcome = agent.poll_once(CONFIG, opener=opener, launch=launch)
            self.assertEqual(outcome, "OPEN_REQUESTED")
            reader.assert_called_once_with(
                CONFIG, request_id=REQUEST, episode_id=EPISODE,
                owner="ROBOT", revision=9, opener=opener)
            self.assertEqual(events, [EPISODE])
            self.assertEqual(json.loads(opener.requests[-1][0].data)["launched"], True)

    def test_rejects_mismatched_facts_without_local_writes(self):
        for field, forged in (("owner", "MANUAL"), ("source_revision", 10),
                              ("trade_episode_id", "te_" + "c" * 24)):
            facts = {**self.facts, field: forged}
            opener = ReplyOpener([json.dumps(facts).encode()])
            with self.subTest(field=field), self.assertRaises(agent.AgentConfigError):
                agent._verified_facts(CONFIG, request_id=REQUEST, episode_id=EPISODE,
                                      owner="ROBOT", revision=9, opener=opener)
            self.assertEqual(opener.requests[0][1], 10)
            self.assertEqual(opener.requests[0][0].full_url,
                "https://example.test/api/diary/simulator-bridge/facts?"
                "device_id=owner-laptop&request_id=" + REQUEST)

    def test_failure_to_fetch_never_launches_or_claims_success(self):
        poll = {"ok": True, "state": "OPEN_EPISODE",
                "request_id": REQUEST, "episode_id": EPISODE,
                "owner": "ROBOT", "source_revision": 9}
        opener = ReplyOpener([poll, {"ok": True, "state": "FAILED"}])
        with tempfile.TemporaryDirectory() as root, \
             patch.object(agent, "HERE", Path(root)), \
             patch.object(agent, "viewer_is_running", return_value=False), \
             patch.object(agent, "_verified_facts", side_effect=agent.AgentConfigError("revision_changed")):
            result = agent.poll_once(CONFIG, opener=opener,
                                     launch=lambda _: self.fail("must not launch"))
            self.assertEqual(result, "OPEN_FAILED")
            self.assertEqual(json.loads(opener.requests[-1][0].data)["launched"], False)
            self.assertFalse((Path(root) / "paper-episode-facts").exists())


if __name__ == "__main__":
    unittest.main()
