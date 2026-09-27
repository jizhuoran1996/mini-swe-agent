from minisweagent.environments.executor import ExecutorEnvironment
from minisweagent.executors.incus import IncusExecutor
from minisweagent.executors.incus import IncusExecutorConfig as IncusEnvironmentConfig

__all__ = ["IncusEnvironment", "IncusEnvironmentConfig"]


class IncusEnvironment(ExecutorEnvironment):
    executor_class = IncusExecutor
