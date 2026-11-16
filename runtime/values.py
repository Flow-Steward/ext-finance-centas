"""Step inputs read strictly, and values written the way Centas WS's examples show them.

Numbers are ``Decimal`` from the request to the wire (``main.py`` reads every
number with a point as Decimal), never float. Dates come in as ISO dates
(YYYY-MM-DD) and go out as YYYY.MM.DD, the form of the documentation's payment
example and of the Centas program.
"""

from __future__ import annotations

import datetime as dt
import re
from collections.abc import Mapping, Sequence
from decimal import ROUND_HALF_UP, Decimal, localcontext
from typing import Any

from .errors import ExtensionError, invalid

CENT = Decimal("0.01")
#: Amounts and quantities this extension accepts: up to 15 whole digits, at most 6
#: decimals (the product price example has six).
MAX_WHOLE_DIGITS = 15
MAX_DECIMALS = 6
_NUMBER_RE = re.compile(r"^[+-]?(\d{1,15})(\.(\d{1,40}))?$", re.ASCII)
_ISO_DATE_RE = re.compile(r"^(\d{4})-(\d{2})-(\d{2})$", re.ASCII)
_WIRE_DATE_RE = re.compile(r"^(\d{4})\.(\d{2})\.(\d{2})$", re.ASCII)
#: Characters a text value may not hold: controls (other than tab and new line where
#: allowed), and the code points XML 1.0 cannot carry.
_SINGLE_LINE_BAD = re.compile(r"[\x00-\x1f\x7f-\x9f￾￿\ud800-\udfff]")
_MULTI_LINE_BAD = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f-\x9f￾￿\ud800-\udfff]")


def number(value: Any, what: str, *, places: int = MAX_DECIMALS) -> Decimal:
    """A finite decimal number with at most ``places`` decimals (trailing zeros aside)."""
    if isinstance(value, bool) or value is None:
        raise invalid(f"{what} must be a number")
    if isinstance(value, int):
        text = str(value)
    elif isinstance(value, Decimal):
        if not value.is_finite():
            raise invalid(f"{what} must be a finite number")
        with localcontext() as ctx:
            ctx.prec = 80
            text = format(value, "f") if abs(value.adjusted()) <= 40 else ""
    elif isinstance(value, str):
        text = value.strip()
    else:
        raise invalid(f"{what} must be a number")
    match = _NUMBER_RE.fullmatch(text)
    if not match:
        raise invalid(
            f"{what} must be a plain number such as 12.50 (a point as decimal mark, at most "
            f"{MAX_WHOLE_DIGITS} whole digits)"
        )
    fraction = (match.group(3) or "").rstrip("0")
    if len(fraction) > places:
        raise invalid(f"{what} may have at most {places} decimals")
    result = Decimal(text)
    return result.quantize(Decimal(1)) if not fraction else result.normalize()


def positive(value: Any, what: str, *, places: int = MAX_DECIMALS) -> Decimal:
    result = number(value, what, places=places)
    if result <= 0:
        raise invalid(f"{what} must be greater than zero")
    return result


def not_negative(value: Any, what: str, *, places: int = MAX_DECIMALS) -> Decimal:
    result = number(value, what, places=places)
    if result < 0:
        raise invalid(f"{what} may not be negative")
    return result


def percent(value: Any, what: str) -> Decimal:
    result = number(value, what, places=2)
    if result < 0 or result > 100:
        raise invalid(f"{what} must be between 0 and 100")
    return result


def cents(value: Decimal) -> Decimal:
    """Rounded half up to cents, as an accountant rounds."""
    return value.quantize(CENT, rounding=ROUND_HALF_UP)


def wire(value: Decimal) -> str:
    """A Decimal as plain digits with a point (never an exponent)."""
    text = format(value, "f")
    if "." in text:
        text = text.rstrip("0").rstrip(".")
    return "0" if text in {"-0", ""} else text


def money(value: Decimal) -> str:
    """An amount with two decimals, as the documentation's examples write them."""
    return format(cents(value), "f")


def iso_date(value: Any, what: str) -> dt.date:
    text = value.strip() if isinstance(value, str) else ""
    match = _ISO_DATE_RE.fullmatch(text)
    if not match:
        raise invalid(f"{what} must be a date written YYYY-MM-DD")
    try:
        return dt.date(int(match.group(1)), int(match.group(2)), int(match.group(3)))
    except ValueError:
        raise invalid(f"{what} is not a real date") from None


