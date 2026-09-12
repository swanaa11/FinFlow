"""Money handling utilities.

Design rule (ADR-0006): monetary amounts are stored and processed as **integer
paise** end-to-end. Floating-point money is only permitted at the human boundary
(parsing statement strings) and the presentation boundary (formatting), never in
storage, transformation, or aggregation.
"""

from __future__ import annotations

from decimal import Decimal, InvalidOperation
from typing import Final

PAISE_PER_RUPEE: Final[int] = 100
_SCALE = Decimal("0.01")


class MoneyFormatError(ValueError):
    """Raised when a monetary value cannot be represented exactly in paise."""


def to_paise(amount: Decimal | float | int | str) -> int:
    """Convert a monetary amount to integer paise, exactly.

    Accepts int (rupees), Decimal, str, or float. Floats are converted via
    Decimal(str(...)) to avoid binary-float artefacts; values with more than
    two decimal places raise MoneyFormatError rather than being rounded
    silently.
    """
    if isinstance(amount, float):
        amount = Decimal(str(amount))
    try:
        value = Decimal(amount) if not isinstance(amount, Decimal) else amount
    except InvalidOperation as exc:
        raise MoneyFormatError(f"Not a valid monetary amount: {amount!r}") from exc

    quantized = value.quantize(_SCALE)
    if quantized != value:
        raise MoneyFormatError(f"Amount {value} has sub-paise precision: {amount!r}")
    return int((quantized * PAISE_PER_RUPEE).to_integral_value())


def from_paise(paise: int) -> Decimal:
    """Convert integer paise back to an exact 2-decimal Decimal (rupees)."""
    return (Decimal(paise) / PAISE_PER_RUPEE).quantize(_SCALE)


def format_inr(paise: int, with_decimals: bool = False) -> str:
    """Format paise as an Indian-grouped rupee string: ₹12,34,567.89.

    Uses the Indian numbering system (last 3 digits, then groups of 2), which
    is what statements and users in India expect.
    """
    sign = "-" if paise < 0 else ""
    magnitude = abs(paise)
    rupees, remainder = divmod(magnitude, PAISE_PER_RUPEE)

    digits = str(rupees)
    if len(digits) > 3:
        head, tail = digits[:-3], digits[-3:]
        groups: list[str] = []
        while len(head) > 2:
            groups.insert(0, head[-2:])
            head = head[:-2]
        if head:
            groups.insert(0, head)
        digits = ",".join([*groups, tail])

    out = f"{sign}₹{digits}"
    if with_decimals or remainder:
        out += f".{remainder:02d}"
    return out
