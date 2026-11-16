"""Take steps: GET operations that take records from the Centas WS queue.

Centas WS is a two-way queue between a shop and the Centas program. These exports
are the program's side of it: the specification says payments/export,
payments/export/{type} and purchase/export without dates mark what they return as
exported or downloaded; documents/export without filters and orders/export return
what "has not yet been marked as downloaded" and do not say they leave it unmarked,
so they are treated the same. After a take, the Centas program no longer sees those
records as new.

So a take is an external effect: it is declared, test runs send nothing, it is never
retried, and a failure after it was sent is reported as unknown. What Centas WS sent
is never lost: the answer, scrubbed of the key, is first saved whole as a workflow
file, and only then read into records. Records that do not fit the step output, or
an answer that cannot be read, stay available in that file.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from . import budget, errors, files, values
from .context import Context
from .records import xml_records
from .transport import PAYMENT_TYPES, unknown

TAKES: dict[str, tuple[str, str]] = {
    # operation id -> (path, record element)
    "take_new_sales_documents": ("documents/export", "dokumentas"),
    "take_new_orders": ("orders/export", "dokumentas"),
    "take_new_purchases": ("purchase/export", "dokumentas"),
    "take_new_payments": ("payments/export", "Payment"),
}
INPUTS: dict[str, frozenset[str]] = {
    "take_new_sales_documents": frozenset(),
    "take_new_orders": frozenset(),
    "take_new_purchases": frozenset(),
    "take_new_payments": frozenset({"payment_type"}),
}
PAYMENT_TYPE_CHOICES = {kind: kind for kind in PAYMENT_TYPES}


def path_of(operation_id: str, operation_input: Mapping[str, Any]) -> str:
    """The queue path a take step calls, its inputs checked."""
    values.closed(operation_input, INPUTS[operation_id] | {"connection_ref"}, "The step input")
    path = TAKES[operation_id][0]
    if operation_id == "take_new_payments":
        kind = values.choice(
            operation_input.get("payment_type"), "Payment type", PAYMENT_TYPE_CHOICES
        )
        if kind is not None:
            path = f"payments/export/{kind}"
    return path


def neutral() -> dict[str, Any]:
    return {"items": [], "count": 0, "file": None}


def take(context: Context, operation_id: str) -> dict[str, Any]:
    path = path_of(operation_id, context.operation_input)
    raw = context.transport.take(path)
    scrubbed = context.transport.scrub_bytes(raw)
    try:
        handle = files.save(
            context,
            scrubbed,
            binding_key=files.QUEUE_BINDING,
            content_type=files.QUEUE_CONTENT_TYPE,
            what="The records taken from Centas WS",
        )
    except errors.ExtensionError as exc:
        raise unknown(
            f"{exc.message}: Centas WS has probably marked them as exported already — check "
            "in Centas before running the step again",
            errors.ARTIFACT_OUTPUT_UNAVAILABLE,
            None,
        ) from None
    warnings: list[str] = []
    try:
        items, read_warnings = xml_records(
            raw, context.transport.scrub, record_tag=TAKES[operation_id][1], path=path
        )
        warnings += read_warnings.items
    except errors.ExtensionError as exc:
        items = []
        warnings.append(f"{exc.message}; the answer is kept whole in the file")
    count = len(items)
    result = {"items": items, "count": count, "file": handle, "warnings": warnings}
    if not budget.fits(result):
        result["items"] = []
        warnings.append(
            f"The {count} records taken are too many for the step output; they are all in the file"
        )
    return result


__all__ = ["INPUTS", "TAKES", "neutral", "path_of", "take"]
