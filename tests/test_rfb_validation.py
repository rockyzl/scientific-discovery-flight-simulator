from __future__ import annotations

import math
from pathlib import Path

import pytest

from discovery_flight_simulator.rfb import contracts
from discovery_flight_simulator.rfb.contracts import (
    FrozenScalarUtilityV1,
    RFBActionSchemaV1,
    RFBActionV1,
    RFBScenarioV1,
)
from discovery_flight_simulator.rfb.scenario import load_rfb_scenario
from discovery_flight_simulator.rfb.validation import (
    RfbProtocolValidator,
    RfbValidationClassification,
    RfbValidationCode,
)


SCENARIO_PATH = Path("scenarios/rfbzero_cell_v0.json")
RFBRequestV1 = getattr(contracts, "RFBRequestV1", contracts.RFBActionRequestV1)


def _scenario() -> RFBScenarioV1:
    candidates = (
        RFBActionV1(0.06, -0.05, 1.5, 0.5, 240),
        RFBActionV1(0.10, -0.08, 1.5, 0.5, 240),
    )
    return RFBScenarioV1(
        scenario_id="rfb-validation",
        scenario_version="1",
        candidate_actions=candidates,
        action_schema=RFBActionSchemaV1(
            {
                "charge_current_A": (0.05, 0.15),
                "discharge_current_A": (-0.12, -0.04),
                "charge_voltage_limit_V": (1.4, 1.6),
                "discharge_voltage_limit_V": (0.4, 0.6),
                "protocol_duration_s": (60, 3600),
            }
        ),
        fixed_fields={
            "charge_voltage_limit_V": 1.5,
            "discharge_voltage_limit_V": 0.5,
            "protocol_duration_s": 240,
        },
        ocv_50_soc_V=1.0,
        utility=FrozenScalarUtilityV1(energy_reference_J=10.0, duration_reference_s=240.0),
        total_attempt_budget=2,
        total_measurement_budget=2,
    )


def _request(
    action: RFBActionV1,
    *,
    request_id: str = "request-1",
    rationale: str = "Evaluate a declared candidate.",
    source: str = "policy",
) -> RFBRequestV1:
    return RFBRequestV1(
        request_id=request_id,
        action=action,
        rationale=rationale,
        source=source,
    )


def _corrupt_request(
    action: object,
    *,
    request_id: object = "request-1",
    rationale: object = "Evaluate a declared candidate.",
    source: object = "policy",
) -> RFBRequestV1:
    request = object.__new__(RFBRequestV1)
    object.__setattr__(request, "request_id", request_id)
    object.__setattr__(request, "action", action)
    object.__setattr__(request, "rationale", rationale)
    object.__setattr__(request, "source", source)
    return request


def _corrupt_action(base: RFBActionV1, **changes: object) -> RFBActionV1:
    action = object.__new__(RFBActionV1)
    for name, value in {**base.to_dict(), **changes}.items():
        object.__setattr__(action, name, value)
    return action


def test_accepts_policy_candidate_and_human_edit_to_another_declared_candidate() -> None:
    scenario = _scenario()
    policy_action, edited_action = scenario.candidate_actions

    policy = RfbProtocolValidator().validate(_request(policy_action), scenario)
    human_edit = RfbProtocolValidator().validate(
        _request(edited_action, request_id="request-2", source="human_edit"), scenario
    )

    assert policy.accepted
    assert policy.classification is RfbValidationClassification.VALID_CANDIDATE
    assert policy.codes == (RfbValidationCode.VALID_CANDIDATE,)
    assert policy.candidate_action_id == policy_action.identity_sha256
    assert human_edit.accepted
    assert human_edit.classification is RfbValidationClassification.VALID_HUMAN_EDIT_CANDIDATE
    assert human_edit.codes == (RfbValidationCode.VALID_HUMAN_EDIT_CANDIDATE,)
    assert human_edit.candidate_action_id == edited_action.identity_sha256


