"""Sales invoices, orders and purchase invoices: what is sent, totals, outcomes."""

from __future__ import annotations

from decimal import Decimal
from typing import Any

import pytest
from support import TOKEN, FakeCentas, dumped, ok, refused, run

LINE = {
    "code": "PRD-001",
    "name": "Widget A",
    "unit": "vnt",
    "quantity": 2,
    "price": 1050,
    "vat_percent": 21,
}


def invoice(**extra: Any) -> dict[str, Any]:
    return {
        "number": "INV-001",
        "date": "2026-11-16",
        "due_date": "2026-12-16",
        "buyer_name": "UAB Pirkejas",
        "cost": "50",
        "lines": [LINE],
        **extra,
    }


def test_sales_invoice_is_multipart_with_the_required_fields_over_https() -> None:
    fake = FakeCentas(documents__create=ok(document_id="abc123"))
    response = run(fake, "send_sales_invoice", invoice())
    assert response["ok"] is True, response
    assert response["external_effect_status"] == "succeeded"
    [call] = fake.calls
    assert call.url == "https://ws.centas.lt/v1/documents/create"
    assert call.verb == "POST"
    assert call.headers["content-type"].startswith("multipart/form-data; boundary=")
    assert call.query == {}
    assert TOKEN not in call.url
    form = call.form
    assert form["token"] == TOKEN
    assert {
        k: form[k]
        for k in (
            "pirkejas",
            "data",
            "dok_suma",
            "dok_num",
            "apmok_iki",
            "pvm_suma",
            "bepvm_suma",
            "savikaina",
        )
    } == {
        "pirkejas": "UAB Pirkejas",
        "data": "2026-11-16",
        "dok_suma": "2541.00",
        "dok_num": "INV-001",
        "apmok_iki": "2026-12-16",
        "pvm_suma": "441.00",
        "bepvm_suma": "2100.00",
        "savikaina": "50.00",
    }
    assert call.rows() == [
        {
            "kodas": "PRD-001",
            "pavadinimas": "Widget A",
            "matovnt": "vnt",
            "kiekis": "2",
            "kaina": "1050",
            "pvmtar": "21",
        }
    ]
    assert response["result"] == {
        "document_id": "abc123",
        "number": "INV-001",
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
        buyer_company_code="123",
        buyer_vat_code="LT1",
        buyer_country="LT",
        buyer_city="Vilnius",
        buyer_address="Gatve 1",
        buyer_email="a@b.lt",
        number_series="AB",
        order_number="U1",
        check_order="1",
        document_type="deb",
        transaction_id="T1",
        buyer_code="K1",
        buyer_eu_type="eu",
        buyer_group="G",
        vat_payable_account="4492",
        receivable_account="2410",
        income_account="5000",
        project="P",
        operation_description="Op",
        note="Line 1\nLine 2",
        issued_by="Jonas",
        issued_by_position="Vadovas",
        intrastat_transport="3",
        intrastat_delivery_terms="EXW",
        intrastat_transaction="11",
        intrastat_county="01",
        intrastat_eu_country="DE",
    )
    assert run(fake, "send_sales_invoice", inputs)["ok"] is True
    form = fake.calls[0].form
    expected = {
        "im_kodas": "123",
        "pvm_kodas": "LT1",
        "salis": "LT",
        "miestas": "Vilnius",
        "adresas": "Gatve 1",
        "email": "a@b.lt",
        "dok_num_series": "AB",
        "uzsaknr": "U1",
        "check_order": "1",
        "type": "deb",
        "trans_id": "T1",
        "kl_kodas": "K1",
        "estipas": "1",
        "grupe": "G",
        "sask_moketpvm": "4492",
        "sask_pirkskol": "2410",
        "sask_pajamos": "5000",
        "projektas": "P",
        "oper_apras": "Op",
        "pastaba": "Line 1\nLine 2",
        "israse_asmuo": "Jonas",
        "israse_pareigos": "Vadovas",
        "intrs_transprusis": "3",
        "intrs_pristsal": "EXW",
        "intrs_sandoris": "11",
        "intrs_apskritis": "01",
        "intrs_eusalis": "DE",
    }
    for key, value in expected.items():
        assert form[key] == value, key
    for absent in ("isaf", "asmuo_status", "salis_kodas", "atv_pvm"):
        assert absent not in form


def test_line_options_are_written_with_their_names() -> None:
    fake = FakeCentas(documents__create=ok(document_id="x"))
    line = dict(
        LINE,
        quantity="1.5",
        price=Decimal("10.123456"),
        vat_percent="9",
        kind="P",
        ean="4750000000001",
        vat_code="PVM1",
        income_account="500",
        project="P1",
        hs_code="8471",
        country_origin="LT",
        material="Al",
    )
    run(fake, "send_sales_invoice", invoice(lines=[line]))
    [row] = fake.calls[0].rows()
    assert row == {
        "kodas": "PRD-001",
        "pavadinimas": "Widget A",
        "matovnt": "vnt",
        "kiekis": "1.5",
        "kaina": "10.123456",
        "pvmtar": "9",
        "prek_pasl": "P",
        "ean": "4750000000001",
        "Mok_kodas": "PVM1",
        "sask_pajamos": "500",
        "projektas": "P1",
        "hs_code": "8471",
        "country_origin": "LT",
        "material": "Al",
    }
    # 1.5 × 10.123456 = 15.185184 → 15.19; VAT 9 % = 1.3671 → 1.37
    assert fake.calls[0].form["bepvm_suma"] == "15.19"
    assert fake.calls[0].form["pvm_suma"] == "1.37"


