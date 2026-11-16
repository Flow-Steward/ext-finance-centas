"""Read steps: GET operations of Centas WS that change nothing.

Lists have no paging in Centas WS: a step reads the answer once, bounded in size
(``transport.MAX_READ_BYTES``), and returns one page of it.
"""

from __future__ import annotations

import datetime as dt
import re
from collections.abc import Callable, Mapping
from typing import Any

from . import budget, errors, files, values
from .context import Context
from .errors import invalid
from .records import Warnings, json_record, xml_fields, xml_records
from .transport import error_text, parse_json, success_of

DEFAULT_LIMIT = 100
MAX_LIMIT = 500
MAX_PAGE = 1_000_000
#: Days before the key's expiry from which Test the connection warns.
EXPIRY_WARNING_DAYS = 30

PAGING = frozenset({"page", "limit"})
INPUTS: dict[str, frozenset[str]] = {
    "check_service": frozenset(),
    "test_connection": frozenset(),
    "get_statistics": frozenset(),
    "get_products": PAGING,
    "get_product": frozenset({"code"}),
    "get_product_stock": frozenset({"barcode"}) | PAGING,
    "get_product_cards": frozenset({"id"}) | PAGING,
    "get_product_gallery_link": frozenset({"product_id"}),
    "get_sales_document": frozenset({"number"}),
    "get_sales_documents": frozenset({"date_from", "date_to", "unpaid"}) | PAGING,
    "get_order_invoice_pdf": frozenset({"order_number", "check_only"}),
    "get_purchases": frozenset({"date_from", "date_to"}) | PAGING,
    "get_contrahents": frozenset({"id"}) | PAGING,
    "find_company_by_code": frozenset({"code"}),
}


def _closed(context: Context, operation_id: str) -> Mapping[str, Any]:
    values.closed(
        context.operation_input, INPUTS[operation_id] | {"connection_ref"}, "The step input"
    )
    if "page" in INPUTS[operation_id]:
        _page(context.operation_input)  # checked before anything is asked for
    return context.operation_input


def _page(operation_input: Mapping[str, Any]) -> tuple[int, int]:
    page = values.int_in(operation_input.get("page"), "Page", default=1, low=1, high=MAX_PAGE)
    limit = values.int_in(
        operation_input.get("limit"), "Rows", default=DEFAULT_LIMIT, low=1, high=MAX_LIMIT
    )
    return page, limit


def paged(
    rows: list[dict[str, Any]], operation_input: Mapping[str, Any], warnings: Warnings
) -> dict[str, Any]:
    page, limit = _page(operation_input)
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


def _json(context: Context, raw: bytes, path: str) -> dict[str, Any]:
    try:
        data = parse_json(raw)
    except ValueError:
        raise errors.no_effect(
            errors.INVALID_RESPONSE,
            f"Centas WS answered {path} with something that is not its JSON",
            failure_class="provider",
            retryable=False,
        ) from None
    scrubbed = context.transport.scrub(data)
    return scrubbed if isinstance(scrubbed, dict) else {}


def _products(
    context: Context, data: Mapping[str, Any], path: str
) -> tuple[list[dict[str, Any]], Warnings]:
    products = data.get("products")
    if not isinstance(products, list) or not all(isinstance(p, Mapping) for p in products):
        raise errors.no_effect(
            errors.INVALID_RESPONSE,
            f"Centas WS's {path} answer holds no product list",
            failure_class="provider",
            retryable=False,
        )
    warnings = Warnings()
    return [json_record(p, warnings) for p in products], warnings


def _date_input(operation_input: Mapping[str, Any], name: str, what: str) -> str | None:
    if operation_input.get(name) is None:
        return None
    return values.wire_date(values.iso_date(operation_input[name], what))


def _range(operation_input: Mapping[str, Any]) -> tuple[str | None, str | None]:
    start = _date_input(operation_input, "date_from", "From date")
    end = _date_input(operation_input, "date_to", "To date")
    if start and end and start > end:
        raise invalid("The from date is after the to date")
    return start, end


