"""Project-scoped Centas WS connection: one Centas project through its API key.

Centas WS (ws.centas.lt) is the web exchange of the Centas desktop program. The
key — "WS raktas" in Centas, the ``token`` of the API documentation — is the only
setting: the address is fixed (``BASE_URL``) and is not configurable, so a
workflow can never send the key anywhere else, and never over plain http.

The key lives in a private field of a frozen dataclass whose ``repr`` never shows
it, and it is never placed in a result, a log line or an exception message.
"""

from __future__ import annotations

import html
import json
import re
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import quote, quote_plus

from . import errors
from .errors import ExtensionError

CONNECTION_TYPE_ID = "centas"
#: The documented address of Centas WS, always over https (the documentation shows
#: some paths with http://; ws.centas.lt answers every one of them over https).
BASE_URL = "https://ws.centas.lt/v1"
HOST = "ws.centas.lt"
CONFIG_FIELDS: frozenset[str] = frozenset({"label"})
SECRET_FIELDS: frozenset[str] = frozenset({"token"})

#: Shorter keys could not be removed from answers without mangling them.
MIN_TOKEN_LENGTH = 8
MAX_TOKEN_LENGTH = 256
#: Printable ASCII without spaces: the documentation's keys are letters, digits and "_".
_TOKEN_RE = re.compile(r"^[\x21-\x7e]+$")


@dataclass(frozen=True)
class Connection:
    """One validated Centas WS connection."""

    connection_id: str
    _token: str = field(repr=False)

    @property
    def token(self) -> str:
        return self._token

    def secret_forms(self) -> tuple[str, ...]:
        """Every way the key can appear in a text: as is and encoded."""
        token = self._token
        forms = {
            token,
            quote_plus(token, safe=""),
            quote(token, safe=""),
            json.dumps(token, ensure_ascii=False)[1:-1],
            html.escape(token, quote=True),
            html.escape(token, quote=False),
        }
        # Longest first, so a form that contains another is removed whole.
        return tuple(sorted((f for f in forms if f), key=len, reverse=True))

    def __repr__(self) -> str:  # pragma: no cover - defensive
        return f"Connection(connection_id={self.connection_id!r})"

    __str__ = __repr__


def _invalid(message: str) -> ExtensionError:
    return errors.no_effect(errors.INVALID_CONNECTION, message)


def _token(value: Any) -> str:
    text = value.strip() if isinstance(value, str) else ""
    if not text:
        raise _invalid("Add the Centas WS key (WS raktas) to this connection")
    if (
        len(text) < MIN_TOKEN_LENGTH
        or len(text) > MAX_TOKEN_LENGTH
        or not _TOKEN_RE.fullmatch(text)
    ):
        raise _invalid(
            "The Centas WS key is not usable: 8 to 256 printable characters without spaces"
        )
    return text


def connection_from_payload(payload: Mapping[str, Any], *, connection_ref: str) -> Connection:
    """Validate the selected project connection before any outbound request."""
    action = payload.get("action")
    target = action.get("target") if isinstance(action, Mapping) else None
    connection = target.get("connection") if isinstance(target, Mapping) else None
    if not isinstance(connection, Mapping):
        raise _invalid("The selected connection is unavailable")
    connection_id = str(connection.get("connection_id") or "")
    if not connection_id or (connection_ref and connection_id != connection_ref):
        raise _invalid("The selected connection does not match connection_ref")
    connection_type = str(
        connection.get("connection_type_id") or connection.get("connection_type") or ""
    )
    if connection_type and connection_type != CONNECTION_TYPE_ID:
        raise _invalid("The selected connection is not supported")
    secrets = connection.get("secrets")
    secrets = secrets if isinstance(secrets, Mapping) else {}
    if set(secrets) - SECRET_FIELDS:
        raise _invalid("The connection carries unsupported secrets")
    return Connection(connection_id=connection_id, _token=_token(secrets.get("token")))


__all__ = [
    "BASE_URL",
    "CONFIG_FIELDS",
    "CONNECTION_TYPE_ID",
    "HOST",
    "SECRET_FIELDS",
    "Connection",
    "connection_from_payload",
]
