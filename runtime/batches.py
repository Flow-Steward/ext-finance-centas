"""Send payments or products to Centas WS: one XML document in the form field ``data``.

Both are batches: Centas WS answers with how many records it found in the XML and
how many it created (and, for products, updated). A batch that Centas WS refuses
may have been saved in part, so a refusal leaves the outcome unknown
(transport); an accepted batch whose counts do not add up is reported in the
warnings with the numbers.

Only the fields a step is given are written: an empty element could clear a value
Centas already holds.
"""

from __future__ import annotations

# Only builds XML from validated values; nothing is parsed here.
import xml.etree.ElementTree as ElementTree  # nosec B405
from collections.abc import Mapping
from decimal import Decimal
from typing import Any

from . import errors, values
from .context import Context
from .errors import ExtensionError, invalid
from .exports import payments_of
from .transport import DeadlineReached

MAX_PAYMENTS = 500
MAX_PRODUCTS = 500
MAX_STOCKS = 50
MAX_PARAMETERS = 100

PAYMENTS_INPUTS: frozenset[str] = frozenset({"payments"})
PAYMENT_FIELDS: frozenset[str] = frozenset(
    {
        "type",
        "date",
        "amount",
        "document_number",
        "reference",
        "details",
        "payer_name",
        "payer_code",
        "account",
    }
)
PRODUCTS_INPUTS: frozenset[str] = frozenset({"products"})
PRODUCT_FIELDS: frozenset[str] = frozenset(
    {
        "code",
        "id",
        "name",
        "unit",
        "price",
        "vat_percent",
        "stock",
        "group1",
        "group2",
        "group3",
        "barcode",
        "description",
        "photo",
        "stocks",
        "parameters",
    }
)
STOCK_FIELDS: frozenset[str] = frozenset({"warehouse_id", "warehouse_name", "quantity"})
PARAMETER_FIELDS: frozenset[str] = frozenset({"name", "value"})

_PAYMENT_TYPE_LENGTH = 30


def _add(parent: ElementTree.Element, tag: str, value: str | None) -> None:
    if value is not None:
        ElementTree.SubElement(parent, tag).text = value


def xml_document(root: ElementTree.Element) -> str:
    body = ElementTree.tostring(root, encoding="unicode")
    return '<?xml version="1.0" encoding="UTF-8"?>\n' + body


# -- payments -------------------------------------------------------------------


def payments_xml(operation_input: Mapping[str, Any]) -> tuple[str, list[str]]:
    """The XML to send and the references, in order."""
    values.closed(operation_input, PAYMENTS_INPUTS | {"connection_ref"}, "The step input")
    items = values.records(operation_input.get("payments"), "Payments", max_items=MAX_PAYMENTS)
    root = ElementTree.Element("root")
    references: list[str] = []
    for index, item in enumerate(items, start=1):
        what = f"Payment {index}"
        values.closed(item, PAYMENT_FIELDS, what)
        kind = values.required_text(
            item.get("type"), f"{what} type", max_length=_PAYMENT_TYPE_LENGTH
        )
        if not kind.isascii() or not kind.isalnum():
            raise invalid(f"{what} type must be a Centas payment type code such as BankDeb")
        date = values.iso_date(item.get("date"), f"{what} date")
        amount = values.positive(item.get("amount"), f"{what} amount", places=2)
        reference = values.required_text(item.get("reference"), f"{what} reference", max_length=100)
        if reference in references:
            raise invalid(
                f"{what} reference {reference} is already used by payment "
                f"{references.index(reference) + 1}; each payment needs its own reference"
            )
        references.append(reference)
        node = ElementTree.SubElement(root, "Payment")
        _add(node, "PaymentType", kind)
        _add(node, "Date", values.wire_date(date))
        _add(node, "Amount", values.money(amount))
        _add(
            node,
            "DocNr",
            values.text(item.get("document_number"), f"{what} document number", max_length=50),
        )
        _add(node, "RefNr", reference)
        _add(node, "Details", values.text(item.get("details"), f"{what} details", max_length=500))
        _add(
            node,
            "RecName",
            values.text(item.get("payer_name"), f"{what} payer name", max_length=255),
        )
        _add(
            node, "RecId", values.text(item.get("payer_code"), f"{what} payer code", max_length=50)
        )
        _add(
            node,
            "ToAccountNumber",
            values.text(item.get("account"), f"{what} account", max_length=50),
        )
    return xml_document(root), references


