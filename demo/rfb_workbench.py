#!/usr/bin/env python3
"""Serve the local simulated 0D virtual RFB cell campaign workbench."""

from __future__ import annotations

import argparse
import mimetypes
import os
import secrets
import sys
from http import HTTPStatus
from http.server import HTTPServer
from pathlib import Path
from typing import Final
from urllib.parse import unquote, urlsplit

# Direct script execution places demo/, not the repository's src/, on sys.path.
REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
SOURCE_ROOT = REPOSITORY_ROOT / "src"
if str(SOURCE_ROOT) not in sys.path:
    sys.path.insert(0, str(SOURCE_ROOT))

from discovery_flight_simulator.rfb.api import RFBAPIRequestHandler, RFBAPIService  # noqa: E402
from discovery_flight_simulator.rfb.scenario import load_rfb_scenario  # noqa: E402
from discovery_flight_simulator.rfb.store import SQLiteRFBCampaignStore  # noqa: E402
from discovery_flight_simulator.rfb.workflow import RFBWorkflowService  # noqa: E402


STATIC_ROOT = Path(__file__).resolve().parent / "rfb_workbench"
_STATIC_ROUTES: Final[dict[str, str]] = {
    "/": "index.html",
    "/rfb-workbench.css": "styles.css",
    "/rfb-workbench.js": "app.js",
}
_STATIC_TYPES: Final[dict[str, str]] = {
    ".css": "text/css; charset=utf-8",
    ".html": "text/html; charset=utf-8",
    ".js": "application/javascript; charset=utf-8",
}
_COMMITMENT_KEY_FILENAME: Final[str] = ".rfb_workbench_commitment_key"
_CAMPAIGN_DB_FILENAME: Final[str] = "rfb_campaigns.sqlite"
_CHECKPOINT_DB_FILENAME: Final[str] = "rfb_workflow_checkpoints.sqlite"
_API_PREFIX: Final[str] = "/api/rfb"


class RFBWorkbenchHTTPServer(HTTPServer):
    """Local server that owns the disposable workflow and SQLite handles."""

    def __init__(
        self,
        address: tuple[str, int],
        handler: type[RFBAPIRequestHandler],
        *,
        workflow: RFBWorkflowService,
        store: SQLiteRFBCampaignStore,
    ) -> None:
        super().__init__(address, handler)
        self._workflow = workflow
        self._store = store
        self._resources_closed = False

    def close(self) -> None:
        """Close the socket and all server-owned persistent-resource handles."""

        self.server_close()
        if not self._resources_closed:
            self._workflow.close()
            self._store.close()
            self._resources_closed = True


class RFBWorkbenchRequestHandler(RFBAPIRequestHandler):
    """Combine a fixed local workbench bundle with the frozen RFB API handler."""

    api_service: RFBAPIService

    def do_GET(self) -> None:  # noqa: N802 - stdlib handler API
        raw_path = urlsplit(self.path).path
        if _is_api_path(raw_path):
            super().do_GET()
            return
        self._serve_static(raw_path, send_body=True)

    def do_HEAD(self) -> None:  # noqa: N802 - stdlib handler API
        raw_path = urlsplit(self.path).path
        if _is_api_path(raw_path):
            super().do_HEAD()
            return
        self._serve_static(raw_path, send_body=False)

    def do_POST(self) -> None:  # noqa: N802 - stdlib handler API
        raw_path = urlsplit(self.path).path
        if _is_api_path(raw_path):
            super().do_POST()
            return
        self._send_static_error(HTTPStatus.NOT_FOUND)

    def _serve_static(self, raw_path: str, *, send_body: bool) -> None:
        try:
            path = unquote(raw_path, errors="strict")
        except UnicodeDecodeError:
            self._send_static_error(HTTPStatus.BAD_REQUEST)
            return
        if "\x00" in path:
            self._send_static_error(HTTPStatus.BAD_REQUEST)
            return

        filename = _STATIC_ROUTES.get(path)
        if filename is None:
            self._send_static_error(HTTPStatus.NOT_FOUND)
            return
        static_file = _confined_static_file(filename)
        if static_file is None:
            self._send_static_error(HTTPStatus.NOT_FOUND)
            return
        try:
            payload = static_file.read_bytes()
        except OSError:
            self._send_static_error(HTTPStatus.NOT_FOUND)
            return

        content_type = _STATIC_TYPES.get(static_file.suffix)
        if content_type is None:
            content_type = f"{mimetypes.guess_type(static_file.name)[0] or 'application/octet-stream'}; charset=utf-8"
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(payload)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        if send_body:
            self.wfile.write(payload)

    def _send_static_error(self, status: HTTPStatus) -> None:
        self.send_response(status)
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.send_header("Content-Length", "0")
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()