def wire_date(value: dt.date) -> str:
    return value.strftime("%Y.%m.%d")


def date_from_wire(text: str) -> str | None:
    """YYYY.MM.DD (or an ISO date) from an export as YYYY-MM-DD; None if it is neither."""
    stripped = text.strip()
    for pattern in (_WIRE_DATE_RE, _ISO_DATE_RE):
        match = pattern.fullmatch(stripped)
        if match:
            try:
                return dt.date(
                    int(match.group(1)), int(match.group(2)), int(match.group(3))
                ).isoformat()
            except ValueError:
                return None
    return None


def decimal_from_wire(text: str) -> str | None:
    """A number from an export, written plainly; None if it is not one."""
    stripped = text.strip()
    if not re.fullmatch(r"[+-]?\d{1,30}(\.\d{1,30})?", stripped, re.ASCII):
        return None
    return wire(Decimal(stripped))


def text(
    value: Any,
    what: str,
    *,
    max_length: int,
    required: bool = False,
    multi_line: bool = False,
) -> str | None:
    """A trimmed text; None when it is empty and not required."""
    if value is None:
        if required:
            raise invalid(f"{what} is required")
        return None
    if (
        isinstance(value, bool)
        or isinstance(value, (Mapping, Sequence))
        and not isinstance(value, str)
    ):
        raise invalid(f"{what} must be text")
    result = str(value).strip()
    if not result:
        if required:
            raise invalid(f"{what} is required")
        return None
    if len(result) > max_length:
        raise invalid(f"{what} may have at most {max_length} characters")
    bad = _MULTI_LINE_BAD if multi_line else _SINGLE_LINE_BAD
    if bad.search(result):
        raise invalid(f"{what} holds control characters")
    return result


def required_text(value: Any, what: str, *, max_length: int, multi_line: bool = False) -> str:
    """A trimmed text that must be given."""
    result = text(value, what, max_length=max_length, required=True, multi_line=multi_line)
    if result is None:  # pragma: no cover - text() refuses an empty required value
        raise invalid(f"{what} is required")
    return result


def choice(value: Any, what: str, options: Mapping[str, str]) -> str | None:
    """One of ``options``' keys, mapped to its wire value; None when not given."""
    if value is None or value == "":
        return None
    if not isinstance(value, str) or value.strip() not in options:
        raise invalid(f"{what} must be one of: {', '.join(options)}")
    return options[value.strip()]


def flag(value: Any, what: str) -> bool:
    if value is None or value == "":
        return False
    if isinstance(value, bool):
        return value
    raise invalid(f"{what} must be true or false")


def records(value: Any, what: str, *, max_items: int) -> list[Mapping[str, Any]]:
    """A non-empty list of objects."""
    if not isinstance(value, list) or not value:
        raise invalid(f"{what} must be a list of at least one item")
    if len(value) > max_items:
        raise invalid(f"{what} may hold at most {max_items} items")
    for index, item in enumerate(value, start=1):
        if not isinstance(item, Mapping):
            raise invalid(f"{what} item {index} must be an object")
    return value


def closed(item: Mapping[str, Any], allowed: frozenset[str], what: str) -> None:
    """Refuse keys the step does not know, rather than silently dropping them."""
    unknown = sorted(str(k) for k in item if k not in allowed)
    if unknown:
        raise invalid(f"{what} has unknown fields: {', '.join(unknown[:10])}")


def int_in(value: Any, what: str, *, default: int, low: int, high: int) -> int:
    if value is None or value == "":
        return default
    if isinstance(value, bool):
        raise invalid(f"{what} must be a whole number")
    if isinstance(value, Decimal) and value == value.to_integral_value():
        value = int(value)
    if isinstance(value, str) and value.strip().isdigit():
        value = int(value.strip())
    if not isinstance(value, int) or not low <= value <= high:
        raise invalid(f"{what} must be a whole number from {low} to {high}")
    return value


__all__ = [
    "CENT",
    "ExtensionError",
    "cents",
    "choice",
    "closed",
    "date_from_wire",
    "decimal_from_wire",
    "flag",
    "int_in",
    "iso_date",
    "money",
    "not_negative",
    "number",
    "percent",
    "positive",
    "records",
    "required_text",
    "text",
    "wire",
    "wire_date",
]
