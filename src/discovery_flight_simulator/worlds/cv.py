"""Transparent synthetic CV mechanism-discrimination world.

This is a teaching emulator.  It intentionally represents only three frozen current-scaling
hypotheses and must not be used as a property predictor or a complete cyclic-voltammetry model.
"""

from __future__ import annotations

import math
from collections import Counter
from typing import Any

from discovery_flight_simulator.contracts import ExperimentRequest, Observation, SeedBundle

from .common import drift_at_attempt, failure_schedule, indexed_gaussian

MECHANISMS = ("diffusion", "surface", "mixed")
REFERENCE_VALUE = 1.0


def response_for(mechanism: str, scan_rate_mv_s: float) -> float:
    """Frozen normalized response models exposed to all planners."""

    x = scan_rate_mv_s / 100.0
    if mechanism == "diffusion":
        return 1.05 * math.sqrt(x)
    if mechanism == "surface":
        return 0.55 * x
    if mechanism == "mixed":
        return 0.58 * math.sqrt(x) + 0.24 * x
    raise ValueError(f"unknown CV mechanism: {mechanism}")


def build_truth(config: dict[str, Any], seeds: SeedBundle) -> dict[str, Any]:
    configured = config.get("private", {}).get("mechanism")
    mechanism = configured or MECHANISMS[seeds.world_seed % len(MECHANISMS)]
    if mechanism not in MECHANISMS:
        raise ValueError(f"unsupported hidden mechanism: {mechanism}")
    schedule = failure_schedule(config.get("failure_profile", {}), seeds.failure_seed)
    return {
        "world_type": "cv_mechanism",
        "mechanism": mechanism,
        "response_parameters": {
            "diffusion": "1.05 * sqrt(scan_rate_mV_s / 100)",
            "surface": "0.55 * (scan_rate_mV_s / 100)",
            "mixed": "0.58 * sqrt(scan_rate_mV_s / 100) + 0.24 * (scan_rate_mV_s / 100)",
        },
        "noise_sigma": float(config["world"]["noise_sigma"]),
        "failure_schedule": schedule,
        "provenance": "simulated",
        "scientific_scope": "transparent teaching emulator; not a complete CV model",
    }


class CVMechanismEnvironment:
    """Stateful instrument emulator with deterministic noise and failures."""

    def __init__(self, config: dict[str, Any], seeds: SeedBundle):
        self._truth = build_truth(config, seeds)
        self._noise_seed = seeds.noise_seed
        self._attempt_index = 0
        self._condition_counts: Counter[str] = Counter()

    @property
    def attempt_index(self) -> int:
        return self._attempt_index

    def execute(self, request: ExperimentRequest) -> Observation:
        # Only validator-accepted requests reach the environment. Failed valid measurements still
        # advance this attempt-indexed instrument schedule.
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

        drift = drift_at_attempt(schedule, attempt)
        sigma = float(self._truth["noise_sigma"])

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

        rate = float(request.controls["scan_rate_mv_s"])
        condition = f"measure:{rate:.12g}"
        repeat = self._condition_counts[condition]
        self._condition_counts[condition] += 1
        noiseless = response_for(self._truth["mechanism"], rate)
        value = noiseless + drift + indexed_gaussian(
            self._noise_seed, condition, repeat, sigma
        )
        flags: list[str] = []
        saturation = schedule.get("saturation_threshold")
        if saturation is not None and value > float(saturation):
            value = float(saturation)
            flags.append("saturated")
        return Observation(
            status="ok",
            requested_controls={"scan_rate_mv_s": rate},
            executed_controls={"scan_rate_mv_s": rate},
            value=value,
            standard_error=sigma,
            qc_flags=tuple(flags),
            attempt_cost=1,
            measurement_cost=1,
        )
