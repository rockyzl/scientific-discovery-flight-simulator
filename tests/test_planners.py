import numpy as np

from discovery_flight_simulator.contracts import Observation, PublicCampaignState
from discovery_flight_simulator.planners.baselines import (
    ExpectedInformationGainPlanner,
    FixedGridPlanner,
    RandomValidPlanner,
)
from discovery_flight_simulator.planners.registry import default_planners
from discovery_flight_simulator.worlds.registry import load_scenario


PRIVATE_KEY = "fixed-test-private-key"


def _state(scenario):
    return PublicCampaignState(
        spec=scenario.public_spec,
        observations=(),
        remaining_attempt_budget=scenario.public_spec.total_attempt_budget,
        remaining_measurement_budget=scenario.public_spec.total_measurement_budget,
        public_beliefs={},
    )


def test_registry_contains_three_non_llm_baselines():
    assert set(default_planners()) == {"random", "fixed_grid", "information_gain"}


def test_all_planners_propose_only_publicly_supported_operations():
    scenario = load_scenario("scenarios/cv_mechanism_v0.json", PRIVATE_KEY)
    for planner_type in (RandomValidPlanner, FixedGridPlanner, ExpectedInformationGainPlanner):
        planner = planner_type()
        request = planner.propose(_state(scenario), np.random.default_rng(10))
        assert request.operation == "calibrate"
        assert request.controls == {}
        assert "truth" not in request.rationale.lower()


def test_information_gain_prior_contains_only_public_candidate_models():
    scenario = load_scenario("scenarios/cv_mechanism_v0.json", PRIVATE_KEY)
    planner = ExpectedInformationGainPlanner()
    planner.propose(_state(scenario), np.random.default_rng(10))
    assert planner.get_public_beliefs() == {
        "diffusion": 1 / 3,
        "surface": 1 / 3,
        "mixed": 1 / 3,
    }


def test_fixed_grid_uses_exact_valid_endpoints():
    scenario = load_scenario("scenarios/cv_mechanism_v0.json", PRIVATE_KEY)
    planner = FixedGridPlanner()
    initial = _state(scenario)
    planner.propose(initial, np.random.default_rng(10))
    calibration = Observation(
        status="ok",
        requested_controls={},
        executed_controls={},
        value=1.0,
        standard_error=0.025,
        qc_flags=("calibration", "operation:calibrate"),
        attempt_cost=1,
        measurement_cost=1,
    )
    planner.observe(calibration, initial)
    after_calibration = PublicCampaignState(
        spec=scenario.public_spec,
        observations=(calibration,),
        remaining_attempt_budget=11,
        remaining_measurement_budget=9,
        public_beliefs=planner.get_public_beliefs(),
    )
    values = [
        planner.propose(after_calibration, np.random.default_rng(10)).controls[
            "scan_rate_mv_s"
        ]
        for _ in range(9)
    ]
    low, high = scenario.public_spec.controls["scan_rate_mv_s"]
    assert values[0] == low
    assert values[-1] == high
    assert all(low <= value <= high for value in values)


def test_noisy_information_gain_quadrature_is_finite_and_deterministic():
    scenario = load_scenario("scenarios/cv_mechanism_v0.json", PRIVATE_KEY)
    planner = ExpectedInformationGainPlanner()
    planner.propose(_state(scenario), np.random.default_rng(10))
    first = planner._expected_information_gain("scan_rate_mv_s", 80.0, 0.05)
    second = planner._expected_information_gain("scan_rate_mv_s", 80.0, 0.05)
    assert np.isfinite(first)
    assert first > 0.0
    assert first == second
