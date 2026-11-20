"""Fail-closed validation for public RFB V1 protocol requests.

This module consumes only the public RFB contracts.  It deliberately has no
dependency on scenario-loader internals, an oracle, or rfbzero.
"""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from enum import StrEnum
from numbers import Real
from typing import Any

from . import contracts
from .contracts import (
    CANONICAL_ACTION_FIELDS,
    V1_FIXED_ACTION_FIELDS,
    RFBActionSchemaV1,
    RFBActionV1,
    RFBScenarioV1,
)


_VALID_SOURCES = frozenset({"policy", "human_edit"})
# RFBActionRequestV1 is the currently exported bridge name.  Prefer the
# canonical RFBRequestV1 name as soon as the contracts module exports it.
RFBRequestV1 = getattr(contracts, "RFBRequestV1", getattr(contracts, "RFBActionRequestV1", None))


class RfbValidationClassification(StrEnum):
    """High-level outcome suitable for workflow decisions."""

    VALID_CANDIDATE = "valid_candidate"
    VALID_HUMAN_EDIT_CANDIDATE = "valid_human_edit_candidate"
    MALFORMED_REQUEST = "malformed_request"
    NONMEMBER_REQUEST = "nonmember_request"


class RfbValidationCode(StrEnum):
    """Stable, machine-readable protocol-validation codes."""

    VALID_CANDIDATE = "VALID_CANDIDATE"
    VALID_HUMAN_EDIT_CANDIDATE = "VALID_HUMAN_EDIT_CANDIDATE"
    INVALID_SCENARIO = "INVALID_SCENARIO"
    INVALID_REQUEST = "INVALID_REQUEST"
    INVALID_ACTION = "INVALID_ACTION"
    INVALID_ACTION_ID = "INVALID_ACTION_ID"
    INVALID_RATIONALE = "INVALID_RATIONALE"
    INVALID_SOURCE = "INVALID_SOURCE"
    INVALID_CONTROLS = "INVALID_CONTROLS"
    MISSING_CONTROL = "MISSING_CONTROL"
    EXTRA_CONTROL = "EXTRA_CONTROL"
    NONFINITE_CONTROL = "NONFINITE_CONTROL"
    CONTROL_OUT_OF_RANGE = "CONTROL_OUT_OF_RANGE"
    FIXED_CONTROL_MISMATCH = "FIXED_CONTROL_MISMATCH"
    CHARGE_CURRENT_NOT_POSITIVE = "CHARGE_CURRENT_NOT_POSITIVE"
    DISCHARGE_CURRENT_NOT_NEGATIVE = "DISCHARGE_CURRENT_NOT_NEGATIVE"
    DURATION_NOT_POSITIVE = "DURATION_NOT_POSITIVE"
    DURATION_NOT_WHOLE_SECONDS = "DURATION_NOT_WHOLE_SECONDS"
    INVALID_VOLTAGE_ORDERING = "INVALID_VOLTAGE_ORDERING"
    CANDIDATE_NOT_FOUND = "CANDIDATE_NOT_FOUND"


@dataclass(frozen=True)
class RfbValidationResult:
    """The deterministic validation decision for one submitted action."""

    accepted: bool
    classification: RfbValidationClassification
    codes: tuple[RfbValidationCode, ...]
    candidate_action_id: str | None = None


class RfbProtocolValidator:
    """Validate public RFB request and scenario contracts without an oracle."""

    def validate(self, request: Any, scenario: Any) -> RfbValidationResult:
        return validate_rfb_action(request, scenario)


