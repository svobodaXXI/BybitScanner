from dataclasses import FrozenInstanceError
from uuid import UUID

import pytest

from app.core.trades.execution_id import ExecutionId


def test_execution_id_generate_parse_and_string_round_trip() -> None:
    execution_id = ExecutionId.generate()

    assert isinstance(execution_id.value, UUID)
    assert ExecutionId.parse(str(execution_id)) == execution_id
    assert str(execution_id) == str(execution_id.value)


def test_execution_id_is_immutable_and_hashable() -> None:
    execution_id = ExecutionId.generate()

    assert hash(execution_id) == hash(ExecutionId.parse(str(execution_id)))
    with pytest.raises(FrozenInstanceError):
        execution_id.value = UUID(int=0)


def test_execution_id_rejects_invalid_value() -> None:
    with pytest.raises(ValueError):
        ExecutionId.parse("not-a-uuid")
