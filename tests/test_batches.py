"""XML writes: the XML sent, the counts, the refusals before sending."""

from __future__ import annotations

import base64

# Parses only XML the tests build themselves.
import xml.etree.ElementTree as ElementTree  # nosec B405
from typing import Any

import pytest
from support import TOKEN, FakeCentas, Files, dumped, ok, refused, run


def sent_xml(fake: FakeCentas, path: str) -> ElementTree.Element:
    call = next(c for c in fake.calls if c.path == path)
    assert call.verb == "POST"
    assert call.query == {}
    data = call.form["data"]
    assert data.startswith('<?xml version="1.0" encoding="UTF-8"?>\n<root')
    return ElementTree.fromstring(data)  # nosec B314


PAYMENT = {
    "type": "BankDeb",
    "date": "2026-01-15",
    "amount": "121.00",
    "document_number": "PAY-001",
    "details": "Payment for INV-001 <&>",
    "payer_name": "UAB Customer",
    "reference": "REF-001",
    "payer_code": "123456789",
    "receiver": "UAB Receiver",
    "account": "LT123456789012345678",
}


def test_payments_are_items_as_the_specification_shows() -> None:
    fake = FakeCentas(payments__import=ok(payments_found_xml=1, payments_created=1))
    response = run(fake, "send_payments", {"payments": [PAYMENT]})
    assert response["ok"] is True, response
    assert fake.paths() == ["payments/import"]
    [node] = sent_xml(fake, "payments/import")
    assert node.tag == "item"
    assert [(c.tag, c.text) for c in node] == [
        ("PaymentType", "BankDeb"),
        ("Date", "2026-01-15"),
        ("Amount", "121.00"),
        ("DocNr", "PAY-001"),
        ("RefNr", "REF-001"),
        ("Details", "Payment for INV-001 <&>"),
        ("RecName", "UAB Customer"),
        ("RecId", "123456789"),
        ("Receiver", "UAB Receiver"),
        ("ToAccountNumber", "LT123456789012345678"),
    ]
    assert response["result"] == {
        "sent": 1,
        "payments_found_xml": 1,
        "payments_created": 1,
        "warnings": [],
        "external_effect_status": "succeeded",
        "definitely_no_external_effect": False,
    }


def test_counts_that_do_not_add_up_are_warnings_with_the_numbers() -> None:
    fake = FakeCentas(payments__import=ok(payments_found_xml=2, payments_created=1))
    response = run(
        fake, "send_payments", {"payments": [PAYMENT, dict(PAYMENT, reference="REF-002")]}
    )
    assert any("created 1 of the 2" in w for w in response["result"]["warnings"])


@pytest.mark.parametrize(
    "bad",
    [
        [PAYMENT, PAYMENT],
        [dict(PAYMENT, type="Bank")],
        [{k: v for k, v in PAYMENT.items() if k != "details"}],
        [{k: v for k, v in PAYMENT.items() if k != "payer_name"}],
        [{k: v for k, v in PAYMENT.items() if k != "document_number"}],
        [dict(PAYMENT, amount="0")],
        [dict(PAYMENT, amount="1.001")],
        [dict(PAYMENT, date="2026.01.15")],
        [dict(PAYMENT, extra=1)],
        [],
    ],
)
def test_bad_payments_are_refused_before_sending(bad: Any) -> None:
    fake = FakeCentas()
    assert run(fake, "send_payments", {"payments": bad})["error_code"] == "invalid_payload"
    assert fake.calls == []


