"""Products, stock and payments read from the exports; Test the connection."""

from __future__ import annotations

from typing import Any

import pytest
from support import TOKEN, FakeCentas, dumped, payments_xml, products_xml, run

DOC_PRODUCT = (
    "<id>1547</id><kodas>1-15</kodas><pavadinimas>Prekė 01</pavadinimas>"
    "<matovnt>vnt.</matovnt><kaina>113.99</kaina><pvmtar>21</pvmtar>"
    "<likutis>907.0000</likutis><grupe1></grupe1><grupe2></grupe2><grupe3></grupe3>"
    "<Nuotrauka></Nuotrauka><barkodas>123456789</barkodas><aprasymas>Prekės aprašymas"
    "</aprasymas><Stocks><Stock><WarehouseId>1</WarehouseId><WarehouseName>Sandelis Nr. 1"
    "</WarehouseName><Quantity>18566.6440</Quantity></Stock><Stock><WarehouseId>2"
    "</WarehouseId><WarehouseName>Sandelis Nr. 2</WarehouseName><Quantity>61.0000</Quantity>"
    "</Stock></Stocks><ProductParameters><Parameter><Name>Kuras</Name><Value>Dujos</Value>"
    "</Parameter></ProductParameters>"
)


def test_the_documented_product_export_is_read_without_the_key() -> None:
    fake = FakeCentas(products__export=products_xml(DOC_PRODUCT))
    response = run(fake, "get_products")
    assert response["ok"] is True, response
    assert TOKEN not in dumped(response)
    [product] = response["result"]["items"]
    assert product == {
        "id": "1547",
        "code": "1-15",
        "name": "Prekė 01",
        "unit": "vnt.",
        "price": "113.99",
        "vat_percent": "21",
        "stock": "907",
        "group1": None,
        "group2": None,
        "group3": None,
        "barcode": "123456789",
        "description": "Prekės aprašymas",
        "photo": None,
        "stocks": [
            {"warehouse_id": "1", "warehouse_name": "Sandelis Nr. 1", "quantity": "18566.644"},
            {"warehouse_id": "2", "warehouse_name": "Sandelis Nr. 2", "quantity": "61"},
        ],
        "parameters": [{"name": "Kuras", "value": "Dujos"}],
    }
    assert response["result"]["total"] == 1
    assert response["result"]["has_more"] is False


def test_the_key_is_dropped_whatever_its_case_and_scrubbed_elsewhere() -> None:
    raw = (
        f"<root><item><TOKEN>{TOKEN}</TOKEN><kodas>A</kodas>"
        f"<aprasymas>see {TOKEN}</aprasymas></item></root>"
    ).encode()
    response = run(FakeCentas(products__export=raw), "get_products")
    assert TOKEN not in dumped(response)
    assert response["result"]["items"][0]["description"] == "see [redacted]"


def test_products_are_paged_here() -> None:
    items = [f"<id>{n}</id><kodas>K{n}</kodas>" for n in range(1, 8)]
    fake = FakeCentas(products__export=products_xml(*items))
    response = run(fake, "get_products", {"limit": 3, "page": 2})
    result = response["result"]
    assert [p["code"] for p in result["items"]] == ["K4", "K5", "K6"]
    assert (result["count"], result["total"], result["has_more"], result["next_page"]) == (
        3,
        7,
        True,
        3,
    )


def test_one_product_by_id_is_asked_for_and_filtered() -> None:
    fake = FakeCentas(
        products__export=products_xml("<id>1</id><kodas>A</kodas>", "<id>2</id><kodas>B</kodas>")
    )
    response = run(fake, "get_products", {"id": "2"})
    assert fake.calls[0].query == {"token": TOKEN, "id": "2"}
    assert [p["code"] for p in response["result"]["items"]] == ["B"]


def test_a_value_that_is_not_a_number_is_returned_as_sent_with_a_warning() -> None:
    fake = FakeCentas(products__export=products_xml("<kodas>A</kodas><kaina>apie 5</kaina>"))
    response = run(fake, "get_products")
    assert response["result"]["items"][0]["price"] == "apie 5"
    assert response["result"]["warnings"]


def test_find_product_by_code_or_barcode() -> None:
    export = products_xml(
        "<kodas>A</kodas><barkodas>111</barkodas>",
        "<kodas>B</kodas><barkodas>222</barkodas>",
        "<kodas>C</kodas><barkodas>222</barkodas>",
    )
    response = run(FakeCentas(products__export=export), "find_product", {"code": "B"})
    assert response["result"]["found"] is True
    assert response["result"]["product"]["code"] == "B"
    response = run(FakeCentas(products__export=export), "find_product", {"code": "Z"})
    assert response["result"] == {"found": False, "product": None, "warnings": []}
    response = run(FakeCentas(products__export=export), "find_product", {"barcode": "222"})
    assert response["error_code"] == "conflict"
    for both in ({}, {"code": "A", "barcode": "111"}):
        assert run(FakeCentas(), "find_product", both)["error_code"] == "invalid_payload"


