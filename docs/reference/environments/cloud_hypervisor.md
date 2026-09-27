# Cloud Hypervisor

This executor boots a VM through Cloud Hypervisor's native Unix-socket API and executes tools over SSH.
It is separate from Firecracker: native VM configuration, boot, and shutdown use Cloud Hypervisor's
`/api/v1` endpoints. Shared SSH transport and per-session rootfs copying keep the tool interface consistent.
The LLM agent and replay machinery never move into the guest.

## Prerequisites

On the execution host, install [Cloud Hypervisor](https://github.com/cloud-hypervisor/cloud-hypervisor)
and grant the service user read/write access to `/dev/kvm`. Prepare a compatible **PVH direct-boot kernel**,
a bootable root disk, a TAP device accessible by that user, and a guest reachable via SSH.
On x86-64, the kernel must support PCI and virtio-PCI as well as the root filesystem; a Firecracker-only
virtio-MMIO kernel or `pci=off` boot argument will not work. The default disk type is raw.

The executor does not create TAPs, routes, NAT, guest accounts, or SSH keys. Setting `guest_ip` selects
the SSH target; it does not configure the guest's network. See also the shared host/guest preparation
requirements on the [Firecracker page](firecracker.md).

## Configuration

```yaml
environment:
  environment_class: executor
  executor:
    backend: cloud_hypervisor
    executable: cloud-hypervisor
    kernel_image: /srv/mini/vmlinux-pvh
    root_drive: /srv/mini/rootfs.ext4
    boot_args: "console=ttyS0 root=/dev/vda rw reboot=k panic=1"
    tap_device: tap-mini-1
    guest_ip: 172.16.1.2
    guest_mac: "06:00:ac:10:01:02"
    ssh_identity_file: /srv/mini/guest.id_ed25519
    vcpu_count: 2
    mem_size_mib: 1024
    copy_root_drive: true
    startup_timeout: 60
    cwd: /root
```

`MSWEA_CLOUD_HYPERVISOR_EXECUTABLE` supplies the default executable. `initrd_path` is optional.
Each executor owns a separate VMM process, API socket, log directory, and writable rootfs clone.
Cleanup shuts down the VMM and removes only that session's temporary resources. Base images are retained.
`keep_runtime_dir: true` retains its logs/rootfs for debugging. The flat
`environment_class: cloud_hypervisor` adapter accepts the same settings.

For [A/B deployment](remote.md), put the backend config under `executor.sandbox` and start B with
`--vm-networks /srv/mini/network-slots.yaml`. Firecracker and Cloud Hypervisor share that exclusive slot
pool; different sessions cannot receive the same TAP/IP/MAC. `copy_root_drive: false` with a writable root
is rejected by the remote service. Incus-managed VMs use Incus's own lifecycle instead of this pool.

::: minisweagent.environments.cloud_hypervisor

::: minisweagent.executors.cloud_hypervisor.CloudHypervisorExecutorConfig
