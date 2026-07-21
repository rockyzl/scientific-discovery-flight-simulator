"""Executable public-product contract for the TEMPO evidence study.

The checks deliberately cover stable scientific/provenance hooks rather than pixels. They protect
the boundary between reported Zhou scalars, synthetic teaching inputs, and API-derived outputs.
"""

from __future__ import annotations

import re
import shutil
import subprocess
from collections import Counter
from html.parser import HTMLParser
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
INDEX_PATH = ROOT / "demo" / "index.html"
HTML_PATH = ROOT / "demo" / "tempo.html"
JS_PATH = ROOT / "demo" / "tempo.js"
CSS_PATH = ROOT / "demo" / "tempo.css"


class ContractParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.ids: list[str] = []
        self.links: list[str] = []
        self.scripts: list[str] = []
        self.inputs: list[dict[str, str]] = []
        self._text: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        values = {name: value or "" for name, value in attrs}
        if values.get("id"):
            self.ids.append(values["id"])
        if tag == "a" and values.get("href"):
            self.links.append(values["href"])
        if tag == "link" and values.get("href"):
            self.links.append(values["href"])
        if tag == "script" and values.get("src"):
            self.scripts.append(values["src"])
        if tag == "input":
            self.inputs.append(values)

    def handle_data(self, data: str) -> None:
        self._text.append(data)

    @property
    def text(self) -> str:
        return " ".join(" ".join(self._text).split())


def page() -> tuple[str, str, str, ContractParser]:
    markup = HTML_PATH.read_text(encoding="utf-8")
    script = JS_PATH.read_text(encoding="utf-8")
    styles = CSS_PATH.read_text(encoding="utf-8")
    parser = ContractParser()
    parser.feed(markup)
    return markup, script, styles, parser


def test_public_page_has_unique_stable_hooks_and_registered_asset_paths() -> None:
    _, _, _, parser = page()
    counts = Counter(parser.ids)
    required = {
        "main",
        "published-atlas",
        "atlas-content",
        "atlas-table-body",
        "synthetic-workbench",
        "analysis-form",
        "peak-table",
        "result-cards",
        "conductivity",
        "conductivity-form",
        "conductivity-result",
    }
    assert required <= counts.keys()
    assert all(counts[item] == 1 for item in required)
    assert "/tempo.css" in parser.links
    assert "/tempo.js" in parser.scripts
    assert "/tempo/tempo.css" not in parser.links
    assert "/tempo/tempo.js" not in parser.scripts


def test_current_cv_explainer_has_a_visible_stable_tempo_backlink() -> None:
    markup = INDEX_PATH.read_text(encoding="utf-8")
    assert 'id="tempo-study-link"' in markup
    assert 'href="/tempo/"' in markup
    assert "Open the TEMPO multi-sample CV evidence study" in markup


def test_reported_atlas_is_attributed_and_fail_closed() -> None:
    markup, script, _, parser = page()
    assert "◆ PUBLISHED REPORTED VALUE" in parser.text
    assert "10.1039/D0RA03424J" in parser.text
    assert "CC BY-NC 3.0" in parser.text
    assert "Table 1" in parser.text
    assert "DATASET UNAVAILABLE" in parser.text
    assert "No substitute values or synthetic curves are shown" in parser.text
    for href in (
        "https://pubs.rsc.org/en/content/articlehtml/2020/ra/d0ra03424j",
        "https://doi.org/10.1039/D0RA03424J",
        "https://www.rsc.org/suppdata/d0/ra/d0ra03424j/d0ra03424j1.pdf",
        "https://creativecommons.org/licenses/by-nc/3.0/",
    ):
        assert href in markup
    assert 'const REFERENCE_URL = "/tempo/reference-v1.json"' in script
    assert 'dataset.schema_version !== "tempo-reference-v1"' in script
    assert 'sample.source_table !== "Table 1"' in script


