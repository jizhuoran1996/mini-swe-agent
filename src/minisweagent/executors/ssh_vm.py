"""Shared lifecycle and SSH transport for local VMM processes."""

from __future__ import annotations

import http.client
import json
import logging
import os
import shlex
import shutil
import socket
import subprocess
import tempfile
import time
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field, model_validator

from minisweagent.executors.base import CommandExecutor, run_process


class SSHVMExecutorConfig(BaseModel):
    kernel_image: str
    """Uncompressed guest kernel image on the host."""
    root_drive: str
    """Bootable ext4 root drive on the host. The guest must provide SSH access."""
    guest_ip: str = "172.16.0.2"
    tap_device: str = "tap0"
    guest_mac: str = "06:00:AC:10:00:02"
    cwd: str = "/root"
    env: dict[str, str] = {}
    forward_env: list[str] = []
    timeout: int = Field(30, gt=0)
    startup_timeout: float = Field(60, gt=0)
    api_timeout: float = Field(5, gt=0)
    vcpu_count: int = Field(2, ge=1, le=256)
    mem_size_mib: int = Field(2048, gt=0)
    boot_args: str = "console=ttyS0 reboot=k panic=1"
    initrd_path: str = ""
    root_read_only: bool = False
    copy_root_drive: bool = True
    ssh_executable: str = os.getenv("MSWEA_SSH_EXECUTABLE", "ssh")
    ssh_user: str = "root"
    ssh_port: int = Field(22, ge=1, le=65535)
    ssh_identity_file: str = ""
    ssh_args: list[str] = [
        "-o",
        "BatchMode=yes",
        "-o",
        "StrictHostKeyChecking=accept-new",
        "-o",
        "ConnectTimeout=2",
    ]
    interpreter: list[str] = ["bash", "-lc"]
    keep_runtime_dir: bool = False

    @model_validator(mode="after")
    def validate_config(self):
        if not self.interpreter:
            raise ValueError("interpreter must not be empty")
        return self


class _UnixHTTPConnection(http.client.HTTPConnection):
    def __init__(self, socket_path: Path, timeout: float):
        super().__init__("localhost", timeout=timeout)
        self.socket_path = socket_path

    def connect(self) -> None:
        self.sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self.sock.settimeout(self.timeout)
        self.sock.connect(str(self.socket_path))


def _build_remote_command(command: str, cwd: str, env: dict[str, str], interpreter: list[str]) -> str:
    setup = [f"cd -- {shlex.quote(cwd)}"]
    setup.extend(f"export {shlex.quote(f'{key}={value}')}" for key, value in env.items())
    setup.append(f"{shlex.join(interpreter)} {shlex.quote(command)}")
    return " && ".join(setup)


