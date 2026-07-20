import json
from dataclasses import asdict

import numpy as np

from discovery_flight_simulator.cli import compare
from discovery_flight_simulator.contracts import PublicCampaignState
from discovery_flight_simulator.planners.baselines import ExpectedInformationGainPlanner
from discovery_flight_simulator.worlds.registry import load_scenario


PRIVATE_KEY = "fixed-test-private-key"


BANNED_KEYS = {"private_truth", "hidden_truth", "failure_schedule", "noiseless_response"}


def _keys(value):
    if isinstance(value, dict):
        return set(value) | {key for child in value.values() for key in _keys(child)}
    if isinstance(value, (tuple, list)):
        return {key for child in value for key in _keys(child)}
    return set()


def test_public_campaign_state_has_no_hidden_world_fields():
    scenario = load_scenario("scenarios/cv_mechanism_v0.json", PRIVATE_KEY)
    state = PublicCampaignState(
        spec=scenario.public_spec,
        observations=(),
        remaining_attempt_budget=12,
        remaining_measurement_budget=10,
        public_beliefs={},
    )
    # Candidate mechanism names may be public hypotheses. What must never cross the boundary is
    # the selected truth, noiseless response, or future failure schedule.
    assert not (_keys(asdict(state)) & BANNED_KEYS)


def test_planner_needs_only_public_state_and_planner_rng():
    scenario = load_scenario("scenarios/microscopy_boundary_v0.json", PRIVATE_KEY)
    state = PublicCampaignState(
        spec=scenario.public_spec,
        observations=(),
        remaining_attempt_budget=12,
        remaining_measurement_budget=10,
        public_beliefs={},
    )
    planner = ExpectedInformationGainPlanner()
    decision = planner.propose(state, np.random.default_rng(2))
    assert decision.operation in state.spec.operations
    assert not hasattr(planner, "private_truth")


def test_shipped_scenarios_contain_no_raw_private_seeds():
    for path in (
        "scenarios/cv_mechanism_v0.json",
        "scenarios/microscopy_boundary_v0.json",
    ):
        raw = open(path, encoding="utf-8").read()
        assert '"world_seed"' not in raw
        assert '"noise_seed"' not in raw
        assert '"failure_seed"' not in raw


def test_private_seed_commitments_are_reproducible_without_revealing_seeds():
    first = load_scenario("scenarios/cv_mechanism_v0.json", PRIVATE_KEY)
    second = load_scenario("scenarios/cv_mechanism_v0.json", PRIVATE_KEY)
    other = load_scenario("scenarios/cv_mechanism_v0.json", "another-key")
    assert first.scenario_identity == second.scenario_identity
    assert first.private_truth == second.private_truth
    assert first.scenario_identity["seed_commitments"] != other.scenario_identity[
        "seed_commitments"
    ]
    public_identity = repr(first.scenario_identity)
    for seed in first.private_truth["private_seeds"].values():
        assert str(seed) not in public_identity


def test_omitted_private_key_generates_a_new_secure_campaign_identity():
    first = load_scenario("scenarios/cv_mechanism_v0.json")
    second = load_scenario("scenarios/cv_mechanism_v0.json")
    assert first.private_truth["replay_key"] != second.private_truth["replay_key"]
    assert first.scenario_identity["seed_commitments"] != second.scenario_identity[
        "seed_commitments"
    ]


def test_private_key_and_raw_seeds_are_absent_from_ledger_and_manifest(tmp_path):
    output = tmp_path / "artifacts"
    compare(
        "scenarios/cv_mechanism_v0.json",
        output,
        private_seed_key=PRIVATE_KEY,
    )
    summary = json.loads((output / "summary.json").read_text(encoding="utf-8"))
    reveal = summary["post_run_reveal"]
    private_values = {reveal["replay_key"], *(str(v) for v in reveal["private_seeds"].values())}
    public_paths = [output / "manifest.json", *(output / "ledgers").glob("*.json")]
    for path in public_paths:
        public_text = path.read_text(encoding="utf-8")
        assert not any(value in public_text for value in private_values)
