"""Every step of this extension: its name, description, inputs and outputs.

The single source of the contracts (tests/reference/build_contracts.py writes them)
and of the step order. ``path`` names the Centas WS operation a step calls;
tests/reference/centas_api.py maps every documented field to these inputs.
"""

from __future__ import annotations

from typing import Any

ISO_DATE = r"^\d{4}-\d{2}-\d{2}$"
NUMBER = ["number", "string"]
NULLABLE_TEXT = ["string", "null"]
NULLABLE_INT = ["integer", "null"]
PAYMENT_TYPES = ["BankDeb", "CashDeb", "BankCred", "CashDeb2"]

RECEIVED = (
    "Centas WS keeps it until the Centas program imports it, so success means Centas WS "
    "received it."
)
REPEATS = (
    "Centas WS does not check for repeats: sending the same {noun} again can create it a "
    "second time."
)
TAKES = (
    "Takes them from the Centas WS queue: Centas WS marks what it hands out, so the Centas "
    "program will no longer see these records as new. The answer is also saved whole as a "
    "workflow file."
)
FROM_PROGRAM = "The data is what the Centas program uploaded to Centas WS."
TOTALS_RULE = (
    "Give the net total and the VAT total (and optionally the total) as on the document: "
    "they are checked against the lines within one cent per line and sent as given. Leave "
    "them empty to have them computed: each line's net amount rounded to cents, its VAT "
    "rounded to cents, summed. Lines with a discount or their own VAT amount need the "
    "totals."
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

# -- building blocks --------------------------------------------------------------------


def text(
    name: str,
    title: str,
    description: str,
    *,
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
    return {"name": name, "value_type": "text", "required": required, "schema": schema}


def date(name: str, title: str, description: str, *, required: bool = False) -> dict[str, Any]:
    return text(
        name,
        title,
        description + " YYYY-MM-DD.",
        max_length=10,
        required=required,
        pattern=ISO_DATE,
    )


def amount(name: str, title: str, description: str, *, required: bool = False) -> dict[str, Any]:
    return {
        "name": name,
        "value_type": "text",
        "required": required,
        "schema": {"type": NUMBER, "title": title, "description": description},
    }


def flag(name: str, title: str, description: str) -> dict[str, Any]:
    return {
        "name": name,
        "value_type": "boolean",
        "required": False,
        "schema": {"type": "boolean", "title": title, "description": description},
    }


def whole(name: str, title: str, description: str, *, required: bool = False) -> dict[str, Any]:
    return {
        "name": name,
        "value_type": "integer",
        "required": required,
        "schema": {
            "type": "integer",
            "minimum": 1,
            "maximum": 2_147_483_647,
            "title": title,
            "description": description,
        },
    }


def choice(name: str, title: str, description: str, options: dict[str, str]) -> dict[str, Any]:
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
    }


def records(
    name: str,
    title: str,
    description: str,
    item: dict[str, Any],
    *,
    max_items: int = 500,
    placeholder: str | None = None,
) -> dict[str, Any]:
    spec: dict[str, Any] = {
        "name": name,
        "value_type": "array",
        "required": True,
        "schema": {
            "type": "array",
            "title": title,
            "description": description,
            "minItems": 1,
            "maxItems": max_items,
            "items": item,
        },
    }
    if placeholder:
        spec["placeholder"] = placeholder
    return spec


def artifact(name: str, title: str, description: str) -> dict[str, Any]:
    return {
        "name": name,
        "value_type": "artifact_handle",
        "required": False,
        "schema": {"title": title, "description": description},
    }


def _t(description: str, max_length: int) -> dict[str, Any]:
    return {"type": "string", "maxLength": max_length, "description": description}


def _n(description: str) -> dict[str, Any]:
    return {"type": NUMBER, "description": description}


def _d(description: str) -> dict[str, Any]:
    return {"type": "string", "pattern": ISO_DATE, "description": description + " YYYY-MM-DD."}


def _b(description: str) -> dict[str, Any]:
    return {"type": "boolean", "description": description}


def _obj(fields: dict[str, Any], required: list[str]) -> dict[str, Any]:
    return {
        "type": "object",
        "additionalProperties": False,
        "required": required,
        "properties": fields,
    }


def _out(name: str, value_type: str, kind: Any, description: str) -> dict[str, Any]:
    return {
        "name": name,
        "value_type": value_type,
        "schema": {"type": kind, "description": description},
    }


def record_schema(
    description: str, fields: dict[str, str], lists: dict[str, str] | None = None
) -> dict[str, Any]:
    """A record as Centas WS sends it, under its own field names."""
    properties: dict[str, Any] = {name: {"description": note} for name, note in fields.items()}
    for name, note in (lists or {}).items():
        properties[name] = {"type": "array", "description": note}
    return {
        "type": "object",
        "additionalProperties": True,
        "description": description,
        "properties": properties,
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
        },
    ]


def page_outputs(item: dict[str, Any], description: str) -> list[dict[str, Any]]:
    return [
        {
            "name": "items",
            "value_type": "array",
            "schema": {"type": "array", "items": item, "description": description},
        },
        _out("count", "integer", "integer", "How many rows this page holds."),
        _out("total", "integer", "integer", "How many rows Centas WS returned in all."),
        _out("page", "integer", "integer", "This page's number."),
        _out("has_more", "boolean", "boolean", "True when more rows follow."),
        _out("next_page", "integer", NULLABLE_INT, "The page to read next, or null."),
        WARNINGS_OUTPUT,
    ]


def take_outputs(item: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        {
            "name": "items",
            "value_type": "array",
            "schema": {
                "type": "array",
                "items": item,
                "description": "The records taken (empty when they do not fit the step "
                "output; then they are all in the file).",
            },
        },
        _out("count", "integer", "integer", "How many records were taken."),
        {
            "name": "file",
            "value_type": "artifact_handle",
            "schema": {
                "type": NULLABLE_TEXT,
                "description": "Centas WS's answer, whole, as an XML workflow file.",
            },
        },
        WARNINGS_OUTPUT,
    ]


DOCUMENT_SENT = [
    _out("number", "text", NULLABLE_TEXT, "The number sent."),
    _out("net_total", "text", NULLABLE_TEXT, "The net total sent."),
    _out("vat_total", "text", NULLABLE_TEXT, "The VAT total sent."),
    _out("total", "text", NULLABLE_TEXT, "The total sent."),
]
TOTALS = [
    amount("net_total", "Net total", "The total without VAT (bepvm_suma). " + TOTALS_RULE),
    amount("vat_total", "VAT total", "The VAT amount (pvm_suma)."),
    amount("total", "Total", "The total with VAT; must be net total + VAT total."),
]