def test_stock_levels_one_row_per_product_and_warehouse() -> None:
    export = products_xml(DOC_PRODUCT, "<kodas>X</kodas><likutis>5</likutis>")
    response = run(FakeCentas(products__export=export), "get_stock_levels")
    rows = response["result"]["items"]
    assert [(r["code"], r["warehouse_id"], r["quantity"]) for r in rows] == [
        ("1-15", "1", "18566.644"),
        ("1-15", "2", "61"),
        ("X", None, "5"),
    ]
    response = run(FakeCentas(products__export=export), "get_stock_levels", {"warehouse_id": "2"})
    assert [(r["code"], r["quantity"]) for r in response["result"]["items"]] == [("1-15", "61")]
    response = run(FakeCentas(products__export=export), "get_stock_levels", {"code": "X"})
    assert len(response["result"]["items"]) == 1


DOC_PAYMENT = (
    "<PaymentType>BankDeb</PaymentType><Date>2020.01.01</Date><Amount>123.23</Amount>"
    "<DocNr>NR001_is_banko</DocNr><RefNr>ABC001</RefNr><Details>mokejimo paskirtis</Details>"
    "<RecName>UAB Moketojas</RecName><RecId>303030303</RecId>"
    "<ToAccountNumber>LT1234567890</ToAccountNumber>"
)


def test_the_documented_payment_export_is_read() -> None:
    response = run(FakeCentas(payments__export=payments_xml(DOC_PAYMENT)), "get_payments")
    assert response["ok"] is True
    assert TOKEN not in dumped(response)
    assert response["result"]["items"] == [
        {
            "type": "BankDeb",
            "document_number": "NR001_is_banko",
            "reference": "ABC001",
            "details": "mokejimo paskirtis",
            "payer_name": "UAB Moketojas",
            "payer_code": "303030303",
            "account": "LT1234567890",
            "date": "2020-01-01",
            "amount": "123.23",
        }
    ]


def test_payments_are_filtered_by_date_and_reference() -> None:
    export = payments_xml(
        "<Date>2026.01.01</Date><RefNr>A</RefNr>",
        "<Date>2026.02.01</Date><RefNr>B</RefNr>",
        "<Date>vakar</Date><RefNr>C</RefNr>",
    )

    def refs(inputs: dict[str, Any]) -> list[str]:
        response = run(FakeCentas(payments__export=export), "get_payments", inputs)
        return [p["reference"] for p in response["result"]["items"]]

    assert refs({}) == ["A", "B", "C"]
    assert refs({"date_from": "2026-01-15"}) == ["B"]
    assert refs({"date_to": "2026-01-15"}) == ["A"]
    assert refs({"reference": "C"}) == ["C"]
    response = run(FakeCentas(payments__export=export), "get_payments", {"date_from": "2026-01-01"})
    assert any("without a readable date" in w for w in response["result"]["warnings"])
    bad = run(FakeCentas(), "get_payments", {"date_from": "2026-02-01", "date_to": "2026-01-01"})
    assert bad["error_code"] == "invalid_payload"


@pytest.mark.parametrize("bad", [{"limit": 0}, {"limit": 501}, {"page": 0}, {"page": "x"}])
def test_paging_inputs_are_checked(bad: dict[str, Any]) -> None:
    assert run(FakeCentas(), "get_products", bad)["error_code"] == "invalid_payload"


def test_test_connection_reads_only_the_start_of_the_export() -> None:
    big = products_xml(*["<kodas>K</kodas><aprasymas>" + "x" * 1000 + "</aprasymas>"] * 100)
    fake = FakeCentas(products__export=big)
    response = run(fake, "test_connection")
    assert response["ok"] is True, response
    assert response["result"]["connected"] is True
    assert set(response["result"]) == {"connected", "duration_ms", "warnings"}


@pytest.mark.parametrize(
    ("answer", "code"),
    [
        ((401, {"success": 0, "error": "Invalid or expired token."}), "authentication_failed"),
        ({"success": 0, "error": "Invalid or expired token."}, "authentication_failed"),
        (b"Hello", "invalid_response"),
    ],
)
def test_test_connection_failures(answer: Any, code: str) -> None:
    response = run(FakeCentas(products__export=answer), "test_connection")
    assert response["error_code"] == code
