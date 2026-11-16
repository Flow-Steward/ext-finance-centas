"""The only way this extension reaches Centas WS.

Seven documented endpoints under ``https://ws.centas.lt/v1`` (``connection.BASE_URL``),
nothing else. Requests go out through the public Flow Steward extension SDK, which
pins DNS, verifies the connected peer, refuses redirects and enforces the timeout.

The key travels as ``token``:

* in the form body of every write (POST) — never in its address;
* in the query of the two exports (GET), the only place Centas WS reads it there.
  The address is therefore never put into a message, a log line or a result, and no
  exception text of the HTTP library is passed on.

Centas WS answers a write with a JSON object: ``success`` 1 and the new record's id,
or ``success`` 0 and ``error``. It documents no idempotency, no duplicate check and
no way to read a sent document back, so a write is sent exactly once and never
retried here, and only ``success`` 1 counts as saved. A missing key or a key
Centas WS does not accept is refused with HTTP 401 before anything is processed
(checked against ws.centas.lt with an invalid key): that is the one answer to a
sent write that certainly changed nothing. Any other failure after a write was
sent leaves its outcome unknown (``timeout_unknown``).
"""

from __future__ import annotations

import http.client
import json
import re
import threading
import time

# DTDs and entity declarations are refused before anything is parsed (parse_xml).
import xml.etree.ElementTree as ElementTree  # nosec B405
from collections.abc import Callable, Iterable, Mapping
from decimal import Decimal
from typing import Any
from urllib.error import HTTPError
from urllib.parse import urlencode
from urllib.request import Request

from flowsteward_extension_sdk import PinnedPeerError, open_pinned_url

from . import errors
from .connection import BASE_URL, Connection
from .errors import ExtensionError

DEFAULT_TIMEOUT_SECONDS = 120.0
#: The most this extension sends in one request (Centas WS documents no limit).
MAX_REQUEST_BODY_BYTES = 5 * 1024 * 1024
#: The most read from one export answer: the exports have no paging.
MAX_EXPORT_BYTES = 20 * 1024 * 1024
#: The most read from a write's answer (a small JSON object).
MAX_WRITE_ANSWER_BYTES = 256 * 1024
MAX_ERROR_BODY_BYTES = 64 * 1024
#: What Test connection reads of the product export: enough to see the answer's kind.
PROBE_BYTES = 4096
CHUNK_BYTES = 64 * 1024
#: Shortest window still worth starting a request in.
MIN_CALL_WINDOW_SECONDS = 15.0
_USER_AGENT = "FlowSteward-Centas/0.1"

#: Every endpoint this extension calls (the documented API, nothing more).
WRITE_PATHS: frozenset[str] = frozenset(
    {
        "documents/create",
        "orders/create",
        "documents/purchase/import",
        "payments/import",
        "products/import",
    }
)
READ_PATHS: frozenset[str] = frozenset({"products/export", "payments/export"})


class DeadlineReached(Exception):
    """The invocation's time budget leaves no room for another request."""


