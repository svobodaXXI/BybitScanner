"""Minimal signed async Bybit V5 REST client using only Python stdlib."""

from __future__ import annotations

import asyncio
import hashlib
import hmac
import json
from time import time
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from .config import BybitSettings
from .errors import BybitAuthenticationError, BybitPayloadError, BybitRateLimitError, BybitRequestError


class BybitRestClient:
    def __init__(self, settings: BybitSettings) -> None:
        self._settings = settings

    async def get(self, path: str, params: dict[str, str]) -> dict:
        return await asyncio.to_thread(self._get_sync, path, params)

    async def get_public(self, path: str, params: dict[str, str]) -> dict:
        """Call a public Bybit endpoint without sending authentication headers."""
        return await asyncio.to_thread(self._get_public_sync, path, params)

    def _get_sync(self, path: str, params: dict[str, str]) -> dict:
        timestamp = str(int(time() * 1000))
        query = urlencode(sorted(params.items()))
        sign_payload = f"{timestamp}{self._settings.api_key}{self._settings.recv_window_ms}{query}"
        signature = hmac.new(
            self._settings.api_secret.encode("utf-8"),
            sign_payload.encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()
        request = Request(
            f"{self._settings.base_url}{path}?{query}",
            headers={
                "X-BAPI-API-KEY": self._settings.api_key,
                "X-BAPI-SIGN": signature,
                "X-BAPI-SIGN-TYPE": "2",
                "X-BAPI-TIMESTAMP": timestamp,
                "X-BAPI-RECV-WINDOW": str(self._settings.recv_window_ms),
            },
            method="GET",
        )
        try:
            with urlopen(request, timeout=self._settings.request_timeout_seconds) as response:
                return json.loads(response.read().decode("utf-8"))
        except HTTPError as error:
            if error.code == 429:
                raise BybitRateLimitError("Bybit request was rate-limited") from error
            if error.code in {401, 403}:
                raise BybitAuthenticationError("Bybit authentication was rejected") from error
            raise BybitRequestError(f"Bybit HTTP request failed with status {error.code}") from error
        except (URLError, TimeoutError, OSError) as error:
            raise BybitRequestError("Bybit network request failed") from error
        except (json.JSONDecodeError, UnicodeDecodeError) as error:
            raise BybitPayloadError("Bybit response was not valid JSON") from error

    def _get_public_sync(self, path: str, params: dict[str, str]) -> dict:
        query = urlencode(sorted(params.items()))
        request = Request(
            f"{self._settings.base_url}{path}?{query}",
            method="GET",
        )
        try:
            with urlopen(request, timeout=self._settings.request_timeout_seconds) as response:
                return json.loads(response.read().decode("utf-8"))
        except HTTPError as error:
            if error.code == 429:
                raise BybitRateLimitError("Bybit request was rate-limited") from error
            raise BybitRequestError(f"Bybit HTTP request failed with status {error.code}") from error
        except (URLError, TimeoutError, OSError) as error:
            raise BybitRequestError("Bybit network request failed") from error
        except (json.JSONDecodeError, UnicodeDecodeError) as error:
            raise BybitPayloadError("Bybit response was not valid JSON") from error
