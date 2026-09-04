"""Durable admission boundary for bounded LIVE Limit acceptance.

This module deliberately owns no exchange adapter. Dispatch wiring is a later delta.
"""

from __future__ import annotations

import os
import socket
import time
from dataclasses import dataclass
from decimal import Decimal
from typing import Callable
from uuid import uuid4

from terminal.application.trading_accounts import (
    TradingAccountEnvironment,
    TradingAccountManager,
    TradingAccountProvider,
    TradingAccountStatus,
)
from terminal.domain.models import Symbol, TradingAccountId
from terminal.persistence.schema import SCHEMA_VERSION
from terminal.persistence.sqlite_store import (
    CommandRecord,
    LiveLimitAdmissionResult,
    LiveLimitAcceptanceSessionRecord,
    LiveLimitRuntimeAttribution,
    PersistenceError,
    SQLiteStore,
)


LIVE_LIMIT_ACCEPTANCE_CAPABILITY = "LIVE_LIMIT_CREATE"
LIVE_LIMIT_ACCEPTANCE_SYMBOL = "ONGUSDT"
LIVE_LIMIT_ACCEPTANCE_MAX_CREATE_COUNT = 1
LIVE_LIMIT_ACCEPTANCE_AGGREGATE_CEILING = Decimal("5.20")
LIVE_LIMIT_ACCEPTANCE_PER_ORDER_CEILING = Decimal("5.20")


@dataclass(frozen=True, slots=True)
class RuntimeProcessIdentity:
    instance_id: str
    started_at_ms: int
    process_id: int
    host_identity: str

    @classmethod
    def capture(cls, *, deployment_identity: str | None = None) -> "RuntimeProcessIdentity":
        host = socket.gethostname().strip()
        deployment = (deployment_identity or "local").strip()
        if not host or not deployment:
            raise PersistenceError("runtime host/deployment identity is unavailable")
        return cls(str(uuid4()), int(time.time() * 1000), os.getpid(), f"{host}/{deployment}")


class LiveLimitAcceptanceService:
    """Account-fenced facade for durable LIVE Limit create ownership only."""

    def __init__(
        self, manager: TradingAccountManager, store: SQLiteStore, *, build_sha: str,
        process_identity: RuntimeProcessIdentity,
        writable_account_provider: Callable[[object], bool],
    ) -> None:
        if not build_sha.strip():
            raise PersistenceError("runtime build SHA is unavailable")
        self._manager = manager
        self._store = store
        self._build_sha = build_sha.strip()
        self._process_identity = process_identity
        self._writable_account_provider = writable_account_provider

    @property
    def runtime_attribution(self) -> LiveLimitRuntimeAttribution:
        process = self._process_identity
        return LiveLimitRuntimeAttribution(
            build_sha=self._build_sha,
            process_instance_id=process.instance_id,
            process_started_at_ms=process.started_at_ms,
            process_id=process.process_id,
            database_path=self._store.normalized_path,
            database_identity=self._store.database_identity,
            schema_version=SCHEMA_VERSION,
            host_identity=process.host_identity,
        )

    def admit_create(
        self, *, acceptance_session_id: str, session_generation: int,
        client_action_id: str, request_fingerprint: str, record: CommandRecord,
        reserved_notional: Decimal, occurred_at_ms: int,
    ) -> LiveLimitAdmissionResult:
        token = self._manager.session_token
        if token.active_account_id != record.trading_account_id:
            raise PersistenceError("LIVE Limit account is not active")
        if token.generation != session_generation:
            raise PersistenceError("LIVE Limit account session is stale")
        account = self._manager.require_active(record.trading_account_id)
        if not (
            account.provider is TradingAccountProvider.BYBIT
            and account.environment is TradingAccountEnvironment.MAINNET
            and account.status is TradingAccountStatus.READY
            and self._writable_account_provider(account.id)
        ):
            raise PersistenceError("LIVE Limit account is not writable MAINNET READY")
        return self._store.admit_live_limit_create(
            acceptance_session_id=acceptance_session_id,
            environment=TradingAccountEnvironment.MAINNET.value,
            capability=LIVE_LIMIT_ACCEPTANCE_CAPABILITY,
            session_generation=session_generation,
            client_action_id=client_action_id,
            request_fingerprint=request_fingerprint,
            record=record,
            reserved_notional=reserved_notional,
            runtime=self.runtime_attribution,
            occurred_at_ms=occurred_at_ms,
        )

    def select_session(
        self, *, account_id: TradingAccountId, session_generation: int, symbol: Symbol,
        client_action_id: str, occurred_at_ms: int,
    ) -> LiveLimitAcceptanceSessionRecord:
        return self._store.select_live_limit_acceptance_session(
            account_id=account_id,
            environment=TradingAccountEnvironment.MAINNET.value,
            symbol=symbol,
            capability=LIVE_LIMIT_ACCEPTANCE_CAPABILITY,
            session_generation=session_generation,
            client_action_id=client_action_id,
            occurred_at_ms=occurred_at_ms,
        )
