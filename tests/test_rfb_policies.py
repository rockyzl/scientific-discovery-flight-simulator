from __future__ import annotations

import ast
import json
from pathlib import Path

import pytest

from discovery_flight_simulator.rfb.contracts import (
    FrozenScalarUtilityV1,
    RFBActionSchemaV1,
    RFBActionV1,
    RFBOutcomeV1,
    RFBPlanningStateV1,
    RFBScenarioV1,
)
from discovery_flight_simulator.rfb.policies import (
    ConstrainedBORFBPolicy,
    FixedGridRFBPolicy,
    RFBPublicObservationV1,
    RandomRFBPolicy,
    public_event_head_hash,
)


def _scenario() -> RFBScenarioV1:
    actions = (
        RFBActionV1(0.06, -0.05, 1.5, 0.5, 240),
        RFBActionV1(0.06, -0.11, 1.5, 0.5, 240),
        RFBActionV1(0.14, -0.05, 1.5, 0.5, 240),
        RFBActionV1(0.14, -0.11, 1.5, 0.5, 240),
    )
    return RFBScenarioV1(
        scenario_id="rfb-policy-test",
        scenario_version="1",
        candidate_actions=actions,
        action_schema=RFBActionSchemaV1(
            {
                "charge_current_A": (0.05, 0.15),
                "discharge_current_A": (-0.12, -0.04),
                "charge_voltage_limit_V": (1.4, 1.6),
                "discharge_voltage_limit_V": (0.4, 0.6),
                "protocol_duration_s": (240, 240),
            }
        ),
        fixed_fields={
            "charge_voltage_limit_V": 1.5,
            "discharge_voltage_limit_V": 0.5,
            "protocol_duration_s": 240,
        },
        ocv_50_soc_V=1.0,
        utility=FrozenScalarUtilityV1(energy_reference_J=10.0, duration_reference_s=240.0),
        total_attempt_budget=4,
        total_measurement_budget=4,
    )


def _outcome(*, high: bool) -> RFBOutcomeV1:
    if high:
        return RFBOutcomeV1("complete", 10.0, 1.0, 1.0, 1.0)
    return RFBOutcomeV1("complete", 0.0, 0.0, 0.0, 240.0)


def _observation(action: RFBActionV1, *, high: bool, utility: float | None = None) -> RFBPublicObservationV1:
    return RFBPublicObservationV1(action=action, outcome=_outcome(high=high), utility=utility)


def _planning_state(scenario: RFBScenarioV1) -> RFBPlanningStateV1:
    return RFBPlanningStateV1(
        scenario=scenario,
        event_head_sha256="c" * 64,
        revision=7,
        remaining_attempt_budget=3,
        remaining_measurement_budget=2,
    )


@pytest.mark.parametrize("policy_type", (FixedGridRFBPolicy, RandomRFBPolicy, ConstrainedBORFBPolicy))
def test_policies_are_deterministic_and_return_validator_requests(policy_type: type[object]) -> None:
    scenario = _scenario()
    history = (_observation(scenario.candidate_actions[0], high=True),)
    policy = policy_type()

    first = policy.recommend(scenario, history)
    second = policy.recommend(scenario, history)

    assert first == second
    assert first is not None
    assert first.action in scenario.candidate_actions[1:]
    assert first.request.action == first.action
    assert first.request.request_id == first.recommendation_id
    assert first.request.source == "policy"
    assert first.candidate_set_hash == scenario.candidate_set_sha256
    assert first.public_event_head_hash == public_event_head_hash(history)
    if policy_type is ConstrainedBORFBPolicy:
        assert first.predicted_utility_mean is not None
        assert first.predicted_utility_std is not None
    else:
        assert first.predicted_utility_mean is None
        assert first.predicted_utility_std is None


def test_fixed_grid_uses_first_valid_untried_candidate_in_declared_order() -> None:
    scenario = _scenario()
    first, rejected, expected = scenario.candidate_actions[:3]

    recommendation = FixedGridRFBPolicy().recommend(
        scenario,
        observations=(_observation(first, high=True),),
        rejected_action_ids=(rejected.identity_sha256,),
    )

    assert recommendation is not None
    assert recommendation.action == expected
    assert recommendation.policy_id == "fixed_grid"
    assert "scenario order" in recommendation.rationale


@pytest.mark.parametrize("policy_type", (FixedGridRFBPolicy, RandomRFBPolicy, ConstrainedBORFBPolicy))
def test_policies_anchor_recommendations_to_the_supplied_public_planning_state(
    policy_type: type[object],
) -> None:
    scenario = _scenario()
    state = _planning_state(scenario)
    recommendation = policy_type().recommend(state)  # type: ignore[union-attr]

    assert recommendation is not None
    assert recommendation.public_projection_sha256 == scenario.public_projection_sha256
    assert recommendation.candidate_set_sha256 == scenario.candidate_set_sha256
    assert recommendation.utility_sha256 == scenario.utility_sha256
    assert recommendation.basis_event_head_sha256 == state.event_head_sha256
    assert recommendation.basis_revision == state.revision
    assert recommendation.remaining_attempt_budget == state.remaining_attempt_budget
    assert recommendation.remaining_measurement_budget == state.remaining_measurement_budget
    assert recommendation.request.request_id == recommendation.recommendation_id
    assert len(recommendation.recommendation_sha256) == 64
    assert json.loads(json.dumps(recommendation.to_dict(), sort_keys=True))["action_id"] == recommendation.action_id


