"""Versioned public contracts for the simulated 0D RFB domain.

The contracts in this module deliberately model a finite, scalar-utility
benchmark.  They do not model hardware, a physical cell, or multi-objective
optimization.  Private oracle configuration belongs to the scenario loader and
is never represented by the public scenario or public planner state below.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any, ClassVar, Mapping

from discovery_flight_simulator.ledger import sha256_json

RFB_DOMAIN_VERSION = "rfb_domain_v1"
RFB_PROVENANCE = "simulated"
RFB_MODEL_DIMENSION = "0D"
RFB_SCENARIO_SCHEMA_VERSION = "rfb_scenario_v1"
RFB_RECOMMENDATION_SCHEMA_VERSION = "rfb_recommendation_v1"
RFB_PLANNING_STATE_SCHEMA_VERSION = "rfb_planning_state_v1"
RFB_CAMPAIGN_EVENT_SCHEMA_VERSION = "rfb_campaign_event_v1"
RFB_COST_MODEL_SCHEMA_VERSION = "rfb_cost_model_v1"
_GENESIS_EVENT_SHA256 = "0" * 64

CANONICAL_ACTION_FIELDS = (
    "charge_current_A",
    "discharge_current_A",
    "charge_voltage_limit_V",
    "discharge_voltage_limit_V",
    "protocol_duration_s",
)
V1_VARYING_AXES = ("charge_current_A", "discharge_current_A")
V1_FIXED_ACTION_FIELDS = (
    "charge_voltage_limit_V",
    "discharge_voltage_limit_V",
    "protocol_duration_s",
)


def _finite_float(name: str, value: Any) -> float:
    if isinstance(value, bool):
        raise ValueError(f"{name} must be a finite number")
    try:
        result = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{name} must be a finite number") from exc
    if not math.isfinite(result):
        raise ValueError(f"{name} must be a finite number")
    return result


def _optional_float(name: str, value: float | None) -> float | None:
    if value is None:
        return None
    if isinstance(value, bool):
        raise ValueError(f"{name} must be a number or None")
    try:
        return float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{name} must be a number or None") from exc


def _positive_integral_seconds(name: str, value: Any) -> int:
    numeric = _finite_float(name, value)
    if numeric <= 0.0 or not numeric.is_integer():
        raise ValueError(f"{name} must be a positive whole number of seconds")
    return int(numeric)


@dataclass(frozen=True)
class RFBActionV1:
    """One fully serialized constant-current protocol from the finite V1 set."""

    charge_current_A: float
    discharge_current_A: float
    charge_voltage_limit_V: float
    discharge_voltage_limit_V: float
    protocol_duration_s: int

    def __post_init__(self) -> None:
        for name in CANONICAL_ACTION_FIELDS[:-1]:
            object.__setattr__(self, name, _finite_float(name, getattr(self, name)))
        object.__setattr__(
            self,
            "protocol_duration_s",
            _positive_integral_seconds("protocol_duration_s", self.protocol_duration_s),
        )
        if self.charge_current_A <= 0.0:
            raise ValueError("charge_current_A must be positive")
        if self.discharge_current_A >= 0.0:
            raise ValueError("discharge_current_A must be negative")
        if self.charge_voltage_limit_V <= self.discharge_voltage_limit_V:
            raise ValueError("charge_voltage_limit_V must exceed discharge_voltage_limit_V")

    @classmethod
    def from_dict(cls, raw: Mapping[str, Any]) -> "RFBActionV1":
        if not isinstance(raw, Mapping) or set(raw) != set(CANONICAL_ACTION_FIELDS):
            raise ValueError("RFB action must contain exactly the five canonical fields")
        return cls(**{name: raw[name] for name in CANONICAL_ACTION_FIELDS})

    def to_dict(self) -> dict[str, float | int]:
        """Return the only permitted serialized representation, in canonical field order."""

        return {name: getattr(self, name) for name in CANONICAL_ACTION_FIELDS}

    @property
    def identity_sha256(self) -> str:
        return sha256_json(self.to_dict())

    @property
    def action_id(self) -> str:
        """Compatibility identifier for the validator's candidate lookup."""

        return self.identity_sha256

    @property
    def controls(self) -> dict[str, float | int]:
        """Compatibility view for the validator's public control interface."""

        return self.to_dict()


