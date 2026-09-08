"""Minimal authorization roles shared by Telegram and WebApp boundaries."""

from enum import StrEnum


class AccessRole(StrEnum):
    OWNER = "OWNER"
    VIEWER = "VIEWER"

    @property
    def can_write(self) -> bool:
        return self is AccessRole.OWNER
