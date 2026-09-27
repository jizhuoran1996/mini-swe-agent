from minisweagent.environments.executor import ExecutorEnvironment
from minisweagent.executors.firecracker import FirecrackerExecutor
from minisweagent.executors.firecracker import FirecrackerExecutorConfig as FirecrackerEnvironmentConfig
from minisweagent.executors.firecracker import _build_remote_command as _build_remote_command

__all__ = ["FirecrackerEnvironment", "FirecrackerEnvironmentConfig"]


class FirecrackerEnvironment(ExecutorEnvironment):
    executor_class = FirecrackerExecutor
