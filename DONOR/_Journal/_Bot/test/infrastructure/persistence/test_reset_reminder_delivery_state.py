import asyncio
from datetime import date, time
from types import SimpleNamespace

import pytest

from app.core.accounts.account_id import AccountId
from app.infrastructure.persistence.reset_reminder_delivery_state import (
    inspect_and_reset_reminder_delivery_state,
)


class _Session:
    def __init__(self, row):
        self.row = row
        self.flush_count = 0

    async def scalar(self, statement):
        return self.row

    async def flush(self):
        self.flush_count += 1


def _row(account_id):
    return SimpleNamespace(
        account_id=account_id.value,
        daily_digest_enabled=True,
        daily_digest_time=time(3, 18),
        timezone_name="Europe/Moscow",
        last_reminder_local_date=date(2026, 9, 7),
    )


def test_dry_run_performs_zero_writes():
    account = AccountId.generate()
    row = _row(account)
    session = _Session(row)

    result = asyncio.run(inspect_and_reset_reminder_delivery_state(session, account, apply=False))

    assert result.current_last_reminder_local_date == date(2026, 9, 7)
    assert row.last_reminder_local_date == date(2026, 9, 7)
    assert session.flush_count == 0


def test_apply_resets_only_date_and_preserves_other_account_settings():
    account = AccountId.generate()
    row = _row(account)
    original = (row.daily_digest_enabled, row.daily_digest_time, row.timezone_name)
    session = _Session(row)

    asyncio.run(inspect_and_reset_reminder_delivery_state(session, account, apply=True))

    assert row.last_reminder_local_date is None
    assert (row.daily_digest_enabled, row.daily_digest_time, row.timezone_name) == original
    assert session.flush_count == 1


def test_unrelated_account_row_is_not_touched():
    selected = AccountId.generate()
    unrelated = _row(AccountId.generate())
    session = _Session(_row(selected))

    asyncio.run(inspect_and_reset_reminder_delivery_state(session, selected, apply=True))

    assert unrelated.last_reminder_local_date == date(2026, 9, 7)


def test_missing_account_aborts_without_write():
    account = AccountId.generate()
    session = _Session(None)

    with pytest.raises(LookupError):
        asyncio.run(inspect_and_reset_reminder_delivery_state(session, account, apply=True))

    assert session.flush_count == 0


def test_cli_requires_explicit_mode_and_aborts_without_account(monkeypatch, capsys):
    import app.infrastructure.persistence.reset_reminder_delivery_state as reset_module

    monkeypatch.delenv("JOURNAL_ACCOUNT_ID", raising=False)
    monkeypatch.setattr(reset_module, "load_environment", lambda: None)

    assert reset_module.main(["--dry-run"]) == 2
    assert "JOURNAL_ACCOUNT_ID is required" in capsys.readouterr().err