def validate_rfb_action(request: Any, scenario: Any) -> RfbValidationResult:
    """Accept only a well-formed request for a declared public candidate.

    RFBActionV1 construction normally prevents malformed controls.  The
    explicit checks below still make the boundary fail closed if a caller
    supplies an object whose invariants were bypassed before validation.
    """

    scenario_data = _public_scenario_data(scenario)
    if scenario_data is None:
        return _rejected(RfbValidationCode.INVALID_SCENARIO)

    ranges, fixed_values, ocv_50_soc_V, candidates = scenario_data
    codes: list[RfbValidationCode] = []
    _validate_request_metadata(request, codes)

    action = getattr(request, "action", None)
    controls = _action_controls(action, codes)
    if controls is not None:
        _validate_ranges(controls, ranges, codes)
        _validate_fixed_fields(controls, fixed_values, codes)
        _validate_protocol_constraints(controls, ocv_50_soc_V, codes)

    if codes:
        return RfbValidationResult(
            accepted=False,
            classification=RfbValidationClassification.MALFORMED_REQUEST,
            codes=tuple(codes),
        )

    assert isinstance(action, RFBActionV1)
    candidate = next((candidate for candidate in candidates if action == candidate), None)
    if candidate is None:
        return RfbValidationResult(
            accepted=False,
            classification=RfbValidationClassification.NONMEMBER_REQUEST,
            codes=(RfbValidationCode.CANDIDATE_NOT_FOUND,),
        )

    if request.source == "human_edit":
        return RfbValidationResult(
            accepted=True,
            classification=RfbValidationClassification.VALID_HUMAN_EDIT_CANDIDATE,
            codes=(RfbValidationCode.VALID_HUMAN_EDIT_CANDIDATE,),
            candidate_action_id=candidate.identity_sha256,
        )
    return RfbValidationResult(
        accepted=True,
        classification=RfbValidationClassification.VALID_CANDIDATE,
        codes=(RfbValidationCode.VALID_CANDIDATE,),
        candidate_action_id=candidate.identity_sha256,
    )


def _public_scenario_data(
    scenario: Any,
) -> tuple[dict[str, tuple[float, float]], dict[str, float], float, tuple[RFBActionV1, ...]] | None:
    """Extract and validate the scenario data intentionally published to planners."""

    if not isinstance(scenario, RFBScenarioV1):
        return None
    candidates = getattr(scenario, "candidate_actions", None)
    if not isinstance(candidates, Sequence) or isinstance(candidates, (str, bytes)):
        return None
    candidates = tuple(candidates)
    if not candidates or not all(isinstance(candidate, RFBActionV1) for candidate in candidates):
        return None

    action_schema = getattr(scenario, "action_schema", None)
    fixed_values = getattr(scenario, "fixed_fields", None)
    ocv_50_soc_V = _as_finite_float(getattr(scenario, "ocv_50_soc_V", None))
    if not isinstance(action_schema, RFBActionSchemaV1):
        return None
    ranges = _public_ranges(action_schema)
    if ranges is None or not isinstance(fixed_values, Mapping) or ocv_50_soc_V is None:
        return None
    if set(fixed_values) != set(V1_FIXED_ACTION_FIELDS):
        return None
    normalized_fixed_values = {
        name: _as_finite_float(fixed_values[name]) for name in V1_FIXED_ACTION_FIELDS
    }
    if any(value is None for value in normalized_fixed_values.values()):
        return None

    for candidate in candidates:
        candidate_codes: list[RfbValidationCode] = []
        controls = _action_controls(candidate, candidate_codes)
        if controls is None:
            return None
        _validate_ranges(controls, ranges, candidate_codes)
        _validate_fixed_fields(controls, normalized_fixed_values, candidate_codes)
        _validate_protocol_constraints(controls, ocv_50_soc_V, candidate_codes)
        if candidate_codes:
            return None

    return ranges, normalized_fixed_values, ocv_50_soc_V, candidates


def _public_ranges(action_schema: RFBActionSchemaV1) -> dict[str, tuple[float, float]] | None:
    """Validate the canonical range map published by the public scenario."""

    raw_ranges = action_schema.ranges
    if not isinstance(raw_ranges, Mapping) or set(raw_ranges) != set(CANONICAL_ACTION_FIELDS):
        return None
    ranges: dict[str, tuple[float, float]] = {}
    for name in CANONICAL_ACTION_FIELDS:
        bounds = raw_ranges[name]
        if not isinstance(bounds, Sequence) or isinstance(bounds, (str, bytes)) or len(bounds) != 2:
            return None
        low, high = (_as_finite_float(value) for value in bounds)
        if low is None or high is None or low > high:
            return None
        ranges[name] = (low, high)
    return ranges


