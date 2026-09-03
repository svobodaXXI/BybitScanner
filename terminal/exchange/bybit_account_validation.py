"""Read-only Bybit credential validation through the official V5 user endpoint."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Mapping

from terminal.exchange.bybit_v5_adapter import BybitCredentials


class AccountValidationError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class ValidatedBybitAccount:
    environment: str
    read_only: bool


def _http_factory(**kwargs: Any) -> Any:
    from pybit.unified_trading import HTTP
    return HTTP(**kwargs)


class BybitAccountValidator:
    def __init__(self, http_factory: Callable[..., Any] | None = None) -> None:
        self._http_factory = http_factory or _http_factory

    def validate(self, credentials: BybitCredentials) -> ValidatedBybitAccount:
        successes: list[ValidatedBybitAccount] = []
        for testnet, environment in ((False, "MAINNET"), (True, "TESTNET")):
            try:
                session = self._http_factory(
                    testnet=testnet, api_key=credentials.api_key,
                    api_secret=credentials.api_secret, timeout=10,
                    force_retry=False, max_retries=1, log_requests=False,
                )
                response = session.get_api_key_information()
                if not isinstance(response, Mapping) or response.get("retCode") != 0:
                    continue
                result = response.get("result")
                if not isinstance(result, Mapping) or result.get("apiKey") != credentials.api_key:
                    continue
                read_only = result.get("readOnly")
                if read_only not in {0, 1}:
                    continue
                permissions = result.get("permissions")
                if not isinstance(permissions, Mapping):
                    continue
                contract_trade = permissions.get("ContractTrade")
                if not isinstance(contract_trade, list) or any(
                    not isinstance(permission, str) for permission in contract_trade
                ):
                    continue
                can_write_contracts = {"Order", "Position"}.issubset(contract_trade)
                effective_read_only = (
                    read_only == 1
                    or environment == "TESTNET"
                    or not can_write_contracts
                )
                successes.append(ValidatedBybitAccount(environment, effective_read_only))
            except Exception:
                continue
        if len(successes) != 1:
            raise AccountValidationError("bybit_validation_failed")
        return successes[0]
