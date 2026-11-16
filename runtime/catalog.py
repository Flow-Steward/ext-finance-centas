"""The closed list of this extension's steps and what each one runs."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from . import batches, documents, exports
from .context import Context

TEST_CONNECTION = "test_connection"

#: Write steps: operation id -> runner.
WRITES: dict[str, Callable[[Context], dict[str, Any]]] = {
    "send_sales_invoice": documents.send_sales_invoice,
    "send_purchase_invoice": documents.send_purchase_invoice,
    "send_order": documents.send_order,
    "send_payments": batches.send_payments,
    "send_products": batches.send_products,
}
#: Read steps: operation id -> runner.
READS: dict[str, Callable[[Context], dict[str, Any]]] = {
    TEST_CONNECTION: exports.test_connection,
    "get_products": exports.get_products,
    "find_product": exports.find_product,
    "get_stock_levels": exports.get_stock_levels,
    "get_payments": exports.get_payments,
}
#: Checks a write's inputs without sending anything (test runs).
VALIDATORS: dict[str, Callable[[Any], Any]] = {
    "send_sales_invoice": documents.sales_invoice_form,
    "send_purchase_invoice": documents.purchase_invoice_form,
    "send_order": documents.order_form,
    "send_payments": batches.payments_xml,
    "send_products": lambda operation_input: batches.products_xml(
        operation_input, "validation-only"
    ),
}
#: The outputs of each write in a test run, where nothing is sent.
NEUTRAL: dict[str, dict[str, Any]] = {
    "send_sales_invoice": {"document_id": None},
    "send_purchase_invoice": {"purchase_id": None},
    "send_order": {"order_hash": None},
    "send_payments": {"sent": 0, "found": None, "created": None, "references": []},
    "send_products": {"sent": 0, "found": None, "created": None, "updated": None, "codes": []},
}

WRITE_OPERATION_IDS: frozenset[str] = frozenset(WRITES)
OPERATION_IDS: frozenset[str] = frozenset(WRITES) | frozenset(READS)

__all__ = [
    "NEUTRAL",
    "OPERATION_IDS",
    "READS",
    "TEST_CONNECTION",
    "VALIDATORS",
    "WRITES",
    "WRITE_OPERATION_IDS",
]
