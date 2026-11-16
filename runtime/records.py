"""Records read from Centas WS, kept under Centas's own field names.

The specification describes most answers by example only, so a record is returned
with the fields Centas WS sent — nothing invented, nothing renamed — and only made
safe and uniform:

* the project's key (a ``token`` element or field, in any letter case) is dropped,
  and every text is scrubbed of it besides;
* dates written YYYY.MM.DD (the purchase export example) are given as YYYY-MM-DD;
  a date field that is not a date is returned as sent, with a warning;
* numbers are plain text: XML values exactly as sent, JSON numbers written without an
  exponent;
* repeated rows and nested lists (eilute, Stocks, ProductParameters, padaliniai)
  become lists; JSON-encoded text fields (stocks, parameters) are decoded.
"""

from __future__ import annotations

import json
from collections.abc import Callable, Mapping
from decimal import Decimal
from typing import Any

from . import errors, values
from .transport import parse_xml

MAX_WARNINGS = 20

#: Fields that hold a date.
DATE_FIELDS = frozenset(
    {"data", "apmok_iki", "uzsak_data", "pristat_data", "Date", "date", "DocumentDate"}
)
#: Repeated child elements that are always a list, even when there is one.
LIST_ELEMENTS = frozenset({"eilute", "payment"})
#: Container element -> its repeated child: the container becomes a list.
CONTAINERS = {"Stocks": "Stock", "ProductParameters": "Parameter", "padaliniai": "padalinis"}
#: JSON fields that hold JSON-encoded text (ProductBasic, ProductFull).
JSON_TEXT_FIELDS = frozenset({"stocks", "parameters"})

Scrub = Callable[[Any], Any]


class Warnings:
    """Distinct warnings, bounded."""

    def __init__(self) -> None:
        self.items: list[str] = []

    def add(self, message: str) -> None:
        if message not in self.items and len(self.items) < MAX_WARNINGS:
            self.items.append(message)


def _tag(element: Any) -> str:
    return str(element.tag).split("}", 1)[-1]


def _date(field: str, value: str, warnings: Warnings) -> str:
    iso = values.date_from_wire(value)
    if iso is None:
        warnings.add(f"Some {field} values are not dates; they are returned as Centas WS sent them")
        return value
    return iso


def element_value(element: Any, scrub: Scrub, warnings: Warnings) -> Any:
    """An element as text (leaf) or as a record (with children)."""
    children = list(element)
    if not children:
        text = (element.text or "").strip()
        return scrub(text) if text else None
    tag = _tag(element)
    if tag in CONTAINERS:
        inner = CONTAINERS[tag]
        return [element_value(c, scrub, warnings) for c in children if _tag(c) == inner]
    record: dict[str, Any] = {}
    for child in children:
        name = _tag(child)
        if name.lower() == "token":
            continue
        value = element_value(child, scrub, warnings)
        if isinstance(value, str) and name in DATE_FIELDS:
            value = _date(name, value, warnings)
        if name in LIST_ELEMENTS:
            record.setdefault(name, []).append(value)
        elif name in record:
            existing = record[name]
            record[name] = [*existing, value] if isinstance(existing, list) else [existing, value]
        else:
            record[name] = value
    return record


def xml_records(
    raw: bytes, scrub: Scrub, *, record_tag: str | None, path: str
) -> tuple[list[dict[str, Any]], Warnings]:
    """The records of an XML answer: the children of <root> named ``record_tag`` (or
    every child when None)."""
    try:
        root = parse_xml(raw)
    except ValueError:
        raise errors.no_effect(
            errors.INVALID_RESPONSE,
            f"Centas WS answered {path} with something that is not its XML",
            failure_class="provider",
            retryable=False,
        ) from None
    if _tag(root) != "root":
        raise errors.no_effect(
            errors.INVALID_RESPONSE,
            f"Centas WS's {path} answer does not have the documented <root> element",
            failure_class="provider",
            retryable=False,
        )
    warnings = Warnings()
    out: list[dict[str, Any]] = []
    for child in root:
        if record_tag is not None and _tag(child) != record_tag:
            continue
        value = element_value(child, scrub, warnings)
        out.append(value if isinstance(value, dict) else {"value": value})
    return out, warnings


def xml_fields(raw: bytes, scrub: Scrub, *, path: str) -> tuple[dict[str, Any], Warnings]:
    """The fields of an XML answer whose <root> holds them directly (statistics)."""
    try:
        root = parse_xml(raw)
    except ValueError:
        raise errors.no_effect(
            errors.INVALID_RESPONSE,
            f"Centas WS answered {path} with something that is not its XML",
            failure_class="provider",
            retryable=False,
        ) from None
    warnings = Warnings()
    value = element_value(root, scrub, warnings)
    return (value if isinstance(value, dict) else {}), warnings


def _plain(value: Any) -> Any:
    """JSON numbers as plain text, like every value read from XML; the key dropped."""
    if isinstance(value, bool) or value is None or isinstance(value, str):
        return value
    if isinstance(value, int):
        return str(value)
    if isinstance(value, Decimal):
        # As written: 121.00 stays 121.00; an exponent is written out.
        return format(value, "f") if value.is_finite() else str(value)
    if isinstance(value, Mapping):
        return {str(k): _plain(v) for k, v in value.items() if str(k).lower() != "token"}
    if isinstance(value, list):
        return [_plain(v) for v in value]
    return value


def json_record(record: Mapping[str, Any], warnings: Warnings) -> dict[str, Any]:
    """A JSON record: the key dropped, JSON-encoded text decoded, dates made ISO, numbers
    as plain text."""
    out: dict[str, Any] = {}
    for key, value in record.items():
        name = str(key)
        if name.lower() == "token":
            continue
        if name in JSON_TEXT_FIELDS and isinstance(value, str) and value.strip():
            try:
                value = json.loads(value, parse_float=Decimal)
            except json.JSONDecodeError:
                warnings.add(f"Some {name} values are not JSON; they are returned as sent")
        elif name in DATE_FIELDS and isinstance(value, str) and value.strip():
            value = _date(name, value.strip(), warnings)
        out[name] = _plain(value)
    return out


__all__ = [
    "Warnings",
    "element_value",
    "json_record",
    "xml_fields",
    "xml_records",
]