def _check_references(context: Context, references: list[str]) -> None:
    """Refuse the batch when Centas WS's payment export already holds one of its
    references, or when the export cannot be read to check: nothing is sent then.

    Whatever the export holds, a reference found in it means Centas WS already knows
    that payment.
    """
    try:
        raw = context.transport.export("payments/export")
        known = {
            str(p.get("reference"))
            for p in payments_of(raw, context.transport)[0]
            if p.get("reference")
        }
    except DeadlineReached:
        raise errors.no_effect(
            errors.TIMEOUT,
            "No payments were sent: the step ran out of time reading Centas WS's payment "
            "export, so it could not check them for repeats",
        ) from None
    except ExtensionError as exc:
        raise errors.no_effect(
            exc.code,
            "No payments were sent: Centas WS's payment export could not be read to check "
            f"them for repeats ({exc.message})",
            failure_class=exc.failure_class,
            retryable=exc.retryable,
            http_status=exc.http_status,
        ) from None
    repeated = [r for r in references if r in known]
    if repeated:
        shown = ", ".join(repeated[:20]) + (" …" if len(repeated) > 20 else "")
        raise errors.no_effect(
            errors.CONFLICT,
            f"No payments were sent: Centas WS's payment export already lists {len(repeated)} "
            f"of their references ({shown})",
        )


def _count(answer: Mapping[str, Any], key: str) -> int | None:
    value = answer.get(key)
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, Decimal) and value == value.to_integral_value():
        return int(value)
    if isinstance(value, str) and value.strip().isdigit():
        return int(value.strip())
    return None


def send_payments(context: Context) -> dict[str, Any]:
    document, references = payments_xml(context.operation_input)
    _check_references(context, references)
    warnings: list[str] = []
    answer = context.transport.write("payments/import", [("data", document)])
    found = _count(answer, "payments_found_xml")
    created = _count(answer, "payments_created")
    if found is None or created is None:
        warnings.append("Centas WS accepted the payments but did not report how many it created")
    else:
        if found != len(references):
            warnings.append(
                f"{len(references)} payments were sent, Centas WS found {found} in them"
            )
        if created != found:
            warnings.append(
                f"Centas WS created {created} of the {found} payments it found; check in Centas "
                "which ones are missing"
            )
    return {
        "sent": len(references),
        "found": found,
        "created": created,
        "references": references,
        "warnings": warnings,
    }


# -- products -------------------------------------------------------------------


def _stocks(value: Any, what: str) -> ElementTree.Element | None:
    if value is None:
        return None
    items = values.records(value, f"{what} stocks", max_items=MAX_STOCKS)
    node = ElementTree.Element("Stocks")
    for index, item in enumerate(items, start=1):
        label = f"{what} stock {index}"
        values.closed(item, STOCK_FIELDS, label)
        stock = ElementTree.SubElement(node, "Stock")
        _add(
            stock,
            "WarehouseId",
            values.text(
                item.get("warehouse_id"), f"{label} warehouse ID", max_length=50, required=True
            ),
        )
        _add(
            stock,
            "WarehouseName",
            values.text(item.get("warehouse_name"), f"{label} warehouse name", max_length=255),
        )
        _add(
            stock, "Quantity", values.wire(values.number(item.get("quantity"), f"{label} quantity"))
        )
    return node


