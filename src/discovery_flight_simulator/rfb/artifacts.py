"""Public RFB store-journal artifact export and verification.

``rfb_artifact_v1`` writes the exact public value returned by
``SQLiteRFBCampaignStore.export_campaign()``.  The artifact layer never makes
its own event hashes: canonical ``rfb_campaign_event_v1`` records are verified
by the pure replay reducer before export and when an artifact is read.
"""

from __future__ import annotations

import ctypes
import errno
import hashlib
import json
import math
import os
import re
import shutil
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

from discovery_flight_simulator.ledger import canonical_json, sha256_json

from .replay import (
    RFBReplayError,
    RFB_WORKFLOW_VERSION,
    ReplayedRFBCampaignV1,
    replay_rfb_campaign_export_v1,
)


RFB_ARTIFACT_VERSION = "rfb_artifact_v1"
RFB_PROVENANCE = "simulated"
STRICT_BENCHMARK_MODE = "strict_benchmark"
WORKFLOW_CASE_STUDY_MODE = "workflow_case_study"

_HEX_64 = re.compile(r"^[0-9a-f]{64}$")
_CAMEL_CASE_BOUNDARY = re.compile(r"(?<=[a-z0-9])(?=[A-Z])|(?<=[A-Z])(?=[A-Z][a-z])")
_KEY_DELIMITER = re.compile(r"[^a-zA-Z0-9]+")
_ARTIFACT_FILENAMES = frozenset({"manifest.json", "journal.json"})
_MANIFEST_CORE_FIELDS = frozenset(
    {
        "artifact_schema_version",
        "workflow_schema_version",
        "provenance",
        "campaign_id",
        "public_scenario",
        "public_scenario_sha256",
        "policy",
        "execution_identity",
        "utility",
        "utility_sha256",
        "cost_model",
        "cost_model_sha256",
        "terminal_state",
        "mode",
        "comparison_eligible",
        "human_intervened",
        "event_head_sha256",
    }
)
_MANIFEST_GENERATED_FIELDS = frozenset(
    {"campaign_identity_sha256", "artifacts", "manifest_sha256"}
)
_TERMINAL_STATE_FIELDS = frozenset(
    {
        "revision",
        "phase",
        "mode",
        "comparison_eligible",
        "human_intervened",
        "cumulative_costs",
        "reserved_costs",
        "event_head_sha256",
    }
)
_SAFE_COMMITMENT_FIELD = "private_config_hmac_sha256"
_PUBLIC_SELECTION_ORDER_FIELD = "selection_order"
_PUBLIC_HIDDEN_METADATA_FIELD = "hidden_layer_count"
_PUBLIC_TOKEN_COUNT_FIELD = "token_count"
_PUBLIC_TOKENIZER_FIELD = "tokenizer"
_PUBLIC_POLICY_METADATA_FIELDS = frozenset(
    {
        _SAFE_COMMITMENT_FIELD,
        _PUBLIC_SELECTION_ORDER_FIELD,
        _PUBLIC_HIDDEN_METADATA_FIELD,
        _PUBLIC_TOKEN_COUNT_FIELD,
        _PUBLIC_TOKENIZER_FIELD,
    }
)
_PUBLIC_SELECTION_ORDERS = frozenset(
    {
        "declared_candidate_order",
        "deterministic_public_history",
        "deterministic_scalar_utility_ucb",
    }
)
_PUBLIC_TOKENIZERS = frozenset({"byte-pair", "wordpiece", "sentencepiece"})
_FORBIDDEN_PUBLIC_FIELDS = frozenset(
    {
        "private",
        "private_config",
        "oracle_config",
        "execution_oracle_spec",
        "model_parameters",
        "replay_key",
        "private_commitment_key",
        "commitment_key",
        "lease_token",
        "lease_generation",
        "lease_expires_at",
        "worker_id",
        "reviewer",
        "reviewer_id",
        "reviewer_data",
        "reviewer_notes",
        "hidden_truth",
        "hidden_state",
        "hidden_outcome",
        "hidden_optimum",
        "hidden_best",
        "evaluator_truth",
        "truth",
        "optimum",
        "token",
        "auth_token",
        "access_token",
        "bearer_token",
    }
)
_FORBIDDEN_PUBLIC_TERMS = frozenset(
    {
        "private",
        "lease",
        "reviewer",
        "oracle",
        "secret",
        "secrets",
        "password",
        "passwords",
        "credential",
        "credentials",
        "digest",
        "commitment",
    }
)
_FORBIDDEN_PUBLIC_TERM_SEQUENCES = (
    ("api", "key"),
    ("access", "key"),
)
_FORBIDDEN_PUBLIC_COMPACT_SUFFIXES = (
    "token",
    "secret",
    "secrets",
    "password",
    "passwords",
    "credential",
    "credentials",
    "digest",
    "commitment",
    "apikey",
    "accesskey",
)
_RENAME_NOREPLACE = 1
_AT_FDCWD = -100


