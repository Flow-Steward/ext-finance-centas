"""How every kind of answer, failure and timeout is reported; where the key travels."""

from __future__ import annotations

import io
import socket
from email.message import Message
from typing import Any
from urllib.error import HTTPError

import pytest
from flowsteward_extension_sdk import PinnedPeerError
from support import TOKEN, FakeCentas, dumped, ok, payload, products_xml, run

from runtime import transport as transport_module
from runtime.connection import connection_from_payload
from runtime.operations import handle_runtime
from runtime.transport import CentasTransport, parse_xml, read_bounded

INVOICE = {
    "number": "S-1",
    "date": "2026-11-16",
    "buyer_name": "UAB",
    "lines": [{"code": "A", "quantity": 1, "price": 10, "vat_percent": 21}],
}
HTML_405 = (
    405,
    b"<!DOCTYPE html><html><head><title>An Error Occurred: Method Not Allowed"
    b"</title></head><body>Method Not Allowed</body></html>",
)


def write(answer: Any) -> dict[str, Any]:
    return run(FakeCentas(documents__create=answer), "send_sales_invoice", INVOICE)


def test_a_rejected_key_on_a_write_certainly_changed_nothing() -> None:
    response = write((401, {"success": 0, "error": "Invalid or expired token."}))
    assert response["error_code"] == "authentication_failed"
    assert response["definitely_no_external_effect"] is True
    assert response["external_effect_status"] == "failed"
    assert "Invalid or expired token." in response["error"]


@pytest.mark.parametrize(
    ("answer", "code"),
    [
        (HTML_405, "not_found"),
        ((404, b"<html>404 - Puslapis nerastas</html>"), "not_found"),
        ((500, b"oops"), "upstream_failure"),
        ((502, b""), "upstream_failure"),
        ((504, b""), "timeout"),
        ((400, {"success": 0, "error": "bad"}), "upstream_validation_failed"),
        ((403, b""), "authentication_failed"),
        ((302, b""), "redirect_rejected"),
        (b"<html>not json</html>", "invalid_response"),
        (b"", "invalid_response"),
        ({"success": "maybe"}, "invalid_response"),
        ({"document_id": "x"}, "invalid_response"),
        ([1, 2], "invalid_response"),
        ({"success": 0, "error": "Klaida"}, "upstream_validation_failed"),
        (TimeoutError(), "timeout_unknown"),
        (socket.timeout(), "timeout_unknown"),
        (ConnectionResetError(), "timeout_unknown"),
    ],
)
def test_any_other_failure_after_a_write_was_sent_leaves_it_unknown(answer: Any, code: str) -> None:
    response = write(answer)
    assert response["ok"] is False
    assert response["error_code"] == code, response
    assert response["external_effect_status"] == "timeout_unknown"
    assert response["definitely_no_external_effect"] is False


@pytest.mark.parametrize("success", [1, "1", True])
def test_success_is_read_in_its_plain_forms(success: Any) -> None:
    assert write({"success": success, "document_id": "x"})["ok"] is True


def test_a_name_that_cannot_be_resolved_is_reported_before_sending() -> None:
    response = write(PinnedPeerError("ws.centas.lt cannot be resolved"))
    assert response["error_code"] == "connection_failed"
    assert response["definitely_no_external_effect"] is True


def test_a_blocked_address_is_reported_before_sending() -> None:
    response = write(PinnedPeerError("blocked"))
    assert response["error_code"] == "blocked_address"
    assert response["definitely_no_external_effect"] is True


@pytest.mark.parametrize(
    ("answer", "code"),
    [
        ((401, {"success": 0, "error": "No token provided."}), "authentication_failed"),
        ((404, b"<html/>"), "not_found"),
        ((500, b""), "upstream_failure"),
        (TimeoutError(), "timeout"),
        (ConnectionResetError(), "connection_failed"),
        ({"success": 0, "error": "Invalid or expired token."}, "authentication_failed"),
        ({"success": 0, "error": "Something else"}, "upstream_validation_failed"),
        (b"not xml", "invalid_response"),
        (b"<root><item></root>", "invalid_response"),
        (b"<other/>", "invalid_response"),
    ],
)
def test_read_failures_change_nothing(answer: Any, code: str) -> None:
    response = run(FakeCentas(products__export=answer), "get_products")
    assert response["error_code"] == code, response
    assert response["definitely_no_external_effect"] is True
    assert response["external_effect_status"] == "failed"


