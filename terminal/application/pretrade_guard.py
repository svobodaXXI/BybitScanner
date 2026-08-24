"""Pure default-off admission and normalization boundary for future mutations."""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from enum import Enum

from terminal.application.command_identity import (
    CommandIdentityCandidate,
    CommandIdentityFactory,
)
from terminal.application.models import ReconciliationResult, TrustState
from terminal.application.normalization import (
    NormalizationError,
    normalize_limit_price,
    normalize_quantity,
    normalize_working_volume_market_quantity,
    require_positive_decimal,
    WorkingVolumeOvershootError,
)
from terminal.domain.models import (
    Category,
    OrderSide,
    PositionKey,
    PositionSide,
    TradingAccountId,
)
from terminal.domain.policies import TradingAction, permission_for
from terminal.domain.states import ConnectivityState
from terminal.exchange.events import InstrumentSnapshot


class OrderKind(str, Enum):
    MARKET = "market"
    LIMIT = "limit"


class IntentClassification(str, Enum):
    ENTRY = "entry"
    SCALE_IN = "scale_in"
    REDUCE = "reduce"
    CLOSE = "close"
    REDUCE_AND_REVERSE = "reduce_and_reverse"


class SlippageToleranceType(str, Enum):
    TICK_SIZE = "TickSize"
    PERCENT = "Percent"


class RejectionCode(str, Enum):
    TRADING_DISABLED = "trading_disabled"
    ACCOUNT_NOT_SELECTED = "account_not_selected"
    ACCOUNT_UNTRUSTED = "account_untrusted"
    POSITION_UNTRUSTED = "position_untrusted"
    SCOPE_MISMATCH = "scope_mismatch"
    INSTRUMENT_UNAVAILABLE = "instrument_unavailable"
    INVALID_INSTRUMENT = "invalid_instrument"
    INVALID_INTENT = "invalid_intent"
    INVALID_REFERENCE_PRICE = "invalid_reference_price"
    INVALID_LIMIT_PRICE = "invalid_limit_price"
    INSUFFICIENT_VOLUME = "insufficient_volume"
    INSUFFICIENT_SIZING_PRECISION = "insufficient_sizing_precision"
    ABOVE_MAXIMUM_QUANTITY = "above_maximum_quantity"
    INVALID_SLIPPAGE = "invalid_slippage"
    UNTRUSTED_EXECUTION_STATE = "untrusted_execution_state"
    OFFLINE = "offline"
    UNRESOLVED_COMMAND_CONFLICT = "unresolved_command_conflict"


@dataclass(frozen=True, slots=True)
class WorkingVolumeIntent:
    wv_count: Decimal
    configured_one_wv_usdt: Decimal


@dataclass(frozen=True, slots=True)
class NotionalIntent:
    usdt_amount: Decimal


@dataclass(frozen=True, slots=True)
class SlippageMetadata:
    tolerance_type: SlippageToleranceType
    value: Decimal


@dataclass(frozen=True, slots=True)
class MutationGate:
    mutations_enabled: bool = False


@dataclass(frozen=True, slots=True)
class PreTradeIntent:
    symbol: str
    side: OrderSide
    order_kind: OrderKind
    volume: WorkingVolumeIntent | NotionalIntent
    sizing_reference_price: Decimal
    requested_limit_price: Decimal | None = None
    slippage: SlippageMetadata | None = None


@dataclass(frozen=True, slots=True)
class PreTradeContext:
    selected_account_id: TradingAccountId | None
    category: Category
    position_key: PositionKey | None
    reported_position_idx: int
    position_side: PositionSide
    confirmed_position_quantity: Decimal
    account_trusted: bool
    position_trusted: bool
    connectivity: ConnectivityState
    reconciliation: ReconciliationResult
    conflicting_unresolved_command: bool
    instrument: InstrumentSnapshot


