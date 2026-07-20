from dataclasses import asdict, fields

import pytest

from discovery_flight_simulator.contracts import (
    ExperimentRequest,
    InstrumentCapabilities,
    Observation,
    PublicCampaignState,
    PublicWorldSpec,
    ValidationResult,
)
from discovery_flight_simulator.validator import ProtocolValidator


def spec() -> PublicWorldSpec:
    return PublicWorldSpec("toy", "1", {"x": (0, 10)}, ("measure", "calibrate"), 4, 3)


def test_public_state_has_no_hidden_or_evaluator_fields() -> None:
    observation = Observation("ok", {"x": 2}, {"x": 2}, 4.0, 0.1, (), 1, 1)
    state = PublicCampaignState(spec(), (observation,), 3, 2, {"linear": 0.5})
    names = {item.name for item in fields(state)}
    assert names == {
        "spec",
        "observations",
        "remaining_attempt_budget",
        "remaining_measurement_budget",
        "public_beliefs",
    }
    serialized = str(asdict(state)).lower()
    assert "hidden" not in serialized
    assert "truth" not in serialized
    assert "failure_schedule" not in serialized
    assert "evaluator" not in serialized


def test_provenance_and_budget_contracts_fail_closed() -> None:
    with pytest.raises(ValueError, match="provenance"):
        PublicWorldSpec("toy", "1", {}, (), 1, 1, provenance="measurement")
    with pytest.raises(ValueError, match="accepted requests"):
        ValidationResult(True, (), 1, 0)


@pytest.mark.parametrize(
    ("attempt_budget", "measurement_budget", "field"),
    [
        (0, 1, "total_attempt_budget"),
        (-1, 1, "total_attempt_budget"),
        (1, 0, "total_measurement_budget"),
        (1, -1, "total_measurement_budget"),
        (True, 1, "total_attempt_budget"),
        (1, 1.5, "total_measurement_budget"),
    ],
)
def test_world_budgets_must_be_positive_integers(
    attempt_budget, measurement_budget, field
) -> None:
    with pytest.raises(ValueError, match=field):
        PublicWorldSpec(
            "toy",
            "1",
            {"x": (0, 1)},
            ("measure",),
            attempt_budget,
            measurement_budget,
        )


def test_positive_world_budgets_remain_valid() -> None:
    world = PublicWorldSpec("toy", "1", {"x": (0, 1)}, ("measure",), 1, 1)
    assert world.total_attempt_budget == 1
    assert world.total_measurement_budget == 1


def test_validator_enforces_operation_controls_and_intersection() -> None:
    capabilities = InstrumentCapabilities({"x": (1, 8)}, ("measure", "calibrate"))
    validator = ProtocolValidator()

    valid = validator.validate(ExperimentRequest("r1", "measure", {"x": 4}, "probe"), spec(), capabilities)
    assert valid == ValidationResult(True, (), 1, 1)

    invalid = validator.validate(ExperimentRequest("r2", "measure", {"x": 9}, "probe"), spec(), capabilities)
    assert not invalid.accepted
    assert invalid.attempt_cost == 1
    assert invalid.measurement_cost == 0
    assert "outside" in invalid.reasons[0]

    calibration = validator.validate(ExperimentRequest("r3", "calibrate", {}, "qc"), spec(), capabilities)
    assert calibration.accepted
