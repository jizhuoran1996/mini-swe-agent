"""Cloud Hypervisor direct-kernel guests; models and agent loops remain on the host."""

import os
from pathlib import Path
from typing import Literal

from minisweagent.executors.ssh_vm import SSHVMExecutor, SSHVMExecutorConfig


class CloudHypervisorExecutorConfig(SSHVMExecutorConfig):
    executable: str = os.getenv("MSWEA_CLOUD_HYPERVISOR_EXECUTABLE", "cloud-hypervisor")
    vmm_args: list[str] = []
    boot_args: str = "console=ttyS0 root=/dev/vda rw reboot=k panic=1"
    image_type: Literal["Raw", "Qcow2", "FixedVhd", "Vhdx"] = "Raw"


def build_vm_config(config: CloudHypervisorExecutorConfig, kernel: Path, root_drive: Path, serial_log: Path) -> dict:
    payload = {"kernel": str(kernel), "cmdline": config.boot_args}
    if config.initrd_path:
        payload["initramfs"] = str(Path(config.initrd_path).expanduser().resolve())
    return {
        "cpus": {"boot_vcpus": config.vcpu_count, "max_vcpus": config.vcpu_count},
        "memory": {"size": config.mem_size_mib * 1024 * 1024},
        "payload": payload,
        "disks": [{"path": str(root_drive), "readonly": config.root_read_only, "image_type": config.image_type}],
        "net": [{"tap": config.tap_device, "mac": config.guest_mac, "num_queues": 2}],
        "rng": {"src": "/dev/urandom"},
        "console": {"mode": "Off"},
        "serial": {"mode": "File", "file": str(serial_log)},
    }


class CloudHypervisorExecutor(SSHVMExecutor):
    config_class = CloudHypervisorExecutorConfig
    runtime_name = "cloud-hypervisor"

    def _start(self) -> None:
        executable = self._validate_host(self.config.executable)
        kernel = self._resolve_file(self.config.kernel_image, "Kernel image")
        if self.config.initrd_path:
            self._resolve_file(self.config.initrd_path, "Initrd")
        root_drive = self._prepare_root_drive()
        self._launch([executable, "--api-socket", str(self.api_socket), *self.config.vmm_args])
        self._api(
            "PUT",
            "/api/v1/vm.create",
            build_vm_config(
                self.config,
                kernel,
                root_drive,
                self.runtime_dir / "serial.log",
            ),
        )
        self._api("PUT", "/api/v1/vm.boot")
        self._wait_for_ssh()
        self.logger.info(f"Started Cloud Hypervisor VM at {self.config.guest_ip}")

    def _shutdown(self) -> None:
        self._api("PUT", "/api/v1/vmm.shutdown")

    def _log_tail(self) -> str:
        serial_log = self.runtime_dir / "serial.log"
        return super()._log_tail() + (serial_log.read_text(errors="replace")[-4000:] if serial_log.exists() else "")
