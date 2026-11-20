import copy
import json
import math
from dataclasses import asdict, fields
from pathlib import Path

import pytest

from discovery_flight_simulator.rfb import (
    CANONICAL_ACTION_FIELDS,
    RFBActionV1,
    RFBOutcomeV1,
    RFBPublicStateV1,
    RFBScenarioV1,
    V1_FIXED_ACTION_FIELDS,
    V1_VARYING_AXES,
    FrozenScalarUtilityV1,
    calculate_scalar_utility,
    load_rfb_scenario,
)
from discovery_flight_simulator.rfb.contracts import (
    RFBActionRequestV1,
    RFBPlanningStateV1,
    RFBRecommendationV1,
    build_rfb_campaign_event_v1,
)
from discovery_flight_simulator.rfb.scenario import RFBZERO_MODEL_PARAMETER_FIELDS
from discovery_flight_simulator.rfb.utility import utility_record_for_outcome
from discovery_flight_simulator.rfb.validation import (
    RfbProtocolValidator,
    RfbValidationClassification,
    RfbValidationCode,
)


SCENARIO_PATH = Path("scenarios/rfbzero_cell_v0.json")
_COMMITMENT_KEY = b"rfb-domain-test-commitment-key"
_PRIVATE_MARKERS = {
    "adapter_id",
    "capacity_reference_C",
    "dependency_pins",
    "evaluator_truth",
    "failure_schedule",
    "model_parameters",
    "private_config_sha256",
    "reducer_id",
    "volume_cls",
}


def _loaded():
    return load_rfb_scenario(SCENARIO_PATH, private_commitment_key=_COMMITMENT_KEY)


def test_v1_actions_serialize_exactly_five_unit_bearing_fields_and_require_integral_seconds() -> None:
    scenario = _loaded().public_projection()

    assert scenario.provenance == "simulated"
    assert scenario.model_dimension == "0D"
    for action in scenario.candidate_actions:
        assert tuple(action.to_dict()) == CANONICAL_ACTION_FIELDS
        assert set(action.to_dict()) == set(CANONICAL_ACTION_FIELDS)
        assert action.charge_current_A > 0.0
        assert action.discharge_current_A < 0.0
        assert isinstance(action.protocol_duration_s, int)

    with pytest.raises(ValueError, match="positive whole number"):
        RFBActionV1(0.1, -0.08, 1.5, 0.5, 240.5)


def test_v1_finite_candidate_set_varies_only_the_two_current_axes() -> None:
    scenario = _loaded().public_projection()
    values = {
        name: {getattr(action, name) for action in scenario.candidate_actions}
        for name in CANONICAL_ACTION_FIELDS
    }

    assert all(len(values[name]) > 1 for name in V1_VARYING_AXES)
    assert all(len(values[name]) == 1 for name in V1_FIXED_ACTION_FIELDS)
    assert scenario.fixed_action_values == {
        "charge_voltage_limit_V": 1.5,
        "discharge_voltage_limit_V": 0.5,
        "protocol_duration_s": 240,
    }
    assert scenario.contains(scenario.candidate_actions[0])
    assert scenario.candidate_index(scenario.candidate_actions[0]) == 0
    assert not scenario.contains(
        RFBActionV1(
            charge_current_A=0.12,
            discharge_current_A=-0.07,
            charge_voltage_limit_V=1.5,
            discharge_voltage_limit_V=0.5,
            protocol_duration_s=240,
        )
    )


def test_real_request_wrapper_validates_against_the_public_scenario() -> None:
    scenario = _loaded().public_projection()
    candidate = scenario.candidate_actions[0]
    request = RFBActionRequestV1(
        request_id="request-001",
        action=candidate,
        rationale="Evaluate the declared finite candidate.",
        source="policy",
    )

    assert tuple(request.to_dict()) == ("request_id", "action", "rationale", "source")
    assert tuple(request.to_dict()["action"]) == CANONICAL_ACTION_FIELDS
    result = RfbProtocolValidator().validate(request, scenario)

    assert result.accepted
    assert result.classification is RfbValidationClassification.VALID_CANDIDATE
    assert result.codes == (RfbValidationCode.VALID_CANDIDATE,)
    assert result.candidate_action_id == candidate.identity_sha256
    assert scenario.contains(request)


def test_public_scenario_exposes_the_validation_envelope() -> None:
    scenario = _loaded().public_projection()

    assert set(scenario.action_schema.ranges) == set(CANONICAL_ACTION_FIELDS)
    assert scenario.action_schema.ranges["charge_current_A"] == (0.06, 0.14)
    assert scenario.action_schema.ranges["discharge_current_A"] == (-0.14, -0.08)
    assert scenario.fixed_fields == scenario.fixed_action_values
    assert scenario.ocv_50_soc_V == 1.0
    public = scenario.to_dict()
    assert public["action_schema"]["ranges"]["protocol_duration_s"] == [240.0, 240.0]
    assert public["fixed_fields"]["protocol_duration_s"] == 240
    assert public["ocv_50_soc_V"] == 1.0
    assert public["cost_model"]["valid_execution"] == {"attempt_cost": 1, "measurement_cost": 1}
    assert public["cost_model"]["invalid_protocol"] == {"attempt_cost": 1, "measurement_cost": 0}
    assert public["utility_sha256"] == scenario.utility_sha256
    assert public["public_projection_sha256"] == scenario.public_projection_sha256
    assert scenario.public_projection_sha256 == scenario.public_projection_sha256


