"""Canonical compatibility policy for Bybit historical Trade executions."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation


@dataclass(frozen=True, slots=True)
class CompatibilityResult:
    supported: bool
    reason: str | None = None

    def __post_init__(self) -> None:
        if self.supported and self.reason is not None:
            raise ValueError("a supported execution cannot have an incompatibility reason")
        if not self.supported and not self.reason:
            raise ValueError("an unsupported execution must have a reason")


SUPPORTED = CompatibilityResult(True)


def check_bybit_execution(item: object) -> CompatibilityResult:
    """Apply the same V1 predicate to raw or pre-normalization Bybit data."""
    if not isinstance(item, dict):
        return CompatibilityResult(False, "normalization error")
    category = item.get("category")
    if category is not None and str(category).strip().lower() != "linear":
        return CompatibilityResult(False, "unsupported category")
    settle_coin = item.get("settleCoin")
    if settle_coin is not None and str(settle_coin).strip().upper() != "USDT":
        return CompatibilityResult(
            False,
            "USDC unsupported" if str(settle_coin).strip().upper() == "USDC" else "unsupported settleCoin",
        )
    exec_type = item.get("execType")
    if exec_type is not None and (not isinstance(exec_type, str) or exec_type.strip().lower() != "trade"):
        return CompatibilityResult(
            False,
            "funding excluded" if isinstance(exec_type, str) and exec_type.strip().lower() == "funding" else "unsupported execType",
        )
    for key in ("execQty", "execPrice", "execFee"):
        if not _text(item.get(key)):
            return CompatibilityResult(False, f"missing {key}")
    if not _text(item.get("symbol")) or not _text(item.get("execId")) or not _text(item.get("execTime")):
        return CompatibilityResult(False, "normalization error")
    if item.get("side") not in {"Buy", "Sell"}:
        return CompatibilityResult(False, "invalid side")
    try:
        quantity = Decimal(item["execQty"])
        price = Decimal(item["execPrice"])
        fee = Decimal(item["execFee"])
    except (InvalidOperation, TypeError, ValueError):
        return CompatibilityResult(False, "normalization error")
    if not all(value.is_finite() for value in (quantity, price, fee)) or quantity <= 0 or price <= 0 or fee < 0:
        return CompatibilityResult(False, "normalization error")
    try:
        timestamp = Decimal(item["execTime"])
        if not timestamp.is_finite() or timestamp != timestamp.to_integral_value():
            return CompatibilityResult(False, "normalization error")
    except (InvalidOperation, TypeError, ValueError):
        return CompatibilityResult(False, "normalization error")
    return SUPPORTED


def check_normalized_bybit_execution(fact: object) -> CompatibilityResult:
    """Apply the same policy after adapter normalization for plan/import paths."""
    if getattr(fact, "exchange", None) != "BYBIT":
        return CompatibilityResult(False, "unsupported exchange")
    fee = getattr(getattr(fact, "fee", None), "currency", None)
    if str(fee).upper() != "USDT":
        return CompatibilityResult(False, "feeCurrency != USDT")
    side = getattr(getattr(fact, "side", None), "value", getattr(fact, "side", None))
    if side not in {"BUY", "SELL"}:
        return CompatibilityResult(False, "invalid side")
    if getattr(fact, "quantity", None) is None or getattr(fact, "price", None) is None or getattr(fact, "executed_at", None) is None:
        return CompatibilityResult(False, "normalization error")
    return SUPPORTED


def _text(value: object) -> bool:
    return isinstance(value, str) and bool(value.strip())
