"""Facts extracted from the Centas WS API specification, operation by operation.

Source of truth: https://ws.centas.lt/api-docs/openapi.yaml (runtime/reference.py:
SPECIFICATION, SHA-256 1860fbaa…498f). Where the specification is silent, the older
GitBook documentation (runtime/reference.py: GITBOOK) adds fields; those are marked
``gitbook``. Neither text is copied into this repository — only names and where each
one goes.

Every operation maps to the steps that call it, or to the reason none does. Every
documented field maps to the step input that fills it (``step.input``,
``step.input[].field``, ``step.input[].list[].field``), or to ``None`` with the reason
it is not offered. tests/test_contracts.py checks both ways.
"""

from __future__ import annotations

from typing import Any

SPEC = "specification"
GITBOOK = "gitbook"

TOKEN_QUERY = (None, "The connection's key, in the query as the specification requires.", SPEC)
TOKEN_FORM = (None, "The connection's key, sent in the form body.", SPEC)
TOKEN_ITEM = (None, "The connection's key, in every item as the specification requires.", SPEC)


def _f(path: str | None, note: str = "", source: str = SPEC) -> tuple[str | None, str, str]:
    return (path, note, source)


def _g(path: str | None, note: str = "") -> tuple[str | None, str, str]:
    return (path, note, GITBOOK)


_SALES = "send_sales_invoice"
_SALES_LINE = "send_sales_invoice.lines[]"
_ORDER = "send_order"
_PRODUCTS = "send_products.products[]"
_COMPANY = "send_invoice_to_company"
_CONTRAHENTS = "send_contrahents.contrahents[]"
_PAYMENTS = "send_payments.payments[]"
_DOC_PAY = "record_document_payments.documents[]"

