"""Review 2026-11-17, item 13: Send invoice to another company says when Centas WS's
counts do not show every line, and when the e-mail asked for was not sent."""

from __future__ import annotations

from typing import Any

import pytest
from support import FakeCentas, ok, run
from test_batches import COMPANY_INVOICE

TWO_LINES = {**COMPANY_INVOICE, "lines": COMPANY_INVOICE["lines"] * 2}


def _warnings(answer: dict[str, Any], inputs: dict[str, Any] = TWO_LINES) -> list[str]:
    response = run(FakeCentas(purchase__import=answer), "send_invoice_to_company", inputs)
    assert response["ok"] is True, response
    assert response["external_effect_status"] == "succeeded"
    return response["result"]["warnings"]


def test_13_counts_equal_to_the_lines_sent_give_no_warning() -> None:
    assert _warnings(ok(purchase_rows_created=2, document_rows_created=2, email_sent=False)) == []


@pytest.mark.parametrize(
    "counts",
    [
        {"purchase_rows_created": 1, "document_rows_created": 2},
        {"purchase_rows_created": 2, "document_rows_created": 0},
        {"purchase_rows_created": 0, "document_rows_created": 0},
    ],
)
def test_13_counts_other_than_the_lines_sent_are_said(counts: dict[str, int]) -> None:
    warnings = _warnings(ok(**counts))
    assert any("2 lines sent" in w and "not confirmed" in w for w in warnings), warnings


@pytest.mark.parametrize(
    "answer",
    [ok(), ok(purchase_rows_created=2), ok(document_rows_created=2), ok(purchase_rows_created="x")],
)
def test_13_missing_counts_are_said(answer: dict[str, Any]) -> None:
    warnings = _warnings(answer)
    assert any("did not report" in w for w in warnings), warnings


@pytest.mark.parametrize("sent", [False, None, "yes"])
def test_13_an_e_mail_asked_for_and_not_confirmed_is_said(sent: Any) -> None:
    answer = ok(purchase_rows_created=2, document_rows_created=2)
    if sent is not None:
        answer["email_sent"] = sent
    warnings = _warnings(answer, {**TWO_LINES, "send_email": True})
    assert any("e-mail" in w for w in warnings), warnings


def test_13_an_e_mail_asked_for_and_sent_gives_no_warning() -> None:
    answer = ok(purchase_rows_created=2, document_rows_created=2, email_sent=True)
    assert _warnings(answer, {**TWO_LINES, "send_email": True}) == []
