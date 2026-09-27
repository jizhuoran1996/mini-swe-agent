import os
import subprocess

from pydantic import BaseModel

from minisweagent.executors.base import CommandExecutor, run_process


class LocalExecutorConfig(BaseModel):
    cwd: str = ""
    env: dict[str, str] = {}
    timeout: int = 30


class LocalExecutor(CommandExecutor):
    def __init__(self, *, config_class: type = LocalExecutorConfig, **kwargs):
        self.config = config_class(**kwargs)

    def _execute_command(
        self, command: str, cwd: str, env: dict[str, str], timeout: float
    ) -> subprocess.CompletedProcess[str]:
        return run_process(
            command,
            shell=True,
            cwd=cwd or self.config.cwd or os.getcwd(),
            env=os.environ | self.config.env | env,
            timeout=timeout,
        )

    def cleanup(self) -> None:
        pass
