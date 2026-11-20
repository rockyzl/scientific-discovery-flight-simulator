"""Loading for frozen RFB V1 scenarios with separated public and execution data."""

from __future__ import annotations

import copy
import hashlib
import hmac
import json
import math
import secrets
from dataclasses import dataclass, field
from pathlib import Path
from types import MappingProxyType
from typing import Any, Mapping

from discovery_flight_simulator.ledger import sha256_json

from .contracts import (
    CANONICAL_ACTION_FIELDS,
    RFB_DOMAIN_VERSION,
    RFB_PROVENANCE,
    V1_FIXED_ACTION_FIELDS,
    V1_VARYING_AXES,
    FrozenScalarUtilityV1,
    RFBActionSchemaV1,
    RFBActionV1,
    RFBOutcomeV1,
    RFBPublicStateV1,
    RFBScenarioV1,
)

RFB_SCENARIO_SCHEMA_VERSION = "rfb_scenario_v1"
RFBZERO_MODEL_PARAMETER_FIELDS = (
    "volume_cls",
    "volume_ncls",
    "c_ox_cls",
    "c_red_cls",
    "c_ox_ncls",
    "c_red_ncls",
    "ocv_50_soc",
    "resistance",
    "k_0_cls",
    "k_0_ncls",
    "alpha_cls",
    "alpha_ncls",
    "geometric_area",
    "cls_negolyte",
    "time_step",
    "k_mt",
    "roughness_factor",
    "num_electrons_cls",
    "num_electrons_ncls",
    "temperature",
)
_RFBZERO_INTEGER_PARAMETERS = {"num_electrons_cls", "num_electrons_ncls"}
_RFBZERO_BOOLEAN_PARAMETERS = {"cls_negolyte"}
_RFBZERO_NONNEGATIVE_PARAMETERS = {
    "c_ox_cls",
    "c_red_cls",
    "c_ox_ncls",
    "c_red_ncls",
    "ocv_50_soc",
    "resistance",
}
_REQUIRED_DEPENDENCY_PINS = {"python", "numpy", "scipy", "rfbzero"}


def _reject_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate JSON key: {key!r}")
        result[key] = value
    return result


