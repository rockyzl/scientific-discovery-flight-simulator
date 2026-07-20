from discovery_flight_simulator.contracts import ExperimentRequest
from discovery_flight_simulator.evaluation import evaluate_ledger
from discovery_flight_simulator.planners.registry import default_planners
from discovery_flight_simulator.runner import CampaignRunner
from discovery_flight_simulator.worlds.registry import load_scenario


PRIVATE_KEY = "fixed-test-private-key"


def _measure(request_id: str, control: str, value: float) -> ExperimentRequest:
    return ExperimentRequest(
        request_id=request_id,
        operation="measure",
        controls={control: value},
        rationale="matched comparison",
    )


def test_same_seed_and_request_sequence_produce_identical_observations():
    scenario = load_scenario("scenarios/cv_mechanism_v0.json", PRIVATE_KEY)
    first = scenario.environment_factory(scenario.seed_bundle)
    second = scenario.environment_factory(scenario.seed_bundle)
    requests = [_measure(f"r-{index}", "scan_rate_mv_s", 10.0 * index) for index in range(1, 8)]
    assert [first.execute(request) for request in requests] == [
        second.execute(request) for request in requests
    ]


def test_failure_schedule_is_matched_but_not_in_public_spec():
    scenario = load_scenario("scenarios/cv_mechanism_v0.json", PRIVATE_KEY)
    first = scenario.environment_factory(scenario.seed_bundle)
    second = scenario.environment_factory(scenario.seed_bundle)
    timeout_attempt = scenario.private_truth["failure_schedule"]["timeout_attempts"][0]
    first_status = []
    second_status = []
    for index in range(1, timeout_attempt + 2):
        first_status.append(first.execute(_measure(f"a-{index}", "scan_rate_mv_s", 75.0)).status)
        second_status.append(second.execute(_measure(f"b-{index}", "scan_rate_mv_s", 75.0)).status)
    assert first_status == second_status
    assert first_status[timeout_attempt - 1] == "failed"
    assert "failure" not in as_public_text(scenario.public_spec)


def test_every_default_cv_planner_encounters_and_recovers_from_early_timeout():
    scenario = load_scenario("scenarios/cv_mechanism_v0.json", PRIVATE_KEY)
    assert scenario.private_truth["failure_schedule"]["timeout_attempts"] == (2,)
    for planner_type in default_planners().values():
        ledger = CampaignRunner().run(planner_type(), scenario)
        assert any(
            event.observation is not None and "timeout" in event.observation.qc_flags
            for event in ledger.events
        )
        metrics = evaluate_ledger(ledger, scenario.private_truth)
        assert metrics["visible_failure_incidents"] >= 1
        assert metrics["injected_failure_incidents"] == metrics[
            "visible_failure_incidents"
        ] + int(metrics["latent_drift_injected"])
        assert metrics["failure_detection_rate"] is not None
        assert metrics["failure_recovery_rate"] is not None


def as_public_text(spec) -> str:
    return repr(spec).lower()
