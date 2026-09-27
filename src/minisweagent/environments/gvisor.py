from minisweagent.environments.docker import DockerEnvironment
from minisweagent.executors.gvisor import GVisorExecutor
from minisweagent.executors.gvisor import GVisorExecutorConfig as GVisorEnvironmentConfig

__all__ = ["GVisorEnvironment", "GVisorEnvironmentConfig"]


class GVisorEnvironment(DockerEnvironment):
    executor_class = GVisorExecutor
