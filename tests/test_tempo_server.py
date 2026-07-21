from __future__ import annotations

import hashlib
import importlib.util
import json
import threading
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen

import pytest

from discovery_flight_simulator.cli import compare


ROOT = Path(__file__).resolve().parents[1]
SERVE_PATH = ROOT / "demo" / "serve.py"
SCENARIO = ROOT / "scenarios" / "cv_mechanism_v0.json"


def load_server_module():
    spec = importlib.util.spec_from_file_location("tempo_demo_server", SERVE_PATH)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def running_server(tmp_path: Path):
    bundle = tmp_path / "bundle"
    compare(SCENARIO, bundle)
    module = load_server_module()
    server = module.create_server(bundle, port=0)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_address[1]}"
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


def get_json(url: str) -> tuple[int, dict[str, object]]:
    with urlopen(url, timeout=2) as response:  # noqa: S310 - local test server only
        return response.status, json.loads(response.read())


def post_json(url: str, payload: object) -> tuple[int, dict[str, object]]:
    request = Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urlopen(request, timeout=2) as response:  # noqa: S310 - local test server only
        return response.status, json.loads(response.read())


def valid_peak_request() -> dict[str, object]:
    potentials = [0.70 + index * 0.01 for index in range(20)]
    currents = [-0.0001 + index * 0.00001 for index in range(20)]
    return {
        "schema_version": "tempo-inference-v1",
        "request_id": "peak-vector-b1",
        "source": {
            "provenance": "synthetic_teaching",
            "source_id": "qa-vector-b1",
            "checksum": "sha256:synthetic-qa-vector-b1",
        },
        "sample": {
            "sample_id": "teaching-4ht",
            "preferred_name": "4-hydroxy-TEMPO teaching sample",
            "molecular_form": "neutral radical",
            "concentration_mol_cm3": 1e-6,
        },
        "condition": {
            "condition_id": "teaching-condition-1",
            "solvent": "water",
            "supporting_electrolyte": {"name": "KCl", "concentration_mol_l": 0.5},
            "ph": {"status": "measured", "value": 7.0},
            "temperature_k": 298.15,
            "working_electrode": {"material": "glassy carbon", "area_cm2": 0.19634954084936207},
            "counter_electrode": "Pt foil",
            "reference_electrode": "SCE",
            "potential_scale": "SHE",
            "electron_count": 1,
            "atmosphere": "N2",
            "preprocessing_description": "synthetic QA fixture; no preprocessing",
            "units": {
                "potential": "V",
                "current": "A",
                "scan_rate": "V/s",
                "area": "cm2",
                "concentration": "mol/cm3",
                "temperature": "K",
            },
        },
        "traces": [
            {
                "trace_id": "trace-1",
                "scan_rate_v_s": 0.025,
                "replicate_id": "r1",
                "cycle_number": 2,
                "potential_v": potentials,
                "current_a": currents,
                "potential_scale": "SHE",
                "transformation": "raw",
            }
        ],
        "peak_assignments": [
            {
                "trace_id": "trace-1",
                "epa_v": 0.842,
                "epc_v": 0.782,
                "ipa_a": 0.000150,
                "ipc_a": -0.000147,
                "assignment_source": "manual",
                "reviewed": True,
            }
        ],
        "requested": ["peak_descriptors"],
    }


