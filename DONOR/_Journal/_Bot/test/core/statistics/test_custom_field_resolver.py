from datetime import datetime, timezone

import pytest

from app.core.statistics import (
    CustomFieldDefinition,
    CustomFieldPhase,
    CustomFieldResolutionContext,
    CustomFieldResolver,
    CustomFieldScope,
    CustomFieldSource,
    CustomFieldValueType,
)


NOW = datetime(2026, 3, 4, 10, 0, tzinfo=timezone.utc)


def field(code, *, phase=CustomFieldPhase.ANY, source=CustomFieldSource.MANUAL):
    return CustomFieldDefinition.create(
        code=code,
        name=code.replace("_", " ").title(),
        value_type=CustomFieldValueType.TEXT,
        source=source,
        phase=phase,
        created_at=NOW,
    )


def context(
    phase=CustomFieldPhase.OPEN,
    *,
    exchange="BYBIT",
    market="CRYPTO",
    strategy_code="LONG_CONTINUATION",
    setup_code="BREAKOUT",
):
    return CustomFieldResolutionContext.create(
        phase=phase,
        exchange=exchange,
        market=market,
        strategy_code=strategy_code,
        setup_code=setup_code,
    )


def test_active_global_field_resolves_and_inactive_field_does_not():
    active = field("active_global")
    inactive = field("inactive_global").deactivate()
    result = CustomFieldResolver().resolve([inactive, active], [], context())

    assert result == (active,)


def test_no_scope_records_mean_global():
    global_field = field("global_field")
    assert CustomFieldResolver().resolve([global_field], [], context()) == (global_field,)


def test_phase_matching_in_open_and_post_trade():
    open_field = field("open_field", phase=CustomFieldPhase.OPEN)
    post_field = field("post_field", phase=CustomFieldPhase.POST_TRADE)
    any_field = field("any_field", phase=CustomFieldPhase.ANY)
    resolver = CustomFieldResolver()

    assert resolver.resolve([post_field, any_field, open_field], [], context(CustomFieldPhase.OPEN)) == (
        any_field,
        open_field,
    )
    assert resolver.resolve([post_field, any_field, open_field], [], context(CustomFieldPhase.POST_TRADE)) == (
        any_field,
        post_field,
    )


def test_any_context_phase_explicitly_accepts_all_field_phases():
    definitions = [
        field("open_field", phase=CustomFieldPhase.OPEN),
        field("post_field", phase=CustomFieldPhase.POST_TRADE),
        field("any_field", phase=CustomFieldPhase.ANY),
    ]
    result = CustomFieldResolver().resolve(definitions, [], context(CustomFieldPhase.ANY))

    assert {item.code.value for item in result} == {"open_field", "post_field", "any_field"}


@pytest.mark.parametrize(
    ("scope", "matching", "mismatching"),
    [
        (lambda field_id: CustomFieldScope.create(field_id, exchange="BYBIT"), context(), context(exchange="MOEX")),
        (lambda field_id: CustomFieldScope.create(field_id, market="CRYPTO"), context(), context(market="EQUITIES")),
        (
            lambda field_id: CustomFieldScope.create(field_id, strategy_code="LONG_CONTINUATION"),
            context(),
            context(strategy_code="CONSOLIDATION_SHORT"),
        ),
        (
            lambda field_id: CustomFieldScope.create(field_id, setup_code="BREAKOUT"),
            context(),
            context(setup_code="REJECTION"),
        ),
    ],
)
def test_each_scope_dimension_matches_only_exact_normalized_context(scope, matching, mismatching):
    definition = field("scoped_field")
    resolver = CustomFieldResolver()
    assert resolver.resolve([definition], [scope(definition.id)], matching) == (definition,)
    assert resolver.resolve([definition], [scope(definition.id)], mismatching) == ()


def test_missing_required_scope_dimension_does_not_guess():
    definition = field("strategy_field")
    scope = CustomFieldScope.create(definition.id, strategy_code="LONG_CONTINUATION")
    missing_strategy = context(strategy_code=None)

    assert CustomFieldResolver().resolve([definition], [scope], missing_strategy) == ()


