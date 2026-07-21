"""Numerical and fail-closed tests for the restricted TEMPO inference contract."""

from __future__ import annotations

import copy
import hashlib
import json

import pytest

from discovery_flight_simulator.tempo import (
    TempoError,
    analyze_cv_request,
    calculate_conductivity,
)


RATES = [0.005, 0.01, 0.025, 0.05, 0.1, 0.2]
CURRENTS = [
    6.618079750015135e-6,
    9.359378139338148e-6,
    1.479847620154866e-5,
    2.092820574668560e-5,
    2.959695240309732e-5,
    4.185641149337120e-5,
]


def canonical_hash(payload: object) -> str:
    canonical = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def cv_request(*, requested: list[str] | None = None) -> dict[str, object]:
    traces = []
    peaks = []
    potential = [0.70 + index * 0.01 for index in range(24)]
    for index, (rate, current) in enumerate(zip(RATES, CURRENTS, strict=True), start=1):
        trace_id = f"trace-{index}"
        traces.append(
            {
                "trace_id": trace_id,
                "scan_rate_v_s": rate,
                "replicate_id": "r1",
                "cycle_number": 1,
                "potential_v": potential,
                "current_a": [(-0.5 + point / 23) * current for point in range(24)],
                "potential_scale": "SHE",
                "transformation": "raw",
            }
        )
        peaks.append(
            {
                "trace_id": trace_id,
                "epa_v": 0.842 + index * 0.001,
                "epc_v": 0.782 - index * 0.001,
                "ipa_a": current,
                "ipc_a": -current,
                "assignment_source": "manual",
                "reviewed": True,
            }
        )
    return {
        "schema_version": "tempo-inference-v1",
        "request_id": "science-vector",
        "source": {
            "provenance": "synthetic_teaching",
            "source_id": "qa-six-rate",
            "checksum": "sha256:qa-six-rate",
        },
        "sample": {
            "sample_id": "tempo-teaching",
            "preferred_name": "TEMPO teaching sample",
            "molecular_form": "neutral nitroxide",
            "concentration_mol_cm3": 1e-6,
        },
        "condition": {
            "condition_id": "condition-298k",
            "solvent": "water",
            "supporting_electrolyte": {"name": "KCl", "concentration_mol_l": 0.5},
            "ph": {"status": "measured", "value": 7.0},
            "temperature_k": 298.15,
            "working_electrode": {
                "material": "glassy carbon",
                "area_cm2": 0.19634954084936207,
            },
            "counter_electrode": "Pt foil",
            "reference_electrode": "SCE",
            "potential_scale": "SHE",
            "electron_count": 1,
            "atmosphere": "N2",
            "preprocessing_description": "none; synthetic QA fixture",
            "units": {
                "potential": "V",
                "current": "A",
                "scan_rate": "V/s",
                "area": "cm2",
                "concentration": "mol/cm3",
                "temperature": "K",
            },
        },
        "traces": traces,
        "peak_assignments": peaks,
        "requested": requested or ["peak_descriptors", "diffusion"],
    }


def test_peak_descriptors_and_aggregate_use_reviewed_assignments() -> None:
    request = cv_request(requested=["peak_descriptors"])
    response = analyze_cv_request(request)
    result = response["results"]["peak_descriptors"]
    first = result["per_trace"][0]
    assert first["e_half_v"] == pytest.approx(0.812)
    assert first["delta_ep_v"] == pytest.approx(0.062)
    assert first["peak_current_ratio"] == pytest.approx(1.0)
    assert result["aggregate"]["e_half_v"]["count"] == 6
    assert result["aggregate"]["delta_ep_v"]["sample_standard_deviation"] > 0
    assert result["reversibility_evidence"]["summary"] == "PARTIAL EVIDENCE"
    assert result["reversibility_evidence"]["classification"] is None


