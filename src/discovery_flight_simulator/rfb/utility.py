"""Canonical public outcome-to-utility records for the frozen RFB V1 utility."""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any

from discovery_flight_simulator.ledger import sha256_json

from .contracts import FrozenScalarUtilityV1, RFBOutcomeV1

RFB_UTILITY_RECORD_SCHEMA_VERSION = "rfb_utility_record_v1"


@dataclass(frozen=True)
class RFBUtilityRecordV1:
    """One serializable scalar-utility result tied to its frozen public utility."""

    utility_sha256: str
    outcome_sha256: str | None
    utility: float
    valid: bool
    schema_version: str = RFB_UTILITY_RECORD_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if self.schema_version != RFB_UTILITY_RECORD_SCHEMA_VERSION:
            raise ValueError(f"unsupported utility record schema: {self.schema_version!r}")
        if not _is_sha256(self.utility_sha256):
            raise ValueError("utility_sha256 must be a lowercase SHA-256 hex digest")
        if self.outcome_sha256 is not None and not _is_sha256(self.outcome_sha256):
            raise ValueError("outcome_sha256 must be a lowercase SHA-256 hex digest or None")
        if isinstance(self.utility, bool) or not isinstance(self.utility, (int, float)):
            raise ValueError("utility must be a finite number")
        utility = float(self.utility)
        if not math.isfinite(utility):
            raise ValueError("utility must be a finite number")
        if not isinstance(self.valid, bool):
            raise ValueError("valid must be a boolean")
        if not self.valid and utility != FrozenScalarUtilityV1.invalid_result_utility:
            raise ValueError("invalid utility records must use the fail-closed utility")
        object.__setattr__(self, "utility", utility)

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "utility_sha256": self.utility_sha256,
            "outcome_sha256": self.outcome_sha256,
            "utility": self.utility,
            "valid": self.valid,
        }


def utility_record_for_outcome(
    outcome: RFBOutcomeV1 | None, utility: FrozenScalarUtilityV1
) -> RFBUtilityRecordV1:
    """Score an outcome once, failing closed for invalid, failed, or missing data."""

    if not isinstance(utility, FrozenScalarUtilityV1):
        raise ValueError("utility must be a FrozenScalarUtilityV1")
    outcome_sha256 = _outcome_sha256(outcome)
    if not _is_scoreable(outcome):
        return RFBUtilityRecordV1(
            utility_sha256=utility.utility_sha256,
            outcome_sha256=outcome_sha256,
            utility=utility.invalid_result_utility,
            valid=False,
        )

    assert outcome is not None
    energy = outcome.delivered_discharge_energy_J
    efficiency = outcome.round_trip_efficiency
    retention = outcome.capacity_retention
    duration = outcome.elapsed_duration_s
    assert energy is not None and efficiency is not None and retention is not None and duration is not None
    value = (
        utility.energy_weight * _clip(energy / utility.energy_reference_J)
        + utility.efficiency_weight * _clip(efficiency)
        + utility.retention_weight * _clip(retention)
        - utility.duration_penalty_weight * _clip(duration / utility.duration_reference_s)
    )
    return RFBUtilityRecordV1(
        utility_sha256=utility.utility_sha256,
        outcome_sha256=outcome_sha256,
        utility=value,
        valid=True,
    )


def score_outcome(outcome: RFBOutcomeV1 | None, utility: FrozenScalarUtilityV1) -> float:
    """Compatibility scalar view of :func:`utility_record_for_outcome`."""

    return utility_record_for_outcome(outcome, utility).utility


canonical_utility_record = utility_record_for_outcome


def _is_scoreable(outcome: RFBOutcomeV1 | None) -> bool:
    if outcome is None or outcome.status != "complete" or outcome.qc_flags:
        return False
    values = (
        outcome.delivered_discharge_energy_J,
        outcome.round_trip_efficiency,
        outcome.capacity_retention,
        outcome.elapsed_duration_s,
    )
    return all(value is not None and math.isfinite(value) for value in values)


def _clip(value: float) -> float:
    return max(0.0, min(1.0, value))


def _outcome_sha256(outcome: RFBOutcomeV1 | None) -> str | None:
    if not isinstance(outcome, RFBOutcomeV1):
        return None
    try:
        return sha256_json(outcome.to_dict())
    except (TypeError, ValueError):
        # A non-finite outcome is invalid and cannot be a canonical public payload.
        return None


def _is_sha256(value: object) -> bool:
    return (
        isinstance(value, str)
        and len(value) == 64
        and all(character in "0123456789abcdef" for character in value)
    )


__all__ = [
    "RFB_UTILITY_RECORD_SCHEMA_VERSION",
    "RFBUtilityRecordV1",
    "canonical_utility_record",
    "score_outcome",
    "utility_record_for_outcome",
]