class CentasTransport:
    """Sends Centas WS requests for one connection."""

    def __init__(
        self,
        connection: Connection,
        *,
        opener: Callable[..., Any] = open_pinned_url,
        clock: Callable[[], float] = time.monotonic,
        timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS,
    ) -> None:
        self._connection = connection
        self._opener = opener
        self.clock = clock
        self._timeout_seconds = timeout_seconds
        self._call_timeout = timeout_seconds
        #: True once a request that can change data may have left this process.
        self.mutated = False
        #: True once Centas WS confirmed a change in this invocation.
        self.committed = False
        #: Monotonic time after which no request may start (set by the operation).
        self.deadline: float | None = None

    @property
    def connection(self) -> Connection:
        return self._connection

    def remaining(self) -> float:
        return float("inf") if self.deadline is None else self.deadline - self.clock()

    # -- public calls --------------------------------------------------------

    def write(self, path: str, form: Iterable[tuple[str, str]]) -> dict[str, Any]:
        """POST one write; its JSON answer when Centas WS confirmed it (``success`` 1)."""
        if path not in WRITE_PATHS:
            raise errors.invalid("Not a Centas WS write")
        fields = [("token", self._connection.token), *form]
        body = urlencode(fields).encode("ascii")
        if len(body) > MAX_REQUEST_BODY_BYTES:
            raise errors.invalid(
                "The request is larger than the 5 MB this extension sends in one step; send "
                "fewer lines or records"
            )
        request = Request(
            f"{BASE_URL}/{path}",
            method="POST",
            data=body,
            headers={
                "Accept": "application/json",
                "Content-Type": "application/x-www-form-urlencoded; charset=utf-8",
                "User-Agent": _USER_AGENT,
            },
        )
        status, raw = self._send(request, path, mutating=True, limit=MAX_WRITE_ANSWER_BYTES)
        data = self._write_answer(raw, path, status)
        self.committed = True
        return data

    def export(self, path: str, query: Iterable[tuple[str, str]] = ()) -> bytes:
        """GET one export; its raw XML answer."""
        if path not in READ_PATHS:
            raise errors.invalid("Not a Centas WS export")
        _, raw = self._send(self._get_request(path, query), path, mutating=False)
        self._refused_read(raw, path)
        return raw

    def probe(self) -> bytes:
        """The start of the product export: enough to know whether the key works."""
        _, raw = self._send(
            self._get_request("products/export", ()),
            "products/export",
            mutating=False,
            limit=PROBE_BYTES,
            truncate=True,
        )
        self._refused_read(raw, "products/export")
        return raw

    # -- one request ---------------------------------------------------------

    def _get_request(self, path: str, query: Iterable[tuple[str, str]]) -> Request:
        url = f"{BASE_URL}/{path}?" + urlencode([("token", self._connection.token), *query])
        return Request(
            url,
            method="GET",
            headers={"Accept": "application/xml, application/json", "User-Agent": _USER_AGENT},
        )

    def _read_expiry(self) -> float | None:
        return None if self.deadline is None else self.deadline + MIN_CALL_WINDOW_SECONDS

    def _send(
        self,
        request: Request,
        path: str,
        *,
        mutating: bool,
        limit: int | None = None,
        truncate: bool = False,
    ) -> tuple[int, bytes]:
        """One exchange — connect, headers and body — bounded by the step's deadline.

        A socket timeout applies to each receive, and a server can answer one byte at a
        time, so the whole exchange runs in a worker thread that is waited for only
        until the read deadline; past it the step reports a timeout (an unknown outcome
        for a write) and the abandoned exchange ends with the process.
        """
        if limit is None:
            limit = MAX_EXPORT_BYTES
        remaining = self.remaining()
        if remaining < MIN_CALL_WINDOW_SECONDS:
            raise DeadlineReached
        self._call_timeout = min(self._timeout_seconds, remaining)
        if mutating:
            self.mutated = True
        expires = self._read_expiry()
        if expires is None:
            return self._exchange(request, path, mutating=mutating, limit=limit, truncate=truncate)
        outcome: dict[str, Any] = {}

        def work() -> None:
            try:
                outcome["value"] = self._exchange(
                    request, path, mutating=mutating, limit=limit, truncate=truncate
                )
            except BaseException as exc:  # handed to the caller below
                outcome["error"] = exc

        worker = threading.Thread(target=work, name="centas-call", daemon=True)
        worker.start()
        worker.join(max(0.0, expires - self.clock()))
        if worker.is_alive():
            _late(mutating)
        if "error" in outcome:
            raise outcome["error"]
        return outcome["value"]

    def _exchange(
        self, request: Request, path: str, *, mutating: bool, limit: int, truncate: bool
    ) -> tuple[int, bytes]:
        try:
            with self._opener(
                request, timeout_seconds=self._call_timeout, purpose="Centas WS"
            ) as response:
                status = int(getattr(response, "status", 0) or getattr(response, "code", 0) or 0)
                raw = read_bounded(
                    response,
                    limit,
                    mutating=mutating,
                    expires=self._read_expiry(),
                    clock=self.clock,
                    per_read=self._call_timeout,
                    truncate=truncate,
                )
        except HTTPError as exc:
            # The exception carries the address (with an export's key): only its status
            # code and a scrubbed body are used.
            try:
                body = exc.read(MAX_ERROR_BODY_BYTES)
            except Exception:  # pragma: no cover - upstream body is optional
                body = b""
            raise self._status_error(int(exc.code), body, path, mutating=mutating) from None
        except PinnedPeerError as exc:
            # Raised while resolving and pinning, before anything was sent.
            if "cannot be resolved" in str(exc):
                raise ExtensionError(
                    errors.CONNECTION_FAILED,
                    "ws.centas.lt could not be resolved; check the network",
                    failure_class="transient",
                    retryable=True,
                    definitely_no_external_effect=True,
                    external_effect_status="failed",
                ) from None
            raise errors.no_effect(
                errors.BLOCKED_ADDRESS,
                "ws.centas.lt is not reachable under the host network policy",
            ) from None
        except TimeoutError:
            raise ExtensionError(
                errors.TIMEOUT_UNKNOWN if mutating else errors.TIMEOUT,
                "Centas WS did not answer in time" + (_CHECK_WS if mutating else ""),
                **_transport_failure_facts(mutating=mutating),
            ) from None
        except (OSError, http.client.HTTPException):
            raise ExtensionError(
                errors.TIMEOUT_UNKNOWN if mutating else errors.CONNECTION_FAILED,
                "The connection to Centas WS failed" + (_CHECK_WS if mutating else ""),
                **_transport_failure_facts(mutating=mutating),
            ) from None
        if status >= 300 or status < 200:
            raise self._status_error(status, raw[:MAX_ERROR_BODY_BYTES], path, mutating=mutating)
        return status, raw

    # -- answers -------------------------------------------------------------

    def scrub(self, value: Any) -> Any:
        """The key removed from every text and key of a parsed answer."""
        if isinstance(value, str):
            for form in self._connection.secret_forms():
                if form in value:
                    value = value.replace(form, "[redacted]")
            return value
        if isinstance(value, Mapping):
            return {self.scrub(k): self.scrub(v) for k, v in value.items()}
        if isinstance(value, list):
            return [self.scrub(v) for v in value]
        return value

    def _detail(self, raw: bytes) -> str:
        """Centas WS's own error text, or the text of an error page; never the key."""
        try:
            data = parse_json(raw)
        except ValueError:
            text = re.sub(r"(?s)<(script|style|head)[^>]*>.*?</\1>", " ", _text_of(raw))
            text = re.sub(r"<[^>]+>", " ", text)
            return errors.safe_text(self.scrub(text), 200)
        return error_text(self.scrub(data))

    def _write_answer(self, raw: bytes, path: str, status: int) -> dict[str, Any]:
        try:
            data = parse_json(raw)
        except ValueError:
            raise _unknown(
                f"Centas WS answered {path} (HTTP {status}) with something that could not be "
                "read" + _CHECK_WS,
                errors.INVALID_RESPONSE,
                status,
            ) from None
        data = self.scrub(data)
        verdict = success_of(data)
        if verdict is True:
            return data
        text = error_text(data)
        if verdict is False:
            # Centas WS documents no error kinds: a refusal may come after part of the
            # work (a batch, a buyer card) was saved, so nothing is promised.
            raise _unknown(
                f"Centas WS refused {path}" + (f": {text}" if text else "") + _CHECK_WS,
                errors.UPSTREAM_VALIDATION_FAILED,
                status,
            )
        raise _unknown(
            f"Centas WS's answer to {path} does not confirm that it was saved" + _CHECK_WS,
            errors.INVALID_RESPONSE,
            status,
        )

    def _refused_read(self, raw: bytes, path: str) -> None:
        """An export answered with Centas WS's JSON refusal instead of XML."""
        if not raw.lstrip(b"\xef\xbb\xbf \t\r\n").startswith(b"{"):
            return
        try:
            data = self.scrub(parse_json(raw))
        except ValueError:
            return  # left to the XML reader, which refuses it
        if success_of(data) is True:
            return
        text = error_text(data)
        lowered = text.lower()
        code = (
            errors.AUTHENTICATION_FAILED
            if "token" in lowered
            else errors.UPSTREAM_VALIDATION_FAILED
        )
        raise errors.no_effect(
            code,
            f"Centas WS refused {path}" + (f": {text}" if text else ""),
            failure_class="provider",
            retryable=False,
        )

    def _status_error(
        self, status: int, raw: bytes, path: str, *, mutating: bool
    ) -> ExtensionError:
        detail = self._detail(raw)
        suffix = f": {detail}" if detail else ""
        if status == 401:
            # Checked: ws.centas.lt answers a missing or unknown key with 401 before it
            # reads anything else.
            return errors.no_effect(
                errors.AUTHENTICATION_FAILED,
                f"Centas WS did not accept the key (HTTP 401){suffix}. Check the WS raktas "
                "in the connection.",
                failure_class="provider",
                retryable=False,
                http_status=status,
            )
        if 300 <= status < 400:
            code, message = (
                errors.REDIRECT_REJECTED,
                f"Centas WS redirected {path} (HTTP {status}); redirects are not followed",
            )
        elif status == 403:
            code, message = (
                errors.AUTHENTICATION_FAILED,
                f"Centas WS refused {path} (HTTP 403){suffix}",
            )
        elif status in {404, 405}:
            code, message = (
                errors.NOT_FOUND,
                f"Centas WS does not offer {path} (HTTP {status}); the API may have changed",
            )
        elif status >= 500 or status in {408, 429}:
            code, message = (
                errors.TIMEOUT if status in {408, 504} else errors.UPSTREAM_FAILURE,
                f"Centas WS could not complete {path} (HTTP {status}){suffix}",
            )
        else:
            code, message = (
                errors.UPSTREAM_VALIDATION_FAILED,
                f"Centas WS rejected {path} (HTTP {status}){suffix}",
            )
        if mutating:
            return _unknown(message + _CHECK_WS, code, status)
        return ExtensionError(
            code,
            message,
            failure_class="provider",
            retryable=status >= 500 or status in {408, 429},
            definitely_no_external_effect=True,
            external_effect_status="failed",
            http_status=status,
        )


