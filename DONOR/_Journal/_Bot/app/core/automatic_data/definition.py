"""Stable metadata and registry for automatic factors.

Definitions are metadata, not trade columns.  A new factor is therefore a
registry entry and does not change the Trade aggregate or the observation
schema.
"""

from dataclasses import dataclass
from enum import StrEnum


class AutomaticFactorCategory(StrEnum):
    PRICE_DYNAMICS_RETURNS = "PRICE_DYNAMICS_RETURNS"
    TRADING_ACTIVITY_LIQUIDITY = "TRADING_ACTIVITY_LIQUIDITY"
    MARKET_MICROSTRUCTURE = "MARKET_MICROSTRUCTURE"
    VOLATILITY_RANGE = "VOLATILITY_RANGE"
    DERIVATIVES_POSITIONING = "DERIVATIVES_POSITIONING"
    CARRY_FUNDING = "CARRY_FUNDING"
    EXECUTION_TRANSACTION_COSTS = "EXECUTION_TRANSACTION_COSTS"
    TEMPORAL_SESSION_CONTEXT = "TEMPORAL_SESSION_CONTEXT"
    INSTRUMENT_CONTRACT_CHARACTERISTICS = "INSTRUMENT_CONTRACT_CHARACTERISTICS"
    OPTIONS_RISK_GREEKS = "OPTIONS_RISK_GREEKS"


class AutomaticFactorSourceKind(StrEnum):
    EXCHANGE = "EXCHANGE"
    MARKET_DATA = "MARKET_DATA"
    DERIVED = "DERIVED"
    SYSTEM = "SYSTEM"


class CaptureSemantics(StrEnum):
    AT_ENTRY = "AT_ENTRY"
    AT_EXIT = "AT_EXIT"
    PREVIOUS_CLOSED_BAR = "PREVIOUS_CLOSED_BAR"
    POST_TRADE = "POST_TRADE"
    SESSION_END = "SESSION_END"


class AutomaticFactorValueType(StrEnum):
    DECIMAL = "DECIMAL"
    INTEGER = "INTEGER"
    BOOLEAN = "BOOLEAN"
    TEXT = "TEXT"


class AutomaticFactorBucketPolicy(StrEnum):
    FIXED_BINS = "FIXED_BINS"
    QUANTILES = "QUANTILES"
    PERCENTILES = "PERCENTILES"
    CUSTOM_BINS = "CUSTOM_BINS"


@dataclass(frozen=True, slots=True)
class AutomaticFactorDefinition:
    factor_id: str
    display_name: str
    description: str
    category_id: AutomaticFactorCategory | str
    value_type: AutomaticFactorValueType | str
    unit: str | None = None
    source_kind: AutomaticFactorSourceKind | str = AutomaticFactorSourceKind.DERIVED
    capture_semantics: CaptureSemantics | str = CaptureSemantics.POST_TRADE
    timeframe_window: str | None = None
    applicability: str = "ALL"
    calculation_version: str = "1"
    definition_version: int = 1
    active: bool = True
    supports_overview: bool = False
    supports_home: bool = False
    supports_filter: bool = False
    supports_group: bool = False
    supports_bucket: bool = False
    timeframe: str | None = None
    window: int | str | None = None

    def __post_init__(self) -> None:
        for name in ("factor_id", "display_name", "description", "applicability", "calculation_version"):
            value = getattr(self, name)
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"{name} must be a non-empty string")
        if self.definition_version < 1:
            raise ValueError("definition_version must be >= 1")
        object.__setattr__(self, "category_id", AutomaticFactorCategory(self.category_id))
        object.__setattr__(self, "value_type", AutomaticFactorValueType(self.value_type))
        object.__setattr__(self, "source_kind", AutomaticFactorSourceKind(self.source_kind))
        object.__setattr__(self, "capture_semantics", CaptureSemantics(self.capture_semantics))
        for name in ("active", "supports_overview", "supports_home", "supports_filter", "supports_group", "supports_bucket"):
            if type(getattr(self, name)) is not bool:
                raise TypeError(f"{name} must be bool")


