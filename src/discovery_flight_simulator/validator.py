"""Fail-closed validation for public experiment requests."""

from __future__ import annotations

import math

from .contracts import (
    ExperimentRequest,
    InstrumentCapabilities,
    PublicWorldSpec,
    ValidationResult,
)

_NO_CONTROL_OPERATIONS = frozenset({"calibrate", "reference", "reset"})


class ProtocolValidator:
    """Validate only public capabilities and constraints; never inspect world truth."""

    def validate(
        self,
        request: ExperimentRequest,
        spec: PublicWorldSpec,
        capabilities: InstrumentCapabilities,
    ) -> ValidationResult:
        reasons: list[str] = []

        if not request.request_id.strip():
            reasons.append("request_id must be non-empty")
        if request.operation not in spec.operations:
            reasons.append(f"operation {request.operation!r} is not allowed by the world")
        if request.operation not in capabilities.operations:
            reasons.append(f"operation {request.operation!r} is not supported by the instrument")

        allowed_controls = set(spec.controls) & set(capabilities.control_ranges)
        for name in sorted(set(request.controls) - allowed_controls):
            reasons.append(f"unknown or unsupported control {name!r}")

        if request.operation not in _NO_CONTROL_OPERATIONS:
            for name in sorted(set(spec.controls) - set(request.controls)):
                reasons.append(f"missing required control {name!r}")

        for name, value in sorted(request.controls.items()):
            if not math.isfinite(value):
                reasons.append(f"control {name!r} must be finite")
                continue
            if name not in allowed_controls:
                continue
            spec_low, spec_high = spec.controls[name]
            cap_low, cap_high = capabilities.control_ranges[name]
            low, high = max(spec_low, cap_low), min(spec_high, cap_high)
            if low > high:
                reasons.append(f"world and instrument ranges do not overlap for {name!r}")
            elif value < low or value > high:
                reasons.append(f"control {name!r}={value} is outside [{low}, {high}]")

        accepted = not reasons
        return ValidationResult(
            accepted=accepted,
            reasons=tuple(reasons),
            attempt_cost=1,
            measurement_cost=1 if accepted else 0,
        )
