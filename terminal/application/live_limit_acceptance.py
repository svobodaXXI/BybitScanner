"""Durable admission boundary for bounded LIVE Limit acceptance.

This module deliberately owns no exchange adapter. Dispatch wiring is a later delta.
"""

from __future__ import annotations

import os
import socket
import time
from dataclasses import dataclass
from decimal import Decimal
from typing import Callable, Mapping
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
    LiveLimitActionRecord,
    LiveLimitAcceptanceSessionRecord,
    LiveLimitAcceptanceState,
    LiveLimitOperationAdmissionResult,
    LiveLimitRuntimeAttribution,
    PersistenceError,
    SQLiteStore,
)
from terminal import APPLICATION_VERSION


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

    def admit_operation(
        self, *, parent: LiveLimitActionRecord, record: CommandRecord,
        operation: str, client_action_id: str, request_fingerprint: str,
        requested_price: Decimal | None, requested_quantity: Decimal | None,
        conservative_notional: Decimal | None, occurred_at_ms: int,
    ) -> LiveLimitOperationAdmissionResult:
        token = self._manager.session_token
        if token.active_account_id != parent.trading_account_id:
            raise PersistenceError("LIVE Limit operation account is not active")
        if token.generation != parent.session_generation:
            raise PersistenceError("LIVE Limit operation account session is stale")
        account = self._manager.require_active(parent.trading_account_id)
        if not (
            account.provider is TradingAccountProvider.BYBIT
            and account.environment is TradingAccountEnvironment.MAINNET
            and account.status is TradingAccountStatus.READY
            and self._writable_account_provider(account.id)
        ):
            raise PersistenceError("LIVE Limit operation account is not writable MAINNET READY")
        return self._store.admit_live_limit_operation(
            parent=parent, record=record, operation=operation,
            client_action_id=client_action_id,
            request_fingerprint=request_fingerprint,
            requested_price=requested_price, requested_quantity=requested_quantity,
            conservative_notional=conservative_notional,
            runtime=self.runtime_attribution, occurred_at_ms=occurred_at_ms,
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


class LiveLimitAcceptanceAdmin:
    """Credential-free operator administration over current backend authority."""

    def __init__(
        self, manager: TradingAccountManager, store: SQLiteStore, *, build_sha: str,
        process_identity: RuntimeProcessIdentity,
        writable_account_provider: Callable[[object], bool],
        gates_provider: Callable[[], Mapping[str, object]],
        clock_ms: Callable[[], int] = lambda: int(time.time() * 1000),
    ) -> None:
        self._manager = manager
        self._store = store
        self._build_sha = build_sha.strip()
        self._process_identity = process_identity
        self._writable_account_provider = writable_account_provider
        self._gates_provider = gates_provider
        self._clock_ms = clock_ms

    @property
    def runtime_attribution(self) -> LiveLimitRuntimeAttribution:
        process = self._process_identity
        return LiveLimitRuntimeAttribution(
            self._build_sha, process.instance_id, process.started_at_ms,
            process.process_id, self._store.normalized_path,
            self._store.database_identity, SCHEMA_VERSION, process.host_identity,
        )

    def diagnostics(self) -> dict[str, object]:
        now = self._clock_ms()
        token = self._manager.session_token
        account = self._manager.active_account
        sessions = self._store.list_live_limit_acceptance_sessions()
        unresolved_actions = tuple(
            item for item in self._store.load_unresolved_live_limit_actions(account.id)
        )
        unresolved_operations = tuple(
            item for item in self._store.load_unresolved_live_limit_operations(account.id)
        )
        session_payloads = tuple(
            self._session_diagnostics(item, token.generation, now) for item in sessions
        )
        current_session = next(
            (item for item in session_payloads
             if item["state"] == LiveLimitAcceptanceState.ARMED.value),
            session_payloads[0] if session_payloads else None,
        )
        runtime = self.runtime_attribution
        gates = dict(self._gates_provider())
        writable = self._is_current_writable(account.id)
        return {
            "application_version": APPLICATION_VERSION,
            "build_sha": runtime.build_sha,
            "process_instance_id": runtime.process_instance_id,
            "process_started_at_ms": runtime.process_started_at_ms,
            "process_id": runtime.process_id,
            "database_path": runtime.database_path,
            "database_identity": runtime.database_identity,
            "schema_version": runtime.schema_version,
            "host_identity": runtime.host_identity,
            "active_account_id": token.active_account_id.value,
            "account_session_generation": token.generation,
            "active_account_environment": account.environment.value,
            "active_account_status": account.status.value,
            "active_account_writable": writable,
            "live_gates": gates,
            "live_capabilities": {
                "market": bool(writable and gates.get("live_mainnet_authorized")
                               and gates.get("live_market_mutations_enabled")),
                "limit": bool(writable and gates.get("live_mainnet_authorized")
                              and gates.get("live_limit_mutations_enabled")
                              and gates.get("live_limit_acceptance_service_available", True)),
                "parity": bool(writable and gates.get("live_mainnet_authorized")
                               and gates.get("live_parity_mutations_enabled")),
            },
            "acceptance_sessions": session_payloads,
            "current_acceptance_session": current_session,
            "unresolved_action_count": len(unresolved_actions),
            "unresolved_operation_count": len(unresolved_operations),
        }

    def arm(
        self, *, acceptance_session_id: str, account_id: str, environment: str,
        symbol: str, capability: str, max_create_count: int,
        aggregate_notional_ceiling: Decimal, per_order_ceiling: Decimal,
        expires_at_ms: int, operator_authorization_reference: str,
        authorized_build_sha: str, authorized_database_identity: str,
        authorized_session_generation: int,
    ) -> LiveLimitAcceptanceSessionRecord:
        now = self._clock_ms()
        normalized_account = TradingAccountId(account_id)
        normalized_symbol = Symbol(symbol.strip().upper())
        if environment != TradingAccountEnvironment.MAINNET.value:
            raise PersistenceError("operator acceptance environment must be MAINNET")
        if capability != LIVE_LIMIT_ACCEPTANCE_CAPABILITY:
            raise PersistenceError("operator acceptance capability must be LIVE_LIMIT_CREATE")
        if normalized_symbol.value != LIVE_LIMIT_ACCEPTANCE_SYMBOL:
            raise PersistenceError("operator acceptance symbol is not authorized")
        if not all((acceptance_session_id.strip(), symbol.strip(),
                    operator_authorization_reference.strip(), authorized_build_sha.strip(),
                    authorized_database_identity.strip())):
            raise PersistenceError("all operator acceptance authority values are required")
        token = self._manager.session_token
        if token.active_account_id != normalized_account:
            raise PersistenceError("operator acceptance account is not active")
        if token.generation != authorized_session_generation:
            raise PersistenceError("operator acceptance account session mismatch")
        if authorized_build_sha != self._build_sha or not self._build_sha:
            raise PersistenceError("operator acceptance build mismatch")
        if authorized_database_identity != self._store.database_identity:
            raise PersistenceError("operator acceptance database mismatch")
        if not self._is_current_writable(normalized_account):
            raise PersistenceError("operator acceptance account is not writable MAINNET READY")
        return self._store.create_live_limit_acceptance_session(
            LiveLimitAcceptanceSessionRecord(
                acceptance_session_id, normalized_account, environment, normalized_symbol,
                capability, LiveLimitAcceptanceState.ARMED, max_create_count,
                aggregate_notional_ceiling, per_order_ceiling, 0, Decimal("0"),
                now, expires_at_ms, authorized_build_sha, authorized_database_identity,
                operator_authorization_reference, authorized_session_generation, now,
            )
        )

    def revoke(
        self, *, acceptance_session_id: str, account_id: str,
        environment: str, symbol: str, capability: str,
    ) -> LiveLimitAcceptanceSessionRecord:
        token = self._manager.session_token
        normalized_account = TradingAccountId(account_id)
        if token.active_account_id != normalized_account:
            raise PersistenceError("operator revocation account is not active")
        return self._store.revoke_live_limit_acceptance_session(
            acceptance_session_id=acceptance_session_id,
            account_id=normalized_account, environment=environment,
            symbol=Symbol(symbol.strip().upper()), capability=capability,
            occurred_at_ms=self._clock_ms(),
        )

    def _is_current_writable(self, account_id: TradingAccountId) -> bool:
        try:
            account = self._manager.require_active(account_id)
            return bool(
                account.provider is TradingAccountProvider.BYBIT
                and account.environment is TradingAccountEnvironment.MAINNET
                and account.status is TradingAccountStatus.READY
                and self._writable_account_provider(account.id)
            )
        except Exception:
            return False

    def _session_diagnostics(
        self, session: LiveLimitAcceptanceSessionRecord, generation: int, now: int,
    ) -> dict[str, object]:
        unresolved_actions = sum(
            1 for item in self._store.load_unresolved_live_limit_actions(session.trading_account_id)
            if item.acceptance_session_id == session.acceptance_session_id
        )
        unresolved_operations = sum(
            1 for item in self._store.load_unresolved_live_limit_operations(session.trading_account_id)
            if item.acceptance_session_id == session.acceptance_session_id
        )
        return {
            "acceptance_session_id": session.acceptance_session_id,
            "state": (
                LiveLimitAcceptanceState.EXPIRED.value
                if session.state is LiveLimitAcceptanceState.ARMED
                and session.expires_at_ms <= now
                else session.state.value
            ),
            "account_id": session.trading_account_id.value,
            "symbol": session.symbol.value,
            "environment": session.environment,
            "capability": session.capability,
            "reserved_count": session.reserved_count,
            "reserved_notional": str(session.reserved_notional),
            "max_create_count": session.max_create_count,
            "aggregate_notional_ceiling": str(session.aggregate_notional_ceiling),
            "per_order_ceiling": str(session.per_order_ceiling),
            "expires_at_ms": session.expires_at_ms,
            "authorized_build_sha": session.authorized_build_sha,
            "authorized_database_identity": session.database_identity,
            "authorized_session_generation": session.authorized_session_generation,
            "operator_authorization_reference": session.operator_authorization_reference,
            "unresolved_action_count": unresolved_actions,
            "unresolved_operation_count": unresolved_operations,
            "authority_matches_runtime": bool(
                session.authorized_build_sha == self._build_sha
                and session.database_identity == self._store.database_identity
                and session.authorized_session_generation == generation
                and session.trading_account_id == self._manager.active_account_id
                and self._is_current_writable(session.trading_account_id)
            ),
        }
