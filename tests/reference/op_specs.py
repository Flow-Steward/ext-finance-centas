"""Every step of this extension: its name, description, inputs and outputs.

The single source of the contracts (tests/reference/build_contracts.py writes them)
and of the step order. Each input is listed with the documentation field it fills
(``wire``), which tests/reference/coverage.json is built from.
"""

from __future__ import annotations

from typing import Any

ISO_DATE = r"^\d{4}-\d{2}-\d{2}$"
NUMBER = ["number", "string"]
NULLABLE_TEXT = ["string", "null"]

RECEIVED = (
    "Centas WS keeps what it receives until an accountant imports it in the Centas "
    "program (menu ws.centas.lt), so success means received by Centas WS, not yet "
    "booked."
)
NOT_RERUNNABLE = (
    "Centas WS does not check for repeats: sending the same document again can create it "
    "a second time."
)
FROM_EXPORT = (
    "The data is what the Centas program last uploaded to Centas WS (its product "
    "export), read whole and filtered here."
)
TOTALS_RULE = (
    "Give the net total and the VAT total (and optionally the total) as on the "
    "document: they are checked against the lines within one cent per line and sent as "
    "given. Leave them empty to have them computed: each line's net amount rounded to "
    "cents, its VAT rounded to cents, summed."
)

WARNINGS_OUTPUT = {
    "name": "warnings",
    "value_type": "array",
    "schema": {
        "type": "array",
        "items": {"type": "string"},
        "description": "What the step could not do fully or what to check.",
    },
}


def text(
    name: str,
    title: str,
    description: str,
    *,
    wire: str | None,
    max_length: int,
    required: bool = False,
    pattern: str | None = None,
) -> dict[str, Any]:
    schema: dict[str, Any] = {
        "type": "string",
        "title": title,
        "description": description,
        "maxLength": max_length,
    }
    if pattern:
        schema["pattern"] = pattern
    return {
        "name": name,
        "value_type": "text",
        "required": required,
        "schema": schema,
        "wire": wire,
    }


def date(
    name: str, title: str, description: str, *, wire: str | None, required: bool = False
) -> dict[str, Any]:
    item = text(
        name,
        title,
        description + " YYYY-MM-DD.",
        wire=wire,
        max_length=10,
        required=required,
        pattern=ISO_DATE,
    )
    return item


def amount(name: str, title: str, description: str, *, wire: str | None) -> dict[str, Any]:
    return {
        "name": name,
        "value_type": "text",
        "required": False,
        "schema": {"type": NUMBER, "title": title, "description": description},
        "wire": wire,
    }


def choice(
    name: str, title: str, description: str, options: dict[str, str], *, wire: str | None
) -> dict[str, Any]:
    return {
        "name": name,
        "value_type": "text",
        "required": False,
        "schema": {
            "type": "string",
            "enum": list(options),
            "title": title,
            "description": description,
        },
        "labels": options,
        "wire": wire,
    }


def paging() -> list[dict[str, Any]]:
    return [
        {
            "name": "page",
            "value_type": "integer",
            "required": False,
            "schema": {
                "type": "integer",
                "minimum": 1,
                "maximum": 1_000_000,
                "title": "Page",
                "description": "The page to read, from 1; pass next_page to continue.",
            },
            "wire": None,
        },
        {
            "name": "limit",
            "value_type": "integer",
            "required": False,
            "schema": {
                "type": "integer",
                "minimum": 1,
                "maximum": 500,
                "title": "Rows",
                "description": "Rows per page, 1 to 500. Default 100.",
            },
            "wire": None,
        },
    ]


def page_outputs(item_schema: dict[str, Any], description: str) -> list[dict[str, Any]]:
    return [
        {
            "name": "items",
            "value_type": "array",
            "schema": {"type": "array", "items": item_schema, "description": description},
        },
        {
            "name": "count",
            "value_type": "integer",
            "schema": {"type": "integer", "description": "How many rows this page holds."},
        },
        {
            "name": "total",
            "value_type": "integer",
            "schema": {"type": "integer", "description": "How many rows match in all."},
        },
        {
            "name": "page",
            "value_type": "integer",
            "schema": {"type": "integer", "description": "This page's number."},
        },
        {
            "name": "has_more",
            "value_type": "boolean",
            "schema": {"type": "boolean", "description": "True when more rows follow."},
        },
        {
            "name": "next_page",
            "value_type": "integer",
            "schema": {
                "type": ["integer", "null"],
                "description": "The page to read next, or null.",
            },
        },
        WARNINGS_OUTPUT,
    ]


