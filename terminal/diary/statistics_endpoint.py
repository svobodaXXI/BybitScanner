"""Active-account projection boundary for Trading Diary D6.4 statistics.

This module is transport-neutral and read-only. It selects the already-authoritative
active account from the runtime catalog, reconstructs that account's TradeEpisode
records through the existing D1 read service, and delegates metric semantics to the
D6.4 statistics runtime projection.
"""

from __future__ import annotations

from pathlib import Path

from terminal.domain.models import TradingAccountId
from terminal.persistence.sqlite_store import SQLiteStore

from .models import DiaryEnvironment
from .service import TradeEpisodeReadService
from .statistics_runtime import project_runtime_statistics


def project_active_account_statistics(
    store: SQLiteStore,
    *,
    account_catalog: dict[str, object],
    factor_store_path: str | Path,
) -> dict[str, object]:
    """Project statistics for the catalog's active account without trading mutation."""
    active_account_id = account_catalog.get("active_account_id")
    session_generation = account_catalog.get("session_generation")
    accounts = account_catalog.get("accounts")
    if (
        not isinstance(active_account_id, str)
        or not active_account_id
        or isinstance(session_generation, bool)
        or not isinstance(session_generation, int)
        or session_generation < 1
        or not isinstance(accounts, list)
    ):
        raise ValueError("invalid account catalog")

    active = next(
        (
            account
            for account in accounts
            if isinstance(account, dict) and account.get("id") == active_account_id
        ),
        None,
    )
    if active is None:
        raise ValueError("active account is absent from catalog")

    environment_value = active.get("environment")
    if environment_value == "PAPER":
        environment = DiaryEnvironment.PAPER
    elif environment_value in {"MAINNET", "LIVE"}:
        environment = DiaryEnvironment.LIVE
    else:
        raise ValueError("unsupported active-account environment")

    episodes = TradeEpisodeReadService(
        store,
        trading_account_id=TradingAccountId(active_account_id),
        environment=environment,
    ).list_episodes()
    return {
        "active_account_id": active_account_id,
        "session_generation": session_generation,
        "environment": environment.value,
        "statistics": project_runtime_statistics(
            episodes,
            factor_store_path=factor_store_path,
        ),
    }
