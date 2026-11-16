"""Read steps: what they ask for, what they return, and that none of them takes."""

from __future__ import annotations

import datetime as dt
from typing import Any

import pytest
from support import TOKEN, FakeCentas, Files, dumped, ok, refused, run, xml

from runtime import reads


def test_test_connection_uses_verify_and_warns_before_expiry(monkeypatch: Any) -> None:
    soon = (dt.date.today() + dt.timedelta(days=10)).isoformat() + " 23:59:59"
    fake = FakeCentas(verify=ok(valid_until=soon, message="Token is valid."))
    response = run(fake, "test_connection")
    assert response["ok"] is True, response
    assert fake.calls[0].query == {"token": TOKEN}
    result = response["result"]
    assert result["connected"] is True and result["valid_until"] == soon
    assert result["days_left"] == 10
    assert "expires in 10 days" in result["warnings"][0]
    far = (dt.date.today() + dt.timedelta(days=300)).isoformat()
    assert (
        run(FakeCentas(verify=ok(valid_until=far)), "test_connection")["result"]["warnings"] == []
    )


@pytest.mark.parametrize(
    "answer",
    [
        (401, refused("Wrong API token key provided.")),
        refused("Wrong API token key provided."),
        {"message": "?"},
    ],
)
def test_test_connection_refusals(answer: Any) -> None:
    assert run(FakeCentas(verify=answer), "test_connection")["error_code"] == (
        "authentication_failed"
    )


def test_statistics_counts_without_taking_and_flags_an_expired_key() -> None:
    raw = (
        b"<root><new_invoices>5</new_invoices><new_orders>3</new_orders>"
        b"<new_purchases>2</new_purchases><new_payments_bd>1</new_payments_bd>"
        b"<new_payments_cd>0</new_payments_cd><new_payments_cd2>0</new_payments_cd2>"
        b"<new_payments_bc>1</new_payments_bc>"
        b"<token_valid_until>2025-12-31 23:59:59</token_valid_until></root>"
    )
    response = run(FakeCentas(statistics=raw), "get_statistics")
    result = response["result"]
    assert (result["new_invoices"], result["new_orders"], result["new_payments_bc"]) == (5, 3, 1)
    assert result["token_valid_until"] == "2025-12-31 23:59:59"
    assert any("expired" in w for w in result["warnings"])


def test_full_products_are_paged_with_their_json_fields_decoded() -> None:
    products = [
        {
            "kodas": f"K{n}",
            "kaina": 10.5,
            "stocks": '[{"WarehouseId":1,"Quantity":2}]',
            "parameters": "not json",
        }
        for n in range(5)
    ]
    response = run(
        FakeCentas(products__export__json__full=ok(products=products)),
        "get_products",
        {"limit": 2, "page": 3},
    )
    result = response["result"]
    assert [p["kodas"] for p in result["items"]] == ["K4"]
    assert result["items"][0]["kaina"] == "10.5"
    assert result["items"][0]["stocks"] == [{"WarehouseId": "1", "Quantity": "2"}]
    assert result["items"][0]["parameters"] == "not json"
    assert result["warnings"]
    assert (result["total"], result["has_more"], result["next_page"]) == (5, False, None)


def test_one_product_by_code() -> None:
    fake = FakeCentas(products__export__json__one=ok(products=[{"kodas": "A", "kaina": 1}]))
    response = run(fake, "get_product", {"code": "A"})
    assert fake.calls[0].query == {"token": TOKEN, "kodas": "A"}
    assert response["result"]["found"] is True
    empty = run(
        FakeCentas(products__export__json__one=ok(products=[])), "get_product", {"code": "A"}
    )
    assert empty["result"] == {"found": False, "product": None, "warnings": []}
    other = run(
        FakeCentas(products__export__json__one=ok(products=[{"kodas": "B"}])),
        "get_product",
        {"code": "A"},
    )
    assert other["error_code"] == "invalid_response"


def test_stock_by_barcode() -> None:
    fake = FakeCentas(products__export__json=ok(products=[{"kodas": "A", "likutis": 5}]))
    response = run(fake, "get_product_stock", {"barcode": "4750000000001"})
    assert fake.calls[0].query == {"token": TOKEN, "barkodas": "4750000000001"}
    assert response["result"]["items"][0]["likutis"] == "5"


def test_product_cards_from_xml_without_the_key() -> None:
    card = (
        "<id>1</id><kodas>PRD-001</kodas><kaina>10.00</kaina><Stocks><Stock>"
        "<WarehouseId>1</WarehouseId><Quantity>100</Quantity></Stock></Stocks>"
        "<ProductParameters><Parameter><Name>Color</Name><Value>Red</Value></Parameter>"
        "</ProductParameters>"
    )
    fake = FakeCentas(products__export=xml(card, "<id>2</id><kodas>X</kodas>"))
    response = run(fake, "get_product_cards", {"id": 1})
    assert fake.calls[0].query == {"token": TOKEN, "id": "1"}
    [item] = response["result"]["items"]
    assert item["Stocks"] == [{"WarehouseId": "1", "Quantity": "100"}]
    assert item["ProductParameters"] == [{"Name": "Color", "Value": "Red"}]
    assert TOKEN not in dumped(response)


def test_gallery_link() -> None:
    fake = FakeCentas(products__gallery=ok(link="https://ws.centas.lt/gallery/1"))
    response = run(fake, "get_product_gallery_link", {"product_id": 1})
    assert response["result"]["link"] == "https://ws.centas.lt/gallery/1"
    assert fake.calls[0].query == {"token": TOKEN, "product_id": "1"}


