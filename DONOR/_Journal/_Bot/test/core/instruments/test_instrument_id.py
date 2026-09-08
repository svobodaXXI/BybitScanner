from dataclasses import FrozenInstanceError
from uuid import UUID

import pytest

from app.core.instruments.instrument_id import InstrumentId


def test_instrument_id_generate_parse_and_string_round_trip() -> None:
    instrument_id = InstrumentId.generate()

    assert isinstance(instrument_id.value, UUID)
    assert InstrumentId.parse(str(instrument_id)) == instrument_id
    assert str(instrument_id) == str(instrument_id.value)


def test_instrument_id_is_immutable_and_hashable() -> None:
    instrument_id = InstrumentId.generate()

    assert hash(instrument_id) == hash(InstrumentId.parse(str(instrument_id)))
    with pytest.raises(FrozenInstanceError):
        instrument_id.value = UUID(int=0)


def test_instrument_id_rejects_invalid_value() -> None:
    with pytest.raises(ValueError):
        InstrumentId.parse("not-a-uuid")

