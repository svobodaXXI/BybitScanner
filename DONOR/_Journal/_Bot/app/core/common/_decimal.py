"""Private Decimal conversion helpers for domain value objects."""

from decimal import Decimal, InvalidOperation


def to_decimal(value: object) -> Decimal:
    """Convert supported numeric inputs to a finite Decimal safely."""
    if isinstance(value, bool):
        raise TypeError("boolean is not a valid Decimal input")

    if isinstance(value, Decimal):
        result = value
    elif isinstance(value, (int, str, float)):
        try:
            result = Decimal(str(value))
        except (InvalidOperation, ValueError) as error:
            raise ValueError(f"invalid Decimal value: {value!r}") from error
    else:
        raise TypeError(f"expected Decimal, int, str, or float; got {type(value).__name__}")

    if not result.is_finite():
        raise ValueError("value must be finite")

    return result

