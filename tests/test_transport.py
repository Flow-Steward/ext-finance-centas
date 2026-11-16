"""How every kind of answer, failure and timeout is reported; where the key travels."""

from __future__ import annotations

import io
import socket
from email.message import Message
from typing import Any
from urllib.error import HTTPError

import pytest
from flowsteward_extension_sdk import PinnedPeerError
from support import TOKEN, FakeCentas, dumped, ok, payload, run, xml

from runtime import transport as transport_module
from runtime.connection import connection_from_payload
from runtime.operations import handle_runtime
from runtime.transport import CentasTransport, multipart, parse_xml, read_bounded

PAYMENT = {
    "type": "BankDeb",
    "date": "2026-01-15",
    "amount": "121.00",
    "document_number": "PAY-001",
    "details": "Payment",
    "payer_name": "UAB",
}
HTML_405 = (
    405,
    b"<!DOCTYPE html><html><head><title>An Error Occurred: Method Not Allowed"
    b"</title></head><body>Method Not Allowed</body></html>",
)


def batch(answer: Any) -> dict[str, Any]:
    """payments/import: an XML batch, whose only documented refusal is 401."""
    return run(FakeCentas(payments__import=answer), "send_payments", {"payments": [PAYMENT]})


def test_a_rejected_key_on_a_write_certainly_changed_nothing() -> None:
    response = batch((401, {"success": 0, "error": "Wrong API token key provided."}))
    assert response["error_code"] == "authentication_failed"
    assert response["definitely_no_external_effect"] is True
    assert response["external_effect_status"] == "failed"


@pytest.mark.parametrize(
    ("answer", "code"),
    [
        ((400, {"success": 0, "error": "bad"}), "upstream_validation_failed"),
        (HTML_405, "not_found"),
        ((404, b"<html>404</html>"), "not_found"),
        ((500, b"oops"), "upstream_failure"),
        ((504, b""), "timeout"),
        ((403, b""), "authentication_failed"),
        ((302, b""), "redirect_rejected"),
        (b"<html>not json</html>", "invalid_response"),
        (b"", "invalid_response"),
        ({"success": "maybe"}, "invalid_response"),
        ([1, 2], "invalid_response"),
        ({"success": 0, "error": "Klaida"}, "upstream_validation_failed"),
        (TimeoutError(), "timeout_unknown"),
        (socket.timeout(), "timeout_unknown"),
        (ConnectionResetError(), "timeout_unknown"),
    ],
)
def test_any_other_failure_of_a_batch_leaves_it_unknown(answer: Any, code: str) -> None:
    response = batch(answer)
    assert response["error_code"] == code, response
    assert response["external_effect_status"] == "timeout_unknown"
    assert response["definitely_no_external_effect"] is False


@pytest.mark.parametrize("path", ["orders__create", "documents__purchase__import"])
def test_a_documented_400_changes_nothing(path: str) -> None:
    fake = FakeCentas(**{path: (400, {"success": 0, "error": "The uzsakovas field is required."})})
    operation = "send_order" if path == "orders__create" else "send_purchase_invoice"
    inputs = {
        "number": "N",
        "date": "2026-11-16",
        "customer_name": "C",
        "seller_name": "S",
        "lines": [{"code": "A", "quantity": 1, "price": 1, "vat_percent": 0}],
    }
    keep = {
        "send_order": {"number", "date", "customer_name", "lines"},
        "send_purchase_invoice": {"number", "date", "seller_name", "lines"},
    }[operation]
    response = run(fake, operation, {k: v for k, v in inputs.items() if k in keep})
    assert response["error_code"] == "upstream_validation_failed"
    assert response["definitely_no_external_effect"] is True


@pytest.mark.parametrize("success", [1, "1", True])
def test_success_is_read_in_its_plain_forms(success: Any) -> None:
    assert batch({"success": success, "payments_found_xml": 1, "payments_created": 1})["ok"]