def test_five_reference_samples_and_typed_quantity_contract_are_exact() -> None:
    _, script, _, _ = page()
    expected = {
        "4ht": ("4-hydroxy-TEMPO", "0.812", "3.14e-6", "4.45e-3", "2.11", "1.25", "33.5"),
        "4ot": ("4-oxo-TEMPO", "0.910", "4.61e-6", "1.05e-2", "1.22", "0.79", "21.2"),
        "4at": ("4-amino-TEMPO", "0.895", "3.77e-6", "4.01e-3", "5.79", "4.80", "128.6"),
        "4cyt": ("4-cyano-TEMPO", "0.881", "6.23e-6", "4.29e-3", "2.6e-2", "null", "null"),
        "4cat": ("4-carboxy-TEMPO", "0.776", "2.64e-6", "2.25e-3", "2.1e-2", "null", "null"),
    }
    for sample_id, values in expected.items():
        pattern = re.compile(
            rf'"{sample_id}":\s*\{{\s*name:\s*"{re.escape(values[0])}",\s*'
            rf'e0:\s*{values[1]},\s*d:\s*{values[2]},\s*k0:\s*{values[3]},\s*'
            rf'water:\s*{values[4]},\s*kcl:\s*{values[5]},\s*capacity:\s*{values[6]}\s*\}}'
        )
        assert pattern.search(script), f"missing frozen reference vector for {sample_id}"

    for key in (
        "formal_potential_v_vs_she",
        "diffusion_coefficient_cm2_s",
        "electron_transfer_rate_constant_cm_s",
        "solubility_water_mol_l",
        "solubility_kcl_mol_l",
        "theoretical_capacity_ah_l",
    ):
        assert key in script
    assert 'item.status === "not_reported"' in script
    assert "item.value !== null" in script


def test_synthetic_teaching_world_is_visibly_separate_from_published_data() -> None:
    markup, script, _, parser = page()
    assert "PUBLISHED SCALAR CONTEXT ENDS HERE" in parser.text
    assert "◇ SYNTHETIC TEACHING DATA · NOT A LAB MEASUREMENT" in parser.text
    assert "Zhou values do not generate, fit, calibrate, or validate" in parser.text
    assert "No automatic peak picking occurs" in parser.text
    assert "not submitted to the analysis API" in markup
    assert "deterministic synthetic schema fixtures" in parser.text
    assert 'provenance: "synthetic_teaching"' in script
    assert 'assignment_source: "manual"' in script


def test_six_editable_reviewed_scan_rates_are_present() -> None:
    markup, _, _, parser = page()
    assert tuple(map(int, re.findall(r'<tr data-rate="(\d+)">', markup))) == (
        5,
        10,
        25,
        50,
        100,
        200,
    )
    peak_inputs = [item for item in parser.inputs if "mV per second" in item.get("aria-label", "")]
    assert len(peak_inputs) == 30
    assert all(item.get("aria-label") for item in peak_inputs)
    reviewed = [item for item in peak_inputs if "reviewed" in item["aria-label"]]
    assert len(reviewed) == 6
    assert all("checked" in item for item in reviewed)


def test_analysis_request_uses_frozen_condition_and_inference_contract() -> None:
    _, script, _, _ = page()
    assert 'const INFERENCE_SCHEMA = "tempo-inference-v1"' in script
    assert 'const ANALYZE_URL = "/api/tempo/analyze"' in script
    assert 'const CONDUCTIVITY_URL = "/api/tempo/conductivity"' in script
    for fragment in (
        'condition_id: "synthetic-tempo-kcl-298k-v1"',
        'supporting_electrolyte: { name: "KCl", concentration_mol_l: 0.5 }',
        'ph: { status: "measured", value: 7 }',
        "temperature_k:",
        'working_electrode: { material: "glassy carbon", area_cm2:',
        'potential_scale: "SHE"',
        "electron_count:",
        'units: { potential: "V", current: "A", scan_rate: "V/s", area: "cm2", concentration: "mol/cm3", temperature: "K" }',
    ):
        assert fragment in script
    assert 'method: "POST"' in script
    assert "crypto.randomUUID()" in script
    assert "stableStringify" in script
    assert 'crypto.subtle.digest("SHA-256"' in script
    assert 'const body = stableStringify(request)' in script
    assert '"X-Tempo-Input-Hash": inputHash' in script
    assert '"X-Tempo-Input-Hash": expectedHash' in script


def test_analysis_response_uses_authoritative_nested_result_schema() -> None:
    _, script, _, _ = page()
    assert "results.peak_descriptors" in script
    assert "peaks.aggregate" in script
    assert "peaks.per_trace" in script
    assert '"reversibility_evidence" in peaks' in script
    assert "results.diffusion" in script
    assert "diffusion.branches" in script
    assert '["anodic", "cathodic"]' in script
    assert "results.ir_correction" in script
    assert "response.results.conductivity" in script
    assert 'conductivity.unit !== "S/m"' in script
    assert 'resistance_kind: "conductivity_cell"' in script
    assert "temperature_k:" in script