PRODUCT = {
    "code": "PRD-001",
    "id": "123",
    "name": "Widget A",
    "unit": "vnt",
    "price": "10.00",
    "cost": "6.5",
    "vat_percent": 21,
    "stock": "100",
    "group1": "G1",
    "group4": "G4",
    "barcode": "4750000000001",
    "description": "Aprašymas\nantra",
    "manufacturer": "ACME",
    "net_weight": "1.2",
    "gross_weight": "1.5",
    "analog_products": ["A1", "A2"],
    "recommended_products": ["R1"],
    "photo": "https://example.lt/a.jpg",
    "vat_code": "PVM1",
    "ordered": "3",
    "warehouse": "S1",
    "stocks": [{"warehouse_id": "1", "warehouse_name": "Main", "quantity": "100"}],
    "parameters": [{"name": "Color", "value": "Red"}],
}


def test_products_carry_every_field_given_and_nothing_else() -> None:
    fake = FakeCentas(
        products__import=ok(products_found_xml=1, products_created=1, products_updated=0)
    )
    response = run(fake, "send_products", {"products": [PRODUCT]})
    assert response["ok"] is True, response
    [item] = sent_xml(fake, "products/import")
    values = {c.tag: c.text for c in item if len(c) == 0}
    assert values["token"] == TOKEN
    assert values["oper"] == "UPD"
    assert values["AnalogProducts"] == "A1,A2"
    assert values["savikaina"] == "6.5" and values["mok_kodas"] == "PVM1"
    assert values["grupe4"] == "G4" and "grupe2" not in values
    assert item.findtext("Stocks/Stock/Quantity") == "100"
    assert item.findtext("ProductParameters/Parameter/Value") == "Red"
    assert response["result"]["products_created"] == 1
    assert TOKEN not in dumped(response)
    minimal = FakeCentas(
        products__import=ok(products_found_xml=1, products_created=0, products_updated=1)
    )
    run(minimal, "send_products", {"products": [{"code": "C9"}]})
    assert [c.tag for c in sent_xml(minimal, "products/import")[0]] == ["token", "oper", "kodas"]


@pytest.mark.parametrize(
    "bad",
    [
        [{"code": "A"}, {"code": "A"}],
        [{"name": "no code"}],
        [{"code": "A", "price": "-1"}],
        [{"code": "A", "analog_products": ["x,y"]}],
        [{"code": "A", "stocks": [{"quantity": 1}]}],
        [{"code": "A", "colour": "red"}],
    ],
)
def test_bad_products_are_refused(bad: Any) -> None:
    fake = FakeCentas()
    assert run(fake, "send_products", {"products": bad})["error_code"] == "invalid_payload"
    assert fake.calls == []


CONTRAHENT = {
    "name": "UAB Partner",
    "id": "1",
    "company_code": "123456789",
    "vat_code": "LT123456789",
    "country": "LT",
    "city": "Vilnius",
    "address": "Main Street 1",
    "email": "p@example.com",
    "phone": "+37060000000",
    "iban": "LT123456789012345678",
    "is_buyer": True,
    "is_supplier": False,
    "debt": "0",
    "branches": [{"name": "Branch Office", "city": "Kaunas"}],
}


def test_contrahents_and_branch_deletions_are_reported() -> None:
    fake = FakeCentas(
        contrahents__import=ok(
            contrahents_found_xml=1,
            contrahents_created=0,
            contrahents_updated=1,
            branches_created=1,
            branches_updated=0,
            branches_deleted=2,
        )
    )
    response = run(fake, "send_contrahents", {"contrahents": [CONTRAHENT]})
    assert response["ok"] is True, response
    [item] = sent_xml(fake, "contrahents/import")
    assert item.findtext("oper") == "UPD"
    assert item.findtext("imones_kodas") == "123456789"
    assert item.findtext("pirkejas") == "1" and item.findtext("tiekejas") == "0"
    assert item.findtext("skola") == "0.00"
    assert item.findtext("padaliniai/padalinis/pavad") == "Branch Office"
    assert item.find("token") is None
    assert "deleted 2 branches" in response["result"]["warnings"][0]


