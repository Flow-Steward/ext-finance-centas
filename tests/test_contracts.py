"""The generated contracts match their source, every form field is a runtime input,
every documented operation and field is covered, and the customer texts stay plain."""

from __future__ import annotations

import hashlib
import re
import struct
import sys
from typing import Any

import pytest
import yaml
from support import BUNDLE

sys.path.insert(0, str(BUNDLE / "tests" / "reference"))

import build_contracts  # noqa: E402
import centas_api  # noqa: E402
import op_specs  # noqa: E402

from runtime import batches, catalog, documents, queue, reads, reference  # noqa: E402
from runtime.connection import CONFIG_FIELDS, SECRET_FIELDS  # noqa: E402
from runtime.transport import READ_PATHS, TAKE_PATHS, WRITE_PATHS  # noqa: E402

#: What each step's runtime accepts (besides connection_ref).
RUNTIME_INPUTS: dict[str, frozenset[str]] = {
    "send_sales_invoice": documents.SALES_INPUTS,
    "send_order": documents.ORDER_INPUTS,
    "send_purchase_invoice": documents.PURCHASE_INPUTS,
    "send_invoice_to_company": batches.COMPANY_INVOICE_INPUTS,
    "send_payments": frozenset({"payments"}),
    "send_products": frozenset({"products"}),
    "send_contrahents": frozenset({"contrahents"}),
    "update_sales_documents": frozenset({"documents"}),
    "delete_sales_documents": frozenset({"documents"}),
    "record_document_payments": frozenset({"documents"}),
    "send_consignment": batches.CONSIGNMENT_INPUTS,
    **queue.INPUTS,
    **reads.INPUTS,
}
#: What each list of records' runtime accepts.
RUNTIME_ITEMS: dict[tuple[str, str], frozenset[str]] = {
    ("send_sales_invoice", "lines"): documents.SALES_LINE_FIELDS,
    ("send_order", "lines"): documents.ORDER_LINE_FIELDS,
    ("send_purchase_invoice", "lines"): documents.PURCHASE_LINE_FIELDS,
    ("send_invoice_to_company", "lines"): batches.INVOICE_LINE_FIELDS,
    ("send_payments", "payments"): batches.PAYMENT_FIELDS,
    ("send_products", "products"): batches.PRODUCT_FIELDS,
    ("send_contrahents", "contrahents"): batches.CONTRAHENT_FIELDS,
    ("update_sales_documents", "documents"): batches.UPDATE_FIELDS,
    ("delete_sales_documents", "documents"): batches.DOCUMENT_KEY_FIELDS,
    ("record_document_payments", "documents"): batches.DOCUMENT_PAYMENT_FIELDS,
    ("send_consignment", "lines"): batches.CONSIGNMENT_LINE_FIELDS,
}


def load(path: str) -> Any:
    return yaml.safe_load((BUNDLE / path).read_text(encoding="utf-8"))


def specs() -> dict[str, dict[str, Any]]:
    return {s["operation_id"]: s for s in op_specs.steps()}


@pytest.mark.parametrize("path", sorted(p for p in build_contracts.outputs() if "/" in p))
def test_generated_files_are_current(path: str) -> None:
    expected = build_contracts.render(path, build_contracts.outputs()[path])
    assert (BUNDLE / path).read_text(encoding="utf-8") == expected, (
        f"{path} drifted: run python3 tests/reference/build_contracts.py"
    )


def test_external_effects_are_the_writes_and_the_takes() -> None:
    manifest = load("extension.yaml")
    assert manifest["external_effects"] == build_contracts.outputs()["external_effects"]
    effects = {e["operation_id"] for e in manifest["external_effects"]}
    assert effects == set(catalog.EFFECT_OPERATION_IDS)
    assert set(catalog.TAKES) <= effects
    assert all(e["test_mode_behavior"] == "suppress" for e in manifest["external_effects"])