class RFBArtifactVerificationError(ValueError):
    """Raised when an RFB artifact is private, incomplete, or inconsistent."""


@dataclass(frozen=True)
class VerifiedRFBArtifactV1:
    """A verified public store-journal artifact and its replayed terminal state."""

    path: Path
    manifest: dict[str, Any]
    journal: dict[str, Any]
    replay: ReplayedRFBCampaignV1

    @property
    def ranking_eligible(self) -> bool:
        """Whether this exact replayed campaign can participate in a ranking."""

        return self.replay.ranking_eligible


def export_rfb_artifact_v1(
    path: str | Path,
    campaign_export: Mapping[str, Any],
    *,
    policy_metadata: Mapping[str, Any],
    execution_identity: Mapping[str, Any],
) -> VerifiedRFBArtifactV1:
    """Export a public RFB artifact from ``SQLiteRFBCampaignStore.export_campaign``.

    ``policy_metadata`` and ``execution_identity`` are explicit because the
    store retains the policy ID/version and public journal, not caller runtime
    metadata.  Both are copied as public JSON and bound into the manifest.
    """

    journal = _copy_public_json(campaign_export, "campaign export")
    policy_extra = _copy_public_json(policy_metadata, "policy_metadata")
    execution = _copy_public_json(execution_identity, "execution_identity")
    replay = _replay_or_error(journal)
    _validate_policy_metadata(policy_extra)
    _validate_execution_identity(execution)
    manifest = _build_manifest(journal, replay, policy_extra, execution)
    _validate_manifest_core({key: manifest[key] for key in _MANIFEST_CORE_FIELDS})
    _validate_artifact_binding(manifest, journal, replay)

    root = Path(path)
    if root.exists():
        raise RFBArtifactVerificationError(f"RFB artifact output already exists: {root}")
    journal_bytes = _json_bytes(journal)
    artifact_manifest = {
        **manifest,
        "artifacts": {"journal.json": hashlib.sha256(journal_bytes).hexdigest()},
    }
    artifact_manifest["manifest_sha256"] = sha256_json(artifact_manifest)
    _validate_manifest(artifact_manifest)

    temporary_root: Path | None = None
    published = False
    try:
        root.parent.mkdir(parents=True, exist_ok=True)
        temporary_root = Path(tempfile.mkdtemp(prefix=f".{root.name}.tmp-", dir=root.parent))
        _write_artifact_files(temporary_root, journal_bytes, _json_bytes(artifact_manifest))
        verified = verify_rfb_artifact_v1(temporary_root)
        _publish_verified_artifact(temporary_root, root)
        published = True
        return VerifiedRFBArtifactV1(root, verified.manifest, verified.journal, verified.replay)
    except RFBArtifactVerificationError:
        raise
    except OSError as exc:
        raise RFBArtifactVerificationError(f"cannot write RFB artifact: {root}: {exc}") from exc
    finally:
        if temporary_root is not None and not published:
            _remove_temporary_artifact(temporary_root)


