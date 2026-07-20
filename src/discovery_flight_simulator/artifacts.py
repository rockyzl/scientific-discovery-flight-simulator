"""Integrity and private-seed commitment checks for completed artifact bundles."""

from __future__ import annotations

import hashlib
import hmac
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .ledger import EvidenceLedger, SCHEMA_VERSION, canonical_json, sha256_json

COMMITMENT_ALGORITHM = "hmac-sha256-v1"
EXPECTED_PLANNERS = ("fixed_grid", "information_gain", "random")
_HEX_64 = re.compile(r"^[0-9a-f]{64}$")
_PRIVATE_SEED_NAMES = ("world_seed", "noise_seed", "failure_seed")


class ArtifactVerificationError(ValueError):
    """Raised when a completed artifact bundle is absent, inconsistent, or tampered."""


@dataclass(frozen=True)
class VerifiedArtifactBundle:
    path: Path
    manifest: dict[str, Any]
    summary: dict[str, Any]
    ledgers: dict[str, EvidenceLedger]


def seed_commitment(replay_key: str, seed_name: str, seed: int) -> str:
    """Commit to a private seed without exposing it in pre-reveal artifacts."""

    if not replay_key:
        raise ValueError("replay_key must be non-empty")
    if seed_name not in _PRIVATE_SEED_NAMES:
        raise ValueError(f"unsupported private seed name: {seed_name!r}")
    message = canonical_json({"name": seed_name, "seed": int(seed)}).encode("utf-8")
    return hmac.new(replay_key.encode("utf-8"), message, hashlib.sha256).hexdigest()


def public_seed_record(planner_seed: int, scenario_identity: dict[str, Any]) -> dict[str, Any]:
    commitments = scenario_identity.get("seed_commitments")
    _validate_commitments(commitments)
    return {"planner_seed": int(planner_seed), "commitments": dict(commitments)}


def _reject_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ArtifactVerificationError(f"duplicate JSON key: {key!r}")
        result[key] = value
    return result


def _read_json(path: Path) -> dict[str, Any]:
    try:
        raw = json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=_reject_duplicate_keys)
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ArtifactVerificationError(f"cannot read JSON artifact {path}: {exc}") from exc
    if not isinstance(raw, dict):
        raise ArtifactVerificationError(f"artifact must contain a JSON object: {path}")
    return raw


def _file_sha256(path: Path) -> str:
    try:
        return hashlib.sha256(path.read_bytes()).hexdigest()
    except OSError as exc:
        raise ArtifactVerificationError(f"cannot read artifact {path}: {exc}") from exc


def _validate_commitments(value: Any) -> None:
    if not isinstance(value, dict):
        raise ArtifactVerificationError("private seed commitments are missing")
    if value.get("algorithm") != COMMITMENT_ALGORITHM:
        raise ArtifactVerificationError("unsupported private seed commitment algorithm")
    if set(value) != {"algorithm", *_PRIVATE_SEED_NAMES}:
        raise ArtifactVerificationError("private seed commitment fields do not match the schema")
    for name in _PRIVATE_SEED_NAMES:
        digest = value.get(name)
        if not isinstance(digest, str) or not _HEX_64.fullmatch(digest):
            raise ArtifactVerificationError(f"invalid commitment for {name}")


def _validate_public_seeds(value: Any) -> None:
    if not isinstance(value, dict) or set(value) != {"planner_seed", "commitments"}:
        raise ArtifactVerificationError(
            "public seeds must contain only planner_seed and private commitments"
        )
    if isinstance(value["planner_seed"], bool) or not isinstance(value["planner_seed"], int):
        raise ArtifactVerificationError("planner_seed must be an integer")
    _validate_commitments(value["commitments"])


def _without_hash(value: dict[str, Any], field: str) -> dict[str, Any]:
    return {key: item for key, item in value.items() if key != field}


def _assert_equal(label: str, left: Any, right: Any) -> None:
    if left != right:
        raise ArtifactVerificationError(f"cross-artifact identity mismatch: {label}")


def _verify_reveal(seeds: dict[str, Any], reveal: Any) -> None:
    if not isinstance(reveal, dict):
        raise ArtifactVerificationError("completed summary is missing post_run_reveal")
    replay_key = reveal.get("replay_key")
    private_seeds = reveal.get("private_seeds")
    if not isinstance(replay_key, str) or not replay_key:
        raise ArtifactVerificationError("post_run_reveal replay_key is missing")
    if not isinstance(private_seeds, dict) or set(private_seeds) != set(_PRIVATE_SEED_NAMES):
        raise ArtifactVerificationError("post_run_reveal private_seeds do not match the schema")
    commitments = seeds["commitments"]
    for name in _PRIVATE_SEED_NAMES:
        seed = private_seeds[name]
        if isinstance(seed, bool) or not isinstance(seed, int):
            raise ArtifactVerificationError(f"revealed {name} must be an integer")
        expected = seed_commitment(replay_key, name, seed)
        if not hmac.compare_digest(expected, commitments[name]):
            raise ArtifactVerificationError(f"revealed {name} does not match its commitment")