def test_reference_route_serves_exact_five_sample_scalar_atlas(running_server: str) -> None:
    status, payload = get_json(f"{running_server}/tempo/reference-v1.json")
    assert status == 200
    assert payload["schema_version"] == "tempo-reference-v1"
    assert payload["doi"] == "10.1039/D0RA03424J"
    assert payload["license_id"] == "CC-BY-NC-3.0"
    assert str(payload["record_checksum"]).startswith("sha256:")
    samples = payload["samples"]
    assert [sample["sample_id"] for sample in samples] == ["4ht", "4ot", "4at", "4cyt", "4cat"]
    expected = {
        "4ht": (0.812, 3.14e-6, 4.45e-3, 2.11, 1.25, 33.5),
        "4ot": (0.910, 4.61e-6, 1.05e-2, 1.22, 0.79, 21.2),
        "4at": (0.895, 3.77e-6, 4.01e-3, 5.79, 4.80, 128.6),
        "4cyt": (0.881, 6.23e-6, 4.29e-3, 2.6e-2, None, None),
        "4cat": (0.776, 2.64e-6, 2.25e-3, 2.1e-2, None, None),
    }
    keys = (
        "formal_potential_v_vs_she",
        "diffusion_coefficient_cm2_s",
        "electron_transfer_rate_constant_cm_s",
        "solubility_water_mol_l",
        "solubility_kcl_mol_l",
        "theoretical_capacity_ah_l",
    )
    for sample in samples:
        assert tuple(sample["quantities"][key]["value"] for key in keys) == expected[
            sample["sample_id"]
        ]
    for index in (3, 4):
        missing = samples[index]["quantities"]["solubility_kcl_mol_l"]
        assert missing == {
            "value": None,
            "unit": "mol/L",
            "status": "not_reported",
            "condition_id": "solubility-0.5m-kcl",
            "method_id": "uv-vis-after-48h-equilibration",
        }
    assert "points" not in json.dumps(payload)


def test_reference_loader_rejects_tamper(tmp_path: Path) -> None:
    module = load_server_module()
    payload = json.loads(module.TEMPO_REFERENCE_PATH.read_text(encoding="utf-8"))
    payload["samples"][0]["quantities"]["formal_potential_v_vs_she"]["value"] = 99
    tampered = tmp_path / "reference.json"
    tampered.write_text(json.dumps(payload), encoding="utf-8")
    module.TEMPO_REFERENCE_PATH = tampered
    with pytest.raises(ValueError, match="checksum"):
        module.load_tempo_reference()


def test_explicit_tempo_static_routes_are_registered() -> None:
    module = load_server_module()
    assert module.STATIC_ROUTES["/tempo/"] == module.DEMO_DIR / "tempo.html"
    assert module.STATIC_ROUTES["/tempo.js"] == module.DEMO_DIR / "tempo.js"
    assert module.STATIC_ROUTES["/tempo.css"] == module.DEMO_DIR / "tempo.css"


def test_peak_descriptor_api_uses_authoritative_envelope(running_server: str) -> None:
    status, payload = post_json(f"{running_server}/api/tempo/analyze", valid_peak_request())
    assert status == 200
    assert payload["schema_version"] == "tempo-inference-v1"
    assert payload["request_id"] == "peak-vector-b1"
    assert payload["status"] == "estimate_available"
    assert payload["provenance"] == "derived"
    assert len(payload["input_hash"]) == 64
    result = payload["results"]["peak_descriptors"]
    assert result["per_trace"][0]["e_half_v"] == pytest.approx(0.812)
    assert result["per_trace"][0]["delta_ep_v"] == pytest.approx(0.060)
    assert result["per_trace"][0]["peak_current_ratio"] == pytest.approx(1.0204081633)
    assert set(result["aggregate"]) == {"e_half_v", "delta_ep_v", "peak_current_ratio"}


def test_api_hashes_exact_utf8_post_body_and_checks_client_digest(running_server: str) -> None:
    payload = valid_peak_request()
    raw = json.dumps(payload, separators=(",", ":"), ensure_ascii=False).replace(
        '"scan_rate_v_s":0.025',
        '"scan_rate_v_s":0.025000000000000001',
    ).encode("utf-8")
    expected = hashlib.sha256(raw).hexdigest()
    request = Request(
        f"{running_server}/api/tempo/analyze",
        data=raw,
        headers={"Content-Type": "application/json", "X-Tempo-Input-Hash": expected},
        method="POST",
    )
    with urlopen(request, timeout=2) as response:  # noqa: S310 - local test server only
        body = json.loads(response.read())
    assert body["input_hash"] == expected
    assert body["audit"]["input_hash"] == expected

    bad_request = Request(
        f"{running_server}/api/tempo/analyze",
        data=raw,
        headers={"Content-Type": "application/json", "X-Tempo-Input-Hash": "0" * 64},
        method="POST",
    )
    with pytest.raises(HTTPError) as error:
        urlopen(bad_request, timeout=2)  # noqa: S310 - local test server only
    assert error.value.code == 400
    assert "exact UTF-8 request body" in json.loads(error.value.read())["error"]


