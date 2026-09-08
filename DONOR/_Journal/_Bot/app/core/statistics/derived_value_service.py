"""Pure V1 calculation service for built-in DERIVED custom fields."""

from dataclasses import dataclass
from decimal import Decimal

from .custom_field_definition import CustomFieldDefinition
from .derived_value_context import DerivedValueContext, TradingSessionRule
from .derived_value_result import DerivedValueResult
from .enums import CustomFieldSource, CustomFieldValueType


class DerivedValueConfigurationError(ValueError):
    """The field definition is not configured for the selected derived value."""


def _minutes_between(start, end) -> Decimal:
    delta = end - start
    micros = (delta.days * 86400 + delta.seconds) * 1_000_000 + delta.microseconds
    return Decimal(micros) / Decimal(60 * 1_000_000)


@dataclass(frozen=True, slots=True)
class DerivedValueService:
    """Calculate one field from explicit facts without persistence or orchestration."""

    session_rules: tuple[TradingSessionRule, ...] = ()

    def __post_init__(self) -> None:
        rules = tuple(self.session_rules)
        if any(not isinstance(rule, TradingSessionRule) for rule in rules):
            raise TypeError("session_rules must contain only TradingSessionRule values")
        self._validate_no_overlaps(rules)
        object.__setattr__(self, "session_rules", rules)

    def calculate(
        self,
        field: CustomFieldDefinition,
        context: DerivedValueContext,
    ) -> DerivedValueResult:
        if not isinstance(field, CustomFieldDefinition):
            raise TypeError("field must be CustomFieldDefinition")
        if not isinstance(context, DerivedValueContext):
            raise TypeError("context must be DerivedValueContext")
        if field.source is not CustomFieldSource.DERIVED:
            raise DerivedValueConfigurationError("DerivedValueService requires a DERIVED field")

        code = str(field.code)
        calculator = {
            "day_of_week": self._day_of_week,
            "entry_hour": self._entry_hour,
            "trading_session": self._trading_session,
            "position_value": self._position_value,
            "holding_duration": self._holding_duration,
            "stop_distance": self._stop_distance,
            "result_r": self._result_r,
        }.get(code)
        if calculator is None:
            return DerivedValueResult.unsupported(f"unsupported derived field code: {code}")
        self._ensure_value_type(code, field.value_type)
        return calculator(context)

    @staticmethod
    def _ensure_value_type(code: str, value_type: CustomFieldValueType) -> None:
        expected = CustomFieldValueType.TEXT if code in {"day_of_week", "trading_session"} else CustomFieldValueType.NUMBER
        if value_type is not expected:
            raise DerivedValueConfigurationError(
                f"derived field {code!r} requires value_type {expected.value}, got {value_type.value}"
            )

    @staticmethod
    def _local_opened_at(context: DerivedValueContext):
        return context.opened_at.astimezone(context.timezone or context.opened_at.tzinfo)

    @classmethod
    def _day_of_week(cls, context: DerivedValueContext) -> DerivedValueResult:
        days = ("MONDAY", "TUESDAY", "WEDNESDAY", "THURSDAY", "FRIDAY", "SATURDAY", "SUNDAY")
        return DerivedValueResult.calculated(days[cls._local_opened_at(context).weekday()])

    @classmethod
    def _entry_hour(cls, context: DerivedValueContext) -> DerivedValueResult:
        return DerivedValueResult.calculated(Decimal(cls._local_opened_at(context).hour))

    def _trading_session(self, context: DerivedValueContext) -> DerivedValueResult:
        rules = context.session_rules or self.session_rules
        if not rules:
            return DerivedValueResult.not_available("session rules are not configured")
        self._validate_no_overlaps(rules)
        local_time = self._local_opened_at(context).time().replace(tzinfo=None)
        matches = [rule.code for rule in rules if rule.matches(local_time)]
        if not matches:
            return DerivedValueResult.not_available("opened_at is outside configured sessions")
        return DerivedValueResult.calculated(matches[0])

    @staticmethod
    def _position_value(context: DerivedValueContext) -> DerivedValueResult:
        return DerivedValueResult.calculated(context.entry_price_decimal * context.quantity_decimal)

    @staticmethod
    def _holding_duration(context: DerivedValueContext) -> DerivedValueResult:
        if context.closed_at is None:
            return DerivedValueResult.not_available("closed_at is missing for an open trade")
        return DerivedValueResult.calculated(_minutes_between(context.opened_at, context.closed_at))

    @staticmethod
    def _stop_distance(context: DerivedValueContext) -> DerivedValueResult:
        stop_price = context.decimal("stop_price")
        if stop_price is None:
            return DerivedValueResult.not_available("stop_price is missing")
        return DerivedValueResult.calculated(abs(context.entry_price_decimal - stop_price))

    @staticmethod
    def _result_r(context: DerivedValueContext) -> DerivedValueResult:
        net_pnl = context.decimal("net_pnl")
        risk = context.decimal("risk")
        if net_pnl is None:
            return DerivedValueResult.not_available("net_pnl is missing")
        if risk is None:
            return DerivedValueResult.not_available("risk is missing")
        if risk == 0:
            return DerivedValueResult.not_available("risk is zero")
        return DerivedValueResult.calculated(net_pnl / risk)

    @staticmethod
    def _validate_no_overlaps(rules: tuple[TradingSessionRule, ...]) -> None:
        intervals: list[tuple[int, int, str]] = []
        for rule in rules:
            start = rule.start_time.hour * 60 + rule.start_time.minute
            end = rule.end_time.hour * 60 + rule.end_time.minute
            if rule.start_time < rule.end_time:
                intervals.append((start, end, rule.code))
            else:
                intervals.extend(((start, 1440, rule.code), (0, end, rule.code)))
        for index, (start, end, code) in enumerate(intervals):
            for other_start, other_end, other_code in intervals[index + 1 :]:
                if max(start, other_start) < min(end, other_end):
                    raise ValueError(f"overlapping trading session rules: {code} and {other_code}")