def _props(fields: dict[str, Any], *, required: list[str] | None = None) -> dict[str, Any]:
    return {
        "type": "object",
        "additionalProperties": False,
        "required": required or [],
        "properties": fields,
    }


def _t(description: str, max_length: int) -> dict[str, Any]:
    return {"type": "string", "maxLength": max_length, "description": description}


def _n(description: str) -> dict[str, Any]:
    return {"type": NUMBER, "description": description}


# -- lines ------------------------------------------------------------------------

SALES_LINE = _props(
    {
        "code": _t("The product's or service's code; Centas looks it up by this code (kodas).", 50),
        "name": _t("Its name (pavadinimas).", 255),
        "unit": _t("Its unit of measure, for example vnt. (matovnt).", 20),
        "quantity": _n("Quantity, greater than zero (kiekis)."),
        "price": _n("Unit price without VAT, up to 6 decimals (kaina)."),
        "vat_percent": _n("VAT rate in percent, 0 to 100 (pvmtar)."),
        "vat_code": _t("VAT tax code of the VMI classifier for i.SAF (Mok_kodas).", 20),
        "income_account": _t("The line's income account (sask_pajamos).", 20),
        "project": _t("The line's project (projektas).", 100),
    },
    required=["code", "quantity", "price", "vat_percent"],
)
PURCHASE_LINE = _props(
    {k: v for k, v in SALES_LINE["properties"].items() if k != "income_account"},
    required=["code", "quantity", "price", "vat_percent"],
)
ORDER_LINE = _props(
    {
        "code": _t("The product's or service's code (kodas).", 50),
        "supplier_code": _t("The supplier's code (t_kodas).", 50),
        "name": _t("Its name (pavadinimas).", 255),
        "unit": _t("Its unit of measure (matovnt).", 20),
        "quantity": _n("Quantity, greater than zero (kiekis)."),
        "price": _n("Unit price without VAT, up to 6 decimals (kaina)."),
        "vat_percent": _n("VAT rate in percent, 0 to 100 (pvm_tar and pvmtar)."),
    },
    required=["code", "quantity", "price", "vat_percent"],
)


def lines(item_schema: dict[str, Any], description: str, placeholder: str) -> dict[str, Any]:
    return {
        "name": "lines",
        "value_type": "array",
        "required": True,
        "schema": {
            "type": "array",
            "title": "Lines",
            "description": description,
            "minItems": 1,
            "maxItems": 500,
            "items": item_schema,
        },
        "placeholder": placeholder,
        "wire": "rows",
    }


TOTAL_INPUTS = [
    amount(
        "net_total",
        "Net total",
        "The total without VAT (bepvm_suma). " + TOTALS_RULE,
        wire="bepvm_suma",
    ),
    amount("vat_total", "VAT total", "The VAT amount (pvm_suma).", wire="pvm_suma"),
    amount("total", "Total", "The total with VAT; must be net total + VAT total.", wire="dok_suma"),
]
SENT_OUTPUTS = [
    {
        "name": "number",
        "value_type": "text",
        "schema": {
            "type": "string",
            "description": "The number sent (auto when Centas numbers it).",
        },
    },
    {
        "name": "net_total",
        "value_type": "text",
        "schema": {"type": "string", "description": "The net total sent."},
    },
    {
        "name": "vat_total",
        "value_type": "text",
        "schema": {"type": "string", "description": "The VAT total sent."},
    },
    {
        "name": "total",
        "value_type": "text",
        "schema": {"type": "string", "description": "The total sent."},
    },
]

# -- products and payments as read ---------------------------------------------------