def test_document_status_updates_need_one_change_and_carry_the_key() -> None:
    fake = FakeCentas(documents__update=ok(documents_found=1, documents_updated=1))
    doc = {
        "type": "deb",
        "number": "DOK-002",
        "date": "2024-01-02",
        "paid": False,
        "remaining_debt": "50",
    }
    response = run(fake, "update_sales_documents", {"documents": [doc]})
    assert response["ok"] is True, response
    [item] = sent_xml(fake, "documents/update")
    assert [(c.tag, c.text) for c in item] == [
        ("token", TOKEN),
        ("type", "deb"),
        ("number", "DOK-002"),
        ("date", "2024-01-02"),
        ("apmoketa", "false"),
        ("dok_skola", "50.00"),
    ]
    bare = {"type": "deb", "number": "DOK-002", "date": "2024-01-02"}
    assert (
        run(FakeCentas(), "update_sales_documents", {"documents": [bare]})["error_code"]
        == "invalid_payload"
    )


@pytest.mark.parametrize(
    "bad",
    [
        [{"type": "deb", "number": "DOK-*", "date": "2024-01-01"}],
        [{"type": "deb", "number": "%", "date": "2024-01-01"}],
        [{"type": "deb", "number": "DOK-1", "date": "2024-01-01"}] * 2,
        [{"type": "deb", "number": "DOK-1"}],
        [{"type": "deb", "number": f"D{n}", "date": "2024-01-01"} for n in range(51)],
    ],
)
def test_deletions_name_documents_exactly(bad: Any) -> None:
    fake = FakeCentas()
    assert (
        run(fake, "delete_sales_documents", {"documents": bad})["error_code"] == "invalid_payload"
    )
    assert fake.calls == []


def test_deletion_sends_the_named_documents() -> None:
    fake = FakeCentas(documents__delete=ok(documents_found=1, documents_deleted=1))
    response = run(
        fake,
        "delete_sales_documents",
        {"documents": [{"type": "deb", "number": "DOK-001", "date": "2024-01-01"}]},
    )
    assert response["result"]["documents_deleted"] == 1
    [item] = sent_xml(fake, "documents/delete")
    assert item.findtext("number") == "DOK-001" and item.findtext("token") == TOKEN


def test_document_payments_nest_their_payments() -> None:
    fake = FakeCentas(
        documents__payments__create=ok(documents_payments_found_xml=1, documents_payments_created=1)
    )
    doc = {
        "type": "deb",
        "number": "INV-001",
        "date": "2024-01-15",
        "paid_sum": "121",
        "paid_in_full": True,
        "customer_id": "123",
        "payments": [
            {"date": "2024-01-20", "number": "PAY-001", "description": "Bank", "total": "121"}
        ],
    }
    response = run(fake, "record_document_payments", {"documents": [doc]})
    assert response["ok"] is True, response
    [item] = sent_xml(fake, "documents/payments/create")
    assert item.findtext("paid_sum") == "121.00" and item.findtext("paid_full") == "1"
    assert item.findtext("customerId") == "123"
    assert item.findtext("payment/total") == "121.00"


def test_a_consignment_note_is_one_document() -> None:
    fake = FakeCentas(consignments__import=ok(consignment_rows_created=2))
    response = run(
        fake,
        "send_consignment",
        {
            "document_uid": "CN-001",
            "document_number": "ORD-001",
            "document_date": "2024-01-15",
            "estimated_arrival": "2024-01-20",
            "consignee_name": "UAB Receiver",
            "consignee_code": "123456789",
            "lines": [
                {"description": "Widget A", "unit": "vnt", "quantity": 100},
                {"description": "Widget B", "unit": "kg", "quantity": "50.5"},
            ],
        },
    )
    assert response["ok"] is True, response
    root = sent_xml(fake, "consignments/import")
    assert root.findtext("DocumentUID") == "CN-001"
    assert root.findtext("EstimatedTimeOfArrival") == "2024-01-20"
    assert [e.findtext("Quantity") for e in root.findall("eilute")] == ["100", "50.5"]
    assert response["result"]["consignment_rows_created"] == 2