def test_action_and_scenario_contracts_reject_schema_and_v1_axis_violations() -> None:
    with pytest.raises(ValueError, match="exactly the five canonical"):
        RFBActionV1.from_dict({"charge_current_A": 0.1})
    with pytest.raises(ValueError, match="negative"):
        RFBActionV1(0.1, 0.08, 1.5, 0.5, 240)

    scenario = _loaded().public_projection()
    altered = tuple(
        RFBActionV1(
            action.charge_current_A,
            action.discharge_current_A,
            1.6 if index == 0 else action.charge_voltage_limit_V,
            action.discharge_voltage_limit_V,
            action.protocol_duration_s,
        )
        for index, action in enumerate(scenario.candidate_actions)
    )
    with pytest.raises(ValueError, match="scenario-fixed"):
        RFBScenarioV1(
            scenario_id=scenario.scenario_id,
            scenario_version=scenario.scenario_version,
            candidate_actions=altered,
            action_schema=scenario.action_schema,
            fixed_fields=scenario.fixed_fields,
            ocv_50_soc_V=scenario.ocv_50_soc_V,
            utility=scenario.utility,
            total_attempt_budget=scenario.total_attempt_budget,
            total_measurement_budget=scenario.total_measurement_budget,
        )


def test_loader_uses_a_keyed_private_commitment_without_public_leaks(tmp_path: Path) -> None:
    first = _loaded()
    second = _loaded()
    assert first.scenario_identity == second.scenario_identity
    assert first.public_scenario.to_dict() == second.public_scenario.to_dict()
    assert first.scenario_identity["candidate_set_sha256"] == first.public_scenario.candidate_set_sha256
    assert "private_config_sha256" not in first.scenario_identity
    assert len(first.scenario_identity["private_config_hmac_sha256"]) == 64

    state = first.public_state()
    assert isinstance(state, RFBPublicStateV1)
    assert {field.name for field in fields(state)} == {
        "scenario",
        "outcomes",
        "remaining_attempt_budget",
        "remaining_measurement_budget",
    }
    public_serializations = (
        json.dumps(first.public_scenario.to_dict(), sort_keys=True),
        json.dumps(asdict(state), sort_keys=True),
        json.dumps(first.scenario_identity, sort_keys=True),
    )
    for serialized in public_serializations:
        assert not any(marker in serialized for marker in _PRIVATE_MARKERS)

    raw = json.loads(SCENARIO_PATH.read_text(encoding="utf-8"))
    changed = copy.deepcopy(raw)
    changed["private"]["oracle"]["model_parameters"]["resistance"] = 0.75
    changed_path = tmp_path / "changed-private.json"
    changed_path.write_text(json.dumps(changed, sort_keys=True), encoding="utf-8")
    changed_scenario = load_rfb_scenario(changed_path, private_commitment_key=_COMMITMENT_KEY)
    assert changed_scenario.public_scenario.to_dict() == first.public_scenario.to_dict()
    assert changed_scenario.scenario_identity["canonical_public_config_sha256"] == first.scenario_identity[
        "canonical_public_config_sha256"
    ]
    assert changed_scenario.scenario_identity["source_sha256"] == first.scenario_identity["source_sha256"]
    assert changed_scenario.scenario_identity["private_config_hmac_sha256"] != first.scenario_identity[
        "private_config_hmac_sha256"
    ]

    unkeyed_first = load_rfb_scenario(SCENARIO_PATH)
    unkeyed_second = load_rfb_scenario(SCENARIO_PATH)
    assert unkeyed_first.scenario_identity["private_config_hmac_sha256"] != unkeyed_second.scenario_identity[
        "private_config_hmac_sha256"
    ]


def test_execution_only_oracle_spec_is_complete_and_fixture_runs() -> None:
    loaded = _loaded()
    spec = loaded.execution_oracle_spec

    assert tuple(spec.model_parameters) == RFBZERO_MODEL_PARAMETER_FIELDS
    assert spec.model_parameters["ocv_50_soc"] == loaded.public_scenario.ocv_50_soc_V
    assert loaded.execution_identity == {
        "adapter": {"id": "discovery_flight_simulator.rfb.rfbzero_adapter", "version": "1"},
        "reducer": {
            "id": "discovery_flight_simulator.rfb.rfbzero_trace_reducer",
            "version": "1",
        },
        "rfbzero_version": "1.0.1",
        "dependency_pins": {
            "python": "3.12.12",
            "numpy": "2.5.1",
            "scipy": "1.18.0",
            "rfbzero": "1.0.1",
        },
    }
    assert "model_parameters" not in json.dumps(loaded.execution_identity, sort_keys=True)

    pytest.importorskip("rfbzero")
    from discovery_flight_simulator.rfb.oracle import RFBZeroOracleAdapter

    outcome = RFBZeroOracleAdapter().execute(spec, loaded.public_scenario.candidate_actions[0])
    assert outcome.status == "complete"
    assert outcome.provenance == "simulated"