def verify_rfb_artifact_v1(path: str | Path) -> VerifiedRFBArtifactV1:
    """Verify a complete ``rfb_artifact_v1`` directory or fail closed."""

    root = Path(path)
    if not root.is_dir():
        raise RFBArtifactVerificationError(f"RFB artifact is not a directory: {root}")
    _verify_inventory(root)
    manifest = _read_json(root / "manifest.json")
    _validate_manifest(manifest)

    journal_path = root / "journal.json"
    if _file_sha256(journal_path) != manifest["artifacts"]["journal.json"]:
        raise RFBArtifactVerificationError("RFB journal file hash mismatch")
    journal = _read_json(journal_path)
    _assert_no_private_material(journal, "journal")
    replay = _replay_or_error(journal)
    _validate_artifact_binding(manifest, journal, replay)
    return VerifiedRFBArtifactV1(root, manifest, journal, replay)


def _build_manifest(
    journal: dict[str, Any],
    replay: ReplayedRFBCampaignV1,
    policy_metadata: dict[str, Any],
    execution_identity: dict[str, Any],
) -> dict[str, Any]:
    campaign = replay.campaign
    scenario = campaign["public_scenario"]
    terminal = _terminal_state(campaign, replay.event_head_sha256)
    core = {
        "artifact_schema_version": RFB_ARTIFACT_VERSION,
        "workflow_schema_version": RFB_WORKFLOW_VERSION,
        "provenance": RFB_PROVENANCE,
        "campaign_id": campaign["campaign_id"],
        "public_scenario": scenario,
        "public_scenario_sha256": scenario["public_projection_sha256"],
        "policy": {
            "id": campaign["policy_id"],
            "version": campaign["policy_version"],
            "metadata": policy_metadata,
        },
        "execution_identity": execution_identity,
        "utility": scenario["utility"],
        "utility_sha256": scenario["utility_sha256"],
        "cost_model": scenario["cost_model"],
        "cost_model_sha256": scenario["cost_model_sha256"],
        "terminal_state": terminal,
        "mode": campaign["mode"],
        "comparison_eligible": campaign["comparison_eligible"],
        "human_intervened": campaign["human_intervened"],
        "event_head_sha256": replay.event_head_sha256,
    }
    return {**core, "campaign_identity_sha256": sha256_json(core)}


def _validate_manifest(manifest: dict[str, Any]) -> None:
    _assert_json_primitive(manifest, "manifest")
    _assert_no_private_material(manifest, "manifest")
    _require_exact_keys(
        manifest,
        _MANIFEST_CORE_FIELDS | _MANIFEST_GENERATED_FIELDS,
        "RFB manifest",
    )
    core = {key: manifest[key] for key in _MANIFEST_CORE_FIELDS}
    _validate_manifest_core(core)
    _require_hex(manifest["campaign_identity_sha256"], "campaign_identity_sha256")
    if manifest["campaign_identity_sha256"] != sha256_json(core):
        raise RFBArtifactVerificationError("campaign identity hash mismatch")
    artifacts = manifest["artifacts"]
    if not isinstance(artifacts, dict) or set(artifacts) != {"journal.json"}:
        raise RFBArtifactVerificationError("RFB artifact inventory does not match rfb_artifact_v1")
    _require_hex(artifacts["journal.json"], "journal artifact hash")
    _require_hex(manifest["manifest_sha256"], "manifest_sha256")
    unsigned = {key: value for key, value in manifest.items() if key != "manifest_sha256"}
    if manifest["manifest_sha256"] != sha256_json(unsigned):
        raise RFBArtifactVerificationError("RFB manifest self-hash mismatch")


