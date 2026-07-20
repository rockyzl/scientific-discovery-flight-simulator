"""Campaign execution with explicit budgets and public/private separation."""

from __future__ import annotations

import copy
from dataclasses import replace
from typing import Any

import numpy as np

from .contracts import (
    ExperimentEvent,
    ExperimentRequest,
    Observation,
    PublicCampaignState,
    SeedBundle,
    StopDecision,
    ValidationResult,
)
from .ledger import EvidenceLedger
from .validator import ProtocolValidator


def _planner_beliefs(planner: Any) -> dict[str, float]:
    getter = getattr(planner, "get_public_beliefs", None)
    if callable(getter):
        value = getter()
    else:
        value = getattr(planner, "public_beliefs", {})
    if value is None:
        return {}
    return {str(name): float(probability) for name, probability in dict(value).items()}


def _failed_observation(request: ExperimentRequest, exc: Exception) -> Observation:
    return Observation(
        status="failed",
        requested_controls=request.controls,
        executed_controls=request.controls,
        value=None,
        standard_error=None,
        qc_flags=(f"execution_exception:{type(exc).__name__}",),
        attempt_cost=1,
        measurement_cost=1,
    )


class CampaignRunner:
    def __init__(self, validator: ProtocolValidator | None = None) -> None:
        self.validator = validator or ProtocolValidator()

    def run(
        self,
        planner: Any,
        scenario: Any,
        *,
        planner_name: str | None = None,
        planner_version: str | None = None,
        seed_bundle: SeedBundle | None = None,
    ) -> EvidenceLedger:
        seeds = seed_bundle or getattr(scenario, "seed_bundle", None)
        if not isinstance(seeds, SeedBundle):
            raise ValueError("CampaignRunner requires an explicit SeedBundle")

        spec = scenario.public_spec
        capabilities = scenario.capabilities
        environment = scenario.environment_factory(seeds)
        name = planner_name or getattr(planner, "name", type(planner).__name__)
        version = planner_version or getattr(planner, "version", "0")
        ledger = EvidenceLedger(spec, seeds, name, version, scenario.scenario_identity)
        planner_rng = np.random.default_rng(seeds.planner_seed)

        attempt_spent = 0
        measurement_spent = 0
        observations: list[Observation] = []
        request_ids: set[str] = set()

        while (
            attempt_spent < spec.total_attempt_budget
            and measurement_spent < spec.total_measurement_budget
        ):
            beliefs_before = _planner_beliefs(planner)
            state = PublicCampaignState(
                spec=copy.deepcopy(spec),
                observations=tuple(copy.deepcopy(observations)),
                remaining_attempt_budget=spec.total_attempt_budget - attempt_spent,
                remaining_measurement_budget=spec.total_measurement_budget - measurement_spent,
                public_beliefs=beliefs_before,
            )
            decision = planner.propose(state, planner_rng)

            if isinstance(decision, StopDecision):
                ledger.append(
                    ExperimentEvent(
                        sequence=len(ledger.events),
                        request=None,
                        stop=decision,
                        validation=None,
                        observation=None,
                        beliefs_before=beliefs_before,
                        beliefs_after=beliefs_before,
                        costs={
                            "attempt": 0,
                            "measurement": 0,
                            "cumulative_attempt": attempt_spent,
                            "cumulative_measurement": measurement_spent,
                        },
                        hashes={},
                    )
                )
                break

            if not isinstance(decision, ExperimentRequest):
                raise TypeError("planner must return ExperimentRequest or StopDecision")

            validation = self.validator.validate(decision, spec, capabilities)
            if decision.request_id in request_ids:
                validation = ValidationResult(
                    accepted=False,
                    reasons=("duplicate request_id",),
                    attempt_cost=1,
                    measurement_cost=0,
                )
            request_ids.add(decision.request_id)

            observation: Observation | None = None
            if validation.accepted:
                try:
                    observation = environment.execute(decision)
                except Exception as exc:  # a simulated instrument failure is evidence, not a crash
                    observation = _failed_observation(decision, exc)
                operation_flag = f"operation:{decision.operation}"
                qc_flags = observation.qc_flags
                if operation_flag not in qc_flags:
                    qc_flags = (*qc_flags, operation_flag)
                observation = replace(
                    observation,
                    qc_flags=qc_flags,
                    attempt_cost=1,
                    measurement_cost=1,
                )
                observations.append(observation)
                observer = getattr(planner, "observe", None)
                if callable(observer):
                    observer(observation, state)

            attempt_spent += validation.attempt_cost
            measurement_spent += validation.measurement_cost
            beliefs_after = _planner_beliefs(planner)
            ledger.append(
                ExperimentEvent(
                    sequence=len(ledger.events),
                    request=decision,
                    stop=None,
                    validation=validation,
                    observation=observation,
                    beliefs_before=beliefs_before,
                    beliefs_after=beliefs_after,
                    costs={
                        "attempt": validation.attempt_cost,
                        "measurement": validation.measurement_cost,
                        "cumulative_attempt": attempt_spent,
                        "cumulative_measurement": measurement_spent,
                    },
                    hashes={},
                )
            )

        if not ledger.verify():
            raise RuntimeError("campaign produced an invalid evidence ledger")
        return ledger
