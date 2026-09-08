from uuid import UUID

import pytest

from app.core.owners import LEGACY_SINGLE_OWNER_ID, OwnerId


def test_owner_id_is_uuid_based_and_round_trips():
    owner_id = OwnerId.generate()

    assert isinstance(owner_id.value, UUID)
    assert OwnerId.parse(str(owner_id)) == owner_id


def test_owner_id_rejects_invalid_inputs():
    with pytest.raises(ValueError, match="invalid OwnerId UUID"):
        OwnerId("not-a-uuid")
    with pytest.raises(TypeError, match="UUID or str"):
        OwnerId(123)


def test_legacy_owner_is_internal_deterministic_uuid():
    assert str(LEGACY_SINGLE_OWNER_ID) == "00000000-0000-0000-0000-000000000001"