def _validate_manifest_core(manifest: dict[str, Any]) -> None:
    _require_exact_keys(manifest, _MANIFEST_CORE_FIELDS, "RFB manifest core")
    _require_equal(manifest["artifact_schema_version"], RFB_ARTIFACT_VERSION, "artifact schema")
    _require_equal(manifest["workflow_schema_version"], RFB_WORKFLOW_VERSION, "workflow schema")
    _require_equal(manifest["provenance"], RFB_PROVENANCE, "manifest provenance")
    _require_nonempty_string(manifest["campaign_id"], "campaign_id")
    _require_hex(manifest["public_scenario_sha256"], "public_scenario_sha256")
    _require_hex(manifest["utility_sha256"], "utility_sha256")
    _require_hex(manifest["cost_model_sha256"], "cost_model_sha256")
    _require_hex(manifest["event_head_sha256"], "event_head_sha256")
    _validate_policy(manifest["policy"])
    _validate_execution_identity(manifest["execution_identity"])
    if not isinstance(manifest["public_scenario"], dict):
        raise RFBArtifactVerificationError("public_scenario must be a JSON object")
    if not _canonical_equal(
        manifest["public_scenario"].get("public_projection_sha256"), manifest["public_scenario_sha256"]
    ):
        raise RFBArtifactVerificationError("public scenario identity hash mismatch")
    if not _canonical_equal(manifest["public_scenario"].get("utility"), manifest["utility"]):
        raise RFBArtifactVerificationError("manifest utility does not match the canonical public scenario")
    if not _canonical_equal(
        manifest["public_scenario"].get("utility_sha256"), manifest["utility_sha256"]
    ):
        raise RFBArtifactVerificationError("manifest utility hash does not match the public scenario")
    if not _canonical_equal(manifest["public_scenario"].get("cost_model"), manifest["cost_model"]):
        raise RFBArtifactVerificationError("manifest cost model does not match the canonical public scenario")
    if not _canonical_equal(
        manifest["public_scenario"].get("cost_model_sha256"), manifest["cost_model_sha256"]
    ):
        raise RFBArtifactVerificationError("manifest cost-model hash does not match the public scenario")
    if manifest["utility_sha256"] != sha256_json(manifest["utility"]):
        raise RFBArtifactVerificationError("utility definition hash mismatch")
    if manifest["cost_model_sha256"] != sha256_json(manifest["cost_model"]):
        raise RFBArtifactVerificationError("cost-model definition hash mismatch")
    _validate_terminal_state(manifest["terminal_state"])
    for field in ("comparison_eligible", "human_intervened"):
        if not isinstance(manifest[field], bool):
            raise RFBArtifactVerificationError(f"{field} must be a boolean")
    if manifest["mode"] not in {STRICT_BENCHMARK_MODE, WORKFLOW_CASE_STUDY_MODE}:
        raise RFBArtifactVerificationError("unsupported RFB campaign mode")
    terminal = manifest["terminal_state"]
    for field in ("mode", "comparison_eligible", "human_intervened", "event_head_sha256"):
        if not _canonical_equal(manifest[field], terminal[field]):
            raise RFBArtifactVerificationError(f"manifest {field} disagrees with terminal_state")
    if manifest["mode"] == STRICT_BENCHMARK_MODE and (
        manifest["human_intervened"] or not manifest["comparison_eligible"]
    ):
        raise RFBArtifactVerificationError(
            "strict benchmark artifact is unrankable after intervention or ineligibility"
        )
    if manifest["mode"] == WORKFLOW_CASE_STUDY_MODE and (
        not manifest["human_intervened"] or manifest["comparison_eligible"]
    ):
        raise RFBArtifactVerificationError("workflow case-study artifact must record human intervention")


def _validate_artifact_binding(
    manifest: dict[str, Any], journal: dict[str, Any], replay: ReplayedRFBCampaignV1
) -> None:
    campaign = replay.campaign
    if not _canonical_equal(journal.get("campaign"), campaign):
        raise RFBArtifactVerificationError("journal terminal state does not match semantic replay")
    expected_terminal = _terminal_state(campaign, replay.event_head_sha256)
    checks = {
        "campaign_id": campaign["campaign_id"],
        "public_scenario": campaign["public_scenario"],
        "public_scenario_sha256": campaign["public_scenario"]["public_projection_sha256"],
        "utility": campaign["public_scenario"]["utility"],
        "utility_sha256": campaign["public_scenario"]["utility_sha256"],
        "cost_model": campaign["public_scenario"]["cost_model"],
        "cost_model_sha256": campaign["public_scenario"]["cost_model_sha256"],
        "terminal_state": expected_terminal,
        "mode": campaign["mode"],
        "comparison_eligible": campaign["comparison_eligible"],
        "human_intervened": campaign["human_intervened"],
        "event_head_sha256": replay.event_head_sha256,
    }
    for field, expected in checks.items():
        if not _canonical_equal(manifest[field], expected):
            raise RFBArtifactVerificationError(f"manifest {field} does not match replayed journal")
    policy = manifest["policy"]
    if not _canonical_equal(policy["id"], campaign["policy_id"]) or not _canonical_equal(
        policy["version"], campaign["policy_version"]
    ):
        raise RFBArtifactVerificationError("manifest policy does not match replayed campaign")
    if not _canonical_equal(journal.get("event_head_sha256"), replay.event_head_sha256):
        raise RFBArtifactVerificationError("journal event head does not match semantic replay")