def test_optional_ir_ui_builds_reviewed_matching_records_without_auto_review() -> None:
    markup, script, _, parser = page()
    for field_id in (
        "resistance-operation-id",
        "resistance-method",
        "ir-cell-id",
        "ir-geometry-id",
        "ir-electrolyte-id",
        "ir-record-reviewed",
        "load-ir-teaching-record",
    ):
        assert f'id="{field_id}"' in markup
    review = next(item for item in parser.inputs if item.get("id") == "ir-record-reviewed")
    assert "checked" not in review
    assert "Loading it does not mark the record reviewed" in parser.text
    for fragment in (
        'provenance: "independent_resistance_measurement"',
        'reviewed: byId("ir-record-reviewed").checked',
        "resistance: { operation_id: operationId, ...sharedContext }",
        "cv: { ...sharedContext }",
        'sample_id: request.sample.sample_id',
        'condition_id: request.condition.condition_id',
        'byId("ir-record-reviewed").checked = false',
    ):
        assert fragment in script
    assert 'byId("ir-record-reviewed").checked = true' not in script


def test_conductivity_ui_builds_calibration_and_matching_records_without_auto_review() -> None:
    markup, script, _, parser = page()
    for field_id in (
        "calibration-method",
        "calibration-id",
        "conductivity-operation-id",
        "conductivity-sample-id",
        "conductivity-cell-id",
        "conductivity-geometry-id",
        "conductivity-condition-id",
        "calibration-record-reviewed",
        "conductivity-record-reviewed",
        "load-conductivity-teaching-record",
    ):
        assert f'id="{field_id}"' in markup
    reviews = {
        item["id"]: item
        for item in parser.inputs
        if item.get("id") in {"calibration-record-reviewed", "conductivity-record-reviewed"}
    }
    assert set(reviews) == {"calibration-record-reviewed", "conductivity-record-reviewed"}
    assert all("checked" not in item for item in reviews.values())
    assert "Loading it never checks the review confirmations for you" in parser.text
    for fragment in (
        'method: byId("calibration-method").value',
        'reviewed: byId("calibration-record-reviewed").checked',
        'reviewed: byId("conductivity-record-reviewed").checked',
        'independent: byId("conductivity-record-reviewed").checked',
        "measurement: { ...matchingContext }",
        'byId("calibration-record-reviewed").checked = false',
        'byId("conductivity-record-reviewed").checked = false',
    ):
        assert fragment in script
    assert 'byId("calibration-record-reviewed").checked = true' not in script
    assert 'byId("conductivity-record-reviewed").checked = true' not in script


def test_refusals_and_stale_input_fail_closed() -> None:
    markup, script, _, parser = page()
    assert "— NO ESTIMATE" in parser.text
    for key in ("code", "message", "missing_fields", "invalid_fields", "excluded_trace_ids", "audit_id"):
        assert f'"{key}"' in script
    assert "analysisController?.abort()" in script
    assert "conductivityController?.abort()" in script
    assert "stale or mismatched analysis response discarded" in script
    assert "stale or mismatched conductivity response discarded" in script
    assert 'byId("request-audit").textContent = "No current request. Input changed or no request has been sent."' in script
    assert 'byId("conductivity-request-audit").textContent = "No current request. Input changed or no request has been sent."' in script
    assert "No hard reversible, quasi-reversible, or irreversible class is emitted" in markup


def test_responsive_controls_and_mobile_overflow_guard_are_present() -> None:
    _, _, styles, _ = page()
    assert "min-height: 44px" in styles
    assert "overflow-x: auto" in styles
    assert "@media (max-width: 980px)" in styles
    assert "@media (max-width: 420px)" in styles
    assert "max-width: 100%" in styles
    assert ".workbench-grid > *" in styles
    assert "#analysis-form" in styles
    assert ".conductivity-form > *" in styles


def test_success_cards_are_plain_summaries_and_full_json_stays_in_audit() -> None:
    markup, script, _, _ = page()
    assert "Mean apparent midpoint" in script
    assert "ΔEp range" in script
    assert "Anodic D" in script
    assert "Cathodic D" in script
    assert "PARTIAL EVIDENCE" in script
    assert "Audit this analysis" in markup
    assert "JSON.stringify(data, null, 2)" not in script


def test_javascript_parses() -> None:
    node = shutil.which("node")
    if not node:
        pytest.skip("Node.js is optional; syntax check unavailable")
    subprocess.run([node, "--check", str(JS_PATH)], check=True, capture_output=True, text=True)
