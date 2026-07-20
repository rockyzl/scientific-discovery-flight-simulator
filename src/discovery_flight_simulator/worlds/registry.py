"""Scenario loading and scientific-world registry."""

from __future__ import annotations

import hashlib
import hmac
import json
import secrets
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from discovery_flight_simulator.artifacts import COMMITMENT_ALGORITHM, seed_commitment
from discovery_flight_simulator.contracts import (
    InstrumentCapabilities,
    PublicWorldSpec,
    SeedBundle,
)

from .cv import CVMechanismEnvironment, build_truth as build_cv_truth
from .microscopy import (
    MicroscopyBoundaryEnvironment,
    build_truth as build_microscopy_truth,
)


@dataclass(frozen=True)
class LoadedScenario:
    public_spec: PublicWorldSpec
    capabilities: InstrumentCapabilities
    seed_bundle: SeedBundle
    private_truth: dict[str, Any]
    scenario_identity: dict[str, Any]
    _config: dict[str, Any]
    _environment_builder: Callable[[dict[str, Any], SeedBundle], Any]

    def environment_factory(self, seed_bundle: SeedBundle):
        return self._environment_builder(self._config, seed_bundle)


def _sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _derive_seed(key: str, scenario_sha256: str, purpose: str) -> int:
    digest = hmac.new(
        key.encode("utf-8"),
        f"{scenario_sha256}:{purpose}".encode("utf-8"),
        hashlib.sha256,
    ).digest()
    return int.from_bytes(digest[:8], "big") & ((1 << 63) - 1)


def load_scenario(path: str | Path, private_seed_key: str | None = None) -> LoadedScenario:
    scenario_path = Path(path)
    raw = scenario_path.read_bytes()
    config = json.loads(raw)
    world = config["world"]
    scenario_sha256 = _sha256_bytes(raw)
    replay_key = private_seed_key or secrets.token_hex(32)
    private_seeds = {
        purpose: _derive_seed(replay_key, scenario_sha256, purpose)
        for purpose in ("world_seed", "noise_seed", "failure_seed")
    }
    seeds = SeedBundle(
        **private_seeds,
        planner_seed=int(config["planner_seed"]),
    )
    controls = {
        name: (float(bounds[0]), float(bounds[1]))
        for name, bounds in world["controls"].items()
    }
    spec = PublicWorldSpec(
        world_id=world["world_id"],
        world_version=world["world_version"],
        controls=controls,
        operations=tuple(world["operations"]),
        total_attempt_budget=int(world["total_attempt_budget"]),
        total_measurement_budget=int(world["total_measurement_budget"]),
        provenance="simulated",
    )
    capabilities = InstrumentCapabilities(
        control_ranges=controls,
        operations=tuple(world["operations"]),
    )

    world_type = world["type"]
    if world_type == "cv_mechanism":
        builder = CVMechanismEnvironment
        truth = build_cv_truth(config, seeds)
    elif world_type == "microscopy_boundary":
        builder = MicroscopyBoundaryEnvironment
        truth = build_microscopy_truth(config, seeds)
    else:
        raise ValueError(f"unknown scientific world type: {world_type}")

    truth["replay_key"] = replay_key
    truth["private_seeds"] = private_seeds
    truth["planner_seed"] = seeds.planner_seed
    identity = {
        "scenario_id": config["scenario_id"],
        "scenario_version": config["scenario_version"],
        "scenario_sha256": scenario_sha256,
        "world_type": world_type,
        "provenance": "simulated",
        "planner_seed": seeds.planner_seed,
        "seed_commitments": {
            "algorithm": COMMITMENT_ALGORITHM,
            **{
                purpose: seed_commitment(replay_key, purpose, seed)
                for purpose, seed in private_seeds.items()
            },
        },
    }
    return LoadedScenario(
        public_spec=spec,
        capabilities=capabilities,
        seed_bundle=seeds,
        private_truth=truth,
        scenario_identity=identity,
        _config=config,
        _environment_builder=builder,
    )