class AutomaticFactorRegistry:
    """Immutable-by-convention lookup of active and historical definitions."""

    def __init__(self, definitions=()):
        items = tuple(definitions)
        if any(not isinstance(item, AutomaticFactorDefinition) for item in items):
            raise TypeError("definitions must contain AutomaticFactorDefinition values")
        ids = [item.factor_id for item in items]
        if len(ids) != len(set(ids)):
            raise ValueError("factor_id must be unique")
        self._definitions = items
        self._by_id = {item.factor_id: item for item in items}

    def get(self, factor_id: str) -> AutomaticFactorDefinition | None:
        return self._by_id.get(factor_id)

    def require(self, factor_id: str) -> AutomaticFactorDefinition:
        item = self.get(factor_id)
        if item is None:
            raise KeyError(f"unknown automatic factor: {factor_id}")
        return item

    def list(self, *, active_only: bool = False) -> tuple[AutomaticFactorDefinition, ...]:
        return tuple(item for item in self._definitions if not active_only or item.active)

    def __iter__(self):
        return iter(self._definitions)

    def __len__(self):
        return len(self._definitions)


DEFAULT_AUTOMATIC_FACTOR_REGISTRY = AutomaticFactorRegistry((
    AutomaticFactorDefinition(
        "holding_duration_seconds", "Holding duration", "Время удержания сделки",
        AutomaticFactorCategory.TRADING_ACTIVITY_LIQUIDITY, AutomaticFactorValueType.DECIMAL,
        unit="seconds", source_kind=AutomaticFactorSourceKind.DERIVED,
        capture_semantics=CaptureSemantics.POST_TRADE, applicability="CLOSED",
        calculation_version="2", definition_version=2,
        supports_filter=True, supports_group=True,
    ),
    AutomaticFactorDefinition(
        "entry_hour", "Entry hour", "Час открытия сделки по локальному времени пользователя",
        AutomaticFactorCategory.TEMPORAL_SESSION_CONTEXT, AutomaticFactorValueType.INTEGER,
        unit="hour", source_kind=AutomaticFactorSourceKind.SYSTEM,
        capture_semantics=CaptureSemantics.AT_ENTRY, applicability="ALL",
        supports_filter=True, supports_group=True,
    ),
    AutomaticFactorDefinition(
        "entry_day_of_week", "Entry day of week",
        "ISO-день недели открытия сделки по UTC: Monday=1, Sunday=7",
        AutomaticFactorCategory.TEMPORAL_SESSION_CONTEXT, AutomaticFactorValueType.INTEGER,
        unit="iso_weekday", source_kind=AutomaticFactorSourceKind.DERIVED,
        capture_semantics=CaptureSemantics.AT_ENTRY, applicability="ALL",
        supports_filter=True, supports_group=True,
    ),
    AutomaticFactorDefinition(
        "volume_1d_at_entry", "Volume 1d at entry",
        "Накопленный объём текущего UTC-дня до минуты входа",
        AutomaticFactorCategory.TRADING_ACTIVITY_LIQUIDITY, AutomaticFactorValueType.DECIMAL,
        unit="base", source_kind=AutomaticFactorSourceKind.MARKET_DATA,
        capture_semantics=CaptureSemantics.AT_ENTRY, applicability="BYBIT_LINEAR_USDT",
    ),
    AutomaticFactorDefinition(
        "turnover_1d_at_entry", "Turnover 1d at entry",
        "Накопленный оборот текущего UTC-дня до минуты входа",
        AutomaticFactorCategory.TRADING_ACTIVITY_LIQUIDITY, AutomaticFactorValueType.DECIMAL,
        unit="USDT", source_kind=AutomaticFactorSourceKind.MARKET_DATA,
        capture_semantics=CaptureSemantics.AT_ENTRY, applicability="BYBIT_LINEAR_USDT",
    ),
    AutomaticFactorDefinition(
        "previous_day_volume", "Previous day volume",
        "Полный объём предыдущей закрытой UTC-дневной свечи",
        AutomaticFactorCategory.TRADING_ACTIVITY_LIQUIDITY, AutomaticFactorValueType.DECIMAL,
        unit="base", source_kind=AutomaticFactorSourceKind.MARKET_DATA,
        capture_semantics=CaptureSemantics.PREVIOUS_CLOSED_BAR, applicability="BYBIT_LINEAR_USDT",
    ),
    AutomaticFactorDefinition(
        "previous_day_turnover", "Previous day turnover",
        "Полный оборот предыдущей закрытой UTC-дневной свечи",
        AutomaticFactorCategory.TRADING_ACTIVITY_LIQUIDITY, AutomaticFactorValueType.DECIMAL,
        unit="USDT", source_kind=AutomaticFactorSourceKind.MARKET_DATA,
        capture_semantics=CaptureSemantics.PREVIOUS_CLOSED_BAR, applicability="BYBIT_LINEAR_USDT",
    ),
    AutomaticFactorDefinition(
        "avg_volume_prev_5d", "Average volume previous 5d",
        "Средний объём пяти предыдущих закрытых UTC-дневных свечей",
        AutomaticFactorCategory.TRADING_ACTIVITY_LIQUIDITY, AutomaticFactorValueType.DECIMAL,
        unit="base", source_kind=AutomaticFactorSourceKind.MARKET_DATA,
        capture_semantics=CaptureSemantics.PREVIOUS_CLOSED_BAR, applicability="BYBIT_LINEAR_USDT",
    ),
    AutomaticFactorDefinition(
        "avg_turnover_prev_5d", "Average turnover previous 5d",
        "Средний оборот пяти предыдущих закрытых UTC-дневных свечей",
        AutomaticFactorCategory.TRADING_ACTIVITY_LIQUIDITY, AutomaticFactorValueType.DECIMAL,
        unit="USDT", source_kind=AutomaticFactorSourceKind.MARKET_DATA,
        capture_semantics=CaptureSemantics.PREVIOUS_CLOSED_BAR, applicability="BYBIT_LINEAR_USDT",
    ),
    AutomaticFactorDefinition(
        "rvol_at_entry", "RVOL at entry",
        "Объём до минуты входа / средний объём до той же минуты за 5 полных UTC-дней",
        AutomaticFactorCategory.TRADING_ACTIVITY_LIQUIDITY, AutomaticFactorValueType.DECIMAL,
        unit="ratio", source_kind=AutomaticFactorSourceKind.MARKET_DATA,
        capture_semantics=CaptureSemantics.AT_ENTRY, applicability="BYBIT_LINEAR_USDT",
    ),
    AutomaticFactorDefinition(
        "market_price_at_entry_snapshot", "Market price at entry snapshot",
        "Цена закрытия последней закрытой 1m свечи перед входом",
        AutomaticFactorCategory.PRICE_DYNAMICS_RETURNS, AutomaticFactorValueType.DECIMAL,
        unit="USDT", source_kind=AutomaticFactorSourceKind.MARKET_DATA,
        capture_semantics=CaptureSemantics.AT_ENTRY, applicability="BYBIT_LINEAR_USDT",
    ),
    AutomaticFactorDefinition(
        "day_open_price", "Day open price",
        "Цена открытия первой использованной 1m свечи UTC-дня",
        AutomaticFactorCategory.PRICE_DYNAMICS_RETURNS, AutomaticFactorValueType.DECIMAL,
        unit="USDT", source_kind=AutomaticFactorSourceKind.MARKET_DATA,
        capture_semantics=CaptureSemantics.AT_ENTRY, applicability="BYBIT_LINEAR_USDT",
    ),
    AutomaticFactorDefinition(
        "day_high_at_entry", "Day high at entry",
        "Максимум high закрытых 1m свечей текущего UTC-дня до входа",
        AutomaticFactorCategory.PRICE_DYNAMICS_RETURNS, AutomaticFactorValueType.DECIMAL,
        unit="USDT", source_kind=AutomaticFactorSourceKind.MARKET_DATA,
        capture_semantics=CaptureSemantics.AT_ENTRY, applicability="BYBIT_LINEAR_USDT",
    ),
    AutomaticFactorDefinition(
        "day_low_at_entry", "Day low at entry",
        "Минимум low закрытых 1m свечей текущего UTC-дня до входа",
        AutomaticFactorCategory.PRICE_DYNAMICS_RETURNS, AutomaticFactorValueType.DECIMAL,
        unit="USDT", source_kind=AutomaticFactorSourceKind.MARKET_DATA,
        capture_semantics=CaptureSemantics.AT_ENTRY, applicability="BYBIT_LINEAR_USDT",
    ),
    AutomaticFactorDefinition(
        "day_change_pct_at_entry", "Day change percent at entry",
        "Изменение цены от открытия UTC-дня до входа в процентах",
        AutomaticFactorCategory.PRICE_DYNAMICS_RETURNS, AutomaticFactorValueType.DECIMAL,
        unit="percent", source_kind=AutomaticFactorSourceKind.MARKET_DATA,
        capture_semantics=CaptureSemantics.AT_ENTRY, applicability="BYBIT_LINEAR_USDT",
    ),
    AutomaticFactorDefinition(
        "day_range_pct_at_entry", "Day range percent at entry",
        "Диапазон high-low текущего UTC-дня относительно открытия в процентах",
        AutomaticFactorCategory.PRICE_DYNAMICS_RETURNS, AutomaticFactorValueType.DECIMAL,
        unit="percent", source_kind=AutomaticFactorSourceKind.MARKET_DATA,
        capture_semantics=CaptureSemantics.AT_ENTRY, applicability="BYBIT_LINEAR_USDT",
    ),
    AutomaticFactorDefinition(
        "day_range_position_at_entry", "Day range position at entry",
        "Положение рыночной цены на момент входа внутри диапазона текущего UTC-дня",
        AutomaticFactorCategory.PRICE_DYNAMICS_RETURNS, AutomaticFactorValueType.DECIMAL,
        unit="ratio", source_kind=AutomaticFactorSourceKind.MARKET_DATA,
        capture_semantics=CaptureSemantics.AT_ENTRY, applicability="BYBIT_LINEAR_USDT",
    ),
    AutomaticFactorDefinition(
        "atr_1d_14", "ATR 1d 14",
        "Среднее арифметическое 14 True Range по закрытым UTC-дням",
        AutomaticFactorCategory.VOLATILITY_RANGE, AutomaticFactorValueType.DECIMAL,
        unit="USDT", source_kind=AutomaticFactorSourceKind.MARKET_DATA,
        capture_semantics=CaptureSemantics.AT_ENTRY, applicability="BYBIT_LINEAR_USDT",
    ),
    AutomaticFactorDefinition(
        "atr_1d_14_pct", "ATR 1d 14 percent",
        "ATR 1d 14 относительно цены входа в процентах",
        AutomaticFactorCategory.VOLATILITY_RANGE, AutomaticFactorValueType.DECIMAL,
        unit="percent", source_kind=AutomaticFactorSourceKind.MARKET_DATA,
        capture_semantics=CaptureSemantics.AT_ENTRY, applicability="BYBIT_LINEAR_USDT",
    ),
    AutomaticFactorDefinition(
        "day_range_to_atr", "Day range to ATR",
        "Текущий внутридневной диапазон в единицах ATR 1d 14",
        AutomaticFactorCategory.VOLATILITY_RANGE, AutomaticFactorValueType.DECIMAL,
        unit="ratio", source_kind=AutomaticFactorSourceKind.MARKET_DATA,
        capture_semantics=CaptureSemantics.AT_ENTRY, applicability="BYBIT_LINEAR_USDT",
    ),
    AutomaticFactorDefinition(
        "vwap_1d_at_entry", "VWAP 1d at entry",
        "Накопленный turnover текущего UTC-дня / накопленный volume до входа",
        AutomaticFactorCategory.PRICE_DYNAMICS_RETURNS, AutomaticFactorValueType.DECIMAL,
        unit="USDT", source_kind=AutomaticFactorSourceKind.MARKET_DATA,
        capture_semantics=CaptureSemantics.AT_ENTRY, applicability="BYBIT_LINEAR_USDT",
    ),
    AutomaticFactorDefinition(
        "distance_to_vwap_pct", "Distance to VWAP percent",
        "Отклонение цены входа от накопленного VWAP в процентах",
        AutomaticFactorCategory.PRICE_DYNAMICS_RETURNS, AutomaticFactorValueType.DECIMAL,
        unit="percent", source_kind=AutomaticFactorSourceKind.MARKET_DATA,
        capture_semantics=CaptureSemantics.AT_ENTRY, applicability="BYBIT_LINEAR_USDT",
    ),
    AutomaticFactorDefinition(
        "change_24h_pct_at_entry", "Change 24h percent at entry",
        "Изменение цены относительно exact comparable 1m candle 24 часа назад",
        AutomaticFactorCategory.PRICE_DYNAMICS_RETURNS, AutomaticFactorValueType.DECIMAL,
        unit="percent", source_kind=AutomaticFactorSourceKind.MARKET_DATA,
        capture_semantics=CaptureSemantics.AT_ENTRY, applicability="BYBIT_LINEAR_USDT",
    ),
    AutomaticFactorDefinition(
        "open_interest_base_at_entry", "Open interest base at entry",
        "Открытый интерес в базовой валюте на историческом 5m cutoff",
        AutomaticFactorCategory.DERIVATIVES_POSITIONING, AutomaticFactorValueType.DECIMAL,
        unit="base", source_kind=AutomaticFactorSourceKind.MARKET_DATA,
        capture_semantics=CaptureSemantics.AT_ENTRY, applicability="BYBIT_LINEAR_USDT",
    ),
    AutomaticFactorDefinition(
        "open_interest_notional_usdt_at_entry", "Open interest notional at entry",
        "Открытый интерес в USDT по исторической mark price",
        AutomaticFactorCategory.DERIVATIVES_POSITIONING, AutomaticFactorValueType.DECIMAL,
        unit="USDT", source_kind=AutomaticFactorSourceKind.MARKET_DATA,
        capture_semantics=CaptureSemantics.AT_ENTRY, applicability="BYBIT_LINEAR_USDT",
    ),
    AutomaticFactorDefinition(
        "open_interest_change_1h_pct_at_entry", "Open interest change 1h",
        "Изменение открытого интереса за час по exact 5m records",
        AutomaticFactorCategory.DERIVATIVES_POSITIONING, AutomaticFactorValueType.DECIMAL,
        unit="percent", source_kind=AutomaticFactorSourceKind.MARKET_DATA,
        capture_semantics=CaptureSemantics.AT_ENTRY, applicability="BYBIT_LINEAR_USDT",
    ),
    AutomaticFactorDefinition(
        "open_interest_change_4h_pct_at_entry", "Open interest change 4h",
        "Изменение открытого интереса за четыре часа по exact 5m records",
        AutomaticFactorCategory.DERIVATIVES_POSITIONING, AutomaticFactorValueType.DECIMAL,
        unit="percent", source_kind=AutomaticFactorSourceKind.MARKET_DATA,
        capture_semantics=CaptureSemantics.AT_ENTRY, applicability="BYBIT_LINEAR_USDT",
    ),
    AutomaticFactorDefinition(
        "open_interest_change_24h_pct_at_entry", "Open interest change 24h",
        "Изменение открытого интереса за 24 часа по exact 5m records",
        AutomaticFactorCategory.DERIVATIVES_POSITIONING, AutomaticFactorValueType.DECIMAL,
        unit="percent", source_kind=AutomaticFactorSourceKind.MARKET_DATA,
        capture_semantics=CaptureSemantics.AT_ENTRY, applicability="BYBIT_LINEAR_USDT",
    ),
    AutomaticFactorDefinition(
        "last_settled_funding_rate_at_entry", "Last settled funding rate",
        "Последняя settled funding rate не позже времени входа",
        AutomaticFactorCategory.CARRY_FUNDING, AutomaticFactorValueType.DECIMAL,
        unit="ratio", source_kind=AutomaticFactorSourceKind.MARKET_DATA,
        capture_semantics=CaptureSemantics.AT_ENTRY, applicability="BYBIT_LINEAR_USDT",
    ),
    AutomaticFactorDefinition(
        "avg_last_3_settled_funding_rate_at_entry", "Average last 3 settled funding rates",
        "Среднее арифметическое трёх последних settled funding rates",
        AutomaticFactorCategory.CARRY_FUNDING, AutomaticFactorValueType.DECIMAL,
        unit="ratio", source_kind=AutomaticFactorSourceKind.MARKET_DATA,
        capture_semantics=CaptureSemantics.AT_ENTRY, applicability="BYBIT_LINEAR_USDT",
    ),
    AutomaticFactorDefinition(
        "funding_interval_minutes_inferred_at_entry", "Inferred funding interval",
        "Исторический funding interval в минутах по двум settlement timestamps",
        AutomaticFactorCategory.CARRY_FUNDING, AutomaticFactorValueType.INTEGER,
        unit="minutes", source_kind=AutomaticFactorSourceKind.MARKET_DATA,
        capture_semantics=CaptureSemantics.AT_ENTRY, applicability="BYBIT_LINEAR_USDT",
    ),
    AutomaticFactorDefinition(
        "minutes_since_last_funding_at_entry", "Minutes since last funding",
        "Время от последнего historical funding settlement до входа",
        AutomaticFactorCategory.CARRY_FUNDING, AutomaticFactorValueType.DECIMAL,
        unit="minutes", source_kind=AutomaticFactorSourceKind.MARKET_DATA,
        capture_semantics=CaptureSemantics.AT_ENTRY, applicability="BYBIT_LINEAR_USDT",
    ),
    AutomaticFactorDefinition(
        "minutes_to_next_funding_inferred_at_entry", "Minutes to next inferred funding",
        "Ожидаемое время до следующего settlement по historical interval",
        AutomaticFactorCategory.CARRY_FUNDING, AutomaticFactorValueType.DECIMAL,
        unit="minutes", source_kind=AutomaticFactorSourceKind.MARKET_DATA,
        capture_semantics=CaptureSemantics.AT_ENTRY, applicability="BYBIT_LINEAR_USDT",
    ),
    AutomaticFactorDefinition(
        "mark_price_at_entry_snapshot", "Mark price at entry snapshot",
        "Close exact closed 1m mark-price candle перед входом",
        AutomaticFactorCategory.DERIVATIVES_POSITIONING, AutomaticFactorValueType.DECIMAL,
        unit="USDT", source_kind=AutomaticFactorSourceKind.MARKET_DATA,
        capture_semantics=CaptureSemantics.AT_ENTRY, applicability="BYBIT_LINEAR_USDT",
    ),
    AutomaticFactorDefinition(
        "index_price_at_entry_snapshot", "Index price at entry snapshot",
        "Close exact closed 1m index-price candle перед входом",
        AutomaticFactorCategory.DERIVATIVES_POSITIONING, AutomaticFactorValueType.DECIMAL,
        unit="USDT", source_kind=AutomaticFactorSourceKind.MARKET_DATA,
        capture_semantics=CaptureSemantics.AT_ENTRY, applicability="BYBIT_LINEAR_USDT",
    ),
    AutomaticFactorDefinition(
        "mark_index_basis_pct_at_entry", "Mark index basis percent at entry",
        "Отклонение mark price от index price на историческом cutoff",
        AutomaticFactorCategory.DERIVATIVES_POSITIONING, AutomaticFactorValueType.DECIMAL,
        unit="percent", source_kind=AutomaticFactorSourceKind.MARKET_DATA,
        capture_semantics=CaptureSemantics.AT_ENTRY, applicability="BYBIT_LINEAR_USDT",
    ),
    AutomaticFactorDefinition(
        "mae_observed_1m_extreme_price", "Observed 1m MAE extreme price",
        "Наблюдаемый 1m adverse extreme price с полными свечами и endpoints сделки",
        AutomaticFactorCategory.VOLATILITY_RANGE, AutomaticFactorValueType.DECIMAL,
        unit="USDT", source_kind=AutomaticFactorSourceKind.MARKET_DATA,
        capture_semantics=CaptureSemantics.POST_TRADE, applicability="BYBIT_LINEAR_USDT",
    ),
    AutomaticFactorDefinition(
        "mfe_observed_1m_extreme_price", "Observed 1m MFE extreme price",
        "Наблюдаемый 1m favorable extreme price с полными свечами и endpoints сделки",
        AutomaticFactorCategory.VOLATILITY_RANGE, AutomaticFactorValueType.DECIMAL,
        unit="USDT", source_kind=AutomaticFactorSourceKind.MARKET_DATA,
        capture_semantics=CaptureSemantics.POST_TRADE, applicability="BYBIT_LINEAR_USDT",
    ),
    AutomaticFactorDefinition(
        "mae_observed_1m_price_distance", "Observed 1m MAE price distance",
        "Наблюдаемая adverse дистанция цены от entry без R-нормализации",
        AutomaticFactorCategory.VOLATILITY_RANGE, AutomaticFactorValueType.DECIMAL,
        unit="USDT", source_kind=AutomaticFactorSourceKind.MARKET_DATA,
        capture_semantics=CaptureSemantics.POST_TRADE, applicability="BYBIT_LINEAR_USDT",
    ),
    AutomaticFactorDefinition(
        "mfe_observed_1m_price_distance", "Observed 1m MFE price distance",
        "Наблюдаемая favorable дистанция цены от entry без R-нормализации",
        AutomaticFactorCategory.VOLATILITY_RANGE, AutomaticFactorValueType.DECIMAL,
        unit="USDT", source_kind=AutomaticFactorSourceKind.MARKET_DATA,
        capture_semantics=CaptureSemantics.POST_TRADE, applicability="BYBIT_LINEAR_USDT",
    ),
    AutomaticFactorDefinition(
        "mae_observed_1m_pct", "Observed 1m MAE percent",
        "Наблюдаемая MAE price distance относительно entry price",
        AutomaticFactorCategory.VOLATILITY_RANGE, AutomaticFactorValueType.DECIMAL,
        unit="percent", source_kind=AutomaticFactorSourceKind.MARKET_DATA,
        capture_semantics=CaptureSemantics.POST_TRADE, applicability="BYBIT_LINEAR_USDT",
    ),
    AutomaticFactorDefinition(
        "mfe_observed_1m_pct", "Observed 1m MFE percent",
        "Наблюдаемая MFE price distance относительно entry price",
        AutomaticFactorCategory.VOLATILITY_RANGE, AutomaticFactorValueType.DECIMAL,
        unit="percent", source_kind=AutomaticFactorSourceKind.MARKET_DATA,
        capture_semantics=CaptureSemantics.POST_TRADE, applicability="BYBIT_LINEAR_USDT",
    ),
    AutomaticFactorDefinition(
        "mae_observed_1m_gross_pnl_usdt", "Observed 1m MAE gross PnL magnitude",
        "Наблюдаемая MAE distance умноженная на quantity без fees/funding/expenses",
        AutomaticFactorCategory.VOLATILITY_RANGE, AutomaticFactorValueType.DECIMAL,
        unit="USDT", source_kind=AutomaticFactorSourceKind.MARKET_DATA,
        capture_semantics=CaptureSemantics.POST_TRADE, applicability="BYBIT_LINEAR_USDT",
    ),
    AutomaticFactorDefinition(
        "mfe_observed_1m_gross_pnl_usdt", "Observed 1m MFE gross PnL magnitude",
        "Наблюдаемая MFE distance умноженная на quantity без fees/funding/expenses",
        AutomaticFactorCategory.VOLATILITY_RANGE, AutomaticFactorValueType.DECIMAL,
        unit="USDT", source_kind=AutomaticFactorSourceKind.MARKET_DATA,
        capture_semantics=CaptureSemantics.POST_TRADE, applicability="BYBIT_LINEAR_USDT",
    ),
    AutomaticFactorDefinition(
        "exit_directional_move_price_signed", "Exit directional move price signed",
        "Направленное изменение цены от entry до exit с учётом направления сделки",
        AutomaticFactorCategory.PRICE_DYNAMICS_RETURNS, AutomaticFactorValueType.DECIMAL,
        unit="USDT", source_kind=AutomaticFactorSourceKind.DERIVED,
        capture_semantics=CaptureSemantics.POST_TRADE, applicability="CLOSED",
    ),
    AutomaticFactorDefinition(
        "exit_directional_move_pct_signed", "Exit directional move percent signed",
        "Направленное изменение цены от entry до exit в процентах",
        AutomaticFactorCategory.PRICE_DYNAMICS_RETURNS, AutomaticFactorValueType.DECIMAL,
        unit="percent", source_kind=AutomaticFactorSourceKind.DERIVED,
        capture_semantics=CaptureSemantics.POST_TRADE, applicability="CLOSED",
    ),
    AutomaticFactorDefinition(
        "exit_efficiency_pct_of_observed_mfe", "Exit efficiency percent of observed MFE",
        "Реализованное направленное движение как доля наблюдаемого MFE",
        AutomaticFactorCategory.PRICE_DYNAMICS_RETURNS, AutomaticFactorValueType.DECIMAL,
        unit="percent", source_kind=AutomaticFactorSourceKind.DERIVED,
        capture_semantics=CaptureSemantics.POST_TRADE, applicability="CLOSED",
    ),
    AutomaticFactorDefinition(
        "profit_capture_pct_of_observed_mfe", "Profit capture percent of observed MFE",
        "Положительная часть реализованного движения как доля наблюдаемого MFE",
        AutomaticFactorCategory.PRICE_DYNAMICS_RETURNS, AutomaticFactorValueType.DECIMAL,
        unit="percent", source_kind=AutomaticFactorSourceKind.DERIVED,
        capture_semantics=CaptureSemantics.POST_TRADE, applicability="CLOSED",
    ),
    AutomaticFactorDefinition(
        "mfe_giveback_price_distance", "MFE giveback price distance",
        "Разница между наблюдаемым MFE и реализованным направленным движением",
        AutomaticFactorCategory.PRICE_DYNAMICS_RETURNS, AutomaticFactorValueType.DECIMAL,
        unit="USDT", source_kind=AutomaticFactorSourceKind.DERIVED,
        capture_semantics=CaptureSemantics.POST_TRADE, applicability="CLOSED",
    ),
    AutomaticFactorDefinition(
        "mfe_giveback_pct_of_observed_mfe", "MFE giveback percent of observed MFE",
        "Giveback как доля наблюдаемого MFE",
        AutomaticFactorCategory.PRICE_DYNAMICS_RETURNS, AutomaticFactorValueType.DECIMAL,
        unit="percent", source_kind=AutomaticFactorSourceKind.DERIVED,
        capture_semantics=CaptureSemantics.POST_TRADE, applicability="CLOSED",
    ),
    AutomaticFactorDefinition(
        "mfe_giveback_pct_of_entry", "MFE giveback percent of entry",
        "Giveback относительно entry price",
        AutomaticFactorCategory.PRICE_DYNAMICS_RETURNS, AutomaticFactorValueType.DECIMAL,
        unit="percent", source_kind=AutomaticFactorSourceKind.DERIVED,
        capture_semantics=CaptureSemantics.POST_TRADE, applicability="CLOSED",
    ),
    AutomaticFactorDefinition(
        "mfe_giveback_gross_pnl_usdt", "MFE giveback gross PnL",
        "Giveback price distance, умноженная на quantity, без fees/funding/expenses",
        AutomaticFactorCategory.PRICE_DYNAMICS_RETURNS, AutomaticFactorValueType.DECIMAL,
        unit="USDT", source_kind=AutomaticFactorSourceKind.DERIVED,
        capture_semantics=CaptureSemantics.POST_TRADE, applicability="CLOSED",
    ),
))
