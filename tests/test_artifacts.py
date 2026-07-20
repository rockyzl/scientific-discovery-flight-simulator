import json
from dataclasses import dataclass

import pytest

from discovery_flight_simulator.artifacts import (
    ArtifactVerificationError,
    COMMITMENT_ALGORITHM,
    seed_commitment,
    verify_artifact_bundle,
)
from discovery_flight_simulator.cli import compare
from discovery_flight_simulator.contracts import (
    ExperimentRequest,
    InstrumentCapabilities,
    Observation,
    PublicWorldSpec,
    SeedBundle,
    StopDecision,
)

REPLAY_KEY = "artifact-verification-key"


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


class Planner:
    name = "test-planner"
    version = "1"

    def __init__(self):
        self.done = False

    def propose(self, state, planner_rng):
        if not self.done:
            self.done = True
            return ExperimentRequest("r1", "measure", {"x": 0.5}, "probe")
        return StopDecision("done", "linear", 0.9)


def _scenario(path, private_seed_key=None):
    del path
    key = private_seed_key or REPLAY_KEY
    seeds = SeedBundle(11, 12, 13, 14)
    commitments = {
        "algorithm": COMMITMENT_ALGORITHM,
        **{
            name: seed_commitment(key, name, getattr(seeds, name))
            for name in ("world_seed", "noise_seed", "failure_seed")
        },
    }
    return Scenario(
        PublicWorldSpec("toy", "1", {"x": (0, 1)}, ("measure",), 3, 2),
        InstrumentCapabilities({"x": (0, 1)}, ("measure",)),
        seeds,
        {
            "scenario_id": "toy",
            "scenario_version": "1",
            "seed_commitments": commitments,
        },
        {"replay_key": key, "seeds": seeds},
    )


def _evaluation(ledger, truth):
    del ledger
    return {
        "ok": True,
        "post_run_reveal": {
            "replay_key": truth["replay_key"],
            "private_seeds": {
                name: getattr(truth["seeds"], name)
                for name in ("world_seed", "noise_seed", "failure_seed")
            },
            "truth": "linear",
        },
    }


def _make_bundle(tmp_path):
    output = tmp_path / "bundle"
    compare(
        "unused",
        output,
        private_seed_key=REPLAY_KEY,
        load_scenario_fn=_scenario,
        planner_registry_fn=lambda: {
            "random": Planner,
            "fixed_grid": Planner,
            "information_gain": Planner,
        },
        evaluation_fn=_evaluation,
    )
    return output


def _mutate_json(path, mutate):
    value = json.loads(path.read_text())
    mutate(value)
    path.write_text(json.dumps(value, sort_keys=True, indent=2) + "\n")


def test_verified_bundle_has_complete_cross_checked_artifacts(tmp_path) -> None:
    bundle = verify_artifact_bundle(_make_bundle(tmp_path))
    assert bundle.manifest["status"] == "complete"
    assert bundle.summary["status"] == "complete"
    assert set(bundle.ledgers) == {"random", "fixed_grid", "information_gain"}
    assert all(ledger.verify() for ledger in bundle.ledgers.values())


@pytest.mark.parametrize(
    ("target", "mutate"),
    [
        ("manifest.json", lambda value: value.__setitem__("world_version", "tampered")),
        (
            "summary.json",
            lambda value: value["post_run_reveal"].__setitem__("truth", "tampered"),
        ),
        (
            "ledgers/random.json",
            lambda value: value["events"][0]["costs"].__setitem__("attempt", 99),
        ),
        (
            "summary.json",
            lambda value: value["post_run_reveal"]["private_seeds"].__setitem__(
                "world_seed", 999
            ),
        ),
        (
            "summary.json",
            lambda value: value["scenario_identity"].__setitem__("scenario_id", "other"),
        ),
    ],
)
def test_tampered_manifest_summary_ledger_commitment_or_identity_fails(
    tmp_path, target, mutate
) -> None:
    output = _make_bundle(tmp_path)
    _mutate_json(output / target, mutate)
    with pytest.raises(ArtifactVerificationError):
        verify_artifact_bundle(output)

def test_missing_or_extra_artifact_fails_closed(tmp_path) -> None:
    output = _make_bundle(tmp_path)
    (output / "ledgers" / "random.json").unlink()
    with pytest.raises(ArtifactVerificationError):
        verify_artifact_bundle(output)

    output = _make_bundle(tmp_path / "second")
    (output / "unexpected.json").write_text("{}\n")
    with pytest.raises(ArtifactVerificationError):
        verify_artifact_bundle(output)
