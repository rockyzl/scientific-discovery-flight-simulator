from pathlib import Path

from discovery_flight_simulator.contracts import ExperimentRequest
from discovery_flight_simulator.worlds.microscopy import response_for_boundary
from discovery_flight_simulator.worlds.registry import load_scenario


SCENARIO = Path("scenarios/microscopy_boundary_v0.json")
PRIVATE_KEY = "fixed-test-private-key"


def test_boundary_response_is_monotonic_and_centered():
    boundary = 0.5
    assert response_for_boundary(boundary, 0.2) < response_for_boundary(boundary, 0.5)
    assert response_for_boundary(boundary, 0.5) < response_for_boundary(boundary, 0.8)
    assert abs(response_for_boundary(boundary, boundary) - 0.5) < 1e-12


def test_microscopy_uses_same_public_environment_interface_as_cv():
    microscopy = load_scenario(SCENARIO, PRIVATE_KEY)
    cv = load_scenario("scenarios/cv_mechanism_v0.json", PRIVATE_KEY)
    for scenario in (microscopy, cv):
        assert hasattr(scenario, "public_spec")
        assert hasattr(scenario, "capabilities")
        assert callable(scenario.environment_factory)
        assert scenario.public_spec.provenance == "simulated"

    environment = microscopy.environment_factory(microscopy.seed_bundle)
    observation = environment.execute(
        ExperimentRequest(
            request_id="scan-1",
            operation="measure",
            controls={"position": 0.3},
            rationale="localize the synthetic phase boundary",
        )
    )
    assert observation.provenance == "simulated"
    assert observation.requested_controls == {"position": 0.3}


def test_microscopy_truth_is_a_boundary_candidate():
    scenario = load_scenario(SCENARIO, PRIVATE_KEY)
    assert scenario.private_truth["world_type"] == "microscopy_boundary"
    assert 0.2 <= scenario.private_truth["boundary"] <= 0.8
    assert "not a microscopy image model" in scenario.private_truth["scientific_scope"]