def verify_artifact_bundle(path: str | Path) -> VerifiedArtifactBundle:
    """Verify a complete comparison bundle or raise before it can be served."""

    root = Path(path)
    if not root.is_dir():
        raise ArtifactVerificationError(f"artifact bundle is not a directory: {root}")
    manifest_path = root / "manifest.json"
    if not manifest_path.is_file():
        raise ArtifactVerificationError("manifest.json is missing")

    manifest = _read_json(manifest_path)
    supplied_manifest_hash = manifest.get("manifest_payload_sha256")
    if supplied_manifest_hash != sha256_json(_without_hash(manifest, "manifest_payload_sha256")):
        raise ArtifactVerificationError("manifest self-hash mismatch")
    if manifest.get("schema_version") != SCHEMA_VERSION:
        raise ArtifactVerificationError("manifest schema version mismatch")
    if manifest.get("provenance") != "simulated":
        raise ArtifactVerificationError("manifest provenance must be simulated")
    if manifest.get("status") != "complete":
        raise ArtifactVerificationError("artifact bundle is not marked complete")

    expected_artifacts = {
        "summary.json",
        *(f"ledgers/{name}.json" for name in EXPECTED_PLANNERS),
    }
    artifacts = manifest.get("artifacts")
    if not isinstance(artifacts, dict) or set(artifacts) != expected_artifacts:
        raise ArtifactVerificationError("manifest artifact inventory does not match the contract")
    actual_files = {
        file.relative_to(root).as_posix() for file in root.rglob("*") if file.is_file()
    }
    if actual_files != {"manifest.json", *expected_artifacts}:
        raise ArtifactVerificationError("artifact bundle has a missing or unexpected file")
    for relative_path, expected_hash in artifacts.items():
        if not isinstance(expected_hash, str) or not _HEX_64.fullmatch(expected_hash):
            raise ArtifactVerificationError(f"invalid file hash for {relative_path}")
        if _file_sha256(root / relative_path) != expected_hash:
            raise ArtifactVerificationError(f"artifact file hash mismatch: {relative_path}")

    summary = _read_json(root / "summary.json")
    supplied_summary_hash = summary.get("summary_sha256")
    if supplied_summary_hash != sha256_json(_without_hash(summary, "summary_sha256")):
        raise ArtifactVerificationError("summary self-hash mismatch")
    if summary.get("schema_version") != SCHEMA_VERSION:
        raise ArtifactVerificationError("summary schema version mismatch")
    if summary.get("provenance") != "simulated":
        raise ArtifactVerificationError("summary provenance must be simulated")
    if summary.get("status") != "complete":
        raise ArtifactVerificationError("summary is not marked complete")

    planners = manifest.get("planners")
    if not isinstance(planners, dict) or set(planners) != set(EXPECTED_PLANNERS):
        raise ArtifactVerificationError("manifest planner set does not match the contract")
    _assert_equal("planners", planners, summary.get("planners"))
    _assert_equal("world_id", manifest.get("world_id"), summary.get("world_id"))
    _assert_equal("world_version", manifest.get("world_version"), summary.get("world_version"))
    _assert_equal(
        "scenario_identity", manifest.get("scenario_identity"), summary.get("scenario_identity")
    )
    _assert_equal("seeds", manifest.get("seeds"), summary.get("seeds"))
    _validate_public_seeds(manifest.get("seeds"))
    scenario_identity = manifest.get("scenario_identity")
    if not isinstance(scenario_identity, dict):
        raise ArtifactVerificationError("scenario_identity must be an object")
    _assert_equal(
        "scenario seed commitments",
        manifest["seeds"]["commitments"],
        scenario_identity.get("seed_commitments"),
    )

    results = summary.get("results")
    if not isinstance(results, dict) or set(results) != set(EXPECTED_PLANNERS):
        raise ArtifactVerificationError("summary result set does not match the planner contract")
    ledgers: dict[str, EvidenceLedger] = {}
    for name in EXPECTED_PLANNERS:
        result = results[name]
        expected_path = f"ledgers/{name}.json"
        if not isinstance(result, dict) or result.get("ledger") != expected_path:
            raise ArtifactVerificationError(f"summary ledger path mismatch for {name}")
        try:
            ledger = EvidenceLedger.read_json(root / expected_path)
        except (KeyError, TypeError, ValueError) as exc:
            raise ArtifactVerificationError(f"invalid ledger for {name}: {exc}") from exc
        if ledger.completion_status not in {"stopped", "budget_exhausted"}:
            raise ArtifactVerificationError(f"ledger is incomplete for {name}")
        _assert_equal(f"ledger {name} world_id", manifest["world_id"], ledger.spec.world_id)
        _assert_equal(
            f"ledger {name} world_version", manifest["world_version"], ledger.spec.world_version
        )
        _assert_equal(
            f"ledger {name} scenario_identity", scenario_identity, ledger.scenario_identity
        )
        _assert_equal(f"ledger {name} seeds", manifest["seeds"], ledger.public_seeds)
        _assert_equal(f"ledger {name} planner", planners[name], {
            "name": ledger.planner_name,
            "version": ledger.planner_version,
        })
        _assert_equal(
            f"ledger {name} payload hash",
            result.get("ledger_sha256"),
            ledger.to_dict()["ledger_sha256"],
        )
        ledgers[name] = ledger

    _verify_reveal(manifest["seeds"], summary.get("post_run_reveal"))
    return VerifiedArtifactBundle(root, manifest, summary, ledgers)