def _is_api_path(path: str) -> bool:
    return path == _API_PREFIX or path.startswith(f"{_API_PREFIX}/")


def _confined_static_file(filename: str) -> Path | None:
    """Resolve one allowlisted file and reject a missing or escaping symlink."""

    root = STATIC_ROOT.resolve()
    candidate = root / filename
    try:
        resolved = candidate.resolve(strict=True)
        resolved.relative_to(root)
    except (OSError, ValueError):
        return None
    return resolved if resolved.is_file() else None


def _state_directory(path: Path) -> Path:
    root = path.expanduser().resolve()
    root.mkdir(mode=0o700, parents=True, exist_ok=True)
    if not root.is_dir():
        raise ValueError("data directory must be a directory")
    return root


def _load_or_create_commitment_key(data_dir: Path) -> bytes:
    """Create one local key atomically so scenario commitments survive restarts."""

    key_path = data_dir / _COMMITMENT_KEY_FILENAME
    try:
        descriptor = os.open(key_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError:
        key = key_path.read_bytes()
    else:
        key = secrets.token_bytes(32)
        try:
            with os.fdopen(descriptor, "wb") as key_file:
                key_file.write(key)
        except BaseException:
            key_path.unlink(missing_ok=True)
            raise
    if not key:
        raise ValueError("local scenario commitment key is empty")
    if os.name == "posix":
        key_path.chmod(0o600)
    return key


def create_server(
    scenario_path: str | Path,
    data_dir: str | Path,
    host: str = "127.0.0.1",
    port: int = 8001,
) -> RFBWorkbenchHTTPServer:
    """Create a local workbench server backed only by the supplied state directory."""

    state_dir = _state_directory(Path(data_dir))
    commitment_key = _load_or_create_commitment_key(state_dir)
    loaded_scenario = load_rfb_scenario(scenario_path, private_commitment_key=commitment_key)
    store = SQLiteRFBCampaignStore(state_dir / _CAMPAIGN_DB_FILENAME)
    workflow = RFBWorkflowService(
        store,
        {loaded_scenario.public_projection().scenario_id: loaded_scenario},
        state_dir / _CHECKPOINT_DB_FILENAME,
    )
    service = RFBAPIService(workflow, loaded_scenario.public_projection())
    handler = type(
        "ConfiguredRFBWorkbenchRequestHandler",
        (RFBWorkbenchRequestHandler,),
        {"api_service": service},
    )
    try:
        return RFBWorkbenchHTTPServer((host, port), handler, workflow=workflow, store=store)
    except BaseException:
        workflow.close()
        store.close()
        raise


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--scenario", required=True, type=Path, help="simulated RFB scenario JSON")
    parser.add_argument("--data-dir", required=True, type=Path, help="private local server state directory")
    parser.add_argument("--host", default="127.0.0.1", help="bind address (default: 127.0.0.1)")
    parser.add_argument("--port", default=8001, type=int, help="bind port (default: 8001)")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    try:
        server = create_server(args.scenario, args.data_dir, args.host, args.port)
    except (OSError, ValueError) as exc:
        raise SystemExit(str(exc)) from exc
    host, port = server.server_address[:2]
    print(f"Serving simulated RFB workbench at http://{host}:{port}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopping RFB workbench")
    finally:
        server.close()


if __name__ == "__main__":
    main()
