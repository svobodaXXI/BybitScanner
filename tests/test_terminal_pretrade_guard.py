"""Offline acceptance tests for the Stage 4 pure pre-trade boundary."""

from __future__ import annotations

import ast
import re
import uuid
from dataclasses import replace
from decimal import Decimal
from pathlib import Path

import pytest

from terminal.application.command_identity import CommandIdentityFactory
from terminal.application.models import ReconciliationResult, TrustState
from terminal.application.pretrade_guard import (
    IntentClassification,
    MutationGate,
    NotionalIntent,
    OrderKind,
    PreTradeContext,
    PreTradeGuard,
    PreTradeIntent,
    RejectionCode,
    SlippageMetadata,
    SlippageToleranceType,
    WorkingVolumeIntent,
)
from terminal.domain.models import (
    Category,
    OrderSide,
    PositionKey,
    PositionSide,
    Symbol,
    TradingAccountId,
)
from terminal.domain.states import ConnectivityState
from terminal.exchange.events import InstrumentSnapshot


ACCOUNT = TradingAccountId("manual-account")
KEY = PositionKey(ACCOUNT, Category.LINEAR, Symbol("BTCUSDT"), 0)
SLIPPAGE = SlippageMetadata(SlippageToleranceType.PERCENT, Decimal("0.50"))


def instrument(**changes) -> InstrumentSnapshot:
    base = InstrumentSnapshot(
        category=Category.LINEAR,
        symbol="BTCUSDT",
        contract_type="LinearPerpetual",
        status="Trading",
        base_coin="BTC",
        quote_coin="USDT",
        settle_coin="USDT",
        min_price=Decimal("1"),
        max_price=Decimal("1000000"),
        tick_size=Decimal("0.1"),
        min_order_quantity=Decimal("0.001"),
        max_order_quantity=Decimal("10"),
        max_market_order_quantity=Decimal("5"),
        quantity_step=Decimal("0.001"),
        min_notional_value=Decimal("5"),
    )
    return replace(base, **changes)


def reconciliation(
    trust: TrustState = TrustState.CONVERGED,
    unresolved: tuple[str, ...] = (),
) -> ReconciliationResult:
    return ReconciliationResult(
        trust_state=trust,
        position_key=KEY,
        active_orders=(),
        unresolved_command_ids=unresolved,
        applied_execution_count=0,
        duplicate_execution_count=0,
        checkpoint=None,
        flat_transition=None,
        reasons=(),
    )


def context(**changes) -> PreTradeContext:
    base = PreTradeContext(
        selected_account_id=ACCOUNT,
        category=Category.LINEAR,
        position_key=KEY,
        reported_position_idx=0,
        position_side=PositionSide.FLAT,
        confirmed_position_quantity=Decimal("0"),
        account_trusted=True,
        position_trusted=True,
        connectivity=ConnectivityState.ONLINE,
        reconciliation=reconciliation(),
        conflicting_unresolved_command=False,
        instrument=instrument(),
    )
    return replace(base, **changes)


def market(
    side: OrderSide = OrderSide.BUY,
    volume=None,
    price: Decimal = Decimal("20000"),
    slippage: SlippageMetadata | None = SLIPPAGE,
) -> PreTradeIntent:
    return PreTradeIntent(
        symbol="BTCUSDT",
        side=side,
        order_kind=OrderKind.MARKET,
        volume=volume or NotionalIntent(Decimal("100")),
        sizing_reference_price=price,
        slippage=slippage,
    )


def limit(side: OrderSide, amount: str, price: str) -> PreTradeIntent:
    return PreTradeIntent(
        symbol="BTCUSDT",
        side=side,
        order_kind=OrderKind.LIMIT,
        volume=NotionalIntent(Decimal(amount)),
        sizing_reference_price=Decimal("1"),
        requested_limit_price=Decimal(price),
    )


def enabled_guard(seed: int = 1) -> PreTradeGuard:
    return PreTradeGuard(
        gate=MutationGate(True),
        identity_factory=CommandIdentityFactory(lambda: uuid.UUID(int=seed)),
    )


def admitted(intent: PreTradeIntent, ctx: PreTradeContext | None = None):
    decision = enabled_guard().evaluate(intent, ctx or context())
    assert decision.admitted, decision
    assert decision.request is not None
    return decision.request


