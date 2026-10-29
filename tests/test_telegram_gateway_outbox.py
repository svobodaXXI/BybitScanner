"""Atomic outbox behavior; no automatic replay of uncertain sends."""
import os
import tempfile
import unittest
from unittest.mock import patch

import telegram_gateway_outbox as outbox


class OutboxTransitionTests(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.env = patch.dict(os.environ, {
            "BYBITSCANNER_TELEGRAM_OUTBOX_DB": self.dir.name + "/events.db"
        })
        self.env.start()

    def tearDown(self):
        self.env.stop()
        self.dir.cleanup()

    def test_claim_once_then_mark_accepted(self):
        outbox.enqueue("event-1", "123", "message")
        self.assertEqual(len(outbox.pending()), 1)
        self.assertTrue(outbox.claim_pending("event-1"))
        self.assertFalse(outbox.claim_pending("event-1"))
        self.assertEqual(outbox.pending(), [])
        outbox.mark("event-1", "ACCEPTED", 17)
        self.assertEqual(outbox.counts(), {"ACCEPTED": 1})

    def test_unknown_never_automatically_replayed(self):
        outbox.enqueue("event-2", "123", "message", {"inline_keyboard": []})
        self.assertTrue(outbox.claim_pending("event-2"))
        outbox.mark("event-2", "UNKNOWN")
        self.assertEqual(outbox.pending(), [])
        self.assertFalse(outbox.claim_pending("event-2"))
        self.assertEqual(outbox.counts(), {"UNKNOWN": 1})

    def test_claim_and_invalid_transition_fail_closed(self):
        outbox.enqueue("event-3", "123", "message")
        with self.assertRaises(outbox.OutboxError):
            outbox.mark("event-3", "ACCEPTED")
        self.assertEqual(outbox.counts(), {"PENDING": 1})


if __name__ == "__main__":
    unittest.main()