def _validate_request_metadata(request: Any, codes: list[RfbValidationCode]) -> None:
    if not isinstance(RFBRequestV1, type) or not isinstance(request, RFBRequestV1):
        _add(codes, RfbValidationCode.INVALID_REQUEST)
        return
    if not isinstance(getattr(request, "request_id", None), str) or not request.request_id.strip():
        _add(codes, RfbValidationCode.INVALID_ACTION_ID)
    if not isinstance(getattr(request, "rationale", None), str) or not request.rationale.strip():
        _add(codes, RfbValidationCode.INVALID_RATIONALE)
    if getattr(request, "source", None) not in _VALID_SOURCES:
        _add(codes, RfbValidationCode.INVALID_SOURCE)


def _action_controls(action: Any, codes: list[RfbValidationCode]) -> dict[str, float] | None:
    if not isinstance(action, RFBActionV1):
        _add(codes, RfbValidationCode.INVALID_ACTION)
        return None
    controls: dict[str, float] = {}
    for name in CANONICAL_ACTION_FIELDS:
        try:
            value = getattr(action, name)
        except AttributeError:
            _add(codes, RfbValidationCode.MISSING_CONTROL)
            continue
        numeric_value = _as_finite_float(value)
        if numeric_value is None:
            _add(codes, RfbValidationCode.NONFINITE_CONTROL)
        else:
            controls[name] = numeric_value
    return controls if len(controls) == len(CANONICAL_ACTION_FIELDS) else None


def _validate_ranges(
    controls: Mapping[str, float], ranges: Mapping[str, tuple[float, float]], codes: list[RfbValidationCode]
) -> None:
    for name in CANONICAL_ACTION_FIELDS:
        low, high = ranges[name]
        if controls[name] < low or controls[name] > high:
            _add(codes, RfbValidationCode.CONTROL_OUT_OF_RANGE)


def _validate_fixed_fields(
    controls: Mapping[str, float], fixed_values: Mapping[str, float], codes: list[RfbValidationCode]
) -> None:
    for name in V1_FIXED_ACTION_FIELDS:
        if controls[name] != fixed_values[name]:
            _add(codes, RfbValidationCode.FIXED_CONTROL_MISMATCH)


def _validate_protocol_constraints(
    controls: Mapping[str, float], ocv_50_soc_V: float, codes: list[RfbValidationCode]
) -> None:
    if controls["charge_current_A"] <= 0.0:
        _add(codes, RfbValidationCode.CHARGE_CURRENT_NOT_POSITIVE)
    if controls["discharge_current_A"] >= 0.0:
        _add(codes, RfbValidationCode.DISCHARGE_CURRENT_NOT_NEGATIVE)
    if controls["protocol_duration_s"] <= 0.0:
        _add(codes, RfbValidationCode.DURATION_NOT_POSITIVE)
    elif not controls["protocol_duration_s"].is_integer():
        _add(codes, RfbValidationCode.DURATION_NOT_WHOLE_SECONDS)
    if not (
        controls["discharge_voltage_limit_V"]
        < ocv_50_soc_V
        < controls["charge_voltage_limit_V"]
    ):
        _add(codes, RfbValidationCode.INVALID_VOLTAGE_ORDERING)


def _as_finite_float(value: Any) -> float | None:
    if isinstance(value, bool) or not isinstance(value, Real):
        return None
    numeric_value = float(value)
    return numeric_value if math.isfinite(numeric_value) else None


def _add(codes: list[RfbValidationCode], code: RfbValidationCode) -> None:
    if code not in codes:
        codes.append(code)


def _rejected(code: RfbValidationCode) -> RfbValidationResult:
    return RfbValidationResult(
        accepted=False,
        classification=RfbValidationClassification.MALFORMED_REQUEST,
        codes=(code,),
    )