_CHECK_WS = (
    "; check in Centas (the ws.centas.lt menu) or at ws.centas.lt whether it arrived before "
    "running the step again"
)


def _unknown(message: str, code: str, status: int | None) -> ExtensionError:
    return ExtensionError(
        code,
        message,
        failure_class="provider",
        retryable=False,
        definitely_no_external_effect=False,
        external_effect_status="timeout_unknown",
        http_status=status,
    )


def _text_of(raw: bytes) -> str:
    return raw.decode("utf-8", "replace")


def parse_json(raw: bytes) -> dict[str, Any]:
    """A JSON object, numbers with a point read as Decimal."""
    text = raw.decode("utf-8-sig", "strict") if raw else ""
    if not text.strip():
        raise ValueError("empty")
    try:
        data = json.loads(text, parse_float=Decimal)
    except json.JSONDecodeError as exc:
        raise ValueError("bad JSON") from exc
    if not isinstance(data, dict):
        raise ValueError("not an object")
    return data


def success_of(data: Mapping[str, Any]) -> bool | None:
    """True for ``success`` 1, False for 0, None when it is missing or anything else."""
    value = data.get("success")
    if isinstance(value, bool):
        return value
    if isinstance(value, int):
        return {1: True, 0: False}.get(value)
    if isinstance(value, str):
        return {"1": True, "0": False}.get(value.strip())
    return None