@dataclass(frozen=True, slots=True)
class AdmittedPreTradeRequest:
    identity: CommandIdentityCandidate
    trading_account_id: TradingAccountId
    category: Category
    symbol: str
    position_idx: int
    side: OrderSide
    order_kind: OrderKind
    requested_notional: Decimal
    sizing_reference_price: Decimal
    raw_quantity: Decimal
    normalized_quantity: Decimal
    final_quantity: Decimal
    normalized_limit_price: Decimal | None
    classification: IntentClassification
    reduce_only: bool
    capped_at_flat: bool
    slippage: SlippageMetadata | None


@dataclass(frozen=True, slots=True)
class PreTradeDecision:
    admitted: bool
    reason_code: RejectionCode | None
    reason: str
    request: AdmittedPreTradeRequest | None


@dataclass(slots=True)
class PreTradeGuard:
    gate: MutationGate = field(default_factory=MutationGate)
    identity_factory: CommandIdentityFactory = field(default_factory=CommandIdentityFactory)

    def evaluate(self, intent: PreTradeIntent, context: PreTradeContext) -> PreTradeDecision:
        if not self.gate.mutations_enabled:
            return _blocked(RejectionCode.TRADING_DISABLED, "Terminal trading mutations are disabled")
        scope_error = _scope_error(intent, context)
        if scope_error is not None:
            return scope_error
        instrument_error = _instrument_error(context.instrument, intent, context.category)
        if instrument_error is not None:
            return instrument_error
        if not context.account_trusted:
            return _blocked(RejectionCode.ACCOUNT_UNTRUSTED, "selected account state is not trusted")
        if not context.position_trusted:
            return _blocked(RejectionCode.POSITION_UNTRUSTED, "position state is not trusted")
        if context.conflicting_unresolved_command or context.reconciliation.unresolved_command_ids:
            return _blocked(
                RejectionCode.UNRESOLVED_COMMAND_CONFLICT,
                "a conflicting command outcome requires reconciliation",
            )
        if context.connectivity is ConnectivityState.OFFLINE:
            return _blocked(RejectionCode.OFFLINE, "offline state cannot admit exchange mutation")

        try:
            requested_notional = _requested_notional(intent.volume)
        except NormalizationError as exc:
            return _blocked(RejectionCode.INVALID_INTENT, str(exc))
        try:
            reference_price, normalized_limit_price = _prices(intent, context.instrument)
            if (
                isinstance(intent.volume, WorkingVolumeIntent)
                and intent.order_kind is OrderKind.MARKET
            ):
                raw_quantity, normalized_quantity = normalize_working_volume_market_quantity(
                    requested_notional,
                    reference_price,
                    context.instrument.quantity_step,
                )
            else:
                raw_quantity, normalized_quantity = normalize_quantity(
                    requested_notional,
                    reference_price,
                    context.instrument.quantity_step,
                )
        except WorkingVolumeOvershootError as exc:
            return _blocked(RejectionCode.INSUFFICIENT_SIZING_PRECISION, str(exc))
        except NormalizationError as exc:
            code = (
                RejectionCode.INVALID_LIMIT_PRICE
                if intent.order_kind is OrderKind.LIMIT
                else RejectionCode.INVALID_REFERENCE_PRICE
            )
            return _blocked(code, str(exc))

        if normalized_quantity <= 0:
            return _blocked(RejectionCode.INSUFFICIENT_VOLUME, "normalized quantity is zero")
        classification, final_quantity, reduce_only, capped = _classify_and_cap(
            intent,
            context,
            normalized_quantity,
        )
        limit_error = _quantity_limit_error(
            final_quantity,
            reference_price,
            intent.order_kind,
            context.instrument,
        )
        if limit_error is not None:
            return limit_error
        slippage_error = _slippage_error(intent)
        if slippage_error is not None:
            return slippage_error
        trust_error = _trust_error(classification, intent.order_kind, context)
        if trust_error is not None:
            return trust_error

        account_id = context.selected_account_id
        assert account_id is not None
        return PreTradeDecision(
            admitted=True,
            reason_code=None,
            reason="pure pre-trade checks passed; persistence is still required",
            request=AdmittedPreTradeRequest(
                identity=self.identity_factory.create(),
                trading_account_id=account_id,
                category=context.category,
                symbol=intent.symbol,
                position_idx=context.reported_position_idx,
                side=intent.side,
                order_kind=intent.order_kind,
                requested_notional=requested_notional,
                sizing_reference_price=reference_price,
                raw_quantity=raw_quantity,
                normalized_quantity=normalized_quantity,
                final_quantity=final_quantity,
                normalized_limit_price=normalized_limit_price,
                classification=classification,
                reduce_only=reduce_only,
                capped_at_flat=capped,
                slippage=intent.slippage,
            ),
        )


