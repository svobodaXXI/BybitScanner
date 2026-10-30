"""Offline unit tests: no Telegram network, VPS runtime, or PAPER DB."""
import hashlib
import hmac
import json
import unittest
from urllib.parse import urlencode
from deploy.terminal_ingress.auth_server import (
    INITDATA_MAX_AGE, SESSION_TTL, sign_session, verify_init_data, verify_session
)

TOKEN = "123456:TEST_TOKEN"
OWNER = 123456789

def telegram_data(user=OWNER, timestamp=1700000000, token=TOKEN):
    fields = {"user": json.dumps({"id": user}, separators=(",", ":")),
              "auth_date": str(timestamp), "query_id": "AA123"}
    data = "\n".join(f"{k}={v}" for k, v in sorted(fields.items()))
    key = hmac.new(b"WebAppData", token.encode(), hashlib.sha256).digest()
    fields["hash"] = hmac.new(key, data.encode(), hashlib.sha256).hexdigest()
    return urlencode(fields)

class TelegramIngressAuthTests(unittest.TestCase):
    def test_valid_signed_owner(self):
        self.assertTrue(verify_init_data(telegram_data(), TOKEN, OWNER, now=1700000100))

    def test_wrong_owner(self):
        self.assertFalse(verify_init_data(telegram_data(user=42), TOKEN, OWNER, now=1700000100))

    def test_wrong_bot_token(self):
        self.assertFalse(verify_init_data(telegram_data(), "different", OWNER, now=1700000100))

    def test_replay_expiry_and_future(self):
        self.assertFalse(verify_init_data(telegram_data(), TOKEN, OWNER,
                                          now=1700000000 + INITDATA_MAX_AGE + 1))
        self.assertFalse(verify_init_data(telegram_data(timestamp=1700000100),
                                          TOKEN, OWNER, now=1700000000))

    def test_duplicate_fields_rejected(self):
        self.assertFalse(verify_init_data(telegram_data() + "&user=override",
                                          TOKEN, OWNER, now=1700000100))

    def test_tampering_rejected(self):
        self.assertFalse(verify_init_data(telegram_data().replace("AA123", "EVIL"),
                                          TOKEN, OWNER, now=1700000100))

    def test_session_signature_owner_and_expiry(self):
        secret = b"x" * 32
        session = sign_session(OWNER, secret, now=1700000000)
        self.assertTrue(verify_session(session, OWNER, secret, now=1700000010))
        self.assertFalse(verify_session(session, OWNER + 1, secret, now=1700000010))
        self.assertFalse(verify_session(session, OWNER, b"y" * 32, now=1700000010))
        self.assertFalse(verify_session(session, OWNER, secret,
                                        now=1700000000 + SESSION_TTL + 1))

    def test_session_tampering(self):
        secret = b"x" * 32
        session = sign_session(OWNER, secret, now=1700000000)
        self.assertFalse(verify_session(session + "a", OWNER, secret, now=1700000010))

if __name__ == "__main__":
    unittest.main()
