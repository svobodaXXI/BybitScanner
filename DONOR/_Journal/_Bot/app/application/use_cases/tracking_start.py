"""Validated tracking-start edits, separate from system history discovery."""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime, timezone
from hashlib import sha256

from app.core.imports import ExchangeImportSettings


@dataclass(frozen=True, slots=True)
class TrackingStartChangePreview:
    current_start: datetime | None
    requested_start: datetime
    affects_older_history: bool
    token: str


class PreviewTrackingStartChange:
    def execute(self, settings: ExchangeImportSettings, requested_start: datetime) -> TrackingStartChangePreview:
        if not isinstance(settings, ExchangeImportSettings):
            raise TypeError("settings must be ExchangeImportSettings")
        requested_start = _utc(requested_start)
        if settings.history_available_from is None:
            raise ValueError("supported history has not been discovered")
        if requested_start < settings.history_available_from:
            raise ValueError("tracking start cannot precede supported history")
        material = f"{settings.account_id}|{settings.exchange}|{requested_start.isoformat()}"
        return TrackingStartChangePreview(
            settings.tracking_start_at,
            requested_start,
            settings.tracking_start_at is not None and requested_start > settings.tracking_start_at,
            sha256(material.encode()).hexdigest()[:24],
        )


class ApplyTrackingStartChange:
    def __init__(self, repository):
        self._repository = repository

    async def execute(self, settings: ExchangeImportSettings, preview: TrackingStartChangePreview, *, confirm_token: str | None = None):
        if confirm_token != preview.token:
            raise PermissionError("tracking start change requires explicit confirmation")
        updated = replace(settings, tracking_start_at=preview.requested_start, updated_at=datetime.now(timezone.utc))
        await self._repository.save(updated)
        return updated


def _utc(value):
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("tracking start must be timezone-aware datetime")
    return value.astimezone(timezone.utc)
