"""Small one-dimensional microscopy boundary-localization transfer world."""

from __future__ import annotations

import math
from collections import Counter
from typing import Any

from discovery_flight_simulator.contracts import ExperimentRequest, Observation, SeedBundle

from .common import drift_at_attempt, failure_schedule, indexed_gaussian

BOUNDARY_CANDIDATES = tuple(round(0.2 + index * 0.075, 3) for index in range(9))
LEFT_LEVEL = 0.2
RIGHT_LEVEL = 0.8
TRANSITION_WIDTH = 0.025
REFERENCE_VALUE = 0.5


def response_for_boundary(boundary: float, position: float) -> float:
    exponent = max(-60.0, min(60.0, -(position - boundary) / TRANSITION_WIDTH))
    transition = 1.0 / (1.0 + math.exp(exponent))
    return LEFT_LEVEL + (RIGHT_LEVEL - LEFT_LEVEL) * transition


def build_truth(config: dict[str, Any], seeds: SeedBundle) -> dict[str, Any]:
    configured = config.get("private", {}).get("boundary")
    boundary = (
        float(configured)
        if configured is not None
        else BOUNDARY_CANDIDATES[seeds.world_seed % len(BOUNDARY_CANDIDATES)]
    )
    schedule = failure_schedule(config.get("failure_profile", {}), seeds.failure_seed)
    return {
        "world_type": "microscopy_boundary",
        "boundary": boundary,
        "left_level": LEFT_LEVEL,
        "right_level": RIGHT_LEVEL,
        "transition_width": TRANSITION_WIDTH,
        "noise_sigma": float(config["world"]["noise_sigma"]),
        "failure_schedule": schedule,
        "provenance": "simulated",
        "scientific_scope": "interface-transfer fixture; not a microscopy image model",
    }


class MicroscopyBoundaryEnvironment:
    def __init__(self, config: dict[str, Any], seeds: SeedBundle):
        self._truth = build_truth(config, seeds)
        self._noise_seed = seeds.noise_seed
        self._attempt_index = 0
        self._condition_counts: Counter[str] = Counter()

    @property
    def attempt_index(self) -> int:
        return self._attempt_index

    def execute(self, request: ExperimentRequest) -> Observation:
        self._attempt_index += 1
        attempt = self._attempt_index
        schedule = self._truth["failure_schedule"]
        if attempt in schedule["timeout_attempts"]:
            return Observation(
                status="failed",
                requested_controls=dict(request.controls),
                executed_controls=dict(request.controls),
                value=None,
                standard_error=None,
                qc_flags=("timeout",),
                attempt_cost=1,
                measurement_cost=1,
            )

        sigma = float(self._truth["noise_sigma"])
        drift = drift_at_attempt(schedule, attempt)
        if request.operation == "calibrate":
            condition = "calibrate"
            repeat = self._condition_counts[condition]
            self._condition_counts[condition] += 1
            value = REFERENCE_VALUE + drift + indexed_gaussian(
                self._noise_seed, condition, repeat, sigma / 2.0
            )
            flags = ["calibration"]
            if abs(value - REFERENCE_VALUE) > 2.5 * sigma:
                flags.append("reference_out_of_tolerance")
            return Observation(
                status="ok",
                requested_controls={},
                executed_controls={},
                value=value,
                standard_error=sigma / 2.0,
                qc_flags=tuple(flags),
                attempt_cost=1,
                measurement_cost=1,
            )

        position = float(request.controls["position"])
        condition = f"measure:{position:.12g}"
        repeat = self._condition_counts[condition]
        self._condition_counts[condition] += 1
        value = response_for_boundary(self._truth["boundary"], position) + drift
        value += indexed_gaussian(self._noise_seed, condition, repeat, sigma)
        flags: list[str] = []
        saturation = schedule.get("saturation_threshold")
        if saturation is not None and value > float(saturation):
            value = float(saturation)
            flags.append("saturated")
        return Observation(
            status="ok",
            requested_controls={"position": position},
            executed_controls={"position": position},
            value=value,
            standard_error=sigma,
            qc_flags=tuple(flags),
            attempt_cost=1,
            measurement_cost=1,
        )
