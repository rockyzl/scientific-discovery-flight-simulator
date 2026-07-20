import json
import math
from pathlib import Path

from discovery_flight_simulator.contracts import ExperimentRequest, SeedBundle
from discovery_flight_simulator.validator import ProtocolValidator
from discovery_flight_simulator.worlds.cv import CVMechanismEnvironment, response_for
from discovery_flight_simulator.worlds.registry import load_scenario


SCENARIO = Path("scenarios/cv_mechanism_v0.json")
PRIVATE_KEY = "fixed-test-private-key"


def _request(index: int, rate: float) -> ExperimentRequest:
    return ExperimentRequest(
        request_id=f"request-{index}",
        operation="measure",
        controls={"scan_rate_mv_s": rate},
        rationale="test",
    )


def test_cv_response_models_have_the_frozen_scalings():
    low, high = 25.0, 100.0
    assert math.isclose(response_for("diffusion", high) / response_for("diffusion", low), 2.0)
    assert math.isclose(response_for("surface", high) / response_for("surface", low), 4.0)
    mixed_ratio = response_for("mixed", high) / response_for("mixed", low)
    assert 2.0 < mixed_ratio < 4.0


def test_cv_scenario_is_explicitly_simulated_and_rejects_invalid_control():
    scenario = load_scenario(SCENARIO, PRIVATE_KEY)
    assert scenario.public_spec.provenance == "simulated"
    assert scenario.private_truth["scientific_scope"].startswith("transparent teaching emulator")
    invalid = _request(1, 501.0)
    result = ProtocolValidator().validate(
        invalid, scenario.public_spec, scenario.capabilities
    )
    assert not result.accepted
    assert result.attempt_cost == 1
    assert result.measurement_cost == 0


def test_cv_noise_is_condition_indexed_in_clean_world():
    config = json.loads(SCENARIO.read_text())
    config["failure_profile"] = {"name": "clean"}
    seeds = SeedBundle(world_seed=11, noise_seed=22, failure_seed=33, planner_seed=44)
    first = CVMechanismEnvironment(config, seeds)
    second = CVMechanismEnvironment(config, seeds)

    first_values = {
        10.0: first.execute(_request(1, 10.0)).value,
        100.0: first.execute(_request(2, 100.0)).value,
    }
    second_values = {
        100.0: second.execute(_request(1, 100.0)).value,
        10.0: second.execute(_request(2, 10.0)).value,
    }
    assert first_values == second_values


def test_timeout_advances_valid_instrument_attempt_schedule():
    scenario = load_scenario(SCENARIO, PRIVATE_KEY)
    environment = scenario.environment_factory(scenario.seed_bundle)
    timeout_attempt = scenario.private_truth["failure_schedule"]["timeout_attempts"][0]
    observations = [
        environment.execute(_request(index, 50.0))
        for index in range(1, timeout_attempt + 1)
    ]
    assert observations[-1].status == "failed"
    assert "timeout" in observations[-1].qc_flags
    assert environment.attempt_index == timeout_attempt
