from dataclasses import dataclass

from discovery_flight_simulator.artifacts import COMMITMENT_ALGORITHM, seed_commitment
from discovery_flight_simulator.contracts import (
    ExperimentRequest,
    InstrumentCapabilities,
    Observation,
    PublicWorldSpec,
    SeedBundle,
    StopDecision,
)
from discovery_flight_simulator.ledger import EvidenceLedger
from discovery_flight_simulator.runner import CampaignRunner


class Environment:
    def execute(self, request):
        if request.controls["x"] == 2:
            raise TimeoutError("injected")
        return Observation("ok", request.controls, request.controls, request.controls["x"] * 2, 0.1, (), 0, 0)


@dataclass
class Scenario:
    public_spec: PublicWorldSpec
    capabilities: InstrumentCapabilities
    seed_bundle: SeedBundle
    scenario_identity: dict
    private_truth: dict

    def environment_factory(self, seed_bundle):
        assert seed_bundle == self.seed_bundle
        return Environment()


def scenario(attempts=4, measurements=3):
    replay_key = "runner-test-key"
    seeds = SeedBundle(1, 2, 3, 4)
    commitments = {
        "algorithm": COMMITMENT_ALGORITHM,
        **{
            name: seed_commitment(replay_key, name, getattr(seeds, name))
            for name in ("world_seed", "noise_seed", "failure_seed")
        },
    }
    return Scenario(
        PublicWorldSpec("toy", "1", {"x": (0, 2)}, ("measure",), attempts, measurements),
        InstrumentCapabilities({"x": (0, 2)}, ("measure",)),
        seeds,
        {"id": "toy-1", "seed_commitments": commitments},
        {"hidden": "never public"},
    )


class ScriptedPlanner:
    name = "scripted"
    version = "1"

    def __init__(self):
        self.calls = 0
        self.seen_states = []
        self.public_beliefs = {"a": 0.5, "b": 0.5}

    def propose(self, state, planner_rng):
        self.seen_states.append(state)
        self.calls += 1
        if self.calls == 1:
            return ExperimentRequest("bad", "measure", {"x": 9}, "invalid")
        if self.calls == 2:
            return ExperimentRequest("failed", "measure", {"x": 2}, "failure")
        return StopDecision("enough", "a", 0.5)

    def observe(self, observation, state):
        self.public_beliefs = {"a": 0.6, "b": 0.4}


def test_runner_budget_semantics_hidden_separation_and_stop() -> None:
    planner = ScriptedPlanner()
    ledger = CampaignRunner().run(planner, scenario())
    assert ledger.verify()
    assert len(ledger.events) == 3

    rejected, failed, stopped = ledger.events
    assert not rejected.validation.accepted
    assert rejected.costs["attempt"] == 1
    assert rejected.costs["measurement"] == 0
    assert rejected.observation is None

    assert failed.validation.accepted
    assert failed.observation.status == "failed"
    assert failed.costs["attempt"] == 1
    assert failed.costs["measurement"] == 1
    assert failed.observation.qc_flags == (
        "execution_exception:TimeoutError",
        "operation:measure",
    )

    assert stopped.stop.final_hypothesis == "a"
    assert stopped.costs["attempt"] == stopped.costs["measurement"] == 0
    assert planner.seen_states[1].remaining_attempt_budget == 3
    assert planner.seen_states[1].remaining_measurement_budget == 3
    assert not hasattr(planner.seen_states[0], "private_truth")


def test_ledger_roundtrip_is_deterministic_and_tamper_evident(tmp_path) -> None:
    ledger = CampaignRunner().run(ScriptedPlanner(), scenario())
    first = ledger.to_json()
    path = tmp_path / "ledger.json"
    ledger.write_json(path)
    restored = EvidenceLedger.read_json(path)
    assert restored.verify()
    assert restored.to_json() == first

    raw = restored.to_dict()
    raw["events"][0]["costs"]["attempt"] = 99
    try:
        EvidenceLedger.from_dict(raw)
    except ValueError as exc:
        assert "hash" in str(exc)
    else:
        raise AssertionError("tampered ledger was accepted")


class NeverStopPlanner:
    name = "never-stop"
    version = "1"

    def __init__(self):
        self.n = 0

    def propose(self, state, planner_rng):
        self.n += 1
        return ExperimentRequest(f"r{self.n}", "measure", {"x": 1}, "continue")


def test_runner_stops_at_measurement_budget() -> None:
    ledger = CampaignRunner().run(NeverStopPlanner(), scenario(attempts=9, measurements=2))
    assert len(ledger.events) == 2
    assert ledger.events[-1].costs["cumulative_measurement"] == 2
