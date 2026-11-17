"""XML writes: one XML document in the form field ``data``.

Payments, products, clients and suppliers, document status, document deletion,
document payments, a consignment note and an invoice to another company. Each is
built from closed lists of fields with ElementTree (so every value is escaped), and
only the fields a step is given are written: an empty element could clear a value
Centas already holds.

For these writes the specification documents only HTTP 200 and 401: a refusal of
any other kind, or a batch whose counts do not add up, says nothing about how much
was saved. Counts that do not add up on a confirmed batch are reported in the
warnings with the numbers.
"""

from __future__ import annotations

import base64

# Only builds XML from validated values; nothing is parsed here.
import xml.etree.ElementTree as ElementTree  # nosec B405
from collections.abc import Mapping
from decimal import Decimal
from typing import Any

from . import files, values
from .context import Context
from .documents import MAX_AMOUNT, check_line, id_of, totals, within_limit
from .errors import invalid
from .transport import PAYMENT_TYPES

MAX_ITEMS = 500
MAX_DELETE = 50
MAX_NESTED = 100

Element = ElementTree.Element


def _add(parent: Element, tag: str, value: str | None) -> None:
    if value is not None:
        ElementTree.SubElement(parent, tag).text = value


def xml_document(root: Element) -> str:
    return '<?xml version="1.0" encoding="UTF-8"?>\n' + ElementTree.tostring(
        root, encoding="unicode"
    )


def _money(value: Any, what: str, *, positive: bool = False) -> str:
    amount = (
        values.positive(value, what, places=2)
        if positive
        else values.not_negative(value, what, places=2)
    )
    within_limit(amount, what)
    return values.money(amount)


def _number(value: Any, what: str) -> str:
    amount = values.number(value, what)
    if abs(amount) > MAX_AMOUNT:
        raise invalid(f"{what} is larger than 15 whole digits")
    return values.wire(amount)


def _bool(value: Any, what: str, *, true: str, false: str) -> str | None:
    if value is None:
        return None
    return true if values.flag(value, what) else false


def _date(value: Any, what: str) -> str:
    return values.wire_date(values.iso_date(value, what))


def _opt_date(item: Mapping[str, Any], key: str, what: str) -> str | None:
    return _date(item[key], what) if item.get(key) is not None else None


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


def _items(
    operation_input: Mapping[str, Any],
    name: str,
    allowed: frozenset[str],
    what: str,
    max_items: int = MAX_ITEMS,
) -> list[Mapping[str, Any]]:
    values.closed(operation_input, frozenset({name, "connection_ref"}), "The step input")
    items = values.records(operation_input.get(name), what, max_items=max_items)
    for index, item in enumerate(items, start=1):
        values.closed(item, allowed, f"{what[:-1]} {index}")
    return items


def _counts_warnings(
    sent: int,
    counts: Mapping[str, int | None],
    found_key: str,
    done_keys: tuple[str, ...],
    noun: str,
) -> list[str]:
    if any(counts.get(k) is None for k in (found_key, *done_keys)):
        return [f"Centas WS accepted the {noun} but did not report all its counts"]
    found = counts[found_key] or 0
    done = sum(counts[k] or 0 for k in done_keys)
    warnings = []
    if found != sent:
        warnings.append(f"{sent} {noun} were sent, Centas WS found {found} in them")
    if done != found:
        named = " and ".join(f"{k.split('_')[-1]} {counts[k]}" for k in done_keys)
        warnings.append(
            f"Centas WS reports {named} of the {found} {noun} it found; check in Centas WS "
            "which ones are missing"
        )
    return warnings


def _batch(
    context: Context,
    path: str,
    document: str,
    sent: int,
    found_key: str,
    done_keys: tuple[str, ...],
    noun: str,
    extra: Mapping[str, Any],
) -> dict[str, Any]:
    answer = context.transport.write(path, [("data", document)])
    counts = {k: _count(answer, k) for k in (found_key, *done_keys)}
    return {
        "sent": sent,
        **{k: counts[k] for k in (found_key, *done_keys)},
        **extra,
        "warnings": _counts_warnings(sent, counts, found_key, done_keys, noun),
    }


