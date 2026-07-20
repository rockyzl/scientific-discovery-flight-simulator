import json
from dataclasses import dataclass

import pytest

from discovery_flight_simulator.artifacts import COMMITMENT_ALGORITHM, seed_commitment
from discovery_flight_simulator.cli import compare
from discovery_flight_simulator.contracts import (
    ExperimentRequest,
    InstrumentCapabilities,
    Observation,
    PublicWorldSpec,
    SeedBundle,
    StopDecision,
)


class Environment:
    def execute(self, request):
        return Observation("ok", request.controls, request.controls, 1.0, 0.1, (), 0, 0)


@dataclass
class Scenario:
    public_spec: PublicWorldSpec
    capabilities: InstrumentCapabilities
    seed_bundle: SeedBundle
    scenario_identity: dict
    private_truth: dict

    def environment_factory(self, seeds):
        return Environment()


class OneShotPlanner:
    name = "one-shot"
    version = "7"

    def __init__(self):
        self.done = False

    def propose(self, state, planner_rng):
        if not self.done:
            self.done = True
            return ExperimentRequest("r1", "measure", {"x": 0.5}, "probe")
        return StopDecision("done", "linear", 0.8)


REPLAY_KEY = "cli-test-private-key"


def load_scenario(path, private_seed_key=None):
    del path
    replay_key = private_seed_key or REPLAY_KEY
    seeds = SeedBundle(1, 2, 3, 4)
    commitments = {
        "algorithm": COMMITMENT_ALGORITHM,
        **{
            name: seed_commitment(replay_key, name, getattr(seeds, name))
            for name in ("world_seed", "noise_seed", "failure_seed")
        },
    }
    return Scenario(
        PublicWorldSpec("toy", "1", {"x": (0, 1)}, ("measure",), 3, 2),
        InstrumentCapabilities({"x": (0, 1)}, ("measure",)),
        seeds,
        {"id": "toy", "seed_commitments": commitments},
        {"answer": "linear", "replay_key": replay_key, "private_seeds": seeds},
    )


def test_compare_writes_exact_artifact_layout_and_fails_closed(tmp_path) -> None:
    output = tmp_path / "run"
    result = compare(
        "unused.json",
        output,
        private_seed_key=REPLAY_KEY,
        load_scenario_fn=load_scenario,
        planner_registry_fn=lambda: {
            "random": OneShotPlanner,
            "fixed_grid": OneShotPlanner,
            "information_gain": OneShotPlanner,
        },
        evaluation_fn=lambda ledger, truth: {
            "correct": truth["answer"] == "linear",
            "post_run_reveal": {
                "answer": truth["answer"],
                "replay_key": truth["replay_key"],
                "private_seeds": {
                    name: getattr(truth["private_seeds"], name)
                    for name in ("world_seed", "noise_seed", "failure_seed")
                },
            },
        },
    )
    assert result == output
    assert sorted(path.relative_to(output).as_posix() for path in output.rglob("*.json")) == [
        "ledgers/fixed_grid.json",
        "ledgers/information_gain.json",
        "ledgers/random.json",
        "manifest.json",
        "summary.json",
    ]
    manifest = json.loads((output / "manifest.json").read_text())
    summary = json.loads((output / "summary.json").read_text())
    ledger = json.loads((output / "ledgers/random.json").read_text())
    assert manifest["provenance"] == summary["provenance"] == ledger["provenance"] == "simulated"
    assert manifest["world_version"] == summary["world_version"] == ledger["world"]["world_version"] == "1"
    assert summary["results"]["random"]["metrics"]["correct"] is True
    assert summary["post_run_reveal"]["answer"] == "linear"
    assert "post_run_reveal" not in manifest
    assert "post_run_reveal" not in ledger
    assert manifest["seeds"]["planner_seed"] == 4
    assert manifest["seeds"]["commitments"]["world_seed"] != "1"
    assert "replay_key" not in manifest

    with pytest.raises(FileExistsError):
        compare(
            "unused.json",
            output,
            private_seed_key=REPLAY_KEY,
            load_scenario_fn=load_scenario,
            planner_registry_fn=lambda: {
                "random": OneShotPlanner,
                "fixed_grid": OneShotPlanner,
                "information_gain": OneShotPlanner,
            },
            evaluation_fn=lambda ledger, truth: {},
        )