def _terminal_state(campaign: Mapping[str, Any], event_head_sha256: str) -> dict[str, Any]:
    return {
        "revision": campaign["revision"],
        "phase": campaign["phase"],
        "mode": campaign["mode"],
        "comparison_eligible": campaign["comparison_eligible"],
        "human_intervened": campaign["human_intervened"],
        "cumulative_costs": campaign["cumulative_costs"],
        "reserved_costs": campaign["reserved_costs"],
        "event_head_sha256": event_head_sha256,
    }


def _validate_terminal_state(value: Any) -> None:
    if not isinstance(value, dict):
        raise RFBArtifactVerificationError("terminal_state must be a JSON object")
    _require_exact_keys(value, _TERMINAL_STATE_FIELDS, "terminal_state")
    if isinstance(value["revision"], bool) or not isinstance(value["revision"], int) or value["revision"] < 0:
        raise RFBArtifactVerificationError("terminal_state.revision must be a non-negative integer")
    _require_nonempty_string(value["phase"], "terminal_state.phase")
    _require_hex(value["event_head_sha256"], "terminal_state.event_head_sha256")
    for field in ("comparison_eligible", "human_intervened"):
        if not isinstance(value[field], bool):
            raise RFBArtifactVerificationError(f"terminal_state.{field} must be a boolean")
    _validate_ledger_costs(value["cumulative_costs"], "terminal_state.cumulative_costs")
    _validate_ledger_costs(value["reserved_costs"], "terminal_state.reserved_costs")


def _validate_policy(value: Any) -> None:
    if not isinstance(value, dict):
        raise RFBArtifactVerificationError("policy metadata must be a JSON object")
    _require_exact_keys(value, {"id", "version", "metadata"}, "policy metadata")
    _require_nonempty_string(value["id"], "policy.id")
    _require_nonempty_string(value["version"], "policy.version")
    _validate_policy_metadata(value["metadata"])


def _validate_policy_metadata(value: Any) -> None:
    if not isinstance(value, dict):
        raise RFBArtifactVerificationError("policy metadata must be a JSON object")
    _assert_json_primitive(value, "policy metadata")
    _assert_no_private_material(value, "policy metadata")
    if not set(value).issubset(_PUBLIC_POLICY_METADATA_FIELDS):
        raise RFBArtifactVerificationError("policy metadata contains an unknown field")
    for key, item in value.items():
        _validate_explicit_public_metadata_field(key, item, f"policy metadata.{key}")


def _validate_execution_identity(value: Any) -> None:
    if not isinstance(value, dict):
        raise RFBArtifactVerificationError("execution_identity must be a JSON object")
    _require_exact_keys(
        value,
        {"adapter", "reducer", "rfbzero_version", "dependency_pins"},
        "execution_identity",
    )
    for field in ("adapter", "reducer"):
        identity = value[field]
        if not isinstance(identity, dict):
            raise RFBArtifactVerificationError(f"execution_identity.{field} must be a JSON object")
        _require_exact_keys(identity, {"id", "version"}, f"execution_identity.{field}")
        _require_nonempty_string(identity["id"], f"execution_identity.{field}.id")
        _require_nonempty_string(identity["version"], f"execution_identity.{field}.version")
    _require_nonempty_string(value["rfbzero_version"], "execution_identity.rfbzero_version")
    dependencies = value["dependency_pins"]
    if not isinstance(dependencies, dict):
        raise RFBArtifactVerificationError("execution_identity.dependency_pins must be a JSON object")
    _require_exact_keys(dependencies, {"python", "numpy", "scipy", "rfbzero"}, "runtime dependencies")
    for field, version in dependencies.items():
        _require_nonempty_string(version, f"execution_identity.dependency_pins.{field}")
    if dependencies["rfbzero"] != value["rfbzero_version"]:
        raise RFBArtifactVerificationError("execution_identity rfbzero version does not match runtime pin")


