import json

from discovery_flight_simulator.evaluation import evaluate_ledger
from discovery_flight_simulator.planners.baselines import ExpectedInformationGainPlanner
from discovery_flight_simulator.runner import CampaignRunner
from discovery_flight_simulator.worlds.registry import load_scenario


PRIVATE_KEY = "fixed-test-private-key"


def test_cv_evaluation_reports_separate_metrics_and_post_run_reveal():
    scenario = load_scenario("scenarios/cv_mechanism_v0.json", PRIVATE_KEY)
    ledger = CampaignRunner().run(ExpectedInformationGainPlanner(), scenario)
    metrics = evaluate_ledger(ledger, scenario.private_truth)
    assert metrics["world_type"] == "cv_mechanism"
    assert isinstance(metrics["mechanism_correct"], bool)
    assert metrics["attempts"] >= metrics["measurement_cost"]
    assert 0.0 <= metrics["ledger_completeness"] <= 1.0
    assert metrics["post_run_reveal"]["value"] == scenario.private_truth["mechanism"]
    assert metrics["post_run_reveal"]["replay_key"] == PRIVATE_KEY
    assert metrics["post_run_reveal"]["private_seeds"] == scenario.private_truth[
        "private_seeds"
    ]


def test_microscopy_evaluation_reports_boundary_error():
    scenario = load_scenario("scenarios/microscopy_boundary_v0.json", PRIVATE_KEY)
    ledger = CampaignRunner().run(ExpectedInformationGainPlanner(), scenario)
    metrics = evaluate_ledger(ledger, scenario.private_truth)
    assert metrics["world_type"] == "microscopy_boundary"
    assert metrics["boundary_absolute_error"] >= 0.0
    assert metrics["post_run_reveal"]["kind"] == "boundary"
    assert metrics["post_run_reveal"]["provenance"] == "simulated"


def test_evaluation_rejects_a_tampered_ledger():
    scenario = load_scenario("scenarios/cv_mechanism_v0.json", PRIVATE_KEY)
    ledger = CampaignRunner().run(ExpectedInformationGainPlanner(), scenario)
    ledger._events[0] = ledger._events[0].__class__(  # deliberate adversarial mutation
        **{**ledger._events[0].__dict__, "costs": {"attempt": 99, "measurement": 99}}
    )
    try:
        evaluate_ledger(ledger, scenario.private_truth)
    except ValueError as exc:
        assert "invalid evidence ledger" in str(exc)
    else:
        raise AssertionError("tampered ledger must not be evaluated")


def test_failure_rates_are_not_applicable_when_no_failure_was_injected(tmp_path):
    config = json.loads(open("scenarios/cv_mechanism_v0.json", encoding="utf-8").read())
    config["failure_profile"] = {"name": "clean"}
    path = tmp_path / "clean.json"
    path.write_text(json.dumps(config), encoding="utf-8")
    scenario = load_scenario(path, PRIVATE_KEY)
    ledger = CampaignRunner().run(ExpectedInformationGainPlanner(), scenario)
    metrics = evaluate_ledger(ledger, scenario.private_truth)
    assert metrics["injected_failure_incidents"] == 0
    assert metrics["failure_evaluation_status"] == "not_applicable"
    assert metrics["failure_detection_rate"] is None
    assert metrics["failure_recovery_rate"] is None
