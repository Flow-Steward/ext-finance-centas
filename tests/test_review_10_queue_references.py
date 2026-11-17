"""Review 2026-11-17, item 10: the key written as XML character references (&#65; or
&#x41;) never reaches the saved queue file, and the records taken are never lost."""

from __future__ import annotations

from typing import Any
from xml.etree import ElementTree

import pytest
from support import TOKEN, FakeCentas, Files, dumped, run, xml

from runtime.transport import CentasTransport

PAYMENT = "<PaymentType>BankDeb</PaymentType><Amount>121.00</Amount><RefNr>REF-001</RefNr>"


def _decimal(text: str) -> str:
    return "".join(f"&#{ord(c)};" for c in text)


def _hex(text: str) -> str:
    return "".join(f"&#x{ord(c):X};" for c in text)


def _mixed(text: str) -> str:
    return "".join(c if i % 2 else f"&#{ord(c)};" for i, c in enumerate(text))


def _leaks(saved: bytes) -> list[str]:
    """Where the key is in the saved bytes, as they are and once the XML is read."""
    found = []
    if TOKEN.encode() in saved:
        found.append("raw")
    root = ElementTree.fromstring(saved)
    for node in root.iter():
        if TOKEN in (node.text or "") or TOKEN in (node.tail or ""):
            found.append(f"<{node.tag}>")
        if any(TOKEN in v for v in node.attrib.values()):
            found.append(f"@{node.tag}")
    return found


@pytest.mark.parametrize("encode", [_decimal, _hex, _mixed], ids=["decimal", "hex", "mixed"])
def test_10_a_key_in_character_references_is_not_in_the_saved_file(encode: Any) -> None:
    files = Files()
    answer = xml(PAYMENT, tag="Payment", token=encode(TOKEN))
    response = run(FakeCentas(payments__export=answer), "take_new_payments", files=files)
    assert response["ok"] is True, response
    saved = files.written[0]["data"]
    assert _leaks(saved) == []
    assert b"[redacted]" in saved
    assert TOKEN not in dumped(response)
    assert response["result"]["items"][0]["RefNr"] == "REF-001"


def test_10_a_key_in_an_attribute_in_references_is_not_in_the_saved_file() -> None:
    files = Files()
    body = (
        f'<?xml version="1.0"?><root><Payment ref="{_hex(TOKEN)}">{PAYMENT}</Payment></root>'
    ).encode()
    response = run(FakeCentas(payments__export=body), "take_new_payments", files=files)
    assert response["ok"] is True, response
    assert _leaks(files.written[0]["data"]) == []


def test_10_records_are_returned_when_the_answer_cannot_be_cleaned(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def broken(self: Any, raw: bytes) -> bytes:
        raise ValueError("the answer could not be cleaned")

    monkeypatch.setattr(CentasTransport, "scrub_bytes", broken)
    files = Files()
    answer = xml(PAYMENT, tag="Payment", token=_decimal(TOKEN))
    response = run(FakeCentas(payments__export=answer), "take_new_payments", files=files)
    assert response["ok"] is True, response
    assert response["external_effect_status"] == "succeeded"
    assert files.written == []
    assert response["result"]["items"][0]["RefNr"] == "REF-001"
    assert response["result"]["file"] is None
    assert any("not in a file" in w for w in response["result"]["warnings"])
    assert TOKEN not in dumped(response)