# -- payments (payments/import) -------------------------------------------------------

PAYMENT_FIELDS: frozenset[str] = frozenset(
    {
        "type",
        "date",
        "amount",
        "document_number",
        "details",
        "payer_name",
        "reference",
        "payer_code",
        "receiver",
        "account",
    }
)
PAYMENT_TYPE_CHOICES = {kind: kind for kind in PAYMENT_TYPES}


def payments_xml(operation_input: Mapping[str, Any]) -> tuple[str, int]:
    items = _items(operation_input, "payments", PAYMENT_FIELDS, "Payments")
    root = Element("root")
    references: list[str] = []
    for index, item in enumerate(items, start=1):
        what = f"Payment {index}"
        kind = values.choice(item.get("type"), f"{what} type", PAYMENT_TYPE_CHOICES)
        if kind is None:
            raise invalid(f"{what} type is required: {', '.join(PAYMENT_TYPES)}")
        reference = values.text(item.get("reference"), f"{what} reference", max_length=100)
        if reference is not None:
            if reference in references:
                raise invalid(
                    f"{what} reference {reference} is already used by another payment of this batch"
                )
            references.append(reference)
        node = ElementTree.SubElement(root, "item")
        _add(node, "PaymentType", kind)
        _add(node, "Date", _date(item.get("date"), f"{what} date"))
        _add(node, "Amount", _money(item.get("amount"), f"{what} amount", positive=True))
        _add(
            node,
            "DocNr",
            values.required_text(
                item.get("document_number"), f"{what} document number", max_length=50
            ),
        )
        _add(node, "RefNr", reference)
        _add(
            node,
            "Details",
            values.required_text(item.get("details"), f"{what} details", max_length=500),
        )
        _add(
            node,
            "RecName",
            values.required_text(item.get("payer_name"), f"{what} payer name", max_length=255),
        )
        _add(
            node, "RecId", values.text(item.get("payer_code"), f"{what} payer code", max_length=50)
        )
        _add(
            node, "Receiver", values.text(item.get("receiver"), f"{what} receiver", max_length=255)
        )
        _add(
            node,
            "ToAccountNumber",
            values.text(item.get("account"), f"{what} account", max_length=50),
        )
    return xml_document(root), len(items)


def send_payments(context: Context) -> dict[str, Any]:
    document, sent = payments_xml(context.operation_input)
    return _batch(
        context,
        "payments/import",
        document,
        sent,
        "payments_found_xml",
        ("payments_created",),
        "payments",
        {},
    )


# -- products (products/import) -------------------------------------------------------

PRODUCT_TEXT: dict[str, tuple[str, int]] = {
    "id": ("id", 20),
    "name": ("pavadinimas", 255),
    "unit": ("matovnt", 20),
    "group1": ("grupe1", 100),
    "group2": ("grupe2", 100),
    "group3": ("grupe3", 100),
    "group4": ("grupe4", 100),
    "barcode": ("barkodas", 50),
    "manufacturer": ("gamintojas", 255),
    "photo": ("Nuotrauka", 500),
    "vat_code": ("mok_kodas", 20),
    "warehouse": ("sandel", 50),
}
PRODUCT_NUMBERS: dict[str, str] = {
    "stock": "likutis",
    "net_weight": "svoris_neto",
    "gross_weight": "svoris_bruto",
    "ordered": "uzsak",
}
PRODUCT_FIELDS: frozenset[str] = frozenset(
    {
        "code",
        "price",
        "cost",
        "vat_percent",
        "description",
        "analog_products",
        "recommended_products",
        "stocks",
        "parameters",
        *PRODUCT_TEXT,
        *PRODUCT_NUMBERS,
    }
)
STOCK_FIELDS: frozenset[str] = frozenset({"warehouse_id", "warehouse_name", "quantity"})
PARAMETER_FIELDS: frozenset[str] = frozenset({"name", "value"})