def test_randles_sevcik_recovers_frozen_diffusion_vector_by_branch() -> None:
    response = analyze_cv_request(cv_request(requested=["diffusion"]))
    result = response["results"]["diffusion"]
    assert result["status"] == "estimate_available"
    for name in ("anodic", "cathodic"):
        branch = result["branches"][name]
        assert branch["branch"] == name
        assert branch["diffusion_coefficient_cm2_s"] == pytest.approx(3.14e-6, rel=1e-10)
        assert branch["r_squared"] == pytest.approx(1.0)
        assert branch["qc_gate"] == {
            "name": "r_squared",
            "threshold": 0.98,
            "passed": True,
        }
        assert len(branch["residuals_a"]) == 6
        assert len(branch["ci95_cm2_s"]) == 2


def test_ir_preview_matches_vector_and_never_mutates_raw_input() -> None:
    request = cv_request(requested=["ir_correction"])
    request["traces"] = [copy.deepcopy(request["traces"][0])]
    request["peak_assignments"] = [copy.deepcopy(request["peak_assignments"][0])]
    request["traces"][0]["potential_v"][0:2] = [0.8, 0.9]
    request["traces"][0]["current_a"][0:2] = [0.001, -0.001]
    request["ir_correction"] = {
        "ru_ohm": 20.0,
        "fraction": 0.85,
        "resistance_source": {
            "operation_id": "operation-eis-17",
            "provenance": "independent_resistance_measurement",
        },
        "measurement_method": "EIS high-frequency resistance",
        "measurement_context": matching_ir_context(),
    }
    before = copy.deepcopy(request)
    response = analyze_cv_request(request)
    result = response["results"]["ir_correction"]
    assert result["traces"][0]["corrected_potential_v"][0:2] == pytest.approx([0.783, 0.917], abs=1e-12)
    assert result["traces"][0]["raw_potential_v"][0:2] == [0.8, 0.9]
    assert request == before
    assert result["traces"][0]["raw_hash"] != result["traces"][0]["corrected_hash"]


def test_success_envelope_hashes_exact_canonical_request_and_audits_copy() -> None:
    request = cv_request(requested=["peak_descriptors"])
    response = analyze_cv_request(request)
    assert response["schema_version"] == "tempo-inference-v1"
    assert response["request_id"] == request["request_id"]
    assert response["status"] == "estimate_available"
    assert response["provenance"] == "derived"
    assert response["input_hash"] == canonical_hash(request)
    assert response["audit"]["exact_input"] == request
    assert response["audit"]["exact_input"] is not request
    assert response["method_version"]
    assert isinstance(response["warnings"], list)
    assert isinstance(response["limitations"], list)


@pytest.mark.parametrize(
    ("mutator", "code"),
    [
        (lambda request: request.update(schema_version="wrong"), "SCHEMA_INVALID"),
        (lambda request: request["condition"]["units"].pop("current"), "UNIT_MISSING"),
        (lambda request: request["peak_assignments"][0].update(reviewed=False), "PEAKS_INVALID"),
        (lambda request: request["peak_assignments"][0].update(ipc_a=0.0), "PEAKS_INVALID"),
        (lambda request: request["peak_assignments"][0].update(epa_v=1.5), "PEAKS_INVALID"),
        (lambda request: request["condition"].update(temperature_k=310.0), "METADATA_MISSING"),
    ],
)
def test_invalid_cv_evidence_fails_closed(mutator, code: str) -> None:
    request = cv_request()
    mutator(request)
    with pytest.raises(TempoError) as error:
        analyze_cv_request(request)
    assert error.value.code == code
    refusal = error.value.response(request["request_id"])
    assert refusal["status"] == "no_estimate"
    assert refusal["results"] == {}
    assert set(refusal["refusal"]) == {
        "code",
        "message",
        "missing_fields",
        "invalid_fields",
        "excluded_trace_ids",
        "audit_id",
    }


def test_diffusion_refuses_fewer_than_three_distinct_rates() -> None:
    request = cv_request(requested=["diffusion"])
    request["traces"] = request["traces"][:2]
    request["peak_assignments"] = request["peak_assignments"][:2]
    with pytest.raises(TempoError, match="three distinct") as error:
        analyze_cv_request(request)
    assert error.value.code == "INSUFFICIENT_RATES"


