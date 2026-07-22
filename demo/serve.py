#!/usr/bin/env python3
"""Serve the static artifact replay demo with a traversal-safe artifact route."""

from __future__ import annotations

import argparse
import hashlib
import json
import mimetypes
import sys
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Protocol
from urllib.parse import unquote, urlsplit

# Direct `python demo/serve.py` execution places demo/, not the repository's src/, on sys.path.
# Resolve the one trusted source directory from this file rather than importing from an arbitrary
# current working directory. Installed and `uv run` execution continue to resolve the same package.
REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
SOURCE_ROOT = REPOSITORY_ROOT / "src"
if str(SOURCE_ROOT) not in sys.path:
    sys.path.insert(0, str(SOURCE_ROOT))

DEMO_DIR = Path(__file__).resolve().parent
STATIC_ROUTES = {
    "/": DEMO_DIR / "index.html",
    "/index.html": DEMO_DIR / "index.html",
    "/styles.css": DEMO_DIR / "styles.css",
    "/app.js": DEMO_DIR / "app.js",
    "/real-cv-data.json": DEMO_DIR / "data" / "all_iron_rfb_cv.json",
    "/tempo/": DEMO_DIR / "tempo.html",
    "/tempo.js": DEMO_DIR / "tempo.js",
    "/tempo.css": DEMO_DIR / "tempo.css",
}
TEMPO_REFERENCE_PATH = DEMO_DIR / "data" / "tempo" / "reference-v1.json"
TEMPO_REFERENCE_ROUTE = "/tempo/reference-v1.json"
MAX_TEMPO_REQUEST_BYTES = 2_000_000
MAX_DIAGNOSIS_REQUEST_BYTES = 2_000_000
DIAGNOSIS_API_PREFIX = "/api/v1/closed-loop"
REQUIRED_ARTIFACTS = (
    "manifest.json",
    "summary.json",
    "ledgers/random.json",
    "ledgers/fixed_grid.json",
    "ledgers/information_gain.json",
)


class DiagnosisServiceProtocol(Protocol):
    """The HTTP adapter's deliberately narrow dependency on the diagnosis core."""

    def get_scenario(self) -> tuple[int, bytes]: ...

    def create_campaign(self, raw_body: bytes) -> tuple[int, bytes]: ...

    def get_campaign(self, campaign_id: str) -> tuple[int, bytes]: ...

    def act(self, campaign_id: str, raw_body: bytes) -> tuple[int, bytes]: ...

    def stop(self, campaign_id: str, raw_body: bytes) -> tuple[int, bytes]: ...

    def get_ledger(self, campaign_id: str) -> tuple[int, bytes]: ...

    def reveal(self, campaign_id: str, raw_body: bytes) -> tuple[int, bytes]: ...