LINE_CORE = {
    "code": _t("Product or service code (kodas).", 50),
    "name": _t("Name (pavadinimas).", 255),
    "unit": _t("Unit of measure, for example vnt. (matovnt).", 20),
    "quantity": _n("Quantity, greater than zero (kiekis)."),
    "price": _n("Unit price without VAT, up to 6 decimals (kaina)."),
    "vat_percent": _n("VAT rate in percent, 0 to 100 (pvmtar)."),
}
SALES_LINE = _obj(
    {
        **LINE_CORE,
        "kind": _t("Product or service mark, for example P (prek_pasl).", 5),
        "ean": _t("EAN barcode (ean).", 20),
        "vat_code": _t("VAT classifier code, for example PVM1 (Mok_kodas).", 20),
        "income_account": _t("Income account (sask_pajamos).", 20),
        "project": _t("Project (projektas).", 100),
        "vat_amount": _n("The line's VAT amount, 2 decimals (pvmsuma)."),
        "discount_percent": _n("Discount in percent (nuolaida_proc)."),
        "discount": _n("Discount amount, 2 decimals (nuolaida)."),
        "hs_code": _t("HS (customs) code (hs_code).", 20),
        "country_origin": _t("Country of origin (country_origin).", 20),
        "material": _t("Material (material).", 100),
    },
    ["code", "name", "unit", "quantity", "price", "vat_percent"],
)
ORDER_LINE = _obj(
    {**LINE_CORE, "supplier_code": _t("Supplier's code (t_kodas).", 50)},
    ["code", "quantity", "price", "vat_percent"],
)
PURCHASE_LINE = _obj(dict(LINE_CORE), ["code", "quantity", "price", "vat_percent"])
COMPANY_LINE = _obj(
    {
        **LINE_CORE,
        "kind": _t("Product or service mark, for example P (prek_pasl).", 5),
        "ean": _t("EAN barcode (ean).", 20),
        "vat_code": _t("VAT classifier code, for example PVM1 (mok_kodas).", 20),
    },
    ["code", "quantity", "price", "vat_percent"],
)
LINE_PLACEHOLDER = (
    '[{"code":"PRD-001","name":"Widget A","unit":"vnt","quantity":10,'
    '"price":"5.00","vat_percent":21}]'
)

DOCUMENT_KEY = {
    "type": _t("Document type, for example deb (type).", 20),
    "number": _t("Document number, exactly — no wildcards (number).", 50),
    "date": _d("Document date (date)."),
}

PRODUCT_FULL = record_schema(
    "A product: kodas, kaina, savikaina, likutis, pavadinimas, grupe1-4, gamintojas, "
    "svoris_neto, svoris_bruto, AnalogProducts, RecommendedProducts, Nuotrauka, aprasymas, "
    "barkodas, uzsak, sandel, stocks, parameters.",
    {
        "kodas": "Product code.",
        "kaina": "Price.",
        "savikaina": "Cost price.",
        "likutis": "Stock balance.",
        "pavadinimas": "Name.",
        "grupe1": "Group 1.",
        "grupe2": "Group 2.",
        "grupe3": "Group 3.",
        "grupe4": "Group 4.",
        "gamintojas": "Manufacturer.",
        "svoris_neto": "Net weight.",
        "svoris_bruto": "Gross weight.",
        "AnalogProducts": "Analog product codes.",
        "RecommendedProducts": "Recommended product codes.",
        "Nuotrauka": "Photo URL.",
        "aprasymas": "Description.",
        "barkodas": "Barcode.",
        "uzsak": "Ordered quantity.",
        "sandel": "Warehouse.",
        "stocks": "Stock by warehouse.",
        "parameters": "Product parameters.",
    },
)
PRODUCT_BASIC = record_schema(
    "A product: kodas, kaina, savikaina, likutis, stocks.",
    {
        "kodas": "Product code.",
        "kaina": "Price.",
        "savikaina": "Cost price.",
        "likutis": "Stock balance.",
        "stocks": "Stock by warehouse.",
    },
)
PRODUCT_CARD = record_schema(
    "A product card: id, kodas, pavadinimas, matovnt, kaina, pvmtar, likutis, Stocks, "
    "ProductParameters and any other field Centas WS sends.",
    {
        "id": "Product ID.",
        "kodas": "Product code.",
        "pavadinimas": "Name.",
        "matovnt": "Unit of measure.",
        "kaina": "Price.",
        "pvmtar": "VAT rate.",
        "likutis": "Stock balance.",
    },
    {
        "Stocks": "Stock by warehouse: WarehouseId, WarehouseName, Quantity.",
        "ProductParameters": "Parameters: Name, Value.",
    },
)
SALES_DOCUMENT = record_schema(
    "A sales document: type, dok_num, data, apmok_iki, pirkejas, dok_suma, pvm_suma, "
    "bepvm_suma, savikaina, im_kodas, pvm_kodas, apmoketa, dok_skola, eilute (rows).",
    {
        "type": "Document type.",
        "dok_num": "Number.",
        "data": "Date.",
        "apmok_iki": "Due date.",
        "pirkejas": "Buyer.",
        "dok_suma": "Total.",
        "pvm_suma": "VAT.",
        "bepvm_suma": "Net total.",
        "savikaina": "Cost.",
        "im_kodas": "Buyer company code.",
        "pvm_kodas": "Buyer VAT code.",
        "apmoketa": "Paid (0 or 1).",
        "dok_skola": "Remaining debt.",
    },
    {"eilute": "Rows: kodas, pavadinimas, matovnt, kiekis, kaina, pvmtar."},
)
ORDER = record_schema(
    "An order: uzsak_num, uzsak_data, uzsakovas, uzsak_suma, pvm_suma, bepvm_suma, eilute (rows).",
    {
        "uzsak_num": "Order number.",
        "uzsak_data": "Order date.",
        "uzsakovas": "Customer.",
        "uzsak_suma": "Total.",
        "pvm_suma": "VAT.",
        "bepvm_suma": "Net total.",
    },
    {"eilute": "Rows: kodas, pavadinimas, matovnt, kiekis, kaina, pvmtar."},
)
PURCHASE = record_schema(
    "A purchase: dok_num, data, apmok_iki, kontrah, dok_suma, pvm_suma, bepvm_suma, eilute (rows).",
    {
        "dok_num": "Number.",
        "data": "Date.",
        "apmok_iki": "Due date.",
        "kontrah": "Supplier.",
        "dok_suma": "Total.",
        "pvm_suma": "VAT.",
        "bepvm_suma": "Net total.",
    },
    {"eilute": "Rows: kodas, prek_pasl, pavadinimas, matovnt, kiekis, kaina, pvmtar, mok_kodas."},
)
PAYMENT = record_schema(
    "A payment: PaymentType, Date, Amount, DocNr, RefNr, Details, RecName, RecId, Receiver, "
    "ToAccountNumber.",
    {
        "PaymentType": "Payment type.",
        "Date": "Date.",
        "Amount": "Amount.",
        "DocNr": "Document number.",
        "RefNr": "Reference.",
        "Details": "Details.",
        "RecName": "Payer or payee name.",
        "RecId": "Payer or payee code.",
        "Receiver": "Receiver.",
        "ToAccountNumber": "Account number.",
    },
)
CONTRAHENT = record_schema(
    "A client or supplier: id, pavadinimas, imones_kodas, pvm_kodas, salis, miestas, "
    "adresas, email, telefonas, iban_nr, pirkejas, tiekejas, skola, padaliniai (branches).",
    {
        "id": "ID.",
        "pavadinimas": "Name.",
        "imones_kodas": "Company code.",
        "pvm_kodas": "VAT code.",
        "salis": "Country.",
        "miestas": "City.",
        "adresas": "Address.",
        "email": "E-mail.",
        "telefonas": "Phone.",
        "iban_nr": "IBAN.",
        "pirkejas": "Buyer (1 or 0).",
        "tiekejas": "Supplier (1 or 0).",
        "skola": "Debt.",
    },
    {"padaliniai": "Branches: pavad, adresas, salis, miestas."},
)

