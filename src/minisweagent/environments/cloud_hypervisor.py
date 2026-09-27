from minisweagent.environments.executor import ExecutorEnvironment
from minisweagent.executors.cloud_hypervisor import CloudHypervisorExecutor
from minisweagent.executors.cloud_hypervisor import CloudHypervisorExecutorConfig as CloudHypervisorEnvironmentConfig

__all__ = ["CloudHypervisorEnvironment", "CloudHypervisorEnvironmentConfig"]


class CloudHypervisorEnvironment(ExecutorEnvironment):
    executor_class = CloudHypervisorExecutor