def _codes(value: Any, what: str) -> str | None:
    """A list of product codes as Centas WS takes it: comma-separated."""
    if value is None:
        return None
    if not isinstance(value, list) or len(value) > MAX_NESTED:
        raise invalid(f"{what} must be a list of at most {MAX_NESTED} product codes")
    codes = [values.required_text(c, f"{what} code", max_length=50) for c in value]
    if any("," in c for c in codes):
        raise invalid(f"{what} codes may not contain commas")
    return ",".join(codes)


def _nested(
    item: Mapping[str, Any],
    key: str,
    container: str,
    child: str,
    allowed: frozenset[str],
    what: str,
) -> Element | None:
    value = item.get(key)
    if value is None:
        return None
    entries = values.records(value, f"{what} {key}", max_items=MAX_NESTED)
    node = Element(container)
    for index, entry in enumerate(entries, start=1):
        label = f"{what} {key[:-1]} {index}"
        values.closed(entry, allowed, label)
        sub = ElementTree.SubElement(node, child)
        if child == "Stock":
            _add(
                sub,
                "WarehouseId",
                values.required_text(
                    entry.get("warehouse_id"), f"{label} warehouse ID", max_length=50
                ),
            )
            _add(
                sub,
                "WarehouseName",
                values.text(entry.get("warehouse_name"), f"{label} warehouse name", max_length=255),
            )
            _add(sub, "Quantity", _number(entry.get("quantity"), f"{label} quantity"))
        else:
            _add(
                sub,
                "Name",
                values.required_text(entry.get("name"), f"{label} name", max_length=255),
            )
            _add(
                sub,
                "Value",
                values.text(entry.get("value"), f"{label} value", max_length=1000) or "",
            )
    return node


def products_xml(operation_input: Mapping[str, Any], token: str) -> tuple[str, list[str]]:
    """The XML to send (the key in every item, as the GitBook documentation and the
    export show it) and the codes, in order."""
    items = _items(operation_input, "products", PRODUCT_FIELDS, "Products")
    root = Element("root")
    codes: list[str] = []
    for index, item in enumerate(items, start=1):
        what = f"Product {index}"
        code = values.required_text(item.get("code"), f"{what} code", max_length=50)
        if code in codes:
            raise invalid(f"{what} code {code} is already used by product {codes.index(code) + 1}")
        codes.append(code)
        node = ElementTree.SubElement(root, "item")
        _add(node, "token", token)
        # UPD (update or create) is the only operation the specification names.
        _add(node, "oper", "UPD")
        _add(node, "kodas", code)
        for key, (field, limit) in PRODUCT_TEXT.items():
            _add(
                node,
                field,
                values.text(item.get(key), f"{what} {key.replace('_', ' ')}", max_length=limit),
            )
        if item.get("price") is not None:
            _add(node, "kaina", values.wire(values.not_negative(item["price"], f"{what} price")))
        if item.get("cost") is not None:
            _add(node, "savikaina", values.wire(values.not_negative(item["cost"], f"{what} cost")))
        if item.get("vat_percent") is not None:
            _add(
                node,
                "pvmtar",
                values.wire(values.percent(item["vat_percent"], f"{what} VAT percent")),
            )
        for key, field in PRODUCT_NUMBERS.items():
            if item.get(key) is not None:
                _add(node, field, _number(item[key], f"{what} {key.replace('_', ' ')}"))
        _add(
            node,
            "aprasymas",
            values.text(
                item.get("description"), f"{what} description", max_length=4000, multi_line=True
            ),
        )
        _add(node, "AnalogProducts", _codes(item.get("analog_products"), f"{what} analog products"))
        _add(
            node,
            "RecommendedProducts",
            _codes(item.get("recommended_products"), f"{what} recommended products"),
        )
        for nested in (
            _nested(item, "stocks", "Stocks", "Stock", STOCK_FIELDS, what),
            _nested(item, "parameters", "ProductParameters", "Parameter", PARAMETER_FIELDS, what),
        ):
            if nested is not None:
                node.append(nested)
    return xml_document(root), codes


