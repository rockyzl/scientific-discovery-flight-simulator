"""Deterministic public-only recommendation policies for finite RFB V1 campaigns.

The policies in this module are deliberately stateless.  Every recommendation is
derived from a public scenario, public completed-outcome history, and the public
identities of actions that were rejected.  This keeps a recommendation replayable
without retaining execution state or consulting any hidden configuration.
"""

from __future__ import annotations

import math
from collections.abc import Iterable
from dataclasses import dataclass
from typing import Any, ClassVar

import numpy as np

from discovery_flight_simulator.ledger import sha256_json

from .contracts import (
    CANONICAL_ACTION_FIELDS,
    RFBActionV1,
    RFBOutcomeV1,
    RFBPlanningStateV1,
    RFBRecommendation,
    RFBRecommendationV1,
    RFBScenarioV1,
    rfb_campaign_event_logical_hash,
)
from .utility import utility_record_for_outcome


POLICY_CONTRACT_VERSION = "1"
_GENESIS_EVENT_HASH = "0" * 64


@dataclass(frozen=True)
class RFBPublicObservationV1:
    """One planner-visible action and its canonical public outcome.

    ``utility`` is optional audit data from a persisted event.  Policies do not
    optimize it directly: the constrained BO policy always recomputes utility
    from ``outcome`` through the scenario's frozen scalar utility.
    """

    action: RFBActionV1
    outcome: RFBOutcomeV1
    utility: float | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.action, RFBActionV1):
            raise ValueError("action must be an RFBActionV1")
        if not isinstance(self.outcome, RFBOutcomeV1):
            raise ValueError("outcome must be an RFBOutcomeV1")
        if self.utility is not None:
            if isinstance(self.utility, bool):
                raise ValueError("utility must be a finite number or None")
            try:
                utility = float(self.utility)
            except (TypeError, ValueError) as exc:
                raise ValueError("utility must be a finite number or None") from exc
            if not math.isfinite(utility):
                raise ValueError("utility must be a finite number or None")
            object.__setattr__(self, "utility", utility)

    @property
    def action_id(self) -> str:
        """Return the canonical identity of the observed action."""

        return self.action.identity_sha256

    def scalar_utility(self, scenario: RFBScenarioV1) -> float:
        """Score this canonical outcome using only the scenario's frozen utility."""

        if not isinstance(scenario, RFBScenarioV1):
            raise ValueError("scenario must be an RFBScenarioV1")
        return utility_record_for_outcome(self.outcome, scenario.utility).utility

    def to_dict(self) -> dict[str, Any]:
        """Return the public, deterministic event payload used for policy hashes."""

        return {
            "action": self.action.to_dict(),
            "outcome": self.outcome.to_dict(),
            "utility": self.utility,
        }


# Shorter aliases make the record convenient at policy call sites while retaining
# the versioned canonical name above for persisted interfaces.
RFBPublicObservation = RFBPublicObservationV1
PublicRFBObservationV1 = RFBPublicObservationV1


class RFBPolicyV1:
    """Stateless base class for a public RFB V1 recommendation policy."""

    policy_id: ClassVar[str]
    policy_version: ClassVar[str] = POLICY_CONTRACT_VERSION

    def recommend(
        self,
        planning_state: RFBPlanningStateV1 | RFBScenarioV1,
        observations: Iterable[RFBPublicObservationV1] = (),
        rejected_action_ids: Iterable[str] = (),
    ) -> RFBRecommendationV1 | None:
        """Return one declared untried candidate, or ``None`` when exhausted."""

        raise NotImplementedError

    def propose(
        self,
        planning_state: RFBPlanningStateV1 | RFBScenarioV1,
        observations: Iterable[RFBPublicObservationV1] = (),
        rejected_action_ids: Iterable[str] = (),
    ) -> RFBRecommendationV1 | None:
        """Alias for callers using a planner-style ``propose`` operation."""

        return self.recommend(planning_state, observations, rejected_action_ids)


class FixedGridRFBPolicy(RFBPolicyV1):
    """Visit declared candidates in public scenario order."""

    policy_id = "fixed_grid"

    def recommend(
        self,
        planning_state: RFBPlanningStateV1 | RFBScenarioV1,
        observations: Iterable[RFBPublicObservationV1] = (),
        rejected_action_ids: Iterable[str] = (),
    ) -> RFBRecommendationV1 | None:
        state, history, rejections, available = _recommendation_context(
            planning_state, observations, rejected_action_ids
        )
        del history, rejections
        if not available:
            return None
        return _recommendation(
            policy=self,
            planning_state=state,
            action=available[0],
            predicted_mean=None,
            predicted_std=None,
            rationale="Select the first untried candidate in declared scenario order.",
        )


