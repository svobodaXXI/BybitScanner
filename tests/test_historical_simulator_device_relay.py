"""Local paired receiver: strict HTTPS, exact PAPER case, immutable cache."""
from contextlib import contextmanager
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase
import json

from research.local_replay_viewer.device_relay_client import PairedEpisodeReceiver


class DummyResponse:
    status = 200
    headers = {"Content-Type": "application/json; charset=utf-8"}

    def __init__(self, value): self.raw = json.dumps(value).encode()

    def read(self, count):
        assert count >= len(self.raw)
        return self.raw

    def __enter__(self): return self

    def __exit__(self, *_): pass


class DummyTransport:
    def __init__(self, events):
        self.events = events
        self.requests = []

    def open(self, request, timeout):
        self.requests.append((
            request.full_url, request.get_method(), request.headers,
            json.loads(request.data) if request.data is not None else None,
        ))
        return DummyResponse(self.events.pop(0))


class DeviceReceiverTests(TestCase):
    EPISODE = "te_" + "a" * 24
    RID = "b" * 32

    def facts(self):
        return {
            "ok": True, "schema": "BYBITSCANNER_CLOSED_EPISODE_FACTS_V1",
            "namespace": "PAPER_READ_ONLY", "source": "PAPER_EXECUTIONS_ATTRIBUTED",
            "account_id": "paper", "owner": "ROBOT",
            "source_revision": 9, "trade_episode_id": self.EPISODE,
            "symbol": "BTCUSDT", "side": "LONG",
            "replay_evidence": "EXECUTION_FACTS_ONLY_NO_DECISIONS_OR_CANDLES",
            "execution_allocations": [{
                "execution_id": "f1", "execution_price": "1.123456789",
                "occurred_at_ms": 1794000000123, "controller": "ROBOT",
            }],
        }

    def test_exact_paper_delivery_stored_before_viewer_open_and_ack(self):
        with TemporaryDirectory() as temp:
            path = Path(temp)
            facts = self.facts()
            calls = []
            transport = DummyTransport([
                {"ok": True, "state": "OPEN_EPISODE", "request_id": self.RID,
                 "episode_id": self.EPISODE, "episode_facts": facts},
                {"ok": True, "state": "LAUNCHED"},
            ])
            def opened(episode):
                self.assertEqual(episode, self.EPISODE)
                self.assertEqual(json.loads((path / (episode + ".json")).read_text()), facts)
                calls.append(episode)
                return True
            receiver = PairedEpisodeReceiver(
                origin="https://statistics.example.test", device_id="owner-pc",
                token="S" * 64, local_archive=path,
                open_episode=opened, transport=transport,
            )
            self.assertEqual(receiver.poll_once(), "LAUNCHED")
            self.assertEqual(calls, [self.EPISODE])
            self.assertEqual(transport.requests[0][1], "GET")
            self.assertEqual(transport.requests[1][1], "POST")
            self.assertEqual(transport.requests[1][3], {
                "device_id": "owner-pc", "request_id": self.RID,
                "launched": True,
            })
            self.assertTrue(all(
                uri.startswith("https://statistics.example.test/api/diary/simulator-bridge/")
                for uri, *_ in transport.requests
            ))
            self.assertNotIn("Authorization", transport.requests[0][2])

    def test_unproven_cross_account_or_missing_case_never_launches(self):
        for mutation in [{"account_id": "main"}, {"trade_episode_id": "te_" + "c"*24}]:
            with self.subTest(mutation=mutation), TemporaryDirectory() as temp:
                facts = {**self.facts(), **mutation}
                transport = DummyTransport([
                    {"ok": True, "state": "OPEN_EPISODE", "request_id": self.RID,
                     "episode_id": self.EPISODE, "episode_facts": facts},
                    {"ok": True, "state": "FAILED"},
                ])
                receiver = PairedEpisodeReceiver(
                    origin="https://statistics.example.test", device_id="owner-pc",
                    token="S"*64, local_archive=Path(temp),
                    open_episode=lambda _: self.fail("must not open"),
                    transport=transport,
                )
                with self.assertRaises(ValueError):
                    receiver.poll_once()
                self.assertEqual(list(Path(temp).glob("*.json")), [])
                self.assertEqual(transport.requests[-1][3]["launched"], False)

    def test_require_pinned_https_no_url_redirect_or_invalid_device(self):
        for origin in [
            "", "http://statistics.example.test",
            "https://statistics.example.test/redirect",
            "https://user:pass@statistics.example.test",
            "https://statistics.example.test?token=secret",
            "https://statistics.example.test#secret",
        ]:
            with self.subTest(origin=origin), self.assertRaises(ValueError):
                PairedEpisodeReceiver(
                    origin=origin, device_id="owner-pc", token="S"*64,
                    local_archive=Path("."), open_episode=lambda _: True,
                )
        with self.assertRaises(ValueError):
            PairedEpisodeReceiver(origin="https://statistics.example.test",
                device_id="owner-pc;evil", token="S"*64,
                local_archive=Path("."), open_episode=lambda _: True)

    def test_already_imported_episode_must_match_payload_not_overwrite(self):
        with TemporaryDirectory() as temp:
            path = Path(temp)
            first = self.facts()
            (path / (self.EPISODE + ".json")).write_text(json.dumps(first))
            changed = {**first, "source_revision": 10}
            transport = DummyTransport([
                {"ok": True, "state": "OPEN_EPISODE", "request_id": self.RID,
                 "episode_id": self.EPISODE, "episode_facts": changed},
                {"ok": True, "state": "FAILED"},
            ])
            receiver = PairedEpisodeReceiver(
                origin="https://statistics.example.test", device_id="owner-pc",
                token="S"*64, local_archive=path,
                open_episode=lambda _: self.fail("conflicting evidence"),
                transport=transport,
            )
            with self.assertRaises(ValueError):
                receiver.poll_once()
            self.assertEqual(json.loads((path / (self.EPISODE + ".json")).read_text()), first)
            self.assertEqual(transport.requests[-1][3]["launched"], False)
