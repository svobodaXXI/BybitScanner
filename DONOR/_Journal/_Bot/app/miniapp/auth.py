"""Server-side Telegram WebApp initData validation."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import hmac
import json
from time import time
from urllib.parse import parse_qsl


class MiniAppAuthError(ValueError):
    """Expected authentication failure safe to expose as 401/403."""


class MiniAppStaleAuthError(MiniAppAuthError):
    """Telegram auth_date is outside the configured freshness window."""


class MiniAppOwnerError(MiniAppAuthError):
    """Authenticated Telegram user is not the configured owner."""


@dataclass(frozen=True, slots=True)
class TelegramWebAppUser:
    user_id: int
    username: str | None
    first_name: str | None
    last_name: str | None
    auth_date: datetime


class TelegramWebAppAuthenticator:
    """Validate initData according to Telegram's WebApp authentication rule.

    ``allowed_user_id`` remains supported for the legacy owner-only boundary.
    Passing ``None`` performs authentication only; a separate server-side
    authorization layer must then decide whether the authenticated user may
    access the journal.
    """

    def __init__(
        self,
        bot_token: str,
        allowed_user_id: int | None,
        *,
        max_age_seconds: int = 86400,
        now=None,
        future_skew_seconds: int = 60,
    ) -> None:
        if not isinstance(bot_token, str) or not bot_token:
            raise ValueError("bot_token must be non-empty")
        if allowed_user_id is not None and type(allowed_user_id) is not int:
            raise TypeError("allowed_user_id must be int or None")
        if type(max_age_seconds) is not int or max_age_seconds <= 0:
            raise ValueError("max_age_seconds must be greater than zero")
        self._bot_token = bot_token
        self._allowed_user_id = allowed_user_id
        self._max_age_seconds = max_age_seconds
        self._now = now or time
        self._future_skew_seconds = future_skew_seconds

    def authenticate(self, init_data: str) -> TelegramWebAppUser:
        if not isinstance(init_data, str) or not init_data.strip():
            raise MiniAppAuthError("Mini App authentication is required")
        try:
            pairs = parse_qsl(init_data, keep_blank_values=True, strict_parsing=True)
        except ValueError as error:
            raise MiniAppAuthError("invalid Mini App authentication payload") from error
        values: dict[str, str] = {}
        for key, value in pairs:
            if key in values:
                raise MiniAppAuthError("invalid Mini App authentication payload")
            values[key] = value
        supplied_hash = values.pop("hash", None)
        if supplied_hash is None or len(supplied_hash) != 64:
            raise MiniAppAuthError("invalid Mini App authentication signature")
        data_check_string = "\n".join(f"{key}={values[key]}" for key in sorted(values))
        secret_key = hmac.new(b"WebAppData", self._bot_token.encode(), hashlib.sha256).digest()
        expected_hash = hmac.new(secret_key, data_check_string.encode(), hashlib.sha256).hexdigest()
        if not hmac.compare_digest(expected_hash, supplied_hash):
            raise MiniAppAuthError("invalid Mini App authentication signature")

        try:
            auth_timestamp = int(values["auth_date"])
            user_payload = json.loads(values["user"])
            user_id = int(user_payload["id"])
        except (KeyError, TypeError, ValueError, json.JSONDecodeError) as error:
            raise MiniAppAuthError("invalid Mini App authentication payload") from error
        if not isinstance(user_payload, dict):
            raise MiniAppAuthError("invalid Mini App user payload")
        now = float(self._now())
        age = now - auth_timestamp
        if age > self._max_age_seconds or age < -self._future_skew_seconds:
            raise MiniAppStaleAuthError("Mini App authentication is stale")
        if self._allowed_user_id is not None and user_id != self._allowed_user_id:
            raise MiniAppOwnerError("Mini App access is restricted to the owner")
        return TelegramWebAppUser(
            user_id=user_id,
            username=_optional_user_text(user_payload.get("username")),
            first_name=_optional_user_text(user_payload.get("first_name")),
            last_name=_optional_user_text(user_payload.get("last_name")),
            auth_date=datetime.fromtimestamp(auth_timestamp, tz=timezone.utc),
        )


def _optional_user_text(value) -> str | None:
    return value if isinstance(value, str) and value else None