def _require_object(value: Any, name: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError(f"{name} must be a JSON object")
    return value


def _require_exact_keys(value: Mapping[str, Any], expected: set[str], name: str) -> None:
    if set(value) != expected:
        missing = sorted(expected - set(value))
        unexpected = sorted(set(value) - expected)
        raise ValueError(f"{name} fields do not match schema; missing={missing}, unexpected={unexpected}")


def _positive_int(value: Any, name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ValueError(f"{name} must be a positive integer")
    return value


def _finite_float(value: Any, name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{name} must be a finite number")
    numeric = float(value)
    if not math.isfinite(numeric):
        raise ValueError(f"{name} must be a finite number")
    return numeric


def _nonempty_string(value: Any, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must be a non-empty string")
    return value.strip()


@dataclass(frozen=True)
class RFBZeroOracleSpecV1:
    """Validated private inputs for the project-owned RFBzero adapter."""

    adapter_id: str
    adapter_version: str
    reducer_id: str
    reducer_version: str
    rfbzero_version: str
    model_parameters: Mapping[str, object]
    capacity_reference_C: float
    charge_first: bool
    dependency_pins: Mapping[str, str]

    def __post_init__(self) -> None:
        for name in (
            "adapter_id",
            "adapter_version",
            "reducer_id",
            "reducer_version",
            "rfbzero_version",
        ):
            object.__setattr__(self, name, _nonempty_string(getattr(self, name), name))
        parameters = self._validate_model_parameters(self.model_parameters)
        object.__setattr__(self, "model_parameters", MappingProxyType(parameters))
        capacity_reference = _finite_float(self.capacity_reference_C, "capacity_reference_C")
        if capacity_reference <= 0.0:
            raise ValueError("capacity_reference_C must be positive")
        object.__setattr__(self, "capacity_reference_C", capacity_reference)
        if not isinstance(self.charge_first, bool):
            raise ValueError("charge_first must be a boolean")
        if not isinstance(self.dependency_pins, Mapping):
            raise ValueError("dependency_pins must be a mapping")
        _require_exact_keys(self.dependency_pins, _REQUIRED_DEPENDENCY_PINS, "dependency_pins")
        pins = {
            name: _nonempty_string(value, f"dependency_pins.{name}")
            for name, value in self.dependency_pins.items()
        }
        if pins["rfbzero"] != self.rfbzero_version:
            raise ValueError("dependency_pins.rfbzero must match rfbzero_version")
        object.__setattr__(self, "dependency_pins", MappingProxyType(pins))

    @staticmethod
    def _validate_model_parameters(raw: Mapping[str, object]) -> dict[str, object]:
        if not isinstance(raw, Mapping):
            raise ValueError("model_parameters must be a mapping")
        _require_exact_keys(raw, set(RFBZERO_MODEL_PARAMETER_FIELDS), "model_parameters")
        parameters: dict[str, object] = {}
        for name in RFBZERO_MODEL_PARAMETER_FIELDS:
            value = raw[name]
            if name in _RFBZERO_BOOLEAN_PARAMETERS:
                if not isinstance(value, bool):
                    raise ValueError(f"model_parameters.{name} must be a boolean")
                parameters[name] = value
                continue
            if name in _RFBZERO_INTEGER_PARAMETERS:
                if isinstance(value, bool) or not isinstance(value, int) or value < 1:
                    raise ValueError(f"model_parameters.{name} must be an integer of at least one")
                parameters[name] = value
                continue
            numeric = _finite_float(value, f"model_parameters.{name}")
            if name in {"alpha_cls", "alpha_ncls"}:
                if not 0.0 < numeric < 1.0:
                    raise ValueError(f"model_parameters.{name} must be strictly between zero and one")
            elif name in _RFBZERO_NONNEGATIVE_PARAMETERS:
                if numeric < 0.0:
                    raise ValueError(f"model_parameters.{name} must be non-negative")
            elif numeric <= 0.0:
                raise ValueError(f"model_parameters.{name} must be positive")
            parameters[name] = numeric

        cls_capacity = (
            parameters["volume_cls"]
            * parameters["num_electrons_cls"]
            * (parameters["c_ox_cls"] + parameters["c_red_cls"])
        )
        ncls_capacity = (
            parameters["volume_ncls"]
            * parameters["num_electrons_ncls"]
            * (parameters["c_ox_ncls"] + parameters["c_red_ncls"])
        )
        if cls_capacity >= ncls_capacity:
            raise ValueError("initial CLS capacity must be less than initial NCLS capacity")
        if parameters["ocv_50_soc"] == 0.0 and parameters["volume_cls"] >= parameters["volume_ncls"]:
            raise ValueError("symmetric-cell volume_cls must be less than volume_ncls")
        if (
            parameters["ocv_50_soc"] == 0.0
            and parameters["num_electrons_cls"] != parameters["num_electrons_ncls"]
        ):
            raise ValueError("symmetric-cell electron counts must match")
        return parameters

    def identity_metadata(self) -> dict[str, Any]:
        """Execution-only adapter and environment identity, excluding model values."""

        return {
            "adapter": {"id": self.adapter_id, "version": self.adapter_version},
            "reducer": {"id": self.reducer_id, "version": self.reducer_version},
            "rfbzero_version": self.rfbzero_version,
            "dependency_pins": dict(self.dependency_pins),
        }


@dataclass(frozen=True)
class _RFBFailureScheduleV1:
    """Private execution policy retained separately from the public scenario."""

    mode: str
    failed_candidate_indices: tuple[int, ...]

    def __post_init__(self) -> None:
        if self.mode != "clean":
            raise ValueError("RFB V1 currently supports only a clean private failure schedule")
        if self.failed_candidate_indices:
            raise ValueError("a clean private failure schedule cannot name failed candidates")


@dataclass(frozen=True)
class LoadedRFBScenarioV1:
    """Loaded execution data with an explicitly separated planner-safe projection."""

    public_scenario: RFBScenarioV1
    scenario_identity: dict[str, Any]
    execution_oracle_spec: RFBZeroOracleSpecV1 = field(repr=False)
    execution_identity: dict[str, Any] = field(repr=False)
    _failure_schedule: _RFBFailureScheduleV1 = field(repr=False)

    def __post_init__(self) -> None:
        object.__setattr__(self, "scenario_identity", copy.deepcopy(self.scenario_identity))
        object.__setattr__(self, "execution_identity", copy.deepcopy(self.execution_identity))

    def public_projection(self) -> RFBScenarioV1:
        return self.public_scenario

    def public_state(
        self,
        outcomes: tuple[RFBOutcomeV1, ...] = (),
        *,
        remaining_attempt_budget: int | None = None,
        remaining_measurement_budget: int | None = None,
    ) -> RFBPublicStateV1:
        return RFBPublicStateV1(
            scenario=self.public_scenario,
            outcomes=outcomes,
            remaining_attempt_budget=(
                self.public_scenario.total_attempt_budget
                if remaining_attempt_budget is None
                else remaining_attempt_budget
            ),
            remaining_measurement_budget=(
                self.public_scenario.total_measurement_budget
                if remaining_measurement_budget is None
                else remaining_measurement_budget
            ),
        )


def _parse_public_scenario(config: dict[str, Any]) -> RFBScenarioV1:
    _require_exact_keys(
        config,
        {
            "schema_version",
            "scenario_id",
            "scenario_version",
            "provenance",
            "world",
            "action_space",
            "validation",
            "utility",
            "private",
        },
        "RFB scenario",
    )
    if config["schema_version"] != RFB_SCENARIO_SCHEMA_VERSION:
        raise ValueError(f"unsupported RFB scenario schema: {config['schema_version']!r}")
    if config["provenance"] != RFB_PROVENANCE:
        raise ValueError("RFB scenario provenance must be simulated")
    scenario_id = _nonempty_string(config["scenario_id"], "scenario_id")
    scenario_version = _nonempty_string(config["scenario_version"], "scenario_version")

    world = _require_object(config["world"], "world")
    _require_exact_keys(world, {"model_dimension", "total_attempt_budget", "total_measurement_budget"}, "world")
    if world["model_dimension"] != "0D":
        raise ValueError("RFB V1 scenarios support only a simulated 0D model")

    action_space = _require_object(config["action_space"], "action_space")
    _require_exact_keys(
        action_space,
        {"serialized_fields", "varying_axes", "fixed", "candidates"},
        "action_space",
    )
    if tuple(action_space["serialized_fields"]) != CANONICAL_ACTION_FIELDS:
        raise ValueError("serialized_fields must be the ordered five-field RFB V1 contract")
    if tuple(action_space["varying_axes"]) != V1_VARYING_AXES:
        raise ValueError("RFB V1 may vary only charge_current_A and discharge_current_A")
    fixed = _require_object(action_space["fixed"], "action_space.fixed")
    _require_exact_keys(fixed, set(V1_FIXED_ACTION_FIELDS), "action_space.fixed")

    candidates = action_space["candidates"]
    if not isinstance(candidates, list) or not candidates:
        raise ValueError("action_space.candidates must be a non-empty JSON array")
    actions = tuple(RFBActionV1.from_dict(_require_object(raw, "candidate")) for raw in candidates)

    validation = _require_object(config["validation"], "validation")
    _require_exact_keys(validation, {"ranges", "fixed_fields", "ocv_50_soc_V"}, "validation")
    validation_fixed = _require_object(validation["fixed_fields"], "validation.fixed_fields")
    _require_exact_keys(validation_fixed, set(V1_FIXED_ACTION_FIELDS), "validation.fixed_fields")
    if dict(validation_fixed) != fixed:
        raise ValueError("validation.fixed_fields must match action_space.fixed")
    action_schema = RFBActionSchemaV1(_require_object(validation["ranges"], "validation.ranges"))

    utility_config = _require_object(config["utility"], "utility")
    _require_exact_keys(utility_config, {"energy_reference_J", "duration_reference_s"}, "utility")
    utility = FrozenScalarUtilityV1(**utility_config)
    _require_object(config["private"], "private")
    return RFBScenarioV1(
        scenario_id=scenario_id,
        scenario_version=scenario_version,
        candidate_actions=actions,
        action_schema=action_schema,
        fixed_fields=validation_fixed,
        ocv_50_soc_V=validation["ocv_50_soc_V"],
        utility=utility,
        total_attempt_budget=_positive_int(world["total_attempt_budget"], "world.total_attempt_budget"),
        total_measurement_budget=_positive_int(
            world["total_measurement_budget"], "world.total_measurement_budget"
        ),
    )


def _parse_private_execution_data(
    config: dict[str, Any], public: RFBScenarioV1
) -> tuple[RFBZeroOracleSpecV1, _RFBFailureScheduleV1]:
    private = _require_object(config["private"], "private")
    _require_exact_keys(private, {"oracle", "failure_schedule"}, "private")

    oracle = _require_object(private["oracle"], "private.oracle")
    _require_exact_keys(
        oracle,
        {
            "adapter_id",
            "adapter_version",
            "reducer_id",
            "reducer_version",
            "rfbzero_version",
            "model_parameters",
            "capacity_reference_C",
            "charge_first",
            "dependency_pins",
        },
        "private.oracle",
    )
    spec = RFBZeroOracleSpecV1(
        adapter_id=oracle["adapter_id"],
        adapter_version=oracle["adapter_version"],
        reducer_id=oracle["reducer_id"],
        reducer_version=oracle["reducer_version"],
        rfbzero_version=oracle["rfbzero_version"],
        model_parameters=_require_object(oracle["model_parameters"], "private.oracle.model_parameters"),
        capacity_reference_C=oracle["capacity_reference_C"],
        charge_first=oracle["charge_first"],
        dependency_pins=_require_object(oracle["dependency_pins"], "private.oracle.dependency_pins"),
    )
    if spec.model_parameters["ocv_50_soc"] != public.ocv_50_soc_V:
        raise ValueError("private oracle ocv_50_soc must match the published ocv_50_soc_V constraint")

    failure_schedule = _require_object(private["failure_schedule"], "private.failure_schedule")
    _require_exact_keys(failure_schedule, {"mode", "failed_candidate_indices"}, "private.failure_schedule")
    failed_candidate_indices = failure_schedule["failed_candidate_indices"]
    if not isinstance(failed_candidate_indices, list) or any(
        isinstance(index, bool) or not isinstance(index, int) or index < 0
        for index in failed_candidate_indices
    ):
        raise ValueError("private.failure_schedule.failed_candidate_indices must contain non-negative integers")
    return spec, _RFBFailureScheduleV1(
        mode=failure_schedule["mode"],
        failed_candidate_indices=tuple(failed_candidate_indices),
    )


def _canonical_json_bytes(value: Mapping[str, Any]) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("utf-8")


def _private_commitment(config: dict[str, Any], key: bytes) -> str:
    return hmac.new(key, _canonical_json_bytes(config["private"]), hashlib.sha256).hexdigest()


def _commitment_key(private_commitment_key: bytes | str | None) -> bytes:
    if private_commitment_key is None:
        return secrets.token_bytes(32)
    if isinstance(private_commitment_key, str):
        key = private_commitment_key.encode("utf-8")
    elif isinstance(private_commitment_key, bytes):
        key = private_commitment_key
    else:
        raise TypeError("private_commitment_key must be bytes, str, or None")
    if not key:
        raise ValueError("private_commitment_key must not be empty")
    return key


def _public_config(config: dict[str, Any]) -> dict[str, Any]:
    return {name: value for name, value in config.items() if name != "private"}


def _scenario_identity(
    config: dict[str, Any], raw: bytes, public: RFBScenarioV1, private_commitment_key: bytes
) -> dict[str, Any]:
    public_config = _public_config(config)
    identity = {
        "domain_version": RFB_DOMAIN_VERSION,
        "scenario_schema_version": RFB_SCENARIO_SCHEMA_VERSION,
        "scenario_id": public.scenario_id,
        "scenario_version": public.scenario_version,
        "provenance": RFB_PROVENANCE,
        "source_sha256": hashlib.sha256(_canonical_json_bytes(public_config)).hexdigest(),
        "canonical_public_config_sha256": sha256_json(public_config),
        "public_projection_sha256": public.public_projection_sha256,
        "candidate_set_sha256": public.candidate_set_sha256,
        "private_config_hmac_sha256": _private_commitment(config, private_commitment_key),
    }
    return {**identity, "identity_sha256": sha256_json(identity)}


def load_rfb_scenario(
    path: str | Path, *, private_commitment_key: bytes | str | None = None
) -> LoadedRFBScenarioV1:
    """Load one RFB V1 scenario and return separated public and execution data.

    Callers that need a stable commitment comparison must provide a secret
    ``private_commitment_key``. Without one, each load uses fresh random keying
    material so a public identity cannot become a reusable private-config digest.
    """

    scenario_path = Path(path)
    raw = scenario_path.read_bytes()
    try:
        config = json.loads(raw.decode("utf-8"), object_pairs_hook=_reject_duplicate_keys)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"cannot decode RFB scenario JSON: {scenario_path}") from exc
    config = _require_object(config, "RFB scenario")
    public = _parse_public_scenario(config)
    oracle_spec, failure_schedule = _parse_private_execution_data(config, public)
    commitment_key = _commitment_key(private_commitment_key)
    return LoadedRFBScenarioV1(
        public_scenario=public,
        scenario_identity=_scenario_identity(config, raw, public, commitment_key),
        execution_oracle_spec=oracle_spec,
        execution_identity=oracle_spec.identity_metadata(),
        _failure_schedule=failure_schedule,
    )


__all__ = [
    "LoadedRFBScenarioV1",
    "RFB_SCENARIO_SCHEMA_VERSION",
    "RFBZERO_MODEL_PARAMETER_FIELDS",
    "RFBZeroOracleSpecV1",
    "load_rfb_scenario",
]