def test_every_step_is_registered_once_and_routable() -> None:
    ids = [s["operation_id"] for s in op_specs.steps()]
    assert len(ids) == len(set(ids)) == 29
    assert set(ids) == set(catalog.OPERATION_IDS)
    assert {s["operation_id"] for s in op_specs.steps() if s["kind"] == "action"} == set(
        catalog.EFFECT_OPERATION_IDS
    )
    assert {s["operation_id"] for s in op_specs.steps() if s["take"]} == set(catalog.TAKES)


def test_every_form_field_is_a_runtime_input_and_back() -> None:
    forms = {f["operation_id"]: f for f in load("contracts/step_ui_manifest.yaml")["forms"]}
    ops = {o["operation_id"]: o for o in load("contracts/operation_manifest.yaml")["operations"]}
    assert set(RUNTIME_INPUTS) == set(ops)
    for operation_id, accepted in RUNTIME_INPUTS.items():
        fields = {f["name"] for f in forms[operation_id]["fields"]}
        inputs = {i["name"] for i in ops[operation_id]["inputs"]} - {"connection_ref"}
        assert fields == inputs == set(accepted), operation_id


def test_every_record_field_is_one_the_runtime_accepts() -> None:
    ops = {o["operation_id"]: o for o in load("contracts/operation_manifest.yaml")["operations"]}
    for (operation_id, name), accepted in RUNTIME_ITEMS.items():
        [item] = [i for i in ops[operation_id]["inputs"] if i["name"] == name]
        assert set(item["schema"]["items"]["properties"]) == set(accepted), operation_id


def test_file_inputs_use_the_artifact_picker() -> None:
    forms = {f["operation_id"]: f for f in load("contracts/step_ui_manifest.yaml")["forms"]}
    [pdf] = [f for f in forms["send_invoice_to_company"]["fields"] if f["name"] == "pdf_file"]
    assert pdf["widget_type"] == "artifact_picker"
    policies = {
        p["operation_id"]: p for p in load("contracts/artifact_policies.yaml")["artifact_policies"]
    }
    assert set(policies) == {"send_invoice_to_company", "get_order_invoice_pdf", *catalog.TAKES}


def test_titles_are_unique_and_start_with_a_verb() -> None:
    titles = [s["display_name"] for s in op_specs.steps()]
    assert len(titles) == len(set(titles))
    for title in titles:
        assert title.split()[0] in {
            "Send",
            "Get",
            "Find",
            "Test",
            "Take",
            "Update",
            "Delete",
            "Record",
            "Check",
        }, title


def test_take_steps_say_they_take_from_the_queue() -> None:
    for spec in op_specs.steps():
        if spec["take"]:
            assert spec["display_name"].startswith("Take new")
            assert "from the Centas WS queue" in spec["display_name"]
            assert "no longer see these records as new" in spec["description"]


def test_every_step_declares_warnings_and_effects_report_theirs() -> None:
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
    form = load("ui/pages/connection.yaml")["components"][0]
    assert set(form["data"]["config_fields"]) == set(CONFIG_FIELDS)
    assert set(form["data"]["secret_fields"]) == set(SECRET_FIELDS)
    assert {f["path"] for f in form["fields"]} == set(CONFIG_FIELDS) | set(SECRET_FIELDS)
    assert form["data"]["test_action"] == catalog.TEST_CONNECTION


def _resolve(path: str) -> dict[str, Any]:
    """The schema an input path names: step.input, step.input[].field, …[].list[].field."""
    operation_id, _, rest = path.partition(".")
    parts = rest.split("[].")
    [item] = [i for i in specs()[operation_id]["inputs"] if i["name"] == parts[0]]
    schema = item["schema"]
    for part in parts[1:]:
        schema = schema["items"]["properties"][part]
    return schema


def test_every_documented_field_has_an_input_or_a_reason() -> None:
    for operation, field, path, note, source in centas_api.documented_fields():
        assert source in {centas_api.SPEC, centas_api.GITBOOK}
        if path is None:
            assert note, (operation, field)
            continue
        assert _resolve(path) is not None, path
        operation_id = path.split(".", 1)[0]
        spec = centas_api.OPERATIONS[operation]
        assert operation_id in spec["steps"] or operation.startswith("GET /consignments"), path


