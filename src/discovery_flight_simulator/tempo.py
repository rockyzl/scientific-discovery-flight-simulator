"""Fail-closed TEMPO CV evidence calculations for the public teaching demo.

The module intentionally implements a narrow contract. It accepts already-reviewed peak
assignments; it does not pick peaks, convert reference scales, infer resistance, or classify
electrochemical reversibility.
"""

from __future__ import annotations

import copy
import hashlib
import json
import math
import re
from collections.abc import Mapping, Sequence
from typing import Any


SCHEMA_VERSION = "tempo-inference-v1"
METHOD_VERSION = "tempo-restricted-v1.0.0"
_ALLOWED_PROVENANCE = {"synthetic_teaching", "user_uploaded_experimental_unverified"}
_ALLOWED_REQUESTS = {"peak_descriptors", "diffusion", "ir_correction"}
_CANONICAL_UNITS = {
    "potential": "V",
    "current": "A",
    "scan_rate": "V/s",
    "area": "cm2",
    "concentration": "mol/cm3",
    "temperature": "K",
}
_UNIT_FACTORS = {
    "potential": {"V": 1.0, "mV": 1e-3},
    "current": {"A": 1.0, "mA": 1e-3, "uA": 1e-6, "µA": 1e-6, "μA": 1e-6},
    "scan_rate": {"V/s": 1.0, "mV/s": 1e-3},
    "area": {"cm2": 1.0},
    "concentration": {"mol/cm3": 1.0},
    "temperature": {"K": 1.0},
}
_CONVERTED_FIELDS = {
    "potential": ["traces[].potential_v", "peak_assignments[].epa_v", "peak_assignments[].epc_v"],
    "current": ["traces[].current_a", "peak_assignments[].ipa_a", "peak_assignments[].ipc_a"],
    "scan_rate": ["traces[].scan_rate_v_s"],
    "area": ["condition.working_electrode.area_cm2"],
    "concentration": ["sample.concentration_mol_cm3"],
    "temperature": ["condition.temperature_k"],
}
_IR_METHODS = {"EIS high-frequency resistance", "current interruption"}
_CALIBRATION_METHODS = {"certified_cell_constant", "standard_solution_calibration"}
_GENERIC_IDENTIFIERS = {
    "unknown",
    "none",
    "na",
    "n/a",
    "test",
    "sample",
    "cell",
    "geometry",
    "condition",
    "banana",
}
_GENERIC_IDENTIFIER_TOKENS = {"unknown", "none", "na", "test", "banana"}
_T_CRITICAL_95 = {
    1: 12.706204736,
    2: 4.30265273,
    3: 3.182446305,
    4: 2.776445105,
    5: 2.570581836,
    6: 2.446911851,
    7: 2.364624252,
    8: 2.306004135,
    9: 2.262157163,
    10: 2.228138852,
    11: 2.20098516,
    12: 2.17881283,
    13: 2.160368656,
    14: 2.144786688,
    15: 2.131449546,
    16: 2.119905299,
    17: 2.109815578,
    18: 2.10092204,
    19: 2.093024054,
    20: 2.085963447,
    21: 2.079613845,
    22: 2.073873068,
    23: 2.06865761,
    24: 2.063898562,
    25: 2.059538553,
    26: 2.055529439,
    27: 2.051830516,
    28: 2.048407142,
    29: 2.045229642,
    30: 2.042272456,
}


def _canonical_json(value: object) -> str:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    )


def _sha256(value: object) -> str:
    return hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()


def _audit_id(value: object) -> str:
    try:
        digest = _sha256(value)
    except (TypeError, ValueError):
        digest = hashlib.sha256(repr(value).encode("utf-8")).hexdigest()
    return f"tempo-audit-{digest[:16]}"