def test_auto_number_is_sent_as_auto() -> None:
    fake = FakeCentas(documents__create=ok(document_id="x"))
    assert run(fake, "send_sales_invoice", invoice(number="AUTO"))["ok"] is True
    assert fake.calls[0].form["dok_num"] == "auto"


def test_discounted_lines_need_the_totals_and_are_not_reconciled() -> None:
    line = dict(LINE, discount_percent="10")
    fake = FakeCentas(documents__create=ok(document_id="x"))
    refused_ = run(fake, "send_sales_invoice", invoice(lines=[line]))
    assert refused_["error_code"] == "invalid_payload"
    assert fake.calls == []
    response = run(
        fake, "send_sales_invoice", invoice(lines=[line], net_total="1890.00", vat_total="396.90")
    )
    assert response["ok"] is True
    assert fake.calls[0].rows()[0]["nuolaida_proc"] == "10"
    assert fake.calls[0].form["dok_suma"] == "2286.90"


def test_given_totals_are_checked_and_sent_as_given() -> None:
    fake = FakeCentas(documents__create=ok(document_id="x"))
    lines = [dict(LINE, quantity=1, price="0.335", vat_percent=21) for _ in range(3)]
    response = run(
        fake,
        "send_sales_invoice",
        invoice(lines=lines, net_total="1.01", vat_total="0.21", total="1.22"),
    )
    assert response["ok"] is True, response
    assert fake.calls[0].form["bepvm_suma"] == "1.01"


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
    assert fake.calls == []


@pytest.mark.parametrize(
    "bad",
    [
        {"date": "16.11.2026"},
        {"due_date": None},
        {"cost": None},
        {"cost": "-1"},
        {"number": None},
        {"lines": []},
        {"lines": [dict(LINE, quantity=0)]},
        {"lines": [dict(LINE, price="-1")]},
        {"lines": [dict(LINE, price="1.1234567")]},
        {"lines": [dict(LINE, price="1e5")]},
        {"lines": [dict(LINE, vat_percent=101)]},
        {"lines": [dict(LINE, colour="red")]},
        {"lines": [dict(LINE, atv_pvm="1")]},
        {"lines": [{k: v for k, v in LINE.items() if k != "unit"}]},
        {"buyer_name": "A\x00B"},
        {"buyer_eu_type": "mars"},
        {"income_account": "50A"},
        {"surprise": "x"},
        {"total": "2541.00"},
    ],
)
def test_bad_inputs_are_refused_before_anything_is_sent(bad: dict[str, Any]) -> None:
    fake = FakeCentas()
    inputs = {k: v for k, v in invoice(**bad).items() if v is not None}
    response = run(fake, "send_sales_invoice", inputs)
    assert response["error_code"] == "invalid_payload", response
    assert response["definitely_no_external_effect"] is True
    assert fake.calls == []


def test_a_documented_400_is_a_refusal_without_effect() -> None:
    fake = FakeCentas(documents__create=(400, refused("The pirkejas field is required.")))
    response = run(fake, "send_sales_invoice", invoice())
    assert response["error_code"] == "upstream_validation_failed"
    assert response["definitely_no_external_effect"] is True
    assert response["external_effect_status"] == "failed"
    assert "pirkejas" in response["error"]


def test_a_duplicate_number_is_a_conflict_without_effect() -> None:
    fake = FakeCentas(
        documents__create=(400, refused("Document with number INV-001 already exists."))
    )
    response = run(fake, "send_sales_invoice", invoice())
    assert response["error_code"] == "conflict"
    assert response["definitely_no_external_effect"] is True


def test_an_unknown_outcome_reports_what_documents_get_shows() -> None:
    fake = FakeCentas(
        documents__create=TimeoutError(),
        documents__get=ok(data={"dok_num": "INV-001", "token": TOKEN}),
    )
    response = run(fake, "send_sales_invoice", invoice())
    assert response["error_code"] == "timeout_unknown"
    assert response["definitely_no_external_effect"] is False
    assert "now lists a document numbered INV-001" in response["error"]
    assert fake.paths() == ["documents/create", "documents/get"]
    assert fake.calls[1].query == {"token": TOKEN, "dok_num": "INV-001"}