def test_a_sales_document_is_returned_as_sent_without_the_key() -> None:
    raw = (
        '{"success":1,"data":{"dok_num":"INV-001","token":"%s","data":"2024.01.15",'
        '"dok_suma":121.00}}' % TOKEN
    ).encode()
    fake = FakeCentas(documents__get=raw)
    response = run(fake, "get_sales_document", {"number": "INV-001"})
    document = response["result"]["document"]
    assert document == {"dok_num": "INV-001", "data": "2024-01-15", "dok_suma": "121.00"}


def test_sales_documents_need_a_filter_so_the_queue_is_never_taken() -> None:
    fake = FakeCentas()
    response = run(fake, "get_sales_documents", {})
    assert response["error_code"] == "invalid_payload"
    assert fake.calls == []
    doc = (
        "<type>deb</type><dok_num>INV-001</dok_num><data>2024-01-15</data><apmoketa>0"
        "</apmoketa><eilute><kodas>A</kodas></eilute><eilute><kodas>B</kodas></eilute>"
    )
    fake = FakeCentas(documents__export=xml(doc, tag="dokumentas"))
    response = run(fake, "get_sales_documents", {"unpaid": True, "date_from": "2024-01-01"})
    assert fake.calls[0].query == {"token": TOKEN, "unpaid": "1", "from": "2024-01-01"}
    [item] = response["result"]["items"]
    assert [r["kodas"] for r in item["eilute"]] == ["A", "B"]


def test_purchases_need_both_dates_and_dotted_dates_become_iso() -> None:
    fake = FakeCentas()
    assert run(fake, "get_purchases", {"date_from": "2024-01-01"})["error_code"] == (
        "invalid_payload"
    )
    assert fake.calls == []
    raw = xml(
        "<dok_num>PUR-001</dok_num><data>2024.01.15</data><apmok_iki>2024.02.15"
        "</apmok_iki><eilute><kodas>A</kodas></eilute>",
        tag="dokumentas",
    )
    fake = FakeCentas(purchase__export=raw)
    response = run(fake, "get_purchases", {"date_from": "2024-01-01", "date_to": "2024-01-31"})
    [item] = response["result"]["items"]
    assert item["data"] == "2024-01-15" and item["apmok_iki"] == "2024-02-15"
    assert fake.calls[0].query == {"token": TOKEN, "from": "2024-01-01", "to": "2024-01-31"}


def test_contrahents_with_branches_and_search_by_code() -> None:
    raw = xml(
        "<oper>UPD</oper><id>1</id><pavadinimas>UAB Partner</pavadinimas><padaliniai>"
        "<padalinis><pavad>Branch</pavad><miestas>Kaunas</miestas></padalinis>"
        "</padaliniai>"
    )
    response = run(FakeCentas(contrahents__export=raw), "get_contrahents")
    [item] = response["result"]["items"]
    assert item["padaliniai"] == [{"pavad": "Branch", "miestas": "Kaunas"}]
    found = run(
        FakeCentas(contrahents__search=ok(name="UAB Example")),
        "find_company_by_code",
        {"code": "123"},
    )
    assert found["result"] == {"found": True, "name": "UAB Example", "warnings": []}
    missing = run(
        FakeCentas(contrahents__search=refused("Not found")),
        "find_company_by_code",
        {"code": "123"},
    )
    assert missing["result"]["found"] is False
    bad_key = run(
        FakeCentas(contrahents__search=refused("Wrong API token key provided.")),
        "find_company_by_code",
        {"code": "123"},
    )
    assert bad_key["error_code"] == "authentication_failed"


def test_order_invoice_pdf_is_saved_or_only_checked() -> None:
    files = Files()
    fake = FakeCentas(orders__document__pdf=b"%PDF-1.4 invoice")
    response = run(fake, "get_order_invoice_pdf", {"order_number": "ORD-001"}, files=files)
    assert response["result"] == {"exists": True, "file": "art_1", "size_bytes": 16, "warnings": []}
    assert files.written[0]["binding_key"] == "centas_pdf"
    assert files.written[0]["content_type"] == "application/pdf"
    check = FakeCentas(orders__document__pdf=ok())
    response = run(check, "get_order_invoice_pdf", {"order_number": "ORD-001", "check_only": True})
    assert response["result"]["exists"] is True and response["result"]["file"] is None
    assert check.calls[0].query == {"token": TOKEN, "order_no": "ORD-001", "check": "1"}
    none = run(
        FakeCentas(orders__document__pdf=refused("No invoice")),
        "get_order_invoice_pdf",
        {"order_number": "ORD-001"},
    )
    assert none["result"]["exists"] is False
    junk = run(
        FakeCentas(orders__document__pdf=b"<html/>"),
        "get_order_invoice_pdf",
        {"order_number": "ORD-001"},
    )
    assert junk["error_code"] == "invalid_response"


def test_every_read_step_is_a_source_and_never_calls_a_queue_path() -> None:
    from runtime.transport import TAKE_PATHS, _safe_read

    assert set(reads.READS) == set(reads.INPUTS)
    for path in TAKE_PATHS:
        assert not _safe_read(path, {}), path


@pytest.mark.parametrize("bad", [{"limit": 0}, {"limit": 501}, {"page": 0}, {"page": "x"}])
def test_paging_inputs_are_checked(bad: dict[str, Any]) -> None:
    assert run(FakeCentas(), "get_products", bad)["error_code"] == "invalid_payload"
