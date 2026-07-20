"""Public contracts for simulated discovery campaigns.

The public campaign state deliberately has no field for hidden truth, future
failures, noiseless responses, or evaluator state. Planners receive this public
view and a planner-only random generator; nothing else.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field, is_dataclass
from typing import Any, Protocol, runtime_checkable


def to_primitive(value: Any) -> Any:
    """Convert contracts and common containers into deterministic JSON values."""

    if is_dataclass(value) and not isinstance(value, type):
        return {key: to_primitive(item) for key, item in asdict(value).items()}
    if isinstance(value, dict):
        return {str(key): to_primitive(item) for key, item in value.items()}
    if isinstance(value, (tuple, list)):
        return [to_primitive(item) for item in value]
    if hasattr(value, "item") and callable(value.item):
        try:
            return value.item()
        except (TypeError, ValueError):
            pass
    return value


def _ranges(value: dict[str, tuple[float, float]]) -> dict[str, tuple[float, float]]:
    return {str(name): (float(bounds[0]), float(bounds[1])) for name, bounds in value.items()}


@dataclass(frozen=True)
class SeedBundle:
    world_seed: int
    noise_seed: int
    failure_seed: int
    planner_seed: int


@dataclass(frozen=True)
class PublicWorldSpec:
    world_id: str
    world_version: str
    controls: dict[str, tuple[float, float]]
    operations: tuple[str, ...]
    total_attempt_budget: int
    total_measurement_budget: int
    provenance: str = "simulated"

    def __post_init__(self) -> None:
        object.__setattr__(self, "controls", _ranges(self.controls))
        object.__setattr__(self, "operations", tuple(str(v) for v in self.operations))
        if self.provenance != "simulated":
            raise ValueError("public worlds must declare provenance='simulated'")
        for name, budget in (
            ("total_attempt_budget", self.total_attempt_budget),
            ("total_measurement_budget", self.total_measurement_budget),
        ):
            if isinstance(budget, bool) or not isinstance(budget, int) or budget <= 0:
                raise ValueError(f"{name} must be a positive integer")
        for name, (low, high) in self.controls.items():
            if low > high:
                raise ValueError(f"invalid control range for {name!r}: {low} > {high}")


@dataclass(frozen=True)
class InstrumentCapabilities:
    control_ranges: dict[str, tuple[float, float]]
    operations: tuple[str, ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "control_ranges", _ranges(self.control_ranges))
        object.__setattr__(self, "operations", tuple(str(v) for v in self.operations))


@dataclass(frozen=True)
class ExperimentRequest:
    request_id: str
    operation: str
    controls: dict[str, float]
    rationale: str

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "controls",
            {str(name): float(value) for name, value in self.controls.items()},
        )


@dataclass(frozen=True)
class StopDecision:
    reason: str
    final_hypothesis: str
    confidence: float


@dataclass(frozen=True)
class ValidationResult:
    accepted: bool
    reasons: tuple[str, ...] = field(default_factory=tuple)
    attempt_cost: int = 1
    measurement_cost: int = 0

    def __post_init__(self) -> None:
        object.__setattr__(self, "reasons", tuple(str(reason) for reason in self.reasons))
        if self.attempt_cost not in (0, 1) or self.measurement_cost not in (0, 1):
            raise ValueError("validation costs must each be 0 or 1")
        if self.accepted and self.measurement_cost != 1:
            raise ValueError("accepted requests must reserve one measurement cost")
        if not self.accepted and self.measurement_cost != 0:
            raise ValueError("rejected requests cannot consume measurement cost")


@dataclass(frozen=True)
class Observation:
    status: str
    requested_controls: dict[str, float]
    executed_controls: dict[str, float]
    value: float | None
    standard_error: float | None
    qc_flags: tuple[str, ...]
    attempt_cost: int
    measurement_cost: int
    provenance: str = "simulated"

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "requested_controls",
            {str(name): float(value) for name, value in self.requested_controls.items()},
        )
        object.__setattr__(
            self,
            "executed_controls",
            {str(name): float(value) for name, value in self.executed_controls.items()},
        )
        object.__setattr__(self, "qc_flags", tuple(str(flag) for flag in self.qc_flags))
        if self.provenance != "simulated":
            raise ValueError("observations must declare provenance='simulated'")
        if self.attempt_cost not in (0, 1) or self.measurement_cost not in (0, 1):
            raise ValueError("observation costs must each be 0 or 1")


@dataclass(frozen=True)
class PublicCampaignState:
    spec: PublicWorldSpec
    observations: tuple[Observation, ...]
    remaining_attempt_budget: int
    remaining_measurement_budget: int
    public_beliefs: dict[str, float]

    def __post_init__(self) -> None:
        object.__setattr__(self, "observations", tuple(self.observations))
        object.__setattr__(
            self,
            "public_beliefs",
            {str(name): float(value) for name, value in self.public_beliefs.items()},
        )
        if self.remaining_attempt_budget < 0 or self.remaining_measurement_budget < 0:
            raise ValueError("remaining budgets must be non-negative")


@dataclass(frozen=True)
class ExperimentEvent:
    sequence: int
    request: ExperimentRequest | None
    stop: StopDecision | None
    validation: ValidationResult | None
    observation: Observation | None
    beliefs_before: dict[str, float]
    beliefs_after: dict[str, float]
    costs: dict[str, int]
    hashes: dict[str, str] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "beliefs_before",
            {str(name): float(value) for name, value in self.beliefs_before.items()},
        )
        object.__setattr__(
            self,
            "beliefs_after",
            {str(name): float(value) for name, value in self.beliefs_after.items()},
        )
        object.__setattr__(self, "costs", {str(name): int(value) for name, value in self.costs.items()})
        object.__setattr__(self, "hashes", {str(name): str(value) for name, value in self.hashes.items()})
        if (self.request is None) == (self.stop is None):
            raise ValueError("an event must contain exactly one request or stop decision")


@runtime_checkable
class Planner(Protocol):
    name: str
    version: str

    def propose(self, state: PublicCampaignState, planner_rng: Any) -> ExperimentRequest | StopDecision:
        """Return one public experiment request or stop decision."""


@runtime_checkable
class CampaignEnvironment(Protocol):
    def execute(self, request: ExperimentRequest) -> Observation:
        """Execute an already validated request in a simulated world."""


@runtime_checkable
class Evaluator(Protocol):
    def score(self, ledger: Any, private_truth: Any) -> dict[str, Any]:
        """Score a completed ledger using truth unavailable during the campaign."""
