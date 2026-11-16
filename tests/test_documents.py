"""Sales invoices, purchase invoices and orders: what is sent, totals, refusals."""

from __future__ import annotations

from decimal import Decimal
from typing import Any

import pytest
from support import TOKEN, FakeCentas, dumped, ok, refused, run

LINE = {
    "code": "11222",
    "name": "Kompiuteris",
    "unit": "vnt.",
    "quantity": 2,
    "price": 1050,
    "vat_percent": 21,
}


def invoice(**extra: Any) -> dict[str, Any]:
    return {
        "number": "S-1",
        "date": "2026-11-16",
        "buyer_name": "UAB Pirkejas",
        "lines": [LINE],
        **extra,
    }


def test_sales_invoice_is_sent_once_in_the_form_body_over_https() -> None:
    fake = FakeCentas(documents__create=ok(document_id="abc123"))
    response = run(fake, "send_sales_invoice", invoice(buyer_eu_type="eu", due_date="2026-12-01"))
    assert response["ok"] is True, response
    assert response["external_effect_status"] == "succeeded"
    assert response["definitely_no_external_effect"] is False
    [call] = fake.calls
    assert call.url == "https://ws.centas.lt/v1/documents/create"
    assert call.verb == "POST"
    assert call.query == {}
    assert TOKEN not in call.url
    assert call.form["token"] == TOKEN
    assert call.form["dok_num"] == "S-1"
    assert call.form["data"] == "2026.11.16"
    assert call.form["apmok_iki"] == "2026.12.01"
    assert call.form["pirkejas"] == "UAB Pirkejas"
    assert call.form["estipas"] == "1"
    assert call.form["bepvm_suma"] == "2100.00"
    assert call.form["pvm_suma"] == "441.00"
    assert call.form["dok_suma"] == "2541.00"
    assert call.rows() == [
        {
            "kodas": "11222",
            "pavadinimas": "Kompiuteris",
            "matovnt": "vnt.",
            "kiekis": "2",
            "kaina": "1050",
            "pvmtar": "21",
        }
    ]
    result = response["result"]
    assert result == {
        "document_id": "abc123",
        "number": "S-1",
        "net_total": "2100.00",
        "vat_total": "441.00",
        "total": "2541.00",
        "warnings": [],
        "external_effect_status": "succeeded",
        "definitely_no_external_effect": False,
    }


def test_every_optional_field_goes_to_its_documented_name() -> None:
    fake = FakeCentas(documents__create=ok(document_id="x"))
    inputs = invoice(
        transaction_id="T1",
        buyer_code="K1",
        buyer_company_code="123",
        buyer_vat_code="LT1",
        buyer_email="a@b.lt",
        buyer_city="Vilnius",
        buyer_address="Gatve 1",
        buyer_country="LT",
        buyer_group="G",
        receivable_account="2410",
        project="P",
        order_number="U1",
        operation_description="Op",
        issued_by="Jonas",
        issued_by_position="Vadovas",
        intrastat_transport="3",
        intrastat_delivery_terms="EXW",
        intrastat_transaction="11",
        intrastat_county="01",
        intrastat_eu_country="DE",
        vat_payable_account="4492",
        income_account="5000",
        cost="10.5",
        note="Line 1\nLine 2",
    )
    assert run(fake, "send_sales_invoice", inputs)["ok"] is True
    form = fake.calls[0].form
    expected = {
        "trans_id": "T1",
        "kl_kodas": "K1",
        "im_kodas": "123",
        "pvm_kodas": "LT1",
        "email": "a@b.lt",
        "miestas": "Vilnius",
        "adresas": "Gatve 1",
        "salis": "LT",
        "grupe": "G",
        "sask_pirkskol": "2410",
        "projektas": "P",
        "uzsaknr": "U1",
        "oper_apras": "Op",
        "israse_asmuo": "Jonas",
        "israse_pareigos": "Vadovas",
        "intrs_transprusis": "3",
        "intrs_pristsal": "EXW",
        "intrs_sandoris": "11",
        "intrs_apskritis": "01",
        "intrs_eusalis": "DE",
        "sask_moketpvm": "4492",
        "sask_pajamos": "5000",
        "savikaina": "10.50",
        "pastaba": "Line 1\nLine 2",
    }
    for key, value in expected.items():
        assert form[key] == value, key
    assert "isaf" not in form and "asmuo_status" not in form and "salis_kodas" not in form