def test_analyze_api_fails_closed_for_unreviewed_peak(running_server: str) -> None:
    payload = valid_peak_request()
    payload["peak_assignments"][0]["reviewed"] = False
    request = Request(
        f"{running_server}/api/tempo/analyze",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with pytest.raises(HTTPError) as error:
        urlopen(request, timeout=2)  # noqa: S310 - local test server only
    assert error.value.code == 422
    refusal = json.loads(error.value.read())
    assert refusal["status"] == "no_estimate"
    assert refusal["refusal"]["code"] == "PEAKS_INVALID"
    assert refusal["results"] == {}


def test_ir_api_requires_structured_matching_independent_provenance(
    running_server: str,
) -> None:
    payload = valid_peak_request()
    payload["requested"] = ["ir_correction"]
    shared = {
        "sample_id": "teaching-4ht",
        "cell_id": "cell-tempo-01",
        "geometry_id": "geometry-gce-5mm",
        "electrolyte_id": "electrolyte-kcl-05m",
        "condition_id": "teaching-condition-1",
    }
    payload["ir_correction"] = {
        "ru_ohm": 20.0,
        "fraction": 0.85,
        "resistance_source": {
            "operation_id": "operation-eis-17",
            "provenance": "independent_resistance_measurement",
        },
        "measurement_method": "EIS high-frequency resistance",
        "measurement_context": {
            "reviewed": True,
            "resistance": {"operation_id": "operation-eis-17", **shared},
            "cv": shared,
        },
    }
    status, response = post_json(f"{running_server}/api/tempo/analyze", payload)
    assert status == 200
    assert response["results"]["ir_correction"]["status"] == "estimate_available"

    payload["request_id"] = "ir-generic-provenance"
    payload["ir_correction"] = {
        "ru_ohm": 20.0,
        "fraction": 0.85,
        "resistance_source": "x",
        "measurement_method": "banana",
        "measurement_context": "somewhere else",
    }
    request = Request(
        f"{running_server}/api/tempo/analyze",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with pytest.raises(HTTPError) as error:
        urlopen(request, timeout=2)  # noqa: S310 - local test server only
    assert error.value.code == 422
    assert json.loads(error.value.read())["refusal"]["code"] == "RESISTANCE_INELIGIBLE"


@pytest.mark.parametrize("operation_id", ["test-01", "banana-01", "unknown-01"])
def test_ir_api_rejects_placeholder_operation_tokens_with_suffixes(
    running_server: str,
    operation_id: str,
) -> None:
    payload = valid_peak_request()
    payload["request_id"] = f"ir-placeholder-{operation_id}"
    payload["requested"] = ["ir_correction"]
    shared = {
        "sample_id": "teaching-4ht",
        "cell_id": "cell-tempo-01",
        "geometry_id": "geometry-gce-5mm",
        "electrolyte_id": "electrolyte-kcl-05m",
        "condition_id": "teaching-condition-1",
    }
    payload["ir_correction"] = {
        "ru_ohm": 20.0,
        "fraction": 0.85,
        "resistance_source": {
            "operation_id": operation_id,
            "provenance": "independent_resistance_measurement",
        },
        "measurement_method": "EIS high-frequency resistance",
        "measurement_context": {
            "reviewed": True,
            "resistance": {"operation_id": operation_id, **shared},
            "cv": shared,
        },
    }
    request = Request(
        f"{running_server}/api/tempo/analyze",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with pytest.raises(HTTPError) as error:
        urlopen(request, timeout=2)  # noqa: S310 - local test server only
    assert error.value.code == 422
    assert json.loads(error.value.read())["refusal"]["code"] == "RESISTANCE_INELIGIBLE"


def test_conductivity_api_is_independent_and_rejects_cv_ru(running_server: str) -> None:
    valid = {
        "schema_version": "tempo-inference-v1",
        "request_id": "conductivity-e1",
        "resistance_ohm": 100.0,
        "cell_constant_m_inv": 100.0,
        "calibration_source": {
            "calibration_id": "calibration-kcl-2026-01",
            "method": "certified_cell_constant",
            "cell_id": "conductivity-cell-01",
            "geometry_id": "conductivity-geometry-01",
            "reviewed": True,
        },
        "measurement_context": {
            "calibration_id": "calibration-kcl-2026-01",
            "reviewed": True,
            "resistance": {
                "operation_id": "resistance-operation-01",
                "independent": True,
                "resistance_kind": "conductivity_cell",
                "sample_id": "tempo-sample-01",
                "cell_id": "conductivity-cell-01",
                "geometry_id": "conductivity-geometry-01",
                "condition_id": "conductivity-condition-298k",
            },
            "measurement": {
                "sample_id": "tempo-sample-01",
                "cell_id": "conductivity-cell-01",
                "geometry_id": "conductivity-geometry-01",
                "condition_id": "conductivity-condition-298k",
            },
        },
        "temperature_k": 298.15,
    }
    status, payload = post_json(f"{running_server}/api/tempo/conductivity", valid)
    assert status == 200
    assert payload["results"]["conductivity"] == {
        "status": "estimate_available",
        "conductivity_s_m": 1.0,
        "unit": "S/m",
        "resistance_ohm": 100.0,
        "cell_constant_m_inv": 100.0,
    }

    invalid = {**valid, "request_id": "conductivity-cv-ru"}
    invalid["measurement_context"] = {
        "independent": False,
        "same_conductivity_cell": False,
        "resistance_kind": "cv_ru",
    }
    request = Request(
        f"{running_server}/api/tempo/conductivity",
        data=json.dumps(invalid).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with pytest.raises(HTTPError) as error:
        urlopen(request, timeout=2)  # noqa: S310 - local test server only
    assert error.value.code == 422

    generic = {**valid, "request_id": "conductivity-generic", "calibration_source": "x"}
    request = Request(
        f"{running_server}/api/tempo/conductivity",
        data=json.dumps(generic).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with pytest.raises(HTTPError) as error:
        urlopen(request, timeout=2)  # noqa: S310 - local test server only
    assert error.value.code == 422
    assert json.loads(error.value.read())["refusal"]["code"] == "CELL_CONSTANT_INELIGIBLE"


@pytest.mark.parametrize("operation_id", ["test-01", "banana-01", "unknown-01"])
def test_conductivity_api_rejects_placeholder_operation_tokens_with_suffixes(
    running_server: str,
    operation_id: str,
) -> None:
    payload = {
        "schema_version": "tempo-inference-v1",
        "request_id": f"conductivity-placeholder-{operation_id}",
        "resistance_ohm": 100.0,
        "cell_constant_m_inv": 100.0,
        "calibration_source": {
            "calibration_id": "calibration-kcl-2026-01",
            "method": "certified_cell_constant",
            "cell_id": "conductivity-cell-01",
            "geometry_id": "conductivity-geometry-01",
            "reviewed": True,
        },
        "measurement_context": {
            "calibration_id": "calibration-kcl-2026-01",
            "reviewed": True,
            "resistance": {
                "operation_id": operation_id,
                "independent": True,
                "resistance_kind": "conductivity_cell",
                "sample_id": "tempo-sample-01",
                "cell_id": "conductivity-cell-01",
                "geometry_id": "conductivity-geometry-01",
                "condition_id": "conductivity-condition-298k",
            },
            "measurement": {
                "sample_id": "tempo-sample-01",
                "cell_id": "conductivity-cell-01",
                "geometry_id": "conductivity-geometry-01",
                "condition_id": "conductivity-condition-298k",
            },
        },
        "temperature_k": 298.15,
    }
    request = Request(
        f"{running_server}/api/tempo/conductivity",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with pytest.raises(HTTPError) as error:
        urlopen(request, timeout=2)  # noqa: S310 - local test server only
    assert error.value.code == 422
    assert json.loads(error.value.read())["refusal"]["code"] == "RESISTANCE_INELIGIBLE"


def test_tempo_api_rejects_malformed_and_unknown_requests(running_server: str) -> None:
    malformed = Request(
        f"{running_server}/api/tempo/analyze",
        data=b"not-json",
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with pytest.raises(HTTPError) as error:
        urlopen(malformed, timeout=2)  # noqa: S310 - local test server only
    assert error.value.code == 400

    with pytest.raises(HTTPError) as error:
        post_json(f"{running_server}/api/tempo/unknown", {})
    assert error.value.code == 404
