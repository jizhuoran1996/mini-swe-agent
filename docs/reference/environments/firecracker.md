# Firecracker

!!! warning "Initial backend"

    This backend launches Firecracker directly, without the Firecracker jailer. Use the jailer and a host-specific
    network policy before treating it as a production security boundary.

`FirecrackerEnvironment` boots a microVM from an uncompressed Linux kernel and an ext4 root drive, then executes
agent bash actions through SSH. It does not convert OCI/Docker images into Firecracker root drives.
It adapts agent actions to `FirecrackerExecutor`; the Agent, LLM client, and replay stay in the original
mini-swe process. See the [tool executor interface](executor.md) for direct use and injection.

## Prerequisites

- Linux on `x86_64` or `aarch64`, with read/write access to `/dev/kvm`.
- A supported `firecracker` binary and an OpenSSH client.
- An uncompressed guest kernel and bootable ext4 root drive.
- The guest must start SSH, contain the configured public key, and configure the IP that corresponds to its MAC.
- A host TAP device must already exist and be reachable from the guest. Firecracker does not create or firewall it.

The defaults follow Firecracker's getting-started network: host TAP `tap0`, guest MAC `06:00:AC:10:00:02`, and
guest IP `172.16.0.2`. A minimal host-side TAP setup is:

```bash
sudo ip tuntap add tap0 mode tap user "$USER"
sudo ip addr add 172.16.0.1/30 dev tap0
sudo ip link set tap0 up
```

Configure routing, NAT, DNS, and egress filtering separately when the guest needs internet access.

## Configuration

```yaml
environment:
  environment_class: firecracker
  kernel_image: /srv/firecracker/vmlinux
  root_drive: /srv/firecracker/rootfs.ext4
  tap_device: tap0
  guest_ip: 172.16.0.2
  guest_mac: "06:00:AC:10:00:02"
  ssh_user: root
  ssh_identity_file: /srv/firecracker/rootfs.id_rsa
  cwd: /root
  vcpu_count: 2
  mem_size_mib: 2048
  copy_root_drive: true
  timeout: 60
```

`copy_root_drive: true` is the default. It creates a sparse, reflink-capable per-run copy so agent writes do not
modify the base image. Set it to `false` only when the supplied drive is disposable or read-only.

The backend configures `/machine-config`, `/boot-source`, `/drives/rootfs`, and `/network-interfaces/<id>` through
the Firecracker Unix API before sending `InstanceStart`. Every agent action runs in a fresh SSH/bash process while
the microVM and its filesystem remain alive for the whole agent episode.

::: minisweagent.environments.firecracker

::: minisweagent.executors.firecracker.FirecrackerExecutorConfig
