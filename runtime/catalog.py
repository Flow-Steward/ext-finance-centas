"""The closed list of this extension's steps and what each one runs."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from functools import partial
from typing import Any

from . import batches, documents, queue, reads
from .context import Context

TEST_CONNECTION = "test_connection"
_CHECK_ONLY_KEY_STAND_IN = "validation-only"

Runner = Callable[[Context], dict[str, Any]]

#: Write steps: operation id -> runner.
WRITES: dict[str, Runner] = {
    "send_sales_invoice": documents.send_sales_invoice,
    "send_order": documents.send_order,
    "send_purchase_invoice": documents.send_purchase_invoice,
    "send_payments": batches.send_payments,
    "send_products": batches.send_products,
    "send_contrahents": batches.send_contrahents,
    "update_sales_documents": batches.update_sales_documents,
    "delete_sales_documents": batches.delete_sales_documents,
    "record_document_payments": batches.record_document_payments,
    "send_consignment": batches.send_consignment,
    "send_invoice_to_company": batches.send_invoice_to_company,
}
#: Take steps (reads with an effect: they take records from the Centas WS queue).
TAKES: dict[str, Runner] = {
    operation_id: partial(queue.take, operation_id=operation_id) for operation_id in queue.TAKES
}
#: Read steps.
READS: dict[str, Runner] = dict(reads.READS)

#: Checks a step's inputs without calling Centas WS (test runs, and before any write).
VALIDATORS: dict[str, Callable[[Mapping[str, Any]], Any]] = {
    "send_sales_invoice": documents.sales_invoice_form,
    "send_order": documents.order_form,
    "send_purchase_invoice": documents.purchase_invoice_form,
    "send_payments": batches.payments_xml,
    "send_products": lambda i: batches.products_xml(i, _CHECK_ONLY_KEY_STAND_IN),
    "send_contrahents": batches.contrahents_xml,
    "update_sales_documents": lambda i: batches.update_xml(i, _CHECK_ONLY_KEY_STAND_IN),
    "delete_sales_documents": lambda i: batches.delete_xml(i, _CHECK_ONLY_KEY_STAND_IN),
    "record_document_payments": lambda i: batches.document_payments_xml(
        i, _CHECK_ONLY_KEY_STAND_IN
    ),
    "send_consignment": batches.consignment_xml,
    "send_invoice_to_company": lambda i: batches.company_invoice_xml(
        i, _CHECK_ONLY_KEY_STAND_IN, None
    ),
    **{operation_id: partial(queue.path_of, operation_id) for operation_id in queue.TAKES},
}

_DOCUMENT_NEUTRAL = {"number": None, "net_total": None, "vat_total": None, "total": None}
#: The outputs of each effect step in a test run, where nothing is sent.
NEUTRAL: dict[str, dict[str, Any]] = {
    "send_sales_invoice": {"document_id": None, **_DOCUMENT_NEUTRAL},
    "send_order": {"order_id": None, **_DOCUMENT_NEUTRAL},
    "send_purchase_invoice": {"purchase_id": None, **_DOCUMENT_NEUTRAL},
    "send_payments": {"sent": 0, "payments_found_xml": None, "payments_created": None},
    "send_products": {
        "sent": 0,
        "products_found_xml": None,
        "products_created": None,
        "products_updated": None,
        "codes": [],
    },
    "send_contrahents": {
        "sent": 0,
        "contrahents_found_xml": None,
        "contrahents_created": None,
        "contrahents_updated": None,
        "branches_created": None,
        "branches_updated": None,
        "branches_deleted": None,
    },
    "update_sales_documents": {"sent": 0, "documents_found": None, "documents_updated": None},
    "delete_sales_documents": {"sent": 0, "documents_found": None, "documents_deleted": None},
    "record_document_payments": {
        "sent": 0,
        "documents_payments_found_xml": None,
        "documents_payments_created": None,
    },
    "send_consignment": {"lines_sent": 0, "consignment_rows_created": None},
    "send_invoice_to_company": {
        **_DOCUMENT_NEUTRAL,
        "email_requested": False,
        "purchase_rows_created": None,
        "document_rows_created": None,
        "email_sent": None,
    },
    **{operation_id: queue.neutral() for operation_id in queue.TAKES},
}
#: Steps whose test run returns the number and totals they would send.
DOCUMENT_STEPS = frozenset(
    {"send_sales_invoice", "send_order", "send_purchase_invoice", "send_invoice_to_company"}
)

#: Steps that save a workflow file after reading.
FILE_OUTPUT_IDS: frozenset[str] = frozenset(TAKES) | {"get_order_invoice_pdf"}

EFFECT_OPERATION_IDS: frozenset[str] = frozenset(WRITES) | frozenset(TAKES)
OPERATION_IDS: frozenset[str] = EFFECT_OPERATION_IDS | frozenset(READS)
#: Kept for callers that ask which steps change Centas WS.
WRITE_OPERATION_IDS = EFFECT_OPERATION_IDS

__all__ = [
    "DOCUMENT_STEPS",
    "EFFECT_OPERATION_IDS",
    "FILE_OUTPUT_IDS",
    "NEUTRAL",
    "OPERATION_IDS",
    "READS",
    "TAKES",
    "TEST_CONNECTION",
    "VALIDATORS",
    "WRITES",
    "WRITE_OPERATION_IDS",
]
