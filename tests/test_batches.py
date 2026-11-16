"""Payments and products: the XML sent, the counts, the reference check."""

from __future__ import annotations

# Parses only XML the tests build themselves.
import xml.etree.ElementTree as ElementTree  # nosec B405
from typing import Any

import pytest
from support import TOKEN, FakeCentas, dumped, ok, payments_xml, refused, run

PAYMENT = {
    "type": "BankDeb",
    "date": "2026-01-15",
    "amount": "123.23",
    "document_number": "NR001",
    "reference": "ABC001",
    "details": "Apmokėjimas <&>",
    "payer_name": "UAB Moketojas",
    "payer_code": "303030303",
    "account": "LT1234567890",
}


def sent_xml(fake: FakeCentas, path: str) -> ElementTree.Element:
    call = next(c for c in fake.calls if c.path == path)
    assert call.verb == "POST"
    assert call.form["token"] == TOKEN
    assert call.query == {}
    data = call.form["data"]
    assert data.startswith('<?xml version="1.0" encoding="UTF-8"?>\n<root>')
    return ElementTree.fromstring(data)  # nosec B314


def test_payments_are_sent_as_the_documented_xml() -> None:
    fake = FakeCentas(
        payments__export=payments_xml(),
        payments__import=ok(payments_found_xml=1, payments_created=1),
    )
    response = run(fake, "send_payments", {"payments": [PAYMENT]})
    assert response["ok"] is True, response
    assert fake.paths() == ["payments/export", "payments/import"]
    [node] = sent_xml(fake, "payments/import")
    assert [(c.tag, c.text) for c in node] == [
        ("PaymentType", "BankDeb"),
        ("Date", "2026.01.15"),
        ("Amount", "123.23"),
        ("DocNr", "NR001"),
        ("RefNr", "ABC001"),
        ("Details", "Apmokėjimas <&>"),
        ("RecName", "UAB Moketojas"),
        ("RecId", "303030303"),
        ("ToAccountNumber", "LT1234567890"),
    ]
    assert response["result"]["sent"] == 1
    assert response["result"]["created"] == 1
    assert response["result"]["references"] == ["ABC001"]
    assert response["result"]["warnings"] == []
    assert response["external_effect_status"] == "succeeded"


def test_only_given_payment_fields_are_sent() -> None:
    fake = FakeCentas(
        payments__export=payments_xml(),
        payments__import=ok(payments_found_xml=1, payments_created=1),
    )
    minimal = {"type": "BankDeb", "date": "2026-01-15", "amount": 5, "reference": "R1"}
    run(fake, "send_payments", {"payments": [minimal]})
    [node] = sent_xml(fake, "payments/import")
    assert [c.tag for c in node] == ["PaymentType", "Date", "Amount", "RefNr"]
    assert node.find("Amount").text == "5.00"  # type: ignore[union-attr]


def test_a_reference_already_in_the_export_stops_the_batch_unsent() -> None:
    fake = FakeCentas(
        payments__export=payments_xml(
            "<RefNr>ABC001</RefNr><Amount>1</Amount>", "<RefNr>OTHER</RefNr>"
        ),
        payments__import=ok(payments_found_xml=2, payments_created=2),
    )
    two = [PAYMENT, dict(PAYMENT, reference="NEW002")]
    response = run(fake, "send_payments", {"payments": two})
    assert response["error_code"] == "conflict"
    assert response["definitely_no_external_effect"] is True
    assert response["external_effect_status"] == "failed"
    assert "1 of their references (ABC001)" in response["error"]
    assert fake.paths() == ["payments/export"]


def test_many_repeated_references_are_named_up_to_twenty() -> None:
    refs = [f"R{n:03d}" for n in range(25)]
    export = payments_xml(*(f"<RefNr>{r}</RefNr>" for r in refs))
    fake = FakeCentas(payments__export=export)
    payments = [dict(PAYMENT, reference=r) for r in refs]
    response = run(fake, "send_payments", {"payments": payments})
    assert response["error_code"] == "conflict"
    assert "25 of their references" in response["error"]
    assert "R019 …" in response["error"] and "R020" not in response["error"]
    assert fake.paths() == ["payments/export"]


