#!/usr/bin/env python3
"""Serve the static artifact replay demo with a traversal-safe artifact route."""

from __future__ import annotations

import argparse
import json
import mimetypes
import sys
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
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
}
REQUIRED_ARTIFACTS = (
    "manifest.json",
    "summary.json",
    "ledgers/random.json",
    "ledgers/fixed_grid.json",
    "ledgers/information_gain.json",
)


class DemoRequestHandler(BaseHTTPRequestHandler):
    """Serve known static files and files confined beneath one artifact root."""

    artifact_root: Path

    def do_GET(self) -> None:  # noqa: N802 - stdlib handler API
        self._serve(send_body=True)

    def do_HEAD(self) -> None:  # noqa: N802 - stdlib handler API
        self._serve(send_body=False)

    def _serve(self, *, send_body: bool) -> None:
        raw_path = urlsplit(self.path).path
        try:
            path = unquote(raw_path, errors="strict")
        except UnicodeDecodeError:
            self.send_error(HTTPStatus.BAD_REQUEST, "Invalid URL encoding")
            return
        if "\x00" in path:
            self.send_error(HTTPStatus.BAD_REQUEST, "Invalid path")
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
) -> ThreadingHTTPServer:
    root = validate_artifact_root(artifact_root)
    handler = type(
        "ConfiguredDemoRequestHandler",
        (DemoRequestHandler,),
        {"artifact_root": root},
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
