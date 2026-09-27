import os
import shutil
import subprocess
from pathlib import Path

import pytest
from pydantic import ValidationError

from minisweagent.environments import get_environment_class
from minisweagent.environments.firecracker import (
    FirecrackerEnvironment,
    FirecrackerEnvironmentConfig,
    _build_remote_command,
)


def test_firecracker_environment_config_and_registry():
    config = FirecrackerEnvironmentConfig(kernel_image="vmlinux", root_drive="rootfs.ext4")

    assert config.guest_ip == "172.16.0.2"
    assert config.tap_device == "tap0"
    assert config.vcpu_count == 2
    assert config.mem_size_mib == 2048
    assert config.copy_root_drive is True
    assert get_environment_class("firecracker") is FirecrackerEnvironment


@pytest.mark.parametrize(("vcpu_count", "smt"), [(0, False), (33, False), (3, False), (3, True)])
def test_firecracker_environment_rejects_invalid_cpu_config(vcpu_count, smt):
    with pytest.raises(ValidationError):
        FirecrackerEnvironmentConfig(kernel_image="vmlinux", root_drive="rootfs.ext4", vcpu_count=vcpu_count, smt=smt)


def test_firecracker_remote_command_preserves_cwd_env_and_shell_syntax(tmp_path):
    command = _build_remote_command(
        'printf "%s\\n" "$VALUE"; printf "%s\\n" "$PWD"',
        str(tmp_path),
        {"VALUE": "spaces and 'quotes'"},
        ["bash", "-lc"],
    )

    result = subprocess.run(["bash", "-lc", command], check=True, capture_output=True, text=True)

    assert result.stdout.splitlines() == ["spaces and 'quotes'", str(tmp_path)]


def test_firecracker_environment_reports_missing_executable():
    with pytest.raises(FileNotFoundError, match="Executable not found"):
        FirecrackerEnvironment(
            kernel_image="missing-vmlinux",
            root_drive="missing-rootfs.ext4",
            firecracker_executable="definitely-not-a-firecracker-binary",
        )


def _integration_available() -> bool:
    required_env = (
        "MSWEA_FIRECRACKER_KERNEL_IMAGE",
        "MSWEA_FIRECRACKER_ROOT_DRIVE",
        "MSWEA_FIRECRACKER_TAP_DEVICE",
        "MSWEA_FIRECRACKER_GUEST_IP",
        "MSWEA_FIRECRACKER_SSH_IDENTITY_FILE",
    )
    return (
        shutil.which(os.getenv("MSWEA_FIRECRACKER_EXECUTABLE", "firecracker")) is not None
        and os.access("/dev/kvm", os.R_OK | os.W_OK)
        and all(os.getenv(name) for name in required_env)
        and (Path("/sys/class/net") / os.getenv("MSWEA_FIRECRACKER_TAP_DEVICE", "")).exists()
    )


@pytest.mark.slow
@pytest.mark.skipif(not _integration_available(), reason="Firecracker integration resources are not configured")
def test_firecracker_environment_real_microvm():
    env = FirecrackerEnvironment(
        kernel_image=os.environ["MSWEA_FIRECRACKER_KERNEL_IMAGE"],
        root_drive=os.environ["MSWEA_FIRECRACKER_ROOT_DRIVE"],
        tap_device=os.environ["MSWEA_FIRECRACKER_TAP_DEVICE"],
        guest_ip=os.environ["MSWEA_FIRECRACKER_GUEST_IP"],
        ssh_identity_file=os.environ["MSWEA_FIRECRACKER_SSH_IDENTITY_FILE"],
        env={"MINI_FIRECRACKER_TEST": "works"},
    )
    try:
        assert env.execute({"command": "printf $MINI_FIRECRACKER_TEST"}) == {
            "output": "works",
            "returncode": 0,
            "exception_info": "",
        }
        assert env.execute({"command": "exit 42"})["returncode"] == 42
    finally:
        env.cleanup()