@dataclass(frozen=True)
class RFBRequestV1:
    """One planner request or approval around a canonical V1 action."""

    request_id: str
    action: RFBActionV1
    rationale: str
    source: str

    def __post_init__(self) -> None:
        for name in ("request_id", "rationale", "source"):
            value = getattr(self, name)
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"{name} must be a non-empty string")
            object.__setattr__(self, name, value.strip())
        if not isinstance(self.action, RFBActionV1):
            raise ValueError("action must be an RFBActionV1")

    @property
    def action_id(self) -> str:
        """Return the action digest derived from the canonical action content."""

        return self.action.identity_sha256

    @property
    def controls(self) -> dict[str, float | int]:
        """Bridge the current validator's controls interface to the action."""

        return self.action.to_dict()

    def to_dict(self) -> dict[str, Any]:
        return {
            "request_id": self.request_id,
            "action": self.action.to_dict(),
            "rationale": self.rationale,
            "source": self.source,
        }

    @property
    def request_sha256(self) -> str:
        """Return a content digest without treating a caller-supplied ID as trusted."""

        return sha256_json(self.to_dict())


# The initial RFB draft exposed the longer name. It remains a strict alias so
# existing validator and store callers continue to receive the canonical V1
# request type rather than a parallel compatibility object.
RFBActionRequestV1 = RFBRequestV1


@dataclass(frozen=True)
class RFBActionSchemaV1:
    """Public numeric envelope for the five canonical V1 action controls."""

    ranges: Mapping[str, tuple[float, float] | list[float]]

    def __post_init__(self) -> None:
        if not isinstance(self.ranges, Mapping) or set(self.ranges) != set(CANONICAL_ACTION_FIELDS):
            raise ValueError("action ranges must cover exactly the five canonical fields")
        normalized: dict[str, tuple[float, float]] = {}
        for name in CANONICAL_ACTION_FIELDS:
            bounds = self.ranges[name]
            if not isinstance(bounds, (tuple, list)) or len(bounds) != 2:
                raise ValueError(f"action range for {name} must contain a lower and upper bound")
            lower = _finite_float(f"{name} minimum", bounds[0])
            upper = _finite_float(f"{name} maximum", bounds[1])
            if lower > upper:
                raise ValueError(f"action range for {name} has an inverted bound")
            normalized[name] = (lower, upper)
        object.__setattr__(self, "ranges", normalized)

    def to_dict(self) -> dict[str, list[float]]:
        return {name: list(self.ranges[name]) for name in CANONICAL_ACTION_FIELDS}


@dataclass(frozen=True)
class RFBOutcomeV1:
    """Public result fields emitted by a simulated virtual-cell execution."""

    status: str
    delivered_discharge_energy_J: float | None
    round_trip_efficiency: float | None
    capacity_retention: float | None
    elapsed_duration_s: float | None
    qc_flags: tuple[str, ...] = ()
    provenance: str = RFB_PROVENANCE

    _STATUSES: ClassVar[tuple[str, ...]] = ("complete", "failed", "invalid", "not_applicable")

    def __post_init__(self) -> None:
        object.__setattr__(self, "status", str(self.status))
        if self.status not in self._STATUSES:
            raise ValueError(f"unsupported RFB outcome status: {self.status!r}")
        if self.provenance != RFB_PROVENANCE:
            raise ValueError("RFB outcomes must declare provenance='simulated'")
        for name in (
            "delivered_discharge_energy_J",
            "round_trip_efficiency",
            "capacity_retention",
            "elapsed_duration_s",
        ):
            object.__setattr__(self, name, _optional_float(name, getattr(self, name)))
        object.__setattr__(self, "qc_flags", tuple(str(flag) for flag in self.qc_flags))

    def to_dict(self) -> dict[str, Any]:
        """Return the complete public outcome payload used by utility records."""

        return {
            "status": self.status,
            "delivered_discharge_energy_J": self.delivered_discharge_energy_J,
            "round_trip_efficiency": self.round_trip_efficiency,
            "capacity_retention": self.capacity_retention,
            "elapsed_duration_s": self.elapsed_duration_s,
            "qc_flags": list(self.qc_flags),
            "provenance": self.provenance,
        }