def test_line_fields_and_decimals_are_written_plainly() -> None:
    fake = FakeCentas(documents__create=ok(document_id="x"))
    line = {
        "code": "A",
        "quantity": "1.5",
        "price": Decimal("10.123456"),
        "vat_percent": "9",
        "vat_code": "PVM1",
        "income_account": "500",
        "project": "P1",
    }
    run(fake, "send_sales_invoice", invoice(lines=[line]))
    [row] = fake.calls[0].rows()
    assert row == {
        "kodas": "A",
        "kiekis": "1.5",
        "kaina": "10.123456",
        "pvmtar": "9",
        "Mok_kodas": "PVM1",
        "sask_pajamos": "500",
        "projektas": "P1",
    }
    # 1.5 × 10.123456 = 15.185184 → 15.19; VAT 9 % = 1.3671 → 1.37
    assert fake.calls[0].form["bepvm_suma"] == "15.19"
    assert fake.calls[0].form["pvm_suma"] == "1.37"


def test_automatic_number_needs_the_transaction_id() -> None:
    fake = FakeCentas(documents__create=ok(document_id="x"))
    response = run(fake, "send_sales_invoice", invoice(number=None))
    assert response["error_code"] == "invalid_payload"
    assert response["definitely_no_external_effect"] is True
    assert fake.calls == []
    response = run(fake, "send_sales_invoice", invoice(number="auto", transaction_id="T9"))
    assert response["ok"] is True
    assert fake.calls[0].form["dok_num"] == "auto"
    assert fake.calls[0].form["trans_id"] == "T9"


def test_given_totals_are_checked_and_sent_as_given() -> None:
    fake = FakeCentas(documents__create=ok(document_id="x"))
    lines = [dict(LINE, quantity=1, price="0.335", vat_percent=21) for _ in range(3)]
    # Lines: 3 × 0.34 = 1.02 net; VAT 3 × 0.07 = 0.21. The document says 1.01 / 0.21.
    response = run(
        fake,
        "send_sales_invoice",
        invoice(lines=lines, net_total="1.01", vat_total="0.21", total="1.22"),
    )
    assert response["ok"] is True, response
    assert fake.calls[0].form["bepvm_suma"] == "1.01"
    assert fake.calls[0].form["dok_suma"] == "1.22"


@pytest.mark.parametrize(
    "totals",
    [
        {"net_total": "2100.00", "vat_total": "441.00", "total": "2541.01"},
        {"net_total": "2100.02", "vat_total": "441.00"},
        {"net_total": "2100.00", "vat_total": "440.98"},
    ],
)
def test_totals_that_do_not_match_stop_with_a_conflict(totals: dict[str, str]) -> None:
    fake = FakeCentas()
    response = run(fake, "send_sales_invoice", invoice(**totals))
    assert response["error_code"] == "conflict"
    assert response["definitely_no_external_effect"] is True
    assert response["external_effect_status"] == "failed"
    assert fake.calls == []


def test_partial_totals_are_refused() -> None:
    response = run(FakeCentas(), "send_sales_invoice", invoice(total="2541.00"))
    assert response["error_code"] == "invalid_payload"