def test_working_volume_and_notional_intents_are_decimal_exact() -> None:
    one = admitted(market(volume=WorkingVolumeIntent(Decimal("1"), Decimal("180"))))
    many = admitted(market(volume=WorkingVolumeIntent(Decimal("2.5"), Decimal("180"))))
    direct = admitted(market(volume=NotionalIntent(Decimal("123.45"))))
    assert one.requested_notional == Decimal("180")
    assert many.requested_notional == Decimal("450.0")
    assert direct.requested_notional == Decimal("123.45")
    assert direct.raw_quantity == Decimal("123.45") / Decimal("20000")


def test_working_volume_market_uses_nearest_step_with_bounded_overshoot() -> None:
    request = admitted(
        market(volume=WorkingVolumeIntent(Decimal("1"), Decimal("250")), price=Decimal("64250")),
    )
    assert request.requested_notional == Decimal("250")
    assert request.raw_quantity == Decimal("250") / Decimal("64250")
    assert request.normalized_quantity == Decimal("0.004")
    assert request.final_quantity == Decimal("0.004")


def test_working_volume_market_midpoint_tie_uses_floor() -> None:
    request = admitted(
        market(volume=WorkingVolumeIntent(Decimal("1"), Decimal("70")), price=Decimal("20000")),
    )
    assert request.raw_quantity == Decimal("0.0035")
    assert request.normalized_quantity == Decimal("0.003")


def test_working_volume_market_rejects_nearest_ceil_above_overshoot_limit() -> None:
    decision = enabled_guard().evaluate(
        market(volume=WorkingVolumeIntent(Decimal("1"), Decimal("12")), price=Decimal("20000")),
        context(),
    )
    assert decision.reason_code is RejectionCode.INSUFFICIENT_SIZING_PRECISION
    assert decision.reason == "nearest Working Volume quantity exceeds maximum rounding overshoot"
    assert decision.request is None


def test_notional_market_and_working_volume_limit_keep_floor_semantics() -> None:
    notional_market = admitted(market(volume=NotionalIntent(Decimal("250")), price=Decimal("64250")))
    working_volume_limit = admitted(PreTradeIntent(
        symbol="BTCUSDT",
        side=OrderSide.BUY,
        order_kind=OrderKind.LIMIT,
        volume=WorkingVolumeIntent(Decimal("1"), Decimal("250")),
        sizing_reference_price=Decimal("1"),
        requested_limit_price=Decimal("64250"),
    ))
    assert notional_market.normalized_quantity == Decimal("0.003")
    assert working_volume_limit.normalized_quantity == Decimal("0.003")


def test_opposite_working_volume_market_nearest_step_is_capped_at_flat() -> None:
    ctx = context(position_side=PositionSide.LONG, confirmed_position_quantity=Decimal("0.003"))
    request = admitted(
        market(
            OrderSide.SELL,
            WorkingVolumeIntent(Decimal("1"), Decimal("250")),
            price=Decimal("64250"),
        ),
        ctx,
    )
    assert request.normalized_quantity == Decimal("0.004")
    assert request.final_quantity == Decimal("0.003")
    assert request.classification is IntentClassification.CLOSE
    assert request.capped_at_flat and request.reduce_only


def test_float_volume_is_rejected_instead_of_entering_decimal_pipeline() -> None:
    decision = enabled_guard().evaluate(
        market(volume=NotionalIntent(100.0)),  # type: ignore[arg-type]
        context(),
    )
    assert decision.reason_code is RejectionCode.INVALID_INTENT
    assert decision.request is None


def test_quantity_is_floored_and_never_increases_requested_exposure() -> None:
    request = admitted(market(volume=NotionalIntent(Decimal("100")), price=Decimal("30000")))
    assert request.raw_quantity == Decimal("100") / Decimal("30000")
    assert request.normalized_quantity == Decimal("0.003")
    assert request.final_quantity * request.sizing_reference_price <= request.requested_notional


