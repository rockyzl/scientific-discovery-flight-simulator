"""Append-only, hash-chained evidence ledger for simulated campaigns."""

from __future__ import annotations

import copy
import hashlib
import json
from dataclasses import replace
from pathlib import Path
from typing import Any

from .contracts import (
    ExperimentEvent,
    ExperimentRequest,
    Observation,
    PublicWorldSpec,
    SeedBundle,
    StopDecision,
    ValidationResult,
    to_primitive,
)

SCHEMA_VERSION = "1"
_GENESIS_HASH = "0" * 64


def canonical_json(value: Any) -> str:
    return json.dumps(
        to_primitive(value),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    )


def sha256_json(value: Any) -> str:
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


def _event_hash(event: ExperimentEvent, previous_hash: str) -> str:
    unsigned = replace(event, hashes={})
    return sha256_json({"previous": previous_hash, "event": unsigned})


class EvidenceLedger:
    """An append-only campaign trace with deterministic JSON and replay verification."""

    schema_version = SCHEMA_VERSION

    def __init__(
        self,
        spec: PublicWorldSpec,
        seed_bundle: SeedBundle | None,
        planner_name: str,
        planner_version: str,
        scenario_identity: Any,
        *,
        public_seeds: dict[str, Any] | None = None,
    ) -> None:
        self.spec = copy.deepcopy(spec)
        self.planner_name = str(planner_name)
        self.planner_version = str(planner_version)
        self.scenario_identity = copy.deepcopy(scenario_identity)
        if public_seeds is None:
            if seed_bundle is None or not isinstance(scenario_identity, dict):
                raise ValueError("ledger requires public planner seed and private commitments")
            commitments = scenario_identity.get("seed_commitments")
            if not isinstance(commitments, dict):
                raise ValueError("scenario identity is missing private seed commitments")
            public_seeds = {
                "planner_seed": seed_bundle.planner_seed,
                "commitments": commitments,
            }
        self.public_seeds = copy.deepcopy(public_seeds)
        self._events: list[ExperimentEvent] = []

    @property
    def events(self) -> tuple[ExperimentEvent, ...]:
        return tuple(copy.deepcopy(self._events))

    @property
    def completion_status(self) -> str:
        if self._events and self._events[-1].stop is not None:
            return "stopped"
        if self._events:
            costs = self._events[-1].costs
            if (
                costs.get("cumulative_attempt", 0) >= self.spec.total_attempt_budget
                or costs.get("cumulative_measurement", 0) >= self.spec.total_measurement_budget
            ):
                return "budget_exhausted"
        return "incomplete"

    def append(self, event: ExperimentEvent) -> ExperimentEvent:
        if event.sequence != len(self._events):
            raise ValueError(f"event sequence must be {len(self._events)}, got {event.sequence}")
        if event.hashes:
            raise ValueError("new events must not supply hashes; the ledger owns the hash chain")
        previous = self._events[-1].hashes["event"] if self._events else _GENESIS_HASH
        digest = _event_hash(event, previous)
        stamped = replace(event, hashes={"previous": previous, "event": digest})
        self._events.append(copy.deepcopy(stamped))
        return copy.deepcopy(stamped)

    def _payload(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "provenance": "simulated",
            "world": to_primitive(self.spec),
            "planner": {"name": self.planner_name, "version": self.planner_version},
            "seeds": to_primitive(self.public_seeds),
            "scenario_identity": to_primitive(self.scenario_identity),
            "completion_status": self.completion_status,
            "events": [to_primitive(event) for event in self._events],
        }

    def to_dict(self) -> dict[str, Any]:
        payload = self._payload()
        return {**payload, "ledger_sha256": sha256_json(payload)}

    def to_json(self) -> str:
        return json.dumps(
            self.to_dict(),
            sort_keys=True,
            indent=2,
            ensure_ascii=False,
            allow_nan=False,
        ) + "\n"

    def write_json(self, path: str | Path) -> None:
        Path(path).write_text(self.to_json(), encoding="utf-8")

    def verify(self) -> bool:
        previous = _GENESIS_HASH
        for sequence, event in enumerate(self._events):
            if event.sequence != sequence:
                return False
            expected = _event_hash(event, previous)
            if event.hashes != {"previous": previous, "event": expected}:
                return False
            previous = expected
        exported = self.to_dict()
        digest = exported.pop("ledger_sha256")
        return digest == sha256_json(exported)

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> "EvidenceLedger":
        if raw.get("schema_version") != SCHEMA_VERSION:
            raise ValueError(f"unsupported ledger schema: {raw.get('schema_version')!r}")
        if raw.get("provenance") != "simulated":
            raise ValueError("ledger provenance must be simulated")
        supplied_digest = raw.get("ledger_sha256")
        payload = {key: value for key, value in raw.items() if key != "ledger_sha256"}
        if supplied_digest != sha256_json(payload):
            raise ValueError("ledger payload hash mismatch")

        world = raw["world"]
        spec = PublicWorldSpec(
            world_id=world["world_id"],
            world_version=world["world_version"],
            controls=world["controls"],
            operations=tuple(world["operations"]),
            total_attempt_budget=int(world["total_attempt_budget"]),
            total_measurement_budget=int(world["total_measurement_budget"]),
            provenance=world["provenance"],
        )
        planner = raw["planner"]
        ledger = cls(
            spec,
            None,
            planner["name"],
            planner["version"],
            raw["scenario_identity"],
            public_seeds=raw["seeds"],
        )
        for event_raw in raw["events"]:
            request_raw = event_raw.get("request")
            stop_raw = event_raw.get("stop")
            validation_raw = event_raw.get("validation")
            observation_raw = event_raw.get("observation")
            event = ExperimentEvent(
                sequence=int(event_raw["sequence"]),
                request=ExperimentRequest(**request_raw) if request_raw else None,
                stop=StopDecision(**stop_raw) if stop_raw else None,
                validation=(
                    ValidationResult(
                        accepted=validation_raw["accepted"],
                        reasons=tuple(validation_raw["reasons"]),
                        attempt_cost=validation_raw["attempt_cost"],
                        measurement_cost=validation_raw["measurement_cost"],
                    )
                    if validation_raw
                    else None
                ),
                observation=(
                    Observation(
                        status=observation_raw["status"],
                        requested_controls=observation_raw["requested_controls"],
                        executed_controls=observation_raw["executed_controls"],
                        value=observation_raw["value"],
                        standard_error=observation_raw["standard_error"],
                        qc_flags=tuple(observation_raw["qc_flags"]),
                        attempt_cost=observation_raw["attempt_cost"],
                        measurement_cost=observation_raw["measurement_cost"],
                        provenance=observation_raw["provenance"],
                    )
                    if observation_raw
                    else None
                ),
                beliefs_before=event_raw["beliefs_before"],
                beliefs_after=event_raw["beliefs_after"],
                costs=event_raw["costs"],
                hashes=event_raw["hashes"],
            )
            ledger._events.append(event)
        if raw.get("completion_status") != ledger.completion_status:
            raise ValueError("ledger completion status mismatch")
        if not ledger.verify():
            raise ValueError("ledger event hash chain mismatch")
        return ledger

    @classmethod
    def read_json(cls, path: str | Path) -> "EvidenceLedger":
        return cls.from_dict(json.loads(Path(path).read_text(encoding="utf-8")))
