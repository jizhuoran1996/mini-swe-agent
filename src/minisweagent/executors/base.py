"""Shared process execution and result format for tool backends."""

import os
import signal
import subprocess
from typing import Any


def run_process(
    command: str | list[str],
    *,
    timeout: float,
    cwd: str | None = None,
    env: dict[str, str] | None = None,
    shell: bool = False,
) -> subprocess.CompletedProcess[str]:
    process = subprocess.Popen(
        command,
        shell=shell,
        cwd=cwd,
        env=env,
        text=True,
        encoding="utf-8",
        errors="replace",
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        start_new_session=os.name == "posix",
    )
    try:
        stdout, _ = process.communicate(timeout=timeout)
    except subprocess.TimeoutExpired:
        os.killpg(process.pid, signal.SIGKILL) if os.name == "posix" else process.kill()
        stdout, _ = process.communicate()
        raise subprocess.TimeoutExpired(command, timeout, output=stdout) from None
    return subprocess.CompletedProcess(command, process.returncode, stdout=stdout)


class CommandExecutor:
    config: Any

    def execute(
        self, command: str, cwd: str = "", *, env: dict[str, str] | None = None, timeout: float | None = None
    ) -> dict[str, Any]:
        timeout = self.config.timeout if timeout is None else timeout
        if timeout <= 0:
            raise ValueError("timeout must be positive")
        try:
            result = self._execute_command(command, cwd, env or {}, timeout)
            return {"output": result.stdout, "returncode": result.returncode, "exception_info": ""}
        except (OSError, subprocess.SubprocessError) as e:
            raw_output = getattr(e, "output", None) or ""
            return {
                "output": raw_output.decode("utf-8", errors="replace") if isinstance(raw_output, bytes) else raw_output,
                "returncode": -1,
                "exception_info": f"An error occurred while executing the command: {e}",
                "extra": {"exception_type": type(e).__name__, "exception": str(e)},
            }

    def _execute_command(
        self, command: str, cwd: str, env: dict[str, str], timeout: float
    ) -> subprocess.CompletedProcess[str]:
        raise NotImplementedError