def test_combined_scope_is_and_within_row():
    definition = field("combined_field")
    scope = CustomFieldScope.create(
        definition.id,
        exchange="BYBIT",
        market="CRYPTO",
        strategy_code="LONG_CONTINUATION",
        setup_code="BREAKOUT",
    )
    resolver = CustomFieldResolver()
    assert resolver.resolve([definition], [scope], context()) == (definition,)
    assert resolver.resolve([definition], [scope], context(setup_code="REJECTION")) == ()
    assert resolver.resolve([definition], [scope], context(strategy_code=None)) == ()


def test_multiple_scopes_are_or_between_rows_and_duplicates_do_not_duplicate_field():
    definition = field("multi_scope_field")
    scopes = [
        CustomFieldScope.create(definition.id, strategy_code="LONG_CONTINUATION"),
        CustomFieldScope.create(definition.id, strategy_code="CONSOLIDATION_SHORT"),
        CustomFieldScope.create(definition.id, strategy_code="LONG_CONTINUATION"),
    ]
    resolver = CustomFieldResolver()
    assert resolver.resolve([definition], scopes, context()) == (definition,)
    assert resolver.resolve([definition], scopes, context(strategy_code="CONSOLIDATION_SHORT")) == (definition,)
    assert resolver.resolve([definition], scopes, context(strategy_code="OTHER")) == ()


def test_setup_scope_can_match_without_strategy_and_does_not_guess_strategy():
    definition = field("setup_only")
    scope = CustomFieldScope.create(definition.id, setup_code="BREAKOUT")

    assert CustomFieldResolver().resolve(
        [definition], [scope], context(strategy_code=None, setup_code="BREAKOUT")
    ) == (definition,)


def test_realistic_journal_context_resolves_only_relevant_active_fields():
    market_condition = field("market_condition")
    breakout_quality = field("breakout_quality")
    short_rejection_quality = field("short_rejection_quality")
    trading_session = field("trading_session", source=CustomFieldSource.DERIVED)
    bybit_execution_quality = field("bybit_execution_quality", source=CustomFieldSource.SYSTEM)
    inactive = field("old_field").deactivate()
    scopes = [
        CustomFieldScope.global_scope(market_condition.id),
        CustomFieldScope.create(
            breakout_quality.id,
            strategy_code="LONG_CONTINUATION",
            setup_code="BREAKOUT",
        ),
        CustomFieldScope.create(
            short_rejection_quality.id,
            strategy_code="CONSOLIDATION_SHORT",
            setup_code="REJECTION",
        ),
        CustomFieldScope.global_scope(trading_session.id),
        CustomFieldScope.create(bybit_execution_quality.id, exchange="BYBIT"),
    ]

    result = CustomFieldResolver().resolve(
        [bybit_execution_quality, inactive, breakout_quality, trading_session, short_rejection_quality, market_condition],
        scopes,
        context(),
    )

    assert [item.code.value for item in result] == [
        "breakout_quality",
        "bybit_execution_quality",
        "market_condition",
        "trading_session",
    ]


def test_output_order_is_deterministic_and_sorted_by_code():
    definitions = [field("zeta"), field("alpha"), field("middle")]
    resolver = CustomFieldResolver()
    first = resolver.resolve(definitions, [], context())
    second = resolver.resolve(list(reversed(definitions)), [], context())

    assert first == second
    assert [item.code.value for item in first] == ["alpha", "middle", "zeta"]


def test_unknown_scope_id_is_ignored_and_duplicate_definition_id_is_rejected():
    known = field("known")
    unknown = field("unknown")
    unknown_scope = CustomFieldScope.global_scope(unknown.id)
    assert CustomFieldResolver().resolve([known], [unknown_scope], context()) == (known,)

    duplicate = CustomFieldDefinition(
        id=known.id,
        code="other_code",
        name="Other code",
        value_type=CustomFieldValueType.TEXT,
        source=CustomFieldSource.MANUAL,
        phase=CustomFieldPhase.ANY,
        required=False,
        definition_version=1,
        created_at=NOW,
    )
    with pytest.raises(ValueError):
        CustomFieldResolver().resolve([known, duplicate], [], context())