def send_products(context: Context) -> dict[str, Any]:
    document, codes = products_xml(context.operation_input, context.connection.token)
    return _batch(
        context,
        "products/import",
        document,
        len(codes),
        "products_found_xml",
        ("products_created", "products_updated"),
        "products",
        {"codes": codes},
    )


# -- clients and suppliers (contrahents/import) ---------------------------------------

CONTRAHENT_TEXT: dict[str, tuple[str, int]] = {
    "id": ("id", 20),
    "company_code": ("imones_kodas", 50),
    "vat_code": ("pvm_kodas", 50),
    "country": ("salis", 100),
    "city": ("miestas", 100),
    "address": ("adresas", 255),
    "email": ("email", 255),
    "phone": ("telefonas", 50),
    "iban": ("iban_nr", 50),
    "telema_id": ("telema_id", 50),
    "edisoft_iln": ("edisoft_iln", 50),
}
CONTRAHENT_FIELDS: frozenset[str] = frozenset(
    {"name", "is_buyer", "is_supplier", "debt", "branches", *CONTRAHENT_TEXT}
)
BRANCH_FIELDS: frozenset[str] = frozenset({"name", "address", "country", "city"})


def contrahents_xml(operation_input: Mapping[str, Any]) -> tuple[str, int, bool]:
    """The XML, the number of contrahents and whether any carries branches."""
    items = _items(operation_input, "contrahents", CONTRAHENT_FIELDS, "Contrahents")
    root = Element("root")
    with_branches = False
    for index, item in enumerate(items, start=1):
        what = f"Contrahent {index}"
        node = ElementTree.SubElement(root, "item")
        _add(node, "oper", "UPD")
        _add(
            node,
            "pavadinimas",
            values.required_text(item.get("name"), f"{what} name", max_length=255),
        )
        for key, (field, limit) in CONTRAHENT_TEXT.items():
            _add(
                node,
                field,
                values.text(item.get(key), f"{what} {key.replace('_', ' ')}", max_length=limit),
            )
        _add(node, "pirkejas", _bool(item.get("is_buyer"), f"{what} is buyer", true="1", false="0"))
        _add(
            node,
            "tiekejas",
            _bool(item.get("is_supplier"), f"{what} is supplier", true="1", false="0"),
        )
        if item.get("debt") is not None:
            _add(node, "skola", values.money(values.number(item["debt"], f"{what} debt", places=2)))
        if item.get("branches") is not None:
            with_branches = True
            branches = values.records(item["branches"], f"{what} branches", max_items=MAX_NESTED)
            container = ElementTree.SubElement(node, "padaliniai")
            for number, branch in enumerate(branches, start=1):
                label = f"{what} branch {number}"
                values.closed(branch, BRANCH_FIELDS, label)
                sub = ElementTree.SubElement(container, "padalinis")
                _add(
                    sub,
                    "pavad",
                    values.required_text(branch.get("name"), f"{label} name", max_length=255),
                )
                _add(
                    sub,
                    "adresas",
                    values.text(branch.get("address"), f"{label} address", max_length=255),
                )
                _add(
                    sub,
                    "salis",
                    values.text(branch.get("country"), f"{label} country", max_length=100),
                )
                _add(
                    sub, "miestas", values.text(branch.get("city"), f"{label} city", max_length=100)
                )
    return xml_document(root), len(items), with_branches


def send_contrahents(context: Context) -> dict[str, Any]:
    document, sent, _ = contrahents_xml(context.operation_input)
    answer = context.transport.write("contrahents/import", [("data", document)])
    keys = ("contrahents_created", "contrahents_updated")
    counts = {k: _count(answer, k) for k in ("contrahents_found_xml", *keys)}
    branches = {
        k: _count(answer, k) for k in ("branches_created", "branches_updated", "branches_deleted")
    }
    warnings = _counts_warnings(sent, counts, "contrahents_found_xml", keys, "contrahents")
    if branches["branches_deleted"]:
        warnings.append(f"Centas WS deleted {branches['branches_deleted']} branches")
    return {"sent": sent, **counts, **branches, "warnings": warnings}