def test_writes_are_multipart_with_the_key_in_the_body() -> None:
    fake = FakeCentas(payments__import=ok(payments_found_xml=1, payments_created=1))
    run(fake, "send_payments", {"payments": [PAYMENT]})
    [call] = fake.calls
    assert call.url == "https://ws.centas.lt/v1/payments/import"
    assert call.query == {}
    assert call.form["token"] == TOKEN
    assert set(call.form) == {"token", "data"}


def test_reads_carry_the_key_in_the_query_only() -> None:
    fake = FakeCentas(products__export__json__full=ok(products=[]))
    assert run(fake, "get_products")["ok"] is True
    [call] = fake.calls
    assert call.url.startswith("https://ws.centas.lt/v1/products/export/json/full?")
    assert call.verb == "GET"
    assert call.query == {"token": TOKEN}
    assert call.raw_body == b""


def test_check_service_sends_no_key() -> None:
    fake = FakeCentas(test={"status": "ok"})
    response = run(fake, "check_service")
    assert response["result"]["running"] is True
    assert fake.calls[0].url == "https://ws.centas.lt/v1/test"


@pytest.mark.parametrize(
    ("answer", "code"),
    [
        ((401, {"success": 0, "error": "Wrong API token key provided."}), "authentication_failed"),
        ((404, b"<html/>"), "not_found"),
        ((500, b""), "upstream_failure"),
        (TimeoutError(), "timeout"),
        (ConnectionResetError(), "connection_failed"),
        ({"success": 0, "error": "Wrong API token key provided."}, "authentication_failed"),
        ({"success": 0, "error": "Something else"}, "upstream_validation_failed"),
        (b"not json", "invalid_response"),
    ],
)
def test_read_failures_change_nothing(answer: Any, code: str) -> None:
    response = run(FakeCentas(products__export__json__full=answer), "get_products")
    assert response["error_code"] == code, response
    assert response["definitely_no_external_effect"] is True
    assert response["external_effect_status"] == "failed"


def test_the_key_is_not_in_any_error_even_when_the_server_echoes_it() -> None:
    encoded = TOKEN.replace("_", "%5F")
    for answer in (
        (500, f"<html>token={TOKEN} {encoded}</html>".encode()),
        (401, {"success": 0, "error": f"Invalid token {TOKEN}"}),
        {"success": 0, "error": f"Klaida: {TOKEN}"},
    ):
        for operation, route, inputs in (
            ("send_payments", "payments__import", {"payments": [PAYMENT]}),
            ("get_products", "products__export__json__full", {}),
        ):
            response = run(FakeCentas(**{route: answer}), operation, inputs)
            assert TOKEN not in dumped(response), (operation, answer)


def test_http_errors_never_pass_on_the_address() -> None:
    def boom(call: Any) -> Any:
        raise HTTPError(call.url, 500, f"error at {call.url}", Message(), io.BytesIO(b""))

    response = run(FakeCentas(products__export__json__full=boom), "get_products")
    assert response["error_code"] == "upstream_failure"
    assert TOKEN not in dumped(response)
    assert "products/export/json/full?" not in dumped(response)


def test_an_internal_error_reports_only_its_place() -> None:
    def boom(call: Any) -> Any:
        raise RuntimeError(f"secret {TOKEN}")

    response = run(FakeCentas(products__export__json__full=boom), "get_products")
    assert response["error_code"] == "internal_error"
    assert TOKEN not in dumped(response)
    assert "RuntimeError at" in response["error"]


def test_name_resolution_and_blocked_addresses_are_before_sending() -> None:
    assert (
        batch(PinnedPeerError("ws.centas.lt cannot be resolved"))["definitely_no_external_effect"]
        is True
    )
    blocked = batch(PinnedPeerError("blocked"))
    assert blocked["error_code"] == "blocked_address"
    assert blocked["definitely_no_external_effect"] is True