@pytest.mark.parametrize(
    ("side", "requested", "expected"),
    [(OrderSide.BUY, "100.19", "100.1"), (OrderSide.SELL, "100.11", "100.2")],
)
def test_limit_price_rounding_preserves_side_semantics(side, requested, expected) -> None:
    request = admitted(limit(side, "1000", requested))
    assert request.normalized_limit_price == Decimal(expected)
    assert request.normalized_quantity == (Decimal("1000") / Decimal(expected) // Decimal("0.001")) * Decimal("0.001")
    assert request.final_quantity * Decimal(expected) <= request.requested_notional


@pytest.mark.parametrize(
    ("intent", "ctx", "reason"),
    [
        (market(volume=NotionalIntent(Decimal("5")), price=Decimal("20000")), context(), RejectionCode.INSUFFICIENT_VOLUME),
        (market(volume=NotionalIntent(Decimal("9")), price=Decimal("1000")), context(instrument=instrument(min_notional_value=Decimal("10"))), RejectionCode.INSUFFICIENT_VOLUME),
        (limit(OrderSide.BUY, "11000", "1000"), context(), RejectionCode.ABOVE_MAXIMUM_QUANTITY),
        (market(volume=NotionalIntent(Decimal("6000")), price=Decimal("1000")), context(), RejectionCode.ABOVE_MAXIMUM_QUANTITY),
    ],
)
def test_exchange_quantity_and_notional_limits_reject(intent, ctx, reason) -> None:
    assert enabled_guard().evaluate(intent, ctx).reason_code is reason


@pytest.mark.parametrize(
    ("ctx", "reason"),
    [
        (context(instrument=instrument(status="Settled")), RejectionCode.INSTRUMENT_UNAVAILABLE),
        (context(category="inverse"), RejectionCode.SCOPE_MISMATCH),
        (context(instrument=instrument(symbol="ETHUSDT")), RejectionCode.SCOPE_MISMATCH),
        (context(selected_account_id=TradingAccountId("other")), RejectionCode.SCOPE_MISMATCH),
        (context(reported_position_idx=1), RejectionCode.SCOPE_MISMATCH),
        (context(position_trusted=False), RejectionCode.POSITION_UNTRUSTED),
        (context(account_trusted=False), RejectionCode.ACCOUNT_UNTRUSTED),
    ],
)
def test_scope_instrument_and_trust_validation_fail_closed(ctx, reason) -> None:
    assert enabled_guard().evaluate(market(), ctx).reason_code is reason


def test_default_kill_switch_blocks_and_explicit_gate_admits() -> None:
    assert PreTradeGuard().evaluate(market(), context()).reason_code is RejectionCode.TRADING_DISABLED
    assert enabled_guard().evaluate(market(), context()).admitted


@pytest.mark.parametrize(
    ("connectivity", "trust", "allowed"),
    [
        (ConnectivityState.ONLINE, TrustState.CONVERGED, True),
        (ConnectivityState.DEGRADED, TrustState.DEGRADED, False),
        (ConnectivityState.UNKNOWN_EXECUTION, TrustState.RECONCILING, False),
        (ConnectivityState.RECONCILING, TrustState.RECONCILING, False),
        (ConnectivityState.OFFLINE, TrustState.DEGRADED, False),
    ],
)
def test_exposure_increase_requires_online_converged(connectivity, trust, allowed) -> None:
    ctx = context(connectivity=connectivity, reconciliation=reconciliation(trust))
    assert enabled_guard().evaluate(market(), ctx).admitted is allowed


def test_degraded_bounded_market_reduction_is_admitted() -> None:
    ctx = context(
        position_side=PositionSide.LONG,
        confirmed_position_quantity=Decimal("0.01"),
        connectivity=ConnectivityState.DEGRADED,
        reconciliation=reconciliation(TrustState.DEGRADED),
    )
    request = admitted(market(OrderSide.SELL, NotionalIntent(Decimal("100"))), ctx)
    assert request.classification is IntentClassification.REDUCE
    assert request.reduce_only


@pytest.mark.parametrize(
    ("side", "position_side"),
    [(OrderSide.SELL, PositionSide.LONG), (OrderSide.BUY, PositionSide.SHORT)],
)
def test_oversized_opposite_market_is_capped_at_flat(side, position_side) -> None:
    ctx = context(position_side=position_side, confirmed_position_quantity=Decimal("0.02"))
    request = admitted(market(side, NotionalIntent(Decimal("1000"))), ctx)
    assert request.normalized_quantity == Decimal("0.050")
    assert request.final_quantity == Decimal("0.02")
    assert request.classification is IntentClassification.CLOSE
    assert request.capped_at_flat and request.reduce_only


@pytest.mark.parametrize(
    ("amount", "classification"),
    [("100", IntentClassification.REDUCE), ("200", IntentClassification.CLOSE), ("300", IntentClassification.REDUCE_AND_REVERSE)],
)
def test_opposite_limit_preserves_reversal_semantics(amount, classification) -> None:
    ctx = context(position_side=PositionSide.LONG, confirmed_position_quantity=Decimal("2"))
    request = admitted(limit(OrderSide.SELL, amount, "100"), ctx)
    assert request.classification is classification
    assert not request.reduce_only
    assert not request.capped_at_flat


def test_unresolved_command_is_a_durable_uncertainty_lock() -> None:
    ctx = context(reconciliation=reconciliation(unresolved=("cmd_unknown",)))
    decision = enabled_guard().evaluate(market(), ctx)
    assert decision.reason_code is RejectionCode.UNRESOLVED_COMMAND_CONFLICT
    assert decision.request is None


def test_command_identity_is_unique_compatible_and_contains_no_context_data() -> None:
    values = iter((uuid.UUID(int=1), uuid.UUID(int=2)))
    factory = CommandIdentityFactory(lambda: next(values))
    first, second = factory.create(), factory.create()
    assert first != second
    assert re.fullmatch(r"cmd_[0-9a-f]{32}", first.command_id.value)
    assert len(first.order_link_id) == 36
    assert re.fullmatch(r"[A-Za-z0-9_-]{36}", first.order_link_id)
    assert "manual-account" not in first.order_link_id
    assert "secret" not in first.order_link_id


@pytest.mark.parametrize(
    "slippage",
    [
        SlippageMetadata(SlippageToleranceType.TICK_SIZE, Decimal("1")),
        SlippageMetadata(SlippageToleranceType.TICK_SIZE, Decimal("10000")),
        SlippageMetadata(SlippageToleranceType.PERCENT, Decimal("0.01")),
        SlippageMetadata(SlippageToleranceType.PERCENT, Decimal("10.00")),
    ],
)
def test_valid_market_slippage_metadata(slippage) -> None:
    assert admitted(market(slippage=slippage)).slippage == slippage


@pytest.mark.parametrize(
    "slippage",
    [
        None,
        SlippageMetadata(SlippageToleranceType.TICK_SIZE, Decimal("1.5")),
        SlippageMetadata(SlippageToleranceType.TICK_SIZE, Decimal("10001")),
        SlippageMetadata(SlippageToleranceType.PERCENT, Decimal("0.001")),
        SlippageMetadata(SlippageToleranceType.PERCENT, Decimal("10.01")),
    ],
)
def test_invalid_market_slippage_is_deterministically_rejected(slippage) -> None:
    assert enabled_guard().evaluate(market(slippage=slippage), context()).reason_code is RejectionCode.INVALID_SLIPPAGE


def test_stage4_has_no_network_mutation_persistence_or_scanner_coupling() -> None:
    root = Path(__file__).parents[1]
    files = [
        root / "terminal/application/pretrade_guard.py",
        root / "terminal/application/normalization.py",
        root / "terminal/application/command_identity.py",
    ]
    forbidden_import_roots = {"pybit", "requests", "httpx", "websocket", "sqlite3", "scanner", "bybit_api"}
    forbidden_methods = {"create_order", "amend_order", "cancel_order", "set_trading_stop", "persist_command_before_submit"}
    for file in files:
        tree = ast.parse(file.read_text(encoding="utf-8"))
        imports = {
            node.names[0].name.split(".")[0]
            for node in ast.walk(tree)
            if isinstance(node, ast.Import)
        } | {
            (node.module or "").split(".")[0]
            for node in ast.walk(tree)
            if isinstance(node, ast.ImportFrom)
        }
        calls = {
            node.func.attr
            for node in ast.walk(tree)
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
        }
        assert imports.isdisjoint(forbidden_import_roots)
        assert calls.isdisjoint(forbidden_methods)
