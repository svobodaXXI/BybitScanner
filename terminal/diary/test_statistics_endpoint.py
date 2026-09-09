from pathlib import Path

import pytest

from terminal.diary.statistics_endpoint import project_active_account_statistics
from terminal.persistence.sqlite_store import SQLiteStore


def _catalog(*, account_id: str = "paper", environment: str = "PAPER") -> dict[str, object]:
    return {
        "active_account_id": account_id,
        "session_generation": 3,
        "accounts": [
            {
                "id": account_id,
                "display_name": "Test",
                "provider": "PAPER" if environment == "PAPER" else "BYBIT",
                "environment": environment,
                "status": "READY",
            }
        ],
    }


def test_empty_active_paper_account_projects_empty_statistics_without_factor_store(tmp_path: Path):
    store = SQLiteStore.open(tmp_path / "runtime.sqlite3")
    factor_store_path = tmp_path / "missing-factors.sqlite3"
    try:
        result = project_active_account_statistics(
            store,
            account_catalog=_catalog(),
            factor_store_path=factor_store_path,
        )
    finally:
        store.close()

    assert result["active_account_id"] == "paper"
    assert result["session_generation"] == 3
    assert result["environment"] == "PAPER"
    assert result["statistics"]["sample"] == {
        "total": 0,
        "eligible_closed_ready": 0,
        "excluded_open": 0,
        "excluded_incomplete": 0,
    }
    assert result["statistics"]["pnl"]["net_pnl"] is None
    assert result["statistics"]["pnl"]["profit_factor"] is None
    assert factor_store_path.exists() is False


def test_mainnet_catalog_maps_to_live_diary_environment(tmp_path: Path):
    store = SQLiteStore.open(tmp_path / "runtime.sqlite3")
    try:
        result = project_active_account_statistics(
            store,
            account_catalog=_catalog(
                account_id="bybit-test-account",
                environment="MAINNET",
            ),
            factor_store_path=tmp_path / "missing-factors.sqlite3",
        )
    finally:
        store.close()

    assert result["active_account_id"] == "bybit-test-account"
    assert result["environment"] == "LIVE"
    assert result["statistics"]["sample"]["total"] == 0


def test_rejects_catalog_without_authoritative_active_account(tmp_path: Path):
    store = SQLiteStore.open(tmp_path / "runtime.sqlite3")
    catalog = _catalog()
    catalog["active_account_id"] = "missing"
    try:
        with pytest.raises(ValueError, match="active account is absent"):
            project_active_account_statistics(
                store,
                account_catalog=catalog,
                factor_store_path=tmp_path / "missing-factors.sqlite3",
            )
    finally:
        store.close()
