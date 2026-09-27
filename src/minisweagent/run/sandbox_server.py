"""Trusted, single-owner sandbox service. Bind to loopback or use an SSH tunnel."""

import hmac
import json
import os
import signal
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import typer
import yaml
from pydantic import ValidationError

from minisweagent.executors.sandbox import ExecutionRequest, SandboxError, SandboxManager

app = typer.Typer(pretty_exceptions_show_locals=False)


class SandboxHTTPServer(ThreadingHTTPServer):
    def __init__(self, address: tuple[str, int], manager: SandboxManager, token: str = ""):
        if address[0] not in ("127.0.0.1", "localhost") and not token:
            raise ValueError("A token is required when binding outside loopback")
        self.manager = manager
        self.token = token
        super().__init__(address, SandboxRequestHandler)


class SandboxRequestHandler(BaseHTTPRequestHandler):
    server: SandboxHTTPServer

    def setup(self) -> None:
        super().setup()
        self.connection.settimeout(15)

    def log_message(self, format: str, *args) -> None:
        pass

    def _handle(self) -> None:
        if self.server.token and not hmac.compare_digest(
            self.headers.get("Authorization", ""), f"Bearer {self.server.token}"
        ):
            self._respond(401, {"error": "Invalid sandbox service token"})
            return
        try:
            self._respond(202 if self.command in ("POST", "DELETE") else 200, self._dispatch())
        except SandboxError as error:
            self._respond(error.status, {"error": str(error)})
        except (ValueError, ValidationError, TypeError) as error:
            self._respond(400, {"error": str(error)})

    def _body(self) -> dict:
        length = int(self.headers.get("Content-Length", "0"))
        if length <= 0 or length > 1024 * 1024:
            raise SandboxError(413, "JSON body must be between 1 byte and 1 MiB")
        payload = json.loads(self.rfile.read(length))
        if not isinstance(payload, dict):
            raise SandboxError(400, "Expected a JSON object")
        return payload

    def _dispatch(self) -> dict:
        parts = self.path.strip("/").split("/")
        manager = self.server.manager
        if self.command == "GET" and parts == ["health"]:
            return {"state": "ready", "protocol_version": 1}
        if self.command == "POST" and parts == ["sandboxes"]:
            payload = self._body()
            if not isinstance(payload.get("id"), str) or not isinstance(payload.get("sandbox"), dict):
                raise SandboxError(400, "Expected id and sandbox configuration")
            return manager.create(payload["id"], payload["sandbox"])
        if len(parts) >= 2 and parts[0] == "sandboxes":
            session_id = parts[1]
            if len(parts) == 2:
                if self.command == "GET":
                    return manager.status(session_id)
                if self.command == "DELETE":
                    return manager.close(session_id)
            if len(parts) >= 3 and parts[2] == "executions":
                if len(parts) == 3 and self.command == "POST":
                    return manager.execute(session_id, ExecutionRequest(**self._body()))
                if len(parts) == 4 and self.command == "GET":
                    return manager.result(session_id, parts[3])
        raise SandboxError(404, "Unknown endpoint")

    def _respond(self, status: int, payload: dict) -> None:
        body = json.dumps(payload, ensure_ascii=True).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        try:
            self.wfile.write(body)
        except (BrokenPipeError, ConnectionResetError):
            # The operation and its result survive a disconnected client.
            pass

    do_GET = do_POST = do_DELETE = _handle


@app.command()
def main(
    host: str = "127.0.0.1",
    port: int = 8080,
    max_sandboxes: int = 32,
    lease_seconds: float = 300,
    allow_local: bool = False,
    firecracker_networks: Path | None = None,
    vm_networks: Path | None = None,
    token_env: str = "MSWEA_SANDBOX_TOKEN",
) -> None:
    """Run on sandbox host B; agents and models stay on A. Local backend is development-only."""
    token = os.getenv(token_env, "")
    if host not in ("127.0.0.1", "localhost") and not token:
        raise typer.BadParameter("Set the token environment variable before binding outside loopback")
    manager = SandboxManager(
        max_sandboxes=max_sandboxes,
        lease_seconds=lease_seconds,
        allow_local=allow_local,
        firecracker_networks=yaml.safe_load(firecracker_networks.read_text()) if firecracker_networks else None,
        vm_networks=yaml.safe_load(vm_networks.read_text()) if vm_networks else None,
    )
    stop = threading.Event()
    signal.signal(signal.SIGTERM, lambda *_: stop.set())
    signal.signal(signal.SIGINT, lambda *_: stop.set())
    try:
        with SandboxHTTPServer((host, port), manager, token) as server:
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            print(json.dumps({"endpoint": f"http://{host}:{server.server_port}", "pid": os.getpid()}), flush=True)
            stop.wait()
            server.shutdown()
            thread.join()
    finally:
        manager.shutdown()


if __name__ == "__main__":
    app()