class RandomRFBPolicy(RFBPolicyV1):
    """Select a candidate from a deterministic hash of public history."""

    policy_id = "random"

    def recommend(
        self,
        planning_state: RFBPlanningStateV1 | RFBScenarioV1,
        observations: Iterable[RFBPublicObservationV1] = (),
        rejected_action_ids: Iterable[str] = (),
    ) -> RFBRecommendationV1 | None:
        state, history, rejections, available = _recommendation_context(
            planning_state, observations, rejected_action_ids
        )
        del history, rejections
        if not available:
            return None
        selection_digest = sha256_json(
            {
                "policy_id": self.policy_id,
                "policy_version": self.policy_version,
                "public_projection_sha256": state.scenario.public_projection_sha256,
                "candidate_set_sha256": state.scenario.candidate_set_sha256,
                "utility_sha256": state.scenario.utility_sha256,
                "basis_event_head_sha256": state.event_head_sha256,
                "basis_revision": state.revision,
                "remaining_attempt_budget": state.remaining_attempt_budget,
                "remaining_measurement_budget": state.remaining_measurement_budget,
                "available_action_ids": [action.identity_sha256 for action in available],
            }
        )
        action = available[int(selection_digest, 16) % len(available)]
        return _recommendation(
            policy=self,
            planning_state=state,
            action=action,
            predicted_mean=None,
            predicted_std=None,
            rationale="Select a valid untried candidate from deterministic public-history sampling.",
        )


class ConstrainedBORFBPolicy(RFBPolicyV1):
    """Finite-candidate Gaussian-process UCB policy over public scalar utilities."""

    policy_id = "constrained_bo"
    length_scale: ClassVar[float] = 0.35
    signal_variance: ClassVar[float] = 1.0
    observation_noise_variance: ClassVar[float] = 1e-6
    ucb_multiplier: ClassVar[float] = 1.96

    def recommend(
        self,
        planning_state: RFBPlanningStateV1 | RFBScenarioV1,
        observations: Iterable[RFBPublicObservationV1] = (),
        rejected_action_ids: Iterable[str] = (),
    ) -> RFBRecommendationV1 | None:
        state, history, rejections, available = _recommendation_context(
            planning_state, observations, rejected_action_ids
        )
        del rejections
        if not available:
            return None

        means, stds = self._predict_public_utilities(state.scenario, history, available)
        ucb = means + self.ucb_multiplier * stds
        selected_index = int(np.argmax(ucb))
        return _recommendation(
            policy=self,
            planning_state=state,
            action=available[selected_index],
            predicted_mean=float(means[selected_index]),
            predicted_std=float(stds[selected_index]),
            rationale="Select the valid untried candidate with maximum deterministic scalar-utility UCB.",
        )

    def _predict_public_utilities(
        self,
        scenario: RFBScenarioV1,
        observations: tuple[RFBPublicObservationV1, ...],
        candidates: tuple[RFBActionV1, ...],
    ) -> tuple[np.ndarray, np.ndarray]:
        """Return GP predictive moments from declared actions and completed public outcomes."""

        declared = _finite_declared_candidates(scenario)
        feature_by_action_id = {
            action.identity_sha256: features
            for action, features in zip(declared, _normalized_features(declared), strict=True)
        }
        candidate_features = np.asarray(
            [feature_by_action_id[action.identity_sha256] for action in candidates], dtype=float
        )

        training_features: list[np.ndarray] = []
        training_utilities: list[float] = []
        for observation in observations:
            action_features = feature_by_action_id.get(observation.action_id)
            if action_features is None or observation.outcome.status != "complete":
                continue
            utility = observation.scalar_utility(scenario)
            if math.isfinite(utility):
                training_features.append(action_features)
                training_utilities.append(utility)

        if not training_features:
            prior_std = math.sqrt(self.signal_variance)
            return np.zeros(len(candidates), dtype=float), np.full(
                len(candidates), prior_std, dtype=float
            )

        train_x = np.asarray(training_features, dtype=float)
        train_y = np.asarray(training_utilities, dtype=float)
        kernel_train = self._rbf_kernel(train_x, train_x)
        kernel_train += np.eye(len(train_x), dtype=float) * self.observation_noise_variance
        kernel_cross = self._rbf_kernel(train_x, candidate_features)
        try:
            alpha = np.linalg.solve(kernel_train, train_y)
            solved_cross = np.linalg.solve(kernel_train, kernel_cross)
        except np.linalg.LinAlgError:
            inverse = np.linalg.pinv(kernel_train, rcond=1e-12)
            alpha = inverse @ train_y
            solved_cross = inverse @ kernel_cross
        means = kernel_cross.T @ alpha
        variances = self.signal_variance - np.sum(kernel_cross * solved_cross, axis=0)
        return means, np.sqrt(np.maximum(variances, 0.0))

    def _rbf_kernel(self, left: np.ndarray, right: np.ndarray) -> np.ndarray:
        differences = left[:, np.newaxis, :] - right[np.newaxis, :, :]
        squared_distance = np.sum(differences * differences, axis=2)
        return self.signal_variance * np.exp(
            -0.5 * squared_distance / (self.length_scale * self.length_scale)
        )