class DemoRequestHandler(BaseHTTPRequestHandler):
    """Serve known static files and files confined beneath one artifact root."""

    artifact_root: Path
    diagnosis_service: DiagnosisServiceProtocol

    def do_GET(self) -> None:  # noqa: N802 - stdlib handler API
        if self._serve_diagnosis_get(send_body=True):
            return
        self._serve(send_body=True)

    def do_HEAD(self) -> None:  # noqa: N802 - stdlib handler API
        self._serve(send_body=False)

    def do_POST(self) -> None:  # noqa: N802 - stdlib handler API
        path = urlsplit(self.path).path
        diagnosis_route = self._diagnosis_post_route(path)
        if diagnosis_route is not None:
            try:
                raw_body = self._read_raw_diagnosis_request()
            except ValueError as exc:
                self._send_diagnosis_transport_error(
                    HTTPStatus.BAD_REQUEST,
                    "INVALID_REQUEST_ENVELOPE",
                    str(exc),
                )
                return
            method, campaign_id = diagnosis_route
            if campaign_id is None:
                status, body = method(raw_body)
            else:
                status, body = method(campaign_id, raw_body)
            self._send_diagnosis_response(status, body)
            return
        if path.startswith(DIAGNOSIS_API_PREFIX):
            self._send_diagnosis_transport_error(
                HTTPStatus.NOT_FOUND,
                "NOT_FOUND",
                "Diagnosis endpoint was not found.",
            )
            return
        if path not in {"/api/tempo/analyze", "/api/tempo/conductivity"}:
            self.send_error(HTTPStatus.NOT_FOUND, "Not found")
            return
        try:
            payload, transport_input_hash = self._read_json_request()
        except ValueError as exc:
            self._send_json({"status": "no_estimate", "error": str(exc)}, HTTPStatus.BAD_REQUEST)
            return
        from discovery_flight_simulator.tempo import (
            TempoError,
            analyze_cv_request,
            calculate_conductivity,
        )
        try:
            if path == "/api/tempo/analyze":
                result = analyze_cv_request(payload, transport_input_hash=transport_input_hash)
            else:
                result = calculate_conductivity(payload, transport_input_hash=transport_input_hash)
        except TempoError as exc:
            status = (
                HTTPStatus.CONFLICT
                if exc.code == "SOURCE_INTEGRITY_FAILED"
                else HTTPStatus.UNPROCESSABLE_ENTITY
            )
            self._send_json(exc.response(payload.get("request_id")), status)
            return
        self._send_json(result, HTTPStatus.OK)

    def _serve_diagnosis_get(self, *, send_body: bool) -> bool:
        parsed = urlsplit(self.path)
        if parsed.query or parsed.fragment:
            return False
        path = parsed.path
        if path == f"{DIAGNOSIS_API_PREFIX}/scenario":
            status, body = self.diagnosis_service.get_scenario()
        else:
            segments = path.split("/")
            expected = ["", "api", "v1", "closed-loop", "campaigns"]
            if segments[:5] != expected or len(segments) not in {6, 7} or not segments[5]:
                return False
            campaign_id = unquote(segments[5], errors="strict")
            if "/" in campaign_id or "\x00" in campaign_id:
                return False
            if len(segments) == 6:
                status, body = self.diagnosis_service.get_campaign(campaign_id)
            elif segments[6] == "ledger":
                status, body = self.diagnosis_service.get_ledger(campaign_id)
            else:
                return False
        self._send_diagnosis_response(status, body, send_body=send_body)
        return True

    def _diagnosis_post_route(self, path: str):
        if urlsplit(self.path).query or urlsplit(self.path).fragment:
            return None
        if path == f"{DIAGNOSIS_API_PREFIX}/campaigns":
            return self.diagnosis_service.create_campaign, None
        segments = path.split("/")
        expected = ["", "api", "v1", "closed-loop", "campaigns"]
        if segments[:5] != expected or len(segments) != 7 or not segments[5]:
            return None
        campaign_id = unquote(segments[5], errors="strict")
        if "/" in campaign_id or "\x00" in campaign_id:
            return None
        method = {
            "actions": self.diagnosis_service.act,
            "stop": self.diagnosis_service.stop,
            "reveal": self.diagnosis_service.reveal,
        }.get(segments[6])
        return None if method is None else (method, campaign_id)

    def _read_raw_diagnosis_request(self) -> bytes:
        raw_length = self.headers.get("Content-Length")
        try:
            length = int(raw_length or "0")
        except ValueError as exc:
            raise ValueError("valid Content-Length is required") from exc
        if length < 0 or length > MAX_DIAGNOSIS_REQUEST_BYTES:
            raise ValueError("request body size is invalid")
        raw_body = self.rfile.read(length)
        if len(raw_body) != length:
            raise ValueError("request body ended before Content-Length bytes were received")
        return raw_body

    def _send_diagnosis_transport_error(
        self,
        status: HTTPStatus,
        code: str,
        message: str,
        *,
        send_body: bool = True,
    ) -> None:
        from discovery_flight_simulator.diagnosis import transport_error_envelope

        self._send_diagnosis_response(
            int(status),
            transport_error_envelope(code, message),
            send_body=send_body,
        )

    def _send_diagnosis_response(
        self,
        status: int,
        body: bytes,
        *,
        send_body: bool = True,
    ) -> None:
        """Relay core-owned status and JSON bytes without parsing or reserialization."""

        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        self.end_headers()
        if send_body:
            self.wfile.write(body)

    def _serve(self, *, send_body: bool) -> None:
        raw_path = urlsplit(self.path).path
        if raw_path.startswith(DIAGNOSIS_API_PREFIX):
            self._send_diagnosis_transport_error(
                HTTPStatus.NOT_FOUND,
                "NOT_FOUND",
                "Diagnosis endpoint was not found.",
                send_body=send_body,
            )
            return
        try:
            path = unquote(raw_path, errors="strict")
        except UnicodeDecodeError:
            self.send_error(HTTPStatus.BAD_REQUEST, "Invalid URL encoding")
            return
        if "\x00" in path:
            self.send_error(HTTPStatus.BAD_REQUEST, "Invalid path")
            return

        if path == TEMPO_REFERENCE_ROUTE:
            try:
                payload = load_tempo_reference()
            except ValueError as exc:
                self._send_json(
                    {"status": "no_estimate", "code": "SOURCE_INTEGRITY_FAILED", "message": str(exc)},
                    HTTPStatus.CONFLICT,
                    send_body=send_body,
                )
                return
            self._send_json(payload, HTTPStatus.OK, send_body=send_body)
            return

        static_file = STATIC_ROUTES.get(path)
        if static_file is not None:
            self._send_file(static_file, send_body=send_body)
            return

        prefix = "/artifacts/"
        if path.startswith(prefix):
            relative = path[len(prefix) :]
            if not relative:
                self.send_error(HTTPStatus.NOT_FOUND, "Artifact file required")
                return
            candidate = (self.artifact_root / relative).resolve()
            try:
                candidate.relative_to(self.artifact_root)
            except ValueError:
                self.send_error(HTTPStatus.FORBIDDEN, "Artifact path is outside the run directory")
                return
            if not candidate.is_file():
                self.send_error(HTTPStatus.NOT_FOUND, "Artifact not found")
                return
            self._send_file(candidate, send_body=send_body)
            return

        self.send_error(HTTPStatus.NOT_FOUND, "Not found")

    def _read_json_request(self) -> tuple[dict[str, object], str]:
        content_type = self.headers.get_content_type()
        if content_type != "application/json":
            raise ValueError("Content-Type must be application/json")
        raw_length = self.headers.get("Content-Length")
        try:
            length = int(raw_length or "")
        except ValueError as exc:
            raise ValueError("valid Content-Length is required") from exc
        if length <= 0 or length > MAX_TEMPO_REQUEST_BYTES:
            raise ValueError("request body size is invalid")
        raw_body = self.rfile.read(length)
        try:
            payload = json.loads(raw_body.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ValueError("request body must be valid UTF-8 JSON") from exc
        if not isinstance(payload, dict):
            raise ValueError("request body must be a JSON object")
        transport_input_hash = hashlib.sha256(raw_body).hexdigest()
        claimed_hash = self.headers.get("X-Tempo-Input-Hash")
        if claimed_hash is not None and claimed_hash != transport_input_hash:
            raise ValueError("X-Tempo-Input-Hash does not match the exact UTF-8 request body")
        return payload, transport_input_hash

    def _send_json(
        self,
        payload: dict[str, object],
        status: HTTPStatus,
        *,
        send_body: bool = True,
    ) -> None:
        body = (json.dumps(payload, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        self.end_headers()
        if send_body:
            self.wfile.write(body)

    def _send_file(self, path: Path, *, send_body: bool) -> None:
        try:
            payload = path.read_bytes()
        except OSError:
            self.send_error(HTTPStatus.NOT_FOUND, "File not found")
            return
        content_type = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
        if path.suffix == ".json":
            content_type = "application/json"
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", f"{content_type}; charset=utf-8")
        self.send_header("Content-Length", str(len(payload)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header(
            "Content-Security-Policy",
            "default-src 'self'; script-src 'self'; style-src 'self'; "
            "connect-src 'self'; img-src 'self' data:; object-src 'none'; base-uri 'none'",
        )
        self.end_headers()
        if send_body:
            self.wfile.write(payload)

    def log_message(self, format: str, *args: object) -> None:
        print(f"{self.address_string()} - {format % args}")


def load_tempo_reference() -> dict[str, object]:
    """Return the curated atlas only when its local deterministic-record checksum matches."""

    try:
        payload = json.loads(TEMPO_REFERENCE_PATH.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"cannot read TEMPO reference: {exc}") from exc
    if not isinstance(payload, dict) or payload.get("schema_version") != "tempo-reference-v1":
        raise ValueError("TEMPO reference schema mismatch")
    supplied = payload.get("record_checksum")
    unhashed = {key: value for key, value in payload.items() if key != "record_checksum"}
    canonical = json.dumps(unhashed, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    expected = "sha256:" + hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    if supplied != expected:
        raise ValueError("TEMPO reference checksum mismatch")
    samples = payload.get("samples")
    if not isinstance(samples, list) or [item.get("sample_id") for item in samples] != [
        "4ht",
        "4ot",
        "4at",
        "4cyt",
        "4cat",
    ]:
        raise ValueError("TEMPO reference sample inventory mismatch")
    return payload


def validate_artifact_root(path: Path) -> Path:
    # Import lazily so `python demo/serve.py --help` works before project dependencies are installed.
    # Actual serving still fails closed unless the core verifier and its dependencies are available.
    from discovery_flight_simulator.artifacts import verify_artifact_bundle

    root = path.expanduser().resolve()
    if not root.is_dir():
        raise ValueError(f"artifact directory does not exist: {root}")
    missing = [name for name in REQUIRED_ARTIFACTS if not (root / name).is_file()]
    if missing:
        raise ValueError(f"artifact directory is incomplete; missing: {', '.join(missing)}")
    for name in REQUIRED_ARTIFACTS:
        try:
            data = json.loads((root / name).read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise ValueError(f"invalid JSON artifact {name}: {exc}") from exc
        if not isinstance(data, dict) or data.get("provenance") != "simulated":
            raise ValueError(f"artifact {name} must declare provenance: simulated")
    # Core owns integrity and cross-file identity semantics. The demo must never expose a bundle
    # that merely looks structurally plausible but has a modified manifest, summary, or ledger.
    bundle = verify_artifact_bundle(root)
    return bundle.path.resolve()


def create_server(
    artifact_root: Path,
    host: str = "127.0.0.1",
    port: int = 8000,
    *,
    diagnosis_service: DiagnosisServiceProtocol | None = None,
    diagnosis_state_dir: Path | None = None,
) -> ThreadingHTTPServer:
    root = validate_artifact_root(artifact_root)
    if diagnosis_service is None:
        from discovery_flight_simulator.diagnosis import DiagnosisService

        private_state = diagnosis_state_dir or (root.parent / ".closed-loop-diagnosis-state")
        diagnosis_service = DiagnosisService(private_state)
    handler = type(
        "ConfiguredDemoRequestHandler",
        (DemoRequestHandler,),
        {"artifact_root": root, "diagnosis_service": diagnosis_service},
    )
    return ThreadingHTTPServer((host, port), handler)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--artifacts", required=True, type=Path, help="completed CLI output directory")
    parser.add_argument("--host", default="127.0.0.1", help="bind address (default: 127.0.0.1)")
    parser.add_argument("--port", default=8000, type=int, help="bind port (default: 8000)")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    try:
        server = create_server(args.artifacts, args.host, args.port)
    except ValueError as exc:
        raise SystemExit(str(exc)) from exc
    host, port = server.server_address[:2]
    print(f"Serving simulated artifact replay at http://{host}:{port}")
    print(f"Artifact root: {args.artifacts.expanduser().resolve()}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopping demo server")
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
