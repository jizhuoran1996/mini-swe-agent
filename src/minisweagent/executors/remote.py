"""Host-side tool executor; only commands and sandbox configuration cross the wire."""

import os
import threading
import time
import uuid
import weakref
from typing import Any

import requests
from pydantic import BaseModel, Field


class RemoteExecutorConfig(BaseModel):
    endpoint: str = "http://127.0.0.1:8080"
    sandbox: dict
    token_env: str = "MSWEA_SANDBOX_TOKEN"
    cwd: str = ""
    env: dict[str, str] = {}
    timeout: float = Field(default=30, gt=0)
    rpc_timeout: float = Field(default=10, gt=0)
    startup_timeout: float = Field(default=300, gt=0)
    cleanup_timeout: float = Field(default=120, gt=0)
    poll_interval: float = Field(default=0.1, gt=0)


class RemoteExecutor:
    def __init__(self, **kwargs):
        self.config = RemoteExecutorConfig(**kwargs)
        self.sandbox_id = uuid.uuid4().hex
        self.pending_execution_id: str | None = None
        self._lock = threading.Lock()
        self._stopped = threading.Event()
        self._closed = False
        self._path = f"/sandboxes/{self.sandbox_id}"
        response = self._request("POST", "/sandboxes", {"id": self.sandbox_id, "sandbox": self.config.sandbox})
        self._wait(self._path, self.config.startup_timeout, "ready")
        threading.Thread(
            target=_heartbeat,
            args=(weakref.ref(self), self._stopped, response["lease_seconds"] / 3),
            name=f"sandbox-lease-{self.sandbox_id[:8]}",
            daemon=True,
        ).start()

    def _request(self, method: str, path: str, payload: dict | None = None) -> dict:
        token = os.getenv(self.config.token_env, "")
        for attempt in range(3):
            try:
                response = requests.request(
                    method,
                    self.config.endpoint.rstrip("/") + path,
                    json=payload,
                    headers={"Authorization": f"Bearer {token}"} if token else {},
                    timeout=self.config.rpc_timeout,
                    allow_redirects=False,
                )
                if response.status_code not in (200, 202):
                    raise RuntimeError(f"Sandbox service HTTP {response.status_code}: {response.text}")
                return response.json()
            except (requests.ConnectionError, requests.Timeout):
                if attempt == 2:
                    raise
                time.sleep(self.config.poll_interval)
        raise AssertionError("unreachable")

    def _wait(self, path: str, timeout: float, target: str) -> dict:
        deadline = time.monotonic() + timeout
        while True:
            status = self._request("GET", path)
            if status["state"] == target:
                return status
            if status["state"] in ("failed", "cleanup_failed", "closed"):
                raise RuntimeError(f"Remote operation {path}: {status}")
            if time.monotonic() >= deadline:
                raise TimeoutError(f"Remote operation still pending: {path}; query the same ID, do not resubmit")
            self._stopped.wait(self.config.poll_interval)

    def execute(
        self, command: str, cwd: str = "", *, env: dict[str, str] | None = None, timeout: float | None = None
    ) -> dict[str, Any]:
        timeout = self.config.timeout if timeout is None else timeout
        if timeout <= 0:
            raise ValueError("timeout must be positive")
        with self._lock:
            if self._closed:
                raise RuntimeError("Remote sandbox has been closed")
            if self.pending_execution_id:
                raise RuntimeError("Previous execution is unresolved; call resume_execution() before sending a new one")
            self.pending_execution_id = uuid.uuid4().hex
            self._pending_payload = {
                "id": self.pending_execution_id,
                "command": command,
                "cwd": cwd or self.config.cwd,
                "env": self.config.env | (env or {}),
                "timeout": timeout,
            }
            return self._resume_execution()

    def resume_execution(self) -> dict[str, Any]:
        """Recover a lost response without executing the command again."""
        with self._lock:
            if not self.pending_execution_id:
                raise RuntimeError("No unresolved execution")
            return self._resume_execution()

    def _resume_execution(self) -> dict[str, Any]:
        self._request("POST", self._path + "/executions", self._pending_payload)
        result = self._wait(
            self._path + f"/executions/{self.pending_execution_id}",
            self._pending_payload["timeout"] + self.config.cleanup_timeout,
            "completed",
        )["result"]
        self.pending_execution_id = None
        return result

    def cleanup(self) -> None:
        with self._lock:
            if not self._closed:
                self._request("DELETE", self._path)
                self._wait(self._path, self.config.cleanup_timeout, "closed")
                self._closed = True
                self._stopped.set()


def _heartbeat(reference: weakref.ReferenceType, stopped: threading.Event, interval: float) -> None:
    while not stopped.wait(interval):
        executor = reference()
        if executor is None:
            return
        try:
            status = executor._request("GET", executor._path)
            if status["state"] in ("closed", "failed", "cleanup_failed"):
                return
        except (requests.RequestException, RuntimeError):
            # A transient disconnect must not kill the lease thread; foreground calls report errors.
            pass
        finally:
            del executor