def test_every_input_that_reaches_centas_is_in_the_coverage() -> None:
    covered = {p.split("[]")[0] for _, _, p, _, _ in centas_api.documented_fields() if p}
    for spec in op_specs.steps():
        for item in spec["inputs"]:
            if item["name"] in centas_api.LOCAL_INPUTS:
                continue
            assert f"{spec['operation_id']}.{item['name']}" in covered, (
                spec["operation_id"],
                item["name"],
            )


def test_every_operation_of_the_specification_is_covered() -> None:
    operations = centas_api.OPERATIONS
    assert len(operations) == 31
    for name, spec in operations.items():
        assert spec["steps"] or spec.get("reason"), name
        for step in spec["steps"]:
            assert step in catalog.OPERATION_IDS, (name, step)
    called = {o.split(" ", 1)[1].lstrip("/") for o, s in operations.items() if s["steps"]}
    called = {"payments/export" if c == "payments/export/{type}" else c for c in called}
    paths = (
        READ_PATHS | WRITE_PATHS | {p for p in TAKE_PATHS if not p.startswith("payments/export/")}
    )
    assert paths == called


def test_the_specification_is_pinned_in_one_place() -> None:
    cov = build_contracts.coverage()
    assert cov["source"]["sha256"] == reference.SPECIFICATION["sha256"]
    assert reference.SPECIFICATION["sha256"] == (
        "1860fbaa2e053f1117c09be6e3d6ddf5b075ee3769af7d40436cb70d7267498f"
    )
    assert cov["source"]["url"] == "https://ws.centas.lt/api-docs/openapi.yaml"


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


def test_ui_pages_hold_no_markdown_tables_and_no_trailing_blank_lines() -> None:
    for path in (BUNDLE / "ui" / "pages").glob("*.yaml"):
        text = path.read_text(encoding="utf-8")
        assert not re.search(r"^\s*\|.*\|\s*$", text, re.M), path
        assert "|+" not in text and not text.rstrip().endswith("..."), path


def test_the_runtime_calls_no_address_but_ws_centas_lt() -> None:
    for path in (p for p in (BUNDLE / "runtime").glob("*.py") if p.name != "reference.py"):
        for host in re.findall(r"https?://([a-z0-9.-]+)", path.read_text(encoding="utf-8")):
            assert host == "ws.centas.lt", (path, host)


def test_customer_texts_list_nothing_unverified() -> None:
    texts = [BUNDLE / "README.md", BUNDLE / "CHANGELOG.md", BUNDLE / "extension.yaml"]
    texts += sorted((BUNDLE / "ui").rglob("*.yaml")) + sorted((BUNDLE / "contracts").glob("*"))
    for path in texts:
        text = path.read_text(encoding="utf-8")
        for phrase in ("Not verified", "not verified", "Limits", "undocumented"):
            assert phrase not in text, (path.name, phrase)


def test_every_write_says_centas_ws_does_not_check_for_repeats() -> None:
    quiet = {"update_sales_documents", "delete_sales_documents"}
    for spec in op_specs.steps():
        if spec["kind"] == "action" and not spec["take"] and spec["operation_id"] not in quiet:
            assert "Centas WS does not check for repeats" in spec["description"], spec[
                "operation_id"
            ]


def test_health_reports_the_pinned_specification() -> None:
    import health

    report = health.check_health()
    assert report["ok"] is True
    assert report["declared_operations"] == len(catalog.OPERATION_IDS)
    assert report["specification_sha256"] == reference.SPECIFICATION["sha256"]


def test_step_order_follows_the_groups() -> None:
    groups = [s["group"] for s in op_specs.steps()]
    assert groups == sorted(groups, key=op_specs.GROUPS.index)
    ids = [o["operation_id"] for o in load("contracts/operation_manifest.yaml")["operations"]]
    assert ids == [s["operation_id"] for s in op_specs.steps()]