# Conventional names for users who do not need the domain prefix in imports.
FixedGridPolicy = FixedGridRFBPolicy
RandomPolicy = RandomRFBPolicy
ConstrainedBOPolicy = ConstrainedBORFBPolicy


def recommend_fixed_grid(
    planning_state: RFBPlanningStateV1 | RFBScenarioV1,
    observations: Iterable[RFBPublicObservationV1] = (),
    rejected_action_ids: Iterable[str] = (),
) -> RFBRecommendationV1 | None:
    """Recommend the first available declared candidate in scenario order."""

    return FixedGridRFBPolicy().recommend(planning_state, observations, rejected_action_ids)


def recommend_random(
    planning_state: RFBPlanningStateV1 | RFBScenarioV1,
    observations: Iterable[RFBPublicObservationV1] = (),
    rejected_action_ids: Iterable[str] = (),
) -> RFBRecommendationV1 | None:
    """Recommend a deterministic public-history-derived available candidate."""

    return RandomRFBPolicy().recommend(planning_state, observations, rejected_action_ids)


def recommend_constrained_bo(
    planning_state: RFBPlanningStateV1 | RFBScenarioV1,
    observations: Iterable[RFBPublicObservationV1] = (),
    rejected_action_ids: Iterable[str] = (),
) -> RFBRecommendationV1 | None:
    """Recommend the maximum-UCB available candidate from public scalar utilities."""

    return ConstrainedBORFBPolicy().recommend(planning_state, observations, rejected_action_ids)


def public_event_head_hash(
    observations: Iterable[RFBPublicObservationV1] = (),
    rejected_action_ids: Iterable[str] = (),
) -> str:
    """Derive the deterministic public event-chain head used by recommendations."""

    history = _normalize_observations(observations)
    rejections = _normalize_rejected_action_ids(rejected_action_ids)
    return _public_event_head_hash(history, rejections)


def _recommendation_context(
    planning_state: RFBPlanningStateV1 | RFBScenarioV1,
    observations: Iterable[RFBPublicObservationV1],
    rejected_action_ids: Iterable[str],
) -> tuple[
    RFBPlanningStateV1,
    tuple[RFBPublicObservationV1, ...],
    tuple[str, ...],
    tuple[RFBActionV1, ...],
]:
    history = _normalize_observations(observations)
    rejections = _normalize_rejected_action_ids(rejected_action_ids)
    state = _normalize_planning_state(planning_state, history, rejections)
    candidates = _finite_declared_candidates(state.scenario)
    candidate_ids = {candidate.identity_sha256 for candidate in candidates}
    tried_ids = {
        observation.action_id for observation in history if observation.action_id in candidate_ids
    }
    unavailable_ids = tried_ids | (set(rejections) & candidate_ids)
    available = tuple(
        candidate for candidate in candidates if candidate.identity_sha256 not in unavailable_ids
    )
    if state.remaining_attempt_budget == 0 or state.remaining_measurement_budget == 0:
        available = ()
    return state, history, rejections, available


def _normalize_planning_state(
    planning_state: RFBPlanningStateV1 | RFBScenarioV1,
    history: tuple[RFBPublicObservationV1, ...],
    rejections: tuple[str, ...],
) -> RFBPlanningStateV1:
    if isinstance(planning_state, RFBPlanningStateV1):
        return planning_state
    if isinstance(planning_state, RFBScenarioV1):
        # Preserve the pre-state policy API without weakening emitted V1 records:
        # the compatibility state remains fully anchored to its public history.
        return RFBPlanningStateV1(
            scenario=planning_state,
            event_head_sha256=_public_event_head_hash(history, rejections),
        )
    raise ValueError("planning_state must be an RFBPlanningStateV1")