@pytest.mark.parametrize("policy_type", (FixedGridRFBPolicy, RandomRFBPolicy, ConstrainedBORFBPolicy))
def test_policies_do_not_recommend_when_a_public_budget_is_exhausted(policy_type: type[object]) -> None:
    scenario = _scenario()
    state = RFBPlanningStateV1(
        scenario=scenario,
        event_head_sha256="d" * 64,
        revision=2,
        remaining_attempt_budget=0,
        remaining_measurement_budget=2,
    )

    assert policy_type().recommend(state) is None  # type: ignore[union-attr]


@pytest.mark.parametrize("policy_type", (FixedGridRFBPolicy, RandomRFBPolicy, ConstrainedBORFBPolicy))
def test_all_policies_skip_rejected_declared_actions(policy_type: type[object]) -> None:
    scenario = _scenario()
    rejected = scenario.candidate_actions[0].identity_sha256

    recommendation = policy_type().recommend(scenario, rejected_action_ids=(rejected,))

    assert recommendation is not None
    assert recommendation.action.identity_sha256 != rejected
    assert scenario.contains(recommendation.action)


@pytest.mark.parametrize("policy_type", (FixedGridRFBPolicy, RandomRFBPolicy, ConstrainedBORFBPolicy))
def test_all_policies_return_none_when_every_candidate_is_unavailable(policy_type: type[object]) -> None:
    scenario = _scenario()
    history = tuple(_observation(action, high=False) for action in scenario.candidate_actions[:2])
    rejected = tuple(action.identity_sha256 for action in scenario.candidate_actions[2:])

    assert policy_type().recommend(scenario, history, rejected) is None


def test_random_choice_is_derived_from_the_public_event_head() -> None:
    scenario = _scenario()
    policy = RandomRFBPolicy()
    first = policy.recommend(scenario)
    changed_history = (_observation(scenario.candidate_actions[0], high=False),)
    second = policy.recommend(scenario, changed_history)

    assert first is not None
    assert second is not None
    assert first.public_event_head_hash != second.public_event_head_hash
    assert first.recommendation_id != second.recommendation_id
    assert second.action != scenario.candidate_actions[0]


def test_bo_uses_only_declared_actions_and_completed_public_outcomes() -> None:
    scenario = _scenario()
    declared_history = (
        _observation(scenario.candidate_actions[0], high=True),
        _observation(scenario.candidate_actions[1], high=False),
    )
    outside_candidate = RFBActionV1(0.10, -0.08, 1.5, 0.5, 240)
    outside_history = RFBPublicObservationV1(outside_candidate, _outcome(high=False), utility=0.9)
    policy = ConstrainedBORFBPolicy()

    baseline = policy.recommend(scenario, declared_history)
    with_outside_action = policy.recommend(scenario, (*declared_history, outside_history))

    assert baseline is not None
    assert with_outside_action is not None
    assert baseline.action == with_outside_action.action
    assert baseline.predicted_utility_mean == with_outside_action.predicted_utility_mean
    assert baseline.predicted_utility_std == with_outside_action.predicted_utility_std
    assert baseline.public_event_head_hash != with_outside_action.public_event_head_hash


def test_bo_recomputes_the_frozen_scalar_utility_from_outcomes() -> None:
    scenario = _scenario()
    policy = ConstrainedBORFBPolicy()
    low_history = (_observation(scenario.candidate_actions[0], high=False, utility=0.9),)
    high_history = (_observation(scenario.candidate_actions[0], high=True, utility=-0.1),)

    low = policy.recommend(scenario, low_history)
    high = policy.recommend(scenario, high_history)

    assert low is not None
    assert high is not None
    assert low.predicted_utility_mean is not None
    assert high.predicted_utility_mean is not None
    assert low.predicted_utility_mean < 0.0
    assert high.predicted_utility_mean > 0.0


def test_policy_module_has_no_forbidden_runtime_imports() -> None:
    import discovery_flight_simulator.rfb.policies as policies

    source = Path(policies.__file__).read_text(encoding="utf-8")
    imports: set[str] = set()
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Import):
            imports.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imports.add(node.module)

    forbidden_roots = {
        "rfbzero",
        "langgraph",
        "requests",
        "http",
        "socket",
        "openai",
        "anthropic",
    }
    assert not {
        imported
        for imported in imports
        if imported.split(".", maxsplit=1)[0] in forbidden_roots
        or imported.endswith((".oracle", ".scenario"))
    }
