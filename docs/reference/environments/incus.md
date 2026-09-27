# Incus containers and VMs

The Incus executor creates a uniquely named instance for each tool session, executes commands with
`incus exec`, and deletes only that instance on cleanup. The agent loop, LLM client, replay timing,
and trajectories stay in mini-swe, outside the guest.

## Prerequisites

On the execution host, [install and initialize Incus](https://linuxcontainers.org/incus/docs/main/installing/)
with an appropriate storage pool and profile. The process running mini-swe or the sandbox service must have
permission to use the Incus daemon. Instance creation is asynchronous at the remote service; this executor
waits until command execution is ready. Images need the configured interpreter (`bash -lc` by default).

For `instance_type: vm`, the host needs KVM/QEMU and the guest image must include **incus-agent**.
This is Incus's guest command/management service, not an LLM agent. It uses virtio-vsock, so SSH credentials
and the Firecracker/Cloud Hypervisor TAP pool are not needed. Image aliases and profiles belong to Incus;
Docker image names are not automatically converted into Incus images.

## Configuration

```yaml
environment:
  environment_class: executor
  executor:
    backend: incus
    image: images:ubuntu/24.04
    instance_type: container  # or vm
    project: default
    profiles: [default]
    cwd: /root
    instance_config:
      limits.cpu: "2"
      limits.memory: 1GiB
    startup_timeout: 240
    timeout: 30
```

`storage` optionally selects a pool. `profiles: []` explicitly disables inherited profiles, so provide
a root disk by selecting `storage`. Keep `instance_config` values as strings. Avoid profiles that bind
shared writable host directories if runs need isolated workspaces. Set `executable` (or
`MSWEA_INCUS_EXECUTABLE`) for a specific client or wrapper; it receives argument lists, not shell strings.
The flat adapter `environment_class: incus` accepts the same backend settings.

For [A/B deployment](remote.md), nest this backend configuration under the remote executor's `sandbox`.
All Incus operations occur on B. Multiple sessions create distinct names and root disks; Incus handles
their network allocation. Remote command timeouts retire the affected instance, leaving other sessions alive.
No backend silently falls back to local execution.

::: minisweagent.environments.incus

::: minisweagent.executors.incus.IncusExecutorConfig
