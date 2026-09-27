# Remote tool sandboxes

The agent, LLM client / ReplayModel, trajectories, and model timing stay on machine A.
Machine B only provisions sandboxes and executes commands. Start with two processes on localhost;
moving to another machine only changes the endpoint and B-side resource paths.

```text
A: Agent + Model / ReplayModel
           |
     ExecutorEnvironment -> RemoteExecutor
                                  | HTTP (sandbox ID + execution ID)
B:                         Sandbox service
                           |       |       |            |               |
                         Docker  gVisor  Firecracker  Cloud Hypervisor  Incus
                         session session  session       session         session
```

## Start B and configure A

Install the same checkout on both machines. On B:

```bash
mini-extra sandbox-server --host 127.0.0.1 --port 8080 --max-sandboxes 32
# Equivalent: python -m minisweagent.run.sandbox_server ...
```

On A, use the normal environment configuration (also accepted by replay's `--environment-config`):

```yaml
environment:
  environment_class: executor
  executor:
    backend: remote
    endpoint: http://127.0.0.1:8080
    token_env: MSWEA_SANDBOX_TOKEN
    timeout: 60
    sandbox:
      backend: docker
      image: your-existing-task-image
      cwd: /testbed
      run_args: ["--rm", "--pull=never"]
```

Switch `sandbox.backend` to `gvisor` to use the Docker-registered `runsc` runtime on B.
Use `incus` for Incus-managed containers or VMs, or `cloud_hypervisor` for direct-kernel KVM guests.
See the [Incus](incus.md) and [Cloud Hypervisor](cloud_hypervisor.md) configurations.
The SWE-bench batch runner also fills in the instance-specific image for remote Docker/gVisor.
Images, bind-mount paths, kernels, rootfs, SSH keys, and executables refer to **B**, not A.
The transport does not upload files or download artifacts automatically; read/export needed results before cleanup.
`sandbox.env` and `sandbox.forward_env` are evaluated on B; outer `executor.env` and per-call variables are sent by A.

For localhost protocol development without a container runtime:

```bash
mini-extra sandbox-server --allow-local --max-sandboxes 4
```

Use `sandbox: {backend: local}`. Each session gets a fresh temporary directory unless `cwd` is explicitly set.
The service deletes only its own temporary workspaces on cleanup. **Local is not a security sandbox**:
commands retain B's host permissions and environment. It is disabled by default, never used as a fallback.

For separate machines, keep B bound to loopback and forward the port from A:

```bash
ssh -N -L 8080:127.0.0.1:8080 user@machine-b
```

Set `MSWEA_SANDBOX_TOKEN` in both processes for bearer authentication. Only the environment-variable name is
saved in the executor configuration, not its secret value. Non-loopback binding requires a token, but plain
HTTP does not encrypt it: use a trusted encrypted tunnel or an HTTPS reverse proxy. This is a single-owner
execution service, not a multi-tenant public API. An authorized caller can request host mounts and executables;
do not expose it to untrusted clients. No LLM/Hugging Face credentials are needed on B for this protocol.

## Concurrency and lifecycle

Create one executor per agent run. Creating multiple executors creates multiple containers/VMs, not multiple
connections to the same sandbox. Each session has a FIFO worker; separate sessions can boot and run commands
concurrently. `--max-sandboxes` counts starting, running, and closing sessions; excess requests return HTTP 429.
This is a count limit, not a CPU/memory scheduler. Size VM resources/container limits for B's available capacity.

```python
from concurrent.futures import ThreadPoolExecutor
from minisweagent.executors import get_executor

def run_one(index):
    executor = get_executor({
        "backend": "remote",
        "endpoint": "http://127.0.0.1:8080",
        "sandbox": {"backend": "docker", "image": "your-existing-task-image"},
    })
    try:
        # Or inject this executor into ExecutorEnvironment and run an agent on A.
        return executor.execute(f"echo task-{index}; hostname")
    finally:
        executor.cleanup()

with ThreadPoolExecutor(max_workers=4) as pool:
    results = list(pool.map(run_one, range(4)))
```

Call `cleanup()` explicitly. It drains already accepted commands, destroys the runtime, and waits for closure.
A background client heartbeat keeps the session alive during LLM/replay delays. If A disappears, B queues
cleanup after `--lease-seconds` (default 300); active commands retain their configured timeout (maximum 3600s).
Docker/SSH/Incus command timeouts retire that sandbox, because killing the transport alone may leave guest work
running. Later queued commands fail rather than overlap a timed-out command. Local timeouts kill the host
process group and allow subsequent commands. Cleanup failures are reported and do not free capacity/network slots.

Requests have client-generated IDs. Retrying a create/execute with the same ID and payload returns the same
operation; using that ID with different content returns HTTP 409. Network retries reuse IDs. If a response
cannot be recovered, `pending_execution_id` remains set: call `resume_execution()` on that executor instead
of executing the command again. Do not create a new executor to retry an uncertain side effect.
Command timeout is enforced on B; `rpc_timeout` only bounds an individual HTTP request on A.

API endpoints:

| Operation | Endpoint |
| --- | --- |
| Create (202) | `POST /sandboxes`, body `{"id": "<uuid hex>", "sandbox": {...}}` |
| Status / lease refresh | `GET /sandboxes/{id}` |
| Submit (202) | `POST /sandboxes/{id}/executions`, body `{"id": "<uuid hex>", "command": "...", "cwd": "", "env": {}, "timeout": 30}` |
| Result / lease refresh | `GET /sandboxes/{id}/executions/{execution_id}` |
| Close (202) | `DELETE /sandboxes/{id}` |

Statuses/results and closed-ID tombstones are held in memory for the service lifetime, with a 10,000-execution
limit per session. There is no persistence, crash recovery, output streaming, or automatic cross-host scheduling
yet. A B-process crash may leave runtime resources needing operator cleanup; never assume an uncertain command
did not run. This first version is intended for controlled experiments; long-lived production deployments need
bounded history/output storage and runtime reconciliation across restarts.

## Concurrent Firecracker and Cloud Hypervisor VMs

Configure a pool of **pre-provisioned** network slots on B. Every slot needs a unique TAP, reachable guest IP,
and MAC. The service allocates a slot exclusively until VM cleanup completes; it rejects duplicate slots and
returns HTTP 429 when no slot is free. It does not create TAP devices, routes, NAT, or guest network configuration.
Both VMM backends share this pool, so a Firecracker and a Cloud Hypervisor VM cannot receive the same slot.
Use only one service process per pool; separate service processes do not coordinate reservations.
Incus manages its own instances and networking and does not consume these slots, including for Incus VMs.

```yaml
# /srv/mini/network-slots.yaml (on B)
- tap_device: tap-mini-1
  guest_ip: 172.16.1.2
  guest_mac: "06:00:ac:10:01:02"
  root_drive: /srv/mini/guest-1.ext4
- tap_device: tap-mini-2
  guest_ip: 172.16.2.2
  guest_mac: "06:00:ac:10:02:02"
  root_drive: /srv/mini/guest-2.ext4
```

Here each base rootfs has networking configured for its slot. Alternatively use a common base and per-slot
`boot_args` if the guest supports kernel IP autoconfiguration. Merely setting `guest_ip` changes the SSH target,
not the guest's network settings. Follow the [Firecracker prerequisites](firecracker.md) for KVM, kernel,
rootfs, SSH, and TAP preparation.

```bash
mini-extra sandbox-server --max-sandboxes 32 --vm-networks /srv/mini/network-slots.yaml
```

The previous `--firecracker-networks` option remains supported; do not pass both options.

On A:

```yaml
environment:
  environment_class: executor
  executor:
    backend: remote
    endpoint: http://127.0.0.1:8080
    sandbox:
      backend: firecracker
      kernel_image: /srv/mini/vmlinux
      root_drive: /srv/mini/base.ext4  # a slot's root_drive overrides this if supplied
      ssh_identity_file: /srv/mini/guest.id_rsa
      vcpu_count: 2
      mem_size_mib: 2048
      copy_root_drive: true
```

Each VM already gets its own API socket, process, runtime directory, and writable rootfs clone.
Sharing a writable rootfs without copying is rejected. Network values supplied by A are overridden by B's slot.
Two slots allow two concurrent VMs; container capacity still follows the overall count limit.
For Cloud Hypervisor, use `backend: cloud_hypervisor` and its compatible PVH/virtio-PCI kernel and rootfs.
The default boot arguments differ between VMMs; avoid a Firecracker-specific `pci=off` in a shared slot.

## Small development checks

```bash
pytest -q tests/environments/test_remote.py
```

The default tests start a real B subprocess and run real local commands, testing overlap, FIFO, isolation of
working directories, idempotency, lease expiry/heartbeat, auth, timeouts, and failed VM slot release without mocks.
Real Docker/gVisor pair tests are opt-in with `MSWEA_REMOTE_TEST_IMAGE` set to an image already on B.
The real VM pair test is opt-in with `MSWEA_REMOTE_TEST_FIRECRACKER` pointing to a JSON file containing
`{"networks_file": "/srv/mini/network-slots.yaml", "sandbox": {...}}`; it needs two configured slots.
These runtime tests do not silently substitute the local backend when prerequisites are missing.

For a small cross-backend smoke check, set `MSWEA_RUNTIME_TEST_CONFIG` to a JSON file like:

```json
{
  "cases": [
    {"name": "gvisor", "sandbox": {"backend": "gvisor", "image": "python:3.12-slim"}},
    {"name": "incus-container", "sandbox": {"backend": "incus", "image": "images:ubuntu/24.04"}},
    {"name": "incus-vm", "sandbox": {"backend": "incus", "image": "images:ubuntu/24.04", "instance_type": "vm"}}
  ]
}
```

Then run `pytest -q tests/environments/test_runtime_backends.py`. Each case creates just two real instances
and checks concurrent commands, file isolation, environment/cwd/exit codes, and timeout reclamation without
affecting the other instance. Images must have `bash` and `python3`; guests need synchronized wall clocks
for the overlap assertion. Add `networks_file` and complete VM configs for direct VMMs. A case can specify
`sandboxes: [config1, config2]` instead of `sandbox` to check mixed Firecracker/Cloud Hypervisor allocation.
