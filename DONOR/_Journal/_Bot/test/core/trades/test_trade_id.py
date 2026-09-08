from dataclasses import FrozenInstanceError
from uuid import UUID

import pytest

from app.core.trades.trade_id import TradeId


def test_trade_id_generate_parse_and_string_round_trip() -> None:
    trade_id = TradeId.generate()

    assert isinstance(trade_id.value, UUID)
    assert TradeId.parse(str(trade_id)) == trade_id
    assert str(trade_id) == str(trade_id.value)


def test_trade_id_is_immutable_and_hashable() -> None:
    trade_id = TradeId.generate()

    assert hash(trade_id) == hash(TradeId.parse(str(trade_id)))
    with pytest.raises(FrozenInstanceError):
        trade_id.value = UUID(int=0)


def test_trade_id_rejects_invalid_value() -> None:
    with pytest.raises(ValueError):
        TradeId.parse("not-a-uuid")

