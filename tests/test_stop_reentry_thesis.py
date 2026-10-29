"""STOP campaign lineage MUST be more than same symbol + direction.

Tests exercise frozen canonical pattern values only. The policy has no
authority to execute positions; actual STOP fill is checked in SQLiteStore.
"""
from terminal.application.robot_reentry_thesis import (
    frozen_corridor, verified_same_thesis,
)
from tests.test_stop_reentry_adapter import lshape, mirror, wedge, box


SHA = "e" * 64


def linked(signal, candidate_id="prior-mirror", sha=SHA):
    signal["reentry_parent"] = {
        "candidate_id": candidate_id, "snapshot_sha256": sha,
    }
    return signal


def compatible(first, second, direction="LONG"):
    return verified_same_thesis(
        previous_candidate_id="prior-mirror",
        previous_snapshot_sha256=SHA, previous_snapshot=first,
        new_snapshot=second, direction=direction,
    )


def test_mirror_stop_then_new_lshape_with_explicit_parent_and_matching_corridor():
    assert compatible(mirror(), linked(lshape(breakout_ms=1_200_000)))


def test_same_symbol_direction_without_immutable_parent_never_suffices():
    assert not compatible(mirror(), lshape(breakout_ms=1_200_000))


def test_wrong_parent_id_or_sha_cannot_steal_another_stop_campaign():
    assert not compatible(mirror(), linked(lshape(), candidate_id="unrelated"))
    assert not compatible(mirror(), linked(lshape(), sha="f" * 64))


def test_unrelated_price_region_denied_even_with_correct_parent_hash():
    new = linked(lshape())
    new["l_shape"]["reference"] = "1000"
    new["l_shape"]["stop"] = "990"
    new["l_shape"]["structural_stop"] = "990"
    new["l_shape"]["target"] = "1100"
    assert not compatible(mirror(), new)


def test_wrong_direction_denied_regardless_of_parent_link():
    assert not compatible(mirror(), linked(lshape()), direction="SHORT")


def test_new_wedge_with_disjoint_geometry_does_not_inherit_mirror_campaign():
    assert not compatible(mirror(), linked(wedge()))


def test_box_corridor_is_from_frozen_stop_take_and_full_grid_average():
    prior = box()
    prior["plan"].update(stop_price="89.6", take_price="99.2")
    p = frozen_corridor(prior)
    assert p is not None
    assert p.low == 89.6
    assert p.high == 99.2
    assert p.reference == 92.8


def test_missing_or_invalid_original_candle_structure_fails_closed():
    assert frozen_corridor({"pattern": "MIRROR"}) is None
    assert not compatible({"pattern": "MIRROR"}, linked(lshape()))


def test_no_mutation_of_canonical_source():
    prior, current = mirror(), linked(lshape())
    old = repr(prior), repr(current)
    assert compatible(prior, current)
    assert (repr(prior), repr(current)) == old
