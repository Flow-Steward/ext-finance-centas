"""Shaping a step's result: the write markers and the output budget."""

from __future__ import annotations

from collections.abc import Mapping
from decimal import Decimal
from typing import Any

from . import budget


def mark_write(result: dict[str, Any]) -> dict[str, Any]:
    result["external_effect_status"] = "succeeded"
    result["definitely_no_external_effect"] = False
    return result


def fit_write_result(result: dict[str, Any]) -> dict[str, Any]:
    """Drop long echo lists until the result fits; the write itself already happened."""
    for key in ("references", "codes"):
        if budget.fits(result):
            break
        if isinstance(result.get(key), list):
            result[key] = []
            result.setdefault("warnings", []).append(
                f"The list of {key} sent is too long for the step output and is left out"
            )
    return result


def plain(value: Any) -> Any:
    """Decimals as plain text, so no number goes through float on the way out."""
    if isinstance(value, Decimal):
        return format(value, "f")
    if isinstance(value, Mapping):
        return {k: plain(v) for k, v in value.items()}
    if isinstance(value, list):
        return [plain(v) for v in value]
    return value


def ok(result: Mapping[str, Any]) -> dict[str, Any]:
    response: dict[str, Any] = {
        "ok": True,
        "result": plain(dict(result)),
        "error_code": None,
        "error": None,
        "errors": [],
    }
    if "external_effect_status" in result:
        response["external_effect_status"] = result["external_effect_status"]
        response["definitely_no_external_effect"] = result["definitely_no_external_effect"]
    return response
