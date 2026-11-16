"""A fake Centas WS and invocation helpers for the tests (no network)."""

from __future__ import annotations

import io
import json
from collections.abc import Callable
from email.message import Message
from pathlib import Path
from typing import Any
from urllib.error import HTTPError
from urllib.parse import parse_qsl, urlsplit

from runtime.operations import handle_runtime
from runtime.transport import CentasTransport

BUNDLE = Path(__file__).resolve().parents[1]
TOKEN = "tk_fixture0123456789abcdefTOKEN"  # pragma: allowlist secret
PREFIX = "/v1/"


class Call:
    def __init__(self, request: Any) -> None:
        parts = urlsplit(request.full_url)
        self.url = request.full_url
        self.scheme = parts.scheme
        self.host = parts.hostname
        self.path = parts.path[len(PREFIX) :] if parts.path.startswith(PREFIX) else parts.path
        self.verb = request.get_method()
        self.query = dict(parse_qsl(parts.query))
        self.headers = {k.lower(): v for k, v in request.header_items()}
        self.raw_body = request.data or b""
        self.form = dict(parse_qsl(self.raw_body.decode("ascii"))) if self.raw_body else {}

    def rows(self) -> Any:
        return json.loads(self.form["rows"])


class Response:
    def __init__(self, status: int, body: bytes) -> None:
        self.status = status
        self._body = body
        self.headers = Message()

    def read(self, size: int = -1) -> bytes:
        chunk, self._body = (
            (self._body, b"") if size < 0 else (self._body[:size], self._body[size:])
        )
        return chunk

    def __enter__(self) -> Response:
        return self

    def __exit__(self, *exc: Any) -> None:
        return None


def ok(**fields: Any) -> dict[str, Any]:
    return {"success": 1, **fields}


def refused(text: str = "Klaida") -> dict[str, Any]:
    return {"success": 0, "error": text}


class FakeCentas:
    """Answers by path; a list of answers is used in order.

    An answer is a dict (JSON, HTTP 200), bytes (HTTP 200), a (status, body) tuple, an
    exception to raise or a callable taking the Call.
    """

    def __init__(self, **routes: Any) -> None:
        self.routes: dict[str, Any] = {
            k.replace("__", "/"): (list(v) if isinstance(v, list) else v) for k, v in routes.items()
        }
        self.calls: list[Call] = []

    def __call__(self, request: Any, *, timeout_seconds: float, purpose: str) -> Response:
        call = Call(request)
        self.calls.append(call)
        route = self.routes.get(call.path)
        if route is None:
            raise AssertionError(f"unexpected call to {call.path}")
        answer = route.pop(0) if isinstance(route, list) else route
        if callable(answer) and not isinstance(answer, BaseException):
            answer = answer(call)
        if isinstance(answer, BaseException):
            raise answer
        status, body = answer if isinstance(answer, tuple) else (200, answer)
        raw = body if isinstance(body, bytes) else json.dumps(body).encode()
        if status >= 300:
            raise HTTPError(request.full_url, status, "error", Message(), io.BytesIO(raw))
        return Response(status, raw)

    def paths(self) -> list[str]:
        return [c.path for c in self.calls]


def payload(
    operation_id: str,
    inputs: dict[str, Any] | None = None,
    *,
    test_mode: bool = False,
    token: str = TOKEN,
) -> dict[str, Any]:
    return {
        "contract_version": "extension_host_v2",
        "mode": "action",
        "runtime_context": {
            "group_id": None,
            "for_each_id": None,
            "step_id": "s",
            "step_execution_id": "5c1d2e3f-4a5b-4c6d-8e7f-000000000001",
            "test_mode": test_mode,
        },
        "action": {
            "action_id": operation_id,
            "input": {"connection_ref": "c1", **(inputs or {})},
            "target": {
                "connection": {
                    "connection_id": "c1",
                    "connection_type_id": "centas",
                    "config": {"label": "UAB X"},
                    "secrets": {"token": token},
                }
            },
        },
    }


def run(
    fake: FakeCentas,
    operation_id: str,
    inputs: dict[str, Any] | None = None,
    *,
    clock: Callable[[], float] | None = None,
    **kw: Any,
) -> dict[str, Any]:
    def factory(connection: Any) -> CentasTransport:
        if clock is None:
            return CentasTransport(connection, opener=fake)
        return CentasTransport(connection, opener=fake, clock=clock)

    return handle_runtime(payload(operation_id, inputs, **kw), transport_factory=factory)


def products_xml(*items: str, token: str = TOKEN) -> bytes:
    body = "".join(f"<item><token>{token}</token><oper>UPD</oper>{i}</item>" for i in items)
    return f'<?xml version="1.0" encoding="UTF-8"?>\n<root>{body}</root>'.encode()


def payments_xml(*payments: str, token: str = TOKEN) -> bytes:
    body = "".join(f"<Payment><token>{token}</token>{p}</Payment>" for p in payments)
    return f'<?xml version="1.0" encoding="UTF-8"?>\n<root>{body}</root>'.encode()


def dumped(response: Any) -> str:
    """A response as one text, to look for the key anywhere in it."""
    return json.dumps(response, default=str, ensure_ascii=False)