def test_fixture_has_no_hidden_optimum_or_physical_claim() -> None:
    raw = json.loads(SCENARIO_PATH.read_text(encoding="utf-8"))
    private = raw["private"]

    assert set(private) == {"oracle", "failure_schedule"}
    assert "evaluator_truth" not in json.dumps(raw, sort_keys=True)
    assert "hidden_best" not in json.dumps(raw, sort_keys=True)
    assert "physical" not in json.dumps(raw, sort_keys=True).lower()


def test_frozen_scalar_utility_has_public_range_and_fails_closed() -> None:
    utility = FrozenScalarUtilityV1(energy_reference_J=10.0, duration_reference_s=240.0)
    complete = RFBOutcomeV1(
        status="complete",
        delivered_discharge_energy_J=8.0,
        round_trip_efficiency=0.7,
        capacity_retention=0.9,
        elapsed_duration_s=120.0,
    )
    assert utility.public_range == (-1.0, 0.9)
    assert math.isclose(calculate_scalar_utility(complete, utility), 0.665)
    assert calculate_scalar_utility(None, utility) == -1.0
    assert calculate_scalar_utility(
        RFBOutcomeV1("failed", None, None, None, None), utility
    ) == -1.0
    assert calculate_scalar_utility(
        RFBOutcomeV1("complete", 8.0, 0.7, 0.9, 120.0, qc_flags=("invalid",)), utility
    ) == -1.0
    assert calculate_scalar_utility(
        RFBOutcomeV1("complete", math.nan, 0.7, 0.9, 120.0), utility
    ) == -1.0
    assert utility.to_dict()["objective"] == "single_scalar_utility"


def test_canonical_utility_record_and_event_contracts_are_serializable_and_private_free() -> None:
    scenario = _loaded().public_projection()
    record = utility_record_for_outcome(None, scenario.utility)
    event = build_rfb_campaign_event_v1(
        event_type="execution_recorded",
        payload={"utility": record.to_dict()},
        sequence=3,
        previous_event_sha256="a" * 64,
        audit_timestamp="2026-07-20T12:00:00+00:00",
    )

    assert record.utility == -1.0
    assert not record.valid
    assert record.utility_sha256 == scenario.utility_sha256
    assert event["schema_version"] == "rfb_campaign_event_v1"
    assert event["event_sha256"] == build_rfb_campaign_event_v1(
        event_type="execution_recorded",
        payload={"utility": record.to_dict()},
        sequence=3,
        previous_event_sha256="a" * 64,
        audit_timestamp="2030-01-01T00:00:00+00:00",
    )["event_sha256"]
    serialized = json.dumps({"scenario": scenario.to_dict(), "event": event}, sort_keys=True)
    assert not any(marker in serialized for marker in _PRIVATE_MARKERS)

    with pytest.raises(ValueError, match="private material"):
        build_rfb_campaign_event_v1(
            event_type="execution_recorded",
            payload={"model_parameters": {"resistance": 0.5}},
            sequence=0,
        )


def test_recommendation_identifiers_are_derived_from_public_canonical_content() -> None:
    scenario = _loaded().public_projection()
    state = RFBPlanningStateV1(
        scenario=scenario,
        event_head_sha256="b" * 64,
        revision=4,
        remaining_attempt_budget=2,
        remaining_measurement_budget=1,
    )
    recommendation = RFBRecommendationV1(
        action=scenario.candidate_actions[0],
        policy_id="fixed_grid",
        policy_version="1",
        public_projection_sha256=scenario.public_projection_sha256,
        candidate_set_sha256=scenario.candidate_set_sha256,
        utility_sha256=scenario.utility_sha256,
        basis_event_head_sha256=state.event_head_sha256,
        basis_revision=state.revision,
        remaining_attempt_budget=state.remaining_attempt_budget,
        remaining_measurement_budget=state.remaining_measurement_budget,
        predicted_utility_mean=None,
        predicted_utility_std=None,
        rationale="Select the first declared candidate.",
    )

    recommendation.validate_integrity()
    assert recommendation.action_id == recommendation.action.identity_sha256
    assert recommendation.request.request_id == recommendation.recommendation_id
    assert len(recommendation.recommendation_sha256) == 64
    assert json.loads(json.dumps(recommendation.to_dict(), sort_keys=True))["utility_sha256"] == scenario.utility_sha256

    with pytest.raises(ValueError, match="action_id"):
        RFBRecommendationV1(
            **{**recommendation.__dict__, "action_id": "0" * 64}
        )
