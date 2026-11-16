"""Read Centas WS's product and payment exports.

Each export is one XML document with every record — no paging, no filters (except
one product id) — holding what the Centas program last uploaded to Centas WS. The
steps read it once, bounded in size (``transport.MAX_EXPORT_BYTES``), filter it
here and return one page of it.

Every record of an export carries the project's key in a ``<token>`` element: it
is dropped while the XML is read, before anything else sees the record, and every
text is scrubbed of the key besides.
"""

from __future__ import annotations

import time
from collections.abc import Callable, Iterable, Mapping
from typing import Any

from . import budget, errors, values
from .context import Context
from .errors import invalid
from .transport import CentasTransport, parse_xml

DEFAULT_LIMIT = 100
MAX_LIMIT = 500
MAX_PAGE = 1_000_000
MAX_WARNINGS = 20

GET_PRODUCTS_INPUTS: frozenset[str] = frozenset({"id", "page", "limit"})
FIND_PRODUCT_INPUTS: frozenset[str] = frozenset({"code", "barcode"})
STOCK_LEVELS_INPUTS: frozenset[str] = frozenset({"code", "warehouse_id", "page", "limit"})
GET_PAYMENTS_INPUTS: frozenset[str] = frozenset(
    {"date_from", "date_to", "reference", "page", "limit"}
)

#: Product element -> output field, for the plain text fields.
_PRODUCT_TEXT = {
    "id": "id",
    "kodas": "code",
    "pavadinimas": "name",
    "matovnt": "unit",
    "grupe1": "group1",
    "grupe2": "group2",
    "grupe3": "group3",
    "barkodas": "barcode",
    "aprasymas": "description",
    "Nuotrauka": "photo",
}
_PRODUCT_NUMBERS = {"kaina": "price", "pvmtar": "vat_percent", "likutis": "stock"}
_PAYMENT_TEXT = {
    "PaymentType": "type",
    "DocNr": "document_number",
    "RefNr": "reference",
    "Details": "details",
    "RecName": "payer_name",
    "RecId": "payer_code",
    "ToAccountNumber": "account",
}


class Warnings:
    """Distinct warnings, bounded."""

    def __init__(self) -> None:
        self.items: list[str] = []

    def add(self, message: str) -> None:
        if message not in self.items and len(self.items) < MAX_WARNINGS:
            self.items.append(message)


def _tag(element: Any) -> str:
    return str(element.tag).split("}", 1)[-1]


def _text(element: Any, scrub: Callable[[Any], Any]) -> str | None:
    text = (element.text or "").strip()
    return scrub(text) if text else None


def _children(element: Any) -> dict[str, Any]:
    """Child elements by tag (the first of each), without the key."""
    out: dict[str, Any] = {}
    for child in element:
        tag = _tag(child)
        if tag.lower() == "token":
            continue
        out.setdefault(tag, child)
    return out


def _number(element: Any, scrub: Callable[[Any], Any], what: str, warnings: Warnings) -> str | None:
    text = _text(element, scrub) if element is not None else None
    if text is None:
        return None
    value = values.decimal_from_wire(text)
    if value is None:
        warnings.add(
            f"Some {what} values are not numbers; they are returned as Centas WS sent them"
        )
        return text
    return value


