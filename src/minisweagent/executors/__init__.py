"""Tool execution backends, independent of the agent loop and model implementation."""

import copy
import importlib

from minisweagent import ToolExecutor

_EXECUTOR_MAPPING = {
    "local": "minisweagent.executors.local.LocalExecutor",
    "docker": "minisweagent.executors.docker.DockerExecutor",
    "gvisor": "minisweagent.executors.gvisor.GVisorExecutor",
    "firecracker": "minisweagent.executors.firecracker.FirecrackerExecutor",
    "cloud_hypervisor": "minisweagent.executors.cloud_hypervisor.CloudHypervisorExecutor",
    "incus": "minisweagent.executors.incus.IncusExecutor",
    "remote": "minisweagent.executors.remote.RemoteExecutor",
}


def get_executor_class(backend: str) -> type[ToolExecutor]:
    full_path = _EXECUTOR_MAPPING.get(backend, backend)
    if "." not in full_path:
        raise ValueError(f"Unknown tool executor: {backend!r}; available: {list(_EXECUTOR_MAPPING)}")
    module, name = full_path.rsplit(".", 1)
    return getattr(importlib.import_module(module), name)


def get_executor(config: dict) -> ToolExecutor:
    config = copy.deepcopy(config)
    return get_executor_class(config.pop("backend", "local"))(**config)