COMPANY_INVOICE = {
    "receiver_company_code": "123456789",
    "receiver_name": "UAB Receiver",
    "receiver_email": "r@example.com",
    "number": "PUR-001",
    "date": "2024-01-15",
    "due_date": "2024-02-15",
    "seller_name": "UAB Sender",
    "document_type": "deb",
    "country_code": "LT",
    "paid": False,
    "remaining_debt": "121",
    "lines": [
        {
            "code": "PRD-001",
            "kind": "P",
            "ean": "4750000000001",
            "name": "Widget A",
            "unit": "vnt",
            "quantity": 10,
            "price": "10",
            "vat_percent": 21,
            "vat_code": "PVM1",
        }
    ],
}


def test_an_invoice_to_another_company_carries_the_key_inside_its_xml() -> None:
    fake = FakeCentas(
        purchase__import=ok(purchase_rows_created=1, document_rows_created=1, email_sent=False)
    )
    files = Files(content=b"%PDF-1.4 invoice")
    response = run(
        fake, "send_invoice_to_company", {**COMPANY_INVOICE, "pdf_file": "art_9"}, files=files
    )
    assert response["ok"] is True, response
    call = fake.calls[0]
    assert "token" not in call.form and call.query == {}
    root = sent_xml(fake, "purchase/import")
    assert root.findtext("siuntejas/token") == TOKEN
    assert root.findtext("gavejas/send_email") == "false"
    assert root.findtext("dokumentas/dok_suma") == "121.00"
    assert root.findtext("dokumentas/apmoketa") == "false"
    assert root.findtext("dokumentas/pdf_name") == "PUR-001.pdf"
    assert base64.b64decode(root.findtext("dokumentas/pdf_base64") or "") == files.content
    row = root.find("dokumentas/eilute")
    assert row is not None
    assert [c.tag for c in row] == [
        "kodas",
        "prek_pasl",
        "ean",
        "pavadinimas",
        "matovnt",
        "kiekis",
        "kaina",
        "pvmtar",
        "mok_kodas",
    ]
    assert response["result"]["email_requested"] is False
    assert TOKEN not in dumped(response)


def test_the_receiver_e_mail_is_sent_only_when_asked() -> None:
    fake = FakeCentas(purchase__import=ok(email_sent=True))
    response = run(fake, "send_invoice_to_company", {**COMPANY_INVOICE, "send_email": True})
    assert sent_xml(fake, "purchase/import").findtext("gavejas/send_email") == "true"
    assert response["result"]["email_sent"] is True


def test_an_invoice_to_another_company_needs_a_receiver_code() -> None:
    inputs = {k: v for k, v in COMPANY_INVOICE.items() if k != "receiver_company_code"}
    assert run(FakeCentas(), "send_invoice_to_company", inputs)["error_code"] == "invalid_payload"


def test_a_documented_400_of_the_company_exchange_changes_nothing() -> None:
    fake = FakeCentas(purchase__import=(400, refused("Receiver not found")))
    response = run(fake, "send_invoice_to_company", COMPANY_INVOICE)
    assert response["error_code"] == "upstream_validation_failed"
    assert response["definitely_no_external_effect"] is True


def test_test_mode_sends_no_batch() -> None:
    fake = FakeCentas()
    for operation, inputs in (
        ("send_payments", {"payments": [PAYMENT]}),
        ("send_products", {"products": [PRODUCT]}),
        ("send_contrahents", {"contrahents": [CONTRAHENT]}),
        (
            "delete_sales_documents",
            {"documents": [{"type": "deb", "number": "D", "date": "2024-01-01"}]},
        ),
        ("send_invoice_to_company", COMPANY_INVOICE),
    ):
        response = run(fake, operation, inputs, test_mode=True)
        assert response["ok"] is True, (operation, response)
        assert response["definitely_no_external_effect"] is True
    assert fake.calls == []
