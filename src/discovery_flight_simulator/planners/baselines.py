"""Shared-inference baselines whose only intended difference is experiment selection."""

from __future__ import annotations

import math
from typing import Any

from discovery_flight_simulator.contracts import (
    ExperimentRequest,
    Observation,
    PublicCampaignState,
    StopDecision,
)
from discovery_flight_simulator.worlds.cv import MECHANISMS, response_for
from discovery_flight_simulator.worlds.microscopy import (
    BOUNDARY_CANDIDATES,
    response_for_boundary,
)


def _entropy(probabilities: dict[str, float]) -> float:
    return -sum(value * math.log(value) for value in probabilities.values() if value > 0.0)


def _normal_likelihood(value: float, mean: float, sigma: float) -> float:
    z = (value - mean) / max(sigma, 1e-9)
    return math.exp(-0.5 * z * z) / max(sigma, 1e-9)


def _logsumexp(values: list[float]) -> float:
    maximum = max(values)
    if not math.isfinite(maximum):
        return maximum
    return maximum + math.log(sum(math.exp(value - maximum) for value in values))


def _normalize(weights: dict[str, float]) -> dict[str, float]:
    total = sum(weights.values())
    if total <= 0.0 or not math.isfinite(total):
        uniform = 1.0 / len(weights)
        return {name: uniform for name in weights}
    return {name: value / total for name, value in weights.items()}


def _is_calibration(observation: Observation) -> bool:
    return "calibration" in observation.qc_flags or "operation:calibrate" in observation.qc_flags


class SharedInferencePlanner:
    """Common posterior, stopping, and recovery logic for fair policy comparisons."""

    version = "0.1.0"
    confidence_threshold = 0.90
    minimum_successful_measurements = 3

    def __init__(self) -> None:
        self.public_beliefs: dict[str, float] = {}
        self._world_type: str | None = None
        self._request_counter = 0
        self._successful_measurements = 0
        self._calibration_offset = 0.0

    def get_public_beliefs(self) -> dict[str, float]:
        return dict(self.public_beliefs)

    def _ensure_world(self, state: PublicCampaignState) -> None:
        if "cv" in state.spec.world_id:
            world_type = "cv_mechanism"
            labels = MECHANISMS
        elif "microscopy" in state.spec.world_id:
            world_type = "microscopy_boundary"
            labels = tuple(f"boundary_{value:.3f}" for value in BOUNDARY_CANDIDATES)
        else:
            raise ValueError(f"unsupported public world: {state.spec.world_id}")
        if self._world_type is None:
            self._world_type = world_type
            probability = 1.0 / len(labels)
            self.public_beliefs = {label: probability for label in labels}
        elif self._world_type != world_type:
            raise RuntimeError("a planner instance cannot be reused across different worlds")

    def _request(self, operation: str, controls: dict[str, float], rationale: str) -> ExperimentRequest:
        self._request_counter += 1
        return ExperimentRequest(
            request_id=f"{self.name}-{self._request_counter:03d}",
            operation=operation,
            controls=controls,
            rationale=rationale,
        )

    def _best(self) -> tuple[str, float]:
        if not self.public_beliefs:
            return "insufficient_evidence", 0.0
        return max(self.public_beliefs.items(), key=lambda item: (item[1], item[0]))

    def _stop_if_ready(self, state: PublicCampaignState) -> StopDecision | None:
        label, confidence = self._best()
        no_budget = state.remaining_attempt_budget <= 0 or state.remaining_measurement_budget <= 0
        confident = (
            self._successful_measurements >= self.minimum_successful_measurements
            and confidence >= self.confidence_threshold
        )
        if confident or no_budget:
            reason = "confidence threshold reached" if confident else "campaign budget exhausted"
            return StopDecision(reason=reason, final_hypothesis=label, confidence=confidence)
        return None

    def _maintenance_or_recovery(self, state: PublicCampaignState) -> ExperimentRequest | None:
        if not state.observations and "calibrate" in state.spec.operations:
            return self._request("calibrate", {}, "Establish the simulated reference baseline.")

        if state.observations:
            last = state.observations[-1]
            if "timeout" in last.qc_flags and last.requested_controls:
                return self._request(
                    "measure",
                    dict(last.requested_controls),
                    "Retry once after the recorded simulated timeout.",
                )
            if "saturated" in last.qc_flags and "scan_rate_mv_s" in last.requested_controls:
                low, _ = state.spec.controls["scan_rate_mv_s"]
                lower = max(low, last.requested_controls["scan_rate_mv_s"] / 2.0)
                return self._request(
                    "measure",
                    {"scan_rate_mv_s": lower},
                    "Reduce scan rate after the simulated saturation flag.",
                )

        if "calibrate" in state.spec.operations and state.remaining_measurement_budget >= 2:
            since_calibration = 0
            for observation in reversed(state.observations):
                if _is_calibration(observation):
                    break
                since_calibration += 1
            if since_calibration >= 4:
                return self._request(
                    "calibrate", {}, "Recheck reference after four simulated measurements."
                )
        return None

    def observe(self, observation: Observation, state: PublicCampaignState) -> None:
        del state  # all belief-relevant information is in the immutable public observation
        if observation.value is None or observation.status != "ok":
            return
        if _is_calibration(observation):
            expected = 1.0 if self._world_type == "cv_mechanism" else 0.5
            self._calibration_offset = float(observation.value) - expected
            return
        if "saturated" in observation.qc_flags:
            return

        value = float(observation.value) - self._calibration_offset
        sigma = float(observation.standard_error or 0.05)
        weights: dict[str, float] = {}
        if self._world_type == "cv_mechanism":
            rate = float(observation.executed_controls["scan_rate_mv_s"])
            for label, prior in self.public_beliefs.items():
                weights[label] = prior * _normal_likelihood(value, response_for(label, rate), sigma)
        elif self._world_type == "microscopy_boundary":
            position = float(observation.executed_controls["position"])
            for label, prior in self.public_beliefs.items():
                boundary = float(label.removeprefix("boundary_"))
                mean = response_for_boundary(boundary, position)
                weights[label] = prior * _normal_likelihood(value, mean, sigma)
        else:
            return
        self.public_beliefs = _normalize(weights)
        self._successful_measurements += 1

    def _begin(self, state: PublicCampaignState) -> ExperimentRequest | StopDecision | None:
        self._ensure_world(state)
        stop = self._stop_if_ready(state)
        if stop is not None:
            return stop
        return self._maintenance_or_recovery(state)