class SSHVMExecutor(CommandExecutor):
    config_class: type = SSHVMExecutorConfig
    runtime_name: str = "vm"

    def __init__(
        self,
        *,
        config_class: type | None = None,
        logger: logging.Logger | None = None,
        **kwargs,
    ):
        self.logger = logger or logging.getLogger("minisweagent.environment")
        self.config = (config_class or self.config_class)(**kwargs)
        self.runtime_dir = Path(tempfile.mkdtemp(prefix=f"minisweagent-{self.runtime_name}-"))
        self.api_socket = self.runtime_dir / "api.socket"
        self.log_path = self.runtime_dir / f"{self.runtime_name}.log"
        self.process: subprocess.Popen | None = None
        self._log_stream = None
        try:
            self._start()
        except Exception:
            self.cleanup()
            raise

    def _resolve_executable(self, executable: str) -> str:
        resolved = shutil.which(executable)
        if resolved is None:
            msg = f"Executable not found: {executable}"
            raise FileNotFoundError(msg)
        return resolved

    def _resolve_file(self, value: str, label: str) -> Path:
        path = Path(value).expanduser().resolve()
        if not path.is_file():
            msg = f"{label} not found: {path}"
            raise FileNotFoundError(msg)
        return path

    def _prepare_root_drive(self) -> Path:
        source = self._resolve_file(self.config.root_drive, "Root drive")
        if not self.config.copy_root_drive:
            return source
        destination = self.runtime_dir / source.name
        subprocess.run(
            ["cp", "--reflink=auto", "--sparse=always", "--", str(source), str(destination)],
            check=True,
            capture_output=True,
            text=True,
        )
        return destination

    def _start(self) -> None:
        raise NotImplementedError

    def _validate_host(self, executable: str) -> str:
        executable = self._resolve_executable(executable)
        self._resolve_executable(self.config.ssh_executable)
        if not os.access("/dev/kvm", os.R_OK | os.W_OK):
            raise PermissionError(f"{self.runtime_name} requires read/write access to /dev/kvm")
        tap_path = Path("/sys/class/net") / self.config.tap_device
        if not tap_path.exists():
            msg = f"TAP device not found: {self.config.tap_device}"
            raise FileNotFoundError(msg)

        if self.config.ssh_identity_file:
            self._resolve_file(self.config.ssh_identity_file, "SSH identity file")
        return executable

    def _launch(self, command: list[str]) -> None:
        self._log_stream = self.log_path.open("w")
        self.process = subprocess.Popen(
            command,
            stdin=subprocess.DEVNULL,
            stdout=self._log_stream,
            stderr=subprocess.STDOUT,
            start_new_session=True,
        )
        self._wait_for_api()

    def _wait_for_api(self) -> None:
        deadline = time.monotonic() + self.config.startup_timeout
        while time.monotonic() < deadline:
            if self.process is not None and self.process.poll() is not None:
                msg = f"{self.runtime_name} exited before opening its API socket:\n{self._log_tail()}"
                raise RuntimeError(msg)
            if self.api_socket.exists():
                return
            time.sleep(0.01)
        msg = f"Timed out waiting for {self.runtime_name} API socket:\n{self._log_tail()}"
        raise TimeoutError(msg)

    def _api(self, method: str, path: str, payload: dict | None = None) -> Any:
        connection = _UnixHTTPConnection(self.api_socket, self.config.api_timeout)
        body = json.dumps(payload) if payload is not None else None
        try:
            connection.request(method, path, body=body, headers={"Content-Type": "application/json"})
            response = connection.getresponse()
            raw = response.read().decode("utf-8", errors="replace")
        finally:
            connection.close()
        if not 200 <= response.status < 300:
            msg = f"{self.runtime_name} API {method} {path} failed with HTTP {response.status}: {raw}"
            raise RuntimeError(msg)
        return json.loads(raw) if raw else None

    def _ssh_command(self, remote_command: str) -> list[str]:
        command = [
            self.config.ssh_executable,
            "-T",
            "-p",
            str(self.config.ssh_port),
            "-o",
            f"UserKnownHostsFile={self.runtime_dir / 'known_hosts'}",
            *self.config.ssh_args,
        ]
        if self.config.ssh_identity_file:
            command.extend(["-i", str(Path(self.config.ssh_identity_file).expanduser().resolve())])
        command.extend([f"{self.config.ssh_user}@{self.config.guest_ip}", remote_command])
        return command

    def _run_ssh(self, remote_command: str, timeout: float) -> subprocess.CompletedProcess[str]:
        return run_process(self._ssh_command(remote_command), timeout=timeout)

    def _wait_for_ssh(self) -> None:
        deadline = time.monotonic() + self.config.startup_timeout
        last_output = ""
        while time.monotonic() < deadline:
            if self.process is not None and self.process.poll() is not None:
                msg = f"{self.runtime_name} exited while waiting for SSH:\n{self._log_tail()}"
                raise RuntimeError(msg)
            try:
                result = self._run_ssh("true", min(3, max(0.1, deadline - time.monotonic())))
                last_output = result.stdout
                if result.returncode == 0:
                    return
            except subprocess.TimeoutExpired as e:
                last_output = e.output or ""
            time.sleep(0.1)
        msg = f"Timed out waiting for SSH at {self.config.guest_ip}: {last_output}\n{self._log_tail()}"
        raise TimeoutError(msg)

    def _execute_command(
        self, command: str, cwd: str, env: dict[str, str], timeout: float
    ) -> subprocess.CompletedProcess[str]:
        environment = {name: os.environ[name] for name in self.config.forward_env if name in os.environ}
        environment.update(self.config.env | env)
        remote_command = _build_remote_command(command, cwd or self.config.cwd, environment, self.config.interpreter)
        return self._run_ssh(remote_command, timeout)

    def _log_tail(self) -> str:
        if self._log_stream is not None:
            self._log_stream.flush()
        if not self.log_path.exists():
            return ""
        return self.log_path.read_text(errors="replace")[-4000:]

    def cleanup(self) -> None:
        process = getattr(self, "process", None)
        if process is not None and process.poll() is None:
            try:
                self._shutdown()
                process.wait(timeout=2)
            except Exception:
                process.terminate()
                try:
                    process.wait(timeout=2)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait()
        if getattr(self, "_log_stream", None) is not None:
            self._log_stream.close()
            self._log_stream = None
        runtime_dir = getattr(self, "runtime_dir", None)
        if runtime_dir is not None and runtime_dir.exists() and not self.config.keep_runtime_dir:
            shutil.rmtree(runtime_dir)

    def __del__(self):
        self.cleanup()

    def _shutdown(self) -> None:
        raise NotImplementedError