def test_the_key_goes_in_the_query_of_an_export_only() -> None:
    fake = FakeCentas(products__export=products_xml("<kodas>A</kodas>"))
    assert run(fake, "get_products")["ok"] is True
    [call] = fake.calls
    assert call.url.startswith("https://ws.centas.lt/v1/products/export?")
    assert call.verb == "GET"
    assert call.query == {"token": TOKEN}
    assert call.raw_body == b""


def test_the_key_is_not_in_any_error_even_when_the_server_echoes_it() -> None:
    encoded = TOKEN.replace("_", "%5F")
    for answer in (
        (500, f"<html>token={TOKEN} {encoded}</html>".encode()),
        (401, {"success": 0, "error": f"Invalid token {TOKEN}"}),
        {"success": 0, "error": f"Klaida: {TOKEN}"},
    ):
        for operation, route in (
            ("send_sales_invoice", "documents__create"),
            ("get_products", "products__export"),
        ):
            fake = FakeCentas(**{route: answer})
            response = run(fake, operation, INVOICE if operation.startswith("send") else {})
            assert TOKEN not in dumped(response), (operation, answer)


def test_http_errors_never_pass_on_the_address() -> None:
    def boom(call: Any) -> Any:
        raise HTTPError(call.url, 500, f"error at {call.url}", Message(), io.BytesIO(b""))

    response = run(FakeCentas(products__export=boom), "get_products")
    assert response["error_code"] == "upstream_failure"
    assert TOKEN not in dumped(response)
    assert "ws.centas.lt/v1/products/export?" not in dumped(response)


def test_an_internal_error_reports_only_its_place() -> None:
    def boom(call: Any) -> Any:
        raise RuntimeError(f"secret {TOKEN}")

    response = run(FakeCentas(products__export=boom), "get_products")
    assert response["error_code"] == "internal_error"
    assert TOKEN not in dumped(response)
    assert "RuntimeError at" in response["error"]


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

    def opener(request: Any, **kw: Any) -> Any:
        return Slow()

    connection = connection_from_payload(payload("send_sales_invoice"), connection_ref="c1")
    transport = CentasTransport(connection, opener=opener, clock=lambda: now[0])
    transport.deadline = 570.0
    response = handle_runtime(
        payload("send_sales_invoice", INVOICE), transport_factory=lambda c: transport
    )
    assert response["error_code"] == "timeout_unknown"
    assert response["definitely_no_external_effect"] is False


def test_no_request_starts_without_time_left() -> None:
    times = iter([0.0])
    fake = FakeCentas(documents__create=ok(document_id="x"))

    def clock() -> float:
        # The deadline is set at 0 s; every later reading is past it.
        return next(times, 1000.0)

    response = run(fake, "send_sales_invoice", INVOICE, clock=clock)
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

    assert len(read_bounded(Big(), 100, truncate=True)) == 100
    with pytest.raises(Exception) as caught:
        read_bounded(Big(), 100)
    assert getattr(caught.value, "code", "") == "response_too_large"
    with pytest.raises(Exception) as caught:
        read_bounded(Big(), 100, mutating=True)
    assert getattr(caught.value, "external_effect_status", "") == "timeout_unknown"


def test_an_export_larger_than_the_limit_is_refused(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(transport_module, "MAX_EXPORT_BYTES", 50)
    response = run(FakeCentas(products__export=products_xml("<kodas>A</kodas>")), "get_products")
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


def test_only_documented_paths_can_be_called() -> None:
    connection = connection_from_payload(payload("get_products"), connection_ref="c1")
    transport = CentasTransport(connection, opener=FakeCentas())
    with pytest.raises(Exception) as caught:
        transport.write("documents/delete", [])
    assert getattr(caught.value, "code", "") == "invalid_payload"
    with pytest.raises(Exception):
        transport.export("documents/export")


@pytest.mark.parametrize(
    "token",
    ["", "short", "has space inside", "x" * 257, "ąčęėįšųū12345"],
)
def test_unusable_keys_are_refused_before_any_request(token: str) -> None:
    fake = FakeCentas()
    response = run(fake, "get_products", token=token)
    assert response["error_code"] == "invalid_connection"
    assert fake.calls == []


def test_a_connection_of_another_type_is_refused() -> None:
    request = payload("get_products")
    request["action"]["target"]["connection"]["connection_type_id"] = "finvalda"
    response = handle_runtime(
        request, transport_factory=lambda c: CentasTransport(c, opener=FakeCentas())
    )
    assert response["error_code"] == "invalid_connection"


def test_unknown_operations_are_refused() -> None:
    response = run(FakeCentas(), "delete_document")
    assert response["error_code"] == "unsupported_operation"
    assert response["definitely_no_external_effect"] is True
