"""Project-owned adapter for the pinned RFBzero virtual-cell model.

Each execution constructs a fresh RFBzero ``ZeroDModel``, reduces the trace to
the public V1 contract, and then discards all engine objects. The adapter is a
deterministic simulated-only boundary: it imports no network, hardware, or LLM
clients and does not serialize engine state.
"""

from __future__ import annotations

import math
import sys
from dataclasses import dataclass
from importlib.metadata import PackageNotFoundError, version as package_version
from types import MappingProxyType
from typing import Mapping, Protocol, runtime_checkable

from rfbzero.experiment import ConstantCurrent
from rfbzero.redox_flow_cell import ZeroDModel

from .contracts import CANONICAL_ACTION_FIELDS, RFBActionV1, RFBOutcomeV1


ACTION_FIELDS = CANONICAL_ACTION_FIELDS
ADAPTER_ID = "discovery_flight_simulator.rfb.rfbzero_adapter"
ADAPTER_VERSION = "1"
REDUCER_ID = "discovery_flight_simulator.rfb.rfbzero_trace_reducer"
REDUCER_VERSION = "1"
_EXPECTED_END_STATUS = "time_duration_reached"


@runtime_checkable
class FrozenOracleConfig(Protocol):
    """Private, frozen virtual-cell inputs needed for one RFBzero execution."""

    model_parameters: Mapping[str, object]
    capacity_reference_C: float
    charge_first: bool


