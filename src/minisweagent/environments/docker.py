import platform
from typing import Any

from minisweagent.environments.executor import ExecutorEnvironment
from minisweagent.executors.docker import DockerExecutor
from minisweagent.executors.docker import DockerExecutorConfig as DockerEnvironmentConfig
from minisweagent.utils.serialize import recursive_merge

__all__ = ["DockerEnvironment", "DockerEnvironmentConfig"]


class DockerEnvironment(ExecutorEnvironment):
    executor_class = DockerExecutor

    @property
    def container_id(self) -> str | None:
        return self.executor.container_id

    def get_template_vars(self, **kwargs) -> dict[str, Any]:
        return recursive_merge(self.config.model_dump(), platform.uname()._asdict(), kwargs)