def _validate_ledger_costs(value: Any, label: str) -> None:
    if not isinstance(value, dict) or set(value) != {"attempts", "measurements"}:
        raise RFBArtifactVerificationError(f"{label} must contain attempts and measurements")
    for field, amount in value.items():
        if isinstance(amount, bool) or not isinstance(amount, int) or amount < 0:
            raise RFBArtifactVerificationError(f"{label}.{field} must be a non-negative integer")


def _replay_or_error(journal: Mapping[str, Any]) -> ReplayedRFBCampaignV1:
    try:
        return replay_rfb_campaign_export_v1(journal)
    except RFBReplayError as exc:
        raise RFBArtifactVerificationError(f"RFB journal replay failed: {exc}") from exc


def _copy_public_json(value: Any, name: str) -> dict[str, Any]:
    _assert_json_primitive(value, name)
    if not isinstance(value, Mapping):
        raise RFBArtifactVerificationError(f"{name} must be a JSON object")
    try:
        copied = json.loads(canonical_json(value), object_pairs_hook=_reject_duplicate_keys)
    except (TypeError, ValueError, json.JSONDecodeError) as exc:
        raise RFBArtifactVerificationError(f"{name} is not canonical JSON data") from exc
    if not isinstance(copied, dict):
        raise RFBArtifactVerificationError(f"{name} must be a JSON object")
    _assert_no_private_material(copied, name)
    return copied


def _assert_json_primitive(value: Any, path: str) -> None:
    if value is None or isinstance(value, (str, bool)):
        return
    if isinstance(value, int) and not isinstance(value, bool):
        return
    if isinstance(value, float):
        if not math.isfinite(value):
            raise RFBArtifactVerificationError(f"{path} contains a non-finite number")
        return
    if isinstance(value, list) or isinstance(value, tuple):
        for index, item in enumerate(value):
            _assert_json_primitive(item, f"{path}[{index}]")
        return
    if isinstance(value, Mapping):
        for key, item in value.items():
            if not isinstance(key, str):
                raise RFBArtifactVerificationError(f"{path} contains a non-string object key")
            _assert_json_primitive(item, f"{path}.{key}")
        return
    raise RFBArtifactVerificationError(f"{path} must contain only primitive JSON values")


def _assert_no_private_material(value: Any, path: str) -> None:
    """Reject known private/control-plane fields while allowing named commitments.

    This is intentionally field-specific: public metadata such as
    ``hidden_layer_count`` is not a hidden truth.  The sole private-named
    exception is a keyed private-config commitment with a fixed digest shape.
    """

    if isinstance(value, Mapping):
        for key, item in value.items():
            if not isinstance(key, str):
                raise RFBArtifactVerificationError("public RFB artifact contains a non-string object key")
            if _validate_explicit_public_metadata_field(key, item, f"{path}.{key}"):
                continue
            normalized = _normalize_public_key(key)
            if normalized in _PUBLIC_POLICY_METADATA_FIELDS or _forbidden_public_key(normalized):
                raise RFBArtifactVerificationError(f"public RFB artifact contains forbidden field: {path}.{key}")
            _assert_no_private_material(item, f"{path}.{key}")
    elif isinstance(value, (list, tuple)):
        for index, item in enumerate(value):
            _assert_no_private_material(item, f"{path}[{index}]")


