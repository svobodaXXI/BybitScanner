from dataclasses import FrozenInstanceError
from uuid import UUID

import pytest

from app.core.accounts.account_id import AccountId


def test_account_id_generate_parse_and_string_round_trip() -> None:
    account_id = AccountId.generate()

    assert isinstance(account_id.value, UUID)
    assert AccountId.parse(str(account_id)) == account_id
    assert str(account_id) == str(account_id.value)


def test_account_id_is_immutable_and_hashable() -> None:
    account_id = AccountId.generate()

    assert hash(account_id) == hash(AccountId.parse(str(account_id)))
    with pytest.raises(FrozenInstanceError):
        account_id.value = UUID(int=0)


def test_account_id_rejects_invalid_value() -> None:
    with pytest.raises(ValueError):
        AccountId.parse("not-a-uuid")