COUNT = "integer"


def _counts(*pairs: tuple[str, str]) -> list[dict[str, Any]]:
    return [_out(name, "integer", NULLABLE_INT, note) for name, note in pairs]


# -- the steps --------------------------------------------------------------------------

GROUPS = [
    "Sales",
    "Orders",
    "Purchases",
    "Payments",
    "Products",
    "Clients and suppliers",
    "Consignments",
    "Connection",
]


def _step(
    operation_id: str,
    display_name: str,
    group: str,
    kind: str,
    path: str,
    description: str,
    inputs: list[dict[str, Any]],
    outputs: list[dict[str, Any]],
    *,
    take: bool = False,
) -> dict[str, Any]:
    return {
        "operation_id": operation_id,
        "display_name": display_name,
        "group": group,
        "kind": kind,
        "take": take,
        "path": path,
        "description": description,
        "inputs": inputs,
        "outputs": outputs,
    }


def _sales_steps() -> list[dict[str, Any]]:
    return [
        _step(
            "send_sales_invoice",
            "Send a sales invoice to Centas",
            "Sales",
            "action",
            "POST /documents/create",
            "Sends a sales invoice with its lines and returns its document ID. Centas WS "
            "refuses a number it already has (a conflict, nothing saved). "
            + RECEIVED
            + " "
            + REPEATS.format(noun="invoice under the automatic number"),
            [
                text(
                    "number",
                    "Invoice number",
                    "The invoice number (dok_num), or auto for Centas's automatic numbering.",
                    max_length=50,
                    required=True,
                ),
                date("date", "Date", "The invoice date (data).", required=True),
                date("due_date", "Due date", "The payment due date (apmok_iki).", required=True),
                text(
                    "buyer_name",
                    "Buyer name",
                    "The buyer's name (pirkejas).",
                    max_length=255,
                    required=True,
                ),
                amount(
                    "cost", "Cost", "The document's cost price total (savikaina).", required=True
                ),
                records(
                    "lines",
                    "Lines",
                    "The invoice lines, 1 to 500: code, name, unit, quantity, price "
                    "without VAT, vat_percent; optionally kind, ean, vat_code, "
                    "income_account, project, vat_amount, discount_percent, discount, "
                    "hs_code, country_origin, material.",
                    SALES_LINE,
                    placeholder=LINE_PLACEHOLDER,
                ),
                *TOTALS,
                text(
                    "buyer_company_code",
                    "Buyer company code",
                    "The buyer's company code (im_kodas).",
                    max_length=50,
                ),
                text(
                    "buyer_vat_code",
                    "Buyer VAT code",
                    "The buyer's VAT code (pvm_kodas).",
                    max_length=50,
                ),
                text(
                    "buyer_country", "Buyer country", "The buyer's country (salis).", max_length=100
                ),
                text("buyer_city", "Buyer city", "The buyer's city (miestas).", max_length=100),
                text(
                    "buyer_address",
                    "Buyer address",
                    "The buyer's address (adresas).",
                    max_length=255,
                ),
                text("buyer_email", "Buyer e-mail", "The buyer's e-mail (email).", max_length=255),
                text(
                    "number_series",
                    "Number series",
                    "The document number series (dok_num_series).",
                    max_length=20,
                ),
                text(
                    "order_number",
                    "Order number",
                    "The related order number (uzsaknr).",
                    max_length=50,
                ),
                text(
                    "check_order",
                    "Check order",
                    "Check the related order (check_order).",
                    max_length=50,
                ),
                text("document_type", "Document type", "The document type (type).", max_length=20),
                text(
                    "transaction_id",
                    "Transaction ID",
                    "Transaction ID for a number from Centas's invoice forms (trans_id).",
                    max_length=50,
                ),
                text(
                    "buyer_code",
                    "Buyer code",
                    "The buyer's code in your systems (kl_kodas).",
                    max_length=50,
                ),
                choice(
                    "buyer_eu_type",
                    "Buyer EU type",
                    "local (0), another EU country (1) or outside the EU (2) (estipas).",
                    {"local": "Local", "eu": "Another EU country", "non_eu": "Outside the EU"},
                ),
                text(
                    "buyer_group", "Buyer group", "The group of a new buyer (grupe).", max_length=50
                ),
                text(
                    "vat_payable_account",
                    "VAT payable account",
                    "VAT payable account, digits (sask_moketpvm).",
                    max_length=20,
                    pattern=r"^\d+$",
                ),
                text(
                    "receivable_account",
                    "Receivable account",
                    "Buyer debt account (sask_pirkskol).",
                    max_length=20,
                ),
                text(
                    "income_account",
                    "Income account",
                    "Income account, digits (sask_pajamos).",
                    max_length=20,
                    pattern=r"^\d+$",
                ),
                text("project", "Project", "Project or cost centre (projektas).", max_length=100),
                text(
                    "operation_description",
                    "Operation description",
                    "Extra description of the operation (oper_apras).",
                    max_length=255,
                ),
                text("note", "Note", "A note on the document (pastaba).", max_length=1000),
                text("issued_by", "Issued by", "Who issued it (israse_asmuo).", max_length=100),
                text(
                    "issued_by_position",
                    "Issuer's position",
                    "The issuer's position (israse_pareigos).",
                    max_length=100,
                ),
                text(
                    "intrastat_transport",
                    "Intrastat transport",
                    "Intrastat transport code (intrs_transprusis).",
                    max_length=20,
                ),
                text(
                    "intrastat_delivery_terms",
                    "Intrastat delivery terms",
                    "Intrastat delivery terms code (intrs_pristsal).",
                    max_length=20,
                ),
                text(
                    "intrastat_transaction",
                    "Intrastat transaction",
                    "Intrastat transaction code (intrs_sandoris).",
                    max_length=20,
                ),
                text(
                    "intrastat_county",
                    "Intrastat county",
                    "Intrastat county code (intrs_apskritis).",
                    max_length=20,
                ),
                text(
                    "intrastat_eu_country",
                    "Intrastat EU country",
                    "Intrastat EU country code (intrs_eusalis).",
                    max_length=20,
                ),
            ],
            [
                _out("document_id", "text", NULLABLE_TEXT, "The document ID Centas WS returned."),
                *DOCUMENT_SENT,
                WARNINGS_OUTPUT,
            ],
        ),
        _step(
            "get_sales_document",
            "Get a sales document by number",
            "Sales",
            "source",
            "GET /documents/get",
            "Reads one sales document by its number, with the fields Centas WS returns.",
            [
                text(
                    "number",
                    "Document number",
                    "The document number.",
                    max_length=50,
                    required=True,
                )
            ],
            [
                _out("found", "boolean", "boolean", "True when Centas WS returned the document."),
                {
                    "name": "document",
                    "value_type": "object",
                    "schema": {
                        "type": ["object", "null"],
                        "additionalProperties": True,
                        "description": "The document as Centas WS returns it, or null.",
                    },
                },
                WARNINGS_OUTPUT,
            ],
        ),
        _step(
            "get_sales_documents",
            "Get sales documents by date or unpaid",
            "Sales",
            "source",
            "GET /documents/export (from, to, unpaid)",
            "Reads sales documents of a date range, or all unpaid ones, with their rows. With "
            "these filters Centas WS ignores its downloaded mark, so nothing is taken from "
            "the queue.",
            [
                date("date_from", "From date", "Only documents on or after this date."),
                date("date_to", "To date", "Only documents on or before this date."),
                flag("unpaid", "Unpaid only", "Only unpaid documents (apmoketa = 0)."),
                *paging(),
            ],
            page_outputs(SALES_DOCUMENT, "The documents of this page."),
        ),
        _step(
            "take_new_sales_documents",
            "Take new sales documents from the Centas WS queue",
            "Sales",
            "action",
            "GET /documents/export",
            "Reads the sales documents not yet marked as downloaded. " + TAKES,
            [],
            take_outputs(SALES_DOCUMENT),
            take=True,
        ),
        _step(
            "update_sales_documents",
            "Update sales documents' payment status",
            "Sales",
            "action",
            "POST /documents/update",
            "Sets the downloaded mark, the paid mark or the remaining debt of sales documents "
            "named by type, number and date; fields not given stay unchanged.",
            [
                records(
                    "documents",
                    "Documents",
                    "The documents, 1 to 500: type, number, date and at least one of "
                    "downloaded, paid, remaining_debt.",
                    _obj(
                        {
                            **DOCUMENT_KEY,
                            "downloaded": _b("Mark as downloaded, or not (downloaded)."),
                            "paid": _b("Paid, or not (apmoketa)."),
                            "remaining_debt": _n("Remaining unpaid amount (dok_skola)."),
                        },
                        ["type", "number", "date"],
                    ),
                    placeholder='[{"type":"deb","number":"DOK-001","date":"2024-01-01",'
                    '"paid":true,"remaining_debt":"0.00"}]',
                )
            ],
            [
                _out("sent", "integer", COUNT, "How many documents were sent."),
                *_counts(
                    ("documents_found", "How many Centas WS found."),
                    ("documents_updated", "How many it updated."),
                ),
                WARNINGS_OUTPUT,
            ],
        ),
        _step(
            "record_document_payments",
            "Record payments against sales documents",
            "Sales",
            "action",
            "POST /documents/payments/create",
            "Records payments against sales documents named by type, number and date, with "
            "the amount paid and the payments themselves. " + REPEATS.format(noun="payment"),
            [
                records(
                    "documents",
                    "Documents",
                    "The documents, 1 to 500: type, number, date, paid_sum, paid_in_full, "
                    "customer_id and payments [{date, number, description, total}].",
                    _obj(
                        {
                            **DOCUMENT_KEY,
                            "paid_sum": _n("Amount paid (paid_sum)."),
                            "paid_in_full": _b("Paid in full (paid_full)."),
                            "customer_id": _t("Customer ID (customerId).", 50),
                            "payments": {
                                "type": "array",
                                "maxItems": 100,
                                "description": "The payments (payment).",
                                "items": _obj(
                                    {
                                        "date": _d("Payment date."),
                                        "number": _t("Payment number.", 50),
                                        "description": _t("Description.", 500),
                                        "total": _n("Amount."),
                                    },
                                    ["date", "number", "total"],
                                ),
                            },
                        },
                        ["type", "number", "date", "paid_sum", "payments"],
                    ),
                    placeholder='[{"type":"deb","number":"INV-001","date":"2024-01-15",'
                    '"paid_sum":"121.00","paid_in_full":true,"payments":[{"date":'
                    '"2024-01-20","number":"PAY-001","total":"121.00"}]}]',
                )
            ],
            [
                _out("sent", "integer", COUNT, "How many documents were sent."),
                *_counts(
                    ("documents_payments_found_xml", "How many Centas WS found."),
                    ("documents_payments_created", "How many payments it created."),
                ),
                WARNINGS_OUTPUT,
            ],
        ),
        _step(
            "delete_sales_documents",
            "Delete sales documents",
            "Sales",
            "action",
            "POST /documents/delete",
            "Deletes sales documents from Centas WS, each named exactly by type, number and "
            "date — at most 50, no wildcards. A deleted document cannot be read back.",
            [
                records(
                    "documents",
                    "Documents",
                    "The documents to delete, 1 to 50: type, number, date.",
                    _obj(dict(DOCUMENT_KEY), ["type", "number", "date"]),
                    max_items=50,
                    placeholder='[{"type":"deb","number":"DOK-001","date":"2024-01-01"}]',
                )
            ],
            [
                _out("sent", "integer", COUNT, "How many documents were named."),
                *_counts(
                    ("documents_found", "How many Centas WS found."),
                    ("documents_deleted", "How many it deleted."),
                ),
                WARNINGS_OUTPUT,
            ],
        ),
    ]