def test_trace_reference_scale_mismatch_is_not_silently_converted() -> None:
    request = cv_request(requested=["peak_descriptors"])
    request["traces"][0]["potential_scale"] = "SCE"
    with pytest.raises(TempoError) as error:
        analyze_cv_request(request)
    assert error.value.code == "INCOMPATIBLE_CONDITIONS"
    assert error.value.excluded_trace_ids == ["trace-1"]


def test_diffusion_refuses_low_quality_fit_instead_of_returning_number() -> None:
    request = cv_request(requested=["diffusion"])
    irregular = [1e-5, 8e-6, 3e-5, 7e-6, 2e-5, 9e-6]
    for assignment, current in zip(request["peak_assignments"], irregular, strict=True):
        assignment["ipa_a"] = current
        assignment["ipc_a"] = -current
    with pytest.raises(TempoError) as error:
        analyze_cv_request(request)
    assert error.value.code == "FIT_QC_FAILED"


def test_diffusion_audit_identifies_unassigned_traces_as_excluded() -> None:
    request = cv_request(requested=["diffusion"])
    request["peak_assignments"] = request["peak_assignments"][:3]
    response = analyze_cv_request(request)
    for branch in response["results"]["diffusion"]["branches"].values():
        assert branch["included_trace_ids"] == ["trace-1", "trace-2", "trace-3"]
        assert branch["excluded_trace_ids"] == ["trace-4", "trace-5", "trace-6"]
    assert response["audit"]["excluded_trace_ids"] == ["trace-4", "trace-5", "trace-6"]


@pytest.mark.parametrize(
    ("current_unit", "current_scale"),
    [("mA", 1e3), ("uA", 1e6), ("µA", 1e6), ("μA", 1e6)],
)
def test_declared_equivalent_units_are_converted_once_and_audited(
    current_unit: str,
    current_scale: float,
) -> None:
    request = cv_request(requested=["peak_descriptors", "diffusion"])
    request["condition"]["units"].update(
        potential="mV",
        current=current_unit,
        scan_rate="mV/s",
    )
    for trace in request["traces"]:
        trace["scan_rate_v_s"] *= 1e3
        trace["potential_v"] = [value * 1e3 for value in trace["potential_v"]]
        trace["current_a"] = [value * current_scale for value in trace["current_a"]]
    for assignment in request["peak_assignments"]:
        assignment["epa_v"] *= 1e3
        assignment["epc_v"] *= 1e3
        assignment["ipa_a"] *= current_scale
        assignment["ipc_a"] *= current_scale
    original = copy.deepcopy(request)

    response = analyze_cv_request(request)
    peaks = response["results"]["peak_descriptors"]
    assert peaks["per_trace"][0]["e_half_v"] == pytest.approx(0.812)
    for branch in response["results"]["diffusion"]["branches"].values():
        assert branch["diffusion_coefficient_cm2_s"] == pytest.approx(3.14e-6, rel=1e-10)

    assert request == original
    assert response["audit"]["exact_input"] == original
    assert response["input_hash"] == canonical_hash(original)
    conversions = {
        item["quantity"]: item for item in response["audit"]["unit_conversions"]
    }
    assert conversions["potential"] == {
        "quantity": "potential",
        "from_unit": "mV",
        "to_unit": "V",
        "factor": 1e-3,
        "fields": [
            "traces[].potential_v",
            "peak_assignments[].epa_v",
            "peak_assignments[].epc_v",
        ],
    }
    assert conversions["current"]["from_unit"] == current_unit
    assert conversions["current"]["factor"] == pytest.approx(1 / current_scale)
    assert conversions["scan_rate"]["factor"] == 1e-3


def test_unknown_declared_unit_is_rejected() -> None:
    request = cv_request(requested=["diffusion"])
    request["condition"]["units"]["current"] = "nA"
    with pytest.raises(TempoError) as error:
        analyze_cv_request(request)
    assert error.value.code == "UNIT_MISSING"
    assert error.value.invalid_fields == ["condition.units.current"]