class TempoError(ValueError):
    """A typed refusal that the demo server serializes as HTTP 422/409."""

    def __init__(
        self,
        code: str,
        message: str,
        *,
        missing_fields: Sequence[str] = (),
        invalid_fields: Sequence[str] = (),
        excluded_trace_ids: Sequence[str] = (),
        audit_id: str | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.missing_fields = list(missing_fields)
        self.invalid_fields = list(invalid_fields)
        self.excluded_trace_ids = list(excluded_trace_ids)
        self.audit_id = audit_id or _audit_id(
            {
                "code": code,
                "message": message,
                "missing": self.missing_fields,
                "invalid": self.invalid_fields,
                "excluded": self.excluded_trace_ids,
            }
        )

    def response(self, request_id: object = None) -> dict[str, object]:
        return {
            "schema_version": SCHEMA_VERSION,
            "request_id": request_id,
            "status": "no_estimate",
            "results": {},
            "refusal": {
                "code": self.code,
                "message": self.message,
                "missing_fields": self.missing_fields,
                "invalid_fields": self.invalid_fields,
                "excluded_trace_ids": self.excluded_trace_ids,
                "audit_id": self.audit_id,
            },
        }


def _refuse(
    request: object,
    code: str,
    message: str,
    *,
    missing: Sequence[str] = (),
    invalid: Sequence[str] = (),
    excluded: Sequence[str] = (),
) -> None:
    raise TempoError(
        code,
        message,
        missing_fields=missing,
        invalid_fields=invalid,
        excluded_trace_ids=excluded,
        audit_id=_audit_id({"request": request, "code": code}),
    )


def _mapping(value: object) -> Mapping[str, Any] | None:
    return value if isinstance(value, Mapping) else None


def _finite_number(value: object, *, positive: bool = False, nonnegative: bool = False) -> bool:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return False
    number = float(value)
    if not math.isfinite(number):
        return False
    if positive and number <= 0:
        return False
    if nonnegative and number < 0:
        return False
    return True


def _nonempty(value: object) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _valid_identifier(value: object) -> bool:
    if not isinstance(value, str):
        return False
    normalized = value.strip()
    normalized_casefolded = normalized.casefold()
    tokens = [token for token in re.split(r"[-_:.]+", normalized_casefolded) if token]
    return (
        6 <= len(normalized) <= 128
        and normalized_casefolded not in _GENERIC_IDENTIFIERS
        and not any(token in _GENERIC_IDENTIFIER_TOKENS for token in tokens)
        and re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._:-]*[A-Za-z0-9]", normalized) is not None
        and any(separator in normalized for separator in ("-", "_", ":", "."))
    )


def _matching_records(
    first: Mapping[str, Any],
    second: Mapping[str, Any],
    fields: Sequence[str],
) -> bool:
    return all(_valid_identifier(first.get(field)) and first.get(field) == second.get(field) for field in fields)


def _scaled(value: object, factor: float) -> object:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return value
    return float(value) * factor


def _normalize_cv_units(
    request: Mapping[str, Any],
) -> tuple[dict[str, Any], list[dict[str, object]]]:
    """Deep-copy and convert declared input fields once into frozen canonical units."""

    normalized = copy.deepcopy(dict(request))
    condition = _mapping(normalized.get("condition"))
    if condition is None:
        return normalized, []
    units = _mapping(condition.get("units"))
    if units is None:
        _refuse(request, "UNIT_MISSING", "Declared scientific units are required.", missing=["condition.units"])
    missing = [key for key in _UNIT_FACTORS if key not in units]
    unknown = [
        f"condition.units.{key}"
        for key, allowed in _UNIT_FACTORS.items()
        if key in units and units.get(key) not in allowed
    ]
    if missing or unknown:
        _refuse(
            request,
            "UNIT_MISSING",
            "A declared unit is missing or unsupported by the frozen conversion boundary.",
            missing=[f"condition.units.{key}" for key in missing],
            invalid=unknown,
        )

    conversions: list[dict[str, object]] = []
    factors: dict[str, float] = {}
    for quantity, canonical_unit in _CANONICAL_UNITS.items():
        declared_unit = str(units[quantity])
        factor = _UNIT_FACTORS[quantity][declared_unit]
        factors[quantity] = factor
        conversions.append(
            {
                "quantity": quantity,
                "from_unit": declared_unit,
                "to_unit": canonical_unit,
                "factor": factor,
                "fields": copy.deepcopy(_CONVERTED_FIELDS[quantity]),
            }
        )
        condition["units"][quantity] = canonical_unit

    sample = _mapping(normalized.get("sample"))
    if sample is not None:
        sample["concentration_mol_cm3"] = _scaled(
            sample.get("concentration_mol_cm3"),
            factors["concentration"],
        )
    electrode = _mapping(condition.get("working_electrode"))
    if electrode is not None:
        electrode["area_cm2"] = _scaled(electrode.get("area_cm2"), factors["area"])
    condition["temperature_k"] = _scaled(condition.get("temperature_k"), factors["temperature"])

    traces = normalized.get("traces")
    if isinstance(traces, list):
        for trace in traces:
            if not isinstance(trace, dict):
                continue
            trace["scan_rate_v_s"] = _scaled(trace.get("scan_rate_v_s"), factors["scan_rate"])
            if isinstance(trace.get("potential_v"), list):
                trace["potential_v"] = [_scaled(value, factors["potential"]) for value in trace["potential_v"]]
            if isinstance(trace.get("current_a"), list):
                trace["current_a"] = [_scaled(value, factors["current"]) for value in trace["current_a"]]

    assignments = normalized.get("peak_assignments")
    if isinstance(assignments, list):
        for assignment in assignments:
            if not isinstance(assignment, dict):
                continue
            for key in ("epa_v", "epc_v"):
                assignment[key] = _scaled(assignment.get(key), factors["potential"])
            for key in ("ipa_a", "ipc_a"):
                assignment[key] = _scaled(assignment.get(key), factors["current"])
    return normalized, conversions