# -- system -------------------------------------------------------------------------


def check_service(context: Context) -> dict[str, Any]:
    _closed(context, "check_service")
    raw = context.transport.read("test", token=False)
    data = _json(context, raw, "test")
    status = data.get("status")
    status = status if isinstance(status, str) else None
    return {"running": status == "ok", "status": status, "warnings": []}


_VALID_UNTIL_RE = re.compile(r"^(\d{4})-(\d{2})-(\d{2})")


def _days_left(valid_until: str | None, today: dt.date) -> int | None:
    match = _VALID_UNTIL_RE.match(valid_until or "")
    if not match:
        return None
    try:
        until = dt.date(int(match.group(1)), int(match.group(2)), int(match.group(3)))
    except ValueError:
        return None
    return (until - today).days


def _expiry_warnings(days: int | None, valid_until: str | None) -> list[str]:
    if days is None:
        return (
            [] if not valid_until else ["Centas WS gave the key's expiry in a form not understood"]
        )
    if days < 0:
        return [f"The WS key expired on {valid_until}"]
    if days <= EXPIRY_WARNING_DAYS:
        return [f"The WS key expires in {days} days ({valid_until}); renew it in Centas WS"]
    return []


def test_connection(context: Context, today: dt.date | None = None) -> dict[str, Any]:
    _closed(context, "test_connection")
    raw = context.transport.read("verify")
    data = _json(context, raw, "verify")
    if success_of(data) is not True:
        raise errors.no_effect(
            errors.AUTHENTICATION_FAILED,
            "Centas WS did not confirm the key"
            + (f": {error_text(data)}" if error_text(data) else ""),
            failure_class="provider",
            retryable=False,
        )
    valid_until = data.get("valid_until")
    valid_until = valid_until if isinstance(valid_until, str) and valid_until.strip() else None
    days = _days_left(valid_until, today or dt.date.today())
    return {
        "connected": True,
        "valid_until": valid_until,
        "days_left": days,
        "warnings": _expiry_warnings(days, valid_until),
    }


_STATISTICS = (
    "new_invoices",
    "new_orders",
    "new_purchases",
    "new_payments_bd",
    "new_payments_cd",
    "new_payments_cd2",
    "new_payments_bc",
)


def get_statistics(context: Context, today: dt.date | None = None) -> dict[str, Any]:
    _closed(context, "get_statistics")
    raw = context.transport.read("statistics")
    fields, warnings = xml_fields(raw, context.transport.scrub, path="statistics")
    result: dict[str, Any] = {}
    for name in _STATISTICS:
        value = fields.get(name)
        result[name] = int(value) if isinstance(value, str) and value.isdigit() else None
        if value is not None and result[name] is None:
            warnings.add(f"{name} is not a count")
    valid_until = fields.get("token_valid_until")
    valid_until = valid_until if isinstance(valid_until, str) else None
    days = _days_left(valid_until, today or dt.date.today())
    result["token_valid_until"] = valid_until
    result["warnings"] = [*warnings.items, *_expiry_warnings(days, valid_until)]
    return result


# -- products -----------------------------------------------------------------------


def get_products(context: Context) -> dict[str, Any]:
    operation_input = _closed(context, "get_products")
    raw = context.transport.read("products/export/json/full")
    products, warnings = _products(
        context, _json(context, raw, "products/export/json/full"), "products/export/json/full"
    )
    return paged(products, operation_input, warnings)


def get_product(context: Context) -> dict[str, Any]:
    operation_input = _closed(context, "get_product")
    code = values.required_text(operation_input.get("code"), "Product code", max_length=50)
    raw = context.transport.read("products/export/json/one", [("kodas", code)])
    products, warnings = _products(
        context, _json(context, raw, "products/export/json/one"), "products/export/json/one"
    )
    matching = [p for p in products if p.get("kodas") == code]
    if len(products) > 1 or (products and not matching):
        raise errors.no_effect(
            errors.INVALID_RESPONSE,
            f"Centas WS answered with {len(products)} products for the code {code}",
            failure_class="provider",
            retryable=False,
        )
    result = {
        "found": bool(matching),
        "product": matching[0] if matching else None,
        "warnings": warnings.items,
    }
    budget.ensure_fits(result)
    return result