@dataclass(frozen=True)
class FrozenScalarUtilityV1:
    """The single, public scalar utility frozen for all V1 candidates."""

    energy_reference_J: float
    duration_reference_s: float

    energy_weight: ClassVar[float] = 0.45
    efficiency_weight: ClassVar[float] = 0.25
    retention_weight: ClassVar[float] = 0.20
    duration_penalty_weight: ClassVar[float] = 0.10
    invalid_result_utility: ClassVar[float] = -1.0
    complete_result_range: ClassVar[tuple[float, float]] = (-0.10, 0.90)

    def __post_init__(self) -> None:
        object.__setattr__(self, "energy_reference_J", _finite_float("energy_reference_J", self.energy_reference_J))
        object.__setattr__(self, "duration_reference_s", _finite_float("duration_reference_s", self.duration_reference_s))
        if self.energy_reference_J <= 0.0:
            raise ValueError("energy_reference_J must be positive")
        if self.duration_reference_s <= 0.0:
            raise ValueError("duration_reference_s must be positive")

    @property
    def public_range(self) -> tuple[float, float]:
        return (self.invalid_result_utility, self.complete_result_range[1])

    def to_dict(self) -> dict[str, Any]:
        return {
            "formula_id": "rfb_scalar_utility_v1",
            "objective": "single_scalar_utility",
            "provenance": RFB_PROVENANCE,
            "energy_reference_J": self.energy_reference_J,
            "duration_reference_s": self.duration_reference_s,
            "weights": {
                "delivered_discharge_energy": self.energy_weight,
                "round_trip_efficiency": self.efficiency_weight,
                "capacity_retention": self.retention_weight,
                "duration_penalty": self.duration_penalty_weight,
            },
            "complete_result_range": {
                "minimum": self.complete_result_range[0],
                "maximum": self.complete_result_range[1],
            },
            "public_range": {"minimum": self.public_range[0], "maximum": self.public_range[1]},
            "invalid_or_missing_result_utility": self.invalid_result_utility,
        }

    @property
    def utility_sha256(self) -> str:
        """Stable public identity for this frozen utility definition."""

        return sha256_json(self.to_dict())

    @property
    def utility_hash(self) -> str:
        """Compatibility spelling for the frozen utility identity."""

        return self.utility_sha256

    def score(self, outcome: RFBOutcomeV1 | None) -> float:
        """Compatibility scalar view of the canonical utility record helper."""

        from .utility import utility_record_for_outcome

        return utility_record_for_outcome(outcome, self).utility


def calculate_scalar_utility(outcome: RFBOutcomeV1 | None, utility: FrozenScalarUtilityV1) -> float:
    """Compatibility scalar view of the canonical utility record helper."""

    from .utility import utility_record_for_outcome

    return utility_record_for_outcome(outcome, utility).utility


@dataclass(frozen=True)
class RFBPublicCostModelV1:
    """The public, immutable cost rules for every RFB V1 campaign action."""

    valid_execution_attempt_cost: int = 1
    valid_execution_measurement_cost: int = 1
    invalid_protocol_attempt_cost: int = 1
    invalid_protocol_measurement_cost: int = 0

    def __post_init__(self) -> None:
        expected = {
            "valid_execution_attempt_cost": 1,
            "valid_execution_measurement_cost": 1,
            "invalid_protocol_attempt_cost": 1,
            "invalid_protocol_measurement_cost": 0,
        }
        for name, required_value in expected.items():
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, int) or value != required_value:
                raise ValueError(f"{name} must be exactly {required_value} for RFB V1")

    @property
    def valid_execution_costs(self) -> dict[str, int]:
        return {
            "attempt_cost": self.valid_execution_attempt_cost,
            "measurement_cost": self.valid_execution_measurement_cost,
        }

    @property
    def invalid_protocol_costs(self) -> dict[str, int]:
        return {
            "attempt_cost": self.invalid_protocol_attempt_cost,
            "measurement_cost": self.invalid_protocol_measurement_cost,
        }

    @property
    def cost_model_sha256(self) -> str:
        return sha256_json(self.to_dict())

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": RFB_COST_MODEL_SCHEMA_VERSION,
            "valid_execution": self.valid_execution_costs,
            "invalid_protocol": self.invalid_protocol_costs,
        }


RFBCostModelV1 = RFBPublicCostModelV1


