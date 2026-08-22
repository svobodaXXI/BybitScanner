"""Default-off, single-attempt Bybit V5 order mutation boundary."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from enum import Enum
from typing import Any, Callable, Mapping

from terminal.exchange.bybit_v5_adapter import BybitCredentials


class BybitEnvironment(str, Enum):
    TESTNET = "testnet"
    TESTNET_DEMO = "testnet_demo"
    MAINNET_DEMO = "mainnet_demo"
    MAINNET = "mainnet"


class MutationKind(str, Enum):
    CREATE = "create"
    AMEND = "amend"
    CANCEL = "cancel"
    PROTECTION = "protection"


class MutationDisposition(str, Enum):
    ACKNOWLEDGED = "acknowledged"
    REJECTED = "rejected"
    UNKNOWN = "unknown"


class MutationDisabled(RuntimeError):
    pass


class LiveAuthorizationRequired(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class MutationOutcome:
    kind: MutationKind
    disposition: MutationDisposition
    order_id: str | None = None
    order_link_id: str | None = None
    reject_code: int | None = None
    reason: str = ""


class _EmptyRetryCodes(set[int]):
    """Empty and truthy so pybit does not restore its mutation retry defaults."""

    def __bool__(self) -> bool:
        return True


HttpFactory = Callable[..., Any]


def _default_http_factory(**kwargs: Any) -> Any:
    from pybit.unified_trading import HTTP

    return HTTP(**kwargs)


_DETERMINISTIC_REJECT_CODES = frozenset(
    {
        10001, 10003, 10004, 10005, 10007, 10010, 10014,
        110001, 110003, 110004, 110006, 110007, 110008, 110009, 110010,
        110012, 110013, 110017, 110018, 110020, 110021, 110022, 110023,
        110024, 110025, 110026, 110028, 110029, 110030, 110031, 110032,
        110033, 110036, 110038, 110041, 110043, 110044, 110045, 110046,
        110047, 110048, 110049, 110050, 110051, 110052, 110053, 110054,
        110055, 110056, 110057, 110058, 110059, 110060, 110061, 110062,
        110063, 110064, 110065, 110066, 110067, 110068, 110072, 110073,
        110074, 110075, 110076, 110077, 110079, 110080, 110082, 110083,
        110085, 110086, 110087, 110088, 110089, 110090, 110091, 110092,
        110093, 110094, 110095, 110096, 110097, 110098, 110099, 110100,
        110101, 110102, 110103, 110104, 110105, 110106, 110107, 110108,
        110109, 110110, 110111, 110112, 110113, 110114, 110115, 110116,
        110117, 110118, 110119, 110120, 110121, 110122, 110123, 110124,
        110125, 110126, 110127, 110128, 110129, 110130, 110131, 110132,
        110133, 110134, 110135, 110136, 110137, 110138, 110139, 110140,
        110141, 110142, 110143, 110144, 110145, 110146, 110147, 110148,
        110149, 110150, 110151, 110152, 110153, 110154, 110155, 110156,
        110157, 110158, 110159, 110160, 110161, 110162, 110163, 110164,
        110165, 110166, 110167, 110168, 110169, 110170, 110171, 110172,
        110173, 110174, 110175, 110176, 110177, 110178, 110179, 110180,
        110181, 110182, 110183, 110184, 110185, 110186, 110187, 110188,
        110189, 110190, 110191, 110192, 110193, 110194, 110195, 110196,
        110197, 110198, 110199, 110200,
    }
)
_AMBIGUOUS_CODES = frozenset({10000, 10002, 10006, 10016, 10019, 110079})


class BybitV5MutationAdapter:
    """Owns a private lazy HTTP client and never retries a mutation."""

    def __init__(
        self,
        credentials: BybitCredentials,
        *,
        environment: BybitEnvironment,
        mutations_enabled: bool = False,
        live_authorized: bool = False,
        http_factory: HttpFactory | None = None,
    ) -> None:
        if not isinstance(environment, BybitEnvironment):
            raise TypeError("environment must be an explicit BybitEnvironment")
        if environment is BybitEnvironment.MAINNET and not live_authorized:
            raise LiveAuthorizationRequired("MAINNET requires separate explicit live authorization")
        self._credentials = credentials
        self.environment = environment
        self.mutations_enabled = bool(mutations_enabled)
        self.live_authorized = bool(live_authorized)
        self._http_factory = http_factory or _default_http_factory
        self._http_session: Any | None = None

    def __repr__(self) -> str:
        return (
            f"BybitV5MutationAdapter(environment={self.environment.value!r}, "
            f"mutations_enabled={self.mutations_enabled!r}, credentials=<redacted>)"
        )

    def _http(self) -> Any:
        self._require_enabled()
        if self._http_session is None:
            testnet = self.environment in {BybitEnvironment.TESTNET, BybitEnvironment.TESTNET_DEMO}
            demo = self.environment in {
                BybitEnvironment.TESTNET_DEMO,
                BybitEnvironment.MAINNET_DEMO,
            }
            self._http_session = self._http_factory(
                testnet=testnet,
                demo=demo,
                api_key=self._credentials.api_key,
                api_secret=self._credentials.api_secret,
                force_retry=False,
                retry_codes=_EmptyRetryCodes(),
                # pybit counts total attempts, not retries: one means one HTTP dispatch.
                max_retries=1,
                log_requests=False,
            )
        return self._http_session

    def _require_enabled(self) -> None:
        if not self.mutations_enabled:
            raise MutationDisabled("Bybit mutations are disabled")
        if self.environment is BybitEnvironment.MAINNET and not self.live_authorized:
            raise LiveAuthorizationRequired("MAINNET live authorization is absent")

    def create_market_order(
        self, *, symbol: str, side: str, qty: Decimal, order_link_id: str,
        reduce_only: bool, slippage_tolerance_type: str, slippage_tolerance: Decimal,
    ) -> MutationOutcome:
        return self._call(
            MutationKind.CREATE,
            "place_order",
            category="linear", symbol=symbol.upper(), side=side, orderType="Market",
            qty=_decimal_text(qty), positionIdx=0, orderLinkId=order_link_id,
            reduceOnly=reduce_only, slippageToleranceType=slippage_tolerance_type,
            slippageTolerance=_decimal_text(slippage_tolerance),
        )

    def create_limit_order(
        self, *, symbol: str, side: str, qty: Decimal, price: Decimal,
        order_link_id: str, reduce_only: bool = False,
    ) -> MutationOutcome:
        return self._call(
            MutationKind.CREATE,
            "place_order",
            category="linear", symbol=symbol.upper(), side=side, orderType="Limit",
            qty=_decimal_text(qty), price=_decimal_text(price), positionIdx=0,
            orderLinkId=order_link_id, timeInForce="GTC", reduceOnly=reduce_only,
        )

    def amend_order(
        self, *, symbol: str, order_id: str | None = None,
        order_link_id: str | None = None, qty: Decimal | None = None,
        price: Decimal | None = None,
    ) -> MutationOutcome:
        identity = _identity(order_id, order_link_id)
        if qty is None and price is None:
            raise ValueError("amend requires a changed total qty and/or price")
        payload: dict[str, Any] = {"category": "linear", "symbol": symbol.upper(), **identity}
        if qty is not None:
            payload["qty"] = _decimal_text(qty)
        if price is not None:
            payload["price"] = _decimal_text(price)
        return self._call(MutationKind.AMEND, "amend_order", **payload)

    def cancel_order(
        self, *, symbol: str, order_id: str | None = None,
        order_link_id: str | None = None,
    ) -> MutationOutcome:
        return self._call(
            MutationKind.CANCEL, "cancel_order", category="linear",
            symbol=symbol.upper(), **_identity(order_id, order_link_id),
        )

    def set_trading_stop(
        self, *, symbol: str, take_profit: Decimal | None,
        stop_loss: Decimal | None, tp_trigger_by: str, sl_trigger_by: str,
    ) -> MutationOutcome:
        allowed = {"LastPrice", "MarkPrice", "IndexPrice"}
        if tp_trigger_by not in allowed or sl_trigger_by not in allowed:
            raise ValueError("protection trigger type is unsupported")
        payload: dict[str, Any] = {
            "category": "linear", "symbol": symbol.upper(), "tpslMode": "Full",
            "positionIdx": 0, "tpOrderType": "Market", "slOrderType": "Market",
            "tpTriggerBy": tp_trigger_by, "slTriggerBy": sl_trigger_by,
            "takeProfit": _non_negative_decimal_text(take_profit),
            "stopLoss": _non_negative_decimal_text(stop_loss),
        }
        return self._call(MutationKind.PROTECTION, "set_trading_stop", **payload)

    def _call(self, kind: MutationKind, method_name: str, **payload: Any) -> MutationOutcome:
        self._require_enabled()
        try:
            response = getattr(self._http(), method_name)(**payload)
        except Exception as exc:
            return MutationOutcome(kind, MutationDisposition.UNKNOWN, reason=_safe_exception(exc))
        return _normalize_response(kind, response, payload.get("orderLinkId"))


def _identity(order_id: str | None, order_link_id: str | None) -> dict[str, str]:
    supplied = int(bool(order_id)) + int(bool(order_link_id))
    if supplied != 1:
        raise ValueError("exactly one of order_id or order_link_id is required")
    return {"orderId": order_id} if order_id else {"orderLinkId": str(order_link_id)}


def _decimal_text(value: Decimal) -> str:
    if not isinstance(value, Decimal) or not value.is_finite() or value <= 0:
        raise ValueError("mutation Decimal must be finite and positive")
    return str(value)


def _non_negative_decimal_text(value: Decimal | None) -> str:
    if value is None:
        return "0"
    if not isinstance(value, Decimal) or not value.is_finite() or value < 0:
        raise ValueError("protection Decimal must be finite and non-negative")
    return str(value)


def _safe_exception(exc: Exception) -> str:
    name = type(exc).__name__
    return f"mutation transport outcome is ambiguous ({name})"


def _normalize_response(
    kind: MutationKind, response: Any, submitted_link_id: str | None,
) -> MutationOutcome:
    if not isinstance(response, Mapping):
        return MutationOutcome(kind, MutationDisposition.UNKNOWN, reason="missing or invalid response")
    code = response.get("retCode")
    if not isinstance(code, int):
        return MutationOutcome(kind, MutationDisposition.UNKNOWN, reason="response has no valid retCode")
    if code != 0:
        disposition = (
            MutationDisposition.REJECTED
            if code in _DETERMINISTIC_REJECT_CODES and code not in _AMBIGUOUS_CODES
            else MutationDisposition.UNKNOWN
        )
        return MutationOutcome(kind, disposition, reject_code=code, reason=f"Bybit retCode={code}")
    result = response.get("result")
    if not isinstance(result, Mapping):
        return MutationOutcome(kind, MutationDisposition.UNKNOWN, reason="successful response has no result")
    if kind is MutationKind.PROTECTION:
        return MutationOutcome(
            kind, MutationDisposition.ACKNOWLEDGED,
            reason="exchange accepted protection mutation",
        )
    order_id = result.get("orderId")
    order_link_id = result.get("orderLinkId") or submitted_link_id
    if not order_id and not order_link_id:
        return MutationOutcome(kind, MutationDisposition.UNKNOWN, reason="ACK has no order identity")
    return MutationOutcome(
        kind, MutationDisposition.ACKNOWLEDGED,
        order_id=str(order_id) if order_id else None,
        order_link_id=str(order_link_id) if order_link_id else None,
        reason="exchange accepted mutation request",
    )