def _require_request_envelope(request: object) -> Mapping[str, Any]:
    if not isinstance(request, Mapping):
        _refuse(request, "SCHEMA_INVALID", "Request must be a JSON object.", invalid=["request"])
    if request.get("schema_version") != SCHEMA_VERSION:
        _refuse(
            request,
            "SCHEMA_INVALID",
            f"schema_version must be {SCHEMA_VERSION}.",
            invalid=["schema_version"],
        )
    if not _nonempty(request.get("request_id")):
        _refuse(
            request,
            "SCHEMA_INVALID",
            "A non-empty request_id is required.",
            missing=["request_id"],
        )
    return request


def _validate_cv_request(request: Mapping[str, Any]) -> tuple[
    Mapping[str, Any],
    Mapping[str, Any],
    list[Mapping[str, Any]],
    list[Mapping[str, Any]],
    list[str],
]:
    missing = [key for key in ("source", "sample", "condition", "traces", "peak_assignments", "requested") if key not in request]
    if missing:
        _refuse(request, "METADATA_MISSING", "Required CV request fields are missing.", missing=missing)

    source = _mapping(request.get("source"))
    sample = _mapping(request.get("sample"))
    condition = _mapping(request.get("condition"))
    traces_value = request.get("traces")
    assignments_value = request.get("peak_assignments")
    requested_value = request.get("requested")
    if source is None or sample is None or condition is None:
        _refuse(request, "SCHEMA_INVALID", "Source, sample, and condition must be objects.", invalid=["source/sample/condition"])
    if not isinstance(traces_value, list) or not isinstance(assignments_value, list) or not isinstance(requested_value, list):
        _refuse(request, "SCHEMA_INVALID", "Traces, peak assignments, and requested must be arrays.", invalid=["traces/peak_assignments/requested"])
    traces = traces_value
    assignments = assignments_value
    requested = requested_value
    if not traces or not assignments:
        _refuse(request, "PEAKS_INVALID", "At least one trace and reviewed peak assignment are required.", missing=["traces/peak_assignments"])
    if not requested or any(item not in _ALLOWED_REQUESTS for item in requested) or len(set(requested)) != len(requested):
        _refuse(request, "SCHEMA_INVALID", "Requested calculations are empty, duplicated, or unsupported.", invalid=["requested"])

    source_missing = [key for key in ("provenance", "source_id", "checksum") if not _nonempty(source.get(key))]
    if source_missing:
        _refuse(request, "METADATA_MISSING", "Source identity is incomplete.", missing=[f"source.{key}" for key in source_missing])
    if source.get("provenance") not in _ALLOWED_PROVENANCE:
        _refuse(request, "SCHEMA_INVALID", "Published scalar records cannot be submitted as CV traces.", invalid=["source.provenance"])

    sample_missing = [key for key in ("sample_id", "preferred_name", "molecular_form") if not _nonempty(sample.get(key))]
    if not _finite_number(sample.get("concentration_mol_cm3"), positive=True):
        sample_missing.append("concentration_mol_cm3")
    if sample_missing:
        _refuse(request, "METADATA_MISSING", "Sample metadata are incomplete or nonpositive.", missing=[f"sample.{key}" for key in sample_missing])

    required_condition = (
        "condition_id",
        "solvent",
        "supporting_electrolyte",
        "ph",
        "temperature_k",
        "working_electrode",
        "counter_electrode",
        "reference_electrode",
        "potential_scale",
        "electron_count",
        "atmosphere",
        "preprocessing_description",
        "units",
    )
    condition_missing = [key for key in required_condition if key not in condition]
    for key in ("condition_id", "solvent", "counter_electrode", "reference_electrode", "potential_scale", "atmosphere", "preprocessing_description"):
        if key in condition and not _nonempty(condition.get(key)):
            condition_missing.append(key)
    electrolyte = _mapping(condition.get("supporting_electrolyte"))
    ph = _mapping(condition.get("ph"))
    electrode = _mapping(condition.get("working_electrode"))
    if electrolyte is None or not _nonempty(electrolyte.get("name")) or not _finite_number(electrolyte.get("concentration_mol_l"), positive=True):
        condition_missing.append("supporting_electrolyte")
    if ph is None or ph.get("status") not in {"measured", "not_measured"} or (ph.get("status") == "measured" and not _finite_number(ph.get("value"))):
        condition_missing.append("ph")
    if ph is not None and ph.get("status") == "not_measured" and ph.get("value") is not None:
        condition_missing.append("ph.value")
    if electrode is None or not _nonempty(electrode.get("material")) or not _finite_number(electrode.get("area_cm2"), positive=True):
        condition_missing.append("working_electrode")
    if not _finite_number(condition.get("temperature_k"), positive=True):
        condition_missing.append("temperature_k")
    if not _finite_number(condition.get("electron_count"), positive=True):
        condition_missing.append("electron_count")
    if condition_missing:
        _refuse(request, "METADATA_MISSING", "CV condition metadata are incomplete or invalid.", missing=[f"condition.{key}" for key in sorted(set(condition_missing))])

    units = _mapping(condition.get("units"))
    if units is None:
        _refuse(request, "UNIT_MISSING", "Canonical scientific units are required.", missing=["condition.units"])
    missing_units = [key for key in _CANONICAL_UNITS if key not in units]
    invalid_units = [f"condition.units.{key}" for key, expected in _CANONICAL_UNITS.items() if key in units and units.get(key) != expected]
    if missing_units or invalid_units:
        _refuse(
            request,
            "UNIT_MISSING",
            "v1 accepts only the declared canonical units.",
            missing=[f"condition.units.{key}" for key in missing_units],
            invalid=invalid_units,
        )

    trace_ids: set[str] = set()
    trace_map: dict[str, Mapping[str, Any]] = {}
    invalid_traces: list[str] = []
    incompatible_traces: list[str] = []
    for raw_trace in traces:
        trace = _mapping(raw_trace)
        if trace is None:
            invalid_traces.append("<non-object>")
            continue
        trace_id = trace.get("trace_id")
        potential = trace.get("potential_v")
        current = trace.get("current_a")
        valid_arrays = (
            isinstance(potential, list)
            and isinstance(current, list)
            and len(potential) == len(current)
            and len(potential) >= 20
            and all(_finite_number(item) for item in potential)
            and all(_finite_number(item) for item in current)
        )
        valid = (
            _nonempty(trace_id)
            and trace_id not in trace_ids
            and _finite_number(trace.get("scan_rate_v_s"), positive=True)
            and _nonempty(trace.get("replicate_id"))
            and isinstance(trace.get("cycle_number"), int)
            and not isinstance(trace.get("cycle_number"), bool)
            and trace.get("cycle_number") >= 0
            and trace.get("transformation") == "raw"
            and valid_arrays
        )
        if not valid:
            invalid_traces.append(str(trace_id or "<missing>"))
            continue
        if trace.get("potential_scale") != condition.get("potential_scale"):
            incompatible_traces.append(str(trace_id))
            continue
        trace_ids.add(trace_id)
        trace_map[trace_id] = trace
    if invalid_traces:
        _refuse(request, "SCHEMA_INVALID", "One or more raw CV traces are invalid.", invalid=["traces"], excluded=invalid_traces)
    if incompatible_traces:
        _refuse(request, "INCOMPATIBLE_CONDITIONS", "Trace and condition potential scales must match; v1 does not convert reference scales.", invalid=["traces.potential_scale"], excluded=incompatible_traces)

    assignment_map: dict[str, Mapping[str, Any]] = {}
    invalid_assignments: list[str] = []
    for raw_assignment in assignments:
        assignment = _mapping(raw_assignment)
        trace_id = assignment.get("trace_id") if assignment else None
        trace = trace_map.get(str(trace_id))
        potential = trace.get("potential_v", []) if trace else []
        inside_window = (
            bool(potential)
            and _finite_number(assignment.get("epa_v") if assignment else None)
            and _finite_number(assignment.get("epc_v") if assignment else None)
            and min(potential) <= float(assignment["epc_v"]) <= max(potential)
            and min(potential) <= float(assignment["epa_v"]) <= max(potential)
        )
        valid = (
            assignment is not None
            and trace_id in trace_map
            and trace_id not in assignment_map
            and assignment.get("assignment_source") in {"manual", "imported"}
            and assignment.get("reviewed") is True
            and all(_finite_number(assignment.get(key)) for key in ("epa_v", "epc_v", "ipa_a", "ipc_a"))
            and float(assignment.get("epa_v", 0)) >= float(assignment.get("epc_v", 0))
            and float(assignment.get("ipa_a", 0)) > 0
            and float(assignment.get("ipc_a", 0)) < 0
            and inside_window
        )
        if not valid:
            invalid_assignments.append(str(trace_id or "<missing>"))
            continue
        assignment_map[trace_id] = assignment
    if invalid_assignments:
        _refuse(request, "PEAKS_INVALID", "Peak assignments must be unique, reviewed, paired, and use anodic-positive/cathodic-negative currents.", invalid=["peak_assignments"], excluded=invalid_assignments)

    return condition, sample, list(trace_map.values()), list(assignment_map.values()), requested


