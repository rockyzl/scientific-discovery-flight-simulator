from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import sys
import threading
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import urlopen

import pytest

from discovery_flight_simulator.cli import compare


ROOT = Path(__file__).resolve().parents[1]
SERVE_PATH = ROOT / "demo" / "serve.py"
SCENARIO = ROOT / "scenarios" / "cv_mechanism_v0.json"


def load_server_module():
    spec = importlib.util.spec_from_file_location("flight_sim_demo_server", SERVE_PATH)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def valid_bundle(tmp_path: Path) -> Path:
    output = tmp_path / "bundle"
    compare(SCENARIO, output)
    return output


@pytest.fixture
def running_server(valid_bundle: Path):
    module = load_server_module()
    server = module.create_server(valid_bundle, port=0)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_address[1]}"
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


def get(url: str):
    with urlopen(url, timeout=2) as response:  # noqa: S310 - local test server only
        return response.status, response.headers, response.read()


def rewrite_json(path: Path, mutation) -> None:
    payload = json.loads(path.read_text(encoding="utf-8"))
    mutation(payload)
    path.write_text(json.dumps(payload, sort_keys=True, indent=2) + "\n", encoding="utf-8")


def test_static_demo_and_json_are_served(running_server: str) -> None:
    status, headers, body = get(f"{running_server}/")
    assert status == 200
    assert b"SIMULATED RUN" in body
    assert headers["X-Content-Type-Options"] == "nosniff"
    assert "default-src 'self'" in headers["Content-Security-Policy"]

    status, headers, body = get(f"{running_server}/artifacts/summary.json")
    assert status == 200
    assert headers.get_content_type() == "application/json"
    assert json.loads(body)["post_run_reveal"]["provenance"] == "simulated"


def test_direct_demo_help_works_without_pythonpath() -> None:
    environment = os.environ.copy()
    environment.pop("PYTHONPATH", None)
    completed = subprocess.run(
        [sys.executable, "demo/serve.py", "--help"],
        cwd=ROOT,
        env=environment,
        check=False,
        capture_output=True,
        text=True,
    )
    assert completed.returncode == 0, completed.stderr
    assert "--artifacts" in completed.stdout


def test_traversal_is_rejected(running_server: str) -> None:
    with pytest.raises(HTTPError) as error:
        get(f"{running_server}/artifacts/%2e%2e/index.html")
    assert error.value.code == 403


def test_symlink_escape_is_rejected(valid_bundle: Path, tmp_path: Path) -> None:
    outside = tmp_path / "private.json"
    outside.write_text('{"secret": true}', encoding="utf-8")
    module = load_server_module()
    server = module.create_server(valid_bundle, port=0)
    # Add the malicious path only after the frozen bundle passed startup verification. The request
    # handler must still confine every artifact request to the verified root.
    (valid_bundle / "escape.json").symlink_to(outside)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        url = f"http://127.0.0.1:{server.server_address[1]}/artifacts/escape.json"
        with pytest.raises(HTTPError) as error:
            get(url)
        assert error.value.code == 403
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


def test_unknown_static_route_is_not_served(running_server: str) -> None:
    with pytest.raises(HTTPError) as error:
        get(f"{running_server}/README.md")
    assert error.value.code == 404


def test_server_rejects_missing_file(valid_bundle: Path) -> None:
    (valid_bundle / "summary.json").unlink()
    with pytest.raises(ValueError, match="missing"):
        load_server_module().create_server(valid_bundle, port=0)


def test_server_rejects_summary_truth_tamper(valid_bundle: Path) -> None:
    rewrite_json(
        valid_bundle / "summary.json",
        lambda payload: payload["post_run_reveal"].update(value="tampered"),
    )
    with pytest.raises(ValueError):
        load_server_module().create_server(valid_bundle, port=0)


def test_server_rejects_ledger_tamper(valid_bundle: Path) -> None:
    rewrite_json(
        valid_bundle / "ledgers" / "random.json",
        lambda payload: payload["events"][0]["observation"].update(value=999),
    )
    with pytest.raises(ValueError):
        load_server_module().create_server(valid_bundle, port=0)


def test_server_rejects_manifest_tamper(valid_bundle: Path) -> None:
    rewrite_json(
        valid_bundle / "manifest.json",
        lambda payload: payload.update(world_version="tampered"),
    )
    with pytest.raises(ValueError):
        load_server_module().create_server(valid_bundle, port=0)


def test_frontend_truth_source_is_summary_only() -> None:
    script = (ROOT / "demo" / "app.js").read_text(encoding="utf-8")
    extract = script.split("function extractReveal()", 1)[1].split("function renderIdentity()", 1)[0]
    assert "state.summary?.post_run_reveal" in extract
    assert "state.ledgers" not in extract
    assert "state.manifest" not in extract


def test_pre_reveal_identity_does_not_render_private_seeds() -> None:
    script = (ROOT / "demo" / "app.js").read_text(encoding="utf-8")
    identity = script.split("function renderIdentity()", 1)[1].split(
        "function plannerDescription", 1
    )[0]
    assert "seeds.world_seed" not in identity
    assert "seeds.noise_seed" not in identity
    assert "seeds.failure_seed" not in identity
    assert "seeds.commitments?.world_seed" in identity
    assert "seeds.commitments?.noise_seed" in identity
    assert "seeds.commitments?.failure_seed" in identity
    assert "planner_seed" in identity
    assert "scenario_sha256" in identity


def test_numeric_formatter_preserves_scientific_magnitude() -> None:
    values = [1e-10, 1e-20, -1e-10, -1e-20, 0.000001, -0.000001, 1e20, 1e21, -1e21]
    node_script = f"""
      const fs = require('fs');
      const vm = require('vm');
      const context = {{ document: {{ addEventListener() {{}} }} }};
      vm.createContext(context);
      vm.runInContext(fs.readFileSync({json.dumps(str(ROOT / 'demo' / 'app.js'))}, 'utf8'), context);
      const values = {json.dumps(values)};
      console.log(JSON.stringify(values.map(value => vm.runInContext(`compact(${{value}})`, context))));
    """
    completed = subprocess.run(
        ["node", "-e", node_script],
        check=True,
        capture_output=True,
        text=True,
    )
    rendered = json.loads(completed.stdout)
    assert rendered[:4] == ["1e-10", "1e-20", "-1e-10", "-1e-20"]
    assert [float(value) for value in rendered] == values