def _finite_number(value: object, field: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{field} must be a finite number")
    numeric = float(value)
    if not math.isfinite(numeric):
        raise ValueError(f"{field} must be a finite number")
    return numeric


@dataclass(frozen=True)
class RFBZeroOracleConfig:
    """Frozen inputs for constructing one fresh ``ZeroDModel`` per execution."""

    model_parameters: Mapping[str, object]
    capacity_reference_C: float
    charge_first: bool = True

    def __post_init__(self) -> None:
        if not isinstance(self.model_parameters, Mapping):
            raise ValueError("model_parameters must be a mapping")
        object.__setattr__(self, "model_parameters", MappingProxyType(dict(self.model_parameters)))
        reference = _finite_number(self.capacity_reference_C, "capacity_reference_C")
        if reference <= 0.0:
            raise ValueError("capacity_reference_C must be positive")
        object.__setattr__(self, "capacity_reference_C", reference)
        if not isinstance(self.charge_first, bool):
            raise ValueError("charge_first must be a boolean")


@dataclass(frozen=True)
class _CompletedSegment:
    is_charge: bool
    start_step: int
    end_step: int
    capacity_C: float


def _installed_version(distribution: str) -> str:
    """Return a locally installed distribution version without querying a registry."""

    try:
        return package_version(distribution)
    except PackageNotFoundError:
        return "unavailable"


def runtime_dependency_identity() -> dict[str, str]:
    """Return the runtime dependency identity required for replay manifests."""

    return {
        "python": ".".join(str(component) for component in sys.version_info[:3]),
        "numpy": _installed_version("numpy"),
        "scipy": _installed_version("scipy"),
        "rfbzero": _installed_version("rfbzero"),
    }


def adapter_replay_identity() -> dict[str, object]:
    """Return project-owned adapter and reducer versions plus local runtime versions."""

    return {
        "adapter_id": ADAPTER_ID,
        "adapter_version": ADAPTER_VERSION,
        "reducer_id": REDUCER_ID,
        "reducer_version": REDUCER_VERSION,
        "runtime_dependencies": runtime_dependency_identity(),
    }


def _canonical_action(action: RFBActionV1 | Mapping[str, object]) -> RFBActionV1:
    if isinstance(action, RFBActionV1):
        return action
    if isinstance(action, Mapping):
        return RFBActionV1.from_dict(action)
    raise ValueError("RFB action must be an RFBActionV1 or its canonical to_dict() mapping")


def _config_values(config: FrozenOracleConfig) -> tuple[dict[str, object], float, bool]:
    parameters = dict(config.model_parameters)
    capacity_reference = _finite_number(config.capacity_reference_C, "capacity_reference_C")
    if capacity_reference <= 0.0:
        raise ValueError("capacity_reference_C must be positive")
    if not isinstance(config.charge_first, bool):
        raise ValueError("charge_first must be a boolean")
    return parameters, capacity_reference, config.charge_first


def _validate_voltage_envelope(action: RFBActionV1, model_parameters: Mapping[str, object]) -> None:
    try:
        ocv_50_soc = _finite_number(model_parameters["ocv_50_soc"], "ocv_50_soc")
    except KeyError as error:
        raise ValueError("model_parameters must include ocv_50_soc") from error
    if not action.discharge_voltage_limit_V < ocv_50_soc < action.charge_voltage_limit_V:
        raise ValueError(
            "discharge_voltage_limit_V < ocv_50_soc < charge_voltage_limit_V is required"
        )
    if ocv_50_soc > 0.0 and action.discharge_voltage_limit_V < 0.0:
        raise ValueError("discharge_voltage_limit_V must be non-negative for a full virtual cell")


def _status_name(status: object) -> str:
    raw = getattr(status, "name", status)
    text = str(raw).strip().lower()
    normalized = "".join(character if character.isalnum() else "_" for character in text)
    return normalized.strip("_") or "unknown"


def _trace_values(results: object) -> tuple[int, float, list[tuple[float, bool, float, float]]]:
    steps_raw = getattr(results, "steps")
    if isinstance(steps_raw, bool) or not isinstance(steps_raw, int) or steps_raw < 0:
        raise ValueError("RFBzero results have an invalid step count")
    steps = steps_raw
    time_step = _finite_number(getattr(results, "time_step"), "RFBzero time_step")
    if time_step <= 0.0:
        raise ValueError("RFBzero time_step must be positive")

    step_time = getattr(results, "step_time")
    step_is_charge = getattr(results, "step_is_charge")
    current = getattr(results, "current")
    cell_v = getattr(results, "cell_v")
    if any(len(values) < steps for values in (step_time, step_is_charge, current, cell_v)):
        raise ValueError("RFBzero results have incomplete trace fields")

    trace: list[tuple[float, bool, float, float]] = []
    previous_time = 0.0
    for index in range(steps):
        elapsed = _finite_number(step_time[index], "RFBzero step_time")
        if elapsed <= previous_time:
            raise ValueError("RFBzero step_time must be strictly increasing")
        phase = step_is_charge[index]
        if not isinstance(phase, bool):
            raise ValueError("RFBzero step_is_charge must contain booleans")
        current_A = _finite_number(current[index], "RFBzero current")
        voltage_V = _finite_number(cell_v[index], "RFBzero cell_v")
        if phase and current_A <= 0.0:
            raise ValueError("RFBzero charge trace has non-positive current")
        if not phase and current_A >= 0.0:
            raise ValueError("RFBzero discharge trace has non-negative current")
        trace.append((elapsed, phase, current_A, voltage_V))
        previous_time = elapsed
    return steps, time_step, trace


def _completed_segments(
    results: object,
    steps: int,
    time_step: float,
    trace: list[tuple[float, bool, float, float]],
) -> list[_CompletedSegment]:
    half_cycle_is_charge = list(getattr(results, "half_cycle_is_charge"))
    half_cycle_capacity = list(getattr(results, "half_cycle_capacity"))
    half_cycle_time = list(getattr(results, "half_cycle_time"))
    if not (
        len(half_cycle_is_charge) == len(half_cycle_capacity) == len(half_cycle_time)
    ):
        raise ValueError("RFBzero completed-half-cycle fields have inconsistent lengths")

    segments: list[_CompletedSegment] = []
    start_step = 0
    for phase, capacity, elapsed in zip(
        half_cycle_is_charge, half_cycle_capacity, half_cycle_time, strict=True
    ):
        if not isinstance(phase, bool):
            raise ValueError("RFBzero half_cycle_is_charge must contain booleans")
        capacity_C = _finite_number(capacity, "RFBzero half_cycle_capacity")
        if capacity_C < 0.0:
            raise ValueError("RFBzero half_cycle_capacity must be non-negative")
        elapsed_s = _finite_number(elapsed, "RFBzero half_cycle_time")
        end_step = int(round(elapsed_s / time_step))
        if end_step <= start_step or end_step > steps:
            raise ValueError("RFBzero completed half-cycle time is outside the trace")
        if any(item[1] != phase for item in trace[start_step:end_step]):
            raise ValueError("RFBzero completed half-cycle phase disagrees with the trace")
        segments.append(_CompletedSegment(phase, start_step, end_step, capacity_C))
        start_step = end_step
    return segments


def _segment_energy_J(
    trace: list[tuple[float, bool, float, float]],
    time_step: float,
    segment: _CompletedSegment,
) -> float:
    energy = 0.0
    for _, is_charge, current_A, voltage_V in trace[segment.start_step : segment.end_step]:
        power_W = current_A * voltage_V if is_charge else -current_A * voltage_V
        energy += power_W * time_step
    return energy


def _paired_cycle_values(
    trace: list[tuple[float, bool, float, float]],
    time_step: float,
    segments: list[_CompletedSegment],
) -> list[tuple[float, float, float]]:
    pairs: list[tuple[float, float, float]] = []
    segment_index = 0
    while segment_index + 1 < len(segments):
        charge_segment = segments[segment_index]
        discharge_segment = segments[segment_index + 1]
        if charge_segment.is_charge and not discharge_segment.is_charge:
            charge_energy = _segment_energy_J(trace, time_step, charge_segment)
            discharge_energy = _segment_energy_J(trace, time_step, discharge_segment)
            if charge_energy <= 0.0 or discharge_energy < 0.0:
                raise ValueError("RFBzero complete half-cycle energy is invalid")
            pairs.append((charge_energy, discharge_energy, discharge_segment.capacity_C))
            segment_index += 2
        else:
            segment_index += 1
    return pairs


def _partial_outcome(elapsed_duration_s: float) -> RFBOutcomeV1:
    """Convert a non-comparable partial RFBzero trace to the frozen V1 contract.

    ``RFBOutcomeV1`` intentionally has no ``partial`` status. A trace without a
    complete charge/discharge pair is therefore represented as canonical
    ``invalid`` rather than by retaining an adapter-specific outcome type.
    """

    return RFBOutcomeV1(
        status="invalid",
        delivered_discharge_energy_J=None,
        round_trip_efficiency=None,
        capacity_retention=None,
        elapsed_duration_s=elapsed_duration_s,
        qc_flags=("rfbzero_partial_execution",),
    )


def _failure_outcome(flag: str, elapsed_duration_s: float | None = None) -> RFBOutcomeV1:
    return RFBOutcomeV1(
        status="failed",
        delivered_discharge_energy_J=None,
        round_trip_efficiency=None,
        capacity_retention=None,
        elapsed_duration_s=elapsed_duration_s,
        qc_flags=(flag,),
    )


def _invalid_input_outcome(error: Exception) -> RFBOutcomeV1:
    return RFBOutcomeV1(
        status="invalid",
        delivered_discharge_energy_J=None,
        round_trip_efficiency=None,
        capacity_retention=None,
        elapsed_duration_s=None,
        qc_flags=(f"rfbzero_invalid_input:{type(error).__name__}",),
    )


def _reduce_results(results: object, capacity_reference_C: float) -> RFBOutcomeV1:
    steps, time_step, trace = _trace_values(results)
    elapsed_duration_s = trace[-1][0] if trace else 0.0
    engine_end_status = _status_name(getattr(results, "end_status"))
    if engine_end_status != _EXPECTED_END_STATUS:
        return _failure_outcome(
            f"rfbzero_end_status:{engine_end_status}", elapsed_duration_s
        )

    segments = _completed_segments(results, steps, time_step, trace)
    pair_energies = _paired_cycle_values(trace, time_step, segments)
    if not pair_energies:
        return _partial_outcome(elapsed_duration_s)

    charge_energy_total = sum(pair[0] for pair in pair_energies)
    discharge_energy_total = sum(pair[1] for pair in pair_energies)
    if charge_energy_total <= 0.0:
        raise ValueError("RFBzero paired charge energy must be positive")
    return RFBOutcomeV1(
        status="complete",
        delivered_discharge_energy_J=discharge_energy_total,
        round_trip_efficiency=discharge_energy_total / charge_energy_total,
        capacity_retention=pair_energies[-1][2] / capacity_reference_C,
        elapsed_duration_s=elapsed_duration_s,
    )


class RFBZeroOracleAdapter:
    """Run one canonical action against a newly constructed RFBzero virtual cell."""

    adapter_id = ADAPTER_ID
    adapter_version = ADAPTER_VERSION
    reducer_id = REDUCER_ID
    reducer_version = REDUCER_VERSION

    @staticmethod
    def manifest_identity() -> dict[str, object]:
        """Expose the exact adapter, reducer, and runtime identity for replay."""

        return adapter_replay_identity()

    def execute(
        self, config: FrozenOracleConfig, action: RFBActionV1 | Mapping[str, object]
    ) -> RFBOutcomeV1:
        """Execute a simulated protocol without retaining RFBzero state or results."""

        try:
            canonical_action = _canonical_action(action)
            model_parameters, capacity_reference_C, charge_first = _config_values(config)
            _validate_voltage_envelope(canonical_action, model_parameters)
        except (AttributeError, TypeError, ValueError) as error:
            return _invalid_input_outcome(error)

        try:
            cell_model = ZeroDModel(**model_parameters)
            protocol = ConstantCurrent(
                voltage_limit_charge=canonical_action.charge_voltage_limit_V,
                voltage_limit_discharge=canonical_action.discharge_voltage_limit_V,
                current_charge=canonical_action.charge_current_A,
                current_discharge=canonical_action.discharge_current_A,
                charge_first=charge_first,
            )
            results = protocol.run(
                duration=canonical_action.protocol_duration_s,
                cell_model=cell_model,
            )
        except Exception as error:
            return _failure_outcome(f"rfbzero_exception:{type(error).__name__}")

        try:
            return _reduce_results(results, capacity_reference_C)
        except Exception as error:
            return _failure_outcome(f"rfbzero_reduction_error:{type(error).__name__}")


def simulate(
    config: FrozenOracleConfig, action: RFBActionV1 | Mapping[str, object]
) -> RFBOutcomeV1:
    """Convenience boundary for one simulated RFB execution."""

    return RFBZeroOracleAdapter().execute(config, action)


__all__ = [
    "ACTION_FIELDS",
    "ADAPTER_ID",
    "ADAPTER_VERSION",
    "FrozenOracleConfig",
    "REDUCER_ID",
    "REDUCER_VERSION",
    "RFBZeroOracleAdapter",
    "RFBZeroOracleConfig",
    "adapter_replay_identity",
    "runtime_dependency_identity",
    "simulate",
]