# -- sales document status, deletion and payments --------------------------------------

DOCUMENT_KEY_FIELDS: frozenset[str] = frozenset({"type", "number", "date"})
UPDATE_FIELDS: frozenset[str] = DOCUMENT_KEY_FIELDS | {"downloaded", "paid", "remaining_debt"}
DOCUMENT_PAYMENT_FIELDS: frozenset[str] = DOCUMENT_KEY_FIELDS | {
    "paid_sum",
    "paid_in_full",
    "customer_id",
    "payments",
}
PAYMENT_ROW_FIELDS: frozenset[str] = frozenset({"date", "number", "description", "total"})
_WILDCARDS = set("*%?")


def _document_key(
    node: Element, item: Mapping[str, Any], what: str, token: str
) -> tuple[str, str, str]:
    kind = values.required_text(item.get("type"), f"{what} type", max_length=20)
    number = values.required_text(item.get("number"), f"{what} number", max_length=50)
    if _WILDCARDS & set(number) or _WILDCARDS & set(kind):
        raise invalid(f"{what} must name one document exactly: no *, % or ? in it")
    date = _date(item.get("date"), f"{what} date")
    _add(node, "token", token)
    _add(node, "type", kind)
    _add(node, "number", number)
    _add(node, "date", date)
    return kind, number, date


def update_xml(operation_input: Mapping[str, Any], token: str) -> tuple[str, int]:
    items = _items(operation_input, "documents", UPDATE_FIELDS, "Documents")
    root = Element("root")
    for index, item in enumerate(items, start=1):
        what = f"Document {index}"
        node = ElementTree.SubElement(root, "item")
        _document_key(node, item, what, token)
        downloaded = _bool(item.get("downloaded"), f"{what} downloaded", true="1", false="0")
        paid = _bool(item.get("paid"), f"{what} paid", true="true", false="false")
        debt = (
            _money(item["remaining_debt"], f"{what} remaining debt")
            if item.get("remaining_debt") is not None
            else None
        )
        if downloaded is None and paid is None and debt is None:
            raise invalid(f"{what} needs at least one of downloaded, paid, remaining_debt")
        _add(node, "downloaded", downloaded)
        _add(node, "apmoketa", paid)
        _add(node, "dok_skola", debt)
    return xml_document(root), len(items)


def update_sales_documents(context: Context) -> dict[str, Any]:
    document, sent = update_xml(context.operation_input, context.connection.token)
    return _batch(
        context,
        "documents/update",
        document,
        sent,
        "documents_found",
        ("documents_updated",),
        "documents",
        {},
    )


def delete_xml(operation_input: Mapping[str, Any], token: str) -> tuple[str, int]:
    items = _items(
        operation_input, "documents", DOCUMENT_KEY_FIELDS, "Documents", max_items=MAX_DELETE
    )
    root = Element("root")
    seen: set[tuple[str, str, str]] = set()
    for index, item in enumerate(items, start=1):
        what = f"Document {index}"
        node = ElementTree.SubElement(root, "item")
        key = _document_key(node, item, what, token)
        if key in seen:
            raise invalid(f"{what} is listed twice")
        seen.add(key)
    return xml_document(root), len(items)


def delete_sales_documents(context: Context) -> dict[str, Any]:
    document, sent = delete_xml(context.operation_input, context.connection.token)
    return _batch(
        context,
        "documents/delete",
        document,
        sent,
        "documents_found",
        ("documents_deleted",),
        "documents",
        {},
    )