@dataclass(frozen=True)
class RFBScenarioV1:
    """Public, finite 0D RFB scenario definition available to planners."""

    scenario_id: str
    scenario_version: str
    candidate_actions: tuple[RFBActionV1, ...]
    action_schema: RFBActionSchemaV1
    fixed_fields: Mapping[str, float | int]
    ocv_50_soc_V: float
    utility: FrozenScalarUtilityV1
    total_attempt_budget: int
    total_measurement_budget: int
    cost_model: RFBPublicCostModelV1 = field(default_factory=RFBPublicCostModelV1)
    provenance: str = RFB_PROVENANCE
    model_dimension: str = RFB_MODEL_DIMENSION
    domain_version: str = RFB_DOMAIN_VERSION
    _candidate_set_sha256: str = field(init=False, repr=False)

    def __post_init__(self) -> None:
        object.__setattr__(self, "scenario_id", str(self.scenario_id))
        object.__setattr__(self, "scenario_version", str(self.scenario_version))
        if not self.scenario_id or not self.scenario_version:
            raise ValueError("scenario_id and scenario_version must be non-empty")
        if self.provenance != RFB_PROVENANCE:
            raise ValueError("RFB scenarios must declare provenance='simulated'")
        if self.model_dimension != RFB_MODEL_DIMENSION:
            raise ValueError("RFB V1 scenarios must declare model_dimension='0D'")
        if self.domain_version != RFB_DOMAIN_VERSION:
            raise ValueError(f"unsupported RFB domain version: {self.domain_version!r}")
        if not isinstance(self.utility, FrozenScalarUtilityV1):
            raise ValueError("utility must be a FrozenScalarUtilityV1")
        if not isinstance(self.cost_model, RFBPublicCostModelV1):
            raise ValueError("cost_model must be an RFBPublicCostModelV1")
        if not isinstance(self.action_schema, RFBActionSchemaV1):
            raise ValueError("action_schema must be an RFBActionSchemaV1")
        if not isinstance(self.fixed_fields, Mapping) or set(self.fixed_fields) != set(
            V1_FIXED_ACTION_FIELDS
        ):
            raise ValueError("fixed_fields must cover the scenario-fixed V1 action fields")
        normalized_fixed: dict[str, float | int] = {}
        for name in V1_FIXED_ACTION_FIELDS:
            if name == "protocol_duration_s":
                normalized_fixed[name] = _positive_integral_seconds(name, self.fixed_fields[name])
            else:
                normalized_fixed[name] = _finite_float(name, self.fixed_fields[name])
        object.__setattr__(self, "fixed_fields", normalized_fixed)
        object.__setattr__(self, "ocv_50_soc_V", _finite_float("ocv_50_soc_V", self.ocv_50_soc_V))
        actions = tuple(self.candidate_actions)
        if not actions or not all(isinstance(action, RFBActionV1) for action in actions):
            raise ValueError("candidate_actions must be a non-empty sequence of RFBActionV1 values")
        identities = tuple(action.identity_sha256 for action in actions)
        if len(set(identities)) != len(identities):
            raise ValueError("candidate_actions must not contain duplicates")
        object.__setattr__(self, "candidate_actions", actions)
        self._validate_v1_axes()
        self._validate_public_envelope()
        for name, budget in (
            ("total_attempt_budget", self.total_attempt_budget),
            ("total_measurement_budget", self.total_measurement_budget),
        ):
            if isinstance(budget, bool) or not isinstance(budget, int) or budget <= 0:
                raise ValueError(f"{name} must be a positive integer")
        object.__setattr__(self, "_candidate_set_sha256", sha256_json([action.to_dict() for action in actions]))

    def _validate_v1_axes(self) -> None:
        values = {
            name: {getattr(action, name) for action in self.candidate_actions}
            for name in CANONICAL_ACTION_FIELDS
        }
        for name in V1_VARYING_AXES:
            if len(values[name]) < 2:
                raise ValueError(f"RFB V1 requires {name} to vary across the finite candidate set")
        for name in V1_FIXED_ACTION_FIELDS:
            if len(values[name]) != 1:
                raise ValueError(f"RFB V1 requires {name} to be scenario-fixed")

    def _validate_public_envelope(self) -> None:
        for action in self.candidate_actions:
            controls = action.to_dict()
            for name in CANONICAL_ACTION_FIELDS:
                lower, upper = self.action_schema.ranges[name]
                if controls[name] < lower or controls[name] > upper:
                    raise ValueError(f"candidate {name} is outside the declared action range")
            for name in V1_FIXED_ACTION_FIELDS:
                if controls[name] != self.fixed_fields[name]:
                    raise ValueError(f"candidate {name} must equal its scenario-fixed value")
            if not (
                action.discharge_voltage_limit_V
                < self.ocv_50_soc_V
                < action.charge_voltage_limit_V
            ):
                raise ValueError(
                    "candidate voltage limits must bracket the published ocv_50_soc_V constraint"
                )

    @property
    def candidate_set_sha256(self) -> str:
        return self._candidate_set_sha256

    @property
    def utility_sha256(self) -> str:
        return self.utility.utility_sha256

    @property
    def utility_hash(self) -> str:
        return self.utility_sha256

    @property
    def cost_model_sha256(self) -> str:
        return self.cost_model.cost_model_sha256

    @property
    def public_projection_sha256(self) -> str:
        """Stable digest of the complete planner-visible scenario projection."""

        return sha256_json(self._public_projection_payload())

    @property
    def public_projection_hash(self) -> str:
        return self.public_projection_sha256

    @property
    def fixed_action_values(self) -> dict[str, float | int]:
        return {name: self.fixed_fields[name] for name in V1_FIXED_ACTION_FIELDS}

    def contains(self, action: RFBActionV1 | RFBActionRequestV1) -> bool:
        if isinstance(action, RFBActionRequestV1):
            action = action.action
        return isinstance(action, RFBActionV1) and any(action == candidate for candidate in self.candidate_actions)

    def candidate_index(self, action: RFBActionV1 | RFBActionRequestV1) -> int:
        if isinstance(action, RFBActionRequestV1):
            action = action.action
        for index, candidate in enumerate(self.candidate_actions):
            if action == candidate:
                return index
        raise ValueError("action is not a member of this finite RFB candidate set")

    def _public_projection_payload(self) -> dict[str, Any]:
        return {
            "schema_version": RFB_SCENARIO_SCHEMA_VERSION,
            "domain_version": self.domain_version,
            "scenario_id": self.scenario_id,
            "scenario_version": self.scenario_version,
            "provenance": self.provenance,
            "model_dimension": self.model_dimension,
            "total_attempt_budget": self.total_attempt_budget,
            "total_measurement_budget": self.total_measurement_budget,
            "varying_axes": list(V1_VARYING_AXES),
            "action_schema": {"ranges": self.action_schema.to_dict()},
            "fixed_fields": self.fixed_action_values,
            "ocv_50_soc_V": self.ocv_50_soc_V,
            "fixed_action_values": self.fixed_action_values,
            "candidate_actions": [action.to_dict() for action in self.candidate_actions],
            "candidate_set_sha256": self.candidate_set_sha256,
            "cost_model": self.cost_model.to_dict(),
            "cost_model_sha256": self.cost_model_sha256,
            "utility": self.utility.to_dict(),
            "utility_sha256": self.utility_sha256,
        }

    def to_dict(self) -> dict[str, Any]:
        """Return the complete, private-free public scenario projection."""

        return {
            **self._public_projection_payload(),
            "public_projection_sha256": self.public_projection_sha256,
        }