def _forbidden_public_key(normalized: str) -> bool:
    terms = tuple(term for term in normalized.split("_") if term)
    compact = "".join(terms)
    if normalized in _FORBIDDEN_PUBLIC_FIELDS:
        return True
    if "hidden" in terms or compact.startswith("hidden"):
        return True
    if normalized.startswith("model_parameters") or compact == "modelparameters":
        return True
    if _contains_token_bearing_term(terms):
        return True
    if any(term in _FORBIDDEN_PUBLIC_TERMS for term in terms):
        return True
    if any(_contains_public_key_terms(terms, sequence) for sequence in _FORBIDDEN_PUBLIC_TERM_SEQUENCES):
        return True
    return compact.endswith(_FORBIDDEN_PUBLIC_COMPACT_SUFFIXES)


def _validate_explicit_public_metadata_field(key: str, value: Any, label: str) -> bool:
    """Validate the narrow public exceptions by their exact source key."""

    if key == _SAFE_COMMITMENT_FIELD:
        _require_hex(value, label)
    elif key == _PUBLIC_SELECTION_ORDER_FIELD:
        _require_one_of(value, _PUBLIC_SELECTION_ORDERS, label)
    elif key == _PUBLIC_HIDDEN_METADATA_FIELD:
        _require_nonnegative_integer(value, label)
    elif key == _PUBLIC_TOKEN_COUNT_FIELD:
        _require_nonnegative_integer(value, label)
    elif key == _PUBLIC_TOKENIZER_FIELD:
        _require_one_of(value, _PUBLIC_TOKENIZERS, label)
    else:
        return False
    return True


def _contains_token_bearing_term(terms: tuple[str, ...]) -> bool:
    """Recognize credential-token terms after camel-case and delimiter splitting."""

    return any("token" in term and not term.startswith("tokenizer") for term in terms)


def _normalize_public_key(key: Any) -> str:
    if not isinstance(key, str):
        raise RFBArtifactVerificationError("public RFB artifact contains a non-string object key")
    separated = _CAMEL_CASE_BOUNDARY.sub("_", key)
    return "_".join(term.casefold() for term in _KEY_DELIMITER.split(separated) if term)


def _contains_public_key_terms(terms: tuple[str, ...], sequence: tuple[str, ...]) -> bool:
    width = len(sequence)
    return any(terms[index : index + width] == sequence for index in range(len(terms) - width + 1))


def _verify_inventory(root: Path) -> None:
    try:
        entries = list(root.iterdir())
    except OSError as exc:
        raise RFBArtifactVerificationError(f"cannot inspect RFB artifact directory: {root}") from exc
    names = {entry.name for entry in entries}
    if names != _ARTIFACT_FILENAMES or any(not entry.is_file() or entry.is_symlink() for entry in entries):
        raise RFBArtifactVerificationError("RFB artifact has a missing or unexpected file")