PRODUCT = _props(
    {
        "id": {"type": NULLABLE_TEXT, "description": "The product's ID in Centas WS."},
        "code": {"type": NULLABLE_TEXT, "description": "Its code."},
        "name": {"type": NULLABLE_TEXT, "description": "Its name."},
        "unit": {"type": NULLABLE_TEXT, "description": "Its unit of measure."},
        "price": {"type": NULLABLE_TEXT, "description": "Its price."},
        "vat_percent": {"type": NULLABLE_TEXT, "description": "Its VAT rate in percent."},
        "stock": {"type": NULLABLE_TEXT, "description": "Its stock in all."},
        "group1": {"type": NULLABLE_TEXT, "description": "Group 1."},
        "group2": {"type": NULLABLE_TEXT, "description": "Group 2."},
        "group3": {"type": NULLABLE_TEXT, "description": "Group 3."},
        "barcode": {"type": NULLABLE_TEXT, "description": "Its barcode."},
        "description": {"type": NULLABLE_TEXT, "description": "Its description."},
        "photo": {"type": NULLABLE_TEXT, "description": "Its photo, as Centas holds it."},
        "stocks": {
            "type": "array",
            "description": "Stock by warehouse.",
            "items": _props(
                {
                    "warehouse_id": {"type": NULLABLE_TEXT, "description": "Warehouse ID."},
                    "warehouse_name": {"type": NULLABLE_TEXT, "description": "Warehouse name."},
                    "quantity": {"type": NULLABLE_TEXT, "description": "Quantity."},
                },
                required=["warehouse_id", "warehouse_name", "quantity"],
            ),
        },
        "parameters": {
            "type": "array",
            "description": "Product parameters.",
            "items": _props(
                {
                    "name": {"type": NULLABLE_TEXT, "description": "Parameter name."},
                    "value": {"type": NULLABLE_TEXT, "description": "Parameter value."},
                },
                required=["name", "value"],
            ),
        },
    },
    required=[
        "id",
        "code",
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
    ],
)
STOCK_ROW = _props(
    {
        "code": {"type": NULLABLE_TEXT, "description": "The product's code."},
        "name": {"type": NULLABLE_TEXT, "description": "Its name."},
        "unit": {"type": NULLABLE_TEXT, "description": "Its unit of measure."},
        "warehouse_id": {
            "type": NULLABLE_TEXT,
            "description": "Warehouse ID; null for the stock in all.",
        },
        "warehouse_name": {"type": NULLABLE_TEXT, "description": "Warehouse name."},
        "quantity": {"type": NULLABLE_TEXT, "description": "Quantity in stock."},
    },
    required=["code", "name", "unit", "warehouse_id", "warehouse_name", "quantity"],
)
PAYMENT = _props(
    {
        "type": {"type": NULLABLE_TEXT, "description": "Payment type, for example BankDeb."},
        "date": {
            "type": NULLABLE_TEXT,
            "description": "Date, YYYY-MM-DD (as sent when it is not a date).",
        },
        "amount": {"type": NULLABLE_TEXT, "description": "Amount."},
        "document_number": {"type": NULLABLE_TEXT, "description": "Document number."},
        "reference": {"type": NULLABLE_TEXT, "description": "Unique reference."},
        "details": {"type": NULLABLE_TEXT, "description": "Payment details."},
        "payer_name": {"type": NULLABLE_TEXT, "description": "Payer or payee name."},
        "payer_code": {"type": NULLABLE_TEXT, "description": "Payer or payee code."},
        "account": {"type": NULLABLE_TEXT, "description": "Account number."},
    },
    required=[
        "type",
        "date",
        "amount",
        "document_number",
        "reference",
        "details",
        "payer_name",
        "payer_code",
        "account",
    ],
)


# -- the steps ------------------------------------------------------------------------


