"""Send a sales invoice, a customer order or a purchase invoice to Centas WS.

Each is one POST of form fields (``multipart/form-data``), its lines as a JSON array
in ``rows``. Fields come from the Centas WS API specification; a few fields that only
the older GitBook documentation describes are offered as optional inputs too
(tests/reference/centas_api.py names the source of each).

Totals: Centas lets each company choose how VAT is summed, so the rounding Centas
applies is not known here. When the step is given the totals, they are checked
against the lines within ``tolerance`` (one cent per line) and sent as given; total
must equal net + VAT exactly. When it is not given them, they are computed by one
rule — each line rounded to cents, its VAT rounded to cents, summed — and the values
sent are returned. Lines with a discount or their own VAT amount cannot be checked
that way: then the totals must be given, and only total = net + VAT is checked.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from decimal import Decimal, localcontext
from typing import Any

from . import errors, values
from .context import Context
from .errors import invalid
from .transport import parse_json, success_of

MAX_LINES = 500
#: The largest amount a line or a document may reach: 15 whole digits and cents.
MAX_AMOUNT = Decimal("999999999999999.99")
#: Digits every sum is taken with (a line is at most 15 + 15 whole digits before the
#: limit is checked, and a document sums up to 500 lines).
PRECISION = 60

_TOTALS = ("net_total", "vat_total", "total")

# -- sales invoice (documents/create) ------------------------------------------------

#: Input -> (form field, max length) of the optional text fields.
_SALES_TEXT: dict[str, tuple[str, int]] = {
    "number_series": ("dok_num_series", 20),
    "check_order": ("check_order", 50),
    "order_number": ("uzsaknr", 50),
    "buyer_company_code": ("im_kodas", 50),
    "buyer_vat_code": ("pvm_kodas", 50),
    "buyer_country": ("salis", 100),
    "buyer_city": ("miestas", 100),
    "buyer_address": ("adresas", 255),
    "buyer_email": ("email", 255),
    "document_type": ("type", 20),
    # Only in the GitBook documentation:
    "transaction_id": ("trans_id", 50),
    "buyer_code": ("kl_kodas", 50),
    "buyer_group": ("grupe", 50),
    "receivable_account": ("sask_pirkskol", 20),
    "project": ("projektas", 100),
    "operation_description": ("oper_apras", 255),
    "issued_by": ("israse_asmuo", 100),
    "issued_by_position": ("israse_pareigos", 100),
    "intrastat_transport": ("intrs_transprusis", 20),
    "intrastat_delivery_terms": ("intrs_pristsal", 20),
    "intrastat_transaction": ("intrs_sandoris", 20),
    "intrastat_county": ("intrs_apskritis", 20),
    "intrastat_eu_country": ("intrs_eusalis", 20),
}
#: Accounts the GitBook documentation types as numbers: digits only.
_SALES_ACCOUNTS: dict[str, str] = {
    "vat_payable_account": "sask_moketpvm",
    "income_account": "sask_pajamos",
}
EU_TYPES = {"local": "0", "eu": "1", "non_eu": "2"}

SALES_INPUTS: frozenset[str] = frozenset(
    {
        "number",
        "date",
        "due_date",
        "buyer_name",
        "buyer_eu_type",
        "cost",
        "note",
        "lines",
        *_SALES_TEXT,
        *_SALES_ACCOUNTS,
        *_TOTALS,
    }
)
#: Line input -> (row field, max length) of the optional text fields of a sales line.
_SALES_LINE_TEXT: dict[str, tuple[str, int]] = {
    "kind": ("prek_pasl", 5),
    "ean": ("ean", 20),
    "vat_code": ("Mok_kodas", 20),
    "income_account": ("sask_pajamos", 20),
    "project": ("projektas", 100),
    "hs_code": ("hs_code", 20),
    "country_origin": ("country_origin", 20),
    "material": ("material", 100),
}
#: Line amounts that change the line's sum in a way the specification does not define.
_SALES_LINE_AMOUNTS: dict[str, str] = {
    "vat_amount": "pvmsuma",
    "discount_percent": "nuolaida_proc",
    "discount": "nuolaida",
}
_LINE_CORE = frozenset({"code", "name", "unit", "quantity", "price", "vat_percent"})
SALES_LINE_FIELDS: frozenset[str] = _LINE_CORE | set(_SALES_LINE_TEXT) | set(_SALES_LINE_AMOUNTS)

# -- order (orders/create) ------------------------------------------------------------

_ORDER_TEXT: dict[str, tuple[str, int]] = {
    "carrier": ("vezejas", 100),
    "comment": ("komentaras", 1000),
    "delivery_branch": ("uzsak_padalinys", 255),
    "delivery_branch_gln": ("uzsak_padalinys_gln", 20),
    "delivery_branch_iln": ("uzsak_padalinys_iln", 20),
    "customer_iln": ("uzsak_iln", 20),
    "customer_company_code": ("im_kodas", 50),
    "customer_vat_code": ("pvm_kodas", 50),
    "customer_country": ("salis", 100),
    "customer_city": ("miestas", 100),
    "customer_address": ("adresas", 255),
    "customer_email": ("email", 255),
    # Only in the GitBook documentation:
    "customer_phone": ("tel", 50),
    "postal_code": ("pasto_kodas", 20),
    "receivable_account": ("pirk_skolsask", 20),
    "warehouse": ("sandelis", 50),
}
_ORDER_DATES: dict[str, str] = {
    "delivery_date": "pristat_data",
    # Only in the GitBook documentation:
    "execution_date": "vykd_data",
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
ORDER_LINE_FIELDS: frozenset[str] = _LINE_CORE | {"supplier_code"}

# -- purchase invoice (documents/purchase/import) -------------------------------------

PURCHASE_INPUTS: frozenset[str] = frozenset({"seller_name", "number", "date", "lines", *_TOTALS})
PURCHASE_LINE_FIELDS: frozenset[str] = _LINE_CORE


class Line:
    """One validated line: its row fields, its net amount and VAT in cents, and
    whether its sum can be checked (no discount, no VAT amount of its own)."""

    def __init__(self, wire: dict[str, str], net: Decimal, vat: Decimal, checkable: bool) -> None:
        self.wire = wire
        self.net = net
        self.vat = vat
        self.checkable = checkable


def check_line(
    item: Mapping[str, Any],
    index: int,
    allowed: frozenset[str],
    *,
    names_required: bool,
) -> Line:
    what = f"Line {index}"
    values.closed(item, allowed, what)
    code = values.required_text(item.get("code"), f"{what} code", max_length=50)
    name = values.text(item.get("name"), f"{what} name", max_length=255, required=names_required)
    unit = values.text(item.get("unit"), f"{what} unit", max_length=20, required=names_required)
    quantity = values.positive(item.get("quantity"), f"{what} quantity")
    price = values.not_negative(item.get("price"), f"{what} price")
    rate = values.percent(item.get("vat_percent"), f"{what} VAT percent")
    with localcontext() as ctx:
        ctx.prec = PRECISION
        net = values.cents(quantity * price)
        vat = values.cents(net * rate / 100)
        within_limit(net + vat, f"{what} amount with VAT")
    wire: dict[str, str] = {"kodas": code}
    if "supplier_code" in allowed:
        supplier = values.text(item.get("supplier_code"), f"{what} supplier code", max_length=50)
        if supplier:
            wire["t_kodas"] = supplier
    if name:
        wire["pavadinimas"] = name
    if unit:
        wire["matovnt"] = unit
    wire["kiekis"] = values.wire(quantity)
    wire["kaina"] = values.wire(price)
    wire["pvmtar"] = values.wire(rate)
    for key, (field, limit) in _SALES_LINE_TEXT.items():
        if key in allowed:
            label = f"{what} {key.replace('_', ' ')}"
            value = values.text(item.get(key), label, max_length=limit)
            if value:
                wire[field] = value
    checkable = True
    for key, field in _SALES_LINE_AMOUNTS.items():
        if key in allowed and item.get(key) is not None:
            label = f"{what} {key.replace('_', ' ')}"
            amount = (
                values.percent(item[key], label)
                if key == "discount_percent"
                else values.not_negative(item[key], label, places=2)
            )
            within_limit(amount, label)
            wire[field] = values.wire(amount)
            checkable = False
    return Line(wire, net, vat, checkable)


def lines_of(value: Any, allowed: frozenset[str], *, names_required: bool) -> list[Line]:
    items = values.records(value, "Lines", max_items=MAX_LINES)
    return [
        check_line(item, i, allowed, names_required=names_required)
        for i, item in enumerate(items, start=1)
    ]


def within_limit(amount: Decimal, what: str) -> None:
    """Refuse an amount beyond 15 whole digits before anything is sent."""
    if amount > MAX_AMOUNT:
        raise invalid(f"{what} is larger than {values.money(MAX_AMOUNT)} (15 whole digits)")


def tolerance(count: int) -> Decimal:
    """How far given totals may differ from the lines: one cent per line."""
    return values.CENT * count


def totals(
    operation_input: Mapping[str, Any], lines: list[Line]
) -> tuple[Decimal, Decimal, Decimal]:
    """(net, VAT, total) to send: given and checked, or computed by one rule.

    Every sum is taken with ``PRECISION`` digits, far beyond the 15 whole digits an
    amount may have, and refused past that limit before anything is sent.
    """
    with localcontext() as ctx:
        ctx.prec = PRECISION
        return _totals(operation_input, lines)


def _totals(
    operation_input: Mapping[str, Any], lines: list[Line]
) -> tuple[Decimal, Decimal, Decimal]:
    computed_net = sum((line.net for line in lines), Decimal("0.00"))
    computed_vat = sum((line.vat for line in lines), Decimal("0.00"))
    within_limit(computed_net + computed_vat, "The lines' total with VAT")
    checkable = all(line.checkable for line in lines)
    given = {k: operation_input.get(k) for k in _TOTALS if operation_input.get(k) is not None}
    if not given:
        if not checkable:
            raise invalid(
                "Lines with a discount or their own VAT amount need the document's net total "
                "and VAT total: give them as on the document"
            )
        return computed_net, computed_vat, computed_net + computed_vat
    if "net_total" not in given or "vat_total" not in given:
        raise invalid(
            "Give both the net total and the VAT total (and optionally the total), or none of "
            "them to have them computed from the lines"
        )
    net = values.not_negative(given["net_total"], "Net total", places=2)
    vat = values.not_negative(given["vat_total"], "VAT total", places=2)
    total = net + vat
    within_limit(total, "The total")
    if "total" in given:
        stated = values.not_negative(given["total"], "Total", places=2)
        if stated != total:
            raise errors.no_effect(
                errors.CONFLICT,
                f"The total {values.money(stated)} is not the net total plus VAT "
                f"({values.money(net)} + {values.money(vat)} = {values.money(total)}); "
                "nothing was sent",
            )
    if not checkable:
        return net, vat, total
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


def _date(operation_input: Mapping[str, Any], name: str, what: str) -> str:
    return values.wire_date(values.iso_date(operation_input.get(name), what))


def _sent(number: str, net: Decimal, vat: Decimal, total: Decimal) -> dict[str, Any]:
    return {
        "number": number,
        "net_total": values.money(net),
        "vat_total": values.money(vat),
        "total": values.money(total),
    }


Form = tuple[list[tuple[str, str]], dict[str, Any]]


def sales_invoice_form(operation_input: Mapping[str, Any]) -> Form:
    values.closed(operation_input, SALES_INPUTS | {"connection_ref"}, "The step input")
    number = values.required_text(operation_input.get("number"), "Invoice number", max_length=50)
    if number.lower() == "auto":
        number = "auto"
    buyer = values.required_text(operation_input.get("buyer_name"), "Buyer name", max_length=255)
    cost = values.not_negative(operation_input.get("cost"), "Cost", places=2)
    within_limit(cost, "Cost")
    lines = lines_of(operation_input.get("lines"), SALES_LINE_FIELDS, names_required=True)
    net, vat, total = totals(operation_input, lines)
    form: list[tuple[str, str]] = [
        ("pirkejas", buyer),
        ("data", _date(operation_input, "date", "Date")),
        ("dok_suma", values.money(total)),
        ("dok_num", number),
        ("apmok_iki", _date(operation_input, "due_date", "Due date")),
        ("pvm_suma", values.money(vat)),
        ("bepvm_suma", values.money(net)),
        ("savikaina", values.money(cost)),
    ]
    eu_type = values.choice(operation_input.get("buyer_eu_type"), "Buyer EU type", EU_TYPES)
    if eu_type is not None:
        form.append(("estipas", eu_type))
    form += _texts(operation_input, _SALES_TEXT)
    for name, wire_name in _SALES_ACCOUNTS.items():
        account = _account(operation_input.get(name), name.replace("_", " ").capitalize())
        if account:
            form.append((wire_name, account))
    note = values.text(operation_input.get("note"), "Note", max_length=1000, multi_line=True)
    if note:
        form.append(("pastaba", note))
    form.append(("rows", rows_json(lines)))
    return form, _sent(number, net, vat, total)


def order_form(operation_input: Mapping[str, Any]) -> Form:
    values.closed(operation_input, ORDER_INPUTS | {"connection_ref"}, "The step input")
    number = values.required_text(operation_input.get("number"), "Order number", max_length=50)
    customer = values.required_text(
        operation_input.get("customer_name"), "Customer name", max_length=255
    )
    lines = lines_of(operation_input.get("lines"), ORDER_LINE_FIELDS, names_required=False)
    net, vat, total = totals(operation_input, lines)
    form: list[tuple[str, str]] = [
        ("uzsakovas", customer),
        ("uzsak_data", _date(operation_input, "date", "Order date")),
        ("uzsak_suma", values.money(total)),
        ("uzsak_num", number),
        ("pvm_suma", values.money(vat)),
        ("bepvm_suma", values.money(net)),
    ]
    for name, wire_name in _ORDER_DATES.items():
        if operation_input.get(name) is not None:
            label = name.replace("_", " ").capitalize()
            form.append((wire_name, _date(operation_input, name, label)))
    form += _texts(operation_input, _ORDER_TEXT)
    note = values.text(
        operation_input.get("customer_note"), "Customer note", max_length=1000, multi_line=True
    )
    if note:
        form.append(("uzsakovas_pastaba", note))
    form.append(("rows", rows_json(lines)))
    return form, _sent(number, net, vat, total)


def purchase_invoice_form(operation_input: Mapping[str, Any]) -> Form:
    values.closed(operation_input, PURCHASE_INPUTS | {"connection_ref"}, "The step input")
    seller = values.required_text(operation_input.get("seller_name"), "Seller name", max_length=255)
    number = values.required_text(operation_input.get("number"), "Invoice number", max_length=50)
    lines = lines_of(operation_input.get("lines"), PURCHASE_LINE_FIELDS, names_required=False)
    net, vat, total = totals(operation_input, lines)
    form = [
        ("kontrah", seller),
        ("data", _date(operation_input, "date", "Date")),
        ("dok_suma", values.money(total)),
        ("dok_num", number),
        ("pvm_suma", values.money(vat)),
        ("bepvm_suma", values.money(net)),
        ("rows", rows_json(lines)),
    ]
    return form, _sent(number, net, vat, total)


def id_of(answer: Mapping[str, Any], *keys: str) -> str | None:
    """The first id among ``keys`` in a write's answer, as text."""
    for key in keys:
        value = answer.get(key)
        if isinstance(value, bool) or value is None:
            continue
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
    keys: tuple[str, ...],
    output_key: str,
) -> dict[str, Any]:
    answer = context.transport.write(path, form)
    record_id = id_of(answer, *keys)
    warnings: list[str] = []
    if record_id is None:
        warnings.append(
            f"Centas WS confirmed the document but returned no {keys[0]}; find it in Centas WS"
        )
    return {output_key: record_id, **sent, "warnings": warnings}