def _requested_notional(volume: WorkingVolumeIntent | NotionalIntent) -> Decimal:
    if isinstance(volume, WorkingVolumeIntent):
        count = require_positive_decimal(volume.wv_count, "WV count")
        one_wv = require_positive_decimal(volume.configured_one_wv_usdt, "configured one WV")
        return count * one_wv
    if isinstance(volume, NotionalIntent):
        return require_positive_decimal(volume.usdt_amount, "notional")
    raise NormalizationError("unsupported volume intent")


def _prices(intent: PreTradeIntent, instrument: InstrumentSnapshot) -> tuple[Decimal, Decimal | None]:
    if intent.order_kind is OrderKind.MARKET:
        return require_positive_decimal(intent.sizing_reference_price, "market sizing reference"), None
    if intent.requested_limit_price is None:
        raise NormalizationError("Limit price is required")
    normalized = normalize_limit_price(intent.requested_limit_price, instrument.tick_size, intent.side)
    if normalized < instrument.min_price or normalized > instrument.max_price:
        raise NormalizationError("normalized Limit price is outside instrument range")
    return normalized, normalized


def _scope_error(intent: PreTradeIntent, context: PreTradeContext) -> PreTradeDecision | None:
    if context.selected_account_id is None:
        return _blocked(RejectionCode.ACCOUNT_NOT_SELECTED, "trading account is not selected")
    if context.category is not Category.LINEAR or context.reported_position_idx != 0:
        return _blocked(RejectionCode.SCOPE_MISMATCH, "Manual v1 requires linear One-Way positionIdx=0")
    key = context.position_key
    if (
        key is None
        or key.trading_account_id != context.selected_account_id
        or key.category is not context.category
        or key.symbol.value != intent.symbol
        or key.position_idx != context.reported_position_idx
        or context.reconciliation.position_key != key
    ):
        return _blocked(RejectionCode.SCOPE_MISMATCH, "account, position or symbol scope does not match")
    quantity = context.confirmed_position_quantity
    if not isinstance(quantity, Decimal) or not quantity.is_finite() or quantity < 0:
        return _blocked(RejectionCode.POSITION_UNTRUSTED, "confirmed position quantity is invalid")
    if (context.position_side is PositionSide.FLAT) != (quantity == 0):
        return _blocked(RejectionCode.POSITION_UNTRUSTED, "position side and quantity are inconsistent")
    return None


def _instrument_error(instrument: InstrumentSnapshot, intent: PreTradeIntent, category: Category):
    if instrument.category is not category or instrument.symbol != intent.symbol:
        return _blocked(RejectionCode.SCOPE_MISMATCH, "instrument category or symbol does not match")
    if instrument.status.lower() != "trading":
        return _blocked(RejectionCode.INSTRUMENT_UNAVAILABLE, "instrument is not actively trading")
    values = (
        instrument.min_price,
        instrument.max_price,
        instrument.tick_size,
        instrument.min_order_quantity,
        instrument.max_order_quantity,
        instrument.max_market_order_quantity,
        instrument.quantity_step,
        instrument.min_notional_value,
    )
    if any(not isinstance(value, Decimal) or not value.is_finite() or value <= 0 for value in values):
        return _blocked(RejectionCode.INVALID_INSTRUMENT, "instrument metadata is invalid")
    if instrument.max_price < instrument.min_price:
        return _blocked(RejectionCode.INVALID_INSTRUMENT, "instrument price bounds are invalid")
    if instrument.max_order_quantity < instrument.min_order_quantity:
        return _blocked(RejectionCode.INVALID_INSTRUMENT, "instrument quantity bounds are invalid")
    return None


