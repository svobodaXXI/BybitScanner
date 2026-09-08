"""Explicit maintenance command for resetting one account's reminder state."""

from __future__ import annotations

import argparse
import asyncio
import os
import sys
from dataclasses import dataclass

from sqlalchemy import select

from app.config import load_environment
from app.core.accounts.account_id import AccountId
from app.infrastructure.persistence.database import create_async_engine, create_session_factory, get_database_url
from app.infrastructure.persistence.models.reminder_settings import ReminderSettingsORM


@dataclass(frozen=True, slots=True)
class ResetReminderDeliveryResult:
    account_id: AccountId
    enabled: bool
    daily_digest_time: object
    timezone_name: str
    current_last_reminder_local_date: object


async def inspect_and_reset_reminder_delivery_state(
    session,
    account_id: AccountId,
    *,
    apply: bool,
) -> ResetReminderDeliveryResult:
    """Inspect exactly one account and optionally clear only its delivery date."""
    row = await session.scalar(
        select(ReminderSettingsORM).where(ReminderSettingsORM.account_id == account_id.value)
    )
    if row is None:
        raise LookupError(f"reminder settings not found for account {account_id}")
    result = ResetReminderDeliveryResult(
        account_id=account_id,
        enabled=row.daily_digest_enabled,
        daily_digest_time=row.daily_digest_time,
        timezone_name=row.timezone_name,
        current_last_reminder_local_date=row.last_reminder_local_date,
    )
    if apply:
        row.last_reminder_local_date = None
        await session.flush()
    return result


def _configured_account() -> AccountId:
    raw = os.getenv("JOURNAL_ACCOUNT_ID", "").strip()
    if not raw:
        raise ValueError("JOURNAL_ACCOUNT_ID is required")
    return AccountId(raw)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Reset reminder delivery state for the configured Journal account only."
    )
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--dry-run", action="store_true", help="inspect without writing")
    mode.add_argument("--apply", action="store_true", help="clear last_reminder_local_date")
    return parser


async def _run(*, apply: bool) -> int:
    load_environment()
    account_id = _configured_account()
    database_url = get_database_url()
    engine = create_async_engine(database_url)
    try:
        session_factory = create_session_factory(engine)
        async with session_factory() as session:
            # The context is transactional in both modes. Dry-run performs a
            # read only transaction; apply commits only the single date column.
            async with session.begin():
                result = await inspect_and_reset_reminder_delivery_state(
                    session, account_id, apply=apply
                )
                print(f"account_id = {result.account_id}")
                print(f"enabled = {result.enabled}")
                print(f"daily_digest_time = {result.daily_digest_time}")
                print(f"timezone_name = {result.timezone_name}")
                print(
                    "current last_reminder_local_date = "
                    f"{result.current_last_reminder_local_date}"
                )
                print("would reset to NULL")
                if apply:
                    print("RESET APPLIED: last_reminder_local_date = NULL")
        return 0
    finally:
        await engine.dispose()


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        return asyncio.run(_run(apply=args.apply))
    except (LookupError, TypeError, ValueError) as error:
        print(f"ABORTED SAFELY: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
