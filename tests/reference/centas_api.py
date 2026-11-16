"""Facts extracted from the Centas API documentation, field by field.

Source: https://centas.gitbook.io/docs/master.md, SHA-256
52b970595b1dcec8421e748251e250a96faffe1e0b8da42020e617aafb4e22b9, retrieved
2026-11-16 (runtime/reference.py). The text itself is not copied into this
repository; only the endpoint and field names and where each one goes.

Every documented field maps to the step input that fills it (``step.input`` or
``step.input[].item_field``), or to ``None`` with the reason it is not offered.
tests/test_coverage.py checks both ways: each mapped input exists in
tests/reference/op_specs.py, and each documented field is listed here.
"""

from __future__ import annotations

from typing import Any

Field = tuple[str | None, str]

#: Endpoint -> (step ids, {documented field: (input path or None, note)}).
ENDPOINTS: dict[str, dict[str, Any]] = {
    "POST /v1/documents/create": {
        "steps": ["send_sales_invoice"],
        "fields": {
            "token": (None, "The connection's key, sent in the form body."),
            "rows": ("send_sales_invoice.lines", ""),
            "trans_id": ("send_sales_invoice.transaction_id", ""),
            "intrs_transprusis": ("send_sales_invoice.intrastat_transport", ""),
            "intrs_pristsal": ("send_sales_invoice.intrastat_delivery_terms", ""),
            "intrs_sandoris": ("send_sales_invoice.intrastat_transaction", ""),
            "intrs_apskritis": ("send_sales_invoice.intrastat_county", ""),
            "intrs_eusalis": ("send_sales_invoice.intrastat_eu_country", ""),
            "oper_apras": ("send_sales_invoice.operation_description", ""),
            "projektas": ("send_sales_invoice.project", ""),
            "uzsaknr": ("send_sales_invoice.order_number", ""),
            "isaf": (
                None,
                "Not offered: the documentation says it is used when the invoice is left out "
                "of the i.SAF registers but not which value to send.",
            ),
            "pastaba": ("send_sales_invoice.note", ""),
            "israse_pareigos": ("send_sales_invoice.issued_by_position", ""),
            "israse_asmuo": ("send_sales_invoice.issued_by", ""),
            "sask_moketpvm": ("send_sales_invoice.vat_payable_account", ""),
            "sask_pirkskol": ("send_sales_invoice.receivable_account", ""),
            "sask_pajamos": ("send_sales_invoice.income_account", ""),
            "kl_kodas": ("send_sales_invoice.buyer_code", ""),
            "estipas": ("send_sales_invoice.buyer_eu_type", ""),
            "email": ("send_sales_invoice.buyer_email", ""),
            "miestas": ("send_sales_invoice.buyer_city", ""),
            "adresas": ("send_sales_invoice.buyer_address", ""),
            "salis": ("send_sales_invoice.buyer_country", ""),
            "grupe": ("send_sales_invoice.buyer_group", ""),
            "pvm_kodas": ("send_sales_invoice.buyer_vat_code", ""),
            "im_kodas": ("send_sales_invoice.buyer_company_code", ""),
            "savikaina": ("send_sales_invoice.cost", ""),
            "bepvm_suma": ("send_sales_invoice.net_total", "Computed from the lines when empty."),
            "pvm_suma": ("send_sales_invoice.vat_total", "Computed from the lines when empty."),
            "apmok_iki": ("send_sales_invoice.due_date", ""),
            "dok_num": ("send_sales_invoice.number", "auto when empty."),
            "dok_suma": ("send_sales_invoice.total", "Net total + VAT total."),
            "data": ("send_sales_invoice.date", ""),
            "pirkejas": ("send_sales_invoice.buyer_name", ""),
            "asmuo_status": (None, "Not offered: the documentation gives it no description."),
            "salis_kodas": (None, "Not offered: the documentation gives it no description."),
        },
        "row_fields": {
            "kodas": ("send_sales_invoice.lines[].code", ""),
            "pavadinimas": ("send_sales_invoice.lines[].name", ""),
            "matovnt": ("send_sales_invoice.lines[].unit", ""),
            "kiekis": ("send_sales_invoice.lines[].quantity", ""),
            "kaina": ("send_sales_invoice.lines[].price", ""),
            "pvmtar": ("send_sales_invoice.lines[].vat_percent", ""),
            "Mok_kodas": ("send_sales_invoice.lines[].vat_code", ""),
            "sask_pajamos": ("send_sales_invoice.lines[].income_account", ""),
            "projektas": ("send_sales_invoice.lines[].project", ""),
        },
    },
    "POST /v1/orders/create": {
        "steps": ["send_order"],
        "fields": {
            "rows": ("send_order.lines", ""),
            "token": (None, "The connection's key, sent in the form body."),
            "uzsakovas": ("send_order.customer_name", ""),
            "miestas": ("send_order.customer_city", ""),
            "adresas": ("send_order.customer_address", ""),
            "tel": ("send_order.customer_phone", ""),
            "im_kodas": ("send_order.customer_company_code", ""),
            "pvm_kodas": ("send_order.customer_vat_code", ""),
            "email": ("send_order.customer_email", ""),
            "uzsak_data": ("send_order.date", ""),
            "vykd_data": ("send_order.execution_date", ""),
            "pristat_data": ("send_order.delivery_date", ""),
            "apmok_data": ("send_order.payment_date", ""),
            "atvyk_data": ("send_order.arrival_date", ""),
            "isvyk_data": ("send_order.departure_date", ""),
            "uzsak_suma": ("send_order.total", "Net total + VAT total."),
            "uzsak_num": ("send_order.number", ""),
            "pvm_suma": ("send_order.vat_total", "Computed from the lines when empty."),
            "bepvm_suma": ("send_order.net_total", "Computed from the lines when empty."),
            "sandelis": ("send_order.warehouse", ""),
            "pasto_kodas": ("send_order.postal_code", ""),
            "uzsakovas_pastaba": ("send_order.customer_note", ""),
            "pirk_skolsask": ("send_order.receivable_account", ""),
        },
        "row_fields": {
            "kodas": ("send_order.lines[].code", ""),
            "t_kodas": ("send_order.lines[].supplier_code", ""),
            "pavadinimas": ("send_order.lines[].name", ""),
            "matovnt": ("send_order.lines[].unit", ""),
            "kiekis": ("send_order.lines[].quantity", ""),
            "kaina": ("send_order.lines[].price", ""),
            "pvm_tar": (
                "send_order.lines[].vat_percent",
                "The table says pvm_tar, the example pvmtar: both are sent.",
            ),
        },
    },
    "POST /v1/products/import": {
        "steps": ["send_products"],
        "fields": {
            "token": (None, "The connection's key: in the form body and in every item."),
            "data": ("send_products.products", "Built as the documented XML."),
        },
        "row_fields": {
            "token": (None, "The connection's key, in every item as documented."),
            "oper": (None, "Always UPD, the only value the documentation shows."),
            "id": ("send_products.products[].id", ""),
            "kodas": ("send_products.products[].code", ""),
            "pavadinimas": ("send_products.products[].name", ""),
            "matovnt": ("send_products.products[].unit", ""),
            "kaina": ("send_products.products[].price", ""),
            "pvmtar": ("send_products.products[].vat_percent", ""),
            "likutis": ("send_products.products[].stock", ""),
            "grupe1": ("send_products.products[].group1", ""),
            "grupe2": ("send_products.products[].group2", ""),
            "grupe3": ("send_products.products[].group3", ""),
            "barkodas": ("send_products.products[].barcode", ""),
            "aprasymas": ("send_products.products[].description", ""),
            "Nuotrauka": ("send_products.products[].photo", ""),
            "Stocks": ("send_products.products[].stocks", ""),
            "ProductParameters": ("send_products.products[].parameters", ""),
            "AnalogProducts": (
                None,
                "Not offered: the documentation shows it only empty, without its content.",
            ),
            "RecommendedProducts": (
                None,
                "Not offered: the documentation shows it only empty, without its content.",
            ),
        },
    },
    "GET /v1/products/export": {
        "steps": ["get_products", "find_product", "get_stock_levels", "test_connection"],
        "fields": {
            "token": (None, "The connection's key, in the query (the only place it is read)."),
            "id": ("get_products.id", ""),
        },
    },
    "POST /v1/payments/import": {
        "steps": ["send_payments"],
        "fields": {
            "token": (None, "The connection's key, sent in the form body."),
            "data": ("send_payments.payments", "Built as the documented XML."),
        },
        "row_fields": {
            "PaymentType": ("send_payments.payments[].type", ""),
            "Date": ("send_payments.payments[].date", ""),
            "Amount": ("send_payments.payments[].amount", ""),
            "DocNr": ("send_payments.payments[].document_number", ""),
            "RefNr": ("send_payments.payments[].reference", ""),
            "Details": ("send_payments.payments[].details", ""),
            "RecName": ("send_payments.payments[].payer_name", ""),
            "RecId": ("send_payments.payments[].payer_code", ""),
            "ToAccountNumber": ("send_payments.payments[].account", ""),
        },
    },
    "GET /v1/payments/export": {
        "steps": ["get_payments", "send_payments"],
        "fields": {
            "token": (None, "The connection's key, in the query (the only place it is read)."),
        },
    },
    "POST /v1/documents/purchase/import": {
        "steps": ["send_purchase_invoice"],
        "fields": {
            "token": (None, "The connection's key, sent in the form body."),
            "kontrah": ("send_purchase_invoice.seller_name", ""),
            "data": ("send_purchase_invoice.date", ""),
            "dok_suma": ("send_purchase_invoice.total", "Net total + VAT total."),
            "dok_num": ("send_purchase_invoice.number", ""),
            "pvm_suma": ("send_purchase_invoice.vat_total", "Computed from the lines when empty."),
            "bepvm_suma": (
                "send_purchase_invoice.net_total",
                "Computed from the lines when empty.",
            ),
            "rows": (
                "send_purchase_invoice.lines",
                "The documentation gives no line fields for purchases; the step sends the "
                "sales invoice's line fields.",
            ),
        },
    },
}