def _descriptor_stats(values: Sequence[float]) -> dict[str, object]:
    count = len(values)
    mean = math.fsum(values) / count
    if count < 2:
        dispersion: float | str = "unavailable"
    else:
        dispersion = math.sqrt(math.fsum((value - mean) ** 2 for value in values) / (count - 1))
    return {"mean": mean, "sample_standard_deviation": dispersion, "count": count}


def _peak_result(assignments: Sequence[Mapping[str, Any]]) -> dict[str, object]:
    per_trace: list[dict[str, object]] = []
    for assignment in assignments:
        epa = float(assignment["epa_v"])
        epc = float(assignment["epc_v"])
        ipa = float(assignment["ipa_a"])
        ipc = float(assignment["ipc_a"])
        per_trace.append(
            {
                "trace_id": assignment["trace_id"],
                "e_half_v": (epa + epc) / 2.0,
                "delta_ep_v": epa - epc,
                "peak_current_ratio": abs(ipa / ipc),
            }
        )
    aggregate = {
        key: _descriptor_stats([float(item[key]) for item in per_trace])
        for key in ("e_half_v", "delta_ep_v", "peak_current_ratio")
    }
    return {
        "status": "estimate_available",
        "per_trace": per_trace,
        "aggregate": aggregate,
        "reversibility_evidence": {
            "status": "partial_evidence" if len(per_trace) > 1 else "inconclusive",
            "summary": "PARTIAL EVIDENCE" if len(per_trace) > 1 else "INCONCLUSIVE",
            "descriptors": ["delta_ep_v", "peak_current_ratio", "peak_position_change_with_scan_rate"],
            "classification": None,
            "limitation": "Descriptors do not establish a categorical reversibility class.",
        },
    }


