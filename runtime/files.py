"""Workflow files: a PDF a step sends, a PDF or a queue answer a step saves."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from flowsteward_extension_sdk import find_artifact_descriptor

from . import errors
from .context import Context
from .errors import ExtensionError, invalid
from .transport import MIN_CALL_WINDOW_SECONDS, DeadlineReached

ARTIFACT_TIMEOUT_SECONDS = 120.0
MAX_UPLOAD_BYTES = 8 * 1024 * 1024
MAX_PDF_BYTES = 40 * 1024 * 1024

#: Must match contracts/artifact_policies.yaml (tests/reference/build_contracts.py).
UPLOAD_BINDING = "centas_upload"
PDF_BINDING = "centas_pdf"
QUEUE_BINDING = "centas_queue"
PDF_CONTENT_TYPE = "application/pdf"
QUEUE_CONTENT_TYPE = "application/xml"


def read_upload(context: Context, handle: str) -> bytes:
    """A workflow file the step sends, at most 8 MB."""
    declared = None
    try:
        descriptor = find_artifact_descriptor(dict(context.payload), artifact_id=handle)
    except Exception:
        descriptor = {}
    if isinstance(descriptor, Mapping):
        size = descriptor.get("size_bytes")
        declared = size if isinstance(size, int) and not isinstance(size, bool) else None
    if declared is not None and declared > MAX_UPLOAD_BYTES:
        raise invalid("The file is larger than 8 MB")
    remaining = context.transport.remaining() - MIN_CALL_WINDOW_SECONDS
    if remaining <= 0:
        raise DeadlineReached
    try:
        body = context.artifact_reader(
            dict(context.payload),
            artifact_id=handle,
            timeout_seconds=min(ARTIFACT_TIMEOUT_SECONDS, remaining),
        )
    except ExtensionError:
        raise
    except Exception:
        raise errors.no_effect(
            errors.ARTIFACT_INPUT_UNAVAILABLE,
            "The file could not be read from Flow Steward storage",
        ) from None
    if not isinstance(body, (bytes, bytearray)) or not body:
        raise invalid("The file is empty")
    if len(body) > MAX_UPLOAD_BYTES:
        raise invalid("The file is larger than 8 MB")
    return bytes(body)


def save(context: Context, data: bytes, *, binding_key: str, content_type: str, what: str) -> str:
    """Save ``data`` as a workflow file; its handle."""
    try:
        written = context.artifact_writer(
            dict(context.payload),
            [data],
            binding_key=binding_key,
            content_type=content_type,
            timeout_seconds=ARTIFACT_TIMEOUT_SECONDS,
        )
    except ExtensionError:
        raise
    except Exception:
        raise errors.no_effect(
            errors.ARTIFACT_OUTPUT_UNAVAILABLE, f"{what} could not be saved"
        ) from None
    handle = written.get("artifact_handle") if isinstance(written, Mapping) else None
    if not isinstance(handle, str) or not handle.strip():
        raise errors.no_effect(errors.ARTIFACT_OUTPUT_UNAVAILABLE, f"{what} could not be saved")
    return handle.strip()


def artifact_handle(value: Any, what: str) -> str:
    if not isinstance(value, str) or not value.strip() or len(value) > 200:
        raise invalid(f"{what} must be a workflow file")
    return value.strip()


__all__ = [
    "MAX_PDF_BYTES",
    "MAX_UPLOAD_BYTES",
    "PDF_BINDING",
    "PDF_CONTENT_TYPE",
    "QUEUE_BINDING",
    "QUEUE_CONTENT_TYPE",
    "UPLOAD_BINDING",
    "artifact_handle",
    "read_upload",
    "save",
]
