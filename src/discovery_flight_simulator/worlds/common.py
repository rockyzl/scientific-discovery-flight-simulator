"""Shared deterministic helpers for synthetic scientific worlds."""

from __future__ import annotations

import hashlib
import random
from typing import Any


def stable_seed(*parts: Any) -> int:
    """Return a process-independent seed derived from JSON-like values."""

    payload = "|".join(str(part) for part in parts).encode("utf-8")
    return int.from_bytes(hashlib.sha256(payload).digest()[:8], "big")


def indexed_gaussian(seed: int, condition: str, repeat_index: int, sigma: float) -> float:
    """Noise tied to a condition and repeat, rather than experiment order."""

    rng = random.Random(stable_seed(seed, condition, repeat_index))
    return rng.gauss(0.0, sigma)


def failure_schedule(profile: dict[str, Any], failure_seed: int) -> dict[str, Any]:
    """Materialize a deterministic, private attempt-indexed failure schedule."""

    if profile.get("name", "clean") == "clean":
        return {
            "name": "clean",
            "timeout_attempts": (),
            "drift_start_attempt": None,
            "drift_per_attempt": 0.0,
            "saturation_threshold": None,
        }

    rng = random.Random(stable_seed("failure", failure_seed))
    configured = tuple(int(value) for value in profile.get("timeout_attempts", ()))
    # Explicit attempts are frozen benchmark inputs. The seed controls latent drift direction,
    # but never silently shifts a documented forced failure to another attempt.
    timeout_attempts = tuple(max(1, value) for value in configured)
    drift = abs(float(profile.get("drift_per_attempt", 0.0)))
    drift_sign = -1.0 if rng.random() < 0.5 else 1.0
    return {
        "name": str(profile.get("name", "challenge")),
        "timeout_attempts": timeout_attempts,
        "drift_start_attempt": profile.get("drift_start_attempt"),
        "drift_per_attempt": drift_sign * drift,
        "saturation_threshold": profile.get("saturation_threshold"),
    }


def drift_at_attempt(schedule: dict[str, Any], attempt_index: int) -> float:
    start = schedule.get("drift_start_attempt")
    if start is None or attempt_index < int(start):
        return 0.0
    return (attempt_index - int(start) + 1) * float(schedule["drift_per_attempt"])