def test_ir_refuses_resistance_fitted_from_same_cv() -> None:
    request = cv_request(requested=["ir_correction"])
    request["ir_correction"] = {
        "ru_ohm": 20.0,
        "fraction": 0.85,
        "resistance_source": "estimated from CV",
        "measurement_method": "fit from CV",
        "measurement_context": "same ordinary CV",
    }
    with pytest.raises(TempoError) as error:
        analyze_cv_request(request)
    assert error.value.code == "RESISTANCE_INELIGIBLE"


def matching_ir_context() -> dict[str, object]:
    shared = {
        "sample_id": "tempo-teaching",
        "cell_id": "cell-tempo-01",
        "geometry_id": "geometry-gce-5mm",
        "electrolyte_id": "electrolyte-kcl-05m",
        "condition_id": "condition-298k",
    }
    return {
        "reviewed": True,
        "resistance": {"operation_id": "operation-eis-17", **shared},
        "cv": copy.deepcopy(shared),
    }


def eligible_ir_record() -> dict[str, object]:
    return {
        "ru_ohm": 20.0,
        "fraction": 0.85,
        "resistance_source": {
            "operation_id": "operation-eis-17",
            "provenance": "independent_resistance_measurement",
        },
        "measurement_method": "EIS high-frequency resistance",
        "measurement_context": matching_ir_context(),
    }


def test_ir_rejects_generic_nonempty_provenance_placeholders() -> None:
    request = cv_request(requested=["ir_correction"])
    request["ir_correction"] = {
        "ru_ohm": 20.0,
        "fraction": 0.85,
        "resistance_source": "x",
        "measurement_method": "banana",
        "measurement_context": "somewhere else",
    }
    with pytest.raises(TempoError) as error:
        analyze_cv_request(request)
    assert error.value.code == "RESISTANCE_INELIGIBLE"


@pytest.mark.parametrize("operation_id", ["test-01", "banana-01", "unknown-01", "  TeSt-01  "])
def test_ir_rejects_placeholder_tokens_with_suffixes(operation_id: str) -> None:
    request = cv_request(requested=["ir_correction"])
    record = eligible_ir_record()
    record["resistance_source"]["operation_id"] = operation_id
    record["measurement_context"]["resistance"]["operation_id"] = operation_id
    request["ir_correction"] = record
    with pytest.raises(TempoError) as error:
        analyze_cv_request(request)
    assert error.value.code == "RESISTANCE_INELIGIBLE"


@pytest.mark.parametrize(
    ("path", "value"),
    [
        (("measurement_method",), "banana"),
        (("resistance_source", "operation_id"), "x"),
        (("measurement_context", "reviewed"), False),
        (("measurement_context", "cv", "cell_id"), "cell-other-02"),
        (("measurement_context", "cv", "sample_id"), "sample-other-02"),
    ],
)
def test_ir_rejects_unknown_or_mismatched_structured_evidence(
    path: tuple[str, ...],
    value: object,
) -> None:
    request = cv_request(requested=["ir_correction"])
    record = eligible_ir_record()
    target = record
    for key in path[:-1]:
        target = target[key]
    target[path[-1]] = value
    request["ir_correction"] = record
    with pytest.raises(TempoError) as error:
        analyze_cv_request(request)
    assert error.value.code == "RESISTANCE_INELIGIBLE"


def conductivity_request() -> dict[str, object]:
    return {
        "schema_version": "tempo-inference-v1",
        "request_id": "conductivity-vector",
        "resistance_ohm": 100.0,
        "cell_constant_m_inv": 100.0,
        "calibration_source": {
            "calibration_id": "calibration-kcl-2026-01",
            "method": "certified_cell_constant",
            "cell_id": "conductivity-cell-01",
            "geometry_id": "conductivity-geometry-01",
            "reviewed": True,
        },
        "measurement_context": {
            "calibration_id": "calibration-kcl-2026-01",
            "reviewed": True,
            "resistance": {
                "operation_id": "resistance-operation-01",
                "independent": True,
                "resistance_kind": "conductivity_cell",
                "sample_id": "tempo-sample-01",
                "cell_id": "conductivity-cell-01",
                "geometry_id": "conductivity-geometry-01",
                "condition_id": "conductivity-condition-298k",
            },
            "measurement": {
                "sample_id": "tempo-sample-01",
                "cell_id": "conductivity-cell-01",
                "geometry_id": "conductivity-geometry-01",
                "condition_id": "conductivity-condition-298k",
            },
        },
        "temperature_k": 298.15,
    }