def get_product_stock(context: Context) -> dict[str, Any]:
    operation_input = _closed(context, "get_product_stock")
    barcode = values.text(operation_input.get("barcode"), "Barcode", max_length=50)
    raw = context.transport.read("products/export/json", [("barkodas", barcode)] if barcode else [])
    products, warnings = _products(
        context, _json(context, raw, "products/export/json"), "products/export/json"
    )
    return paged(products, operation_input, warnings)


def get_product_cards(context: Context) -> dict[str, Any]:
    operation_input = _closed(context, "get_product_cards")
    product_id = (
        values.int_in(operation_input.get("id"), "Product ID", default=0, low=1, high=2_147_483_647)
        if operation_input.get("id") is not None
        else None
    )
    query = [("id", str(product_id))] if product_id is not None else []
    raw = context.transport.read("products/export", query)
    items, warnings = xml_records(
        raw, context.transport.scrub, record_tag="item", path="products/export"
    )
    if product_id is not None:
        items = [i for i in items if i.get("id") == str(product_id)]
    return paged(items, operation_input, warnings)


def get_product_gallery_link(context: Context) -> dict[str, Any]:
    operation_input = _closed(context, "get_product_gallery_link")
    product_id = values.int_in(
        operation_input.get("product_id"), "Product ID", default=0, low=1, high=2_147_483_647
    )
    raw = context.transport.read("products/gallery", [("product_id", str(product_id))])
    data = _json(context, raw, "products/gallery")
    link = data.get("link")
    link = link if isinstance(link, str) and link.startswith(("https://", "http://")) else None
    warnings = [] if link else ["Centas WS returned no gallery link"]
    return {"link": link, "warnings": warnings}


# -- sales documents ----------------------------------------------------------------


def get_sales_document(context: Context) -> dict[str, Any]:
    operation_input = _closed(context, "get_sales_document")
    number = values.required_text(operation_input.get("number"), "Document number", max_length=50)
    raw = context.transport.read("documents/get", [("dok_num", number)])
    data = _json(context, raw, "documents/get")
    document = data.get("data")
    warnings = Warnings()
    # The specification describes the document only as "an object with all fields":
    # it is returned as Centas WS sent it, without the key.
    found = isinstance(document, Mapping) and bool(document)
    result = {
        "found": found,
        "document": json_record(document, warnings)
        if found and isinstance(document, Mapping)
        else None,
        "warnings": warnings.items,
    }
    budget.ensure_fits(result)
    return result


def get_sales_documents(context: Context) -> dict[str, Any]:
    operation_input = _closed(context, "get_sales_documents")
    start, end = _range(operation_input)
    unpaid = values.flag(operation_input.get("unpaid"), "Unpaid only")
    if not (start or end or unpaid):
        raise invalid(
            "Give a date (from, to or both) or choose unpaid only: without them Centas WS "
            "hands out its queue of new documents (use Take new sales documents for that)"
        )
    query: list[tuple[str, str]] = []
    if unpaid:
        query.append(("unpaid", "1"))
    if start:
        query.append(("from", start))
    if end:
        query.append(("to", end))
    raw = context.transport.read("documents/export", query)
    items, warnings = xml_records(
        raw, context.transport.scrub, record_tag="dokumentas", path="documents/export"
    )
    return paged(items, operation_input, warnings)


# -- orders -------------------------------------------------------------------------


