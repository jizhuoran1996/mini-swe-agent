from minisweagent.executors.docker import DockerExecutor, DockerExecutorConfig


class GVisorExecutorConfig(DockerExecutorConfig):
    runtime: str = "runsc"


class GVisorExecutor(DockerExecutor):
    def __init__(self, *, config_class: type = GVisorExecutorConfig, **kwargs):
        super().__init__(config_class=config_class, **kwargs)