def _parameters(value: Any, what: str) -> ElementTree.Element | None:
    if value is None:
        return None
    items = values.records(value, f"{what} parameters", max_items=MAX_PARAMETERS)
    node = ElementTree.Element("ProductParameters")
    for index, item in enumerate(items, start=1):
        label = f"{what} parameter {index}"
        values.closed(item, PARAMETER_FIELDS, label)
        parameter = ElementTree.SubElement(node, "Parameter")
        _add(
            parameter,
            "Name",
            values.text(item.get("name"), f"{label} name", max_length=255, required=True),
        )
        _add(
            parameter,
            "Value",
            values.text(item.get("value"), f"{label} value", max_length=1000) or "",
        )
    return node


def products_xml(operation_input: Mapping[str, Any], token: str) -> tuple[str, list[str]]:
    """The XML to send (the key in every item, as documented) and the codes, in order."""
    values.closed(operation_input, PRODUCTS_INPUTS | {"connection_ref"}, "The step input")
    items = values.records(operation_input.get("products"), "Products", max_items=MAX_PRODUCTS)
    root = ElementTree.Element("root")
    codes: list[str] = []
    for index, item in enumerate(items, start=1):
        what = f"Product {index}"
        values.closed(item, PRODUCT_FIELDS, what)
        code = values.required_text(item.get("code"), f"{what} code", max_length=50)
        if code in codes:
            raise invalid(f"{what} code {code} is already used by product {codes.index(code) + 1}")
        codes.append(code)
        node = ElementTree.SubElement(root, "item")
        _add(node, "token", token)
        # UPD is the only operation the documentation shows.
        _add(node, "oper", "UPD")
        _add(node, "id", values.text(item.get("id"), f"{what} ID", max_length=50))
        _add(node, "kodas", code)
        _add(node, "pavadinimas", values.text(item.get("name"), f"{what} name", max_length=255))
        _add(node, "matovnt", values.text(item.get("unit"), f"{what} unit", max_length=20))
        if item.get("price") is not None:
            _add(node, "kaina", values.wire(values.not_negative(item["price"], f"{what} price")))
        if item.get("vat_percent") is not None:
            _add(
                node,
                "pvmtar",
                values.wire(values.percent(item["vat_percent"], f"{what} VAT percent")),
            )
        if item.get("stock") is not None:
            _add(node, "likutis", values.wire(values.number(item["stock"], f"{what} stock")))
        for n in (1, 2, 3):
            _add(
                node,
                f"grupe{n}",
                values.text(item.get(f"group{n}"), f"{what} group {n}", max_length=100),
            )
        _add(node, "barkodas", values.text(item.get("barcode"), f"{what} barcode", max_length=50))
        _add(
            node,
            "aprasymas",
            values.text(
                item.get("description"), f"{what} description", max_length=2000, multi_line=True
            ),
        )
        _add(node, "Nuotrauka", values.text(item.get("photo"), f"{what} photo", max_length=500))
        for child in (_stocks(item.get("stocks"), what), _parameters(item.get("parameters"), what)):
            if child is not None:
                node.append(child)
    return xml_document(root), codes


def send_products(context: Context) -> dict[str, Any]:
    document, codes = products_xml(context.operation_input, context.connection.token)
    answer = context.transport.write("products/import", [("data", document)])
    found = _count(answer, "products_found_xml")
    created = _count(answer, "products_created")
    updated = _count(answer, "products_updated")
    warnings: list[str] = []
    if found is None or created is None or updated is None:
        warnings.append(
            "Centas WS accepted the products but did not report how many it created and updated"
        )
    else:
        if found != len(codes):
            warnings.append(f"{len(codes)} products were sent, Centas WS found {found} in them")
        if created + updated != found:
            warnings.append(
                f"Centas WS created {created} and updated {updated} of the {found} products it "
                "found; check in Centas which ones are missing"
            )
    return {
        "sent": len(codes),
        "found": found,
        "created": created,
        "updated": updated,
        "codes": codes,
        "warnings": warnings,
    }


__all__ = [
    "MAX_PAYMENTS",
    "MAX_PRODUCTS",
    "PAYMENTS_INPUTS",
    "PRODUCTS_INPUTS",
    "errors",
    "payments_xml",
    "products_xml",
    "send_payments",
    "send_products",
]