def error_text(data: Mapping[str, Any]) -> str:
    value = data.get("error")
    if isinstance(value, str) and value.strip():
        return errors.safe_text(value, 500)
    if isinstance(value, list) and value and all(isinstance(v, str) for v in value):
        return errors.safe_text("; ".join(value), 500)
    return ""


def parse_xml(raw: bytes) -> ElementTree.Element:
    """An export's XML document, parsed only after refusing any DOCTYPE or entity
    declaration, so no entity can be expanded and nothing outside it is read."""
    try:
        text = raw.decode("utf-8-sig", "strict")
    except UnicodeDecodeError as exc:
        raise ValueError("not UTF-8") from exc
    stripped = text.strip()
    if not stripped.startswith("<"):
        raise ValueError("not XML")
    upper = stripped.upper()
    if "<!DOCTYPE" in upper or "<!ENTITY" in upper:
        raise ValueError("DTD refused")
    try:
        return ElementTree.fromstring(stripped)  # nosec B314
    except ElementTree.ParseError as exc:
        raise ValueError("bad XML") from exc


def read_bounded(
    response: Any,
    limit: int,
    *,
    mutating: bool = False,
    expires: float | None = None,
    clock: Callable[[], float] = time.monotonic,
    per_read: float | None = None,
    truncate: bool = False,
) -> bytes:
    """Read at most ``limit`` bytes before ``expires``.

    With ``truncate`` the first ``limit`` bytes are returned and the rest is left
    unread; otherwise a longer answer is an error.
    """
    buffer = bytearray()
    sock = _socket_of(response)
    while True:
        if expires is not None:
            left = expires - clock()
            if left <= 0:
                _late(mutating)
            if sock is not None:
                try:
                    sock.settimeout(max(0.5, min(left, per_read or left)))
                except OSError:  # pragma: no cover - a closed socket fails the read below
                    pass
        chunk = response.read(min(CHUNK_BYTES, limit + 1 - len(buffer)))
        if not chunk:
            break
        buffer.extend(chunk)
        if expires is not None and clock() > expires:
            _late(mutating)
        if len(buffer) > limit:
            if truncate:
                return bytes(buffer[:limit])
            if mutating:
                raise _unknown(
                    "Centas WS's answer was too large to read" + _CHECK_WS,
                    errors.INVALID_RESPONSE,
                    None,
                )
            raise errors.no_effect(
                errors.RESPONSE_TOO_LARGE,
                f"Centas WS's export is larger than the {limit // (1024 * 1024)} MB this "
                "extension reads",
            )
    return bytes(buffer)


def _late(mutating: bool) -> None:
    if not mutating:
        raise DeadlineReached
    raise ExtensionError(
        errors.TIMEOUT_UNKNOWN,
        "Centas WS's answer did not arrive in time" + _CHECK_WS,
        failure_class="transient",
        retryable=False,
        definitely_no_external_effect=False,
        external_effect_status="timeout_unknown",
    )


def _socket_of(response: Any) -> Any:
    """The socket under an http.client response, when it can be reached."""
    for path in (("fp", "raw", "_sock"), ("fp", "fp", "raw", "_sock"), ("_sock",)):
        node = response
        for name in path:
            node = getattr(node, name, None)
        if node is not None and hasattr(node, "settimeout"):
            return node
    return None


def _transport_failure_facts(*, mutating: bool) -> dict[str, Any]:
    return {
        "failure_class": "transient",
        "retryable": not mutating,
        "definitely_no_external_effect": not mutating,
        "external_effect_status": "timeout_unknown" if mutating else "failed",
    }


__all__ = [
    "READ_PATHS",
    "WRITE_PATHS",
    "CentasTransport",
    "DeadlineReached",
    "error_text",
    "parse_json",
    "parse_xml",
    "read_bounded",
    "success_of",
]
