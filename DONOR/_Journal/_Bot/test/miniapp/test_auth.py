import hashlib
import hmac
import json
from datetime import datetime, timezone
from urllib.parse import urlencode

import pytest

from app.miniapp.auth import (
    MiniAppAuthError,
    MiniAppOwnerError,
    MiniAppStaleAuthError,
    TelegramWebAppAuthenticator,
)


TOKEN = "123456:TEST_TOKEN"
AUTH_TIMESTAMP = 1_725_000_000


def init_data(*, user_id=42, auth_date=AUTH_TIMESTAMP, hash_override=None):
    values = {
        "auth_date": str(auth_date),
        "query_id": "AAH-test-query",
        "user": json.dumps({"id": user_id, "username": "owner", "first_name": "Owner"}, separators=(",", ":")),
    }
    check = "\n".join(f"{key}={values[key]}" for key in sorted(values))
    secret = hmac.new(b"WebAppData", TOKEN.encode(), hashlib.sha256).digest()
    signature = hmac.new(secret, check.encode(), hashlib.sha256).hexdigest()
    values["hash"] = hash_override or signature
    return urlencode(values)


def authenticator(now=AUTH_TIMESTAMP):
    return TelegramWebAppAuthenticator(TOKEN, 42, max_age_seconds=3600, now=lambda: now)


def test_valid_init_data_is_accepted_and_normalized_to_utc():
    user = authenticator().authenticate(init_data())
    assert user.user_id == 42
    assert user.username == "owner"
    assert user.auth_date.tzinfo is timezone.utc


def test_invalid_hash_is_rejected():
    with pytest.raises(MiniAppAuthError):
        authenticator().authenticate(init_data(hash_override="0" * 64))


def test_stale_and_future_auth_are_rejected():
    with pytest.raises(MiniAppStaleAuthError):
        authenticator().authenticate(init_data(auth_date=AUTH_TIMESTAMP - 3601))
    with pytest.raises(MiniAppStaleAuthError):
        authenticator().authenticate(init_data(auth_date=AUTH_TIMESTAMP + 61))


def test_wrong_owner_is_rejected_after_signature_validation():
    with pytest.raises(MiniAppOwnerError):
        authenticator().authenticate(init_data(user_id=99))


def test_missing_init_data_is_rejected():
    with pytest.raises(MiniAppAuthError):
        authenticator().authenticate("")