def _ols(x: Sequence[float], y: Sequence[float]) -> dict[str, object]:
    count = len(x)
    x_mean = math.fsum(x) / count
    y_mean = math.fsum(y) / count
    sxx = math.fsum((value - x_mean) ** 2 for value in x)
    if sxx <= 0:
        raise ValueError("scan rates do not span a fit")
    slope = math.fsum((xv - x_mean) * (yv - y_mean) for xv, yv in zip(x, y, strict=True)) / sxx
    intercept = y_mean - slope * x_mean
    residuals = [yv - (intercept + slope * xv) for xv, yv in zip(x, y, strict=True)]
    sse = math.fsum(value * value for value in residuals)
    sst = math.fsum((value - y_mean) ** 2 for value in y)
    r_squared = 1.0 if sst == 0 and sse == 0 else (1.0 - sse / sst if sst > 0 else 0.0)
    slope_se = math.sqrt((sse / (count - 2)) / sxx) if count > 2 else math.inf
    return {
        "slope": slope,
        "intercept": intercept,
        "residuals": residuals,
        "r_squared": r_squared,
        "slope_standard_error": slope_se,
    }


def _diffusion_result(
    request: Mapping[str, Any],
    condition: Mapping[str, Any],
    sample: Mapping[str, Any],
    traces: Sequence[Mapping[str, Any]],
    assignments: Sequence[Mapping[str, Any]],
) -> dict[str, object]:
    temperature = float(condition["temperature_k"])
    if abs(temperature - 298.15) > 0.50:
        _refuse(request, "METADATA_MISSING", "The frozen Randles–Sevcik model requires 298.15 ± 0.50 K.", invalid=["condition.temperature_k"])
    trace_map = {str(trace["trace_id"]): trace for trace in traces}
    distinct_rates = {float(trace_map[str(item["trace_id"])]["scan_rate_v_s"]) for item in assignments}
    if len(distinct_rates) < 3:
        _refuse(request, "INSUFFICIENT_RATES", "At least three distinct reviewed scan rates are required for diffusion estimation.", invalid=["traces.scan_rate_v_s"])

    ordered = sorted(assignments, key=lambda item: float(trace_map[str(item["trace_id"])]["scan_rate_v_s"]))
    included_ids = [str(item["trace_id"]) for item in ordered]
    excluded_ids = [str(trace["trace_id"]) for trace in traces if str(trace["trace_id"]) not in included_ids]
    x = [math.sqrt(float(trace_map[str(item["trace_id"])]["scan_rate_v_s"])) for item in ordered]
    denominator = 2.69e5 * float(condition["electron_count"]) ** 1.5 * float(condition["working_electrode"]["area_cm2"]) * float(sample["concentration_mol_cm3"])
    branches: dict[str, object] = {}
    failed: list[str] = []
    for branch, current_key in (("anodic", "ipa_a"), ("cathodic", "ipc_a")):
        y = [abs(float(item[current_key])) for item in ordered]
        try:
            fit = _ols(x, y)
        except ValueError:
            failed.append(branch)
            continue
        slope = float(fit["slope"])
        r_squared = float(fit["r_squared"])
        if slope <= 0 or not math.isfinite(r_squared) or r_squared < 0.98:
            failed.append(branch)
            continue
        slope_se = float(fit["slope_standard_error"])
        t_value = _T_CRITICAL_95.get(len(x) - 2, 1.959963985)
        lower_slope = max(0.0, slope - t_value * slope_se)
        upper_slope = max(0.0, slope + t_value * slope_se)
        diffusion = (slope / denominator) ** 2
        ci = [(lower_slope / denominator) ** 2, (upper_slope / denominator) ** 2]
        flags = ["BOUNDARY_SENSITIVE"] if slope - t_value * slope_se < 0 else []
        branches[branch] = {
            "status": "estimate_available",
            "branch": branch,
            "diffusion_coefficient_cm2_s": diffusion,
            "ci95_cm2_s": ci,
            "slope_a_per_sqrt_v_s": slope,
            "slope_standard_error": slope_se,
            "intercept_a": fit["intercept"],
            "r_squared": r_squared,
            "residuals_a": fit["residuals"],
            "included_trace_ids": included_ids,
            "excluded_trace_ids": excluded_ids,
            "qc_gate": {"name": "r_squared", "threshold": 0.98, "passed": True},
            "flags": flags,
        }
    if failed:
        _refuse(request, "FIT_QC_FAILED", "One or more diffusion branches failed the positive-slope or R² ≥ 0.98 software QC gate.", invalid=[f"diffusion.branches.{name}" for name in failed])
    return {
        "status": "estimate_available",
        "model": "Randles-Sevcik 298.15 K; OLS with intercept; separate anodic/cathodic branches",
        "branches": branches,
    }


