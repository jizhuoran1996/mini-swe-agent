"""Boot a Firecracker microVM; execute tools through the shared SSH transport."""

import os
from typing import Any, Literal

from pydantic import Field, model_validator

from minisweagent.executors.ssh_vm import SSHVMExecutor, SSHVMExecutorConfig, _build_remote_command

__all__ = ["FirecrackerExecutor", "FirecrackerExecutorConfig", "_build_remote_command"]


class FirecrackerExecutorConfig(SSHVMExecutorConfig):
    firecracker_executable: str = os.getenv("MSWEA_FIRECRACKER_EXECUTABLE", "firecracker")
    firecracker_args: list[str] = []
    network_interface_id: str = "eth0"
    vcpu_count: int = Field(2, ge=1, le=32)
    smt: bool = False
    track_dirty_pages: bool = False
    boot_args: str = "console=ttyS0 reboot=k panic=1 pci=off"
    cpu_template: str = ""
    huge_pages: Literal["", "None", "Transparent", "2M"] = ""
    root_cache_type: Literal["Unsafe", "Writeback"] = "Unsafe"
    root_io_engine: Literal["Sync", "Async"] = "Sync"

    @model_validator(mode="after")
    def validate_cpu_count(self):
        if self.vcpu_count != 1 and self.vcpu_count % 2:
            raise ValueError("vcpu_count must be 1 or even")
        return self


class FirecrackerExecutor(SSHVMExecutor):
    config_class = FirecrackerExecutorConfig
    runtime_name = "firecracker"

    def _start(self) -> None:
        executable = self._validate_host(self.config.firecracker_executable)
        kernel = self._resolve_file(self.config.kernel_image, "Kernel image")
        root_drive = self._prepare_root_drive()
        initrd = self._resolve_file(self.config.initrd_path, "Initrd") if self.config.initrd_path else None
        self._launch([executable, "--api-sock", str(self.api_socket), *self.config.firecracker_args])
        machine_config: dict[str, Any] = {
            "vcpu_count": self.config.vcpu_count,
            "mem_size_mib": self.config.mem_size_mib,
            "smt": self.config.smt,
            "track_dirty_pages": self.config.track_dirty_pages,
        }
        if self.config.cpu_template:
            machine_config["cpu_template"] = self.config.cpu_template
        if self.config.huge_pages:
            machine_config["huge_pages"] = self.config.huge_pages
        self._api("PUT", "/machine-config", machine_config)
        boot_source = {"kernel_image_path": str(kernel), "boot_args": self.config.boot_args}
        if initrd is not None:
            boot_source["initrd_path"] = str(initrd)
        self._api("PUT", "/boot-source", boot_source)
        self._api(
            "PUT",
            "/drives/rootfs",
            {
                "drive_id": "rootfs",
                "path_on_host": str(root_drive),
                "is_root_device": True,
                "is_read_only": self.config.root_read_only,
                "cache_type": self.config.root_cache_type,
                "io_engine": self.config.root_io_engine,
            },
        )
        self._api(
            "PUT",
            f"/network-interfaces/{self.config.network_interface_id}",
            {
                "iface_id": self.config.network_interface_id,
                "host_dev_name": self.config.tap_device,
                "guest_mac": self.config.guest_mac,
            },
        )
        self._api("PUT", "/actions", {"action_type": "InstanceStart"})
        self._wait_for_ssh()
        self.logger.info(f"Started Firecracker microVM at {self.config.guest_ip}")

    def _shutdown(self) -> None:
        self._api("PUT", "/actions", {"action_type": "SendCtrlAltDel"})
