"""Take steps: they take records from the Centas WS queue, an external effect."""

from __future__ import annotations

from typing import Any

import pytest
from support import TOKEN, FakeCentas, Files, dumped, run, xml

from runtime import budget

PAYMENT = (
    "<PaymentType>BankDeb</PaymentType><Date>2024-01-15</Date><Amount>121.00</Amount>"
    "<DocNr>PAY-001</DocNr><RefNr>REF-001</RefNr>"
)


def test_taken_records_are_saved_whole_then_returned() -> None:
    files = Files()
    fake = FakeCentas(payments__export=xml(PAYMENT, tag="Payment"))
    response = run(fake, "take_new_payments", files=files)
    assert response["ok"] is True, response
    assert response["external_effect_status"] == "succeeded"
    assert response["definitely_no_external_effect"] is False
    result = response["result"]
    assert result["count"] == 1 and result["file"] == "art_1"
    assert result["items"][0]["RefNr"] == "REF-001"
    saved = files.written[0]
    assert saved["binding_key"] == "centas_queue"
    assert saved["content_type"] == "application/xml"
    assert TOKEN.encode() not in saved["data"] and b"[redacted]" in saved["data"]
    assert TOKEN not in dumped(response)


def test_a_payment_type_takes_only_that_type() -> None:
    fake = FakeCentas(**{"payments__export__CashDeb": xml(tag="Payment")})
    response = run(fake, "take_new_payments", {"payment_type": "CashDeb"})
    assert response["ok"] is True
    assert fake.paths() == ["payments/export/CashDeb"]
    assert (
        run(FakeCentas(), "take_new_payments", {"payment_type": "Gold"})["error_code"]
        == "invalid_payload"
    )


@pytest.mark.parametrize(
    ("operation", "route", "tag"),
    [
        ("take_new_sales_documents", "documents__export", "dokumentas"),
        ("take_new_orders", "orders__export", "dokumentas"),
        ("take_new_purchases", "purchase__export", "dokumentas"),
    ],
)
def test_queue_exports_are_called_without_filters(operation: str, route: str, tag: str) -> None:
    fake = FakeCentas(**{route: xml("<dok_num>D-1</dok_num>", tag=tag)})
    response = run(fake, operation)
    assert response["result"]["count"] == 1
    assert fake.calls[0].query == {"token": TOKEN}


def test_test_mode_takes_nothing() -> None:
    fake = FakeCentas()
    response = run(fake, "take_new_orders", test_mode=True)
    assert response["ok"] is True
    assert response["result"]["items"] == [] and response["result"]["file"] is None
    assert response["definitely_no_external_effect"] is True
    assert fake.calls == []


@pytest.mark.parametrize(
    "answer",
    [
        TimeoutError(),
        ConnectionResetError(),
        (500, b""),
        (404, b"<html/>"),
        {"success": 0, "error": "Klaida"},
    ],
)
def test_a_failure_after_the_request_left_is_unknown(answer: Any) -> None:
    response = run(FakeCentas(orders__export=answer), "take_new_orders")
    assert response["external_effect_status"] == "timeout_unknown"
    assert response["definitely_no_external_effect"] is False
    assert "marked the records as exported" in response["error"]


def test_a_rejected_key_takes_nothing() -> None:
    response = run(
        FakeCentas(orders__export=(401, {"success": 0, "error": "Wrong token"})), "take_new_orders"
    )
    assert response["error_code"] == "authentication_failed"
    assert response["definitely_no_external_effect"] is True


def test_an_answer_that_cannot_be_read_stays_in_the_file() -> None:
    files = Files()
    response = run(FakeCentas(orders__export=b"<root><dokumentas>"), "take_new_orders", files=files)
    assert response["ok"] is True
    assert response["result"]["items"] == [] and response["result"]["file"] == "art_1"
    assert "kept whole in the file" in response["result"]["warnings"][0]
    assert files.written[0]["data"] == b"<root><dokumentas>"


def test_records_too_many_for_the_output_stay_in_the_file(monkeypatch: Any) -> None:
    monkeypatch.setattr(budget, "MAX_CANDIDATE_STRINGS", 5)
    raw = xml(*[PAYMENT] * 3, tag="Payment")
    response = run(FakeCentas(payments__export=raw), "take_new_payments")
    result = response["result"]
    assert result["items"] == [] and result["count"] == 3 and result["file"] == "art_1"
    assert any("too many" in w for w in result["warnings"])


def test_a_file_that_cannot_be_saved_is_reported_as_unknown() -> None:
    response = run(
        FakeCentas(orders__export=xml(tag="dokumentas")), "take_new_orders", files=Files(fail=True)
    )
    assert response["error_code"] == "artifact_output_unavailable"
    assert response["external_effect_status"] == "timeout_unknown"
    assert "marked them as exported" in response["error"]