@dataclass(frozen=True)
class RFBPublicStateV1:
    """The planner-visible state, intentionally limited to public scenario and results."""

    scenario: RFBScenarioV1
    outcomes: tuple[RFBOutcomeV1, ...]
    remaining_attempt_budget: int
    remaining_measurement_budget: int

    def __post_init__(self) -> None:
        if not isinstance(self.scenario, RFBScenarioV1):
            raise ValueError("scenario must be an RFBScenarioV1")
        object.__setattr__(self, "outcomes", tuple(self.outcomes))
        if not all(isinstance(outcome, RFBOutcomeV1) for outcome in self.outcomes):
            raise ValueError("outcomes must contain only RFBOutcomeV1 values")
        for name, value in (
            ("remaining_attempt_budget", self.remaining_attempt_budget),
            ("remaining_measurement_budget", self.remaining_measurement_budget),
        ):
            if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                raise ValueError(f"{name} must be a non-negative integer")


@dataclass(frozen=True)
class RFBPlanningStateV1:
    """The complete public basis a policy must anchor a recommendation to."""

    scenario: RFBScenarioV1
    event_head_sha256: str = _GENESIS_EVENT_SHA256
    revision: int = 0
    remaining_attempt_budget: int | None = None
    remaining_measurement_budget: int | None = None
    schema_version: str = RFB_PLANNING_STATE_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if not isinstance(self.scenario, RFBScenarioV1):
            raise ValueError("scenario must be an RFBScenarioV1")
        if self.schema_version != RFB_PLANNING_STATE_SCHEMA_VERSION:
            raise ValueError(f"unsupported planning state schema: {self.schema_version!r}")
        if not _is_sha256(self.event_head_sha256):
            raise ValueError("event_head_sha256 must be a lowercase SHA-256 hex digest")
        if isinstance(self.revision, bool) or not isinstance(self.revision, int) or self.revision < 0:
            raise ValueError("revision must be a non-negative integer")
        remaining_attempts = (
            self.scenario.total_attempt_budget
            if self.remaining_attempt_budget is None
            else self.remaining_attempt_budget
        )
        remaining_measurements = (
            self.scenario.total_measurement_budget
            if self.remaining_measurement_budget is None
            else self.remaining_measurement_budget
        )
        for name, value, maximum in (
            ("remaining_attempt_budget", remaining_attempts, self.scenario.total_attempt_budget),
            (
                "remaining_measurement_budget",
                remaining_measurements,
                self.scenario.total_measurement_budget,
            ),
        ):
            if isinstance(value, bool) or not isinstance(value, int) or not 0 <= value <= maximum:
                raise ValueError(f"{name} must be a non-negative integer within the scenario budget")
        object.__setattr__(self, "remaining_attempt_budget", remaining_attempts)
        object.__setattr__(self, "remaining_measurement_budget", remaining_measurements)

    @property
    def public_event_head_hash(self) -> str:
        """Compatibility spelling for the canonical planning event head."""

        return self.event_head_sha256

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "scenario": self.scenario.to_dict(),
            "event_head_sha256": self.event_head_sha256,
            "revision": self.revision,
            "remaining_attempt_budget": self.remaining_attempt_budget,
            "remaining_measurement_budget": self.remaining_measurement_budget,
        }


