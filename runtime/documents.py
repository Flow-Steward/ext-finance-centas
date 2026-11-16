"""Send a sales invoice, a purchase invoice or a customer order to Centas WS.

Each is one POST of form fields, its lines as a JSON array in ``rows``. What
Centas WS receives waits in its exchange until an accountant imports it in the
Centas program (menu "ws.centas.lt"); the step's success means "received by
Centas WS", which is what its outputs say.

Totals: Centas lets each company choose how VAT is summed ("PVM sumos
skaičiavimas": from the document total or line by line), so the rounding Centas
applies is not known here. When the step is given the totals, they are checked
against the lines within ``tolerance`` (one cent per line) and sent as given;
total must equal net + VAT exactly. When it is not given them, they are computed
by one rule — each line rounded to cents, its VAT rounded to cents, summed — and
the values sent are returned.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from decimal import Decimal, localcontext
from typing import Any

from . import errors, values
from .context import Context
from .errors import invalid

MAX_LINES = 500

EU_TYPES = {"local": "0", "eu": "1", "non_eu": "2"}

#: Input field name -> (wire name, max length) of the optional text fields.
_SALES_TEXT: dict[str, tuple[str, int]] = {
    "transaction_id": ("trans_id", 50),
    "buyer_code": ("kl_kodas", 50),
    "buyer_company_code": ("im_kodas", 50),
    "buyer_vat_code": ("pvm_kodas", 50),
    "buyer_email": ("email", 255),
    "buyer_city": ("miestas", 100),
    "buyer_address": ("adresas", 255),
    "buyer_country": ("salis", 100),
    "buyer_group": ("grupe", 50),
    "receivable_account": ("sask_pirkskol", 20),
    "project": ("projektas", 100),
    "order_number": ("uzsaknr", 50),
    "operation_description": ("oper_apras", 255),
    "issued_by": ("israse_asmuo", 100),
    "issued_by_position": ("israse_pareigos", 100),
    "intrastat_transport": ("intrs_transprusis", 20),
    "intrastat_delivery_terms": ("intrs_pristsal", 20),
    "intrastat_transaction": ("intrs_sandoris", 20),
    "intrastat_county": ("intrs_apskritis", 20),
    "intrastat_eu_country": ("intrs_eusalis", 20),
}
#: Accounts the documentation types as numbers: digits only.
_SALES_ACCOUNTS: dict[str, str] = {
    "vat_payable_account": "sask_moketpvm",
    "income_account": "sask_pajamos",
}
_TOTALS = ("net_total", "vat_total", "total")

SALES_INPUTS: frozenset[str] = frozenset(
    {
        "number",
        "date",
        "due_date",
        "buyer_name",
        "buyer_eu_type",
        "note",
        "cost",
        "lines",
        *_SALES_TEXT,
        *_SALES_ACCOUNTS,
        *_TOTALS,
    }
)
SALES_LINE_FIELDS: frozenset[str] = frozenset(
    {
        "code",
        "name",
        "unit",
        "quantity",
        "price",
        "vat_percent",
        "vat_code",
        "income_account",
        "project",
    }
)

PURCHASE_INPUTS: frozenset[str] = frozenset({"seller_name", "number", "date", "lines", *_TOTALS})
PURCHASE_LINE_FIELDS: frozenset[str] = frozenset(
    {"code", "name", "unit", "quantity", "price", "vat_percent", "vat_code", "project"}
)

_ORDER_TEXT: dict[str, tuple[str, int]] = {
    "customer_city": ("miestas", 100),
    "customer_address": ("adresas", 255),
    "customer_phone": ("tel", 50),
    "customer_company_code": ("im_kodas", 50),
    "customer_vat_code": ("pvm_kodas", 50),
    "customer_email": ("email", 255),
    "postal_code": ("pasto_kodas", 20),
    "receivable_account": ("pirk_skolsask", 20),
    "warehouse": ("sandelis", 50),
}
_ORDER_DATES: dict[str, str] = {
    "execution_date": "vykd_data",
    "delivery_date": "pristat_data",
    "payment_date": "apmok_data",
    "arrival_date": "atvyk_data",
    "departure_date": "isvyk_data",
}
ORDER_INPUTS: frozenset[str] = frozenset(
    {
        "number",
        "date",
        "customer_name",
        "customer_note",
        "lines",
        *_ORDER_TEXT,
        *_ORDER_DATES,
        *_TOTALS,
    }
)
ORDER_LINE_FIELDS: frozenset[str] = frozenset(
    {"code", "supplier_code", "name", "unit", "quantity", "price", "vat_percent"}
)


# -- lines and totals ---------------------------------------------------------


class Line:
    """One validated line: its wire fields and its net amount and VAT in cents."""

    def __init__(self, wire: dict[str, str], net: Decimal, vat: Decimal) -> None:
        self.wire = wire
        self.net = net
        self.vat = vat


def _line(
    item: Mapping[str, Any], index: int, allowed: frozenset[str], *, order: bool = False
) -> Line:
    what = f"Line {index}"
    values.closed(item, allowed, what)
    code = values.text(item.get("code"), f"{what} code", max_length=50, required=True)
    quantity = values.positive(item.get("quantity"), f"{what} quantity")
    price = values.not_negative(item.get("price"), f"{what} price")
    rate = values.percent(item.get("vat_percent"), f"{what} VAT percent")
    with localcontext() as ctx:
        ctx.prec = 60
        net = values.cents(quantity * price)
        vat = values.cents(net * rate / 100)
    wire: dict[str, str] = {"kodas": str(code)}
    if order:
        supplier = values.text(item.get("supplier_code"), f"{what} supplier code", max_length=50)
        if supplier:
            wire["t_kodas"] = supplier
    name = values.text(item.get("name"), f"{what} name", max_length=255)
    unit = values.text(item.get("unit"), f"{what} unit", max_length=20)
    if name:
        wire["pavadinimas"] = name
    if unit:
        wire["matovnt"] = unit
    wire["kiekis"] = values.wire(quantity)
    wire["kaina"] = values.wire(price)
    if order:
        # The documentation names the order line's VAT rate pvm_tar in its table and
        # pvmtar in its example; both are sent with the same value.
        wire["pvm_tar"] = values.wire(rate)
        wire["pvmtar"] = values.wire(rate)
    else:
        wire["pvmtar"] = values.wire(rate)
        vat_code = values.text(item.get("vat_code"), f"{what} VAT code", max_length=20)
        if vat_code:
            wire["Mok_kodas"] = vat_code
        if "income_account" in allowed:
            account = values.text(
                item.get("income_account"), f"{what} income account", max_length=20
            )
            if account:
                wire["sask_pajamos"] = account
        project = values.text(item.get("project"), f"{what} project", max_length=100)
        if project:
            wire["projektas"] = project
    return Line(wire, net, vat)


def lines_of(value: Any, allowed: frozenset[str], *, order: bool = False) -> list[Line]:
    items = values.records(value, "Lines", max_items=MAX_LINES)
    return [_line(item, i, allowed, order=order) for i, item in enumerate(items, start=1)]


def tolerance(count: int) -> Decimal:
    """How far given totals may differ from the lines: one cent per line."""
    return values.CENT * count


def totals(
    operation_input: Mapping[str, Any], lines: list[Line]
) -> tuple[Decimal, Decimal, Decimal]:
    """(net, VAT, total) to send: given and checked, or computed by one rule."""
    computed_net = sum((line.net for line in lines), Decimal("0.00"))
    computed_vat = sum((line.vat for line in lines), Decimal("0.00"))
    given = {k: operation_input.get(k) for k in _TOTALS if operation_input.get(k) is not None}
    if not given:
        return computed_net, computed_vat, computed_net + computed_vat
    if "net_total" not in given or "vat_total" not in given:
        raise invalid(
            "Give both the net total and the VAT total (and optionally the total), or none of "
            "them to have them computed from the lines"
        )
    net = values.not_negative(given["net_total"], "Net total", places=2)
    vat = values.not_negative(given["vat_total"], "VAT total", places=2)
    total = net + vat
    if "total" in given:
        stated = values.not_negative(given["total"], "Total", places=2)
        if stated != total:
            raise errors.no_effect(
                errors.CONFLICT,
                f"The total {values.money(stated)} is not the net total plus VAT "
                f"({values.money(net)} + {values.money(vat)} = {values.money(total)}); "
                "nothing was sent",
            )
    allowed = tolerance(len(lines))
    if abs(net - computed_net) > allowed:
        raise errors.no_effect(
            errors.CONFLICT,
            f"The net total {values.money(net)} differs from the lines' "
            f"{values.money(computed_net)} by more than {values.money(allowed)} (one cent per "
            "line); nothing was sent",
        )
    if abs(vat - computed_vat) > allowed:
        raise errors.no_effect(
            errors.CONFLICT,
            f"The VAT total {values.money(vat)} differs from the lines' "
            f"{values.money(computed_vat)} by more than {values.money(allowed)} (one cent per "
            "line); nothing was sent",
        )
    return net, vat, total


def rows_json(lines: list[Line]) -> str:
    return json.dumps([line.wire for line in lines], ensure_ascii=False, separators=(",", ":"))


def _texts(
    operation_input: Mapping[str, Any], spec: Mapping[str, tuple[str, int]]
) -> list[tuple[str, str]]:
    form: list[tuple[str, str]] = []
    for name, (wire_name, limit) in spec.items():
        value = values.text(
            operation_input.get(name), name.replace("_", " ").capitalize(), max_length=limit
        )
        if value:
            form.append((wire_name, value))
    return form


def _account(value: Any, what: str) -> str | None:
    account = values.text(value, what, max_length=20)
    if account is not None and not account.isdigit():
        raise invalid(f"{what} must be digits (an account number)")
    return account


def _sent(number: str, net: Decimal, vat: Decimal, total: Decimal) -> dict[str, Any]:
    return {
        "number": number,
        "net_total": values.money(net),
        "vat_total": values.money(vat),
        "total": values.money(total),
    }


# -- the three documents -----------------------------------------------------


def sales_invoice_form(
    operation_input: Mapping[str, Any],
) -> tuple[list[tuple[str, str]], dict[str, Any]]:
    values.closed(operation_input, SALES_INPUTS | {"connection_ref"}, "The step input")
    number = values.text(operation_input.get("number"), "Number", max_length=50)
    transaction = values.text(
        operation_input.get("transaction_id"), "Transaction ID", max_length=50
    )
    if number is None or number.lower() == "auto":
        if not transaction:
            raise invalid(
                "Give the invoice number, or leave it empty and give the transaction ID so "
                "Centas numbers it from its free invoice forms"
            )
        number = "auto"
    date = values.iso_date(operation_input.get("date"), "Date")
    buyer = values.text(
        operation_input.get("buyer_name"), "Buyer name", max_length=255, required=True
    )
    lines = lines_of(operation_input.get("lines"), SALES_LINE_FIELDS)
    net, vat, total = totals(operation_input, lines)
    form: list[tuple[str, str]] = [
        ("dok_num", number),
        ("data", values.wire_date(date)),
        ("pirkejas", str(buyer)),
        ("bepvm_suma", values.money(net)),
        ("pvm_suma", values.money(vat)),
        ("dok_suma", values.money(total)),
    ]
    if operation_input.get("due_date") is not None:
        form.append(
            (
                "apmok_iki",
                values.wire_date(values.iso_date(operation_input["due_date"], "Due date")),
            )
        )
    eu_type = values.choice(operation_input.get("buyer_eu_type"), "Buyer EU type", EU_TYPES)
    if eu_type is not None:
        form.append(("estipas", eu_type))
    form += _texts(operation_input, _SALES_TEXT)
    for name, wire_name in _SALES_ACCOUNTS.items():
        account = _account(operation_input.get(name), name.replace("_", " ").capitalize())
        if account:
            form.append((wire_name, account))
    if operation_input.get("cost") is not None:
        form.append(
            (
                "savikaina",
                values.money(values.not_negative(operation_input["cost"], "Cost", places=2)),
            )
        )
    note = values.text(operation_input.get("note"), "Note", max_length=1000, multi_line=True)
    if note:
        form.append(("pastaba", note))
    form.append(("rows", rows_json(lines)))
    return form, _sent(number, net, vat, total)


def purchase_invoice_form(
    operation_input: Mapping[str, Any],
) -> tuple[list[tuple[str, str]], dict[str, Any]]:
    values.closed(operation_input, PURCHASE_INPUTS | {"connection_ref"}, "The step input")
    seller = values.text(
        operation_input.get("seller_name"), "Seller name", max_length=255, required=True
    )
    number = values.text(operation_input.get("number"), "Number", max_length=50, required=True)
    date = values.iso_date(operation_input.get("date"), "Date")
    lines = lines_of(operation_input.get("lines"), PURCHASE_LINE_FIELDS)
    net, vat, total = totals(operation_input, lines)
    form = [
        ("kontrah", str(seller)),
        ("data", values.wire_date(date)),
        ("dok_suma", values.money(total)),
        ("dok_num", str(number)),
        ("pvm_suma", values.money(vat)),
        ("bepvm_suma", values.money(net)),
        ("rows", rows_json(lines)),
    ]
    return form, _sent(str(number), net, vat, total)


def order_form(operation_input: Mapping[str, Any]) -> tuple[list[tuple[str, str]], dict[str, Any]]:
    values.closed(operation_input, ORDER_INPUTS | {"connection_ref"}, "The step input")
    number = values.text(
        operation_input.get("number"), "Order number", max_length=50, required=True
    )
    date = values.iso_date(operation_input.get("date"), "Order date")
    customer = values.text(
        operation_input.get("customer_name"), "Customer name", max_length=255, required=True
    )
    lines = lines_of(operation_input.get("lines"), ORDER_LINE_FIELDS, order=True)
    net, vat, total = totals(operation_input, lines)
    form: list[tuple[str, str]] = [
        ("uzsak_num", str(number)),
        ("uzsak_data", values.wire_date(date)),
        ("uzsakovas", str(customer)),
        ("bepvm_suma", values.money(net)),
        ("pvm_suma", values.money(vat)),
        ("uzsak_suma", values.money(total)),
    ]
    for name, wire_name in _ORDER_DATES.items():
        if operation_input.get(name) is not None:
            label = name.replace("_", " ").capitalize()
            form.append(
                (wire_name, values.wire_date(values.iso_date(operation_input[name], label)))
            )
    form += _texts(operation_input, _ORDER_TEXT)
    note = values.text(
        operation_input.get("customer_note"), "Customer note", max_length=1000, multi_line=True
    )
    if note:
        form.append(("uzsakovas_pastaba", note))
    form.append(("rows", rows_json(lines)))
    return form, _sent(str(number), net, vat, total)


def _id_of(answer: Mapping[str, Any], key: str) -> str | None:
    value = answer.get(key)
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, (int, Decimal)):
        return str(value)
    if isinstance(value, str) and value.strip():
        return errors.safe_text(value, 200)
    return None


def _send(
    context: Context,
    path: str,
    form: list[tuple[str, str]],
    sent: dict[str, Any],
    id_key: str,
    output_key: str,
) -> dict[str, Any]:
    answer = context.transport.write(path, form)
    record_id = _id_of(answer, id_key)
    warnings: list[str] = []
    if record_id is None:
        warnings.append(
            f"Centas WS confirmed the document but returned no {id_key}; find it in Centas WS"
        )
    return {output_key: record_id, **sent, "warnings": warnings}


def send_sales_invoice(context: Context) -> dict[str, Any]:
    form, sent = sales_invoice_form(context.operation_input)
    return _send(context, "documents/create", form, sent, "document_id", "document_id")


def send_purchase_invoice(context: Context) -> dict[str, Any]:
    form, sent = purchase_invoice_form(context.operation_input)
    return _send(context, "documents/purchase/import", form, sent, "purchase_id", "purchase_id")


def send_order(context: Context) -> dict[str, Any]:
    form, sent = order_form(context.operation_input)
    return _send(context, "orders/create", form, sent, "order_hash", "order_hash")


__all__ = [
    "MAX_LINES",
    "ORDER_INPUTS",
    "PURCHASE_INPUTS",
    "SALES_INPUTS",
    "order_form",
    "purchase_invoice_form",
    "sales_invoice_form",
    "send_order",
    "send_purchase_invoice",
    "send_sales_invoice",
    "tolerance",
    "totals",
]