@pytest.mark.parametrize(
    "bad",
    [
        {"date": "16.11.2026"},
        {"date": "2026-02-30"},
        {"lines": []},
        {"lines": [dict(LINE, quantity=0)]},
        {"lines": [dict(LINE, quantity=-1)]},
        {"lines": [dict(LINE, price="-1")]},
        {"lines": [dict(LINE, price="1.1234567")]},
        {"lines": [dict(LINE, price="1e5")]},
        {"lines": [dict(LINE, price=1.5)]},
        {"lines": [dict(LINE, vat_percent=101)]},
        {"lines": [dict(LINE, colour="red")]},
        {"lines": [{k: v for k, v in LINE.items() if k != "vat_percent"}]},
        {"buyer_name": "A\x00B"},
        {"buyer_eu_type": "mars"},
        {"income_account": "50A"},
        {"surprise": "x"},
        {"net_total": "1.001", "vat_total": "0"},
    ],
)
def test_bad_inputs_are_refused_before_anything_is_sent(bad: dict[str, Any]) -> None:
    fake = FakeCentas()
    response = run(fake, "send_sales_invoice", invoice(**bad))
    assert response["ok"] is False
    assert response["error_code"] == "invalid_payload", response
    assert response["definitely_no_external_effect"] is True
    assert fake.calls == []


def test_a_refusal_after_sending_leaves_the_outcome_unknown() -> None:
    fake = FakeCentas(documents__create=refused("Nerastas pirkėjas"))
    response = run(fake, "send_sales_invoice", invoice())
    assert response["error_code"] == "upstream_validation_failed"
    assert "Nerastas pirkėjas" in response["error"]
    assert response["external_effect_status"] == "timeout_unknown"
    assert response["definitely_no_external_effect"] is False
    assert len(fake.calls) == 1


def test_a_missing_id_is_a_warning_not_a_failure() -> None:
    fake = FakeCentas(documents__create=ok())
    response = run(fake, "send_sales_invoice", invoice())
    assert response["ok"] is True
    assert response["result"]["document_id"] is None
    assert response["result"]["warnings"]


def test_test_mode_checks_and_sends_nothing() -> None:
    fake = FakeCentas()
    response = run(fake, "send_sales_invoice", invoice(), test_mode=True)
    assert response["ok"] is True
    assert fake.calls == []
    assert response["external_effect_status"] == "failed"
    assert response["definitely_no_external_effect"] is True
    assert response["result"]["document_id"] is None
    assert response["result"]["total"] == "2541.00"
    bad = run(fake, "send_sales_invoice", invoice(lines=[]), test_mode=True)
    assert bad["error_code"] == "invalid_payload"


def test_order_lines_carry_both_vat_names() -> None:
    fake = FakeCentas(orders__create=ok(order_hash="h1"))
    line = {
        "code": "11222",
        "supplier_code": "122",
        "name": "Kompiuteris",
        "unit": "vnt.",
        "quantity": 2,
        "price": 1050,
        "vat_percent": 21,
    }
    response = run(
        fake,
        "send_order",
        {
            "number": "U-1",
            "date": "2026-11-16",
            "customer_name": "Jonas",
            "customer_phone": "+370600",
            "warehouse": "S1",
            "delivery_date": "2026-11-20",
            "customer_note": "Skambinti",
            "lines": [line],
        },
    )
    assert response["ok"] is True, response
    call = fake.calls[0]
    assert call.url == "https://ws.centas.lt/v1/orders/create"
    assert call.form["uzsak_num"] == "U-1"
    assert call.form["uzsak_data"] == "2026.11.16"
    assert call.form["uzsakovas"] == "Jonas"
    assert call.form["tel"] == "+370600"
    assert call.form["sandelis"] == "S1"
    assert call.form["pristat_data"] == "2026.11.20"
    assert call.form["uzsakovas_pastaba"] == "Skambinti"
    assert call.form["uzsak_suma"] == "2541.00"
    assert call.rows() == [
        {
            "kodas": "11222",
            "t_kodas": "122",
            "pavadinimas": "Kompiuteris",
            "matovnt": "vnt.",
            "kiekis": "2",
            "kaina": "1050",
            "pvm_tar": "21",
            "pvmtar": "21",
        }
    ]
    assert response["result"]["order_hash"] == "h1"