RFBPolicyPlanningStateV1 = RFBPlanningStateV1
RFBPublicPlanningStateV1 = RFBPlanningStateV1


@dataclass(frozen=True)
class RFBRecommendationV1:
    """A self-validating, replayable public RFB policy recommendation."""

    action: RFBActionV1
    policy_id: str
    policy_version: str
    public_projection_sha256: str
    candidate_set_sha256: str
    utility_sha256: str
    basis_event_head_sha256: str
    basis_revision: int
    remaining_attempt_budget: int
    remaining_measurement_budget: int
    predicted_utility_mean: float | None
    predicted_utility_std: float | None
    rationale: str
    action_id: str | None = None
    recommendation_id: str | None = None
    recommendation_sha256: str | None = None
    schema_version: str = RFB_RECOMMENDATION_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if not isinstance(self.action, RFBActionV1):
            raise ValueError("action must be an RFBActionV1")
        if self.schema_version != RFB_RECOMMENDATION_SCHEMA_VERSION:
            raise ValueError(f"unsupported recommendation schema: {self.schema_version!r}")
        for name in ("policy_id", "policy_version", "rationale"):
            value = getattr(self, name)
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"{name} must be a non-empty string")
            object.__setattr__(self, name, value.strip())
        for name in (
            "public_projection_sha256",
            "candidate_set_sha256",
            "utility_sha256",
            "basis_event_head_sha256",
        ):
            if not _is_sha256(getattr(self, name)):
                raise ValueError(f"{name} must be a lowercase SHA-256 hex digest")
        for name in (
            "basis_revision",
            "remaining_attempt_budget",
            "remaining_measurement_budget",
        ):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                raise ValueError(f"{name} must be a non-negative integer")
        mean = _optional_finite_float("predicted_utility_mean", self.predicted_utility_mean)
        std = _optional_finite_float("predicted_utility_std", self.predicted_utility_std)
        if (mean is None) != (std is None):
            raise ValueError("predicted utility mean and std must be supplied together")
        if std is not None and std < 0.0:
            raise ValueError("predicted_utility_std must be non-negative")
        object.__setattr__(self, "predicted_utility_mean", mean)
        object.__setattr__(self, "predicted_utility_std", std)

        expected_action_id = self.action.identity_sha256
        if self.action_id is not None and self.action_id != expected_action_id:
            raise ValueError("action_id must match the canonical action content")
        object.__setattr__(self, "action_id", expected_action_id)
        expected_hash = self._derived_recommendation_sha256()
        if self.recommendation_sha256 is not None and self.recommendation_sha256 != expected_hash:
            raise ValueError("recommendation_sha256 must match canonical recommendation content")
        expected_id = _recommendation_id(expected_hash)
        if self.recommendation_id is not None and self.recommendation_id != expected_id:
            raise ValueError("recommendation_id must match canonical recommendation content")
        object.__setattr__(self, "recommendation_sha256", expected_hash)
        object.__setattr__(self, "recommendation_id", expected_id)

    @property
    def request(self) -> RFBRequestV1:
        return self.to_request()

    @property
    def request_id(self) -> str:
        return self.recommendation_id

    @property
    def candidate_set_hash(self) -> str:
        return self.candidate_set_sha256

    @property
    def utility_hash(self) -> str:
        return self.utility_sha256

    @property
    def public_projection_hash(self) -> str:
        return self.public_projection_sha256

    @property
    def public_event_head_hash(self) -> str:
        return self.basis_event_head_sha256

    @property
    def public_event_head_sha256(self) -> str:
        return self.basis_event_head_sha256

    def _canonical_content(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "policy_id": self.policy_id,
            "policy_version": self.policy_version,
            "action": self.action.to_dict(),
            "action_id": self.action_id,
            "public_projection_sha256": self.public_projection_sha256,
            "candidate_set_sha256": self.candidate_set_sha256,
            "utility_sha256": self.utility_sha256,
            "basis_event_head_sha256": self.basis_event_head_sha256,
            "basis_revision": self.basis_revision,
            "remaining_attempt_budget": self.remaining_attempt_budget,
            "remaining_measurement_budget": self.remaining_measurement_budget,
            "predicted_utility_mean": self.predicted_utility_mean,
            "predicted_utility_std": self.predicted_utility_std,
            "rationale": self.rationale,
        }

    def _derived_recommendation_sha256(self) -> str:
        return sha256_json(self._canonical_content())

    def validate_integrity(self) -> None:
        """Raise when any derived identifier no longer matches canonical public data."""

        if self.action_id != self.action.identity_sha256:
            raise ValueError("action_id does not match the canonical action content")
        expected_hash = self._derived_recommendation_sha256()
        if self.recommendation_sha256 != expected_hash:
            raise ValueError("recommendation_sha256 does not match canonical recommendation content")
        if self.recommendation_id != _recommendation_id(expected_hash):
            raise ValueError("recommendation_id does not match canonical recommendation content")

    def to_request(self) -> RFBRequestV1:
        self.validate_integrity()
        return RFBRequestV1(
            request_id=self.recommendation_id,
            action=self.action,
            rationale=self.rationale,
            source="policy",
        )

    def to_dict(self) -> dict[str, Any]:
        self.validate_integrity()
        return {
            **self._canonical_content(),
            "recommendation_id": self.recommendation_id,
            "recommendation_sha256": self.recommendation_sha256,
            "request": self.to_request().to_dict(),
        }