def _order_and_purchase_steps() -> list[dict[str, Any]]:
    return [
        _step(
            "send_order",
            "Send a customer order to Centas",
            "Orders",
            "action",
            "POST /orders/create",
            "Sends a customer order with its lines and returns its order ID. "
            + RECEIVED
            + " "
            + REPEATS.format(noun="order"),
            [
                text(
                    "number",
                    "Order number",
                    "The order number, unique (uzsak_num).",
                    max_length=50,
                    required=True,
                ),
                date("date", "Order date", "The order date (uzsak_data).", required=True),
                text(
                    "customer_name",
                    "Customer name",
                    "The customer's name (uzsakovas).",
                    max_length=255,
                    required=True,
                ),
                records(
                    "lines",
                    "Lines",
                    "The order lines, 1 to 500: code, name, unit, quantity, price without "
                    "VAT, vat_percent, supplier_code.",
                    ORDER_LINE,
                    placeholder=LINE_PLACEHOLDER,
                ),
                *TOTALS[:2],
                amount(
                    "total",
                    "Total",
                    "The order total with VAT; must be net total + VAT total (uzsak_suma).",
                ),
                date("delivery_date", "Delivery date", "The delivery date (pristat_data)."),
                text("carrier", "Carrier", "The carrier (vezejas).", max_length=100),
                text("comment", "Comment", "A comment (komentaras).", max_length=1000),
                text(
                    "customer_note",
                    "Customer note",
                    "The customer's note (uzsakovas_pastaba).",
                    max_length=1000,
                ),
                text(
                    "delivery_branch",
                    "Delivery branch",
                    "The delivery branch (uzsak_padalinys).",
                    max_length=255,
                ),
                text(
                    "delivery_branch_gln",
                    "Delivery branch GLN",
                    "The delivery branch's GLN code (uzsak_padalinys_gln).",
                    max_length=20,
                ),
                text(
                    "delivery_branch_iln",
                    "Delivery branch ILN",
                    "The delivery branch's ILN code (uzsak_padalinys_iln).",
                    max_length=20,
                ),
                text(
                    "customer_iln",
                    "Customer ILN",
                    "The customer's ILN code (uzsak_iln).",
                    max_length=20,
                ),
                text(
                    "customer_company_code",
                    "Customer company code",
                    "Company registration code (im_kodas).",
                    max_length=50,
                ),
                text(
                    "customer_vat_code", "Customer VAT code", "VAT code (pvm_kodas).", max_length=50
                ),
                text("customer_country", "Customer country", "Country (salis).", max_length=100),
                text("customer_city", "Customer city", "City (miestas).", max_length=100),
                text("customer_address", "Customer address", "Address (adresas).", max_length=255),
                text("customer_email", "Customer e-mail", "E-mail (email).", max_length=255),
                text("customer_phone", "Customer phone", "Phone (tel).", max_length=50),
                text("postal_code", "Postal code", "Postal code (pasto_kodas).", max_length=20),
                text(
                    "receivable_account",
                    "Receivable account",
                    "Customer debt account (pirk_skolsask).",
                    max_length=20,
                ),
                text("warehouse", "Warehouse", "Warehouse (sandelis).", max_length=50),
                date("execution_date", "Execution date", "When to carry it out (vykd_data)."),
                date("payment_date", "Payment date", "The payment date (apmok_data)."),
                date("arrival_date", "Arrival date", "The arrival date (atvyk_data)."),
                date("departure_date", "Departure date", "The departure date (isvyk_data)."),
            ],
            [
                _out("order_id", "text", NULLABLE_TEXT, "The order ID Centas WS returned."),
                *DOCUMENT_SENT,
                WARNINGS_OUTPUT,
            ],
        ),
        _step(
            "take_new_orders",
            "Take new orders from the Centas WS queue",
            "Orders",
            "action",
            "GET /orders/export",
            "Reads the orders not yet marked as downloaded. " + TAKES,
            [],
            take_outputs(ORDER),
            take=True,
        ),
        _step(
            "get_order_invoice_pdf",
            "Get the invoice PDF of an order",
            "Orders",
            "source",
            "GET /orders/document/pdf",
            "Saves the PDF of the invoice issued for an order as a workflow file, or only "
            "checks whether there is one.",
            [
                text(
                    "order_number",
                    "Order number",
                    "The order number.",
                    max_length=50,
                    required=True,
                ),
                flag("check_only", "Check only", "Only check whether the PDF exists."),
            ],
            [
                _out("exists", "boolean", "boolean", "True when the order has an invoice PDF."),
                {
                    "name": "file",
                    "value_type": "artifact_handle",
                    "schema": {
                        "type": NULLABLE_TEXT,
                        "description": "The PDF, as a workflow file.",
                    },
                },
                _out("size_bytes", "integer", NULLABLE_INT, "The PDF's size."),
                WARNINGS_OUTPUT,
            ],
        ),
        _step(
            "send_purchase_invoice",
            "Send a purchase invoice to Centas",
            "Purchases",
            "action",
            "POST /documents/purchase/import",
            "Sends a supplier's invoice with its lines and returns its purchase ID. "
            + RECEIVED
            + " "
            + REPEATS.format(noun="invoice"),
            [
                text(
                    "seller_name",
                    "Seller name",
                    "The supplier's name (kontrah).",
                    max_length=255,
                    required=True,
                ),
                text(
                    "number",
                    "Invoice number",
                    "The supplier's invoice number (dok_num).",
                    max_length=50,
                    required=True,
                ),
                date("date", "Date", "The invoice date (data).", required=True),
                records(
                    "lines",
                    "Lines",
                    "The invoice lines, 1 to 500: code, name, unit, quantity, price "
                    "without VAT, vat_percent.",
                    PURCHASE_LINE,
                    placeholder=LINE_PLACEHOLDER,
                ),
                *TOTALS,
            ],
            [
                _out("purchase_id", "text", NULLABLE_TEXT, "The purchase ID Centas WS returned."),
                *DOCUMENT_SENT,
                WARNINGS_OUTPUT,
            ],
        ),
        _step(
            "send_invoice_to_company",
            "Send an invoice to another company's Centas",
            "Purchases",
            "action",
            "POST /purchase/import",
            "Sends your sales invoice to the receiving company's Centas WS as their purchase, "
            "with its lines and optionally its PDF. With Send e-mail on, Centas WS also "
            "e-mails the receiver. " + REPEATS.format(noun="invoice"),
            [
                text(
                    "receiver_company_code",
                    "Receiver company code",
                    "The receiver's company code (gavejas im_kodas).",
                    max_length=50,
                ),
                text(
                    "receiver_vat_code",
                    "Receiver VAT code",
                    "The receiver's VAT code (gavejas pvm_kodas).",
                    max_length=50,
                ),
                text(
                    "receiver_name",
                    "Receiver name",
                    "The receiver's name (gavejas kontrah).",
                    max_length=255,
                ),
                text(
                    "receiver_email",
                    "Receiver e-mail",
                    "The receiver's e-mail (email).",
                    max_length=255,
                ),
                text("receiver_country", "Receiver country", "Country (salis).", max_length=100),
                text("receiver_city", "Receiver city", "City (miestas).", max_length=100),
                text("receiver_address", "Receiver address", "Address (adresas).", max_length=255),
                text(
                    "receiver_telema_id",
                    "Receiver Telema ID",
                    "Telema ID (telema_id).",
                    max_length=50,
                ),
                text(
                    "receiver_edisoft_iln",
                    "Receiver Edisoft ILN",
                    "Edisoft ILN (edisoft_iln).",
                    max_length=50,
                ),
                flag(
                    "send_email",
                    "Send e-mail",
                    "Have Centas WS e-mail the receiver about the invoice (send_email). Off "
                    "unless chosen.",
                ),
                text(
                    "number",
                    "Invoice number",
                    "The invoice number (dok_num).",
                    max_length=50,
                    required=True,
                ),
                date("date", "Date", "The invoice date (data).", required=True),
                date("due_date", "Due date", "The payment due date (apmok_iki)."),
                text(
                    "seller_name",
                    "Seller name",
                    "Your company's name (dokumentas kontrah).",
                    max_length=255,
                ),
                text(
                    "document_type",
                    "Document type",
                    "The document type, for example deb (DocType).",
                    max_length=20,
                ),
                text(
                    "country_code",
                    "Country code",
                    "Country code, for example LT (salis_kodas).",
                    max_length=2,
                ),
                flag("paid", "Paid", "Already paid (apmoketa)."),
                amount("remaining_debt", "Remaining debt", "Remaining unpaid amount (dok_skola)."),
                artifact(
                    "pdf_file",
                    "PDF",
                    "The invoice PDF from an earlier step, up to 8 MB (pdf_base64).",
                ),
                text(
                    "pdf_name",
                    "PDF name",
                    "The PDF's file name (pdf_name). Default: the invoice number.",
                    max_length=100,
                ),
                records(
                    "lines",
                    "Lines",
                    "The invoice lines, 1 to 500: code, name, unit, quantity, price "
                    "without VAT, vat_percent; optionally kind, ean, vat_code.",
                    COMPANY_LINE,
                    placeholder=LINE_PLACEHOLDER,
                ),
                *TOTALS,
            ],
            [
                *DOCUMENT_SENT,
                _out("email_requested", "boolean", "boolean", "Whether an e-mail was asked for."),
                *_counts(
                    ("purchase_rows_created", "Purchase rows created."),
                    ("document_rows_created", "Document rows created."),
                ),
                _out(
                    "email_sent",
                    "boolean",
                    ["boolean", "null"],
                    "Whether Centas WS sent the e-mail.",
                ),
                WARNINGS_OUTPUT,
            ],
        ),
        _step(
            "get_purchases",
            "Get purchases for a date range",
            "Purchases",
            "source",
            "GET /purchase/export (from, to)",
            "Reads the purchases of a date range with their rows. With a date range Centas WS "
            "leaves its downloaded mark unchanged, so nothing is taken from the queue.",
            [
                date("date_from", "From date", "The first day.", required=True),
                date("date_to", "To date", "The last day.", required=True),
                *paging(),
            ],
            page_outputs(PURCHASE, "The purchases of this page."),
        ),
        _step(
            "take_new_purchases",
            "Take new purchases from the Centas WS queue",
            "Purchases",
            "action",
            "GET /purchase/export",
            "Reads the purchases not yet downloaded. " + TAKES,
            [],
            take_outputs(PURCHASE),
            take=True,
        ),
    ]