def send_sales_invoice(context: Context) -> dict[str, Any]:
    form, sent = sales_invoice_form(context.operation_input)
    try:
        return _send(context, "documents/create", form, sent, ("document_id",), "document_id")
    except errors.ExtensionError as exc:
        if exc.external_effect_status == "timeout_unknown" and sent["number"] != "auto":
            raise _with_lookup(context, exc, sent["number"]) from None
        raise


def _with_lookup(
    context: Context, exc: errors.ExtensionError, number: str
) -> errors.ExtensionError:
    """After an unknown outcome, one read of documents/get by number, as information only.

    The write is never sent again here; the answer only tells the operator what to check.
    """
    try:
        raw = context.transport.read("documents/get", [("dok_num", number)])
        answer = parse_json(raw)
        found = success_of(answer) is True and bool(answer.get("data"))
    except errors.ExtensionError as lookup:
        if lookup.code != errors.UPSTREAM_VALIDATION_FAILED:
            return exc
        found = False  # Centas WS's own "no such document" refusal
    except Exception:  # the lookup is only a hint; its failure changes nothing
        return exc
    hint = (
        f" Centas WS now lists a document numbered {number}."
        if found
        else f" Centas WS did not return a document numbered {number} when asked right after."
    )
    return errors.ExtensionError(
        exc.code,
        exc.message + hint,
        failure_class=exc.failure_class,
        retryable=False,
        definitely_no_external_effect=False,
        external_effect_status="timeout_unknown",
        http_status=exc.http_status,
    )


def send_order(context: Context) -> dict[str, Any]:
    form, sent = order_form(context.operation_input)
    # The specification answers order_id; the GitBook documentation order_hash.
    return _send(context, "orders/create", form, sent, ("order_id", "order_hash"), "order_id")


def send_purchase_invoice(context: Context) -> dict[str, Any]:
    form, sent = purchase_invoice_form(context.operation_input)
    return _send(context, "documents/purchase/import", form, sent, ("purchase_id",), "purchase_id")


__all__ = [
    "MAX_AMOUNT",
    "MAX_LINES",
    "ORDER_INPUTS",
    "ORDER_LINE_FIELDS",
    "PURCHASE_INPUTS",
    "PURCHASE_LINE_FIELDS",
    "SALES_INPUTS",
    "SALES_LINE_FIELDS",
    "Line",
    "check_line",
    "id_of",
    "order_form",
    "purchase_invoice_form",
    "sales_invoice_form",
    "send_order",
    "send_purchase_invoice",
    "send_sales_invoice",
    "tolerance",
    "totals",
    "within_limit",
]