RFBRecommendation = RFBRecommendationV1


def rfb_campaign_event_logical_content(
    *,
    event_type: str,
    payload: Mapping[str, Any],
    sequence: int,
    previous_event_sha256: str = _GENESIS_EVENT_SHA256,
) -> dict[str, Any]:
    """Return hashable public event content without an audit timestamp."""

    if not isinstance(event_type, str) or not event_type.strip():
        raise ValueError("event_type must be a non-empty string")
    if isinstance(sequence, bool) or not isinstance(sequence, int) or sequence < 0:
        raise ValueError("sequence must be a non-negative integer")
    if not _is_sha256(previous_event_sha256):
        raise ValueError("previous_event_sha256 must be a lowercase SHA-256 hex digest")
    return {
        "schema_version": RFB_CAMPAIGN_EVENT_SCHEMA_VERSION,
        "event_type": event_type.strip(),
        "payload": _public_json_value(payload, "payload"),
        "sequence": sequence,
        "previous_event_sha256": previous_event_sha256,
    }


def rfb_campaign_event_logical_hash(
    *,
    event_type: str,
    payload: Mapping[str, Any],
    sequence: int,
    previous_event_sha256: str = _GENESIS_EVENT_SHA256,
) -> str:
    """Hash only canonical event logic; audit timestamps are intentionally absent."""

    return sha256_json(
        rfb_campaign_event_logical_content(
            event_type=event_type,
            payload=payload,
            sequence=sequence,
            previous_event_sha256=previous_event_sha256,
        )
    )


