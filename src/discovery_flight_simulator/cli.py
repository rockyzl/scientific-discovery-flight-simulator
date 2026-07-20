"""Command-line entry point for deterministic paired planner comparisons."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import shutil
import sys
import tempfile
from pathlib import Path
from typing import Any, Callable

import numpy as np

from . import __version__
from .artifacts import public_seed_record, verify_artifact_bundle
from .contracts import SeedBundle, to_primitive
from .ledger import SCHEMA_VERSION, sha256_json
from .runner import CampaignRunner


def _write_json(path: Path, value: Any) -> None:
    path.write_text(
        json.dumps(
            to_primitive(value),
            sort_keys=True,
            indent=2,
            ensure_ascii=False,
            allow_nan=False,
        )
        + "\n",
        encoding="utf-8",
    )


def _file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _seed_bundle(scenario: Any) -> SeedBundle:
    direct = getattr(scenario, "seed_bundle", None)
    if isinstance(direct, SeedBundle):
        return direct
    identity = getattr(scenario, "scenario_identity", {})
    if isinstance(identity, dict):
        values = identity.get("seeds") or identity.get("seed_bundle")
        if isinstance(values, dict):
            return SeedBundle(**{key: int(value) for key, value in values.items()})
    raise ValueError("scenario must provide seed_bundle or scenario_identity['seeds']")


def _planner(factory: Any) -> Any:
    if isinstance(factory, type):
        return factory()
    return factory() if callable(factory) and not hasattr(factory, "propose") else factory


def compare(
    scenario_path: str | Path,
    output_dir: str | Path,
    *,
    private_seed_key: str | None = None,
    load_scenario_fn: Callable[..., Any] | None = None,
    planner_registry_fn: Callable[[], dict[str, Any]] | None = None,
    evaluation_fn: Callable[[Any, Any], dict[str, Any]] | None = None,
) -> Path:
    output = Path(output_dir)
    if output.exists():
        raise FileExistsError(f"output directory already exists: {output}")

    if load_scenario_fn is None:
        from .worlds.registry import load_scenario as load_scenario_fn
    if planner_registry_fn is None:
        from .planners.registry import default_planners as planner_registry_fn
    if evaluation_fn is None:
        from .evaluation import evaluate_ledger as evaluation_fn

    scenario = load_scenario_fn(scenario_path, private_seed_key=private_seed_key)
    seeds = _seed_bundle(scenario)
    public_seeds = public_seed_record(seeds.planner_seed, scenario.scenario_identity)
    factories = planner_registry_fn()
    if not factories:
        raise ValueError("planner registry is empty")

    output.parent.mkdir(parents=True, exist_ok=True)
    temp = Path(tempfile.mkdtemp(prefix=f".{output.name}.", dir=output.parent))
    try:
        ledgers_dir = temp / "ledgers"
        ledgers_dir.mkdir()
        results: dict[str, Any] = {}
        planner_metadata: dict[str, Any] = {}
        artifact_hashes: dict[str, str] = {}
        post_run_reveal: Any = None

        for registry_name, factory in sorted(factories.items()):
            planner = _planner(factory)
            planner_name = str(getattr(planner, "name", registry_name))
            planner_version = str(getattr(planner, "version", "0"))
            ledger = CampaignRunner().run(
                planner,
                scenario,
                planner_name=planner_name,
                planner_version=planner_version,
                seed_bundle=seeds,
            )
            ledger_path = ledgers_dir / f"{registry_name}.json"
            ledger.write_json(ledger_path)
            evaluation = dict(evaluation_fn(ledger, scenario.private_truth))
            planner_reveal = evaluation.pop("post_run_reveal", None)
            if planner_reveal is not None:
                if post_run_reveal is None:
                    post_run_reveal = planner_reveal
                elif to_primitive(post_run_reveal) != to_primitive(planner_reveal):
                    raise ValueError("evaluators returned inconsistent post_run_reveal values")
            results[registry_name] = {
                "planner_name": planner_name,
                "planner_version": planner_version,
                "metrics": evaluation,
                "ledger": f"ledgers/{registry_name}.json",
                "ledger_sha256": ledger.to_dict()["ledger_sha256"],
            }
            planner_metadata[registry_name] = {
                "name": planner_name,
                "version": planner_version,
            }
            artifact_hashes[f"ledgers/{registry_name}.json"] = _file_sha256(ledger_path)

        spec = scenario.public_spec
        summary_payload = {
            "schema_version": SCHEMA_VERSION,
            "provenance": "simulated",
            "status": "complete",
            "world_id": spec.world_id,
            "world_version": spec.world_version,
            "seeds": public_seeds,
            "scenario_identity": to_primitive(scenario.scenario_identity),
            "planners": planner_metadata,
            "results": results,
        }
        if post_run_reveal is not None:
            summary_payload["post_run_reveal"] = to_primitive(post_run_reveal)
        summary = {**summary_payload, "summary_sha256": sha256_json(summary_payload)}
        summary_path = temp / "summary.json"
        _write_json(summary_path, summary)
        artifact_hashes["summary.json"] = _file_sha256(summary_path)

        manifest_payload = {
            "schema_version": SCHEMA_VERSION,
            "provenance": "simulated",
            "status": "complete",
            "package": {
                "name": "scientific-discovery-flight-simulator",
                "version": __version__,
            },
            "world_id": spec.world_id,
            "world_version": spec.world_version,
            "seeds": public_seeds,
            "scenario_identity": to_primitive(scenario.scenario_identity),
            "planners": planner_metadata,
            "runtime": {
                "python": platform.python_version(),
                "numpy": np.__version__,
                "platform": platform.platform(),
            },
            "artifacts": artifact_hashes,
        }
        manifest = {**manifest_payload, "manifest_payload_sha256": sha256_json(manifest_payload)}
        _write_json(temp / "manifest.json", manifest)
        verify_artifact_bundle(temp)
        os.replace(temp, output)
    except Exception:
        shutil.rmtree(temp, ignore_errors=True)
        raise
    return output


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="discovery-flight-simulator")
    subparsers = parser.add_subparsers(dest="command", required=True)
    compare_parser = subparsers.add_parser("compare", help="compare planners on one frozen scenario")
    compare_parser.add_argument("--scenario", required=True, help="path to a frozen scenario JSON file")
    compare_parser.add_argument("--output", required=True, help="new output directory (must not exist)")
    compare_parser.add_argument(
        "--private-seed-key",
        help="private replay key for exact reproduction; generated securely when omitted",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if args.command == "compare":
            destination = compare(
                args.scenario,
                args.output,
                private_seed_key=args.private_seed_key,
            )
            print(f"simulated comparison written to {destination}")
            return 0
    except Exception as exc:  # CLI boundary: concise failure, no partial output
        print(f"error: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 2
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