def test_purchase_invoice_sends_every_required_field() -> None:
    fake = FakeCentas(documents__purchase__import=ok(purchase_id=1))
    response = run(
        fake,
        "send_purchase_invoice",
        {
            "seller_name": "UAB Tiekejas",
            "number": "P-9",
            "date": "2026-11-01",
            "lines": [dict(LINE, vat_code="PVM1")],
        },
    )
    assert response["ok"] is True, response
    form = fake.calls[0].form
    assert set(form) == {
        "token",
        "kontrah",
        "data",
        "dok_suma",
        "dok_num",
        "pvm_suma",
        "bepvm_suma",
        "rows",
    }
    assert form["kontrah"] == "UAB Tiekejas"
    assert form["dok_suma"] == "2541.00"
    assert response["result"]["purchase_id"] == "1"


def test_purchase_lines_refuse_an_income_account() -> None:
    response = run(
        FakeCentas(),
        "send_purchase_invoice",
        {
            "seller_name": "S",
            "number": "P",
            "date": "2026-11-01",
            "lines": [dict(LINE, income_account="500")],
        },
    )
    assert response["error_code"] == "invalid_payload"


def test_the_key_never_appears_in_a_result_or_an_error() -> None:
    fake = FakeCentas(documents__create=refused(f"Bad token {TOKEN}"))
    response = run(fake, "send_sales_invoice", invoice())
    assert TOKEN not in dumped(response)
    assert "[redacted]" in response["error"]


LIMIT = "999999999999999.99"


def test_amounts_up_to_fifteen_whole_digits_are_sent() -> None:
    fake = FakeCentas(documents__create=ok(document_id="x"))
    line = {"code": "A", "quantity": 1, "price": LIMIT, "vat_percent": 0}
    response = run(fake, "send_sales_invoice", invoice(lines=[line]))
    assert response["ok"] is True, response
    assert fake.calls[0].form["dok_suma"] == LIMIT
    given = invoice(lines=[line], net_total=LIMIT, vat_total="0", total=LIMIT)
    assert (
        run(FakeCentas(documents__create=ok(document_id="x")), "send_sales_invoice", given)["ok"]
        is True
    )


@pytest.mark.parametrize(
    "bad",
    [
        # One line beyond the limit: quantity × price.
        {"lines": [{"code": "A", "quantity": 2, "price": LIMIT, "vat_percent": 0}]},
        # One line within it, its VAT beyond.
        {"lines": [{"code": "A", "quantity": 1, "price": LIMIT, "vat_percent": 21}]},
        # The largest numbers the inputs allow: 30 whole digits before the check.
        {
            "lines": [
                {
                    "code": "A",
                    "quantity": "999999999999999.999999",
                    "price": "999999999999999.999999",
                    "vat_percent": 100,
                }
            ]
        },
        # Two lines within it, their sum beyond.
        {"lines": [{"code": "A", "quantity": 1, "price": LIMIT, "vat_percent": 0}] * 2},
        # Given totals whose sum is beyond it.
        {
            "lines": [{"code": "A", "quantity": 1, "price": LIMIT, "vat_percent": 0}],
            "net_total": LIMIT,
            "vat_total": "0.01",
        },
    ],
)
def test_amounts_beyond_fifteen_whole_digits_are_refused_unsent(bad: dict[str, Any]) -> None:
    fake = FakeCentas()
    for operation, inputs in (
        ("send_sales_invoice", invoice(**bad)),
        ("send_order", {"number": "U", "date": "2026-11-16", "customer_name": "C", **bad}),
        ("send_purchase_invoice", {"seller_name": "S", "number": "P", "date": "2026-11-16", **bad}),
    ):
        response = run(fake, operation, inputs)
        assert response["error_code"] == "invalid_payload", (operation, response)
        assert "15 whole digits" in response["error"]
        assert response["definitely_no_external_effect"] is True
    assert fake.calls == []
