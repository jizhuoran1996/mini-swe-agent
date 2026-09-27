import os
import platform
from typing import Any

from minisweagent.environments.executor import ExecutorEnvironment
from minisweagent.executors.local import LocalExecutor
from minisweagent.executors.local import LocalExecutorConfig as LocalEnvironmentConfig
from minisweagent.utils.serialize import recursive_merge

__all__ = ["LocalEnvironment", "LocalEnvironmentConfig"]


class LocalEnvironment(ExecutorEnvironment):
    executor_class = LocalExecutor

    def get_template_vars(self, **kwargs) -> dict[str, Any]:
        return recursive_merge(self.config.model_dump(), platform.uname()._asdict(), os.environ, kwargs)