class RandomValidPlanner(SharedInferencePlanner):
    name = "random"

    def propose(self, state: PublicCampaignState, planner_rng: Any):
        early = self._begin(state)
        if early is not None:
            return early
        control, (low, high) = next(iter(state.spec.controls.items()))
        value = float(planner_rng.uniform(low, high))
        return self._request(
            "measure", {control: value}, "Random valid control sampled from the public range."
        )


class FixedGridPlanner(SharedInferencePlanner):
    name = "fixed_grid"

    def __init__(self) -> None:
        super().__init__()
        self._grid_index = 0

    def propose(self, state: PublicCampaignState, planner_rng: Any):
        del planner_rng
        early = self._begin(state)
        if early is not None:
            return early
        control, (low, high) = next(iter(state.spec.controls.items()))
        if control == "scan_rate_mv_s":
            count = 9
            fraction = (self._grid_index % count) / (count - 1)
            if fraction == 0.0:
                value = low
            elif fraction == 1.0:
                value = high
            else:
                value = math.exp(math.log(low) + fraction * (math.log(high) - math.log(low)))
        else:
            count = 9
            fraction = (self._grid_index % count) / (count - 1)
            value = low + fraction * (high - low)
        self._grid_index += 1
        return self._request(
            "measure", {control: value}, "Next point in the fixed public expert grid."
        )


class ExpectedInformationGainPlanner(SharedInferencePlanner):
    name = "information_gain"

    def _predicted_value(self, label: str, control: str, value: float) -> float:
        if control == "scan_rate_mv_s":
            return response_for(label, value)
        boundary = float(label.removeprefix("boundary_"))
        return response_for_boundary(boundary, value)

    def _expected_information_gain(self, control: str, value: float, sigma: float) -> float:
        """Integrate posterior entropy over the public noisy predictive mixture.

        Candidate response functions, priors, and noise are public benchmark assumptions. The
        selected hidden mechanism/boundary and future failures never enter this computation.
        """

        current_entropy = _entropy(self.public_beliefs)
        labels = tuple(self.public_beliefs)
        means = {label: self._predicted_value(label, control, value) for label in labels}
        lower = min(means.values()) - 6.0 * sigma
        upper = max(means.values()) + 6.0 * sigma
        points = 161
        step = (upper - lower) / (points - 1)
        entropy_integral = 0.0
        predictive_mass = 0.0
        normal_log_constant = -math.log(max(sigma, 1e-12)) - 0.5 * math.log(2.0 * math.pi)
        for index in range(points):
            outcome = lower + index * step
            log_joint = []
            for label in labels:
                prior = max(self.public_beliefs[label], 1e-300)
                z = (outcome - means[label]) / max(sigma, 1e-12)
                log_joint.append(math.log(prior) + normal_log_constant - 0.5 * z * z)
            log_predictive = _logsumexp(log_joint)
            predictive = math.exp(log_predictive)
            posterior = {
                label: math.exp(log_value - log_predictive)
                for label, log_value in zip(labels, log_joint, strict=True)
            }
            trapezoid_weight = 0.5 if index in (0, points - 1) else 1.0
            predictive_mass += trapezoid_weight * predictive
            entropy_integral += trapezoid_weight * predictive * _entropy(posterior)
        expected_entropy = entropy_integral / max(predictive_mass, 1e-300)
        return max(0.0, current_entropy - expected_entropy)

    def propose(self, state: PublicCampaignState, planner_rng: Any):
        del planner_rng
        early = self._begin(state)
        if early is not None:
            return early
        control, (low, high) = next(iter(state.spec.controls.items()))
        if control == "scan_rate_mv_s":
            candidates = [
                math.exp(math.log(low) + index / 20.0 * (math.log(high) - math.log(low)))
                for index in range(21)
            ]
            sigma = 0.05
        else:
            candidates = [low + index / 20.0 * (high - low) for index in range(21)]
            sigma = 0.025
        scored = [
            (self._expected_information_gain(control, value, sigma), -value, value)
            for value in candidates
        ]
        _, _, selected = max(scored)
        return self._request(
            "measure",
            {control: selected},
            "Select the public candidate with maximum expected information gain.",
        )
