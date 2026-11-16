"""The generated contracts match their source, and every form field is a runtime input."""

from __future__ import annotations

import hashlib
import re
import struct
import sys
import zlib
from pathlib import Path
from typing import Any

import pytest
import yaml
from support import BUNDLE

sys.path.insert(0, str(BUNDLE / "tests" / "reference"))

import build_contracts  # noqa: E402
import centas_api  # noqa: E402
import op_specs  # noqa: E402

from runtime import batches, catalog, documents, exports  # noqa: E402
from runtime.connection import CONFIG_FIELDS, SECRET_FIELDS  # noqa: E402

#: What each step's runtime accepts (besides connection_ref).
RUNTIME_INPUTS: dict[str, frozenset[str]] = {
    "send_sales_invoice": documents.SALES_INPUTS,
    "send_purchase_invoice": documents.PURCHASE_INPUTS,
    "send_order": documents.ORDER_INPUTS,
    "send_payments": batches.PAYMENTS_INPUTS,
    "send_products": batches.PRODUCTS_INPUTS,
    "get_products": exports.GET_PRODUCTS_INPUTS,
    "find_product": exports.FIND_PRODUCT_INPUTS,
    "get_stock_levels": exports.STOCK_LEVELS_INPUTS,
    "get_payments": exports.GET_PAYMENTS_INPUTS,
    "test_connection": frozenset(),
}
#: What each line or record list's runtime accepts.
RUNTIME_ITEMS: dict[tuple[str, str], frozenset[str]] = {
    ("send_sales_invoice", "lines"): documents.SALES_LINE_FIELDS,
    ("send_purchase_invoice", "lines"): documents.PURCHASE_LINE_FIELDS,
    ("send_order", "lines"): documents.ORDER_LINE_FIELDS,
    ("send_payments", "payments"): batches.PAYMENT_FIELDS,
    ("send_products", "products"): batches.PRODUCT_FIELDS,
}


def load(path: str) -> Any:
    return yaml.safe_load((BUNDLE / path).read_text(encoding="utf-8"))


@pytest.mark.parametrize("path", sorted(p for p in build_contracts.outputs() if "/" in p))
def test_generated_files_are_current(path: str) -> None:
    expected = build_contracts.render(path, build_contracts.outputs()[path])
    assert (BUNDLE / path).read_text(encoding="utf-8") == expected, (
        f"{path} drifted: run python3 tests/reference/build_contracts.py"
    )


def test_external_effects_match_the_write_steps() -> None:
    manifest = load("extension.yaml")
    assert manifest["external_effects"] == build_contracts.outputs()["external_effects"]
    assert {e["operation_id"] for e in manifest["external_effects"]} == set(
        catalog.WRITE_OPERATION_IDS
    )


def test_every_step_is_registered_once_and_routable() -> None:
    ids = [s["operation_id"] for s in op_specs.steps()]
    assert len(ids) == len(set(ids))
    assert set(ids) == set(catalog.OPERATION_IDS)
    writes = {s["operation_id"] for s in op_specs.steps() if s["kind"] == "action"}
    assert writes == set(catalog.WRITE_OPERATION_IDS)


def test_every_form_field_is_a_runtime_input_and_back() -> None:
    forms = {f["operation_id"]: f for f in load("contracts/step_ui_manifest.yaml")["forms"]}
    ops = {o["operation_id"]: o for o in load("contracts/operation_manifest.yaml")["operations"]}
    for operation_id, accepted in RUNTIME_INPUTS.items():
        fields = {f["name"] for f in forms[operation_id]["fields"]}
        inputs = {i["name"] for i in ops[operation_id]["inputs"]} - {"connection_ref"}
        assert fields == inputs == set(accepted), operation_id


def test_every_record_field_is_one_the_runtime_accepts() -> None:
    ops = {o["operation_id"]: o for o in load("contracts/operation_manifest.yaml")["operations"]}
    for (operation_id, name), accepted in RUNTIME_ITEMS.items():
        [item] = [i for i in ops[operation_id]["inputs"] if i["name"] == name]
        assert set(item["schema"]["items"]["properties"]) == set(accepted), operation_id


def test_titles_are_unique_and_start_with_a_verb() -> None:
    titles = [s["display_name"] for s in op_specs.steps()]
    assert len(titles) == len(set(titles))
    for title in titles:
        assert title.split()[0] in {"Send", "Get", "Find", "Test"}, title


def test_every_step_declares_warnings_and_writes_their_effect() -> None:
    for op in load("contracts/operation_manifest.yaml")["operations"]:
        names = [o["name"] for o in op["outputs"]]
        assert "warnings" in names, op["operation_id"]
        if op["operation_kind"] == "action":
            assert names[-2:] == ["external_effect_status", "definitely_no_external_effect"]
            assert "timeout_unknown" in op["error_codes"]