def build_rfb_campaign_event_v1(
    *,
    event_type: str,
    payload: Mapping[str, Any],
    sequence: int,
    previous_event_sha256: str = _GENESIS_EVENT_SHA256,
    audit_timestamp: str | None = None,
) -> dict[str, Any]:
    """Build a canonical public event; ``audit_timestamp`` never affects its hash."""

    del audit_timestamp
    content = rfb_campaign_event_logical_content(
        event_type=event_type,
        payload=payload,
        sequence=sequence,
        previous_event_sha256=previous_event_sha256,
    )
    return {**content, "event_sha256": sha256_json(content)}


rfb_campaign_event_sha256 = rfb_campaign_event_logical_hash
make_rfb_campaign_event_v1 = build_rfb_campaign_event_v1


def _recommendation_id(recommendation_sha256: str) -> str:
    return f"rfb-recommendation-v1-{recommendation_sha256}"


def _optional_finite_float(name: str, value: float | None) -> float | None:
    if value is None:
        return None
    return _finite_float(name, value)


def _is_sha256(value: object) -> bool:
    return (
        isinstance(value, str)
        and len(value) == 64
        and all(character in "0123456789abcdef" for character in value)
    )


def _public_json_value(value: Any, path: str) -> Any:
    """Normalize a serializable public payload and reject private-shaped fields."""

    if isinstance(value, Mapping):
        normalized: dict[str, Any] = {}
        for key, nested in value.items():
            if not isinstance(key, str) or not key:
                raise ValueError(f"{path} keys must be non-empty strings")
            _reject_private_public_field(key, f"{path}.{key}")
            normalized[key] = _public_json_value(nested, f"{path}.{key}")
        return normalized
    if isinstance(value, (list, tuple)):
        return [_public_json_value(nested, f"{path}[{index}]") for index, nested in enumerate(value)]
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError(f"{path} must not contain a non-finite number")
        return value
    if value is None or isinstance(value, (str, int, bool)):
        return value
    raise ValueError(f"{path} must contain only JSON-serializable public values")


def _reject_private_public_field(key: str, path: str) -> None:
    normalized = key.lower().replace("-", "_")
    prohibited_exact = {
        "private",
        "private_config",
        "oracle_config",
        "execution_oracle_spec",
        "model_parameters",
        "replay_key",
        "private_commitment_key",
        "commitment_key",
    }
    prohibited_fragments = (
        "private_key",
        "secret",
        "password",
        "credential",
        "api_key",
        "access_key",
    )
    is_digest = any(marker in normalized for marker in ("sha256", "hmac", "digest", "commitment"))
    if (
        normalized in prohibited_exact
        or any(fragment in normalized for fragment in prohibited_fragments)
        or ("private" in normalized and not is_digest)
    ):
        raise ValueError(f"{path} contains forbidden private material")


RFBAction = RFBActionV1

__all__ = [
    "CANONICAL_ACTION_FIELDS",
    "RFB_CAMPAIGN_EVENT_SCHEMA_VERSION",
    "RFB_COST_MODEL_SCHEMA_VERSION",
    "RFBAction",
    "RFBActionRequestV1",
    "RFBActionSchemaV1",
    "RFBActionV1",
    "RFBCostModelV1",
    "RFBPlanningStateV1",
    "RFBPolicyPlanningStateV1",
    "RFBPublicCostModelV1",
    "RFBPublicPlanningStateV1",
    "RFBRequestV1",
    "RFBRecommendation",
    "RFBRecommendationV1",
    "RFB_DOMAIN_VERSION",
    "RFB_MODEL_DIMENSION",
    "RFB_PLANNING_STATE_SCHEMA_VERSION",
    "RFB_PROVENANCE",
    "RFB_RECOMMENDATION_SCHEMA_VERSION",
    "RFBOutcomeV1",
    "RFBPublicStateV1",
    "RFB_SCENARIO_SCHEMA_VERSION",
    "RFBScenarioV1",
    "FrozenScalarUtilityV1",
    "V1_FIXED_ACTION_FIELDS",
    "V1_VARYING_AXES",
    "build_rfb_campaign_event_v1",
    "calculate_scalar_utility",
    "make_rfb_campaign_event_v1",
    "rfb_campaign_event_logical_content",
    "rfb_campaign_event_logical_hash",
    "rfb_campaign_event_sha256",
]