def steps() -> list[dict[str, Any]]:
    """Every step, in the order the step picker and the Centas API page show them."""
    return [
        {
            "operation_id": "send_sales_invoice",
            "display_name": "Send a sales invoice to Centas",
            "group": "Sales",
            "kind": "action",
            "path": "POST /v1/documents/create",
            "description": (
                "Sends a sales invoice with its lines to Centas WS and returns its document "
                "ID. " + RECEIVED + " " + NOT_RERUNNABLE
            ),
            "inputs": [
                text(
                    "number",
                    "Invoice number",
                    "The invoice number (dok_num). Leave empty, or write auto, to have Centas "
                    "number it from its free invoice forms; then give the transaction ID.",
                    wire="dok_num",
                    max_length=50,
                ),
                text(
                    "transaction_id",
                    "Transaction ID",
                    "Needed for an automatic number from Centas's invoice forms (trans_id).",
                    wire="trans_id",
                    max_length=50,
                ),
                date("date", "Date", "The invoice date (data).", wire="data", required=True),
                date("due_date", "Due date", "The payment term (apmok_iki).", wire="apmok_iki"),
                text(
                    "buyer_name",
                    "Buyer name",
                    "The buyer's name (pirkejas).",
                    wire="pirkejas",
                    max_length=255,
                    required=True,
                ),
                text(
                    "buyer_code",
                    "Buyer code",
                    "The buyer's code in your systems (kl_kodas).",
                    wire="kl_kodas",
                    max_length=50,
                ),
                text(
                    "buyer_company_code",
                    "Buyer company code",
                    "The buyer's company or personal code (im_kodas).",
                    wire="im_kodas",
                    max_length=50,
                ),
                text(
                    "buyer_vat_code",
                    "Buyer VAT code",
                    "The buyer's VAT code (pvm_kodas).",
                    wire="pvm_kodas",
                    max_length=50,
                ),
                text(
                    "buyer_email",
                    "Buyer e-mail",
                    "The buyer's e-mail (email).",
                    wire="email",
                    max_length=255,
                ),
                text(
                    "buyer_address",
                    "Buyer address",
                    "The buyer's address (adresas).",
                    wire="adresas",
                    max_length=255,
                ),
                text(
                    "buyer_city",
                    "Buyer city",
                    "The buyer's city (miestas).",
                    wire="miestas",
                    max_length=100,
                ),
                text(
                    "buyer_country",
                    "Buyer country",
                    "The buyer's country (salis).",
                    wire="salis",
                    max_length=100,
                ),
                choice(
                    "buyer_eu_type",
                    "Buyer EU type",
                    "local (0), another EU country (1) or outside the EU (2) (estipas).",
                    {"local": "Local", "eu": "Another EU country", "non_eu": "Outside the EU"},
                    wire="estipas",
                ),
                text(
                    "buyer_group",
                    "Buyer group",
                    "The group a new buyer is put in (grupe).",
                    wire="grupe",
                    max_length=50,
                ),
                lines(
                    SALES_LINE,
                    "The invoice lines, 1 to 500: code, name, unit, quantity, price without "
                    "VAT, vat_percent, vat_code, income_account, project.",
                    '[{"code":"11222","name":"Kompiuteris","unit":"vnt.","quantity":2,'
                    '"price":1050,"vat_percent":21}]',
                ),
                *TOTAL_INPUTS,
                amount("cost", "Cost", "The document's cost price (savikaina).", wire="savikaina"),
                text(
                    "vat_payable_account",
                    "VAT payable account",
                    "The VAT payable account, digits (sask_moketpvm).",
                    wire="sask_moketpvm",
                    max_length=20,
                    pattern=r"^\d+$",
                ),
                text(
                    "receivable_account",
                    "Receivable account",
                    "The buyer debt account (sask_pirkskol).",
                    wire="sask_pirkskol",
                    max_length=20,
                ),
                text(
                    "income_account",
                    "Income account",
                    "The income account, digits (sask_pajamos).",
                    wire="sask_pajamos",
                    max_length=20,
                    pattern=r"^\d+$",
                ),
                text(
                    "project",
                    "Project",
                    "The project or cost centre (projektas).",
                    wire="projektas",
                    max_length=100,
                ),
                text(
                    "order_number",
                    "Order number",
                    "The number of the order this invoice is for (uzsaknr).",
                    wire="uzsaknr",
                    max_length=50,
                ),
                text(
                    "operation_description",
                    "Operation description",
                    "An extra description of the operation (oper_apras).",
                    wire="oper_apras",
                    max_length=255,
                ),
                text(
                    "note",
                    "Note",
                    "A note on the document (pastaba).",
                    wire="pastaba",
                    max_length=1000,
                ),
                text(
                    "issued_by",
                    "Issued by",
                    "Who issued the invoice (israse_asmuo).",
                    wire="israse_asmuo",
                    max_length=100,
                ),
                text(
                    "issued_by_position",
                    "Issuer's position",
                    "The issuer's position (israse_pareigos).",
                    wire="israse_pareigos",
                    max_length=100,
                ),
                text(
                    "intrastat_transport",
                    "Intrastat transport",
                    "Transport code for Intrastat (intrs_transprusis).",
                    wire="intrs_transprusis",
                    max_length=20,
                ),
                text(
                    "intrastat_delivery_terms",
                    "Intrastat delivery terms",
                    "Delivery terms code for Intrastat (intrs_pristsal).",
                    wire="intrs_pristsal",
                    max_length=20,
                ),
                text(
                    "intrastat_transaction",
                    "Intrastat transaction",
                    "Transaction code for Intrastat (intrs_sandoris).",
                    wire="intrs_sandoris",
                    max_length=20,
                ),
                text(
                    "intrastat_county",
                    "Intrastat county",
                    "County code for Intrastat (intrs_apskritis).",
                    wire="intrs_apskritis",
                    max_length=20,
                ),
                text(
                    "intrastat_eu_country",
                    "Intrastat EU country",
                    "EU country code for Intrastat (intrs_eusalis).",
                    wire="intrs_eusalis",
                    max_length=20,
                ),
            ],
            "outputs": [
                {
                    "name": "document_id",
                    "value_type": "text",
                    "schema": {
                        "type": NULLABLE_TEXT,
                        "description": "The document ID Centas WS returned.",
                    },
                },
                *SENT_OUTPUTS,
                WARNINGS_OUTPUT,
            ],
        },
        {
            "operation_id": "send_order",
            "display_name": "Send a customer order to Centas",
            "group": "Sales",
            "kind": "action",
            "path": "POST /v1/orders/create",
            "description": (
                "Sends a customer order with its lines to Centas WS and returns its order "
                "hash. " + RECEIVED + " " + NOT_RERUNNABLE
            ),
            "inputs": [
                text(
                    "number",
                    "Order number",
                    "The order number (uzsak_num).",
                    wire="uzsak_num",
                    max_length=50,
                    required=True,
                ),
                date(
                    "date",
                    "Order date",
                    "The order date (uzsak_data).",
                    wire="uzsak_data",
                    required=True,
                ),
                text(
                    "customer_name",
                    "Customer name",
                    "The customer's name (uzsakovas).",
                    wire="uzsakovas",
                    max_length=255,
                    required=True,
                ),
                text(
                    "customer_company_code",
                    "Customer company code",
                    "The customer's company code (im_kodas).",
                    wire="im_kodas",
                    max_length=50,
                ),
                text(
                    "customer_vat_code",
                    "Customer VAT code",
                    "The customer's VAT code (pvm_kodas).",
                    wire="pvm_kodas",
                    max_length=50,
                ),
                text(
                    "customer_email",
                    "Customer e-mail",
                    "The customer's e-mail (email).",
                    wire="email",
                    max_length=255,
                ),
                text(
                    "customer_phone",
                    "Customer phone",
                    "The customer's phone (tel).",
                    wire="tel",
                    max_length=50,
                ),
                text(
                    "customer_address",
                    "Customer address",
                    "The customer's address (adresas).",
                    wire="adresas",
                    max_length=255,
                ),
                text(
                    "customer_city",
                    "Customer city",
                    "The customer's city (miestas).",
                    wire="miestas",
                    max_length=100,
                ),
                text(
                    "postal_code",
                    "Postal code",
                    "The postal code (pasto_kodas).",
                    wire="pasto_kodas",
                    max_length=20,
                ),
                text(
                    "customer_note",
                    "Customer note",
                    "The customer's note (uzsakovas_pastaba).",
                    wire="uzsakovas_pastaba",
                    max_length=1000,
                ),
                text(
                    "receivable_account",
                    "Receivable account",
                    "The customer debt account (pirk_skolsask).",
                    wire="pirk_skolsask",
                    max_length=20,
                ),
                text(
                    "warehouse",
                    "Warehouse",
                    "The warehouse (sandelis).",
                    wire="sandelis",
                    max_length=50,
                ),
                date(
                    "execution_date",
                    "Execution date",
                    "When to carry it out (vykd_data).",
                    wire="vykd_data",
                ),
                date(
                    "delivery_date",
                    "Delivery date",
                    "The delivery date (pristat_data).",
                    wire="pristat_data",
                ),
                date(
                    "payment_date",
                    "Payment date",
                    "The payment date (apmok_data).",
                    wire="apmok_data",
                ),
                date(
                    "arrival_date",
                    "Arrival date",
                    "The arrival date (atvyk_data).",
                    wire="atvyk_data",
                ),
                date(
                    "departure_date",
                    "Departure date",
                    "The departure date (isvyk_data).",
                    wire="isvyk_data",
                ),
                lines(
                    ORDER_LINE,
                    "The order lines, 1 to 500: code, supplier_code, name, unit, quantity, "
                    "price without VAT, vat_percent.",
                    '[{"code":"11222","name":"Kompiuteris","unit":"vnt.","quantity":2,'
                    '"price":1050,"vat_percent":21}]',
                ),
                amount(
                    "net_total",
                    "Net total",
                    "The order total without VAT (bepvm_suma). " + TOTALS_RULE,
                    wire="bepvm_suma",
                ),
                amount("vat_total", "VAT total", "The order's VAT (pvm_suma).", wire="pvm_suma"),
                amount(
                    "total",
                    "Total",
                    "The order total with VAT; must be net total + VAT total (uzsak_suma).",
                    wire="uzsak_suma",
                ),
            ],
            "outputs": [
                {
                    "name": "order_hash",
                    "value_type": "text",
                    "schema": {
                        "type": NULLABLE_TEXT,
                        "description": "The order hash Centas WS returned.",
                    },
                },
                *SENT_OUTPUTS,
                WARNINGS_OUTPUT,
            ],
        },
        {
            "operation_id": "send_purchase_invoice",
            "display_name": "Send a purchase invoice to Centas",
            "group": "Purchases",
            "kind": "action",
            "path": "POST /v1/documents/purchase/import",
            "description": (
                "Sends a supplier's invoice with its lines to Centas WS and returns its "
                "purchase ID. " + RECEIVED + " " + NOT_RERUNNABLE
            ),
            "inputs": [
                text(
                    "seller_name",
                    "Seller name",
                    "The seller's name (kontrah).",
                    wire="kontrah",
                    max_length=255,
                    required=True,
                ),
                text(
                    "number",
                    "Invoice number",
                    "The supplier's invoice number (dok_num).",
                    wire="dok_num",
                    max_length=50,
                    required=True,
                ),
                date("date", "Date", "The invoice date (data).", wire="data", required=True),
                lines(
                    PURCHASE_LINE,
                    "The invoice lines, 1 to 500: code, name, unit, quantity, price without "
                    "VAT, vat_percent, vat_code, project.",
                    '[{"code":"11222","name":"Kompiuteris","unit":"vnt.","quantity":2,'
                    '"price":1050,"vat_percent":21}]',
                ),
                *TOTAL_INPUTS,
            ],
            "outputs": [
                {
                    "name": "purchase_id",
                    "value_type": "text",
                    "schema": {
                        "type": NULLABLE_TEXT,
                        "description": "The purchase ID Centas WS returned.",
                    },
                },
                *SENT_OUTPUTS,
                WARNINGS_OUTPUT,
            ],
        },
        {
            "operation_id": "send_payments",
            "display_name": "Send bank payments to Centas",
            "group": "Payments",
            "kind": "action",
            "path": "POST /v1/payments/import",
            "description": (
                "Sends bank payments to Centas WS in one batch and returns how many it "
                "created. Each payment needs its own reference (RefNr). Before sending, the "
                "step reads Centas WS's payment export: when it already lists one of the "
                "references, or cannot be read, the step stops and sends nothing. "
                + RECEIVED
                + " "
                + NOT_RERUNNABLE
            ),
            "inputs": [
                {
                    "name": "payments",
                    "value_type": "array",
                    "required": True,
                    "schema": {
                        "type": "array",
                        "title": "Payments",
                        "description": (
                            "The payments, 1 to 500: type (for example BankDeb), date, amount, "
                            "document_number, reference, details, payer_name, payer_code, "
                            "account."
                        ),
                        "minItems": 1,
                        "maxItems": 500,
                        "items": _props(
                            {
                                "type": _t(
                                    "Payment type code, for example BankDeb (PaymentType).", 30
                                ),
                                "date": {
                                    "type": "string",
                                    "pattern": ISO_DATE,
                                    "description": "Date, YYYY-MM-DD (Date).",
                                },
                                "amount": _n("Amount, greater than zero, 2 decimals (Amount)."),
                                "document_number": _t("Document number (DocNr).", 50),
                                "reference": _t("Unique reference of the payment (RefNr).", 100),
                                "details": _t("Payment details (Details).", 500),
                                "payer_name": _t("Payer or payee name (RecName).", 255),
                                "payer_code": _t("Payer or payee code (RecId).", 50),
                                "account": _t("Account number (ToAccountNumber).", 50),
                            },
                            required=["type", "date", "amount", "reference"],
                        ),
                    },
                    "placeholder": (
                        '[{"type":"BankDeb","date":"2026-01-15","amount":"123.23",'
                        '"reference":"ABC001","payer_name":"UAB Moketojas"}]'
                    ),
                    "wire": "data",
                },
            ],
            "outputs": [
                {
                    "name": "sent",
                    "value_type": "integer",
                    "schema": {"type": "integer", "description": "How many payments were sent."},
                },
                {
                    "name": "found",
                    "value_type": "integer",
                    "schema": {
                        "type": ["integer", "null"],
                        "description": "How many Centas WS found in them.",
                    },
                },
                {
                    "name": "created",
                    "value_type": "integer",
                    "schema": {
                        "type": ["integer", "null"],
                        "description": "How many Centas WS created.",
                    },
                },
                {
                    "name": "references",
                    "value_type": "array",
                    "schema": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "The references sent, in order.",
                    },
                },
                WARNINGS_OUTPUT,
            ],
        },
        {
            "operation_id": "get_payments",
            "display_name": "Get payments",
            "group": "Payments",
            "kind": "source",
            "path": "GET /v1/payments/export",
            "description": (
                "Reads the payments in Centas WS's payment export, optionally only a date "
                "range or one reference, one page at a time. The export is read whole and "
                "filtered here."
            ),
            "inputs": [
                date("date_from", "From date", "Only payments on or after this date.", wire=None),
                date("date_to", "To date", "Only payments on or before this date.", wire=None),
                text(
                    "reference",
                    "Reference",
                    "Only the payment with this reference.",
                    wire=None,
                    max_length=100,
                ),
                *paging(),
            ],
            "outputs": page_outputs(PAYMENT, "The payments of this page."),
        },
        {
            "operation_id": "send_products",
            "display_name": "Send products to Centas",
            "group": "Products",
            "kind": "action",
            "path": "POST /v1/products/import",
            "description": (
                "Sends product cards to Centas WS in one batch; Centas WS creates new ones "
                "and updates known ones and returns the counts. Only the fields given are "
                "sent. Centas WS does not check for repeats: sending the same product again can "
                "create it a second time."
            ),
            "inputs": [
                {
                    "name": "products",
                    "value_type": "array",
                    "required": True,
                    "schema": {
                        "type": "array",
                        "title": "Products",
                        "description": (
                            "The products, 1 to 500: code, id, name, unit, price, vat_percent, "
                            "stock, group1-3, barcode, description, photo, stocks "
                            "[{warehouse_id, warehouse_name, quantity}], parameters "
                            "[{name, value}]."
                        ),
                        "minItems": 1,
                        "maxItems": 500,
                        "items": _props(
                            {
                                "code": _t("Product code (kodas).", 50),
                                "id": _t("Product ID in Centas WS (id).", 50),
                                "name": _t("Name (pavadinimas).", 255),
                                "unit": _t("Unit of measure (matovnt).", 20),
                                "price": _n("Price, up to 6 decimals (kaina)."),
                                "vat_percent": _n("VAT rate in percent (pvmtar)."),
                                "stock": _n("Stock in all (likutis)."),
                                "group1": _t("Group 1 (grupe1).", 100),
                                "group2": _t("Group 2 (grupe2).", 100),
                                "group3": _t("Group 3 (grupe3).", 100),
                                "barcode": _t("Barcode (barkodas).", 50),
                                "description": _t("Description (aprasymas).", 2000),
                                "photo": _t("Photo (Nuotrauka).", 500),
                                "stocks": {
                                    "type": "array",
                                    "maxItems": 50,
                                    "description": "Stock by warehouse (Stocks).",
                                    "items": _props(
                                        {
                                            "warehouse_id": _t("Warehouse ID (WarehouseId).", 50),
                                            "warehouse_name": _t(
                                                "Warehouse name (WarehouseName).", 255
                                            ),
                                            "quantity": _n("Quantity (Quantity)."),
                                        },
                                        required=["warehouse_id", "quantity"],
                                    ),
                                },
                                "parameters": {
                                    "type": "array",
                                    "maxItems": 100,
                                    "description": "Parameters (ProductParameters).",
                                    "items": _props(
                                        {
                                            "name": _t("Parameter name (Name).", 255),
                                            "value": _t("Parameter value (Value).", 1000),
                                        },
                                        required=["name"],
                                    ),
                                },
                            },
                            required=["code"],
                        ),
                    },
                    "placeholder": (
                        '[{"code":"C001","name":"Programa nr. 1","unit":"vnt.",'
                        '"price":"100.00","vat_percent":21}]'
                    ),
                    "wire": "data",
                },
            ],
            "outputs": [
                {
                    "name": "sent",
                    "value_type": "integer",
                    "schema": {"type": "integer", "description": "How many products were sent."},
                },
                {
                    "name": "found",
                    "value_type": "integer",
                    "schema": {
                        "type": ["integer", "null"],
                        "description": "How many Centas WS found in them.",
                    },
                },
                {
                    "name": "created",
                    "value_type": "integer",
                    "schema": {
                        "type": ["integer", "null"],
                        "description": "How many Centas WS created.",
                    },
                },
                {
                    "name": "updated",
                    "value_type": "integer",
                    "schema": {
                        "type": ["integer", "null"],
                        "description": "How many Centas WS updated.",
                    },
                },
                {
                    "name": "codes",
                    "value_type": "array",
                    "schema": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "The product codes sent, in order.",
                    },
                },
                WARNINGS_OUTPUT,
            ],
        },
        {
            "operation_id": "get_products",
            "display_name": "Get products",
            "group": "Products",
            "kind": "source",
            "path": "GET /v1/products/export",
            "description": (
                "Reads product cards, with stock by warehouse and parameters, one page at a "
                "time; or one product by its ID. " + FROM_EXPORT
            ),
            "inputs": [
                text(
                    "id",
                    "Product ID",
                    "Only this product (its ID in Centas WS).",
                    wire="id",
                    max_length=50,
                ),
                *paging(),
            ],
            "outputs": page_outputs(PRODUCT, "The products of this page."),
        },
        {
            "operation_id": "find_product",
            "display_name": "Find a product by code or barcode",
            "group": "Products",
            "kind": "source",
            "path": "GET /v1/products/export",
            "description": (
                "Finds the one product with this code or barcode. Several products with it "
                "stop the step with a conflict. " + FROM_EXPORT
            ),
            "inputs": [
                text("code", "Code", "The product code, exactly.", wire=None, max_length=50),
                text("barcode", "Barcode", "Or the barcode, exactly.", wire=None, max_length=50),
            ],
            "outputs": [
                {
                    "name": "found",
                    "value_type": "boolean",
                    "schema": {"type": "boolean", "description": "True when the product exists."},
                },
                {
                    "name": "product",
                    "value_type": "object",
                    "schema": {
                        **PRODUCT,
                        "type": ["object", "null"],
                        "description": "The product, or null.",
                    },
                },
                WARNINGS_OUTPUT,
            ],
        },
        {
            "operation_id": "get_stock_levels",
            "display_name": "Get stock levels",
            "group": "Products",
            "kind": "source",
            "path": "GET /v1/products/export",
            "description": (
                "Stock of products by warehouse, one row per product and warehouse, "
                "optionally for one product or one warehouse. " + FROM_EXPORT
            ),
            "inputs": [
                text("code", "Code", "Only this product code.", wire=None, max_length=50),
                text(
                    "warehouse_id", "Warehouse ID", "Only this warehouse.", wire=None, max_length=50
                ),
                *paging(),
            ],
            "outputs": page_outputs(STOCK_ROW, "One row per product and warehouse."),
        },
        {
            "operation_id": "test_connection",
            "display_name": "Test the connection",
            "group": "Connection",
            "kind": "source",
            "path": "GET /v1/products/export",
            "description": (
                "Checks the key by starting to read the product export; reads only its first "
                "few kilobytes."
            ),
            "inputs": [],
            "outputs": [
                {
                    "name": "connected",
                    "value_type": "boolean",
                    "schema": {"type": "boolean", "description": "True when the key works."},
                },
                {
                    "name": "duration_ms",
                    "value_type": "integer",
                    "schema": {
                        "type": "integer",
                        "description": "How long the check took, in milliseconds.",
                    },
                },
                WARNINGS_OUTPUT,
            ],
        },
    ]


GROUPS = ["Sales", "Purchases", "Payments", "Products", "Connection"]

__all__ = ["GROUPS", "steps"]