def _finite_declared_candidates(scenario: RFBScenarioV1) -> tuple[RFBActionV1, ...]:
    """Filter defensively to finite candidates that are members of this public scenario."""

    return tuple(
        action
        for action in scenario.candidate_actions
        if _is_finite_action(action) and scenario.contains(action)
    )


def _is_finite_action(action: RFBActionV1) -> bool:
    if not isinstance(action, RFBActionV1):
        return False
    try:
        values = [float(getattr(action, name)) for name in CANONICAL_ACTION_FIELDS]
    except (AttributeError, TypeError, ValueError):
        return False
    return all(math.isfinite(value) for value in values)


def _normalized_features(candidates: tuple[RFBActionV1, ...]) -> np.ndarray:
    values = np.asarray(
        [[float(getattr(action, name)) for name in CANONICAL_ACTION_FIELDS] for action in candidates],
        dtype=float,
    )
    lower = np.min(values, axis=0)
    span = np.max(values, axis=0) - lower
    safe_span = np.where(span > 0.0, span, 1.0)
    return (values - lower) / safe_span


def _recommendation(
    *,
    policy: RFBPolicyV1,
    planning_state: RFBPlanningStateV1,
    action: RFBActionV1,
    predicted_mean: float | None,
    predicted_std: float | None,
    rationale: str,
) -> RFBRecommendationV1:
    scenario = planning_state.scenario
    return RFBRecommendationV1(
        action=action,
        policy_id=policy.policy_id,
        policy_version=policy.policy_version,
        public_projection_sha256=scenario.public_projection_sha256,
        candidate_set_sha256=scenario.candidate_set_sha256,
        utility_sha256=scenario.utility_sha256,
        basis_event_head_sha256=planning_state.event_head_sha256,
        basis_revision=planning_state.revision,
        remaining_attempt_budget=planning_state.remaining_attempt_budget,
        remaining_measurement_budget=planning_state.remaining_measurement_budget,
        predicted_utility_mean=predicted_mean,
        predicted_utility_std=predicted_std,
        rationale=rationale,
    )


def _normalize_observations(
    observations: Iterable[RFBPublicObservationV1],
) -> tuple[RFBPublicObservationV1, ...]:
    if isinstance(observations, (str, bytes)):
        raise ValueError("observations must be an iterable of RFBPublicObservationV1 values")
    try:
        history = tuple(observations)
    except TypeError as exc:
        raise ValueError("observations must be an iterable of RFBPublicObservationV1 values") from exc
    if not all(isinstance(observation, RFBPublicObservationV1) for observation in history):
        raise ValueError("observations must contain only RFBPublicObservationV1 values")
    return history


def _normalize_rejected_action_ids(rejected_action_ids: Iterable[str]) -> tuple[str, ...]:
    if isinstance(rejected_action_ids, (str, bytes)):
        raise ValueError("rejected_action_ids must be an iterable of action identity strings")
    try:
        raw_ids = tuple(rejected_action_ids)
    except TypeError as exc:
        raise ValueError("rejected_action_ids must be an iterable of action identity strings") from exc
    if not all(isinstance(action_id, str) and action_id for action_id in raw_ids):
        raise ValueError("rejected_action_ids must contain non-empty action identity strings")
    return tuple(sorted(set(raw_ids)))


def _public_event_head_hash(
    observations: tuple[RFBPublicObservationV1, ...], rejected_action_ids: tuple[str, ...]
) -> str:
    head = _GENESIS_EVENT_HASH
    for sequence, observation in enumerate(observations):
        head = rfb_campaign_event_logical_hash(
            event_type="execution_recorded",
            payload=observation.to_dict(),
            sequence=sequence,
            previous_event_sha256=head,
        )
    for offset, action_id in enumerate(rejected_action_ids, start=len(observations)):
        head = rfb_campaign_event_logical_hash(
            event_type="invalid_protocol_consumed",
            payload={"action_id": action_id},
            sequence=offset,
            previous_event_sha256=head,
        )
    return head


__all__ = [
    "POLICY_CONTRACT_VERSION",
    "ConstrainedBOPolicy",
    "ConstrainedBORFBPolicy",
    "FixedGridPolicy",
    "FixedGridRFBPolicy",
    "PublicRFBObservationV1",
    "RFBPolicyV1",
    "RFBPublicObservation",
    "RFBPublicObservationV1",
    "RFBRecommendation",
    "RFBRecommendationV1",
    "RandomPolicy",
    "RandomRFBPolicy",
    "public_event_head_hash",
    "recommend_constrained_bo",
    "recommend_fixed_grid",
    "recommend_random",
]
