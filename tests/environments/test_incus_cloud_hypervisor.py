import uuid
from pathlib import Path

import pytest
from pydantic import ValidationError

from minisweagent.environments import get_environment_class
from minisweagent.environments.cloud_hypervisor import CloudHypervisorEnvironment
from minisweagent.environments.incus import IncusEnvironment
from minisweagent.executors import get_executor
from minisweagent.executors.cloud_hypervisor import CloudHypervisorExecutorConfig, build_vm_config
from minisweagent.executors.incus import IncusExecutorConfig, build_exec_command, build_launch_command
from minisweagent.executors.sandbox import SandboxError, SandboxManager


def test_incus_launch_and_exec_preserve_arguments():
    config = IncusExecutorConfig(
        image="images:ubuntu/24.04",
        instance_type="vm",
        project="test-project",
        profiles=[],
        storage="test-pool",
        instance_config={"limits.cpu": "2", "limits.memory": "1GiB"},
        cwd="/work space",
        env={"VALUE": "default", "KEEP": "configured"},
    )
    assert build_launch_command(config, "unique-name") == [
        config.executable,
        "launch",
        "images:ubuntu/24.04",
        "unique-name",
        "--project",
        "test-project",
        "--vm",
        "--profile",
        "",
        "--storage",
        "test-pool",
        "--config",
        "limits.cpu=2",
        "--config",
        "limits.memory=1GiB",
        "--config",
        "user.minisweagent=unique-name",
    ]
    command = 'printf "%s" "$VALUE"; exit 42'
    assert build_exec_command(config, "unique-name", command, "", {"VALUE": "a 'quote'; $(exit 9)"}) == [
        config.executable,
        "exec",
        "unique-name",
        "--project",
        "test-project",
        "--mode=non-interactive",
        "--disable-stdin",
        "--cwd",
        "/work space",
        "--env",
        "VALUE=a 'quote'; $(exit 9)",
        "--env",
        "KEEP=configured",
        "--",
        "bash",
        "-lc",
        command,
    ]
    assert "--vm" not in build_launch_command(IncusExecutorConfig(image="local-image"), "container-name")
    with pytest.raises(ValidationError):
        IncusExecutorConfig(image="local-image", instance_type="invalid")
    with pytest.raises(ValidationError):
        IncusExecutorConfig(image="local-image", interpreter=[])


def test_cloud_hypervisor_native_payload_and_private_disk():
    config = CloudHypervisorExecutorConfig(
        kernel_image="base-kernel",
        root_drive="base.ext4",
        initrd_path="/initrd",
        vcpu_count=3,
        mem_size_mib=512,
        tap_device="test-tap",
        guest_mac="06:00:ac:10:02:02",
    )
    payload = build_vm_config(config, Path("/kernel"), Path("/private/root.ext4"), Path("/private/serial.log"))
    assert payload["cpus"] == {"boot_vcpus": 3, "max_vcpus": 3}
    assert payload["memory"] == {"size": 512 * 1024 * 1024}
    assert payload["payload"] == {"kernel": "/kernel", "initramfs": "/initrd", "cmdline": config.boot_args}
    assert "pci=off" not in config.boot_args
    assert payload["disks"] == [{"path": "/private/root.ext4", "readonly": False, "image_type": "Raw"}]
    assert payload["net"] == [{"tap": "test-tap", "mac": "06:00:ac:10:02:02", "num_queues": 2}]
    assert payload["serial"] == {"mode": "File", "file": "/private/serial.log"}
    assert config.copy_root_drive is True
    with pytest.raises(ValidationError):
        CloudHypervisorExecutorConfig(kernel_image="unused", root_drive="unused", vcpu_count=0)
    with pytest.raises(ValidationError):
        CloudHypervisorExecutorConfig(kernel_image="unused", root_drive="unused", image_type="Vhd")


def test_new_backends_register_and_fail_without_local_fallback():
    assert get_environment_class("incus") is IncusEnvironment
    assert get_environment_class("cloud_hypervisor") is CloudHypervisorEnvironment
    for config in [
        {"backend": "incus", "image": "unused"},
        {"backend": "cloud_hypervisor", "kernel_image": "unused", "root_drive": "unused"},
    ]:
        with pytest.raises(FileNotFoundError, match="Executable not found"):
            get_executor(config | {"executable": "/missing-sandbox-executable"})


def test_mixed_vm_pool_reserves_and_releases_slots():
    slots = [
        {"tap_device": f"test-tap-{i}", "guest_ip": f"172.16.{i}.2", "guest_mac": f"06:00:ac:10:0{i}:02"}
        for i in range(2)
    ]
    with pytest.raises(ValueError, match="not both"):
        SandboxManager(vm_networks=slots, firecracker_networks=slots)
    manager = SandboxManager(vm_networks=slots)
    ids = [uuid.uuid4().hex for _ in slots]
    config = {"kernel_image": "unused", "root_drive": "unused", "executable": "/missing-vmm"}
    try:
        with pytest.raises(SandboxError, match="private writable root"):
            manager.create(uuid.uuid4().hex, config | {"backend": "cloud_hypervisor", "copy_root_drive": False})
        # Failed real launches cannot release slots while we hold the registry lock.
        with manager._lock:
            manager.create(ids[0], config | {"backend": "firecracker", "firecracker_executable": "/missing-vmm"})
            manager.create(ids[1], config | {"backend": "cloud_hypervisor"})
            assert manager._reserved == {0, 1}
            assert [manager._sessions[sid].config["tap_device"] for sid in ids] == ["test-tap-0", "test-tap-1"]
            with pytest.raises(SandboxError, match="No free VM network slots"):
                manager.create(uuid.uuid4().hex, config | {"backend": "cloud_hypervisor"})
    finally:
        manager.shutdown()
    assert not manager._reserved
    assert all(manager.status(sid)["state"] == "closed" for sid in ids)
    assert all("Executable not found" in manager.status(sid)["error"] for sid in ids)