PRODUCT_ITEM = _obj(
    {
        "code": _t("Product code (kodas).", 50),
        "id": _t("Product ID in Centas WS (id).", 20),
        "name": _t("Name (pavadinimas).", 255),
        "unit": _t("Unit of measure (matovnt).", 20),
        "price": _n("Price, up to 6 decimals (kaina)."),
        "cost": _n("Cost price (savikaina)."),
        "vat_percent": _n("VAT rate in percent (pvmtar)."),
        "stock": _n("Stock balance (likutis)."),
        "group1": _t("Group 1 (grupe1).", 100),
        "group2": _t("Group 2 (grupe2).", 100),
        "group3": _t("Group 3 (grupe3).", 100),
        "group4": _t("Group 4 (grupe4).", 100),
        "barcode": _t("Barcode (barkodas).", 50),
        "description": _t("Description (aprasymas).", 4000),
        "manufacturer": _t("Manufacturer (gamintojas).", 255),
        "net_weight": _n("Net weight (svoris_neto)."),
        "gross_weight": _n("Gross weight (svoris_bruto)."),
        "analog_products": {
            "type": "array",
            "maxItems": 100,
            "items": {"type": "string", "maxLength": 50},
            "description": "Analog product codes (AnalogProducts).",
        },
        "recommended_products": {
            "type": "array",
            "maxItems": 100,
            "items": {"type": "string", "maxLength": 50},
            "description": "Recommended product codes (RecommendedProducts).",
        },
        "photo": _t("Photo URL (Nuotrauka).", 500),
        "vat_code": _t("VAT classifier code (mok_kodas).", 20),
        "ordered": _n("Ordered quantity (uzsak)."),
        "warehouse": _t("Warehouse (sandel).", 50),
        "stocks": {
            "type": "array",
            "maxItems": 100,
            "description": "Stock by warehouse (Stocks).",
            "items": _obj(
                {
                    "warehouse_id": _t("WarehouseId.", 50),
                    "warehouse_name": _t("WarehouseName.", 255),
                    "quantity": _n("Quantity."),
                },
                ["warehouse_id", "quantity"],
            ),
        },
        "parameters": {
            "type": "array",
            "maxItems": 100,
            "description": "Parameters (ProductParameters).",
            "items": _obj({"name": _t("Name.", 255), "value": _t("Value.", 1000)}, ["name"]),
        },
    },
    ["code"],
)
CONTRAHENT_ITEM = _obj(
    {
        "name": _t("Name (pavadinimas).", 255),
        "id": _t("ID in Centas WS (id).", 20),
        "company_code": _t("Company code (imones_kodas).", 50),
        "vat_code": _t("VAT code (pvm_kodas).", 50),
        "country": _t("Country (salis).", 100),
        "city": _t("City (miestas).", 100),
        "address": _t("Address (adresas).", 255),
        "email": _t("E-mail (email).", 255),
        "phone": _t("Phone (telefonas).", 50),
        "iban": _t("IBAN (iban_nr).", 50),
        "is_buyer": _b("A buyer (pirkejas)."),
        "is_supplier": _b("A supplier (tiekejas)."),
        "debt": _n("Debt (skola)."),
        "telema_id": _t("Telema ID (telema_id).", 50),
        "edisoft_iln": _t("Edisoft ILN (edisoft_iln).", 50),
        "branches": {
            "type": "array",
            "maxItems": 100,
            "description": "Branches (padaliniai).",
            "items": _obj(
                {
                    "name": _t("Name (pavad).", 255),
                    "address": _t("Address.", 255),
                    "country": _t("Country.", 100),
                    "city": _t("City.", 100),
                },
                ["name"],
            ),
        },
    },
    ["name"],
)