@pytest.mark.parametrize(
    ("answer", "code"),
    [
        ((500, b""), "upstream_failure"),
        ((401, {"success": 0, "error": "Invalid or expired token."}), "authentication_failed"),
        (b"not xml", "invalid_response"),
        (TimeoutError(), "timeout"),
        ({"success": 0, "error": "Klaida"}, "upstream_validation_failed"),
    ],
)
def test_an_unreadable_export_stops_the_batch_unsent(answer: Any, code: str) -> None:
    fake = FakeCentas(
        payments__export=answer, payments__import=ok(payments_found_xml=1, payments_created=1)
    )
    response = run(fake, "send_payments", {"payments": [PAYMENT]})
    assert response["error_code"] == code, response
    assert response["definitely_no_external_effect"] is True
    assert response["external_effect_status"] == "failed"
    assert response["error"].startswith("No payments were sent")
    assert fake.paths() == ["payments/export"]


def test_an_export_too_large_stops_the_batch_unsent(monkeypatch: pytest.MonkeyPatch) -> None:
    from runtime import transport

    monkeypatch.setattr(transport, "MAX_EXPORT_BYTES", 10)
    fake = FakeCentas(payments__export=payments_xml("<RefNr>X</RefNr>"))
    response = run(fake, "send_payments", {"payments": [PAYMENT]})
    assert response["error_code"] == "response_too_large"
    assert response["definitely_no_external_effect"] is True
    assert fake.paths() == ["payments/export"]


def test_no_time_left_after_the_export_stops_the_batch_unsent() -> None:
    times = iter([0.0, 0.0])
    fake = FakeCentas(payments__export=payments_xml())

    def clock() -> float:
        # Deadline set at 0 s, the export starts at 0 s, then time is up.
        return next(times, 1000.0)

    response = run(fake, "send_payments", {"payments": [PAYMENT]}, clock=clock)
    assert response["error_code"] == "timeout"
    assert response["definitely_no_external_effect"] is True
    assert "payments/import" not in fake.paths()


def test_running_out_of_time_reading_the_export_is_reported_as_unsent() -> None:
    times = iter([0.0])
    fake = FakeCentas(payments__export=payments_xml())

    def clock() -> float:
        return next(times, 1000.0)

    response = run(fake, "send_payments", {"payments": [PAYMENT]}, clock=clock)
    assert response["error_code"] == "timeout"
    assert response["definitely_no_external_effect"] is True
    assert response["error"].startswith("No payments were sent")
    assert fake.paths() == []


def test_counts_that_do_not_add_up_are_warnings_with_the_numbers() -> None:
    fake = FakeCentas(
        payments__export=payments_xml(),
        payments__import=ok(payments_found_xml=2, payments_created=1),
    )
    two = [PAYMENT, dict(PAYMENT, reference="ABC002")]
    response = run(fake, "send_payments", {"payments": two})
    assert response["ok"] is True
    assert any("created 1 of the 2" in w for w in response["result"]["warnings"])


def test_a_refused_batch_leaves_the_outcome_unknown() -> None:
    fake = FakeCentas(payments__export=payments_xml(), payments__import=refused("XML klaida"))
    response = run(fake, "send_payments", {"payments": [PAYMENT]})
    assert response["error_code"] == "upstream_validation_failed"
    assert response["external_effect_status"] == "timeout_unknown"
    assert response["definitely_no_external_effect"] is False