def _ir_result(
    request: Mapping[str, Any],
    sample: Mapping[str, Any],
    condition: Mapping[str, Any],
    traces: Sequence[Mapping[str, Any]],
) -> dict[str, object]:
    correction = _mapping(request.get("ir_correction"))
    if correction is None:
        _refuse(request, "RESISTANCE_INELIGIBLE", "An independent iR correction record is required.", missing=["ir_correction"])
    required = ("ru_ohm", "fraction", "resistance_source", "measurement_method", "measurement_context")
    missing = [key for key in required if key not in correction or correction.get(key) in (None, "")]
    if missing:
        _refuse(request, "RESISTANCE_INELIGIBLE", "The independent resistance record is incomplete.", missing=[f"ir_correction.{key}" for key in missing])
    ru = correction.get("ru_ohm")
    fraction = correction.get("fraction")
    if (
        not _finite_number(ru, positive=True)
        or not _finite_number(fraction, nonnegative=True)
        or float(fraction) > 1
    ):
        _refuse(request, "RESISTANCE_INELIGIBLE", "Ru must be a positive independent measurement with matching provenance and a correction fraction from 0 to 1.", invalid=["ir_correction"])

    source = _mapping(correction.get("resistance_source"))
    context = _mapping(correction.get("measurement_context"))
    resistance_context = _mapping(context.get("resistance")) if context else None
    cv_context = _mapping(context.get("cv")) if context else None
    context_fields = ("sample_id", "cell_id", "geometry_id", "electrolyte_id", "condition_id")
    source_eligible = (
        source is not None
        and source.get("provenance") == "independent_resistance_measurement"
        and _valid_identifier(source.get("operation_id"))
    )
    operation_matches = (
        source is not None
        and resistance_context is not None
        and resistance_context.get("operation_id") == source.get("operation_id")
    )
    context_eligible = (
        context is not None
        and context.get("reviewed") is True
        and resistance_context is not None
        and cv_context is not None
        and _matching_records(resistance_context, cv_context, context_fields)
        and operation_matches
    )
    request_match = (
        cv_context is not None
        and cv_context.get("sample_id") == sample.get("sample_id")
        and cv_context.get("condition_id") == condition.get("condition_id")
    )
    if correction.get("measurement_method") not in _IR_METHODS or not source_eligible or not context_eligible or not request_match:
        _refuse(
            request,
            "RESISTANCE_INELIGIBLE",
            "iR correction requires an allowed independent method and reviewed matching sample, cell, geometry, electrolyte, and condition records.",
            invalid=["ir_correction.resistance_source/measurement_method/measurement_context"],
        )

    output_traces: list[dict[str, object]] = []
    for trace in traces:
        raw = [float(value) for value in trace["potential_v"]]
        current = [float(value) for value in trace["current_a"]]
        corrected = [potential - float(fraction) * ampere * float(ru) for potential, ampere in zip(raw, current, strict=True)]
        raw_payload = {"potential_v": raw, "current_a": current}
        output_traces.append(
            {
                "trace_id": trace["trace_id"],
                "raw_potential_v": raw,
                "current_a": current,
                "corrected_potential_v": corrected,
                "raw_hash": _sha256(raw_payload),
                "corrected_hash": _sha256({"potential_v": corrected, "current_a": current}),
            }
        )
    return {
        "status": "estimate_available",
        "ru_ohm": float(ru),
        "fraction": float(fraction),
        "resistance_source": copy.deepcopy(dict(source)),
        "measurement_method": correction["measurement_method"],
        "measurement_context": copy.deepcopy(dict(context)),
        "traces": output_traces,
        "limitation": "Pointwise preview only; raw arrays are retained and dynamic distortion may remain.",
    }