def document_payments_xml(operation_input: Mapping[str, Any], token: str) -> tuple[str, int]:
    items = _items(operation_input, "documents", DOCUMENT_PAYMENT_FIELDS, "Documents")
    root = Element("root")
    for index, item in enumerate(items, start=1):
        what = f"Document {index}"
        node = ElementTree.SubElement(root, "item")
        _document_key(node, item, what, token)
        _add(node, "paid_sum", _money(item.get("paid_sum"), f"{what} paid sum"))
        _add(
            node,
            "paid_full",
            _bool(item.get("paid_in_full"), f"{what} paid in full", true="1", false="0"),
        )
        _add(
            node,
            "customerId",
            values.text(item.get("customer_id"), f"{what} customer ID", max_length=50),
        )
        rows = values.records(item.get("payments"), f"{what} payments", max_items=MAX_NESTED)
        for number, row in enumerate(rows, start=1):
            label = f"{what} payment {number}"
            values.closed(row, PAYMENT_ROW_FIELDS, label)
            sub = ElementTree.SubElement(node, "payment")
            _add(sub, "date", _date(row.get("date"), f"{label} date"))
            _add(
                sub,
                "number",
                values.required_text(row.get("number"), f"{label} number", max_length=50),
            )
            _add(
                sub,
                "description",
                values.text(row.get("description"), f"{label} description", max_length=500),
            )
            _add(sub, "total", _money(row.get("total"), f"{label} total", positive=True))
    return xml_document(root), len(items)


def record_document_payments(context: Context) -> dict[str, Any]:
    document, sent = document_payments_xml(context.operation_input, context.connection.token)
    return _batch(
        context,
        "documents/payments/create",
        document,
        sent,
        "documents_payments_found_xml",
        ("documents_payments_created",),
        "document payments",
        {},
    )


# -- consignment note (consignments/import) -------------------------------------------

CONSIGNMENT_INPUTS: frozenset[str] = frozenset(
    {
        "document_uid",
        "document_number",
        "document_date",
        "estimated_arrival",
        "consignee_name",
        "consignee_code",
        "lines",
    }
)
CONSIGNMENT_LINE_FIELDS: frozenset[str] = frozenset({"description", "unit", "quantity"})


def consignment_xml(operation_input: Mapping[str, Any]) -> tuple[str, int]:
    values.closed(operation_input, CONSIGNMENT_INPUTS | {"connection_ref"}, "The step input")
    root = Element("root")
    _add(
        root,
        "DocumentUID",
        values.required_text(operation_input.get("document_uid"), "Document UID", max_length=100),
    )
    _add(
        root,
        "DocumentNumber",
        values.required_text(
            operation_input.get("document_number"), "Document number", max_length=50
        ),
    )
    _add(root, "DocumentDate", _date(operation_input.get("document_date"), "Document date"))
    _add(
        root,
        "EstimatedTimeOfArrival",
        _opt_date(operation_input, "estimated_arrival", "Estimated arrival"),
    )
    _add(
        root,
        "ConsigneeName",
        values.required_text(
            operation_input.get("consignee_name"), "Consignee name", max_length=255
        ),
    )
    _add(
        root,
        "ConsigneeRegistrationNumber",
        values.text(operation_input.get("consignee_code"), "Consignee code", max_length=50),
    )
    lines = values.records(operation_input.get("lines"), "Lines", max_items=MAX_ITEMS)
    for index, line in enumerate(lines, start=1):
        what = f"Line {index}"
        values.closed(line, CONSIGNMENT_LINE_FIELDS, what)
        node = ElementTree.SubElement(root, "eilute")
        _add(
            node,
            "ProductDescription",
            values.required_text(line.get("description"), f"{what} description", max_length=255),
        )
        _add(
            node,
            "UnitOfMeasure",
            values.required_text(line.get("unit"), f"{what} unit", max_length=20),
        )
        _add(
            node, "Quantity", values.wire(values.positive(line.get("quantity"), f"{what} quantity"))
        )
    return xml_document(root), len(lines)


def send_consignment(context: Context) -> dict[str, Any]:
    document, sent = consignment_xml(context.operation_input)
    answer = context.transport.write("consignments/import", [("data", document)])
    created = _count(answer, "consignment_rows_created")
    warnings = []
    if created is None:
        warnings.append("Centas WS accepted the consignment but did not report its rows")
    elif created != sent:
        warnings.append(f"{sent} lines were sent, Centas WS created {created}")
    return {"lines_sent": sent, "consignment_rows_created": created, "warnings": warnings}


