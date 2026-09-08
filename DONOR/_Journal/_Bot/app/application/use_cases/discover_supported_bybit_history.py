"""Discover the first homogeneous, currently supported Bybit history row."""

from __future__ import annotations

import inspect
import logging
from dataclasses import replace
from datetime import datetime, timezone, timedelta
from decimal import Decimal, InvalidOperation

from app.core.imports import (
    ExchangeImportSettings,
    HistoryIncompatibility,
    SupportedHistoryDiscovery,
    check_bybit_execution,
)

logger = logging.getLogger(__name__)


class DiscoverSupportedBybitHistory:
    """Read-only boundary discovery for current Bybit UTA linear Trade rows."""

    def __init__(self, source, settings_repository=None):
        self._source = source
        self._settings = settings_repository

    async def execute(self, *, lookback_start: datetime, lookback_end: datetime | None = None,
                      persist: bool = True, force_refresh: bool = False, progress_callback=None) -> SupportedHistoryDiscovery:
        start = _utc(lookback_start, "lookback_start")
        end = _utc(lookback_end, "lookback_end") if lookback_end is not None else datetime.now(timezone.utc)
        if start > end:
            raise ValueError("lookback_start must be <= lookback_end")
        kwargs = {"start_at": start, "end_at": end}
        if progress_callback is not None:
            kwargs["progress_callback"] = progress_callback
        try:
            raw_rows = await self._source.fetch_raw_historical_executions(**kwargs)
        except TypeError as error:
            if progress_callback is None or "progress_callback" not in str(error):
                raise
            raw_rows = await self._source.fetch_raw_historical_executions(start_at=start, end_at=end)
        rows = _dedupe_and_sort(tuple(raw_rows))
        if not rows:
            return SupportedHistoryDiscovery("NO_HISTORY", None, None, None, 0, 0, None)

        results = [await _compatibility(self._source, row) for row in rows]
        incompatibilities = []
        incompatible_indexes = []
        for index, (row, compatibility) in enumerate(zip(rows, results)):
            if compatibility.supported:
                continue
            incompatible_indexes.append(index)
            diagnostic = _diagnostic(row, compatibility.reason or "normalization error")
            incompatibilities.append(diagnostic)
            logger.debug(
                "BYBIT incompatible execution execTime=%s symbol=%s side=%s execId=%s reason_incompatible=%s",
                diagnostic.exec_time.isoformat() if diagnostic.exec_time else None,
                diagnostic.symbol, diagnostic.side, diagnostic.exec_id, diagnostic.reason_incompatible,
            )

        last_incompatible = incompatible_indexes[-1] if incompatible_indexes else None
        boundary_index = 0 if last_incompatible is None else last_incompatible + 1
        if boundary_index >= len(rows):
            return SupportedHistoryDiscovery(
                "NO_SUPPORTED_HISTORY", None, _row_time(rows[0]), _row_time(rows[-1]), len(rows),
                len(incompatible_indexes), _row_time(rows[last_incompatible]),
                incompatibilities=tuple(incompatibilities),
            )
        if not all(item.supported for item in results[boundary_index:]):
            raise RuntimeError("Bybit supported-history discovery invariant failed")
        result = SupportedHistoryDiscovery(
            "SUPPORTED", _row_time(rows[boundary_index]), _row_time(rows[0]), _row_time(rows[-1]),
            len(rows), len(incompatible_indexes),
            None if last_incompatible is None else _row_time(rows[last_incompatible]),
            tuple(str(row.get("execId")) for row in rows[boundary_index:]), tuple(incompatibilities),
        )
        if persist and self._settings is not None and result.history_available_from is not None:
            current = await self._settings.get(account_id=self._source.account_id, exchange="BYBIT")
            if current is None:
                current = ExchangeImportSettings(account_id=self._source.account_id, exchange="BYBIT",
                                                 history_available_from=result.history_available_from)
            elif force_refresh or current.history_available_from is None or result.history_available_from < current.history_available_from:
                current = replace(current, history_available_from=result.history_available_from,
                                  updated_at=datetime.now(timezone.utc))
            await self._settings.save(current)
        return result


async def _compatibility(source, row):
    checker = getattr(source, "check_historical_compatibility", None)
    if checker is None:
        return check_bybit_execution(row)
    value = checker(row)
    return await value if inspect.isawaitable(value) else value


def _diagnostic(row: dict, reason: str) -> HistoryIncompatibility:
    return HistoryIncompatibility(
        _safe_row_time(row),
        row.get("symbol") if isinstance(row.get("symbol"), str) else None,
        row.get("side") if isinstance(row.get("side"), str) else None,
        row.get("execId") if isinstance(row.get("execId"), str) else None,
        reason,
    )


def _utc(value: datetime, name: str) -> datetime:
    if not isinstance(value, datetime):
        raise TypeError(f"{name} must be datetime")
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{name} must be timezone-aware")
    return value.astimezone(timezone.utc)


def _row_time(row: dict) -> datetime:
    value = row.get("execTime")
    if isinstance(value, bool):
        raise ValueError("execTime must be a timestamp")
    try:
        milliseconds = Decimal(str(value))
        if not milliseconds.is_finite() or milliseconds != milliseconds.to_integral_value():
            raise ValueError
        return datetime(1970, 1, 1, tzinfo=timezone.utc) + timedelta(milliseconds=int(milliseconds))
    except (InvalidOperation, TypeError, ValueError, OverflowError) as error:
        raise ValueError("execTime must be a valid millisecond timestamp") from error


def _safe_row_time(row: dict) -> datetime | None:
    try:
        return _row_time(row)
    except ValueError:
        return None


def _dedupe_and_sort(rows: tuple[dict, ...]) -> tuple[dict, ...]:
    by_key: dict[tuple[datetime, str], dict] = {}
    for row in rows:
        try:
            key = (_row_time(row), str(row.get("execId", "")))
        except ValueError:
            key = (datetime.min.replace(tzinfo=timezone.utc), str(row.get("execId", "")))
        previous = by_key.get(key)
        if previous is not None and previous != row:
            raise ValueError(f"conflicting duplicate Bybit execution: {key[1]}")
        by_key[key] = row
    return tuple(item for _, item in sorted(by_key.items(), key=lambda pair: pair[0]))