def _records(raw: bytes, transport: CentasTransport, tag: str, path: str) -> list[Any]:
    try:
        root = parse_xml(raw)
    except ValueError:
        raise errors.no_effect(
            errors.INVALID_RESPONSE,
            f"Centas WS answered {path} with something that is not its XML export",
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
    return [child for child in root if _tag(child) == tag]


def products_of(raw: bytes, transport: CentasTransport) -> tuple[list[dict[str, Any]], Warnings]:
    warnings = Warnings()
    scrub = transport.scrub
    products: list[dict[str, Any]] = []
    for element in _records(raw, transport, "item", "products/export"):
        fields = _children(element)
        product: dict[str, Any] = {}
        for tag, name in _PRODUCT_TEXT.items():
            product[name] = _text(fields[tag], scrub) if tag in fields else None
        for tag, name in _PRODUCT_NUMBERS.items():
            product[name] = _number(fields.get(tag), scrub, name.replace("_", " "), warnings)
        stocks = []
        for stock in fields["Stocks"] if "Stocks" in fields else []:
            parts = _children(stock)
            stocks.append(
                {
                    "warehouse_id": _text(parts["WarehouseId"], scrub)
                    if "WarehouseId" in parts
                    else None,
                    "warehouse_name": _text(parts["WarehouseName"], scrub)
                    if "WarehouseName" in parts
                    else None,
                    "quantity": _number(parts.get("Quantity"), scrub, "quantity", warnings),
                }
            )
        parameters = []
        for parameter in fields["ProductParameters"] if "ProductParameters" in fields else []:
            parts = _children(parameter)
            parameters.append(
                {
                    "name": _text(parts["Name"], scrub) if "Name" in parts else None,
                    "value": _text(parts["Value"], scrub) if "Value" in parts else None,
                }
            )
        product["stocks"] = stocks
        product["parameters"] = parameters
        products.append(product)
    return products, warnings


def payments_of(raw: bytes, transport: CentasTransport) -> tuple[list[dict[str, Any]], Warnings]:
    warnings = Warnings()
    scrub = transport.scrub
    payments: list[dict[str, Any]] = []
    for element in _records(raw, transport, "Payment", "payments/export"):
        fields = _children(element)
        payment: dict[str, Any] = {}
        for tag, name in _PAYMENT_TEXT.items():
            payment[name] = _text(fields[tag], scrub) if tag in fields else None
        date_text = _text(fields["Date"], scrub) if "Date" in fields else None
        date = values.date_from_wire(date_text) if date_text else None
        if date_text and date is None:
            warnings.add(
                "Some payment dates are not dates; they are returned as Centas WS sent them"
            )
        payment["date"] = date if date is not None else date_text
        payment["date_is_valid"] = date is not None
        payment["amount"] = _number(fields.get("Amount"), scrub, "amount", warnings)
        payments.append(payment)
    return payments, warnings


# -- paging ---------------------------------------------------------------------


def _page(operation_input: Mapping[str, Any]) -> tuple[int, int]:
    page = values.int_in(operation_input.get("page"), "Page", default=1, low=1, high=MAX_PAGE)
    limit = values.int_in(
        operation_input.get("limit"), "Rows", default=DEFAULT_LIMIT, low=1, high=MAX_LIMIT
    )
    return page, limit


def paged(rows: list[dict[str, Any]], page: int, limit: int, warnings: Warnings) -> dict[str, Any]:
    start = (page - 1) * limit
    items = rows[start : start + limit]
    has_more = start + limit < len(rows)
    result = {
        "items": items,
        "count": len(items),
        "total": len(rows),
        "page": page,
        "has_more": has_more,
        "next_page": page + 1 if has_more else None,
        "warnings": warnings.items,
    }
    budget.ensure_fits(result)
    return result


def _closed(operation_input: Mapping[str, Any], allowed: Iterable[str]) -> None:
    values.closed(operation_input, frozenset(allowed) | {"connection_ref"}, "The step input")


# -- the read steps -------------------------------------------------------------


def _product_export(
    context: Context, query: list[tuple[str, str]] | None = None
) -> tuple[list[dict[str, Any]], Warnings]:
    raw = context.transport.export("products/export", query or [])
    return products_of(raw, context.transport)


def get_products(context: Context) -> dict[str, Any]:
    _closed(context.operation_input, GET_PRODUCTS_INPUTS)
    product_id = values.text(context.operation_input.get("id"), "Product ID", max_length=50)
    page, limit = _page(context.operation_input)
    products, warnings = _product_export(context, [("id", product_id)] if product_id else None)
    if product_id:
        # Only the product asked for, whatever the export holds.
        products = [p for p in products if p.get("id") == product_id]
    return paged(products, page, limit, warnings)


def find_product(context: Context) -> dict[str, Any]:
    _closed(context.operation_input, FIND_PRODUCT_INPUTS)
    code = values.text(context.operation_input.get("code"), "Code", max_length=50)
    barcode = values.text(context.operation_input.get("barcode"), "Barcode", max_length=50)
    if (code is None) == (barcode is None):
        raise invalid("Give either the product code or the barcode")
    products, warnings = _product_export(context)
    key, wanted = ("code", code) if code is not None else ("barcode", barcode)
    matches = [p for p in products if p.get(key) == wanted]
    if len(matches) > 1:
        raise errors.no_effect(
            errors.CONFLICT,
            f"{len(matches)} products in Centas WS have the {key} {wanted}; it does not name one "
            "product",
        )
    result = {
        "found": bool(matches),
        "product": matches[0] if matches else None,
        "warnings": warnings.items,
    }
    budget.ensure_fits(result)
    return result


def get_stock_levels(context: Context) -> dict[str, Any]:
    _closed(context.operation_input, STOCK_LEVELS_INPUTS)
    code = values.text(context.operation_input.get("code"), "Code", max_length=50)
    warehouse = values.text(
        context.operation_input.get("warehouse_id"), "Warehouse ID", max_length=50
    )
    page, limit = _page(context.operation_input)
    products, warnings = _product_export(context)
    rows: list[dict[str, Any]] = []
    for product in products:
        if code is not None and product.get("code") != code:
            continue
        base = {
            "code": product.get("code"),
            "name": product.get("name"),
            "unit": product.get("unit"),
        }
        stocks = product.get("stocks") or []
        if not stocks:
            if warehouse is None:
                rows.append(
                    {
                        **base,
                        "warehouse_id": None,
                        "warehouse_name": None,
                        "quantity": product.get("stock"),
                    }
                )
            continue
        for stock in stocks:
            if warehouse is not None and stock.get("warehouse_id") != warehouse:
                continue
            rows.append({**base, **stock})
    return paged(rows, page, limit, warnings)


def get_payments(context: Context) -> dict[str, Any]:
    operation_input = context.operation_input
    _closed(operation_input, GET_PAYMENTS_INPUTS)
    date_from = (
        values.iso_date(operation_input["date_from"], "From date")
        if operation_input.get("date_from") is not None
        else None
    )
    date_to = (
        values.iso_date(operation_input["date_to"], "To date")
        if operation_input.get("date_to") is not None
        else None
    )
    if date_from and date_to and date_from > date_to:
        raise invalid("The from date is after the to date")
    reference = values.text(operation_input.get("reference"), "Reference", max_length=100)
    page, limit = _page(operation_input)
    raw = context.transport.export("payments/export")
    payments, warnings = payments_of(raw, context.transport)
    rows: list[dict[str, Any]] = []
    skipped = 0
    for payment in payments:
        valid = payment.pop("date_is_valid")
        if reference is not None and payment.get("reference") != reference:
            continue
        if date_from or date_to:
            if not valid:
                skipped += 1
                continue
            day = str(payment["date"])
            if (date_from and day < date_from.isoformat()) or (
                date_to and day > date_to.isoformat()
            ):
                continue
        rows.append(payment)
    if skipped:
        warnings.add(f"{skipped} payments without a readable date were left out of the date filter")
    return paged(rows, page, limit, warnings)


def test_connection(
    context: Context, clock: Callable[[], float] = time.monotonic
) -> dict[str, Any]:
    _closed(context.operation_input, ())
    started = clock()
    raw = context.transport.probe()
    if not raw.lstrip(b"\xef\xbb\xbf \t\r\n").startswith(b"<"):
        raise errors.no_effect(
            errors.INVALID_RESPONSE,
            "Centas WS answered the product export with something that is not XML",
            failure_class="provider",
            retryable=False,
        )
    return {
        "connected": True,
        "duration_ms": int((clock() - started) * 1000),
        "warnings": [],
    }


__all__ = [
    "DEFAULT_LIMIT",
    "FIND_PRODUCT_INPUTS",
    "GET_PAYMENTS_INPUTS",
    "GET_PRODUCTS_INPUTS",
    "MAX_LIMIT",
    "STOCK_LEVELS_INPUTS",
    "find_product",
    "get_payments",
    "get_products",
    "get_stock_levels",
    "paged",
    "payments_of",
    "products_of",
    "test_connection",
]