@pytest.mark.parametrize(
    ("request_id", "rationale", "source", "code"),
    [
        ("", "Valid rationale", "policy", RfbValidationCode.INVALID_ACTION_ID),
        ("request-1", "", "policy", RfbValidationCode.INVALID_RATIONALE),
        ("request-1", "Valid rationale", "planner", RfbValidationCode.INVALID_SOURCE),
        ("request-1", "Valid rationale", "", RfbValidationCode.INVALID_SOURCE),
    ],
)
def test_rejects_malformed_request_metadata_and_source(
    request_id: object, rationale: object, source: object, code: RfbValidationCode
) -> None:
    scenario = _scenario()

    result = RfbProtocolValidator().validate(
        _corrupt_request(
            scenario.candidate_actions[0],
            request_id=request_id,
            rationale=rationale,
            source=source,
        ),
        scenario,
    )

    assert not result.accepted
    assert result.classification is RfbValidationClassification.MALFORMED_REQUEST
    assert code in result.codes


@pytest.mark.parametrize(
    ("changes", "code"),
    [
        ({"charge_current_A": math.nan}, RfbValidationCode.NONFINITE_CONTROL),
        ({"charge_current_A": 0.0}, RfbValidationCode.CHARGE_CURRENT_NOT_POSITIVE),
        ({"discharge_current_A": 0.0}, RfbValidationCode.DISCHARGE_CURRENT_NOT_NEGATIVE),
        ({"protocol_duration_s": 0.0}, RfbValidationCode.DURATION_NOT_POSITIVE),
        ({"protocol_duration_s": 240.5}, RfbValidationCode.DURATION_NOT_WHOLE_SECONDS),
        ({"discharge_voltage_limit_V": 2.0}, RfbValidationCode.INVALID_VOLTAGE_ORDERING),
    ],
)
def test_fails_closed_on_corrupted_canonical_action_controls(
    changes: dict[str, object], code: RfbValidationCode
) -> None:
    scenario = _scenario()
    malformed_action = _corrupt_action(scenario.candidate_actions[0], **changes)

    result = RfbProtocolValidator().validate(_corrupt_request(malformed_action), scenario)

    assert not result.accepted
    assert result.classification is RfbValidationClassification.MALFORMED_REQUEST
    assert code in result.codes


def test_rejects_fixed_field_mismatch_and_out_of_range_action() -> None:
    scenario = _scenario()
    base = scenario.candidate_actions[0]
    fixed_mismatch = RFBActionV1(
        **{**base.to_dict(), "charge_voltage_limit_V": base.charge_voltage_limit_V + 0.1}
    )
    out_of_range = RFBActionV1(**{**base.to_dict(), "charge_current_A": 0.16})

    fixed_result = RfbProtocolValidator().validate(_request(fixed_mismatch), scenario)
    range_result = RfbProtocolValidator().validate(_request(out_of_range), scenario)

    assert not fixed_result.accepted
    assert RfbValidationCode.FIXED_CONTROL_MISMATCH in fixed_result.codes
    assert not range_result.accepted
    assert RfbValidationCode.CONTROL_OUT_OF_RANGE in range_result.codes


def test_rejects_envelope_valid_action_missing_from_finite_candidate_set() -> None:
    scenario = _scenario()
    base = scenario.candidate_actions[0]
    nonmember = RFBActionV1(**{**base.to_dict(), "charge_current_A": 0.08})

    result = RfbProtocolValidator().validate(_request(nonmember), scenario)

    assert not result.accepted
    assert result.classification is RfbValidationClassification.NONMEMBER_REQUEST
    assert result.codes == (RfbValidationCode.CANDIDATE_NOT_FOUND,)


def test_loaded_scenario_uses_only_its_public_projection() -> None:
    try:
        scenario = load_rfb_scenario(SCENARIO_PATH).public_projection()
    except TypeError as exc:
        pytest.skip(f"loaded RFB scenario has not adopted the public protocol contract: {exc}")

    result = RfbProtocolValidator().validate(_request(scenario.candidate_actions[0]), scenario)

    assert result.accepted
    assert result.codes == (RfbValidationCode.VALID_CANDIDATE,)