def test_the_lookup_never_resends_and_its_failure_changes_nothing() -> None:
    fake = FakeCentas(documents__create=(502, b""), documents__get=(500, b""))
    response = run(fake, "send_sales_invoice", invoice())
    assert response["external_effect_status"] == "timeout_unknown"
    assert fake.paths() == ["documents/create", "documents/get"]
    auto = FakeCentas(documents__create=(502, b""))
    response = run(auto, "send_sales_invoice", invoice(number="auto"))
    assert auto.paths() == ["documents/create"]


def test_success_zero_in_a_200_answer_leaves_the_outcome_unknown() -> None:
    fake = FakeCentas(documents__create=refused("Klaida"), documents__get=refused("nėra"))
    response = run(fake, "send_sales_invoice", invoice())
    assert response["error_code"] == "upstream_validation_failed"
    assert response["external_effect_status"] == "timeout_unknown"
    assert "did not return a document" in response["error"]


def test_test_mode_checks_and_sends_nothing() -> None:
    fake = FakeCentas()
    response = run(fake, "send_sales_invoice", invoice(), test_mode=True)
    assert response["ok"] is True
    assert fake.calls == []
    assert response["definitely_no_external_effect"] is True
    assert response["result"]["total"] == "2541.00"
    assert (
        run(fake, "send_sales_invoice", invoice(lines=[]), test_mode=True)["error_code"]
        == "invalid_payload"
    )


def test_order_uses_the_specification_fields_and_answer() -> None:
    fake = FakeCentas(orders__create=ok(order_id="o1"))
    response = run(
        fake,
        "send_order",
        {
            "number": "ORD-001",
            "date": "2026-11-16",
            "customer_name": "UAB Customer",
            "lines": [dict(LINE, supplier_code="122")],
            "carrier": "DPD",
            "comment": "Skubu",
            "delivery_branch": "Kaunas",
            "delivery_branch_gln": "123",
            "customer_iln": "456",
            "delivery_date": "2026-11-20",
            "customer_phone": "+370600",
        },
    )
    assert response["ok"] is True, response
    form = fake.calls[0].form
    assert form["uzsak_num"] == "ORD-001"
    assert form["uzsak_data"] == "2026-11-16"
    assert form["vezejas"] == "DPD"
    assert form["komentaras"] == "Skubu"
    assert form["uzsak_padalinys"] == "Kaunas"
    assert form["uzsak_padalinys_gln"] == "123"
    assert form["uzsak_iln"] == "456"
    assert form["pristat_data"] == "2026-11-20"
    assert form["tel"] == "+370600"
    [row] = fake.calls[0].rows()
    assert row["pvmtar"] == "21" and "pvm_tar" not in row
    assert row["t_kodas"] == "122"
    assert response["result"]["order_id"] == "o1"


def test_order_accepts_the_gitbook_answer_name() -> None:
    fake = FakeCentas(orders__create=ok(order_hash="h1"))
    response = run(
        fake,
        "send_order",
        {"number": "U", "date": "2026-11-16", "customer_name": "C", "lines": [LINE]},
    )
    assert response["result"]["order_id"] == "h1"


def test_purchase_invoice_sends_the_required_fields() -> None:
    fake = FakeCentas(documents__purchase__import=ok(purchase_id=1))
    response = run(
        fake,
        "send_purchase_invoice",
        {"seller_name": "UAB Supplier", "number": "PUR-001", "date": "2026-11-01", "lines": [LINE]},
    )
    assert response["ok"] is True, response
    assert set(fake.calls[0].form) == {
        "token",
        "kontrah",
        "data",
        "dok_suma",
        "dok_num",
        "pvm_suma",
        "bepvm_suma",
        "rows",
    }
    assert response["result"]["purchase_id"] == "1"


def test_the_key_never_appears_in_a_result_or_an_error() -> None:
    fake = FakeCentas(documents__create=(400, refused(f"Bad token {TOKEN}")))
    response = run(fake, "send_sales_invoice", invoice())
    assert TOKEN not in dumped(response)
    assert "[redacted]" in response["error"]


LIMIT = "999999999999999.99"


def test_amounts_up_to_fifteen_whole_digits_are_sent() -> None:
    fake = FakeCentas(documents__create=ok(document_id="x"))
    line = dict(LINE, quantity=1, price=LIMIT, vat_percent=0)
    response = run(fake, "send_sales_invoice", invoice(lines=[line]))
    assert response["ok"] is True, response
    assert fake.calls[0].form["dok_suma"] == LIMIT


@pytest.mark.parametrize(
    "bad",
    [
        {"lines": [dict(LINE, quantity=2, price=LIMIT, vat_percent=0)]},
        {"lines": [dict(LINE, quantity=1, price=LIMIT, vat_percent=21)]},
        {
            "lines": [
                dict(
                    LINE,
                    quantity="999999999999999.999999",
                    price="999999999999999.999999",
                    vat_percent=100,
                )
            ]
        },
        {"lines": [dict(LINE, quantity=1, price=LIMIT, vat_percent=0)] * 2},
        {
            "lines": [dict(LINE, quantity=1, price=LIMIT, vat_percent=0)],
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
    assert fake.calls == []