def test_an_answer_trickling_past_the_deadline_is_a_timeout() -> None:
    now = [0.0]

    class Slow:
        status = 200

        def read(self, size: int = -1) -> bytes:
            now[0] += 400.0
            return b"x"

        def __enter__(self) -> Any:
            return self

        def __exit__(self, *exc: Any) -> None:
            return None

    connection = connection_from_payload(payload("send_payments"), connection_ref="c1")
    transport = CentasTransport(connection, opener=lambda r, **kw: Slow(), clock=lambda: now[0])
    response = handle_runtime(
        payload("send_payments", {"payments": [PAYMENT]}), transport_factory=lambda c: transport
    )
    assert response["error_code"] == "timeout_unknown"
    assert response["definitely_no_external_effect"] is False


def test_no_request_starts_without_time_left() -> None:
    times = iter([0.0])
    fake = FakeCentas(payments__import=ok())
    response = run(
        fake, "send_payments", {"payments": [PAYMENT]}, clock=lambda: next(times, 1000.0)
    )
    assert response["error_code"] == "timeout"
    assert response["definitely_no_external_effect"] is True
    assert fake.calls == []


def test_answers_are_read_only_up_to_their_limit() -> None:
    class Big:
        def __init__(self) -> None:
            self.left = 10_000

        def read(self, size: int = -1) -> bytes:
            size = min(size, self.left)
            self.left -= size
            return b"x" * size

    with pytest.raises(Exception) as caught:
        read_bounded(Big(), 100)
    assert getattr(caught.value, "code", "") == "response_too_large"
    with pytest.raises(Exception) as caught:
        read_bounded(Big(), 100, mutating=True)
    assert getattr(caught.value, "external_effect_status", "") == "timeout_unknown"


def test_a_read_larger_than_the_limit_is_refused(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(transport_module, "MAX_READ_BYTES", 20)
    response = run(FakeCentas(products__export=xml("<kodas>A</kodas>")), "get_product_cards")
    assert response["error_code"] == "response_too_large"


@pytest.mark.parametrize(
    "raw",
    [
        b'<?xml version="1.0"?><!DOCTYPE r [<!ENTITY a "aaaa">]><root>&a;</root>',
        b'<?xml version="1.0"?><!DOCTYPE r SYSTEM "file:///etc/passwd"><root/>',
        b"<root><!ENTITY x 'y'></root>",
    ],
)
def test_dtds_and_entities_are_refused(raw: bytes) -> None:
    with pytest.raises(ValueError):
        parse_xml(raw)


def test_only_documented_operations_can_be_called_and_reads_never_take() -> None:
    connection = connection_from_payload(payload("get_products"), connection_ref="c1")
    transport = CentasTransport(connection, opener=FakeCentas())
    for call in (
        lambda: transport.write("documents/void", []),
        lambda: transport.read("payments/export"),
        lambda: transport.read("documents/export"),
        lambda: transport.read("purchase/export", [("from", "2026-01-01")]),
        lambda: transport.take("documents/export", [("unpaid", "1")]),
        lambda: transport.take("products/export"),
    ):
        with pytest.raises(Exception) as caught:
            call()
        assert getattr(caught.value, "code", "") == "invalid_payload"


def test_multipart_refuses_odd_field_names() -> None:
    body, kind = multipart([("data", "<root/>"), ("token", "t")])
    assert kind.startswith("multipart/form-data; boundary=")
    assert b'name="data"' in body
    with pytest.raises(Exception):
        multipart([('da"ta', "x")])


@pytest.mark.parametrize("token", ["", "short", "has space inside", "x" * 257, "ąčęėįšųū12345"])
def test_unusable_keys_are_refused_before_any_request(token: str) -> None:
    fake = FakeCentas()
    response = run(fake, "get_products", token=token)
    assert response["error_code"] == "invalid_connection"
    assert fake.calls == []


def test_unknown_operations_are_refused() -> None:
    response = run(FakeCentas(), "delete_everything")
    assert response["error_code"] == "unsupported_operation"
    assert response["definitely_no_external_effect"] is True