def _other_steps() -> list[dict[str, Any]]:
    return [
        _step(
            "send_payments",
            "Send bank and cash payments to Centas",
            "Payments",
            "action",
            "POST /payments/import",
            "Sends payments in one batch and returns how many Centas WS created. "
            + RECEIVED
            + " "
            + REPEATS.format(noun="payment"),
            [
                records(
                    "payments",
                    "Payments",
                    "The payments, 1 to 500: type (BankDeb, CashDeb, BankCred, CashDeb2), "
                    "date, amount, document_number, details, payer_name; optionally "
                    "reference, payer_code, receiver, account.",
                    _obj(
                        {
                            "type": {
                                "type": "string",
                                "enum": PAYMENT_TYPES,
                                "description": "Payment type (PaymentType).",
                            },
                            "date": _d("Date (Date)."),
                            "amount": _n("Amount, greater than zero, 2 decimals (Amount)."),
                            "document_number": _t("Document number (DocNr).", 50),
                            "details": _t("Details (Details).", 500),
                            "payer_name": _t("Payer or payee name (RecName).", 255),
                            "reference": _t("Reference, unique in the batch (RefNr).", 100),
                            "payer_code": _t("Payer or payee code (RecId).", 50),
                            "receiver": _t("Receiver (Receiver).", 255),
                            "account": _t("Account number (ToAccountNumber).", 50),
                        },
                        ["type", "date", "amount", "document_number", "details", "payer_name"],
                    ),
                    placeholder='[{"type":"BankDeb","date":"2024-01-15","amount":"121.00",'
                    '"document_number":"PAY-001","details":"Payment for INV-001",'
                    '"payer_name":"UAB Customer"}]',
                )
            ],
            [
                _out("sent", "integer", COUNT, "How many payments were sent."),
                *_counts(
                    ("payments_found_xml", "How many Centas WS found."),
                    ("payments_created", "How many it created."),
                ),
                WARNINGS_OUTPUT,
            ],
        ),
        _step(
            "take_new_payments",
            "Take new payments from the Centas WS queue",
            "Payments",
            "action",
            "GET /payments/export, /payments/export/{type}",
            "Reads the payments not yet exported, all or of one type. " + TAKES,
            [
                choice(
                    "payment_type",
                    "Payment type",
                    "Only payments of this type.",
                    {k: k for k in PAYMENT_TYPES},
                )
            ],
            take_outputs(PAYMENT),
            take=True,
        ),
        _step(
            "get_products",
            "Get products",
            "Products",
            "source",
            "GET /products/export/json/full",
            "Reads every product with all its fields, one page at a time. " + FROM_PROGRAM,
            paging(),
            page_outputs(PRODUCT_FULL, "The products of this page."),
        ),
        _step(
            "get_product",
            "Get a product by code",
            "Products",
            "source",
            "GET /products/export/json/one",
            "Reads one product with all its fields. " + FROM_PROGRAM,
            [
                text(
                    "code",
                    "Product code",
                    "The product code (kodas).",
                    max_length=50,
                    required=True,
                )
            ],
            [
                _out("found", "boolean", "boolean", "True when the product exists."),
                {
                    "name": "product",
                    "value_type": "object",
                    "schema": {**PRODUCT_FULL, "type": ["object", "null"]},
                },
                WARNINGS_OUTPUT,
            ],
        ),
        _step(
            "get_product_stock",
            "Get product prices and stock",
            "Products",
            "source",
            "GET /products/export/json",
            "Reads products' price, cost, stock and stock by warehouse, optionally of one "
            "barcode. " + FROM_PROGRAM,
            [
                text(
                    "barcode",
                    "Barcode",
                    "Only the product with this barcode (barkodas).",
                    max_length=50,
                ),
                *paging(),
            ],
            page_outputs(PRODUCT_BASIC, "The products of this page."),
        ),
        _step(
            "get_product_cards",
            "Get product cards with units and VAT rates",
            "Products",
            "source",
            "GET /products/export",
            "Reads product cards with unit, VAT rate, stock by warehouse and parameters; or "
            "one card by its ID. " + FROM_PROGRAM,
            [whole("id", "Product ID", "Only this product (its ID in Centas WS)."), *paging()],
            page_outputs(PRODUCT_CARD, "The product cards of this page."),
        ),
        _step(
            "get_product_gallery_link",
            "Get a product's gallery link",
            "Products",
            "source",
            "GET /products/gallery",
            "Returns the link to a product's image gallery.",
            [whole("product_id", "Product ID", "The product's ID in Centas WS.", required=True)],
            [_out("link", "text", NULLABLE_TEXT, "The gallery's address."), WARNINGS_OUTPUT],
        ),
        _step(
            "send_products",
            "Send products to Centas",
            "Products",
            "action",
            "POST /products/import",
            "Sends product cards in one batch; Centas WS creates new ones and updates known "
            "ones and returns the counts. Only the fields given are sent. "
            + REPEATS.format(noun="product"),
            [
                records(
                    "products",
                    "Products",
                    "The products, 1 to 500: code and any of id, name, unit, price, cost, "
                    "vat_percent, stock, group1-4, barcode, description, manufacturer, "
                    "net_weight, gross_weight, analog_products, recommended_products, photo, "
                    "vat_code, ordered, warehouse, stocks, parameters.",
                    PRODUCT_ITEM,
                    placeholder='[{"code":"PRD-001","name":"Widget A","unit":"vnt",'
                    '"price":"10.00","vat_percent":21}]',
                )
            ],
            [
                _out("sent", "integer", COUNT, "How many products were sent."),
                *_counts(
                    ("products_found_xml", "How many Centas WS found."),
                    ("products_created", "How many it created."),
                    ("products_updated", "How many it updated."),
                ),
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
        ),
        _step(
            "send_contrahents",
            "Send clients and suppliers to Centas",
            "Clients and suppliers",
            "action",
            "POST /contrahents/import",
            "Sends clients and suppliers in one batch; Centas WS creates new ones and updates "
            "known ones. When branches are given, Centas WS may delete branches it has that "
            "are not among them (it reports how many). " + REPEATS.format(noun="client"),
            [
                records(
                    "contrahents",
                    "Clients and suppliers",
                    "1 to 500: name and any of id, company_code, vat_code, country, city, "
                    "address, email, phone, iban, is_buyer, is_supplier, debt, telema_id, "
                    "edisoft_iln, branches [{name, address, country, city}].",
                    CONTRAHENT_ITEM,
                    placeholder='[{"name":"UAB Partner","company_code":"123456789",'
                    '"vat_code":"LT123456789","is_buyer":true}]',
                )
            ],
            [
                _out("sent", "integer", COUNT, "How many were sent."),
                *_counts(
                    ("contrahents_found_xml", "How many Centas WS found."),
                    ("contrahents_created", "How many it created."),
                    ("contrahents_updated", "How many it updated."),
                    ("branches_created", "Branches created."),
                    ("branches_updated", "Branches updated."),
                    ("branches_deleted", "Branches deleted."),
                ),
                WARNINGS_OUTPUT,
            ],
        ),
        _step(
            "get_contrahents",
            "Get clients and suppliers",
            "Clients and suppliers",
            "source",
            "GET /contrahents/export",
            "Reads clients and suppliers with their branches; or one by its ID. " + FROM_PROGRAM,
            [whole("id", "ID", "Only this client or supplier (its ID in Centas WS)."), *paging()],
            page_outputs(CONTRAHENT, "The clients and suppliers of this page."),
        ),
        _step(
            "find_company_by_code",
            "Find a company's name by its code",
            "Clients and suppliers",
            "source",
            "GET /contrahents/search",
            "Looks a company up by its registration code and returns its name.",
            [
                text(
                    "code",
                    "Company code",
                    "The company registration code.",
                    max_length=50,
                    required=True,
                )
            ],
            [
                _out("found", "boolean", "boolean", "True when a company was found."),
                _out("name", "text", NULLABLE_TEXT, "The company's name."),
                WARNINGS_OUTPUT,
            ],
        ),
        _step(
            "send_consignment",
            "Send a consignment note to Centas",
            "Consignments",
            "action",
            "POST /consignments/import",
            "Sends a consignment note (waybill) with its lines. "
            + REPEATS.format(noun="consignment note"),
            [
                text(
                    "document_uid",
                    "Document UID",
                    "The consignment's unique ID (DocumentUID).",
                    max_length=100,
                    required=True,
                ),
                text(
                    "document_number",
                    "Document number",
                    "The related document number (DocumentNumber).",
                    max_length=50,
                    required=True,
                ),
                date(
                    "document_date",
                    "Document date",
                    "The document date (DocumentDate).",
                    required=True,
                ),
                date(
                    "estimated_arrival",
                    "Estimated arrival",
                    "Estimated time of arrival (EstimatedTimeOfArrival).",
                ),
                text(
                    "consignee_name",
                    "Consignee name",
                    "The consignee (ConsigneeName).",
                    max_length=255,
                    required=True,
                ),
                text(
                    "consignee_code",
                    "Consignee code",
                    "The consignee's registration number (ConsigneeRegistrationNumber).",
                    max_length=50,
                ),
                records(
                    "lines",
                    "Lines",
                    "1 to 500: description, unit, quantity.",
                    _obj(
                        {
                            "description": _t("Product description (ProductDescription).", 255),
                            "unit": _t("Unit of measure (UnitOfMeasure).", 20),
                            "quantity": _n("Quantity (Quantity)."),
                        },
                        ["description", "unit", "quantity"],
                    ),
                    placeholder='[{"description":"Widget A","unit":"vnt","quantity":100}]',
                ),
            ],
            [
                _out("lines_sent", "integer", COUNT, "How many lines were sent."),
                *_counts(("consignment_rows_created", "How many rows Centas WS created.")),
                WARNINGS_OUTPUT,
            ],
        ),
        _step(
            "test_connection",
            "Test the connection",
            "Connection",
            "source",
            "GET /verify",
            "Checks the WS key and returns until when it is valid; warns 30 days before it "
            "expires.",
            [],
            [
                _out("connected", "boolean", "boolean", "True when Centas WS accepted the key."),
                _out("valid_until", "text", NULLABLE_TEXT, "Until when the key is valid."),
                _out("days_left", "integer", NULLABLE_INT, "Days until it expires."),
                WARNINGS_OUTPUT,
            ],
        ),
        _step(
            "get_statistics",
            "Get counts of new documents",
            "Connection",
            "source",
            "GET /statistics",
            "Counts the new invoices, orders, purchases and payments waiting in Centas WS, "
            "without taking them, and the key's expiry. Works with an expired key too.",
            [],
            [
                *_counts(
                    ("new_invoices", "New invoices."),
                    ("new_orders", "New orders."),
                    ("new_purchases", "New purchases."),
                    ("new_payments_bd", "New bank debit payments."),
                    ("new_payments_cd", "New cash debit payments."),
                    ("new_payments_cd2", "New cash debit 2 payments."),
                    ("new_payments_bc", "New bank credit payments."),
                ),
                _out("token_valid_until", "text", NULLABLE_TEXT, "Until when the key is valid."),
                WARNINGS_OUTPUT,
            ],
        ),
        _step(
            "check_service",
            "Check that Centas WS is running",
            "Connection",
            "source",
            "GET /test",
            "Asks Centas WS whether it is running; uses no key.",
            [],
            [
                _out("running", "boolean", "boolean", "True when Centas WS answered ok."),
                _out("status", "text", NULLABLE_TEXT, "The status Centas WS gave."),
                WARNINGS_OUTPUT,
            ],
        ),
    ]


def steps() -> list[dict[str, Any]]:
    """Every step, in the order the step picker and the Centas API page show them."""
    return [*_sales_steps(), *_order_and_purchase_steps(), *_other_steps()]


__all__ = ["GROUPS", "steps"]
