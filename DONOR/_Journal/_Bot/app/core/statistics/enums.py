"""Enums used by the dynamic statistics domain."""

from enum import StrEnum


class CustomFieldSource(StrEnum):
    MANUAL = "MANUAL"
    EXCHANGE = "EXCHANGE"
    SYSTEM = "SYSTEM"
    MARKET_DATA = "MARKET_DATA"
    DERIVED = "DERIVED"


class CustomFieldStatus(StrEnum):
    ACTIVE = "ACTIVE"
    INACTIVE = "INACTIVE"


class CustomFieldValueType(StrEnum):
    CHOICE = "CHOICE"
    NUMBER = "NUMBER"
    YES_NO = "YES_NO"
    TEXT = "TEXT"


class CustomFieldPhase(StrEnum):
    OPEN = "OPEN"
    POST_TRADE = "POST_TRADE"
    ANY = "ANY"