def _success(
    request: Mapping[str, Any],
    results: Mapping[str, object],
    formulas: Sequence[str],
    *,
    transport_input_hash: str | None = None,
    unit_conversions: Sequence[Mapping[str, object]] = (),
) -> dict[str, object]:
    request_copy = copy.deepcopy(dict(request))
    input_hash = transport_input_hash or _sha256(request_copy)
    if len(input_hash) != 64 or any(character not in "0123456789abcdef" for character in input_hash):
        raise ValueError("transport_input_hash must be a lowercase SHA-256 hex digest")
    excluded_trace_ids: list[str] = []
    diffusion = _mapping(results.get("diffusion"))
    branches = _mapping(diffusion.get("branches")) if diffusion else None
    if branches:
        for branch_name in ("anodic", "cathodic"):
            branch = _mapping(branches.get(branch_name))
            if not branch or not isinstance(branch.get("excluded_trace_ids"), list):
                continue
            for trace_id in branch["excluded_trace_ids"]:
                if isinstance(trace_id, str) and trace_id not in excluded_trace_ids:
                    excluded_trace_ids.append(trace_id)

    return {
        "schema_version": SCHEMA_VERSION,
        "request_id": request["request_id"],
        "status": "estimate_available",
        "provenance": "derived",
        "method_version": METHOD_VERSION,
        "input_hash": input_hash,
        "results": dict(results),
        "warnings": [],
        "limitations": [
            "Derived values remain bound to the supplied sample, condition, units, and reviewed assignments.",
            "R² is a software quality gate and does not prove diffusion control or electrochemical reversibility.",
        ],
        "audit": {
            "audit_id": _audit_id({"request": request_copy, "method_version": METHOD_VERSION}),
            "exact_input": request_copy,
            "canonical_units": copy.deepcopy(_CANONICAL_UNITS),
            "unit_conversions": copy.deepcopy(list(unit_conversions)),
            "formulas": list(formulas),
            "excluded_trace_ids": excluded_trace_ids,
            "input_hash": input_hash,
        },
    }