def get_order_invoice_pdf(context: Context) -> dict[str, Any]:
    operation_input = _closed(context, "get_order_invoice_pdf")
    number = values.required_text(
        operation_input.get("order_number"), "Order number", max_length=50
    )
    check_only = values.flag(operation_input.get("check_only"), "Check only")
    query = [("order_no", number), *([("check", "1")] if check_only else [])]
    try:
        raw = context.transport.read("orders/document/pdf", query, limit=files.MAX_PDF_BYTES)
    except errors.ExtensionError as exc:
        if exc.code == errors.UPSTREAM_VALIDATION_FAILED:
            # Centas WS's JSON refusal: there is no invoice PDF for this order (yet).
            return {"exists": False, "file": None, "size_bytes": None, "warnings": [exc.message]}
        raise
    if raw.lstrip(b"\xef\xbb\xbf \t\r\n").startswith(b"{"):
        data = _json(context, raw, "orders/document/pdf")
        exists = success_of(data) is True
        return {"exists": exists, "file": None, "size_bytes": None, "warnings": []}
    if check_only:
        return {"exists": True, "file": None, "size_bytes": None, "warnings": []}
    if not raw.startswith(b"%PDF"):
        raise errors.no_effect(
            errors.INVALID_RESPONSE,
            "Centas WS answered with something that is not a PDF",
            failure_class="provider",
            retryable=False,
        )
    handle = files.save(
        context,
        raw,
        binding_key=files.PDF_BINDING,
        content_type=files.PDF_CONTENT_TYPE,
        what="The invoice PDF",
    )
    return {"exists": True, "file": handle, "size_bytes": len(raw), "warnings": []}


# -- purchases ----------------------------------------------------------------------


def get_purchases(context: Context) -> dict[str, Any]:
    operation_input = _closed(context, "get_purchases")
    start, end = _range(operation_input)
    if not (start and end):
        raise invalid(
            "Give both dates: only with a date range does Centas WS leave its purchase queue "
            "unchanged (use Take new purchases for the queue)"
        )
    raw = context.transport.read("purchase/export", [("from", start), ("to", end)])
    items, warnings = xml_records(
        raw, context.transport.scrub, record_tag="dokumentas", path="purchase/export"
    )
    return paged(items, operation_input, warnings)


# -- contrahents --------------------------------------------------------------------


def get_contrahents(context: Context) -> dict[str, Any]:
    operation_input = _closed(context, "get_contrahents")
    contrahent_id = (
        values.int_in(
            operation_input.get("id"), "Contrahent ID", default=0, low=1, high=2_147_483_647
        )
        if operation_input.get("id") is not None
        else None
    )
    query = [("id", str(contrahent_id))] if contrahent_id is not None else []
    raw = context.transport.read("contrahents/export", query)
    items, warnings = xml_records(
        raw, context.transport.scrub, record_tag="item", path="contrahents/export"
    )
    if contrahent_id is not None:
        items = [i for i in items if i.get("id") == str(contrahent_id)]
    return paged(items, operation_input, warnings)


def find_company_by_code(context: Context) -> dict[str, Any]:
    operation_input = _closed(context, "find_company_by_code")
    code = values.required_text(operation_input.get("code"), "Company code", max_length=50)
    try:
        raw = context.transport.read("contrahents/search", [("code", code)])
    except errors.ExtensionError as exc:
        if exc.code == errors.UPSTREAM_VALIDATION_FAILED:
            # A JSON refusal that is not about the key: no company with this code.
            return {"found": False, "name": None, "warnings": [exc.message]}
        raise
    data = _json(context, raw, "contrahents/search")
    name = data.get("name")
    name = name.strip() if isinstance(name, str) and name.strip() else None
    return {"found": name is not None, "name": name, "warnings": []}


READS: dict[str, Callable[[Context], dict[str, Any]]] = {
    "check_service": check_service,
    "test_connection": test_connection,
    "get_statistics": get_statistics,
    "get_products": get_products,
    "get_product": get_product,
    "get_product_stock": get_product_stock,
    "get_product_cards": get_product_cards,
    "get_product_gallery_link": get_product_gallery_link,
    "get_sales_document": get_sales_document,
    "get_sales_documents": get_sales_documents,
    "get_order_invoice_pdf": get_order_invoice_pdf,
    "get_purchases": get_purchases,
    "get_contrahents": get_contrahents,
    "find_company_by_code": find_company_by_code,
}

__all__ = ["INPUTS", "READS", "paged"]