def test_independent_conductivity_vectors() -> None:
    request = conductivity_request()
    response = calculate_conductivity(request)
    assert response["results"]["conductivity"] == {
        "status": "estimate_available",
        "conductivity_s_m": 1.0,
        "unit": "S/m",
        "resistance_ohm": 100.0,
        "cell_constant_m_inv": 100.0,
    }
    request.update(request_id="conductivity-vector-4", resistance_ohm=30.0, cell_constant_m_inv=120.0)
    assert calculate_conductivity(request)["results"]["conductivity"]["conductivity_s_m"] == 4.0


@pytest.mark.parametrize(
    ("field", "value", "code"),
    [
        ("resistance_ohm", 0.0, "RESISTANCE_INELIGIBLE"),
        ("cell_constant_m_inv", -1.0, "CELL_CONSTANT_INELIGIBLE"),
        ("calibration_source", "", "CELL_CONSTANT_INELIGIBLE"),
    ],
)
def test_conductivity_fails_closed_for_ineligible_inputs(field: str, value: object, code: str) -> None:
    request = conductivity_request()
    request[field] = value
    with pytest.raises(TempoError) as error:
        calculate_conductivity(request)
    assert error.value.code == code


def test_conductivity_rejects_cv_ru_and_unrelated_geometry() -> None:
    request = conductivity_request()
    request["measurement_context"] = {
        "independent": False,
        "same_conductivity_cell": False,
        "resistance_kind": "cv_ru",
    }
    with pytest.raises(TempoError) as error:
        calculate_conductivity(request)
    assert error.value.code == "RESISTANCE_INELIGIBLE"


def test_conductivity_rejects_generic_nonempty_calibration_and_context() -> None:
    request = conductivity_request()
    request["calibration_source"] = "x"
    request["measurement_context"] = {
        "independent": True,
        "same_conductivity_cell": True,
        "resistance_kind": "conductivity_cell",
    }
    with pytest.raises(TempoError) as error:
        calculate_conductivity(request)
    assert error.value.code == "CELL_CONSTANT_INELIGIBLE"


@pytest.mark.parametrize("operation_id", ["test-01", "banana-01", "unknown-01", "  UNKNOWN-01  "])
def test_conductivity_rejects_placeholder_operation_tokens_with_suffixes(
    operation_id: str,
) -> None:
    request = conductivity_request()
    request["measurement_context"]["resistance"]["operation_id"] = operation_id
    with pytest.raises(TempoError) as error:
        calculate_conductivity(request)
    assert error.value.code == "RESISTANCE_INELIGIBLE"


@pytest.mark.parametrize(
    ("section", "field", "value", "code"),
    [
        ("measurement", "sample_id", "sample-other-02", "RESISTANCE_INELIGIBLE"),
        ("measurement", "cell_id", "conductivity-cell-99", "RESISTANCE_INELIGIBLE"),
        ("measurement", "geometry_id", "conductivity-geometry-99", "RESISTANCE_INELIGIBLE"),
        ("measurement", "condition_id", "conductivity-condition-310k", "RESISTANCE_INELIGIBLE"),
        ("calibration", "cell_id", "conductivity-cell-99", "RESISTANCE_INELIGIBLE"),
        ("calibration", "calibration_id", "calibration-other-02", "RESISTANCE_INELIGIBLE"),
    ],
)
def test_conductivity_rejects_context_or_calibration_mismatch(
    section: str,
    field: str,
    value: object,
    code: str,
) -> None:
    request = conductivity_request()
    if section == "calibration":
        request["calibration_source"][field] = value
    else:
        request["measurement_context"][section][field] = value
    with pytest.raises(TempoError) as error:
        calculate_conductivity(request)
    assert error.value.code == code