def analyze_cv_request(
    request: object,
    *,
    transport_input_hash: str | None = None,
) -> dict[str, object]:
    """Validate one frozen-contract CV request and return only supported derived evidence."""

    original = _require_request_envelope(request)
    normalized, unit_conversions = _normalize_cv_units(original)
    condition, sample, traces, assignments, requested = _validate_cv_request(normalized)
    results: dict[str, object] = {}
    formulas: list[str] = []
    if "peak_descriptors" in requested:
        results["peak_descriptors"] = _peak_result(assignments)
        formulas.extend(["E1/2=(Epa+Epc)/2", "delta_Ep=Epa-Epc", "ratio=abs(ipa/ipc)"])
    if "diffusion" in requested:
        results["diffusion"] = _diffusion_result(normalized, condition, sample, traces, assignments)
        formulas.append("ip=2.69e5*n^(3/2)*A*C*sqrt(D)*sqrt(v)")
    if "ir_correction" in requested:
        results["ir_correction"] = _ir_result(normalized, sample, condition, traces)
        formulas.append("Ecorrected=Emeasured-fraction*I*Ru")
    return _success(
        original,
        results,
        formulas,
        transport_input_hash=transport_input_hash,
        unit_conversions=unit_conversions,
    )


def calculate_conductivity(
    request: object,
    *,
    transport_input_hash: str | None = None,
) -> dict[str, object]:
    """Calculate conductivity only from an eligible independent same-cell measurement."""

    validated = _require_request_envelope(request)
    required = ("resistance_ohm", "cell_constant_m_inv", "calibration_source", "measurement_context", "temperature_k")
    missing = [key for key in required if key not in validated]
    if missing:
        _refuse(validated, "METADATA_MISSING", "Conductivity measurement metadata are incomplete.", missing=missing)
    if not _finite_number(validated.get("resistance_ohm"), positive=True):
        _refuse(validated, "RESISTANCE_INELIGIBLE", "Resistance must be a positive independent conductivity-cell measurement.", invalid=["resistance_ohm"])
    if not _finite_number(validated.get("cell_constant_m_inv"), positive=True):
        _refuse(validated, "CELL_CONSTANT_INELIGIBLE", "A positive calibrated cell constant is required.", invalid=["cell_constant_m_inv"])
    if not _finite_number(validated.get("temperature_k"), positive=True):
        _refuse(validated, "METADATA_MISSING", "A positive measurement temperature is required.", invalid=["temperature_k"])
    calibration = _mapping(validated.get("calibration_source"))
    context = _mapping(validated.get("measurement_context"))
    resistance_record = _mapping(context.get("resistance")) if context else None
    measurement_record = _mapping(context.get("measurement")) if context else None
    calibration_eligible = (
        calibration is not None
        and calibration.get("reviewed") is True
        and calibration.get("method") in _CALIBRATION_METHODS
        and all(
            _valid_identifier(calibration.get(field))
            for field in ("calibration_id", "cell_id", "geometry_id")
        )
    )
    if not calibration_eligible:
        _refuse(
            validated,
            "CELL_CONSTANT_INELIGIBLE",
            "Cell constant requires a reviewed calibration record with an allowed method and auditable calibration, cell, and geometry identifiers.",
            invalid=["calibration_source"],
        )
    context_eligible = (
        context is not None
        and context.get("reviewed") is True
        and resistance_record is not None
        and measurement_record is not None
        and resistance_record.get("independent") is True
        and resistance_record.get("resistance_kind") == "conductivity_cell"
        and _valid_identifier(resistance_record.get("operation_id"))
        and _matching_records(
            resistance_record,
            measurement_record,
            ("sample_id", "cell_id", "geometry_id", "condition_id"),
        )
        and calibration.get("calibration_id") == context.get("calibration_id")
        and calibration.get("cell_id") == measurement_record.get("cell_id")
        and calibration.get("geometry_id") == measurement_record.get("geometry_id")
    )
    if not context_eligible:
        _refuse(
            validated,
            "RESISTANCE_INELIGIBLE",
            "Conductivity requires reviewed resistance and measurement records with identical sample, cell, geometry, and condition IDs, linked to the applicable calibration.",
            invalid=["measurement_context"],
        )

    resistance = float(validated["resistance_ohm"])
    cell_constant = float(validated["cell_constant_m_inv"])
    result = {
        "status": "estimate_available",
        "conductivity_s_m": cell_constant / resistance,
        "unit": "S/m",
        "resistance_ohm": resistance,
        "cell_constant_m_inv": cell_constant,
    }
    return _success(
        validated,
        {"conductivity": result},
        ["conductivity=cell_constant/resistance"],
        transport_input_hash=transport_input_hash,
    )