# -- invoice to another company (purchase/import) -------------------------------------

RECEIVER_TEXT: dict[str, tuple[str, int]] = {
    "receiver_company_code": ("im_kodas", 50),
    "receiver_vat_code": ("pvm_kodas", 50),
    "receiver_name": ("kontrah", 255),
    "receiver_email": ("email", 255),
    "receiver_country": ("salis", 100),
    "receiver_city": ("miestas", 100),
    "receiver_address": ("adresas", 255),
    "receiver_telema_id": ("telema_id", 50),
    "receiver_edisoft_iln": ("edisoft_iln", 50),
}
INVOICE_LINE_TEXT: dict[str, tuple[str, int]] = {
    "kind": ("prek_pasl", 5),
    "ean": ("ean", 20),
    "vat_code": ("mok_kodas", 20),
}
_CORE_LINE: frozenset[str] = frozenset({"code", "name", "unit", "quantity", "price", "vat_percent"})
INVOICE_LINE_FIELDS: frozenset[str] = frozenset(
    {"code", "name", "unit", "quantity", "price", "vat_percent", *INVOICE_LINE_TEXT}
)
COMPANY_INVOICE_INPUTS: frozenset[str] = frozenset(
    {
        "send_email",
        "number",
        "date",
        "due_date",
        "seller_name",
        "document_type",
        "country_code",
        "paid",
        "remaining_debt",
        "pdf_file",
        "pdf_name",
        "lines",
        "net_total",
        "vat_total",
        "total",
        *RECEIVER_TEXT,
    }
)


def company_invoice_xml(
    operation_input: Mapping[str, Any], token: str, pdf: bytes | None
) -> tuple[str, dict[str, Any]]:
    values.closed(operation_input, COMPANY_INVOICE_INPUTS | {"connection_ref"}, "The step input")
    root = Element("root")
    sender = ElementTree.SubElement(root, "siuntejas")
    _add(sender, "token", token)
    receiver = ElementTree.SubElement(root, "gavejas")
    if not (
        operation_input.get("receiver_company_code") or operation_input.get("receiver_vat_code")
    ):
        raise invalid("Give the receiver's company code or VAT code")
    for key, (field, limit) in RECEIVER_TEXT.items():
        _add(
            receiver,
            field,
            values.text(
                operation_input.get(key), key.replace("_", " ").capitalize(), max_length=limit
            ),
        )
    send_email = values.flag(operation_input.get("send_email"), "Send e-mail")
    _add(receiver, "send_email", "true" if send_email else "false")
    items = values.records(operation_input.get("lines"), "Lines", max_items=MAX_ITEMS)
    checked = []
    for index, item in enumerate(items, start=1):
        values.closed(item, INVOICE_LINE_FIELDS, f"Line {index}")
        core = {k: v for k, v in item.items() if k not in INVOICE_LINE_TEXT}
        checked.append((check_line(core, index, _CORE_LINE, names_required=False), item))
    net, vat, total = totals(operation_input, [line for line, _ in checked])
    document = ElementTree.SubElement(root, "dokumentas")
    number = values.required_text(operation_input.get("number"), "Invoice number", max_length=50)
    _add(document, "dok_num", number)
    _add(document, "data", _date(operation_input.get("date"), "Date"))
    _add(document, "dok_suma", values.money(total))
    _add(document, "pvm_suma", values.money(vat))
    _add(document, "bepvm_suma", values.money(net))
    _add(document, "apmok_iki", _opt_date(operation_input, "due_date", "Due date"))
    _add(
        document,
        "kontrah",
        values.text(operation_input.get("seller_name"), "Seller name", max_length=255),
    )
    _add(
        document,
        "DocType",
        values.text(operation_input.get("document_type"), "Document type", max_length=20),
    )
    _add(
        document,
        "salis_kodas",
        values.text(operation_input.get("country_code"), "Country code", max_length=2),
    )
    _add(
        document, "apmoketa", _bool(operation_input.get("paid"), "Paid", true="true", false="false")
    )
    if operation_input.get("remaining_debt") is not None:
        _add(document, "dok_skola", _money(operation_input["remaining_debt"], "Remaining debt"))
    if pdf is not None:
        name = values.text(operation_input.get("pdf_name"), "PDF name", max_length=100) or (
            f"{number}.pdf"
        )
        _add(document, "pdf_name", name)
        _add(document, "pdf_base64", base64.b64encode(pdf).decode("ascii"))
    for line, item in checked:
        row = ElementTree.SubElement(document, "eilute")
        _add(row, "kodas", line.wire["kodas"])
        for key, (field, limit) in INVOICE_LINE_TEXT.items():
            if key == "vat_code":
                continue
            _add(row, field, values.text(item.get(key), f"Line {key}", max_length=limit))
        for wire_key in ("pavadinimas", "matovnt", "kiekis", "kaina", "pvmtar"):
            _add(row, wire_key, line.wire.get(wire_key))
        _add(row, "mok_kodas", values.text(item.get("vat_code"), "Line VAT code", max_length=20))
    sent = {
        "number": number,
        "net_total": values.money(net),
        "vat_total": values.money(vat),
        "total": values.money(total),
        "email_requested": send_email,
    }
    return xml_document(root), sent


