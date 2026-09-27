# Tool executors

The mini-swe process owns the agent loop, LLM client or ReplayModel, conversation history, and timing.
A tool executor receives a shell command and execution options, and returns its output and exit code.
Container or VM execution applies to the tool command; the agent and model remain in their original process.

```text
Model / ReplayModel -> Agent -> ExecutorEnvironment -> ToolExecutor
                                                        |
                                 Local / Docker / gVisor / Firecracker / Cloud Hypervisor / Incus
                                                        |
                                                actual tool result
```

`ExecutorEnvironment` extracts the command from a parsed action and handles the agent's submission marker.
Executors have no knowledge of messages, tool-call IDs, trajectories, LLM APIs, or submission semantics.
Printing `COMPLETE_TASK_AND_SUBMIT_FINAL_OUTPUT` through an executor returns ordinary text; the environment
adapter interprets it when used in an agent run.

## Direct execution and agent injection

```python
from minisweagent.executors import get_executor
from minisweagent.environments.executor import ExecutorEnvironment

executor = get_executor({"backend": "local", "cwd": "/path/to/workspace"})
try:
    result = executor.execute(
        command="pytest tests/",
        cwd="/path/to/workspace",
        env={"PYTHONUNBUFFERED": "1"},
        timeout=60,
    )
    environment = ExecutorEnvironment(executor=executor)
    # Pass environment to DefaultAgent, JournalAgent, or InteractiveAgent as usual.
finally:
    executor.cleanup()
```

All built-in executors implement:

```python
execute(command: str, cwd: str = "", *, env: dict[str, str] | None = None,
        timeout: float | None = None) -> dict
cleanup() -> None
```

Results contain `output` (combined stdout and stderr), `returncode`, and `exception_info`.
Process launch failures and timeouts return `returncode: -1` with details in `extra` and captured output.
An ordinary command failure retains its exit code. Backend initialization failures propagate to the caller.
The configured backend never falls back to local execution.

`cwd` and `timeout` default to backend configuration. Per-call `env` overrides configured variables without
changing future calls. Local execution inherits the mini-swe process environment; remote commands receive
configured `forward_env` values plus explicit variables. Timeouts kill the local command/client process
group; Docker/SSH/Incus transport termination alone does not guarantee all guest descendants have stopped.
The remote sandbox service retires non-local sandboxes after a command timeout to stop remaining guest work.

Supply a fresh executor dedicated to each environment. Call `environment.cleanup()` after its agent run;
the adapter delegates cleanup to its executor.

## Configuration

This configuration works with the normal mini CLI and replay's `--environment-config`:

```yaml
environment:
  environment_class: executor
  executor:
    backend: docker
    image: your-existing-task-image
    cwd: /testbed
    timeout: 60
```

Flat environment settings inherited from a base config (such as `env`, `cwd`, and `timeout`) supply defaults.
The nested `executor` configuration takes precedence, including individual environment variable values.

Backend-specific initialization settings stay with that backend:

| Backend | Initialization | Command transport |
| --- | --- | --- |
| `local` | Existing local workspace | Local subprocess |
| `docker` | Docker `image`, optional `run_args` | `docker exec` |
| `gvisor` | Docker `image`, registered `runsc` runtime | `docker exec` |
| `firecracker` | Kernel, root drive, TAP, guest SSH settings | SSH into the microVM |
| `cloud_hypervisor` | PVH kernel, root drive, TAP, guest SSH settings | SSH into the VM |
| `incus` | Incus image, project/profiles; `instance_type: container` or `vm` | `incus exec` (VMs use incus-agent) |
| `remote` | B-side sandbox configuration and service endpoint | HTTP to B; B selects any of the isolated backends above |

gVisor follows its [Docker setup](https://gvisor.dev/docs/user_guide/quick_start/docker/), with
`runtime: runsc` by default. Firecracker settings are documented on the [Firecracker page](firecracker.md).
See [Cloud Hypervisor](cloud_hypervisor.md) and [Incus](incus.md) for their distinct prerequisites and configuration.
OCI conversion, a guest model framework, and snapshot pools are outside this interface's scope.
See [remote sandboxes](remote.md) to keep the agent on A while executing tools in concurrent sandboxes on B.

Existing flat configurations such as `environment_class: docker` and Python imports such as
`LocalEnvironment` continue to work. Their adapters use these same executors and retain the original
trajectory metadata shape. Other environment plugins continue to use the existing Environment interface.

## Replay with a different executor

Keep the source trajectory and model timing unchanged and supply a new environment configuration:

```bash
python -m minisweagent.run.replay run \
  --store ./tapes --source source-episode \
  --timing instant --environment-config ./executor.yaml \
  --output ./replayed.index.json
```

Changing the environment class replaces its initialization configuration. Overriding settings on the same
class preserves unspecified settings. The generic adapter's nested `executor` block is replaced as a unit;
provide a complete block when changing its backend. Source metadata is not modified.

Replay returns recorded model replies, executes their tool calls, and records new observations.
Differences in tool output are audited by the existing replay policy. No additional LLM request is made.
For local execution, explicitly provide a fresh workspace; for Docker/gVisor replay, the task image must
already be present. `recorded` and `simulated` timing apply to the model only.

::: minisweagent.environments.executor