OPERATIONS: dict[str, dict[str, Any]] = {
    "GET /test": {"steps": ["check_service"], "fields": {}},
    "GET /verify": {"steps": ["test_connection"], "fields": {"token": TOKEN_QUERY}},
    "GET /statistics": {"steps": ["get_statistics"], "fields": {"token": TOKEN_QUERY}},
    "GET /products/export/json": {
        "steps": ["get_product_stock"],
        "fields": {"token": TOKEN_QUERY, "barkodas": _f("get_product_stock.barcode")},
    },
    "GET /products/export/json/full": {
        "steps": ["get_products"],
        "fields": {"token": TOKEN_QUERY},
    },
    "GET /products/export/json/one": {
        "steps": ["get_product"],
        "fields": {"token": TOKEN_QUERY, "kodas": _f("get_product.code")},
    },
    "GET /products/export": {
        "steps": ["get_product_cards"],
        "fields": {"token": TOKEN_QUERY, "id": _f("get_product_cards.id")},
    },
    "POST /products/import": {
        "steps": ["send_products"],
        "fields": {
            "token": TOKEN_FORM,
            "data": _f("send_products.products", "Built as the documented XML."),
            "item.token": _g(
                None,
                "The connection's key, in every item as the GitBook documentation and the "
                "product export show it.",
            ),
            "item.oper": _f(None, "Always UPD (update or create), the only value named."),
            "item.id": _f(f"{_PRODUCTS}.id"),
            "item.kodas": _f(f"{_PRODUCTS}.code"),
            "item.pavadinimas": _f(f"{_PRODUCTS}.name"),
            "item.matovnt": _f(f"{_PRODUCTS}.unit"),
            "item.kaina": _f(f"{_PRODUCTS}.price"),
            "item.pvmtar": _f(f"{_PRODUCTS}.vat_percent"),
            "item.likutis": _f(f"{_PRODUCTS}.stock"),
            "item.grupe1": _f(f"{_PRODUCTS}.group1"),
            "item.grupe2": _f(f"{_PRODUCTS}.group2"),
            "item.grupe3": _f(f"{_PRODUCTS}.group3"),
            "item.grupe4": _f(f"{_PRODUCTS}.group4"),
            "item.barkodas": _f(f"{_PRODUCTS}.barcode"),
            "item.aprasymas": _f(f"{_PRODUCTS}.description"),
            "item.gamintojas": _f(f"{_PRODUCTS}.manufacturer"),
            "item.svoris_neto": _f(f"{_PRODUCTS}.net_weight"),
            "item.svoris_bruto": _f(f"{_PRODUCTS}.gross_weight"),
            "item.AnalogProducts": _f(f"{_PRODUCTS}.analog_products", "Comma-separated."),
            "item.RecommendedProducts": _f(f"{_PRODUCTS}.recommended_products", "Comma-separated."),
            "item.Nuotrauka": _f(f"{_PRODUCTS}.photo"),
            "item.mok_kodas": _f(f"{_PRODUCTS}.vat_code"),
            "item.savikaina": _f(f"{_PRODUCTS}.cost"),
            "item.uzsak": _f(f"{_PRODUCTS}.ordered"),
            "item.sandel": _f(f"{_PRODUCTS}.warehouse"),
            "item.Stocks": _f(f"{_PRODUCTS}.stocks"),
            "item.Stocks.Stock.WarehouseId": _f(f"{_PRODUCTS}.stocks[].warehouse_id"),
            "item.Stocks.Stock.WarehouseName": _f(f"{_PRODUCTS}.stocks[].warehouse_name"),
            "item.Stocks.Stock.Quantity": _f(f"{_PRODUCTS}.stocks[].quantity"),
            "item.ProductParameters": _f(f"{_PRODUCTS}.parameters"),
            "item.ProductParameters.Parameter.Name": _f(f"{_PRODUCTS}.parameters[].name"),
            "item.ProductParameters.Parameter.Value": _f(f"{_PRODUCTS}.parameters[].value"),
        },
    },
    "GET /products/gallery": {
        "steps": ["get_product_gallery_link"],
        "fields": {
            "token": TOKEN_QUERY,
            "product_id": _f("get_product_gallery_link.product_id"),
        },
    },
    "GET /documents/export": {
        "steps": ["get_sales_documents", "take_new_sales_documents"],
        "fields": {
            "token": TOKEN_QUERY,
            "unpaid": _f("get_sales_documents.unpaid"),
            "from": _f("get_sales_documents.date_from"),
            "to": _f("get_sales_documents.date_to"),
        },
    },
    "GET /documents/create": {
        "steps": [],
        "reason": "Not a step: it only answers that POST is required.",
        "fields": {"token": TOKEN_QUERY},
    },
    "POST /documents/create": {
        "steps": [_SALES],
        "fields": {
            "token": TOKEN_FORM,
            "pirkejas": _f(f"{_SALES}.buyer_name"),
            "data": _f(f"{_SALES}.date"),
            "dok_suma": _f(f"{_SALES}.total", "Net total + VAT total."),
            "dok_num": _f(f"{_SALES}.number"),
            "apmok_iki": _f(f"{_SALES}.due_date"),
            "pvm_suma": _f(f"{_SALES}.vat_total", "Computed from the lines when empty."),
            "bepvm_suma": _f(f"{_SALES}.net_total", "Computed from the lines when empty."),
            "savikaina": _f(f"{_SALES}.cost"),
            "rows": _f(f"{_SALES}.lines"),
            "rows[].kodas": _f(f"{_SALES_LINE}.code"),
            "rows[].pavadinimas": _f(f"{_SALES_LINE}.name"),
            "rows[].matovnt": _f(f"{_SALES_LINE}.unit"),
            "rows[].kiekis": _f(f"{_SALES_LINE}.quantity"),
            "rows[].kaina": _f(f"{_SALES_LINE}.price"),
            "rows[].pvmtar": _f(f"{_SALES_LINE}.vat_percent"),
            "rows[].prek_pasl": _f(f"{_SALES_LINE}.kind"),
            "rows[].ean": _f(f"{_SALES_LINE}.ean"),
            "rows[].Mok_kodas": _f(f"{_SALES_LINE}.vat_code"),
            "rows[].sask_pajamos": _f(f"{_SALES_LINE}.income_account"),
            "rows[].projektas": _f(f"{_SALES_LINE}.project"),
            "rows[].pvmsuma": _f(f"{_SALES_LINE}.vat_amount"),
            "rows[].nuolaida_proc": _f(f"{_SALES_LINE}.discount_percent"),
            "rows[].nuolaida": _f(f"{_SALES_LINE}.discount"),
            "rows[].atv_pvm": _f(
                None, "Not offered: the specification names it without its meaning or values."
            ),
            "rows[].hs_code": _f(f"{_SALES_LINE}.hs_code"),
            "rows[].country_origin": _f(f"{_SALES_LINE}.country_origin"),
            "rows[].material": _f(f"{_SALES_LINE}.material"),
            "dok_num_series": _f(f"{_SALES}.number_series"),
            "check_order": _f(f"{_SALES}.check_order"),
            "uzsaknr": _f(f"{_SALES}.order_number"),
            "im_kodas": _f(f"{_SALES}.buyer_company_code"),
            "pvm_kodas": _f(f"{_SALES}.buyer_vat_code"),
            "salis": _f(f"{_SALES}.buyer_country"),
            "miestas": _f(f"{_SALES}.buyer_city"),
            "adresas": _f(f"{_SALES}.buyer_address"),
            "email": _f(f"{_SALES}.buyer_email"),
            "type": _f(f"{_SALES}.document_type"),
            "trans_id": _g(f"{_SALES}.transaction_id"),
            "kl_kodas": _g(f"{_SALES}.buyer_code"),
            "estipas": _g(f"{_SALES}.buyer_eu_type"),
            "grupe": _g(f"{_SALES}.buyer_group"),
            "sask_moketpvm": _g(f"{_SALES}.vat_payable_account"),
            "sask_pirkskol": _g(f"{_SALES}.receivable_account"),
            "sask_pajamos": _g(f"{_SALES}.income_account"),
            "projektas": _g(f"{_SALES}.project"),
            "oper_apras": _g(f"{_SALES}.operation_description"),
            "pastaba": _g(f"{_SALES}.note"),
            "israse_asmuo": _g(f"{_SALES}.issued_by"),
            "israse_pareigos": _g(f"{_SALES}.issued_by_position"),
            "intrs_transprusis": _g(f"{_SALES}.intrastat_transport"),
            "intrs_pristsal": _g(f"{_SALES}.intrastat_delivery_terms"),
            "intrs_sandoris": _g(f"{_SALES}.intrastat_transaction"),
            "intrs_apskritis": _g(f"{_SALES}.intrastat_county"),
            "intrs_eusalis": _g(f"{_SALES}.intrastat_eu_country"),
            "isaf": _g(
                None,
                "Not offered: the documentation says it leaves the invoice out of the i.SAF "
                "registers but not which value to send.",
            ),
            "asmuo_status": _g(None, "Not offered: the documentation gives it no description."),
            "salis_kodas": _g(None, "Not offered: the documentation gives it no description."),
        },
    },
    "GET /documents/get": {
        "steps": ["get_sales_document"],
        "fields": {"token": TOKEN_QUERY, "dok_num": _f("get_sales_document.number")},
    },
    "POST /documents/update": {
        "steps": ["update_sales_documents"],
        "fields": {
            "token": TOKEN_FORM,
            "data": _f("update_sales_documents.documents", "Built as the documented XML."),
            "item.token": TOKEN_ITEM,
            "item.type": _f("update_sales_documents.documents[].type"),
            "item.number": _f("update_sales_documents.documents[].number"),
            "item.date": _f("update_sales_documents.documents[].date"),
            "item.downloaded": _f("update_sales_documents.documents[].downloaded"),
            "item.apmoketa": _f("update_sales_documents.documents[].paid"),
            "item.dok_skola": _f("update_sales_documents.documents[].remaining_debt"),
        },
    },
    "POST /documents/delete": {
        "steps": ["delete_sales_documents"],
        "fields": {
            "token": TOKEN_FORM,
            "data": _f("delete_sales_documents.documents", "Built as the documented XML."),
            "item.token": TOKEN_ITEM,
            "item.type": _f("delete_sales_documents.documents[].type"),
            "item.number": _f("delete_sales_documents.documents[].number"),
            "item.date": _f("delete_sales_documents.documents[].date"),
        },
    },
    "POST /documents/payments/create": {
        "steps": ["record_document_payments"],
        "fields": {
            "token": TOKEN_FORM,
            "data": _f("record_document_payments.documents", "Built as the documented XML."),
            "item.token": TOKEN_ITEM,
            "item.type": _f(f"{_DOC_PAY}.type"),
            "item.number": _f(f"{_DOC_PAY}.number"),
            "item.date": _f(f"{_DOC_PAY}.date"),
            "item.paid_sum": _f(f"{_DOC_PAY}.paid_sum"),
            "item.paid_full": _f(f"{_DOC_PAY}.paid_in_full"),
            "item.customerId": _f(f"{_DOC_PAY}.customer_id"),
            "item.payment": _f(f"{_DOC_PAY}.payments"),
            "item.payment.date": _f(f"{_DOC_PAY}.payments[].date"),
            "item.payment.number": _f(f"{_DOC_PAY}.payments[].number"),
            "item.payment.description": _f(f"{_DOC_PAY}.payments[].description"),
            "item.payment.total": _f(f"{_DOC_PAY}.payments[].total"),
        },
    },
    "GET /orders/create": {
        "steps": [],
        "reason": "Not a step: it only answers that POST is required.",
        "fields": {"token": TOKEN_QUERY},
    },
    "POST /orders/create": {
        "steps": [_ORDER],
        "fields": {
            "token": TOKEN_FORM,
            "uzsakovas": _f(f"{_ORDER}.customer_name"),
            "uzsak_data": _f(f"{_ORDER}.date"),
            "uzsak_suma": _f(f"{_ORDER}.total", "Net total + VAT total."),
            "uzsak_num": _f(f"{_ORDER}.number"),
            "pvm_suma": _f(f"{_ORDER}.vat_total", "Computed from the lines when empty."),
            "bepvm_suma": _f(f"{_ORDER}.net_total", "Computed from the lines when empty."),
            "rows": _f(f"{_ORDER}.lines"),
            "rows[].kodas": _f(f"{_ORDER}.lines[].code"),
            "rows[].pavadinimas": _f(f"{_ORDER}.lines[].name"),
            "rows[].matovnt": _f(f"{_ORDER}.lines[].unit"),
            "rows[].kiekis": _f(f"{_ORDER}.lines[].quantity"),
            "rows[].kaina": _f(f"{_ORDER}.lines[].price"),
            "rows[].pvmtar": _f(f"{_ORDER}.lines[].vat_percent"),
            "rows[].t_kodas": _g(f"{_ORDER}.lines[].supplier_code"),
            "rows[].pvm_tar": _g(
                None,
                "The GitBook table's name of pvmtar; the specification and both examples use "
                "pvmtar, which is sent.",
            ),
            "vezejas": _f(f"{_ORDER}.carrier"),
            "uzsakovas_pastaba": _f(f"{_ORDER}.customer_note"),
            "komentaras": _f(f"{_ORDER}.comment"),
            "uzsak_padalinys": _f(f"{_ORDER}.delivery_branch"),
            "uzsak_padalinys_gln": _f(f"{_ORDER}.delivery_branch_gln"),
            "uzsak_padalinys_iln": _f(f"{_ORDER}.delivery_branch_iln"),
            "uzsak_iln": _f(f"{_ORDER}.customer_iln"),
            "pristat_data": _f(f"{_ORDER}.delivery_date"),
            "im_kodas": _f(f"{_ORDER}.customer_company_code"),
            "pvm_kodas": _f(f"{_ORDER}.customer_vat_code"),
            "salis": _f(f"{_ORDER}.customer_country"),
            "miestas": _f(f"{_ORDER}.customer_city"),
            "adresas": _f(f"{_ORDER}.customer_address"),
            "email": _f(f"{_ORDER}.customer_email"),
            "tel": _g(f"{_ORDER}.customer_phone"),
            "pasto_kodas": _g(f"{_ORDER}.postal_code"),
            "pirk_skolsask": _g(f"{_ORDER}.receivable_account"),
            "sandelis": _g(f"{_ORDER}.warehouse"),
            "vykd_data": _g(f"{_ORDER}.execution_date"),
            "apmok_data": _g(f"{_ORDER}.payment_date"),
            "atvyk_data": _g(f"{_ORDER}.arrival_date"),
            "isvyk_data": _g(f"{_ORDER}.departure_date"),
        },
    },
    "GET /orders/export": {"steps": ["take_new_orders"], "fields": {"token": TOKEN_QUERY}},
    "GET /orders/document/pdf": {
        "steps": ["get_order_invoice_pdf"],
        "fields": {
            "token": TOKEN_QUERY,
            "order_no": _f("get_order_invoice_pdf.order_number"),
            "check": _f("get_order_invoice_pdf.check_only"),
        },
    },
    "POST /purchase/import": {
        "steps": [_COMPANY],
        "fields": {
            "data": _f(f"{_COMPANY}.lines", "Built as the documented XML."),
            "siuntejas.token": _f(
                None, "The connection's key: this operation reads it here, not from the query."
            ),
            "gavejas.im_kodas": _f(f"{_COMPANY}.receiver_company_code"),
            "gavejas.pvm_kodas": _f(f"{_COMPANY}.receiver_vat_code"),
            "gavejas.kontrah": _f(f"{_COMPANY}.receiver_name"),
            "gavejas.email": _f(f"{_COMPANY}.receiver_email"),
            "gavejas.salis": _f(f"{_COMPANY}.receiver_country"),
            "gavejas.miestas": _f(f"{_COMPANY}.receiver_city"),
            "gavejas.adresas": _f(f"{_COMPANY}.receiver_address"),
            "gavejas.send_email": _f(f"{_COMPANY}.send_email"),
            "gavejas.telema_id": _f(f"{_COMPANY}.receiver_telema_id"),
            "gavejas.edisoft_iln": _f(f"{_COMPANY}.receiver_edisoft_iln"),
            "dokumentas.dok_num": _f(f"{_COMPANY}.number"),
            "dokumentas.data": _f(f"{_COMPANY}.date"),
            "dokumentas.dok_suma": _f(f"{_COMPANY}.total"),
            "dokumentas.pvm_suma": _f(f"{_COMPANY}.vat_total"),
            "dokumentas.bepvm_suma": _f(f"{_COMPANY}.net_total"),
            "dokumentas.apmok_iki": _f(f"{_COMPANY}.due_date"),
            "dokumentas.kontrah": _f(f"{_COMPANY}.seller_name"),
            "dokumentas.DocType": _f(f"{_COMPANY}.document_type"),
            "dokumentas.salis_kodas": _f(f"{_COMPANY}.country_code"),
            "dokumentas.apmoketa": _f(f"{_COMPANY}.paid"),
            "dokumentas.dok_skola": _f(f"{_COMPANY}.remaining_debt"),
            "dokumentas.pdf_name": _f(f"{_COMPANY}.pdf_name"),
            "dokumentas.pdf_base64": _f(f"{_COMPANY}.pdf_file", "A workflow file, as Base64."),
            "dokumentas.eilute.kodas": _f(f"{_COMPANY}.lines[].code"),
            "dokumentas.eilute.prek_pasl": _f(f"{_COMPANY}.lines[].kind"),
            "dokumentas.eilute.ean": _f(f"{_COMPANY}.lines[].ean"),
            "dokumentas.eilute.pavadinimas": _f(f"{_COMPANY}.lines[].name"),
            "dokumentas.eilute.matovnt": _f(f"{_COMPANY}.lines[].unit"),
            "dokumentas.eilute.kiekis": _f(f"{_COMPANY}.lines[].quantity"),
            "dokumentas.eilute.kaina": _f(f"{_COMPANY}.lines[].price"),
            "dokumentas.eilute.pvmtar": _f(f"{_COMPANY}.lines[].vat_percent"),
            "dokumentas.eilute.mok_kodas": _f(f"{_COMPANY}.lines[].vat_code"),
        },
    },
    "GET /purchase/export": {
        "steps": ["get_purchases", "take_new_purchases"],
        "fields": {
            "token": TOKEN_QUERY,
            "from": _f("get_purchases.date_from"),
            "to": _f("get_purchases.date_to"),
        },
    },
    "POST /documents/purchase/import": {
        "steps": ["send_purchase_invoice"],
        "fields": {
            "token": TOKEN_FORM,
            "kontrah": _f("send_purchase_invoice.seller_name"),
            "data": _f("send_purchase_invoice.date"),
            "dok_suma": _f("send_purchase_invoice.total", "Net total + VAT total."),
            "dok_num": _f("send_purchase_invoice.number"),
            "pvm_suma": _f(
                "send_purchase_invoice.vat_total", "Computed from the lines when empty."
            ),
            "bepvm_suma": _f(
                "send_purchase_invoice.net_total", "Computed from the lines when empty."
            ),
            "rows": _f("send_purchase_invoice.lines"),
            "rows[].kodas": _f("send_purchase_invoice.lines[].code"),
            "rows[].pavadinimas": _f("send_purchase_invoice.lines[].name"),
            "rows[].matovnt": _f("send_purchase_invoice.lines[].unit"),
            "rows[].kiekis": _f("send_purchase_invoice.lines[].quantity"),
            "rows[].kaina": _f("send_purchase_invoice.lines[].price"),
            "rows[].pvmtar": _f("send_purchase_invoice.lines[].vat_percent"),
        },
    },
    "POST /payments/import": {
        "steps": ["send_payments"],
        "fields": {
            "token": TOKEN_FORM,
            "data": _f("send_payments.payments", "Built as the documented XML."),
            "item.PaymentType": _f(f"{_PAYMENTS}.type"),
            "item.Date": _f(f"{_PAYMENTS}.date"),
            "item.Amount": _f(f"{_PAYMENTS}.amount"),
            "item.DocNr": _f(f"{_PAYMENTS}.document_number"),
            "item.RefNr": _f(f"{_PAYMENTS}.reference"),
            "item.Details": _f(f"{_PAYMENTS}.details"),
            "item.RecName": _f(f"{_PAYMENTS}.payer_name"),
            "item.RecId": _f(f"{_PAYMENTS}.payer_code"),
            "item.Receiver": _f(f"{_PAYMENTS}.receiver"),
            "item.ToAccountNumber": _f(f"{_PAYMENTS}.account"),
        },
    },
    "GET /payments/export": {
        "steps": ["take_new_payments"],
        "fields": {"token": TOKEN_QUERY},
    },
    "GET /payments/export/{type}": {
        "steps": ["take_new_payments"],
        "fields": {"token": TOKEN_QUERY, "type": _f("take_new_payments.payment_type")},
    },
    "POST /contrahents/import": {
        "steps": ["send_contrahents"],
        "fields": {
            "token": TOKEN_FORM,
            "data": _f("send_contrahents.contrahents", "Built as the documented XML."),
            "item.oper": _f(None, "Always UPD, the only value named."),
            "item.id": _f(f"{_CONTRAHENTS}.id"),
            "item.pavadinimas": _f(f"{_CONTRAHENTS}.name"),
            "item.imones_kodas": _f(f"{_CONTRAHENTS}.company_code"),
            "item.pvm_kodas": _f(f"{_CONTRAHENTS}.vat_code"),
            "item.salis": _f(f"{_CONTRAHENTS}.country"),
            "item.miestas": _f(f"{_CONTRAHENTS}.city"),
            "item.adresas": _f(f"{_CONTRAHENTS}.address"),
            "item.email": _f(f"{_CONTRAHENTS}.email"),
            "item.telefonas": _f(f"{_CONTRAHENTS}.phone"),
            "item.iban_nr": _f(f"{_CONTRAHENTS}.iban"),
            "item.pirkejas": _f(f"{_CONTRAHENTS}.is_buyer"),
            "item.tiekejas": _f(f"{_CONTRAHENTS}.is_supplier"),
            "item.skola": _f(f"{_CONTRAHENTS}.debt"),
            "item.telema_id": _f(f"{_CONTRAHENTS}.telema_id"),
            "item.edisoft_iln": _f(f"{_CONTRAHENTS}.edisoft_iln"),
            "item.padaliniai": _f(f"{_CONTRAHENTS}.branches"),
            "item.padaliniai.padalinis.pavad": _f(f"{_CONTRAHENTS}.branches[].name"),
            "item.padaliniai.padalinis.adresas": _f(f"{_CONTRAHENTS}.branches[].address"),
            "item.padaliniai.padalinis.salis": _f(f"{_CONTRAHENTS}.branches[].country"),
            "item.padaliniai.padalinis.miestas": _f(f"{_CONTRAHENTS}.branches[].city"),
        },
    },
    "GET /contrahents/export": {
        "steps": ["get_contrahents"],
        "fields": {"token": TOKEN_QUERY, "id": _f("get_contrahents.id")},
    },
    "GET /contrahents/search": {
        "steps": ["find_company_by_code"],
        "fields": {"token": TOKEN_QUERY, "code": _f("find_company_by_code.code")},
    },
    "GET /consignments/import": {
        "steps": [],
        "reason": "Not a step: the same as POST /consignments/import, which the specification "
        "prefers, but with the data and the key in the address.",
        "fields": {
            "token": TOKEN_QUERY,
            "data": _f("send_consignment.lines", "Offered through the POST."),
        },
    },
    "POST /consignments/import": {
        "steps": ["send_consignment"],
        "fields": {
            "token": TOKEN_FORM,
            "data": _f("send_consignment.lines", "Built as the documented XML."),
            "DocumentUID": _f("send_consignment.document_uid"),
            "DocumentNumber": _f("send_consignment.document_number"),
            "DocumentDate": _f("send_consignment.document_date"),
            "EstimatedTimeOfArrival": _f("send_consignment.estimated_arrival"),
            "ConsigneeName": _f("send_consignment.consignee_name"),
            "ConsigneeRegistrationNumber": _f("send_consignment.consignee_code"),
            "eilute.ProductDescription": _f("send_consignment.lines[].description"),
            "eilute.UnitOfMeasure": _f("send_consignment.lines[].unit"),
            "eilute.Quantity": _f("send_consignment.lines[].quantity"),
        },
    },
}