#: Paths that answer on ws.centas.lt but are not in the documentation.
UNDOCUMENTED: dict[str, str] = {
    "GET /v1/documents/export": "excluded: undocumented",
    "GET /v1/orders/export": "excluded: undocumented",
    "GET /v1/documents/get": "excluded: undocumented",
    "/v1/documents/delete": "excluded: undocumented",
}

#: What the documentation does not settle, and what this release assumes. Shown on
#: the Coverage page; the first things to check against a live Centas WS.
NOT_VERIFIED: list[str] = [
    "Dates are sent as YYYY.MM.DD, the form of the documentation's payment example and of "
    "the Centas program; the documentation gives no date format for the other fields.",
    "The document and order fields are sent in the POST body, like the key; the "
    "documentation lists them as query parameters of a POST.",
    "Line values are sent as text with a point as decimal mark, as in the documentation's "
    "examples.",
    "Order lines carry the VAT rate as both pvm_tar and pvmtar, because the documentation "
    "names it both ways.",
    "Purchase invoice lines use the sales invoice's line fields; the documentation names "
    "none for purchases.",
    "Centas WS documents no duplicate check: sending the same invoice, order, payment or "
    "product again may create it again.",
    "How Centas matches the buyer of a sales invoice to an existing client (code, company "
    "code, VAT code or name) is not documented; the buyer group applies to a new buyer.",
    "Centas WS documents no required fields except for purchase invoices; the steps "
    "require the number, date, party name and lines.",
    "Which payments the payment export holds is not documented; Send bank payments stops "
    "without sending when a reference is already in it or it cannot be read.",
    "Totals are checked within one cent per line, because Centas lets each company choose "
    "how VAT is summed.",
]


def documented_fields() -> list[tuple[str, str, str | None, str]]:
    """(endpoint, field, input path or None, note) for every documented field."""
    out: list[tuple[str, str, str | None, str]] = []
    for endpoint, spec in ENDPOINTS.items():
        for kind in ("fields", "row_fields"):
            for name, (path, note) in spec.get(kind, {}).items():
                label = name if kind == "fields" else f"rows[].{name}"
                out.append((endpoint, label, path, note))
    return out


__all__ = ["ENDPOINTS", "NOT_VERIFIED", "UNDOCUMENTED", "documented_fields"]
