"""Pure pre-persistence command correlation identity generation."""

from __future__ import annotations

import hashlib
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


def robot_emergency_close_identity(client_action_id: str, symbol: str) -> CommandIdentityCandidate:
    """Stable PAPER Market identity for the candidate's initial-protection close.

    The ClientActionId is only an API response label; it does not deduplicate
    TradingApplication.submit(). The deterministic command/orderLink pair does.
    Use a distinct domain separator from owner Close-All and normal Market
    entry identities; preserve the same pair across restarts and adapters.
    """
    if not isinstance(client_action_id, str) or not client_action_id.strip():
        raise ValueError("emergency close action identity is required")
    if not isinstance(symbol, str) or not symbol.strip() or symbol != symbol.strip().upper():
        raise ValueError("emergency close symbol must be normalized")
    digest = hashlib.sha256(
        f"robot-initial-protection-close\\0{client_action_id}\\0{symbol}".encode("utf-8")
    ).hexdigest()[:32]
    checksum = format(sum(bytes.fromhex(digest)) & 0xF, "x")
    return CommandIdentityCandidate(
        command_id=CommandId(f"cmd_{digest}"),
        order_link_id=f"tw_{digest}{checksum}",
    )