def _read_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(
            path.read_text(encoding="utf-8"),
            object_pairs_hook=_reject_duplicate_keys,
            parse_constant=_reject_json_constant,
        )
    except (OSError, UnicodeError, json.JSONDecodeError, ValueError) as exc:
        raise RFBArtifactVerificationError(f"cannot read RFB JSON artifact {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise RFBArtifactVerificationError(f"RFB JSON artifact must be an object: {path}")
    _assert_json_primitive(value, str(path))
    return value


def _reject_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate JSON key: {key!r}")
        result[key] = value
    return result


def _reject_json_constant(value: str) -> None:
    raise ValueError(f"non-finite JSON constant: {value}")


def _json_bytes(value: Mapping[str, Any]) -> bytes:
    return (canonical_json(value) + "\n").encode("utf-8")


def _write_artifact_files(root: Path, journal_bytes: bytes, manifest_bytes: bytes) -> None:
    """Write a complete candidate artifact before it is published atomically."""

    (root / "journal.json").write_bytes(journal_bytes)
    (root / "manifest.json").write_bytes(manifest_bytes)


def _publish_verified_artifact(temporary_root: Path, root: Path) -> None:
    """Atomically publish a verified directory without replacing another export."""

    try:
        _rename_no_replace(temporary_root, root)
    except FileExistsError as exc:
        raise RFBArtifactVerificationError(f"RFB artifact output already exists: {root}") from exc
    except OSError as exc:
        raise RFBArtifactVerificationError(f"cannot publish RFB artifact: {root}: {exc}") from exc


def _remove_temporary_artifact(temporary_root: Path) -> None:
    try:
        shutil.rmtree(temporary_root)
    except OSError as exc:
        raise RFBArtifactVerificationError(
            f"cannot remove incomplete RFB artifact: {temporary_root}: {exc}"
        ) from exc


def _rename_no_replace(source: Path, destination: Path) -> None:
    """Use Linux ``renameat2(RENAME_NOREPLACE)`` so publication cannot race."""

    try:
        renameat2 = ctypes.CDLL(None, use_errno=True).renameat2
    except AttributeError as exc:
        raise OSError(errno.ENOSYS, "renameat2(RENAME_NOREPLACE) is unavailable") from exc
    renameat2.argtypes = [ctypes.c_int, ctypes.c_char_p, ctypes.c_int, ctypes.c_char_p, ctypes.c_uint]
    renameat2.restype = ctypes.c_int
    if renameat2(
        _AT_FDCWD,
        os.fsencode(source),
        _AT_FDCWD,
        os.fsencode(destination),
        _RENAME_NOREPLACE,
    ) == 0:
        return
    error = ctypes.get_errno()
    if error == errno.EEXIST:
        raise FileExistsError(error, os.strerror(error), destination)
    raise OSError(error, os.strerror(error), destination)


def _file_sha256(path: Path) -> str:
    try:
        return hashlib.sha256(path.read_bytes()).hexdigest()
    except OSError as exc:
        raise RFBArtifactVerificationError(f"cannot read RFB artifact file {path}: {exc}") from exc


def _require_exact_keys(value: Any, expected: set[str] | frozenset[str], label: str) -> None:
    if not isinstance(value, dict) or set(value) != set(expected):
        raise RFBArtifactVerificationError(f"{label} fields do not match rfb_artifact_v1")


def _require_equal(actual: Any, expected: Any, label: str) -> None:
    if not _canonical_equal(actual, expected):
        raise RFBArtifactVerificationError(f"{label} mismatch")


def _canonical_equal(actual: Any, expected: Any) -> bool:
    """Compare public JSON by canonical bytes, preserving scalar JSON types."""

    try:
        return canonical_json(actual) == canonical_json(expected)
    except (TypeError, ValueError):
        return False


def _require_nonempty_string(value: Any, label: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise RFBArtifactVerificationError(f"{label} must be a non-empty string")


def _require_nonnegative_integer(value: Any, label: str) -> None:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise RFBArtifactVerificationError(f"{label} must be a non-negative integer")


def _require_integer(value: Any, label: str) -> None:
    if isinstance(value, bool) or not isinstance(value, int):
        raise RFBArtifactVerificationError(f"{label} must be an integer")


def _require_string(value: Any, label: str) -> None:
    if not isinstance(value, str):
        raise RFBArtifactVerificationError(f"{label} must be a string")


def _require_one_of(value: Any, allowed_values: frozenset[str], label: str) -> None:
    if not isinstance(value, str) or value not in allowed_values:
        raise RFBArtifactVerificationError(f"{label} must be an allowed value")


def _require_hex(value: Any, label: str) -> None:
    if not isinstance(value, str) or not _HEX_64.fullmatch(value):
        raise RFBArtifactVerificationError(f"{label} must be a lowercase SHA-256 hex digest")


export_rfb_artifact = export_rfb_artifact_v1
export_rfb_store_journal_artifact_v1 = export_rfb_artifact_v1
verify_rfb_artifact = verify_rfb_artifact_v1
RFBArtifactError = RFBArtifactVerificationError


__all__ = [
    "RFB_ARTIFACT_VERSION",
    "RFB_PROVENANCE",
    "RFB_WORKFLOW_VERSION",
    "RFBArtifactError",
    "RFBArtifactVerificationError",
    "STRICT_BENCHMARK_MODE",
    "WORKFLOW_CASE_STUDY_MODE",
    "VerifiedRFBArtifactV1",
    "export_rfb_artifact",
    "export_rfb_artifact_v1",
    "export_rfb_store_journal_artifact_v1",
    "verify_rfb_artifact",
    "verify_rfb_artifact_v1",
]
