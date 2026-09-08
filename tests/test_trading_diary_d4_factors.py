from pathlib import Path

import pytest

from scanner_diary_factors import record_scanner_p0_factors
from terminal.diary import DecisionEventId, SetupInstanceId
from terminal.diary.factors import (
    P0_FACTOR_DEFINITIONS_V1,
    DiaryFactorStore,
    FactorDefinition,
    FactorImmutableConflict,
    FactorObservation,
    FactorProvenance,
    FactorSubjectKind,
    FactorTiming,
    FactorValueKind,
)


def test_factor_definitions_are_versioned_immutable_and_reopen_safe(tmp_path: Path):
    path = tmp_path / "factors.sqlite3"
    with DiaryFactorStore.open(path) as store:
        store.register_definitions(P0_FACTOR_DEFINITIONS_V1)
        definition = P0_FACTOR_DEFINITIONS_V1[0]
        assert store.register_definition(definition) == definition
        with pytest.raises(FactorImmutableConflict):
            store.register_definition(
                FactorDefinition(
                    factor_key=definition.factor_key,
                    version=definition.version,
                    value_kind=definition.value_kind,
                    subject_kind=definition.subject_kind,
                    timing=definition.timing,
                    unit=definition.unit,
                    description="different semantics",
                )
            )

    with DiaryFactorStore.open(path) as store:
        assert store.get_definition("scanner.final_score", 1) == P0_FACTOR_DEFINITIONS_V1[0]


def test_factor_observation_replay_is_idempotent_but_conflict_fails(tmp_path: Path):
    with DiaryFactorStore.open(tmp_path / "factors.sqlite3") as store:
        store.register_definitions(P0_FACTOR_DEFINITIONS_V1)
        observation = FactorObservation(
            observation_id="fo-1",
            factor_key="scanner.final_score",
            factor_version=1,
            subject_kind=FactorSubjectKind.SETUP_INSTANCE,
            subject_id="si-1",
            observed_at_ms=100,
            provenance=FactorProvenance.SCANNER_DERIVED,
            source_version="source-v1",
            value=80,
        )
        assert store.append_observation(observation) == observation
        assert store.append_observation(observation) == observation
        conflict = FactorObservation(
            observation_id="fo-1",
            factor_key="scanner.final_score",
            factor_version=1,
            subject_kind=FactorSubjectKind.SETUP_INSTANCE,
            subject_id="si-1",
            observed_at_ms=100,
            provenance=FactorProvenance.SCANNER_DERIVED,
            source_version="source-v1",
            value=81,
        )
        with pytest.raises(FactorImmutableConflict):
            store.append_observation(conflict)


def test_scanner_p0_producer_records_only_available_decision_time_factors(tmp_path: Path):
    path = tmp_path / "factors.sqlite3"
    result = record_scanner_p0_factors(
        setup_instance_id=SetupInstanceId("si-1"),
        decision_event_id=DecisionEventId("de-1"),
        analysis={
            "final_score": 82,
            "confirmation": {
                "confirmation_score": 21,
                "breakout": True,
                "volume": False,
                # volatility deliberately missing: absence must not become False.
            },
        },
        observed_at_ms=123,
        database_path=path,
    )
    assert result.status == "RECORDED"
    assert result.recorded == 4

    with DiaryFactorStore.open(path) as store:
        observations = store.load_observations(
            subject_kind=FactorSubjectKind.SETUP_INSTANCE,
            subject_id="si-1",
        )
        values = {item.factor_key: item.value for item in observations}
        assert values == {
            "scanner.breakout": True,
            "scanner.confirmation_score": 21,
            "scanner.final_score": 82,
            "scanner.volume_confirmation": False,
        }
        assert "scanner.volatility_confirmation" not in values
        assert all(item.provenance is FactorProvenance.SCANNER_DERIVED for item in observations)


def test_same_scanner_decision_replay_does_not_duplicate_factors(tmp_path: Path):
    path = tmp_path / "factors.sqlite3"
    kwargs = dict(
        setup_instance_id=SetupInstanceId("si-1"),
        decision_event_id=DecisionEventId("de-1"),
        analysis={"final_score": 80, "confirmation": {"breakout": False}},
        observed_at_ms=100,
        database_path=path,
    )
    first = record_scanner_p0_factors(**kwargs)
    second = record_scanner_p0_factors(**kwargs)
    assert first.status == "RECORDED"
    assert second.status == "UNCHANGED"
    assert second.recorded == 0

    with DiaryFactorStore.open(path) as store:
        observations = store.load_observations(
            subject_kind=FactorSubjectKind.SETUP_INSTANCE,
            subject_id="si-1",
        )
        assert len(observations) == 2


def test_factor_contract_keeps_decision_time_separate_from_post_trade():
    assert all(
        definition.timing is FactorTiming.DECISION_TIME
        and definition.subject_kind is FactorSubjectKind.SETUP_INSTANCE
        for definition in P0_FACTOR_DEFINITIONS_V1
    )
    assert {definition.value_kind for definition in P0_FACTOR_DEFINITIONS_V1} == {
        FactorValueKind.DECIMAL,
        FactorValueKind.BOOLEAN,
    }