@pytest.mark.parametrize(
    "bad",
    [
        [PAYMENT, PAYMENT],
        [dict(PAYMENT, reference="")],
        [dict(PAYMENT, amount="0")],
        [dict(PAYMENT, amount="-5")],
        [dict(PAYMENT, amount="1.001")],
        [dict(PAYMENT, type="Bank Deb")],
        [dict(PAYMENT, date="2026.01.15")],
        [dict(PAYMENT, extra=1)],
        [dict(PAYMENT, details="a\x01b")],
        [],
        "not a list",
    ],
)
def test_bad_payments_are_refused_before_anything_is_read_or_sent(bad: Any) -> None:
    fake = FakeCentas()
    response = run(fake, "send_payments", {"payments": bad})
    assert response["error_code"] == "invalid_payload", response
    assert fake.calls == []


PRODUCT = {
    "code": "C001",
    "id": "101",
    "name": "Programa nr. 1",
    "unit": "vnt.",
    "price": "100.00",
    "vat_percent": 21,
    "stock": "250",
    "group1": "G1",
    "barcode": "123456789",
    "description": "Aprašymas\nantra eilutė",
    "photo": "https://example.lt/a.jpg",
    "stocks": [{"warehouse_id": "1", "warehouse_name": "Sandelis Nr. 1", "quantity": "18566.644"}],
    "parameters": [{"name": "Kuras", "value": "Dujos"}],
}


def test_products_are_sent_with_the_key_in_every_item_as_documented() -> None:
    fake = FakeCentas(
        products__import=ok(products_found_xml=1, products_created=1, products_updated=0)
    )
    response = run(fake, "send_products", {"products": [PRODUCT]})
    assert response["ok"] is True, response
    [item] = sent_xml(fake, "products/import")
    assert [c.tag for c in item] == [
        "token",
        "oper",
        "id",
        "kodas",
        "pavadinimas",
        "matovnt",
        "kaina",
        "pvmtar",
        "likutis",
        "grupe1",
        "barkodas",
        "aprasymas",
        "Nuotrauka",
        "Stocks",
        "ProductParameters",
    ]
    assert item.findtext("token") == TOKEN
    assert item.findtext("oper") == "UPD"
    assert item.findtext("kaina") == "100"
    assert item.findtext("Stocks/Stock/Quantity") == "18566.644"
    assert item.findtext("ProductParameters/Parameter/Value") == "Dujos"
    result = response["result"]
    assert (result["found"], result["created"], result["updated"]) == (1, 1, 0)
    assert TOKEN not in dumped(response)


def test_a_product_with_only_its_code_sends_nothing_else() -> None:
    fake = FakeCentas(
        products__import=ok(products_found_xml=1, products_created=0, products_updated=1)
    )
    run(fake, "send_products", {"products": [{"code": "C9"}]})
    [item] = sent_xml(fake, "products/import")
    assert [c.tag for c in item] == ["token", "oper", "kodas"]


def test_missing_counts_are_a_warning() -> None:
    fake = FakeCentas(products__import=ok())
    response = run(fake, "send_products", {"products": [{"code": "C9"}]})
    assert response["ok"] is True
    assert response["result"]["warnings"]


@pytest.mark.parametrize(
    "bad",
    [
        [{"code": "A"}, {"code": "A"}],
        [{"name": "no code"}],
        [{"code": "A", "price": "-1"}],
        [{"code": "A", "stocks": [{"quantity": 1}]}],
        [{"code": "A", "parameters": [{"value": "x"}]}],
        [{"code": "A", "colour": "red"}],
    ],
)
def test_bad_products_are_refused(bad: Any) -> None:
    fake = FakeCentas()
    response = run(fake, "send_products", {"products": bad})
    assert response["error_code"] == "invalid_payload"
    assert fake.calls == []


def test_test_mode_sends_no_batch() -> None:
    fake = FakeCentas()
    for operation, inputs in (
        ("send_payments", {"payments": [PAYMENT]}),
        ("send_products", {"products": [PRODUCT]}),
    ):
        response = run(fake, operation, inputs, test_mode=True)
        assert response["ok"] is True
        assert response["result"]["sent"] == 0
    assert fake.calls == []