#: Step inputs that do not reach Centas WS: paging over an answer read whole.
LOCAL_INPUTS = frozenset({"page", "limit"})

#: Where the GitBook documentation and the specification differ (the specification wins).
DIFFERENCES: list[str] = [
    "Dates: GitBook shows YYYY.MM.DD (payment example); the specification writes YYYY-MM-DD "
    "everywhere it sends a date (its purchase export example still answers YYYY.MM.DD).",
    "payments/import: GitBook wraps each payment in <Payment>, the specification in <item>; "
    "the specification requires DocNr, Details and RecName, makes RefNr optional and adds "
    "Receiver.",
    "orders/create: GitBook answers order_hash, the specification order_id; the row's VAT "
    "rate is pvm_tar in the GitBook table, pvmtar in both examples and the specification; "
    "the specification adds vezejas, komentaras, uzsak_padalinys(_gln, _iln), uzsak_iln and "
    "salis, and omits tel, vykd_data, apmok_data, atvyk_data, isvyk_data, sandelis, "
    "pasto_kodas and pirk_skolsask.",
    "documents/create: the specification requires apmok_iki and savikaina and six row "
    "fields, adds dok_num_series, check_order, type and the row fields prek_pasl, ean, "
    "pvmsuma, nuolaida_proc, nuolaida, atv_pvm, hs_code, country_origin and material; "
    "GitBook adds trans_id, kl_kodas, estipas, grupe, the accounts, Intrastat, oper_apras, "
    "pastaba, israse_*, isaf, asmuo_status and salis_kodas.",
    "documents/create: the specification documents HTTP 400 for a validation error and a "
    "duplicate number; GitBook says every answer is HTTP 200.",
    "products/import: GitBook puts the key in every <item>, the specification's example does "
    "not; the specification adds grupe4, gamintojas, svoris_neto, svoris_bruto, mok_kodas, "
    "savikaina, uzsak and sandel.",
    "Writes are multipart/form-data in the specification; GitBook calls their fields query "
    "parameters.",
    "The specification documents 26 more operations than GitBook: statistics, verify, the "
    "JSON product exports, gallery, document export, get, update, delete and payments, order "
    "export and PDF, purchase exchange and export, payment export by type, contrahents and "
    "consignments.",
]


def documented_fields() -> list[tuple[str, str, str | None, str, str]]:
    """(operation, field, input path or None, note, source) for every documented field."""
    return [
        (operation, field, path, note, source)
        for operation, spec in OPERATIONS.items()
        for field, (path, note, source) in spec["fields"].items()
    ]


__all__ = ["DIFFERENCES", "LOCAL_INPUTS", "OPERATIONS", "documented_fields"]
