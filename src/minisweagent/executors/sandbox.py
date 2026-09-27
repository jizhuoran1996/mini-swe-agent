"""Server-side sessions. One FIFO worker per sandbox; no global execution lock."""

import copy
import re
import shutil
import tempfile
import threading
import time
from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import dataclass, field
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field

from minisweagent.executors import get_executor
from minisweagent.executors.cloud_hypervisor import CloudHypervisorExecutorConfig
from minisweagent.executors.firecracker import FirecrackerExecutorConfig


class SandboxError(ValueError):
    def __init__(self, status: int, message: str):
        super().__init__(message)
        self.status = status


class ExecutionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str = Field(pattern=r"^[0-9a-f]{32}$")
    command: str
    cwd: str = ""
    env: dict[str, str] = {}
    timeout: float = Field(default=30, gt=0, le=3600, allow_inf_nan=False)


@dataclass
class SandboxSession:
    id: str
    request: dict
    config: dict
    worker: ThreadPoolExecutor
    start: Future
    executions: dict[str, tuple[dict, Future]] = field(default_factory=dict)
    close: Future | None = None
    touched: float = field(default_factory=time.monotonic)
    workspace: Path | None = None
    network_slot: int | None = None
    unusable: bool = False


class SandboxManager:
    def __init__(
        self,
        *,
        max_sandboxes: int = 32,
        lease_seconds: float = 300,
        allow_local: bool = False,
        firecracker_networks: list[dict] | None = None,
        vm_networks: list[dict] | None = None,
    ):
        if max_sandboxes < 1 or lease_seconds <= 0:
            raise ValueError("max_sandboxes and lease_seconds must be positive")
        self.max_sandboxes = max_sandboxes
        self.lease_seconds = lease_seconds
        self.allow_local = allow_local
        if firecracker_networks is not None and vm_networks is not None:
            raise ValueError("Use vm_networks or the legacy firecracker_networks option, not both")
        self.networks = copy.deepcopy(vm_networks if vm_networks is not None else (firecracker_networks or []))
        for slot in self.networks:
            if set(slot) - {"tap_device", "guest_ip", "guest_mac", "boot_args", "root_drive"}:
                raise ValueError("Network slots only accept tap_device, guest_ip, guest_mac, boot_args, root_drive")
        for key in ("tap_device", "guest_ip", "guest_mac"):
            values = [slot[key].lower() for slot in self.networks]
            if any(not value for value in values) or len(set(values)) != len(values):
                raise ValueError(f"VM network slots require unique, nonempty {key}")
        self._reserved: set[int] = set()
        self._sessions: dict[str, SandboxSession] = {}
        self._lock = threading.RLock()
        self._stopped = threading.Event()
        self._reaper = threading.Thread(target=self._reap, name="sandbox-reaper", daemon=True)
        self._reaper.start()

    @staticmethod
    def _finished(future: Future | None) -> bool:
        return future is not None and future.done() and future.exception() is None

    def create(self, session_id: str, config: dict) -> dict:
        if not re.fullmatch(r"[0-9a-f]{32}", session_id):
            raise SandboxError(400, "Sandbox ID must be 32 lowercase hex characters")
        with self._lock:
            if self._stopped.is_set():
                raise SandboxError(503, "Sandbox service is shutting down")
            if session_id in self._sessions:
                session = self._sessions[session_id]
                if session.request != config:
                    raise SandboxError(409, "Sandbox ID already used with a different configuration")
                return self.status(session_id)
            if sum(not self._finished(s.close) for s in self._sessions.values()) >= self.max_sandboxes:
                raise SandboxError(429, "Sandbox capacity exhausted")
            backend = config.get("backend")
            if backend not in ("docker", "gvisor", "firecracker", "cloud_hypervisor", "incus") and not (
                backend == "local" and self.allow_local
            ):
                raise SandboxError(400, "Unsupported backend (local requires --allow-local)")
            prepared = copy.deepcopy(config)
            workspace = None
            network_slot = None
            if backend in ("firecracker", "cloud_hypervisor"):
                network_slot = next((i for i in range(len(self.networks)) if i not in self._reserved), None)
                if network_slot is None:
                    raise SandboxError(429, "No free VM network slots; configure --vm-networks")
                prepared.update(self.networks[network_slot])
                config_class = FirecrackerExecutorConfig if backend == "firecracker" else CloudHypervisorExecutorConfig
                vm_config = config_class(**prepared)
                if not vm_config.copy_root_drive and not vm_config.root_read_only:
                    raise SandboxError(400, "Concurrent VMs require private writable root drives")
                self._reserved.add(network_slot)
            if backend == "local" and not prepared.get("cwd"):
                workspace = Path(tempfile.mkdtemp(prefix="minisweagent-sandbox-"))
                prepared["cwd"] = str(workspace)
            worker = ThreadPoolExecutor(max_workers=1, thread_name_prefix=f"sandbox-{session_id[:8]}")
            session = SandboxSession(
                session_id,
                copy.deepcopy(config),
                prepared,
                worker,
                worker.submit(get_executor, prepared),
                workspace=workspace,
                network_slot=network_slot,
            )
            self._sessions[session_id] = session
            session.start.add_done_callback(lambda future: self.close(session_id) if future.exception() else None)
            return self.status(session_id)

    def _get(self, session_id: str) -> SandboxSession:
        if session_id not in self._sessions:
            raise SandboxError(404, "Unknown sandbox")
        session = self._sessions[session_id]
        session.touched = time.monotonic()
        return session

    def status(self, session_id: str) -> dict:
        with self._lock:
            session = self._get(session_id)
            state, error = "starting", ""
            if session.start.done():
                state = "failed" if session.start.exception() else "ready"
                error = str(session.start.exception() or "")
            if session.close is not None:
                state = "closing"
                if session.close.done():
                    state = "cleanup_failed" if session.close.exception() else "closed"
                    error = str(session.close.exception() or error)
            return {"sandbox_id": session_id, "state": state, "error": error, "lease_seconds": self.lease_seconds}

    def execute(self, session_id: str, request: ExecutionRequest) -> dict:
        with self._lock:
            session = self._get(session_id)
            payload = request.model_dump()
            if request.id in session.executions:
                if session.executions[request.id][0] != payload:
                    raise SandboxError(409, "Execution ID already used with a different command")
            else:
                if session.close is not None or session.unusable:
                    raise SandboxError(409, "Sandbox is closing or unusable")
                if len(session.executions) >= 10000:
                    raise SandboxError(429, "Execution history limit reached; create a new sandbox")
                session.executions[request.id] = (payload, session.worker.submit(self._execute, session, payload))
            return self.result(session_id, request.id)

    def _execute(self, session: SandboxSession, payload: dict) -> dict:
        if session.unusable:
            raise RuntimeError("Sandbox retired after an earlier command timed out")
        result = session.start.result().execute(**{key: value for key, value in payload.items() if key != "id"})
        if session.config["backend"] != "local" and result.get("extra", {}).get("exception_type") == "TimeoutExpired":
            # Killing a transport client does not guarantee that the guest process has stopped.
            session.unusable = True
            self.close(session.id)
        return result

    def result(self, session_id: str, execution_id: str) -> dict:
        with self._lock:
            session = self._get(session_id)
            if execution_id not in session.executions:
                raise SandboxError(404, "Unknown execution")
            future = session.executions[execution_id][1]
            if not future.done():
                return {"execution_id": execution_id, "state": "running" if future.running() else "queued"}
            if future.exception():
                return {"execution_id": execution_id, "state": "failed", "error": str(future.exception())}
            return {"execution_id": execution_id, "state": "completed", "result": future.result()}

    def close(self, session_id: str) -> dict:
        with self._lock:
            session = self._get(session_id)
            if session.close is None or (session.close.done() and session.close.exception()):
                session.close = session.worker.submit(self._cleanup, session)
                session.close.add_done_callback(
                    lambda future: session.worker.shutdown(wait=False) if not future.exception() else None
                )
            return self.status(session_id)

    def _cleanup(self, session: SandboxSession) -> None:
        if session.start.exception() is None:
            session.start.result().cleanup()
        if session.workspace is not None:
            shutil.rmtree(session.workspace)
            session.workspace = None
        with self._lock:
            if session.network_slot is not None:
                self._reserved.remove(session.network_slot)
                session.network_slot = None

    def _reap(self) -> None:
        while not self._stopped.wait(min(1, self.lease_seconds / 4)):
            with self._lock:
                for session in self._sessions.values():
                    if session.close is None and time.monotonic() - session.touched > self.lease_seconds:
                        self.close(session.id)

    def shutdown(self) -> None:
        self._stopped.set()
        self._reaper.join()
        with self._lock:
            sessions = list(self._sessions.values())
            for session in sessions:
                self.close(session.id)
        for session in sessions:
            session.worker.shutdown(wait=True)
            session.close.result()
