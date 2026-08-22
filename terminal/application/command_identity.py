"""Pure pre-persistence command correlation identity generation."""

from __future__ import annotations

import re
import uuid
from dataclasses import dataclass
from typing import Callable

from terminal.domain.models import CommandId


_ORDER_LINK_PATTERN = re.compile(r"^[A-Za-z0-9_-]{1,36}$")


@dataclass(frozen=True, slots=True)
class CommandIdentityCandidate:
    command_id: CommandId
    order_link_id: str


class CommandIdentityFactory:
    def __init__(self, uuid_source: Callable[[], uuid.UUID] = uuid.uuid4):
        self._uuid_source = uuid_source

    def create(self) -> CommandIdentityCandidate:
        value = self._uuid_source()
        if not isinstance(value, uuid.UUID):
            raise TypeError("uuid source must return UUID")
        hexadecimal = value.hex
        checksum = format(sum(value.bytes) & 0xF, "x")
        order_link_id = f"tw_{hexadecimal}{checksum}"
        if len(order_link_id) != 36 or not _ORDER_LINK_PATTERN.fullmatch(order_link_id):
            raise ValueError("generated orderLinkId is not Bybit compatible")
        return CommandIdentityCandidate(
            command_id=CommandId(f"cmd_{hexadecimal}"),
            order_link_id=order_link_id,
        )