def test_the_connection_form_matches_the_connection_type() -> None:
    [kind] = load("contracts/connection_types.yaml")["connection_types"]
    assert set(kind["config_schema"]["properties"]) == set(CONFIG_FIELDS)
    assert set(kind["secret_schema"]["properties"]) == set(SECRET_FIELDS)
    page = load("ui/pages/connection.yaml")
    form = page["components"][0]
    assert set(form["data"]["config_fields"]) == set(CONFIG_FIELDS)
    assert set(form["data"]["secret_fields"]) == set(SECRET_FIELDS)
    assert {f["path"] for f in form["fields"]} == set(CONFIG_FIELDS) | set(SECRET_FIELDS)
    assert form["data"]["test_action"] == catalog.TEST_CONNECTION


def test_every_documented_field_has_an_input_or_a_reason() -> None:
    specs = {s["operation_id"]: s for s in op_specs.steps()}
    for endpoint, field, path, note in centas_api.documented_fields():
        if path is None:
            assert note, (endpoint, field)
            continue
        operation_id, _, rest = path.partition(".")
        name, _, item = rest.partition("[].")
        [found] = [i for i in specs[operation_id]["inputs"] if i["name"] == name]
        if item:
            assert item in found["schema"]["items"]["properties"], path
        assert operation_id in centas_api.ENDPOINTS[endpoint]["steps"], path


def test_every_input_that_reaches_centas_is_in_the_coverage() -> None:
    covered = {p for _, _, p, _ in centas_api.documented_fields() if p}
    for spec in op_specs.steps():
        for item in spec["inputs"]:
            if item.get("wire"):
                assert f"{spec['operation_id']}.{item['name']}" in covered, item["name"]


def test_seven_documented_endpoints_and_the_undocumented_are_excluded() -> None:
    assert len(centas_api.ENDPOINTS) == 7
    cov = build_contracts.coverage()
    assert all(e["status"] == "excluded: undocumented" for e in cov["undocumented"])
    from runtime.transport import READ_PATHS, WRITE_PATHS

    documented = {e.split(" ", 1)[1].removeprefix("/v1/") for e in centas_api.ENDPOINTS}
    assert READ_PATHS | WRITE_PATHS == documented


def test_versions_agree() -> None:
    version = load("extension.yaml")["version"]
    changelog = (BUNDLE / "CHANGELOG.md").read_text(encoding="utf-8")
    assert re.search(rf"^## {re.escape(version)} — \d{{4}}-\d{{2}}-\d{{2}}$", changelog, re.M)


def test_the_icon_is_a_square_png_described_in_branding() -> None:
    data = (BUNDLE / "icon.png").read_bytes()
    assert data[:8] == b"\x89PNG\r\n\x1a\n"
    width, height = struct.unpack(">II", data[16:24])
    assert width == height and 32 <= width <= 512
    assert hashlib.sha256(data).hexdigest() in (BUNDLE / "BRANDING.md").read_text()


def test_the_icon_is_drawn_by_its_script() -> None:
    import make_icon

    # The pixels, not the compressed bytes: another zlib may compress them differently.
    data = (BUNDLE / "icon.png").read_bytes()
    idat = data.index(b"IDAT")
    (length,) = struct.unpack(">I", data[idat - 4 : idat])
    assert zlib.decompress(data[idat + 4 : idat + 4 + length]) == b"".join(make_icon.pixels())


def test_ui_pages_hold_no_markdown_tables() -> None:
    for path in (BUNDLE / "ui" / "pages").glob("*.yaml"):
        assert not re.search(r"^\s*\|.*\|\s*$", path.read_text(encoding="utf-8"), re.M), path


def test_the_runtime_calls_no_address_but_ws_centas_lt() -> None:
    # runtime/reference.py only names the documentation's sources.
    for path in (p for p in (BUNDLE / "runtime").glob("*.py") if p.name != "reference.py"):
        for host in re.findall(r"https?://([a-z0-9.-]+)", path.read_text(encoding="utf-8")):
            assert host == "ws.centas.lt", (path, host)


def test_the_readme_promises_nothing_unverified() -> None:
    readme = (BUNDLE / "README.md").read_text(encoding="utf-8")
    assert "Limits" not in readme


def test_health_reports_the_pinned_source() -> None:
    import health

    report = health.check_health()
    assert report["ok"] is True
    assert report["declared_operations"] == len(catalog.OPERATION_IDS)
    assert report["documentation_sha256"] == build_contracts.coverage()["source"]["sha256"]


def _all_ids(path: Path) -> list[str]:
    return [o["operation_id"] for o in yaml.safe_load(path.read_text())["operations"]]


def test_step_order_follows_the_groups() -> None:
    groups = [s["group"] for s in op_specs.steps()]
    assert groups == sorted(groups, key=op_specs.GROUPS.index)
    assert _all_ids(BUNDLE / "contracts/operation_manifest.yaml") == [
        s["operation_id"] for s in op_specs.steps()
    ]