def send_invoice_to_company(context: Context) -> dict[str, Any]:
    operation_input = context.operation_input
    company_invoice_xml(operation_input, "validation-only", None)  # every check first
    pdf = None
    if operation_input.get("pdf_file") is not None:
        pdf = files.read_upload(
            context, files.artifact_handle(operation_input["pdf_file"], "PDF file")
        )
    document, sent = company_invoice_xml(operation_input, context.connection.token, pdf)
    # The key travels inside the XML (siuntejas), as the specification shows.
    answer = context.transport.write("purchase/import", [("data", document)], token_field=False)
    email_sent = answer.get("email_sent")
    counts = {key: _count(answer, key) for key in COMPANY_INVOICE_COUNTS}
    lines = len(operation_input.get("lines") or [])
    return {
        **sent,
        **counts,
        "email_sent": email_sent if isinstance(email_sent, bool) else None,
        "warnings": _company_invoice_warnings(lines, counts, sent["email_requested"], email_sent),
    }


#: The specification's counts of purchase/import: "Number of purchase rows created" (at
#: the receiver) and "Number of document rows created" (the sender's sales document).
COMPANY_INVOICE_COUNTS = {
    "purchase_rows_created": "purchase rows (the receiver's purchase)",
    "document_rows_created": "document rows (your sales document)",
}


def _company_invoice_warnings(
    lines: int, counts: Mapping[str, int | None], email_requested: Any, email_sent: Any
) -> list[str]:
    """What the answer does not confirm. The specification does not say that a count
    equals the lines sent, so a difference is said as not confirmed, not as an error;
    the document is never sent again by this step."""
    warnings = []
    for key, what in COMPANY_INVOICE_COUNTS.items():
        count = counts.get(key)
        if count is None:
            warnings.append(
                f"Centas WS did not report {key}: that {what} were created for the {lines} "
                "lines sent is not confirmed; check the document in Centas"
            )
        elif count != lines:
            warnings.append(
                f"Centas WS reports {count} {what} created for {lines} lines sent: that every "
                "line arrived is not confirmed; check the document in Centas before sending "
                "it again"
            )
    if email_requested is True and email_sent is not True:
        said = "false" if email_sent is False else "nothing about it"
        warnings.append(
            f"An e-mail to the receiver was asked for, but Centas WS reports {said} for "
            "email_sent: the receiver may not have been notified"
        )
    return warnings


__all__ = [
    "CONSIGNMENT_INPUTS",
    "COMPANY_INVOICE_INPUTS",
    "MAX_DELETE",
    "company_invoice_xml",
    "consignment_xml",
    "contrahents_xml",
    "delete_xml",
    "document_payments_xml",
    "id_of",
    "payments_xml",
    "products_xml",
    "update_xml",
]