def _classify_and_cap(intent, context, normalized_quantity):
    side = context.position_side
    quantity = context.confirmed_position_quantity
    same_direction = (
        side is PositionSide.LONG and intent.side is OrderSide.BUY
    ) or (
        side is PositionSide.SHORT and intent.side is OrderSide.SELL
    )
    if side is PositionSide.FLAT:
        return IntentClassification.ENTRY, normalized_quantity, False, False
    if same_direction:
        return IntentClassification.SCALE_IN, normalized_quantity, False, False
    if intent.order_kind is OrderKind.MARKET:
        final = min(normalized_quantity, quantity)
        classification = IntentClassification.CLOSE if final == quantity else IntentClassification.REDUCE
        return classification, final, True, normalized_quantity > final
    if normalized_quantity < quantity:
        classification = IntentClassification.REDUCE
    elif normalized_quantity == quantity:
        classification = IntentClassification.CLOSE
    else:
        classification = IntentClassification.REDUCE_AND_REVERSE
    return classification, normalized_quantity, False, False


def _quantity_limit_error(quantity, price, order_kind, instrument):
    if quantity <= 0 or quantity < instrument.min_order_quantity:
        return _blocked(RejectionCode.INSUFFICIENT_VOLUME, "quantity is below instrument minimum")
    if quantity * price < instrument.min_notional_value:
        return _blocked(RejectionCode.INSUFFICIENT_VOLUME, "notional is below instrument minimum")
    maximum = (
        instrument.max_market_order_quantity
        if order_kind is OrderKind.MARKET
        else instrument.max_order_quantity
    )
    if quantity > maximum:
        return _blocked(RejectionCode.ABOVE_MAXIMUM_QUANTITY, "quantity exceeds instrument maximum")
    return None


def _slippage_error(intent: PreTradeIntent):
    if intent.order_kind is OrderKind.LIMIT:
        if intent.slippage is not None:
            return _blocked(RejectionCode.INVALID_SLIPPAGE, "slippage metadata is Market-only")
        return None
    slippage = intent.slippage
    if slippage is None or not isinstance(slippage.value, Decimal) or not slippage.value.is_finite():
        return _blocked(RejectionCode.INVALID_SLIPPAGE, "valid Market slippage metadata is required")
    value = slippage.value
    if slippage.tolerance_type is SlippageToleranceType.TICK_SIZE:
        valid = value == value.to_integral_value() and Decimal("1") <= value <= Decimal("10000")
    elif slippage.tolerance_type is SlippageToleranceType.PERCENT:
        valid = Decimal("0.01") <= value <= Decimal("10") and value.normalize().as_tuple().exponent >= -2
    else:
        valid = False
    if not valid:
        return _blocked(RejectionCode.INVALID_SLIPPAGE, "Market slippage tolerance is outside Bybit constraints")
    return None


def _trust_error(classification, order_kind, context):
    exposure_increasing = classification in {
        IntentClassification.ENTRY,
        IntentClassification.SCALE_IN,
        IntentClassification.REDUCE_AND_REVERSE,
    }
    safely_bounded = (
        order_kind is OrderKind.MARKET
        and classification in {IntentClassification.REDUCE, IntentClassification.CLOSE}
    )
    if exposure_increasing or not safely_bounded:
        if (
            context.reconciliation.trust_state is not TrustState.CONVERGED
            or context.connectivity is not ConnectivityState.ONLINE
        ):
            return _blocked(
                RejectionCode.UNTRUSTED_EXECUTION_STATE,
                "new or unbounded exposure requires ONLINE converged state",
            )
        return None
    action = TradingAction.EMERGENCY_CLOSE if classification is IntentClassification.CLOSE else TradingAction.REDUCE
    permission = permission_for(context.connectivity, action, safely_bounded=True)
    if not permission.allowed or context.reconciliation.trust_state in {
        TrustState.UNTRUSTED_STARTUP,
        TrustState.FAILED_INCONSISTENT,
    }:
        return _blocked(RejectionCode.UNTRUSTED_EXECUTION_STATE, permission.reason)
    return None


def _blocked(code: RejectionCode, reason: str) -> PreTradeDecision:
    return PreTradeDecision(False, code, reason, None)
